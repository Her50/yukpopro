"""Cost Advisor — Système d'alerte préventif crédits (transverse, multi-module).

Objectif : avant d'exécuter une opération coûteuse (LLM Sonnet/Opus long,
génération vidéo, batch import, analyse de gros dataset, etc.), estimer
le coût en crédits et :

  • Si l'opération va consommer ≥ X % du solde restant → demander
    confirmation explicite à l'utilisateur (modale frontend).
  • Si le solde est insuffisant → bloquer + proposer recharge.
  • Sinon → exécution silencieuse.

Le seuil X dépend du PLAN d'abonnement de l'utilisateur :

  Plan          | % solde restant déclenchant confirmation
  --------------|-----------------------------------------
  gratuit       | 20 %   (très protecteur — solde faible par défaut)
  secretariat   | 25 %
  infographie   | 25 %
  complet       | 35 %   (plus permissif — quota gros)
  pro_starter   | 25 %
  pro_business  | 40 %
  pro_enterprise| 60 %   (utilisateurs avertis, gros volume)

Override env : `COST_ADVISOR_THRESHOLDS_JSON` permet de surcharger.

Usage standard :

    from core.cost_advisor import advisor, AdvisorAction

    verdict = await advisor.evaluer(
        user_id=current_user.user_id,
        cout_credits_estime=750.0,
        module="freeform_pdf",
    )

    if verdict.action == AdvisorAction.BLOCK:
        raise HTTPException(402, verdict.detail_pour_402())

    if verdict.action == AdvisorAction.CONFIRM and not body.confirmer_cout:
        raise HTTPException(402, verdict.detail_pour_402())

    # action == GO ou confirmer_cout=True → on procède
    # ... exécution ...

Le frontend intercepte le 402 type='cost_confirm_required' et affiche
une modale "Cette opération coûtera ~X crédits (Y FCFA), il vous reste
Z crédits. Continuer ?" + bouton Recharger.
"""
from __future__ import annotations

import enum
import json
import logging
import os
from dataclasses import dataclass, asdict
from typing import Any, Optional

logger = logging.getLogger("yukpo_assurance.cost_advisor")


# ── Seuils par plan (% du solde restant) ──────────────────────────────────────
# Si cout_estime >= seuil_pct × solde_restant → confirmation requise.
_DEFAULT_SEUILS_PCT: dict[str, float] = {
    "gratuit":         0.20,
    "secretariat":     0.25,
    "infographie":     0.25,
    "complet":         0.35,
    "pro_starter":     0.25,
    "pro_business":    0.40,
    "pro_enterprise":  0.60,
    # Fallback si plan inconnu
    "default":         0.25,
}

# Plancher absolu : pour ne pas spammer de modales sur les micro-opérations.
# Sous ce seuil en crédits, on n'embête JAMAIS l'utilisateur même si
# le ratio % est dépassé.
_PLANCHER_CREDITS_CONFIRM = float(os.getenv("COST_ADVISOR_PLANCHER", "50"))


def _seuils_charges() -> dict[str, float]:
    """Charge les seuils avec override env optionnel."""
    override = os.getenv("COST_ADVISOR_THRESHOLDS_JSON", "").strip()
    if not override:
        return dict(_DEFAULT_SEUILS_PCT)
    try:
        custom = json.loads(override)
        merged = dict(_DEFAULT_SEUILS_PCT)
        merged.update({k: float(v) for k, v in custom.items()})
        return merged
    except Exception as e:
        logger.warning(f"[CostAdvisor] override JSON invalide ({e}) → défauts")
        return dict(_DEFAULT_SEUILS_PCT)


class AdvisorAction(str, enum.Enum):
    GO = "go"             # Exécuter silencieusement
    CONFIRM = "confirm"   # Demander confirmation explicite user
    BLOCK = "block"       # Solde insuffisant — refuser + proposer recharge


@dataclass
class AdvisorVerdict:
    action: AdvisorAction
    plan: str
    cout_credits_estime: float
    cout_fcfa_estime: float
    solde_credits_avant: float
    solde_credits_apres_estime: float
    quota_total: float
    pct_solde_consomme: float        # % du solde restant que ça va prendre
    seuil_pct_plan: float
    message_user: str
    module: str = ""

    def detail_pour_402(self) -> dict:
        """Body JSON renvoyé par HTTPException(402, ...) côté FastAPI."""
        return {
            "type": (
                "cost_confirm_required" if self.action == AdvisorAction.CONFIRM
                else "credits_insuffisants"
            ),
            **{k: v for k, v in asdict(self).items() if k != "action"},
        }


class CostAdvisor:
    """Singleton — instancié dans `advisor` plus bas."""

    def __init__(self):
        self._seuils = _seuils_charges()

    def seuil_pour_plan(self, plan: str) -> float:
        return self._seuils.get(plan, self._seuils["default"])

    async def _solde(self, user_id: int) -> tuple[float, float, str]:
        """Retourne (solde_restant_credits, quota_total, plan_actif)."""
        from modules.pro.service_credits import get_ou_creer_credits as _get_pro
        from modules.bureau.service_credits_bureau import (
            get_ou_creer_credits_bureau as _get_bureau,
        )
        from core.database import async_session_maker

        # Priorité au plan Pro actif (sinon Bureau pay-as-you-go)
        try:
            async with async_session_maker() as db:
                pro = await _get_pro(user_id, db)
                if pro and pro.plan and pro.plan != "gratuit":
                    restants = max(0.0, pro.credits_alloues - pro.credits_utilises)
                    return restants, float(pro.credits_alloues), pro.plan
        except Exception as e:
            logger.debug(f"[CostAdvisor] pro lookup user={user_id} : {e}")

        try:
            async with async_session_maker() as db:
                bur = await _get_bureau(user_id, db)
                restants = max(0.0, bur.credits_alloues - bur.credits_utilises)
                return restants, float(bur.credits_alloues), bur.plan or "gratuit"
        except Exception as e:
            logger.warning(f"[CostAdvisor] bureau lookup user={user_id} : {e}")
            return 0.0, 0.0, "gratuit"

    async def evaluer(
        self,
        user_id: int,
        cout_credits_estime: float,
        module: str = "",
    ) -> AdvisorVerdict:
        """Verdict pour une opération qui va coûter ~`cout_credits_estime` crédits."""
        solde, quota, plan = await self._solde(user_id)
        seuil_pct = self.seuil_pour_plan(plan)
        cout = max(0.0, float(cout_credits_estime))
        cout_fcfa = round(cout * 0.6, 1)  # convention : 1 crédit ≈ 0.6 FCFA user
        solde_apres = solde - cout
        pct_consomme = (cout / solde) if solde > 0 else float("inf")

        # 1. BLOCK : solde insuffisant
        if solde <= 0 or solde_apres < 0:
            return AdvisorVerdict(
                action=AdvisorAction.BLOCK,
                plan=plan, cout_credits_estime=round(cout, 1),
                cout_fcfa_estime=cout_fcfa,
                solde_credits_avant=round(solde, 1),
                solde_credits_apres_estime=round(solde_apres, 1),
                quota_total=quota,
                pct_solde_consomme=round(min(pct_consomme, 999.0) * 100, 1),
                seuil_pct_plan=seuil_pct,
                module=module,
                message_user=(
                    f"Crédits insuffisants : il vous reste {int(solde)} "
                    f"crédit(s), cette opération en demande "
                    f"{int(cout)}. Rechargez ou changez de plan."
                ),
            )

        # 2. CONFIRM : opération non triviale ET ratio dépasse le seuil du plan
        if cout >= _PLANCHER_CREDITS_CONFIRM and pct_consomme >= seuil_pct:
            return AdvisorVerdict(
                action=AdvisorAction.CONFIRM,
                plan=plan, cout_credits_estime=round(cout, 1),
                cout_fcfa_estime=cout_fcfa,
                solde_credits_avant=round(solde, 1),
                solde_credits_apres_estime=round(solde_apres, 1),
                quota_total=quota,
                pct_solde_consomme=round(pct_consomme * 100, 1),
                seuil_pct_plan=seuil_pct,
                module=module,
                message_user=(
                    f"Cette opération va consommer "
                    f"{int(pct_consomme * 100)}% de votre solde restant "
                    f"(~{int(cout)} crédits / ~{int(cout_fcfa)} FCFA). "
                    f"Solde après : {int(solde_apres)} crédits. Continuer ?"
                ),
            )

        # 3. GO
        return AdvisorVerdict(
            action=AdvisorAction.GO,
            plan=plan, cout_credits_estime=round(cout, 1),
            cout_fcfa_estime=cout_fcfa,
            solde_credits_avant=round(solde, 1),
            solde_credits_apres_estime=round(solde_apres, 1),
            quota_total=quota,
            pct_solde_consomme=round(pct_consomme * 100, 1),
            seuil_pct_plan=seuil_pct,
            module=module,
            message_user="",
        )


# ── Estimation par module (heuristique) ──────────────────────────────────────
# Carte des coûts crédits estimés (max plausible) par type d'opération.
# Utilisée par l'endpoint `/preview-cost` quand le frontend envoie un type
# d'opération sans pouvoir calculer le coût exact lui-même.
_ESTIMATIONS_DEFAUT: dict[str, float] = {
    # Génération doc rapide
    "redaction_lettre":         60.0,
    "redaction_devis":          80.0,
    # Génération PDF/DOCX longue (LLM + render)
    "rapport_docx_court":      150.0,
    "rapport_docx_long":       500.0,
    "slides_pptx":             200.0,
    "slides_web":              250.0,
    # Landing pages
    "landing_page":            300.0,
    "landing_publish":          70.0,   # publish ~30 + QR 5 ≈ 35 + marge
    # Vidéo (très cher)
    "video_5s_standard":      1200.0,
    "video_5s_premium":       4800.0,
    "video_5s_ultra":        12000.0,
    "video_30s_premium":     28800.0,   # 6 clips × 4800
    # Designer Pro
    "designerpro_creation":    200.0,
    "designerpro_modif":        60.0,
    "designerpro_image_ultra": 560.0,
    "designerpro_brand_lora": 80000.0,  # one-shot, énorme
    # Freeform (PDF 1-page IA)
    "freeform_pdf_a4":         400.0,
    "freeform_pdf_long":      1500.0,
    # Infographie
    "infographie_flyer":       100.0,
    "infographie_carte":        50.0,
    # OCR
    "ocr_page":                 60.0,
    # Audio transcription minute
    "audio_min":                50.0,
    # Traduction (par 1000 chars)
    "traduction_1k_chars":      40.0,
    # Génération formulaire enquête (Phase E à venir)
    "enquete_generer":         300.0,
    "enquete_analyse_simple":  150.0,
    "enquete_analyse_complexe": 800.0,
    # Catch-all
    "default":                 100.0,
}


def estimer_cout_module(operation: str, multiplicateur: float = 1.0) -> float:
    """Retourne l'estimation crédits pour un type d'opération nommée.

    Si `operation` n'est pas dans le dict → retourne "default" (100 crédits).
    `multiplicateur` : nombre d'unités (ex. nb pages, nb minutes audio).
    """
    base = _ESTIMATIONS_DEFAUT.get(operation, _ESTIMATIONS_DEFAUT["default"])
    return base * max(1.0, float(multiplicateur))


# Singleton exporté
advisor = CostAdvisor()
