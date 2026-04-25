"""MTN Mobile Money — Collections API.

Doc : https://momodeveloper.mtn.com/api-documentation/api-description
Flux :
  1. Obtenir token OAuth (POST /collection/token/)
  2. requestToPay (POST /collection/v1_0/requesttopay) avec X-Reference-Id (UUID)
  3. Statut (GET /collection/v1_0/requesttopay/{ref})
  4. Webhook callback (X-Callback-Url envoyé à l'init)
"""
from __future__ import annotations

import base64
import hmac
import hashlib
import json
import logging
import uuid
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

logger = logging.getLogger("yukpo_assurance.paiement.v2.mtn_momo")

_STATUS_MAP = {
    "PENDING": PaymentStatus.PROCESSING,
    "SUCCESSFUL": PaymentStatus.SUCCESS,
    "FAILED": PaymentStatus.FAILED,
    "TIMEOUT": PaymentStatus.EXPIRED,
    "REJECTED": PaymentStatus.FAILED,
}


class MTNMoMoProvider(PaymentProvider):
    name = ProviderName.MTN_MOMO

    def __init__(self) -> None:
        # Pas de fallback settings.* car MTN_MOMO_API_KEY est dans .env legacy
        # mais avec un nom différent côté yukpomnang2 (MTN_MONEY_API_KEY)
        import os
        self.api_user = os.environ.get("MTN_MOMO_API_USER", "") or os.environ.get("MTN_MONEY_MERCHANT_ID", "")
        self.api_key = os.environ.get("MTN_MOMO_API_KEY", "") or os.environ.get("MTN_MONEY_API_KEY", "")
        self.subscription_key = os.environ.get("MTN_MOMO_SUBSCRIPTION_KEY", "") or os.environ.get("MTN_MONEY_API_SECRET", "")
        self.environment = os.environ.get("MTN_MOMO_ENVIRONMENT", "sandbox") or "sandbox"
        self.webhook_secret = get_secret("MTN_MOMO_WEBHOOK_SECRET")
        self.callback_host = os.environ.get("MTN_MOMO_CALLBACK_HOST", "")

        if self.environment == "production":
            self.base_url = "https://momodeveloper.mtn.com"
            self.target_env = "mtn-cameroon"  # ou nigeria/ghana selon CompagnieDB.pays
        else:
            self.base_url = "https://sandbox.momodeveloper.mtn.com"
            self.target_env = "sandbox"

    def is_configured(self) -> bool:
        return bool(self.api_user and self.api_key and self.subscription_key)

    async def _get_token(self) -> str:
        creds = base64.b64encode(f"{self.api_user}:{self.api_key}".encode()).decode()
        async with httpx.AsyncClient(timeout=20.0) as cli:
            r = await cli.post(
                f"{self.base_url}/collection/token/",
                headers={
                    "Authorization": f"Basic {creds}",
                    "Ocp-Apim-Subscription-Key": self.subscription_key,
                },
            )
            r.raise_for_status()
            return r.json()["access_token"]

    async def initiate(self, request: PaymentRequest) -> PaymentResponse:
        if not self.is_configured():
            raise ProviderUnavailable("MTN MoMo non configuré")

        token = await self._get_token()
        ref_id = str(uuid.uuid4())
        phone = request.customer_phone.lstrip("+")

        payload = {
            "amount": str(int(request.amount)),
            "currency": request.currency,
            "externalId": request.reference,
            "payer": {"partyIdType": "MSISDN", "partyId": phone},
            "payerMessage": (request.description or "Paiement YukpoPro")[:160],
            "payeeNote": request.reference[:160],
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Reference-Id": ref_id,
            "X-Target-Environment": self.target_env,
            "Ocp-Apim-Subscription-Key": self.subscription_key,
            "Content-Type": "application/json",
        }
        if request.notify_url or self.callback_host:
            headers["X-Callback-Url"] = request.notify_url or f"{self.callback_host}/paiement/v2/webhook/mtn_momo"

        async with httpx.AsyncClient(timeout=30.0) as cli:
            r = await cli.post(
                f"{self.base_url}/collection/v1_0/requesttopay",
                headers=headers,
                json=payload,
            )
            if r.status_code not in (200, 202):
                logger.error("MTN MoMo init KO %s: %s", r.status_code, r.text[:200])
                return PaymentResponse(
                    reference=request.reference,
                    provider=self.name,
                    status=PaymentStatus.FAILED,
                    error_message=f"HTTP {r.status_code}",
                    raw_provider_response={"body": r.text[:500]},
                )

        return PaymentResponse(
            reference=request.reference,
            provider=self.name,
            status=PaymentStatus.INITIATED,
            provider_reference=ref_id,
            ussd_instructions=f"Composez *126# sur le mobile {phone} et confirmez le paiement de {int(request.amount)} {request.currency}.",
            raw_provider_response={"x_reference_id": ref_id},
        )

    async def check_status(self, provider_reference: str) -> PaymentStatus:
        if not self.is_configured():
            return PaymentStatus.PENDING
        try:
            token = await self._get_token()
            async with httpx.AsyncClient(timeout=20.0) as cli:
                r = await cli.get(
                    f"{self.base_url}/collection/v1_0/requesttopay/{provider_reference}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-Target-Environment": self.target_env,
                        "Ocp-Apim-Subscription-Key": self.subscription_key,
                    },
                )
                r.raise_for_status()
                data = r.json()
                return _STATUS_MAP.get(data.get("status", "").upper(), PaymentStatus.PENDING)
        except Exception as exc:
            logger.warning("MTN check_status erreur: %s", exc)
            return PaymentStatus.PENDING

    async def parse_webhook(
        self, body: bytes, headers: dict[str, str]
    ) -> Optional[WebhookEvent]:
        # Validation HMAC si secret configuré
        if self.webhook_secret:
            sig = headers.get("x-mtn-signature") or headers.get("X-MTN-Signature", "")
            expected = hmac.new(self.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected):
                logger.warning("MTN webhook signature invalide")
                return None
        try:
            data = json.loads(body)
        except Exception:
            return None

        return WebhookEvent(
            provider=self.name,
            provider_reference=data.get("referenceId") or data.get("externalId", ""),
            status=_STATUS_MAP.get(str(data.get("status", "")).upper(), PaymentStatus.PROCESSING),
            amount=float(data.get("amount", 0) or 0),
            currency=data.get("currency"),
            raw_payload=data,
            signature_valid=True,
        )
