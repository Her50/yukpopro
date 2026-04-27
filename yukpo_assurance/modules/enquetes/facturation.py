"""
Facturation du module Enquêtes — tous les endpoints (LLM ou non) débitent des crédits.

Règles :
- Chaque appel est pré-vérifié (→ HTTP 402 si crédits épuisés).
- Les appels LLM sont facturés via `verifier_et_debiter` avec les tokens réels
  quand disponibles (ReponseIA.tokens_input / tokens_output), sinon via un
  forfait FCFA estimé. La marge Yukpo (×20) est appliquée par le service crédits.
- Les appels non-LLM sont facturés via `debiter_forfait_fcfa` (coût FCFA faible).
- Aucune opération n'est gratuite : le minimum de débit est 1 crédit par appel.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import HTTPException

from modules.pro.service_credits import (
    verifier_solde_suffisant,
    verifier_et_debiter,
    debiter_forfait_fcfa,
)

logger = logging.getLogger("yukpo_assurance.enquetes.facturation")


# Coûts FCFA bruts (avant marge Yukpo ×20 appliquée par service_credits).
# Les valeurs LLM correspondent à la consommation typique observée ;
# elles ne servent que de fallback si les tokens réels ne sont pas disponibles.
TARIFS_FCFA: dict[str, float] = {
    # Opérations gratuites de lecture (débit minimal = 1 crédit)
    "etude_get":              0.01,
    "etude_list":             0.01,
    "formulaire_get":         0.01,
    "formulaire_donnees":     0.01,
    "transcription_list":     0.01,
    "dictionnaire_get":       0.01,
    "plan_get":               0.01,
    "rapport_get":            0.01,

    # Opérations d'écriture non-LLM
    "etude_create":           0.05,
    "formulaire_create":      0.10,
    "formulaire_maj":         0.05,
    "dictionnaire_save":      0.05,
    "plan_save":              0.05,
    "soumission_reponse":     0.05,

    # Exports (fichiers générés localement)
    "xlsform_export":         0.50,
    "csv_export":             0.50,
    "questionnaire_docx":     0.75,
    "plan_docx":              0.75,

    # Appels LLM (fallback si tokens réels indisponibles)
    "audio_transcription":    15.0,   # Whisper : ~3 FCFA/min × 5 min moyen
    "analyse_qualitative":    50.0,
    "analyse_quantitative":   20.0,   # non-LLM mais calculs + graphiques
    "analyse_intelligente":   40.0,
    "analyse_commentaires":   30.0,
    "rapport":                80.0,
    "formulaire_ia":          40.0,
    "protocole_upload":       50.0,
    "dictionnaire_ia":        25.0,
    "plan_ia":                30.0,
}


async def precheck(user_id: int) -> None:
    """Lève HTTPException 402 si le solde est insuffisant."""
    try:
        ok, restants, plan, msg = await verifier_solde_suffisant(user_id)
    except Exception as e:
        logger.warning(f"[Facturation/precheck] erreur non bloquante user={user_id} : {e}")
        return
    if not ok:
        raise HTTPException(status_code=402, detail={
            "code":    "CREDITS_EPUISES",
            "message": f"Crédits Yukpo épuisés (plan={plan}). Rechargez pour continuer.",
            "action":  "Rechargez vos crédits ou changez de plan.",
            "url":     "/abonnement",
        })


async def debiter(user_id: int, operation: str, *, reponse_ia: Optional[Any] = None) -> None:
    """
    Débite le coût d'une opération du module Enquêtes.

    - Si `reponse_ia` est fourni et possède des tokens, débit réel via LLM pricing.
    - Sinon, débit forfait FCFA selon `TARIFS_FCFA[operation]`.
    La marge Yukpo ×20 est appliquée automatiquement par le service crédits.
    """
    # Débit LLM réel si tokens disponibles
    if reponse_ia is not None:
        ti = int(getattr(reponse_ia, "tokens_input", 0) or 0)
        to = int(getattr(reponse_ia, "tokens_output", 0) or 0)
        modele = str(getattr(reponse_ia, "modele_utilise", "default") or "default")
        if ti or to:
            try:
                await verifier_et_debiter(
                    user_id=user_id,
                    modele=modele,
                    tokens_input=ti,
                    tokens_output=to,
                    module=f"enquetes.{operation}",
                )
                return
            except Exception as e:
                logger.warning(f"[Facturation/LLM] fallback forfait {operation} user={user_id} : {e}")

    # Débit forfait FCFA (opérations non-LLM ou fallback LLM)
    cout = TARIFS_FCFA.get(operation, 0.10)
    try:
        await debiter_forfait_fcfa(
            user_id=user_id,
            cout_fcfa=cout,
            module=f"enquetes.{operation}",
        )
    except Exception as e:
        logger.warning(f"[Facturation/forfait] {operation} user={user_id} : {e}")
