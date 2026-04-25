"""
YukpoAssurance — Module Paiement v2

Système de paiement multi-providers avec sélection intelligente, cascade
de fallback et routage par pays/opérateur. Inspiré de l'architecture
yukpomnang2 (Rust → Python).

Hiérarchie de fallback :
    1. MTN MoMo / Orange Money (direct, push USSD)
    2. CinetPay (agrégateur CEMAC/UEMOA)
    3. Flutterwave (Pan-African)
    4. NotchPay (fallback Afrique de l'Ouest)
    5. Stripe / PayPal (cartes internationales)
    6. Campay (fintech CM locale)
    7. gestionnaire_paiement.py legacy (validation manuelle admin)

Point d'entrée principal : `PaymentOrchestrator.initiate(...)`.
"""
from modules.paiement.v2.orchestrator import PaymentOrchestrator
from modules.paiement.v2.models import (
    PaymentRequest,
    PaymentResponse,
    PaymentStatus,
    PaymentMethod,
    ProviderName,
)

__all__ = [
    "PaymentOrchestrator",
    "PaymentRequest",
    "PaymentResponse",
    "PaymentStatus",
    "PaymentMethod",
    "ProviderName",
]
