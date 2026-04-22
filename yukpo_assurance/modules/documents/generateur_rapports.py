"""
Générateur de Rapports & Présentations Avancées — YukpoAssurance

Fonctionnalités :
  - Graphiques Python haute qualité (matplotlib/seaborn) intégrés dans le PPT
  - Cartes géographiques (Afrique subsaharienne) via folium → image PNG
  - Rapports d'activité hebdomadaires et mensuels automatisés
  - Présentations contextuelles selon le rôle et les données de l'utilisateur
  - Thèmes professionnels, mise en page 16:9

Types de rapports supportés :
  - rapport_activite_hebdo   : résumé hebdomadaire (production, sinistres, KPIs)
  - rapport_activite_mensuel : bilan mensuel complet
  - presentation_ca          : présentation Conseil d'Administration
  - presentation_commerciale : revue pipeline / performance commerciale
  - rapport_rh               : tableau de bord RH (effectifs, paie, absences)
  - rapport_financier        : bilans, ratios CIMA, prévisions
"""
from __future__ import annotations

import base64
import io
import logging
import math
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("yukpo.generateur_rapports")


# ─── Palette de couleurs thèmes ──────────────────────────────────────────────

THEMES = {
    "corporate_blue": {
        "primary": "#003366",
        "accent": "#0066CC",
        "light": "#E8F0FB",
        "text": "#1A1A2E",
        "success": "#27AE60",
        "warning": "#F39C12",
        "danger": "#E74C3C",
        "bg_slide": "#FFFFFF",
    },
    "dark_pro": {
        "primary": "#1A1A2E",
        "accent": "#00C8FF",
        "light": "#2D2D44",
        "text": "#E8E8F0",
        "success": "#2ECC71",
        "warning": "#F1C40F",
        "danger": "#E74C3C",
        "bg_slide": "#16213E",
    },
    "green_finance": {
        "primary": "#1B7735",
        "accent": "#27AE60",
        "light": "#E8F8EE",
        "text": "#142F1D",
        "success": "#2ECC71",
        "warning": "#F39C12",
        "danger": "#E74C3C",
        "bg_slide": "#FFFFFF",
    },
}
DEFAULT_THEME = "corporate_blue"


def _hex_rgb(h: str) -> Tuple[int, int, int]:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


# ─── Génération de graphiques matplotlib ─────────────────────────────────────

def _fig_to_bytes(fig) -> bytes:
    """Rendu PNG en mémoire — synchrone (appelé via asyncio.to_thread en contexte async)."""
    import matplotlib
    matplotlib.use("Agg")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    buf.seek(0)
    return buf.read()


async def _fig_to_bytes_async(fig) -> bytes:
    """Version async de _fig_to_bytes — évite de bloquer l'event loop."""
    import asyncio
    return await asyncio.to_thread(_fig_to_bytes, fig)


def _fig_to_b64(fig) -> str:
    return base64.b64encode(_fig_to_bytes(fig)).decode()


def chart_barres(
    labels: List[str],
    valeurs: List[float],
    titre: str,
    xlabel: str = "",
    ylabel: str = "",
    theme: str = DEFAULT_THEME,
    horizontal: bool = False,
    couleurs: Optional[List[str]] = None,
) -> bytes:
    """Graphique à barres verticales ou horizontales. Retourne PNG bytes."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker

    T = THEMES.get(theme, THEMES[DEFAULT_THEME])
    fig, ax = plt.subplots(figsize=(10, 5), facecolor="#FFFFFF")
    ax.set_facecolor(T["light"])

    if not couleurs:
        n = len(valeurs)
        import matplotlib.cm as cm
        cmap = cm.get_cmap("Blues")
        couleurs = [matplotlib.colors.to_hex(cmap(0.4 + 0.5 * i / max(1, n - 1))) for i in range(n)]

    bars = (ax.barh(labels, valeurs, color=couleurs, edgecolor="white", height=0.6)
            if horizontal else
            ax.bar(labels, valeurs, color=couleurs, edgecolor="white", width=0.6))

    ax.bar_label(bars, fmt="%.0f", fontsize=9, padding=3, color=T["text"])
    ax.set_title(titre, fontsize=14, fontweight="bold", color=T["primary"], pad=14)
    if xlabel: ax.set_xlabel(xlabel, fontsize=10, color=T["text"])
    if ylabel: ax.set_ylabel(ylabel, fontsize=10, color=T["text"])

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if not horizontal:
        plt.xticks(rotation=30, ha="right", fontsize=9, color=T["text"])
    plt.yticks(fontsize=9, color=T["text"])
    fig.tight_layout()
    data = _fig_to_bytes(fig)
    plt.close(fig)
    return data


def chart_lignes(
    x: List[Any],
    series: Dict[str, List[float]],
    titre: str,
    xlabel: str = "",
    ylabel: str = "",
    theme: str = DEFAULT_THEME,
) -> bytes:
    """Graphique multi-courbes. series = {'Série A': [v1,v2...], ...}."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    T = THEMES.get(theme, THEMES[DEFAULT_THEME])
    palette = [T["primary"], T["accent"], T["success"], T["warning"], T["danger"]]
    fig, ax = plt.subplots(figsize=(11, 5), facecolor="#FFFFFF")
    ax.set_facecolor(T["light"])

    for i, (nom, vals) in enumerate(series.items()):
        color = palette[i % len(palette)]
        ax.plot(x, vals, marker="o", markersize=5, linewidth=2.5, color=color, label=nom)
        ax.fill_between(range(len(x)), vals, alpha=0.07, color=color)

    ax.set_title(titre, fontsize=14, fontweight="bold", color=T["primary"], pad=14)
    if xlabel: ax.set_xlabel(xlabel, fontsize=10, color=T["text"])
    if ylabel: ax.set_ylabel(ylabel, fontsize=10, color=T["text"])
    ax.set_xticks(range(len(x)))
    ax.set_xticklabels([str(v) for v in x], rotation=30, ha="right", fontsize=9, color=T["text"])
    ax.legend(fontsize=9, framealpha=0.6)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    data = _fig_to_bytes(fig)
    plt.close(fig)
    return data


def chart_secteurs(
    labels: List[str],
    valeurs: List[float],
    titre: str,
    theme: str = DEFAULT_THEME,
) -> bytes:
    """Camembert / diagramme circulaire."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    T = THEMES.get(theme, THEMES[DEFAULT_THEME])
    fig, ax = plt.subplots(figsize=(7, 6), facecolor="#FFFFFF")
    palette = plt.cm.get_cmap("tab10").colors

    wedges, texts, autotexts = ax.pie(
        valeurs, labels=labels, autopct="%1.1f%%",
        colors=palette[:len(labels)], startangle=140,
        wedgeprops={"edgecolor": "white", "linewidth": 2},
        textprops={"fontsize": 10, "color": T["text"]},
    )
    for at in autotexts:
        at.set_fontsize(9)
        at.set_fontweight("bold")
    ax.set_title(titre, fontsize=14, fontweight="bold", color=T["primary"], pad=14)
    fig.tight_layout()
    data = _fig_to_bytes(fig)
    plt.close(fig)
    return data


def chart_kpi_gauge(valeur: float, max_val: float, titre: str, unite: str = "", theme: str = DEFAULT_THEME) -> bytes:
    """Jauge semi-circulaire pour un KPI."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np

    T = THEMES.get(theme, THEMES[DEFAULT_THEME])
    fig, ax = plt.subplots(figsize=(5, 3.5), facecolor="#FFFFFF")
    ax.set_aspect("equal")
    ax.axis("off")

    pct = min(1.0, max(0.0, valeur / max_val))
    theta_range = np.linspace(math.pi, 0, 200)
    bg_x = np.cos(theta_range)
    bg_y = np.sin(theta_range)
    ax.plot(bg_x, bg_y, color="#E0E0E0", linewidth=20, solid_capstyle="round")

    theta_fill = np.linspace(math.pi, math.pi - pct * math.pi, 200)
    fx = np.cos(theta_fill)
    fy = np.sin(theta_fill)
    color = T["success"] if pct >= 0.75 else T["warning"] if pct >= 0.4 else T["danger"]
    ax.plot(fx, fy, color=color, linewidth=20, solid_capstyle="round")

    label = f"{valeur:,.0f}{unite}"
    ax.text(0, -0.15, label, ha="center", va="center", fontsize=22, fontweight="bold", color=T["primary"])
    ax.text(0, -0.45, titre, ha="center", va="center", fontsize=11, color=T["text"])
    ax.text(0, -0.65, f"/ {max_val:,.0f}{unite}", ha="center", va="center", fontsize=9, color="#999999")
    ax.set_xlim(-1.3, 1.3)
    ax.set_ylim(-0.9, 1.1)
    fig.tight_layout()
    data = _fig_to_bytes(fig)
    plt.close(fig)
    return data


def carte_afrique_subsaharienne(
    donnees_pays: Dict[str, float],
    titre: str,
    unite: str = "",
    theme: str = DEFAULT_THEME,
) -> Optional[bytes]:
    """
    Carte choroplèthe Afrique subsaharienne.
    donnees_pays = {'CM': 1.2e9, 'CI': 850e6, 'SN': 320e6, ...}
    Retourne PNG bytes ou None si geopandas indisponible.
    """
    try:
        import geopandas as gpd
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import Normalize
        import matplotlib.cm as cm

        # Téléchargement naturalearthdata si disponible, sinon on utilise la carte intégrée
        world = gpd.read_file(gpd.datasets.get_path("naturalearth_lowres"))
        afrique = world[world.continent.isin(["Africa"])]

        afrique = afrique.copy()
        afrique["valeur"] = afrique["iso_a3"].apply(
            lambda x: donnees_pays.get(x, donnees_pays.get(x[:2], None))
        )

        T = THEMES.get(theme, THEMES[DEFAULT_THEME])
        fig, ax = plt.subplots(figsize=(8, 9), facecolor="#FFFFFF")
        afrique.plot(
            column="valeur", cmap="Blues", linewidth=0.5, edgecolor="#AAAAAA",
            missing_kwds={"color": "#F0F0F0"}, legend=True,
            legend_kwds={"label": unite, "shrink": 0.7},
            ax=ax,
        )
        afrique[afrique["valeur"].notna()].apply(
            lambda row: ax.annotate(
                row["iso_a3"], xy=row.geometry.centroid.coords[0],
                fontsize=7, ha="center", color=T["primary"],
            ), axis=1,
        )
        ax.set_title(titre, fontsize=14, fontweight="bold", color=T["primary"], pad=12)
        ax.axis("off")
        fig.tight_layout()
        data = _fig_to_bytes(fig)
        plt.close(fig)
        return data
    except ImportError:
        logger.info("[Carte] geopandas non disponible — carte non générée")
        return None
    except Exception as e:
        logger.warning(f"[Carte] Erreur génération carte: {e}")
        return None


# ─── Intégration d'un graphique dans un slide PPTX ───────────────────────────

def _ajouter_image_slide(slide, img_bytes: bytes, left: float, top: float, width: float, height: float = 0):
    """Insère une image (bytes PNG) dans un slide PPTX aux coordonnées Inches données."""
    from pptx.util import Inches
    buf = io.BytesIO(img_bytes)
    if height:
        slide.shapes.add_picture(buf, Inches(left), Inches(top), Inches(width), Inches(height))
    else:
        slide.shapes.add_picture(buf, Inches(left), Inches(top), Inches(width))


def _rgb(h: str):
    from pptx.dml.color import RGBColor
    r, g, b = _hex_rgb(h)
    return RGBColor(r, g, b)


# ─── Constructeur de présentation PPTX ───────────────────────────────────────

class PresentationBuilder:
    """
    Construit une présentation PPTX haute qualité avec graphiques intégrés.
    """
    def __init__(self, theme: str = DEFAULT_THEME):
        from pptx import Presentation
        from pptx.util import Inches, Pt
        self.prs = Presentation()
        self.prs.slide_width = Inches(13.33)
        self.prs.slide_height = Inches(7.5)
        self.theme = THEMES.get(theme, THEMES[DEFAULT_THEME])
        self.T = self.theme

    def _blank_layout(self):
        return self.prs.slide_layouts[6]  # blank

    def _add_background(self, slide, color: str):
        from pptx.util import Inches, Pt, Emu
        from pptx.dml.color import RGBColor
        from pptx.enum.shapes import MSO_SHAPE_TYPE
        w = self.prs.slide_width
        h = self.prs.slide_height
        shape = slide.shapes.add_shape(1, 0, 0, w, h)  # 1 = MSO_SHAPE.RECTANGLE
        shape.fill.solid()
        shape.fill.fore_color.rgb = _rgb(color)
        shape.line.fill.background()
        shape.zorder = 0

    def _add_text(self, slide, text: str, left: float, top: float, width: float, height: float,
                  font_size: int = 12, bold: bool = False, color: str = "#1A1A2E",
                  align: str = "left", italic: bool = False):
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN
        txBox = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
        tf = txBox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = {"center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}.get(align, PP_ALIGN.LEFT)
        run = p.add_run()
        run.text = text
        run.font.size = Pt(font_size)
        run.font.bold = bold
        run.font.italic = italic
        run.font.color.rgb = _rgb(color)
        return txBox

    def _add_rectangle(self, slide, left: float, top: float, width: float, height: float,
                       fill_color: str, line_color: Optional[str] = None):
        from pptx.util import Inches
        shape = slide.shapes.add_shape(1, Inches(left), Inches(top), Inches(width), Inches(height))
        shape.fill.solid()
        shape.fill.fore_color.rgb = _rgb(fill_color)
        if line_color:
            shape.line.color.rgb = _rgb(line_color)
        else:
            shape.line.fill.background()
        return shape

    def ajouter_slide_couverture(self, titre: str, sous_titre: str, date_str: str = "", auteur: str = ""):
        slide = self.prs.slides.add_slide(self._blank_layout())
        T = self.T

        # Fond
        self._add_background(slide, T["primary"])

        # Bande décorative accent
        self._add_rectangle(slide, 0, 5.5, 13.33, 0.3, T["accent"])

        # Titre principal
        self._add_text(slide, titre, 0.5, 1.8, 12.3, 2.0,
                       font_size=34, bold=True, color="#FFFFFF", align="center")

        # Sous-titre
        if sous_titre:
            self._add_text(slide, sous_titre, 0.5, 3.6, 12.3, 0.8,
                           font_size=18, color="#BDD7EE", align="center", italic=True)

        # Ligne décorative fine
        self._add_rectangle(slide, 4.0, 4.6, 5.33, 0.04, T["accent"])

        # Date et auteur
        if date_str:
            self._add_text(slide, date_str, 0.5, 5.0, 6.0, 0.5,
                           font_size=12, color="#BDD7EE", align="center")
        if auteur:
            self._add_text(slide, auteur, 6.83, 5.0, 6.0, 0.5,
                           font_size=12, color="#BDD7EE", align="center")

    def ajouter_slide_titre_section(self, titre: str, description: str = ""):
        slide = self.prs.slides.add_slide(self._blank_layout())
        T = self.T
        self._add_background(slide, T["light"])
        self._add_rectangle(slide, 0, 0, 0.15, 7.5, T["accent"])
        self._add_text(slide, titre, 0.6, 2.5, 12.0, 1.2,
                       font_size=28, bold=True, color=T["primary"], align="left")
        if description:
            self._add_text(slide, description, 0.6, 3.9, 12.0, 0.7,
                           font_size=14, color=T["text"], align="left", italic=True)

    def ajouter_slide_kpis(self, titre: str, kpis: List[Dict]):
        """kpis = [{"label": "Primes émises", "valeur": "2,1 Mds FCFA", "variation": "+12%", "icon": "📈"}]"""
        slide = self.prs.slides.add_slide(self._blank_layout())
        T = self.T
        self._add_background(slide, "#FFFFFF")
        self._add_rectangle(slide, 0, 0, 13.33, 0.6, T["primary"])
        self._add_text(slide, titre, 0.2, 0.05, 12.9, 0.5,
                       font_size=18, bold=True, color="#FFFFFF")

        n = min(len(kpis), 5)
        box_w = 12.5 / n
        for i, kpi in enumerate(kpis[:n]):
            x = 0.4 + i * (box_w + 0.1)
            self._add_rectangle(slide, x, 1.0, box_w - 0.1, 2.5, T["light"], T["accent"])
            icon = kpi.get("icon", "")
            label = kpi.get("label", "")
            valeur = kpi.get("valeur", "")
            variation = kpi.get("variation", "")
            var_color = T["success"] if variation.startswith("+") else T["danger"] if variation.startswith("-") else T["text"]

            if icon:
                self._add_text(slide, icon, x + 0.1, 1.1, box_w - 0.3, 0.5, font_size=22, align="center")
            self._add_text(slide, label, x + 0.1, 1.7, box_w - 0.3, 0.4,
                           font_size=10, color="#666666", align="center")
            self._add_text(slide, valeur, x + 0.1, 2.1, box_w - 0.3, 0.7,
                           font_size=20, bold=True, color=T["primary"], align="center")
            if variation:
                self._add_text(slide, variation, x + 0.1, 2.85, box_w - 0.3, 0.4,
                               font_size=13, bold=True, color=var_color, align="center")

    def ajouter_slide_graphique(self, titre: str, img_bytes: bytes,
                                description: str = "", texte_gauche: str = ""):
        slide = self.prs.slides.add_slide(self._blank_layout())
        T = self.T
        self._add_background(slide, "#FFFFFF")
        self._add_rectangle(slide, 0, 0, 13.33, 0.6, T["primary"])
        self._add_text(slide, titre, 0.2, 0.05, 12.9, 0.5, font_size=18, bold=True, color="#FFFFFF")

        if texte_gauche:
            # Layout : texte à gauche, graphique à droite
            self._add_text(slide, texte_gauche, 0.3, 0.75, 3.8, 6.0,
                           font_size=11, color=T["text"], align="left")
            _ajouter_image_slide(slide, img_bytes, left=4.3, top=0.75, width=8.8, height=5.8)
        else:
            _ajouter_image_slide(slide, img_bytes, left=0.5, top=0.75, width=12.3, height=5.8)

        if description:
            self._add_text(slide, f"💡 {description}", 0.3, 6.7, 12.7, 0.5,
                           font_size=9, color="#666666", italic=True)

    def ajouter_slide_deux_graphiques(self, titre: str, img1: bytes, titre1: str,
                                      img2: bytes, titre2: str):
        slide = self.prs.slides.add_slide(self._blank_layout())
        T = self.T
        self._add_background(slide, "#FFFFFF")
        self._add_rectangle(slide, 0, 0, 13.33, 0.6, T["primary"])
        self._add_text(slide, titre, 0.2, 0.05, 12.9, 0.5, font_size=18, bold=True, color="#FFFFFF")
        self._add_text(slide, titre1, 0.3, 0.7, 6.0, 0.4, font_size=11, bold=True, color=T["primary"])
        _ajouter_image_slide(slide, img1, left=0.3, top=1.1, width=6.1, height=4.5)
        self._add_text(slide, titre2, 6.9, 0.7, 6.0, 0.4, font_size=11, bold=True, color=T["primary"])
        _ajouter_image_slide(slide, img2, left=6.9, top=1.1, width=6.1, height=4.5)

    def ajouter_slide_tableau(self, titre: str, headers: List[str], rows: List[List[Any]],
                              note: str = ""):
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN

        slide = self.prs.slides.add_slide(self._blank_layout())
        T = self.T
        self._add_background(slide, "#FFFFFF")
        self._add_rectangle(slide, 0, 0, 13.33, 0.6, T["primary"])
        self._add_text(slide, titre, 0.2, 0.05, 12.9, 0.5, font_size=18, bold=True, color="#FFFFFF")

        max_rows = min(len(rows), 12)
        n_cols = len(headers)
        table = slide.shapes.add_table(
            max_rows + 1, n_cols,
            Inches(0.3), Inches(0.75),
            Inches(12.73), Inches(min(5.8, 0.45 * (max_rows + 1)))
        ).table

        # En-têtes
        for ci, h in enumerate(headers):
            cell = table.cell(0, ci)
            cell.text = str(h)
            cell.fill.solid()
            cell.fill.fore_color.rgb = _rgb(T["primary"])
            p = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER
            r = p.runs[0] if p.runs else p.add_run()
            r.font.bold = True
            r.font.size = Pt(10)
            r.font.color.rgb = _rgb("#FFFFFF")

        for ri, row in enumerate(rows[:max_rows]):
            alt = ri % 2 == 1
            for ci, val in enumerate(row[:n_cols]):
                cell = table.cell(ri + 1, ci)
                cell.text = str(val)
                if alt:
                    cell.fill.solid()
                    cell.fill.fore_color.rgb = _rgb(T["light"])
                p = cell.text_frame.paragraphs[0]
                p.alignment = PP_ALIGN.CENTER
                r = p.runs[0] if p.runs else p.add_run()
                r.font.size = Pt(9)
                r.font.color.rgb = _rgb(T["text"])

        if note:
            self._add_text(slide, f"Note : {note}", 0.3, 6.8, 12.7, 0.4,
                           font_size=8, color="#888888", italic=True)

    def ajouter_slide_texte(self, titre: str, bullets: List[str], icone: str = "▸",
                            sous_titre: str = ""):
        slide = self.prs.slides.add_slide(self._blank_layout())
        T = self.T
        self._add_background(slide, "#FFFFFF")
        self._add_rectangle(slide, 0, 0, 13.33, 0.6, T["primary"])
        self._add_text(slide, titre, 0.2, 0.05, 12.9, 0.5, font_size=18, bold=True, color="#FFFFFF")

        if sous_titre:
            self._add_text(slide, sous_titre, 0.4, 0.7, 12.5, 0.4,
                           font_size=12, color=T["accent"], italic=True)
        top = 1.25 if sous_titre else 0.85
        for i, bullet in enumerate(bullets[:10]):
            self._add_text(slide, f"  {icone}  {bullet}",
                           0.4, top + i * 0.58, 12.5, 0.55,
                           font_size=13, color=T["text"])

    def ajouter_slide_conclusion(self, titre: str, messages: List[str],
                                 appel_action: str = ""):
        slide = self.prs.slides.add_slide(self._blank_layout())
        T = self.T
        self._add_background(slide, T["primary"])
        self._add_rectangle(slide, 0, 6.8, 13.33, 0.7, T["accent"])
        self._add_text(slide, titre, 0.5, 0.6, 12.3, 1.0,
                       font_size=28, bold=True, color="#FFFFFF", align="center")
        for i, msg in enumerate(messages[:5]):
            self._add_text(slide, f"✓  {msg}", 2.0, 2.0 + i * 0.7, 9.33, 0.6,
                           font_size=14, color="#BDD7EE")
        if appel_action:
            self._add_text(slide, appel_action, 0.5, 5.8, 12.3, 0.7,
                           font_size=16, bold=True, color=T["accent"], align="center")

    def build(self) -> bytes:
        buf = io.BytesIO()
        self.prs.save(buf)
        return buf.getvalue()


# ─── Rapports d'activité ─────────────────────────────────────────────────────

def generer_rapport_activite(
    periode: str,
    type_rapport: str,
    donnees: Dict[str, Any],
    auteur: str = "",
    compagnie_nom: str = "YukpoAssurance",
    theme: str = DEFAULT_THEME,
) -> bytes:
    """
    Génère un rapport d'activité PPT (hebdomadaire ou mensuel).

    Args:
        periode      : ex "Semaine 15 — 7 au 13 avril 2025" ou "Mars 2025"
        type_rapport : "hebdomadaire" | "mensuel"
        donnees      : dict structuré (voir ci-dessous)
        auteur       : prénom + nom de l'auteur
        compagnie_nom: nom de la compagnie
        theme        : thème visuel

    Structure donnees :
    {
        "kpis": [{"label": "Nouvelles polices", "valeur": "47", "variation": "+8%", "icon": "📋"}],
        "production": {"labels": ["Jan","Fév",...], "series": {"Auto": [1e9,...], "Vie": [500e6,...]}},
        "sinistralite": {"labels": [...], "series": {"Déclarés": [...], "Réglés": [...]}},
        "top_branches": {"labels": [...], "valeurs": [...]},
        "points_forts": ["Point 1", "Point 2"],
        "points_attention": ["Alerte 1"],
        "actions": ["Action 1", "Action 2"],
        "tableau_courtiers": {"headers": ["Courtier","Polices","Primes"], "rows": [...]},
        "repartition_branches": {"labels": [...], "valeurs": [...]},
        "pays_activite": {"CM": 1.5e9, "CI": 800e6},  # pour carte
    }
    """
    builder = PresentationBuilder(theme=theme)
    T = THEMES.get(theme, THEMES[DEFAULT_THEME])
    titre_rapport = f"Rapport d'Activité {'Hebdomadaire' if type_rapport == 'hebdomadaire' else 'Mensuel'}"
    date_gen = datetime.now().strftime("%d/%m/%Y à %H:%M")

    # 1. Couverture
    builder.ajouter_slide_couverture(
        titre=f"{compagnie_nom}\n{titre_rapport}",
        sous_titre=periode,
        date_str=f"Généré le {date_gen}",
        auteur=auteur,
    )

    # 2. KPIs principaux
    if donnees.get("kpis"):
        builder.ajouter_slide_kpis("Indicateurs Clés de Performance", donnees["kpis"])

    # 3. Production (graphique lignes)
    if donnees.get("production"):
        prod = donnees["production"]
        img = chart_lignes(
            x=prod.get("labels", []),
            series=prod.get("series", {}),
            titre=f"Évolution de la Production — {periode}",
            xlabel="Période",
            ylabel="Primes (FCFA)",
            theme=theme,
        )
        builder.ajouter_slide_graphique(
            titre="Production — Primes Émises",
            img_bytes=img,
            description="Évolution des primes par branche d'assurance",
        )

    # 4. Répartition branches (barres) + secteurs côte à côte
    if donnees.get("top_branches") and donnees.get("repartition_branches"):
        tb = donnees["top_branches"]
        rb = donnees["repartition_branches"]
        img1 = chart_barres(
            labels=tb.get("labels", []),
            valeurs=tb.get("valeurs", []),
            titre="Top Branches",
            ylabel="Primes (FCFA)",
            theme=theme,
        )
        img2 = chart_secteurs(
            labels=rb.get("labels", []),
            valeurs=rb.get("valeurs", []),
            titre="Répartition",
            theme=theme,
        )
        builder.ajouter_slide_deux_graphiques(
            "Portefeuille par Branche", img1, "Volume par branche", img2, "Parts de portefeuille"
        )
    elif donnees.get("top_branches"):
        tb = donnees["top_branches"]
        img = chart_barres(tb.get("labels", []), tb.get("valeurs", []),
                           "Production par Branche", ylabel="Primes (FCFA)", theme=theme)
        builder.ajouter_slide_graphique("Production par Branche", img)

    # 5. Sinistralité
    if donnees.get("sinistralite"):
        sin = donnees["sinistralite"]
        img = chart_lignes(
            x=sin.get("labels", []),
            series=sin.get("series", {}),
            titre=f"Sinistralité — {periode}",
            xlabel="Période",
            ylabel="Nombre / Montant",
            theme=theme,
        )
        builder.ajouter_slide_graphique(
            titre="Suivi Sinistres",
            img_bytes=img,
            description="Évolution des sinistres déclarés vs réglés",
        )

    # 6. Carte géographique si données pays
    if donnees.get("pays_activite"):
        carte_bytes = carte_afrique_subsaharienne(
            donnees_pays=donnees["pays_activite"],
            titre=f"Répartition Géographique — {periode}",
            unite="FCFA",
            theme=theme,
        )
        if carte_bytes:
            builder.ajouter_slide_graphique(
                titre="Couverture Géographique",
                img_bytes=carte_bytes,
                description="Primes émises par pays d'opération",
            )

    # 7. Tableau des meilleurs courtiers
    if donnees.get("tableau_courtiers"):
        tc = donnees["tableau_courtiers"]
        builder.ajouter_slide_tableau(
            titre="Performance Courtiers",
            headers=tc.get("headers", []),
            rows=tc.get("rows", []),
        )

    # 8. Points forts / Points d'attention
    if donnees.get("points_forts"):
        builder.ajouter_slide_texte(
            titre="✅ Points Forts de la Période",
            bullets=donnees["points_forts"],
            icone="✅",
        )
    if donnees.get("points_attention"):
        builder.ajouter_slide_texte(
            titre="⚠️ Points d'Attention",
            bullets=donnees["points_attention"],
            icone="⚠️",
            sous_titre="Éléments nécessitant un suivi immédiat",
        )

    # 9. Plan d'actions
    if donnees.get("actions"):
        builder.ajouter_slide_texte(
            titre="Plan d'Actions",
            bullets=donnees["actions"],
            icone="→",
            sous_titre="Actions prioritaires à mener",
        )

    # 10. Conclusion
    builder.ajouter_slide_conclusion(
        titre=f"Merci — {titre_rapport}",
        messages=[
            "Document généré automatiquement par YukpoAssurance IA",
            f"Période : {periode}",
            f"Présenté par : {auteur}" if auteur else "Pour toute question, contactez la Direction",
        ],
        appel_action="Prochaine revue : " + (
            "semaine prochaine" if type_rapport == "hebdomadaire" else "fin du mois prochain"
        ),
    )

    return builder.build()


def generer_presentation_personnalisee(
    titre: str,
    slides_config: List[Dict[str, Any]],
    auteur: str = "",
    compagnie_nom: str = "YukpoAssurance",
    theme: str = DEFAULT_THEME,
) -> bytes:
    """
    Génère une présentation PPT depuis une config structurée (produite par l'IA).

    Chaque slide_config peut contenir :
    {
        "type": "couverture"|"section"|"kpis"|"graphique_barres"|"graphique_lignes"|
                "graphique_secteurs"|"tableau"|"texte"|"conclusion",
        "titre": str,
        "donnees": {...},   # selon le type
    }
    """
    builder = PresentationBuilder(theme=theme)
    date_gen = datetime.now().strftime("%d/%m/%Y")

    for slide_cfg in slides_config:
        typ = slide_cfg.get("type", "texte")
        titre_slide = slide_cfg.get("titre", "")
        d = slide_cfg.get("donnees", {})

        if typ == "couverture":
            builder.ajouter_slide_couverture(
                titre=d.get("titre", titre_slide),
                sous_titre=d.get("sous_titre", ""),
                date_str=d.get("date", date_gen),
                auteur=d.get("auteur", auteur),
            )

        elif typ == "section":
            builder.ajouter_slide_titre_section(titre_slide, d.get("description", ""))

        elif typ == "kpis":
            builder.ajouter_slide_kpis(titre_slide, d.get("kpis", []))

        elif typ == "graphique_barres":
            img = chart_barres(
                labels=d.get("labels", []),
                valeurs=d.get("valeurs", []),
                titre=d.get("titre_graphique", titre_slide),
                xlabel=d.get("xlabel", ""),
                ylabel=d.get("ylabel", ""),
                theme=theme,
                horizontal=d.get("horizontal", False),
            )
            builder.ajouter_slide_graphique(titre_slide, img, description=d.get("description", ""),
                                            texte_gauche=d.get("texte_gauche", ""))

        elif typ == "graphique_lignes":
            img = chart_lignes(
                x=d.get("labels", []),
                series=d.get("series", {}),
                titre=d.get("titre_graphique", titre_slide),
                xlabel=d.get("xlabel", ""),
                ylabel=d.get("ylabel", ""),
                theme=theme,
            )
            builder.ajouter_slide_graphique(titre_slide, img, description=d.get("description", ""))

        elif typ == "graphique_secteurs":
            img = chart_secteurs(
                labels=d.get("labels", []),
                valeurs=d.get("valeurs", []),
                titre=d.get("titre_graphique", titre_slide),
                theme=theme,
            )
            builder.ajouter_slide_graphique(titre_slide, img, description=d.get("description", ""))

        elif typ == "carte":
            carte_bytes = carte_afrique_subsaharienne(
                donnees_pays=d.get("pays", {}),
                titre=d.get("titre_graphique", titre_slide),
                unite=d.get("unite", ""),
                theme=theme,
            )
            if carte_bytes:
                builder.ajouter_slide_graphique(titre_slide, carte_bytes,
                                                description=d.get("description", ""))

        elif typ == "tableau":
            builder.ajouter_slide_tableau(
                titre=titre_slide,
                headers=d.get("headers", []),
                rows=d.get("rows", []),
                note=d.get("note", ""),
            )

        elif typ == "texte":
            builder.ajouter_slide_texte(
                titre=titre_slide,
                bullets=d.get("bullets", []),
                icone=d.get("icone", "▸"),
                sous_titre=d.get("sous_titre", ""),
            )

        elif typ == "conclusion":
            builder.ajouter_slide_conclusion(
                titre=titre_slide,
                messages=d.get("messages", []),
                appel_action=d.get("appel_action", ""),
            )

    return builder.build()


async def generer_presentation_depuis_ia(
    demande: str,
    contexte: Dict[str, Any],
    auteur: str = "",
    compagnie_nom: str = "YukpoAssurance",
    theme: str = DEFAULT_THEME,
    claude_api_key: str = "",
    openai_api_key: str = "",
) -> bytes:
    """
    L'IA génère la structure complète d'une présentation depuis une demande en langage naturel,
    puis `generer_presentation_personnalisee` construit le PPT.
    """
    date_str = datetime.now().strftime("%B %Y")
    contexte_str = "\n".join(f"- {k}: {v}" for k, v in (contexte or {}).items())

    system_prompt = """Tu es un expert en communication corporate et présentation PowerPoint.
Tu génères des structures de présentations professionnelles en JSON strict.
Chaque slide doit avoir : {"type": ..., "titre": ..., "donnees": {...}}
Types disponibles : couverture, section, kpis, graphique_barres, graphique_lignes,
graphique_secteurs, tableau, texte, conclusion.
Pour graphique_barres: donnees = {"labels": [...], "valeurs": [...], "ylabel": "...", "description": "..."}
Pour graphique_lignes: donnees = {"labels": [...], "series": {"Nom": [...]}, "ylabel": "...", "description": "..."}
Pour kpis: donnees = {"kpis": [{"label": "...", "valeur": "...", "variation": "...", "icon": "..."}]}
Pour tableau: donnees = {"headers": [...], "rows": [[...], ...], "note": "..."}
Pour texte: donnees = {"bullets": [...], "icone": "▸", "sous_titre": "..."}
Utilise des données réalistes et des chiffres plausibles pour l'Afrique subsaharienne.
Génère minimum 8 slides maximum 15. Retourne UNIQUEMENT le JSON: {"slides": [...]}"""

    user_msg = f"""Génère une présentation PowerPoint pour :
{demande}

Contexte compagnie :
{contexte_str}

Date : {date_str}
Auteur : {auteur}
Compagnie : {compagnie_nom}"""

    slides_config = []

    # Appel IA
    try:
        if claude_api_key:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=claude_api_key)
            msg = await client.messages.create(
                model="claude-opus-4-6",
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_msg}],
                temperature=0.4,
            )
            import json, re
            text = msg.content[0].text.strip()
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                slides_config = json.loads(match.group())["slides"]
        elif openai_api_key:
            import openai, json, re
            client = openai.AsyncOpenAI(api_key=openai_api_key)
            resp = await client.chat.completions.create(
                model="gpt-4o",
                max_tokens=4096,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.4,
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.choices[0].message.content)
            slides_config = data.get("slides", [])
    except Exception as e:
        logger.error(f"[Présentation/IA] Erreur: {e}")

    if not slides_config:
        # Fallback structuré par défaut
        slides_config = [
            {"type": "couverture", "titre": demande[:60], "donnees": {"titre": demande[:60], "auteur": auteur}},
            {"type": "texte", "titre": "Objectifs", "donnees": {"bullets": ["Présentation générée automatiquement", "Données à enrichir selon contexte"], "sous_titre": ""}},
            {"type": "conclusion", "titre": "Merci", "donnees": {"messages": ["Document généré par YukpoAssurance IA"]}},
        ]

    return generer_presentation_personnalisee(
        titre=demande[:60],
        slides_config=slides_config,
        auteur=auteur,
        compagnie_nom=compagnie_nom,
        theme=theme,
    )
