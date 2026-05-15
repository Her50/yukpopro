"""Routes YukpoShop (Phase D) — boutique e-commerce.

Endpoints (tous /api/v1/pro/shop sauf public/) :

  Boutique
  --------
  POST   /shop/initialiser           : crée la boutique du user (1 par user)
  GET    /shop                       : détail boutique du user connecté
  PATCH  /shop                       : maj nom/desc/brand_kit/devise/settings
  POST   /shop/publier               : déploie le storefront sur Netlify
                                       (multi-fichiers, sous-domaine custom)

  Produits
  --------
  GET    /shop/produits              : liste produits paginée
  POST   /shop/produits              : crée un produit manuellement
  GET    /shop/produits/{id}         : détail
  PATCH  /shop/produits/{id}         : maj
  DELETE /shop/produits/{id}         : supprime

  IA Magic
  --------
  POST   /shop/produits/import-ia    : photos N → fiche produit IA complète

  Catégories
  ----------
  GET    /shop/categories
  POST   /shop/categories
  DELETE /shop/categories/{id}

  Commandes (marchand)
  --------------------
  GET    /shop/commandes             : liste commandes
  GET    /shop/commandes/{id}        : détail
  PATCH  /shop/commandes/{id}        : maj statut/notes

  Public (storefront)
  -------------------
  POST   /shop/public/{slug}/orders  : créer commande depuis storefront
                                       (no auth, déclenche notif marchand)
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Path, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import TokenData, get_current_user
from core.database import (
    ShopBoutiqueDB, ShopCategorieDB, ShopMessageDB, ShopOrderDB,
    ShopOrderItemDB, ShopProductCommentDB, ShopProductDB,
    ShopLivraisonZoneDB, async_session_maker,
)

logger = logging.getLogger("yukpo_assurance.api.pro_shop")

router = APIRouter()
router_public = APIRouter()


async def _get_db():
    async with async_session_maker() as session:
        yield session


# ─── Helpers ──────────────────────────────────────────────────────────────────


async def _user_email_nom(user_id: int, db: AsyncSession) -> tuple[str, str]:
    """Retourne (email, nom_affichage) pour un user. Utilisé par le bridge
    Rust (Piste 1) qui a besoin de l'email pour mapper côté Yukpo Rust."""
    from core.database import UtilisateurDB
    u = (await db.execute(
        select(UtilisateurDB).where(UtilisateurDB.id == user_id)
    )).scalar_one_or_none()
    if not u:
        return (f"user{user_id}@yukpo.local", f"User {user_id}")
    nom_aff = " ".join(
        x for x in [getattr(u, "prenoms", None), getattr(u, "nom", None)] if x
    ) or u.username or (u.email.split("@")[0] if u.email else f"User {user_id}")
    return (u.email or f"user{user_id}@yukpo.local", nom_aff)


def _schedule_rust_sync(bg: BackgroundTasks, produit_id: int,
                        vendeur_email: str, vendeur_nom: str) -> None:
    """Programme la publication marketplace Rust en background (non-bloquant).
    Best-effort : aucune erreur ne remonte à l'utilisateur."""
    from modules.pro.yukposhop_rust_bridge import publier_async_safe
    bg.add_task(
        publier_async_safe,
        produit_id=produit_id,
        vendeur_email=vendeur_email,
        vendeur_nom=vendeur_nom,
    )

def _slugify(s: str, maxlen: int = 80) -> str:
    s = re.sub(r"[^a-zA-Z0-9-]+", "-", (s or "").lower().strip())
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return (s or "item")[:maxlen]


async def _get_boutique_du_user(user_id: int, db: AsyncSession) -> ShopBoutiqueDB:
    row = (await db.execute(
        select(ShopBoutiqueDB).where(ShopBoutiqueDB.user_id == user_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Boutique non initialisée — POST /shop/initialiser d'abord")
    return row


_SLUGS_RESERVES = {
    "www", "api", "app", "admin", "blog", "shop", "panier", "checkout",
    "yukpo", "yukpopro", "yukposec",
}


# ─── Schemas ──────────────────────────────────────────────────────────────────


class InitBoutiqueRequest(BaseModel):
    nom: str = Field(..., min_length=2, max_length=120)
    description: Optional[str] = Field(None, max_length=2000)
    devise: str = Field("XAF", pattern=r"^(XAF|XOF|MAD|NGN|EUR|USD|GHS)$")
    pays_principal: str = Field("CM", min_length=2, max_length=8)
    slug_souhaite: Optional[str] = Field(None, max_length=60)


class PatchBoutiqueRequest(BaseModel):
    nom: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    brand_kit_json: Optional[dict] = None
    devise: Optional[str] = None
    pays_principal: Optional[str] = None
    langues_actives_json: Optional[list[str]] = None
    settings_json: Optional[dict] = None
    # Piste 1 — toggle publication marketplace Yukpo Rust (opt-out par boutique)
    rust_sync_enabled: Optional[bool] = None
    # Piste 2 — toggle bloc cross-sell "Autres marchands" dans storefront
    cross_sell_enabled: Optional[bool] = None


class ProduitCreateRequest(BaseModel):
    titre: str = Field(..., min_length=2, max_length=200)
    description_courte: Optional[str] = None
    description_longue: Optional[str] = None
    prix_unit: float = Field(..., ge=0)
    prix_unit_promo: Optional[float] = Field(None, ge=0)
    devise: Optional[str] = None
    tva_pct: float = Field(0, ge=0, le=100)
    stock: int = Field(0, ge=0)
    stock_alerte: int = Field(5, ge=0)
    photos_urls_json: Optional[list[str]] = None
    categorie_id: Optional[int] = None
    tags_json: Optional[list[str]] = None
    variantes_json: Optional[list[dict]] = None
    seo_titre: Optional[str] = None
    seo_desc: Optional[str] = None
    seo_keywords_json: Optional[list[str]] = None
    statut: str = Field("actif", pattern=r"^(actif|brouillon|archive|rupture)$")
    # Piste 6b — vidéo produit (optionnelle) pour VideoFeed mobile Yukpo
    video_url: Optional[str] = Field(None, max_length=500,
        description="URL d'une vidéo produit. Si fournie, le produit "
                    "apparaît dans le VideoFeed mobile Yukpo (~100k users).")
    video_thumbnail_url: Optional[str] = Field(None, max_length=500)


class ProduitPatchRequest(BaseModel):
    titre: Optional[str] = None
    description_courte: Optional[str] = None
    description_longue: Optional[str] = None
    prix_unit: Optional[float] = None
    prix_unit_promo: Optional[float] = None
    tva_pct: Optional[float] = None
    stock: Optional[int] = None
    photos_urls_json: Optional[list[str]] = None
    video_url: Optional[str] = None  # Piste 6b
    video_thumbnail_url: Optional[str] = None  # Piste 6b
    categorie_id: Optional[int] = None
    tags_json: Optional[list[str]] = None
    variantes_json: Optional[list[dict]] = None
    seo_titre: Optional[str] = None
    seo_desc: Optional[str] = None
    statut: Optional[str] = None


class PublierShopRequest(BaseModel):
    confirmer_cout: bool = False


class CategorieCreateRequest(BaseModel):
    nom: str = Field(..., min_length=2, max_length=120)
    parent_id: Optional[int] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    ordre: int = 0


class OrderClientInfo(BaseModel):
    client_nom: str = Field(..., max_length=120)
    client_telephone: str = Field(..., max_length=40)
    client_email: Optional[str] = Field(None, max_length=255)
    ville: Optional[str] = None
    adresse: Optional[str] = None
    provider: str = Field("orange_money",
        pattern=r"^(stripe|flutterwave|orange_money|mtn_momo|wave|campay|cinetpay|cash)$")


class OrderItem(BaseModel):
    id: int
    titre: str
    prix: float
    qte: int = 1
    photo: Optional[str] = None
    variante_label: Optional[str] = None
    variante_json: Optional[dict] = None


class CreerOrderRequest(BaseModel):
    items: list[OrderItem] = Field(..., min_length=1)
    client: OrderClientInfo
    source: str = "storefront"
    utm_source: Optional[str] = None
    utm_campaign: Optional[str] = None
    code_promo: Optional[str] = None


class PatchCommandeRequest(BaseModel):
    statut: Optional[str] = Field(None,
        pattern=r"^(en_attente_paiement|payee|en_preparation|expediee|livree|annulee|remboursee)$")
    notes_marchand: Optional[str] = None
    tracking_url: Optional[str] = None


# ─── Boutique CRUD ────────────────────────────────────────────────────────────


@router.post("/shop/initialiser", summary="Crée la boutique du user (1 par user)")
async def initialiser_boutique(
    req: InitBoutiqueRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    existe = (await db.execute(
        select(ShopBoutiqueDB).where(ShopBoutiqueDB.user_id == current_user.user_id)
    )).scalar_one_or_none()
    if existe:
        return {"ok": True, "deja_existante": True,
                "slug": existe.slug, "id": existe.id}

    slug = _slugify(req.slug_souhaite or req.nom, 60)
    if slug in _SLUGS_RESERVES:
        slug = f"{slug}-{current_user.user_id}"
    # Unicité globale
    suffix = 0
    base = slug
    while True:
        c = (await db.execute(
            select(ShopBoutiqueDB).where(ShopBoutiqueDB.slug == slug)
        )).scalar_one_or_none()
        if not c:
            break
        suffix += 1
        slug = f"{base}-{suffix}"
        if suffix > 50:
            raise HTTPException(409, "Slug en collision — essayez un autre nom")

    boutique = ShopBoutiqueDB(
        user_id=current_user.user_id,
        slug=slug, nom=req.nom, description=req.description,
        devise=req.devise, pays_principal=req.pays_principal,
        langues_actives_json=["fr"], statut="brouillon",
    )
    db.add(boutique)
    await db.commit()
    await db.refresh(boutique)

    # ── Piste 6e — Google Places enrichment (best-effort, non bloquant) ──
    try:
        from modules.pro.yukposhop_rust_boutique import enrichir_boutique_google_places
        # Heuristique : la "ville" n'est pas demandée dans req, donc on tente
        # avec le pays_principal seul. Le marchand peut PATCH plus tard.
        enrich = await enrichir_boutique_google_places(
            nom_boutique=req.nom,
            pays=req.pays_principal,
        )
        if enrich.success:
            boutique.google_place_id = enrich.place_id
            boutique.adresse_complete = enrich.adresse_complete
            boutique.gps = enrich.gps
            boutique.google_rating = enrich.rating
            boutique.telephone = enrich.telephone
            boutique.google_horaires_json = enrich.horaires_json
            boutique.google_enriched_at = datetime.utcnow()
            await db.commit()
            logger.info(
                f"[Shop/init] Google Places enriched : place_id={enrich.place_id} "
                f"adresse={enrich.adresse_complete}"
            )
    except Exception as _e:
        logger.info(f"[Shop/init] Google Places enrich skip ({_e})")

    return {
        "ok": True, "id": boutique.id, "slug": boutique.slug,
        "nom": boutique.nom,
        "url_pressentie": f"https://{boutique.slug}.yukpomnang.com",
        "google_enriched": {
            "adresse": getattr(boutique, "adresse_complete", None),
            "gps": getattr(boutique, "gps", None),
            "rating": getattr(boutique, "google_rating", None),
        },
    }


@router.get("/shop", summary="Détail de ma boutique")
async def get_ma_boutique(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    nb_produits = (await db.execute(
        select(func.count(ShopProductDB.id)).where(ShopProductDB.boutique_id == b.id)
    )).scalar() or 0
    nb_commandes = (await db.execute(
        select(func.count(ShopOrderDB.id)).where(ShopOrderDB.boutique_id == b.id)
    )).scalar() or 0
    return {
        "id": b.id, "slug": b.slug, "nom": b.nom,
        "description": b.description, "logo_url": b.logo_url,
        "banniere_url": b.banniere_url,
        "brand_kit_json": b.brand_kit_json,
        "devise": b.devise, "pays_principal": b.pays_principal,
        "langues_actives": b.langues_actives_json or ["fr"],
        "url_public": b.url_public, "plan": b.plan, "statut": b.statut,
        "settings_json": b.settings_json or {},
        "stats": {"nb_produits": nb_produits, "nb_commandes": nb_commandes},
    }


@router.patch("/shop", summary="Maj de ma boutique")
async def patch_ma_boutique(
    req: PatchBoutiqueRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    data = req.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(b, k, v)
    b.derniere_modif = datetime.utcnow()
    await db.commit()
    return {"ok": True}


# ─── Produits CRUD ────────────────────────────────────────────────────────────


@router.get("/shop/produits", summary="Liste produits de ma boutique")
async def lister_produits(
    statut: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    q = (select(ShopProductDB).where(ShopProductDB.boutique_id == b.id)
         .order_by(desc(ShopProductDB.modif_le)))
    if statut:
        q = q.where(ShopProductDB.statut == statut)
    total = (await db.execute(
        select(func.count(ShopProductDB.id))
        .where(ShopProductDB.boutique_id == b.id)
        .where(ShopProductDB.statut == statut) if statut else
        select(func.count(ShopProductDB.id))
        .where(ShopProductDB.boutique_id == b.id)
    )).scalar() or 0
    q = q.limit(limit).offset(offset)
    rows = (await db.execute(q)).scalars().all()
    return {
        "produits": [_produit_to_dict(p) for p in rows],
        "total": int(total), "limit": limit, "offset": offset,
    }


def _produit_to_dict(p: ShopProductDB) -> dict:
    return {
        "id": p.id, "boutique_id": p.boutique_id, "sku": p.sku,
        "titre": p.titre, "slug": p.slug,
        "description_courte": p.description_courte,
        "description_longue": p.description_longue,
        "prix_unit": float(p.prix_unit), "prix_unit_promo": p.prix_unit_promo,
        "devise": p.devise, "tva_pct": float(p.tva_pct),
        "stock": p.stock, "stock_alerte": p.stock_alerte,
        "photos_urls_json": p.photos_urls_json,
        "categorie_id": p.categorie_id,
        "tags_json": p.tags_json,
        "variantes_json": p.variantes_json,
        "seo_titre": p.seo_titre, "seo_desc": p.seo_desc,
        "seo_keywords_json": p.seo_keywords_json,
        "statut": p.statut, "source": p.source,
        # Piste 6a — enrichissement IA Yukpo Rust (exposé à l'UI)
        "yukpo_category": getattr(p, "yukpo_category", None),
        "yukpo_specialized_type": getattr(p, "yukpo_specialized_type", None),
        "yukpo_tags_json": getattr(p, "yukpo_tags_json", None),
        "yukpo_description_enriched": getattr(p, "yukpo_description_enriched", None),
        "yukpo_quality_score": getattr(p, "yukpo_quality_score", None),
        "yukpo_language_detected": getattr(p, "yukpo_language_detected", None),
        "yukpo_enriched_at": (p.yukpo_enriched_at.isoformat()
                              if getattr(p, "yukpo_enriched_at", None) else None),
        # Piste 6b — vidéo VideoFeed
        "video_url": getattr(p, "video_url", None),
        "video_thumbnail_url": getattr(p, "video_thumbnail_url", None),
        # Piste 6d — modération IA images
        "yukpo_ai_moderation_status": getattr(p, "yukpo_ai_moderation_status", None),
        "yukpo_ai_moderation_reason": getattr(p, "yukpo_ai_moderation_reason", None),
        "cree_le": p.cree_le.isoformat(),
        "modif_le": p.modif_le.isoformat(),
    }


@router.post("/shop/produits", summary="Crée un produit (manuel)")
async def creer_produit(
    req: ProduitCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    slug = _slugify(req.titre, 120)
    # Unicité par boutique
    suffix = 0
    base = slug
    while True:
        c = (await db.execute(
            select(ShopProductDB)
            .where(ShopProductDB.boutique_id == b.id)
            .where(ShopProductDB.slug == slug)
        )).scalar_one_or_none()
        if not c:
            break
        suffix += 1
        slug = f"{base}-{suffix}"

    p = ShopProductDB(
        boutique_id=b.id, slug=slug, titre=req.titre,
        description_courte=req.description_courte,
        description_longue=req.description_longue,
        prix_unit=req.prix_unit, prix_unit_promo=req.prix_unit_promo,
        devise=req.devise or b.devise,
        tva_pct=req.tva_pct, stock=req.stock, stock_alerte=req.stock_alerte,
        photos_urls_json=req.photos_urls_json,
        categorie_id=req.categorie_id, tags_json=req.tags_json,
        variantes_json=req.variantes_json,
        seo_titre=req.seo_titre, seo_desc=req.seo_desc,
        seo_keywords_json=req.seo_keywords_json,
        statut=req.statut, source="manuel",
        video_url=req.video_url,
        video_thumbnail_url=req.video_thumbnail_url,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)

    try:
        from modules.bureau.service_credits_bureau import debiter_forfait_unifie
        await debiter_forfait_unifie(
            current_user.user_id, "client_action", module="shop_produits",
        )
    except Exception:
        pass

    # ── Piste 1 — publication marketplace Yukpo Rust (non-bloquant) ──────
    if p.statut == "actif":
        try:
            email, nom = await _user_email_nom(current_user.user_id, db)
            _schedule_rust_sync(background_tasks, p.id, email, nom)
        except Exception as _e:
            logger.debug(f"[RustBridge] schedule failed produit={p.id}: {_e}")

    return {"ok": True, "produit": _produit_to_dict(p)}


@router.patch("/shop/produits/{produit_id}", summary="Maj produit")
async def patch_produit(
    produit_id: int,
    req: ProduitPatchRequest,
    background_tasks: BackgroundTasks,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    p = (await db.execute(
        select(ShopProductDB)
        .where(ShopProductDB.id == produit_id)
        .where(ShopProductDB.boutique_id == b.id)
    )).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Produit introuvable")
    data = req.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(p, k, v)
    p.modif_le = datetime.utcnow()
    # Si le statut bascule sur "actif" ou le contenu change, on re-marque
    # pending pour ré-indexer côté Rust marketplace.
    fields_qui_invalident_le_sync = {
        "titre", "description_courte", "description_longue", "prix_unit",
        "prix_unit_promo", "devise", "photos_urls_json", "tags_json",
        "statut", "stock",
    }
    if fields_qui_invalident_le_sync & set(data.keys()):
        p.rust_sync_status = "pending"
        # On NE remet PAS attempts à 0 : un commerçant qui modifie 10 fois
        # un produit cassé ne doit pas bypasser le cap MAX_ATTEMPTS.
    await db.commit()

    # ── Piste 1 — re-publication marketplace si actif ────────────────────
    if p.statut == "actif" and (fields_qui_invalident_le_sync & set(data.keys())):
        try:
            email, nom = await _user_email_nom(current_user.user_id, db)
            _schedule_rust_sync(background_tasks, p.id, email, nom)
        except Exception as _e:
            logger.debug(f"[RustBridge] schedule failed produit={p.id}: {_e}")

    return {"ok": True, "produit": _produit_to_dict(p)}


@router.post(
    "/shop/produits/{produit_id}/dupliquer",
    summary="Duplique un produit (clone avec slug -copie-N, statut brouillon)",
)
async def dupliquer_produit(
    produit_id: int,
    background_tasks: BackgroundTasks,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    """Clone un produit dans la même boutique. Le nouveau produit hérite de
    titre/desc/prix/photos/tags/variantes du parent. Statut forcé 'brouillon'
    pour que le commerçant ajuste avant publication. Les champs yukpo_*
    (enrichissement IA) sont VIDÉS — re-calculés au prochain sync Rust.

    NOTE — pas un doublon avec Rust : Rust a aussi `duplicate_product` mais
    il opère sur la table native `service_products` Rust. YukpoShop a sa
    propre table `shop_products` (Python) qui est juste **miroir** côté Rust
    via `external_product_links` (Piste 1). Le clone Python crée donc un
    nouveau `shop_products.id` → BackgroundTask Piste 1 fera le sync vers
    Rust qui créera un service miroir. Pas de duplication de logique.
    """
    b = await _get_boutique_du_user(current_user.user_id, db)
    src = (await db.execute(
        select(ShopProductDB)
        .where(ShopProductDB.id == produit_id)
        .where(ShopProductDB.boutique_id == b.id)
    )).scalar_one_or_none()
    if not src:
        raise HTTPException(404, "Produit source introuvable")

    base_slug = re.sub(r"-copie(-\d+)?$", "", src.slug)
    new_slug = f"{base_slug}-copie"
    suffix = 0
    while True:
        c = (await db.execute(
            select(ShopProductDB).where(ShopProductDB.boutique_id == b.id)
            .where(ShopProductDB.slug == new_slug)
        )).scalar_one_or_none()
        if not c:
            break
        suffix += 1
        new_slug = f"{base_slug}-copie-{suffix}"
        if suffix > 20:
            raise HTTPException(409, "Trop de duplicatas — renommer l'original")

    clone = ShopProductDB(
        boutique_id=b.id, slug=new_slug,
        titre=f"{src.titre} (copie)"[:200],
        description_courte=src.description_courte,
        description_longue=src.description_longue,
        prix_unit=src.prix_unit, prix_unit_promo=src.prix_unit_promo,
        devise=src.devise,
        tva_pct=src.tva_pct, stock=src.stock, stock_alerte=src.stock_alerte,
        photos_urls_json=src.photos_urls_json,
        video_url=src.video_url, video_thumbnail_url=src.video_thumbnail_url,
        categorie_id=src.categorie_id, tags_json=src.tags_json,
        variantes_json=src.variantes_json,
        seo_titre=src.seo_titre, seo_desc=src.seo_desc,
        seo_keywords_json=src.seo_keywords_json,
        statut="brouillon",
        source="dupliqué",
    )
    db.add(clone)
    await db.commit()
    await db.refresh(clone)
    return {"ok": True, "produit": _produit_to_dict(clone)}


@router.post(
    "/shop/produits/{produit_id}/generer-video",
    summary="Génère une vidéo pub IA pour un produit via Yukpo Rust Remotion",
)
async def generer_video_produit(
    produit_id: int,
    ton: Optional[str] = Form("dynamique"),
    duree_s: int = Form(15, ge=5, le=60),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    """Génère une vidéo publicitaire courte (5-60s) à partir des photos
    du produit, via le pipeline Remotion + IA de Yukpo Rust. La vidéo
    est sauvegardée et son URL est stockée dans `shop_products.video_url`,
    rendant le produit éligible au VideoFeed mobile Yukpo (Piste 6b)."""
    b = await _get_boutique_du_user(current_user.user_id, db)
    p = (await db.execute(
        select(ShopProductDB)
        .where(ShopProductDB.id == produit_id)
        .where(ShopProductDB.boutique_id == b.id)
    )).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Produit introuvable")
    if not p.photos_urls_json:
        raise HTTPException(400, "Pas de photos sur ce produit — uploader d'abord 1-5 photos")

    try:
        from modules.pro.yukposhop_rust_video import generer_video_produit_via_rust
        res = await generer_video_produit_via_rust(
            produit=p, ton=ton or "dynamique", duree_s=duree_s,
        )
        if res.success and res.video_url:
            p.video_url = res.video_url
            if res.thumbnail_url:
                p.video_thumbnail_url = res.thumbnail_url
            await db.commit()
            return {
                "ok": True, "video_url": res.video_url,
                "thumbnail_url": res.thumbnail_url, "duration_s": res.duration_s,
                "duree_render_s": res.duree_render_s,
            }
        raise HTTPException(502, res.error or "Génération vidéo échouée")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erreur génération vidéo : {str(e)[:200]}")


@router.delete("/shop/produits/{produit_id}", summary="Supprime un produit")
async def supprimer_produit(
    produit_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    p = (await db.execute(
        select(ShopProductDB)
        .where(ShopProductDB.id == produit_id)
        .where(ShopProductDB.boutique_id == b.id)
    )).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Produit introuvable")
    await db.execute(
        ShopProductDB.__table__.delete().where(ShopProductDB.id == produit_id)
    )
    await db.commit()
    return {"ok": True}


# ─── Piste 1 — Re-publication marketplace Yukpo Rust ────────────────────────

@router.post(
    "/shop/produits/{produit_id}/republier-rust",
    summary="Piste 1 — Force la re-publication d'un produit dans le marketplace Yukpo Rust",
)
async def republier_produit_rust(
    produit_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    """Sync manuel — utile si :
    - la sync auto a échoué (rust_sync_status = 'failed')
    - le marchand veut re-pousser après modif majeure (titre, prix, photos)
    - le MAX_ATTEMPTS a été atteint et il faut forcer un retry

    Reset rust_sync_attempts à 0 pour bypass le cap. Retourne le résultat
    sync (synchrone — l'user voit l'erreur si Rust est down).
    """
    b = await _get_boutique_du_user(current_user.user_id, db)
    p = (await db.execute(
        select(ShopProductDB)
        .where(ShopProductDB.id == produit_id)
        .where(ShopProductDB.boutique_id == b.id)
    )).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Produit introuvable")
    if p.statut != "actif":
        raise HTTPException(400, f"Produit doit être 'actif' (actuel : {p.statut})")
    if not getattr(b, "rust_sync_enabled", True):
        raise HTTPException(400, "Sync marketplace désactivée pour cette boutique. "
                                  "Active-la via PATCH /shop avec rust_sync_enabled=true.")

    # Reset le compteur pour autoriser un retry frais
    p.rust_sync_attempts = 0
    p.rust_sync_status = "pending"
    p.rust_sync_error = None
    await db.commit()

    from modules.pro.yukposhop_rust_bridge import publier_produit_vers_rust
    email, nom = await _user_email_nom(current_user.user_id, db)
    result = await publier_produit_vers_rust(
        produit_id=p.id, db=db, vendeur_email=email, vendeur_nom=nom,
    )
    return {
        "ok": result.success,
        "rust_service_id": result.rust_service_id,
        "error": result.error,
        "http_status": result.http_status,
        "duration_ms": result.duration_ms,
    }


@router.get(
    "/shop/social/status",
    summary="Piste 4 — État des comptes sociaux connectés via Yukpo Rust",
)
async def shop_social_status(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    """Retourne quels comptes Meta/IG/WA/TikTok/YouTube le commerçant a
    connecté côté Yukpo (l'app principale Rust). Si rien, l'UI affiche
    un bouton 'Connecter Meta' redirigeant vers le flow OAuth Rust."""
    email, _ = await _user_email_nom(current_user.user_id, db)
    from modules.pro.yukposhop_rust_social import get_social_status
    res = await get_social_status(email)
    return {
        "ok": res.ok,
        "vendeur_email": email,
        "rust_user_id": res.rust_user_id,
        "platforms": [
            {"platform": p.platform, "account_name": p.account_name,
             "is_active": p.is_active}
            for p in res.platforms
        ],
        "connect_url": res.connect_url,
        "error": res.error,
    }


class ShopSocialDistributeRequest(BaseModel):
    produit_ids: list[int] = Field(..., min_length=1, max_length=50)
    platforms: list[str] = Field(..., min_length=1, max_length=8,
        description="ex: ['facebook', 'instagram', 'whatsapp']")
    message_template: Optional[str] = Field(None, max_length=2000)


@router.post(
    "/shop/social/distribute",
    summary="Piste 4 — Publie N produits YukpoShop vers les comptes sociaux via Yukpo Rust",
)
async def shop_social_distribute(
    req: ShopSocialDistributeRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    """Déclenche une distribution sociale via Rust. Le caller doit fournir
    les ID locaux YukpoShop (shop_products.id) — Rust les résout via
    `external_product_links` (Piste 1).

    Pré-requis : les produits doivent être sync vers Rust (Piste 1),
    sinon Rust ne sait pas à quoi correspondent ces IDs.
    """
    b = await _get_boutique_du_user(current_user.user_id, db)
    # Vérifie ownership des produits
    produits_owned = (await db.execute(
        select(ShopProductDB.id)
        .where(ShopProductDB.id.in_(req.produit_ids))
        .where(ShopProductDB.boutique_id == b.id)
    )).scalars().all()
    if not produits_owned:
        raise HTTPException(404, "Aucun de ces produits n'appartient à votre boutique")
    if len(produits_owned) != len(req.produit_ids):
        missing = set(req.produit_ids) - set(produits_owned)
        raise HTTPException(403,
            f"Produits non possédés ou inexistants : {sorted(missing)}")

    email, _ = await _user_email_nom(current_user.user_id, db)
    from modules.pro.yukposhop_rust_social import distribuer_produits
    res = await distribuer_produits(
        vendeur_email=email,
        produit_ids=list(produits_owned),
        platforms=req.platforms,
        message_template=req.message_template,
    )
    if not res.success:
        # 502 si Rust pas joignable, 400 si Rust a refusé
        status = 502 if res.error and "réseau" in res.error else 400
        raise HTTPException(status,
            res.error or res.note or "Distribution échouée")
    return {
        "ok": True,
        "jobs_created": res.jobs_created,
        "products_resolved": res.products_resolved,
        "platforms": res.platforms,
        "note": res.note,
    }


@router.post(
    "/shop/google-enrich",
    summary="Piste 6e — Re-enrichit ma boutique avec Google Places (manuel)",
)
async def shop_google_enrich(
    ville: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    """Re-déclenche l'enrichissement Google Places — utile si le commerçant
    a corrigé le nom de sa boutique ou ajoute la ville pour précision."""
    b = await _get_boutique_du_user(current_user.user_id, db)
    from modules.pro.yukposhop_rust_boutique import enrichir_boutique_google_places
    res = await enrichir_boutique_google_places(
        nom_boutique=b.nom, ville=ville, pays=b.pays_principal,
    )
    if res.success:
        b.google_place_id = res.place_id
        b.adresse_complete = res.adresse_complete
        b.gps = res.gps
        b.google_rating = res.rating
        if res.telephone:
            b.telephone = res.telephone
        if res.horaires_json:
            b.google_horaires_json = res.horaires_json
        b.google_enriched_at = datetime.utcnow()
        await db.commit()
    return {
        "ok": res.success,
        "place_id": res.place_id,
        "adresse_complete": res.adresse_complete,
        "gps": res.gps,
        "rating": res.rating,
        "telephone": res.telephone,
        "photo_url": res.photo_url,
        "error": res.error,
    }


@router.get(
    "/shop/produits/{produit_id}/similar",
    summary="Piste 6c — Produits similaires via marketplace Yukpo Rust (embeddings + catégorie)",
)
async def produit_similar(
    produit_id: int,
    limit: int = 6,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    """Retourne N produits similaires depuis le marketplace Yukpo Rust.

    Stratégie :
    - Si le produit a `yukpo_category` + `yukpo_specialized_type` (enrichis
      via Piste 6a) : on les utilise comme query pour cibler finement.
    - Sinon fallback sur le titre brut du produit.
    - Exclut les produits venant de YukpoShop (filtre external_source).

    À utiliser pour :
    - section "Vous aimerez aussi" sur la page produit storefront
    - dashboard commerçant "Produits similaires dans le marketplace"
    """
    b = await _get_boutique_du_user(current_user.user_id, db)
    p = (await db.execute(
        select(ShopProductDB).where(ShopProductDB.id == produit_id)
        .where(ShopProductDB.boutique_id == b.id)
    )).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Produit introuvable")

    # Compose la query en priorisant les enrichissements IA
    parts = []
    if getattr(p, "yukpo_specialized_type", None):
        parts.append(p.yukpo_specialized_type)
    if getattr(p, "yukpo_category", None):
        parts.append(p.yukpo_category)
    if not parts:
        parts.append(p.titre[:80])
    query = " ".join(parts)[:200]

    categories = getattr(p, "yukpo_category", None) or \
                 "ecommerce,supermarche,mode,electronique,sport,maison"

    from modules.pro.yukposhop_rust_search import chercher_services_marketplace
    items = await chercher_services_marketplace(
        query=query, limit=max(1, min(limit, 12)),
        categories=categories,
        # exclude_external_source par défaut = yukposhop → pas d'auto-reco
    )
    return {
        "ok": True, "produit_id": produit_id,
        "query_used": query, "category_used": categories,
        "nb_items": len(items), "items": items,
    }


@router.get(
    "/shop/cross-sell/preview",
    summary="Piste 2 — Preview des items cross-sell marketplace pour ma boutique",
)
async def cross_sell_preview(
    q: Optional[str] = None,
    limit: int = 6,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    """Permet de tester ce que la search Rust marketplace renverra pour la
    catégorie principale de la boutique. Utile pour valider l'intégration
    avant de re-publier le storefront entier."""
    b = await _get_boutique_du_user(current_user.user_id, db)
    if not getattr(b, "cross_sell_enabled", True):
        return {
            "ok": True, "boutique_id": b.id, "enabled": False,
            "items": [],
            "message": "Cross-sell désactivé pour cette boutique (PATCH /shop avec cross_sell_enabled=true)",
        }
    categories = (await db.execute(
        select(ShopCategorieDB).where(ShopCategorieDB.boutique_id == b.id)
        .order_by(ShopCategorieDB.ordre).limit(3)
    )).scalars().all()
    query = q or (", ".join([c.nom for c in categories]) or b.nom)
    from modules.pro.yukposhop_rust_search import chercher_services_marketplace
    items = await chercher_services_marketplace(
        query=query, limit=max(1, min(limit, 20)),
        categories="ecommerce,supermarche,mode,electronique,sport,maison",
    )
    return {
        "ok": True, "boutique_id": b.id, "enabled": True,
        "query_used": query, "nb_items": len(items),
        "items": items,
    }


@router.get(
    "/shop/rust-sync/stats",
    summary="Piste 1 — Stats de publication marketplace Yukpo Rust",
)
async def rust_sync_stats(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    """Dashboard : combien de produits sont synced / failed / pending côté Rust."""
    b = await _get_boutique_du_user(current_user.user_id, db)
    rows = (await db.execute(
        select(ShopProductDB.rust_sync_status, func.count(ShopProductDB.id))
        .where(ShopProductDB.boutique_id == b.id)
        .group_by(ShopProductDB.rust_sync_status)
    )).all()
    stats = {row[0]: int(row[1]) for row in rows}
    return {
        "ok": True,
        "boutique_id": b.id,
        "rust_sync_enabled": bool(getattr(b, "rust_sync_enabled", True)),
        "stats": stats,
        "total": sum(stats.values()),
    }


# ─── D2 — Magic Import IA depuis photos ──────────────────────────────────────


@router.post(
    "/shop/produits/import-ia",
    summary="Phase D2 — Photos → fiche produit IA complète (Opus Vision)",
)
async def import_ia_produit(
    photos: list[UploadFile] = File(..., description="1-10 photos du produit"),
    brief: str = Form(""),
    categorie_hint: Optional[str] = Form(None),
    auto_save: bool = Form(True, description="Si True, sauve le produit en brouillon ; sinon retourne juste la fiche"),
    confirmer_cout: bool = Form(False),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    """Pipeline magic :
       1. Lecture des N photos (1-10) et conversion base64
       2. LLM Vision Opus compose la fiche produit complète
       3. Persistance en brouillon (modifiable ensuite via PATCH)
    """
    from api.routes_pro_generateurs import _pre_check_credits
    await _pre_check_credits(current_user.user_id, role=current_user.role)

    if not confirmer_cout:
        from core.cost_advisor import advisor, estimer_cout_module, AdvisorAction
        # Vision Opus + 10 photos + 16k tokens = lourd
        cout = estimer_cout_module("shop_magic_import", multiplicateur=max(1.0, len(photos) / 5.0))
        v = await advisor.evaluer(current_user.user_id, cout, module="shop_magic_import")
        if v.action in (AdvisorAction.BLOCK, AdvisorAction.CONFIRM):
            raise HTTPException(402, v.detail_pour_402())

    b = await _get_boutique_du_user(current_user.user_id, db)
    photos = photos[:10]
    photos_b64 = []
    photos_data_uris_persistees = []
    import base64
    for f in photos:
        content = await f.read()
        if len(content) > 8 * 1024 * 1024:
            raise HTTPException(413, f"Photo {f.filename} > 8 MB")
        mime = f.content_type or "image/jpeg"
        b64 = base64.b64encode(content).decode()
        data_uri = f"data:{mime};base64,{b64}"
        photos_b64.append(data_uri)
        photos_data_uris_persistees.append(data_uri)

    from modules.pro.shop_builder import magic_import_depuis_photos
    try:
        produit_data, usages = await magic_import_depuis_photos(
            photos_b64, brief_optionnel=brief,
            categorie_hint=categorie_hint,
            pays=b.pays_principal, devise=b.devise,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"[Shop/import-ia] LLM échec user={current_user.user_id}: {e}")
        raise HTTPException(500, f"Erreur IA : {str(e)[:200]}")

    # Débit LLM
    try:
        from modules.bureau.service_credits_bureau import debiter_llm_unifie
        for u in usages:
            await debiter_llm_unifie(
                user_id=current_user.user_id,
                modele=u.get("modele", "claude-opus-4-7"),
                tokens_input=int(u.get("tokens_in", 0)),
                tokens_output=int(u.get("tokens_out", 0)),
                module="shop_magic_import",
            )
    except Exception:
        pass

    produit_data["photos_urls_json"] = photos_data_uris_persistees
    produit_data["devise"] = b.devise

    if auto_save:
        slug = _slugify(
            produit_data.get("slug") or produit_data.get("titre", "produit"), 120,
        )
        # Unicité
        suffix = 0
        base = slug
        while True:
            c = (await db.execute(
                select(ShopProductDB)
                .where(ShopProductDB.boutique_id == b.id)
                .where(ShopProductDB.slug == slug)
            )).scalar_one_or_none()
            if not c:
                break
            suffix += 1
            slug = f"{base}-{suffix}"

        p = ShopProductDB(
            boutique_id=b.id, slug=slug,
            titre=produit_data.get("titre", "Produit")[:200],
            description_courte=produit_data.get("description_courte"),
            description_longue=produit_data.get("description_longue"),
            prix_unit=float(produit_data.get("prix_suggere") or 0),
            devise=b.devise, tva_pct=0,
            stock=int(produit_data.get("stock_initial_suggere") or 10),
            stock_alerte=5,
            photos_urls_json=photos_data_uris_persistees,
            tags_json=produit_data.get("tags"),
            variantes_json=produit_data.get("variantes_detectees"),
            seo_titre=produit_data.get("seo_titre"),
            seo_desc=produit_data.get("seo_desc"),
            seo_keywords_json=produit_data.get("seo_keywords"),
            statut="brouillon",  # à valider par le marchand
            source="import_ia",
        )
        db.add(p)
        await db.commit()
        await db.refresh(p)
        return {"ok": True, "produit": _produit_to_dict(p), "spec_ia": produit_data}

    return {"ok": True, "spec_ia": produit_data}


# ─── Catégories ──────────────────────────────────────────────────────────────


@router.get("/shop/categories", summary="Liste catégories")
async def lister_categories(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    cats = (await db.execute(
        select(ShopCategorieDB)
        .where(ShopCategorieDB.boutique_id == b.id)
        .order_by(ShopCategorieDB.ordre)
    )).scalars().all()
    return {
        "categories": [
            {"id": c.id, "nom": c.nom, "slug": c.slug,
             "parent_id": c.parent_id, "ordre": c.ordre,
             "description": c.description, "image_url": c.image_url}
            for c in cats
        ]
    }


@router.post("/shop/categories", summary="Crée une catégorie")
async def creer_categorie(
    req: CategorieCreateRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    slug = _slugify(req.nom, 80)
    c = ShopCategorieDB(
        boutique_id=b.id, nom=req.nom, slug=slug,
        parent_id=req.parent_id, ordre=req.ordre,
        description=req.description, image_url=req.image_url,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return {"ok": True, "id": c.id, "slug": c.slug}


@router.delete("/shop/categories/{cat_id}", summary="Supprime catégorie")
async def supprimer_categorie(
    cat_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    await db.execute(
        ShopCategorieDB.__table__.delete()
        .where(ShopCategorieDB.id == cat_id)
        .where(ShopCategorieDB.boutique_id == b.id)
    )
    await db.commit()
    return {"ok": True}


# ─── Publier le storefront (D3) ──────────────────────────────────────────────


@router.post(
    "/shop/publier",
    summary="Phase D3 — Déploie le storefront sur Netlify (multi-fichiers)",
)
async def publier_shop(
    req: PublierShopRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    from api.routes_pro_generateurs import _pre_check_credits
    await _pre_check_credits(current_user.user_id, role=current_user.role)

    if not req.confirmer_cout:
        from core.cost_advisor import advisor, estimer_cout_module, AdvisorAction
        cout = estimer_cout_module("site_publish")
        v = await advisor.evaluer(current_user.user_id, cout, module="shop_publish")
        if v.action in (AdvisorAction.BLOCK, AdvisorAction.CONFIRM):
            raise HTTPException(402, v.detail_pour_402())

    b = await _get_boutique_du_user(current_user.user_id, db)

    from modules.pro.landing_publisher import (
        publier_site_multipage, is_active as _netlify_active, NetlifyError,
    )
    if not _netlify_active():
        raise HTTPException(503, "NETLIFY_API_TOKEN non configuré")

    produits = (await db.execute(
        select(ShopProductDB).where(ShopProductDB.boutique_id == b.id)
    )).scalars().all()
    categories = (await db.execute(
        select(ShopCategorieDB)
        .where(ShopCategorieDB.boutique_id == b.id)
        .order_by(ShopCategorieDB.ordre)
    )).scalars().all()

    boutique_dict = {
        "id": b.id, "slug": b.slug, "nom": b.nom,
        "description": b.description, "logo_url": b.logo_url,
        "brand_kit_json": b.brand_kit_json,
        "devise": b.devise, "pays_principal": b.pays_principal,
        "langue_principale": (b.langues_actives_json or ["fr"])[0],
        "url_public": b.url_public,
    }
    produits_dicts = [_produit_to_dict(p) for p in produits]
    cats_dicts = [
        {"id": c.id, "nom": c.nom, "slug": c.slug, "image_url": c.image_url}
        for c in categories
    ]

    from modules.pro.shop_builder import construire_arborescence_storefront
    api_base = os.getenv("YUKPO_PUBLIC_API_BASE", "").strip()

    # ── Piste 2 — fetch cross-sell marketplace Yukpo Rust (best-effort) ─
    cross_sell_items: list[dict] = []
    if getattr(b, "cross_sell_enabled", True):
        try:
            from modules.pro.yukposhop_rust_search import chercher_services_marketplace
            # Query basée sur catégories de la boutique sinon nom boutique.
            # Limite 6 cards (responsive grid 6 cols max).
            query = ", ".join(
                [c.nom for c in categories[:3]]
            ) or b.nom
            # GPS commerçant : pour l'instant on n'a pas la lat/lng dans
            # shop_boutiques (seulement pays_principal). On laisse Rust
            # ranker par recency+full-text. Une future migration ajoutera
            # boutique.lat/lng pour rayon GPS précis.
            cross_sell_items = await chercher_services_marketplace(
                query=query, limit=6,
                # Filtre sur catégories e-commerce pertinentes pour shop
                categories="ecommerce,supermarche,mode,electronique,sport,maison",
            )
            logger.info(
                f"[Shop/publier] cross-sell : {len(cross_sell_items)} items "
                f"fetched (query={query[:50]!r})"
            )
        except Exception as _e:
            logger.warning(f"[Shop/publier] cross-sell fetch échec (non bloquant) : {_e}")

    files = construire_arborescence_storefront(
        boutique_dict, produits=produits_dicts,
        categories=cats_dicts, api_base=api_base,
        cross_sell_items=cross_sell_items,
    )

    try:
        res = await publier_site_multipage(
            files, b.slug, site_id_existant=b.netlify_site_id,
        )
    except NetlifyError as e:
        _msg = str(e)
        # Rate-limit Netlify (free 100 sites/24h, pro 500/24h). L'utilisateur
        # ne peut rien y faire à part attendre que le plafond se réinit (~24h).
        # On retourne un 429 explicite + message FR clair.
        if "429" in _msg or "rate limit" in _msg.lower():
            logger.warning(
                f"[Shop/publier] Netlify rate-limit atteint (user={current_user.user_id}, "
                f"slug={b.slug}) → 429 frontend."
            )
            raise HTTPException(
                429,
                "Plafond quotidien Netlify atteint sur la plateforme "
                "(100 sites/24h). La publication se relancera "
                "automatiquement demain dès la réinitialisation. Tu peux "
                "continuer à éditer ta boutique en brouillon en attendant.",
            )
        raise HTTPException(502, f"Erreur publication : {_msg[:200]}")

    if res.get("is_new"):
        b.netlify_site_id = res["site_id"]
        b.url_public = res["url_public"] or f"https://{b.slug}.yukpomnang.com"
        b.publie_le = datetime.utcnow()
    b.statut = "publie"
    b.derniere_modif = datetime.utcnow()
    await db.commit()

    # Débit forfait
    try:
        from modules.bureau.service_credits_bureau import debiter_forfait_unifie
        await debiter_forfait_unifie(
            current_user.user_id, "pdf_generation",
            module="shop_publish",
            multiplicateur=max(1.0, len(produits_dicts) / 10.0),
        )
    except Exception:
        pass

    # ── SEO référencement automatique : ping IndexNow ────────────────────
    # Soumet l'URL home + toutes les URLs produits aux moteurs IndexNow
    # (Bing, Yandex, Naver, Seznam). Indexation typiquement 2-7 jours.
    # Google ne supporte pas officiellement IndexNow mais ses crawlers
    # peuvent capter le signal indirect. Best-effort, jamais bloquant.
    indexnow_result = None
    try:
        from modules.pro.seo_referencing import ping_indexnow, get_indexnow_key
        if get_indexnow_key():
            host = (b.url_public or f"https://{b.slug}.yukpomnang.com").replace("https://", "").replace("http://", "").strip("/")
            base = b.url_public or f"https://{b.slug}.yukpomnang.com"
            urls = [base + "/"]
            urls += [f"{base}/p/{p.slug}" for p in produits if p.statut == "actif"][:50]
            urls += [f"{base}/c/{c.slug}" for c in categories][:20]
            indexnow_result = await ping_indexnow(host, urls)
            if indexnow_result.get("ok"):
                logger.info(
                    f"[Shop/publier] IndexNow {len(urls)} URLs soumises "
                    f"({indexnow_result['status']}) → indexation 2-7j Bing/Yandex/Naver"
                )
            else:
                logger.info(f"[Shop/publier] IndexNow KO : {indexnow_result.get('error')}")
        else:
            indexnow_result = {"ok": False,
                "error": "INDEXNOW_KEY non configurée (configure-la pour activer auto-indexation Bing/Yandex)"}
    except Exception as _e:
        logger.warning(f"[Shop/publier] IndexNow non bloquant : {_e}")

    return {
        "ok": True, "slug": b.slug, "url_public": b.url_public,
        "nb_produits": len(produits_dicts),
        "nb_categories": len(cats_dicts),
        "seo": {
            "indexnow": indexnow_result,
            "sitemap_url": f"{b.url_public or f'https://{b.slug}.yukpomnang.com'}/sitemap.xml",
            "google_merchant_feed_url": f"{b.url_public or f'https://{b.slug}.yukpomnang.com'}/feed/google.xml",
            "instructions": {
                "google_search_console": "Soumets le sitemap_url dans Google Search Console (1 fois) → indexation Google ~7-30j",
                "google_merchant": "Soumets google_merchant_feed_url dans Google Merchant Center → onglet Shopping Google",
                "indexnow_status": indexnow_result.get("ok") if indexnow_result else False,
            },
        },
    }


# ─── Commandes marchand ──────────────────────────────────────────────────────


@router.get("/shop/commandes", summary="Liste commandes du marchand")
async def lister_commandes(
    statut: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    q = (select(ShopOrderDB).where(ShopOrderDB.boutique_id == b.id)
         .order_by(desc(ShopOrderDB.cree_le)))
    if statut:
        q = q.where(ShopOrderDB.statut == statut)
    q = q.limit(limit).offset(offset)
    rows = (await db.execute(q)).scalars().all()
    return {
        "commandes": [_order_to_dict(o) for o in rows],
    }


def _order_to_dict(o: ShopOrderDB) -> dict:
    return {
        "id": o.id, "numero": o.numero,
        "client_nom": o.client_nom, "client_email": o.client_email,
        "client_telephone": o.client_telephone,
        "montant_total": float(o.montant_total), "devise": o.devise,
        "statut": o.statut, "paiement_statut": o.paiement_statut,
        "paiement_provider": o.paiement_provider,
        "source": o.source, "cree_le": o.cree_le.isoformat(),
        "paye_le": o.paye_le.isoformat() if o.paye_le else None,
    }


@router.get("/shop/commandes/{order_id}", summary="Détail commande")
async def detail_commande(
    order_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    o = (await db.execute(
        select(ShopOrderDB)
        .where(ShopOrderDB.id == order_id)
        .where(ShopOrderDB.boutique_id == b.id)
    )).scalar_one_or_none()
    if not o:
        raise HTTPException(404, "Commande introuvable")
    items = (await db.execute(
        select(ShopOrderItemDB).where(ShopOrderItemDB.order_id == o.id)
    )).scalars().all()
    return {
        "commande": _order_to_dict(o),
        "items": [{
            "id": it.id, "titre": it.titre, "quantite": it.quantite,
            "prix_unit": float(it.prix_unit), "variante_label": it.variante_label,
            "photo_url": it.photo_url,
        } for it in items],
        "adresse_livraison": o.adresse_livraison_json,
        "notes_marchand": o.notes_marchand, "notes_client": o.notes_client,
    }


@router.patch("/shop/commandes/{order_id}", summary="Maj statut commande")
async def patch_commande(
    order_id: int,
    req: PatchCommandeRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    o = (await db.execute(
        select(ShopOrderDB)
        .where(ShopOrderDB.id == order_id)
        .where(ShopOrderDB.boutique_id == b.id)
    )).scalar_one_or_none()
    if not o:
        raise HTTPException(404, "Commande introuvable")
    if req.statut is not None:
        o.statut = req.statut
        if req.statut == "expediee":
            o.expedie_le = datetime.utcnow()
        elif req.statut == "livree":
            o.livre_le = datetime.utcnow()
    if req.notes_marchand is not None:
        o.notes_marchand = req.notes_marchand
    if req.tracking_url is not None:
        o.tracking_url = req.tracking_url
    o.modif_le = datetime.utcnow()
    await db.commit()
    return {"ok": True}


# ─── Endpoint PUBLIC création commande (depuis storefront) ───────────────────


@router_public.post(
    "/{slug}/orders",
    summary="Phase D — Créer commande depuis storefront public (no auth)",
)
async def creer_order_public(
    slug: str = Path(..., min_length=3, max_length=60,
                     pattern=r"^[a-z0-9][a-z0-9-]{1,58}[a-z0-9]$"),
    payload: CreerOrderRequest = ...,
    db: AsyncSession = Depends(_get_db),
):
    b = (await db.execute(
        select(ShopBoutiqueDB).where(ShopBoutiqueDB.slug == slug)
    )).scalar_one_or_none()
    if not b:
        raise HTTPException(404, "Boutique introuvable")
    if b.statut != "publie":
        raise HTTPException(403, "Boutique non publiée")

    # Calcul montants
    montant_produits = sum(it.prix * it.qte for it in payload.items)
    montant_total = montant_produits  # TODO : livraison + tva + promo

    numero = f"YK-{datetime.utcnow().year}-{int(time.time()) % 1000000:06d}"

    adresse = {
        "ville":     payload.client.ville,
        "adresse":   payload.client.adresse,
    }

    order = ShopOrderDB(
        boutique_id=b.id, numero=numero,
        client_nom=payload.client.client_nom,
        client_email=payload.client.client_email,
        client_telephone=payload.client.client_telephone,
        adresse_livraison_json=adresse,
        montant_produits=montant_produits,
        montant_total=montant_total,
        devise=b.devise,
        paiement_provider=payload.client.provider,
        source=payload.source,
        utm_source=payload.utm_source,
        utm_campaign=payload.utm_campaign,
        code_promo=payload.code_promo,
    )
    db.add(order)
    await db.flush()

    # ── Piste 5 : décrément stock local + collecte pour push Rust ────────
    decrements_pour_rust: list[tuple[int, int]] = []  # (product_id, qte)
    for it in payload.items:
        db.add(ShopOrderItemDB(
            order_id=order.id, product_id=it.id,
            titre=it.titre, quantite=it.qte, prix_unit=it.prix,
            photo_url=it.photo, variante_label=it.variante_label,
            variante_json=it.variante_json,
        ))
        # Décrément stock local (best-effort, n'empêche pas l'order)
        if it.id and it.qte > 0:
            try:
                p = (await db.execute(
                    select(ShopProductDB).where(ShopProductDB.id == it.id)
                )).scalar_one_or_none()
                if p:
                    p.stock = max(0, (p.stock or 0) - it.qte)
                    decrements_pour_rust.append((it.id, it.qte))
            except Exception as _e:
                logger.warning(f"[Order] décrément stock local échec produit={it.id}: {_e}")

    await db.commit()
    await db.refresh(order)

    # Push décrément vers Rust marketplace (best-effort, non bloquant)
    if decrements_pour_rust:
        try:
            from modules.pro.yukposhop_rust_inventory import decrementer_stock_rust
            for produit_id, qte in decrements_pour_rust:
                _r = await decrementer_stock_rust(
                    produit_id=produit_id, quantite=qte,
                    order_numero=numero,
                )
                if not _r.success:
                    logger.info(
                        f"[Order] sync inventaire Rust échec produit={produit_id} "
                        f"event_id={_r.event_id} err={_r.error}"
                    )
        except Exception as _e:
            logger.warning(f"[Order] push inventaire Rust échec global : {_e}")

    # Débit forfait sur le marchand pour la commande capturée
    try:
        from modules.bureau.service_credits_bureau import debiter_forfait_unifie
        await debiter_forfait_unifie(
            b.user_id, "client_action", module="shop_order",
        )
    except Exception:
        pass

    # Notif marchand WA prioritaire + SMS fallback
    try:
        from core.notifications import notifier_telephone
        from core.database import UtilisateurDB
        marchand = (await db.execute(
            select(UtilisateurDB).where(UtilisateurDB.id == b.user_id)
        )).scalar_one_or_none()
        if marchand and marchand.telephone:
            items_summary = " · ".join(
                f"{it.qte}× {it.titre[:40]}" for it in payload.items[:5]
            )
            contenu = (
                f"🛒 Nouvelle commande {numero}\n\n"
                f"Client : {payload.client.client_nom}\n"
                f"Tel : {payload.client.client_telephone}\n"
                f"Ville : {payload.client.ville or '—'}\n"
                f"Articles : {items_summary}\n"
                f"Total : {int(montant_total)} {b.devise}\n"
                f"Paiement : {payload.client.provider}\n\n"
                f"Gérer : https://yukpopro.yukpomnang.com/ma-boutique/commandes/{order.id}"
            )
            await notifier_telephone(
                marchand.telephone, contenu,
                metadata={"type": "shop_order", "numero": numero},
                prefer="whatsapp",
            )
            await debiter_forfait_unifie(
                b.user_id, "whatsapp_message", module="shop_order_notif",
            )
    except Exception as _e:
        logger.warning(f"[Shop/order] notif échec : {_e}")

    # Démarrage paiement (si pas cash) — branchement paiement v2 existant
    paiement_url = None
    if payload.client.provider != "cash":
        try:
            paiement_url = await _initier_paiement_v2(
                order=order, boutique=b, db=db, provider=payload.client.provider,
            )
        except Exception as e:
            logger.warning(f"[Shop/order] init paiement échec : {e}")

    return {
        "ok": True, "numero": numero, "order_id": order.id,
        "montant_total": montant_total, "devise": b.devise,
        "paiement_url": paiement_url,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Q1 — Commentaires produits + Messages visiteur ↔ vendeur
# ═══════════════════════════════════════════════════════════════════════════


class CommentairePublicIn(BaseModel):
    author_nom: str = Field(..., min_length=1, max_length=120)
    author_telephone: Optional[str] = Field(None, max_length=40)
    author_email: Optional[str] = Field(None, max_length=150)
    contenu: str = Field(..., min_length=2, max_length=2000)
    note: Optional[int] = Field(None, ge=1, le=5)


@router_public.post(
    "/{slug}/p/{prod_slug}/comment",
    summary="Q1 — Visiteur dépose un avis/commentaire (modération requise)",
)
async def deposer_commentaire_public(
    slug: str, prod_slug: str,
    payload: CommentairePublicIn,
    db: AsyncSession = Depends(_get_db),
):
    b = (await db.execute(
        select(ShopBoutiqueDB).where(ShopBoutiqueDB.slug == slug)
    )).scalar_one_or_none()
    if not b or b.statut != "publie":
        raise HTTPException(404, "Boutique introuvable")
    p = (await db.execute(
        select(ShopProductDB).where(
            ShopProductDB.boutique_id == b.id,
            ShopProductDB.slug == prod_slug,
        )
    )).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Produit introuvable")

    c = ShopProductCommentDB(
        product_id=p.id, boutique_id=b.id,
        author_nom=payload.author_nom.strip(),
        author_telephone=payload.author_telephone,
        author_email=payload.author_email,
        contenu=payload.contenu.strip(),
        note=payload.note,
        statut="pending",
    )
    db.add(c)
    await db.commit()
    return {"ok": True, "id": c.id, "statut": "pending"}


@router_public.get(
    "/{slug}/p/{prod_slug}/comments",
    summary="Q1 — Liste commentaires approuvés pour un produit (storefront)",
)
async def lister_commentaires_public(
    slug: str, prod_slug: str,
    db: AsyncSession = Depends(_get_db),
):
    b = (await db.execute(
        select(ShopBoutiqueDB).where(ShopBoutiqueDB.slug == slug)
    )).scalar_one_or_none()
    if not b:
        raise HTTPException(404, "Boutique introuvable")
    p = (await db.execute(
        select(ShopProductDB).where(
            ShopProductDB.boutique_id == b.id,
            ShopProductDB.slug == prod_slug,
        )
    )).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Produit introuvable")

    rows = (await db.execute(
        select(ShopProductCommentDB).where(
            ShopProductCommentDB.product_id == p.id,
            ShopProductCommentDB.statut == "approved",
        ).order_by(desc(ShopProductCommentDB.cree_le)).limit(100)
    )).scalars().all()

    avg = None
    if rows:
        notes = [r.note for r in rows if r.note]
        if notes:
            avg = round(sum(notes) / len(notes), 2)

    return {
        "ok": True, "total": len(rows), "note_moyenne": avg,
        "items": [{
            "id": r.id, "author": r.author_nom, "contenu": r.contenu,
            "note": r.note, "date": r.cree_le.isoformat(),
        } for r in rows],
    }


@router.get("/shop/comments", summary="Q1 — Admin : liste commentaires (modération)")
async def admin_lister_commentaires(
    statut: Optional[str] = None,
    produit_id: Optional[int] = None,
    limit: int = 50,
    user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(user.id, db)
    stmt = select(ShopProductCommentDB).where(ShopProductCommentDB.boutique_id == b.id)
    if statut:
        stmt = stmt.where(ShopProductCommentDB.statut == statut)
    if produit_id:
        stmt = stmt.where(ShopProductCommentDB.product_id == produit_id)
    stmt = stmt.order_by(desc(ShopProductCommentDB.cree_le)).limit(min(limit, 200))
    rows = (await db.execute(stmt)).scalars().all()
    return {"ok": True, "items": [{
        "id": r.id, "product_id": r.product_id,
        "author_nom": r.author_nom, "author_telephone": r.author_telephone,
        "author_email": r.author_email, "contenu": r.contenu,
        "note": r.note, "statut": r.statut,
        "cree_le": r.cree_le.isoformat(),
    } for r in rows]}


class CommentaireModerationIn(BaseModel):
    statut: str = Field(..., pattern=r"^(approved|rejected|pending)$")


@router.patch("/shop/comments/{cid}", summary="Q1 — Admin : modère un commentaire")
async def admin_moderer_commentaire(
    cid: int,
    payload: CommentaireModerationIn,
    user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(user.id, db)
    c = (await db.execute(
        select(ShopProductCommentDB).where(
            ShopProductCommentDB.id == cid,
            ShopProductCommentDB.boutique_id == b.id,
        )
    )).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Commentaire introuvable")
    c.statut = payload.statut
    await db.commit()
    return {"ok": True, "id": c.id, "statut": c.statut}


@router.delete("/shop/comments/{cid}", summary="Q1 — Admin : supprime un commentaire")
async def admin_supprimer_commentaire(
    cid: int,
    user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(user.id, db)
    c = (await db.execute(
        select(ShopProductCommentDB).where(
            ShopProductCommentDB.id == cid,
            ShopProductCommentDB.boutique_id == b.id,
        )
    )).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Commentaire introuvable")
    await db.delete(c)
    await db.commit()
    return {"ok": True}


# ─── Messages visiteur → vendeur (chat asynchrone) ─────────────────────────


class MessagePublicIn(BaseModel):
    visitor_nom: str = Field(..., min_length=1, max_length=120)
    visitor_telephone: Optional[str] = Field(None, max_length=40)
    visitor_email: Optional[str] = Field(None, max_length=150)
    sujet: Optional[str] = Field(None, max_length=200)
    contenu: str = Field(..., min_length=2, max_length=4000)
    product_id: Optional[int] = None


@router_public.post(
    "/{slug}/message",
    summary="Q1 — Visiteur envoie un message au vendeur (notif WhatsApp)",
)
async def envoyer_message_public(
    slug: str,
    payload: MessagePublicIn,
    db: AsyncSession = Depends(_get_db),
):
    b = (await db.execute(
        select(ShopBoutiqueDB).where(ShopBoutiqueDB.slug == slug)
    )).scalar_one_or_none()
    if not b or b.statut != "publie":
        raise HTTPException(404, "Boutique introuvable")

    if payload.product_id:
        p = (await db.execute(
            select(ShopProductDB).where(
                ShopProductDB.id == payload.product_id,
                ShopProductDB.boutique_id == b.id,
            )
        )).scalar_one_or_none()
        if not p:
            payload.product_id = None

    m = ShopMessageDB(
        boutique_id=b.id, product_id=payload.product_id,
        visitor_nom=payload.visitor_nom.strip(),
        visitor_telephone=payload.visitor_telephone,
        visitor_email=payload.visitor_email,
        sujet=(payload.sujet or "").strip() or None,
        contenu=payload.contenu.strip(),
        statut="non_lu",
    )
    db.add(m)
    await db.commit()
    await db.refresh(m)

    # Notif marchand (WhatsApp prioritaire, SMS fallback)
    try:
        from core.notifications import notifier_telephone
        from core.database import UtilisateurDB
        from modules.bureau.service_credits_bureau import debiter_forfait_unifie
        marchand = (await db.execute(
            select(UtilisateurDB).where(UtilisateurDB.id == b.user_id)
        )).scalar_one_or_none()
        if marchand and marchand.telephone:
            sujet = payload.sujet or "Sans objet"
            contenu = (
                f"💬 Nouveau message visiteur boutique\n\n"
                f"De : {payload.visitor_nom}\n"
                f"Tel : {payload.visitor_telephone or '—'}\n"
                f"Sujet : {sujet}\n\n"
                f"« {payload.contenu[:300]} »\n\n"
                f"Répondre : https://yukpopro.yukpomnang.com/ma-boutique?tab=messages&id={m.id}"
            )
            await notifier_telephone(
                marchand.telephone, contenu,
                metadata={"type": "shop_message", "message_id": m.id},
                prefer="whatsapp",
            )
            await debiter_forfait_unifie(
                b.user_id, "whatsapp_message", module="shop_message_notif",
            )
    except Exception as _e:
        logger.warning(f"[Shop/message] notif échec : {_e}")

    return {"ok": True, "id": m.id}


@router.get("/shop/messages", summary="Q1 — Admin : inbox messages visiteurs")
async def admin_lister_messages(
    statut: Optional[str] = None,
    limit: int = 50,
    user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(user.id, db)
    stmt = select(ShopMessageDB).where(ShopMessageDB.boutique_id == b.id)
    if statut:
        stmt = stmt.where(ShopMessageDB.statut == statut)
    stmt = stmt.order_by(desc(ShopMessageDB.cree_le)).limit(min(limit, 200))
    rows = (await db.execute(stmt)).scalars().all()
    return {"ok": True, "items": [{
        "id": r.id, "product_id": r.product_id,
        "visitor_nom": r.visitor_nom, "visitor_telephone": r.visitor_telephone,
        "visitor_email": r.visitor_email,
        "sujet": r.sujet, "contenu": r.contenu,
        "statut": r.statut,
        "reponse_marchand": r.reponse_marchand,
        "repondu_le": r.repondu_le.isoformat() if r.repondu_le else None,
        "cree_le": r.cree_le.isoformat(),
    } for r in rows]}


class MessageReplyIn(BaseModel):
    contenu: str = Field(..., min_length=1, max_length=4000)
    notifier_visiteur: bool = True


@router.post("/shop/messages/{mid}/reply", summary="Q1 — Admin : répond au visiteur")
async def admin_repondre_message(
    mid: int,
    payload: MessageReplyIn,
    user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(user.id, db)
    m = (await db.execute(
        select(ShopMessageDB).where(
            ShopMessageDB.id == mid,
            ShopMessageDB.boutique_id == b.id,
        )
    )).scalar_one_or_none()
    if not m:
        raise HTTPException(404, "Message introuvable")

    m.reponse_marchand = payload.contenu.strip()
    m.repondu_le = datetime.utcnow()
    m.statut = "repondu"
    await db.commit()

    # Notif visiteur (best-effort)
    if payload.notifier_visiteur and (m.visitor_telephone or m.visitor_email):
        try:
            from core.notifications import notifier_telephone
            from modules.bureau.service_credits_bureau import debiter_forfait_unifie
            if m.visitor_telephone:
                contenu = (
                    f"💬 {b.nom} a répondu à votre message\n\n"
                    f"« {payload.contenu[:400]} »\n\n"
                    f"Boutique : https://{b.slug}.yukpomnang.com"
                )
                await notifier_telephone(
                    m.visitor_telephone, contenu,
                    metadata={"type": "shop_message_reply", "message_id": m.id},
                    prefer="whatsapp",
                )
                await debiter_forfait_unifie(
                    b.user_id, "whatsapp_message", module="shop_message_reply",
                )
        except Exception as _e:
            logger.warning(f"[Shop/message] notif visiteur échec : {_e}")

    return {"ok": True, "id": m.id, "statut": m.statut}


@router.patch("/shop/messages/{mid}", summary="Q1 — Admin : maj statut (lu/non_lu)")
async def admin_maj_statut_message(
    mid: int,
    statut: str,
    user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    if statut not in ("lu", "non_lu", "repondu", "archive"):
        raise HTTPException(400, "Statut invalide")
    b = await _get_boutique_du_user(user.id, db)
    m = (await db.execute(
        select(ShopMessageDB).where(
            ShopMessageDB.id == mid,
            ShopMessageDB.boutique_id == b.id,
        )
    )).scalar_one_or_none()
    if not m:
        raise HTTPException(404, "Message introuvable")
    m.statut = statut
    await db.commit()
    return {"ok": True, "id": m.id, "statut": m.statut}


# ═══════════════════════════════════════════════════════════════════════════
# Q2 — Livraison intelligente : zones GPS + devis automatique
# ═══════════════════════════════════════════════════════════════════════════


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance haversine en kilomètres."""
    import math
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _parse_gps_centre(gps: Optional[str]) -> Optional[tuple[float, float]]:
    """Parse 'lat,lng' ou 'lat;lng' → (lat, lng) ou None."""
    if not gps:
        return None
    try:
        parts = re.split(r"[,;]", gps.strip())
        if len(parts) < 2:
            return None
        return (float(parts[0]), float(parts[1]))
    except (ValueError, IndexError):
        return None


class LivraisonZoneIn(BaseModel):
    nom: str = Field(..., min_length=1, max_length=120)
    ville: Optional[str] = Field(None, max_length=80)
    frais: float = Field(0.0, ge=0)
    frais_par_km: Optional[float] = Field(None, ge=0)
    rayon_max_km: Optional[float] = Field(None, ge=0)
    gps_centre: Optional[str] = Field(None, max_length=60)
    delai_jours: Optional[int] = Field(None, ge=0, le=90)
    actif: bool = True


@router.get("/shop/livraison/zones", summary="Q2 — Liste zones de livraison")
async def lister_zones_livraison(
    user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(user.id, db)
    rows = (await db.execute(
        select(ShopLivraisonZoneDB)
        .where(ShopLivraisonZoneDB.boutique_id == b.id)
        .order_by(ShopLivraisonZoneDB.nom)
    )).scalars().all()
    return {"ok": True, "items": [{
        "id": r.id, "nom": r.nom, "ville": r.ville,
        "frais": float(r.frais or 0),
        "frais_par_km": float(r.frais_par_km) if r.frais_par_km is not None else None,
        "rayon_max_km": float(r.rayon_max_km) if r.rayon_max_km is not None else None,
        "gps_centre": r.gps_centre,
        "delai_jours": r.delai_jours, "actif": r.actif,
    } for r in rows]}


@router.post("/shop/livraison/zones", summary="Q2 — Crée une zone de livraison")
async def creer_zone_livraison(
    payload: LivraisonZoneIn,
    user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(user.id, db)
    z = ShopLivraisonZoneDB(
        boutique_id=b.id,
        nom=payload.nom.strip(), ville=payload.ville,
        frais=payload.frais,
        frais_par_km=payload.frais_par_km,
        rayon_max_km=payload.rayon_max_km,
        gps_centre=payload.gps_centre,
        delai_jours=payload.delai_jours, actif=payload.actif,
    )
    db.add(z)
    await db.commit()
    await db.refresh(z)
    return {"ok": True, "id": z.id}


@router.patch("/shop/livraison/zones/{zid}", summary="Q2 — Maj zone livraison")
async def maj_zone_livraison(
    zid: int,
    payload: LivraisonZoneIn,
    user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(user.id, db)
    z = (await db.execute(
        select(ShopLivraisonZoneDB).where(
            ShopLivraisonZoneDB.id == zid,
            ShopLivraisonZoneDB.boutique_id == b.id,
        )
    )).scalar_one_or_none()
    if not z:
        raise HTTPException(404, "Zone introuvable")
    z.nom = payload.nom.strip()
    z.ville = payload.ville
    z.frais = payload.frais
    z.frais_par_km = payload.frais_par_km
    z.rayon_max_km = payload.rayon_max_km
    z.gps_centre = payload.gps_centre
    z.delai_jours = payload.delai_jours
    z.actif = payload.actif
    await db.commit()
    return {"ok": True}


@router.delete("/shop/livraison/zones/{zid}", summary="Q2 — Supprime zone")
async def supprimer_zone_livraison(
    zid: int,
    user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(user.id, db)
    z = (await db.execute(
        select(ShopLivraisonZoneDB).where(
            ShopLivraisonZoneDB.id == zid,
            ShopLivraisonZoneDB.boutique_id == b.id,
        )
    )).scalar_one_or_none()
    if not z:
        raise HTTPException(404, "Zone introuvable")
    await db.delete(z)
    await db.commit()
    return {"ok": True}


class DeliveryQuoteIn(BaseModel):
    items: list[dict] = Field(..., description="[{product_id, qte}, ...]")
    destination_lat: Optional[float] = Field(None, ge=-90, le=90)
    destination_lng: Optional[float] = Field(None, ge=-180, le=180)
    destination_ville: Optional[str] = Field(None, max_length=80)


@router_public.post(
    "/{slug}/delivery/quote",
    summary="Q2 — Devis livraison : calcule frais selon GPS / ville / zone",
)
async def devis_livraison_public(
    slug: str,
    payload: DeliveryQuoteIn,
    db: AsyncSession = Depends(_get_db),
):
    b = (await db.execute(
        select(ShopBoutiqueDB).where(ShopBoutiqueDB.slug == slug)
    )).scalar_one_or_none()
    if not b:
        raise HTTPException(404, "Boutique introuvable")

    zones = (await db.execute(
        select(ShopLivraisonZoneDB).where(
            ShopLivraisonZoneDB.boutique_id == b.id,
            ShopLivraisonZoneDB.actif == True,  # noqa: E712
        )
    )).scalars().all()

    if not zones:
        return {
            "ok": True, "frais": 0.0, "devise": b.devise,
            "methode": "aucune_zone", "zone": None,
            "delai_jours": None, "distance_km": None,
            "message": "Aucune zone de livraison configurée — contactez le vendeur.",
        }

    best_zone = None
    best_frais = None
    best_methode = None
    best_distance = None
    best_delai = None

    # 1) Tentative GPS si destination fournie
    if payload.destination_lat is not None and payload.destination_lng is not None:
        for z in zones:
            centre = _parse_gps_centre(z.gps_centre)
            if not centre:
                continue
            d = _haversine_km(centre[0], centre[1],
                              payload.destination_lat, payload.destination_lng)
            if z.rayon_max_km and d > float(z.rayon_max_km):
                continue
            base = float(z.frais or 0)
            par_km = float(z.frais_par_km or 0)
            frais = base + par_km * d
            if best_frais is None or frais < best_frais:
                best_frais = frais
                best_zone = z
                best_methode = "gps"
                best_distance = round(d, 2)
                best_delai = z.delai_jours

    # 2) Fallback ville si rien trouvé via GPS
    if best_frais is None and payload.destination_ville:
        ville_norm = payload.destination_ville.strip().lower()
        for z in zones:
            if z.ville and z.ville.strip().lower() == ville_norm:
                best_frais = float(z.frais or 0)
                best_zone = z
                best_methode = "ville"
                best_delai = z.delai_jours
                break

    # 3) Fallback zone par défaut (sans ville ni GPS)
    if best_frais is None:
        zdefault = next((z for z in zones if not z.ville and not z.gps_centre), None)
        if zdefault:
            best_frais = float(zdefault.frais or 0)
            best_zone = zdefault
            best_methode = "default"
            best_delai = zdefault.delai_jours

    if best_frais is None:
        return {
            "ok": False, "frais": None, "devise": b.devise,
            "methode": "non_livrable", "zone": None,
            "delai_jours": None, "distance_km": None,
            "message": "Destination hors zone de livraison — contactez le vendeur.",
        }

    return {
        "ok": True,
        "frais": round(best_frais, 2),
        "devise": b.devise,
        "methode": best_methode,
        "zone": {"id": best_zone.id, "nom": best_zone.nom} if best_zone else None,
        "delai_jours": best_delai,
        "distance_km": best_distance,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Branding — logo + bannière (upload manuel ou génération IA)
# ═══════════════════════════════════════════════════════════════════════════


_BRANDING_MIME_OK = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/svg+xml"}
_BRANDING_MAX_BYTES = 8 * 1024 * 1024  # 8 MB


async def _persister_image_branding(
    *, boutique_id: int, kind: str, content: bytes, ext: str,
    content_type: str,
) -> str:
    """Sauvegarde image branding (logo/banniere/icon) et renvoie URL publique."""
    from core.storage import save_artifact
    name = f"boutique_{boutique_id}_{kind}_{int(time.time())}.{ext}"
    info = save_artifact(
        category="shop_branding", name=name,
        content=content, content_type=content_type,
    )
    if info.get("storage") == "r2":
        public_base = os.getenv("R2_PUBLIC_BASE_URL", "").rstrip("/")
        if public_base:
            return f"{public_base}/{info['key']}"
        return f"/api/v1/storage/shop_branding/{name}"
    return f"/api/v1/storage/shop_branding/{name}"


@router.post("/shop/branding/logo", summary="Branding — upload logo")
async def uploader_logo(
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    if file.content_type not in _BRANDING_MIME_OK:
        raise HTTPException(400, f"Type fichier non supporté : {file.content_type}")
    content = await file.read()
    if len(content) > _BRANDING_MAX_BYTES:
        raise HTTPException(400, "Fichier trop volumineux (>8 Mo)")
    ext = (file.filename or "logo.png").rsplit(".", 1)[-1].lower() or "png"
    if ext not in ("png", "jpg", "jpeg", "webp", "svg"):
        ext = "png"
    url = await _persister_image_branding(
        boutique_id=b.id, kind="logo", content=content, ext=ext,
        content_type=file.content_type,
    )
    b.logo_url = url
    b.derniere_modif = datetime.utcnow()
    await db.commit()
    return {"ok": True, "url": url}


@router.post("/shop/branding/banniere", summary="Branding — upload bannière")
async def uploader_banniere(
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    if file.content_type not in _BRANDING_MIME_OK:
        raise HTTPException(400, f"Type fichier non supporté : {file.content_type}")
    content = await file.read()
    if len(content) > _BRANDING_MAX_BYTES:
        raise HTTPException(400, "Fichier trop volumineux (>8 Mo)")
    ext = (file.filename or "banniere.png").rsplit(".", 1)[-1].lower() or "png"
    if ext not in ("png", "jpg", "jpeg", "webp"):
        ext = "png"
    url = await _persister_image_branding(
        boutique_id=b.id, kind="banniere", content=content, ext=ext,
        content_type=file.content_type,
    )
    b.banniere_url = url
    b.derniere_modif = datetime.utcnow()
    await db.commit()
    return {"ok": True, "url": url}


class BrandingGenerationIn(BaseModel):
    brief: Optional[str] = Field(None, max_length=2000)
    style: Optional[str] = Field(None, max_length=200)


def _construire_prompt_logo(boutique: ShopBoutiqueDB, brief: Optional[str], style: Optional[str]) -> str:
    nom = boutique.nom or "Boutique"
    desc = boutique.description or ""
    style_part = f"Style: {style}. " if style else ""
    brief_part = f"{brief}. " if brief else ""
    return (
        f"Professional brand logo for '{nom}', an e-commerce shop. "
        f"{brief_part}{style_part}"
        f"Context: {desc[:300]}. "
        f"Requirements: clean modern flat design, vector-style, centered, "
        f"square 1:1 ratio, white or transparent background, "
        f"high contrast, suitable as app icon and website header, "
        f"NO text unless it is a short stylized monogram, NO photo, NO photorealism. "
        f"Output: a single iconic emblem/wordmark."
    )


def _construire_prompt_banniere(boutique: ShopBoutiqueDB, brief: Optional[str], style: Optional[str]) -> str:
    nom = boutique.nom or "Boutique"
    desc = boutique.description or ""
    style_part = f"Style: {style}. " if style else ""
    brief_part = f"{brief}. " if brief else ""
    return (
        f"E-commerce hero banner for '{nom}'. "
        f"{brief_part}{style_part}"
        f"Context: {desc[:300]}. "
        f"Requirements: wide cinematic 16:9 composition, vibrant colors, "
        f"warm welcoming atmosphere, professional photography style, "
        f"clear empty space on the left for text overlay, "
        f"high quality marketing visual, NO embedded text."
    )


@router.post("/shop/branding/logo/generer-ia", summary="Branding — génère logo IA")
async def generer_logo_ia(
    payload: BrandingGenerationIn,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    # Pré-check crédits (génération image = ~150 crédits)
    try:
        from modules.bureau.service_credits_bureau import (
            _pre_check_credits, debiter_forfait_unifie,
        )
        await _pre_check_credits(current_user.user_id, "pdf_generation")
    except Exception:
        pass

    prompt = _construire_prompt_logo(b, payload.brief, payload.style)
    try:
        from modules.bureau.image_gen import generer_image
        png = await generer_image(
            prompt=prompt, mode="standard", format_="square_1_1",
        )
    except Exception as e:
        logger.warning(f"[Shop/branding] gen logo IA échec : {e}")
        raise HTTPException(502, f"Génération logo IA indisponible : {e}")

    url = await _persister_image_branding(
        boutique_id=b.id, kind="logo_ia", content=png, ext="png",
        content_type="image/png",
    )
    b.logo_url = url
    b.derniere_modif = datetime.utcnow()
    await db.commit()

    # Débit forfait
    try:
        await debiter_forfait_unifie(
            current_user.user_id, "pdf_generation", module="shop_logo_ia",
        )
    except Exception:
        pass

    return {"ok": True, "url": url, "cost": 1}


@router.post("/shop/branding/banniere/generer-ia", summary="Branding — génère bannière IA")
async def generer_banniere_ia(
    payload: BrandingGenerationIn,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    try:
        from modules.bureau.service_credits_bureau import (
            _pre_check_credits, debiter_forfait_unifie,
        )
        await _pre_check_credits(current_user.user_id, "pdf_generation")
    except Exception:
        pass

    prompt = _construire_prompt_banniere(b, payload.brief, payload.style)
    try:
        from modules.bureau.image_gen import generer_image
        png = await generer_image(
            prompt=prompt, mode="standard", format_="landscape_16_9",
        )
    except Exception as e:
        logger.warning(f"[Shop/branding] gen bannière IA échec : {e}")
        raise HTTPException(502, f"Génération bannière IA indisponible : {e}")

    url = await _persister_image_branding(
        boutique_id=b.id, kind="banniere_ia", content=png, ext="png",
        content_type="image/png",
    )
    b.banniere_url = url
    b.derniere_modif = datetime.utcnow()
    await db.commit()

    try:
        await debiter_forfait_unifie(
            current_user.user_id, "pdf_generation", module="shop_banniere_ia",
        )
    except Exception:
        pass

    return {"ok": True, "url": url, "cost": 1}


async def _initier_paiement_v2(
    *, order: ShopOrderDB, boutique: ShopBoutiqueDB,
    db: AsyncSession, provider: str,
) -> Optional[str]:
    """Branche la commande au système paiement_v2 existant (Stripe, Flutterwave,
    Orange Money, MTN MoMo, Wave, Campay, CinetPay).

    Retourne l'URL de paiement où rediriger le client (si applicable), ou None
    pour les providers async (mobile money confirmation par webhook).
    """
    try:
        from modules.paiement.v2 import paiement_v2_service as _pv2
        # API existante : créer une session de paiement avec montant + currency
        # + callback URL + métadonnées commande. Si l'API diffère, le wrapper
        # ci-dessous gère gracieusement (best-effort, fallback cash si KO).
        url = await _pv2.creer_session_paiement(
            user_id=boutique.user_id,
            montant=float(order.montant_total),
            devise=order.devise,
            provider=provider,
            metadata={
                "type": "shop_order",
                "order_id": order.id, "numero": order.numero,
                "boutique_slug": boutique.slug,
            },
            callback_url=(
                f"{boutique.url_public or f'https://{boutique.slug}.yukpomnang.com'}"
                f"/panier?paiement=callback&order={order.numero}"
            ),
        )
        return url
    except (ImportError, AttributeError) as e:
        logger.info(f"[Shop/pay] paiement_v2 indisponible ({e}) — commande créée sans URL")
        return None
    except Exception as e:
        logger.warning(f"[Shop/pay] init session échec : {e}")
        return None
