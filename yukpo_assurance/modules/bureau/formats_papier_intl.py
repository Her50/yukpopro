"""
Phase 4.3a — Catalogue mondial des formats papier d'impression.

Couvre :
  - Série ISO A (A0 à A10) — standard international
  - Série ISO B (B0 à B6)
  - US/Canada (Letter, Legal, Tabloid, Ledger, Executive, Junior Legal, Half Letter)
  - Japon (B-JIS, kiku, shiroku-ban)
  - Photo (10×15, 13×18, 18×24, 20×30, 30×40 cm)
  - Cartes (visite, postale, voeux)
  - Affiches grand format (40×60, 50×70, 70×100)
  - Banderoles (roll-up 80×200, banderole 200×80, bâche XXL)
  - Pliés/dépliants (3 volets, 4 volets, accordéon, fenêtre)

Le LLM choisit dans ce catalogue (ou compose un format custom si besoin).
"""
from __future__ import annotations


# Format = (width_mm, height_mm) en portrait (rotation possible pour paysage)
FORMATS_PAPIER_INTL: dict[str, dict] = {
    # ─── Série ISO A (international) ──────────────────────────────────────
    "A0":   {"label": "A0",    "width_mm": 841, "height_mm": 1189, "categorie": "ISO A", "usage": "affiche grand format / plan"},
    "A1":   {"label": "A1",    "width_mm": 594, "height_mm": 841,  "categorie": "ISO A", "usage": "affiche / poster"},
    "A2":   {"label": "A2",    "width_mm": 420, "height_mm": 594,  "categorie": "ISO A", "usage": "affiche moyenne"},
    "A3":   {"label": "A3",    "width_mm": 297, "height_mm": 420,  "categorie": "ISO A", "usage": "petite affiche / tableau"},
    "A4":   {"label": "A4",    "width_mm": 210, "height_mm": 297,  "categorie": "ISO A", "usage": "lettre / brochure standard"},
    "A5":   {"label": "A5",    "width_mm": 148, "height_mm": 210,  "categorie": "ISO A", "usage": "flyer / carnet"},
    "A6":   {"label": "A6",    "width_mm": 105, "height_mm": 148,  "categorie": "ISO A", "usage": "carte postale / carton invitation"},
    "A7":   {"label": "A7",    "width_mm": 74,  "height_mm": 105,  "categorie": "ISO A", "usage": "ticket / mini-flyer"},
    # ─── Série ISO B ──────────────────────────────────────────────────────
    "B0":   {"label": "B0",    "width_mm": 1000, "height_mm": 1414, "categorie": "ISO B", "usage": "très grande affiche"},
    "B1":   {"label": "B1",    "width_mm": 707,  "height_mm": 1000, "categorie": "ISO B", "usage": "grande affiche"},
    "B2":   {"label": "B2",    "width_mm": 500,  "height_mm": 707,  "categorie": "ISO B", "usage": "affiche événementielle"},
    "B3":   {"label": "B3",    "width_mm": 353,  "height_mm": 500,  "categorie": "ISO B", "usage": "poster moyen"},
    "B4":   {"label": "B4",    "width_mm": 250,  "height_mm": 353,  "categorie": "ISO B", "usage": "magazine / catalogue"},
    "B5":   {"label": "B5",    "width_mm": 176,  "height_mm": 250,  "categorie": "ISO B", "usage": "livre poche / carnet"},
    "B6":   {"label": "B6",    "width_mm": 125,  "height_mm": 176,  "categorie": "ISO B", "usage": "carte / mini-livret"},
    # ─── US/Canada ────────────────────────────────────────────────────────
    "US_LETTER":   {"label": "US Letter",   "width_mm": 215.9, "height_mm": 279.4, "categorie": "US",  "usage": "lettre standard US"},
    "US_LEGAL":    {"label": "US Legal",    "width_mm": 215.9, "height_mm": 355.6, "categorie": "US",  "usage": "documents juridiques US"},
    "US_TABLOID":  {"label": "US Tabloid",  "width_mm": 279.4, "height_mm": 431.8, "categorie": "US",  "usage": "tabloïd, brochure 11×17"},
    "US_LEDGER":   {"label": "US Ledger",   "width_mm": 431.8, "height_mm": 279.4, "categorie": "US",  "usage": "registre paysage"},
    "US_EXECUTIVE":{"label": "US Executive","width_mm": 184.2, "height_mm": 266.7, "categorie": "US",  "usage": "papier exécutif compact"},
    "US_HALF":     {"label": "US Half-Letter","width_mm": 139.7, "height_mm": 215.9, "categorie": "US","usage": "demi-lettre, carnet US"},
    # ─── Cartes & invitations ────────────────────────────────────────────
    "CARTE_VISITE_INTL":  {"label": "Carte de visite (intl 85×55)", "width_mm": 85, "height_mm": 55, "categorie": "carte", "usage": "carte de visite standard mondial"},
    "CARTE_VISITE_US":    {"label": "Carte de visite US (89×51)",   "width_mm": 88.9, "height_mm": 50.8, "categorie": "carte", "usage": "carte US/Canada"},
    "CARTE_POSTALE":      {"label": "Carte postale 100×148",         "width_mm": 100, "height_mm": 148, "categorie": "carte", "usage": "carte postale internationale"},
    "CARTE_VOEUX":        {"label": "Carte de voeux 150×210",        "width_mm": 150, "height_mm": 210, "categorie": "carte", "usage": "carte de voeux"},
    "CARTON_INVITATION":  {"label": "Carton invitation 105×210",     "width_mm": 105, "height_mm": 210, "categorie": "carte", "usage": "invitation événement"},
    # ─── Photo ────────────────────────────────────────────────────────────
    "PHOTO_10X15":  {"label": "Photo 10×15", "width_mm": 100, "height_mm": 150, "categorie": "photo", "usage": "tirage standard"},
    "PHOTO_13X18":  {"label": "Photo 13×18", "width_mm": 130, "height_mm": 180, "categorie": "photo", "usage": "tirage moyen"},
    "PHOTO_18X24":  {"label": "Photo 18×24", "width_mm": 180, "height_mm": 240, "categorie": "photo", "usage": "agrandissement"},
    "PHOTO_20X30":  {"label": "Photo 20×30", "width_mm": 200, "height_mm": 300, "categorie": "photo", "usage": "poster photo"},
    "PHOTO_30X40":  {"label": "Photo 30×40", "width_mm": 300, "height_mm": 400, "categorie": "photo", "usage": "grand poster photo"},
    # ─── Affiches grand format ───────────────────────────────────────────
    "POSTER_40X60": {"label": "Poster 40×60", "width_mm": 400, "height_mm": 600,  "categorie": "poster", "usage": "affiche moyenne décoration"},
    "POSTER_50X70": {"label": "Poster 50×70", "width_mm": 500, "height_mm": 700,  "categorie": "poster", "usage": "affiche standard musée/expo"},
    "POSTER_70X100":{"label": "Poster 70×100", "width_mm": 700, "height_mm": 1000, "categorie": "poster", "usage": "très grande affiche"},
    # ─── Banderoles / roll-up / bâche ────────────────────────────────────
    "ROLLUP_80X200":  {"label": "Roll-up 80×200",   "width_mm": 800,  "height_mm": 2000, "categorie": "grand_format", "usage": "stand événementiel vertical"},
    "ROLLUP_85X200":  {"label": "Roll-up 85×200",   "width_mm": 850,  "height_mm": 2000, "categorie": "grand_format", "usage": "roll-up large"},
    "BANDEROLE_200X80": {"label": "Banderole 200×80", "width_mm": 2000, "height_mm": 800,  "categorie": "grand_format", "usage": "banderole horizontale"},
    "BANDEROLE_300X100": {"label": "Banderole 300×100", "width_mm": 3000, "height_mm": 1000, "categorie": "grand_format", "usage": "très grande banderole"},
    "BACHE_XXL":      {"label": "Bâche XXL 400×200",  "width_mm": 4000, "height_mm": 2000, "categorie": "grand_format", "usage": "bâche événementielle XXL"},
    # ─── Pliés / dépliants (note : format en mm = format DÉPLIÉ) ─────────
    "PLIE_3VOLETS_A4": {"label": "Dépliant 3 volets A4 (déplié 297×210)", "width_mm": 297, "height_mm": 210, "categorie": "plie", "usage": "dépliant 3 volets DL plié 99×210", "fold": "trifold"},
    "PLIE_3VOLETS_A3": {"label": "Dépliant 3 volets A3", "width_mm": 420, "height_mm": 297, "categorie": "plie", "usage": "dépliant 3 volets large", "fold": "trifold"},
    "PLIE_4VOLETS_A4": {"label": "Dépliant 4 volets A4", "width_mm": 297, "height_mm": 210, "categorie": "plie", "usage": "dépliant 4 volets accordéon plié 74×210", "fold": "z-fold-4"},
    "PLIE_FENETRE":    {"label": "Pli fenêtre A4",       "width_mm": 297, "height_mm": 210, "categorie": "plie", "usage": "pliage fenêtre/portefeuille", "fold": "gate-fold"},
    "PLIE_LIVRET_A5":  {"label": "Livret A5 plié (couverture A4)", "width_mm": 297, "height_mm": 210, "categorie": "plie", "usage": "livret 4 pages A5 = 1 feuille A4", "fold": "saddle-stitch"},
    # ─── Calendriers ─────────────────────────────────────────────────────
    "CALENDRIER_MURAL_A3":    {"label": "Calendrier mural A3", "width_mm": 297, "height_mm": 420, "categorie": "calendrier", "usage": "calendrier mural standard"},
    "CALENDRIER_BUREAU":       {"label": "Calendrier bureau triangulaire", "width_mm": 200, "height_mm": 100, "categorie": "calendrier", "usage": "calendrier de bureau"},
    "CALENDRIER_POCHE":        {"label": "Calendrier poche (carte)",     "width_mm": 85,  "height_mm": 55,  "categorie": "calendrier", "usage": "calendrier format carte de visite"},
}


def trouver_format_par_label(label_ou_cle: str) -> dict | None:
    """Recherche par clé exacte OU par label (case-insensitive partial)."""
    if label_ou_cle in FORMATS_PAPIER_INTL:
        return {**FORMATS_PAPIER_INTL[label_ou_cle], "cle": label_ou_cle}
    low = label_ou_cle.lower()
    for cle, fmt in FORMATS_PAPIER_INTL.items():
        if low == fmt["label"].lower() or low in fmt["label"].lower():
            return {**fmt, "cle": cle}
    return None


def lister_formats_par_categorie() -> dict[str, list[dict]]:
    """Groupe les formats par catégorie pour UI / orchestrateur LLM."""
    out: dict[str, list[dict]] = {}
    for cle, fmt in FORMATS_PAPIER_INTL.items():
        cat = fmt.get("categorie", "autre")
        out.setdefault(cat, []).append({"cle": cle, **fmt})
    return out


def descripteur_compact_pour_llm() -> list[dict]:
    """Descripteur compact pour injection dans prompt orchestrateur."""
    return [
        {"cle": cle, "label": fmt["label"],
         "format_mm": [fmt["width_mm"], fmt["height_mm"]],
         "categorie": fmt["categorie"], "usage": fmt["usage"]}
        for cle, fmt in FORMATS_PAPIER_INTL.items()
    ]
