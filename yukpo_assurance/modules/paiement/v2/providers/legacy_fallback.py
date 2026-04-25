"""Provider de secours ultime : reroute vers le système manuel existant.

Quand tous les providers API échouent ou sont indisponibles, on retombe sur
le flux historique YukpoPro : génération d'une référence + instructions
USSD + validation manuelle par l'admin dans les 3h.

Délègue à `modules/paiement/gestionnaire_paiement.py` (legacy).
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from modules.paiement.v2.models import (
    PaymentRequest, PaymentResponse, PaymentStatus, ProviderName, WebhookEvent,
)
from modules.paiement.v2.providers.base import PaymentProvider

logger = logging.getLogger("yukpo_assurance.paiement.v2.legacy")


class LegacyManualProvider(PaymentProvider):
    """Toujours configuré — c'est le filet de sécurité final."""

    name = ProviderName.LEGACY_MANUAL

    def is_configured(self) -> bool:
        return True

    async def initiate(self, request: PaymentRequest) -> PaymentResponse:
        # Génération d'instructions USSD selon le pays/opérateur
        phone = request.customer_phone
        instructions = (
            f"Effectuez un dépôt Mobile Money de {int(request.amount)} {request.currency} "
            f"vers le numéro YukpoPro indiqué, puis confirmez avec la référence "
            f"{request.reference}. Validation admin sous 3h."
        )
        provider_ref = f"MANUAL-{uuid.uuid4().hex[:10].upper()}"
        logger.info("Fallback manuel activé pour %s (%s)", request.reference, phone)

        return PaymentResponse(
            reference=request.reference,
            provider=self.name,
            status=PaymentStatus.PENDING,
            provider_reference=provider_ref,
            ussd_instructions=instructions,
            raw_provider_response={"mode": "manual_admin_validation", "deadline_hours": 3},
        )

    async def check_status(self, provider_reference: str) -> PaymentStatus:
        # Le statut est mis à jour par l'admin, pas par polling automatique.
        return PaymentStatus.PENDING

    async def parse_webhook(
        self, body: bytes, headers: dict[str, str]
    ) -> Optional[WebhookEvent]:
        return None
