"""
SlideBuilder Pro v2 — Générateur de présentations PowerPoint par IA.

4 thèmes visuels distincts selon le type de présentation :
  • CORPORATE  → bilan_activite, rapport_direction
  • PITCH      → pitch_projet, proposition_client
  • FINANCE    → rapport_financier, analyse_marche
  • FORMATION  → formation

Modes : executive | detaille | pitch | expert

Sortie : PPTX (python-pptx) ou Markdown (fallback / prévisualisation)
"""
from __future__ import annotations

import io
import logging
import math
import random
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("yukpo_assurance.pro.slide_builder")

_OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "generated" / "pro_slides"
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 4 Thèmes visuels ──────────────────────────────────────────────────────────

_THEMES: dict[str, dict] = {

    # ── Corporate : Rapport & Direction ──────────────────────────────────────
    "corporate": {
        "nom":        "Corporate",
        "primaire":   (0x0A, 0x2A, 0x4A),   # Bleu marine profond
        "secondaire": (0x1C, 0x4E, 0x80),   # Bleu acier
        "accent":     (0xD4, 0xAF, 0x37),   # Or prestige
        "accent2":    (0xE8, 0xF4, 0xFF),   # Bleu très clair
        "blanc":      (0xFF, 0xFF, 0xFF),
        "gris_clair": (0xF2, 0xF6, 0xFA),
        "gris_texte": (0x44, 0x5A, 0x70),
        "texte":      (0x0A, 0x2A, 0x4A),
        "success":    (0x00, 0x8E, 0x5B),
        "danger":     (0xC0, 0x39, 0x2B),
        "cover_style": "diagonal",
        "bullet_char": "▪",
        "kpi_shape":   "rect",
    },

    # ── Pitch : Startup & Commercial ─────────────────────────────────────────
    "pitch": {
        "nom":        "Pitch",
        "primaire":   (0x1A, 0x1A, 0x2E),   # Nuit profonde
        "secondaire": (0x16, 0x21, 0x3E),   # Bleu très sombre
        "accent":     (0xE9, 0x4F, 0x37),   # Rouge vif
        "accent2":    (0xFF, 0xC3, 0x00),   # Jaune énergie
        "blanc":      (0xFF, 0xFF, 0xFF),
        "gris_clair": (0xF8, 0xF9, 0xFA),
        "gris_texte": (0x6C, 0x75, 0x7D),
        "texte":      (0x1A, 0x1A, 0x2E),
        "success":    (0x2E, 0xCC, 0x71),
        "danger":     (0xE7, 0x4C, 0x3C),
        "cover_style": "full_color",
        "bullet_char": "→",
        "kpi_shape":   "rounded",
    },

    # ── Finance : Marchés & Financier ────────────────────────────────────────
    "finance": {
        "nom":        "Finance",
        "primaire":   (0x00, 0x4D, 0x40),   # Vert forêt
        "secondaire": (0x00, 0x69, 0x57),   # Vert émeraude
        "accent":     (0x00, 0xBF, 0x6F),   # Vert clair vif
        "accent2":    (0xE8, 0xF8, 0xF2),   # Vert très pâle
        "blanc":      (0xFF, 0xFF, 0xFF),
        "gris_clair": (0xF4, 0xFB, 0xF7),
        "gris_texte": (0x3D, 0x5A, 0x47),
        "texte":      (0x00, 0x4D, 0x40),
        "success":    (0x00, 0xBF, 0x6F),
        "danger":     (0xC0, 0x39, 0x2B),
        "cover_style": "geometric",
        "bullet_char": "◆",
        "kpi_shape":   "rect",
    },

    # ── Formation : Pédagogique ───────────────────────────────────────────────
    "formation": {
        "nom":        "Formation",
        "primaire":   (0x00, 0x6E, 0xB6),   # Bleu ciel profond
        "secondaire": (0x00, 0x4F, 0x9F),   # Bleu cobalt
        "accent":     (0xFF, 0x8C, 0x00),   # Orange vif
        "accent2":    (0xFF, 0xF3, 0xE0),   # Jaune très pâle
        "blanc":      (0xFF, 0xFF, 0xFF),
        "gris_clair": (0xF0, 0xF4, 0xFF),
        "gris_texte": (0x55, 0x6A, 0x7D),
        "texte":      (0x1A, 0x2E, 0x4A),
        "success":    (0x27, 0xAE, 0x60),
        "danger":     (0xE7, 0x4C, 0x3C),
        "cover_style": "stripe",
        "bullet_char": "●",
        "kpi_shape":   "rounded",
    },
}

# Mapping type_pres → thème
_THEME_PAR_TYPE: dict[str, str] = {
    "bilan_activite":      "corporate",
    "rapport_direction":   "corporate",
    "proposition_client":  "pitch",
    "pitch_projet":        "pitch",
    "rapport_financier":   "finance",
    "analyse_marche":      "finance",
    "formation":           "formation",
}

# ── Structures par type et mode ───────────────────────────────────────────────
_STRUCTURES: dict[str, dict[str, list]] = {
    "bilan_activite": {
        "executive": [
            {"titre": "Synthèse exécutive",           "type": "kpi"},
            {"titre": "Résultats clés de la période",  "type": "bullets"},
            {"titre": "Points d'attention prioritaires","type": "bullets"},
            {"titre": "Perspectives et orientations",  "type": "bullets"},
            {"titre": "Décisions requises",            "type": "action"},
        ],
        "detaille": [
            {"titre": "Couverture",                    "type": "cover"},
            {"titre": "Sommaire",                      "type": "sommaire"},
            {"titre": "Résumé exécutif",               "type": "kpi"},
            {"titre": "Activité & Production",         "type": "bullets"},
            {"titre": "Performance commerciale",       "type": "bullets"},
            {"titre": "Résultats financiers",          "type": "kpi"},
            {"titre": "Ressources humaines",           "type": "two_columns"},
            {"titre": "Points d'attention et risques", "type": "bullets"},
            {"titre": "Initiatives en cours",          "type": "bullets"},
            {"titre": "Perspectives et plan d'action", "type": "action"},
        ],
        "pitch": [
            {"titre": "Couverture",                    "type": "cover"},
            {"titre": "Faits marquants",               "type": "kpi"},
            {"titre": "Réalisations clés",             "type": "bullets"},
            {"titre": "Chiffres & Performance",        "type": "kpi"},
            {"titre": "Défis et solutions",            "type": "two_columns"},
            {"titre": "Plan d'action",                 "type": "action"},
            {"titre": "Questions & Discussion",        "type": "fin"},
        ],
    },
    "proposition_client": {
        "executive": [
            {"titre": "Votre défi",                    "type": "bullets"},
            {"titre": "Notre proposition de valeur",   "type": "kpi"},
            {"titre": "Pourquoi nous choisir",         "type": "bullets"},
            {"titre": "Prochaines étapes",             "type": "action"},
        ],
        "detaille": [
            {"titre": "Couverture",                    "type": "cover"},
            {"titre": "Compréhension de vos besoins",  "type": "bullets"},
            {"titre": "Notre approche",                "type": "bullets"},
            {"titre": "Solution proposée",             "type": "bullets"},
            {"titre": "Méthodologie",                  "type": "bullets"},
            {"titre": "Livrables et délais",           "type": "two_columns"},
            {"titre": "Équipe dédiée",                 "type": "bullets"},
            {"titre": "Budget et modalités",           "type": "kpi"},
            {"titre": "Références et preuves",         "type": "bullets"},
            {"titre": "Prochaines étapes",             "type": "action"},
        ],
        "pitch": [
            {"titre": "Couverture",                    "type": "cover"},
            {"titre": "Votre problème",                "type": "bullets"},
            {"titre": "Notre solution",                "type": "kpi"},
            {"titre": "Pourquoi nous",                 "type": "bullets"},
            {"titre": "Investissement & ROI",          "type": "kpi"},
            {"titre": "Passons à l'action",            "type": "action"},
        ],
    },
    "rapport_direction": {
        "executive": [
            {"titre": "Tableau de bord stratégique",   "type": "kpi"},
            {"titre": "Résultats vs Objectifs",        "type": "bullets"},
            {"titre": "Risques & Alertes",             "type": "bullets"},
            {"titre": "Décisions à prendre",           "type": "action"},
        ],
        "detaille": [
            {"titre": "Couverture",                    "type": "cover"},
            {"titre": "Sommaire",                      "type": "sommaire"},
            {"titre": "Tableau de bord stratégique",   "type": "kpi"},
            {"titre": "Performance financière",        "type": "kpi"},
            {"titre": "Performance commerciale",       "type": "bullets"},
            {"titre": "Opérations et qualité",         "type": "bullets"},
            {"titre": "Ressources humaines",           "type": "two_columns"},
            {"titre": "Risques et conformité",         "type": "bullets"},
            {"titre": "Projets stratégiques",          "type": "bullets"},
            {"titre": "Perspectives",                  "type": "bullets"},
            {"titre": "Points de décision",            "type": "action"},
        ],
        "pitch": [
            {"titre": "Couverture",                    "type": "cover"},
            {"titre": "Messages clés",                 "type": "kpi"},
            {"titre": "Situation actuelle",            "type": "bullets"},
            {"titre": "Enjeux stratégiques",           "type": "bullets"},
            {"titre": "Plan d'action prioritaire",     "type": "action"},
            {"titre": "Merci",                         "type": "fin"},
        ],
    },
    "formation": {
        "executive": [
            {"titre": "Objectifs de la formation",     "type": "bullets"},
            {"titre": "Points clés à retenir",         "type": "bullets"},
            {"titre": "Synthèse",                      "type": "kpi"},
        ],
        "detaille": [
            {"titre": "Couverture",                    "type": "cover"},
            {"titre": "Objectifs pédagogiques",        "type": "bullets"},
            {"titre": "Programme",                     "type": "sommaire"},
            {"titre": "Introduction au sujet",         "type": "bullets"},
            {"titre": "Concepts fondamentaux",         "type": "two_columns"},
            {"titre": "Cadre réglementaire",           "type": "bullets"},
            {"titre": "Application pratique",          "type": "bullets"},
            {"titre": "Cas pratiques",                 "type": "bullets"},
            {"titre": "Bonnes pratiques",              "type": "bullets"},
            {"titre": "Synthèse et points clés",       "type": "kpi"},
            {"titre": "Questions / Échanges",          "type": "fin"},
        ],
        "pitch": [
            {"titre": "Couverture",                    "type": "cover"},
            {"titre": "Le contexte",                   "type": "bullets"},
            {"titre": "Ce qu'il faut absolument savoir","type": "bullets"},
            {"titre": "Application concrète",          "type": "bullets"},
            {"titre": "Erreurs à éviter",              "type": "bullets"},
            {"titre": "À retenir",                     "type": "kpi"},
            {"titre": "Questions",                     "type": "fin"},
        ],
    },
    "pitch_projet": {
        "executive": [
            {"titre": "Le problème",                   "type": "bullets"},
            {"titre": "Notre solution",                "type": "kpi"},
            {"titre": "Impact attendu",                "type": "bullets"},
            {"titre": "Appel à l'action",              "type": "action"},
        ],
        "detaille": [
            {"titre": "Couverture",                    "type": "cover"},
            {"titre": "Le problème à résoudre",        "type": "bullets"},
            {"titre": "Notre solution",                "type": "bullets"},
            {"titre": "Modèle et approche",            "type": "bullets"},
            {"titre": "Marché et opportunité",         "type": "kpi"},
            {"titre": "Équipe",                        "type": "two_columns"},
            {"titre": "Traction et résultats",         "type": "kpi"},
            {"titre": "Budget et besoins",             "type": "bullets"},
            {"titre": "Feuille de route",              "type": "bullets"},
            {"titre": "Appel à l'action",              "type": "action"},
        ],
        "pitch": [
            {"titre": "Couverture",                    "type": "cover"},
            {"titre": "Le problème",                   "type": "bullets"},
            {"titre": "La solution",                   "type": "kpi"},
            {"titre": "Le marché",                     "type": "bullets"},
            {"titre": "Business model",                "type": "bullets"},
            {"titre": "Traction",                      "type": "kpi"},
            {"titre": "L'équipe",                      "type": "bullets"},
            {"titre": "Notre demande",                 "type": "action"},
        ],
    },
    "rapport_financier": {
        "executive": [
            {"titre": "Indicateurs clés",              "type": "kpi"},
            {"titre": "Performance financière",        "type": "bullets"},
            {"titre": "Analyse des risques",           "type": "bullets"},
            {"titre": "Recommandations",               "type": "action"},
        ],
        "detaille": [
            {"titre": "Couverture",                    "type": "cover"},
            {"titre": "Sommaire",                      "type": "sommaire"},
            {"titre": "Indicateurs financiers clés",   "type": "kpi"},
            {"titre": "Compte de résultat",            "type": "bullets"},
            {"titre": "Bilan & Trésorerie",            "type": "kpi"},
            {"titre": "Analyse des charges",           "type": "bullets"},
            {"titre": "Analyse des revenus",           "type": "bullets"},
            {"titre": "Ratios & Performance",          "type": "two_columns"},
            {"titre": "Risques financiers",            "type": "bullets"},
            {"titre": "Recommandations",               "type": "action"},
        ],
        "pitch": [
            {"titre": "Couverture",                    "type": "cover"},
            {"titre": "Synthèse financière",           "type": "kpi"},
            {"titre": "Points forts",                  "type": "bullets"},
            {"titre": "Zones de vigilance",            "type": "bullets"},
            {"titre": "Recommandations prioritaires",  "type": "action"},
        ],
    },
    "analyse_marche": {
        "executive": [
            {"titre": "Insights marché",               "type": "kpi"},
            {"titre": "Opportunités",                  "type": "bullets"},
            {"titre": "Menaces et risques",            "type": "bullets"},
            {"titre": "Recommandations stratégiques",  "type": "action"},
        ],
        "detaille": [
            {"titre": "Couverture",                    "type": "cover"},
            {"titre": "Sommaire",                      "type": "sommaire"},
            {"titre": "Vue d'ensemble du marché",      "type": "kpi"},
            {"titre": "Analyse de la demande",         "type": "bullets"},
            {"titre": "Paysage concurrentiel",         "type": "bullets"},
            {"titre": "Tendances sectorielles",        "type": "bullets"},
            {"titre": "Analyse SWOT",                  "type": "two_columns"},
            {"titre": "Opportunités identifiées",      "type": "bullets"},
            {"titre": "Risques et barrières",          "type": "bullets"},
            {"titre": "Recommandations stratégiques",  "type": "action"},
        ],
        "pitch": [
            {"titre": "Couverture",                    "type": "cover"},
            {"titre": "Le marché en chiffres",         "type": "kpi"},
            {"titre": "Forces en présence",            "type": "bullets"},
            {"titre": "Où sont les opportunités",      "type": "bullets"},
            {"titre": "Notre positionnement",          "type": "action"},
        ],
    },
}

_TOKENS_PAR_MODE = {"executive": 6000, "detaille": 16000, "pitch": 10000, "expert": 24000}

# Taille des lots (nb slides par appel IA) pour contourner le plafond par appel
# et maximiser la densité des slides sans troncature silencieuse.
_SLIDES_PAR_LOT = {"executive": 99, "pitch": 99, "detaille": 10, "expert": 8}


# ── Helpers PPTX ──────────────────────────────────────────────────────────────

def _rgb(t: tuple) -> "RGBColor":
    from pptx.dml.color import RGBColor
    return RGBColor(*t)


def _rect(slide, left, top, width, height, fill_color, line=False):
    """Ajoute un rectangle solide."""
    shp = slide.shapes.add_shape(1, int(left), int(top), int(width), int(height))
    shp.fill.solid()
    shp.fill.fore_color.rgb = _rgb(fill_color)
    if not line:
        shp.line.fill.background()
    return shp


def _textbox(slide, left, top, width, height) -> "TextFrame":
    tb = slide.shapes.add_textbox(int(left), int(top), int(width), int(height))
    return tb.text_frame


def _para(tf, text: str, size: int, bold=False, color=None, align="left", italic=False,
          space_before=0, space_after=0):
    """Ajoute un paragraphe dans un TextFrame."""
    from pptx.util import Pt
    from pptx.enum.text import PP_ALIGN

    p = tf.add_paragraph() if tf.paragraphs[0].runs else tf.paragraphs[0]
    # Si déjà un paragraphe avec du texte, ajouter un nouveau
    if tf.paragraphs[-1].runs:
        p = tf.add_paragraph()
    else:
        p = tf.paragraphs[-1]

    p.space_before = Pt(space_before)
    p.space_after  = Pt(space_after)
    _align_map = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}
    p.alignment = _align_map.get(align, PP_ALIGN.LEFT)

    run = p.add_run()
    run.text       = text
    run.font.size  = Pt(size)
    run.font.bold  = bold
    run.font.italic = italic
    if color:
        run.font.color.rgb = _rgb(color)
    return p


class SlideBuilderPro:
    """Générateur de présentations PowerPoint avec 4 thèmes visuels distincts."""

    def __init__(self, profil=None):
        self._profil = profil
        self._theme: dict = {}

    async def generer(
        self,
        sujet:          str,
        type_pres:      str = "rapport_direction",
        mode:           str = "executive",
        contexte:       Optional[str] = None,
        donnees:        Optional[dict] = None,
        format_sortie:  str = "pptx",
    ) -> dict:
        if type_pres not in _STRUCTURES:
            type_pres = "rapport_direction"
        if mode not in ("executive", "detaille", "pitch", "expert"):
            mode = "executive"

        # Sélection du thème
        nom_theme = _THEME_PAR_TYPE.get(type_pres, "corporate")
        self._theme = _THEMES[nom_theme]

        structure_mode = "detaille" if mode == "expert" else mode
        structure = _STRUCTURES[type_pres][structure_mode]
        if mode == "expert":
            structure = structure + [
                {"titre": f"Analyse approfondie — {s['titre']}", "type": s["type"]}
                for s in structure if s["type"] not in ("cover", "fin", "sommaire")
            ]

        slides_contenu = await self._generer_contenu_ia(
            sujet=sujet, type_pres=type_pres, mode=mode,
            structure=structure, contexte=contexte, donnees=donnees,
        )

        nom_fichier = self._nom_fichier(sujet, type_pres, mode)

        if format_sortie in ("pptx", "pdf"):
            chemin = await self._construire_pptx(nom_fichier, sujet, slides_contenu, type_pres, mode)
            chemin_str = str(chemin) if chemin else None
            if format_sortie == "pdf" and chemin_str:
                pdf_path = await self._convertir_en_pdf(Path(chemin_str))
                if pdf_path:
                    chemin_str = str(pdf_path)
                else:
                    logger.warning("[SlideBuilder] Conversion PDF échouée — PPTX retourné")
                    format_sortie = "pptx"
        else:
            chemin_str = None

        contenu_md = self._slides_vers_markdown(sujet, slides_contenu)

        if self._profil:
            try:
                from core.database import async_session_maker
                from modules.pro.service_profil import incrementer_stat
                async with async_session_maker() as db:
                    await incrementer_stat(self._profil.user_id, "nb_slides", db, xp_gain=5)
            except Exception:
                pass

        ext_map = {"pptx": ".pptx", "pdf": ".pdf", "markdown": ".md"}
        return {
            "chemin_fichier":   chemin_str,
            "nom_fichier":      nom_fichier + ext_map.get(format_sortie, ".md"),
            "contenu_markdown": contenu_md,
            "nb_slides":        len(slides_contenu),
            "mode":             mode,
            "type_pres":        type_pres,
            "theme":            nom_theme,
            "sujet":            sujet,
            "genere_le":        datetime.utcnow().isoformat(),
        }

    # ── Génération IA ─────────────────────────────────────────────────────────

    async def _generer_contenu_ia(
        self,
        sujet: str, type_pres: str, mode: str,
        structure: list[dict], contexte: Optional[str], donnees: Optional[dict],
    ) -> list[dict]:
        from core.ia_client import ModeIA, ia_client
        from core.pays_devise import vocabulaire_devise

        metier_info  = f"Métier : {self._profil.metier}" if self._profil else ""
        pays_info    = f"Pays : {self._profil.pays}"     if self._profil else ""
        devise_locale = vocabulaire_devise(self._profil.pays if self._profil else None)

        titres_str = "\n".join(
            f'{i+1}. "{s["titre"]}" (type: {s["type"]})'
            for i, s in enumerate(structure)
        )

        contexte_str = (
            f"\n\n{'═'*60}\nDONNÉES SOURCE (EXPLOITER INTÉGRALEMENT) :\n{'═'*60}\n{contexte}"
        ) if contexte else ""
        donnees_str = f"\n\nDONNÉES SUPPLÉMENTAIRES :\n{donnees}" if donnees else ""
        nb_slides   = len(structure)

        instructions_donnees = (
            "\n\nOBLIGATIONS SI DES DONNÉES SONT FOURNIES :\n"
            "• Extraire les chiffres réels et les placer dans les KPIs\n"
            "• Calculer variations, totaux, pourcentages à partir des données\n"
            "• Les KPIs doivent refléter les données réelles — jamais de valeurs fictives\n"
            "• Identifier les tendances clés et les mettre en avant\n"
        ) if contexte else ""

        prompt = (
            f"Crée une présentation PowerPoint professionnelle de TRÈS HAUTE QUALITÉ sur :\n\n"
            f"SUJET / INSTRUCTION : {sujet}\n"
            f"TYPE : {type_pres.replace('_', ' ')}\n"
            f"MODE : {mode}\n"
            f"{metier_info} {pays_info}"
            f"{contexte_str}{donnees_str}"
            f"{instructions_donnees}\n\n"
            f"SLIDES À GÉNÉRER ({nb_slides} slides) :\n{titres_str}\n\n"
            f"CONSIGNES DE QUALITÉ ÉLEVÉE :\n"
            f"• 4 à 6 points par slide, percutants et factuels (jamais de généralités)\n"
            f"• Slides type 'kpi' : exactement 3-5 KPIs chiffrés avec unité, valeur réelle et tendance\n"
            f"• Slides type 'action' : actions SMART avec responsable, délai concret, ressource\n"
            f"• Slides type 'two_columns' : 'points' = [{{'gauche': [...], 'droite': [...]}}] — liste des items gauche et droite\n"
            f"• Messages clés tirés des données réelles fournies\n"
            f"• Langage professionnel niveau direction générale / investisseurs\n"
            f"• Devise locale OBLIGATOIRE pour tous les montants : {devise_locale}\n"
            f"• Références réglementaires : adapter au pays/secteur (OHADA/SYSCOHADA/BEAC/CEMAC "
            f"si Afrique francophone ; IFRS/normes locales sinon — ne pas forcer un cadre régional non pertinent)\n"
            f"• Chaque slide doit avoir un titre percutant et un message accrocheur\n\n"
            f"RÉPONDS UNIQUEMENT EN JSON (sans balise markdown) :\n"
            f'{{"slides": ['
            f'{{"titre": "...", "type": "...", '
            f'"points": ["point1 factuel", "point2..."], '
            f'"kpis": [{{"label": "Libellé", "valeur": "1 234 (devise locale {devise_locale})", "tendance": "hausse|baisse|stable"}}], '
            f'"message_cle": "Message fort de la slide en 1 phrase percutante", '
            f'"notes_orateur": "OBLIGATOIRE — 3 à 5 phrases substantives pour le présentateur '
            f'(contexte, transitions, anecdote, chiffre supplémentaire, anticipation question)"'
            f'}}]}}'
        )

        systeme_prompt = (
            "Tu es un expert en communication stratégique et présentation d'excellence "
            "pour dirigeants et investisseurs. Tu produis des présentations niveau McKinsey/BCG : "
            "messages percutants, données concrètes, KPIs réels, recommandations actionnables. "
            "Si des données ou contexte sont fournis, tu les exploites INTÉGRALEMENT. "
            "Tu ne génères JAMAIS de données fictives si des données réelles sont disponibles. "
            "Réponds uniquement en JSON valide."
        )

        taille_lot = _SLIDES_PAR_LOT.get(mode, 99)
        if taille_lot >= len(structure):
            reponse_ia = await ia_client.appeler(
                prompt=prompt, systeme=systeme_prompt, mode=ModeIA.REDACTION,
                max_tokens_override=_TOKENS_PAR_MODE[mode],
                json_attendu=True, utiliser_cache=False,
            )
            return self._parser_slides_json(reponse_ia.contenu, structure)

        # Chunking SÉQUENTIEL avec contexte cumulatif (élimine les doublons
        # de slides quand on a plusieurs lots pour les modes longs).
        lots = [structure[i:i + taille_lot] for i in range(0, len(structure), taille_lot)]

        def _resumer_slides_pour_contexte(slides: list[dict], max_chars: int = 2000) -> str:
            if not slides:
                return ""
            morceaux = []
            for j, s in enumerate(slides, 1):
                titre = (s.get("titre") or "").strip()
                msg = (s.get("message_cle") or "").strip()
                points = s.get("points") or []
                pts_courts = [str(p)[:80] for p in points[:3]] if isinstance(points, list) else []
                ligne = f"{j}. « {titre} » — {msg[:120]}"
                if pts_courts:
                    ligne += " | " + " · ".join(pts_courts)
                morceaux.append(ligne)
            r = "\n".join(morceaux)
            return r[:max_chars] + ("…" if len(r) > max_chars else "")

        slides_out: list[dict] = []
        for idx, lot in enumerate(lots):
            titres_lot = "\n".join(
                f'{i+1}. "{s["titre"]}" (type: {s["type"]})'
                for i, s in enumerate(lot)
            )
            prompt_lot = prompt.replace(
                f"SLIDES À GÉNÉRER ({nb_slides} slides) :\n{titres_str}",
                f"⚙️ LOT {idx+1}/{len(lots)} — génère UNIQUEMENT ces {len(lot)} slides :\n{titres_lot}",
            )
            resume_prec = _resumer_slides_pour_contexte(slides_out)
            if resume_prec:
                prompt_lot = (
                    f"📚 SLIDES DÉJÀ GÉNÉRÉES — NE PAS DUPLIQUER, NE PAS REFORMULER :\n"
                    f"{resume_prec}\n"
                    f"{'─'*50}\n"
                    f"⚠️ Tes nouvelles slides doivent COMPLÉTER les précédentes (pas répéter "
                    f"leurs titres, leurs messages-clés ou leurs points). Construis sur ce qui "
                    f"a déjà été dit avec angles différents et nouvelles données.\n\n"
                    + prompt_lot
                )
            try:
                rep = await ia_client.appeler(
                    prompt=prompt_lot, systeme=systeme_prompt, mode=ModeIA.REDACTION,
                    max_tokens_override=_TOKENS_PAR_MODE[mode],
                    json_attendu=True, utiliser_cache=False,
                )
                slides_out.extend(self._parser_slides_json(rep.contenu, lot))
            except Exception as e:
                logger.warning(f"[SlideBuilder] Lot {idx+1} échoué : {e}")
                slides_out.extend(
                    {"titre": s["titre"], "type": s["type"], "points": [],
                     "kpis": [], "message_cle": "", "note": ""}
                    for s in lot
                )

        # ── Anti-doublon final : déduplication par titre ────────────────
        vus_titres = set()
        slides_dedup: list[dict] = []
        for s in slides_out:
            t_norm = (s.get("titre") or "").strip().lower()
            if t_norm and t_norm in vus_titres:
                logger.info(f"[SlideBuilder] Doublon supprimé : {s.get('titre')}")
                continue
            if t_norm:
                vus_titres.add(t_norm)
            slides_dedup.append(s)
        return slides_dedup

    def _parser_slides_json(self, texte: str, structure: list[dict]) -> list[dict]:
        import json, re

        def _normaliser_points(points, type_slide: str) -> list:
            if not isinstance(points, list):
                return []
            if type_slide == "two_columns":
                return points
            flat: list[str] = []
            for p in points:
                if isinstance(p, str):
                    flat.append(p)
                elif isinstance(p, dict):
                    g = p.get("gauche") or []
                    d = p.get("droite") or []
                    if g or d:
                        flat.extend(str(x) for x in list(g) + list(d) if x)
                    else:
                        label = p.get("label") or p.get("titre") or p.get("nom") or ""
                        val   = p.get("valeur") or p.get("value") or p.get("description") or ""
                        flat.append(f"{label} : {val}".strip(" :") or json.dumps(p, ensure_ascii=False))
                else:
                    flat.append(str(p))
            return flat

        def _normaliser_kpis(kpis) -> list[dict]:
            if not isinstance(kpis, list):
                return []
            out: list[dict] = []
            for k in kpis:
                if isinstance(k, dict):
                    out.append({
                        "label":    str(k.get("label", "") or ""),
                        "valeur":   str(k.get("valeur", k.get("value", "—"))),
                        "tendance": str(k.get("tendance", "stable")),
                    })
                elif isinstance(k, str):
                    out.append({"label": k, "valeur": "—", "tendance": "stable"})
            return out

        try:
            match = re.search(r'\{[\s\S]*"slides"[\s\S]*\}', texte)
            if match:
                data   = json.loads(match.group())
                slides = data.get("slides", [])
                if slides:
                    result = []
                    for slide, struct in zip(slides, structure):
                        type_s = struct["type"]
                        # `notes_orateur` (nouveau, mandaté par le prompt TOP 2)
                        # avec fallback sur `note` (ancien champ optionnel) pour
                        # rétrocompatibilité avec les réponses cached.
                        notes_val = (
                            slide.get("notes_orateur")
                            or slide.get("note")
                            or ""
                        )
                        result.append({
                            "titre":          str(slide.get("titre", struct["titre"]) or struct["titre"]),
                            "type":           type_s,
                            "points":         _normaliser_points(slide.get("points", []), type_s),
                            "kpis":           _normaliser_kpis(slide.get("kpis", [])),
                            "message_cle":    str(slide.get("message_cle", "") or ""),
                            "notes_orateur":  str(notes_val or ""),
                        })
                    return result
        except Exception as e:
            logger.warning(f"[SlideBuilder] Erreur parsing JSON slides : {e}")

        return [
            {"titre": s["titre"], "type": s["type"], "points": [], "kpis": [], "message_cle": "", "notes_orateur": ""}
            for s in structure
        ]

    # ── Construction PPTX ─────────────────────────────────────────────────────

    async def _convertir_en_pdf(self, pptx_path: Path) -> Optional[Path]:
        """Convertit un PPTX en PDF via LibreOffice headless."""
        import asyncio as _aio
        try:
            pptx_path = Path(pptx_path)
            if not pptx_path.exists():
                return None
            out_dir = pptx_path.parent
            for cmd in ("soffice", "libreoffice"):
                try:
                    proc = await _aio.create_subprocess_exec(
                        cmd, "--headless", "--convert-to", "pdf",
                        "--outdir", str(out_dir), str(pptx_path),
                        stdout=_aio.subprocess.PIPE, stderr=_aio.subprocess.PIPE,
                    )
                    _, err = await _aio.wait_for(proc.communicate(), timeout=120)
                    if proc.returncode == 0:
                        pdf_path = out_dir / (pptx_path.stem + ".pdf")
                        if pdf_path.exists() and pdf_path.stat().st_size > 0:
                            logger.info(f"[SlideBuilder] PDF généré : {pdf_path.name}")
                            return pdf_path
                except FileNotFoundError:
                    continue
                except _aio.TimeoutError:
                    return None
            return None
        except Exception as e:
            logger.error(f"[SlideBuilder] Conversion PDF échouée : {e}")
            return None

    async def _construire_pptx(
        self,
        nom_fichier: str,
        sujet:       str,
        slides:      list[dict],
        type_pres:   str,
        mode:        str,
    ) -> Optional[Path]:
        try:
            from pptx import Presentation
            from pptx.util import Inches
        except ImportError:
            logger.warning("[SlideBuilder] python-pptx non disponible")
            return None

        prs = Presentation()
        prs.slide_width  = Inches(13.33)
        prs.slide_height = Inches(7.5)

        # ── Métadonnées PPTX (Fichier > Propriétés sous PowerPoint) ───────
        # Avant : 0 metadata. Après : title/author/subject/keywords/category
        # renseignés → indexable DMS, perception "logiciel pro" immédiate.
        try:
            cp = prs.core_properties
            cp.title = (sujet or "")[:255]
            cp.subject = f"{type_pres} ({mode})"
            if self._profil:
                auteur = (
                    getattr(self._profil, "nom_complet", None)
                    or getattr(self._profil, "nom", None)
                    or getattr(self._profil, "user_nom", None)
                    or "Yukpo"
                )
                cp.author = str(auteur)[:255]
                cp.last_modified_by = str(auteur)[:255]
                org = (
                    getattr(self._profil, "nom_organisation", None)
                    or getattr(self._profil, "entreprise", None) or ""
                )
                if org:
                    cp.company = str(org)[:255]
            else:
                cp.author = "Yukpo"
            kw = [type_pres, mode]
            try:
                if self._profil:
                    pays = getattr(self._profil, "pays", None)
                    if pays: kw.append(str(pays))
                    metier = getattr(self._profil, "metier", None)
                    if metier: kw.append(str(metier))
            except Exception:
                pass
            cp.keywords = ", ".join(filter(None, kw))[:255]
            cp.category = "Présentation"
            cp.comments = "Généré par Yukpo Pro"
        except Exception as _e_meta:
            logger.debug(f"[SlideBuilder] Métadonnées PPTX non posées : {_e_meta}")

        nb_total = len(slides)
        for idx, slide_data in enumerate(slides):
            self._ajouter_slide(prs, slide_data, sujet, idx + 1, nb_total)

        chemin = _OUTPUT_DIR / (nom_fichier + ".pptx")
        prs.save(str(chemin))
        logger.info(f"[SlideBuilder] PPTX ({self._theme['nom']}) → {chemin}")
        return chemin

    # ── Dispatcher slides ─────────────────────────────────────────────────────

    def _ajouter_slide(self, prs, slide_data: dict, sujet: str, num: int, total: int):
        from pptx.util import Inches

        type_slide = slide_data.get("type", "bullets")
        slide_layout = prs.slide_layouts[6]  # Blank
        slide = prs.slides.add_slide(slide_layout)
        w = prs.slide_width
        h = prs.slide_height
        T = self._theme

        # ── Fond de slide ────────────────────────────────────────────────────
        _rect(slide, 0, 0, w, h, T["gris_clair"])

        if type_slide == "cover":
            self._slide_cover(slide, sujet, w, h)
        elif type_slide == "fin":
            self._slide_fin(slide, sujet, w, h)
        elif type_slide == "sommaire":
            self._slide_sommaire(slide, slide_data, w, h)
        elif type_slide == "kpi":
            self._slide_header(slide, slide_data["titre"], w, h, num, total)
            self._slide_kpi(slide, slide_data, w, h)
        elif type_slide == "two_columns":
            self._slide_header(slide, slide_data["titre"], w, h, num, total)
            self._slide_two_columns(slide, slide_data, w, h)
        elif type_slide == "action":
            self._slide_header(slide, slide_data["titre"], w, h, num, total)
            self._slide_action(slide, slide_data, w, h)
        else:
            self._slide_header(slide, slide_data["titre"], w, h, num, total)
            self._slide_bullets(slide, slide_data, w, h)

        # Pied de page (sauf cover/fin)
        if type_slide not in ("cover", "fin"):
            self._slide_footer(slide, w, h, num, total)

        # ── Notes orateur (TOP 2) ────────────────────────────────────────────
        # Le LLM a généré 3-5 phrases substantives par slide (cf. prompt).
        # On les injecte dans le panneau "Notes" PowerPoint via notes_slide.
        # Avant : aucune note (grep notes_slide = 0). Après : presenter view
        # natif PowerPoint utilisable en démo client / training équipe.
        notes_txt = (slide_data.get("notes_orateur") or slide_data.get("note") or "").strip()
        if notes_txt:
            try:
                ns = slide.notes_slide
                ns.notes_text_frame.text = notes_txt
            except Exception as _e_ns:
                logger.debug(f"[SlideBuilder] Notes slide {num} non injectées : {_e_ns}")

    # ── Header commun ─────────────────────────────────────────────────────────

    def _slide_header(self, slide, titre: str, w, h, num: int, total: int):
        """Bande de titre avec trait d'accent."""
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN
        T = self._theme

        # Bande fond primaire
        hdr_h = Inches(1.15)
        _rect(slide, 0, 0, w, hdr_h, T["primaire"])

        # Trait accent vertical gauche
        _rect(slide, 0, 0, Inches(0.06), hdr_h, T["accent"])

        # Titre
        tb = slide.shapes.add_textbox(
            int(Inches(0.2)), int(Inches(0.1)),
            int(w - Inches(1.5)), int(hdr_h - Inches(0.1))
        )
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        run = p.add_run()
        run.text = titre.upper()
        run.font.size  = Pt(20)
        run.font.bold  = True
        run.font.color.rgb = _rgb(T["blanc"])

        # Numéro de slide (discret, coin droit)
        tb_num = slide.shapes.add_textbox(
            int(w - Inches(1.3)), int(Inches(0.38)),
            int(Inches(1.1)), int(Inches(0.4))
        )
        tf_num = tb_num.text_frame
        p_num  = tf_num.paragraphs[0]
        from pptx.enum.text import PP_ALIGN
        p_num.alignment = PP_ALIGN.RIGHT
        run_num = p_num.add_run()
        run_num.text = f"{num}/{total}"
        run_num.font.size = Pt(9)
        run_num.font.color.rgb = _rgb(T["accent"])

    # ── Slide COVER ───────────────────────────────────────────────────────────

    def _slide_cover(self, slide, sujet: str, w, h):
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN
        T = self._theme
        style = T["cover_style"]

        if style == "diagonal":
            self._cover_diagonal(slide, sujet, w, h, T)
        elif style == "full_color":
            self._cover_full_color(slide, sujet, w, h, T)
        elif style == "geometric":
            self._cover_geometric(slide, sujet, w, h, T)
        else:
            self._cover_stripe(slide, sujet, w, h, T)

    def _cover_diagonal(self, slide, sujet: str, w, h, T):
        """Corporate : fond blanc, bande diagonale bleue, accent or."""
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN
        from pptx.util import Emu

        _rect(slide, 0, 0, w, h, T["blanc"])
        # Grande bande primaire (60% gauche)
        _rect(slide, 0, 0, int(w * 0.60), h, T["primaire"])
        # Trait accent vertical
        _rect(slide, int(w * 0.60), 0, Inches(0.12), h, T["accent"])
        # Petit rectangle accent en bas
        _rect(slide, 0, int(h - Inches(0.5)), int(w * 0.60), Inches(0.5), T["accent"])

        # Titre sur fond bleu
        tb = slide.shapes.add_textbox(int(Inches(0.7)), int(Inches(2.0)),
                                       int(w * 0.55), int(Inches(2.5)))
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        run = p.add_run()
        run.text = sujet
        run.font.size  = Pt(30)
        run.font.bold  = True
        run.font.color.rgb = _rgb(T["blanc"])

        # Sous-titre / métier
        metier = self._profil.metier.title() if self._profil else "Présentation Professionnelle"
        tb2 = slide.shapes.add_textbox(int(Inches(0.7)), int(Inches(4.8)),
                                        int(w * 0.55), int(Inches(0.8)))
        tf2 = tb2.text_frame
        p2  = tf2.paragraphs[0]
        p2.alignment = PP_ALIGN.LEFT
        run2 = p2.add_run()
        run2.text = f"{metier}  •  {datetime.now().strftime('%B %Y').capitalize()}"
        run2.font.size  = Pt(14)
        run2.font.color.rgb = _rgb(T["accent"])

        # Côté droit : logo placeholder ou motif décoratif (cercles)
        for i, (cx, cy, r, alpha) in enumerate([
            (int(w * 0.82), int(h * 0.3), Inches(0.9), T["accent"]),
            (int(w * 0.87), int(h * 0.55), Inches(0.5), T["secondaire"]),
            (int(w * 0.75), int(h * 0.65), Inches(0.3), T["accent"]),
        ]):
            shp = slide.shapes.add_shape(9, cx - r, cy - r, r * 2, r * 2)  # 9 = ellipse
            shp.fill.solid()
            shp.fill.fore_color.rgb = _rgb(alpha)
            shp.line.fill.background()

    def _cover_full_color(self, slide, sujet: str, w, h, T):
        """Pitch : fond sombre, grande typographie, trait de couleur."""
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN

        _rect(slide, 0, 0, w, h, T["primaire"])
        # Ligne horizontale accent
        _rect(slide, Inches(0.8), int(h * 0.42), int(w - Inches(1.6)), Inches(0.04), T["accent"])
        # Rectangles décoratifs
        _rect(slide, 0, 0, Inches(0.15), h, T["accent"])
        _rect(slide, int(w - Inches(0.15)), 0, Inches(0.15), h, T["accent2"])

        tb = slide.shapes.add_textbox(int(Inches(0.8)), int(Inches(1.8)),
                                       int(w - Inches(1.6)), int(Inches(2.0)))
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        run = p.add_run()
        run.text = sujet
        run.font.size  = Pt(34)
        run.font.bold  = True
        run.font.color.rgb = _rgb(T["blanc"])

        metier = self._profil.metier.title() if self._profil else "Présentation"
        tb2 = slide.shapes.add_textbox(int(Inches(0.8)), int(h * 0.47),
                                        int(w - Inches(1.6)), int(Inches(0.8)))
        tf2 = tb2.text_frame
        p2  = tf2.paragraphs[0]
        p2.alignment = PP_ALIGN.LEFT
        run2 = p2.add_run()
        run2.text = f"{metier}  ·  {datetime.now().strftime('%B %Y').capitalize()}"
        run2.font.size  = Pt(15)
        run2.font.color.rgb = _rgb(T["accent"])

    def _cover_geometric(self, slide, sujet: str, w, h, T):
        """Finance : fond blanc, triangle vert, chiffres."""
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN

        _rect(slide, 0, 0, w, h, T["blanc"])
        # Bandes verticales gauche
        _rect(slide, 0, 0, Inches(0.5), h, T["primaire"])
        _rect(slide, Inches(0.5), 0, Inches(0.12), h, T["accent"])
        # Bande horizontale haut
        _rect(slide, 0, 0, w, Inches(0.5), T["primaire"])
        # Bloc coloré bas droite
        _rect(slide, int(w * 0.65), int(h * 0.65), int(w * 0.35), int(h * 0.35), T["accent2"])

        tb = slide.shapes.add_textbox(int(Inches(1.0)), int(Inches(1.2)),
                                       int(w * 0.60), int(Inches(2.8)))
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        run = p.add_run()
        run.text = sujet
        run.font.size  = Pt(30)
        run.font.bold  = True
        run.font.color.rgb = _rgb(T["primaire"])

        metier = self._profil.metier.title() if self._profil else "Analyse"
        tb2 = slide.shapes.add_textbox(int(Inches(1.0)), int(Inches(5.0)),
                                        int(w * 0.60), int(Inches(0.8)))
        tf2 = tb2.text_frame
        p2  = tf2.paragraphs[0]
        run2 = p2.add_run()
        run2.text = f"{metier}  |  {datetime.now().strftime('%B %Y').capitalize()}"
        run2.font.size  = Pt(13)
        run2.font.color.rgb = _rgb(T["accent"])

    def _cover_stripe(self, slide, sujet: str, w, h, T):
        """Formation : fond clair, bandes colorées, style éducatif."""
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN

        _rect(slide, 0, 0, w, h, T["gris_clair"])
        # Bande primaire en haut (40% hauteur)
        top_h = int(h * 0.42)
        _rect(slide, 0, 0, w, top_h, T["primaire"])
        # Trait accent
        _rect(slide, 0, top_h, w, Inches(0.09), T["accent"])

        # Titre sur fond coloré
        tb = slide.shapes.add_textbox(int(Inches(0.8)), int(Inches(0.6)),
                                       int(w - Inches(1.6)), int(top_h - Inches(0.8)))
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        run = p.add_run()
        run.text = sujet
        run.font.size  = Pt(28)
        run.font.bold  = True
        run.font.color.rgb = _rgb(T["blanc"])

        # Sous-partie sur fond clair
        metier = self._profil.metier.title() if self._profil else "Formation"
        tb2 = slide.shapes.add_textbox(int(Inches(0.8)), int(top_h + Inches(0.5)),
                                        int(w - Inches(1.6)), int(Inches(0.8)))
        tf2 = tb2.text_frame
        p2  = tf2.paragraphs[0]
        run2 = p2.add_run()
        run2.text = f"🎓  {metier}  •  {datetime.now().strftime('%B %Y').capitalize()}"
        run2.font.size  = Pt(14)
        run2.font.bold  = True
        run2.font.color.rgb = _rgb(T["primaire"])

        # Rectangles déco bas
        for i in range(5):
            x = int(Inches(0.8) + i * Inches(1.5))
            clr = T["accent"] if i % 2 == 0 else T["secondaire"]
            _rect(slide, x, int(h - Inches(0.8)), Inches(1.2), Inches(0.08), clr)

    # ── Slide FIN ─────────────────────────────────────────────────────────────

    def _slide_fin(self, slide, sujet: str, w, h):
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN
        T = self._theme

        _rect(slide, 0, 0, w, h, T["primaire"])
        _rect(slide, 0, int(h * 0.5), w, Inches(0.06), T["accent"])

        tb = slide.shapes.add_textbox(int(Inches(2)), int(Inches(2.0)),
                                       int(w - Inches(4)), int(Inches(1.8)))
        tf = tb.text_frame
        p  = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = "Merci pour votre attention"
        run.font.size  = Pt(32)
        run.font.bold  = True
        run.font.color.rgb = _rgb(T["blanc"])

        tb2 = slide.shapes.add_textbox(int(Inches(2)), int(h * 0.5 + Inches(0.5)),
                                        int(w - Inches(4)), int(Inches(1.2)))
        tf2 = tb2.text_frame
        p2  = tf2.paragraphs[0]
        p2.alignment = PP_ALIGN.CENTER
        run2 = p2.add_run()
        run2.text = "Questions & Échanges"
        run2.font.size  = Pt(20)
        run2.font.color.rgb = _rgb(T["accent"])

        # Branding bas
        tb3 = slide.shapes.add_textbox(int(Inches(2)), int(h - Inches(1.0)),
                                        int(w - Inches(4)), int(Inches(0.5)))
        tf3 = tb3.text_frame
        p3  = tf3.paragraphs[0]
        p3.alignment = PP_ALIGN.CENTER
        run3 = p3.add_run()
        run3.text = f"YukpoPro  •  {datetime.now().strftime('%Y')}"
        run3.font.size = Pt(10)
        run3.font.color.rgb = _rgb(T["accent"])

    # ── Slide SOMMAIRE ────────────────────────────────────────────────────────

    def _slide_sommaire(self, slide, slide_data: dict, w, h):
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN
        T = self._theme

        self._slide_header(slide, slide_data["titre"], w, h, 2, 10)
        points = slide_data.get("points", [])

        top = Inches(1.4)
        item_h = Inches(0.55)

        for i, point in enumerate(points[:8]):
            y = top + i * item_h
            # Numéro
            num_rect = _rect(slide, int(Inches(0.4)), int(y), int(Inches(0.4)), int(Inches(0.42)), T["accent"])
            tf_num = num_rect.text_frame
            p_num  = tf_num.paragraphs[0]
            p_num.alignment = PP_ALIGN.CENTER
            run_num = p_num.add_run()
            run_num.text = str(i + 1)
            run_num.font.size  = Pt(13)
            run_num.font.bold  = True
            run_num.font.color.rgb = _rgb(T["blanc"])

            # Texte
            tb = slide.shapes.add_textbox(int(Inches(0.95)), int(y + Inches(0.05)),
                                           int(w - Inches(1.2)), int(Inches(0.42)))
            tf = tb.text_frame
            p  = tf.paragraphs[0]
            run = p.add_run()
            run.text = point
            run.font.size  = Pt(14)
            run.font.color.rgb = _rgb(T["texte"])

            # Ligne séparatrice légère
            _rect(slide, int(Inches(0.4)), int(y + Inches(0.43)), int(w - Inches(0.8)),
                  Inches(0.02), T["gris_texte"])

    # ── Slide KPI ─────────────────────────────────────────────────────────────

    def _slide_kpi(self, slide, slide_data: dict, w, h):
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN
        T = self._theme

        kpis     = slide_data.get("kpis", [])[:4]
        points   = slide_data.get("points", [])
        msg      = slide_data.get("message_cle", "")

        if not kpis:
            self._slide_bullets(slide, slide_data, w, h)
            return

        nb = len(kpis)
        marge  = Inches(0.35)
        top    = Inches(1.35)
        gap    = Inches(0.22)
        box_w  = (w - 2 * marge - (nb - 1) * gap) / nb
        box_h  = Inches(2.4)

        kpi_couleurs = [
            T["primaire"], T["accent"] if T["accent"] != (0xD4, 0xAF, 0x37) else T["secondaire"],
            T["success"], T["danger"],
        ]
        # Pour theme corporate: garder les 4 couleurs distinctes
        if T["nom"] == "Corporate":
            kpi_couleurs = [
                (0x0A, 0x2A, 0x4A), (0x1C, 0x4E, 0x80),
                (0x00, 0x8E, 0x5B), (0xB7, 0x7D, 0x00),
            ]

        for i, kpi in enumerate(kpis):
            left = int(marge + i * (box_w + gap))
            rect = _rect(slide, left, int(top), int(box_w), int(box_h), kpi_couleurs[i % 4])

            # Ombre simulée (rectangle légèrement décalé)
            shadow = _rect(slide, left + 4, int(top) + 4, int(box_w), int(box_h),
                           T["gris_texte"])
            shadow.fill.solid()
            shadow.fill.fore_color.rgb = _rgb(T["gris_texte"])
            shadow.line.fill.background()
            # Remettre le rect principal au-dessus via re-ajout (ordre d'insertion)
            rect2 = _rect(slide, left, int(top), int(box_w), int(box_h), kpi_couleurs[i % 4])
            rect2.line.fill.background()

            # Valeur
            tf = rect2.text_frame
            tf.word_wrap = True

            p_val = tf.paragraphs[0]
            p_val.alignment = PP_ALIGN.CENTER
            run_val = p_val.add_run()
            run_val.text = kpi.get("valeur", "—")
            run_val.font.size  = Pt(26)
            run_val.font.bold  = True
            run_val.font.color.rgb = _rgb(T["blanc"])

            # Label
            p_label = tf.add_paragraph()
            p_label.alignment = PP_ALIGN.CENTER
            p_label.space_before = Pt(4)
            run_label = p_label.add_run()
            run_label.text = kpi.get("label", "")
            run_label.font.size  = Pt(10)
            run_label.font.color.rgb = _rgb(T["blanc"])

            # Tendance
            tendance = kpi.get("tendance", "")
            sym = {"hausse": "↑ Hausse", "baisse": "↓ Baisse", "stable": "→ Stable"}.get(tendance, "")
            if sym:
                p_t = tf.add_paragraph()
                p_t.alignment = PP_ALIGN.CENTER
                p_t.space_before = Pt(6)
                run_t = p_t.add_run()
                run_t.text = sym
                run_t.font.size = Pt(11)
                run_t.font.bold = True
                t_col = T["success"] if tendance == "hausse" else (T["danger"] if tendance == "baisse" else T["blanc"])
                run_t.font.color.rgb = _rgb(T["blanc"])  # sur fond coloré, garder blanc

        # Message clé sous les KPIs
        if msg or points:
            bottom_text = msg or (points[0] if points else "")
            y_bottom = int(top + box_h + Inches(0.25))
            h_bottom = int(h - y_bottom - Inches(0.5))
            if h_bottom > 0:
                tb = slide.shapes.add_textbox(int(marge), y_bottom, int(w - 2 * marge), h_bottom)
                tf = tb.text_frame
                tf.word_wrap = True
                p = tf.paragraphs[0]
                from pptx.enum.text import PP_ALIGN
                p.alignment = PP_ALIGN.CENTER
                run = p.add_run()
                run.text = bottom_text
                run.font.size  = Pt(13)
                run.font.italic = True
                run.font.color.rgb = _rgb(T["gris_texte"])

    # ── Slide BULLETS ─────────────────────────────────────────────────────────

    def _slide_bullets(self, slide, slide_data: dict, w, h):
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN
        T = self._theme

        points    = slide_data.get("points", [])
        msg       = slide_data.get("message_cle", "")
        bullet    = T["bullet_char"]

        top    = Inches(1.35)
        left   = Inches(0.45)
        width  = w - Inches(0.9)

        for i, point in enumerate(points[:6]):
            # Alternance de fond subtile
            if i % 2 == 0:
                _rect(slide, int(left - Inches(0.1)), int(top + i * Inches(0.78)),
                      int(width + Inches(0.2)), int(Inches(0.76)), T["blanc"])

            # Puce colorée
            puce = _rect(slide, int(left), int(top + i * Inches(0.78) + Inches(0.18)),
                         int(Inches(0.28)), int(Inches(0.28)), T["accent"])
            tf_puce = puce.text_frame
            p_puce  = tf_puce.paragraphs[0]
            p_puce.alignment = PP_ALIGN.CENTER
            run_puce = p_puce.add_run()
            run_puce.text = bullet
            run_puce.font.size = Pt(10)
            run_puce.font.color.rgb = _rgb(T["blanc"])

            # Texte
            tb = slide.shapes.add_textbox(
                int(left + Inches(0.38)), int(top + i * Inches(0.78) + Inches(0.1)),
                int(width - Inches(0.38)), int(Inches(0.64))
            )
            tf = tb.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            run = p.add_run()
            run.text = point
            run.font.size  = Pt(14)
            run.font.color.rgb = _rgb(T["texte"])

        # Message clé en bas
        if msg and len(points) < 5:
            y_msg = int(top + len(points) * Inches(0.78) + Inches(0.2))
            _rect(slide, int(left), y_msg, int(width), int(Inches(0.5)), T["accent2"] if "accent2" in T else T["gris_clair"])
            tb_msg = slide.shapes.add_textbox(int(left + Inches(0.2)), y_msg + 4,
                                               int(width - Inches(0.4)), int(Inches(0.46)))
            tf_msg = tb_msg.text_frame
            p_msg  = tf_msg.paragraphs[0]
            run_msg = p_msg.add_run()
            run_msg.text = f"💡 {msg}"
            run_msg.font.size  = Pt(12)
            run_msg.font.italic = True
            run_msg.font.color.rgb = _rgb(T["primaire"])

    # ── Slide TWO_COLUMNS ─────────────────────────────────────────────────────

    def _slide_two_columns(self, slide, slide_data: dict, w, h):
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN
        T = self._theme

        points = slide_data.get("points", [])
        msg    = slide_data.get("message_cle", "")

        # Tenter de lire gauche/droite si structure de dict
        gauche, droite = [], []
        if points and isinstance(points[0], dict):
            gauche = points[0].get("gauche", [])
            droite = points[0].get("droite", [])
        elif points:
            mid = len(points) // 2
            gauche = points[:mid] if mid > 0 else points
            droite = points[mid:] if mid > 0 else []

        col_w  = int((w - Inches(1.3)) / 2)
        top    = Inches(1.35)
        col_h  = int(h - Inches(2.0))

        # Colonne gauche
        _rect(slide, int(Inches(0.3)), int(top), col_w, col_h, T["blanc"])
        # Header gauche
        _rect(slide, int(Inches(0.3)), int(top), col_w, int(Inches(0.45)), T["primaire"])
        tb_hg = slide.shapes.add_textbox(int(Inches(0.5)), int(top + Inches(0.05)),
                                          col_w - int(Inches(0.2)), int(Inches(0.38)))
        tf_hg = tb_hg.text_frame
        p_hg  = tf_hg.paragraphs[0]
        run_hg = p_hg.add_run()
        run_hg.text = "Points clés"
        run_hg.font.size  = Pt(12)
        run_hg.font.bold  = True
        run_hg.font.color.rgb = _rgb(T["blanc"])

        for i, point in enumerate(gauche[:5]):
            tb = slide.shapes.add_textbox(
                int(Inches(0.45)), int(top + Inches(0.55) + i * Inches(0.72)),
                col_w - int(Inches(0.2)), int(Inches(0.70))
            )
            tf = tb.text_frame
            tf.word_wrap = True
            p  = tf.paragraphs[0]
            run = p.add_run()
            run.text = f"{T['bullet_char']}  {point}"
            run.font.size  = Pt(13)
            run.font.color.rgb = _rgb(T["texte"])

        # Séparateur central
        sep_x = int(Inches(0.3) + col_w + Inches(0.05))
        _rect(slide, sep_x, int(top), int(Inches(0.06)), col_h, T["accent"])

        # Colonne droite
        right_x = sep_x + int(Inches(0.12))
        _rect(slide, right_x, int(top), col_w, col_h, T["blanc"])
        _rect(slide, right_x, int(top), col_w, int(Inches(0.45)), T["secondaire"])
        tb_hd = slide.shapes.add_textbox(right_x + int(Inches(0.1)), int(top + Inches(0.05)),
                                          col_w - int(Inches(0.2)), int(Inches(0.38)))
        tf_hd = tb_hd.text_frame
        p_hd  = tf_hd.paragraphs[0]
        run_hd = p_hd.add_run()
        run_hd.text = "Compléments"
        run_hd.font.size  = Pt(12)
        run_hd.font.bold  = True
        run_hd.font.color.rgb = _rgb(T["blanc"])

        for i, point in enumerate(droite[:5]):
            tb = slide.shapes.add_textbox(
                right_x + int(Inches(0.1)), int(top + Inches(0.55) + i * Inches(0.72)),
                col_w - int(Inches(0.2)), int(Inches(0.70))
            )
            tf = tb.text_frame
            tf.word_wrap = True
            p  = tf.paragraphs[0]
            run = p.add_run()
            run.text = f"{T['bullet_char']}  {point}"
            run.font.size  = Pt(13)
            run.font.color.rgb = _rgb(T["texte"])

    # ── Slide ACTION ─────────────────────────────────────────────────────────

    def _slide_action(self, slide, slide_data: dict, w, h):
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN
        T = self._theme

        points = slide_data.get("points", [])
        msg    = slide_data.get("message_cle", "")
        top    = Inches(1.35)
        left   = Inches(0.35)
        width  = w - Inches(0.7)

        for i, point in enumerate(points[:5]):
            y = int(top + i * Inches(0.92))
            row_clr = T["primaire"] if i == 0 else (T["secondaire"] if i == 1 else T["gris_clair"])
            txt_clr = T["blanc"] if i <= 1 else T["texte"]

            _rect(slide, int(left), y, int(width), int(Inches(0.82)), row_clr)

            # Numéro
            _rect(slide, int(left), y, int(Inches(0.5)), int(Inches(0.82)),
                  T["accent"] if i <= 1 else T["accent"])
            tb_n = slide.shapes.add_textbox(int(left), y, int(Inches(0.5)), int(Inches(0.82)))
            tf_n = tb_n.text_frame
            p_n  = tf_n.paragraphs[0]
            p_n.alignment = PP_ALIGN.CENTER
            run_n = p_n.add_run()
            run_n.text = str(i + 1)
            run_n.font.size  = Pt(16)
            run_n.font.bold  = True
            run_n.font.color.rgb = _rgb(T["blanc"])

            # Texte
            tb = slide.shapes.add_textbox(
                int(left + Inches(0.6)), y + int(Inches(0.15)),
                int(width - Inches(0.65)), int(Inches(0.62))
            )
            tf = tb.text_frame
            tf.word_wrap = True
            p  = tf.paragraphs[0]
            run = p.add_run()
            run.text = point
            run.font.size  = Pt(13)
            run.font.color.rgb = _rgb(txt_clr)

        # Message CTA en bas
        if msg:
            y_cta = int(top + len(points) * Inches(0.92) + Inches(0.15))
            h_cta = int(h - y_cta - Inches(0.55))
            if h_cta > int(Inches(0.35)):
                _rect(slide, int(left), y_cta, int(width), h_cta, T["accent2"] if "accent2" in T else T["gris_clair"])
                tb_cta = slide.shapes.add_textbox(int(left + Inches(0.2)), y_cta + 4,
                                                   int(width - Inches(0.4)), h_cta - 4)
                tf_cta = tb_cta.text_frame
                tf_cta.word_wrap = True
                p_cta  = tf_cta.paragraphs[0]
                p_cta.alignment = PP_ALIGN.LEFT
                run_cta = p_cta.add_run()
                run_cta.text = f"⚡ {msg}"
                run_cta.font.size  = Pt(12)
                run_cta.font.bold  = True
                run_cta.font.italic = True
                run_cta.font.color.rgb = _rgb(T["primaire"])

    # ── Footer ────────────────────────────────────────────────────────────────

    def _slide_footer(self, slide, w, h, num: int, total: int):
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN
        T = self._theme

        _rect(slide, 0, int(h - Inches(0.32)), w, Inches(0.32), T["primaire"])

        tb = slide.shapes.add_textbox(
            int(Inches(0.3)), int(h - Inches(0.30)),
            int(w - Inches(0.6)), int(Inches(0.28))
        )
        tf = tb.text_frame
        p  = tf.paragraphs[0]
        p.alignment = PP_ALIGN.RIGHT
        run = p.add_run()
        run.text = f"YukpoPro  •  {self._theme['nom']}  •  {datetime.now().strftime('%m/%Y')}"
        run.font.size  = Pt(8)
        run.font.color.rgb = _rgb(T["accent"])

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _nom_fichier(sujet: str, type_pres: str, mode: str) -> str:
        import re
        slug = re.sub(r"[^\w\s-]", "", sujet.lower())
        slug = re.sub(r"[\s_-]+", "_", slug)[:40]
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{type_pres}_{mode}_{slug}_{ts}"

    @staticmethod
    def _slides_vers_markdown(sujet: str, slides: list[dict]) -> str:
        lignes = [f"# {sujet}\n", f"*{datetime.now().strftime('%d/%m/%Y %H:%M')}*\n"]
        for i, slide in enumerate(slides):
            lignes.append(f"\n## Slide {i+1} : {slide['titre']}\n")
            if slide.get("message_cle"):
                lignes.append(f"> {slide['message_cle']}\n")
            for pt in slide.get("points", []):
                if isinstance(pt, dict):
                    for x in pt.get("gauche", []) + pt.get("droite", []):
                        lignes.append(f"- {x}")
                else:
                    lignes.append(f"- {pt}")
            for kpi in slide.get("kpis", []):
                tend = {"hausse": " ↑", "baisse": " ↓", "stable": " →"}.get(kpi.get("tendance", ""), "")
                lignes.append(f"- **{kpi.get('label', '')}** : {kpi.get('valeur', '')}{tend}")
        return "\n".join(lignes)
