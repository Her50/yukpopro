"""
Freeform Composer — LLM (Opus 4.7 / gpt-4-turbo via LLM_PRIMAIRE) compose
un JSON de layout primitive à partir d'un brief utilisateur libre.

Aucun template, aucun catalogue de pages prédéfinies. Le LLM est libre
de produire N'IMPORTE QUEL visuel imprimable :
- 8 cartes de visite 90×55mm sur A4 + crop marks
- Flyer A3 photo héroïque + texte CTA
- BD éducative 4 pages × 6 cases avec bulles dialogue
- Packaging dieline boîte produit
- CV graphique 1 page (timeline + barres compétences)
- Posts réseaux sociaux carré/9:16/paysage
- Affiche événement
- Dépliant 3 volets
- Mind map, infographie, schéma technique
- N'importe quoi d'autre

Le LLM reçoit :
- Brief utilisateur (libre)
- Médias disponibles (URLs ou refs)
- Brand kit org (palette, logo, polices, ToV)
- Verticale métier dynamique (sites officiels, ton, lexique)
- Pays + langue (auto-adapté)

Il retourne un JSON conforme au schema freeform_layout (rendu via
modules.bureau.freeform_layout.rendre_pdf_depuis_json).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger("yukpo_assurance.bureau.freeform_composer")


_PROMPT_SYSTEME = """\
Tu es DIRECTEUR DE CRÉATION SENIOR (15+ ans, Pentagram / Wieden+Kennedy /
agences Lagos-Dakar-Casablanca-Paris-Tokyo). Mission : composer le LAYOUT
d'un visuel imprimable (PDF print-ready) à partir d'un brief utilisateur.

PHILOSOPHIE :
- AUCUN template prédéfini. Tu composes LIBREMENT page par page.
- Tu es responsable de l'intégralité du visuel : format, fond, palette,
  typographie, hiérarchie, composition, alignements, espaces blancs.
- Niveau de qualité attendu : agence pro, niveau Adobe InDesign / Figma.
- Adapté au contexte : pays, langue, métier/secteur, brand kit organisation.

FORMAT DE SORTIE — JSON STRICT (rendu via ReportLab) :

{
  "titre": "Court titre du document (≤80 chars)",
  "format_mm": [LARGEUR, HAUTEUR],
  "bleed_mm": 3,
  "palette_meta": {"primaire": "#xxx", "accent": "#xxx", "fond": "#xxx"},
  "pages": [
    {
      "numero": 1,
      "fond_couleur": "#FFFFFF",
      "elements": [
        { "type": "rectangle", "x_mm": 10, "y_mm": 10, "w_mm": 90, "h_mm": 55,
          "fond": "#003D82", "border_radius_mm": 2, "z_index": 0 },
        { "type": "texte", "x_mm": 15, "y_mm": 18, "w_mm": 70,
          "contenu": "NGONO Marie", "police": "Inter-Bold", "taille_pt": 14,
          "couleur": "#FFFFFF", "alignement": "left", "z_index": 1 },
        { "type": "texte", "x_mm": 15, "y_mm": 28, "w_mm": 70,
          "contenu": "Directrice Générale", "police": "Inter", "taille_pt": 9,
          "couleur": "#FFB800", "z_index": 1 },
        { "type": "ligne", "x1_mm": 15, "y1_mm": 35, "x2_mm": 50, "y2_mm": 35,
          "epaisseur_pt": 0.5, "couleur": "#FFB800", "z_index": 1 },
        { "type": "qr", "x_mm": 75, "y_mm": 40, "w_mm": 12, "h_mm": 12,
          "donnees": "BEGIN:VCARD\\nVERSION:3.0\\nFN:NGONO Marie\\nTITLE:DG\\nEND:VCARD",
          "couleur": "#FFFFFF", "fond": "#003D82", "z_index": 2 },
        { "type": "image", "x_mm": 70, "y_mm": 12, "w_mm": 22, "h_mm": 10,
          "ref_media": "session:logo_org", "z_index": 1 },
        { "type": "crop_marks", "x_mm": 10, "y_mm": 10, "w_mm": 90, "h_mm": 55,
          "longueur_mm": 3, "epaisseur_pt": 0.25, "couleur": "#000000" }
      ]
    }
  ]
}

TYPES D'ÉLÉMENTS DISPONIBLES :

1. **rectangle** — `x_mm, y_mm, w_mm, h_mm, fond, border, border_width_pt,
   border_radius_mm, opacity` — fonds colorés, cards, panneaux
2. **texte** — `x_mm, y_mm, w_mm, contenu, police, taille_pt, couleur,
   alignement (left|center|right|justify), interligne, bold, italic, underline`
3. **image** — `x_mm, y_mm, w_mm, h_mm, ref_media (session:X|compte:X), data_url,
   url, prompt_ia (génération IA si fourni), mode (cover|contain|stretch),
   border_radius_mm` — photos uploadées, logo, image générée IA
4. **ligne** — `x1_mm, y1_mm, x2_mm, y2_mm, epaisseur_pt, couleur,
   style (solid|dashed|dotted)` — séparateurs, accents
5. **qr** — `x_mm, y_mm, w_mm, h_mm, donnees, couleur, fond` — vCard, URL,
   tracking
6. **ornement** — `x_mm, y_mm, w_mm, h_mm, motif (ligne|vague|geometrique|
   etoile|feuilles), couleur, epaisseur_pt` — décor vectoriel
7. **crop_marks** — `x_mm, y_mm, w_mm, h_mm, longueur_mm, epaisseur_pt,
   couleur, decalage_mm` — repères découpe imprimerie (auto autour des
   zones à découper : cartes de visite, étiquettes, BD cases)

POLICES DISPONIBLES (système ou embedded) :
- "Inter", "Inter-Bold", "Inter-SemiBold" (sans-serif moderne, défaut)
- "Helvetica", "Helvetica-Bold" (sans-serif classique)
- "Times-Roman", "Times-Bold", "Times-Italic" (serif éditorial)
- "Courier" (mono technique)

SYSTÈME DE COORDONNÉES :
- (0, 0) en HAUT-GAUCHE de la zone TRIM (zone finale après coupe)
- Unités en MILLIMÈTRES (mm)
- Les coordonnées sont relatives au TRIM, le bleed (3mm par défaut) est
  ajouté automatiquement par le renderer
- Pour les éléments fond perdu (image pleine page), positionne x_mm=-3,
  y_mm=-3, w_mm=format_w+6, h_mm=format_h+6 pour couvrir le bleed

RÈGLES DE COMPOSITION (qualité agence pro) :

1. **Hiérarchie typographique** — 3 niveaux max : titre principal (16-32pt),
   sous-titre (10-14pt), corps (8-10pt). Espace généreux entre les blocs.
2. **Alignement** — grille invisible, marges symétriques, texte aligné à
   gauche ou centré (jamais full justified pour visuels courts).
3. **Couleurs** — palette de 2-3 couleurs max (primaire + accent + fond).
   Si BrandKit fourni, utilise-le. Sinon palette adaptée au registre
   (sobre/festif/cérémonial/technique/ludique).
4. **Espace blanc** — laisse respirer. Pas de bord à bord avec texte sauf
   intention design (fullbleed cover).
5. **Bleed** — pour les éléments fond (couleurs, images plein-page),
   étends-les de -3mm à format_w+3mm pour éviter les bords blancs après coupe.
6. **Crop marks** — pour les visuels imprimable multi-éléments à découper
   (cartes de visite, étiquettes, BD cases), ajoute des crop_marks autour
   de chaque trim.
7. **Adaptation au brief** — pour 5 personnes / 8 cartes de visite, calcule
   la grille (ex: 2 colonnes × 4 rangs sur A4 portrait, gutter 5mm).
8. **Verticalité métier** — adapte les éléments au secteur (banque/finance
   = sobre + bleu navy + or ; santé = vert + propre ; mariage = pastel +
   floral ; tech = futuriste + sombre).

ATTENTION :
- N'invente PAS de noms / dates / chiffres si tu n'as pas l'info.
- Pour les cartes de visite, si le brief demande N personnes : génère N noms
  africains francophones réalistes + fonctions cohérentes avec l'organisation.
- Le QR vCard doit contenir VRAIMENT du contenu vCard valide (BEGIN:VCARD…
  END:VCARD avec FN, TITLE, ORG, TEL, EMAIL).
- Toujours produire un JSON STRICT, sans commentaire ni markdown.

Tu reçois maintenant le contexte (brief + médias + brand kit + verticale).
Compose le layout PARFAIT pour ce visuel.
"""


async def composer_freeform_layout(
    brief: str,
    profil: Optional[dict] = None,
    medias_descripteurs: Optional[list[dict]] = None,
    brand_kit: Optional[dict] = None,
    descripteur_vertical: Optional[dict] = None,
    pays: str = "CM",
    langue: str = "fr",
) -> dict:
    """Appelle le LLM (Opus → traduit en gpt-4-turbo via LLM_PRIMAIRE=gpt)
    pour composer un JSON de layout. Retourne le dict prêt à passer à
    `rendre_pdf_depuis_json()`.

    En cas d'échec total : retourne un layout minimal (1 page blanche A4
    avec un texte d'erreur) pour ne pas casser le pipeline appelant.
    """
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire

    profil_block = ""
    if profil:
        nom_org = profil.get("nom_organisation") or ""
        metier = profil.get("metier") or ""
        couleur_prim = profil.get("couleur_primaire_hex") or ""
        couleurs_acc = profil.get("couleurs_accents_hex") or []
        profil_block = (
            f"\n## PROFIL UTILISATEUR\n"
            f"- Organisation : {nom_org or '(non précisée)'}\n"
            f"- Métier : {metier or '(non précisé)'}\n"
            f"- Couleur primaire : {couleur_prim or '(libre)'}\n"
            f"- Couleurs accents : {', '.join(couleurs_acc) if couleurs_acc else '(libre)'}\n"
        )

    brand_block = ""
    if brand_kit:
        baseline = brand_kit.get("baseline") or ""
        tov = brand_kit.get("tone_of_voice") or ""
        lex = brand_kit.get("lexique_prefere") or []
        mots_int = brand_kit.get("mots_interdits") or []
        if baseline or tov or lex or mots_int:
            brand_block = (
                f"\n## BRAND KIT VERROUILLÉ (à respecter strictement)\n"
                f"- Baseline : {baseline or '(aucune)'}\n"
                f"- Ton : {tov or '(libre)'}\n"
                f"- Vocabulaire préféré : {', '.join(lex) if lex else '(libre)'}\n"
                f"- Mots interdits : {', '.join(mots_int) if mots_int else '(aucun)'}\n"
            )

    vertical_block = ""
    if descripteur_vertical:
        couleurs_typ = descripteur_vertical.get("couleurs_typiques") or ""
        polices_typ = descripteur_vertical.get("polices_typiques") or ""
        ton = descripteur_vertical.get("ton_recommande") or ""
        vertical_block = (
            f"\n## CONTEXTE MÉTIER ({descripteur_vertical.get('label', '')})\n"
            f"- Couleurs typiques : {couleurs_typ or '(libre)'}\n"
            f"- Polices typiques : {polices_typ or '(libre)'}\n"
            f"- Ton recommandé : {ton or '(libre)'}\n"
        )

    medias_block = ""
    if medias_descripteurs:
        medias_block = (
            f"\n## MÉDIATHÈQUE DISPONIBLE (refs réutilisables)\n"
            f"{json.dumps(medias_descripteurs, ensure_ascii=False, indent=2)}\n"
        )

    prompt_user = f"""\
## BRIEF UTILISATEUR
\"\"\"{brief[:4000]}\"\"\"

## CONTEXTE
- Pays : {pays}
- Langue : {langue}
{profil_block}{brand_block}{vertical_block}{medias_block}

Compose maintenant le layout PARFAIT pour ce brief. JSON STRICT uniquement,
sans commentaire ni markdown.
"""

    try:
        rep = await ia_client.appeler(
            prompt=prompt_user,
            systeme=_PROMPT_SYSTEME,
            mode=ModeIA.ANALYSE,
            forcer_modele=ModelePrioritaire.CLAUDE_OPUS,   # tier-traduit en gpt-4-turbo si LLM_PRIMAIRE=gpt
            json_attendu=True,
            max_tokens_override=8000,
            utiliser_cache=False,
        )
        contenu = rep.contenu or "{}"
        try:
            data = json.loads(contenu)
        except json.JSONDecodeError:
            import re as _re
            m = _re.search(r"\{[\s\S]*\}", contenu)
            data = json.loads(m.group()) if m else {}
    except Exception as e:
        logger.warning(f"[FreeformComposer] Echec LLM : {e}")
        data = {}

    # Validation minimale + correction défensive
    if not isinstance(data, dict) or not data.get("pages"):
        logger.info("[FreeformComposer] Layout LLM invalide → fallback page vide A4")
        data = _layout_fallback(brief)

    return data


def _layout_fallback(brief: str) -> dict:
    """Layout minimal de secours quand le LLM échoue totalement."""
    return {
        "titre": "Document",
        "format_mm": [210, 297],
        "bleed_mm": 3,
        "pages": [{
            "numero": 1,
            "fond_couleur": "#FFFFFF",
            "elements": [
                {
                    "type": "texte",
                    "x_mm": 20, "y_mm": 30, "w_mm": 170,
                    "contenu": "Nous n'avons pas pu composer ce visuel automatiquement. "
                                "Précise davantage ton brief ou contacte le support.",
                    "police": "Helvetica",
                    "taille_pt": 12, "couleur": "#444444",
                    "alignement": "center", "interligne": 1.4,
                },
                {
                    "type": "texte",
                    "x_mm": 20, "y_mm": 80, "w_mm": 170,
                    "contenu": f"Brief reçu : « {brief[:400]} »",
                    "police": "Helvetica", "italic": True,
                    "taille_pt": 9, "couleur": "#888888",
                    "alignement": "center", "interligne": 1.3,
                },
            ],
        }],
    }
