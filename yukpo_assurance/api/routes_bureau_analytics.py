"""
Phase 5 — Analytics & Insights pour bureau (Yukpo Designer Pro + Secrétariat).

Endpoints (JWT, role admin/dg/daf/manager) :
  GET /bureau-analytics/usage        → volume usage par module, période, user
  GET /bureau-analytics/cost         → coûts cumulés FCFA/credits par compagnie
  GET /bureau-analytics/templates    → top templates Designer Pro générés
  GET /bureau-analytics/users        → top users (volume + coût)
  GET /bureau-analytics/quality      → taux succès / latency par endpoint (SLA)
  GET /bureau-analytics/dashboard    → résumé exécutif unique (home admin)

Filtres : ?days=30 (défaut 30j), ?module=infographie

Distinct du module routes_analytics.py existant qui couvre l'assurance CIMA.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func

from core.auth import TokenData, get_current_user

logger = logging.getLogger("yukpo_assurance.api.bureau_analytics")
router = APIRouter()

_ROLES_ANALYTICS = {"admin", "dg", "daf", "manager", "yukpo_owner", "super_admin"}


def _check_acces(user: TokenData):
    if (user.role or "").lower() not in _ROLES_ANALYTICS:
        raise HTTPException(403, f"Rôle '{user.role}' non autorisé. Requis : admin/dg/daf/manager")


def _periode_cutoff(days: int) -> datetime:
    return datetime.utcnow() - timedelta(days=max(1, min(365, days)))


async def _user_ids_compagnie(compagnie_id: int) -> list[int]:
    """Récupère tous les user_id d'une compagnie pour scope multi-tenant."""
    from core.database import async_session_maker, UtilisateurDB
    async with async_session_maker() as db:
        rows = (await db.execute(
            select(UtilisateurDB.user_id).where(UtilisateurDB.compagnie_id == compagnie_id)
        )).scalars().all()
    return list(rows) or []


# ─── /usage ──────────────────────────────────────────────────────────────────


@router.get("/usage", tags=["Bureau — Analytics & Insights"])
async def usage_endpoint(
    days: int = Query(30, ge=1, le=365),
    module: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Volume d'usage agrégé par module + par jour (last N days)."""
    _check_acces(current_user)
    from core.database import async_session_maker, ConsommationBureauDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    user_ids = await _user_ids_compagnie(cid)
    if not user_ids:
        return {"days": days, "total_appels": 0, "par_module": [], "par_jour": []}
    cutoff = _periode_cutoff(days)
    async with async_session_maker() as db:
        q_module = select(
            ConsommationBureauDB.module, func.count().label("nb"),
            func.sum(ConsommationBureauDB.tokens_input).label("tok_in"),
            func.sum(ConsommationBureauDB.tokens_output).label("tok_out"),
        ).where(
            ConsommationBureauDB.user_id.in_(user_ids),
            ConsommationBureauDB.cree_le >= cutoff,
        )
        if module:
            q_module = q_module.where(ConsommationBureauDB.module == module)
        q_module = q_module.group_by(ConsommationBureauDB.module).order_by(func.count().desc())
        rows_mod = (await db.execute(q_module)).all()
        q_jour = select(
            func.date_trunc('day', ConsommationBureauDB.cree_le).label("jour"),
            func.count().label("nb"),
        ).where(
            ConsommationBureauDB.user_id.in_(user_ids),
            ConsommationBureauDB.cree_le >= cutoff,
        )
        if module:
            q_jour = q_jour.where(ConsommationBureauDB.module == module)
        q_jour = q_jour.group_by("jour").order_by("jour")
        rows_jour = (await db.execute(q_jour)).all()
    return {
        "days": days,
        "total_appels": sum(r.nb for r in rows_mod),
        "par_module": [
            {"module": r.module or "inconnu", "nb_appels": r.nb,
             "tokens_in": int(r.tok_in or 0), "tokens_out": int(r.tok_out or 0)}
            for r in rows_mod
        ],
        "par_jour": [
            {"jour": r.jour.date().isoformat() if r.jour else None, "nb_appels": r.nb}
            for r in rows_jour
        ],
    }


# ─── /cost ──────────────────────────────────────────────────────────────────


@router.get("/cost", tags=["Bureau — Analytics & Insights"])
async def cost_endpoint(
    days: int = Query(30, ge=1, le=365),
    current_user: TokenData = Depends(get_current_user),
):
    """Coûts cumulés FCFA + crédits par module + par jour."""
    _check_acces(current_user)
    from core.database import async_session_maker, ConsommationBureauDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    user_ids = await _user_ids_compagnie(cid)
    if not user_ids:
        return {"days": days, "total_fcfa": 0, "total_credits": 0,
                "par_module": [], "par_jour": []}
    cutoff = _periode_cutoff(days)
    async with async_session_maker() as db:
        rows_mod = (await db.execute(
            select(
                ConsommationBureauDB.module,
                func.sum(ConsommationBureauDB.cout_fcfa).label("fcfa"),
                func.sum(ConsommationBureauDB.credits_debites).label("credits"),
                func.count().label("nb"),
            ).where(
                ConsommationBureauDB.user_id.in_(user_ids),
                ConsommationBureauDB.cree_le >= cutoff,
            ).group_by(ConsommationBureauDB.module).order_by(
                func.sum(ConsommationBureauDB.credits_debites).desc()
            )
        )).all()
        rows_jour = (await db.execute(
            select(
                func.date_trunc('day', ConsommationBureauDB.cree_le).label("jour"),
                func.sum(ConsommationBureauDB.cout_fcfa).label("fcfa"),
                func.sum(ConsommationBureauDB.credits_debites).label("credits"),
            ).where(
                ConsommationBureauDB.user_id.in_(user_ids),
                ConsommationBureauDB.cree_le >= cutoff,
            ).group_by("jour").order_by("jour")
        )).all()
    total_fcfa = sum(r.fcfa or 0 for r in rows_mod)
    total_credits = sum(r.credits or 0 for r in rows_mod)
    nb_total = sum(r.nb for r in rows_mod) or 1
    return {
        "days": days,
        "total_fcfa": round(total_fcfa, 0),
        "total_credits": round(total_credits, 1),
        "moyenne_fcfa_par_appel": round(total_fcfa / nb_total, 1),
        "par_module": [
            {"module": r.module or "inconnu",
             "fcfa": round(r.fcfa or 0, 0), "credits": round(r.credits or 0, 1),
             "nb_appels": r.nb}
            for r in rows_mod
        ],
        "par_jour": [
            {"jour": r.jour.date().isoformat() if r.jour else None,
             "fcfa": round(r.fcfa or 0, 0), "credits": round(r.credits or 0, 1)}
            for r in rows_jour
        ],
    }


# ─── /templates ──────────────────────────────────────────────────────────────


@router.get("/templates", tags=["Bureau — Analytics & Insights"])
async def top_templates(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=5, le=100),
    current_user: TokenData = Depends(get_current_user),
):
    """Top N templates Designer Pro / types_doc générés (last N days)."""
    _check_acces(current_user)
    from core.database import async_session_maker, DocumentGenereDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    cutoff = _periode_cutoff(days)
    async with async_session_maker() as db:
        rows = (await db.execute(
            select(
                DocumentGenereDB.type_doc, func.count().label("nb"),
                func.sum(DocumentGenereDB.cout_fcfa).label("fcfa"),
            ).where(
                DocumentGenereDB.compagnie_id == cid,
                DocumentGenereDB.cree_le >= cutoff,
            ).group_by(DocumentGenereDB.type_doc).order_by(func.count().desc()).limit(limit)
        )).all()
    return {
        "days": days, "total_documents": sum(r.nb for r in rows),
        "top": [
            {"type_doc": r.type_doc or "inconnu", "nb_generes": r.nb,
             "cout_fcfa_total": round(r.fcfa or 0, 0)}
            for r in rows
        ],
    }


# ─── /users ──────────────────────────────────────────────────────────────────


@router.get("/users", tags=["Bureau — Analytics & Insights"])
async def top_users(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=5, le=100),
    current_user: TokenData = Depends(get_current_user),
):
    """Top N utilisateurs (volume + coût) de l'organisation."""
    _check_acces(current_user)
    from core.database import async_session_maker, ConsommationBureauDB, UtilisateurDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    user_ids = await _user_ids_compagnie(cid)
    if not user_ids:
        return {"days": days, "top": []}
    cutoff = _periode_cutoff(days)
    async with async_session_maker() as db:
        rows = (await db.execute(
            select(
                ConsommationBureauDB.user_id, func.count().label("nb"),
                func.sum(ConsommationBureauDB.credits_debites).label("credits"),
                func.sum(ConsommationBureauDB.cout_fcfa).label("fcfa"),
            ).where(
                ConsommationBureauDB.user_id.in_(user_ids),
                ConsommationBureauDB.cree_le >= cutoff,
            ).group_by(ConsommationBureauDB.user_id).order_by(
                func.sum(ConsommationBureauDB.credits_debites).desc()
            ).limit(limit)
        )).all()
        if not rows:
            return {"days": days, "top": []}
        users = (await db.execute(
            select(UtilisateurDB.user_id, UtilisateurDB.nom).where(
                UtilisateurDB.user_id.in_([r.user_id for r in rows])
            )
        )).all()
        nom_par_id = {u.user_id: u.nom for u in users}
    return {
        "days": days,
        "top": [
            {"user_id": r.user_id, "nom": nom_par_id.get(r.user_id, "?"),
             "nb_appels": r.nb, "credits_total": round(r.credits or 0, 1),
             "fcfa_total": round(r.fcfa or 0, 0)}
            for r in rows
        ],
    }


# ─── /quality ────────────────────────────────────────────────────────────────


@router.get("/quality", tags=["Bureau — Analytics & Insights"])
async def quality_metrics(
    last_minutes: int = Query(60, ge=5, le=1440),
    current_user: TokenData = Depends(get_current_user),
):
    """Taux succès / latency par endpoint depuis l'infrastructure SLA Sprint 2.6."""
    _check_acces(current_user)
    try:
        from core import sla_metrics as _sm
        endpoints = [_sm.stats_endpoint(ep, last_minutes) for ep in _sm._LATENCY_BUFFER]
        endpoints.sort(key=lambda x: x.get("samples", 0), reverse=True)
        return {"window_minutes": last_minutes, "endpoints": endpoints}
    except Exception as e:
        return {"erreur": str(e)[:200], "endpoints": []}


# ─── /dashboard (résumé exécutif) ────────────────────────────────────────────


@router.get("/dashboard", tags=["Bureau — Analytics & Insights"])
async def dashboard_resume(
    days: int = Query(30, ge=1, le=365),
    current_user: TokenData = Depends(get_current_user),
):
    """Résumé exécutif KPI — 1 endpoint pour la home page admin org."""
    _check_acces(current_user)
    from core.database import async_session_maker, ConsommationBureauDB, DocumentGenereDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    user_ids = await _user_ids_compagnie(cid)
    cutoff = _periode_cutoff(days)
    if not user_ids:
        return {"compagnie_id": cid, "days": days, "vide": True}
    async with async_session_maker() as db:
        totaux = (await db.execute(
            select(
                func.count().label("nb_appels"),
                func.sum(ConsommationBureauDB.credits_debites).label("credits"),
                func.sum(ConsommationBureauDB.cout_fcfa).label("fcfa"),
                func.count(func.distinct(ConsommationBureauDB.user_id)).label("nb_users_actifs"),
            ).where(
                ConsommationBureauDB.user_id.in_(user_ids),
                ConsommationBureauDB.cree_le >= cutoff,
            )
        )).first()
        nb_docs = (await db.execute(
            select(func.count()).select_from(DocumentGenereDB).where(
                DocumentGenereDB.compagnie_id == cid,
                DocumentGenereDB.cree_le >= cutoff,
            )
        )).scalar() or 0
        top_modules = (await db.execute(
            select(
                ConsommationBureauDB.module, func.count().label("nb"),
                func.sum(ConsommationBureauDB.credits_debites).label("credits"),
            ).where(
                ConsommationBureauDB.user_id.in_(user_ids),
                ConsommationBureauDB.cree_le >= cutoff,
            ).group_by(ConsommationBureauDB.module).order_by(func.count().desc()).limit(3)
        )).all()
    nb_jours = max(1, days)
    return {
        "compagnie_id": cid, "days": days,
        "kpis": {
            "nb_appels_llm": totaux.nb_appels or 0,
            "nb_documents_generes": int(nb_docs),
            "credits_consommes": round(totaux.credits or 0, 1),
            "fcfa_consommes": round(totaux.fcfa or 0, 0),
            "nb_users_actifs": totaux.nb_users_actifs or 0,
            "moyenne_credits_par_jour": round((totaux.credits or 0) / nb_jours, 1),
            "moyenne_docs_par_jour": round(nb_docs / nb_jours, 1),
        },
        "top_modules": [
            {"module": r.module or "inconnu", "nb_appels": r.nb,
             "credits": round(r.credits or 0, 1)}
            for r in top_modules
        ],
    }
