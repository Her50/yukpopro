"""
Analytics Community Manager — YukpoAssurance
Portage de social_analytics_service.rs de yukpomnang2.

Dashboard unifié cross-plateformes :
- Engagement (likes, commentaires, partages, portée)
- ROAS social (commandes et revenus attribués aux posts)
- Meilleure heure de publication (data-driven)
- Top posts par effectiveness_score
- Tendance hebdomadaire
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("yukpo.cm.analytics")


@dataclass
class StatsPlateforme:
    plateforme: str
    nb_posts: int
    impressions: int
    portee: int
    engagement: int
    taux_engagement: float  # %
    commandes: int
    revenus_fcfa: int


@dataclass
class TopPost:
    post_id: Optional[int]
    plateforme: str
    apercu_legende: str
    impressions: int
    taux_engagement: float
    commandes_attribuees: int
    effectiveness_score: float
    publie_le: Optional[str]


@dataclass
class MeilleureHeure:
    heure: int              # 0-23
    taux_engagement_moyen: float
    nb_posts: int


@dataclass
class StatsSemaine:
    semaine_debut: str
    nb_posts: int
    portee: int
    engagement: int
    commandes: int


@dataclass
class DashboardAnalytics:
    compagnie_id: int
    periode_jours: int
    total_posts: int
    total_impressions: int
    total_portee: int
    total_engagement: int
    taux_engagement_moyen: float
    commandes_attribuees: int
    revenus_attribues_fcfa: int
    par_plateforme: List[StatsPlateforme]
    top_posts: List[TopPost]
    meilleures_heures: List[MeilleureHeure]
    tendance_semaines: List[StatsSemaine]


async def get_dashboard_analytics(
    db,
    compagnie_id: int,
    periode_jours: int = 30,
) -> DashboardAnalytics:
    """
    Charge le dashboard complet depuis la table AnalyticsPostDB.
    Portage de get_social_dashboard() de yukpomnang2.
    """
    from sqlalchemy import select, func, text
    from core.database import AnalyticsPostDB, PostSocialDB

    depuis = f"{periode_jours} days"

    # ── Agrégats globaux ─────────────────────────────────────────────────────
    result_global = await db.execute(
        select(
            func.count().label("total_posts"),
            func.coalesce(func.sum(AnalyticsPostDB.impressions), 0).label("total_impressions"),
            func.coalesce(func.sum(AnalyticsPostDB.portee), 0).label("total_portee"),
            func.coalesce(
                func.sum(AnalyticsPostDB.likes + AnalyticsPostDB.commentaires + AnalyticsPostDB.partages), 0
            ).label("total_engagement"),
            func.coalesce(func.avg(AnalyticsPostDB.taux_engagement), 0).label("taux_moyen"),
            func.coalesce(func.sum(AnalyticsPostDB.commandes_attribuees), 0).label("total_commandes"),
            func.coalesce(func.sum(AnalyticsPostDB.revenus_attribues_fcfa), 0).label("total_revenus"),
        ).where(
            AnalyticsPostDB.compagnie_id == compagnie_id,
            text(f"publie_le >= NOW() - INTERVAL '{depuis}'"),
        )
    )
    glob = result_global.one()

    # ── Par plateforme ────────────────────────────────────────────────────────
    result_plat = await db.execute(
        select(
            AnalyticsPostDB.plateforme,
            func.count().label("nb_posts"),
            func.coalesce(func.sum(AnalyticsPostDB.impressions), 0).label("impressions"),
            func.coalesce(func.sum(AnalyticsPostDB.portee), 0).label("portee"),
            func.coalesce(
                func.sum(AnalyticsPostDB.likes + AnalyticsPostDB.commentaires + AnalyticsPostDB.partages), 0
            ).label("engagement"),
            func.coalesce(func.avg(AnalyticsPostDB.taux_engagement), 0).label("taux"),
            func.coalesce(func.sum(AnalyticsPostDB.commandes_attribuees), 0).label("commandes"),
            func.coalesce(func.sum(AnalyticsPostDB.revenus_attribues_fcfa), 0).label("revenus"),
        ).where(
            AnalyticsPostDB.compagnie_id == compagnie_id,
            text(f"publie_le >= NOW() - INTERVAL '{depuis}'"),
        ).group_by(AnalyticsPostDB.plateforme)
        .order_by(text("impressions DESC"))
    )
    par_plateforme = [
        StatsPlateforme(
            plateforme=row.plateforme,
            nb_posts=row.nb_posts or 0,
            impressions=row.impressions or 0,
            portee=row.portee or 0,
            engagement=row.engagement or 0,
            taux_engagement=round(float(row.taux or 0), 2),
            commandes=row.commandes or 0,
            revenus_fcfa=row.revenus or 0,
        )
        for row in result_plat.all()
    ]

    # ── Top 5 posts ───────────────────────────────────────────────────────────
    result_top = await db.execute(
        select(
            AnalyticsPostDB.post_id,
            AnalyticsPostDB.plateforme,
            AnalyticsPostDB.impressions,
            AnalyticsPostDB.taux_engagement,
            AnalyticsPostDB.commandes_attribuees,
            AnalyticsPostDB.effectiveness_score,
            AnalyticsPostDB.publie_le,
            PostSocialDB.legende,
        ).outerjoin(PostSocialDB, PostSocialDB.id == AnalyticsPostDB.post_id)
        .where(
            AnalyticsPostDB.compagnie_id == compagnie_id,
            text(f"analytics_posts.publie_le >= NOW() - INTERVAL '{depuis}'"),
        ).order_by(text("effectiveness_score DESC NULLS LAST"))
        .limit(5)
    )
    top_posts = [
        TopPost(
            post_id=row.post_id,
            plateforme=row.plateforme or "",
            apercu_legende=(row.legende or "")[:120],
            impressions=row.impressions or 0,
            taux_engagement=round(float(row.taux_engagement or 0), 2),
            commandes_attribuees=row.commandes_attribuees or 0,
            effectiveness_score=round(float(row.effectiveness_score or 0), 2),
            publie_le=row.publie_le.isoformat() if row.publie_le else None,
        )
        for row in result_top.all()
    ]

    # ── Meilleures heures ─────────────────────────────────────────────────────
    result_heures = await db.execute(
        select(
            func.extract("hour", AnalyticsPostDB.publie_le).label("heure"),
            func.avg(AnalyticsPostDB.taux_engagement).label("taux_moyen"),
            func.count().label("nb_posts"),
        ).where(
            AnalyticsPostDB.compagnie_id == compagnie_id,
            AnalyticsPostDB.taux_engagement.isnot(None),
            text(f"publie_le >= NOW() - INTERVAL '{depuis}'"),
        ).group_by(text("1"))
        .order_by(text("taux_moyen DESC"))
        .limit(5)
    )
    meilleures_heures = [
        MeilleureHeure(
            heure=int(row.heure or 0),
            taux_engagement_moyen=round(float(row.taux_moyen or 0), 3),
            nb_posts=row.nb_posts or 0,
        )
        for row in result_heures.all()
    ]

    # ── Tendance hebdomadaire (12 semaines) ───────────────────────────────────
    result_weeks = await db.execute(
        select(
            text("DATE_TRUNC('week', publie_le)::date::text as semaine_debut"),
            func.count().label("nb_posts"),
            func.coalesce(func.sum(AnalyticsPostDB.portee), 0).label("portee"),
            func.coalesce(
                func.sum(AnalyticsPostDB.likes + AnalyticsPostDB.commentaires + AnalyticsPostDB.partages), 0
            ).label("engagement"),
            func.coalesce(func.sum(AnalyticsPostDB.commandes_attribuees), 0).label("commandes"),
        ).where(
            AnalyticsPostDB.compagnie_id == compagnie_id,
            text("publie_le >= NOW() - INTERVAL '12 weeks'"),
        ).group_by(text("1"))
        .order_by(text("1 DESC"))
        .limit(12)
    )
    tendance_semaines = [
        StatsSemaine(
            semaine_debut=row.semaine_debut or "",
            nb_posts=row.nb_posts or 0,
            portee=row.portee or 0,
            engagement=row.engagement or 0,
            commandes=row.commandes or 0,
        )
        for row in result_weeks.all()
    ]

    return DashboardAnalytics(
        compagnie_id=compagnie_id,
        periode_jours=periode_jours,
        total_posts=glob.total_posts or 0,
        total_impressions=glob.total_impressions or 0,
        total_portee=glob.total_portee or 0,
        total_engagement=glob.total_engagement or 0,
        taux_engagement_moyen=round(float(glob.taux_moyen or 0), 3),
        commandes_attribuees=glob.total_commandes or 0,
        revenus_attribues_fcfa=glob.total_revenus or 0,
        par_plateforme=par_plateforme,
        top_posts=top_posts,
        meilleures_heures=meilleures_heures,
        tendance_semaines=tendance_semaines,
    )


async def sync_insights_meta(
    db,
    post_id: int,
    external_post_id: str,
    plateforme: str,
    page_token: str,
    compagnie_id: int,
) -> None:
    """
    Récupère les insights d'un post Meta et les persiste dans AnalyticsPostDB.
    Portage de sync_meta_post_insights() de yukpomnang2.
    """
    from sqlalchemy import select
    from core.database import AnalyticsPostDB
    from modules.community_manager.publisher_meta import (
        recuperer_insights_facebook, recuperer_insights_instagram,
    )

    try:
        if plateforme == "facebook":
            insights = await recuperer_insights_facebook(page_token, external_post_id)
            impressions = insights.get("post_impressions", 0)
            portee = insights.get("post_reach", 0)
            engagement = insights.get("post_engaged_users", 0)
            likes = 0
            commentaires = 0
            partages = 0
        elif plateforme == "instagram":
            insights = await recuperer_insights_instagram("", external_post_id, page_token)
            impressions = insights.get("impressions", 0)
            portee = insights.get("reach", 0)
            likes = insights.get("likes", 0)
            commentaires = insights.get("comments", 0)
            partages = insights.get("shares", 0)
            engagement = likes + commentaires + partages
        else:
            return

        total_audience = portee if portee > 0 else 1
        taux = round(engagement / total_audience * 100, 3)
        effectiveness = round((taux * 0.4 + impressions / 10000 * 0.3 + portee / 5000 * 0.3), 2)

        # Upsert analytics
        result = await db.execute(
            select(AnalyticsPostDB).where(AnalyticsPostDB.post_id == post_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.impressions = impressions
            existing.portee = portee
            existing.likes = likes
            existing.commentaires = commentaires
            existing.partages = partages
            existing.taux_engagement = taux
            existing.effectiveness_score = effectiveness
        else:
            db.add(AnalyticsPostDB(
                post_id=post_id,
                compagnie_id=compagnie_id,
                plateforme=plateforme,
                impressions=impressions,
                portee=portee,
                likes=likes,
                commentaires=commentaires,
                partages=partages,
                taux_engagement=taux,
                effectiveness_score=effectiveness,
            ))

        await db.commit()
        logger.info(f"[Analytics] Post {post_id} sync OK — engagement {taux:.2f}%")

    except Exception as e:
        logger.error(f"[Analytics] Erreur sync insights post {post_id}: {e}")
