"""Interface abstraite pour tous les providers de paiement v2."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from modules.paiement.v2.models import (
    PaymentRequest,
    PaymentResponse,
    PaymentStatus,
    ProviderName,
    WebhookEvent,
)


class ProviderUnavailable(Exception):
    """Le provider est mal configuré ou indisponible (clés manquantes, API down)."""


class PaymentProvider(ABC):
    name: ProviderName

    @abstractmethod
    def is_configured(self) -> bool:
        """True si le provider a toutes les clés nécessaires pour fonctionner."""

    @abstractmethod
    async def initiate(self, request: PaymentRequest) -> PaymentResponse:
        """Initie un paiement. Lève ProviderUnavailable si non configuré."""

    @abstractmethod
    async def check_status(self, provider_reference: str) -> PaymentStatus:
        """Vérifie le statut d'une transaction côté provider."""

    @abstractmethod
    async def parse_webhook(
        self, body: bytes, headers: dict[str, str]
    ) -> Optional[WebhookEvent]:
        """Parse et valide un webhook entrant. Retourne None si signature invalide."""
