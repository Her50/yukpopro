"""
Routes FastAPI — Veille & Tendances (TrendPulse)
- GET /pulse              : tendances actuelles par région
- GET /pour-moi           : tendances personnalisées selon le secteur
- POST /analyser          : analyse IA approfondie
- GET /veille-reglementaire : actualités réglementaires du secteur
- GET /historique         : snapshots historiques des tendances
- GET /alertes            : alertes actives
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db, CompagnieDB, TrendSnapshotDB, AlerteTrendDB, BrouillonTrendDB
from core.auth import get_current_user, TokenData, require_permission
from core.multitenancy import require_module
from config.settings import settings
from modules.trends.gestionnaire_trends import MoteurTrends, Tendance

router = APIRouter(
    prefix="/trends",
    tags=["Veille & Tendances"],
    dependencies=[Depends(require_permission("trends"))],
)


# ─────────────────────────────────────────────────────────────
# Schémas
# ─────────────────────────────────────────────────────────────

class AnalyserSchema(BaseModel):
    region: str = "CM"
    periode: str = "24h"
    contexte_compagnie: str = ""
    nb_tendances: int = 5


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

async def _get_secteur_compagnie(compagnie_id: int, db: AsyncSession) -> str:
    r = await db.execute(select(CompagnieDB).where(CompagnieDB.id == compagnie_id))
    c = r.scalar_one_or_none()
    if c:
        return getattr(c, "secteur", "assurance") or "assurance"
    return "assurance"


def _moteur(secteur: str) -> MoteurTrends:
    return MoteurTrends(
        claude_api_key=settings.CLAUDE_API_KEY,
        openai_api_key=settings.OPENAI_API_KEY,
        secteur=secteur,
        serpapi_key=settings.SERPAPI_KEY,
        youtube_api_key=settings.YOUTUBE_API_KEY,
        newsapi_key=settings.NEWSAPI_KEY,
    )


def _tendance_to_dict(t: Tendance) -> dict:
    return {
        "sujet": t.sujet,
        "region": t.region,
        "score_social": t.score_social,
        "score_commerce": t.score_commerce,
        "score_opportunite": t.score_opportunite,
        "momentum_pct": t.momentum_pct,
        "categories": t.categories,
        "sources": t.sources,
        "resume": t.resume,
        "recommandations": t.recommandations,
    }


# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────

@router.get(
    "/pulse",
    dependencies=[Depends(require_module("trends"))],
)
async def get_pulse(
    region: str = "CM",
    periode: str = "24h",
    categorie: Optional[str] = None,
    score_min: float = 0.0,
    limit: int = Query(20, le=50),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Tendances actuelles filtrées par région et période."""
    secteur = await _get_secteur_compagnie(current_user.compagnie_id, db)
    moteur = _moteur(secteur)

    pulse = moteur.obtenir_tendances(
        region=region.upper(),
        periode=periode,
        categorie=categorie,
        score_min=score_min,
        limit=limit,
    )

    # Sauvegarder les snapshots en DB
    for t in pulse.tendances:
        snap = TrendSnapshotDB(
            compagnie_id=current_user.compagnie_id,
            region=t.region,
            periode=periode,
            sujet=t.sujet,
            score_social=t.score_social,
            score_commerce=t.score_commerce,
            score_opportunite=t.score_opportunite,
            momentum_pct=t.momentum_pct,
            categories=t.categories,
            sources=t.sources,
        )
        db.add(snap)
    await db.commit()

    return {
        "region": pulse.region,
        "periode": pulse.periode,
        "genere_le": pulse.genere_le,
        "resume_executif": pulse.resume_executif,
        "tendances_en_hausse": pulse.tendances_en_hausse,
        "top_categories": pulse.top_categories,
        "tendances": [_tendance_to_dict(t) for t in pulse.tendances],
    }


@router.get(
    "/pour-moi",
    dependencies=[Depends(require_module("trends"))],
)
async def tendances_pour_moi(
    region: str = "CM",
    periode: str = "24h",
    limit: int = Query(10, le=20),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Tendances personnalisées selon le secteur de la compagnie connectée."""
    secteur = await _get_secteur_compagnie(current_user.compagnie_id, db)
    moteur = _moteur(secteur)

    pulse = moteur.obtenir_tendances(region=region.upper(), periode=periode, limit=limit)
    top = pulse.tendances[:5]
    alertes = [t for t in top if moteur.evaluer_alerte(t)]

    return {
        "secteur": secteur,
        "region": pulse.region,
        "resume_executif": pulse.resume_executif,
        "tendances_prioritaires": [_tendance_to_dict(t) for t in top],
        "alertes_immediates": [t.sujet for t in alertes],
        "nb_opportunites_score_80plus": len([t for t in pulse.tendances if t.score_opportunite >= 80]),
    }


@router.post(
    "/analyser",
    dependencies=[Depends(require_module("trends"))],
)
async def analyser_tendances(
    payload: AnalyserSchema,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Analyse IA approfondie des tendances avec recommandations stratégiques."""
    secteur = await _get_secteur_compagnie(current_user.compagnie_id, db)
    moteur = _moteur(secteur)

    pulse = moteur.obtenir_tendances(
        region=payload.region.upper(),
        periode=payload.periode,
        limit=payload.nb_tendances,
    )

    analyse = await moteur.analyser_avec_ia(
        tendances=pulse.tendances,
        contexte_compagnie=payload.contexte_compagnie,
    )

    return {
        "analyse": analyse,
        "tendances_analysees": [_tendance_to_dict(t) for t in pulse.tendances],
        "secteur": secteur,
        "region": pulse.region,
    }


@router.get(
    "/veille-reglementaire",
    dependencies=[Depends(require_module("trends"))],
)
async def veille_reglementaire(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Actualités et rappels réglementaires pour le secteur de la compagnie."""
    secteur = await _get_secteur_compagnie(current_user.compagnie_id, db)
    moteur = _moteur(secteur)
    veille = moteur.veille_reglementaire(secteur)
    return {
        "secteur": secteur,
        "nb_elements": len(veille),
        "elements": veille,
    }


@router.get(
    "/historique",
    dependencies=[Depends(require_module("trends"))],
)
async def historique_tendances(
    region: Optional[str] = None,
    sujet: Optional[str] = None,
    limit: int = Query(50, le=200),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Historique des snapshots de tendances sauvegardés."""
    q = select(TrendSnapshotDB).where(
        TrendSnapshotDB.compagnie_id == current_user.compagnie_id
    )
    if region:
        q = q.where(TrendSnapshotDB.region == region.upper())
    if sujet:
        q = q.where(TrendSnapshotDB.sujet.ilike(f"%{sujet}%"))
    q = q.order_by(desc(TrendSnapshotDB.snapshot_le)).limit(limit)
    r = await db.execute(q)
    snaps = r.scalars().all()

    return [
        {
            "id": s.id,
            "region": s.region,
            "periode": s.periode,
            "sujet": s.sujet,
            "score_opportunite": s.score_opportunite,
            "momentum_pct": s.momentum_pct,
            "categories": s.categories,
            "snapshot_le": s.snapshot_le,
        }
        for s in snaps
    ]
