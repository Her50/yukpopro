"""Routes copilote — assistant quotidien"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional
import base64

from modules.copilote.assistant_quotidien import AssistantQuotidien, SessionCopilote, assistant, get_or_create_session
from core.auth import TokenData, get_current_user, require_permission

router = APIRouter(dependencies=[Depends(require_permission("copilote"))])


class QuestionRequest(BaseModel):
    question: str
    user_id: int = 1
    role: str = "agent"
    contexte_actif: Optional[str] = None


class CourrierRequest(BaseModel):
    type_courrier: str
    donnees: dict
    role: str = "agent"


class FormationRequest(BaseModel):
    sujet: str
    niveau: str = "operationnel"


@router.post("/chat")
async def chat(
    req: QuestionRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Point d'entrée principal du copilote — conversation libre"""
    session = get_or_create_session(current_user.user_id, current_user.role)
    if req.contexte_actif:
        session.contexte_actif = req.contexte_actif
    return await assistant.repondre(question=req.question, session=session)


@router.post("/rediger-courrier")
async def rediger_courrier(req: CourrierRequest):
    """Rédaction assistée de courriers professionnels d'assurance"""
    courrier = await assistant.rediger_courrier(
        type_courrier=req.type_courrier,
        donnees=req.donnees,
        role=req.role,
    )
    return {"courrier": courrier, "type": req.type_courrier}


@router.post("/analyser-clause")
async def analyser_clause(body: dict):
    """Analyse d'une clause contractuelle"""
    clause = body.get("clause", "")
    if not clause:
        raise HTTPException(400, "Clause manquante")
    return await assistant.analyser_clause_contrat(clause)


@router.post("/former")
async def former(req: FormationRequest):
    """Module de formation intégré"""
    return await assistant.former_equipe(req.sujet, req.niveau)


@router.get("/veille-reglementaire")
async def veille():
    """Veille réglementaire CIMA"""
    return await assistant.veille_reglementaire()


@router.post("/calculer-indemnite")
async def calculer_indemnite(donnees: dict):
    """Calcul d'indemnité de sinistre assisté"""
    return await assistant.calculer_indemnite_sinistre(donnees)
