"""Orchestrateur central : sélectionne le meilleur provider et gère la cascade.

Cycle de vie :
  - PaymentOrchestrator() découvre tous les providers et leur état (configured ou non)
  - .initiate(request) : essaie cascade pays → 1er succès gagne, sinon fallback manuel
  - .check_status(provider, ref) : délègue au provider
  - .handle_webhook(provider, body, headers) : parse + valide signature
"""
from __future__ import annotations

import logging
from typing import Optional

from modules.paiement.v2.country_router import build_cascade
from modules.paiement.v2.models import (
    PaymentRequest, PaymentResponse, PaymentStatus, ProviderName, WebhookEvent,
)
from modules.paiement.v2.providers import (
    CampayProvider, CinetPayProvider, FlutterwaveProvider, LegacyManualProvider,
    MTNMoMoProvider, NotchPayProvider, OrangeMoneyProvider, PaymentProvider,
    PayPalProvider, ProviderUnavailable, StripeProvider,
)

logger = logging.getLogger("yukpo_assurance.paiement.v2.orchestrator")


class PaymentOrchestrator:
    """Singleton-friendly : peut être instancié une fois au boot via DI FastAPI."""

    def __init__(self) -> None:
        self.providers: dict[ProviderName, PaymentProvider] = {
            ProviderName.MTN_MOMO: MTNMoMoProvider(),
            ProviderName.ORANGE_MONEY: OrangeMoneyProvider(),
            ProviderName.CINETPAY: CinetPayProvider(),
            ProviderName.FLUTTERWAVE: FlutterwaveProvider(),
            ProviderName.STRIPE: StripeProvider(),
            ProviderName.PAYPAL: PayPalProvider(),
            ProviderName.NOTCHPAY: NotchPayProvider(),
            ProviderName.CAMPAY: CampayProvider(),
            ProviderName.LEGACY_MANUAL: LegacyManualProvider(),
        }

    def available_providers(self) -> set[ProviderName]:
        """Liste les providers configurés (clés présentes)."""
        return {name for name, p in self.providers.items() if p.is_configured()}

    def health_report(self) -> dict[str, bool]:
        """Diagnostic public : {provider_name: configured}. Pour /admin/payments/health."""
        return {name.value: p.is_configured() for name, p in self.providers.items()}

    async def initiate(self, request: PaymentRequest) -> PaymentResponse:
        """
        Tente la cascade de providers jusqu'au premier succès d'initiation.
        Le LegacyManualProvider est toujours en bout de cascade et réussit toujours.
        """
        available = self.available_providers()
        cascade = build_cascade(
            country_code=request.country_code,
            phone=request.customer_phone,
            preferred=request.preferred_provider,
            available_providers=available,
        )
        logger.info(
            "Cascade pour %s (pays=%s, tel=%s): %s",
            request.reference, request.country_code, request.customer_phone,
            [p.value for p in cascade],
        )

        last_error: Optional[str] = None
        for provider_name in cascade:
            provider = self.providers.get(provider_name)
            if provider is None:
                continue
            try:
                response = await provider.initiate(request)
                if response.status not in (PaymentStatus.FAILED, PaymentStatus.EXPIRED):
                    logger.info("Init OK via %s pour %s", provider_name.value, request.reference)
                    return response
                last_error = response.error_message
                logger.warning("Provider %s a refusé (%s) — fallback", provider_name.value, last_error)
            except ProviderUnavailable as exc:
                logger.debug("Provider %s indispo (%s) — skip", provider_name.value, exc)
                continue
            except Exception as exc:
                last_error = str(exc)
                logger.exception("Erreur inattendue %s: %s", provider_name.value, exc)
                continue

        # Garde-fou ultime — ne devrait jamais arriver car LegacyManualProvider est toujours dispo
        return PaymentResponse(
            reference=request.reference,
            provider=ProviderName.LEGACY_MANUAL,
            status=PaymentStatus.PENDING,
            error_message=last_error or "Aucun provider disponible",
        )

    async def check_status(
        self, provider: ProviderName, provider_reference: str
    ) -> PaymentStatus:
        p = self.providers.get(provider)
        if p is None:
            return PaymentStatus.PENDING
        return await p.check_status(provider_reference)

    async def handle_webhook(
        self, provider: ProviderName, body: bytes, headers: dict[str, str]
    ) -> Optional[WebhookEvent]:
        p = self.providers.get(provider)
        if p is None:
            return None
        return await p.parse_webhook(body, headers)


# Singleton lazy
_orchestrator: Optional[PaymentOrchestrator] = None


def get_orchestrator() -> PaymentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = PaymentOrchestrator()
    return _orchestrator
