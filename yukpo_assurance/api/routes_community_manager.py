"""
Routes FastAPI — Community Manager IA
- POST /generer          : génère un post social
- POST /planifier        : planifie un post
- GET  /posts            : liste des posts
- PUT  /posts/{id}/statut: change le statut (publié, annulé…)
- GET  /analytics        : stats d'engagement
- GET  /preferences      : préférences CM de la compagnie
- PUT  /preferences      : met à jour les préférences CM
- POST /brouillon-trend  : génère un brouillon depuis une tendance
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db, CompagnieDB, PostSocialDB, PreferencesCMDB, AnalyticsPostDB, SocialConnectorDB
from core.auth import get_current_user, TokenData, require_permission
from core.multitenancy import require_module
from config.settings import settings
from modules.community_manager.gestionnaire_cm import (
    ContexteContenu,
    MoteurCommunityManager,
)

router = APIRouter(
    prefix="/community-manager",
    tags=["Community Manager IA"],
    dependencies=[Depends(require_permission("community_manager"))],
)


# ─────────────────────────────────────────────────────────────
# Schémas
# ─────────────────────────────────────────────────────────────

class GenererPostSchema(BaseModel):
    type_contenu: str = "produit"
    sujet: str
    plateforme: str
    ton: str = "professionnel"
    langue: str = "fr"
    inject_trend: Optional[str] = None
    inclure_cta: bool = True
    max_caracteres: Optional[int] = None
    hashtags_supplementaires: List[str] = []
    planifier_le: Optional[datetime] = None


class PlanifierPostSchema(BaseModel):
    legende: str
    plateforme: str
    type_contenu: str = "produit"
    hashtags: List[str] = []
    image_url: Optional[str] = None
    lien_url: Optional[str] = None
    planifie_le: Optional[datetime] = None
    legende_variante_b: Optional[str] = None


class ChangerStatutSchema(BaseModel):
    statut: str  # brouillon | planifie | publie | echoue | annule


class PreferencesCMSchema(BaseModel):
    voix_marque: Optional[str] = None
    mots_interdits: List[str] = []
    toujours_inclure: List[str] = []
    hashtags_defaut: List[str] = []
    heures_publication: List[int] = [8, 12, 18]
    plateformes_actives: dict = {}
    max_posts_par_jour: int = 3
    ab_test_auto: bool = True
    secteur_contenu: str = "assurance"
    modele_ia_prefere: str = "claude-opus-4-6"


class BrouillonTrendSchema(BaseModel):
    sujet_trend: str
    score_opportunite: float
    region: str = "CM"


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

async def _get_prefs(compagnie_id: int, db: AsyncSession) -> Optional[dict]:
    r = await db.execute(
        select(PreferencesCMDB).where(PreferencesCMDB.compagnie_id == compagnie_id)
    )
    prefs = r.scalar_one_or_none()
    if not prefs:
        return None
    return {
        "voix_marque": prefs.voix_marque,
        "mots_interdits": prefs.mots_interdits or [],
        "toujours_inclure": prefs.toujours_inclure or [],
        "hashtags_defaut": prefs.hashtags_defaut or [],
        "heures_publication": prefs.heures_publication or [8, 12, 18],
        "secteur_contenu": prefs.secteur_contenu or "assurance",
    }


async def _get_compagnie(compagnie_id: int, db: AsyncSession):
    r = await db.execute(select(CompagnieDB).where(CompagnieDB.id == compagnie_id))
    return r.scalar_one_or_none()


def _moteur(secteur: str = "assurance") -> MoteurCommunityManager:
    return MoteurCommunityManager(
        claude_api_key=settings.CLAUDE_API_KEY,
        openai_api_key=settings.OPENAI_API_KEY,
        secteur=secteur,
    )


# ─────────────────────────────────────────────────────────────
# Générer un post
# ─────────────────────────────────────────────────────────────

@router.post(
    "/generer",
    dependencies=[Depends(require_module("community_manager"))],
)
async def generer_post(
    payload: GenererPostSchema,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    prefs = await _get_prefs(current_user.compagnie_id, db)
    secteur = prefs.get("secteur_contenu", "assurance") if prefs else "assurance"

    ctx = ContexteContenu(
        type_contenu=payload.type_contenu,
        sujet=payload.sujet,
        plateforme=payload.plateforme,
        ton=payload.ton,
        langue=payload.langue,
        inject_trend=payload.inject_trend,
        inclure_cta=payload.inclure_cta,
        max_caracteres=payload.max_caracteres,
        hashtags_supplementaires=payload.hashtags_supplementaires,
    )

    post_gen = await _moteur(secteur).generer_post(ctx, prefs)

    # Sauvegarder en brouillon
    post = PostSocialDB(
        compagnie_id=current_user.compagnie_id,
        plateforme=payload.plateforme,
        type_contenu=payload.type_contenu,
        sujet=payload.sujet,
        legende=post_gen.legende,
        legende_variante_b=post_gen.legende_variante_b,
        hashtags=post_gen.hashtags,
        ton=payload.ton,
        langue=payload.langue,
        statut="planifie" if payload.planifier_le else "brouillon",
        planifie_le=payload.planifier_le,
        modele_ia=post_gen.modele_utilise,
        prompt_generation=post_gen.prompt_utilise[:2000] if post_gen.prompt_utilise else None,
        cree_par=current_user.username,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)

    return {
        "id": post.id,
        "legende": post_gen.legende,
        "legende_variante_b": post_gen.legende_variante_b,
        "hashtags": post_gen.hashtags,
        "plateforme": payload.plateforme,
        "statut": post.statut,
        "modele": post_gen.modele_utilise,
    }


# ─────────────────────────────────────────────────────────────
# Planifier un post existant / manuel
# ─────────────────────────────────────────────────────────────

@router.post(
    "/planifier",
    dependencies=[Depends(require_module("community_manager"))],
)
async def planifier_post(
    payload: PlanifierPostSchema,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    post = PostSocialDB(
        compagnie_id=current_user.compagnie_id,
        plateforme=payload.plateforme,
        type_contenu=payload.type_contenu,
        legende=payload.legende,
        legende_variante_b=payload.legende_variante_b,
        hashtags=payload.hashtags,
        image_url=payload.image_url,
        lien_url=payload.lien_url,
        planifie_le=payload.planifie_le,
        statut="planifie" if payload.planifie_le else "brouillon",
        cree_par=current_user.username,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return {"id": post.id, "statut": post.statut, "planifie_le": post.planifie_le}


# ─────────────────────────────────────────────────────────────
# Liste des posts
# ─────────────────────────────────────────────────────────────

@router.get(
    "/posts",
    dependencies=[Depends(require_module("community_manager"))],
)
async def lister_posts(
    statut: Optional[str] = None,
    plateforme: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(PostSocialDB).where(PostSocialDB.compagnie_id == current_user.compagnie_id)
    if statut:
        q = q.where(PostSocialDB.statut == statut)
    if plateforme:
        q = q.where(PostSocialDB.plateforme == plateforme)
    q = q.order_by(desc(PostSocialDB.cree_le)).offset(offset).limit(limit)
    r = await db.execute(q)
    posts = r.scalars().all()

    return [
        {
            "id": p.id,
            "plateforme": p.plateforme,
            "type_contenu": p.type_contenu,
            "sujet": p.sujet,
            "legende": p.legende[:200] + "…" if p.legende and len(p.legende) > 200 else p.legende,
            "hashtags": p.hashtags,
            "statut": p.statut,
            "planifie_le": p.planifie_le,
            "publie_le": p.publie_le,
            "engagement_a": p.engagement_a,
            "engagement_b": p.engagement_b,
            "cree_le": p.cree_le,
        }
        for p in posts
    ]


@router.get(
    "/posts/{post_id}",
    dependencies=[Depends(require_module("community_manager"))],
)
async def detail_post(
    post_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(
        select(PostSocialDB).where(
            PostSocialDB.id == post_id,
            PostSocialDB.compagnie_id == current_user.compagnie_id,
        )
    )
    p = r.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Post introuvable")
    return {
        "id": p.id, "plateforme": p.plateforme, "type_contenu": p.type_contenu,
        "sujet": p.sujet, "legende": p.legende, "legende_variante_b": p.legende_variante_b,
        "hashtags": p.hashtags, "ton": p.ton, "langue": p.langue,
        "image_url": p.image_url, "lien_url": p.lien_url,
        "statut": p.statut, "planifie_le": p.planifie_le, "publie_le": p.publie_le,
        "engagement_a": p.engagement_a, "engagement_b": p.engagement_b,
        "ab_gagnant": p.ab_gagnant, "modele_ia": p.modele_ia,
        "cree_par": p.cree_par, "cree_le": p.cree_le,
    }


@router.put(
    "/posts/{post_id}/statut",
    dependencies=[Depends(require_module("community_manager"))],
)
async def changer_statut_post(
    post_id: int,
    payload: ChangerStatutSchema,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(
        select(PostSocialDB).where(
            PostSocialDB.id == post_id,
            PostSocialDB.compagnie_id == current_user.compagnie_id,
        )
    )
    post = r.scalar_one_or_none()
    if not post:
        raise HTTPException(404, "Post introuvable")

    post.statut = payload.statut
    if payload.statut == "publie":
        post.publie_le = datetime.utcnow()
    await db.commit()
    return {"id": post_id, "statut": payload.statut}


# ─────────────────────────────────────────────────────────────
# Analytics
# ─────────────────────────────────────────────────────────────

@router.get(
    "/analytics",
    dependencies=[Depends(require_module("community_manager"))],
)
async def analytics_cm(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cid = current_user.compagnie_id

    r_stats = await db.execute(
        select(
            PostSocialDB.plateforme,
            PostSocialDB.statut,
            func.count().label("nb"),
            func.sum(PostSocialDB.engagement_a).label("engagement_total"),
        )
        .where(PostSocialDB.compagnie_id == cid)
        .group_by(PostSocialDB.plateforme, PostSocialDB.statut)
    )
    stats = {}
    for row in r_stats.all():
        plat = row[0]
        if plat not in stats:
            stats[plat] = {"publie": 0, "planifie": 0, "brouillon": 0, "engagement_total": 0}
        stats[plat][row[1]] = row[2]
        stats[plat]["engagement_total"] += (row[3] or 0)

    r_total = await db.execute(
        select(func.count()).where(PostSocialDB.compagnie_id == cid)
    )
    total = r_total.scalar() or 0

    return {"total_posts": total, "par_plateforme": stats}


# ─────────────────────────────────────────────────────────────
# Préférences CM
# ─────────────────────────────────────────────────────────────

@router.get(
    "/preferences",
    dependencies=[Depends(require_module("community_manager"))],
)
async def get_preferences(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    prefs = await _get_prefs(current_user.compagnie_id, db)
    return prefs or {}


@router.put(
    "/preferences",
    dependencies=[Depends(require_module("community_manager"))],
)
async def update_preferences(
    payload: PreferencesCMSchema,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(
        select(PreferencesCMDB).where(PreferencesCMDB.compagnie_id == current_user.compagnie_id)
    )
    prefs = r.scalar_one_or_none()
    if not prefs:
        prefs = PreferencesCMDB(compagnie_id=current_user.compagnie_id)
        db.add(prefs)

    prefs.voix_marque = payload.voix_marque
    prefs.mots_interdits = payload.mots_interdits
    prefs.toujours_inclure = payload.toujours_inclure
    prefs.hashtags_defaut = payload.hashtags_defaut
    prefs.heures_publication = payload.heures_publication
    prefs.plateformes_actives = payload.plateformes_actives
    prefs.max_posts_par_jour = payload.max_posts_par_jour
    prefs.ab_test_auto = payload.ab_test_auto
    prefs.secteur_contenu = payload.secteur_contenu
    prefs.modele_ia_prefere = payload.modele_ia_prefere
    prefs.mise_a_jour_le = datetime.utcnow()
    await db.commit()
    return {"message": "Préférences CM mises à jour"}


# ─────────────────────────────────────────────────────────────
# Brouillon depuis tendance
# ─────────────────────────────────────────────────────────────

@router.post(
    "/brouillon-trend",
    dependencies=[Depends(require_module("community_manager"))],
)
async def brouillon_depuis_trend(
    payload: BrouillonTrendSchema,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    prefs = await _get_prefs(current_user.compagnie_id, db)
    secteur = prefs.get("secteur_contenu", "assurance") if prefs else "assurance"

    brouillons = await _moteur(secteur).generer_brouillon_depuis_trend(
        sujet_trend=payload.sujet_trend,
        score_opportunite=payload.score_opportunite,
        region=payload.region,
        prefs=prefs,
    )
    return {
        "sujet_trend": payload.sujet_trend,
        "score_opportunite": payload.score_opportunite,
        **brouillons,
    }


# ─────────────────────────────────────────────────────────────
# Dashboard Analytics ROAS
# ─────────────────────────────────────────────────────────────

@router.get(
    "/analytics/dashboard",
    dependencies=[Depends(require_module("community_manager"))],
)
async def analytics_dashboard(
    periode_jours: int = Query(30, ge=7, le=365),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dashboard analytique complet avec ROAS, meilleure heure, top posts."""
    from modules.community_manager.analytics_cm import get_dashboard_analytics
    dashboard = await get_dashboard_analytics(db, current_user.compagnie_id, periode_jours)
    return {
        "compagnie_id": dashboard.compagnie_id,
        "periode_jours": dashboard.periode_jours,
        "total_posts": dashboard.total_posts,
        "total_impressions": dashboard.total_impressions,
        "total_portee": dashboard.total_portee,
        "total_engagement": dashboard.total_engagement,
        "taux_engagement_moyen": dashboard.taux_engagement_moyen,
        "commandes_attribuees": dashboard.commandes_attribuees,
        "revenus_attribues_fcfa": dashboard.revenus_attribues_fcfa,
        "par_plateforme": [
            {
                "plateforme": p.plateforme,
                "nb_posts": p.nb_posts,
                "impressions": p.impressions,
                "portee": p.portee,
                "engagement": p.engagement,
                "taux_engagement": p.taux_engagement,
                "commandes": p.commandes,
                "revenus_fcfa": p.revenus_fcfa,
            }
            for p in dashboard.par_plateforme
        ],
        "top_posts": [
            {
                "post_id": tp.post_id,
                "plateforme": tp.plateforme,
                "apercu_legende": tp.apercu_legende,
                "impressions": tp.impressions,
                "taux_engagement": tp.taux_engagement,
                "commandes_attribuees": tp.commandes_attribuees,
                "effectiveness_score": tp.effectiveness_score,
                "publie_le": tp.publie_le,
            }
            for tp in dashboard.top_posts
        ],
        "meilleures_heures": [
            {
                "heure": mh.heure,
                "taux_engagement_moyen": mh.taux_engagement_moyen,
                "nb_posts": mh.nb_posts,
            }
            for mh in dashboard.meilleures_heures
        ],
        "tendance_semaines": [
            {
                "semaine_debut": s.semaine_debut,
                "nb_posts": s.nb_posts,
                "portee": s.portee,
                "engagement": s.engagement,
                "commandes": s.commandes,
            }
            for s in dashboard.tendance_semaines
        ],
    }


@router.post(
    "/posts/{post_id}/sync-insights",
    dependencies=[Depends(require_module("community_manager"))],
)
async def sync_insights(
    post_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Synchronise les insights Meta (Facebook/Instagram) pour un post publié."""
    r = await db.execute(
        select(PostSocialDB).where(
            PostSocialDB.id == post_id,
            PostSocialDB.compagnie_id == current_user.compagnie_id,
            PostSocialDB.statut == "publie",
        )
    )
    post = r.scalar_one_or_none()
    if not post:
        raise HTTPException(404, "Post publié introuvable")

    ext_id = post.id_post_externe or post.external_post_id
    if not ext_id:
        raise HTTPException(400, "Aucun ID externe — post non publié via l'API Meta")

    from modules.community_manager.analytics_cm import sync_insights_meta
    from modules.community_manager.publisher_meta import charger_config_meta
    config = await charger_config_meta(db, current_user.compagnie_id, post.plateforme)
    await sync_insights_meta(
        db=db,
        post_id=post_id,
        external_post_id=ext_id,
        plateforme=post.plateforme,
        page_token=config["page_token"],
        compagnie_id=current_user.compagnie_id,
    )
    return {"message": f"Insights synchronisés pour le post {post_id}"}


# ─────────────────────────────────────────────────────────────
# Comptes sociaux connectés (Social Connectors)
# ─────────────────────────────────────────────────────────────

class SocialConnectorSchema(BaseModel):
    plateforme: str                   # facebook | instagram | linkedin
    account_id: Optional[str] = None
    account_nom: Optional[str] = None
    metadata_json: dict = {}          # page_access_token, page_id, ig_user_id


@router.get(
    "/social-accounts",
    dependencies=[Depends(require_module("community_manager"))],
)
async def lister_comptes_sociaux(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Liste les comptes sociaux connectés de la compagnie."""
    r = await db.execute(
        select(SocialConnectorDB).where(
            SocialConnectorDB.compagnie_id == current_user.compagnie_id,
        ).order_by(SocialConnectorDB.plateforme)
    )
    connectors = r.scalars().all()
    return [
        {
            "id": c.id,
            "plateforme": c.plateforme,
            "account_id": c.account_id,
            "account_nom": c.account_nom,
            "est_actif": c.est_actif,
            "connecte_le": c.connecte_le,
            "expire_le": c.expire_le,
        }
        for c in connectors
    ]


@router.post(
    "/social-accounts",
    dependencies=[Depends(require_module("community_manager"))],
)
async def connecter_compte_social(
    payload: SocialConnectorSchema,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enregistre ou met à jour un compte social pour la compagnie."""
    # Upsert par compagnie + plateforme
    r = await db.execute(
        select(SocialConnectorDB).where(
            SocialConnectorDB.compagnie_id == current_user.compagnie_id,
            SocialConnectorDB.plateforme == payload.plateforme,
        )
    )
    connector = r.scalar_one_or_none()
    if connector:
        connector.account_id = payload.account_id
        connector.account_nom = payload.account_nom
        connector.metadata_json = payload.metadata_json
        connector.est_actif = True
        connector.connecte_le = datetime.utcnow()
    else:
        connector = SocialConnectorDB(
            compagnie_id=current_user.compagnie_id,
            plateforme=payload.plateforme,
            account_id=payload.account_id,
            account_nom=payload.account_nom,
            metadata_json=payload.metadata_json,
            cree_par=current_user.username,
        )
        db.add(connector)
    await db.commit()
    await db.refresh(connector)
    return {"id": connector.id, "plateforme": connector.plateforme, "est_actif": connector.est_actif}


@router.delete(
    "/social-accounts/{connector_id}",
    dependencies=[Depends(require_module("community_manager"))],
)
async def deconnecter_compte_social(
    connector_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Désactive un compte social connecté."""
    r = await db.execute(
        select(SocialConnectorDB).where(
            SocialConnectorDB.id == connector_id,
            SocialConnectorDB.compagnie_id == current_user.compagnie_id,
        )
    )
    connector = r.scalar_one_or_none()
    if not connector:
        raise HTTPException(404, "Compte social introuvable")
    connector.est_actif = False
    await db.commit()
    return {"message": f"Compte {connector.plateforme} déconnecté"}
