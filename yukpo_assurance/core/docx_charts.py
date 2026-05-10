"""
Générateur de graphiques PNG depuis tableaux markdown.

Source unique de vérité partagée entre :
- Pro : `report_writer_pro.py` (rapports d'audit, financiers, RH, etc.)
- Sec : `redacteur.py` (notes admin, plans d'affaires, mémoires, etc.)

Choix bar/line auto. Palette pro. Annotations valeurs. Format milliers.
"""
from __future__ import annotations

import logging
import re as _re
from typing import Optional

logger = logging.getLogger("yukpo_assurance.docx_charts")


def generer_png_depuis_tableau(
    headers: list[str],
    rows: list[str],
    colonnes_num: set,
) -> Optional[bytes]:
    """
    Génère un PNG (bar chart ou line chart) depuis un tableau markdown.
    Retourne None si non graphable (≤ 2 lignes, valeurs non extractibles, > 20 lignes).

    Args:
      headers : noms de colonnes (premier `|` séparé)
      rows    : lignes brutes markdown ("| ... | ... |")
      colonnes_num : indices de colonnes contenant des chiffres
    """
    try:
        import io as _io

        def _to_float(v: str) -> Optional[float]:
            v = (v or "").strip().strip("*").replace(" ", " ")
            v = _re.sub(r"[^\d,.\-]", "", v.replace(" ", "").replace(",", "."))
            try:
                return float(v) if v else None
            except ValueError:
                return None

        labels: list[str] = []
        series: dict[int, list[float]] = {ci: [] for ci in sorted(colonnes_num)}
        for row_line in rows:
            cells = [c.strip() for c in row_line.split("|") if c.strip()]
            if not cells:
                continue
            # exclure lignes total/moyenne du graphique
            if _re.match(r"^\s*\*?\*?\s*(total|moyenne|sous-total|grand total)",
                         cells[0], _re.IGNORECASE):
                continue
            label = cells[0].strip("*")[:18]
            labels.append(label)
            for ci in sorted(colonnes_num):
                val = _to_float(cells[ci]) if ci < len(cells) else None
                series[ci].append(val if val is not None else 0.0)

        if not labels or not any(any(v != 0 for v in s) for s in series.values()):
            return None
        if len(labels) > 20:
            return None

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.rcParams["font.family"] = "DejaVu Sans"
        palette = ["#0047AB", "#16A34A", "#F59E0B", "#DC2626", "#7C3AED",
                   "#0EA5E9", "#10B981", "#F97316"]

        fig, ax = plt.subplots(figsize=(9, 4.5), dpi=110)
        fig.patch.set_facecolor("#FFFFFF")
        ax.set_facecolor("#FFFFFF")

        n_series = len(series)
        nombres_x = [i for i in range(len(labels))]
        if n_series == 1 and len(labels) >= 5:
            ci = list(series.keys())[0]
            ax.plot(nombres_x, series[ci], marker="o", color=palette[0],
                    linewidth=2.2, markersize=5, markerfacecolor="white",
                    markeredgewidth=1.5,
                    label=headers[ci] if ci < len(headers) else "")
            ax.fill_between(nombres_x, series[ci], alpha=0.10, color=palette[0])
        else:
            largeur_totale = 0.78
            w = largeur_totale / max(n_series, 1)
            for i, (ci, vals) in enumerate(series.items()):
                offset = (i - (n_series - 1) / 2) * w
                bars = ax.bar(
                    [x + offset for x in nombres_x], vals, width=w * 0.92,
                    color=palette[i % len(palette)],
                    label=headers[ci] if ci < len(headers) else f"Col {ci}",
                    alpha=0.92, zorder=3,
                )
                if len(vals) <= 12:
                    for bar in bars:
                        h = bar.get_height()
                        if h != 0:
                            ax.annotate(
                                f"{h:,.0f}" if abs(h) >= 100 else f"{h:.1f}",
                                xy=(bar.get_x() + bar.get_width() / 2, h),
                                xytext=(0, 3), textcoords="offset points",
                                ha="center", fontsize=7, color="#374151",
                            )

        ax.set_xticks(nombres_x)
        ax.set_xticklabels(
            labels, rotation=30 if len(labels) > 5 else 0,
            ha="right" if len(labels) > 5 else "center", fontsize=8,
        )
        ax.tick_params(colors="#6B7280", labelsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#E5E7EB")
        ax.spines["bottom"].set_color("#E5E7EB")
        ax.grid(axis="y", linestyle="--", alpha=0.4, color="#E5E7EB")
        if n_series > 1 or (n_series == 1 and headers):
            ax.legend(loc="best", fontsize=8, frameon=False)
        try:
            ax.yaxis.set_major_formatter(
                plt.FuncFormatter(lambda x, _: f"{x:,.0f}".replace(",", " "))
            )
        except Exception:
            pass
        fig.tight_layout(pad=1.5)
        buf = _io.BytesIO()
        fig.savefig(buf, format="png", dpi=110, bbox_inches="tight",
                    facecolor="#FFFFFF")
        plt.close(fig)
        return buf.getvalue()
    except Exception as e:
        logger.debug(f"[docx_charts] Graphique échoué : {e}")
        return None


def detecter_colonnes_numeriques(headers: list[str], data_rows: list[str]) -> set:
    """Détecte les indices de colonnes dont la majorité des valeurs sont numériques.
    Utile pour décider quelle colonne plotter en chart.
    `data_rows` = lignes du tableau hors header (lignes brutes markdown)."""
    def _est_numerique(v: str) -> bool:
        return bool(_re.match(
            r'^[\s\-+]*[\d\s.,]+[\s%]*(FCFA|XAF|XOF|€|\$|F)?\s*$',
            (v or "").strip(),
        ))

    colonnes_num: set = set()
    for ci in range(len(headers)):
        vals = []
        for r_line in data_rows:
            cells_r = [c.strip() for c in r_line.split('|') if c.strip()]
            if ci < len(cells_r):
                vals.append(cells_r[ci].strip('*'))
        if vals and sum(1 for v in vals if _est_numerique(v)) >= max(1, len(vals) // 2):
            colonnes_num.add(ci)
    return colonnes_num


def parser_tableau_markdown(lignes_md: list[str], depart: int) -> tuple[list[str], list[str], int]:
    """
    Parse un tableau markdown à partir de la ligne `depart`.
    Retourne (headers, data_rows, idx_apres_tableau).
    Si pas de tableau valide → ([], [], depart+1).

    Filtre la ligne separator (---).
    """
    tbl_lignes = []
    i = depart
    while i < len(lignes_md) and '|' in lignes_md[i]:
        tbl_lignes.append(lignes_md[i])
        i += 1
    if not tbl_lignes:
        return [], [], depart + 1
    rows = [
        l for l in tbl_lignes
        if not _re.match(r'^\|[\s\-:|\s]+\|$', l.strip())
    ]
    if len(rows) < 2:
        return [], [], i
    headers = [c.strip() for c in rows[0].split('|') if c.strip()]
    data_rows = rows[1:]
    return headers, data_rows, i
