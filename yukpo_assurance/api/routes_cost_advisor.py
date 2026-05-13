"""Routes Cost Advisor — preview de coût + endpoint user-facing.

Endpoints :

  POST /api/v1/cost/preview         (auth)
       Body  : {operation, multiplicateur?, cout_credits_force?}
       Returns: AdvisorVerdict (action go/confirm/block + détail)

       Le frontend appelle ce endpoint AVANT de lancer une opération
       coûteuse pour décider d'afficher ou non la modale de confirmation.

  GET  /api/v1/cost/seuils          (auth)
       Returns: tous les seuils % par plan (debug + page abonnement).

Pattern d'usage dans les endpoints coûteux :

    from core.cost_advisor import advisor, AdvisorAction
    from core.cost_advisor import estimer_cout_module

    cout = estimer_cout_module("rapport_docx_long")
    v = await advisor.evaluer(user_id, cout, module="rapports")
    if v.action == AdvisorAction.BLOCK:
        raise HTTPException(402, v.detail_pour_402())
    if v.action == AdvisorAction.CONFIRM and not req.confirmer_cout:
        raise HTTPException(402, v.detail_pour_402())
    # ... exécution ...
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.auth import TokenData, get_current_user
from core.cost_advisor import advisor, estimer_cout_module, AdvisorAction

logger = logging.getLogger("yukpo_assurance.api.cost_advisor")

router = APIRouter()


class PreviewRequest(BaseModel):
    operation: str = Field(
        ..., max_length=80,
        description="Type d'opération (clé du dict d'estimations). "
                    "Ex : 'rapport_docx_long', 'video_5s_premium', "
                    "'landing_page', 'enquete_generer'.",
    )
    multiplicateur: float = Field(1.0, ge=0.0, le=10000.0)
    cout_credits_force: Optional[float] = Field(
        None, ge=0.0,
        description="Si fourni, court-circuite l'estimation auto et utilise "
                    "ce coût (le frontend a calculé un coût précis).",
    )


@router.post("/cost/preview", summary="Preview coût d'une opération + verdict advisor")
async def preview_cost(
    body: PreviewRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Retourne le verdict CostAdvisor pour une opération envisagée.

    Le frontend doit appeler ce endpoint AVANT toute opération non triviale.
    Selon verdict.action :
      • 'go'      → exécuter direct
      • 'confirm' → afficher modale + champ `confirmer_cout=true` sur l'appel suivant
      • 'block'   → rediriger vers /abonnement (solde insuffisant)
    """
    if body.cout_credits_force is not None:
        cout = float(body.cout_credits_force)
    else:
        cout = estimer_cout_module(body.operation, body.multiplicateur)

    verdict = await advisor.evaluer(
        user_id=current_user.user_id,
        cout_credits_estime=cout,
        module=body.operation,
    )
    return {"action": verdict.action.value, **verdict.detail_pour_402()}


@router.get("/cost/seuils", summary="Seuils % de confirmation par plan")
async def get_seuils(_user: TokenData = Depends(get_current_user)):
    """Expose les seuils plan → % du solde au-delà duquel on demande
    confirmation. Utile pour afficher dans la page /abonnement
    (transparence sur le système de protection)."""
    return {
        "seuils_pct": advisor._seuils,  # noqa: SLF001 — lecture intentionnelle
        "plancher_credits_confirm": 50,
        "explication": (
            "Si une opération va consommer plus de `seuils_pct[plan]` × "
            "votre solde restant ET au moins 50 crédits, une modale de "
            "confirmation s'affiche avant exécution. Vous pouvez recharger "
            "ponctuellement à ce moment."
        ),
    }
