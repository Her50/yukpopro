"""
Service Crédits IA YukpoPro — Gestion de la consommation de tokens et crédits.

Principe :
  1 crédit Yukpo = 200 × (coût réel du token en FCFA)
  1 USD = 600 FCFA

Tarifs modèles IA (prix public approximatif en USD/1M tokens) :
  - claude-sonnet-4-6   : $3.00 input  / $15.00 output
  - claude-haiku-4-5    : $0.25 input  / $1.25  output
  - claude-opus-4-6     : $15.00 input / $75.00 output
  - gpt-4o              : $2.50 input  / $10.00 output
  - gpt-4o-mini         : $0.15 input  / $0.60  output

Allocation mensuelle par plan :
  - gratuit  :    500 crédits/mois
  - starter  :  5 000 crédits/mois
  - pro      : 20 000 crédits/mois
  - business : illimité (999 999)
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import CreditIAUserDB, ConsommationTokenDB

logger = logging.getLogger("yukpo_assurance.pro.service_credits")

# ── Taux de change ─────────────────────────────────────────────────────────────
USD_TO_FCFA = 600.0
MULTIPLICATEUR_YUKPO = 20.0   # 20× le coût réel en FCFA (marge Yukpo)

# ── Tarifs par modèle (USD / 1M tokens) ───────────────────────────────────────
TARIFS_MODELES: dict[str, dict[str, float]] = {
    "claude-opus-4-6":         {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-6":       {"input":  3.00, "output": 15.00},
    "claude-sonnet-4-5":       {"input":  3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.25, "output":  1.25},
    "claude-haiku-4-5":        {"input":  0.25, "output":  1.25},
    "gpt-4o":                  {"input":  2.50, "output": 10.00},
    "gpt-4o-mini":             {"input":  0.15, "output":  0.60},
    # Fallback
    "default":                 {"input":  3.00, "output": 15.00},
}

# ── Crédits mensuels par plan ──────────────────────────────────────────────────
CREDITS_PAR_PLAN: dict[str, int] = {
    "gratuit":  1_000,
    "starter":  5_000,
    "pro":      20_000,
    "business": 999_999,
}

# Label lisible pour l'interface
LABEL_CREDITS_PLAN: dict[str, str] = {
    "gratuit":  "1 000 crédits / mois",
    "starter":  "5 000 crédits / mois",
    "pro":      "20 000 crédits / mois",
    "business": "Illimité",
}


def calculer_cout(modele: str, tokens_input: int, tokens_output: int) -> dict:
    """
    Calcule le coût réel et les crédits Yukpo pour un appel IA.
    Retourne : cout_usd, cout_fcfa, credits_debites
    """
    tarif = TARIFS_MODELES.get(modele, TARIFS_MODELES["default"])
    cout_usd = (tokens_input * tarif["input"] + tokens_output * tarif["output"]) / 1_000_000
    cout_fcfa = cout_usd * USD_TO_FCFA
    credits_debites = cout_fcfa * MULTIPLICATEUR_YUKPO
    # Minimum 1 crédit par appel
    credits_debites = max(1.0, credits_debites)
    return {
        "cout_usd": round(cout_usd, 6),
        "cout_fcfa": round(cout_fcfa, 4),
        "credits_debites": round(credits_debites, 2),
    }


async def get_ou_creer_credits(user_id: int, db: AsyncSession) -> CreditIAUserDB:
    """Récupère ou crée le solde de crédits d'un utilisateur."""
    result = await db.execute(
        select(CreditIAUserDB).where(CreditIAUserDB.user_id == user_id)
    )
    credit = result.scalar_one_or_none()
    if not credit:
        credit = CreditIAUserDB(
            user_id=user_id,
            plan="gratuit",
            credits_alloues=CREDITS_PAR_PLAN["gratuit"],
            credits_utilises=0,
            periode_debut=datetime.utcnow(),
            periode_fin=datetime.utcnow() + timedelta(days=30),
        )
        db.add(credit)
        await db.flush()
        await db.refresh(credit)
    return credit


async def verifier_solde_suffisant(user_id: int) -> Tuple[bool, float, str, str]:
    """
    Pré-check rapide avant un appel LLM / service coûteux.
    Retourne : (ok, credits_restants, plan, message).
    Ne débite rien — sert à retourner 402 CREDITS_EPUISES avant de commencer le travail.
    """
    from core.database import async_session_maker

    try:
        async with async_session_maker() as fresh_db:
            credit = await get_ou_creer_credits(user_id, fresh_db)

            # Sync plan depuis profil si encore "gratuit"
            if credit.plan == "gratuit":
                try:
                    from modules.pro.service_profil import get_or_create as _get_profil
                    profil, _ = await _get_profil(user_id, fresh_db)
                    plan_profil = (profil.preferences or {}).get("plan", "gratuit")
                    if plan_profil != "gratuit":
                        credit.plan = plan_profil
                        credit.credits_alloues = CREDITS_PAR_PLAN.get(
                            plan_profil, CREDITS_PAR_PLAN["gratuit"]
                        )
                        await fresh_db.commit()
                except Exception:
                    pass

            if credit.plan == "business":
                return True, float("inf"), credit.plan, "ok"

            if credit.periode_fin and datetime.utcnow() > credit.periode_fin:
                credit.credits_utilises = 0
                credit.periode_debut = datetime.utcnow()
                credit.periode_fin = datetime.utcnow() + timedelta(days=30)
                await fresh_db.commit()

            restants = credit.credits_alloues - credit.credits_utilises
            if restants <= 0:
                return False, 0.0, credit.plan, (
                    f"CREDITS_EPUISES|restants=0|plan={credit.plan}"
                )
            return True, float(restants), credit.plan, "ok"
    except Exception as e:
        logger.error(f"[Credits/PreCheck] Erreur user={user_id}: {e}")
        # Ne pas bloquer en cas d'erreur DB
        return True, 0.0, "inconnu", "ok"


async def verifier_et_debiter(
    user_id: int,
    modele: str,
    tokens_input: int,
    tokens_output: int,
    module: str = "chat",
    session_id: Optional[str] = None,
    db: Optional[AsyncSession] = None,
) -> Tuple[bool, float, str]:
    """
    Vérifie si l'utilisateur a assez de crédits et les débite.
    Retourne : (ok, credits_debites, message)

    Utilise toujours sa propre session indépendante pour éviter les conflits
    avec la session de requête principale.
    """
    from core.database import async_session_maker

    try:
        async with async_session_maker() as fresh_db:
            credit = await get_ou_creer_credits(user_id, fresh_db)

            # Synchroniser le plan depuis le profil si toujours "gratuit" par défaut
            if credit.plan == "gratuit":
                try:
                    from modules.pro.service_profil import get_or_create as _get_profil
                    profil, _ = await _get_profil(user_id, fresh_db)
                    plan_profil = (profil.preferences or {}).get("plan", "gratuit")
                    if plan_profil != "gratuit":
                        credit.plan = plan_profil
                        credit.credits_alloues = CREDITS_PAR_PLAN.get(plan_profil, CREDITS_PAR_PLAN["gratuit"])
                        await fresh_db.flush()
                except Exception:
                    pass

            # Plan business = illimité, pas de vérification ni débit
            if credit.plan == "business":
                return True, 0.0, "ok"

            # Renouvellement mensuel automatique
            if credit.periode_fin and datetime.utcnow() > credit.periode_fin:
                credit.credits_utilises = 0
                credit.periode_debut = datetime.utcnow()
                credit.periode_fin = datetime.utcnow() + timedelta(days=30)
                await fresh_db.commit()

            calcul = calculer_cout(modele, tokens_input, tokens_output)
            credits_debites = calcul["credits_debites"]

            restants = credit.credits_alloues - credit.credits_utilises
            if restants <= 0:
                return False, 0.0, (
                    f"CREDITS_EPUISES|{credit.credits_utilises}|{credit.credits_alloues}"
                )

            # Débit
            credit.credits_utilises += credits_debites
            credit.mise_a_jour = datetime.utcnow()

            # Log consommation
            log = ConsommationTokenDB(
                user_id=user_id,
                modele=modele,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                cout_usd=calcul["cout_usd"],
                cout_fcfa=calcul["cout_fcfa"],
                credits_debites=credits_debites,
                module=module,
                session_id=session_id,
            )
            fresh_db.add(log)
            await fresh_db.commit()

            logger.info(
                f"[Credits] user={user_id} modele={modele} "
                f"tokens={tokens_input}+{tokens_output} "
                f"credits={credits_debites:.1f} restants={restants - credits_debites:.0f}"
            )
            return True, credits_debites, "ok"

    except Exception as e:
        logger.error(f"[Credits] Erreur débit user={user_id} : {e}", exc_info=True)
        # Ne pas bloquer l'IA en cas d'erreur DB
        return True, 0.0, "ok"


async def _forcer_plan_business(user_id: int, db: Optional[AsyncSession] = None) -> None:
    """Force le plan business pour les admins sans toucher aux stats de consommation."""
    from core.database import async_session_maker
    async with async_session_maker() as fresh_db:
        credit = await get_ou_creer_credits(user_id, fresh_db)
        if credit.plan != "business":
            credit.plan = "business"
            credit.credits_alloues = CREDITS_PAR_PLAN["business"]
            credit.mise_a_jour = datetime.utcnow()
            await fresh_db.commit()
            logger.warning(f"[Credits] Plan forcé business (admin) user={user_id}")


async def debiter_forfait_fcfa(
    user_id: int,
    cout_fcfa: float,
    module: str = "service",
    multiplicateur: float = MULTIPLICATEUR_YUKPO,
) -> Tuple[bool, float, str]:
    """
    Débite un forfait exprimé en FCFA pour les services non-LLM.
    credits_debites = cout_fcfa × multiplicateur (min 1).
    multiplicateur : 20× (défaut, avec traduction) ou 5× (STT-only, sans traduction).
    """
    from core.database import async_session_maker, ConsommationTokenDB

    credits_debites = max(1.0, round(cout_fcfa * multiplicateur, 2))
    try:
        async with async_session_maker() as fresh_db:
            credit = await get_ou_creer_credits(user_id, fresh_db)

            if credit.plan == "business":
                return True, 0.0, "ok"

            if credit.periode_fin and datetime.utcnow() > credit.periode_fin:
                credit.credits_utilises = 0
                credit.periode_debut = datetime.utcnow()
                credit.periode_fin = datetime.utcnow() + timedelta(days=30)
                await fresh_db.commit()

            restants = credit.credits_alloues - credit.credits_utilises
            if restants <= 0:
                return False, 0.0, (
                    f"CREDITS_EPUISES|{credit.credits_utilises}|{credit.credits_alloues}"
                )

            credit.credits_utilises += credits_debites
            credit.mise_a_jour = datetime.utcnow()

            log = ConsommationTokenDB(
                user_id=user_id,
                modele="forfait",
                tokens_input=0,
                tokens_output=0,
                cout_usd=round(cout_fcfa / USD_TO_FCFA, 6),
                cout_fcfa=round(cout_fcfa, 4),
                credits_debites=credits_debites,
                module=module,
                session_id=None,
            )
            fresh_db.add(log)
            await fresh_db.commit()

            logger.info(
                f"[Credits/Forfait] user={user_id} module={module} "
                f"cout={cout_fcfa}FCFA credits={credits_debites:.1f}"
            )
            return True, credits_debites, "ok"

    except Exception as e:
        logger.error(f"[Credits/Forfait] Erreur user={user_id}: {e}", exc_info=True)
        return True, 0.0, "ok"


async def synchroniser_plan(user_id: int, plan: str, db: AsyncSession) -> None:
    """
    Met à jour le plan d'un utilisateur après confirmation de paiement.
    Alloue les nouveaux crédits mensuels selon le plan choisi.
    """
    credit = await get_ou_creer_credits(user_id, db)
    credit.plan = plan
    credit.credits_alloues = CREDITS_PAR_PLAN.get(plan, CREDITS_PAR_PLAN["gratuit"])
    # Renouvellement immédiat
    credit.credits_utilises = 0
    credit.periode_debut = datetime.utcnow()
    credit.periode_fin = datetime.utcnow() + timedelta(days=30)
    credit.mise_a_jour = datetime.utcnow()
    await db.commit()
    logger.info(f"[Credits] Plan mis à jour user={user_id} → {plan} ({credit.credits_alloues} crédits/mois)")


async def solde_utilisateur(user_id: int, db: AsyncSession) -> dict:
    """Retourne le solde complet d'un utilisateur."""
    credit = await get_ou_creer_credits(user_id, db)

    # Renouvellement automatique
    if credit.periode_fin and datetime.utcnow() > credit.periode_fin:
        credit.credits_utilises = 0
        credit.periode_debut = datetime.utcnow()
        credit.periode_fin = datetime.utcnow() + timedelta(days=30)
        await db.commit()

    restants = max(0.0, credit.credits_alloues - credit.credits_utilises)
    pct_utilise = (credit.credits_utilises / credit.credits_alloues * 100) if credit.credits_alloues > 0 else 0

    return {
        "plan": credit.plan,
        "credits_alloues": credit.credits_alloues,
        "credits_utilises": round(credit.credits_utilises, 1),
        "credits_restants": round(restants, 1),
        "pct_utilise": round(pct_utilise, 1),
        "label_plan": LABEL_CREDITS_PLAN.get(credit.plan, "Gratuit"),
        "periode_debut": credit.periode_debut.isoformat() if credit.periode_debut else None,
        "periode_fin": credit.periode_fin.isoformat() if credit.periode_fin else None,
        "renouvellement_le": credit.periode_fin.strftime("%d/%m/%Y") if credit.periode_fin else None,
        # Equivalents lisibles
        "credits_en_fcfa_equiv": round(restants / MULTIPLICATEUR_YUKPO, 0),
        "explication": (
            f"Vos {int(restants)} crédits Yukpo restants équivalent à environ "
            f"{int(restants / MULTIPLICATEUR_YUKPO)} FCFA d'utilisation Yukpo."
        ),
    }
