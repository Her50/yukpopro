"""
pays_devise — Mapping pays → devise pour affichages informatifs.

Usage : format_amount(montant, pays) → "1 250 000 FCFA" / "$1,250" / "₦450,000"

ATTENTION : Cet helper sert UNIQUEMENT aux affichages informatifs (prompts LLM,
rapports générés, prix indicatifs). Les flux de paiement (abonnement, wallet,
mobile money) restent en XAF/XOF — ne pas utiliser ici.
"""
from __future__ import annotations

# ISO 3166-1 alpha-2 → (code devise ISO 4217, symbole, séparateur milliers)
PAYS_DEVISE: dict[str, tuple[str, str, str]] = {
    # Zone CEMAC (XAF)
    "CM": ("XAF", "FCFA", " "),
    "GA": ("XAF", "FCFA", " "),
    "CG": ("XAF", "FCFA", " "),
    "TD": ("XAF", "FCFA", " "),
    "CF": ("XAF", "FCFA", " "),
    "GQ": ("XAF", "FCFA", " "),
    # Zone UEMOA (XOF)
    "SN": ("XOF", "FCFA", " "),
    "CI": ("XOF", "FCFA", " "),
    "BF": ("XOF", "FCFA", " "),
    "ML": ("XOF", "FCFA", " "),
    "NE": ("XOF", "FCFA", " "),
    "TG": ("XOF", "FCFA", " "),
    "BJ": ("XOF", "FCFA", " "),
    "GW": ("XOF", "FCFA", " "),
    # Afrique anglophone / autres
    "NG": ("NGN", "₦", ","),
    "GH": ("GHS", "GH₵", ","),
    "KE": ("KES", "KSh", ","),
    "TZ": ("TZS", "TSh", ","),
    "UG": ("UGX", "USh", ","),
    "RW": ("RWF", "RF", ","),
    "ET": ("ETB", "Br", ","),
    "ZA": ("ZAR", "R", " "),
    "EG": ("EGP", "E£", ","),
    "MA": ("MAD", "DH", " "),
    "DZ": ("DZD", "DA", " "),
    "TN": ("TND", "DT", " "),
    "LY": ("LYD", "LD", ","),
    "SD": ("SDG", "SDG", ","),
    "AO": ("AOA", "Kz", " "),
    "MZ": ("MZN", "MT", " "),
    "CD": ("CDF", "FC", " "),
    "MG": ("MGA", "Ar", " "),
    "MU": ("MUR", "Rs", ","),
    "ZW": ("ZWL", "Z$", ","),
    "ZM": ("ZMW", "ZK", ","),
    # Hors Afrique (référence)
    "FR": ("EUR", "€", " "),
    "BE": ("EUR", "€", " "),
    "DE": ("EUR", "€", "."),
    "ES": ("EUR", "€", "."),
    "IT": ("EUR", "€", "."),
    "PT": ("EUR", "€", "."),
    "GB": ("GBP", "£", ","),
    "US": ("USD", "$", ","),
    "CA": ("CAD", "CA$", ","),
    "CH": ("CHF", "CHF", " "),
    "CN": ("CNY", "¥", ","),
    "IN": ("INR", "₹", ","),
    "JP": ("JPY", "¥", ","),
    "BR": ("BRL", "R$", "."),
    "AE": ("AED", "AED", ","),
    "SA": ("SAR", "SAR", ","),
    "TR": ("TRY", "₺", "."),
    "RU": ("RUB", "₽", " "),
}

DEVISE_DEFAUT: tuple[str, str, str] = ("XAF", "FCFA", " ")


def get_devise(pays: str | None) -> tuple[str, str, str]:
    """Retourne (code ISO, symbole, séparateur milliers) pour un pays."""
    if not pays:
        return DEVISE_DEFAUT
    return PAYS_DEVISE.get(pays.strip().upper(), DEVISE_DEFAUT)


def format_amount(montant: float | int | None, pays: str | None = None) -> str:
    """
    Formate un montant avec la devise du pays.

    >>> format_amount(1250000, "CM")
    '1 250 000 FCFA'
    >>> format_amount(1250, "US")
    '$1,250'
    >>> format_amount(450000, "NG")
    '₦450,000'
    """
    if montant is None:
        return "—"
    _, symbole, sep = get_devise(pays)
    try:
        n = float(montant)
    except (TypeError, ValueError):
        return str(montant)
    if n == int(n):
        formatted = f"{int(n):,}".replace(",", sep)
    else:
        formatted = f"{n:,.2f}".replace(",", "\u0000").replace(".", ",").replace("\u0000", sep)
    # Symbole préfixe pour devises occidentales/asiatiques, suffixe pour FCFA/africaines
    if symbole in ("€", "$", "£", "¥", "₦", "₹", "₽", "₺", "R$", "CA$", "GH₵"):
        return f"{symbole}{formatted}"
    return f"{formatted} {symbole}"


def vocabulaire_devise(pays: str | None) -> str:
    """Retourne une mention 'devise locale (CODE)' pour les system prompts LLM."""
    code, symbole, _ = get_devise(pays)
    if symbole == "FCFA":
        return f"FCFA ({code})"
    return f"{symbole} ({code})"


# ISO 3166-1 alpha-2 → continent (AF/EU/AM/AS)
PAYS_CONTINENT: dict[str, str] = {
    "CM": "AF", "GA": "AF", "CG": "AF", "TD": "AF", "CF": "AF", "GQ": "AF",
    "SN": "AF", "CI": "AF", "BF": "AF", "ML": "AF", "NE": "AF", "TG": "AF",
    "BJ": "AF", "GW": "AF", "NG": "AF", "GH": "AF", "KE": "AF", "TZ": "AF",
    "UG": "AF", "RW": "AF", "ET": "AF", "ZA": "AF", "EG": "AF", "MA": "AF",
    "DZ": "AF", "TN": "AF", "LY": "AF", "SD": "AF", "AO": "AF", "MZ": "AF",
    "CD": "AF", "MG": "AF", "MU": "AF", "ZW": "AF", "ZM": "AF",
    "FR": "EU", "BE": "EU", "DE": "EU", "ES": "EU", "IT": "EU", "PT": "EU",
    "GB": "EU", "CH": "EU", "RU": "EU",
    "US": "AM", "CA": "AM", "BR": "AM",
    "CN": "AS", "IN": "AS", "JP": "AS", "AE": "AS", "SA": "AS", "TR": "AS",
}

CONTINENT_LABELS: dict[str, str] = {
    "AF": "Afrique", "EU": "Europe", "AM": "Amériques", "AS": "Asie", "OC": "Océanie",
}


def get_continent(pays: str | None) -> str | None:
    """Retourne le code continent (AF/EU/AM/AS) pour un pays ISO."""
    if not pays:
        return None
    return PAYS_CONTINENT.get(pays.strip().upper())


def pays_du_continent(continent: str) -> list[str]:
    """Liste des codes pays appartenant à un continent donné."""
    c = continent.strip().upper()
    return [p for p, cont in PAYS_CONTINENT.items() if cont == c]
