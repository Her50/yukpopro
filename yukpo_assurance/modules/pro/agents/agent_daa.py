"""
AgentDAA — Agent IA d'analyse de données niveau Data Analyst Senior.

Capacités :
  - Analyse exploratoire complète (statistiques, distributions, corrélations, outliers)
  - Détection automatique du meilleur type de graphique selon les données
  - Lecture multi-feuilles Excel (toutes les feuilles en un appel)
  - Croisement multi-fichiers Excel (jointures, consolidations, analyses comparatives)
  - Tableaux croisés dynamiques multi-dimensions
  - Analyse de tendances, régression linéaire, moyennes mobiles, prévisions
  - Interprétation narrative LLM niveau senior DA (insights métier, anomalies, recommandations)
  - Génération de rapport DOCX complet avec graphiques intégrés
  - Génération de graphiques haute qualité (matplotlib) avec sélection auto du type
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from core.agent_orchestrateur import TypeAgent
from modules.pro.agent_pro_base import AgentProBase

logger = logging.getLogger("yukpo_assurance.pro.agent_daa")

_OUTPUT_DIR = Path("data/generated/pro_data")
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# Imports conditionnels
# ══════════════════════════════════════════════════════════════════════════════

def _import_pandas():
    try:
        import pandas as pd
        return pd
    except ImportError as e:
        raise ImportError("pandas non installé. Exécuter : pip install pandas openpyxl") from e


def _import_matplotlib():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        return plt
    except ImportError as e:
        raise ImportError("matplotlib non installé. Exécuter : pip install matplotlib") from e


# ══════════════════════════════════════════════════════════════════════════════
# Chargement et lecture des données
# ══════════════════════════════════════════════════════════════════════════════

def _charger_donnees(source: dict | list | str) -> "pd.DataFrame":
    """Charge un dataset depuis dict, list ou JSON string."""
    pd = _import_pandas()
    if isinstance(source, str):
        try:
            source = json.loads(source)
        except json.JSONDecodeError as e:
            raise ValueError(f"Données JSON invalides : {e}") from e
    if isinstance(source, list):
        return pd.DataFrame(source)
    if isinstance(source, dict):
        return pd.DataFrame(source)
    raise TypeError(f"Format non supporté : {type(source)}")


def _lire_excel_multi_feuilles(contenu: bytes, limite_lignes: int = 10000) -> dict[str, "pd.DataFrame"]:
    """
    Lit toutes les feuilles d'un fichier Excel.
    Retourne un dict {nom_feuille: DataFrame}.
    """
    pd = _import_pandas()
    import io
    xl = pd.ExcelFile(io.BytesIO(contenu))
    feuilles = {}
    for nom in xl.sheet_names:
        try:
            df = pd.read_excel(xl, sheet_name=nom)
            if len(df) > limite_lignes:
                df = df.head(limite_lignes)
            # Nettoyage basique
            df.columns = [str(c).strip() for c in df.columns]
            df = df.dropna(how="all").dropna(axis=1, how="all")
            if not df.empty:
                feuilles[nom] = df
        except Exception as e:
            logger.warning(f"[AgentDAA] Feuille '{nom}' illisible : {e}")
    return feuilles


def _consolider_feuilles(feuilles: dict[str, "pd.DataFrame"]) -> "pd.DataFrame":
    """
    Consolide plusieurs feuilles de même structure en un seul DataFrame.
    Ajoute une colonne 'Feuille' pour tracer l'origine.
    """
    pd = _import_pandas()
    morceaux = []
    for nom, df in feuilles.items():
        df_c = df.copy()
        df_c["_feuille"] = nom
        morceaux.append(df_c)
    if not morceaux:
        return pd.DataFrame()
    try:
        return pd.concat(morceaux, ignore_index=True)
    except Exception:
        return morceaux[0]


def _croiser_deux_dataframes(
    df1: "pd.DataFrame", nom1: str,
    df2: "pd.DataFrame", nom2: str,
    cle_commune: str | None = None,
) -> "pd.DataFrame":
    """
    Croise deux DataFrames. Tente une jointure sur clé commune détectée,
    sinon retourne la concaténation.
    """
    pd = _import_pandas()

    # Détection automatique de la clé commune
    if not cle_commune:
        cols1, cols2 = set(df1.columns), set(df2.columns)
        communes = cols1 & cols2
        # Préférer les colonnes d'identifiant ou de date
        candidats = [c for c in communes if any(
            mot in c.lower() for mot in ["id", "code", "ref", "date", "mois", "periode", "annee"]
        )]
        cle_commune = candidats[0] if candidats else (list(communes)[0] if communes else None)

    if cle_commune and cle_commune in df1.columns and cle_commune in df2.columns:
        suffix1 = f"_{nom1[:8]}" if nom1 else "_g"
        suffix2 = f"_{nom2[:8]}" if nom2 else "_d"
        try:
            return pd.merge(df1, df2, on=cle_commune, how="outer", suffixes=(suffix1, suffix2))
        except Exception:
            pass

    # Fallback : concaténation avec tag
    df1c, df2c = df1.copy(), df2.copy()
    df1c["_source"], df2c["_source"] = nom1, nom2
    try:
        return pd.concat([df1c, df2c], ignore_index=True)
    except Exception:
        return df1


# ══════════════════════════════════════════════════════════════════════════════
# Extraction de données depuis PDF (rapports SI, tableaux, exports)
# ══════════════════════════════════════════════════════════════════════════════

def _extraire_pdf_tableaux_et_contexte(contenu: bytes) -> tuple[list, str]:
    """
    Extrait les tableaux et le texte d'un PDF (rapport, export SI, etc.).

    Stratégie :
      1. pdfplumber  → extraction précise page par page (privilégié)
      2. tabula-py   → fallback si pdfplumber ne trouve pas de tableaux
      3. PyPDF2/pdfminer → texte brut si aucun tableau détecté (PDF texte)

    Retourne : (liste_de_dataframes, texte_contexte_global)
    """
    pd = _import_pandas()
    import io, re

    dataframes: list = []
    texte_pages: list[str] = []

    # ── Tentative 1 : pdfplumber ──────────────────────────────────────────────
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(contenu)) as pdf:
            for num_page, page in enumerate(pdf.pages, 1):
                # Texte de la page
                txt = page.extract_text() or ""
                if txt.strip():
                    texte_pages.append(f"--- Page {num_page} ---\n{txt.strip()}")

                # Tableaux de la page
                for tbl in page.extract_tables():
                    if not tbl or len(tbl) < 2:
                        continue
                    try:
                        headers = [str(h).strip() if h else f"Col{i}" for i, h in enumerate(tbl[0])]
                        # Dédupliquer les entêtes
                        seen: dict[str, int] = {}
                        clean_headers = []
                        for h in headers:
                            if h in seen:
                                seen[h] += 1
                                clean_headers.append(f"{h}_{seen[h]}")
                            else:
                                seen[h] = 0
                                clean_headers.append(h)
                        rows = tbl[1:]
                        df = pd.DataFrame(rows, columns=clean_headers)
                        # Nettoyage : supprimer lignes/colonnes vides
                        df = df.replace("", pd.NA).dropna(how="all").dropna(axis=1, how="all")
                        df = df.replace(pd.NA, "")
                        # Conversion numérique auto
                        for col in df.columns:
                            cleaned = df[col].astype(str).str.replace(r"[\s\u00a0]", "", regex=True)
                            cleaned = cleaned.str.replace(",", ".").str.replace(r"[^\d.\-]", "", regex=True)
                            try:
                                df[col] = pd.to_numeric(cleaned)
                            except (ValueError, TypeError):
                                pass  # garder comme string
                        if not df.empty and len(df) >= 1:
                            df.attrs["source"] = f"PDF page {num_page}"
                            dataframes.append(df)
                    except Exception as e:
                        logger.debug(f"[AgentDAA] PDF table page {num_page} : {e}")

        if dataframes or texte_pages:
            logger.info(f"[AgentDAA] pdfplumber : {len(dataframes)} tableaux, {len(texte_pages)} pages de texte")
            return dataframes, "\n\n".join(texte_pages)
    except ImportError:
        logger.debug("[AgentDAA] pdfplumber non disponible — fallback tabula")
    except Exception as e:
        logger.warning(f"[AgentDAA] pdfplumber error : {e}")

    # ── Tentative 2 : tabula-py ───────────────────────────────────────────────
    try:
        import tabula
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(contenu)
            tmp_path = tmp.name
        try:
            dfs = tabula.read_pdf(tmp_path, pages="all", multiple_tables=True, silent=True)
            for df in (dfs or []):
                if not df.empty:
                    df.attrs["source"] = "PDF tabula"
                    dataframes.append(df)
            logger.info(f"[AgentDAA] tabula : {len(dataframes)} tableaux extraits")
        finally:
            os.unlink(tmp_path)
        if dataframes:
            return dataframes, "\n\n".join(texte_pages)
    except ImportError:
        logger.debug("[AgentDAA] tabula-py non disponible")
    except Exception as e:
        logger.warning(f"[AgentDAA] tabula error : {e}")

    # ── Tentative 3 : extraction texte brut (PyPDF2 / pypdf) ─────────────────
    try:
        try:
            from pypdf import PdfReader
        except ImportError:
            from PyPDF2 import PdfReader  # type: ignore
        reader = PdfReader(io.BytesIO(contenu))
        for num_page, page in enumerate(reader.pages, 1):
            txt = page.extract_text() or ""
            if txt.strip():
                texte_pages.append(f"--- Page {num_page} ---\n{txt.strip()}")
        # Tenter de parser les tableaux depuis le texte brut
        texte_complet = "\n\n".join(texte_pages)
        df_texte = _pdf_texte_vers_dataframe(texte_complet)
        if df_texte is not None and not df_texte.empty:
            dataframes.append(df_texte)
        logger.info(f"[AgentDAA] PyPDF2 : texte extrait de {len(reader.pages)} pages")
        return dataframes, texte_complet
    except ImportError:
        logger.warning("[AgentDAA] Aucune lib PDF disponible (installer pdfplumber)")
    except Exception as e:
        logger.warning(f"[AgentDAA] PDF texte brut error : {e}")

    return [], "Extraction PDF impossible — aucune bibliothèque PDF disponible."


def _pdf_texte_vers_dataframe(texte: str) -> "pd.DataFrame | None":
    """
    Tente de reconstruire un DataFrame depuis du texte PDF mal structuré.
    Détecte les lignes séparées par des espaces multiples (tableau ASCII).
    """
    pd = _import_pandas()
    import re

    lignes = [l for l in texte.split("\n") if l.strip()]
    # Heuristique : si beaucoup de pipes ou d'espaces multiples → tableau
    tableau_lignes = [l for l in lignes if re.search(r"\s{3,}|\|", l)]
    if len(tableau_lignes) < 3:
        return None
    try:
        # Séparer par espaces multiples (≥3)
        rows = []
        for l in tableau_lignes:
            cols = re.split(r"\s{3,}|\|", l.strip())
            cols = [c.strip() for c in cols if c.strip()]
            if cols:
                rows.append(cols)
        if len(rows) < 2:
            return None
        # Uniformiser la largeur
        n_cols = max(len(r) for r in rows)
        rows = [r + [""] * (n_cols - len(r)) for r in rows]
        headers = [f"Col{i+1}" for i in range(n_cols)]
        df = pd.DataFrame(rows, columns=headers)
        return df
    except Exception:
        return None


def _resumer_pdf_pour_llm(dataframes: list, texte: str, max_chars: int = 8000) -> str:
    """
    Produit un résumé compact du contenu PDF pour le LLM (contexte limité).
    """
    pd = _import_pandas()
    parties = []

    if texte:
        parties.append(f"=== TEXTE DU DOCUMENT ===\n{texte[:4000]}")
        if len(texte) > 4000:
            parties.append(f"[... {len(texte) - 4000} caractères supplémentaires tronqués ...]")

    for i, df in enumerate(dataframes[:5]):
        src = df.attrs.get("source", f"Tableau {i+1}")
        parties.append(f"\n=== {src.upper()} ===")
        parties.append(f"Dimensions : {df.shape[0]} lignes × {df.shape[1]} colonnes")
        parties.append(f"Colonnes : {', '.join(df.columns.tolist())}")
        parties.append(f"Aperçu (5 premières lignes) :\n{df.head(5).to_string(index=False)}")
        # Stats rapides numériques
        num_cols = df.select_dtypes(include="number").columns.tolist()
        if num_cols:
            desc = df[num_cols].describe().round(2)
            parties.append(f"Statistiques numériques :\n{desc.to_string()}")

    resume = "\n".join(parties)
    return resume[:max_chars]


# ══════════════════════════════════════════════════════════════════════════════
# Analyse statistique
# ══════════════════════════════════════════════════════════════════════════════

def _stats_descriptives(df: "pd.DataFrame") -> dict:
    """Statistiques descriptives complètes par colonne."""
    pd = _import_pandas()
    result = {}
    for col in df.columns:
        serie = df[col]
        missing = int(serie.isna().sum())
        entry: dict[str, Any] = {
            "colonne":       col,
            "type":          str(serie.dtype),
            "count":         len(serie),
            "manquants":     missing,
            "pct_manquants": round(missing / len(serie) * 100, 1) if len(serie) else 0,
        }
        if pd.api.types.is_numeric_dtype(serie):
            s = serie.dropna()
            if len(s) > 0:
                q1, q3 = float(s.quantile(0.25)), float(s.quantile(0.75))
                iqr = q3 - q1
                entry.update({
                    "min":        round(float(s.min()),    4),
                    "max":        round(float(s.max()),    4),
                    "moyenne":    round(float(s.mean()),   4),
                    "mediane":    round(float(s.median()), 4),
                    "ecart_type": round(float(s.std()),    4),
                    "q1":         round(q1, 4),
                    "q3":         round(q3, 4),
                    "nb_outliers": int(((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).sum()),
                    "somme":      round(float(s.sum()),    2),
                })
        elif pd.api.types.is_object_dtype(serie) or hasattr(pd.api.types, 'is_categorical_dtype') and pd.api.types.is_categorical_dtype(serie):
            vc = serie.value_counts()
            entry.update({
                "nb_uniques": int(serie.nunique()),
                "top_valeur": str(vc.index[0]) if len(vc) > 0 else None,
                "top_freq":   int(vc.iloc[0])   if len(vc) > 0 else 0,
                "top_5":      [str(v) for v in vc.index[:5].tolist()],
            })
        elif pd.api.types.is_datetime64_any_dtype(serie):
            s = serie.dropna()
            if len(s) > 0:
                entry.update({
                    "date_min": str(s.min()),
                    "date_max": str(s.max()),
                    "plage_jours": (s.max() - s.min()).days,
                })
        result[col] = entry
    return result


def _calculer_correlations(df: "pd.DataFrame") -> dict:
    """Matrice de corrélation Pearson pour les colonnes numériques (r > 0.5 reportées)."""
    pd = _import_pandas()
    num_df = df.select_dtypes(include="number")
    if num_df.shape[1] < 2:
        return {}
    try:
        corr = num_df.corr()
        fortes = {}
        cols = list(corr.columns)
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                r = round(float(corr.iloc[i, j]), 3)
                if abs(r) >= 0.5:
                    fortes[f"{cols[i]} ↔ {cols[j]}"] = r
        return fortes
    except Exception:
        return {}


# ══════════════════════════════════════════════════════════════════════════════
# Détection automatique du type de graphique
# ══════════════════════════════════════════════════════════════════════════════

def _choisir_type_graphique(
    df: "pd.DataFrame",
    col_x: str | None = None,
    col_y: str | None = None,
    nb_series: int = 1,
) -> str:
    """
    Choisit automatiquement le meilleur type de graphique.

    Règles :
    - Axe X temporel (dates, mois, années) → courbe
    - Axe X catégoriel ≤ 6 valeurs uniques + 1 série → camembert
    - Axe X catégoriel + multi-séries ou > 6 valeurs → barres
    - Deux axes numériques → scatter (courbe ici)
    - Colonne numérique seule → histogramme
    - Séries multiples temporelles → courbe
    """
    pd = _import_pandas()

    if col_x and col_x in df.columns:
        col = df[col_x]
        # Temporel
        if pd.api.types.is_datetime64_any_dtype(col):
            return "courbe"
        if pd.api.types.is_object_dtype(col):
            # Détection heuristique de dates/périodes
            sample = col.dropna().astype(str).head(10)
            date_patterns = ["jan", "fév", "mar", "avr", "mai", "jun", "jul",
                             "aoû", "sep", "oct", "nov", "déc",
                             "q1", "q2", "q3", "q4", "trim",
                             "2019", "2020", "2021", "2022", "2023", "2024", "2025"]
            if any(any(p in s.lower() for p in date_patterns) for s in sample):
                return "courbe"
            # Catégoriel
            nb_uniques = int(col.nunique())
            if nb_uniques <= 6 and nb_series == 1:
                return "camembert"
            return "barres"

        if pd.api.types.is_numeric_dtype(col) and col_y and col_y in df.columns:
            if pd.api.types.is_numeric_dtype(df[col_y]):
                return "courbe"

    if nb_series > 1:
        return "barres"

    # Colonne numérique seule
    num_cols = df.select_dtypes(include="number").columns
    if len(num_cols) == 1:
        return "histogramme"

    return "barres"


# ══════════════════════════════════════════════════════════════════════════════
# Visualisation — graphiques haute qualité
# ══════════════════════════════════════════════════════════════════════════════

# Palette professionnelle africaine (accessible, contrastée)
_PALETTE = [
    "#0047AB",  # Bleu royal
    "#E67E22",  # Orange africain
    "#27AE60",  # Vert
    "#C0392B",  # Rouge
    "#8E44AD",  # Violet
    "#17A589",  # Turquoise
    "#2C3E50",  # Bleu nuit
    "#F39C12",  # Jaune or
]


def _appliquer_style_graphique(fig, ax, titre: str, x_label: str, y_label: str):
    """Style global professionnel pour tous les graphiques."""
    import matplotlib.pyplot as plt
    fig.patch.set_facecolor("#F9FAFB")
    ax.set_facecolor("#FFFFFF")
    if titre:
        ax.set_title(titre, fontsize=14, fontweight="bold", pad=16,
                     color="#1F2937", fontfamily="DejaVu Sans")
    if x_label:
        ax.set_xlabel(x_label, fontsize=11, color="#6B7280")
    if y_label:
        ax.set_ylabel(y_label, fontsize=11, color="#6B7280")
    ax.tick_params(colors="#6B7280", labelsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#E5E7EB")
    ax.spines["bottom"].set_color("#E5E7EB")
    ax.grid(axis="y", linestyle="--", alpha=0.4, color="#E5E7EB")
    fig.tight_layout(pad=2.0)


def _generer_graphique(
    donnees:     dict,
    type_graphe: str,
    titre:       str = "",
    x_label:     str = "",
    y_label:     str = "",
    auto_detect: bool = False,
) -> str:
    """
    Génère un graphique matplotlib de haute qualité.
    donnees : {"labels": [...], "series": [{"nom": str, "valeurs": [...]}]}
    Retourne le chemin du fichier PNG.
    """
    plt = _import_matplotlib()

    labels = donnees.get("labels", [])
    series = donnees.get("series", [])
    if not series:
        return "Aucune donnée à visualiser"

    fig, ax = plt.subplots(figsize=(11, 5.5))

    if type_graphe == "barres":
        n = len(series)
        total_w = 0.72
        w = total_w / max(n, 1)
        offsets = [(i - (n - 1) / 2) * w for i in range(n)]
        for i, s in enumerate(series):
            vals = s["valeurs"]
            x = list(range(len(labels)))
            bars = ax.bar([xi + offsets[i] for xi in x], vals, width=w * 0.9,
                          color=_PALETTE[i % len(_PALETTE)], label=s["nom"],
                          alpha=0.88, zorder=3)
            # Valeurs sur barres
            if len(vals) <= 12:
                for bar in bars:
                    h = bar.get_height()
                    if h != 0:
                        ax.annotate(
                            f"{h:,.0f}" if abs(h) >= 100 else f"{h:.1f}",
                            xy=(bar.get_x() + bar.get_width() / 2, h),
                            xytext=(0, 4), textcoords="offset points",
                            ha="center", fontsize=7.5, color="#374151",
                        )
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=30 if len(labels) > 6 else 0, ha="right")

    elif type_graphe == "courbe":
        for i, s in enumerate(series):
            ax.plot(labels, s["valeurs"], marker="o", label=s["nom"],
                    color=_PALETTE[i % len(_PALETTE)], linewidth=2.2,
                    markersize=5, markerfacecolor="white",
                    markeredgewidth=1.5, markeredgecolor=_PALETTE[i % len(_PALETTE)],
                    zorder=3)
            # Zone sous la courbe (opaque)
            ax.fill_between(range(len(labels)), s["valeurs"],
                            alpha=0.06, color=_PALETTE[i % len(_PALETTE)])
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=30 if len(labels) > 6 else 0, ha="right")

    elif type_graphe == "camembert":
        vals  = series[0]["valeurs"]
        total = sum(v for v in vals if v and v > 0)
        pcts  = [v / total * 100 for v in vals] if total else vals
        wedges, texts, autotexts = ax.pie(
            pcts, labels=labels,
            colors=_PALETTE[:len(labels)],
            autopct="%1.1f%%", startangle=90,
            pctdistance=0.82,
            wedgeprops={"linewidth": 1.5, "edgecolor": "white"},
        )
        for at in autotexts:
            at.set_fontsize(9)
            at.set_color("white")
            at.set_fontweight("bold")
        ax.axis("equal")

    elif type_graphe == "histogramme":
        for i, s in enumerate(series):
            vals = [v for v in s["valeurs"] if v is not None]
            ax.hist(vals, bins=min(20, max(5, len(vals) // 5)),
                    color=_PALETTE[i % len(_PALETTE)], alpha=0.82,
                    label=s["nom"], edgecolor="white", linewidth=0.5, zorder=3)

    elif type_graphe == "barres_horizontales":
        for i, s in enumerate(series):
            y = list(range(len(labels)))
            ax.barh(y, s["valeurs"], color=_PALETTE[i % len(_PALETTE)],
                    alpha=0.88, label=s["nom"], zorder=3)
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels)
        ax.grid(axis="x", linestyle="--", alpha=0.4, color="#E5E7EB")
        ax.grid(axis="y", visible=False)

    else:
        plt.close(fig)
        return f"Type '{type_graphe}' non supporté"

    _appliquer_style_graphique(fig, ax, titre, x_label, y_label)
    if len(series) > 1 or type_graphe not in ("camembert",):
        if len(series) > 1:
            ax.legend(fontsize=9, framealpha=0.8, loc="best")

    nom_fichier = f"graph_{uuid.uuid4().hex[:8]}.png"
    chemin = _OUTPUT_DIR / nom_fichier
    fig.savefig(str(chemin), dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    logger.info(f"[AgentDAA] Graphique généré : {chemin}")
    return str(chemin)


def _auto_generer_graphiques(df: "pd.DataFrame", titre_base: str = "") -> list[str]:
    """
    Génère automatiquement les graphiques les plus pertinents pour un DataFrame.
    Retourne la liste des chemins PNG.
    """
    pd = _import_pandas()
    chemins = []

    num_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = df.select_dtypes(include="object").columns.tolist()

    # Détection colonne temporelle
    col_temps = None
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            col_temps = c
            break
        if pd.api.types.is_object_dtype(df[c]):
            sample = df[c].dropna().astype(str).head(5)
            if any(any(p in s.lower() for p in ["jan", "fév", "q1", "2020", "2021", "2022", "2023", "2024"]) for s in sample):
                col_temps = c
                break

    # 1. Séries temporelles → courbes
    if col_temps and num_cols:
        cols_a_tracer = num_cols[:4]
        try:
            labels = df[col_temps].astype(str).tolist()
            series = [{"nom": c, "valeurs": df[c].fillna(0).tolist()} for c in cols_a_tracer]
            titre = f"{titre_base} — Évolution temporelle" if titre_base else "Évolution temporelle"
            ch = _generer_graphique({"labels": labels, "series": series}, "courbe",
                                    titre=titre, x_label=col_temps, y_label="")
            if ch and "non supporté" not in ch:
                chemins.append(ch)
        except Exception as e:
            logger.warning(f"[AgentDAA] Graphique temporel échoué : {e}")

    # 2. Distribution première variable numérique → histogramme
    if num_cols:
        try:
            col = num_cols[0]
            vals = df[col].dropna().tolist()
            ch = _generer_graphique(
                {"labels": [col], "series": [{"nom": col, "valeurs": vals}]},
                "histogramme", titre=f"Distribution — {col}"
            )
            if ch and "non supporté" not in ch:
                chemins.append(ch)
        except Exception as e:
            logger.warning(f"[AgentDAA] Histogramme échoué : {e}")

    # 3. Catégorie × Montant → barres ou camembert
    if cat_cols and num_cols:
        try:
            cat_col = cat_cols[0]
            num_col = num_cols[0]
            nb_uniq = df[cat_col].nunique()
            if nb_uniq <= 20:
                agg = df.groupby(cat_col)[num_col].sum().sort_values(ascending=False).head(10)
                labels = agg.index.astype(str).tolist()
                vals   = agg.values.tolist()
                type_g = "camembert" if nb_uniq <= 6 else "barres"
                ch = _generer_graphique(
                    {"labels": labels, "series": [{"nom": num_col, "valeurs": vals}]},
                    type_g, titre=f"{num_col} par {cat_col}", y_label=num_col
                )
                if ch and "non supporté" not in ch:
                    chemins.append(ch)
        except Exception as e:
            logger.warning(f"[AgentDAA] Barres catégoriel échoué : {e}")

    # 4. Si multi colonnes numériques → comparatif barres
    if len(num_cols) >= 3 and col_temps is None:
        try:
            summs = {c: df[c].sum() for c in num_cols[:6]}
            labels = list(summs.keys())
            vals   = list(summs.values())
            ch = _generer_graphique(
                {"labels": labels, "series": [{"nom": "Total", "valeurs": vals}]},
                "barres_horizontales",
                titre=f"Comparatif des indicateurs — {titre_base}" if titre_base else "Comparatif indicateurs",
                x_label="Valeur"
            )
            if ch and "non supporté" not in ch:
                chemins.append(ch)
        except Exception as e:
            logger.warning(f"[AgentDAA] Comparatif échoué : {e}")

    return chemins[:4]  # max 4 graphiques auto


# ══════════════════════════════════════════════════════════════════════════════
# Analyse de tendance
# ══════════════════════════════════════════════════════════════════════════════

def _calculer_tendance(serie: list[float]) -> dict:
    n = len(serie)
    if n < 2:
        return {"erreur": "Au moins 2 points nécessaires"}
    x  = list(range(n))
    mx = sum(x) / n
    my = sum(serie) / n
    num   = sum((xi - mx) * (yi - my) for xi, yi in zip(x, serie))
    denom = sum((xi - mx) ** 2 for xi in x)
    pente = num / denom if denom != 0 else 0
    b     = my - pente * mx
    ss_tot = sum((yi - my) ** 2 for yi in serie)
    ss_res = sum((yi - (pente * xi + b)) ** 2 for xi, yi in zip(x, serie))
    r2     = 1 - (ss_res / ss_tot) if ss_tot != 0 else 1.0
    previsions = [round(pente * (n + i) + b, 2) for i in range(3)]
    direction = "stable" if abs(pente) < abs(my) * 0.01 else ("haussière" if pente > 0 else "baissière")
    return {
        "pente": round(pente, 4), "ordonnee": round(b, 4),
        "r2": round(r2, 4), "direction": direction, "previsions": previsions,
    }


def _moyennes_mobiles(serie: list[float], fenetre: int = 3) -> list[float]:
    result = []
    for i in range(len(serie)):
        debut = max(0, i - fenetre + 1)
        result.append(round(sum(serie[debut:i + 1]) / (i - debut + 1), 4))
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Tableaux croisés dynamiques
# ══════════════════════════════════════════════════════════════════════════════

def _pivoter_tableau(
    df: "pd.DataFrame",
    index: list[str],
    colonnes: list[str] | None,
    valeurs: list[str],
    aggregation: str = "sum",
) -> "pd.DataFrame":
    pd = _import_pandas()
    agg_map = {"sum": "sum", "mean": "mean", "count": "count", "max": "max", "min": "min", "std": "std"}
    aggfunc = agg_map.get(aggregation, "sum")
    pivot = pd.pivot_table(
        df, index=index, columns=colonnes or None,
        values=valeurs, aggfunc=aggfunc, fill_value=0,
    )
    return pivot.reset_index()


# ══════════════════════════════════════════════════════════════════════════════
# Rendus texte / Markdown
# ══════════════════════════════════════════════════════════════════════════════

def _rendu_stats(stats: dict, titre: str = "") -> str:
    lignes = [f"## {titre}\n" if titre else "## ANALYSE DESCRIPTIVE\n"]
    for col, s in stats.items():
        lignes.append(f"### {col}  *(type : {s['type']})*")
        lignes.append(f"- Observations : **{s['count']:,}**  |  Manquants : **{s['manquants']}** ({s['pct_manquants']}%)")
        if "moyenne" in s:
            lignes += [
                f"- Min : {s['min']:,.4g}  |  Max : {s['max']:,.4g}  |  Somme : **{s.get('somme', '—'):,.2f}**",
                f"- Moyenne : **{s['moyenne']:,.4g}**  |  Médiane : {s['mediane']:,.4g}",
                f"- Écart-type : {s['ecart_type']:,.4g}  |  Q1 : {s['q1']:,.4g}  |  Q3 : {s['q3']:,.4g}",
            ]
            if s.get("nb_outliers", 0) > 0:
                lignes.append(f"- ⚠️  **{s['nb_outliers']} valeur(s) aberrante(s)** (méthode IQR)")
        elif "nb_uniques" in s:
            lignes += [
                f"- Valeurs uniques : **{s['nb_uniques']}**",
                f"- Valeur dominante : **{s['top_valeur']}** ({s['top_freq']} occurrences)",
                f"- Top 5 : {', '.join(s.get('top_5', []))}",
            ]
        elif "date_min" in s:
            lignes += [
                f"- Période : {s['date_min']} → {s['date_max']}",
                f"- Plage : {s.get('plage_jours', '?')} jours",
            ]
        lignes.append("")
    return "\n".join(lignes)


def _rendu_tendance(tendance: dict, nom_serie: str = "Série") -> str:
    if "erreur" in tendance:
        return f"Erreur tendance : {tendance['erreur']}"
    d = tendance
    q = "bonne" if d['r2'] > 0.7 else ("moyenne" if d['r2'] > 0.4 else "faible")
    return "\n".join([
        f"**TENDANCE — {nom_serie}**",
        f"- Direction : **{d['direction']}** (pente : {d['pente']:+.4f}/période)",
        f"- Corrélation R² : {d['r2']:.3f} ({q} corrélation)",
        f"- Prévisions : P+1 = {d['previsions'][0]:,.2f}  |  P+2 = {d['previsions'][1]:,.2f}  |  P+3 = {d['previsions'][2]:,.2f}",
    ])


def _rendu_pivot(pivot_df: "pd.DataFrame", titre: str = "") -> str:
    if pivot_df.empty:
        return "Tableau croisé vide."
    cols   = list(pivot_df.columns)
    header = "| " + " | ".join(str(c) for c in cols) + " |"
    sep    = "| " + " | ".join(":---:" for _ in cols) + " |"
    lignes = [f"**{titre}**\n" if titre else "", header, sep]
    for _, row in pivot_df.iterrows():
        vals = []
        for c in cols:
            v = row[c]
            try:
                if isinstance(v, float) and abs(v) >= 1000:
                    vals.append(f"{v:,.0f}")
                elif isinstance(v, int) and abs(v) >= 1000:
                    vals.append(f"{v:,}")
                else:
                    vals.append(str(v))
            except Exception:
                vals.append(str(v))
        lignes.append("| " + " | ".join(vals) + " |")
    return "\n".join(lignes)


# ══════════════════════════════════════════════════════════════════════════════
# Interprétation LLM niveau senior DA
# ══════════════════════════════════════════════════════════════════════════════

async def _interpreter_donnees_llm(
    df: "pd.DataFrame",
    stats: dict,
    correlations: dict,
    contexte_metier: str = "",
    titre: str = "",
    pays: str = "Afrique francophone",
    feuilles_info: str = "",
) -> str:
    """
    Appelle le LLM pour produire une interprétation narrative de niveau Data Analyst Senior.
    Inclut : insights métier, anomalies, corrélations, recommandations stratégiques.
    """
    from core.ia_client import ModeIA, ia_client

    pd = _import_pandas()
    n_lignes, n_cols = df.shape
    num_cols = df.select_dtypes(include="number").columns.tolist()

    # Résumé compact des stats pour le LLM
    resume_stats = []
    for col, s in stats.items():
        if "moyenne" in s:
            resume_stats.append(
                f"- **{col}** : moy={s['moyenne']:,.2f}, min={s['min']:,.2f}, "
                f"max={s['max']:,.2f}, manquants={s['pct_manquants']}%, "
                f"outliers={s.get('nb_outliers', 0)}, somme={s.get('somme', '?'):,.0f}"
            )
        elif "nb_uniques" in s:
            resume_stats.append(
                f"- **{col}** (catégorie) : {s['nb_uniques']} valeurs distinctes, "
                f"top={s['top_valeur']} ({s['top_freq']} fois)"
            )

    corr_str = ""
    if correlations:
        corr_str = "\n**Corrélations fortes détectées :**\n" + "\n".join(
            f"- {pair} : r={r:.3f} ({'forte positive' if r > 0 else 'forte négative'})"
            for pair, r in sorted(correlations.items(), key=lambda x: abs(x[1]), reverse=True)
        )

    apercu = df.head(5).to_string(index=False) if n_lignes > 0 else ""

    prompt = f"""Tu es un Data Analyst Senior expert en Afrique francophone. Analyse ce dataset et produis une interprétation exhaustive de niveau professionnel.

**DATASET** : {titre or 'Analyse de données'}
**Dimensions** : {n_lignes:,} lignes × {n_cols} colonnes
**Contexte métier** : {contexte_metier or 'Non précisé'}
**Pays/Zone** : {pays}
{feuilles_info}

**STATISTIQUES CLÉS** :
{chr(10).join(resume_stats[:20])}
{corr_str}

**APERÇU (5 premières lignes)** :
{apercu}

**INTERPRÉTATION REQUISE** — structure OBLIGATOIRE :

## 1. Synthèse exécutive (3-5 phrases)
> Message clé : ce que ces données nous disent en premier lieu

## 2. Analyse des indicateurs clés
Pour chaque variable numérique importante : signification, niveau, comparaison sectorielle africaine si pertinente, alerte si anomalie.

## 3. Patterns et tendances détectés
Tendances, saisonnalités, cycles, progressions ou régressions identifiées.

## 4. Anomalies et points d'attention
Valeurs aberrantes et leur signification métier (pas juste "outlier IQR"). Données manquantes et leur impact.

## 5. Corrélations et relations clés
Interprétation métier des corrélations (cause/effet probable, co-évolution).

## 6. Segmentation recommandée
Quelle(s) dimension(s) d'analyse approfondir ? Quels croisements seraient révélateurs ?

## 7. Recommandations stratégiques (3-5 actions)
Actions concrètes, priorisées, adaptées au contexte {pays} et au secteur {contexte_metier or 'professionnel'}.

## 8. Limites de l'analyse
Ce que les données ne permettent PAS de conclure. Données manquantes importantes.

Ton style : expert, factuel, concis. Chiffres précis. Pas de généralités. Contexte africain quand pertinent (FCFA, OHADA, marchés locaux)."""

    try:
        rep = await ia_client.appeler(
            prompt=prompt,
            systeme=(
                "Tu es un Data Analyst Senior avec 15 ans d'expérience en Afrique francophone. "
                "Tes analyses sont factuelles, chiffrées et directement actionnables. "
                "Tu distingues correlation et causalité. Tu contextualises dans le marché africain."
            ),
            mode=ModeIA.REDACTION,
            max_tokens_override=4096,
            utiliser_cache=False,
        )
        return rep.contenu if hasattr(rep, "contenu") else str(rep)
    except Exception as e:
        logger.warning(f"[AgentDAA] Interprétation LLM échouée : {e}")
        return "Interprétation automatique indisponible — analyse statistique ci-dessus."


# ══════════════════════════════════════════════════════════════════════════════
# Génération rapport DOCX complet avec graphiques
# ══════════════════════════════════════════════════════════════════════════════

def _generer_rapport_docx(
    titre: str,
    interpretation: str,
    stats_markdown: str,
    pivot_markdown: str,
    chemins_graphiques: list[str],
    contexte: str = "",
) -> bytes:
    """
    Produit un rapport DOCX structuré avec interprétation LLM + stats + graphiques.
    """
    try:
        import io
        import re
        from docx import Document
        from docx.shared import Pt, Inches, RGBColor, Cm
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml.ns import qn
        from lxml import etree
        from datetime import datetime as _dt

        doc = Document()

        # ── Page setup ────────────────────────────────────────────────────────
        section = doc.sections[0]
        section.page_width  = Inches(8.27)   # A4
        section.page_height = Inches(11.69)
        section.left_margin = section.right_margin = Inches(1.0)
        section.top_margin  = section.bottom_margin = Inches(1.0)

        # ── Styles de base ───────────────────────────────────────────────────
        styles = doc.styles

        def ajouter_paragraphe_style(texte: str, taille: int, bold: bool = False,
                                      couleur: tuple = (30, 30, 30), espacement_avant: int = 0,
                                      espacement_apres: int = 0, italique: bool = False,
                                      alignement=WD_ALIGN_PARAGRAPH.LEFT) -> None:
            p = doc.add_paragraph()
            p.alignment = alignement
            p.paragraph_format.space_before = Pt(espacement_avant)
            p.paragraph_format.space_after  = Pt(espacement_apres)
            run = p.add_run(texte)
            run.font.size   = Pt(taille)
            run.font.bold   = bold
            run.font.italic = italique
            run.font.color.rgb = RGBColor(*couleur)
            return p

        # ── Page de titre ────────────────────────────────────────────────────
        p_titre = doc.add_paragraph()
        p_titre.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_titre.paragraph_format.space_before = Pt(48)
        p_titre.paragraph_format.space_after  = Pt(12)
        run_t = p_titre.add_run(titre.upper())
        run_t.font.size  = Pt(22)
        run_t.font.bold  = True
        run_t.font.color.rgb = RGBColor(0, 71, 171)  # Bleu royal

        if contexte:
            ajouter_paragraphe_style(contexte, 11, italique=True,
                                      couleur=(107, 114, 128),
                                      espacement_apres=6,
                                      alignement=WD_ALIGN_PARAGRAPH.CENTER)

        ajouter_paragraphe_style(
            f"Rapport généré le {_dt.now().strftime('%d %B %Y à %H:%M')} — Yukpo Assurance Pro",
            9, couleur=(150, 150, 150), espacement_apres=24,
            alignement=WD_ALIGN_PARAGRAPH.CENTER
        )
        doc.add_page_break()

        # ── Interprétation LLM ───────────────────────────────────────────────
        doc.add_paragraph()
        lignes_interp = interpretation.split("\n")
        for ligne in lignes_interp:
            ligne = ligne.strip()
            if not ligne:
                doc.add_paragraph()
                continue
            if ligne.startswith("## "):
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(14)
                p.paragraph_format.space_after  = Pt(6)
                run = p.add_run(ligne[3:])
                run.font.size  = Pt(14)
                run.font.bold  = True
                run.font.color.rgb = RGBColor(0, 71, 171)
            elif ligne.startswith("### "):
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(8)
                run = p.add_run(ligne[4:])
                run.font.size = Pt(12)
                run.font.bold = True
                run.font.color.rgb = RGBColor(26, 26, 46)
            elif ligne.startswith("> "):
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Inches(0.4)
                p.paragraph_format.space_before = Pt(4)
                p.paragraph_format.space_after  = Pt(4)
                run = p.add_run(ligne[2:])
                run.font.size   = Pt(11)
                run.font.italic = True
                run.font.color.rgb = RGBColor(30, 86, 160)
            elif ligne.startswith("- ") or ligne.startswith("• "):
                p = doc.add_paragraph(style="List Bullet")
                texte_bullet = ligne[2:]
                # Gras pour les **textes en gras**
                parties = re.split(r"\*\*(.+?)\*\*", texte_bullet)
                for i, partie in enumerate(parties):
                    run = p.add_run(partie)
                    run.font.size = Pt(10.5)
                    run.font.bold = (i % 2 == 1)
                    run.font.color.rgb = RGBColor(30, 30, 30)
            else:
                p = doc.add_paragraph()
                parties = re.split(r"\*\*(.+?)\*\*", ligne)
                for i, partie in enumerate(parties):
                    run = p.add_run(partie)
                    run.font.size = Pt(10.5)
                    run.font.bold = (i % 2 == 1)
                    run.font.color.rgb = RGBColor(30, 30, 30)

        # ── Graphiques ───────────────────────────────────────────────────────
        if chemins_graphiques:
            doc.add_page_break()
            p = doc.add_paragraph()
            run = p.add_run("VISUALISATIONS")
            run.font.size  = Pt(16)
            run.font.bold  = True
            run.font.color.rgb = RGBColor(0, 71, 171)
            p.paragraph_format.space_after = Pt(12)

            for ch in chemins_graphiques:
                if ch and Path(ch).exists():
                    try:
                        doc.add_picture(ch, width=Inches(6.0))
                        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                        doc.add_paragraph()
                    except Exception as eg:
                        logger.warning(f"[AgentDAA] Graphique non inséré dans DOCX : {eg}")

        # ── Annexe statistique ────────────────────────────────────────────────
        if stats_markdown:
            doc.add_page_break()
            p_annexe = doc.add_paragraph()
            run_a = p_annexe.add_run("ANNEXE — STATISTIQUES DESCRIPTIVES COMPLÈTES")
            run_a.font.size = Pt(14)
            run_a.font.bold = True
            run_a.font.color.rgb = RGBColor(0, 71, 171)
            p_annexe.paragraph_format.space_after = Pt(12)

            for ligne in stats_markdown.split("\n"):
                ligne = ligne.strip()
                if not ligne:
                    continue
                if ligne.startswith("## ") or ligne.startswith("### "):
                    p = doc.add_paragraph()
                    run = p.add_run(ligne.lstrip("#").strip())
                    run.font.size = Pt(12)
                    run.font.bold = True
                    run.font.color.rgb = RGBColor(26, 26, 46)
                elif ligne.startswith("- "):
                    p = doc.add_paragraph(style="List Bullet")
                    run = p.add_run(ligne[2:])
                    run.font.size = Pt(9.5)
                    run.font.color.rgb = RGBColor(60, 60, 60)
                else:
                    p = doc.add_paragraph()
                    run = p.add_run(ligne)
                    run.font.size = Pt(9.5)
                    run.font.color.rgb = RGBColor(60, 60, 60)

        # Tableau croisé
        if pivot_markdown:
            doc.add_paragraph()
            p = doc.add_paragraph()
            run = p.add_run("TABLEAU CROISÉ DYNAMIQUE")
            run.font.size = Pt(12)
            run.font.bold = True
            run.font.color.rgb = RGBColor(26, 26, 46)
            for ligne in pivot_markdown.split("\n"):
                if ligne.strip():
                    p2 = doc.add_paragraph()
                    run2 = p2.add_run(ligne)
                    run2.font.size = Pt(9)
                    run2.font.color.rgb = RGBColor(50, 50, 50)

        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()

    except ImportError as e:
        logger.error(f"[AgentDAA] python-docx/lxml non installé : {e}")
        raise
    except Exception as e:
        logger.exception("[AgentDAA] Génération DOCX échouée")
        raise


# ══════════════════════════════════════════════════════════════════════════════
# Prompt analyse fichier entrant
# ══════════════════════════════════════════════════════════════════════════════

def _prompt_analyse_fichier_entrant(params: dict) -> str:
    description  = params.get("description_fichier", "")
    type_fichier = params.get("type_fichier", "autre")
    source       = params.get("source", "")
    types_labels = {
        "ventes": "fichier de données de ventes",
        "rh": "fichier de données RH / paie",
        "comptabilite": "fichier comptable / grand livre",
        "logistique": "fichier de données logistique / stock",
        "crm": "fichier CRM / clients",
        "autre": "fichier de données",
    }
    label = types_labels.get(type_fichier, "fichier de données")
    return f"""Tu es un data analyst expert en données d'entreprises africaines.

Analyse ce {label}{f' provenant de {source}' if source else ''}.

DESCRIPTION / EXTRAIT :
{description}

ANALYSE REQUISE :
1. **Structure identifiée** — colonnes, types de données, format
2. **Qualité des données** — valeurs manquantes, doublons, formats incohérents
3. **Colonnes clés** — identifiants, dates, montants, dimensions d'analyse
4. **Analyses réalisables** — tendances, segmentations, KPIs, croisements
5. **Pré-traitements recommandés** — nettoyage avant analyse
6. **Questions métier** auxquelles ce fichier peut répondre (3-5 exemples concrets)
7. **Type de graphique optimal** pour visualiser les données principales

Format : structuré, orienté valeur métier, accessible à un non-technicien."""


# ══════════════════════════════════════════════════════════════════════════════
# Classe AgentDAA
# ══════════════════════════════════════════════════════════════════════════════

class AgentDAA(AgentProBase):
    """Agent Data Analyst Senior — analyse multi-feuilles, multi-fichiers, graphiques auto."""

    type_agent = TypeAgent.PRO_DAA

    def _system_prompt(self) -> str:
        base = super()._system_prompt()
        return base + """

EXPERTISE DATA ANALYST SENIOR :
Tu es un Data Analyst Senior avec 15 ans d'expérience en Afrique francophone (FCFA, OHADA, marchés régionaux).

COMPÉTENCES :
- Analyse exploratoire complète (EDA) : stats descriptives, distributions, corrélations, outliers
- Lecture et croisement multi-feuilles Excel et multi-fichiers
- Extraction et analyse de rapports PDF (exports ERP, bilans, tableaux de bord, états financiers)
- Détection automatique du meilleur type de graphique selon les données
- Tableaux croisés dynamiques multi-dimensions
- Analyse de tendances, régression linéaire, prévisions
- Interprétation narrative niveau direction générale (insights, pas juste statistiques)
- Génération de rapports DOCX complets avec graphiques intégrés

PHILOSOPHIE D'ANALYSE :
- Toujours contextualiser les chiffres dans le secteur et le marché africain concerné
- Distinguer corrélation et causalité — signaler les limites explicitement
- Proposer proactivement les analyses complémentaires pertinentes
- Travailler UNIQUEMENT avec les données fournies — jamais inventer
- Signaler clairement quand le dataset est trop petit pour des conclusions fiables

COMPORTEMENT :
- Propose d'abord l'analyse complète, puis affine selon les questions
- Suggère les visualisations optimales pour chaque type de données
- Identifie proactivement les anomalies et leur signification métier
- Croise automatiquement les feuilles Excel quand plusieurs sont disponibles
"""

    def _prompt_questions_specifiques(self) -> str:
        return (
            "- Si données absentes : demander CSV, Excel, PDF ou JSON\n"
            "- Si type d'analyse non précisé : lancer EDA complète par défaut\n"
            "- Si plusieurs feuilles Excel : proposer analyse croisée automatiquement\n"
            "- Si fichier PDF : utiliser l'outil 'pdf_analyser' pour extraire tableaux et données\n"
            "- Si plusieurs fichiers : proposer consolidation ou jointure\n"
            "- Pour les PDFs contenant des tableaux de SI/ERP : utiliser toujours pdf_analyser\n"
            "- Ne jamais redemander les infos déjà fournies"
        )

    def _outils_metier(self) -> list[dict]:
        return [
            {
                "name": "donnees_analyser",
                "description": (
                    "Analyse statistique descriptive complète : min, max, moyenne, médiane, "
                    "écart-type, quartiles, outliers IQR, corrélations inter-colonnes, "
                    "valeurs manquantes. Accepte JSON ou dict pandas."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "donnees":   {"description": "Dataset : liste de dicts ou dict de listes"},
                        "titre":     {"type": "string"},
                        "colonnes":  {"type": "array", "description": "Colonnes à analyser (toutes si absent)"},
                        "avec_correlations": {"type": "boolean", "default": True,
                                               "description": "Calculer la matrice de corrélation"},
                    },
                    "required": ["donnees"],
                },
            },
            {
                "name": "tableau_pivoter",
                "description": (
                    "Tableau croisé dynamique multi-dimensions avec agrégation. "
                    "Ex : ventes par région et par produit, charges par département."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "donnees":      {"description": "Dataset source"},
                        "index":        {"type": "array", "description": "Colonnes en lignes"},
                        "colonnes":     {"type": "array", "description": "Colonnes en entête"},
                        "valeurs":      {"type": "array", "description": "Colonnes à agréger"},
                        "aggregation":  {"type": "string", "description": "sum|mean|count|max|min|std"},
                        "titre":        {"type": "string"},
                    },
                    "required": ["donnees", "index", "valeurs"],
                },
            },
            {
                "name": "graphique_generer",
                "description": (
                    "Génère un graphique haute qualité (PNG). "
                    "Types : barres, courbe, camembert, histogramme, barres_horizontales. "
                    "Si type_graphe='auto', sélectionne automatiquement le meilleur type selon les données."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "donnees":     {"type": "object",
                                        "description": "{'labels': [...], 'series': [{'nom': str, 'valeurs': [...]}]}"},
                        "type_graphe": {"type": "string",
                                        "description": "barres|courbe|camembert|histogramme|barres_horizontales|auto"},
                        "titre":       {"type": "string"},
                        "x_label":     {"type": "string"},
                        "y_label":     {"type": "string"},
                        "col_x":       {"type": "string", "description": "Colonne X pour auto-détection du type"},
                        "col_y":       {"type": "string", "description": "Colonne Y pour auto-détection du type"},
                    },
                    "required": ["donnees", "type_graphe"],
                },
            },
            {
                "name": "tendance_analyser",
                "description": (
                    "Analyse de tendance : régression linéaire, R², direction haussière/baissière/stable, "
                    "moyenne mobile, prévisions 3 prochaines périodes."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "serie":      {"type": "array", "description": "Valeurs numériques ordonnées"},
                        "nom_serie":  {"type": "string"},
                        "fenetre_mm": {"type": "integer", "default": 3},
                    },
                    "required": ["serie"],
                },
            },
            {
                "name": "rapport_data_generer",
                "description": (
                    "Génère un rapport d'analyse complet niveau Senior DA : "
                    "statistiques descriptives, interprétation LLM métier, graphiques automatiques, "
                    "corrélations, anomalies, recommandations stratégiques. "
                    "Produit un fichier DOCX téléchargeable avec graphiques intégrés."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "donnees":           {"description": "Dataset à analyser"},
                        "titre":             {"type": "string"},
                        "contexte":          {"type": "string", "description": "Contexte métier"},
                        "questions":         {"type": "array", "description": "Questions analytiques"},
                        "avec_graphiques":   {"type": "boolean", "default": True},
                        "avec_docx":         {"type": "boolean", "default": True},
                        "pays":              {"type": "string", "default": "Afrique francophone"},
                        "feuilles_info":     {"type": "string", "description": "Info sur les feuilles Excel source"},
                    },
                    "required": ["donnees"],
                },
            },
            {
                "name": "croisement_multi_feuilles",
                "description": (
                    "Croise plusieurs feuilles Excel ou plusieurs DataFrames pour une analyse consolidée. "
                    "Détecte automatiquement les clés de jointure communes."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "feuilles": {
                            "type": "array",
                            "description": "Liste de {'nom': str, 'donnees': dict|list}",
                        },
                        "cle_commune": {"type": "string", "description": "Clé de jointure (auto-détectée si absent)"},
                        "titre":       {"type": "string"},
                    },
                    "required": ["feuilles"],
                },
            },
            {
                "name": "detecter_anomalies_narratif",
                "description": "Détecte et explique les anomalies en langage naturel pour non-techniciens.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "donnees":           {"description": "Dataset"},
                        "contexte_metier":   {"type": "string"},
                        "seuil_aberrant_pct": {"type": "number", "default": 1.5},
                    },
                    "required": ["donnees"],
                },
            },
            {
                "name": "analyser_fichier_entrant",
                "description": "Analyse la structure et la qualité d'un fichier de données entrant.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "description_fichier": {"type": "string"},
                        "type_fichier":        {"type": "string"},
                        "source":              {"type": "string"},
                    },
                    "required": ["description_fichier"],
                },
            },
            {
                "name": "pdf_analyser",
                "description": (
                    "Analyse un rapport ou export PDF provenant d'un SI (ERP, CRM, logiciel comptable, etc.). "
                    "Extrait automatiquement les tableaux, données et texte du PDF, les convertit en DataFrames, "
                    "réalise une analyse statistique complète et produit une interprétation métier niveau senior DA. "
                    "Accepte PDF de rapports, bilans, tableaux de bord, exports ERP, états financiers. "
                    "Fonctionne même si le PDF contient des tableaux complexes ou du texte formaté."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "contenu_base64": {
                            "type": "string",
                            "description": "Contenu du PDF encodé en base64 (si disponible)",
                        },
                        "texte_extrait": {
                            "type": "string",
                            "description": "Texte brut déjà extrait du PDF (si base64 non disponible)",
                        },
                        "titre":         {"type": "string"},
                        "contexte":      {"type": "string", "description": "Contexte métier du document"},
                        "pays":          {"type": "string", "default": "Afrique francophone"},
                        "avec_rapport":  {"type": "boolean", "default": True,
                                          "description": "Générer rapport DOCX complet"},
                    },
                },
            },
        ]

    async def _executer_outil_metier(self, nom: str, params: dict, user_id: int, execution_id: str) -> str:
        if nom == "donnees_analyser":
            return self._outil_analyser(params)
        if nom == "tableau_pivoter":
            return self._outil_pivoter(params)
        if nom == "graphique_generer":
            return self._outil_graphique(params)
        if nom == "tendance_analyser":
            return self._outil_tendance(params)
        if nom == "rapport_data_generer":
            return await self._outil_rapport(params)
        if nom == "croisement_multi_feuilles":
            return await self._outil_croisement(params)
        if nom == "detecter_anomalies_narratif":
            return await self._outil_anomalies_narratif(params)
        if nom == "analyser_fichier_entrant":
            from core.ia_client import ModeIA, ia_client
            prompt = _prompt_analyse_fichier_entrant(params)
            rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
            return rep.contenu
        if nom == "pdf_analyser":
            return await self._outil_pdf_analyser(params)
        return f"[Outil '{nom}' non reconnu par AgentDAA]"

    # ── Implémentations ──────────────────────────────────────────────────────

    def _outil_analyser(self, params: dict) -> str:
        try:
            df = _charger_donnees(params["donnees"])
            colonnes = params.get("colonnes")
            if colonnes:
                df = df[[c for c in colonnes if c in df.columns]]
            stats = _stats_descriptives(df)
            rendu = _rendu_stats(stats, params.get("titre", "Analyse descriptive"))
            if params.get("avec_correlations", True):
                corrs = _calculer_correlations(df)
                if corrs:
                    rendu += "\n\n## Corrélations fortes (|r| ≥ 0.5)\n"
                    for pair, r in sorted(corrs.items(), key=lambda x: abs(x[1]), reverse=True):
                        direction = "positive" if r > 0 else "négative"
                        rendu += f"- **{pair}** : r = {r:.3f} (corrélation {direction})\n"
            return rendu
        except ImportError as e:
            return f"Dépendance manquante : {e}"
        except Exception as e:
            logger.exception("[AgentDAA] donnees_analyser error")
            return f"Erreur : {e}"

    def _outil_pivoter(self, params: dict) -> str:
        try:
            df      = _charger_donnees(params["donnees"])
            index   = params.get("index", [])
            cols    = params.get("colonnes")
            valeurs = params.get("valeurs", [])
            agg     = params.get("aggregation", "sum")
            titre   = params.get("titre", "Tableau croisé")
            missing = [c for c in index + (cols or []) + valeurs if c not in df.columns]
            if missing:
                return f"Colonnes introuvables : {missing}\nColonnes disponibles : {list(df.columns)}"
            pivot = _pivoter_tableau(df, index, cols, valeurs, agg)
            return _rendu_pivot(pivot, titre)
        except ImportError as e:
            return f"Dépendance manquante : {e}"
        except Exception as e:
            logger.exception("[AgentDAA] tableau_pivoter error")
            return f"Erreur pivot : {e}"

    def _outil_graphique(self, params: dict) -> str:
        try:
            type_graphe = params.get("type_graphe", "barres")
            donnees     = params["donnees"]

            # Auto-détection du type si demandé
            if type_graphe == "auto":
                try:
                    # Reconstruire un df minimal pour la détection
                    pd = _import_pandas()
                    labels = donnees.get("labels", [])
                    series = donnees.get("series", [])
                    if labels and series:
                        df_tmp = pd.DataFrame(
                            {s["nom"]: s["valeurs"] for s in series},
                            index=labels,
                        )
                        type_graphe = _choisir_type_graphique(
                            df_tmp,
                            col_x=params.get("col_x"),
                            col_y=params.get("col_y"),
                            nb_series=len(series),
                        )
                    else:
                        type_graphe = "barres"
                except Exception:
                    type_graphe = "barres"

            chemin = _generer_graphique(
                donnees=donnees, type_graphe=type_graphe,
                titre=params.get("titre", ""),
                x_label=params.get("x_label", ""),
                y_label=params.get("y_label", ""),
            )
            nom = Path(chemin).name if chemin and "/" in chemin or "\\" in chemin else chemin
            return (
                f"**Graphique généré** (type : {type_graphe})\n"
                f"Fichier : `{nom}`\n"
                f"Accès : `/api/v1/pro/generateurs/fichier/{nom}`"
            )
        except ImportError as e:
            return f"Dépendance manquante : {e}"
        except Exception as e:
            logger.exception("[AgentDAA] graphique_generer error")
            return f"Erreur graphique : {e}"

    def _outil_tendance(self, params: dict) -> str:
        try:
            serie   = [float(v) for v in params["serie"]]
            nom     = params.get("nom_serie", "Série")
            fenetre = int(params.get("fenetre_mm", 3))
            tendance = _calculer_tendance(serie)
            mm       = _moyennes_mobiles(serie, fenetre)
            rendu    = _rendu_tendance(tendance, nom)
            rendu   += f"\n\n**Moyenne mobile ({fenetre} périodes) :**\n"
            for i, (v, m) in enumerate(zip(serie, mm)):
                rendu += f"  P{i+1}: {v:,.4g}  →  MM{fenetre}: {m:,.4g}\n"
            return rendu
        except Exception as e:
            logger.exception("[AgentDAA] tendance_analyser error")
            return f"Erreur tendance : {e}"

    async def _outil_rapport(self, params: dict) -> str:
        try:
            from pathlib import Path as _Path
            from datetime import datetime as _dt

            df         = _charger_donnees(params["donnees"])
            titre      = params.get("titre", "Rapport d'Analyse de Données")
            contexte   = params.get("contexte", "")
            questions  = params.get("questions", [])
            avec_graph = params.get("avec_graphiques", True)
            avec_docx  = params.get("avec_docx", True)
            pays       = params.get("pays", "Afrique francophone")
            feuilles_info = params.get("feuilles_info", "")

            n_lignes, n_cols = df.shape
            stats    = _stats_descriptives(df)
            corrs    = _calculer_correlations(df)
            rendu_st = _rendu_stats(stats, "Statistiques descriptives")

            # ── Graphiques automatiques ──
            chemins_graphiques = []
            if avec_graph:
                chemins_graphiques = _auto_generer_graphiques(df, titre_base=titre)

            # ── Interprétation LLM senior DA ──
            interp = await _interpreter_donnees_llm(
                df=df, stats=stats, correlations=corrs,
                contexte_metier=contexte, titre=titre,
                pays=pays, feuilles_info=feuilles_info,
            )

            # ── Tableau croisé automatique ──
            pivot_md = ""
            pd_mod = _import_pandas()
            num_cols = df.select_dtypes(include="number").columns.tolist()
            cat_cols = df.select_dtypes(include="object").columns.tolist()
            if cat_cols and num_cols:
                try:
                    pivot_df = _pivoter_tableau(df, [cat_cols[0]], None, num_cols[:3], "sum")
                    pivot_md = _rendu_pivot(pivot_df, f"Tableau croisé : {cat_cols[0]} × {', '.join(num_cols[:3])}")
                except Exception:
                    pass

            # ── Génération DOCX ──
            chemin_docx = None
            if avec_docx:
                try:
                    docx_bytes = _generer_rapport_docx(
                        titre=titre,
                        interpretation=interp,
                        stats_markdown=rendu_st,
                        pivot_markdown=pivot_md,
                        chemins_graphiques=chemins_graphiques,
                        contexte=contexte,
                    )
                    reports_dir = _Path("data/generated/pro_reports")
                    reports_dir.mkdir(parents=True, exist_ok=True)
                    ts = _dt.utcnow().strftime("%Y%m%d_%H%M%S")
                    nom_f = f"rapport_data_{ts}.docx"
                    chemin_docx = reports_dir / nom_f
                    chemin_docx.write_bytes(docx_bytes)
                    logger.info(f"[AgentDAA] Rapport DOCX : {chemin_docx}")
                except Exception as e_docx:
                    logger.warning(f"[AgentDAA] DOCX échoué : {e_docx}")

            # ── Résultat final ──
            lignes = [
                f"# {titre}",
                f"**Dataset** : {n_lignes:,} lignes × {n_cols} colonnes\n",
            ]
            if questions:
                lignes.append("**Questions d'analyse :**")
                for q in questions:
                    lignes.append(f"- {q}")
                lignes.append("")

            lignes.append(interp)

            if pivot_md:
                lignes.append("\n## Tableau croisé dynamique automatique\n")
                lignes.append(pivot_md)

            if chemins_graphiques:
                lignes.append("\n## Graphiques générés\n")
                for ch in chemins_graphiques:
                    nom = _Path(ch).name
                    lignes.append(f"- `{nom}` → `/api/v1/pro/generateurs/fichier/{nom}`")

            if chemin_docx:
                lignes.append(f"\n## Rapport DOCX\n")
                lignes.append(f"Fichier téléchargeable : `/api/v1/pro/generateurs/fichier/{chemin_docx.name}`")

            return "\n".join(lignes)

        except ImportError as e:
            return f"Dépendance manquante : {e}"
        except Exception as e:
            logger.exception("[AgentDAA] rapport_data_generer error")
            return f"Erreur rapport : {e}"

    async def _outil_croisement(self, params: dict) -> str:
        try:
            feuilles_raw = params.get("feuilles", [])
            cle_commune  = params.get("cle_commune")
            titre        = params.get("titre", "Analyse croisée")

            if len(feuilles_raw) < 2:
                return "Au moins 2 feuilles/datasets nécessaires pour un croisement."

            feuilles = []
            for f in feuilles_raw:
                df = _charger_donnees(f["donnees"])
                feuilles.append((f.get("nom", f"Dataset {len(feuilles)+1}"), df))

            # Essayer la jointure
            df_final, nom1, nom2 = feuilles[0][1], feuilles[0][0], feuilles[1][0]
            df_croise = _croiser_deux_dataframes(df_final, nom1, feuilles[1][1], nom2, cle_commune)

            # Ajouter les feuilles supplémentaires
            for nom, df in feuilles[2:]:
                df_croise = _croiser_deux_dataframes(df_croise, "croisé", df, nom, cle_commune)

            stats = _stats_descriptives(df_croise)
            rendu = _rendu_stats(stats, f"{titre} — {df_croise.shape[0]:,} lignes × {df_croise.shape[1]} colonnes")
            corrs = _calculer_correlations(df_croise)
            if corrs:
                rendu += "\n\n**Corrélations croisées (|r| ≥ 0.5) :**\n"
                for pair, r in sorted(corrs.items(), key=lambda x: abs(x[1]), reverse=True)[:8]:
                    rendu += f"- **{pair}** : r = {r:.3f}\n"

            return rendu

        except Exception as e:
            logger.exception("[AgentDAA] croisement_multi_feuilles error")
            return f"Erreur croisement : {e}"

    async def _outil_anomalies_narratif(self, params: dict) -> str:
        try:
            from core.ia_client import ModeIA, ia_client
            df       = _charger_donnees(params["donnees"])
            stats    = _stats_descriptives(df)
            contexte = params.get("contexte_metier", "")

            anomalies = []
            for col, s in stats.items():
                if s.get("nb_outliers", 0) > 0:
                    anomalies.append(
                        f"Colonne '{col}' : {s['nb_outliers']} valeur(s) aberrante(s) "
                        f"(min={s.get('min', '?')}, max={s.get('max', '?')}, "
                        f"Q1={s.get('q1', '?')}, Q3={s.get('q3', '?')})"
                    )
                if s.get("pct_manquants", 0) > 10:
                    anomalies.append(
                        f"Colonne '{col}' : {s['pct_manquants']}% de valeurs manquantes — impact sur fiabilité"
                    )

            if not anomalies:
                return "✅ Aucune anomalie significative détectée (seuil IQR + seuil 10% manquants)."

            prompt = f"""Tu es un analyste de données expert.

Génère un rapport d'anomalies en langage naturel, accessible à un dirigeant non-technicien.

CONTEXTE MÉTIER : {contexte or 'Non précisé'}

ANOMALIES DÉTECTÉES :
{chr(10).join(f'  • {a}' for a in anomalies)}

RAPPORT STRUCTURÉ :
1. **Résumé exécutif** (2-3 phrases) — what's wrong en termes simples
2. **Détail par anomalie** — signification concrète dans le métier
3. **Causes probables** — erreurs de saisie, cas exceptionnels, fraude potentielle ?
4. **Impact si ignoré** — conséquences opérationnelles
5. **Actions recommandées** — qui doit vérifier quoi, dans quel délai

Style : clair, non technique, actionnable, concis."""

            rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
            return rep.contenu
        except ImportError as e:
            return f"Dépendance manquante : {e}"
        except Exception as e:
            logger.exception("[AgentDAA] anomalies_narratif error")
            return f"Erreur : {e}"

    async def _outil_pdf_analyser(self, params: dict) -> str:
        """
        Analyse un PDF de rapport / export SI :
          - Extrait tableaux + texte
          - EDA sur chaque tableau
          - Interprétation LLM niveau senior DA
          - Rapport DOCX si demandé
        """
        import base64
        pd = _import_pandas()

        titre   = params.get("titre", "Analyse rapport PDF")
        contexte = params.get("contexte", "")
        pays    = params.get("pays", "Afrique francophone")
        avec_rapport = params.get("avec_rapport", True)

        dataframes: list = []
        texte: str = ""

        # 1. Décoder le PDF depuis base64 si fourni
        b64 = params.get("contenu_base64", "")
        texte_extrait = params.get("texte_extrait", "")

        if b64:
            try:
                if "," in b64:
                    b64 = b64.split(",", 1)[1]
                contenu_bytes = base64.b64decode(b64)
                dataframes, texte = _extraire_pdf_tableaux_et_contexte(contenu_bytes)
            except Exception as e:
                return f"Erreur décodage PDF : {e}"
        elif texte_extrait:
            texte = texte_extrait
            # Tenter de détecter des tableaux dans le texte
            df_texte = _pdf_texte_vers_dataframe(texte_extrait)
            if df_texte is not None and not df_texte.empty:
                dataframes = [df_texte]
        else:
            return (
                "Aucun contenu PDF fourni. Envoyez le fichier PDF directement dans le chat "
                "ou fournissez le texte extrait via 'texte_extrait'."
            )

        if not dataframes and not texte:
            return (
                "Le PDF ne contient pas de tableaux extractibles ou de texte lisible. "
                "Il s'agit peut-être d'un PDF scanné (image). "
                "Pour les PDFs scannés, une OCR est nécessaire (non disponible actuellement)."
            )

        # 2. Résumé pour le LLM
        resume_pdf = _resumer_pdf_pour_llm(dataframes, texte)

        # 3. EDA sur chaque tableau extrait
        stats_globales = {}
        df_principal = None
        parties_stats = []

        for i, df in enumerate(dataframes[:4]):
            src = df.attrs.get("source", f"Tableau {i+1}")
            try:
                stats = _stats_descriptives(df)
                stats_globales.update({f"{src}::{k}": v for k, v in stats.items()})
                parties_stats.append(_rendu_stats(stats, f"{titre} — {src}"))
                if df_principal is None and not df.empty:
                    df_principal = df
            except Exception as e:
                logger.debug(f"[AgentDAA] Stats tableau {src} : {e}")

        # 4. Corrélations sur le DataFrame principal
        correlations = {}
        if df_principal is not None:
            try:
                correlations = _calculer_correlations(df_principal)
            except Exception:
                pass

        # 5. Interprétation LLM avec contexte du PDF
        contexte_metier = f"{contexte}\n\nContenu du document :\n{resume_pdf[:3000]}" if contexte else f"Contenu du document PDF :\n{resume_pdf[:3000]}"
        df_analyse = df_principal if df_principal is not None else pd.DataFrame()

        try:
            if df_analyse.empty:
                # Interprétation purement textuelle
                from core.ia_client import ModeIA, ia_client
                prompt_txt = f"""Tu es un Data Analyst Senior. Analyse ce rapport PDF et produis une interprétation structurée.

DOCUMENT : {titre}
PAYS/ZONE : {pays}
CONTEXTE : {contexte or 'Non précisé'}

CONTENU DU DOCUMENT :
{resume_pdf[:6000]}

ANALYSE REQUISE :
## 1. Synthèse exécutive
## 2. Indicateurs et chiffres clés identifiés
## 3. Tendances et observations
## 4. Points d'attention et anomalies
## 5. Recommandations stratégiques

Style : factuel, chiffres précis, contexte africain si pertinent."""
                rep = await ia_client.appeler(prompt=prompt_txt, mode=ModeIA.REDACTION,
                                               max_tokens_override=3000)
                interpretation = rep.contenu if hasattr(rep, "contenu") else str(rep)
            else:
                interpretation = await _interpreter_donnees_llm(
                    df_analyse, stats_globales, correlations,
                    contexte_metier=contexte_metier, titre=titre, pays=pays,
                    feuilles_info=f"\n**Source** : Rapport PDF — {len(dataframes)} tableau(x) extrait(s)",
                )
        except Exception as e:
            interpretation = f"Interprétation indisponible : {e}"

        # 6. Graphiques automatiques
        chemins_graphs: list[str] = []
        if df_principal is not None and not df_principal.empty:
            try:
                chemins_graphs = _auto_generer_graphiques(df_principal, titre)
            except Exception:
                pass

        # 7. Rapport DOCX
        chemin_docx = None
        if avec_rapport and interpretation:
            try:
                stats_md = "\n\n".join(parties_stats) if parties_stats else ""
                # Info sur les tableaux en aperçu
                apercu_tableaux = ""
                for i, df in enumerate(dataframes[:3]):
                    src = df.attrs.get("source", f"Tableau {i+1}")
                    apercu_tableaux += f"\n**{src}** ({df.shape[0]} lignes × {df.shape[1]} colonnes)\n"
                    apercu_tableaux += df.head(5).to_string(index=False) + "\n"

                docx_bytes = _generer_rapport_docx(
                    titre=f"Analyse — {titre}",
                    interpretation=interpretation,
                    stats_markdown=stats_md + "\n\n## Aperçu des tableaux extraits\n" + apercu_tableaux,
                    pivot_markdown="",
                    chemins_graphiques=chemins_graphs,
                    contexte=f"Source : PDF  |  {len(dataframes)} tableau(x) extrait(s)  |  {pays}",
                )
                nom_f = f"analyse_pdf_{uuid.uuid4().hex[:8]}.docx"
                chemin_docx = str(_OUTPUT_DIR / nom_f)
                with open(chemin_docx, "wb") as f:
                    f.write(docx_bytes)
            except Exception as e:
                logger.warning(f"[AgentDAA] DOCX PDF échoué : {e}")

        # 8. Réponse Markdown
        parties: list[str] = [
            f"# Analyse du rapport PDF : {titre}\n",
            f"*{len(dataframes)} tableau(x) extrait(s) · "
            f"{df_principal.shape[0] if df_principal is not None else 0} lignes de données*\n",
        ]

        if not dataframes:
            parties.append("⚠️ **Aucun tableau structuré détecté** — analyse basée sur le texte du document.\n")

        parties.append(interpretation)

        if chemins_graphs:
            parties.append(f"\n\n📊 **{len(chemins_graphs)} graphique(s) généré(s) automatiquement**")
            for ch in chemins_graphs:
                parties.append(f"- `{Path(ch).name}`")

        if chemin_docx:
            parties.append(f"\n\n📄 **Rapport DOCX** : `{Path(chemin_docx).name}`")

        return "\n".join(parties)
