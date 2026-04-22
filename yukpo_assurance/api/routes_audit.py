"""Routes Audit Trail — consultation de l'historique des actions"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from core.audit import audit_service
from core.auth import TokenData, get_current_user, require_permission

# Audit accessible seulement aux rôles dg et admin
router = APIRouter(dependencies=[Depends(require_permission("audit"))])


@router.get("/utilisateur/{user_id}")
async def historique_utilisateur(
    user_id: int,
    skip: int = Query(0, ge=0),
    limite: int = Query(100, le=500),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Toutes les actions d'un utilisateur (paginée).
    Permet de savoir ce que Dupont a fait aujourd'hui.
    """
    # Un utilisateur peut voir son propre historique; DG/admin voient tous
    if current_user.user_id != user_id and current_user.role not in ("dg", "admin"):
        raise HTTPException(403, "Accès limité à votre propre historique")
    logs = await audit_service.historique_utilisateur(user_id=user_id, limite=limite)
    page = logs[skip:skip + limite]
    return {"user_id": user_id, "total": len(logs), "skip": skip, "nb_actions": len(page), "actions": page}


@router.get("/dossier/{reference}")
async def historique_dossier(
    reference: str,
    skip: int = Query(0, ge=0),
    limite: int = Query(50, le=200),
):
    """
    Toutes les actions sur un dossier (sinistre, session, réunion...).
    Exemple : /audit/dossier/SIN-2025-001234
    """
    logs = await audit_service.historique_dossier(resource_id=reference, limite=limite)
    page = logs[skip:skip + limite]
    return {"reference": reference, "total": len(logs), "skip": skip, "nb_actions": len(page), "historique": page}


@router.get("/module/{module}")
async def historique_module(
    module: str,
    skip: int = Query(0, ge=0),
    limite: int = Query(200, le=1000),
):
    """
    Toutes les actions sur un module (paginée).
    Modules : chat | sinistres | documents | reunions | cima | comptabilite | analytics
    """
    logs = await audit_service.historique_module(module=module, limite=limite)
    page = logs[skip:skip + limite]
    return {"module": module, "total": len(logs), "skip": skip, "nb_actions": len(page), "actions": page}


@router.get("/recent")
async def actions_recentes(
    skip: int = Query(0, ge=0),
    limite: int = Query(50, le=200),
    current_user: TokenData = Depends(get_current_user),
):
    """Les N dernières actions toutes sources confondues (paginée)"""
    from core.database import async_session_maker, AuditLogDB
    from sqlalchemy import select, desc

    async with async_session_maker() as db:
        result = await db.execute(
            select(AuditLogDB)
            .order_by(desc(AuditLogDB.timestamp))
            .offset(skip)
            .limit(limite)
        )
        logs = result.scalars().all()
        return {
            "skip": skip,
            "nb": len(logs),
            "actions": [
                {
                    "id": l.id,
                    "timestamp": l.timestamp.isoformat(),
                    "user_nom": l.user_nom or "Système",
                    "action": l.action,
                    "module": l.module,
                    "resource_id": l.resource_id,
                    "succes": l.succes,
                    "duree_ms": l.duree_ms,
                }
                for l in logs
            ],
        }


@router.get("/couts-ia")
async def couts_ia(
    skip: int = Query(0, ge=0),
    limite: int = Query(100, le=1000),
    modele: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Suivi des coûts d'utilisation des APIs IA (tokens + coût USD estimé)"""
    from core.database import async_session_maker, CoutIADB
    from sqlalchemy import select, desc, func

    async with async_session_maker() as db:
        q = select(CoutIADB).order_by(desc(CoutIADB.timestamp))
        if modele:
            q = q.where(CoutIADB.modele == modele)
        result = await db.execute(q.offset(skip).limit(limite))
        rows = result.scalars().all()

        # Total
        total_res = await db.execute(
            select(func.sum(CoutIADB.cout_estime_usd), func.sum(CoutIADB.tokens_input + CoutIADB.tokens_output))
        )
        total_cout, total_tokens = total_res.one()

        return {
            "total_cout_usd": round(total_cout or 0, 4),
            "total_tokens": total_tokens or 0,
            "skip": skip,
            "nb": len(rows),
            "details": [
                {
                    "timestamp": r.timestamp.isoformat(),
                    "modele": r.modele,
                    "module": r.module,
                    "tokens_input": r.tokens_input,
                    "tokens_output": r.tokens_output,
                    "cout_usd": r.cout_estime_usd,
                }
                for r in rows
            ],
        }
