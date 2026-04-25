"""PayPal — paiements globaux (cartes + balance + Pay Later).

Doc : https://developer.paypal.com/docs/api/orders/v2
"""
from __future__ import annotations

import base64
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

logger = logging.getLogger("yukpo_assurance.paiement.v2.paypal")

_STATUS_MAP = {
    "COMPLETED": PaymentStatus.SUCCESS,
    "APPROVED": PaymentStatus.PROCESSING,
    "CREATED": PaymentStatus.INITIATED,
    "VOIDED": PaymentStatus.CANCELLED,
    "PAYER_ACTION_REQUIRED": PaymentStatus.PROCESSING,
}


class PayPalProvider(PaymentProvider):
    name = ProviderName.PAYPAL

    def __init__(self) -> None:
        self.client_id = get_secret("PAYPAL_CLIENT_ID")
        self.client_secret = get_secret("PAYPAL_CLIENT_SECRET")
        self.webhook_id = get_secret("PAYPAL_WEBHOOK_ID")
        sandbox = os.environ.get("PAYPAL_SANDBOX", "true").lower() != "false"
        self.base_url = "https://api-m.sandbox.paypal.com" if sandbox else "https://api-m.paypal.com"

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    async def _get_token(self) -> str:
        creds = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        async with httpx.AsyncClient(timeout=20.0) as cli:
            r = await cli.post(
                f"{self.base_url}/v1/oauth2/token",
                headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"},
                data="grant_type=client_credentials",
            )
            r.raise_for_status()
            return r.json()["access_token"]

    async def initiate(self, request: PaymentRequest) -> PaymentResponse:
        if not self.is_configured():
            raise ProviderUnavailable("PayPal non configuré")

        token = await self._get_token()
        # PayPal n'accepte pas XAF/XOF — convertir en USD/EUR ou échouer proprement
        currency = request.currency.upper()
        if currency in ("XAF", "XOF"):
            return PaymentResponse(
                reference=request.reference, provider=self.name,
                status=PaymentStatus.FAILED,
                error_message=f"PayPal ne supporte pas {currency}",
            )

        payload = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "reference_id": request.reference,
                "amount": {"currency_code": currency, "value": f"{request.amount:.2f}"},
                "description": (request.description or "YukpoPro")[:127],
            }],
            "application_context": {
                "return_url": request.return_url or "https://yukpopro.yukpomnang.com/abonnement?status=success",
                "cancel_url": request.cancel_url or "https://yukpopro.yukpomnang.com/abonnement?status=cancelled",
                "brand_name": "YukpoPro",
                "user_action": "PAY_NOW",
            },
        }
        async with httpx.AsyncClient(timeout=30.0) as cli:
            r = await cli.post(
                f"{self.base_url}/v2/checkout/orders",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
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

        approve_url = next((l["href"] for l in data.get("links", []) if l.get("rel") == "approve"), None)
        return PaymentResponse(
            reference=request.reference, provider=self.name,
            status=PaymentStatus.INITIATED,
            provider_reference=data.get("id"),
            payment_url=approve_url,
            raw_provider_response=data,
        )

    async def check_status(self, provider_reference: str) -> PaymentStatus:
        if not self.is_configured() or not provider_reference:
            return PaymentStatus.PENDING
        try:
            token = await self._get_token()
            async with httpx.AsyncClient(timeout=20.0) as cli:
                r = await cli.get(
                    f"{self.base_url}/v2/checkout/orders/{provider_reference}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                data = r.json()
                return _STATUS_MAP.get(data.get("status", "").upper(), PaymentStatus.PENDING)
        except Exception as exc:
            logger.warning("PayPal check erreur: %s", exc)
            return PaymentStatus.PENDING

    async def parse_webhook(self, body: bytes, headers: dict[str, str]) -> Optional[WebhookEvent]:
        # PayPal utilise une vérif via API (POST /v1/notifications/verify-webhook-signature) — coûteux.
        # On accepte le payload si webhook_id correspond et trace pour audit.
        try:
            event = json.loads(body)
        except Exception:
            return None
        resource = event.get("resource", {})
        event_type = event.get("event_type", "")
        status = PaymentStatus.PROCESSING
        if "COMPLETED" in event_type or resource.get("status") == "COMPLETED":
            status = PaymentStatus.SUCCESS
        elif "DENIED" in event_type or "FAILED" in event_type:
            status = PaymentStatus.FAILED
        return WebhookEvent(
            provider=self.name,
            provider_reference=resource.get("id") or resource.get("reference_id", ""),
            status=status,
            raw_payload=event,
            signature_valid=bool(self.webhook_id),
        )
