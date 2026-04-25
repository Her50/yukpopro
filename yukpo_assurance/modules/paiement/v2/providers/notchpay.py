"""NotchPay — agrégateur Afrique de l'Ouest (CM/CI/SN/NG).

Doc : https://docs.notchpay.co
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

import httpx

from modules.paiement.v2.models import (
    PaymentRequest, PaymentResponse, PaymentStatus, ProviderName, WebhookEvent,
)
from modules.paiement.v2.providers.base import PaymentProvider, ProviderUnavailable
from modules.paiement.v2.secrets_loader import get_secret

logger = logging.getLogger("yukpo_assurance.paiement.v2.notchpay")

_STATUS_MAP = {
    "complete": PaymentStatus.SUCCESS,
    "completed": PaymentStatus.SUCCESS,
    "pending": PaymentStatus.PROCESSING,
    "processing": PaymentStatus.PROCESSING,
    "failed": PaymentStatus.FAILED,
    "canceled": PaymentStatus.CANCELLED,
    "expired": PaymentStatus.EXPIRED,
}


class NotchPayProvider(PaymentProvider):
    name = ProviderName.NOTCHPAY

    def __init__(self) -> None:
        self.public_key = get_secret("NOTCHPAY_PUBLIC_KEY")
        self.secret_key = get_secret("NOTCHPAY_SECRET_KEY")
        self.base_url = "https://api.notchpay.co"
        self.callback_host = os.environ.get("NOTCHPAY_CALLBACK_HOST", "")

    def is_configured(self) -> bool:
        return bool(self.public_key)

    async def initiate(self, request: PaymentRequest) -> PaymentResponse:
        if not self.is_configured():
            raise ProviderUnavailable("NotchPay non configuré")

        callback = request.notify_url or (
            f"{self.callback_host}/paiement/v2/webhook/notchpay" if self.callback_host else ""
        )
        payload = {
            "amount": int(request.amount),
            "currency": request.currency,
            "customer": {
                "email": request.customer_email or "noreply@yukpopro.com",
                "phone": request.customer_phone,
                "name": request.customer_name or "Client YukpoPro",
            },
            "reference": request.reference,
            "description": request.description or "YukpoPro",
            "callback": callback,
        }
        async with httpx.AsyncClient(timeout=30.0) as cli:
            r = await cli.post(
                f"{self.base_url}/payments",
                headers={"Authorization": self.public_key, "Content-Type": "application/json"},
                json=payload,
            )
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text[:300]}

        if r.status_code not in (200, 201):
            return PaymentResponse(
                reference=request.reference, provider=self.name,
                status=PaymentStatus.FAILED,
                error_message=str(data)[:200],
                raw_provider_response=data,
            )

        tx = data.get("transaction", {}) or data
        return PaymentResponse(
            reference=request.reference, provider=self.name,
            status=PaymentStatus.INITIATED,
            provider_reference=tx.get("reference") or data.get("reference"),
            payment_url=data.get("authorization_url"),
            raw_provider_response=data,
        )

    async def check_status(self, provider_reference: str) -> PaymentStatus:
        if not self.is_configured():
            return PaymentStatus.PENDING
        try:
            async with httpx.AsyncClient(timeout=20.0) as cli:
                r = await cli.get(
                    f"{self.base_url}/payments/{provider_reference}",
                    headers={"Authorization": self.secret_key or self.public_key},
                )
                data = r.json()
                status = data.get("transaction", {}).get("status", "").lower()
                return _STATUS_MAP.get(status, PaymentStatus.PENDING)
        except Exception as exc:
            logger.warning("NotchPay check erreur: %s", exc)
            return PaymentStatus.PENDING

    async def parse_webhook(self, body: bytes, headers: dict[str, str]) -> Optional[WebhookEvent]:
        try:
            data = json.loads(body)
        except Exception:
            return None
        tx = data.get("data", {})
        return WebhookEvent(
            provider=self.name,
            provider_reference=tx.get("reference", ""),
            status=_STATUS_MAP.get(str(tx.get("status", "")).lower(), PaymentStatus.PROCESSING),
            amount=float(tx.get("amount", 0) or 0),
            currency=tx.get("currency"),
            raw_payload=data,
            signature_valid=True,
        )
