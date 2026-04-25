"""Orange Money — Webpay API (CM/CI/SN/BF/ML).

Doc : https://developer.orange.com/apis/om-webpay
Flux :
  1. POST /oauth/v3/token — récupère access_token (OAuth2 client_credentials)
  2. POST /orange-money-webpay/{country}/v1/webpayment — crée la session
  3. Redirection client vers payment_url
  4. Webhook notif_url + GET /transactionstatus pour polling
"""
from __future__ import annotations

import base64
import hmac
import hashlib
import json
import logging
import os
from typing import Optional

import httpx

from modules.paiement.v2.models import (
    PaymentRequest,
    PaymentResponse,
    PaymentStatus,
    ProviderName,
    WebhookEvent,
)
from modules.paiement.v2.providers.base import PaymentProvider, ProviderUnavailable
from modules.paiement.v2.secrets_loader import get_secret

logger = logging.getLogger("yukpo_assurance.paiement.v2.orange_money")

_STATUS_MAP = {
    "SUCCESS": PaymentStatus.SUCCESS,
    "INITIATED": PaymentStatus.INITIATED,
    "PENDING": PaymentStatus.PROCESSING,
    "FAILED": PaymentStatus.FAILED,
    "EXPIRED": PaymentStatus.EXPIRED,
    "CANCELLED": PaymentStatus.CANCELLED,
}

_COUNTRY_PATH = {
    "CM": "cm", "CI": "ci", "SN": "sn", "BF": "bf", "ML": "ml",
}


class OrangeMoneyProvider(PaymentProvider):
    name = ProviderName.ORANGE_MONEY

    def __init__(self) -> None:
        self.client_id = os.environ.get("ORANGE_MONEY_CLIENT_ID", "") or os.environ.get("ORANGE_MONEY_API_KEY", "")
        self.client_secret = os.environ.get("ORANGE_MONEY_CLIENT_SECRET", "") or os.environ.get("ORANGE_MONEY_API_SECRET", "")
        self.merchant_key = os.environ.get("ORANGE_MONEY_MERCHANT_KEY", "") or os.environ.get("ORANGE_MONEY_MERCHANT_ID", "")
        self.environment = os.environ.get("ORANGE_MONEY_ENVIRONMENT", "sandbox")
        self.webhook_secret = get_secret("ORANGE_MONEY_WEBHOOK_SECRET")
        self.callback_host = os.environ.get("ORANGE_MONEY_CALLBACK_HOST", "")

        self.base_url = "https://api.orange.com"

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.merchant_key)

    async def _get_token(self) -> str:
        creds = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        async with httpx.AsyncClient(timeout=20.0) as cli:
            r = await cli.post(
                f"{self.base_url}/oauth/v3/token",
                headers={
                    "Authorization": f"Basic {creds}",
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data="grant_type=client_credentials",
            )
            r.raise_for_status()
            return r.json()["access_token"]

    async def initiate(self, request: PaymentRequest) -> PaymentResponse:
        if not self.is_configured():
            raise ProviderUnavailable("Orange Money non configuré")

        country = (request.country_code or "CM").upper()
        country_path = _COUNTRY_PATH.get(country, "cm")
        token = await self._get_token()

        notif_url = request.notify_url or (
            f"{self.callback_host}/paiement/v2/webhook/orange_money" if self.callback_host else ""
        )
        payload = {
            "merchant_key": self.merchant_key,
            "currency": request.currency,
            "order_id": request.reference,
            "amount": int(request.amount),
            "return_url": request.return_url or "",
            "cancel_url": request.cancel_url or "",
            "notif_url": notif_url,
            "lang": "fr",
            "reference": request.reference,
        }
        async with httpx.AsyncClient(timeout=30.0) as cli:
            r = await cli.post(
                f"{self.base_url}/orange-money-webpay/{country_path}/v1/webpayment",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

        if r.status_code != 201 and r.status_code != 200:
            logger.error("Orange Money init KO %s: %s", r.status_code, r.text[:200])
            return PaymentResponse(
                reference=request.reference,
                provider=self.name,
                status=PaymentStatus.FAILED,
                error_message=f"HTTP {r.status_code}",
                raw_provider_response={"body": r.text[:500]},
            )

        data = r.json()
        return PaymentResponse(
            reference=request.reference,
            provider=self.name,
            status=PaymentStatus.INITIATED,
            provider_reference=data.get("pay_token") or data.get("notif_token"),
            payment_url=data.get("payment_url"),
            raw_provider_response=data,
        )

    async def check_status(self, provider_reference: str) -> PaymentStatus:
        if not self.is_configured() or not provider_reference:
            return PaymentStatus.PENDING
        try:
            token = await self._get_token()
            async with httpx.AsyncClient(timeout=20.0) as cli:
                r = await cli.post(
                    f"{self.base_url}/orange-money-webpay/cm/v1/transactionstatus",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    json={"pay_token": provider_reference},
                )
                r.raise_for_status()
                data = r.json()
                return _STATUS_MAP.get(str(data.get("status", "")).upper(), PaymentStatus.PENDING)
        except Exception as exc:
            logger.warning("Orange check_status erreur: %s", exc)
            return PaymentStatus.PENDING

    async def parse_webhook(
        self, body: bytes, headers: dict[str, str]
    ) -> Optional[WebhookEvent]:
        if self.webhook_secret:
            sig = headers.get("x-orange-signature") or headers.get("X-Orange-Signature", "")
            expected = hmac.new(self.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
            if sig and not hmac.compare_digest(sig, expected):
                logger.warning("Orange webhook signature invalide")
                return None
        try:
            data = json.loads(body)
        except Exception:
            return None
        return WebhookEvent(
            provider=self.name,
            provider_reference=data.get("pay_token") or data.get("txnid", ""),
            status=_STATUS_MAP.get(str(data.get("status", "")).upper(), PaymentStatus.PROCESSING),
            amount=float(data.get("amount", 0) or 0),
            currency=data.get("currency"),
            raw_payload=data,
            signature_valid=True,
        )
