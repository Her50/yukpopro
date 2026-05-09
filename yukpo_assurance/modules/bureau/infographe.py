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

# Palettes de couleurs — chaque palette adaptée à un contexte
PALETTES: dict[str, dict] = {
    "classique": {
        "primaire": (0, 102, 204), "secondaire": (255, 165, 0),
        "fond": (255, 255, 255), "texte": (30, 30, 30), "accent": (220, 50, 50),
    },
    "cameroun": {
        "primaire": (0, 148, 68), "secondaire": (206, 17, 38),
        "fond": (255, 255, 255), "texte": (30, 30, 30), "accent": (255, 205, 0),
    },
    "senegal": {
        "primaire": (0, 139, 61), "secondaire": (253, 221, 69),
        "fond": (255, 255, 255), "texte": (30, 30, 30), "accent": (220, 50, 50),
    },
    "elegance": {
        "primaire": (30, 30, 30), "secondaire": (196, 155, 80),
        "fond": (248, 245, 240), "texte": (30, 30, 30), "accent": (196, 155, 80),
    },
    "moderne": {
        "primaire": (63, 81, 181), "secondaire": (255, 87, 34),
        "fond": (250, 250, 250), "texte": (33, 33, 33), "accent": (0, 188, 212),
    },
    # Wedding : doré + crème + rose poudré
    "mariage": {
        "primaire": (176, 141, 87),      # Or rosé
        "secondaire": (206, 162, 149),   # Rose poudré
        "fond": (253, 248, 243),         # Ivoire chaud
        "texte": (74, 56, 42),           # Bistre
        "accent": (139, 93, 59),         # Bronze
    },
    # Funeral : gris + blanc + bleu ardoise (sobre)
    "deuil": {
        "primaire": (55, 65, 81),        # Ardoise sombre
        "secondaire": (156, 163, 175),   # Gris neutre
        "fond": (249, 250, 251),         # Blanc cassé
        "texte": (31, 41, 55),
        "accent": (107, 114, 128),
    },
    # Baptême : bleu pastel + blanc + or pâle
    "bapteme": {
        "primaire": (147, 197, 253),     # Bleu ciel
        "secondaire": (254, 240, 138),   # Jaune pastel
        "fond": (255, 255, 255),
        "texte": (55, 65, 81),
        "accent": (191, 219, 254),
    },
    # Corporate premium : bleu marine + or + blanc
    "corporate": {
        "primaire": (15, 23, 42),        # Bleu nuit
        "secondaire": (203, 161, 53),    # Or sobre
        "fond": (255, 255, 255),
        "texte": (30, 41, 59),
        "accent": (71, 85, 105),
    },
    # Festif / boutique : fuchsia + turquoise + jaune
    "festif": {
        "primaire": (236, 72, 153),      # Fuchsia
        "secondaire": (250, 204, 21),    # Jaune vif
        "fond": (255, 255, 255),
        "texte": (31, 41, 55),
        "accent": (6, 182, 212),         # Turquoise
    },
    # Minimaliste : noir / blanc / gris — design épuré
    "minimaliste": {
        "primaire": (17, 24, 39),
        "secondaire": (107, 114, 128),
        "fond": (255, 255, 255),
        "texte": (17, 24, 39),
        "accent": (239, 68, 68),
    },
    # Royal : bordeaux + or + crème — diplômes, badges
    "royal": {
        "primaire": (127, 29, 29),       # Bordeaux
        "secondaire": (202, 138, 4),     # Or
        "fond": (254, 252, 232),         # Crème
        "texte": (69, 26, 3),
        "accent": (180, 83, 9),
    },
    # Tropical : coucher de soleil africain
    "tropical": {
        "primaire": (194, 65, 12),       # Terracotta
        "secondaire": (234, 179, 8),     # Jaune mangue
        "fond": (255, 251, 235),
        "texte": (67, 20, 7),
        "accent": (22, 101, 52),         # Vert feuille
    },
}

# Palette conseillée selon le type de gabarit (utilisé par défaut si l'IA ne choisit pas)
PALETTE_PAR_DEFAUT: dict[str, str] = {
    "faire_part_mariage": "mariage",
    "faire_part_bapteme": "bapteme",
    "faire_part_deces": "deuil",
    "diplome": "royal",
    "carte_visite": "corporate",
    "entete_courrier": "corporate",
    "enveloppe_c5": "corporate",
    "badge_conference": "royal",
    "flyer_boutique": "festif",
    "menu_restaurant": "tropical",
    "instagram_post": "moderne",
    "instagram_story": "moderne",
    "facebook_cover": "corporate",
    "linkedin_banner": "corporate",
    "youtube_thumbnail": "festif",
    "rollup_85x200": "moderne",
    "kakemono_80x200": "moderne",
    "bache_3x1": "festif",
    "bache_6x1": "festif",
    "banderole": "festif",
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
    pdf_cmyk_bytes: Optional[bytes] = None   # Version CMJN print-pro
    png_bytes: Optional[bytes] = None        # Preview haute résolution (300 DPI)
    png_preview_bytes: Optional[bytes] = None  # Preview web 150 DPI optimisé
    svg_bytes: Optional[bytes] = None        # Export vectoriel SVG
    specification: Optional[SpecificationInfographie] = None
    gabarit: str = ""
    meta: dict = field(default_factory=dict)


def _palette_personnalisee_depuis_hex(primaire_hex: str, accents_hex: Optional[list[str]] = None) -> dict:
    """Construit une palette ad-hoc à partir de couleurs hex fournies (marque utilisateur)."""
    def _hex_to_rgb(h: str) -> tuple[int, int, int]:
        h = (h or "").lstrip("#").strip()
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        if len(h) != 6:
            return (0, 102, 204)
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        except ValueError:
            return (0, 102, 204)
    primaire = _hex_to_rgb(primaire_hex)
    accents_hex = accents_hex or []
    secondaire = _hex_to_rgb(accents_hex[0]) if accents_hex else (203, 161, 53)
    accent = _hex_to_rgb(accents_hex[1]) if len(accents_hex) > 1 else secondaire
    # Fond clair pour lisibilité / texte foncé
    return {
        "primaire": primaire,
        "secondaire": secondaire,
        "fond": (255, 255, 255),
        "texte": (30, 30, 30),
        "accent": accent,
    }


async def generer_specification_depuis_brief(
    brief: str,
    type_gabarit: str,
    pays: str = "CM",
    profil: Optional[dict] = None,
    variante_hint: Optional[str] = None,
) -> tuple[SpecificationInfographie, dict]:
    """
    Analyse un brief client en langage naturel et extrait la spécification structurée
    pour la génération de l'infographie.

    `profil` peut contenir : metier, secteur, nom_organisation, couleur_primaire_hex,
    couleurs_accents_hex (list[str]), audience, ton (formel|chaleureux|jeune|premium).
    `variante_hint` force une direction créative alternative (utilisé pour générer
    4 variantes parallèles : "classique", "audacieux", "minimaliste", "festif").
    """
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire

    gabarit_info = GABARITS.get(type_gabarit, GABARITS["flyer_a5"])
    profil = profil or {}
    metier = profil.get("metier") or ""
    secteur = profil.get("secteur") or ""
    nom_org_profil = profil.get("nom_organisation") or ""
    audience = profil.get("audience") or ""
    ton = profil.get("ton") or ""
    couleur_prim = profil.get("couleur_primaire_hex") or ""
    couleurs_acc = profil.get("couleurs_accents_hex") or []

    bloc_profil_lignes = []
    if metier:
        bloc_profil_lignes.append(f"- Métier / activité : {metier}")
    if secteur:
        bloc_profil_lignes.append(f"- Secteur : {secteur}")
    if nom_org_profil:
        bloc_profil_lignes.append(f"- Organisation : {nom_org_profil}")
    if audience:
        bloc_profil_lignes.append(f"- Audience cible : {audience}")
    if ton:
        bloc_profil_lignes.append(f"- Ton souhaité : {ton}")
    if couleur_prim:
        bloc_profil_lignes.append(f"- Couleur primaire de marque : {couleur_prim}")
    if couleurs_acc:
        bloc_profil_lignes.append(f"- Couleurs d'accent de marque : {', '.join(couleurs_acc)}")
    bloc_profil = "\n".join(bloc_profil_lignes) or "(profil non renseigné — rester générique)"

    palettes_dispo = "|".join(PALETTES.keys())
    hint_ligne = (
        f"\nDirection créative imposée pour cette variante : **{variante_hint}** "
        "(doit se distinguer nettement des autres variantes par les choix typo/couleurs/hiérarchie)."
        if variante_hint else ""
    )

    prompt = f"""Tu es directeur artistique senior (15+ ans d'expérience) pour communication visuelle **internationale**, tous secteurs, tous pays.

═══════════════════════════════════════════════════
  CONTEXTE CLIENT
═══════════════════════════════════════════════════
Pays de diffusion : {pays}
{bloc_profil}

Brief client :
\"\"\"{brief}\"\"\"

═══════════════════════════════════════════════════
  LIVRABLE
═══════════════════════════════════════════════════
Type de document : {gabarit_info['label']}
Format : {gabarit_info['width_mm']}mm × {gabarit_info['height_mm']}mm
Catégorie : {gabarit_info.get('categorie', 'print')}{hint_ligne}

═══════════════════════════════════════════════════
  RÈGLES DE CONCEPTION
═══════════════════════════════════════════════════
1. Cohérence métier : le vocabulaire, les images mentales et les détails doivent coller au métier et au secteur du client.
2. Si des couleurs de marque sont fournies, **réutilise-les impérativement** dans `palette_hex_primaire` et `palettes_hex_accents`. Sinon choisis dans {palettes_dispo}.
3. Adapte la hiérarchie (titre / sous-titre / corps / détails) au format : un grand format laisse plus respirer, une carte de visite doit être dense mais aérée.
4. Ton et registre : calqués sur l'audience et le ton déclarés, ou déduits du brief si absents.
5. Aucun détail inventé qui contredirait le brief (pas de prix fantaisiste, pas de date non demandée).
6. Textes directement utilisables — pas de placeholder type "[insérer ici]".

═══════════════════════════════════════════════════
  FORMAT DE SORTIE — JSON STRICT
═══════════════════════════════════════════════════
{{
  "titre": "Titre principal accrocheur (max 60 caractères)",
  "sous_titre": "Sous-titre si pertinent (max 80 caractères ou null)",
  "corps": "Corps de texte principal si pertinent (max 300 caractères ou null)",
  "details": ["Point 1", "Point 2"],
  "palette": "{palettes_dispo}",
  "palette_hex_primaire": "#RRGGBB ou null si pas de couleur de marque",
  "palettes_hex_accents": ["#RRGGBB", "#RRGGBB"],
  "nom_organisation": "Nom de l'organisation ou null",
  "contact": "Téléphone, email, adresse sur une ligne ou null",
  "slogan": "Slogan/accroche ou null",
  "date_evenement": "Date ou null",
  "lieu": "Lieu ou null",
  "justification_direction": "Phrase courte expliquant le parti pris créatif (max 140 car.)"
}}

Retourne UNIQUEMENT le JSON, sans commentaire ni markdown."""

    # Forcer Haiku 4.5 — la spec est du JSON structuré, Haiku est ~12× moins
    # cher que Sonnet/GPT-4o sans perte de qualité perceptible sur ce format.
    reponse = await ia_client.appeler(
        prompt=prompt,
        mode=ModeIA.REDACTION,  # temp 0.4 — équilibre créativité / JSON fiable
        json_attendu=True,
        forcer_modele=ModelePrioritaire.CLAUDE_HAIKU,
    )

    try:
        data = json.loads(reponse.contenu)
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{.*\}', reponse.contenu, re.DOTALL)
        data = json.loads(match.group()) if match else {}

    # Si couleurs de marque fournies par le LLM ou le profil, construire palette custom
    palette_hex_primaire = (data.get("palette_hex_primaire") or couleur_prim or "").strip()
    palettes_hex_accents = data.get("palettes_hex_accents") or couleurs_acc or []
    meta_palette_custom = None
    if palette_hex_primaire:
        meta_palette_custom = _palette_personnalisee_depuis_hex(palette_hex_primaire, palettes_hex_accents)

    spec = SpecificationInfographie(
        type_gabarit=type_gabarit,
        titre=data.get("titre", "Titre principal"),
        sous_titre=data.get("sous_titre"),
        corps=data.get("corps"),
        details=data.get("details", []),
        palette=data.get("palette", "classique"),
        nom_organisation=data.get("nom_organisation") or nom_org_profil or None,
        contact=data.get("contact"),
        slogan=data.get("slogan"),
        date_evenement=data.get("date_evenement"),
        lieu=data.get("lieu"),
        meta={
            "palette_custom": meta_palette_custom,
            "justification": data.get("justification_direction"),
            "variante_hint": variante_hint,
        },
    )
    tokens_meta = {
        "modele": reponse.modele_utilise,
        "tokens_input": reponse.tokens_input,
        "tokens_output": reponse.tokens_output,
        "fallback_utilise": reponse.fallback_utilise,
    }
    return spec, tokens_meta


def generer_pdf(
    spec: SpecificationInfographie,
    gabarit_info: Optional[dict] = None,
    mode_couleur: str = "rgb",  # "rgb" | "cmyk"
) -> bytes:
    """
    Génère un PDF print-ready avec ReportLab.
    Route vers un layout spécialisé selon la catégorie du gabarit.

    mode_couleur="cmyk" → export compatible offset 4 couleurs (imprimeurs pro).
    """
    from reportlab.lib.pagesizes import mm
    from reportlab.pdfgen import canvas

    gabarit = gabarit_info or GABARITS.get(spec.type_gabarit, GABARITS["flyer_a5"])

    # Palette : priorité à une palette custom construite depuis les couleurs de marque
    # (injectée via spec.meta["palette_custom"]), sinon la palette conseillée, sinon classique.
    palette_custom = (spec.meta or {}).get("palette_custom")
    if palette_custom:
        palette = palette_custom
    else:
        palette_cle = spec.palette if spec.palette in PALETTES else None
        if not palette_cle:
            palette_cle = PALETTE_PAR_DEFAUT.get(spec.type_gabarit, "classique")
        palette = PALETTES[palette_cle]

    w_mm = gabarit["width_mm"] + gabarit["bleed_mm"] * 2
    h_mm = gabarit["height_mm"] + gabarit["bleed_mm"] * 2
    bleed = gabarit["bleed_mm"] * mm
    w = w_mm * mm
    h = h_mm * mm

    buf = io.BytesIO()
    # pageCompression=1 + métadonnées PDF/X-compatibles pour workflow impression
    c = canvas.Canvas(buf, pagesize=(w, h), pageCompression=1)
    c.setTitle(spec.titre or "Infographie Yukpo")
    c.setSubject(gabarit.get("label", ""))
    c.setCreator("Yukpo Infographe")
    c.setProducer(f"Yukpo Infographe — {'CMJN' if mode_couleur == 'cmyk' else 'RGB'}")

    ctx = _RenderCtx(
        c=c, w=w, h=h, bleed=bleed, palette=palette, spec=spec, gabarit=gabarit,
        mode_couleur=mode_couleur,
    )
    _MODE_COULEUR_COURANT["v"] = mode_couleur

    # Routage par catégorie / gabarit spécifique
    cat = gabarit.get("categorie", "print")
    cle = spec.type_gabarit

    if cle == "faire_part_mariage":
        _layout_mariage(ctx)
    elif cle == "faire_part_bapteme":
        _layout_bapteme(ctx)
    elif cle == "faire_part_deces":
        _layout_deuil(ctx)
    elif cle in ("diplome", "badge_conference"):
        _layout_officiel(ctx)
    elif cle == "carte_visite":
        _layout_carte_visite(ctx)
    elif cle in ("entete_courrier", "enveloppe_c5"):
        _layout_entete(ctx)
    elif cat == "social_media":
        _layout_social(ctx)
    elif cat == "grand_format":
        _layout_grand_format(ctx)
    elif cat == "commercial":
        _layout_commercial(ctx)
    else:
        _layout_default(ctx)

    _dessiner_traits_coupe(c, w, h, bleed)
    c.save()
    # Reset du mode couleur global après rendu (évite fuite entre appels concurrents)
    _MODE_COULEUR_COURANT["v"] = "rgb"
    return buf.getvalue()


# ── Contexte de rendu ─────────────────────────────────────────────────────────

@dataclass
class _RenderCtx:
    c: object
    w: float
    h: float
    bleed: float
    palette: dict
    spec: SpecificationInfographie
    gabarit: dict
    mode_couleur: str = "rgb"  # "rgb" | "cmyk"


# ── Conversion RGB → CMJN (formule standard, approximation naive mais exploitable) ──
def _rgb_to_cmyk(r: int, g: int, b: int) -> tuple[float, float, float, float]:
    """Approx. RGB 0-255 → CMYK 0-1. Pour du print offset, un profil ICC serait idéal,
    mais cette conversion donne un résultat correct pour la plupart des usages."""
    rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
    k = 1.0 - max(rf, gf, bf)
    if k >= 0.999:
        return (0.0, 0.0, 0.0, 1.0)
    c_ = (1.0 - rf - k) / (1.0 - k)
    m_ = (1.0 - gf - k) / (1.0 - k)
    y_ = (1.0 - bf - k) / (1.0 - k)
    return (c_, m_, y_, k)


# Mode couleur courant utilisé par les helpers (basculé par _RenderCtx avant chaque layout)
_MODE_COULEUR_COURANT = {"v": "rgb"}


def _rgb(t):
    from reportlab.lib.colors import Color, CMYKColor
    if _MODE_COULEUR_COURANT["v"] == "cmyk":
        c_, m_, y_, k = _rgb_to_cmyk(int(t[0]), int(t[1]), int(t[2]))
        return CMYKColor(c_, m_, y_, k)
    return Color(t[0]/255, t[1]/255, t[2]/255)


def _rgba(t, alpha):
    from reportlab.lib.colors import Color, CMYKColor
    if _MODE_COULEUR_COURANT["v"] == "cmyk":
        c_, m_, y_, k = _rgb_to_cmyk(int(t[0]), int(t[1]), int(t[2]))
        return CMYKColor(c_, m_, y_, k, alpha=alpha)
    return Color(t[0]/255, t[1]/255, t[2]/255, alpha=alpha)


def _fill_bg(ctx: "_RenderCtx"):
    ctx.c.setFillColor(_rgb(ctx.palette["fond"]))
    ctx.c.rect(0, 0, ctx.w, ctx.h, fill=True, stroke=False)


def _bande_horizontale(ctx, y, hauteur, couleur, alpha=1.0):
    ctx.c.setFillColor(_rgba(couleur, alpha) if alpha < 1 else _rgb(couleur))
    ctx.c.rect(0, y, ctx.w, hauteur, fill=True, stroke=False)


def _gradient_vertical(ctx, y_bas, hauteur, couleur_bas, couleur_haut, steps=40):
    """Simule un dégradé vertical par bandes successives."""
    for i in range(steps):
        t = i / (steps - 1)
        r = couleur_bas[0] + (couleur_haut[0] - couleur_bas[0]) * t
        g = couleur_bas[1] + (couleur_haut[1] - couleur_bas[1]) * t
        b = couleur_bas[2] + (couleur_haut[2] - couleur_bas[2]) * t
        ctx.c.setFillColor(_rgb((r, g, b)))
        ctx.c.rect(0, y_bas + hauteur * t, ctx.w, hauteur / steps + 0.5, fill=True, stroke=False)


def _cadre(ctx, x, y, w, h, couleur, epaisseur=0.6):
    ctx.c.setStrokeColor(_rgb(couleur))
    ctx.c.setLineWidth(epaisseur)
    ctx.c.rect(x, y, w, h, fill=False, stroke=True)


def _ornement_coin(ctx, x, y, taille, couleur, sens=(1, 1)):
    """Dessine un petit ornement décoratif (L inversé) à un coin."""
    ctx.c.setStrokeColor(_rgb(couleur))
    ctx.c.setLineWidth(0.8)
    ctx.c.line(x, y, x + sens[0] * taille, y)
    ctx.c.line(x, y, x, y + sens[1] * taille)


def _centrer_texte(ctx, texte: str, y: float, taille: float, couleur, font="Helvetica-Bold"):
    ctx.c.setFont(font, taille)
    ctx.c.setFillColor(_rgb(couleur))
    ctx.c.drawCentredString(ctx.w / 2, y, texte)


def _police_adaptee(texte: str, largeur_dispo: float, base: float = 28, mini: float = 10) -> float:
    """Ajuste une taille de police pour qu'un texte tienne dans une largeur donnée."""
    nb = max(len(texte), 1)
    estim = largeur_dispo / (nb * 0.55)
    return max(mini, min(base, estim))


# ── Layouts spécialisés ───────────────────────────────────────────────────────

def _layout_mariage(ctx: "_RenderCtx"):
    """Faire-part mariage : cadre or + typographie scripte + ornements."""
    from reportlab.lib.pagesizes import mm
    _fill_bg(ctx)
    pal, w, h, bl = ctx.palette, ctx.w, ctx.h, ctx.bleed
    # Cadre double
    _cadre(ctx, bl + 3*mm, bl + 3*mm, w - 2*bl - 6*mm, h - 2*bl - 6*mm, pal["primaire"], 1.2)
    _cadre(ctx, bl + 5*mm, bl + 5*mm, w - 2*bl - 10*mm, h - 2*bl - 10*mm, pal["accent"], 0.4)
    # Ornements coins
    for (x, y, sx, sy) in [
        (bl+8*mm, bl+8*mm, 1, 1), (w-bl-8*mm, bl+8*mm, -1, 1),
        (bl+8*mm, h-bl-8*mm, 1, -1), (w-bl-8*mm, h-bl-8*mm, -1, -1),
    ]:
        _ornement_coin(ctx, x, y, 6*mm, pal["secondaire"], (sx, sy))

    # "Invitation" en haut
    _centrer_texte(ctx, "Invitation", h - bl - 20*mm, 11, pal["secondaire"], "Helvetica-Oblique")
    # Titre (noms)
    taille_titre = _police_adaptee(ctx.spec.titre[:60], w - 2*bl - 20*mm, base=34, mini=18)
    _centrer_texte(ctx, ctx.spec.titre[:60], h - bl - 38*mm, taille_titre, pal["primaire"], "Helvetica-Bold")
    # Ligne décorative
    ctx.c.setStrokeColor(_rgb(pal["secondaire"])); ctx.c.setLineWidth(0.6)
    ctx.c.line(w/2 - 20*mm, h - bl - 46*mm, w/2 + 20*mm, h - bl - 46*mm)
    # Sous-titre
    if ctx.spec.sous_titre:
        _centrer_texte(ctx, ctx.spec.sous_titre[:80], h - bl - 55*mm, 11, pal["texte"], "Helvetica-Oblique")
    # Corps
    y = h/2
    if ctx.spec.corps:
        ctx.c.setFont("Helvetica", 10); ctx.c.setFillColor(_rgb(pal["texte"]))
        _dessiner_texte_wrap_centre(ctx.c, ctx.spec.corps, w/2, y, w - 2*bl - 20*mm, 10)
        y -= 25*mm
    # Date/Lieu en bloc central
    if ctx.spec.date_evenement:
        _centrer_texte(ctx, ctx.spec.date_evenement[:50], bl + 50*mm, 14, pal["primaire"], "Helvetica-Bold")
    if ctx.spec.lieu:
        _centrer_texte(ctx, ctx.spec.lieu[:70], bl + 42*mm, 10, pal["texte"], "Helvetica")
    # Détails
    if ctx.spec.details:
        for i, d in enumerate(ctx.spec.details[:3]):
            _centrer_texte(ctx, d[:80], bl + 30*mm - i*6*mm, 9, pal["texte"], "Helvetica-Oblique")
    # Slogan/contact
    if ctx.spec.contact:
        _centrer_texte(ctx, ctx.spec.contact[:80], bl + 12*mm, 8, pal["accent"], "Helvetica")


def _layout_bapteme(ctx):
    from reportlab.lib.pagesizes import mm
    _fill_bg(ctx)
    pal, w, h, bl = ctx.palette, ctx.w, ctx.h, ctx.bleed
    # Dégradé doux en haut
    _gradient_vertical(ctx, h - h*0.35, h*0.35, pal["fond"], pal["primaire"])
    # Cercle décoratif (simulation par ellipse)
    ctx.c.setFillColor(_rgba(pal["accent"], 0.25))
    ctx.c.ellipse(w/2 - 25*mm, h - bl - 50*mm, w/2 + 25*mm, h - bl - 15*mm, fill=True, stroke=False)
    # "Baptême" étiquette
    _centrer_texte(ctx, "Baptême", h - bl - 18*mm, 10, pal["texte"], "Helvetica-Oblique")
    # Titre (prénom bébé)
    _centrer_texte(ctx, ctx.spec.titre[:60], h - bl - 35*mm, 26, pal["texte"], "Helvetica-Bold")
    if ctx.spec.sous_titre:
        _centrer_texte(ctx, ctx.spec.sous_titre[:80], h - bl - 45*mm, 10, pal["texte"], "Helvetica-Oblique")
    if ctx.spec.corps:
        ctx.c.setFont("Helvetica", 10); ctx.c.setFillColor(_rgb(pal["texte"]))
        _dessiner_texte_wrap_centre(ctx.c, ctx.spec.corps, w/2, h/2, w - 2*bl - 20*mm, 10)
    if ctx.spec.date_evenement:
        _centrer_texte(ctx, ctx.spec.date_evenement[:50], bl + 35*mm, 13, pal["primaire"], "Helvetica-Bold")
    if ctx.spec.lieu:
        _centrer_texte(ctx, ctx.spec.lieu[:70], bl + 27*mm, 9, pal["texte"], "Helvetica")
    if ctx.spec.contact:
        _centrer_texte(ctx, ctx.spec.contact[:80], bl + 12*mm, 8, pal["accent"], "Helvetica")


def _layout_deuil(ctx):
    from reportlab.lib.pagesizes import mm
    _fill_bg(ctx)
    pal, w, h, bl = ctx.palette, ctx.w, ctx.h, ctx.bleed
    # Bande noire en haut (très sobre)
    _bande_horizontale(ctx, h - 18*mm, 18*mm, pal["primaire"])
    _centrer_texte(ctx, "In Memoriam", h - 11*mm, 9, (255, 255, 255), "Helvetica-Oblique")
    # Cadre strict
    _cadre(ctx, bl + 5*mm, bl + 5*mm, w - 2*bl - 10*mm, h - 2*bl - 30*mm, pal["secondaire"], 0.4)
    # Nom défunt
    _centrer_texte(ctx, ctx.spec.titre[:60], h - bl - 45*mm, 24, pal["primaire"], "Helvetica-Bold")
    if ctx.spec.sous_titre:
        _centrer_texte(ctx, ctx.spec.sous_titre[:80], h - bl - 56*mm, 10, pal["texte"], "Helvetica-Oblique")
    # Ligne sobre
    ctx.c.setStrokeColor(_rgb(pal["secondaire"])); ctx.c.setLineWidth(0.4)
    ctx.c.line(w/2 - 25*mm, h - bl - 62*mm, w/2 + 25*mm, h - bl - 62*mm)
    # Corps (hommage)
    y = h - bl - 75*mm
    if ctx.spec.corps:
        ctx.c.setFont("Helvetica", 10); ctx.c.setFillColor(_rgb(pal["texte"]))
        _dessiner_texte_wrap_centre(ctx.c, ctx.spec.corps, w/2, y, w - 2*bl - 20*mm, 10)
    # Date + lieu
    if ctx.spec.date_evenement:
        _centrer_texte(ctx, ctx.spec.date_evenement[:60], bl + 30*mm, 11, pal["primaire"], "Helvetica-Bold")
    if ctx.spec.lieu:
        _centrer_texte(ctx, ctx.spec.lieu[:70], bl + 22*mm, 9, pal["texte"], "Helvetica")
    if ctx.spec.contact:
        _centrer_texte(ctx, ctx.spec.contact[:80], bl + 10*mm, 8, pal["accent"], "Helvetica")


def _layout_officiel(ctx):
    """Diplôme / Badge conférence : cadre royal, sceau symbolique, certificat."""
    from reportlab.lib.pagesizes import mm
    _fill_bg(ctx)
    pal, w, h, bl = ctx.palette, ctx.w, ctx.h, ctx.bleed
    # Double cadre orné
    _cadre(ctx, bl + 4*mm, bl + 4*mm, w - 2*bl - 8*mm, h - 2*bl - 8*mm, pal["primaire"], 2.5)
    _cadre(ctx, bl + 7*mm, bl + 7*mm, w - 2*bl - 14*mm, h - 2*bl - 14*mm, pal["secondaire"], 0.8)
    # Ornements coins
    for (x, y, sx, sy) in [
        (bl+10*mm, bl+10*mm, 1, 1), (w-bl-10*mm, bl+10*mm, -1, 1),
        (bl+10*mm, h-bl-10*mm, 1, -1), (w-bl-10*mm, h-bl-10*mm, -1, -1),
    ]:
        _ornement_coin(ctx, x, y, 8*mm, pal["secondaire"], (sx, sy))
    # En-tête
    if ctx.spec.nom_organisation:
        _centrer_texte(ctx, ctx.spec.nom_organisation[:70], h - bl - 25*mm, 11, pal["texte"], "Helvetica-Bold")
    _centrer_texte(ctx, "CERTIFICAT" if ctx.spec.type_gabarit == "diplome" else "BADGE",
                   h - bl - 38*mm, 16, pal["secondaire"], "Helvetica-Bold")
    # Ligne
    ctx.c.setStrokeColor(_rgb(pal["secondaire"])); ctx.c.setLineWidth(0.5)
    ctx.c.line(w/2 - 30*mm, h - bl - 43*mm, w/2 + 30*mm, h - bl - 43*mm)
    # Titre principal (nom récipiendaire)
    _centrer_texte(ctx, ctx.spec.titre[:60], h/2 + 10*mm,
                   _police_adaptee(ctx.spec.titre, w - 2*bl - 30*mm, 30, 16),
                   pal["primaire"], "Helvetica-Bold")
    if ctx.spec.sous_titre:
        _centrer_texte(ctx, ctx.spec.sous_titre[:80], h/2 - 2*mm, 11, pal["texte"], "Helvetica-Oblique")
    if ctx.spec.corps:
        ctx.c.setFont("Helvetica", 9); ctx.c.setFillColor(_rgb(pal["texte"]))
        _dessiner_texte_wrap_centre(ctx.c, ctx.spec.corps, w/2, h/2 - 15*mm, w - 2*bl - 30*mm, 9)
    if ctx.spec.date_evenement:
        _centrer_texte(ctx, ctx.spec.date_evenement[:40], bl + 20*mm, 10, pal["texte"], "Helvetica")
    if ctx.spec.lieu:
        _centrer_texte(ctx, ctx.spec.lieu[:70], bl + 13*mm, 9, pal["texte"], "Helvetica-Oblique")


def _layout_carte_visite(ctx):
    """Carte de visite : split vertical, nom + fonction + contact compact."""
    from reportlab.lib.pagesizes import mm
    _fill_bg(ctx)
    pal, w, h, bl = ctx.palette, ctx.w, ctx.h, ctx.bleed
    # Bande verticale couleur sur 1/3
    ctx.c.setFillColor(_rgb(pal["primaire"]))
    ctx.c.rect(0, 0, w * 0.35, h, fill=True, stroke=False)
    # Accent
    ctx.c.setFillColor(_rgb(pal["secondaire"]))
    ctx.c.rect(w * 0.35, 0, 1.5*mm, h, fill=True, stroke=False)

    # Logo/monogramme côté couleur (initiales si nom_org dispo)
    if ctx.spec.nom_organisation:
        initiales = "".join(x[0] for x in ctx.spec.nom_organisation.split()[:2]).upper()
        ctx.c.setFillColor(_rgb((255, 255, 255)))
        ctx.c.setFont("Helvetica-Bold", 22)
        ctx.c.drawCentredString(w * 0.175, h/2 + 2*mm, initiales)

    # Nom sur fond clair
    x_txt = w * 0.42
    y = h - bl - 12*mm
    ctx.c.setFillColor(_rgb(pal["texte"]))
    ctx.c.setFont("Helvetica-Bold", 11)
    ctx.c.drawString(x_txt, y, ctx.spec.titre[:40])
    if ctx.spec.sous_titre:
        y -= 5*mm
        ctx.c.setFont("Helvetica-Oblique", 8)
        ctx.c.setFillColor(_rgb(pal["secondaire"]))
        ctx.c.drawString(x_txt, y, ctx.spec.sous_titre[:50])
    # Ligne
    y -= 4*mm
    ctx.c.setStrokeColor(_rgb(pal["secondaire"])); ctx.c.setLineWidth(0.5)
    ctx.c.line(x_txt, y, x_txt + 20*mm, y)
    # Contact bloc
    y -= 5*mm
    ctx.c.setFont("Helvetica", 7.5); ctx.c.setFillColor(_rgb(pal["texte"]))
    if ctx.spec.contact:
        for ligne in ctx.spec.contact.split(" | ")[:4]:
            ctx.c.drawString(x_txt, y, ligne[:40]); y -= 3.5*mm
    if ctx.spec.slogan:
        ctx.c.setFont("Helvetica-Oblique", 6.5); ctx.c.setFillColor(_rgb(pal["accent"]))
        ctx.c.drawString(x_txt, bl + 3*mm, f"« {ctx.spec.slogan[:60]} »")


def _layout_entete(ctx):
    """En-tête courrier / enveloppe : logo à gauche, coordonnées à droite."""
    from reportlab.lib.pagesizes import mm
    _fill_bg(ctx)
    pal, w, h, bl = ctx.palette, ctx.w, ctx.h, ctx.bleed
    # Bande supérieure mince
    _bande_horizontale(ctx, h - 4*mm, 4*mm, pal["secondaire"])
    # Nom organisation (grand à gauche)
    ctx.c.setFillColor(_rgb(pal["primaire"]))
    ctx.c.setFont("Helvetica-Bold", 18)
    ctx.c.drawString(bl + 5*mm, h - bl - 18*mm, (ctx.spec.nom_organisation or ctx.spec.titre)[:40])
    if ctx.spec.slogan:
        ctx.c.setFont("Helvetica-Oblique", 9); ctx.c.setFillColor(_rgb(pal["secondaire"]))
        ctx.c.drawString(bl + 5*mm, h - bl - 24*mm, ctx.spec.slogan[:70])
    # Contact à droite
    if ctx.spec.contact:
        ctx.c.setFont("Helvetica", 8); ctx.c.setFillColor(_rgb(pal["texte"]))
        lignes = ctx.spec.contact.split(" | ")[:4]
        y = h - bl - 10*mm
        for l in lignes:
            ctx.c.drawRightString(w - bl - 5*mm, y, l[:50])
            y -= 3.5*mm
    # Ligne de séparation basse
    ctx.c.setStrokeColor(_rgb(pal["primaire"])); ctx.c.setLineWidth(0.8)
    ctx.c.line(bl + 5*mm, bl + 2*mm, w - bl - 5*mm, bl + 2*mm)


def _layout_social(ctx):
    """Posts/stories sociaux : visuel fort, titre hero, contraste élevé."""
    from reportlab.lib.pagesizes import mm
    pal, w, h, bl = ctx.palette, ctx.w, ctx.h, ctx.bleed
    # Dégradé plein format
    _gradient_vertical(ctx, 0, h, pal["primaire"], pal["accent"])
    # Voile clair pour lisibilité
    ctx.c.setFillColor(_rgba((255, 255, 255), 0.08))
    ctx.c.rect(0, 0, w, h, fill=True, stroke=False)
    # Cadre blanc intérieur
    _cadre(ctx, bl + 4*mm, bl + 4*mm, w - 2*bl - 8*mm, h - 2*bl - 8*mm, (255, 255, 255), 0.6)

    # Organisation / handle
    if ctx.spec.nom_organisation:
        ctx.c.setFont("Helvetica-Bold", 9); ctx.c.setFillColor(_rgb((255, 255, 255)))
        ctx.c.drawString(bl + 8*mm, h - bl - 12*mm, ctx.spec.nom_organisation[:40].upper())

    # Titre hero
    taille = _police_adaptee(ctx.spec.titre, w - 2*bl - 20*mm, base=42, mini=22)
    _centrer_texte(ctx, ctx.spec.titre[:60], h/2 + 10*mm, taille, (255, 255, 255), "Helvetica-Bold")
    # Sous-titre
    if ctx.spec.sous_titre:
        _centrer_texte(ctx, ctx.spec.sous_titre[:80], h/2 - 2*mm, 12, (255, 255, 255), "Helvetica")
    # Détails bullets stylisés
    if ctx.spec.details:
        y = h/2 - 15*mm
        ctx.c.setFont("Helvetica-Bold", 10); ctx.c.setFillColor(_rgb(pal["secondaire"]))
        for d in ctx.spec.details[:4]:
            ctx.c.drawCentredString(w/2, y, f"✓ {d[:60]}"); y -= 6*mm
    # Date / lieu
    if ctx.spec.date_evenement or ctx.spec.lieu:
        info = " • ".join(filter(None, [ctx.spec.date_evenement, ctx.spec.lieu]))
        _centrer_texte(ctx, info[:80], bl + 15*mm, 11, pal["secondaire"], "Helvetica-Bold")
    # Contact/CTA
    if ctx.spec.contact:
        _centrer_texte(ctx, ctx.spec.contact[:80], bl + 8*mm, 8, (255, 255, 255), "Helvetica")


def _layout_grand_format(ctx):
    """Banderoles/roll-up : titre énorme, contraste, hiérarchie forte."""
    from reportlab.lib.pagesizes import mm
    pal, w, h, bl = ctx.palette, ctx.w, ctx.h, ctx.bleed
    _fill_bg(ctx)
    # Bande primaire haute (20%)
    _bande_horizontale(ctx, h * 0.8, h * 0.2, pal["primaire"])
    # Bande accent fine
    _bande_horizontale(ctx, h * 0.79, 1.5*mm, pal["secondaire"])
    # Titre énorme sur la bande
    taille = _police_adaptee(ctx.spec.titre, w - 20*mm, base=min(90, w/6/mm), mini=28)
    _centrer_texte(ctx, ctx.spec.titre[:60], h * 0.88, taille, (255, 255, 255), "Helvetica-Bold")
    if ctx.spec.sous_titre:
        _centrer_texte(ctx, ctx.spec.sous_titre[:80], h * 0.82, taille * 0.35, (255, 255, 255), "Helvetica")
    # Bloc central
    if ctx.spec.corps:
        ctx.c.setFont("Helvetica", min(28, w/28/mm)); ctx.c.setFillColor(_rgb(pal["texte"]))
        _dessiner_texte_wrap_centre(ctx.c, ctx.spec.corps, w/2, h * 0.6, w - 40*mm, min(28, w/28/mm))
    if ctx.spec.details:
        y = h * 0.45
        ctx.c.setFont("Helvetica-Bold", min(22, w/32/mm)); ctx.c.setFillColor(_rgb(pal["primaire"]))
        for d in ctx.spec.details[:5]:
            ctx.c.drawCentredString(w/2, y, f"• {d[:80]}"); y -= 12*mm
    # Footer
    if ctx.spec.contact:
        _bande_horizontale(ctx, 0, h * 0.08, pal["primaire"])
        _centrer_texte(ctx, ctx.spec.contact[:100], h * 0.04, min(18, w/36/mm), (255, 255, 255), "Helvetica-Bold")


def _layout_commercial(ctx):
    """Flyers commerciaux, menus : visuel énergique, CTA fort."""
    from reportlab.lib.pagesizes import mm
    pal, w, h, bl = ctx.palette, ctx.w, ctx.h, ctx.bleed
    _fill_bg(ctx)
    # Diagonale supérieure
    _bande_horizontale(ctx, h - h*0.3, h*0.3, pal["primaire"])
    # Triangle accent en bas-droite
    ctx.c.setFillColor(_rgb(pal["secondaire"]))
    p = ctx.c.beginPath()
    p.moveTo(w, 0); p.lineTo(w, h*0.2); p.lineTo(w*0.7, 0); p.close()
    ctx.c.drawPath(p, fill=True, stroke=False)
    # Organisation
    if ctx.spec.nom_organisation:
        _centrer_texte(ctx, ctx.spec.nom_organisation[:40], h - bl - 12*mm, 10, (255, 255, 255), "Helvetica-Bold")
    # Titre
    taille = _police_adaptee(ctx.spec.titre, w - 2*bl - 15*mm, base=34, mini=16)
    _centrer_texte(ctx, ctx.spec.titre[:60], h - bl - 28*mm, taille, (255, 255, 255), "Helvetica-Bold")
    if ctx.spec.sous_titre:
        _centrer_texte(ctx, ctx.spec.sous_titre[:80], h - bl - 40*mm, 11, (255, 255, 255), "Helvetica-Oblique")
    # Corps
    y = h * 0.55
    if ctx.spec.corps:
        ctx.c.setFont("Helvetica", 10); ctx.c.setFillColor(_rgb(pal["texte"]))
        _dessiner_texte_wrap_centre(ctx.c, ctx.spec.corps, w/2, y, w - 2*bl - 20*mm, 10)
        y -= 20*mm
    # Bullets
    if ctx.spec.details:
        ctx.c.setFont("Helvetica-Bold", 10)
        ctx.c.setFillColor(_rgb(pal["primaire"]))
        for d in ctx.spec.details[:5]:
            ctx.c.drawString(bl + 10*mm, y, f"▸ {d[:70]}")
            y -= 6.5*mm
    # Bloc CTA en bas
    y_cta = bl + 25*mm
    ctx.c.setFillColor(_rgb(pal["accent"]))
    ctx.c.roundRect(bl + 15*mm, y_cta, w - 2*bl - 30*mm, 12*mm, 3*mm, fill=True, stroke=False)
    if ctx.spec.date_evenement or ctx.spec.lieu:
        info = " • ".join(filter(None, [ctx.spec.date_evenement, ctx.spec.lieu]))
        _centrer_texte(ctx, info[:70], y_cta + 4*mm, 11, (255, 255, 255), "Helvetica-Bold")
    # Contact / slogan
    if ctx.spec.slogan:
        _centrer_texte(ctx, f"« {ctx.spec.slogan[:70]} »", bl + 15*mm, 9, pal["primaire"], "Helvetica-Oblique")
    if ctx.spec.contact:
        _centrer_texte(ctx, ctx.spec.contact[:80], bl + 8*mm, 8, pal["texte"], "Helvetica")


def _layout_default(ctx):
    """Layout générique : version améliorée du layout original."""
    from reportlab.lib.pagesizes import mm
    pal, w, h, bl = ctx.palette, ctx.w, ctx.h, ctx.bleed
    _fill_bg(ctx)
    # Bande dégradée haute
    _gradient_vertical(ctx, h - h*0.32, h*0.32, pal["primaire"], pal["accent"])
    # Accent ruban
    ctx.c.setFillColor(_rgb(pal["secondaire"]))
    ctx.c.rect(0, h - h*0.32 - 2*mm, w, 2*mm, fill=True, stroke=False)
    # Titre
    taille = _police_adaptee(ctx.spec.titre, w - 2*bl - 15*mm, base=32, mini=14)
    _centrer_texte(ctx, ctx.spec.titre[:60], h - h*0.16, taille, (255, 255, 255), "Helvetica-Bold")
    if ctx.spec.sous_titre:
        _centrer_texte(ctx, ctx.spec.sous_titre[:80], h - h*0.16 - taille*0.7, taille * 0.4, (255, 255, 255), "Helvetica-Oblique")
    # Organisation
    y = h - h*0.32 - 12*mm
    if ctx.spec.nom_organisation:
        _centrer_texte(ctx, ctx.spec.nom_organisation[:60], y, 13, pal["primaire"], "Helvetica-Bold")
        y -= 8*mm
    # Corps
    if ctx.spec.corps:
        ctx.c.setFont("Helvetica", 10); ctx.c.setFillColor(_rgb(pal["texte"]))
        _dessiner_texte_wrap_centre(ctx.c, ctx.spec.corps, w/2, y, w - 2*bl - 15*mm, 10)
        y -= 20*mm
    # Bullets
    if ctx.spec.details:
        ctx.c.setFont("Helvetica", 10); ctx.c.setFillColor(_rgb(pal["texte"]))
        for d in ctx.spec.details[:5]:
            if y > bl + 25*mm:
                ctx.c.setFillColor(_rgb(pal["secondaire"]))
                ctx.c.drawString(bl + 8*mm, y, "▸")
                ctx.c.setFillColor(_rgb(pal["texte"]))
                ctx.c.drawString(bl + 12*mm, y, d[:80])
                y -= 6.5*mm
    # Date / lieu
    if ctx.spec.date_evenement or ctx.spec.lieu:
        info = " | ".join(filter(None, [ctx.spec.date_evenement, ctx.spec.lieu]))
        _centrer_texte(ctx, info[:80], bl + 20*mm, 11, pal["primaire"], "Helvetica-Bold")
    if ctx.spec.slogan:
        _centrer_texte(ctx, f"« {ctx.spec.slogan[:70]} »", bl + 12*mm, 9, pal["accent"], "Helvetica-Oblique")
    if ctx.spec.contact:
        _centrer_texte(ctx, ctx.spec.contact[:80], bl + 5*mm, 8, pal["texte"], "Helvetica")


def _dessiner_texte_wrap_centre(c, texte: str, x_centre: float, y: float, largeur: float, taille: float) -> None:
    """Dessine un texte centré avec wrap."""
    mots = texte.split()
    lignes: list[str] = []
    ligne = ""
    for mot in mots:
        test = f"{ligne} {mot}".strip()
        if len(test) * taille * 0.5 > largeur and ligne:
            lignes.append(ligne); ligne = mot
        else:
            ligne = test
    if ligne:
        lignes.append(ligne)
    for l in lignes[:5]:
        c.drawCentredString(x_centre, y, l)
        y -= taille * 1.35


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


def _rendre_png(pdf_bytes: bytes, dpi: int) -> Optional[bytes]:
    """Rastérise la première page d'un PDF en PNG à la résolution demandée."""
    try:
        from pdf2image import convert_from_bytes
        images = convert_from_bytes(pdf_bytes, dpi=dpi, first_page=1, last_page=1)
        if not images:
            return None
        buf = io.BytesIO()
        images[0].save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except Exception as e:
        logger.debug(f"[Infographe] PNG {dpi}dpi indisponible : {e}")
        return None


def _generer_svg_depuis_spec(spec: SpecificationInfographie, gabarit: dict) -> Optional[bytes]:
    """
    Génère une version SVG simple de l'infographie (titre, sous-titre, détails, contact).
    Le SVG est vectoriel pur — idéal pour web/retouche Illustrator/Inkscape.
    Les layouts complexes ReportLab ne sont pas reproduits 1:1 : ce SVG est un
    "master éditable" simplifié. Pour le rendu fidèle impression → utiliser le PDF.
    """
    try:
        import svgwrite
    except Exception:
        logger.debug("[Infographe] svgwrite absent — export SVG désactivé")
        return None

    palette_custom = (spec.meta or {}).get("palette_custom")
    if palette_custom:
        palette = palette_custom
    else:
        palette_cle = spec.palette if spec.palette in PALETTES else PALETTE_PAR_DEFAUT.get(spec.type_gabarit, "classique")
        palette = PALETTES[palette_cle]

    def _hex(t):
        return "#{:02X}{:02X}{:02X}".format(int(t[0]), int(t[1]), int(t[2]))

    w_mm = gabarit["width_mm"] + gabarit["bleed_mm"] * 2
    h_mm = gabarit["height_mm"] + gabarit["bleed_mm"] * 2

    buf = io.BytesIO()
    dwg = svgwrite.Drawing(
        size=(f"{w_mm}mm", f"{h_mm}mm"),
        viewBox=f"0 0 {w_mm} {h_mm}",
        profile="tiny",
    )
    # Fond
    dwg.add(dwg.rect(insert=(0, 0), size=(w_mm, h_mm), fill=_hex(palette["fond"])))
    # Bande supérieure couleur primaire
    dwg.add(dwg.rect(insert=(0, 0), size=(w_mm, h_mm * 0.18), fill=_hex(palette["primaire"])))
    # Titre
    dwg.add(dwg.text(
        spec.titre or "",
        insert=(w_mm / 2, h_mm * 0.12),
        text_anchor="middle",
        font_size=f"{max(4, h_mm * 0.05):.1f}mm",
        font_family="Helvetica, Arial, sans-serif",
        font_weight="bold",
        fill=_hex(palette["fond"]),
    ))
    # Sous-titre
    if spec.sous_titre:
        dwg.add(dwg.text(
            spec.sous_titre,
            insert=(w_mm / 2, h_mm * 0.26),
            text_anchor="middle",
            font_size=f"{max(3, h_mm * 0.028):.1f}mm",
            font_family="Helvetica, Arial, sans-serif",
            fill=_hex(palette["texte"]),
        ))
    # Corps
    y = h_mm * 0.36
    if spec.corps:
        # Wrap manuel approx (60 car/ligne)
        corps = spec.corps
        ligne_max = 60
        lignes = [corps[i:i + ligne_max] for i in range(0, len(corps), ligne_max)][:6]
        for ligne in lignes:
            dwg.add(dwg.text(
                ligne,
                insert=(w_mm / 2, y),
                text_anchor="middle",
                font_size=f"{max(2.5, h_mm * 0.022):.1f}mm",
                font_family="Helvetica, Arial, sans-serif",
                fill=_hex(palette["texte"]),
            ))
            y += h_mm * 0.035
    # Détails (liste à puces)
    for det in (spec.details or [])[:6]:
        dwg.add(dwg.text(
            f"• {det}",
            insert=(w_mm * 0.1, y),
            font_size=f"{max(2.5, h_mm * 0.022):.1f}mm",
            font_family="Helvetica, Arial, sans-serif",
            fill=_hex(palette["texte"]),
        ))
        y += h_mm * 0.035
    # Contact en bas
    if spec.contact:
        dwg.add(dwg.rect(insert=(0, h_mm * 0.92), size=(w_mm, h_mm * 0.08), fill=_hex(palette["secondaire"])))
        dwg.add(dwg.text(
            spec.contact,
            insert=(w_mm / 2, h_mm * 0.97),
            text_anchor="middle",
            font_size=f"{max(2.5, h_mm * 0.022):.1f}mm",
            font_family="Helvetica, Arial, sans-serif",
            fill=_hex(palette["fond"]),
        ))

    svg_str = dwg.tostring()
    buf.write(svg_str.encode("utf-8"))
    return buf.getvalue()


async def generer_infographie(
    brief: str,
    type_gabarit: str,
    pays: str = "CM",
    spec_override: Optional[SpecificationInfographie] = None,
    gabarits_override: Optional[dict] = None,
    profil: Optional[dict] = None,
    dpi_preview: int = 300,
    dpi_web: int = 150,
    export_cmyk: bool = True,
    export_svg: bool = True,
    variante_hint: Optional[str] = None,
) -> ResultatInfographie:
    """
    Pipeline complet : brief → spec IA → PDF (RGB + CMJN) + PNG 300dpi + PNG 150dpi + SVG.

    Flags :
      dpi_preview : résolution du PNG haute définition (par défaut 300 DPI = print)
      dpi_web     : résolution du PNG preview web (par défaut 150 DPI)
      export_cmyk : génère aussi une version PDF CMJN prête pour offset
      export_svg  : génère un SVG vectoriel
      profil      : dict {metier, secteur, couleur_primaire_hex, ...} pour contextualisation LLM
      variante_hint : direction créative forcée ("classique", "audacieux", ...)
    """
    _gabarits = gabarits_override or GABARITS
    gabarit = _gabarits.get(type_gabarit)
    if not gabarit:
        raise ValueError(f"Gabarit inconnu : {type_gabarit}. Disponibles : {list(_gabarits.keys())}")

    tokens_meta: dict = {}
    if spec_override:
        spec = spec_override
    else:
        spec, tokens_meta = await generer_specification_depuis_brief(
            brief, type_gabarit, pays, profil=profil, variante_hint=variante_hint,
        )

    # Génération PDF RGB (principal)
    pdf_bytes: Optional[bytes] = None
    try:
        pdf_bytes = generer_pdf(spec, gabarit_info=gabarit, mode_couleur="rgb")
    except Exception as e:
        logger.error(f"[Infographe] Génération PDF RGB échouée : {e}")
        raise RuntimeError(f"Génération PDF échouée : {e}")

    # Version CMJN print-pro (en parallèle logique — séquentiel mais rapide car ReportLab)
    pdf_cmyk_bytes: Optional[bytes] = None
    if export_cmyk:
        try:
            pdf_cmyk_bytes = generer_pdf(spec, gabarit_info=gabarit, mode_couleur="cmyk")
        except Exception as e:
            logger.warning(f"[Infographe] Export CMJN échoué : {e}")

    # PNG 300 DPI (print-ready) + 150 DPI (web preview)
    png_bytes = _rendre_png(pdf_bytes, dpi=dpi_preview)
    png_preview_bytes = _rendre_png(pdf_bytes, dpi=dpi_web) if dpi_web != dpi_preview else png_bytes

    # SVG
    svg_bytes: Optional[bytes] = None
    if export_svg:
        svg_bytes = _generer_svg_depuis_spec(spec, gabarit)

    return ResultatInfographie(
        pdf_bytes=pdf_bytes,
        pdf_cmyk_bytes=pdf_cmyk_bytes,
        png_bytes=png_bytes,
        png_preview_bytes=png_preview_bytes,
        svg_bytes=svg_bytes,
        specification=spec,
        gabarit=type_gabarit,
        meta={
            "gabarit_label": gabarit["label"],
            "prix_fcfa": gabarit.get("prix_fcfa", 5000),
            "dpi_print": dpi_preview,
            "dpi_web": dpi_web,
            "cmjn_disponible": pdf_cmyk_bytes is not None,
            "svg_disponible": svg_bytes is not None,
            **tokens_meta,
        },
    )


VARIANTES_DIRECTIONS = ["classique", "audacieux", "minimaliste", "festif"]


async def generer_variantes_parallele(
    brief: str,
    type_gabarit: str,
    pays: str = "CM",
    profil: Optional[dict] = None,
    nombre: int = 4,
) -> list[ResultatInfographie]:
    """
    Génère N variantes en parallèle avec des directions créatives distinctes.
    Permet à l'utilisateur de choisir parmi plusieurs propositions (spec IA + rendu).
    """
    import asyncio as _asyncio
    directions = VARIANTES_DIRECTIONS[:max(1, min(nombre, len(VARIANTES_DIRECTIONS)))]
    taches = [
        generer_infographie(
            brief=brief,
            type_gabarit=type_gabarit,
            pays=pays,
            profil=profil,
            variante_hint=direction,
            export_cmyk=False,   # économie : on ne génère le CMJN qu'à la sélection finale
            export_svg=True,
        )
        for direction in directions
    ]
    resultats = await _asyncio.gather(*taches, return_exceptions=True)
    retour: list[ResultatInfographie] = []
    for direction, res in zip(directions, resultats):
        if isinstance(res, Exception):
            logger.warning(f"[Infographe] Variante '{direction}' échouée : {res}")
            continue
        res.meta["variante"] = direction
        retour.append(res)
    return retour


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
            mode=ModeIA.ANALYSE,
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
