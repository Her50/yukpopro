"""
Bureau Session — endpoints pour le chat unifié (YPro + YSec).

GET  /api/v1/bureau/session/courante     → renvoie le dernier fichier/pipeline
                                            mémorisé pour l'user.
POST /api/v1/bureau/session/intent       → classe un message user en
                                            {modification, nouvelle_demande, ambigu}
                                            avec proposition de route /modifier
                                            si modification.
POST /api/v1/bureau/session/reset        → expire la session active (clic
                                            "Nouvelle conversation").

Ces endpoints permettent au frontend de décider AVANT chaque envoi : faut-il
appeler /generer (nouvelle demande) ou /modifier (suite logique sur dernier
fichier) ?
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.auth import TokenData, get_current_user
from modules.bureau import bureau_session as _bs

logger = logging.getLogger("yukpo_assurance.api.bureau_session")
router = APIRouter()


# ─── GET session courante ─────────────────────────────────────────────────────

@router.get("/session/courante", tags=["Bureau — Session"])
async def get_session_courante(
    current_user: TokenData = Depends(get_current_user),
):
    """
    Retourne la session active (dans le TTL 30 min) ou None si aucune.
    Le frontend l'appelle au chargement du chat pour savoir s'il peut
    afficher "Continuer la modification de [titre du dernier doc]".
    """
    sess = await _bs.get_or_create_session(current_user.user_id)
    return {
        "session_id": sess.session_id,
        "pipeline": sess.pipeline,
        "dernier_fichier_id": sess.dernier_fichier_id,
        "dernier_brief": sess.dernier_brief,
        "a_dernier_fichier": bool(sess.dernier_fichier_id),
        "derniere_interaction": sess.derniere_interaction.isoformat() if sess.derniere_interaction else None,
    }


# ─── POST détection intent (avant envoi message) ─────────────────────────────

class DemandeIntent(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000,
        description="Nouveau message utilisateur à classifier")


# Mapping pipeline → endpoint /modifier suggéré au frontend
_MODIFIER_ENDPOINTS = {
    "infographe":     "/api/v1/bureau/infographie/modifier",
    "freeform":       "/api/v1/bureau/freeform/modifier",
    "designer_pro":   "/api/v1/bureau/infographie-pro/modifier",
    "rapport":        "/api/v1/pro/rapports/modifier",
    "slides":         "/api/v1/pro/slides/modifier",
    "geometric":      "/api/v1/bureau/infographie-pro/geometric-placement/modifier",
}


@router.post("/session/intent", tags=["Bureau — Session"])
async def detecter_intent(
    demande: DemandeIntent,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Classifie le nouveau message user → {modification, nouvelle_demande, ambigu}.
    Si modification : retourne l'endpoint /modifier à appeler + le dernier
    fichier_id. Le frontend route en conséquence.

    Coût : 1 appel Sonnet ~200-400 tokens (skip si pas de session active).
    Débité via debiter_llm.
    """
    from modules.bureau.service_credits_bureau import debiter_llm

    sess = await _bs.get_or_create_session(current_user.user_id)
    intent, confiance, usage = await _bs.detecter_intent_modification(
        user_message=demande.message,
        dernier_brief=sess.dernier_brief,
        dernier_fichier_id=sess.dernier_fichier_id,
        dernier_pipeline=sess.pipeline,
    )

    if usage.get("tokens_in") or usage.get("tokens_out"):
        try:
            await debiter_llm(
                current_user.user_id,
                modele=usage.get("modele", "claude"),
                tokens_input=int(usage.get("tokens_in", 0)),
                tokens_output=int(usage.get("tokens_out", 0)),
                module="infographie",
            )
        except Exception as e:
            logger.warning(f"[BureauSession/Intent] débit LLM skip : {e}")

    response = {
        "intent": intent,
        "confiance": confiance,
        "session_id": sess.session_id,
        "pipeline": sess.pipeline,
        "dernier_fichier_id": sess.dernier_fichier_id,
    }
    if intent == "modification" and sess.pipeline in _MODIFIER_ENDPOINTS:
        response["route_modifier"] = _MODIFIER_ENDPOINTS[sess.pipeline]
        response["recommandation"] = (
            f"Appeler {_MODIFIER_ENDPOINTS[sess.pipeline]} avec "
            f"fichier_id={sess.dernier_fichier_id} + instructions={demande.message}"
        )
    elif intent == "modification" and sess.pipeline:
        response["route_modifier"] = None
        response["recommandation"] = (
            f"Pipeline '{sess.pipeline}' ne supporte pas encore /modifier — "
            f"fallback /generer avec contexte du dernier brief."
        )
    return response


# ─── POST reset session ──────────────────────────────────────────────────────

@router.post("/session/reset", tags=["Bureau — Session"])
async def reset_session_endpoint(
    current_user: TokenData = Depends(get_current_user),
):
    """Expire la session active. Le prochain message commence une nouvelle session."""
    await _bs.reset_session(current_user.user_id)
    return {"ok": True, "message": "Session expirée — prochain message = nouvelle conversation"}
