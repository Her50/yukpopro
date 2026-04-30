"""
Persistance DB des Enquêtes — sérialisation JSON blob dans EtudeDB.
Chaque Etude (+ formulaire + transcriptions + analyses) est sauvegardée
comme un seul enregistrement JSON pour éviter ~20 tables relationnelles.

Fonctions publiques :
  sauvegarder_etude(etude, user_id)  — upsert async
  charger_etudes_user(user_id)       — load au login / refresh
  charger_toutes_etudes()            — warm-up au démarrage
  supprimer_etude(etude_id)          — suppression physique
"""
from __future__ import annotations

import dataclasses
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select, delete

if TYPE_CHECKING:
    pass

logger = logging.getLogger("yukpo_assurance.enquetes.persistence")


# ─── Sérialisation ─────────────────────────────────────────────────────────────

def _etude_to_dict(etude) -> dict:
    """Convertit un dataclass Etude (récursivement) en dict JSON-sérialisable."""
    def _conv(obj):
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return {f.name: _conv(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
        if isinstance(obj, list):
            return [_conv(i) for i in obj]
        if isinstance(obj, dict):
            return {k: _conv(v) for k, v in obj.items()}
        return obj
    return _conv(etude)


def _dict_to_etude(data: dict):
    """Reconstruit les dataclasses Etude depuis un dict JSON (chargé depuis DB)."""
    from modules.enquetes.gestionnaire_enquetes import (
        Etude, Formulaire, QuestionFormulaire, ThemeQualitatif, TranscriptionAudio,
    )

    def _build_question(d: dict) -> QuestionFormulaire:
        valid = {f.name for f in dataclasses.fields(QuestionFormulaire)}
        return QuestionFormulaire(**{k: v for k, v in d.items() if k in valid})

    def _build_formulaire(d: dict | None) -> Formulaire | None:
        if not d:
            return None
        valid = {f.name for f in dataclasses.fields(Formulaire)}
        kwargs = {k: v for k, v in d.items() if k in valid}
        kwargs["questions"] = [_build_question(q) for q in (d.get("questions") or [])]
        return Formulaire(**kwargs)

    def _build_transcription(d: dict) -> TranscriptionAudio:
        valid = {f.name for f in dataclasses.fields(TranscriptionAudio)}
        return TranscriptionAudio(**{k: v for k, v in d.items() if k in valid})

    def _build_theme(d: dict) -> ThemeQualitatif:
        valid = {f.name for f in dataclasses.fields(ThemeQualitatif)}
        return ThemeQualitatif(**{k: v for k, v in d.items() if k in valid})

    valid_etude = {f.name for f in dataclasses.fields(Etude)}
    kwargs = {k: v for k, v in data.items() if k in valid_etude}
    kwargs["transcriptions"] = [_build_transcription(t) for t in (data.get("transcriptions") or [])]
    kwargs["themes"] = [_build_theme(t) for t in (data.get("themes") or [])]
    kwargs["formulaire"] = _build_formulaire(data.get("formulaire"))
    return Etude(**kwargs)


# ─── Opérations DB ─────────────────────────────────────────────────────────────

async def sauvegarder_etude(etude, user_id: int) -> None:
    """Upsert l'étude dans EtudeDB (crée ou met à jour)."""
    from core.database import async_session_maker, EtudeDB

    try:
        data = _etude_to_dict(etude)
        # Colonnes TIMESTAMP WITHOUT TIME ZONE → datetime naïf requis par asyncpg
        now = datetime.utcnow()
        async with async_session_maker() as session:
            result = await session.get(EtudeDB, etude.etude_id)
            if result:
                result.titre      = etude.titre
                result.statut     = etude.statut
                result.data       = data
                result.modifie_le = now
            else:
                session.add(EtudeDB(
                    etude_id   = etude.etude_id,
                    user_id    = user_id,
                    titre      = etude.titre,
                    statut     = etude.statut,
                    data       = data,
                    cree_le    = now,
                    modifie_le = now,
                ))
            await session.commit()
    except Exception as e:
        logger.error(f"[Enquêtes] Échec persistance etude {etude.etude_id}: {e}")


async def charger_etudes_user(user_id: int) -> list:
    """Charge toutes les études d'un utilisateur depuis la DB → list[Etude]."""
    from core.database import async_session_maker, EtudeDB
    from modules.enquetes import gestionnaire_enquetes as ge

    try:
        async with async_session_maker() as session:
            rows = (await session.execute(
                select(EtudeDB).where(EtudeDB.user_id == user_id)
            )).scalars().all()

        etudes = []
        for row in rows:
            try:
                etude = _dict_to_etude(row.data)
                ge._etudes[etude.etude_id] = etude
                if etude.formulaire:
                    ge._formulaires_publics[etude.formulaire.formulaire_id] = etude.etude_id
                etudes.append(etude)
            except Exception as e:
                logger.warning(f"[Enquêtes] Impossible de reconstruire {row.etude_id}: {e}")

        logger.info(f"[Enquêtes] {len(etudes)} étude(s) chargée(s) pour user {user_id}")
        return etudes
    except Exception as e:
        logger.error(f"[Enquêtes] Échec chargement user {user_id}: {e}")
        return []


async def charger_toutes_etudes() -> int:
    """Warm-up au démarrage : charge toutes les études en mémoire."""
    from core.database import async_session_maker, EtudeDB
    from modules.enquetes import gestionnaire_enquetes as ge

    try:
        async with async_session_maker() as session:
            rows = (await session.execute(select(EtudeDB))).scalars().all()

        count = 0
        for row in rows:
            try:
                etude = _dict_to_etude(row.data)
                ge._etudes[etude.etude_id] = etude
                if etude.formulaire:
                    ge._formulaires_publics[etude.formulaire.formulaire_id] = etude.etude_id
                count += 1
            except Exception as e:
                logger.warning(f"[Enquêtes] Reconstruction {row.etude_id} échouée: {e}")

        logger.info(f"[Enquêtes] Warm-up: {count} étude(s) chargée(s)")
        return count
    except Exception as e:
        logger.error(f"[Enquêtes] Warm-up échoué: {e}")
        return 0


async def supprimer_etude(etude_id: str) -> None:
    """Supprime une étude de la DB."""
    from core.database import async_session_maker, EtudeDB

    try:
        async with async_session_maker() as session:
            await session.execute(delete(EtudeDB).where(EtudeDB.etude_id == etude_id))
            await session.commit()
    except Exception as e:
        logger.error(f"[Enquêtes] Échec suppression {etude_id}: {e}")
