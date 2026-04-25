"""CinetPay — agrégateur multi-pays CEMAC/UEMOA.

Doc : https://docs.cinetpay.com
Endpoint : https://api-checkout.cinetpay.com/v2/payment
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

logger = logging.getLogger("yukpo_assurance.paiement.v2.cinetpay")

_STATUS_MAP = {
    "ACCEPTED": PaymentStatus.SUCCESS,
    "REFUSED": PaymentStatus.FAILED,
    "WAITING_FOR_CUSTOMER": PaymentStatus.PROCESSING,
    "CANCELLED": PaymentStatus.CANCELLED,
    "PENDING": PaymentStatus.PROCESSING,
}


class CinetPayProvider(PaymentProvider):
    name = ProviderName.CINETPAY

    def __init__(self) -> None:
        self.api_key = get_secret("CINETPAY_API_KEY", fallback_settings_attr="CINETPAY_API_KEY")
        self.site_id = get_secret("CINETPAY_SITE_ID", fallback_settings_attr="CINETPAY_SITE_ID")
        self.secret_key = get_secret("CINETPAY_SECRET_KEY")
        self.api_password = get_secret("CINETPAY_API_PASSWORD")
        self.base_url = "https://api-checkout.cinetpay.com/v2"
        self.callback_host = os.environ.get("CINETPAY_CALLBACK_HOST", "")

    def is_configured(self) -> bool:
        return bool(self.api_key and self.site_id)

    async def initiate(self, request: PaymentRequest) -> PaymentResponse:
        if not self.is_configured():
            raise ProviderUnavailable("CinetPay non configuré")

        notify_url = request.notify_url or (
            f"{self.callback_host}/paiement/v2/webhook/cinetpay" if self.callback_host else ""
        )
        payload = {
            "apikey": self.api_key,
            "site_id": self.site_id,
            "transaction_id": request.reference,
            "amount": int(request.amount),
            "currency": request.currency,
            "description": (request.description or "YukpoPro")[:120],
            "notify_url": notify_url,
            "return_url": request.return_url or "",
            "channels": "ALL",
            "customer_phone_number": request.customer_phone,
            "customer_email": request.customer_email or "",
            "customer_name": request.customer_name or "",
            "customer_surname": "",
            "lang": "FR",
        }
        async with httpx.AsyncClient(timeout=30.0) as cli:
            r = await cli.post(f"{self.base_url}/payment", json=payload)

        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text[:300]}

        if r.status_code != 200 or data.get("code") != "201":
            logger.error("CinetPay init KO %s: %s", r.status_code, str(data)[:200])
            return PaymentResponse(
                reference=request.reference,
                provider=self.name,
                status=PaymentStatus.FAILED,
                error_message=data.get("message", f"HTTP {r.status_code}"),
                raw_provider_response=data,
            )

        d = data.get("data", {})
        return PaymentResponse(
            reference=request.reference,
            provider=self.name,
            status=PaymentStatus.INITIATED,
            provider_reference=d.get("payment_token"),
            payment_url=d.get("payment_url"),
            raw_provider_response=data,
        )

    async def check_status(self, provider_reference: str) -> PaymentStatus:
        if not self.is_configured():
            return PaymentStatus.PENDING
        try:
            async with httpx.AsyncClient(timeout=20.0) as cli:
                r = await cli.post(
                    f"{self.base_url}/payment/check",
                    json={
                        "apikey": self.api_key,
                        "site_id": self.site_id,
                        "transaction_id": provider_reference,
                    },
                )
                data = r.json()
                status = data.get("data", {}).get("status", "").upper()
                return _STATUS_MAP.get(status, PaymentStatus.PENDING)
        except Exception as exc:
            logger.warning("CinetPay check_status erreur: %s", exc)
            return PaymentStatus.PENDING

    async def parse_webhook(
        self, body: bytes, headers: dict[str, str]
    ) -> Optional[WebhookEvent]:
        try:
            data = json.loads(body) if body.strip().startswith(b"{") else dict(
                kv.split("=", 1) for kv in body.decode().split("&") if "=" in kv
            )
        except Exception:
            return None

        if self.secret_key:
            token_payload = (
                f"{data.get('cpm_site_id','')}{data.get('cpm_trans_id','')}"
                f"{data.get('cpm_trans_date','')}{data.get('cpm_amount','')}"
                f"{data.get('cpm_currency','')}"
            )
            expected = hmac.new(self.secret_key.encode(), token_payload.encode(), hashlib.sha256).hexdigest()
            received = headers.get("x-token") or headers.get("X-Token", "")
            if received and not hmac.compare_digest(received, expected):
                logger.warning("CinetPay webhook signature invalide")
                return None

        status_raw = str(data.get("cpm_result", "") or data.get("status", "")).upper()
        status_map_legacy = {"00": PaymentStatus.SUCCESS, "600": PaymentStatus.FAILED}
        status = status_map_legacy.get(status_raw) or _STATUS_MAP.get(status_raw, PaymentStatus.PROCESSING)

        return WebhookEvent(
            provider=self.name,
            provider_reference=data.get("cpm_trans_id") or data.get("transaction_id", ""),
            status=status,
            amount=float(data.get("cpm_amount", 0) or data.get("amount", 0) or 0),
            currency=data.get("cpm_currency") or data.get("currency"),
            raw_payload=data,
            signature_valid=True,
        )
