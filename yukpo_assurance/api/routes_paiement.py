"""
Routes FastAPI — Paiement Mobile Money.
- POST /initier          : initier un paiement (CinetPay, MTN, Orange, Wave)
- GET  /statut/{ref}     : vérifier le statut d'une transaction
- GET  /transactions     : liste des transactions (admin)
- GET  /transactions/{id}: détail d'une transaction
- POST /callback/cinetpay: webhook CinetPay
- POST /callback/mtn     : webhook MTN MoMo
- POST /callback/orange  : webhook Orange Money
- GET  /stats            : statistiques (admin)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

logger = logging.getLogger("yukpo_assurance.paiement")
from pydantic import BaseModel
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db, CompagnieDB, TransactionPaiementDB
from core.auth import get_current_user, TokenData
from core.multitenancy import require_module
from modules.paiement.gestionnaire_paiement import (
    GestionnairePaiement,
    calculer_penalite_retard_cima,
)

router = APIRouter(prefix="/paiement", tags=["Paiement"])

# ─────────────────────────────────────────────────────────────
# Schémas
# ─────────────────────────────────────────────────────────────

class InitierPaiementSchema(BaseModel):
    montant: float
    devise: str = "XAF"
    operateur: str          # cinetpay | mtn_momo | orange_money | wave | simulation
    telephone_client: str
    nom_client: str = ""
    email_client: str = ""
    reference_police: str = ""
    description: str = "Prime d'assurance"
    url_retour: str = ""
    url_notification: str = ""


class VerifierStatutSchema(BaseModel):
    operateur: str


class PenaliteSchema(BaseModel):
    montant_prime: float
    jours_retard: int
    taux_legal: float = 0.065


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

async def _get_compagnie(compagnie_id: int, db: AsyncSession) -> Optional[CompagnieDB]:
    result = await db.execute(select(CompagnieDB).where(CompagnieDB.id == compagnie_id))
    return result.scalar_one_or_none()


def _verifier_signature_webhook(
    body: bytes,
    secret: str,
    signature_recue: Optional[str],
    algo: str = "sha256",
) -> bool:
    """Vérifie la signature HMAC d'un webhook en temps constant."""
    if not secret or not signature_recue:
        return False
    attendu = hmac.new(secret.encode(), body, getattr(hashlib, algo)).hexdigest()
    return hmac.compare_digest(attendu, signature_recue.lower().lstrip("sha256="))


def _build_config(compagnie: CompagnieDB) -> dict:
    return {
        "cinetpay_api_key": compagnie.cinetpay_api_key or "",
        "cinetpay_site_id": compagnie.cinetpay_site_id or "",
        "mtn_momo_api_key": compagnie.mtn_momo_api_key or "",
        "mtn_momo_subscription_key": compagnie.mtn_momo_subscription_key or "",
        "mtn_momo_environment": compagnie.mtn_momo_environment or "sandbox",
        "orange_money_client_id": compagnie.orange_money_client_id or "",
        "orange_money_client_secret": compagnie.orange_money_client_secret or "",
        "orange_money_merchant_key": compagnie.orange_money_merchant_key or "",
        "wave_api_key": compagnie.wave_api_key or "",
    }


# ─────────────────────────────────────────────────────────────
# Initier un paiement
# ─────────────────────────────────────────────────────────────

@router.post(
    "/initier",
    dependencies=[Depends(require_module("paiement"))],
)
async def initier_paiement(
    payload: InitierPaiementSchema,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    compagnie = await _get_compagnie(current_user.compagnie_id, db)
    if not compagnie:
        raise HTTPException(404, "Compagnie introuvable")

    # Référence interne unique
    reference_interne = f"PAY-{uuid.uuid4().hex[:12].upper()}"

    # Créer la transaction en base (état initial)
    transaction = TransactionPaiementDB(
        reference_interne=reference_interne,
        compagnie_id=current_user.compagnie_id,
        montant=payload.montant,
        devise=payload.devise,
        operateur=payload.operateur,
        telephone_client=payload.telephone_client,
        nom_client=payload.nom_client,
        email_client=payload.email_client,
        reference_police=payload.reference_police,
        description=payload.description,
        etat="en_attente",
        cree_par=current_user.username,
        cree_le=datetime.utcnow(),
    )
    db.add(transaction)
    await db.flush()

    config = _build_config(compagnie)
    gestionnaire = GestionnairePaiement(config)

    try:
        resultat = await gestionnaire.initier_paiement(
            montant=payload.montant,
            devise=payload.devise,
            operateur=payload.operateur,
            telephone_client=payload.telephone_client,
            nom_client=payload.nom_client,
            email_client=payload.email_client,
            reference_interne=reference_interne,
            description=payload.description,
            url_retour=payload.url_retour,
            url_notification=payload.url_notification,
        )
    except Exception as exc:
        transaction.etat = "echoue"
        transaction.message_erreur = str(exc)
        await db.commit()
        raise HTTPException(502, f"Erreur opérateur : {exc}")

    # Mise à jour avec la référence externe
    transaction.etat = "initie"
    transaction.reference_externe = resultat.get("reference_externe", "")
    transaction.url_paiement = resultat.get("url_paiement", "")
    await db.commit()

    return {
        "reference_interne": reference_interne,
        "etat": "initie",
        **resultat,
    }


# ─────────────────────────────────────────────────────────────
# Vérifier le statut
# ─────────────────────────────────────────────────────────────

@router.get(
    "/statut/{reference}",
    dependencies=[Depends(require_module("paiement"))],
)
async def verifier_statut(
    reference: str,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TransactionPaiementDB).where(
            TransactionPaiementDB.reference_interne == reference,
            TransactionPaiementDB.compagnie_id == current_user.compagnie_id,
        )
    )
    transaction = result.scalar_one_or_none()
    if not transaction:
        raise HTTPException(404, "Transaction introuvable")

    compagnie = await _get_compagnie(current_user.compagnie_id, db)
    config = _build_config(compagnie)
    gestionnaire = GestionnairePaiement(config)

    statut_externe = await gestionnaire.verifier_statut(
        reference=transaction.reference_externe or reference,
        operateur=transaction.operateur,
    )

    # Synchroniser si changement
    nouvel_etat = statut_externe.get("etat", transaction.etat)
    if nouvel_etat != transaction.etat:
        transaction.etat = nouvel_etat
        if nouvel_etat == "reussi":
            transaction.paye_le = datetime.utcnow()
        await db.commit()

    return {
        "reference_interne": transaction.reference_interne,
        "reference_externe": transaction.reference_externe,
        "etat": transaction.etat,
        "montant": transaction.montant,
        "devise": transaction.devise,
        "operateur": transaction.operateur,
        "reference_police": transaction.reference_police,
        "paye_le": transaction.paye_le,
        **statut_externe,
    }


# ─────────────────────────────────────────────────────────────
# Liste des transactions
# ─────────────────────────────────────────────────────────────

@router.get(
    "/transactions",
    dependencies=[Depends(require_module("paiement"))],
)
async def lister_transactions(
    etat: Optional[str] = None,
    operateur: Optional[str] = None,
    reference_police: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(TransactionPaiementDB).where(
        TransactionPaiementDB.compagnie_id == current_user.compagnie_id
    )
    if etat:
        query = query.where(TransactionPaiementDB.etat == etat)
    if operateur:
        query = query.where(TransactionPaiementDB.operateur == operateur)
    if reference_police:
        query = query.where(TransactionPaiementDB.reference_police == reference_police)

    query = query.order_by(desc(TransactionPaiementDB.cree_le)).offset(offset).limit(limit)
    result = await db.execute(query)
    transactions = result.scalars().all()

    return [
        {
            "id": t.id,
            "reference_interne": t.reference_interne,
            "reference_externe": t.reference_externe,
            "reference_police": t.reference_police,
            "montant": t.montant,
            "devise": t.devise,
            "operateur": t.operateur,
            "etat": t.etat,
            "telephone_client": t.telephone_client,
            "nom_client": t.nom_client,
            "cree_le": t.cree_le,
            "paye_le": t.paye_le,
        }
        for t in transactions
    ]


@router.get(
    "/transactions/{transaction_id}",
    dependencies=[Depends(require_module("paiement"))],
)
async def detail_transaction(
    transaction_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TransactionPaiementDB).where(
            TransactionPaiementDB.id == transaction_id,
            TransactionPaiementDB.compagnie_id == current_user.compagnie_id,
        )
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Transaction introuvable")

    return {
        "id": t.id,
        "reference_interne": t.reference_interne,
        "reference_externe": t.reference_externe,
        "reference_police": t.reference_police,
        "montant": t.montant,
        "devise": t.devise,
        "operateur": t.operateur,
        "etat": t.etat,
        "telephone_client": t.telephone_client,
        "nom_client": t.nom_client,
        "email_client": t.email_client,
        "description": t.description,
        "url_paiement": t.url_paiement,
        "message_erreur": t.message_erreur,
        "cree_par": t.cree_par,
        "cree_le": t.cree_le,
        "paye_le": t.paye_le,
    }


# ─────────────────────────────────────────────────────────────
# Callbacks opérateurs (pas d'authentification JWT)
# ─────────────────────────────────────────────────────────────

@router.post("/callback/cinetpay/{compagnie_id}")
async def callback_cinetpay(
    compagnie_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_cinetpay_signature: Optional[str] = Header(None),
):
    """Webhook CinetPay — confirmation de paiement."""
    body = await request.body()

    compagnie = await _get_compagnie(compagnie_id, db)
    if not compagnie:
        return {"status": "ignored"}

    # Vérification signature HMAC si la compagnie a configuré un secret webhook
    webhook_secret = getattr(compagnie, "webhook_secret", None) or ""
    if webhook_secret:
        if not _verifier_signature_webhook(body, webhook_secret, x_cinetpay_signature):
            logger.warning(f"[Webhook CinetPay] Signature invalide compagnie={compagnie_id}")
            raise HTTPException(status_code=403, detail="Signature webhook invalide")

    try:
        import json
        data = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Corps JSON invalide")

    # CinetPay : vérifier que le site_id correspond à la compagnie
    if compagnie.cinetpay_site_id and str(data.get("cpm_site_id", "")) != str(compagnie.cinetpay_site_id):
        logger.warning(f"[Webhook CinetPay] site_id mismatch compagnie={compagnie_id}")
        return {"status": "ignored"}

    config = _build_config(compagnie)
    gestionnaire = GestionnairePaiement(config)
    resultat = gestionnaire.traiter_callback_cinetpay(data)

    ref_interne = resultat.get("reference_interne")
    if ref_interne:
        r = await db.execute(
            select(TransactionPaiementDB).where(
                TransactionPaiementDB.reference_interne == ref_interne,
                TransactionPaiementDB.compagnie_id == compagnie_id,
            )
        )
        t = r.scalar_one_or_none()
        if t:
            t.etat = resultat.get("etat", t.etat)
            if t.etat == "reussi":
                t.paye_le = datetime.utcnow()
            await db.commit()

    return {"status": "ok"}


@router.post("/callback/mtn/{compagnie_id}")
async def callback_mtn(
    compagnie_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_reference_id: Optional[str] = Header(None),
    x_signature: Optional[str] = Header(None),
):
    """Webhook MTN MoMo — confirmation de paiement."""
    body = await request.body()

    compagnie = await _get_compagnie(compagnie_id, db)
    if not compagnie:
        return {"status": "ignored"}

    webhook_secret = getattr(compagnie, "webhook_secret", None) or ""
    if webhook_secret:
        if not _verifier_signature_webhook(body, webhook_secret, x_signature):
            logger.warning(f"[Webhook MTN] Signature invalide compagnie={compagnie_id}")
            raise HTTPException(status_code=403, detail="Signature webhook invalide")

    try:
        import json
        data = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Corps JSON invalide")

    config = _build_config(compagnie)
    gestionnaire = GestionnairePaiement(config)
    resultat = gestionnaire.traiter_callback_mtn(data)

    ref_externe = resultat.get("reference_externe") or x_reference_id
    if ref_externe:
        r = await db.execute(
            select(TransactionPaiementDB).where(
                TransactionPaiementDB.reference_externe == ref_externe,
                TransactionPaiementDB.compagnie_id == compagnie_id,
            )
        )
        t = r.scalar_one_or_none()
        if t:
            t.etat = resultat.get("etat", t.etat)
            if t.etat == "reussi":
                t.paye_le = datetime.utcnow()
            await db.commit()

    return {"status": "ok"}


@router.post("/callback/orange/{compagnie_id}")
async def callback_orange(
    compagnie_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_orange_signature: Optional[str] = Header(None),
):
    """Webhook Orange Money — confirmation de paiement."""
    body = await request.body()

    compagnie = await _get_compagnie(compagnie_id, db)
    if not compagnie:
        return {"status": "ignored"}

    webhook_secret = getattr(compagnie, "webhook_secret", None) or ""
    if webhook_secret:
        if not _verifier_signature_webhook(body, webhook_secret, x_orange_signature):
            logger.warning(f"[Webhook Orange] Signature invalide compagnie={compagnie_id}")
            raise HTTPException(status_code=403, detail="Signature webhook invalide")

    try:
        import json
        data = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Corps JSON invalide")

    ref_externe = data.get("pay_token") or data.get("transaction_id", "")

    if ref_externe:
        r = await db.execute(
            select(TransactionPaiementDB).where(
                TransactionPaiementDB.reference_externe == ref_externe,
                TransactionPaiementDB.compagnie_id == compagnie_id,
            )
        )
        t = r.scalar_one_or_none()
        if t:
            statut = data.get("status", "")
            if statut in ("SUCCESS", "SUCCESSFULL"):
                t.etat = "reussi"
                t.paye_le = datetime.utcnow()
            elif statut in ("FAILED", "CANCELLED"):
                t.etat = "echoue"
            await db.commit()

    return {"status": "ok"}


# ─────────────────────────────────────────────────────────────
# Statistiques
# ─────────────────────────────────────────────────────────────

@router.get(
    "/stats",
    dependencies=[Depends(require_module("paiement"))],
)
async def stats_paiements(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cid = current_user.compagnie_id

    # Montant total encaissé
    r_total = await db.execute(
        select(func.sum(TransactionPaiementDB.montant)).where(
            TransactionPaiementDB.compagnie_id == cid,
            TransactionPaiementDB.etat == "reussi",
        )
    )
    total_encaisse = r_total.scalar() or 0.0

    # Nb transactions par état
    r_etats = await db.execute(
        select(TransactionPaiementDB.etat, func.count())
        .where(TransactionPaiementDB.compagnie_id == cid)
        .group_by(TransactionPaiementDB.etat)
    )
    etats = {row[0]: row[1] for row in r_etats.all()}

    # Nb transactions par opérateur
    r_ops = await db.execute(
        select(TransactionPaiementDB.operateur, func.count(), func.sum(TransactionPaiementDB.montant))
        .where(
            TransactionPaiementDB.compagnie_id == cid,
            TransactionPaiementDB.etat == "reussi",
        )
        .group_by(TransactionPaiementDB.operateur)
    )
    par_operateur = [
        {"operateur": row[0], "nb_transactions": row[1], "total": row[2] or 0}
        for row in r_ops.all()
    ]

    return {
        "total_encaisse": total_encaisse,
        "par_etat": etats,
        "par_operateur": par_operateur,
    }


# ─────────────────────────────────────────────────────────────
# Pénalité CIMA Art. 12-ter
# ─────────────────────────────────────────────────────────────

@router.post(
    "/penalite-cima",
    dependencies=[Depends(require_module("paiement"))],
)
async def calculer_penalite(
    payload: PenaliteSchema,
    _: TokenData = Depends(get_current_user),
):
    """Calcule la pénalité de retard de règlement sinistre (Art. 12-ter Code CIMA)."""
    penalite = calculer_penalite_retard_cima(
        montant_prime=payload.montant_prime,
        jours_retard=payload.jours_retard,
        taux_legal=payload.taux_legal,
    )
    taux_effectif = payload.taux_legal * 1.5
    return {
        "montant_prime": payload.montant_prime,
        "jours_retard": payload.jours_retard,
        "taux_legal": payload.taux_legal,
        "taux_effectif_cima": taux_effectif,
        "penalite": penalite,
        "total_du": payload.montant_prime + penalite,
        "base_legale": "Art. 12-ter Code CIMA — taux légal × 1,5 × jours/365",
    }
