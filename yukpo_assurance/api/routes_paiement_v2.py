"""Routes paiement v2 — orchestrateur multi-provider unifié.

Endpoints :
  - POST /paiement/v2/initier         : initie un paiement (cascade auto)
  - GET  /paiement/v2/transactions/{ref} : statut + refresh provider
  - POST /paiement/v2/webhook/{provider} : webhook unifié par provider
  - GET  /paiement/v2/health          : diagnostic providers configurés
  - GET  /paiement/v2/providers       : liste providers dispos pour ce client
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, TokenData
from core.database import (
    get_db,
    PaymentTransactionV2DB,
    PaymentAttemptDB,
    PaymentWebhookEventDB,
)
from modules.paiement.v2 import (
    PaymentOrchestrator,
    PaymentRequest,
    PaymentMethod,
    ProviderName,
)
from modules.paiement.v2.country_router import build_cascade, detect_country_from_phone
from modules.paiement.v2.orchestrator import get_orchestrator

logger = logging.getLogger("yukpo_assurance.paiement.v2.routes")

router = APIRouter(prefix="/paiement/v2", tags=["Paiement v2 (multi-provider)"])


# ─── Schémas ────────────────────────────────────────────────────────────────

class InitiateSchema(BaseModel):
    type: str = Field(..., description="abonnement | recharge | service")
    plan_ou_pack: Optional[str] = None
    amount: float
    currency: str = "XAF"
    customer_phone: str
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    country_code: Optional[str] = None
    method: PaymentMethod = PaymentMethod.MOBILE_MONEY
    preferred_provider: Optional[ProviderName] = None
    return_url: Optional[str] = None
    cancel_url: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class InitiateResponseSchema(BaseModel):
    reference: str
    provider: str
    status: str
    payment_url: Optional[str] = None
    ussd_instructions: Optional[str] = None
    provider_reference: Optional[str] = None
    error_message: Optional[str] = None


# ─── Helpers ───────────────────────────────────────────────────────────────

def _generate_reference(user_id: int, phone: str) -> str:
    suffix = "".join(c for c in phone if c.isdigit())[-4:].zfill(4)
    return f"{datetime.utcnow().strftime('%y%m%d')}-{user_id:05d}-{suffix}"


_CREDITS_BY_PACK = {"pack_500": 500, "pack_2000": 2000, "pack_5000": 5000, "pack_15000": 15000}


async def _apply_payment_success(tx: PaymentTransactionV2DB, db: AsyncSession) -> None:
    """Crédite l'utilisateur après confirmation d'un paiement V2 (idempotent)."""
    meta = dict(tx.metadata_json or {})
    if meta.get("applied_at"):
        return
    if not tx.user_id:
        logger.warning("[Paiement V2] tx %s sans user_id, skip apply", tx.reference)
        return
    try:
        from modules.pro.service_profil import get_or_create
        from modules.pro.service_credits import get_ou_creer_credits, synchroniser_plan
        from datetime import timedelta

        if tx.type == "recharge":
            credits_ajout = _CREDITS_BY_PACK.get(tx.plan_ou_pack or "", 0)
            if credits_ajout > 0:
                credit = await get_ou_creer_credits(tx.user_id, db)
                credit.credits_alloues += credits_ajout
                credit.mise_a_jour = datetime.utcnow()
        elif tx.type == "abonnement" and tx.plan_ou_pack:
            profil, _ = await get_or_create(tx.user_id, db)
            prefs = dict(profil.preferences or {})
            debut = datetime.utcnow()
            prefs["plan"] = tx.plan_ou_pack
            prefs["abonnement_debut"] = debut.isoformat()
            prefs["abonnement_fin"] = (debut + timedelta(days=30)).isoformat()
            prefs["derniere_reference"] = tx.reference
            prefs["abonnement_statut"] = "actif"
            profil.preferences = prefs
            try:
                await synchroniser_plan(tx.user_id, tx.plan_ou_pack, db)
            except Exception as e:
                logger.warning("[Paiement V2] sync plan KO: %s", e)
        meta["applied_at"] = datetime.utcnow().isoformat()
        tx.metadata_json = meta
    except Exception as e:
        logger.exception("[Paiement V2] apply KO pour %s: %s", tx.reference, e)


# ─── Routes ────────────────────────────────────────────────────────────────

@router.post("/initier", response_model=InitiateResponseSchema)
async def initier_paiement_v2(
    payload: InitiateSchema,
    request: Request,
    user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    orch = get_orchestrator()
    reference = _generate_reference(user.user_id, payload.customer_phone)
    country = payload.country_code or detect_country_from_phone(payload.customer_phone) or "CM"

    pay_req = PaymentRequest(
        reference=reference,
        amount=payload.amount,
        currency=payload.currency,
        description=f"YukpoPro {payload.type} {payload.plan_ou_pack or ''}".strip(),
        customer_phone=payload.customer_phone,
        customer_email=payload.customer_email,
        customer_name=payload.customer_name,
        country_code=country,
        method=payload.method,
        preferred_provider=payload.preferred_provider,
        return_url=payload.return_url,
        cancel_url=payload.cancel_url,
        metadata={**payload.metadata, "user_id": user.user_id, "compagnie_id": user.compagnie_id},
    )

    # Création transaction (statut initial : pending)
    tx = PaymentTransactionV2DB(
        reference=reference,
        compagnie_id=user.compagnie_id,
        user_id=user.user_id,
        type=payload.type,
        plan_ou_pack=payload.plan_ou_pack,
        amount=payload.amount,
        currency=payload.currency,
        country_code=country,
        customer_phone=payload.customer_phone,
        customer_email=payload.customer_email,
        payment_method=payload.method.value,
        status="pending",
    )
    db.add(tx)
    await db.flush()

    # Cascade providers
    response = await orch.initiate(pay_req)

    # Enregistrer la tentative
    db.add(PaymentAttemptDB(
        transaction_id=tx.id,
        provider=response.provider.value,
        provider_reference=response.provider_reference,
        status=response.status.value,
        error_message=response.error_message,
        response_payload=response.raw_provider_response,
    ))

    # Mise à jour de la transaction
    tx.provider = response.provider.value
    tx.provider_reference = response.provider_reference
    tx.status = response.status.value
    tx.payment_url = response.payment_url
    tx.ussd_instructions = response.ussd_instructions
    tx.error_message = response.error_message
    tx.updated_at = datetime.utcnow()

    await db.commit()

    return InitiateResponseSchema(
        reference=reference,
        provider=response.provider.value,
        status=response.status.value,
        payment_url=response.payment_url,
        ussd_instructions=response.ussd_instructions,
        provider_reference=response.provider_reference,
        error_message=response.error_message,
    )


@router.get("/transactions/{reference}")
async def get_transaction(
    reference: str,
    user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PaymentTransactionV2DB).where(PaymentTransactionV2DB.reference == reference)
    )
    tx = result.scalar_one_or_none()
    if not tx:
        raise HTTPException(404, "Transaction introuvable")
    if tx.compagnie_id != user.compagnie_id:
        raise HTTPException(403, "Accès refusé")

    # Refresh statut depuis le provider si pas terminal
    if tx.status in ("pending", "initiated", "processing") and tx.provider and tx.provider_reference:
        orch = get_orchestrator()
        try:
            new_status = await orch.check_status(ProviderName(tx.provider), tx.provider_reference)
            if new_status.value != tx.status:
                tx.status = new_status.value
                tx.updated_at = datetime.utcnow()
                if new_status.value in ("success", "failed", "cancelled", "refunded"):
                    tx.completed_at = datetime.utcnow()
                if new_status.value == "success":
                    await _apply_payment_success(tx, db)
                await db.commit()
        except Exception as exc:
            logger.warning("Refresh statut KO pour %s: %s", reference, exc)

    return {
        "reference": tx.reference,
        "status": tx.status,
        "provider": tx.provider,
        "amount": float(tx.amount),
        "currency": tx.currency,
        "payment_url": tx.payment_url,
        "ussd_instructions": tx.ussd_instructions,
        "created_at": tx.created_at.isoformat() if tx.created_at else None,
        "completed_at": tx.completed_at.isoformat() if tx.completed_at else None,
    }


@router.post("/webhook/{provider}")
async def webhook_v2(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        provider_enum = ProviderName(provider)
    except ValueError:
        raise HTTPException(400, f"Provider inconnu: {provider}")

    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    orch = get_orchestrator()
    event = await orch.handle_webhook(provider_enum, body, headers)

    # Audit log systématique (même si signature invalide)
    db.add(PaymentWebhookEventDB(
        provider=provider,
        provider_reference=event.provider_reference if event else None,
        status_received=event.status.value if event else None,
        signature_valid=event.signature_valid if event else False,
        raw_payload={"headers_count": len(headers), "body_size": len(body)} if not event else event.raw_payload,
    ))

    if event is None:
        await db.commit()
        return {"received": True, "valid": False}

    # Mise à jour transaction associée
    if event.provider_reference:
        result = await db.execute(
            select(PaymentTransactionV2DB).where(
                (PaymentTransactionV2DB.provider_reference == event.provider_reference)
                | (PaymentTransactionV2DB.reference == event.provider_reference)
            )
        )
        tx = result.scalar_one_or_none()
        if tx:
            tx.status = event.status.value
            tx.updated_at = datetime.utcnow()
            if event.status.value in ("success", "failed", "cancelled", "refunded"):
                tx.completed_at = datetime.utcnow()
            if event.status.value == "success":
                await _apply_payment_success(tx, db)

    await db.commit()
    return {"received": True, "valid": True, "status": event.status.value}


@router.get("/health")
async def health_v2(user: TokenData = Depends(get_current_user)):
    """Diagnostic providers configurés (admin/superadmin recommandé)."""
    orch = get_orchestrator()
    return {"providers": orch.health_report()}


@router.get("/providers")
async def list_providers_for_client(
    phone: str,
    country: Optional[str] = None,
):
    """Liste ordonnée des providers pour un client (utilisée par le frontend pour
    afficher dynamiquement les options de paiement)."""
    orch = get_orchestrator()
    available = orch.available_providers()
    cascade = build_cascade(country_code=country, phone=phone, available_providers=available)
    return {
        "country": country or detect_country_from_phone(phone),
        "providers": [p.value for p in cascade if p != ProviderName.LEGACY_MANUAL],
        "fallback_manual": ProviderName.LEGACY_MANUAL.value,
    }
