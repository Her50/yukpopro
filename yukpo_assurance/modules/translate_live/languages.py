"""
Référentiel de langues — codes ISO 639-1 supportés par la traduction live.
"""
from typing import Optional

LANGUES_SUPPORTEES: list[dict] = [
    {"code": "auto", "label": "Détection automatique",        "flag": "🌐", "stt": True,  "trad": False},
    {"code": "fr",   "label": "Français",                      "flag": "🇫🇷", "stt": True,  "trad": True},
    {"code": "en",   "label": "Anglais",                       "flag": "🇬🇧", "stt": True,  "trad": True},
    {"code": "pt",   "label": "Portugais",                     "flag": "🇵🇹", "stt": True,  "trad": True},
    {"code": "es",   "label": "Espagnol",                      "flag": "🇪🇸", "stt": True,  "trad": True},
    {"code": "ar",   "label": "Arabe",                         "flag": "🇸🇦", "stt": True,  "trad": True},
    {"code": "de",   "label": "Allemand",                      "flag": "🇩🇪", "stt": True,  "trad": True},
    {"code": "it",   "label": "Italien",                       "flag": "🇮🇹", "stt": True,  "trad": True},
    {"code": "nl",   "label": "Néerlandais",                   "flag": "🇳🇱", "stt": True,  "trad": True},
    {"code": "zh",   "label": "Mandarin (chinois simplifié)",  "flag": "🇨🇳", "stt": True,  "trad": True},
    {"code": "ja",   "label": "Japonais",                      "flag": "🇯🇵", "stt": True,  "trad": True},
    {"code": "ko",   "label": "Coréen",                        "flag": "🇰🇷", "stt": True,  "trad": True},
    {"code": "ru",   "label": "Russe",                         "flag": "🇷🇺", "stt": True,  "trad": True},
    {"code": "hi",   "label": "Hindi",                         "flag": "🇮🇳", "stt": True,  "trad": True},
    {"code": "tr",   "label": "Turc",                          "flag": "🇹🇷", "stt": True,  "trad": True},
    # Langues africaines — traduction disponible mais STT limité (nécessite Sprint 3 / NLLB)
    {"code": "sw",   "label": "Swahili",                       "flag": "🇹🇿", "stt": False, "trad": True},
    {"code": "ha",   "label": "Hausa",                         "flag": "🇳🇬", "stt": False, "trad": True},
    {"code": "yo",   "label": "Yoruba",                        "flag": "🇳🇬", "stt": False, "trad": True},
    {"code": "wo",   "label": "Wolof",                         "flag": "🇸🇳", "stt": False, "trad": True},
    {"code": "ln",   "label": "Lingala",                       "flag": "🇨🇩", "stt": False, "trad": True},
]

_CODES_VALIDES = {l["code"] for l in LANGUES_SUPPORTEES}

# Noms humains pour le prompt de traduction
LABEL_PAR_CODE: dict[str, str] = {
    "fr": "français", "en": "anglais", "pt": "portugais", "es": "espagnol",
    "ar": "arabe",    "de": "allemand", "it": "italien",   "nl": "néerlandais",
    "zh": "mandarin", "ja": "japonais", "ko": "coréen",    "ru": "russe",
    "hi": "hindi",    "tr": "turc",     "sw": "swahili",   "ha": "hausa",
    "yo": "yoruba",   "wo": "wolof",    "ln": "lingala",
}


def normaliser_code_langue(code: Optional[str], defaut: str = "auto") -> str:
    """Accepte `fr`, `FR`, `fr-FR`, `French` → retourne code normalisé ou `defaut`."""
    if not code:
        return defaut
    c = code.strip().lower().split("-")[0].split("_")[0]
    if c in _CODES_VALIDES:
        return c
    # Alias courants
    alias = {"english": "en", "francais": "fr", "français": "fr",
             "chinese": "zh", "mandarin": "zh", "espanol": "es", "español": "es"}
    return alias.get(c, defaut)


def nom_humain(code: str) -> str:
    """Retourne le nom humain de la langue pour prompt (ex: 'anglais')."""
    return LABEL_PAR_CODE.get(code, code)
