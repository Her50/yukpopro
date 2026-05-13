"""
LLM Placement Planner — Phase 1 du pipeline Designer Pro NEXT-GEN.

Demande à un LLM (Sonnet pour la vision géométrique, Opus si demandes très
complexes) de produire un PlacementPlan JSON à partir de :
  - brief utilisateur (intention sémantique)
  - dimensions de page (W×H mm, bleed, orientation)
  - manifest des médias uploadés (dim source, ratio, contenu sémantique)
  - palette de marque optionnelle (BrandKit org)

Le LLM raisonne EN VISION HUMAINE :
  "Le portrait du défunt est en pied, photo 800×1200 portrait. Je le mets
   dans un cercle de 60mm centré en haut de la couverture, recadrage focal
   sur le visage (focal_y=0.2 pour garder la tête). Sous le portrait, le
   nom du défunt en gros (Cormorant 42pt, bleu marine), centré, italique
   léger. En bas, dates 1948–2026 en Lato 18pt gris."

Python implémente CETTE intention en pixels exacts via geometric_placement.

Modèle par défaut : Sonnet (équilibre vision + math). Fallback GPT-4 turbo
si Claude indispo. Cap tokens out : ~3000 pour un layout riche.
"""
from __future__ import annotations

import io
import json
import logging
import re
from typing import Optional

from .geometric_placement import (
    PlacementPlan, TextPlacement, ImagePlacement, ShapePlacement,
    BBox, Color, Transform, Shadow, PageBackground,
    DesignTokens, TypographyToken,
)


def _empty_usage() -> dict:
    return {"modele": "", "tokens_in": 0, "tokens_out": 0}


def _usage_from_rep(rep) -> dict:
    """Extrait usage info depuis une réponse ia_client (pour facturation aval)."""
    return {
        "modele":     getattr(rep, "modele_utilise", "") or "",
        "tokens_in":  int(getattr(rep, "tokens_input", 0) or 0),
        "tokens_out": int(getattr(rep, "tokens_output", 0) or 0),
    }

logger = logging.getLogger("yukpo_assurance.bureau.llm_placement")


# ═══════════════════════════════════════════════════════════════════════
# Manifest d'image uploadée — métadonnées exploitables par le LLM
# ═══════════════════════════════════════════════════════════════════════

def manifest_image(
    media_ref: str,
    image_bytes: bytes,
    tags: Optional[list[str]] = None,
    role_hint: Optional[str] = None,
) -> dict:
    """
    Construit le manifest d'une image pour le LLM.

    `media_ref` : identifiant stable (ex: 'session:abc123')
    `tags`      : sémantique humaine (['portrait', 'visage', 'défunt']) ; si
                  None, on tente une auto-détection légère (orientation,
                  couleur dominante). Vision Sonnet idéal pour générer tags
                  riches mais c'est un appel séparé hors scope ici.
    `role_hint` : suggestion sémantique ('portrait_principal', 'logo',
                  'fond_decoratif', 'illustration_section')
    """
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        ratio = round(w / max(1, h), 3)
        orientation = "portrait" if h > w * 1.1 else ("paysage" if w > h * 1.1 else "carre")
        # Couleur dominante moyenne sur thumbnail
        thumb = img.convert("RGB").resize((40, 40))
        pixels = list(thumb.getdata())
        avg = tuple(sum(c[i] for c in pixels) // len(pixels) for i in range(3))
    except Exception as e:
        logger.warning(f"[Manifest] échec lecture image {media_ref} : {e}")
        w = h = 0; ratio = 1.0; orientation = "inconnu"; avg = (128, 128, 128)

    return {
        "media_ref": media_ref,
        "width_px": w, "height_px": h,
        "ratio": ratio, "orientation": orientation,
        "couleur_dominante_hex": f"#{avg[0]:02x}{avg[1]:02x}{avg[2]:02x}",
        "tags": tags or [],
        "role_hint": role_hint or "auto",
    }


# ═══════════════════════════════════════════════════════════════════════
# Prompt LLM — placement géométrique
# ═══════════════════════════════════════════════════════════════════════

PROMPT_SYSTEM = """Tu es DIRECTEUR ARTISTIQUE, GRAPHISTE EXPERT et TYPOGRAPHE.

Mission : pour un visuel imprimable (flyer, carte, livret, affiche, faire-part,
diplôme…), tu décides EN VISION HUMAINE le placement parfait de chaque élément
(texte, image, forme décorative) sur la page.

Tu reçois :
  - Brief utilisateur (intention, contenu)
  - Page : largeur, hauteur, marges bleed (en mm, origine top-left)
  - Médias uploadés : dimensions, orientation, contenu sémantique
  - Palette/typographie de marque (si fournie)

Tu produis un PLAN JSON où CHAQUE élément a sa bounding box EXACTE en mm,
ses propriétés visuelles complètes, et les ajustements géométriques nécessaires
(recadrage focal des images, masque silhouette, rotation, ombre, etc.).

PRINCIPES DE DESIGN :
1. RESPIRATION — laisse 8-15mm de marge intérieure depuis le trim.
2. HIÉRARCHIE — 1 élément dominant (≥40% de la surface visuelle), 2-3 secondaires,
   reste accessoire. Jamais 10 éléments tous au même niveau.
3. ALIGNEMENT — grille visuelle implicite, axes alignés. Centres optiques
   coïncident souvent.
4. CONTRASTE — couleur, taille, poids. Pas de mou.
5. AÉRATION TYPOGRAPHIQUE — line-height 1.2-1.5, letter-spacing élargi
   (0.05-0.15em) pour les TITRES MAJUSCULES, normal sinon.
6. ROLE DES IMAGES — un portrait = cercle ou masque doux (pas un rectangle dur).
   Un logo = rectangle aligné en coin. Un fond = full-bleed + opacité réduite
   si du texte se superpose.
7. CADRAGE FOCAL — si une photo doit être recadrée pour s'adapter à la zone,
   précise focal_point_x/y pour ancrer le sujet (visage, produit, mention clé).

Pour CHAQUE image dans target_zone :
  - Si le ratio source ≠ ratio cible, fit_mode='smart_focus' avec focal_point
    explicite (ex: portrait debout dans cercle → focal_y=0.2 pour visage en haut).
  - mask_shape adapté : portrait = circle ou rounded_rect, paysage = rect,
    logo = rect, illustration = blob ou polygon si organique.
  - filters (recolor/grayscale/blur) si l'image distrait du message principal
    (ex: fond de carte = grayscale + blur léger + opacity 0.3).

Pour CHAQUE texte (CRITIQUE — la typographie est 50% du design) :
  - bbox AVEC marge de respiration (pas collé au bord).
  - vertical_align logique (titre = center vertical dans son bloc, paragraphe = top).

  ─── HIÉRARCHIE TYPOGRAPHIQUE OBLIGATOIRE ─────────────────────────────────
  Tu DOIS donner à CHAQUE texte une mise en forme RÉFLÉCHIE qui reflète son
  RÔLE SÉMANTIQUE dans le visuel. Jamais 2 textes au même niveau sauf
  intention d'équilibre symétrique.

  ─── DIMENSIONNEMENT PROPORTIONNEL À LA PAGE (CRITIQUE) ───────────────────
  Les tailles pt ABSOLUES n'ont PAS de sens — un titre de 60pt sur une carte
  de visite 90×55mm est ridicule, sur une affiche A0 (841×1189mm) c'est petit.
  Tu DOIS calculer font_size_pt PROPORTIONNELLEMENT à la diagonale de la page.

  Méthode : compute la diagonale = √(page_w_mm² + page_h_mm²), puis dérive
  les tailles depuis des FRACTIONS de cette diagonale (1 mm ≈ 2.83 pt) :

  | Rôle sémantique   | Fraction de diagonale (en mm) → pt           |
  |-------------------|----------------------------------------------|
  | Display (héros)   | 5-9 % de la diagonale × 2.83                 |
  | Headline (H1)     | 3-5 %                                         |
  | Subhead (H2)      | 2-3 %                                         |
  | Title (H3)        | 1.5-2 %                                       |
  | Body              | 0.9-1.3 %                                     |
  | Caption           | 0.6-0.9 %                                     |
  | Overline          | 0.7-1 % (UPPERCASE + letter-spaced)          |

  Exemples concrets calculés (diagonale en mm → pt résultat) :
  • Carte de visite 90×55mm  → diag = 105mm  → Display ~21pt, Body ~3pt (donc
    n'utilise PAS Display sur une carte ; max Headline ~5pt … ce qui est
    trop petit aussi → adapte : sur carte, le titre principal devient H2
    ~14-16pt et le reste descend en proportion).
  • Flyer A5 148×210mm        → diag = 257mm  → Display ~51pt, Body ~7pt.
  • Affiche A3 297×420mm      → diag = 515mm  → Display ~102pt, Body ~14pt.
  • Affiche A0 841×1189mm     → diag = 1457mm → Display ~287pt, Body ~40pt.
  • Banderole 800×200mm       → diag = 825mm  → Display ~163pt, Body ~23pt.

  PRINCIPE : adapte AUSSI le NIVEAU le plus haut utilisé selon la nature du
  visuel. Sur petit support (carte visite, ticket, sticker), le plus haut
  niveau est H2/H3 — pas de Display. Sur grand support (affiche, banderole),
  le plus haut niveau est Display.

  font_weight reste cohérent : titres ≥ 700, corps 400, captions 400-500.
  Le RAPPORT entre niveaux compte plus que les valeurs absolues : titre / corps
  doit faire ratio ≈ 2.5-4× (pas 1.5× faible, pas 8× écrasant).

  ─── CHOIX DE POLICE par REGISTRE ────────────────────────────────────────
  | Registre                    | Famille titre        | Famille corps         |
  |-----------------------------|----------------------|-----------------------|
  | Sobre corporate / pro       | Inter, Calibri Light | Inter, Calibri        |
  | Luxe / élégant / mariage    | Playfair Display,    | Lato, Inter           |
  |                             | Cormorant, Bodoni    |                       |
  | Deuil / classique / formel  | Cormorant, EB Garamond | Lato, Source Serif  |
  | Festif / jeune / dynamique  | Bebas Neue, Anton,   | Inter, Lato           |
  |                             | Oswald               |                       |
  | Artistique / créatif        | Caveat, Pacifico,    | Inter, Lato           |
  |                             | Permanent Marker     |                       |
  | Tech / startup              | Inter, Space Grotesk | Inter, Source Sans    |
  | Officiel / institutionnel   | Lato, Source Sans    | Lato, Source Sans     |

  Limite : MAX 2 familles différentes par visuel (1 titre + 1 corps).
  Sauf intention créative explicite (festival, art) : alors 3 max.

  ─── GRAS, ITALIQUE, MAJUSCULES ──────────────────────────────────────────
  - GRAS (font_weight ≥ 700) : pour le mot/concept-clé d'une phrase, le
    titre, le label de KPI. Pas tout en gras.
  - ITALIQUE (italic=true) : pour citations, mots étrangers, attributions,
    "Fait à Yaoundé le", légendes de figure. Pas dans le corps narratif.
  - UPPERCASE (uppercase=true) : pour overlines, labels de section,
    "PRÉSENTE", "INVITATION", mentions courtes. Letter-spacing élargi
    (0.08-0.20em) pour aération. Pas pour titres > 12 mots (illisible).
  - SOULIGNÉ (underline=true) : très rare, sauf hyperliens ou intention
    d'emphase délibérée.

  ─── COULEUR DE TEXTE ─────────────────────────────────────────────────────
  - Contraste fond/texte ≥ 4.5:1 pour corps (WCAG AA). ≥ 3:1 pour titres ≥ 18pt.
  - Cohérence : max 3 couleurs de texte par visuel (titre, corps, accent).
  - Accent = couleur primaire de la palette pour mots-clés / liens / dates.

  ─── EFFETS ──────────────────────────────────────────────────────────────
  - line_height : 1.1-1.3 pour titres, 1.4-1.6 pour corps de texte long.
  - letter_spacing_em : 0.05-0.15 pour MAJUSCULES, -0.02 à 0 pour gros titres
    (resserrer le crénage), 0 pour corps normal.
  - shadow : SEULEMENT si texte sur image/fond bruité (visibilité). Pas sur
    fond uni où ça paraît cheap.
  - transform.rotation_deg : 0 par défaut. -3 à 5° pour effet créatif léger
    (faire-part, festival). Pas de rotation pour corporate.

SORTIE : JSON STRICT conforme au schéma indiqué. Pas de markdown, pas de prose.
"""


_LANGUE_INFOS = {
    "fr": {"nom": "français",  "direction": "ltr", "polices_priorisees": ["Inter", "Calibri", "Lato"]},
    "en": {"nom": "anglais",   "direction": "ltr", "polices_priorisees": ["Inter", "Helvetica", "Arial"]},
    "es": {"nom": "espagnol",  "direction": "ltr", "polices_priorisees": ["Inter", "Lato"]},
    "pt": {"nom": "portugais", "direction": "ltr", "polices_priorisees": ["Inter", "Lato"]},
    "de": {"nom": "allemand",  "direction": "ltr", "polices_priorisees": ["Inter", "Calibri"]},
    "it": {"nom": "italien",   "direction": "ltr", "polices_priorisees": ["Inter", "Lato"]},
    "ar": {"nom": "arabe",     "direction": "rtl", "polices_priorisees": ["Noto Sans Arabic", "Amiri", "Cairo"]},
    "zh": {"nom": "chinois",   "direction": "ltr", "polices_priorisees": ["Noto Sans SC", "PingFang SC"]},
    "ja": {"nom": "japonais",  "direction": "ltr", "polices_priorisees": ["Noto Sans JP", "Hiragino"]},
    "ru": {"nom": "russe",     "direction": "ltr", "polices_priorisees": ["Inter", "Liberation Sans"]},
    "hi": {"nom": "hindi",     "direction": "ltr", "polices_priorisees": ["Noto Sans Devanagari"]},
    "sw": {"nom": "swahili",   "direction": "ltr", "polices_priorisees": ["Inter", "Lato"]},
    "ha": {"nom": "haoussa",   "direction": "ltr", "polices_priorisees": ["Inter", "Noto Sans"]},
    "wo": {"nom": "wolof",     "direction": "ltr", "polices_priorisees": ["Inter", "Lato"]},
    "ln": {"nom": "lingala",   "direction": "ltr", "polices_priorisees": ["Inter", "Lato"]},
    "am": {"nom": "amharique", "direction": "ltr", "polices_priorisees": ["Noto Sans Ethiopic"]},
    "tr": {"nom": "turc",      "direction": "ltr", "polices_priorisees": ["Inter", "Lato"]},
}


def construire_prompt_user(
    brief: str,
    page_w_mm: float,
    page_h_mm: float,
    bleed_mm: float = 3.0,
    medias: Optional[list[dict]] = None,
    brand_kit: Optional[dict] = None,
    inspiration: Optional[str] = None,
    langue: str = "fr",
    tokens: Optional[DesignTokens] = None,
) -> str:
    """
    Compose le prompt user complet.

    `medias`     : liste de manifests produits par manifest_image().
    `brand_kit`  : {couleur_primaire_hex, couleur_accent_hex, polices: {titre, corps}, ...}
    `inspiration`: brief de style libre ("style minimaliste japonais", "deuil classique européen").
    `langue`     : code ISO de la langue cible pour TOUS les textes du visuel
                   (fr/en/es/pt/de/ar/zh/ja/ru/hi/sw/ha/wo/ln/am/tr).
    """
    medias_str = ""
    if medias:
        medias_str = "\n\nMÉDIAS UPLOADÉS DISPONIBLES :\n" + json.dumps(medias, ensure_ascii=False, indent=2)
    brand_str = ""
    if brand_kit:
        brand_str = "\n\nCHARTE DE MARQUE (à respecter strictement) :\n" + json.dumps(brand_kit, ensure_ascii=False, indent=2)
    inspi_str = ""
    if inspiration:
        inspi_str = f"\n\nINSPIRATION STYLISTIQUE : {inspiration}"

    # DesignTokens — système design pré-calculé (Phase 0). Le LLM placement
    # consomme ces tokens comme contraintes au lieu de tout redéfinir.
    tokens_str = ""
    if tokens is not None:
        tokens_str = (
            "\n\nDESIGN SYSTEM PRÉ-CALCULÉ (contrainte absolue — utilise CES "
            "valeurs pour chaque texte, ne re-calcule pas les tailles/polices/"
            "line_height/letter_spacing : pioche dans typo_scale selon le rôle "
            "sémantique de chaque texte, applique palette et font families) :\n"
            + json.dumps(tokens.model_dump(), ensure_ascii=False, indent=2)
        )

    # Langue cible : injection explicite des contraintes typographiques
    info_l = _LANGUE_INFOS.get(langue, _LANGUE_INFOS["fr"])
    polices_pref = ", ".join(info_l["polices_priorisees"])
    rtl_note = ""
    if info_l["direction"] == "rtl":
        rtl_note = (
            "\n  • Direction RTL (droite→gauche) : align='right' pour les blocs "
            "de paragraphe, mais align='center' pour titres centrés sur la page. "
            "Le texte arabe lui-même est rendu correctement par PIL/HarfBuzz."
        )
    langue_str = (
        f"\n\nLANGUE DES TEXTES SUR LE VISUEL : {info_l['nom']} (code ISO : {langue})\n"
        f"  • TOUS les textes (titres, sous-titres, corps, légendes, mentions) "
        f"DOIVENT être en {info_l['nom']}. Pas de mélange.\n"
        f"  • Polices priorisées (par ordre de préférence selon la couverture "
        f"glyphes) : {polices_pref}. Choisis font_family parmi cette liste.{rtl_note}"
    )

    return f"""BRIEF UTILISATEUR :
\"\"\"{brief}\"\"\"

PAGE :
  - Largeur  : {page_w_mm} mm (trim, sans bleed)
  - Hauteur  : {page_h_mm} mm
  - Bleed    : {bleed_mm} mm (zone de fond perdu pour découpe imprimeur)
  - Origine  : top-left, axe Y descendant (comme CSS){langue_str}
{tokens_str}{medias_str}{brand_str}{inspi_str}

SCHÉMA JSON ATTENDU :
{{
  "page_w_mm": {page_w_mm},
  "page_h_mm": {page_h_mm},
  "bleed_mm": {bleed_mm},
  "background": {{
    "color": {{"r": 255, "g": 255, "b": 255, "a": 1.0}},
    "gradient": null,
    "image_media_ref": null
  }},
  "items": [
    {{
      "kind": "image",
      "media_ref": "session:abc",
      "target_zone": {{"x": 30, "y": 25, "w": 60, "h": 60}},
      "fit_mode": "smart_focus",
      "focal_point_x": 0.5, "focal_point_y": 0.25,
      "mask_shape": "circle",
      "mask_extra": {{}},
      "border_mm": 0.8,
      "border_color": {{"r": 200, "g": 200, "b": 200, "a": 1.0}},
      "shadow": {{"offset_x_mm": 0.5, "offset_y_mm": 0.8, "blur_mm": 2.0,
                 "color": {{"r": 0, "g": 0, "b": 0, "a": 0.25}}}},
      "z_index": 5
    }},
    {{
      "kind": "text",
      "text": "Marie NGONO",
      "bbox": {{"x": 15, "y": 95, "w": 120, "h": 18}},
      "font_family": "Cormorant",
      "font_size_pt": 32,
      "font_weight": 600,
      "italic": false,
      "color": {{"r": 30, "g": 40, "b": 60, "a": 1.0}},
      "align": "center",
      "vertical_align": "middle",
      "line_height": 1.15,
      "letter_spacing_em": 0.02,
      "uppercase": false,
      "z_index": 10
    }},
    {{
      "kind": "shape",
      "shape": "rect",
      "bbox": {{"x": 50, "y": 120, "w": 50, "h": 0.4}},
      "fill": {{"r": 180, "g": 150, "b": 90, "a": 1.0}},
      "stroke": null,
      "z_index": 1
    }}
  ]
}}

RÈGLES STRICTES :
- Tu DOIS placer TOUS les médias uploadés (ne pas en ignorer).
- Tu DOIS respecter la palette de marque si fournie (couleurs, polices).
- bbox.x + bbox.w ≤ page_w_mm + bleed_mm (pas de débordement).
- bbox.y + bbox.h ≤ page_h_mm + bleed_mm.
- z_index : background=0, formes décoratives=1-3, images=5-8, textes=10-15.
- target_zone.x doit être ≥ 5mm de marge intérieure SAUF si fond full-bleed
  intentionnel (auquel cas la zone déborde jusqu'à -bleed_mm).

Réponds UNIQUEMENT en JSON valide, sans markdown, sans préambule.
"""


# ═══════════════════════════════════════════════════════════════════════
# Phase 0 — Analyse pré-placement : calcule les DesignTokens
# ═══════════════════════════════════════════════════════════════════════

PROMPT_TOKENS_SYSTEM = """Tu es DIRECTEUR ARTISTIQUE et SYSTÈME DESIGN MANAGER.

Ton rôle (phase préparatoire AVANT le placement des éléments) : analyser
le brief utilisateur, les dimensions de la page, les médias uploadés, la
marque (si fournie), la langue cible, puis produire un SYSTÈME DE DESIGN
COMPLET et COHÉRENT (DesignTokens JSON) qui sera utilisé en INPUT par le
LLM de placement.

Tu décides :
  1. PALETTE — 2 à 6 couleurs harmoniques cohérentes avec le registre,
     le brief, et la charte si fournie. Première = primaire, dernière = la
     plus discrète. Tu identifies explicitement : couleur_fond,
     couleur_texte_principal, couleur_accent.

  2. POLICES — UN couple titre/corps adapté au registre :
     • Sobre corporate / institutionnel → Inter ou Calibri Light + Inter/Lato
     • Luxe / élégant / mariage → Playfair Display ou Cormorant + Lato
     • Deuil / classique / formel → Cormorant ou EB Garamond + Lato
     • Festif / jeune / dynamique → Bebas Neue, Anton ou Oswald + Inter
     • Artistique / créatif → Caveat, Pacifico ou Permanent Marker + Inter
     • Tech / startup → Inter ou Space Grotesk + Source Sans
     Tu peux utiliser la même famille pour les 2 si tu choisis Inter
     (famille très versatile).

  3. ÉCHELLE TYPO — calcule chaque niveau (display, h1, h2, h3, body,
     caption, overline) selon la DIAGONALE de la page. Formule :
       diag_mm = √(page_w_mm² + page_h_mm²)
       display.font_size_pt = round(0.07 × diag_mm × 2.83)
       h1      = 0.045 × diag_mm × 2.83
       h2      = 0.025 × diag_mm × 2.83
       h3      = 0.018 × diag_mm × 2.83
       body    = 0.011 × diag_mm × 2.83
       caption = 0.0075 × diag_mm × 2.83
       overline= 0.009 × diag_mm × 2.83 (uppercase letter-spaced)
     N'INCLUS PAS les niveaux non pertinents pour le format : carte de
     visite n'a pas de display ni h1 (trop gros, le plus haut sera h2 ou h3).
     Affiche A0 a tous les niveaux. Adapte intelligemment.

  4. line_height par niveau — INTELLIGENT selon le rôle ET la nature du
     visuel :
     • Display / H1 → 1.05-1.15 (resserré, impact)
     • H2 / H3 → 1.2-1.3 (équilibre)
     • Body → 1.45-1.65 (lecture confortable). Sur visuel dense → 1.4 max.
       Sur visuel aéré minimaliste → 1.6-1.8 (respiration).
     • Caption / Overline → 1.3-1.5
     Adapte aussi : faire-part deuil = ligne plus aérée (1.6+) pour
     respect ; flyer commercial = compact (1.3-1.4) ; livre photo = très
     aéré (1.7).

  5. letter_spacing par niveau :
     • Display / H1 grand → -0.02 à 0 (resserrer le crénage)
     • Body → 0 par défaut
     • Overline / labels UPPERCASE → 0.08 à 0.20 em
     • Si registre luxe → légèrement plus aéré partout (+0.01-0.03)

  6. REGISTRE global (sobre_corporate | luxe_elegant | deuil_classique |
     festif_jeune | artistique | tech_startup | institutionnel |
     minimaliste | dense_informatif).

  7. DENSITÉ visuelle visée (minimaliste | aere | equilibre | dense | sature).

  8. FORMES DÉCORATIVES autorisées selon le registre :
     • sobre_corporate → ['rect','rounded_rect','circle']
     • luxe_elegant → ['rect','rounded_rect','circle','ellipse','diamond']
     • deuil_classique → ['rect','circle','ellipse']
     • festif_jeune → ['blob','star','polygon','hexagon','rounded_rect']
     • artistique → ['blob','polygon','star','hexagon','diamond']
     • tech_startup → ['rect','rounded_rect','hexagon','polygon']
     • minimaliste → ['rect','circle']
     Limite la palette de formes : ça aide à garder la cohérence visuelle.

SORTIE JSON STRICT (DesignTokens) :
{
  "palette": [{"r":..,"g":..,"b":..,"a":1.0}, ...],
  "couleur_fond": {"r":..,"g":..,"b":..,"a":1.0},
  "couleur_texte_principal": {"r":..,"g":..,"b":..,"a":1.0},
  "couleur_accent": {"r":..,"g":..,"b":..,"a":1.0},
  "font_family_titre": "Cormorant",
  "font_family_corps": "Lato",
  "typo_scale": [
    {"nom":"h1","font_size_pt":32,"font_weight":700,"line_height":1.15,"letter_spacing_em":-0.01,"uppercase":false},
    {"nom":"h2","font_size_pt":18,"font_weight":600,"line_height":1.3,"letter_spacing_em":0,"uppercase":false},
    {"nom":"body","font_size_pt":11,"font_weight":400,"line_height":1.55,"letter_spacing_em":0,"uppercase":false},
    {"nom":"caption","font_size_pt":8,"font_weight":500,"line_height":1.4,"letter_spacing_em":0.02,"uppercase":false},
    {"nom":"overline","font_size_pt":9,"font_weight":600,"line_height":1.2,"letter_spacing_em":0.15,"uppercase":true}
  ],
  "registre": "deuil_classique",
  "densite_visuelle": "aere",
  "formes_decoratives_autorisees": ["rect","circle","ellipse"],
  "raisonnement": "Faire-part deuil A5 portrait : Cormorant pour la dignité, palette gris-bleu sombre, typo aérée respect. Pas de display (page trop petite). Formes uniquement géométriques sobres."
}

Réponds UNIQUEMENT en JSON valide, sans markdown.
"""


async def analyser_design_tokens(
    brief: str,
    page_w_mm: float,
    page_h_mm: float,
    medias: Optional[list[dict]] = None,
    brand_kit: Optional[dict] = None,
    langue: str = "fr",
    inspiration: Optional[str] = None,
    modele: str = "haiku",
) -> tuple[Optional[DesignTokens], dict]:
    """
    Phase 0 — Analyse préalable qui produit le DesignTokens à injecter dans
    la phase de placement.

    Retourne (tokens, usage_llm) — le caller débite usage via debiter_llm.
    Modèle par défaut : Haiku (analyse rapide ~600 tokens out, marge respectée).
    """
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire

    forcer_modele = {
        "sonnet": ModelePrioritaire.CLAUDE_SONNET,
        "opus":   ModelePrioritaire.CLAUDE_OPUS,
        "haiku":  ModelePrioritaire.CLAUDE_HAIKU,
    }.get(modele, ModelePrioritaire.CLAUDE_HAIKU)

    info_l = _LANGUE_INFOS.get(langue, _LANGUE_INFOS["fr"])
    medias_str = json.dumps(medias or [], ensure_ascii=False)[:2000]
    brand_str = json.dumps(brand_kit or {}, ensure_ascii=False)[:1500] if brand_kit else "(aucune)"
    insp_str = inspiration or "(aucune)"

    diag_mm = (page_w_mm ** 2 + page_h_mm ** 2) ** 0.5

    user_prompt = (
        f"BRIEF :\n\"\"\"{brief}\"\"\"\n\n"
        f"PAGE : {page_w_mm} × {page_h_mm} mm   (diagonale : {diag_mm:.0f} mm)\n"
        f"LANGUE CIBLE TEXTES : {info_l['nom']} (ISO {langue}), "
        f"polices recommandées pour le script : {', '.join(info_l['polices_priorisees'])}\n"
        f"INSPIRATION : {insp_str}\n"
        f"CHARTE MARQUE : {brand_str}\n"
        f"MÉDIAS UPLOADÉS : {medias_str}\n\n"
        f"Calcule l'échelle typo SELON la diagonale ({diag_mm:.0f} mm). "
        f"Inclus uniquement les niveaux utiles pour ce format (carte petite "
        f"→ pas de display ; affiche grande → display obligatoire).\n"
        f"Retourne le JSON DesignTokens."
    )

    try:
        rep = await ia_client.appeler(
            prompt=user_prompt,
            systeme=PROMPT_TOKENS_SYSTEM,
            mode=ModeIA.PRECISION,
            forcer_modele=forcer_modele,
            json_attendu=True,
            # DesignTokens reste compact mais le raisonnement + 7 niveaux typo
            # détaillés peuvent atteindre 1500-2000 tokens. 2500 = marge safe.
            max_tokens_override=2500,
        )
    except Exception as e:
        logger.warning(f"[DesignTokens] LLM échec : {e}")
        return None, _empty_usage()

    raw = (rep.contenu or "").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return None, _usage_from_rep(rep)
        try:
            data = json.loads(m.group())
        except Exception:
            return None, _usage_from_rep(rep)

    try:
        tokens = DesignTokens(**data)
    except Exception as e:
        logger.warning(f"[DesignTokens] Validation Pydantic échouée : {e}")
        return None, _usage_from_rep(rep)
    return tokens, _usage_from_rep(rep)


# ═══════════════════════════════════════════════════════════════════════
# Appel LLM
# ═══════════════════════════════════════════════════════════════════════

async def generer_placement_plan(
    brief: str,
    page_w_mm: float,
    page_h_mm: float,
    bleed_mm: float = 3.0,
    medias: Optional[list[dict]] = None,
    brand_kit: Optional[dict] = None,
    inspiration: Optional[str] = None,
    modele: str = "sonnet",
    langue: str = "fr",
    tokens: Optional[DesignTokens] = None,
) -> tuple[Optional[PlacementPlan], dict]:
    """
    Phase 1 — Appelle le LLM et retourne (PlacementPlan, usage_llm).

    `tokens` : DesignTokens issu de Phase 0 (analyser_design_tokens). Si fourni,
               le LLM placement les UTILISE comme contraintes au lieu de tout
               re-calculer → cohérence renforcée + tokens moins gaspillés.
    """
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire

    forcer_modele = {
        "sonnet": ModelePrioritaire.CLAUDE_SONNET,
        "opus":   ModelePrioritaire.CLAUDE_OPUS,
        "haiku":  ModelePrioritaire.CLAUDE_HAIKU,
    }.get(modele, ModelePrioritaire.CLAUDE_SONNET)

    user_prompt = construire_prompt_user(
        brief, page_w_mm, page_h_mm, bleed_mm,
        medias=medias, brand_kit=brand_kit, inspiration=inspiration,
        langue=langue, tokens=tokens,
    )

    try:
        rep = await ia_client.appeler(
            prompt=user_prompt,
            systeme=PROMPT_SYSTEM,
            mode=ModeIA.PRECISION,
            forcer_modele=forcer_modele,
            json_attendu=True,
            # Visuel complexe (livret 8-16 items texte/image/forme) = JSON
            # pouvant atteindre 8-10k tokens. 12000 = marge safe. Sonnet 4.6
            # supporte jusqu'à 64k tokens output.
            max_tokens_override=12000,
        )
    except Exception as e:
        logger.error(f"[LLMPlacement] Appel LLM échoué : {e}")
        return None, _empty_usage()

    usage = _usage_from_rep(rep)
    raw = (rep.contenu or "").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            logger.warning("[LLMPlacement] Pas de JSON parseable dans la réponse")
            return None, usage
        try:
            data = json.loads(m.group())
        except Exception as e:
            logger.warning(f"[LLMPlacement] JSON malformé : {e}")
            return None, usage

    try:
        plan = PlacementPlan(**data)
    except Exception as e:
        logger.warning(f"[LLMPlacement] Validation Pydantic échouée : {e}")
        data.setdefault("page_w_mm", page_w_mm)
        data.setdefault("page_h_mm", page_h_mm)
        data.setdefault("bleed_mm", bleed_mm)
        data.setdefault("items", [])
        try:
            plan = PlacementPlan(**data)
        except Exception as e2:
            logger.error(f"[LLMPlacement] Auto-fix échoué : {e2}")
            return None, usage
    return plan, usage


# ═══════════════════════════════════════════════════════════════════════
# Boucle auto-critique LLM Vision (audit + révision avant rendu final)
# ═══════════════════════════════════════════════════════════════════════

PROMPT_REVISION_SYSTEM = """Tu es DIRECTEUR ARTISTIQUE SENIOR au niveau cabinet
top-tier (Adobe / Pentagram / Sagmeister). Tu reçois UN VISUEL DÉJÀ RENDU à
auditer en VISION (image PNG attachée) AVEC le PlacementPlan JSON qui l'a
produit et le BRIEF INITIAL utilisateur. Ton job : repérer les défauts qu'un
humain remarquerait au premier coup d'œil ET les écarts par rapport à
l'intention exprimée dans le brief, puis proposer un plan corrigé.

═══════════════════════════════════════════════════════════════════════
GRILLE D'AUDIT — 5 axes critiques (chaque axe noté de 0 à 10)
═══════════════════════════════════════════════════════════════════════

1) CONFORMITÉ AU BRIEF (le visuel répond-il à l'intention ?)
   - Ton/registre demandé respecté (formel / chaleureux / festif / sobre /
     minimaliste / luxe / corporate / artistique) ?
   - Tous les contenus exigés présents (titre, sous-titre, mention spéciale,
     CTA, contact, date, etc.) ? Aucun ajout intempestif ?
   - Format/orientation cohérent avec l'usage cité (carte de visite, flyer,
     affiche, faire-part, etc.) ?
   - Si brand_kit fourni : palette + polices RESPECTÉES (pas de couleur
     hors charte).

2) COULEURS — cohérence et pertinence
   - Palette harmonique (max 3-4 couleurs dominantes, gammes complémentaires
     ou analogues). Pas d'arc-en-ciel chaotique.
   - Couleurs sémantiquement PERTINENTES (deuil = sombre/sobre ;
     mariage = chaud/élégant ; corporate = sobre + accent vif ;
     festif = vif + contrasté ; luxe = noir/or/blanc).
   - Contraste texte/fond ≥ 4.5:1 (WCAG AA) pour le corps de texte,
     ≥ 3:1 pour les titres ≥ 18pt.
   - Pas de couleur saturée à 100% sur fond saturé à 100% (vibration
     fatigante).
   - Cohérence entre fond, texte, accents, illustrations (mêmes températures
     ou contraste assumé).

3) DISPOSITION DES ÉLÉMENTS — composition graphique
   - Hiérarchie visuelle CLAIRE : 1 dominant, 2-3 secondaires, reste discret.
   - Alignement implicite : centres optiques alignés, axes verticaux/
     horizontaux respectés (grille mentale visible).
   - Marges intérieures cohérentes (8-15mm depuis le trim sauf
     full-bleed assumé). Pas de respiration cassée.
   - Équilibre des masses (densité non-concentrée sur un côté sauf
     intention asymétrique délibérée).
   - Espacement régulier entre éléments répétés.
   - Aucun chevauchement non-intentionnel.

4) COMPLEXITÉ GÉOMÉTRIQUE vs BRIEF
   - Brief "minimaliste / sobre / épuré" → 3-5 éléments max, beaucoup de
     blanc, formes simples, pas d'ornement.
   - Brief "riche / festif / décoré" → ornements présents, palette vivante,
     formes variées (étoiles, blobs, polygons décoratifs).
   - Brief "corporate / institutionnel" → formes rect/rounded_rect, palette
     contenue, pas de forme organique (blob/star inappropriés).
   - Brief "artistique / créatif" → asymétrie, rotations, blobs, mix de
     formes audacieux.
   - Si la complexité visuelle ne correspond PAS au registre demandé,
     c'est un défaut MAJEUR.

5) TYPOGRAPHIE — hiérarchie + cohérence + proportion vs page
   - Hiérarchie visible : titre principal ≥ 2.5× la taille du corps de texte,
     sous-titre intermédiaire. Pas 2 textes au même niveau sauf symétrie
     intentionnelle.
   - TAILLES PROPORTIONNELLES À LA PAGE : un titre de 60pt sur une carte de
     visite 90×55mm est aberrant ; un titre de 14pt sur une affiche A0 est
     ridiculement petit. Calcule la diagonale = √(W²+H²) et vérifie que la
     plus grande taille pt est ≈ 5-9% de la diagonale en mm pour les supports
     de communication, plus petit pour formats utilitaires. Tailles totalement
     hors proportion (titre < 2% diag OU > 12% diag sans intention héros) =
     défaut MAJEUR.
   - font_weight cohérent : titres ≥ 700, corps 400, captions 400-500.
     Tout en bold = défaut critique (perte de hiérarchie).
   - Max 2 familles de polices (1 titre + 1 corps), 3 max si registre
     artistique. Plus = chaos typographique.
   - Police adaptée au registre (Cormorant pour deuil/luxe, Bebas Neue pour
     festif, Inter pour corporate). Cormorant sur un flyer techno = défaut.
   - GRAS/ITALIQUE/MAJUSCULES utilisés à bon escient :
     • Gras = emphase ponctuelle, pas sur le corps de texte entier.
     • Italique = citation/mot étranger/attribution, pas dans le narratif.
     • Majuscules = overlines courts, pas titres > 12 mots.
   - Letter-spacing élargi (0.08-0.20em) sur UPPERCASE. Resserré (-0.02 à 0)
     sur très gros titres (> 5% diagonale). Défaut 0 sur corps.
   - line-height (INTERLIGNE) — INTELLIGENT selon le rôle ET la densité du
     visuel. Vérifie que :
     • Display / H1 : 1.05-1.15 (resserré, impact)
     • H2 / H3 : 1.2-1.3
     • Body : 1.45-1.65 (lecture confortable, jamais 1.0). Sur visuel dense
       1.4 OK, sur visuel aéré 1.6-1.8 (respiration).
     • Faire-part deuil → 1.6+ (respect), flyer commercial → 1.3-1.4
       (compact), livre photo → 1.7+ (aération éditoriale).
   - SI les DesignTokens étaient fournis (typo_scale), vérifie que CHAQUE
     texte a bien utilisé un niveau de la typo_scale (pas une taille
     inventée). Tout texte hors scale = défaut majeur de cohérence.

6) DÉTAILS TECHNIQUES
   - Texte tronqué (ne rentre pas dans sa bbox), débordement, chevauchement.
   - Image mal cadrée (sujet coupé, visage tronqué, focal_point décalé).
   - Police inadaptée au script (Cormorant pour arabe → glyphes manquants).
   - Rotation/ombre/effet excessif ou absent là où il manque pour la
     lisibilité (texte sur image → ombre obligatoire).
   - Forme du masque adaptée au contenu (portrait = circle, paysage = rect,
     logo = rect aligné coin).
   - Bordures et stroke cohérents.

═══════════════════════════════════════════════════════════════════════
SORTIE JSON STRICT
═══════════════════════════════════════════════════════════════════════
{
  "verdict": "ok" | "ameliorations_mineures" | "refonte_necessaire",
  "score_qualite_sur_10": 7.5,
  "scores_par_axe": {
    "conformite_brief": 8.5,
    "couleurs": 7.0,
    "disposition": 6.5,
    "complexite_geometrique": 8.0,
    "typographie": 7.5,
    "details_techniques": 7.5
  },
  "issues": [
    {"severite": "critique|majeur|mineur",
     "axe": "couleurs|disposition|complexite|conformite|details",
     "type": "texte_tronque|contraste_insuffisant|...",
     "item_index": 2,
     "description": "Description précise du défaut",
     "correctif": "Action concrète : changer field X de A à B, OU élargir bbox.w"}
  ],
  "synthese": "1-2 phrases de feedback global qualité",
  "plan_revise": null OU {PlacementPlan complet avec corrections}
}

Si verdict='ok' (score ≥ 8 ET aucune issue critique) → plan_revise=null.
Si verdict='ameliorations_mineures' (score 6-8 OU issues mineures) →
  fournis plan_revise corrigé.
Si verdict='refonte_necessaire' (score < 6 OU issues critiques) → fournis
  plan_revise complètement repensé.

⚠ NE PAS halluciner des défauts pour justifier un re-render. Sois HONNÊTE :
si c'est bon, dis-le et score haut.
"""


async def auditer_et_reviser_placement(
    plan: PlacementPlan,
    png_bytes: bytes,
    brief: str,
    medias_manifest: Optional[list[dict]] = None,
    modele: str = "sonnet",
    tokens: Optional[DesignTokens] = None,
) -> tuple[Optional["RevisionResult"], dict]:
    """
    Phase 3 (optionnelle) : audit visuel du rendu par Sonnet Vision puis
    proposition de plan révisé si défauts détectés.

    Retourne un RevisionResult avec verdict + issues + plan_revise (ou None).
    """
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire
    import base64

    forcer_modele = {
        "sonnet": ModelePrioritaire.CLAUDE_SONNET,
        "opus":   ModelePrioritaire.CLAUDE_OPUS,
    }.get(modele, ModelePrioritaire.CLAUDE_SONNET)

    tokens_str = ""
    if tokens is not None:
        tokens_str = (
            "\n\nDESIGN TOKENS qui ont été appliqués (palette/typo/registre/"
            "densité — vérifie que le rendu les respecte fidèlement) :\n"
            + json.dumps(tokens.model_dump(), ensure_ascii=False)[:2500]
        )
    user_prompt = (
        f"BRIEF UTILISATEUR INITIAL :\n\"\"\"{brief}\"\"\"\n\n"
        f"PLACEMENT_PLAN qui a produit le visuel ci-joint :\n"
        f"{json.dumps(plan.model_dump(), ensure_ascii=False)[:6000]}{tokens_str}\n\n"
        f"MÉDIAS UPLOADÉS :\n"
        f"{json.dumps(medias_manifest or [], ensure_ascii=False)[:2000]}\n\n"
        f"Audite le visuel attaché et retourne le JSON de révision."
    )

    # Sonnet supporte les images en input via 'images' param du ia_client.
    # Si l'implémentation locale ne supporte pas, fallback texte-only avec
    # description sommaire (mais qualité dégradée).
    image_b64 = base64.b64encode(png_bytes).decode()
    try:
        rep = await ia_client.appeler(
            prompt=user_prompt,
            systeme=PROMPT_REVISION_SYSTEM,
            mode=ModeIA.PRECISION,
            forcer_modele=forcer_modele,
            json_attendu=True,
            # L'audit retourne {verdict, scores, issues, synthese} + EN OPTION
            # un plan_revise complet (~8k tokens). 12000 = marge safe.
            max_tokens_override=12000,
            images=[{"data": image_b64, "mime": "image/png"}],
        )
    except TypeError:
        # ia_client ne supporte pas images= → fallback sans vision
        logger.info("[Revision] ia_client.appeler ne supporte pas images, audit texte-only")
        try:
            rep = await ia_client.appeler(
                prompt=user_prompt + "\n\n[NOTE: rendu visuel non transmis, audit basé "
                                       "uniquement sur le PlacementPlan JSON]",
                systeme=PROMPT_REVISION_SYSTEM,
                mode=ModeIA.PRECISION,
                forcer_modele=forcer_modele,
                json_attendu=True,
                max_tokens_override=12000,
            )
        except Exception as e:
            logger.warning(f"[Revision] LLM fallback texte échoué : {e}")
            return None, _empty_usage()
    except Exception as e:
        logger.warning(f"[Revision] LLM échoué : {e}")
        return None, _empty_usage()

    usage = _usage_from_rep(rep)
    raw = (rep.contenu or "").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return None, usage
        try:
            data = json.loads(m.group())
        except Exception:
            return None, usage

    verdict = data.get("verdict", "ok")
    issues = data.get("issues", [])
    score = float(data.get("score_qualite_sur_10", 5.0))
    scores_par_axe = data.get("scores_par_axe", {}) or {}
    synthese = str(data.get("synthese", "") or "")[:500]
    plan_revise = None
    raw_revise = data.get("plan_revise")
    if isinstance(raw_revise, dict):
        try:
            plan_revise = PlacementPlan(**raw_revise)
        except Exception as e:
            logger.warning(f"[Revision] plan_revise invalide : {e}")
            plan_revise = None

    result = RevisionResult(
        verdict=verdict, score=score,
        scores_par_axe=scores_par_axe, issues=issues, synthese=synthese,
        plan_revise=plan_revise,
    )
    return result, usage


class RevisionResult(BaseModel):
    """Résultat d'un audit Vision LLM."""
    verdict: str = Field(...,
        description="ok | ameliorations_mineures | refonte_necessaire")
    score: float = Field(..., ge=0.0, le=10.0)
    scores_par_axe: dict = Field(default_factory=dict,
        description="{conformite_brief, couleurs, disposition, complexite_geometrique, details_techniques}")
    issues: list[dict] = Field(default_factory=list)
    synthese: str = ""
    plan_revise: Optional[PlacementPlan] = None


# ═══════════════════════════════════════════════════════════════════════
# Audit générique : pour TOUT pipeline visuel (catalog mono, multi-page,
# bulk, etc.) — pas seulement /geometric-placement. Ne renvoie PAS de plan
# révisé (les pipelines catalog ne sont pas re-renderable depuis un plan
# Pydantic), retourne juste une note qualité + suggestions textuelles.
# ═══════════════════════════════════════════════════════════════════════

PROMPT_AUDIT_GENERIQUE = """Tu es DIRECTEUR ARTISTIQUE SENIOR. Audite ce visuel
PNG vs le brief utilisateur initial. Évalue 4 axes : conformité au brief
(intention/contenu/format), couleurs (cohérence + pertinence + contraste WCAG),
disposition (hiérarchie + alignement + équilibre), complexité géométrique
(adaptation au registre demandé : minimaliste/festif/corporate/luxe/artistique).

Sortie JSON strict, AUCUN markdown :
{
  "score_qualite_sur_10": 8.0,
  "scores_par_axe": {"conformite_brief": 8, "couleurs": 7.5,
                     "disposition": 8, "complexite": 9},
  "verdict": "excellent" | "bon" | "acceptable" | "ameliorations_recommandees" | "refonte_necessaire",
  "points_forts": ["...", "..."],
  "points_faibles": [{"axe": "couleurs", "description": "...",
                       "suggestion": "..."}],
  "synthese": "1-2 phrases courtes feedback global"
}

Sois honnête. Note objectivement vs un standard "agence pro".
"""


async def auditer_visuel_generique(
    png_bytes: bytes,
    brief: str,
    langue: str = "fr",
    brand_kit: Optional[dict] = None,
    contexte: Optional[str] = None,
    modele: str = "sonnet",
) -> tuple[Optional[dict], dict]:
    """
    Audite n'importe quel visuel PNG (peu importe le pipeline qui l'a produit)
    contre le brief utilisateur initial. Retourne un dict de qualité ou None
    si l'audit a échoué.

    Idéal pour les pipelines catalog (/generer mono-page, /generer-auto multi)
    où il n'y a pas de PlacementPlan structuré à réviser : on retourne juste
    une NOTE QUALITÉ + SUGGESTIONS pour information à l'utilisateur (qui peut
    décider de relancer une variante s'il n'est pas satisfait).
    """
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire
    import base64

    forcer_modele = {
        "sonnet": ModelePrioritaire.CLAUDE_SONNET,
        "opus":   ModelePrioritaire.CLAUDE_OPUS,
    }.get(modele, ModelePrioritaire.CLAUDE_SONNET)

    brand_str = ""
    if brand_kit:
        brand_str = f"\n\nCHARTE DE MARQUE : {json.dumps(brand_kit, ensure_ascii=False)[:1500]}"
    ctx_str = f"\n\nCONTEXTE ADDITIONNEL : {contexte}" if contexte else ""

    user_prompt = (
        f"BRIEF UTILISATEUR :\n\"\"\"{brief}\"\"\"\n\n"
        f"LANGUE CIBLE DES TEXTES : {langue}{brand_str}{ctx_str}\n\n"
        f"Audite le visuel PNG attaché et retourne le JSON de qualité."
    )

    image_b64 = base64.b64encode(png_bytes).decode()
    try:
        rep = await ia_client.appeler(
            prompt=user_prompt,
            systeme=PROMPT_AUDIT_GENERIQUE,
            mode=ModeIA.PRECISION,
            forcer_modele=forcer_modele,
            json_attendu=True,
            # Audit court (verdict + scores + 4-6 points) ~1500 tokens.
            # 2500 = marge safe pour suggestions détaillées.
            max_tokens_override=2500,
            images=[{"data": image_b64, "mime": "image/png"}],
        )
    except TypeError:
        # Sans vision : retourne None (le caller saura ignorer)
        logger.info("[AuditGenerique] ia_client ne supporte pas images=, audit skip")
        return None, _empty_usage()
    except Exception as e:
        logger.warning(f"[AuditGenerique] LLM échec : {e}")
        return None, _empty_usage()

    usage = _usage_from_rep(rep)
    raw = (rep.contenu or "").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return None, usage
        try:
            data = json.loads(m.group())
        except Exception:
            return None, usage
    return data, usage


async def generer_visuel_avec_revision(
    brief: str,
    page_w_mm: float, page_h_mm: float, bleed_mm: float,
    medias_bytes: dict[str, bytes],
    medias_manifest: list[dict],
    brand_kit: Optional[dict] = None,
    inspiration: Optional[str] = None,
    modele: str = "sonnet",
    langue: str = "fr",
    dpi: int = 300,
    max_iterations: int = 2,
    score_seuil_ok: float = 7.5,
    avec_design_tokens: bool = True,
    modele_tokens: str = "haiku",
) -> tuple[Optional[PlacementPlan], bytes, list[dict], list[dict]]:
    """
    Pipeline complet : (Phase 0 tokens) → Phase 1 placement → Phase 2 rendu
    → Phase 3 audit → Phase 3b révision → re-rendu.

    Retourne (plan_final, png_final, journal_revisions, usages_llm).
    `usages_llm` = liste de {modele, tokens_in, tokens_out, etape} —
    le caller débite via debiter_llm pour chaque entrée (marge x12 appliquée
    automatiquement par le pricing interne).
    """
    from .geometric_placement import render_placement_plan

    journal: list[dict] = []
    usages: list[dict] = []

    # ── Phase 0 : DesignTokens (préanalyse) ─────────────────────────────
    tokens: Optional[DesignTokens] = None
    if avec_design_tokens:
        tokens, usage_tokens = await analyser_design_tokens(
            brief=brief, page_w_mm=page_w_mm, page_h_mm=page_h_mm,
            medias=medias_manifest, brand_kit=brand_kit, langue=langue,
            inspiration=inspiration, modele=modele_tokens,
        )
        if usage_tokens.get("tokens_in") or usage_tokens.get("tokens_out"):
            usages.append({**usage_tokens, "etape": "design_tokens"})
        journal.append({"iteration": 0, "etape": "design_tokens",
                        "ok": tokens is not None,
                        "registre": getattr(tokens, "registre", None) if tokens else None})

    # ── Phase 1 : Placement (consomme tokens si dispo) ──────────────────
    plan, usage_placement = await generer_placement_plan(
        brief, page_w_mm, page_h_mm, bleed_mm,
        medias=medias_manifest, brand_kit=brand_kit,
        inspiration=inspiration, modele=modele, langue=langue,
        tokens=tokens,
    )
    if usage_placement.get("tokens_in") or usage_placement.get("tokens_out"):
        usages.append({**usage_placement, "etape": "placement_initial"})
    if plan is None:
        return None, b"", journal + [{"iteration": 0, "erreur": "LLM placement initial KO"}], usages

    # ── Phase 2 : Rendu Python ──────────────────────────────────────────
    png = render_placement_plan(plan, medias_bytes, dpi=dpi, include_bleed=True)
    journal.append({"iteration": 0, "etape": "render_initial", "size_kb": len(png) // 1024})

    # ── Phase 3 : Audit + révisions itératives ──────────────────────────
    for it in range(1, max_iterations + 1):
        revision, usage_audit = await auditer_et_reviser_placement(
            plan, png, brief, medias_manifest=medias_manifest,
            modele=modele, tokens=tokens,
        )
        if usage_audit.get("tokens_in") or usage_audit.get("tokens_out"):
            usages.append({**usage_audit, "etape": f"audit_it{it}"})
        if revision is None:
            journal.append({"iteration": it, "etape": "audit_skip", "raison": "LLM KO"})
            break

        journal.append({
            "iteration": it, "etape": "audit",
            "verdict": revision.verdict,
            "score": revision.score,
            "scores_par_axe": revision.scores_par_axe,
            "nb_issues": len(revision.issues),
            "issues_critiques": sum(1 for i in revision.issues
                                     if i.get("severite") == "critique"),
            "synthese": revision.synthese,
        })

        if revision.verdict == "ok" or revision.score >= score_seuil_ok:
            break
        if revision.plan_revise is None:
            journal.append({"iteration": it, "etape": "audit_sans_revise"})
            break

        plan = revision.plan_revise
        png = render_placement_plan(plan, medias_bytes, dpi=dpi, include_bleed=True)
        journal.append({"iteration": it, "etape": "re_render",
                        "size_kb": len(png) // 1024})

    return plan, png, journal, usages
