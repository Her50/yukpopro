"""Campay — fintech 100% camerounaise (MTN MoMo + Orange Money agrégés).

Doc : https://documenter.getpostman.com/view/2391374/T1LV8PVA
Endpoint : https://demo.campay.net (sandbox) / https://www.campay.net (prod)

Avantage : un seul provider local couvre MTN+Orange CM avec une seule
intégration, idéal en fallback rapide quand MTN/Orange direct sont KO.
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

logger = logging.getLogger("yukpo_assurance.paiement.v2.campay")

_STATUS_MAP = {
    "SUCCESSFUL": PaymentStatus.SUCCESS,
    "PENDING": PaymentStatus.PROCESSING,
    "FAILED": PaymentStatus.FAILED,
    "CANCELLED": PaymentStatus.CANCELLED,
}


class CampayProvider(PaymentProvider):
    name = ProviderName.CAMPAY

    def __init__(self) -> None:
        self.app_username = os.environ.get("CAMPAY_USERNAME", "")
        self.app_password = os.environ.get("CAMPAY_PASSWORD", "")
        self.permanent_token = os.environ.get("CAMPAY_PERMANENT_TOKEN", "")
        env = os.environ.get("CAMPAY_ENV", "sandbox")
        self.base_url = "https://demo.campay.net/api" if env == "sandbox" else "https://www.campay.net/api"
        self.callback_host = os.environ.get("CAMPAY_CALLBACK_HOST", "")

    def is_configured(self) -> bool:
        return bool(self.permanent_token or (self.app_username and self.app_password))

    async def _get_token(self) -> str:
        if self.permanent_token:
            return self.permanent_token
        async with httpx.AsyncClient(timeout=20.0) as cli:
            r = await cli.post(
                f"{self.base_url}/token/",
                json={"username": self.app_username, "password": self.app_password},
            )
            r.raise_for_status()
            return r.json()["token"]

    async def initiate(self, request: PaymentRequest) -> PaymentResponse:
        if not self.is_configured():
            raise ProviderUnavailable("Campay non configuré")

        token = await self._get_token()
        phone = request.customer_phone.lstrip("+")
        payload = {
            "amount": str(int(request.amount)),
            "currency": request.currency,
            "from": phone,
            "description": (request.description or "YukpoPro")[:120],
            "external_reference": request.reference,
        }
        async with httpx.AsyncClient(timeout=30.0) as cli:
            r = await cli.post(
                f"{self.base_url}/collect/",
                headers={"Authorization": f"Token {token}", "Content-Type": "application/json"},
                json=payload,
            )
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text[:300]}

        if r.status_code != 200:
            return PaymentResponse(
                reference=request.reference, provider=self.name,
                status=PaymentStatus.FAILED,
                error_message=str(data)[:200],
                raw_provider_response=data,
            )

        return PaymentResponse(
            reference=request.reference, provider=self.name,
            status=PaymentStatus.INITIATED,
            provider_reference=data.get("reference"),
            ussd_instructions=f"Validez le paiement de {int(request.amount)} {request.currency} via la notification reçue sur {phone}.",
            raw_provider_response=data,
        )

    async def check_status(self, provider_reference: str) -> PaymentStatus:
        if not self.is_configured():
            return PaymentStatus.PENDING
        try:
            token = await self._get_token()
            async with httpx.AsyncClient(timeout=20.0) as cli:
                r = await cli.get(
                    f"{self.base_url}/transaction/{provider_reference}/",
                    headers={"Authorization": f"Token {token}"},
                )
                data = r.json()
                return _STATUS_MAP.get(data.get("status", "").upper(), PaymentStatus.PENDING)
        except Exception as exc:
            logger.warning("Campay check erreur: %s", exc)
            return PaymentStatus.PENDING

    async def parse_webhook(self, body: bytes, headers: dict[str, str]) -> Optional[WebhookEvent]:
        try:
            data = json.loads(body)
        except Exception:
            return None
        return WebhookEvent(
            provider=self.name,
            provider_reference=data.get("reference") or data.get("external_reference", ""),
            status=_STATUS_MAP.get(str(data.get("status", "")).upper(), PaymentStatus.PROCESSING),
            amount=float(data.get("amount", 0) or 0),
            currency=data.get("currency"),
            raw_payload=data,
            signature_valid=True,
        )
