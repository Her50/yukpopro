"""
Routes Abonnement YukpoPro — Gestion des plans et paiements Mobile Money.

Plans :
  - gratuit   : 5 req/jour, 3 agents suggérés
  - starter   : 50 req/jour, tous agents — 3 000 FCFA/mois
  - pro       : 200 req/jour, tous agents + extras — 7 500 FCFA/mois
  - business  : illimité, API, multi-users — 20 000 FCFA/mois

Endpoints :
  GET    /api/v1/pro/abonnement/         — Mon abonnement actif
  GET    /api/v1/pro/abonnement/plans    — Tous les plans disponibles
  POST   /api/v1/pro/abonnement/initier  — Initier un paiement Mobile Money
  POST   /api/v1/pro/abonnement/confirmer — Confirmer après paiement
  GET    /api/v1/pro/abonnement/historique — Historique des paiements
"""
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import TokenData, get_current_user
from core.database import async_session_maker

logger = logging.getLogger("yukpo_assurance.api.pro_abonnement")

router = APIRouter()


async def get_db():
    async with async_session_maker() as session:
        yield session


# ── Plans disponibles ─────────────────────────────────────────────────────────

PLANS = {
    "gratuit": {
        "id": "gratuit",
        "nom": "Gratuit",
        "prix_fcfa": 0,
        "quota_jour": 5,
        "duree_jours": 0,  # permanent
        "agents_illimites": True,
        "nb_agents_max": 13,
    },
    "starter": {
        "id": "starter",
        "nom": "Starter",
        "prix_fcfa": 3000,
        "quota_jour": 50,
        "duree_jours": 30,
        "agents_illimites": True,
        "nb_agents_max": 11,
    },
    "pro": {
        "id": "pro",
        "nom": "Pro",
        "prix_fcfa": 7500,
        "quota_jour": 200,
        "duree_jours": 30,
        "agents_illimites": True,
        "nb_agents_max": 11,
    },
    "business": {
        "id": "business",
        "nom": "Business",
        "prix_fcfa": 20000,
        "quota_jour": 99999,
        "duree_jours": 30,
        "agents_illimites": True,
        "nb_agents_max": 11,
    },
}

# ── Packs de recharge de crédits ─────────────────────────────────────────────

PACKS_CREDITS = {
    # Ratio de référence : 5 000 crédits = 3 000 FCFA (0,6 FCFA/crédit)
    "pack_500": {
        "id": "pack_500",
        "nom": "Pack 500",
        "credits": 500,
        "prix_fcfa": 300,
        "description": "500 crédits supplémentaires",
    },
    "pack_2000": {
        "id": "pack_2000",
        "nom": "Pack 2 000",
        "credits": 2000,
        "prix_fcfa": 1200,
        "description": "2 000 crédits supplémentaires",
        "badge": "Populaire",
    },
    "pack_5000": {
        "id": "pack_5000",
        "nom": "Pack 5 000",
        "credits": 5000,
        "prix_fcfa": 3000,
        "description": "5 000 crédits supplémentaires",
        "badge": "Meilleur prix",
    },
    "pack_15000": {
        "id": "pack_15000",
        "nom": "Pack 15 000",
        "credits": 15000,
        "prix_fcfa": 9000,
        "description": "15 000 crédits supplémentaires",
    },
}


class InitierRechargeRequest(BaseModel):
    pack_id:          str = Field(..., description="pack_500 | pack_2000 | pack_5000 | pack_15000")
    operateur:        str = Field(..., description="orange_money | mtn_momo | wave | ...")
    numero_telephone: str = Field(..., min_length=8, max_length=15)
    pays:             str = Field("CM")


OPERATEURS = {
    "orange_money":  {"label": "Orange Money",  "prefixes": ["69", "65", "66"]},
    "mtn_momo":      {"label": "MTN MoMo",       "prefixes": ["67", "68"]},
    "wave":          {"label": "Wave",            "prefixes": ["70", "76"]},
    "moov_money":    {"label": "Moov Money",      "prefixes": ["56"]},
    "airtel_money":  {"label": "Airtel Money",    "prefixes": ["77"]},
    "expressunion":  {"label": "Express Union",   "prefixes": ["93", "94"]},
}


# ── Modèles Pydantic ──────────────────────────────────────────────────────────

class InitierPaiementRequest(BaseModel):
    plan:              str = Field(..., description="starter | pro | business")
    operateur:         str = Field(..., description="orange_money | mtn_momo | wave | ...")
    numero_telephone:  str = Field(..., min_length=8, max_length=15)
    pays:              str = Field("CM", description="Code pays ISO 2")


class ConfirmerPaiementRequest(BaseModel):
    reference_paiement: str = Field(..., min_length=4)
    transaction_id:     Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════════
# Routes
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/plans", summary="Liste des plans disponibles")
async def lister_plans():
    """Retourne tous les plans avec leurs caractéristiques et tarifs."""
    return {"plans": list(PLANS.values())}


ADMIN_ROLES = ("admin", "super_admin", "yukpo_owner")


@router.get("/", summary="Mon abonnement actif")
async def mon_abonnement(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retourne le plan actif, le quota restant et la date d'expiration."""
    # Les admins ont un accès illimité sans abonnement
    if current_user.role in ADMIN_ROLES:
        from modules.pro.service_credits import _forcer_plan_business
        try:
            await _forcer_plan_business(current_user.user_id, db)
        except Exception as _e:
            logger.warning(f"[Admin] _forcer_plan_business erreur: {_e}")
        _ADMIN_CREDITS = 999_999
        return {
            "plan":               "business",
            "nom_plan":           "Admin — Accès Total",
            "statut":             "actif",
            "credits_alloues":    _ADMIN_CREDITS,
            "credits_utilises":   0,
            "credits_restants":   _ADMIN_CREDITS,
            "label_credits":      "Illimité",
            "agents_illimites":   True,
            "date_fin":           None,
            "prix_fcfa":          0,
            "operateur":          None,
            "numero_telephone":   None,
            # Rétrocompat
            "quota_jour":         99999,
            "requetes_utilisees": 0,
            "requetes_restantes": 99999,
        }

    from modules.pro.service_profil import get_or_create
    from modules.pro.service_credits import solde_utilisateur, CREDITS_PAR_PLAN, LABEL_CREDITS_PLAN

    profil, _ = await get_or_create(current_user.user_id, db)

    # Lire l'abonnement depuis les préférences du profil
    prefs = profil.preferences or {}
    plan_actif = prefs.get("plan", "gratuit")
    date_fin_str = prefs.get("abonnement_fin")
    statut = "actif"

    # Vérifier expiration
    if date_fin_str:
        try:
            date_fin = datetime.fromisoformat(date_fin_str)
            if datetime.utcnow() > date_fin:
                plan_actif = "gratuit"
                statut = "expire"
        except ValueError:
            pass

    plan_info = PLANS.get(plan_actif, PLANS["gratuit"])

    # Crédits IA (nouveau système tokens)
    try:
        solde = await solde_utilisateur(current_user.user_id, db)
    except Exception:
        solde = {
            "credits_alloues": CREDITS_PAR_PLAN.get(plan_actif, 500),
            "credits_utilises": 0,
            "credits_restants": CREDITS_PAR_PLAN.get(plan_actif, 500),
            "label_plan": LABEL_CREDITS_PLAN.get(plan_actif, "Gratuit"),
            "pct_utilise": 0,
            "renouvellement_le": None,
            "explication": "",
        }

    return {
        "plan":               plan_actif,
        "nom_plan":           plan_info["nom"],
        "statut":             statut,
        # Crédits IA (système tokens)
        "credits_alloues":    solde["credits_alloues"],
        "credits_utilises":   solde["credits_utilises"],
        "credits_restants":   solde["credits_restants"],
        "pct_utilise":        solde["pct_utilise"],
        "label_credits":      solde.get("label_plan", LABEL_CREDITS_PLAN.get(plan_actif, "")),
        "renouvellement_le":  solde.get("renouvellement_le"),
        "explication_credits": solde.get("explication", ""),
        "agents_illimites":   plan_info["agents_illimites"],
        "date_fin":           date_fin_str,
        "prix_fcfa":          plan_info["prix_fcfa"],
        "operateur":          prefs.get("operateur_paiement"),
        "numero_telephone":   prefs.get("numero_telephone"),
        # Rétrocompat frontend
        "quota_jour":         plan_info["quota_jour"],
        "requetes_utilisees": int(solde["credits_utilises"]),
        "requetes_restantes": int(solde["credits_restants"]),
    }


@router.post("/initier", summary="Initier un paiement Mobile Money")
async def initier_paiement(
    req: InitierPaiementRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Initie une demande de paiement Mobile Money.

    En mode simulation : retourne les instructions de paiement manuel.
    En mode production : déclenche l'API Mobile Money de l'opérateur.

    L'utilisateur reçoit :
    - Un numéro de référence à enregistrer
    - Les instructions pour valider le paiement sur son téléphone
    - Un délai de confirmation (15 minutes)
    """
    if req.plan not in PLANS or req.plan == "gratuit":
        raise HTTPException(status_code=400, detail="Plan invalide. Choisir : starter, pro, business")

    if req.operateur not in OPERATEURS:
        raise HTTPException(status_code=400, detail=f"Opérateur non supporté. Disponibles : {', '.join(OPERATEURS.keys())}")

    plan_info = PLANS[req.plan]
    reference = f"YKP-{uuid.uuid4().hex[:8].upper()}"
    operateur_info = OPERATEURS[req.operateur]

    # En production, ici on appellerait l'API de l'opérateur Mobile Money
    # Ex: Orange Money API (Cameroun) : POST /openapi/mm/v1/payments/...
    # Ex: MTN MoMo API : POST /collection/v1_0/requesttopay
    # Pour l'instant on génère les instructions manuelles

    instructions = _generer_instructions_paiement(
        operateur=req.operateur,
        montant=plan_info["prix_fcfa"],
        reference=reference,
        numero=req.numero_telephone,
    )

    # Sauvegarder la demande en attente
    from modules.pro.service_profil import get_or_create
    profil, _ = await get_or_create(current_user.user_id, db)
    prefs = dict(profil.preferences or {})
    prefs["paiement_en_attente"] = {
        "reference": reference,
        "plan": req.plan,
        "operateur": req.operateur,
        "numero": req.numero_telephone,
        "montant": plan_info["prix_fcfa"],
        "date_initiation": datetime.utcnow().isoformat(),
        "expire_a": (datetime.utcnow() + timedelta(minutes=30)).isoformat(),
    }
    profil.preferences = prefs
    await db.commit()

    logger.info(f"[Abonnement] Paiement initié: user={current_user.user_id} plan={req.plan} ref={reference}")

    return {
        "reference":         reference,
        "plan":              req.plan,
        "montant_fcfa":      plan_info["prix_fcfa"],
        "operateur":         operateur_info["label"],
        "numero_telephone":  req.numero_telephone,
        "instructions":      instructions,
        "expire_dans":       "30 minutes",
        "prochaine_etape":   f"Après paiement, utilisez POST /api/v1/pro/abonnement/confirmer avec votre référence : {reference}",
    }


@router.post("/confirmer", summary="Confirmer le paiement après validation")
async def confirmer_paiement(
    req: ConfirmerPaiementRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Confirme un paiement Mobile Money après que l'utilisateur a validé sur son téléphone.
    En mode simulation : active l'abonnement immédiatement.
    En mode production : vérifie la transaction auprès de l'opérateur.
    """
    from modules.pro.service_profil import get_or_create
    from config.settings import settings

    profil, _ = await get_or_create(current_user.user_id, db)
    prefs = dict(profil.preferences or {})
    attente = prefs.get("paiement_en_attente", {})

    # Vérifier que la référence correspond
    if not attente or attente.get("reference") != req.reference_paiement:
        raise HTTPException(
            status_code=400,
            detail=f"Référence de paiement invalide. Référence attendue : {attente.get('reference', 'Aucune demande en attente')}",
        )

    # Vérifier expiration (30 min)
    expire_str = attente.get("expire_a")
    if expire_str:
        try:
            if datetime.utcnow() > datetime.fromisoformat(expire_str):
                raise HTTPException(status_code=400, detail="La demande de paiement a expiré. Réinitiez le processus.")
        except ValueError:
            pass

    plan = attente["plan"]
    plan_info = PLANS.get(plan, PLANS["gratuit"])

    # En mode simulation : on fait confiance à l'utilisateur (à valider manuellement par admin)
    # En mode prod : vérifier l'API de l'opérateur avec le transaction_id

    # Activer l'abonnement
    date_debut = datetime.utcnow()
    date_fin = date_debut + timedelta(days=plan_info["duree_jours"])

    prefs["plan"] = plan
    prefs["abonnement_debut"] = date_debut.isoformat()
    prefs["abonnement_fin"] = date_fin.isoformat()
    prefs["operateur_paiement"] = attente.get("operateur")
    prefs["numero_telephone"] = attente.get("numero")
    prefs["derniere_reference"] = req.reference_paiement

    # Historique des paiements
    historique = prefs.get("historique_paiements", [])
    historique.append({
        "reference": req.reference_paiement,
        "plan": plan,
        "montant_fcfa": plan_info["prix_fcfa"],
        "operateur": attente.get("operateur"),
        "date": date_debut.isoformat(),
        "statut": "confirme",
        "transaction_id": req.transaction_id,
    })
    prefs["historique_paiements"] = historique[-20:]  # Garder les 20 derniers

    # Effacer la demande en attente
    prefs.pop("paiement_en_attente", None)
    profil.preferences = prefs
    await db.commit()

    # ── Synchroniser les crédits IA selon le nouveau plan ──────────────────
    try:
        from modules.pro.service_credits import synchroniser_plan
        await synchroniser_plan(current_user.user_id, plan, db)
    except Exception as e_credits:
        logger.warning(f"[Abonnement] Sync crédits échoué (non bloquant) : {e_credits}")

    logger.info(f"[Abonnement] Activé: user={current_user.user_id} plan={plan} ref={req.reference_paiement}")

    from modules.pro.service_credits import CREDITS_PAR_PLAN, LABEL_CREDITS_PLAN
    return {
        "succes":           True,
        "message":          f"Abonnement {plan_info['nom']} activé avec succès !",
        "plan":             plan,
        "date_debut":       date_debut.isoformat(),
        "date_fin":         date_fin.isoformat(),
        "credits_alloues":  CREDITS_PAR_PLAN.get(plan, 500),
        "label_credits":    LABEL_CREDITS_PLAN.get(plan, "500 crédits / mois"),
    }


@router.get("/packs-credits", summary="Liste des packs de recharge")
async def lister_packs_credits():
    """Retourne les packs de crédits disponibles à l'achat."""
    return {"packs": list(PACKS_CREDITS.values())}


@router.post("/initier-recharge", summary="Initier un achat de crédits supplémentaires")
async def initier_recharge_credits(
    req: InitierRechargeRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Initie un paiement Mobile Money pour acheter des crédits supplémentaires.
    Ces crédits s'ajoutent au quota mensuel sans changer de plan.
    """
    if req.pack_id not in PACKS_CREDITS:
        raise HTTPException(400, f"Pack invalide. Disponibles : {', '.join(PACKS_CREDITS.keys())}")
    if req.operateur not in OPERATEURS:
        raise HTTPException(400, f"Opérateur non supporté : {', '.join(OPERATEURS.keys())}")

    pack = PACKS_CREDITS[req.pack_id]
    reference = f"YKP-RC-{uuid.uuid4().hex[:8].upper()}"

    instructions = _generer_instructions_paiement(
        operateur=req.operateur,
        montant=pack["prix_fcfa"],
        reference=reference,
        numero=req.numero_telephone,
    )

    from modules.pro.service_profil import get_or_create
    profil, _ = await get_or_create(current_user.user_id, db)
    prefs = dict(profil.preferences or {})
    prefs["recharge_en_attente"] = {
        "reference":        reference,
        "pack_id":          req.pack_id,
        "credits":          pack["credits"],
        "operateur":        req.operateur,
        "numero":           req.numero_telephone,
        "montant":          pack["prix_fcfa"],
        "date_initiation":  datetime.utcnow().isoformat(),
        "expire_a":         (datetime.utcnow() + timedelta(hours=24)).isoformat(),
    }
    profil.preferences = prefs
    await db.commit()

    logger.info(f"[Recharge] Initié: user={current_user.user_id} pack={req.pack_id} ref={reference}")

    return {
        "reference":        reference,
        "pack_id":          req.pack_id,
        "pack_nom":         pack["nom"],
        "credits":          pack["credits"],
        "montant_fcfa":     pack["prix_fcfa"],
        "operateur":        OPERATEURS[req.operateur]["label"],
        "instructions":     instructions,
        "expire_dans":      "24 heures",
    }


@router.post("/confirmer-recharge", summary="Confirmer l'achat de crédits après paiement")
async def confirmer_recharge_credits(
    req: ConfirmerPaiementRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Confirme l'achat de crédits supplémentaires.
    Ajoute les crédits directement au solde de l'utilisateur.
    """
    from modules.pro.service_profil import get_or_create

    profil, _ = await get_or_create(current_user.user_id, db)
    prefs = dict(profil.preferences or {})
    attente = prefs.get("recharge_en_attente", {})

    if not attente or attente.get("reference") != req.reference_paiement:
        raise HTTPException(400, "Référence de recharge invalide ou expirée.")

    expire_a = datetime.fromisoformat(attente["expire_a"])
    if datetime.utcnow() > expire_a:
        raise HTTPException(400, "Cette référence de recharge a expiré (24h). Recommencez.")

    credits_a_ajouter = attente["credits"]
    pack_id = attente["pack_id"]
    pack = PACKS_CREDITS.get(pack_id, {})

    # Créditer le solde
    try:
        from modules.pro.service_credits import get_ou_creer_credits
        from core.database import async_session_maker
        async with async_session_maker() as fresh_db:
            credit = await get_ou_creer_credits(current_user.user_id, fresh_db)
            credit.credits_alloues += credits_a_ajouter
            credit.mise_a_jour = datetime.utcnow()
            await fresh_db.commit()
    except Exception as e_cred:
        logger.error(f"[Recharge] Crédit échoué user={current_user.user_id}: {e_cred}")
        raise HTTPException(500, "Erreur lors de l'ajout des crédits.")

    # Historique
    historique = prefs.get("historique_recharges", [])
    historique.insert(0, {
        "reference":   req.reference_paiement,
        "pack_nom":    pack.get("nom", pack_id),
        "credits":     credits_a_ajouter,
        "montant":     attente["montant"],
        "date":        datetime.utcnow().strftime("%d/%m/%Y %H:%M"),
    })
    prefs["historique_recharges"] = historique[:20]
    prefs.pop("recharge_en_attente", None)
    profil.preferences = prefs
    await db.commit()

    logger.info(f"[Recharge] Confirmée: user={current_user.user_id} pack={pack_id} +{credits_a_ajouter} crédits")

    return {
        "succes":           True,
        "message":          f"{credits_a_ajouter:,} crédits ajoutés à votre solde !",
        "credits_ajoutes":  credits_a_ajouter,
        "pack_nom":         pack.get("nom", pack_id),
    }


@router.get("/historique", summary="Historique de mes paiements")
async def historique_paiements(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retourne l'historique des paiements et abonnements passés."""
    from modules.pro.service_profil import get_or_create
    profil, _ = await get_or_create(current_user.user_id, db)
    prefs = profil.preferences or {}
    return {
        "historique": prefs.get("historique_paiements", []),
        "plan_actuel": prefs.get("plan", "gratuit"),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generer_instructions_paiement(operateur: str, montant: int, reference: str, numero: str) -> dict:
    """Génère les instructions spécifiques à chaque opérateur Mobile Money."""
    montant_str = f"{montant:,}".replace(",", " ")

    instructions_base = {
        "orange_money": {
            "ussd": f"#150#",
            "menu": f"1 → Paiement → Paiement marchand → Numéro marchand : 690000001 → Montant : {montant} → Référence : {reference}",
            "sms": f"Envoyez SMS au 690000001 : PAYER {montant} {reference}",
            "app": "Application Orange Money → Payer un marchand → Code : YKP → Réf : " + reference,
        },
        "mtn_momo": {
            "ussd": "#126#",
            "menu": f"1 → MoMoPay → Numéro marchand : 677000001 → Montant : {montant} → Réf : {reference}",
            "app": "Application MTN MoMo → Payer → Merchant code : YUKPO → Réf : " + reference,
        },
        "wave": {
            "app": f"Application Wave → Envoyer → Numéro : +237600000001 → Montant : {montant} FCFA → Note : {reference}",
            "qr": "Scanner le QR code YukpoPro dans l'application Wave",
        },
        "moov_money": {
            "ussd": "#155#",
            "menu": f"Paiement → Numéro marchand : 560000001 → {montant} FCFA → Réf : {reference}",
        },
        "airtel_money": {
            "ussd": "#777#",
            "menu": f"Paiements → Numéro : 770000001 → {montant} FCFA → Réf : {reference}",
        },
        "expressunion": {
            "agence": f"Rendez-vous en agence Express Union avec la référence {reference} — Montant : {montant_str} FCFA",
            "app": f"Application Express Union → Transfert marchand → Réf : {reference}",
        },
    }

    ops = instructions_base.get(operateur, {})
    return {
        "operateur": operateur,
        "montant_fcfa": montant,
        "reference": reference,
        "etapes": ops,
        "important": f"Conservez votre référence {reference} pour confirmer le paiement sur YukpoPro.",
        "contact_support": "support@yukpopro.com ou WhatsApp : +237 6XX XXX XXX",
    }
