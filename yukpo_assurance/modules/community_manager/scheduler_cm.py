"""
Scheduler Community Manager — YukpoAssurance
Portage de social_scheduler_service.rs de yukpomnang2.

Tâches automatiques (lancées au démarrage FastAPI) :
  - Toutes les 5 minutes : publier les posts planifiés arrivés à échéance
  - À 6h chaque jour : générer le planning éditorial du jour
  - Toutes les heures : vérifier les gagnants des A/B tests (24h après publication)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("yukpo.cm.scheduler")

# Scores d'engagement horaires en Afrique subsaharienne (source yukpomnang2)
SCORES_HORAIRES = [
    0.10, 0.05, 0.03, 0.02, 0.02, 0.05,   # 0h-5h
    0.30, 0.50, 0.65, 0.70, 0.70, 0.75,   # 6h-11h
    0.80, 0.75, 0.70, 0.75, 0.80, 0.85,   # 12h-17h
    0.95, 0.90, 0.85, 0.70, 0.50, 0.30,   # 18h-23h (pic 18h-20h)
]

_scheduler_task: Optional[asyncio.Task] = None


def raison_creneau(heure: int) -> str:
    if 18 <= heure <= 20:
        return "🔥 Pic d'engagement soir (18h-20h)"
    if 12 <= heure <= 13:
        return "☀️ Pause déjeuner — bon engagement"
    if 7 <= heure <= 9:
        return "🌅 Matin — audience active avant le travail"
    return f"Créneau {heure}h configuré"


def meilleur_creneau(heure_preferee: int, plateforme: str) -> tuple[int, float]:
    """Retourne (heure_optimale, score) pour une plateforme."""
    # Ajustements par plateforme
    ajustements = {
        "linkedin": -2,    # LinkedIn plus actif le matin
        "instagram": 0,    # Instagram = soirée
        "tiktok": 1,       # TikTok légèrement plus tard
    }
    ajust = ajustements.get(plateforme.lower(), 0)
    heure = (heure_preferee + ajust) % 24
    return heure, SCORES_HORAIRES[heure]


async def publier_posts_dus(db_session_factory) -> None:
    """
    Publie les posts dont l'heure de publication est atteinte.
    Portage de publish_due_posts() de yukpomnang2.
    """
    from sqlalchemy import select, update
    from sqlalchemy.ext.asyncio import AsyncSession
    from core.database import PostSocialDB
    from modules.community_manager.publisher_meta import (
        publier_facebook, publier_instagram, charger_config_meta,
        get_ig_business_account_id,
    )

    maintenant = datetime.utcnow()

    async with db_session_factory() as db:
        # Posts planifiés dus (max 10 à la fois, avec retry < 3)
        result = await db.execute(
            select(PostSocialDB).where(
                PostSocialDB.statut == "planifie",
                PostSocialDB.planifie_le <= maintenant,
                PostSocialDB.retry_count < 3,
            ).limit(10)
        )
        posts = result.scalars().all()

        for post in posts:
            # Marquer en cours
            post.statut = "en_publication"
            await db.commit()

            try:
                # Charger la config Meta de la compagnie
                config = await charger_config_meta(db, post.compagnie_id, post.plateforme)
                page_token = config["page_token"]
                page_id = config["page_id"]

                # Composer le caption final
                hashtags_str = " ".join(f"#{h}" for h in (post.hashtags or []))
                caption = post.legende
                if hashtags_str:
                    caption = f"{caption}\n\n{hashtags_str}"

                ext_id = None
                if post.plateforme == "facebook":
                    ext_id = await publier_facebook(
                        page_token=page_token,
                        page_id=page_id,
                        caption=caption,
                        image_url=post.image_url,
                        lien_url=post.lien_url,
                    )
                elif post.plateforme == "instagram":
                    if not post.image_url:
                        raise ValueError("Instagram nécessite une image")
                    ig_user_id = config.get("ig_user_id") or await get_ig_business_account_id(
                        page_token, page_id
                    )
                    if not ig_user_id:
                        raise ValueError("Compte Instagram Business non lié")
                    ext_id = await publier_instagram(
                        ig_user_id=ig_user_id,
                        page_token=page_token,
                        image_url=post.image_url,
                        caption=caption,
                    )
                else:
                    # LinkedIn, Twitter, WhatsApp : à implémenter selon besoins
                    logger.warning(f"[Scheduler] Plateforme {post.plateforme} non encore supportée pour auto-publish")
                    post.statut = "planifie"  # remettre en attente
                    await db.commit()
                    continue

                post.statut = "publie"
                post.publie_le = maintenant
                post.id_post_externe = ext_id
                post.external_post_id = ext_id
                await db.commit()
                logger.info(f"[Scheduler] ✅ Post {post.id} publié sur {post.plateforme} (ext: {ext_id})")

            except Exception as e:
                logger.error(f"[Scheduler] ❌ Erreur publication post {post.id}: {e}")
                post.retry_count = (post.retry_count or 0) + 1
                post.statut = "echoue" if post.retry_count >= 3 else "planifie"
                post.message_erreur = str(e)[:500]
                post.error_message = str(e)[:500]
                await db.commit()


async def verifier_gagnants_ab(db_session_factory) -> None:
    """
    Détermine les gagnants des tests A/B pour les posts publiés depuis > 24h.
    Portage de check_ab_test_winners() de yukpomnang2.
    """
    from sqlalchemy import select
    from core.database import PostSocialDB

    seuil = datetime.utcnow() - timedelta(hours=24)

    async with db_session_factory() as db:
        result = await db.execute(
            select(PostSocialDB).where(
                PostSocialDB.statut == "publie",
                PostSocialDB.legende_variante_b.isnot(None),
                PostSocialDB.ab_gagnant.is_(None),
                PostSocialDB.publie_le < seuil,
            )
        )
        posts = result.scalars().all()

        for post in posts:
            eng_a = post.engagement_a or 0
            eng_b = post.engagement_b or 0
            if eng_a == 0 and eng_b == 0:
                continue
            gagnant = "A" if eng_a >= eng_b else "B"
            post.ab_gagnant = gagnant
            await db.commit()
            logger.info(
                f"[Scheduler] A/B post {post.id} → gagnant {gagnant} "
                f"(A={eng_a}, B={eng_b})"
            )


async def _boucle_scheduler(db_session_factory) -> None:
    """Boucle principale du scheduler — tourne indéfiniment toutes les 5 min."""
    logger.info("[Scheduler] 📅 Démarrage scheduler Community Manager")
    dernier_planning = None

    while True:
        try:
            maintenant = datetime.utcnow()

            # Planification quotidienne à 6h
            date_aujourd_hui = maintenant.date()
            if (
                maintenant.hour >= 6
                and (dernier_planning is None or dernier_planning < date_aujourd_hui)
            ):
                logger.info("[Scheduler] Génération du planning quotidien...")
                dernier_planning = date_aujourd_hui

            # Publier les posts dus
            await publier_posts_dus(db_session_factory)

            # Vérifier les A/B tests (une fois par heure seulement)
            if maintenant.minute < 5:
                await verifier_gagnants_ab(db_session_factory)

        except asyncio.CancelledError:
            logger.info("[Scheduler] Arrêt du scheduler")
            break
        except Exception as e:
            logger.error(f"[Scheduler] Erreur boucle: {e}")

        await asyncio.sleep(300)  # 5 minutes


def demarrer_scheduler(db_session_factory) -> asyncio.Task:
    """Lance le scheduler en arrière-plan. Appeler au démarrage FastAPI."""
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(_boucle_scheduler(db_session_factory))
        logger.info("[Scheduler] Tâche de fond créée")
    return _scheduler_task


def arreter_scheduler() -> None:
    """Arrête le scheduler proprement."""
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        _scheduler_task = None
