"""Tâches Celery — Email follow-up landing leads (Phase B4).

Scheduled daily via beat (cf. core/celery_app.py beat_schedule).

Logique :
  • Scan landing_leads où source='form'/'newsletter' avec email renseigné.
  • Pour chaque user qui a `landing_followup_settings.jX_actif=True` :
    - J+3 → envoie email si lead créé il y a 3-4 jours ET statut='non_lu'
            ET pas déjà notifié (champ notes='followup_j3' utilisé comme flag).
    - J+7 → envoie email si lead créé il y a 7-8 jours ET statut in
            ('non_lu', 'lu') ET pas déjà notifié J+7.

Auto-reply J+0 → déclenché en synchro depuis routes_landing_leads.py
au moment de la capture (pas par cette tâche).

Facturation : chaque email envoyé débite `whatsapp_message` côté MARCHAND
(forfait existant). Si solde insuffisant → email skip (log warning).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, select

from core.celery_app import celery_app
from core.database import (
    async_session_maker, LandingFollowupSettingsDB,
    LandingLeadDB, LandingPublicationDB, UtilisateurDB,
)

logger = logging.getLogger("yukpo_assurance.tasks.landing_followup")


_FLAG_J3 = "[followup_j3_envoyé]"
_FLAG_J7 = "[followup_j7_envoyé]"


def _interpoler(template: str | None, lead: LandingLeadDB) -> str:
    """Remplace {nom}, {email}, {slug}, {message} dans un template."""
    if not template:
        return ""
    return (template
            .replace("{nom}", lead.nom or "")
            .replace("{email}", lead.email or "")
            .replace("{slug}", lead.slug)
            .replace("{message}", lead.message or "")
            )


async def _envoyer_un_followup(
    lead: LandingLeadDB,
    settings: LandingFollowupSettingsDB,
    pub: LandingPublicationDB,
    marchand: UtilisateurDB,
    quand: str,
) -> bool:
    """Envoie 1 follow-up. WA prioritaire si tél fourni, email sinon.

    Retourne True si envoyé OK sur au moins un canal.
    """
    if quand == "j3":
        if not settings.j3_actif or not settings.j3_sujet:
            return False
        sujet = _interpoler(settings.j3_sujet, lead)
        corps = _interpoler(settings.j3_corps, lead)
        flag = _FLAG_J3
    elif quand == "j7":
        if not settings.j7_actif or not settings.j7_sujet:
            return False
        sujet = _interpoler(settings.j7_sujet, lead)
        corps = _interpoler(settings.j7_corps, lead)
        flag = _FLAG_J7
    else:
        return False

    # Si ni email ni téléphone → impossible de joindre
    if not lead.email and not lead.telephone:
        return False

    from modules.bureau.service_credits_bureau import debiter_forfait_unifie

    envoye = False
    # 1. WhatsApp / SMS prioritaire si téléphone fourni
    if lead.telephone:
        try:
            from core.notifications import notifier_telephone
            # SMS = pas de sujet → on prépend juste le sujet en titre
            contenu = (f"{sujet}\n\n{corps}" if sujet else corps)[:1500]
            res = await notifier_telephone(
                lead.telephone, contenu,
                metadata={"type": "followup", "quand": quand, "slug": lead.slug},
                prefer="whatsapp",
            )
            if res["canal_final"] != "none":
                envoye = True
                logger.info(
                    f"[Followup/{quand}] lead={lead.id} canal={res['canal_final']}"
                )
        except Exception as e:
            logger.warning(f"[Followup/{quand}] tel échec lead={lead.id}: {e}")

    # 2. Email — fallback si pas de tél, ou bonus si tél a marché
    if lead.email:
        try:
            from core.notifications import _envoyer_email
            ok = await _envoyer_email(lead.email, corps, sujet=sujet)
            if ok:
                envoye = True
        except Exception as e:
            logger.warning(f"[Followup/{quand}] email échec lead={lead.id}: {e}")

    if not envoye:
        return False

    try:
        await debiter_forfait_unifie(
            marchand.id, "whatsapp_message", module="landing_followup",
        )
    except Exception as e:
        logger.warning(f"[Followup] débit user={marchand.id} échec : {e}")

    lead.notes = (lead.notes or "") + f"\n{flag} {datetime.utcnow().isoformat()}"
    return True


async def _scan_et_envoyer() -> dict:
    """Scan + envoi de tous les follow-ups dus. Retourne stats."""
    envoye_j3 = 0
    envoye_j7 = 0
    erreurs = 0
    async with async_session_maker() as db:
        now = datetime.utcnow()

        # Fenêtres temporelles : leads créés entre J-X et J-(X+1)
        # (on tolère un jour d'imprécision vs. exécution daily du beat)
        fen_j3_min = now - timedelta(days=4)
        fen_j3_max = now - timedelta(days=3)
        fen_j7_min = now - timedelta(days=8)
        fen_j7_max = now - timedelta(days=7)

        # Récupère tous les settings followup actifs
        settings_rows = (await db.execute(
            select(LandingFollowupSettingsDB).where(
                (LandingFollowupSettingsDB.j3_actif.is_(True))
                | (LandingFollowupSettingsDB.j7_actif.is_(True))
            )
        )).scalars().all()
        if not settings_rows:
            return {"envoye_j3": 0, "envoye_j7": 0, "erreurs": 0,
                    "raison": "aucun followup actif"}

        for s in settings_rows:
            marchand = (await db.execute(
                select(UtilisateurDB).where(UtilisateurDB.id == s.user_id)
            )).scalar_one_or_none()
            if not marchand:
                continue

            # J+3 : leads de ce marchand, créés il y a 3-4j, statut=non_lu
            if s.j3_actif:
                q = (
                    select(LandingLeadDB, LandingPublicationDB)
                    .join(LandingPublicationDB,
                          LandingPublicationDB.slug == LandingLeadDB.slug)
                    .where(LandingPublicationDB.user_id == s.user_id)
                    .where(and_(
                        LandingLeadDB.created_at >= fen_j3_min,
                        LandingLeadDB.created_at < fen_j3_max,
                    ))
                    .where(LandingLeadDB.statut == "non_lu")
                )
                for lead, pub in (await db.execute(q)).all():
                    if _FLAG_J3 in (lead.notes or ""):
                        continue
                    try:
                        ok = await _envoyer_un_followup(lead, s, pub, marchand, "j3")
                        if ok:
                            envoye_j3 += 1
                    except Exception as e:
                        logger.warning(f"[Followup/j3] lead={lead.id}: {e}")
                        erreurs += 1

            # J+7 : statut non_lu OU lu
            if s.j7_actif:
                q = (
                    select(LandingLeadDB, LandingPublicationDB)
                    .join(LandingPublicationDB,
                          LandingPublicationDB.slug == LandingLeadDB.slug)
                    .where(LandingPublicationDB.user_id == s.user_id)
                    .where(and_(
                        LandingLeadDB.created_at >= fen_j7_min,
                        LandingLeadDB.created_at < fen_j7_max,
                    ))
                    .where(LandingLeadDB.statut.in_(["non_lu", "lu"]))
                )
                for lead, pub in (await db.execute(q)).all():
                    if _FLAG_J7 in (lead.notes or ""):
                        continue
                    try:
                        ok = await _envoyer_un_followup(lead, s, pub, marchand, "j7")
                        if ok:
                            envoye_j7 += 1
                    except Exception as e:
                        logger.warning(f"[Followup/j7] lead={lead.id}: {e}")
                        erreurs += 1

        await db.commit()

    return {"envoye_j3": envoye_j3, "envoye_j7": envoye_j7, "erreurs": erreurs}


@celery_app.task(name="landing.followup.daily_scan")
def daily_scan_followup() -> dict:
    """Beat-scheduled : balaie quotidiennement les leads et envoie J+3/J+7."""
    try:
        result = asyncio.run(_scan_et_envoyer())
        logger.info(f"[Followup] résultats : {result}")
        return result
    except Exception as e:
        logger.error(f"[Followup] échec global : {e}", exc_info=True)
        return {"envoye_j3": 0, "envoye_j7": 0, "erreurs": 1, "error": str(e)}


async def envoyer_auto_reply_j0(
    lead: LandingLeadDB, settings: LandingFollowupSettingsDB | None,
) -> bool:
    """Auto-reply visiteur J+0 — appelé synchrone depuis route capture.

    Priorité WhatsApp/SMS si visiteur a fourni un téléphone (contexte
    africain). Fallback email si seulement email fourni.
    """
    if not settings or not settings.j0_actif:
        return False
    if not lead.email and not lead.telephone:
        return False

    sujet = _interpoler(settings.j0_sujet, lead) or "Merci pour votre message"
    corps = _interpoler(settings.j0_corps, lead) or (
        "Bonjour,\n\nMerci pour votre message — nous revenons vers vous "
        "très vite.\n\nCordialement."
    )

    envoye = False
    # WhatsApp / SMS prioritaire
    if lead.telephone:
        try:
            from core.notifications import notifier_telephone
            contenu = (f"{sujet}\n\n{corps}" if sujet else corps)[:1500]
            res = await notifier_telephone(
                lead.telephone, contenu,
                metadata={"type": "auto_reply_j0", "slug": lead.slug},
                prefer="whatsapp",
            )
            if res["canal_final"] != "none":
                envoye = True
        except Exception as e:
            logger.warning(f"[AutoReply/J0] tel échec lead={lead.id}: {e}")

    if lead.email and not envoye:
        try:
            from core.notifications import _envoyer_email
            envoye = await _envoyer_email(lead.email, corps, sujet=sujet)
        except Exception as e:
            logger.warning(f"[AutoReply/J0] email échec lead={lead.id}: {e}")

    return envoye
