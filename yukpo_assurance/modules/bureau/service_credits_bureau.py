"""
Service Crédits Bureau — YukpoSecrétariat.

Philosophie identique à YukpoPro :
  1 crédit Yukpo = 20× le coût réel en FCFA (marge de 2000%)
  1 USD = 600 FCFA

Plans YukpoSecrétariat :
  - gratuit     : 0 FCFA       → 1 000  crédits/mois   (tous modules, quota limité)
  - secretariat : 5 000 FCFA   → 20 000 crédits/mois   (rédaction, OCR, audio, traduction, gestion)
  - infographie : 5 000 FCFA   → 20 000 crédits/mois   (infographie, gestion)
  - complet     : 10 000 FCFA  → 50 000 crédits/mois   (tous les modules)

Toutes les fonctionnalités (LLM et non-LLM) sont facturées en crédits :
  - LLM : basé sur tokens × tarif modèle × 20
  - Non-LLM : forfait FCFA × 20 (OCR, génération PDF/DOCX, kanban, caisse, CRM…)
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import CreditBureauDB, ConsommationBureauDB

logger = logging.getLogger("yukpo_assurance.bureau.service_credits")

# ── Constantes ─────────────────────────────────────────────────────────────────
USD_TO_FCFA = 600.0
MULTIPLICATEUR_YUKPO = 20.0  # 20× coût réel FCFA

# ── Tarifs modèles (USD / 1M tokens) — mêmes que YukpoPro ─────────────────────
TARIFS_MODELES: dict[str, dict[str, float]] = {
    "claude-opus-4-6":           {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-6":         {"input":  3.00, "output": 15.00},
    "claude-sonnet-4-5":         {"input":  3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input":  0.25, "output":  1.25},
    "claude-haiku-4-5":          {"input":  0.25, "output":  1.25},
    "gpt-4o":                    {"input":  2.50, "output": 10.00},
    "gpt-4o-mini":               {"input":  0.15, "output":  0.60},
    "whisper-1":                 {"input":  0.00, "output":  0.00},  # facturé en forfait
    "default":                   {"input":  3.00, "output": 15.00},
}

# ── Plans Bureau ───────────────────────────────────────────────────────────────
PLANS_BUREAU: dict[str, dict] = {
    "gratuit": {
        "id": "gratuit",
        "nom": "Gratuit",
        "prix_fcfa": 0,
        "credits_mois": 1_000,
        "duree_jours": 0,
        "modules": ["redaction", "ocr", "audio", "traduction", "infographie", "gestion", "documents"],
        "description": "Accès à tous les modules — crédits limités pour découvrir",
        "label_credits": "1 000 crédits / mois",
    },
    "secretariat": {
        "id": "secretariat",
        "nom": "Secrétariat",
        "prix_fcfa": 5_000,
        "credits_mois": 20_000,
        "duree_jours": 30,
        "modules": ["redaction", "ocr", "audio", "traduction", "gestion", "documents"],
        "description": "Rédaction IA, OCR, Audio, Traduction + Gestion complète",
        "label_credits": "20 000 crédits / mois",
        "badge": "Populaire",
    },
    "infographie": {
        "id": "infographie",
        "nom": "Infographie",
        "prix_fcfa": 5_000,
        "credits_mois": 20_000,
        "duree_jours": 30,
        "modules": ["infographie", "gestion", "documents"],
        "description": "Tous les formats d'infographie print + Gestion",
        "label_credits": "20 000 crédits / mois",
    },
    "complet": {
        "id": "complet",
        "nom": "Complet",
        "prix_fcfa": 10_000,
        "credits_mois": 50_000,
        "duree_jours": 30,
        "modules": ["redaction", "ocr", "audio", "traduction", "infographie", "gestion", "documents"],
        "description": "Accès illimité à tous les modules Secrétariat + Infographie",
        "label_credits": "50 000 crédits / mois",
        "badge": "Meilleur rapport qualité/prix",
    },
}

# ── Forfaits non-LLM (FCFA) ───────────────────────────────────────────────────
# Multiplié par 20 = crédits Yukpo débités
COUTS_FORFAIT_FCFA: dict[str, float] = {
    # Infographie (non-LLM = rendu ReportLab + traitement image)
    # "infographie_creation" est facturé au tarif réel du gabarit (en FCFA),
    # via multiplicateur=prix_fcfa_du_gabarit. Ex : carte visite 2000 FCFA, flyer A5 3000 FCFA.
    "infographie_creation":  1.0,   # base 1 FCFA, multiplié par le prix_fcfa du gabarit
    "infographie_vision":   10.0,   # 200 crédits (analyse image modèle uploadé)
    # OCR / traitement image
    "ocr_scan":              3.0,   #  60 crédits
    "ocr_manuscrit":         5.0,   # 100 crédits (vision avancée)
    # Génération documents bureautique
    "docx_generation":       1.5,   #  30 crédits
    "pdf_generation":        1.5,   #  30 crédits
    # Audio (transcription Whisper en plus du forfait)
    "audio_transcription":   2.5,   #  50 crédits / minute audio
    # Gestion
    "devis_pdf":             1.0,   #  20 crédits
    "facture_pdf":           1.0,   #  20 crédits
    "kanban_action":         0.25,  #   5 crédits (créer/modifier tâche)
    "client_action":         0.5,   #  10 crédits (créer/modifier client)
    "caisse_transaction":    0.25,  #   5 crédits (enregistrer transaction)
    "whatsapp_message":      0.5,   #  10 crédits
    "document_download":     0.25,  #   5 crédits
    "document_suppression":  0.1,   #   2 crédits
}

# ── Labels crédits par plan ────────────────────────────────────────────────────
LABEL_CREDITS_PLAN: dict[str, str] = {
    p: info["label_credits"] for p, info in PLANS_BUREAU.items()
}


def calculer_cout_llm(modele: str, tokens_input: int, tokens_output: int) -> dict:
    """Calcule le coût réel + crédits à débiter pour un appel LLM."""
    tarif = TARIFS_MODELES.get(modele, TARIFS_MODELES["default"])
    cout_usd = (tokens_input * tarif["input"] + tokens_output * tarif["output"]) / 1_000_000
    cout_fcfa = cout_usd * USD_TO_FCFA
    credits_debites = max(1.0, cout_fcfa * MULTIPLICATEUR_YUKPO)
    return {
        "cout_usd": round(cout_usd, 6),
        "cout_fcfa": round(cout_fcfa, 4),
        "credits_debites": round(credits_debites, 2),
    }


async def get_ou_creer_credits_bureau(user_id: int, db: AsyncSession) -> CreditBureauDB:
    """Récupère ou crée le solde bureau d'un utilisateur (plan gratuit par défaut)."""
    result = await db.execute(select(CreditBureauDB).where(CreditBureauDB.user_id == user_id))
    credit = result.scalar_one_or_none()
    if not credit:
        credit = CreditBureauDB(
            user_id=user_id,
            plan="gratuit",
            credits_alloues=PLANS_BUREAU["gratuit"]["credits_mois"],
            credits_utilises=0.0,
            periode_debut=datetime.utcnow(),
            periode_fin=datetime.utcnow() + timedelta(days=30),
        )
        db.add(credit)
        await db.flush()
        await db.refresh(credit)
    return credit


def module_autorise(plan: str, module: str) -> bool:
    """Vérifie si un module est autorisé pour le plan donné."""
    info = PLANS_BUREAU.get(plan, PLANS_BUREAU["gratuit"])
    return module in info.get("modules", [])


async def verifier_acces_module(user_id: int, module: str) -> Tuple[bool, str, str]:
    """
    Vérifie si l'utilisateur a accès au module bureau demandé.
    Tout abonné YukpoPro (starter/pro/business) a accès à tous les modules bureau.
    Retourne (autorise, plan_actif, message).
    """
    try:
        pro_actif, plan_pro = await _has_plan_pro_actif(user_id)
        if pro_actif:
            return True, f"pro:{plan_pro}", "ok"
    except Exception:
        pass

    from core.database import async_session_maker
    try:
        async with async_session_maker() as fresh_db:
            credit = await get_ou_creer_credits_bureau(user_id, fresh_db)
            plan = credit.plan
            if module_autorise(plan, module):
                return True, plan, "ok"
            plans_autorises = [p for p, info in PLANS_BUREAU.items() if module in info["modules"] and p != "gratuit"]
            return False, plan, (
                f"MODULE_NON_AUTORISE|{module}|{plan}|"
                f"Plans donnant accès : {', '.join(plans_autorises)}"
            )
    except Exception as e:
        logger.error(f"[Bureau/Access] Erreur user={user_id} module={module} : {e}")
        return True, "gratuit", "ok"  # ne pas bloquer sur erreur DB


async def _renouveler_si_expire(credit: CreditBureauDB, db: AsyncSession) -> None:
    """Renouvellement mensuel automatique."""
    if credit.periode_fin and datetime.utcnow() > credit.periode_fin:
        credit.credits_utilises = 0.0
        credit.periode_debut = datetime.utcnow()
        credit.periode_fin = datetime.utcnow() + timedelta(days=30)
        await db.commit()


async def debiter_llm(
    user_id: int,
    modele: str,
    tokens_input: int,
    tokens_output: int,
    module: str = "bureau",
) -> Tuple[bool, float, str]:
    """
    Débite les crédits pour un appel LLM bureau.
    Si l'utilisateur a un abonnement YukpoPro actif, débite côté Pro en priorité.
    Sinon retombe sur le solde bureau.
    Non-bloquant : si la DB échoue, on n'empêche pas l'IA.
    """
    from core.database import async_session_maker
    try:
        pro_actif, _ = await _has_plan_pro_actif(user_id)
        if pro_actif:
            from modules.pro.service_credits import verifier_et_debiter as _pro_debit
            ok, dbt, msg = await _pro_debit(
                user_id=user_id, modele=modele,
                tokens_input=tokens_input, tokens_output=tokens_output,
                module=module,
            )
            if ok:
                return ok, dbt, msg
    except Exception as e:
        logger.warning(f"[Bureau/Unifie] délégation Pro LLM échouée user={user_id}: {e}")

    try:
        async with async_session_maker() as fresh_db:
            credit = await get_ou_creer_credits_bureau(user_id, fresh_db)
            await _renouveler_si_expire(credit, fresh_db)

            calcul = calculer_cout_llm(modele, tokens_input, tokens_output)
            credits_debites = calcul["credits_debites"]

            restants = credit.credits_alloues - credit.credits_utilises
            if restants <= 0:
                return False, 0.0, f"CREDITS_EPUISES|{int(credit.credits_utilises)}|{credit.credits_alloues}"

            credit.credits_utilises += credits_debites
            credit.mise_a_jour = datetime.utcnow()

            log = ConsommationBureauDB(
                user_id=user_id, modele=modele,
                tokens_input=tokens_input, tokens_output=tokens_output,
                cout_usd=calcul["cout_usd"], cout_fcfa=calcul["cout_fcfa"],
                credits_debites=credits_debites, module=module,
            )
            fresh_db.add(log)
            await fresh_db.commit()

            logger.info(
                f"[Bureau/Credits] user={user_id} module={module} modele={modele} "
                f"tokens={tokens_input}+{tokens_output} credits={credits_debites:.1f}"
            )
            return True, credits_debites, "ok"
    except Exception as e:
        logger.error(f"[Bureau/Credits] Erreur LLM user={user_id} : {e}", exc_info=True)
        return True, 0.0, "ok"


async def debiter_forfait(
    user_id: int,
    type_forfait: str,
    module: str = "bureau",
    multiplicateur: float = 1.0,
) -> Tuple[bool, float, str]:
    """
    Débite un forfait non-LLM.
    type_forfait : clé de COUTS_FORFAIT_FCFA (ex : "ocr_scan", "infographie_pdf")
    multiplicateur : permet de facturer plusieurs unités (ex : durée audio en minutes)

    Si l'utilisateur a un abonnement YukpoPro actif, débite côté Pro en priorité.
    """
    from core.database import async_session_maker

    cout_fcfa = COUTS_FORFAIT_FCFA.get(type_forfait, 1.0) * multiplicateur
    credits_debites = max(1.0, round(cout_fcfa * MULTIPLICATEUR_YUKPO, 2))

    try:
        pro_actif, _ = await _has_plan_pro_actif(user_id)
        if pro_actif:
            from modules.pro.service_credits import debiter_forfait_fcfa as _pro_forfait
            ok, dbt, msg = await _pro_forfait(user_id, cout_fcfa, module=module)
            if ok:
                return ok, dbt, msg
    except Exception as e:
        logger.warning(f"[Bureau/Unifie] délégation Pro forfait échouée user={user_id}: {e}")

    try:
        async with async_session_maker() as fresh_db:
            credit = await get_ou_creer_credits_bureau(user_id, fresh_db)
            await _renouveler_si_expire(credit, fresh_db)

            restants = credit.credits_alloues - credit.credits_utilises
            if restants <= 0:
                return False, 0.0, f"CREDITS_EPUISES|{int(credit.credits_utilises)}|{credit.credits_alloues}"

            credit.credits_utilises += credits_debites
            credit.mise_a_jour = datetime.utcnow()

            log = ConsommationBureauDB(
                user_id=user_id, modele=f"forfait:{type_forfait}",
                tokens_input=0, tokens_output=0,
                cout_usd=round(cout_fcfa / USD_TO_FCFA, 6),
                cout_fcfa=round(cout_fcfa, 4),
                credits_debites=credits_debites, module=module,
            )
            fresh_db.add(log)
            await fresh_db.commit()

            logger.info(
                f"[Bureau/Forfait] user={user_id} type={type_forfait} module={module} "
                f"credits={credits_debites:.1f} (x{multiplicateur})"
            )
            return True, credits_debites, "ok"
    except Exception as e:
        logger.error(f"[Bureau/Forfait] Erreur user={user_id} : {e}", exc_info=True)
        return True, 0.0, "ok"


async def verifier_solde(user_id: int) -> Tuple[bool, float, int]:
    """
    Vérifie rapidement si l'utilisateur a encore des crédits.
    Si abonnement YukpoPro actif, on regarde son solde Pro en priorité.
    Retourne (a_credits, restants, alloues).
    """
    try:
        pro_actif, _ = await _has_plan_pro_actif(user_id)
        if pro_actif:
            from modules.pro.service_credits import verifier_solde_suffisant as _pro_chk
            ok, restants_pro, plan_pro, _msg = await _pro_chk(user_id)
            if ok:
                from modules.pro.service_credits import CREDITS_PAR_PLAN
                alloues = CREDITS_PAR_PLAN.get(plan_pro, CREDITS_PAR_PLAN["gratuit"])
                rest = float(restants_pro) if restants_pro != float("inf") else 999999.0
                return True, rest, int(alloues)
    except Exception as e:
        logger.warning(f"[Bureau/Unifie] check Pro solde échoué user={user_id}: {e}")

    from core.database import async_session_maker
    try:
        async with async_session_maker() as fresh_db:
            credit = await get_ou_creer_credits_bureau(user_id, fresh_db)
            await _renouveler_si_expire(credit, fresh_db)
            restants = max(0.0, credit.credits_alloues - credit.credits_utilises)
            return restants > 0, restants, credit.credits_alloues
    except Exception:
        return True, 999999.0, 999999


_PRO_PLAN_CACHE: dict[int, tuple[float, bool, str]] = {}
_PRO_PLAN_TTL_S = 60.0


async def _has_plan_pro_actif(user_id: int) -> tuple[bool, str]:
    """Indique si l'utilisateur dispose d'un abonnement Pro payant ou business.

    Cache 60 s par user_id pour limiter la pression DB.
    Sur erreur DB, on retourne le dernier état connu (sticky) plutôt que
    de retomber silencieusement à 'gratuit' et provoquer un 402 abusif.
    """
    import time
    from core.database import async_session_maker
    from modules.pro.service_credits import get_ou_creer_credits as _get_pro
    from modules.pro.service_profil import get_or_create as _get_profil

    now = time.monotonic()
    cached = _PRO_PLAN_CACHE.get(user_id)
    if cached and (now - cached[0]) < _PRO_PLAN_TTL_S:
        return cached[1], cached[2]

    last_err: Optional[Exception] = None
    for tentative in range(2):
        try:
            async with async_session_maker() as fresh:
                credit = await _get_pro(user_id, fresh)
                plan = credit.plan or "gratuit"
                if plan == "gratuit":
                    try:
                        profil, _ = await _get_profil(user_id, fresh)
                        plan = (profil.preferences or {}).get("plan", "gratuit") or "gratuit"
                    except Exception:
                        pass
                actif = plan in ("starter", "pro", "business")
                _PRO_PLAN_CACHE[user_id] = (now, actif, plan)
                return actif, plan
        except Exception as e:
            last_err = e

    logger.warning(f"[Bureau/Unifie] check Pro échoué user={user_id}: {last_err}")
    if cached:
        return cached[1], cached[2]
    return False, "gratuit"


async def verifier_solde_unifie(user_id: int) -> tuple[bool, float, str, str]:
    """
    Pré-check unifié Pro+Bureau pour modules bureau.
    Si l'utilisateur a un abonnement YukpoPro actif (starter/pro/business), on utilise
    le solde Pro. Sinon on retombe sur le solde Bureau.
    Retourne (ok, restants, source, message) — source ∈ {pro, bureau}.
    """
    pro_actif, plan_pro = await _has_plan_pro_actif(user_id)
    if pro_actif:
        from modules.pro.service_credits import verifier_solde_suffisant
        ok, restants, plan, msg = await verifier_solde_suffisant(user_id)
        if ok:
            return True, restants, "pro", "ok"
        # Pro épuisé → on tente le bureau en fallback
    ok_b, restants_b, alloues_b = await verifier_solde(user_id)
    if ok_b:
        return True, float(restants_b), "bureau", "ok"
    return False, 0.0, "bureau", f"CREDITS_EPUISES|restants=0|plan_pro={plan_pro}"


async def debiter_llm_unifie(
    user_id: int, modele: str, tokens_input: int, tokens_output: int,
    module: str = "bureau",
) -> Tuple[bool, float, str]:
    """Débite l'appel LLM côté Pro si abonné, sinon Bureau."""
    pro_actif, _ = await _has_plan_pro_actif(user_id)
    if pro_actif:
        from modules.pro.service_credits import verifier_et_debiter
        ok, dbt, msg = await verifier_et_debiter(
            user_id=user_id, modele=modele,
            tokens_input=tokens_input, tokens_output=tokens_output,
            module=module,
        )
        if ok:
            return ok, dbt, msg
    return await debiter_llm(user_id, modele, tokens_input, tokens_output, module)


async def debiter_forfait_unifie(
    user_id: int, type_forfait: str, module: str = "bureau", multiplicateur: float = 1.0,
) -> Tuple[bool, float, str]:
    """Débite un forfait non-LLM côté Pro si abonné, sinon Bureau."""
    pro_actif, _ = await _has_plan_pro_actif(user_id)
    if pro_actif:
        cout_fcfa = COUTS_FORFAIT_FCFA.get(type_forfait, 1.0) * multiplicateur
        from modules.pro.service_credits import debiter_forfait_fcfa
        ok, dbt, msg = await debiter_forfait_fcfa(user_id, cout_fcfa, module=module)
        if ok:
            return ok, dbt, msg
    return await debiter_forfait(user_id, type_forfait, module=module, multiplicateur=multiplicateur)


async def synchroniser_plan_bureau(user_id: int, plan: str, db: AsyncSession) -> None:
    """Active un nouveau plan après paiement confirmé (reset mensuel)."""
    credit = await get_ou_creer_credits_bureau(user_id, db)
    credit.plan = plan
    credit.credits_alloues = PLANS_BUREAU.get(plan, PLANS_BUREAU["gratuit"])["credits_mois"]
    credit.credits_utilises = 0.0
    credit.periode_debut = datetime.utcnow()
    credit.periode_fin = datetime.utcnow() + timedelta(days=30)
    credit.mise_a_jour = datetime.utcnow()
    await db.commit()
    logger.info(f"[Bureau/Plan] Activé user={user_id} → {plan} ({credit.credits_alloues} crédits)")


async def solde_utilisateur_bureau(user_id: int, db: AsyncSession) -> dict:
    """Retourne le solde complet d'un utilisateur bureau."""
    credit = await get_ou_creer_credits_bureau(user_id, db)
    await _renouveler_si_expire(credit, db)

    restants = max(0.0, credit.credits_alloues - credit.credits_utilises)
    pct_utilise = (credit.credits_utilises / credit.credits_alloues * 100) if credit.credits_alloues > 0 else 0
    plan_info = PLANS_BUREAU.get(credit.plan, PLANS_BUREAU["gratuit"])

    return {
        "plan": credit.plan,
        "nom_plan": plan_info["nom"],
        "prix_fcfa": plan_info["prix_fcfa"],
        "modules_autorises": plan_info["modules"],
        "credits_alloues": credit.credits_alloues,
        "credits_utilises": round(credit.credits_utilises, 1),
        "credits_restants": round(restants, 1),
        "pct_utilise": round(pct_utilise, 1),
        "label_credits": plan_info["label_credits"],
        "periode_debut": credit.periode_debut.isoformat() if credit.periode_debut else None,
        "periode_fin": credit.periode_fin.isoformat() if credit.periode_fin else None,
        "renouvellement_le": credit.periode_fin.strftime("%d/%m/%Y") if credit.periode_fin else None,
        "credits_en_fcfa_equiv": round(restants / MULTIPLICATEUR_YUKPO, 0),
        "explication": (
            f"Vos {int(restants)} crédits Yukpo restants équivalent à environ "
            f"{int(restants / MULTIPLICATEUR_YUKPO)} FCFA d'utilisation."
        ),
    }


# ── Packs de recharge (mêmes tarifs que YukpoPro) ─────────────────────────────

PACKS_CREDITS_BUREAU: dict[str, dict] = {
    "pack_bureau_2000": {
        "id": "pack_bureau_2000",
        "nom": "Pack 2 000",
        "credits": 2_000,
        "prix_fcfa": 1_200,
        "description": "2 000 crédits supplémentaires",
    },
    "pack_bureau_5000": {
        "id": "pack_bureau_5000",
        "nom": "Pack 5 000",
        "credits": 5_000,
        "prix_fcfa": 3_000,
        "description": "5 000 crédits supplémentaires",
        "badge": "Populaire",
    },
    "pack_bureau_15000": {
        "id": "pack_bureau_15000",
        "nom": "Pack 15 000",
        "credits": 15_000,
        "prix_fcfa": 9_000,
        "description": "15 000 crédits supplémentaires",
        "badge": "Meilleur prix",
    },
    "pack_bureau_30000": {
        "id": "pack_bureau_30000",
        "nom": "Pack 30 000",
        "credits": 30_000,
        "prix_fcfa": 18_000,
        "description": "30 000 crédits supplémentaires",
    },
}
