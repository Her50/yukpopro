"""Flutterwave — Pan-African + International.

Doc : https://developer.flutterwave.com/reference/charges
Endpoint : https://api.flutterwave.com/v3/payments
"""
from __future__ import annotations

import hashlib
import hmac
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

logger = logging.getLogger("yukpo_assurance.paiement.v2.flutterwave")

_STATUS_MAP = {
    "successful": PaymentStatus.SUCCESS,
    "pending": PaymentStatus.PROCESSING,
    "failed": PaymentStatus.FAILED,
    "cancelled": PaymentStatus.CANCELLED,
}


class FlutterwaveProvider(PaymentProvider):
    name = ProviderName.FLUTTERWAVE

    def __init__(self) -> None:
        self.secret_key = get_secret("FLUTTERWAVE_SECRET_KEY")
        self.public_key = get_secret("FLUTTERWAVE_PUBLIC_KEY")
        self.webhook_hash = os.environ.get("FLUTTERWAVE_WEBHOOK_HASH", "")
        self.base_url = "https://api.flutterwave.com/v3"
        self.callback_host = os.environ.get("FLUTTERWAVE_CALLBACK_HOST", "")

    def is_configured(self) -> bool:
        return bool(self.secret_key)

    async def initiate(self, request: PaymentRequest) -> PaymentResponse:
        if not self.is_configured():
            raise ProviderUnavailable("Flutterwave non configuré")

        payload = {
            "tx_ref": request.reference,
            "amount": request.amount,
            "currency": request.currency,
            "redirect_url": request.return_url or "",
            "customer": {
                "email": request.customer_email or "noreply@yukpopro.com",
                "phonenumber": request.customer_phone,
                "name": request.customer_name or "Client YukpoPro",
            },
            "customizations": {
                "title": "YukpoPro",
                "description": request.description or "Paiement YukpoPro",
            },
            "meta": {**request.metadata, "country": request.country_code},
        }
        async with httpx.AsyncClient(timeout=30.0) as cli:
            r = await cli.post(
                f"{self.base_url}/payments",
                headers={"Authorization": f"Bearer {self.secret_key}", "Content-Type": "application/json"},
                json=payload,
            )

        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text[:300]}

        if r.status_code != 200 or data.get("status") != "success":
            logger.error("Flutterwave init KO: %s", str(data)[:200])
            return PaymentResponse(
                reference=request.reference, provider=self.name,
                status=PaymentStatus.FAILED,
                error_message=data.get("message", "init failed"),
                raw_provider_response=data,
            )

        link = data.get("data", {}).get("link")
        return PaymentResponse(
            reference=request.reference, provider=self.name,
            status=PaymentStatus.INITIATED,
            payment_url=link,
            provider_reference=request.reference,
            raw_provider_response=data,
        )

    async def check_status(self, provider_reference: str) -> PaymentStatus:
        if not self.is_configured():
            return PaymentStatus.PENDING
        try:
            async with httpx.AsyncClient(timeout=20.0) as cli:
                r = await cli.get(
                    f"{self.base_url}/transactions/verify_by_reference",
                    headers={"Authorization": f"Bearer {self.secret_key}"},
                    params={"tx_ref": provider_reference},
                )
                data = r.json()
                status = data.get("data", {}).get("status", "").lower()
                return _STATUS_MAP.get(status, PaymentStatus.PENDING)
        except Exception as exc:
            logger.warning("Flutterwave check erreur: %s", exc)
            return PaymentStatus.PENDING

    async def parse_webhook(self, body: bytes, headers: dict[str, str]) -> Optional[WebhookEvent]:
        if self.webhook_hash:
            received = headers.get("verif-hash") or headers.get("Verif-Hash", "")
            if not hmac.compare_digest(received, self.webhook_hash):
                logger.warning("Flutterwave webhook hash invalide")
                return None
        try:
            data = json.loads(body)
        except Exception:
            return None
        d = data.get("data", data)
        return WebhookEvent(
            provider=self.name,
            provider_reference=d.get("tx_ref") or d.get("reference", ""),
            status=_STATUS_MAP.get(str(d.get("status", "")).lower(), PaymentStatus.PROCESSING),
            amount=float(d.get("amount", 0) or 0),
            currency=d.get("currency"),
            raw_payload=data,
            signature_valid=True,
        )
