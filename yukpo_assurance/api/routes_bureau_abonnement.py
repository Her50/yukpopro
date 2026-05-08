"""
Routes Abonnement YukpoSecrétariat — Gestion des plans et paiements Mobile Money.

Plans :
  - gratuit     : 0 FCFA         → 1 000 crédits/mois   (tous modules)
  - secretariat : 5 000 FCFA/mois → 20 000 crédits/mois (rédaction, OCR, audio, traduction, gestion, documents)
  - infographie : 5 000 FCFA/mois → 20 000 crédits/mois (infographie, gestion, documents)
  - complet     : 10 000 FCFA/mois → 50 000 crédits/mois (tous les modules)

Endpoints :
  GET    /api/v1/bureau/abonnement/             — Mon abonnement actif
  GET    /api/v1/bureau/abonnement/plans        — Tous les plans disponibles
  POST   /api/v1/bureau/abonnement/initier      — Initier un paiement Mobile Money
  POST   /api/v1/bureau/abonnement/confirmer    — Confirmer après paiement
  GET    /api/v1/bureau/abonnement/packs-credits — Packs de recharge
  POST   /api/v1/bureau/abonnement/initier-recharge    — Achat de crédits
  POST   /api/v1/bureau/abonnement/confirmer-recharge  — Confirmer recharge
  GET    /api/v1/bureau/abonnement/historique   — Historique des paiements
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
from modules.bureau.service_credits_bureau import (
    PLANS_BUREAU,
    PACKS_CREDITS_BUREAU,
    LABEL_CREDITS_PLAN,
    get_ou_creer_credits_bureau,
    solde_utilisateur_bureau,
    synchroniser_plan_bureau,
)

logger = logging.getLogger("yukpo_assurance.api.bureau_abonnement")

router = APIRouter()


async def get_db():
    async with async_session_maker() as session:
        yield session


# Opérateurs Mobile Money (identiques à YukpoPro)
OPERATEURS = {
    "orange_money":  {"label": "Orange Money",  "prefixes": ["69", "65", "66"]},
    "mtn_momo":      {"label": "MTN MoMo",       "prefixes": ["67", "68"]},
    "wave":          {"label": "Wave",            "prefixes": ["70", "76"]},
    "moov_money":    {"label": "Moov Money",      "prefixes": ["56"]},
    "airtel_money":  {"label": "Airtel Money",    "prefixes": ["77"]},
    "expressunion":  {"label": "Express Union",   "prefixes": ["93", "94"]},
}


# ── Modèles Pydantic ──────────────────────────────────────────────────────────

class InitierPaiementBureauRequest(BaseModel):
    plan:              str = Field(..., description="secretariat | infographie | complet")
    operateur:         str = Field(..., description="orange_money | mtn_momo | wave | ...")
    numero_telephone:  str = Field(..., min_length=8, max_length=15)
    pays:              str = Field("CM", description="Code pays ISO 2")


class ConfirmerPaiementBureauRequest(BaseModel):
    reference_paiement: str = Field(..., min_length=4)
    transaction_id:     Optional[str] = None


class InitierRechargeBureauRequest(BaseModel):
    pack_id:          str = Field(..., description="pack_bureau_2000 | pack_bureau_5000 | pack_bureau_15000 | pack_bureau_30000")
    operateur:        str = Field(..., description="orange_money | mtn_momo | wave | ...")
    numero_telephone: str = Field(..., min_length=8, max_length=15)
    pays:             str = Field("CM")


class InitierRechargeCustomRequest(BaseModel):
    montant_fcfa:     int = Field(..., ge=1000, description="Montant FCFA à recharger, minimum 1000")
    operateur:        str = Field(..., description="orange_money | mtn_momo | wave | ...")
    numero_telephone: str = Field(..., min_length=8, max_length=15)
    pays:             str = Field("CM")


ADMIN_ROLES = ("admin", "super_admin", "yukpo_owner")


# ══════════════════════════════════════════════════════════════════════════════
# Routes
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/plans", summary="Liste des plans YukpoSecrétariat")
async def lister_plans_bureau():
    """Retourne tous les plans bureau avec leurs caractéristiques et tarifs."""
    return {"plans": list(PLANS_BUREAU.values())}


@router.get("/", summary="Mon abonnement bureau actif")
async def mon_abonnement_bureau(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retourne le plan bureau actif, les crédits restants et la date d'expiration."""
    # Admins : accès complet sans abonnement
    if current_user.role in ADMIN_ROLES:
        try:
            await synchroniser_plan_bureau(current_user.user_id, "complet", db)
        except Exception as _e:
            logger.warning(f"[Bureau/Admin] sync plan erreur : {_e}")
        plan_info = PLANS_BUREAU["complet"]
        return {
            "plan":              "complet",
            "nom_plan":          "Admin — Accès Total",
            "statut":            "actif",
            "credits_alloues":   plan_info["credits_mois"],
            "credits_utilises":  0,
            "credits_restants":  plan_info["credits_mois"],
            "pct_utilise":       0,
            "label_credits":     plan_info["label_credits"],
            "modules_autorises": plan_info["modules"],
            "date_fin":          None,
            "prix_fcfa":         0,
            "operateur":         None,
            "numero_telephone":  None,
        }

    from modules.pro.service_profil import get_or_create
    profil, _ = await get_or_create(current_user.user_id, db)

    prefs = profil.preferences or {}
    plan_stocke = prefs.get("bureau_plan", "gratuit")
    date_fin_str = prefs.get("bureau_abonnement_fin")
    statut = "actif"

    if date_fin_str:
        try:
            date_fin = datetime.fromisoformat(date_fin_str)
            if datetime.utcnow() > date_fin:
                plan_stocke = "gratuit"
                statut = "expire"
        except ValueError:
            pass

    plan_info = PLANS_BUREAU.get(plan_stocke, PLANS_BUREAU["gratuit"])

    try:
        solde = await solde_utilisateur_bureau(current_user.user_id, db)
    except Exception:
        solde = {
            "credits_alloues":  plan_info["credits_mois"],
            "credits_utilises": 0,
            "credits_restants": plan_info["credits_mois"],
            "pct_utilise":      0,
            "label_credits":    plan_info["label_credits"],
            "renouvellement_le": None,
            "explication":      "",
        }

    return {
        "plan":                plan_stocke,
        "nom_plan":            plan_info["nom"],
        "statut":              statut,
        "credits_alloues":     solde["credits_alloues"],
        "credits_utilises":    solde["credits_utilises"],
        "credits_restants":    solde["credits_restants"],
        "pct_utilise":         solde["pct_utilise"],
        "label_credits":       solde.get("label_credits", plan_info["label_credits"]),
        "modules_autorises":   plan_info["modules"],
        "renouvellement_le":   solde.get("renouvellement_le"),
        "explication_credits": solde.get("explication", ""),
        "date_fin":            date_fin_str,
        "prix_fcfa":           plan_info["prix_fcfa"],
        "operateur":           prefs.get("bureau_operateur_paiement"),
        "numero_telephone":    prefs.get("bureau_numero_telephone"),
    }


@router.post("/initier", summary="Initier un paiement d'abonnement bureau")
async def initier_paiement_bureau(
    req: InitierPaiementBureauRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Initie une demande de paiement Mobile Money pour un plan YukpoSecrétariat."""
    if req.plan not in PLANS_BUREAU or req.plan == "gratuit":
        raise HTTPException(400, "Plan invalide. Choisir : secretariat, infographie, complet")

    if req.operateur not in OPERATEURS:
        raise HTTPException(400, f"Opérateur non supporté. Disponibles : {', '.join(OPERATEURS.keys())}")

    plan_info = PLANS_BUREAU[req.plan]
    reference = f"YKS-{uuid.uuid4().hex[:8].upper()}"
    operateur_info = OPERATEURS[req.operateur]

    instructions = _generer_instructions_paiement(
        operateur=req.operateur,
        montant=plan_info["prix_fcfa"],
        reference=reference,
        numero=req.numero_telephone,
    )

    from modules.pro.service_profil import get_or_create
    profil, _ = await get_or_create(current_user.user_id, db)
    prefs = dict(profil.preferences or {})
    prefs["bureau_paiement_en_attente"] = {
        "reference":       reference,
        "plan":            req.plan,
        "operateur":       req.operateur,
        "numero":          req.numero_telephone,
        "montant":         plan_info["prix_fcfa"],
        "date_initiation": datetime.utcnow().isoformat(),
        "expire_a":        (datetime.utcnow() + timedelta(minutes=30)).isoformat(),
    }
    profil.preferences = prefs
    await db.commit()

    logger.info(f"[Bureau/Abonnement] Initié : user={current_user.user_id} plan={req.plan} ref={reference}")

    return {
        "reference":        reference,
        "plan":             req.plan,
        "montant_fcfa":     plan_info["prix_fcfa"],
        "operateur":        operateur_info["label"],
        "numero_telephone": req.numero_telephone,
        "instructions":     instructions,
        "expire_dans":      "30 minutes",
        "prochaine_etape":  f"Après paiement : POST /api/v1/bureau/abonnement/confirmer avec la référence {reference}",
    }


@router.post("/confirmer", summary="Confirmer le paiement d'abonnement bureau")
async def confirmer_paiement_bureau(
    req: ConfirmerPaiementBureauRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirme un paiement Mobile Money et active le plan bureau."""
    from modules.pro.service_profil import get_or_create

    profil, _ = await get_or_create(current_user.user_id, db)
    prefs = dict(profil.preferences or {})
    attente = prefs.get("bureau_paiement_en_attente", {})

    if not attente or attente.get("reference") != req.reference_paiement:
        raise HTTPException(
            400,
            f"Référence invalide. Attendue : {attente.get('reference', 'aucune demande en attente')}",
        )

    expire_str = attente.get("expire_a")
    if expire_str:
        try:
            if datetime.utcnow() > datetime.fromisoformat(expire_str):
                raise HTTPException(400, "La demande de paiement a expiré. Réinitiez le processus.")
        except ValueError:
            pass

    plan = attente["plan"]
    plan_info = PLANS_BUREAU.get(plan, PLANS_BUREAU["gratuit"])

    date_debut = datetime.utcnow()
    date_fin = date_debut + timedelta(days=plan_info["duree_jours"] or 30)

    prefs["bureau_plan"] = plan
    prefs["bureau_abonnement_debut"] = date_debut.isoformat()
    prefs["bureau_abonnement_fin"] = date_fin.isoformat()
    prefs["bureau_operateur_paiement"] = attente.get("operateur")
    prefs["bureau_numero_telephone"] = attente.get("numero")
    prefs["bureau_derniere_reference"] = req.reference_paiement

    historique = prefs.get("bureau_historique_paiements", [])
    historique.insert(0, {
        "reference":      req.reference_paiement,
        "plan":           plan,
        "montant_fcfa":   plan_info["prix_fcfa"],
        "operateur":      attente.get("operateur"),
        "date":           date_debut.isoformat(),
        "statut":         "confirme",
        "transaction_id": req.transaction_id,
    })
    prefs["bureau_historique_paiements"] = historique[:20]

    prefs.pop("bureau_paiement_en_attente", None)
    profil.preferences = prefs
    await db.commit()

    # Synchroniser les crédits bureau
    try:
        async with async_session_maker() as fresh_db:
            await synchroniser_plan_bureau(current_user.user_id, plan, fresh_db)
    except Exception as e_credits:
        logger.warning(f"[Bureau/Abonnement] Sync crédits échoué : {e_credits}")

    logger.info(f"[Bureau/Abonnement] Activé : user={current_user.user_id} plan={plan} ref={req.reference_paiement}")

    return {
        "succes":          True,
        "message":         f"Abonnement {plan_info['nom']} activé avec succès !",
        "plan":            plan,
        "date_debut":      date_debut.isoformat(),
        "date_fin":        date_fin.isoformat(),
        "credits_alloues": plan_info["credits_mois"],
        "label_credits":   plan_info["label_credits"],
        "modules_autorises": plan_info["modules"],
    }


@router.get("/packs-credits", summary="Liste des packs de recharge bureau")
async def lister_packs_credits_bureau():
    """Retourne les packs de crédits bureau disponibles à l'achat."""
    return {"packs": list(PACKS_CREDITS_BUREAU.values())}


@router.post("/initier-recharge-custom", summary="Recharge avec montant libre (min 1000 FCFA)")
async def initier_recharge_custom(
    req: InitierRechargeCustomRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Mode pay-as-you-go : l'utilisateur saisit le montant qu'il veut recharger
    (minimum 1 000 FCFA). Tarif aligné sur YukpoPro : 0,6 FCFA = 1 crédit Yukpo
    (équivalent à 1 000 FCFA → ~1 667 crédits, 5 000 FCFA → ~8 333 crédits).
    """
    if req.operateur not in OPERATEURS:
        raise HTTPException(400, f"Opérateur non supporté : {', '.join(OPERATEURS.keys())}")
    if req.montant_fcfa < 1000:
        raise HTTPException(400, "Montant minimum : 1 000 FCFA")

    # Ratio YukpoPro : 0,6 FCFA / crédit (équivaut à 5/3 crédits par FCFA)
    FCFA_PAR_CREDIT = 0.6
    credits_a_creer = int(req.montant_fcfa / FCFA_PAR_CREDIT)
    reference = f"YKS-RC-{uuid.uuid4().hex[:8].upper()}"

    instructions = _generer_instructions_paiement(
        operateur=req.operateur,
        montant=req.montant_fcfa,
        reference=reference,
        numero=req.numero_telephone,
    )

    from modules.pro.service_profil import get_or_create
    profil, _ = await get_or_create(current_user.user_id, db)
    prefs = dict(profil.preferences or {})
    prefs["bureau_recharge_en_attente"] = {
        "reference":       reference,
        "pack_id":         f"custom_{req.montant_fcfa}",
        "credits":         credits_a_creer,
        "operateur":       req.operateur,
        "numero":          req.numero_telephone,
        "montant":         req.montant_fcfa,
        "date_initiation": datetime.utcnow().isoformat(),
        "expire_a":        (datetime.utcnow() + timedelta(hours=24)).isoformat(),
    }
    profil.preferences = prefs
    await db.commit()

    logger.info(
        f"[Bureau/Recharge-Custom] Initié : user={current_user.user_id} "
        f"montant={req.montant_fcfa} FCFA = {credits_a_creer} crédits ref={reference}"
    )

    return {
        "reference":     reference,
        "montant_fcfa":  req.montant_fcfa,
        "credits":       credits_a_creer,
        "pack_nom":      f"Recharge {req.montant_fcfa:,} FCFA".replace(",", " "),
        "operateur":     OPERATEURS[req.operateur]["label"],
        "instructions":  instructions,
        "expire_dans":   "24 heures",
    }


@router.post("/initier-recharge", summary="Initier un achat de crédits bureau (pack préréglé)")
async def initier_recharge_credits_bureau(
    req: InitierRechargeBureauRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Initie un paiement Mobile Money pour acheter des crédits supplémentaires."""
    if req.pack_id not in PACKS_CREDITS_BUREAU:
        raise HTTPException(400, f"Pack invalide. Disponibles : {', '.join(PACKS_CREDITS_BUREAU.keys())}")
    if req.operateur not in OPERATEURS:
        raise HTTPException(400, f"Opérateur non supporté : {', '.join(OPERATEURS.keys())}")

    pack = PACKS_CREDITS_BUREAU[req.pack_id]
    reference = f"YKS-RC-{uuid.uuid4().hex[:8].upper()}"

    instructions = _generer_instructions_paiement(
        operateur=req.operateur,
        montant=pack["prix_fcfa"],
        reference=reference,
        numero=req.numero_telephone,
    )

    from modules.pro.service_profil import get_or_create
    profil, _ = await get_or_create(current_user.user_id, db)
    prefs = dict(profil.preferences or {})
    prefs["bureau_recharge_en_attente"] = {
        "reference":       reference,
        "pack_id":         req.pack_id,
        "credits":         pack["credits"],
        "operateur":       req.operateur,
        "numero":          req.numero_telephone,
        "montant":         pack["prix_fcfa"],
        "date_initiation": datetime.utcnow().isoformat(),
        "expire_a":        (datetime.utcnow() + timedelta(hours=24)).isoformat(),
    }
    profil.preferences = prefs
    await db.commit()

    logger.info(f"[Bureau/Recharge] Initié : user={current_user.user_id} pack={req.pack_id} ref={reference}")

    return {
        "reference":    reference,
        "pack_id":      req.pack_id,
        "pack_nom":     pack["nom"],
        "credits":      pack["credits"],
        "montant_fcfa": pack["prix_fcfa"],
        "operateur":    OPERATEURS[req.operateur]["label"],
        "instructions": instructions,
        "expire_dans":  "24 heures",
    }


@router.post("/confirmer-recharge", summary="Confirmer l'achat de crédits bureau")
async def confirmer_recharge_credits_bureau(
    req: ConfirmerPaiementBureauRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirme l'achat de crédits supplémentaires bureau et les ajoute au solde."""
    from modules.pro.service_profil import get_or_create

    profil, _ = await get_or_create(current_user.user_id, db)
    prefs = dict(profil.preferences or {})
    attente = prefs.get("bureau_recharge_en_attente", {})

    if not attente or attente.get("reference") != req.reference_paiement:
        raise HTTPException(400, "Référence de recharge invalide ou expirée.")

    try:
        expire_a = datetime.fromisoformat(attente["expire_a"])
        if datetime.utcnow() > expire_a:
            raise HTTPException(400, "Cette référence de recharge a expiré (24h). Recommencez.")
    except (ValueError, KeyError):
        raise HTTPException(400, "Référence invalide.")

    credits_a_ajouter = attente["credits"]
    pack_id = attente["pack_id"]
    pack = PACKS_CREDITS_BUREAU.get(pack_id, {})

    try:
        async with async_session_maker() as fresh_db:
            credit = await get_ou_creer_credits_bureau(current_user.user_id, fresh_db)
            credit.credits_alloues += credits_a_ajouter
            credit.mise_a_jour = datetime.utcnow()
            await fresh_db.commit()
    except Exception as e_cred:
        logger.error(f"[Bureau/Recharge] Crédit échoué user={current_user.user_id} : {e_cred}")
        raise HTTPException(500, "Erreur lors de l'ajout des crédits.")

    historique = prefs.get("bureau_historique_recharges", [])
    historique.insert(0, {
        "reference": req.reference_paiement,
        "pack_nom":  pack.get("nom", pack_id),
        "credits":   credits_a_ajouter,
        "montant":   attente["montant"],
        "date":      datetime.utcnow().strftime("%d/%m/%Y %H:%M"),
    })
    prefs["bureau_historique_recharges"] = historique[:20]
    prefs.pop("bureau_recharge_en_attente", None)
    profil.preferences = prefs
    await db.commit()

    logger.info(
        f"[Bureau/Recharge] Confirmée : user={current_user.user_id} pack={pack_id} +{credits_a_ajouter} crédits"
    )

    return {
        "succes":          True,
        "message":         f"{credits_a_ajouter:,} crédits ajoutés à votre solde !",
        "credits_ajoutes": credits_a_ajouter,
        "pack_nom":        pack.get("nom", pack_id),
    }


@router.get("/wallet", summary="Wallet Bureau — solde + consommation détaillée")
async def wallet_bureau(
    jours: int = 30,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Dashboard wallet complet pour YukpoSecrétariat :
      - solde actuel + équivalent FCFA
      - top modules consommateurs sur N derniers jours
      - historique détaillé des consommations
      - série temporelle quotidienne
      - séparation LLM vs forfaits
    Aligné sur le wallet YukpoPro.
    """
    from datetime import timedelta
    from sqlalchemy import select, func, and_
    from core.database import ConsommationBureauDB
    from modules.bureau.service_credits_bureau import (
        solde_utilisateur_bureau, MULTIPLICATEUR_YUKPO,
    )

    jours = max(1, min(365, jours))
    since = datetime.utcnow() - timedelta(days=jours)
    FCFA_PAR_CREDIT = 0.6

    solde = await solde_utilisateur_bureau(current_user.user_id, db)

    # Historique (200 dernières lignes)
    rows = (await db.execute(
        select(ConsommationBureauDB)
        .where(and_(
            ConsommationBureauDB.user_id == current_user.user_id,
            ConsommationBureauDB.cree_le >= since,
        ))
        .order_by(ConsommationBureauDB.cree_le.desc())
        .limit(200)
    )).scalars().all()

    historique = [{
        "id":              r.id,
        "date":            r.cree_le.isoformat() if r.cree_le else None,
        "modele":          r.modele,
        "module":          r.module or "inconnu",
        "tokens_input":    r.tokens_input or 0,
        "tokens_output":   r.tokens_output or 0,
        "cout_fcfa":       round(r.cout_fcfa or 0.0, 2),
        "credits_debites": round(r.credits_debites or 0.0, 1),
    } for r in rows]

    # Top modules
    agg_module = (await db.execute(
        select(
            ConsommationBureauDB.module,
            func.sum(ConsommationBureauDB.credits_debites).label("credits"),
            func.count(ConsommationBureauDB.id).label("appels"),
            func.sum(ConsommationBureauDB.tokens_input + ConsommationBureauDB.tokens_output).label("tokens"),
        )
        .where(and_(
            ConsommationBureauDB.user_id == current_user.user_id,
            ConsommationBureauDB.cree_le >= since,
        ))
        .group_by(ConsommationBureauDB.module)
        .order_by(func.sum(ConsommationBureauDB.credits_debites).desc())
    )).all()

    top_modules = [{
        "module":  m or "inconnu",
        "credits": round(c or 0.0, 1),
        "appels":  int(a or 0),
        "tokens":  int(t or 0),
    } for (m, c, a, t) in agg_module]

    # Série quotidienne
    agg_jour = (await db.execute(
        select(
            func.date(ConsommationBureauDB.cree_le).label("jour"),
            func.sum(ConsommationBureauDB.credits_debites).label("credits"),
            func.count(ConsommationBureauDB.id).label("appels"),
        )
        .where(and_(
            ConsommationBureauDB.user_id == current_user.user_id,
            ConsommationBureauDB.cree_le >= since,
        ))
        .group_by(func.date(ConsommationBureauDB.cree_le))
        .order_by(func.date(ConsommationBureauDB.cree_le))
    )).all()

    serie_jour = [{
        "jour":    str(j),
        "credits": round(c or 0.0, 1),
        "appels":  int(a or 0),
    } for (j, c, a) in agg_jour]

    total_credits = sum(m["credits"] for m in top_modules)
    total_appels  = sum(m["appels"]  for m in top_modules)
    nb_llm        = sum(1 for r in rows if not (r.modele or "").startswith("forfait:"))
    nb_forfait    = len(rows) - nb_llm

    return {
        "solde":         solde,
        "periode_jours": jours,
        "ratio_fcfa_par_credit": FCFA_PAR_CREDIT,
        "totaux": {
            "credits_consommes": round(total_credits, 1),
            "appels":            total_appels,
            "valeur_fcfa_payee": round(total_credits * FCFA_PAR_CREDIT, 0),
            "nb_appels_llm":     nb_llm,
            "nb_forfaits":       nb_forfait,
        },
        "top_modules": top_modules,
        "serie_jour":  serie_jour,
        "historique":  historique,
    }


@router.get("/historique", summary="Historique de mes paiements bureau")
async def historique_paiements_bureau(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retourne l'historique des paiements et recharges bureau."""
    from modules.pro.service_profil import get_or_create
    profil, _ = await get_or_create(current_user.user_id, db)
    prefs = profil.preferences or {}
    return {
        "historique_abonnements": prefs.get("bureau_historique_paiements", []),
        "historique_recharges":   prefs.get("bureau_historique_recharges", []),
        "plan_actuel":            prefs.get("bureau_plan", "gratuit"),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generer_instructions_paiement(operateur: str, montant: int, reference: str, numero: str) -> dict:
    """Génère les instructions spécifiques à chaque opérateur Mobile Money."""
    montant_str = f"{montant:,}".replace(",", " ")

    instructions_base = {
        "orange_money": {
            "ussd": "#150#",
            "menu": f"1 → Paiement → Paiement marchand → Numéro marchand : 690000001 → Montant : {montant} → Référence : {reference}",
            "sms":  f"Envoyez SMS au 690000001 : PAYER {montant} {reference}",
            "app":  f"Application Orange Money → Payer un marchand → Code : YKS → Réf : {reference}",
        },
        "mtn_momo": {
            "ussd": "#126#",
            "menu": f"1 → MoMoPay → Numéro marchand : 677000001 → Montant : {montant} → Réf : {reference}",
            "app":  f"Application MTN MoMo → Payer → Merchant code : YUKPOSEC → Réf : {reference}",
        },
        "wave": {
            "app": f"Application Wave → Envoyer → Numéro : +237600000001 → Montant : {montant} FCFA → Note : {reference}",
            "qr":  "Scanner le QR code YukpoSecrétariat dans l'application Wave",
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
            "app":    f"Application Express Union → Transfert marchand → Réf : {reference}",
        },
    }

    ops = instructions_base.get(operateur, {})
    return {
        "operateur":       operateur,
        "montant_fcfa":    montant,
        "reference":       reference,
        "etapes":          ops,
        "important":       f"Conservez votre référence {reference} pour confirmer le paiement sur YukpoSecrétariat.",
        "contact_support": "support@yukpo.com ou WhatsApp : +237 6XX XXX XXX",
    }
