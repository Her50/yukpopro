"""Stripe — cartes internationales (Visa/Mastercard/Amex/Apple/Google Pay).

Doc : https://stripe.com/docs/api/checkout/sessions
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Optional

import httpx

from modules.paiement.v2.models import (
    PaymentRequest, PaymentResponse, PaymentStatus, ProviderName, WebhookEvent,
)
from modules.paiement.v2.providers.base import PaymentProvider, ProviderUnavailable
from modules.paiement.v2.secrets_loader import get_secret

logger = logging.getLogger("yukpo_assurance.paiement.v2.stripe")

_STATUS_MAP = {
    "complete": PaymentStatus.SUCCESS,
    "open": PaymentStatus.PROCESSING,
    "expired": PaymentStatus.EXPIRED,
}


class StripeProvider(PaymentProvider):
    name = ProviderName.STRIPE

    def __init__(self) -> None:
        self.secret_key = get_secret("STRIPE_SECRET_KEY")
        self.publishable_key = get_secret("STRIPE_PUBLISHABLE_KEY")
        self.webhook_secret = get_secret("STRIPE_WEBHOOK_SECRET")
        self.base_url = "https://api.stripe.com/v1"
        self.callback_host = os.environ.get("STRIPE_CALLBACK_HOST", "")

    def is_configured(self) -> bool:
        return bool(self.secret_key)

    async def initiate(self, request: PaymentRequest) -> PaymentResponse:
        if not self.is_configured():
            raise ProviderUnavailable("Stripe non configuré")

        # Stripe attend les montants en plus petite unité (XAF: pas de cent, USD/EUR: cents)
        zero_decimal = {"XAF", "XOF", "JPY", "KRW", "VND"}
        currency = request.currency.upper()
        unit_amount = int(request.amount) if currency in zero_decimal else int(request.amount * 100)

        data = {
            "mode": "payment",
            "payment_method_types[]": "card",
            "line_items[0][price_data][currency]": currency.lower(),
            "line_items[0][price_data][product_data][name]": request.description or "YukpoPro",
            "line_items[0][price_data][unit_amount]": str(unit_amount),
            "line_items[0][quantity]": "1",
            "client_reference_id": request.reference,
            "success_url": request.return_url or "https://yukpopro.yukpomnang.com/abonnement?status=success",
            "cancel_url": request.cancel_url or "https://yukpopro.yukpomnang.com/abonnement?status=cancelled",
        }
        if request.customer_email:
            data["customer_email"] = request.customer_email

        async with httpx.AsyncClient(timeout=30.0) as cli:
            r = await cli.post(
                f"{self.base_url}/checkout/sessions",
                headers={"Authorization": f"Bearer {self.secret_key}"},
                data=data,
            )

        try:
            resp = r.json()
        except Exception:
            resp = {"raw": r.text[:300]}

        if r.status_code != 200:
            logger.error("Stripe init KO: %s", str(resp)[:200])
            return PaymentResponse(
                reference=request.reference, provider=self.name,
                status=PaymentStatus.FAILED,
                error_message=resp.get("error", {}).get("message", "init failed"),
                raw_provider_response=resp,
            )

        return PaymentResponse(
            reference=request.reference, provider=self.name,
            status=PaymentStatus.INITIATED,
            provider_reference=resp.get("id"),
            payment_url=resp.get("url"),
            raw_provider_response=resp,
        )

    async def check_status(self, provider_reference: str) -> PaymentStatus:
        if not self.is_configured():
            return PaymentStatus.PENDING
        try:
            async with httpx.AsyncClient(timeout=20.0) as cli:
                r = await cli.get(
                    f"{self.base_url}/checkout/sessions/{provider_reference}",
                    headers={"Authorization": f"Bearer {self.secret_key}"},
                )
                data = r.json()
                status = data.get("status", "").lower()
                if data.get("payment_status") == "paid":
                    return PaymentStatus.SUCCESS
                return _STATUS_MAP.get(status, PaymentStatus.PENDING)
        except Exception as exc:
            logger.warning("Stripe check erreur: %s", exc)
            return PaymentStatus.PENDING

    async def parse_webhook(self, body: bytes, headers: dict[str, str]) -> Optional[WebhookEvent]:
        sig_header = headers.get("stripe-signature") or headers.get("Stripe-Signature", "")
        if self.webhook_secret and sig_header:
            # Format: t=timestamp,v1=signature
            parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
            ts = parts.get("t", "")
            v1 = parts.get("v1", "")
            signed = f"{ts}.{body.decode()}".encode()
            expected = hmac.new(self.webhook_secret.encode(), signed, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(v1, expected):
                logger.warning("Stripe webhook signature invalide")
                return None
            # Tolérance temporelle 5 min
            try:
                if abs(int(time.time()) - int(ts)) > 300:
                    return None
            except Exception:
                pass

        try:
            event = json.loads(body)
        except Exception:
            return None
        obj = event.get("data", {}).get("object", {})
        event_type = event.get("type", "")

        status = PaymentStatus.PROCESSING
        if event_type == "checkout.session.completed" and obj.get("payment_status") == "paid":
            status = PaymentStatus.SUCCESS
        elif event_type in ("checkout.session.expired", "payment_intent.payment_failed"):
            status = PaymentStatus.FAILED

        return WebhookEvent(
            provider=self.name,
            provider_reference=obj.get("id") or obj.get("client_reference_id", ""),
            status=status,
            amount=float(obj.get("amount_total", 0) or 0) / 100,
            currency=(obj.get("currency") or "").upper(),
            raw_payload=event,
            signature_valid=True,
        )
