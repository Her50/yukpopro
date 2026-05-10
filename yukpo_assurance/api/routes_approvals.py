"""
Sprint 2.3 — Approval workflows pour Designer Pro.

Workflow standard : draft → submitted → approved | rejected → published

Cas d'usage B2B (banques/marketing) : un junior crée un visuel, un manager
doit valider avant publication client final.

Endpoints :
  GET    /approvals                              → liste org (filtrable par statut)
  POST   /approvals                              → crée un approval (draft) lié à un projet
  POST   /approvals/{id}/submit                  → draft → submitted (notif approvers)
  POST   /approvals/{id}/approve                 → submitted → approved (manager+)
  POST   /approvals/{id}/reject                  → submitted → rejected + note
  POST   /approvals/{id}/publish                 → approved → published
  POST   /approvals/{id}/archive                 → → archived (soft-delete)
  GET    /approvals/kanban                       → groupé par statut pour UI

Permissions :
- Créer/soumettre : tout user de l'org
- Approuver/rejeter/publier : rôle manager / dg / daf / admin (RBAC existant)
- Archiver : créateur OU manager+
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from core.auth import TokenData, get_current_user

logger = logging.getLogger("yukpo_assurance.api.approvals")
router = APIRouter()

# Rôles autorisés à approuver/rejeter/publier
_ROLES_APPROVERS = {"manager", "daf", "dg", "admin", "actuaire", "commercial"}


# ─── Modèles ──────────────────────────────────────────────────────────────────


class ApprovalCreate(BaseModel):
    titre: str = Field(..., min_length=2, max_length=300)
    cle_projet: str = Field(..., max_length=80)
    document_id: Optional[int] = Field(default=None,
        description="ID DocumentGenereDB lié (optionnel)")
    projet_json_id: Optional[str] = Field(default=None, max_length=120)
    note_submission: Optional[str] = Field(default=None, max_length=2000)
    meta: Optional[dict] = None


class ApprovalDecision(BaseModel):
    note: Optional[str] = Field(default=None, max_length=2000,
        description="Raison de l'approbation/rejet (optionnel pour approve, recommandé pour reject)")


class ApprovalResponse(BaseModel):
    approval_id: str
    compagnie_id: int
    titre: str
    cle_projet: str
    statut: str
    user_id_createur: int
    user_id_approver: Optional[int] = None
    document_id: Optional[int] = None
    projet_json_id: Optional[str] = None
    note_submission: Optional[str] = None
    note_decision: Optional[str] = None
    cree_le: str
    soumis_le: Optional[str] = None
    decide_le: Optional[str] = None
    publie_le: Optional[str] = None
    meta: Optional[dict] = None


def _row_to_response(row) -> ApprovalResponse:
    return ApprovalResponse(
        approval_id=row.approval_id, compagnie_id=row.compagnie_id,
        titre=row.titre, cle_projet=row.cle_projet, statut=row.statut,
        user_id_createur=row.user_id_createur, user_id_approver=row.user_id_approver,
        document_id=row.document_id, projet_json_id=row.projet_json_id,
        note_submission=row.note_submission, note_decision=row.note_decision,
        cree_le=row.cree_le.isoformat(),
        soumis_le=row.soumis_le.isoformat() if row.soumis_le else None,
        decide_le=row.decide_le.isoformat() if row.decide_le else None,
        publie_le=row.publie_le.isoformat() if row.publie_le else None,
        meta=row.meta,
    )


def _is_approver(user: TokenData) -> bool:
    return (user.role or "").lower() in _ROLES_APPROVERS


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=list[ApprovalResponse], tags=["Approval Workflows"])
async def lister_approvals(
    statut: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Liste les approvals de l'org (filtrable par statut)."""
    from core.database import async_session_maker, ProjetApprovalDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    async with async_session_maker() as db:
        q = select(ProjetApprovalDB).where(ProjetApprovalDB.compagnie_id == cid)
        if statut:
            q = q.where(ProjetApprovalDB.statut == statut)
        q = q.order_by(ProjetApprovalDB.cree_le.desc())
        rows = (await db.execute(q)).scalars().all()
    return [_row_to_response(r) for r in rows]


@router.get("/kanban", tags=["Approval Workflows"])
async def kanban_approvals(current_user: TokenData = Depends(get_current_user)):
    """Approvals groupés par statut pour vue Kanban."""
    from core.database import async_session_maker, ProjetApprovalDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    async with async_session_maker() as db:
        rows = (await db.execute(
            select(ProjetApprovalDB).where(ProjetApprovalDB.compagnie_id == cid)
            .order_by(ProjetApprovalDB.cree_le.desc())
        )).scalars().all()
    par_statut: dict = {"draft": [], "submitted": [], "approved": [],
                         "rejected": [], "published": [], "archived": []}
    for r in rows:
        bucket = r.statut if r.statut in par_statut else "archived"
        par_statut[bucket].append(_row_to_response(r).model_dump())
    return {"colonnes": par_statut, "total": len(rows)}


@router.post("", response_model=ApprovalResponse, tags=["Approval Workflows"])
async def creer_approval(
    demande: ApprovalCreate,
    current_user: TokenData = Depends(get_current_user),
):
    """Crée un approval en statut 'draft' (1ère étape du workflow)."""
    from core.database import async_session_maker, ProjetApprovalDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    aid = str(uuid.uuid4())
    async with async_session_maker() as db:
        row = ProjetApprovalDB(
            approval_id=aid, compagnie_id=cid,
            user_id_createur=current_user.user_id,
            titre=demande.titre, cle_projet=demande.cle_projet,
            document_id=demande.document_id, projet_json_id=demande.projet_json_id,
            statut="draft", note_submission=demande.note_submission,
            meta=demande.meta or {},
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
    logger.info(f"[Approval] Créé {aid} compagnie={cid} par user={current_user.user_id}")
    return _row_to_response(row)


@router.post("/{approval_id}/submit", response_model=ApprovalResponse, tags=["Approval Workflows"])
async def soumettre_approval(
    approval_id: str, demande: ApprovalDecision,
    current_user: TokenData = Depends(get_current_user),
):
    """draft → submitted. Le créateur soumet pour revue manager."""
    from core.database import async_session_maker, ProjetApprovalDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    async with async_session_maker() as db:
        row = (await db.execute(
            select(ProjetApprovalDB).where(
                ProjetApprovalDB.approval_id == approval_id,
                ProjetApprovalDB.compagnie_id == cid,
            )
        )).scalar_one_or_none()
        if not row:
            raise HTTPException(404, "Approval introuvable")
        if row.statut != "draft":
            raise HTTPException(400, f"Statut actuel '{row.statut}' — submit autorisé seulement depuis 'draft'")
        row.statut = "submitted"
        row.soumis_le = datetime.utcnow()
        if demande.note:
            row.note_submission = demande.note
        await db.commit()
        await db.refresh(row)
    logger.info(f"[Approval] {approval_id} submitted par user={current_user.user_id}")
    # TODO Sprint 2.3b : notif Slack/Teams/email aux approvers de l'org
    return _row_to_response(row)


@router.post("/{approval_id}/approve", response_model=ApprovalResponse, tags=["Approval Workflows"])
async def approuver_approval(
    approval_id: str, demande: ApprovalDecision,
    current_user: TokenData = Depends(get_current_user),
):
    """submitted → approved. Réservé aux rôles manager/daf/dg/admin."""
    if not _is_approver(current_user):
        raise HTTPException(403, f"Rôle '{current_user.role}' non autorisé. Requis : {sorted(_ROLES_APPROVERS)}")
    from core.database import async_session_maker, ProjetApprovalDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    async with async_session_maker() as db:
        row = (await db.execute(
            select(ProjetApprovalDB).where(
                ProjetApprovalDB.approval_id == approval_id,
                ProjetApprovalDB.compagnie_id == cid,
            )
        )).scalar_one_or_none()
        if not row:
            raise HTTPException(404, "Approval introuvable")
        if row.statut != "submitted":
            raise HTTPException(400, f"Statut '{row.statut}' — approve autorisé seulement depuis 'submitted'")
        row.statut = "approved"
        row.user_id_approver = current_user.user_id
        row.decide_le = datetime.utcnow()
        row.note_decision = demande.note
        await db.commit()
        await db.refresh(row)
    logger.info(f"[Approval] {approval_id} approved par user={current_user.user_id}")
    return _row_to_response(row)


@router.post("/{approval_id}/reject", response_model=ApprovalResponse, tags=["Approval Workflows"])
async def rejeter_approval(
    approval_id: str, demande: ApprovalDecision,
    current_user: TokenData = Depends(get_current_user),
):
    """submitted → rejected. Note recommandée pour expliquer."""
    if not _is_approver(current_user):
        raise HTTPException(403, f"Rôle '{current_user.role}' non autorisé.")
    from core.database import async_session_maker, ProjetApprovalDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    async with async_session_maker() as db:
        row = (await db.execute(
            select(ProjetApprovalDB).where(
                ProjetApprovalDB.approval_id == approval_id,
                ProjetApprovalDB.compagnie_id == cid,
            )
        )).scalar_one_or_none()
        if not row:
            raise HTTPException(404, "Approval introuvable")
        if row.statut != "submitted":
            raise HTTPException(400, f"Statut '{row.statut}' — reject autorisé seulement depuis 'submitted'")
        row.statut = "rejected"
        row.user_id_approver = current_user.user_id
        row.decide_le = datetime.utcnow()
        row.note_decision = demande.note or "(pas de raison fournie)"
        await db.commit()
        await db.refresh(row)
    logger.info(f"[Approval] {approval_id} rejected par user={current_user.user_id}")
    return _row_to_response(row)


@router.post("/{approval_id}/publish", response_model=ApprovalResponse, tags=["Approval Workflows"])
async def publier_approval(
    approval_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """approved → published. Marque le visuel comme officiellement publié."""
    if not _is_approver(current_user):
        raise HTTPException(403, f"Rôle '{current_user.role}' non autorisé.")
    from core.database import async_session_maker, ProjetApprovalDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    async with async_session_maker() as db:
        row = (await db.execute(
            select(ProjetApprovalDB).where(
                ProjetApprovalDB.approval_id == approval_id,
                ProjetApprovalDB.compagnie_id == cid,
            )
        )).scalar_one_or_none()
        if not row:
            raise HTTPException(404, "Approval introuvable")
        if row.statut != "approved":
            raise HTTPException(400, f"Statut '{row.statut}' — publish autorisé seulement depuis 'approved'")
        row.statut = "published"
        row.publie_le = datetime.utcnow()
        await db.commit()
        await db.refresh(row)
    logger.info(f"[Approval] {approval_id} published par user={current_user.user_id}")
    return _row_to_response(row)


@router.post("/{approval_id}/archive", tags=["Approval Workflows"])
async def archiver_approval(
    approval_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Archive (soft-delete). Permis au créateur OU à un approver."""
    from core.database import async_session_maker, ProjetApprovalDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    async with async_session_maker() as db:
        row = (await db.execute(
            select(ProjetApprovalDB).where(
                ProjetApprovalDB.approval_id == approval_id,
                ProjetApprovalDB.compagnie_id == cid,
            )
        )).scalar_one_or_none()
        if not row:
            raise HTTPException(404, "Approval introuvable")
        if row.user_id_createur != current_user.user_id and not _is_approver(current_user):
            raise HTTPException(403, "Seul le créateur ou un approver peut archiver")
        row.statut = "archived"
        await db.commit()
    logger.info(f"[Approval] {approval_id} archived par user={current_user.user_id}")
    return {"ok": True, "approval_id": approval_id, "statut": "archived"}
