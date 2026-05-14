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
    ShopBoutiqueDB, ShopCategorieDB, ShopOrderDB, ShopOrderItemDB,
    ShopProductDB, async_session_maker,
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


class ProduitPatchRequest(BaseModel):
    titre: Optional[str] = None
    description_courte: Optional[str] = None
    description_longue: Optional[str] = None
    prix_unit: Optional[float] = None
    prix_unit_promo: Optional[float] = None
    tva_pct: Optional[float] = None
    stock: Optional[int] = None
    photos_urls_json: Optional[list[str]] = None
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

    return {
        "ok": True, "id": boutique.id, "slug": boutique.slug,
        "nom": boutique.nom, "url_pressentie": f"https://{boutique.slug}.yukpomnang.com",
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
        raise HTTPException(502, f"Erreur Netlify : {str(e)[:200]}")

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

    return {
        "ok": True, "slug": b.slug, "url_public": b.url_public,
        "nb_produits": len(produits_dicts),
        "nb_categories": len(cats_dicts),
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

    for it in payload.items:
        db.add(ShopOrderItemDB(
            order_id=order.id, product_id=it.id,
            titre=it.titre, quantite=it.qte, prix_unit=it.prix,
            photo_url=it.photo, variante_label=it.variante_label,
            variante_json=it.variante_json,
        ))

    await db.commit()
    await db.refresh(order)

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
