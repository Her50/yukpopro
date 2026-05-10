"""
Chargeur de polices Google Fonts pour ReportLab.

Télécharge les .ttf depuis le dépôt google/fonts (CDN GitHub) au premier usage,
les met en cache sur disque (data/fonts/), et les enregistre auprès de
reportlab.pdfbase.pdfmetrics. Si la police n'est pas téléchargeable (offline,
404), on retombe sur les 14 polices core PostScript.

Familles supportées (couvrent couvrent la plupart des cas Phase 1) :
- Playfair Display (titre élégant, sérif)
- Cormorant (sérif fin, cérémonies)
- Lato (corps neutre, sans-serif)
- Inter (corps moderne, sans-serif)
- Montserrat (titres marketing)
- Merriweather (corps lecture)
- Lora (corps éditorial)

Pour chaque famille on tente Regular / Bold / Italic / BoldItalic.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger("yukpo_assurance.bureau.font_loader")

_CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "fonts"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Repère officiel : https://github.com/google/fonts/raw/main/ofl/{slug}/{File}.ttf
_GH_BASE = "https://raw.githubusercontent.com/google/fonts/main/ofl"

# Famille → (slug, {variante: nom_fichier_ttf})
FAMILLES = {
    "Playfair Display": ("playfairdisplay", {
        "Regular":     "PlayfairDisplay%5Bwght%5D.ttf",
        "Bold":        "PlayfairDisplay%5Bwght%5D.ttf",
        "Italic":      "PlayfairDisplay-Italic%5Bwght%5D.ttf",
        "BoldItalic":  "PlayfairDisplay-Italic%5Bwght%5D.ttf",
    }),
    "Cormorant": ("cormorant", {
        "Regular":    "Cormorant%5Bwght%5D.ttf",
        "Bold":       "Cormorant%5Bwght%5D.ttf",
        "Italic":     "Cormorant-Italic%5Bwght%5D.ttf",
        "BoldItalic": "Cormorant-Italic%5Bwght%5D.ttf",
    }),
    "Lato": ("lato", {
        "Regular":    "Lato-Regular.ttf",
        "Bold":       "Lato-Bold.ttf",
        "Italic":     "Lato-Italic.ttf",
        "BoldItalic": "Lato-BoldItalic.ttf",
    }),
    "Inter": ("inter", {
        "Regular":    "Inter%5Bopsz%2Cwght%5D.ttf",
        "Bold":       "Inter%5Bopsz%2Cwght%5D.ttf",
        "Italic":     "Inter-Italic%5Bopsz%2Cwght%5D.ttf",
        "BoldItalic": "Inter-Italic%5Bopsz%2Cwght%5D.ttf",
    }),
    "Montserrat": ("montserrat", {
        "Regular":    "Montserrat%5Bwght%5D.ttf",
        "Bold":       "Montserrat%5Bwght%5D.ttf",
        "Italic":     "Montserrat-Italic%5Bwght%5D.ttf",
        "BoldItalic": "Montserrat-Italic%5Bwght%5D.ttf",
    }),
    "Merriweather": ("merriweather", {
        "Regular":    "Merriweather-Regular.ttf",
        "Bold":       "Merriweather-Bold.ttf",
        "Italic":     "Merriweather-Italic.ttf",
        "BoldItalic": "Merriweather-BoldItalic.ttf",
    }),
    "Lora": ("lora", {
        "Regular":    "Lora%5Bwght%5D.ttf",
        "Bold":       "Lora%5Bwght%5D.ttf",
        "Italic":     "Lora-Italic%5Bwght%5D.ttf",
        "BoldItalic": "Lora-Italic%5Bwght%5D.ttf",
    }),
}

# Cache process : famille+variante déjà enregistrée auprès de reportlab
_REGISTERED: dict[str, str] = {}   # nom_reportlab → chemin_ttf
_FAMILY_REGISTERED: set[str] = set()  # familles dont la mapFontFamily est faite
_LOCK = threading.Lock()


def _telecharger_ttf(famille: str, variante: str) -> Optional[Path]:
    info = FAMILLES.get(famille)
    if not info:
        return None
    slug, fichiers = info
    nom_fichier = fichiers.get(variante)
    if not nom_fichier:
        return None
    nom_local = f"{slug}_{variante}.ttf"
    chemin = _CACHE_DIR / nom_local
    if chemin.exists() and chemin.stat().st_size > 1024:
        return chemin
    url = f"{_GH_BASE}/{slug}/{nom_fichier}"
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            r = client.get(url)
            if r.status_code != 200 or len(r.content) < 1024:
                logger.info(f"[FontLoader] {famille}/{variante} indisponible (HTTP {r.status_code})")
                return None
            chemin.write_bytes(r.content)
            return chemin
    except Exception as e:
        logger.info(f"[FontLoader] téléchargement {famille}/{variante} échoué : {e}")
        return None


def _nom_reportlab(famille: str, variante: str) -> str:
    """Nom unique pour identifier la police chez reportlab."""
    return f"{famille.replace(' ', '')}-{variante}"


def enregistrer_famille(famille: str) -> Optional[str]:
    """
    Tente de télécharger + enregistrer toutes les variantes d'une famille.
    Retourne le nom reportlab à utiliser comme base (Regular) si succès,
    sinon None (caller fera fallback core PostScript).
    """
    with _LOCK:
        if famille in _FAMILY_REGISTERED:
            return _nom_reportlab(famille, "Regular") if _nom_reportlab(famille, "Regular") in _REGISTERED else None

        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
        except Exception:
            return None

        info = FAMILLES.get(famille)
        if not info:
            return None

        nom_regular = None
        for variante in ("Regular", "Bold", "Italic", "BoldItalic"):
            chemin = _telecharger_ttf(famille, variante)
            if not chemin:
                continue
            nom_rl = _nom_reportlab(famille, variante)
            if nom_rl in _REGISTERED:
                continue
            try:
                pdfmetrics.registerFont(TTFont(nom_rl, str(chemin)))
                _REGISTERED[nom_rl] = str(chemin)
                if variante == "Regular":
                    nom_regular = nom_rl
            except Exception as e:
                logger.warning(f"[FontLoader] registerFont {nom_rl}: {e}")

        if nom_regular:
            try:
                pdfmetrics.registerFontFamily(
                    nom_regular,
                    normal=_nom_reportlab(famille, "Regular"),
                    bold=_nom_reportlab(famille, "Bold") if _nom_reportlab(famille, "Bold") in _REGISTERED else nom_regular,
                    italic=_nom_reportlab(famille, "Italic") if _nom_reportlab(famille, "Italic") in _REGISTERED else nom_regular,
                    boldItalic=_nom_reportlab(famille, "BoldItalic") if _nom_reportlab(famille, "BoldItalic") in _REGISTERED else nom_regular,
                )
            except Exception as e:
                logger.warning(f"[FontLoader] registerFontFamily {famille}: {e}")

        _FAMILY_REGISTERED.add(famille)
        return nom_regular


def police_pour(famille: str, italic: bool = False, bold: bool = False) -> Optional[str]:
    """
    Retourne le nom reportlab de la variante demandée si disponible
    (téléchargement à la demande), sinon None.
    """
    if famille not in FAMILLES:
        return None
    enregistrer_famille(famille)
    if bold and italic:
        cand = _nom_reportlab(famille, "BoldItalic")
    elif bold:
        cand = _nom_reportlab(famille, "Bold")
    elif italic:
        cand = _nom_reportlab(famille, "Italic")
    else:
        cand = _nom_reportlab(famille, "Regular")
    return cand if cand in _REGISTERED else None


def chemin_ttf_pour(nom_rl: str) -> Optional[str]:
    """Sprint 1.3 — Retourne le chemin TTF d'une police déjà enregistrée.
    Utilisé par les effets typographiques rasterisés (Pillow) qui ont besoin
    du fichier source plutôt que du nom ReportLab."""
    return _REGISTERED.get(nom_rl)


def prechauffer(familles: Optional[list[str]] = None) -> dict:
    """Précharge les familles principales (à appeler au démarrage si besoin)."""
    cibles = familles or ["Playfair Display", "Lato", "Inter", "Cormorant"]
    out = {}
    for f in cibles:
        out[f] = enregistrer_famille(f) is not None
    return out
