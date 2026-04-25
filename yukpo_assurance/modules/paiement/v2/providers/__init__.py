"""Implémentations concrètes des providers de paiement."""
from modules.paiement.v2.providers.base import PaymentProvider, ProviderUnavailable
from modules.paiement.v2.providers.mtn_momo import MTNMoMoProvider
from modules.paiement.v2.providers.orange_money import OrangeMoneyProvider
from modules.paiement.v2.providers.cinetpay import CinetPayProvider
from modules.paiement.v2.providers.flutterwave import FlutterwaveProvider
from modules.paiement.v2.providers.stripe_provider import StripeProvider
from modules.paiement.v2.providers.paypal_provider import PayPalProvider
from modules.paiement.v2.providers.notchpay import NotchPayProvider
from modules.paiement.v2.providers.campay import CampayProvider
from modules.paiement.v2.providers.legacy_fallback import LegacyManualProvider

__all__ = [
    "PaymentProvider",
    "ProviderUnavailable",
    "MTNMoMoProvider",
    "OrangeMoneyProvider",
    "CinetPayProvider",
    "FlutterwaveProvider",
    "StripeProvider",
    "PayPalProvider",
    "NotchPayProvider",
    "CampayProvider",
    "LegacyManualProvider",
]
