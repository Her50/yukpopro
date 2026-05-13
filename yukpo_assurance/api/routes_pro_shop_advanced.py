"""Routes YukpoShop avancées (Phase D6 + D7 + D8 + D9).

Tous endpoints sous /api/v1/pro/shop, authentifiés (ownership boutique
vérifiée sur user_id).
"""
from __future__ import annotations

import io
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import TokenData, get_current_user
from core.database import (
    ShopAdsIntegrationDB, ShopAdsMetricDB, ShopBoutiqueDB, ShopClientDB,
    ShopClientEventDB, ShopLivraisonEtiquetteDB, ShopLivraisonZoneDB,
    ShopOrderDB, ShopProductDB, ShopSocialIntegrationDB,
    ShopSocialPublicationDB, async_session_maker,
)

logger = logging.getLogger("yukpo_assurance.api.pro_shop_advanced")

router = APIRouter()


async def _get_db():
    async with async_session_maker() as session:
        yield session


async def _get_boutique_du_user(user_id: int, db: AsyncSession) -> ShopBoutiqueDB:
    row = (await db.execute(
        select(ShopBoutiqueDB).where(ShopBoutiqueDB.user_id == user_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Boutique non initialisée")
    return row


# ─── D6 — Social integrations (Meta FB/IG, TikTok Shop) ─────────────────────


@router.get("/shop/social", summary="Statut intégrations sociales")
async def get_social_integrations(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    rows = (await db.execute(
        select(ShopSocialIntegrationDB)
        .where(ShopSocialIntegrationDB.boutique_id == b.id)
    )).scalars().all()
    return {
        "integrations": [
            {
                "id": r.id, "platform": r.platform,
                "page_id": r.page_id, "catalog_id": r.catalog_id,
                "compte_username": r.compte_username,
                "statut": r.statut,
                "derniere_sync": r.derniere_sync.isoformat() if r.derniere_sync else None,
                "expire_le": r.expire_le.isoformat() if r.expire_le else None,
            } for r in rows
        ],
    }


@router.get("/shop/social/connect-url", summary="URL OAuth pour connecter Meta")
async def get_oauth_url_meta(
    current_user: TokenData = Depends(get_current_user),
):
    from modules.pro.shop_social_sync import url_oauth_meta
    app_id = os.getenv("META_FB_APP_ID", "").strip()
    if not app_id:
        raise HTTPException(503, "META_FB_APP_ID non configuré côté serveur")
    base_url = os.getenv("YUKPO_PUBLIC_API_BASE", "").rstrip("/")
    redirect = f"{base_url}/api/v1/pro/shop/social/callback-meta"
    state = f"u{current_user.user_id}-{int(datetime.utcnow().timestamp())}"
    url = url_oauth_meta(redirect, app_id, state)
    return {"oauth_url": url, "state": state}


@router.get("/shop/social/callback-meta", summary="Callback OAuth Meta — interne")
async def callback_oauth_meta(
    code: str, state: str,
    db: AsyncSession = Depends(_get_db),
):
    """Callback Meta : échange code → long-lived token + persiste integration."""
    if not state.startswith("u"):
        raise HTTPException(400, "State invalide")
    try:
        user_id = int(state[1:].split("-")[0])
    except Exception:
        raise HTTPException(400, "State invalide")

    b = (await db.execute(
        select(ShopBoutiqueDB).where(ShopBoutiqueDB.user_id == user_id)
    )).scalar_one_or_none()
    if not b:
        raise HTTPException(404, "Boutique introuvable")

    app_id = os.getenv("META_FB_APP_ID", "").strip()
    app_secret = os.getenv("META_FB_APP_SECRET", "").strip()
    base_url = os.getenv("YUKPO_PUBLIC_API_BASE", "").rstrip("/")
    redirect = f"{base_url}/api/v1/pro/shop/social/callback-meta"

    from modules.pro.shop_social_sync import echanger_code_pour_token, lister_pages_user
    try:
        token_data = await echanger_code_pour_token(code, redirect, app_id, app_secret)
        pages = await lister_pages_user(token_data["access_token"])
    except Exception as e:
        raise HTTPException(502, f"Meta OAuth échec : {str(e)[:200]}")

    # Pour MVP : prend la 1re page disponible (le user peut éditer après)
    page = pages[0] if pages else {}
    integ = (await db.execute(
        select(ShopSocialIntegrationDB)
        .where(ShopSocialIntegrationDB.boutique_id == b.id)
        .where(ShopSocialIntegrationDB.platform == "meta_fb")
    )).scalar_one_or_none()
    if not integ:
        integ = ShopSocialIntegrationDB(boutique_id=b.id, platform="meta_fb")
        db.add(integ)

    integ.access_token_chiffre = token_data["access_token"]  # TODO chiffrer
    integ.page_id = page.get("id")
    integ.compte_username = page.get("name")
    integ.expire_le = datetime.utcnow() + timedelta(seconds=token_data.get("expires_in_seconds", 60 * 86400))
    integ.statut = "actif"
    integ.derniere_sync = datetime.utcnow()
    integ.modif_le = datetime.utcnow()
    await db.commit()

    # Redirige vers la page boutique avec confirmation
    from fastapi.responses import RedirectResponse
    url_pro = os.getenv("YUKPO_PUBLIC_PRO_URL", "https://yukpopro.yukpomnang.com")
    return RedirectResponse(f"{url_pro}/ma-boutique?social=meta_connecte")


@router.post("/shop/social/sync-catalog", summary="D6 — Sync produits vers Meta Catalog")
async def sync_meta_catalog(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    integ = (await db.execute(
        select(ShopSocialIntegrationDB)
        .where(ShopSocialIntegrationDB.boutique_id == b.id)
        .where(ShopSocialIntegrationDB.platform == "meta_fb")
        .where(ShopSocialIntegrationDB.statut == "actif")
    )).scalar_one_or_none()
    if not integ or not integ.catalog_id:
        raise HTTPException(400,
            "Pas de catalog_id Meta configuré. Configurez-le dans Business Manager Meta.")

    produits = (await db.execute(
        select(ShopProductDB)
        .where(ShopProductDB.boutique_id == b.id)
        .where(ShopProductDB.statut == "actif")
    )).scalars().all()
    produits_dicts = [{
        "id": p.id, "titre": p.titre, "slug": p.slug,
        "description_courte": p.description_courte,
        "prix_unit": float(p.prix_unit), "devise": p.devise,
        "stock": p.stock,
        "photos_urls_json": p.photos_urls_json,
    } for p in produits]

    from modules.pro.shop_social_sync import sync_produits_vers_meta_catalog
    store_url = b.url_public or f"https://{b.slug}.yukpomnang.com"
    res = await sync_produits_vers_meta_catalog(
        integ.catalog_id, integ.access_token_chiffre,
        produits_dicts, store_url_base=store_url,
    )

    integ.derniere_sync = datetime.utcnow()
    await db.commit()
    return {"ok": res["nb_sync_erreur"] == 0, **res, "nb_produits": len(produits)}


# ─── D7 — Ads ROAS ─────────────────────────────────────────────────────────


@router.get("/shop/ads/dashboard", summary="D7 — Dashboard ROAS toutes plateformes")
async def get_ads_dashboard(
    jours: int = Query(30, ge=1, le=365),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    since = datetime.utcnow().date() - timedelta(days=jours)
    metrics_rows = (await db.execute(
        select(ShopAdsMetricDB)
        .where(ShopAdsMetricDB.boutique_id == b.id)
        .where(ShopAdsMetricDB.jour >= since)
        .order_by(desc(ShopAdsMetricDB.jour))
    )).scalars().all()

    metrics_dicts = [{
        "platform": m.platform, "campagne_id": m.campagne_id,
        "campagne_nom": m.campagne_nom, "jour": m.jour.isoformat(),
        "depenses": float(m.depenses), "impressions": m.impressions,
        "clics": m.clics, "conversions_externes": m.conversions_externes,
        "conversions_locales": m.conversions_locales,
        "revenu_local": float(m.revenu_local), "devise": m.devise,
    } for m in metrics_rows]

    from modules.pro.shop_ads_aggregator import calculer_roas
    roas = calculer_roas(metrics_dicts)
    return {"periode_jours": jours, **roas}


@router.post("/shop/ads/sync", summary="D7 — Sync métriques depuis plateformes connectées")
async def sync_ads_metrics(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    integrations = (await db.execute(
        select(ShopAdsIntegrationDB)
        .where(ShopAdsIntegrationDB.boutique_id == b.id)
        .where(ShopAdsIntegrationDB.statut == "actif")
    )).scalars().all()

    if not integrations:
        return {"ok": False, "message": "Aucune plateforme pub connectée"}

    from modules.pro.shop_ads_aggregator import (
        croiser_avec_commandes, recuperer_metriques_fb_ads,
    )
    nb_total = 0
    for integ in integrations:
        if integ.platform != "fb_ads":
            continue  # MVP : FB seulement
        try:
            raw = await recuperer_metriques_fb_ads(
                integ.ad_account_id, integ.access_token_chiffre, jours=30,
            )
            enriched = await croiser_avec_commandes(b.id, raw, db)
            for m in enriched:
                jour = (
                    datetime.fromisoformat(m["jour"]).date()
                    if isinstance(m["jour"], str) else m["jour"]
                )
                existant = (await db.execute(
                    select(ShopAdsMetricDB)
                    .where(ShopAdsMetricDB.boutique_id == b.id)
                    .where(ShopAdsMetricDB.platform == m["platform"])
                    .where(ShopAdsMetricDB.campagne_id == m["campagne_id"])
                    .where(ShopAdsMetricDB.jour == jour)
                )).scalar_one_or_none()
                if not existant:
                    existant = ShopAdsMetricDB(
                        boutique_id=b.id, platform=m["platform"],
                        campagne_id=m["campagne_id"], jour=jour,
                    )
                    db.add(existant)
                existant.campagne_nom = m.get("campagne_nom")
                existant.depenses = m.get("depenses") or 0
                existant.impressions = m.get("impressions") or 0
                existant.clics = m.get("clics") or 0
                existant.conversions_externes = m.get("conversions_externes") or 0
                existant.conversions_locales = m.get("conversions_locales") or 0
                existant.revenu_local = m.get("revenu_local") or 0
                existant.devise = m.get("devise") or b.devise
                existant.derniere_maj = datetime.utcnow()
                nb_total += 1
            integ.derniere_sync = datetime.utcnow()
        except Exception as e:
            logger.warning(f"[Ads/sync] {integ.platform} échec : {e}")
            integ.derniere_erreur = str(e)[:500]
    await db.commit()
    return {"ok": True, "nb_metrics_synced": nb_total}


@router.post("/shop/ads/recommandations", summary="D7 — Recommandations IA Opus sur ROAS")
async def get_ads_recommandations(
    jours: int = Query(30, ge=7, le=365),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    """IA Opus analyse les métriques + génère recommandations actionnables."""
    from api.routes_pro_generateurs import _pre_check_credits
    await _pre_check_credits(current_user.user_id, role=current_user.role)

    b = await _get_boutique_du_user(current_user.user_id, db)
    since = datetime.utcnow().date() - timedelta(days=jours)
    metrics_rows = (await db.execute(
        select(ShopAdsMetricDB)
        .where(ShopAdsMetricDB.boutique_id == b.id)
        .where(ShopAdsMetricDB.jour >= since)
    )).scalars().all()
    metrics_dicts = [{
        "platform": m.platform, "campagne_id": m.campagne_id,
        "campagne_nom": m.campagne_nom, "jour": m.jour.isoformat(),
        "depenses": float(m.depenses), "impressions": m.impressions,
        "clics": m.clics, "conversions_locales": m.conversions_locales,
        "revenu_local": float(m.revenu_local),
    } for m in metrics_rows]

    from modules.pro.shop_ads_aggregator import calculer_roas, generer_recommandations_ia
    roas = calculer_roas(metrics_dicts)
    if not roas["par_campagne"]:
        return {"ok": True, "recommandations_md": "Pas assez de données pour générer des recommandations.",
                "roas_data": roas}
    recos = await generer_recommandations_ia(roas)
    try:
        from modules.bureau.service_credits_bureau import debiter_forfait_unifie
        await debiter_forfait_unifie(
            current_user.user_id, "pdf_generation", module="ads_reco",
        )
    except Exception:
        pass
    return {"ok": True, "recommandations_md": recos, "roas_data": roas}


# ─── D8 — CRM clients ──────────────────────────────────────────────────────


@router.get("/shop/crm/clients", summary="D8 — Liste clients segmentés")
async def lister_clients_crm(
    segment: Optional[str] = None,
    limit: int = 50, offset: int = 0,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    q = (select(ShopClientDB)
         .where(ShopClientDB.boutique_id == b.id)
         .order_by(desc(ShopClientDB.revenu_total)))
    if segment:
        q = q.where(ShopClientDB.segment == segment)
    q = q.limit(limit).offset(offset)
    rows = (await db.execute(q)).scalars().all()
    return {
        "clients": [{
            "id": c.id, "nom": c.nom, "telephone": c.telephone, "email": c.email,
            "ville": c.ville, "source_acquisition": c.source_acquisition,
            "nb_commandes": c.nb_commandes, "revenu_total": float(c.revenu_total),
            "ltv_predite": c.ltv_predite, "score_churn_pct": c.score_churn_pct,
            "segment": c.segment,
            "derniere_commande_le": c.derniere_commande_le.isoformat() if c.derniere_commande_le else None,
        } for c in rows]
    }


@router.post("/shop/crm/agreger", summary="D8 — Agrège les clients depuis les commandes")
async def agreger_clients_crm(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    from modules.pro.crm_scorer import aggreger_clients_boutique
    n = await aggreger_clients_boutique(b.id, db)
    return {"ok": True, "nb_clients_traites": n}


@router.post("/shop/crm/scorer", summary="D8 — Score N clients via LLM (segment + churn)")
async def scorer_clients_crm(
    limit: int = Query(50, ge=1, le=500),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    from api.routes_pro_generateurs import _pre_check_credits
    await _pre_check_credits(current_user.user_id, role=current_user.role)

    b = await _get_boutique_du_user(current_user.user_id, db)
    from modules.pro.crm_scorer import scorer_tous_clients_boutique
    n = await scorer_tous_clients_boutique(b.id, db, limit_par_run=limit)
    return {"ok": True, "nb_clients_scores": n}


@router.get("/shop/crm/clients/{client_id}", summary="D8 — Profil 360°")
async def detail_client_crm(
    client_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    c = (await db.execute(
        select(ShopClientDB)
        .where(ShopClientDB.id == client_id)
        .where(ShopClientDB.boutique_id == b.id)
    )).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Client introuvable")
    events = (await db.execute(
        select(ShopClientEventDB)
        .where(ShopClientEventDB.client_id == c.id)
        .order_by(desc(ShopClientEventDB.created_at))
        .limit(50)
    )).scalars().all()
    return {
        "client": {
            "id": c.id, "nom": c.nom, "telephone": c.telephone,
            "email": c.email, "ville": c.ville,
            "source_acquisition": c.source_acquisition,
            "nb_commandes": c.nb_commandes,
            "revenu_total": float(c.revenu_total),
            "ltv_predite": c.ltv_predite,
            "score_churn_pct": c.score_churn_pct,
            "segment": c.segment, "recos_ia": c.recos_ia_json or [],
            "premiere_commande_le": c.premiere_commande_le.isoformat() if c.premiere_commande_le else None,
            "derniere_commande_le": c.derniere_commande_le.isoformat() if c.derniere_commande_le else None,
        },
        "events": [{
            "type": e.type_event, "product_id": e.product_id,
            "source": e.source, "created_at": e.created_at.isoformat(),
        } for e in events],
    }


class RelancerClientRequest(BaseModel):
    message: str = Field(..., min_length=10, max_length=600)


@router.post("/shop/crm/clients/{client_id}/relancer", summary="D8 — Relance WA + SMS au client")
async def relancer_client(
    client_id: int,
    payload: RelancerClientRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    c = (await db.execute(
        select(ShopClientDB)
        .where(ShopClientDB.id == client_id)
        .where(ShopClientDB.boutique_id == b.id)
    )).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Client introuvable")
    from modules.pro.crm_scorer import relancer_client_wa
    ok = await relancer_client_wa(c, current_user.user_id, payload.message)
    return {"ok": ok}


# ─── D9 — Logistique ───────────────────────────────────────────────────────


class CreerZoneRequest(BaseModel):
    nom: str = Field(..., min_length=2, max_length=120)
    villes_json: Optional[list[str]] = None
    regions_json: Optional[list[str]] = None
    pays_json: Optional[list[str]] = None
    tarif: float = Field(..., ge=0)
    devise: Optional[str] = None
    delai_jours_min: int = Field(1, ge=0, le=180)
    delai_jours_max: int = Field(3, ge=0, le=180)
    transporteur_prefere: Optional[str] = None
    ordre: int = 0


@router.get("/shop/livraison/zones", summary="D9 — Zones de livraison configurées")
async def lister_zones_livraison(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    rows = (await db.execute(
        select(ShopLivraisonZoneDB)
        .where(ShopLivraisonZoneDB.boutique_id == b.id)
        .order_by(ShopLivraisonZoneDB.ordre)
    )).scalars().all()
    return {
        "zones": [{
            "id": z.id, "nom": z.nom,
            "villes": z.villes_json or [], "regions": z.regions_json or [],
            "pays": z.pays_json or [],
            "tarif": float(z.tarif), "devise": z.devise,
            "delai_min": z.delai_jours_min, "delai_max": z.delai_jours_max,
            "transporteur_prefere": z.transporteur_prefere,
            "actif": z.actif, "ordre": z.ordre,
        } for z in rows]
    }


@router.post("/shop/livraison/zones", summary="D9 — Crée une zone de livraison")
async def creer_zone_livraison(
    req: CreerZoneRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    z = ShopLivraisonZoneDB(
        boutique_id=b.id, nom=req.nom,
        villes_json=req.villes_json, regions_json=req.regions_json,
        pays_json=req.pays_json,
        tarif=req.tarif, devise=req.devise or b.devise,
        delai_jours_min=req.delai_jours_min, delai_jours_max=req.delai_jours_max,
        transporteur_prefere=req.transporteur_prefere,
        ordre=req.ordre, actif=True,
    )
    db.add(z)
    await db.commit()
    await db.refresh(z)
    return {"ok": True, "id": z.id}


@router.delete("/shop/livraison/zones/{zone_id}", summary="D9 — Supprime zone")
async def supprimer_zone_livraison(
    zone_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    b = await _get_boutique_du_user(current_user.user_id, db)
    await db.execute(
        ShopLivraisonZoneDB.__table__.delete()
        .where(ShopLivraisonZoneDB.id == zone_id)
        .where(ShopLivraisonZoneDB.boutique_id == b.id)
    )
    await db.commit()
    return {"ok": True}


@router.post("/shop/commandes/{order_id}/etiquette", summary="D9 — Génère étiquette PDF + tracking")
async def generer_etiquette(
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

    from modules.pro.shop_logistique import (
        generer_etiquette_pdf_generique, generer_tracking_num,
    )
    tracking = generer_tracking_num()
    base = os.getenv("YUKPO_PUBLIC_API_BASE", "https://yukpopro.yukpomnang.com").rstrip("/")

    pdf_bytes = generer_etiquette_pdf_generique(
        order_data={
            "numero": o.numero, "client_nom": o.client_nom,
            "client_telephone": o.client_telephone,
            "adresse_livraison_json": o.adresse_livraison_json,
        },
        boutique_data={
            "nom": b.nom, "url_public": b.url_public,
            "ville": b.pays_principal,
        },
        tracking_num=tracking,
        tracking_base_url=base,
    )

    # Persiste l'étiquette en DB (mais pas le PDF — on retourne en stream)
    etiq = ShopLivraisonEtiquetteDB(
        order_id=o.id, transporteur="generique",
        tracking_num=tracking, statut="creee",
    )
    db.add(etiq)
    o.tracking_url = f"{base}/track/{tracking}"
    await db.commit()

    try:
        from modules.bureau.service_credits_bureau import debiter_forfait_unifie
        await debiter_forfait_unifie(
            current_user.user_id, "pdf_generation", module="shop_etiquette",
        )
    except Exception:
        pass

    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="etiquette-{tracking}.pdf"'},
    )
