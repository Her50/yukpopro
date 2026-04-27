"""
Persistance DB des sessions Copilote — upsert JSON dans SessionCopiloteDB.
L'historique est plafonné à 100 échanges pour éviter la croissance illimitée.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select

if TYPE_CHECKING:
    pass

logger = logging.getLogger("yukpo_assurance.copilote.persistence")

_MAX_HISTORIQUE = 100


async def sauvegarder_session(session) -> None:
    """Upsert la session copilote dans SessionCopiloteDB."""
    from core.database import async_session_maker, SessionCopiloteDB

    try:
        historique = (session.historique or [])[-_MAX_HISTORIQUE:]
        now = datetime.now(timezone.utc)
        async with async_session_maker() as db:
            row = await db.get(SessionCopiloteDB, session.user_id)
            if row:
                row.role           = session.role
                row.historique     = historique
                row.contexte_actif = session.contexte_actif
                row.modifie_le     = now
            else:
                db.add(SessionCopiloteDB(
                    user_id        = session.user_id,
                    role           = session.role,
                    historique     = historique,
                    contexte_actif = session.contexte_actif,
                    modifie_le     = now,
                ))
            await db.commit()
    except Exception as e:
        logger.error(f"[Copilote] Échec persistance session user {session.user_id}: {e}")


async def charger_session(user_id: int):
    """Charge une session depuis la DB. Retourne SessionCopilote ou None."""
    from core.database import async_session_maker, SessionCopiloteDB
    from modules.copilote.assistant_quotidien import SessionCopilote, _sessions

    try:
        async with async_session_maker() as db:
            row = await db.get(SessionCopiloteDB, user_id)
        if row:
            s = SessionCopilote(
                user_id        = row.user_id,
                role           = row.role,
                historique     = list(row.historique or []),
                contexte_actif = row.contexte_actif,
            )
            _sessions[user_id] = s
            return s
    except Exception as e:
        logger.warning(f"[Copilote] Impossible de charger session user {user_id}: {e}")
    return None


async def charger_toutes_sessions() -> int:
    """Warm-up au démarrage — charge toutes les sessions en mémoire."""
    from core.database import async_session_maker, SessionCopiloteDB
    from modules.copilote.assistant_quotidien import SessionCopilote, _sessions

    try:
        async with async_session_maker() as db:
            rows = (await db.execute(select(SessionCopiloteDB))).scalars().all()

        count = 0
        for row in rows:
            _sessions[row.user_id] = SessionCopilote(
                user_id        = row.user_id,
                role           = row.role,
                historique     = list(row.historique or []),
                contexte_actif = row.contexte_actif,
            )
            count += 1

        logger.info(f"[Copilote] Warm-up: {count} session(s) chargée(s)")
        return count
    except Exception as e:
        logger.error(f"[Copilote] Warm-up échoué: {e}")
        return 0
