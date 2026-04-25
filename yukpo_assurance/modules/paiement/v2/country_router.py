"""Routage intelligent par pays / opérateur / numéro de téléphone.

Détermine la cascade de providers à essayer en fonction du contexte client.
"""
from __future__ import annotations

import re
from typing import Optional

from modules.paiement.v2.models import ProviderName

# Indicatifs téléphoniques → pays (ISO-2)
PHONE_PREFIX_TO_COUNTRY: dict[str, str] = {
    "+237": "CM", "+225": "CI", "+221": "SN", "+223": "ML", "+226": "BF",
    "+228": "TG", "+229": "BJ", "+224": "GN", "+243": "CD", "+241": "GA",
    "+242": "CG", "+235": "TD", "+236": "CF", "+240": "GQ", "+227": "NE",
    "+234": "NG", "+233": "GH", "+254": "KE", "+255": "TZ", "+256": "UG",
    "+250": "RW", "+260": "ZM", "+27": "ZA", "+251": "ET", "+258": "MZ",
}

# Préfixes opérateurs nationaux (8 premiers chiffres après l'indicatif)
# Indispensable pour MTN/Orange Cameroun où chaque opérateur a ses préfixes
OPERATOR_PREFIXES_CM = {
    "mtn": ["67", "68", "650", "651", "652", "653", "654"],
    "orange": ["69", "655", "656", "657", "658", "659"],
    "nexttel": ["66"],
    "camtel": ["620", "621", "242"],
}

# Cascade par pays — providers essayés dans l'ordre
COUNTRY_CASCADE: dict[str, list[ProviderName]] = {
    "CM": [
        ProviderName.MTN_MOMO,
        ProviderName.ORANGE_MONEY,
        ProviderName.CAMPAY,
        ProviderName.CINETPAY,
        ProviderName.NOTCHPAY,
        ProviderName.FLUTTERWAVE,
    ],
    "CI": [
        ProviderName.ORANGE_MONEY,
        ProviderName.MTN_MOMO,
        ProviderName.WAVE,
        ProviderName.CINETPAY,
        ProviderName.FLUTTERWAVE,
    ],
    "SN": [
        ProviderName.WAVE,
        ProviderName.ORANGE_MONEY,
        ProviderName.CINETPAY,
        ProviderName.FLUTTERWAVE,
    ],
    "BF": [ProviderName.ORANGE_MONEY, ProviderName.CINETPAY, ProviderName.FLUTTERWAVE],
    "ML": [ProviderName.ORANGE_MONEY, ProviderName.CINETPAY, ProviderName.FLUTTERWAVE],
    "TG": [ProviderName.CINETPAY, ProviderName.FLUTTERWAVE],
    "BJ": [ProviderName.MTN_MOMO, ProviderName.CINETPAY, ProviderName.FLUTTERWAVE],
    "GA": [ProviderName.CINETPAY, ProviderName.FLUTTERWAVE],
    "CG": [ProviderName.MTN_MOMO, ProviderName.CINETPAY, ProviderName.FLUTTERWAVE],
    "CD": [ProviderName.ORANGE_MONEY, ProviderName.FLUTTERWAVE],
    "NG": [ProviderName.FLUTTERWAVE, ProviderName.NOTCHPAY, ProviderName.STRIPE],
    "KE": [ProviderName.FLUTTERWAVE, ProviderName.STRIPE],
    "ZA": [ProviderName.STRIPE, ProviderName.PAYPAL, ProviderName.FLUTTERWAVE],
}

# Cascade par défaut (international / pays non listé)
DEFAULT_INTL_CASCADE: list[ProviderName] = [
    ProviderName.STRIPE,
    ProviderName.PAYPAL,
    ProviderName.FLUTTERWAVE,
]


def detect_country_from_phone(phone: str) -> Optional[str]:
    """Détecte le code pays ISO-2 depuis un numéro E.164."""
    if not phone:
        return None
    phone = phone.strip().replace(" ", "")
    if not phone.startswith("+"):
        phone = "+" + phone
    # Essai du plus long au plus court (3 puis 2 chiffres)
    for length in (4, 3, 2):
        prefix = phone[: length + 1]  # +XXX...
        if prefix in PHONE_PREFIX_TO_COUNTRY:
            return PHONE_PREFIX_TO_COUNTRY[prefix]
    return None


def detect_operator_cm(phone: str) -> Optional[ProviderName]:
    """Détecte MTN ou Orange depuis un numéro camerounais."""
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("237"):
        digits = digits[3:]
    if not digits:
        return None
    for op, prefixes in OPERATOR_PREFIXES_CM.items():
        for p in prefixes:
            if digits.startswith(p):
                if op == "mtn":
                    return ProviderName.MTN_MOMO
                if op == "orange":
                    return ProviderName.ORANGE_MONEY
    return None


def build_cascade(
    *,
    country_code: Optional[str],
    phone: Optional[str],
    preferred: Optional[ProviderName] = None,
    available_providers: Optional[set[ProviderName]] = None,
) -> list[ProviderName]:
    """
    Construit la liste ordonnée des providers à essayer.

    Logique :
    1. `preferred` en tête s'il est dispo
    2. Si pays = CM, on détecte l'opérateur exact (MTN/Orange) et le met en 2e
    3. Cascade pays par défaut
    4. Filtrage par `available_providers` (providers configurés/sains)
    5. Toujours terminer par LEGACY_MANUAL en dernier recours
    """
    country = country_code or detect_country_from_phone(phone or "")
    cascade: list[ProviderName] = []

    if preferred:
        cascade.append(preferred)

    if country == "CM" and phone:
        detected_op = detect_operator_cm(phone)
        if detected_op and detected_op not in cascade:
            cascade.append(detected_op)

    base_cascade = COUNTRY_CASCADE.get(country, DEFAULT_INTL_CASCADE) if country else DEFAULT_INTL_CASCADE
    for p in base_cascade:
        if p not in cascade:
            cascade.append(p)

    if available_providers is not None:
        cascade = [p for p in cascade if p in available_providers]

    if ProviderName.LEGACY_MANUAL not in cascade:
        cascade.append(ProviderName.LEGACY_MANUAL)

    return cascade
