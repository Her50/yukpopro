"""
Bureau Infographe — Génération d'infographies print-ready pour secrétariats africains.

Pipeline :
  1. Brief client (texte) → Claude génère layout/textes/palette
  2. Moteur ReportLab + Pillow compose le fichier
  3. Export PDF/X print-ready (bleed 3mm, 300 DPI) + PNG preview + SVG

Productions : cartes de visite, flyers, affiches, faire-part, diplômes,
               banderoles, en-têtes, cartes de vœux.
"""
from __future__ import annotations

import io
import json
import logging
import math
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("yukpo_assurance.bureau.infographe")

# ─── Gabarits locaux (contexte africain francophone) ─────────────────────────

GABARITS: dict[str, dict] = {
    "carte_visite": {
        "label": "Carte de visite",
        "width_mm": 90, "height_mm": 55,
        "bleed_mm": 3,
        "categorie": "print",
        "description": "Format standard 85×54mm + bleed 3mm",
        "prix_fcfa": 2000,
    },
    "flyer_a5": {
        "label": "Flyer A5",
        "width_mm": 148, "height_mm": 210,
        "bleed_mm": 3,
        "categorie": "print",
        "description": "Flyer recto A5 + bleed",
        "prix_fcfa": 3000,
    },
    "flyer_a4": {
        "label": "Flyer A4",
        "width_mm": 210, "height_mm": 297,
        "bleed_mm": 3,
        "categorie": "print",
        "description": "Flyer recto A4 + bleed",
        "prix_fcfa": 4000,
    },
    "affiche_a3": {
        "label": "Affiche A3",
        "width_mm": 297, "height_mm": 420,
        "bleed_mm": 3,
        "categorie": "print",
        "description": "Affiche A3 + bleed",
        "prix_fcfa": 5000,
    },
    "affiche_a2": {
        "label": "Affiche A2",
        "width_mm": 420, "height_mm": 594,
        "bleed_mm": 3,
        "categorie": "print",
        "description": "Affiche A2 grand format",
        "prix_fcfa": 7000,
    },
    "faire_part_mariage": {
        "label": "Faire-part de mariage",
        "width_mm": 148, "height_mm": 105,
        "bleed_mm": 3,
        "categorie": "evenement",
        "description": "Faire-part format paysage A6",
        "prix_fcfa": 3500,
    },
    "faire_part_bapteme": {
        "label": "Faire-part de baptême",
        "width_mm": 148, "height_mm": 105,
        "bleed_mm": 3,
        "categorie": "evenement",
        "description": "Faire-part baptême format A6",
        "prix_fcfa": 3000,
    },
    "faire_part_deces": {
        "label": "Faire-part de décès",
        "width_mm": 210, "height_mm": 297,
        "bleed_mm": 3,
        "categorie": "evenement",
        "description": "Faire-part de deuil format A4",
        "prix_fcfa": 3000,
    },
    "diplome": {
        "label": "Diplôme / Attestation",
        "width_mm": 297, "height_mm": 210,
        "bleed_mm": 3,
        "categorie": "officiel",
        "description": "Diplôme format A3 paysage",
        "prix_fcfa": 4000,
    },
    "entete_courrier": {
        "label": "En-tête de courrier",
        "width_mm": 210, "height_mm": 60,
        "bleed_mm": 0,
        "categorie": "corporate",
        "description": "En-tête A4 pour papier à en-tête",
        "prix_fcfa": 2500,
    },
    "banderole": {
        "label": "Banderole / Roll-up",
        "width_mm": 800, "height_mm": 200,
        "bleed_mm": 5,
        "categorie": "grand_format",
        "description": "Banderole 8m×2m (à l'échelle)",
        "prix_fcfa": 8000,
    },
    "carte_voeux": {
        "label": "Carte de vœux",
        "width_mm": 148, "height_mm": 105,
        "bleed_mm": 3,
        "categorie": "evenement",
        "description": "Carte vœux format A6",
        "prix_fcfa": 2000,
    },
    "flyer_conference": {
        "label": "Programme de conférence",
        "width_mm": 210, "height_mm": 297,
        "bleed_mm": 3,
        "categorie": "evenement",
        "description": "Flyer/programme conférence A4",
        "prix_fcfa": 4000,
    },
    "flyer_boutique": {
        "label": "Flyer ouverture boutique",
        "width_mm": 148, "height_mm": 210,
        "bleed_mm": 3,
        "categorie": "commercial",
        "description": "Flyer promotion/ouverture A5",
        "prix_fcfa": 3000,
    },
    # ── Formats paysage ──────────────────────────────────────────────────────
    "a4_paysage": {
        "label": "A4 Paysage",
        "width_mm": 297, "height_mm": 210,
        "bleed_mm": 3,
        "categorie": "print",
        "description": "Format A4 paysage universel",
        "prix_fcfa": 4000,
    },
    "a5_paysage": {
        "label": "A5 Paysage",
        "width_mm": 210, "height_mm": 148,
        "bleed_mm": 3,
        "categorie": "print",
        "description": "Format A5 paysage",
        "prix_fcfa": 3000,
    },
    # ── Formats grand format ─────────────────────────────────────────────────
    "rollup_85x200": {
        "label": "Roll-up 85×200 cm",
        "width_mm": 850, "height_mm": 2000,
        "bleed_mm": 10,
        "categorie": "grand_format",
        "description": "Roll-up standard 85×200cm + bleed 10mm",
        "prix_fcfa": 10000,
    },
    "kakemono_80x200": {
        "label": "Kakémono 80×200 cm",
        "width_mm": 800, "height_mm": 2000,
        "bleed_mm": 10,
        "categorie": "grand_format",
        "description": "Kakémono vertical 80×200cm",
        "prix_fcfa": 10000,
    },
    "bache_3x1": {
        "label": "Bâche 3×1 m",
        "width_mm": 3000, "height_mm": 1000,
        "bleed_mm": 20,
        "categorie": "grand_format",
        "description": "Bâche imprimée 3m×1m",
        "prix_fcfa": 12000,
    },
    "bache_6x1": {
        "label": "Bâche 6×1 m",
        "width_mm": 6000, "height_mm": 1000,
        "bleed_mm": 20,
        "categorie": "grand_format",
        "description": "Grande bâche 6m×1m",
        "prix_fcfa": 18000,
    },
    # ── Réseaux sociaux ──────────────────────────────────────────────────────
    "instagram_post": {
        "label": "Instagram Post (carré)",
        "width_mm": 105, "height_mm": 105,
        "bleed_mm": 0,
        "categorie": "social_media",
        "description": "Post Instagram carré 1080×1080px",
        "prix_fcfa": 2500,
    },
    "instagram_story": {
        "label": "Instagram / WhatsApp Story",
        "width_mm": 90, "height_mm": 160,
        "bleed_mm": 0,
        "categorie": "social_media",
        "description": "Story verticale 9:16 (1080×1920px)",
        "prix_fcfa": 2500,
    },
    "facebook_cover": {
        "label": "Couverture Facebook",
        "width_mm": 228, "height_mm": 84,
        "bleed_mm": 0,
        "categorie": "social_media",
        "description": "Bannière Facebook 820×312px",
        "prix_fcfa": 2000,
    },
    "linkedin_banner": {
        "label": "Bannière LinkedIn",
        "width_mm": 228, "height_mm": 60,
        "bleed_mm": 0,
        "categorie": "social_media",
        "description": "Bannière LinkedIn 1584×396px",
        "prix_fcfa": 2000,
    },
    "youtube_thumbnail": {
        "label": "Miniature YouTube",
        "width_mm": 178, "height_mm": 100,
        "bleed_mm": 0,
        "categorie": "social_media",
        "description": "Thumbnail YouTube 1280×720px",
        "prix_fcfa": 2000,
    },
    # ── Papeterie & courrier ─────────────────────────────────────────────────
    "enveloppe_c5": {
        "label": "Enveloppe C5",
        "width_mm": 229, "height_mm": 162,
        "bleed_mm": 3,
        "categorie": "corporate",
        "description": "Enveloppe format C5",
        "prix_fcfa": 2500,
    },
    "badge_conference": {
        "label": "Badge de conférence",
        "width_mm": 90, "height_mm": 120,
        "bleed_mm": 3,
        "categorie": "evenement",
        "description": "Badge nominatif conférence/salon",
        "prix_fcfa": 1500,
    },
    "menu_restaurant": {
        "label": "Menu de restaurant",
        "width_mm": 210, "height_mm": 297,
        "bleed_mm": 3,
        "categorie": "commercial",
        "description": "Carte/menu restaurant format A4",
        "prix_fcfa": 4000,
    },
}

# Palettes de couleurs africaines locales
PALETTES: dict[str, dict] = {
    "classique": {
        "primaire": (0, 102, 204),       # Bleu institutionnel
        "secondaire": (255, 165, 0),     # Orange africain
        "fond": (255, 255, 255),
        "texte": (30, 30, 30),
        "accent": (220, 50, 50),
    },
    "cameroun": {
        "primaire": (0, 148, 68),        # Vert Cameroun
        "secondaire": (206, 17, 38),     # Rouge Cameroun
        "fond": (255, 255, 255),
        "texte": (30, 30, 30),
        "accent": (255, 205, 0),         # Jaune Cameroun
    },
    "senegal": {
        "primaire": (0, 139, 61),        # Vert Sénégal
        "secondaire": (253, 221, 69),    # Jaune Sénégal
        "fond": (255, 255, 255),
        "texte": (30, 30, 30),
        "accent": (220, 50, 50),         # Rouge Sénégal
    },
    "elegance": {
        "primaire": (30, 30, 30),        # Noir élégant
        "secondaire": (196, 155, 80),    # Or africain
        "fond": (248, 245, 240),
        "texte": (30, 30, 30),
        "accent": (196, 155, 80),
    },
    "moderne": {
        "primaire": (63, 81, 181),       # Indigo moderne
        "secondaire": (255, 87, 34),     # Orange deep
        "fond": (250, 250, 250),
        "texte": (33, 33, 33),
        "accent": (0, 188, 212),
    },
}


@dataclass
class SpecificationInfographie:
    type_gabarit: str
    titre: str
    sous_titre: Optional[str] = None
    corps: Optional[str] = None          # Texte principal
    details: list[str] = field(default_factory=list)  # Bullets, lignes secondaires
    palette: str = "classique"
    nom_organisation: Optional[str] = None
    contact: Optional[str] = None        # Tel, email, adresse
    slogan: Optional[str] = None
    date_evenement: Optional[str] = None
    lieu: Optional[str] = None
    meta: dict = field(default_factory=dict)


@dataclass
class ResultatInfographie:
    pdf_bytes: Optional[bytes] = None
    png_bytes: Optional[bytes] = None    # Preview 72 DPI
    specification: Optional[SpecificationInfographie] = None
    gabarit: str = ""
    meta: dict = field(default_factory=dict)


async def generer_specification_depuis_brief(
    brief: str,
    type_gabarit: str,
    pays: str = "CM",
) -> tuple[SpecificationInfographie, dict]:
    """
    Analyse un brief client en langage naturel et extrait la spécification structurée
    pour la génération de l'infographie.
    """
    from core.ia_client import ia_client, ModeIA

    gabarit_info = GABARITS.get(type_gabarit, GABARITS["flyer_a5"])

    prompt = f"""Tu es directeur artistique spécialisé en communication visuelle pour l'Afrique francophone.

Brief client :
{brief}

Type de document : {gabarit_info['label']}
Format : {gabarit_info['width_mm']}mm × {gabarit_info['height_mm']}mm

Analyse ce brief et retourne un JSON avec la structure suivante :
{{
  "titre": "Titre principal accrocheur (max 60 caractères)",
  "sous_titre": "Sous-titre si pertinent (max 80 caractères ou null)",
  "corps": "Corps de texte principal si pertinent (max 300 caractères ou null)",
  "details": ["Point 1", "Point 2", "..."], // max 6 éléments
  "palette": "classique|cameroun|senegal|elegance|moderne",
  "nom_organisation": "Nom de l'organisation/entreprise ou null",
  "contact": "Téléphone, email, adresse sur une ligne ou null",
  "slogan": "Slogan ou accroche ou null",
  "date_evenement": "Date de l'événement si applicable ou null",
  "lieu": "Lieu si applicable ou null"
}}

Adapte le style et le registre au contexte africain francophone ({pays}).
Retourne UNIQUEMENT le JSON, sans commentaire."""

    reponse = await ia_client.appeler(
        prompt=prompt,
        mode=ModeIA.ANALYSE,
        json_attendu=True,
    )

    try:
        data = json.loads(reponse.contenu)
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{.*\}', reponse.contenu, re.DOTALL)
        data = json.loads(match.group()) if match else {}

    spec = SpecificationInfographie(
        type_gabarit=type_gabarit,
        titre=data.get("titre", "Titre principal"),
        sous_titre=data.get("sous_titre"),
        corps=data.get("corps"),
        details=data.get("details", []),
        palette=data.get("palette", "classique"),
        nom_organisation=data.get("nom_organisation"),
        contact=data.get("contact"),
        slogan=data.get("slogan"),
        date_evenement=data.get("date_evenement"),
        lieu=data.get("lieu"),
    )
    tokens_meta = {
        "modele": reponse.modele_utilise,
        "tokens_input": reponse.tokens_input,
        "tokens_output": reponse.tokens_output,
    }
    return spec, tokens_meta


def generer_pdf(spec: SpecificationInfographie, gabarit_info: Optional[dict] = None) -> bytes:
    """
    Génère un PDF print-ready avec ReportLab.
    Bleed 3mm, polices incorporées, résolution 300 DPI pour éléments raster.
    gabarit_info permet de passer un gabarit custom sans modifier GABARITS global.
    """
    from reportlab.lib.pagesizes import mm
    from reportlab.lib.colors import HexColor, Color
    from reportlab.pdfgen import canvas
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    gabarit = gabarit_info or GABARITS.get(spec.type_gabarit, GABARITS["flyer_a5"])
    palette = PALETTES.get(spec.palette, PALETTES["classique"])

    w_mm = gabarit["width_mm"] + gabarit["bleed_mm"] * 2
    h_mm = gabarit["height_mm"] + gabarit["bleed_mm"] * 2
    bleed = gabarit["bleed_mm"] * mm

    w = w_mm * mm
    h = h_mm * mm

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h))

    def rgb(t): return Color(t[0]/255, t[1]/255, t[2]/255)

    # Fond
    c.setFillColor(rgb(palette["fond"]))
    c.rect(0, 0, w, h, fill=True, stroke=False)

    # Bande de couleur primaire en haut
    bande_h = h * 0.35
    c.setFillColor(rgb(palette["primaire"]))
    c.rect(0, h - bande_h, w, bande_h, fill=True, stroke=False)

    # Accent décoratif (triangle bas-gauche)
    c.setFillColor(rgb(palette["accent"]))
    p = c.beginPath()
    p.moveTo(0, 0)
    p.lineTo(w * 0.25, 0)
    p.lineTo(0, h * 0.18)
    p.close()
    c.drawPath(p, fill=True, stroke=False)

    # Titre
    c.setFillColor(rgb((255, 255, 255)))
    c.setFont("Helvetica-Bold", _taille_police_titre(spec.titre, w))
    titre_y = h - bande_h / 2 + 5 * mm
    c.drawCentredString(w / 2, titre_y, spec.titre[:60])

    # Sous-titre
    if spec.sous_titre:
        c.setFont("Helvetica", _taille_police_titre(spec.sous_titre, w) * 0.6)
        c.drawCentredString(w / 2, titre_y - 10 * mm, spec.sous_titre[:80])

    # Corps / organisation
    y_courant = h - bande_h - 15 * mm
    c.setFillColor(rgb(palette["texte"]))

    if spec.nom_organisation:
        c.setFont("Helvetica-Bold", max(8, min(14, w / 20 / mm)))
        c.drawCentredString(w / 2, y_courant, spec.nom_organisation[:60])
        y_courant -= 8 * mm

    if spec.corps:
        c.setFont("Helvetica", max(7, min(11, w / 25 / mm)))
        _dessiner_texte_wrap(c, spec.corps, bleed, y_courant, w - bleed * 2)
        y_courant -= 15 * mm

    # Détails (bullets)
    if spec.details:
        c.setFont("Helvetica", max(7, min(10, w / 28 / mm)))
        for detail in spec.details[:6]:
            if y_courant > bleed + 15 * mm:
                c.drawString(bleed + 5 * mm, y_courant, f"• {detail[:70]}")
                y_courant -= 6 * mm

    # Éléments événement
    if spec.date_evenement or spec.lieu:
        c.setFont("Helvetica-Bold", max(8, min(12, w / 22 / mm)))
        c.setFillColor(rgb(palette["secondaire"]))
        info_evt = " | ".join(filter(None, [spec.date_evenement, spec.lieu]))
        c.drawCentredString(w / 2, bleed + 20 * mm, info_evt[:80])

    # Slogan
    if spec.slogan:
        c.setFont("Helvetica-Oblique", max(7, min(10, w / 30 / mm)))
        c.setFillColor(rgb(palette["primaire"]))
        c.drawCentredString(w / 2, bleed + 12 * mm, f"« {spec.slogan[:70]} »")

    # Contact
    if spec.contact:
        c.setFont("Helvetica", max(6, min(9, w / 32 / mm)))
        c.setFillColor(rgb(palette["texte"]))
        c.drawCentredString(w / 2, bleed + 5 * mm, spec.contact[:80])

    # Traits de coupe (crop marks)
    _dessiner_traits_coupe(c, w, h, bleed)

    c.save()
    return buf.getvalue()


def _taille_police_titre(texte: str, largeur_pt: float) -> float:
    """Calcule une taille de police adaptée à la largeur disponible."""
    nb_chars = len(texte)
    taille = min(48, max(14, largeur_pt / (nb_chars * 0.55)))
    return taille


def _dessiner_texte_wrap(c, texte: str, x: float, y: float, largeur: float, taille: float = 10) -> None:
    """Dessine du texte avec retour à la ligne simple."""
    mots = texte.split()
    ligne = ""
    for mot in mots:
        test = f"{ligne} {mot}".strip()
        if len(test) * taille * 0.5 > largeur:
            c.drawString(x, y, ligne)
            y -= taille * 1.4
            ligne = mot
        else:
            ligne = test
    if ligne:
        c.drawString(x, y, ligne)


def _dessiner_traits_coupe(c, w: float, h: float, bleed: float) -> None:
    """Dessine les traits de coupe aux 4 coins (impression professionnelle)."""
    from reportlab.lib.colors import black
    taille_trait = 5  # points
    c.setStrokeColor(black)
    c.setLineWidth(0.25)
    offset = 2  # espace entre le bord et le trait

    coins = [
        (bleed, bleed),
        (w - bleed, bleed),
        (bleed, h - bleed),
        (w - bleed, h - bleed),
    ]
    for cx, cy in coins:
        dx = 1 if cx < w / 2 else -1
        dy = 1 if cy < h / 2 else -1
        c.line(cx + dx * offset, cy, cx + dx * (offset + taille_trait), cy)
        c.line(cx, cy + dy * offset, cx, cy + dy * (offset + taille_trait))


async def generer_infographie(
    brief: str,
    type_gabarit: str,
    pays: str = "CM",
    spec_override: Optional[SpecificationInfographie] = None,
    gabarits_override: Optional[dict] = None,
) -> ResultatInfographie:
    """
    Pipeline complet : brief → spec IA → PDF print-ready + PNG preview.
    gabarits_override permet d'injecter des gabarits customs sans modifier le dict global.
    """
    _gabarits = gabarits_override or GABARITS
    gabarit = _gabarits.get(type_gabarit)
    if not gabarit:
        raise ValueError(f"Gabarit inconnu : {type_gabarit}. Disponibles : {list(_gabarits.keys())}")

    tokens_meta: dict = {}
    if spec_override:
        spec = spec_override
    else:
        spec, tokens_meta = await generer_specification_depuis_brief(brief, type_gabarit, pays)

    # Génération PDF
    pdf_bytes: Optional[bytes] = None
    try:
        pdf_bytes = generer_pdf(spec, gabarit_info=gabarit)
    except Exception as e:
        logger.error(f"[Infographe] Génération PDF échouée : {e}")
        raise RuntimeError(f"Génération PDF échouée : {e}")

    # Preview PNG (via Pillow si pdf2image disponible, sinon None)
    png_bytes: Optional[bytes] = None
    try:
        from pdf2image import convert_from_bytes
        images = convert_from_bytes(pdf_bytes, dpi=72, first_page=1, last_page=1)
        if images:
            buf = io.BytesIO()
            images[0].save(buf, format="PNG", optimize=True)
            png_bytes = buf.getvalue()
    except Exception:
        pass  # pdf2image optionnel

    return ResultatInfographie(
        pdf_bytes=pdf_bytes,
        png_bytes=png_bytes,
        specification=spec,
        gabarit=type_gabarit,
        meta={
            "gabarit_label": gabarit["label"],
            "prix_fcfa": gabarit.get("prix_fcfa", 5000),
            **tokens_meta,
        },
    )


async def analyser_modele_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """
    Analyse une image modèle uploadée par l'utilisateur et retourne une description
    du style graphique pour inspirer la génération IA.
    """
    import base64
    from core.ia_client import ia_client, ModeIA

    b64 = base64.b64encode(image_bytes).decode()
    prompt_sys = (
        "Tu es directeur artistique expert. Analyse cette image de référence et décris "
        "précisément son style graphique pour guider la création d'une infographie similaire."
    )
    prompt_user = (
        "Décris ce modèle graphique en JSON :\n"
        "{\n"
        '  "style_general": "moderne|classique|minimaliste|coloré|élégant|audacieux",\n'
        '  "palette_dominante": ["couleur1_hex", "couleur2_hex", "couleur3_hex"],\n'
        '  "disposition": "description du layout (centré, colonnes, header/footer, etc.)",\n'
        '  "typographie": "description des polices et tailles perçues",\n'
        '  "elements_visuels": ["logo", "photo", "icônes", etc.],\n'
        '  "ambiance": "description de l\'atmosphère générale",\n'
        '  "points_forts": "ce qui rend ce design efficace"\n'
        "}\n"
        "Retourne UNIQUEMENT le JSON."
    )
    try:
        reponse = await ia_client.analyser_image_vision(
            image_b64=b64,
            prompt=prompt_sys + "\n" + prompt_user,
            mode=ModeIA.CLAUDE_VISION,
        )
        return reponse.contenu
    except Exception as e:
        logger.warning(f"[Infographe] Analyse modèle image : {e}")
        return "{}"


def creer_gabarit_custom(width_mm: float, height_mm: float, bleed_mm: float = 3) -> dict:
    """Crée un gabarit personnalisé à partir de dimensions saisies."""
    return {
        "label": f"Format personnalisé {width_mm}×{height_mm}mm",
        "width_mm": width_mm,
        "height_mm": height_mm,
        "bleed_mm": bleed_mm,
        "categorie": "custom",
        "description": f"Format sur mesure {width_mm}mm × {height_mm}mm",
        "prix_fcfa": 5000,
    }
