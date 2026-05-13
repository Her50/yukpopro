"""
Analyseur Excel Avancé — YukpoAssurance
Analyse profonde d'un fichier Excel depuis le SI ou envoyé par l'utilisateur.

Fonctionnalités :
  - Chargement depuis bytes (upload) ou chemin (SI)
  - Analyse statistique complète par pandas (stats descriptives, corrélations,
    valeurs manquantes, outliers, distributions)
  - Génération de graphiques matplotlib (barres, lignes, secteurs, heatmap)
    exportés en base64 PNG, prêts à être intégrés dans un rapport ou PPT
  - Commentaire IA contextuel (Claude en priorité, GPT-4o en fallback)
  - Données dashboard prêtes à afficher côté frontend
"""
from __future__ import annotations

import base64
import io
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("yukpo.analyseur_excel")

# ─── Structures de résultat ──────────────────────────────────────────────────

@dataclass
class ColonneAnalyse:
    nom: str
    type_donnee: str          # numeric | categoric | datetime | bool | mixed
    nb_valeurs: int
    nb_manquants: int
    pct_manquants: float
    # Champs numériques
    min: Optional[float] = None
    max: Optional[float] = None
    moyenne: Optional[float] = None
    mediane: Optional[float] = None
    ecart_type: Optional[float] = None
    q25: Optional[float] = None
    q75: Optional[float] = None
    nb_outliers: int = 0
    # Champs catégoriels
    nb_uniques: int = 0
    top_valeurs: List[Tuple[Any, int]] = field(default_factory=list)


@dataclass
class GraphiqueAnalyse:
    titre: str
    type_graphique: str       # bar | line | pie | heatmap | hist | scatter | box
    image_base64: str         # PNG en base64 (sans le préfixe data:image/...)
    colonne: Optional[str] = None
    description: str = ""


@dataclass
class ResultatAnalyse:
    nom_fichier: str
    nb_feuilles: int
    feuilles: List[str]
    feuille_active: str
    nb_lignes: int
    nb_colonnes: int
    colonnes: List[ColonneAnalyse]
    correlations: Optional[Dict[str, Dict[str, float]]] = None
    graphiques: List[GraphiqueAnalyse] = field(default_factory=list)
    resume_ia: str = ""
    points_cles: List[str] = field(default_factory=list)
    alertes: List[str] = field(default_factory=list)
    tableau_resume: List[Dict] = field(default_factory=list)   # pour affichage dashboard


# ─── Helpers graphiques ───────────────────────────────────────────────────────

def _fig_to_b64(fig) -> str:
    """Exporte une figure matplotlib en PNG base64."""
    import matplotlib
    matplotlib.use("Agg")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def _safe_float(v) -> Optional[float]:
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 4)
    except Exception:
        return None


# ─── Analyse d'une feuille ───────────────────────────────────────────────────

def _analyser_colonne(series: pd.Series) -> ColonneAnalyse:
    nom = str(series.name)
    nb_valeurs = len(series)
    nb_manquants = int(series.isna().sum())
    pct_manquants = round(nb_manquants / nb_valeurs * 100, 2) if nb_valeurs > 0 else 0.0
    nb_uniques = int(series.nunique())

    # Détection type
    if pd.api.types.is_datetime64_any_dtype(series):
        dtype = "datetime"
    elif pd.api.types.is_bool_dtype(series):
        dtype = "bool"
    elif pd.api.types.is_numeric_dtype(series):
        dtype = "numeric"
    elif nb_uniques <= min(50, nb_valeurs // 2 + 1):
        dtype = "categoric"
    else:
        dtype = "text"

    col = ColonneAnalyse(
        nom=nom,
        type_donnee=dtype,
        nb_valeurs=nb_valeurs,
        nb_manquants=nb_manquants,
        pct_manquants=pct_manquants,
        nb_uniques=nb_uniques,
    )

    if dtype == "numeric":
        clean = series.dropna()
        if len(clean) > 0:
            q25 = clean.quantile(0.25)
            q75 = clean.quantile(0.75)
            iqr = q75 - q25
            nb_outliers = int(((clean < q25 - 1.5 * iqr) | (clean > q75 + 1.5 * iqr)).sum())
            col.min = _safe_float(clean.min())
            col.max = _safe_float(clean.max())
            col.moyenne = _safe_float(clean.mean())
            col.mediane = _safe_float(clean.median())
            col.ecart_type = _safe_float(clean.std())
            col.q25 = _safe_float(q25)
            col.q75 = _safe_float(q75)
            col.nb_outliers = nb_outliers

    elif dtype in ("categoric", "text", "bool"):
        vc = series.value_counts().head(10)
        col.top_valeurs = [(str(k), int(v)) for k, v in vc.items()]

    return col


def _generer_graphiques(df: pd.DataFrame, colonnes: List[ColonneAnalyse], theme_color: str = "#1F4E79") -> List[GraphiqueAnalyse]:
    """Génère jusqu'à 6 graphiques pertinents selon les colonnes disponibles."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    import seaborn as sns

    graphiques: List[GraphiqueAnalyse] = []
    plt.rcParams["font.family"] = "DejaVu Sans"
    plt.rcParams["axes.facecolor"] = "#F8FAFC"
    plt.rcParams["figure.facecolor"] = "#FFFFFF"

    cols_num = [c for c in colonnes if c.type_donnee == "numeric"]
    cols_cat = [c for c in colonnes if c.type_donnee in ("categoric", "bool")]

    # 1. Histogramme de la première colonne numérique
    if cols_num:
        col = cols_num[0]
        data = df[col.nom].dropna()
        if len(data) > 0:
            fig, ax = plt.subplots(figsize=(7, 4))
            ax.hist(data, bins=min(30, len(data.unique())), color=theme_color, alpha=0.8, edgecolor="white")
            ax.set_title(f"Distribution — {col.nom}", fontsize=13, fontweight="bold", pad=12)
            ax.set_xlabel(col.nom, fontsize=10)
            ax.set_ylabel("Fréquence", fontsize=10)
            ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
            fig.tight_layout()
            graphiques.append(GraphiqueAnalyse(
                titre=f"Distribution — {col.nom}",
                type_graphique="hist",
                image_base64=_fig_to_b64(fig),
                colonne=col.nom,
                description=f"Distribution des valeurs de {col.nom} — moy={col.moyenne}, σ={col.ecart_type}",
            ))
            plt.close(fig)

    # 2. Barres pour la première colonne catégorielle
    if cols_cat:
        col = cols_cat[0]
        if col.top_valeurs:
            labels = [v[0][:20] for v in col.top_valeurs[:10]]
            counts = [v[1] for v in col.top_valeurs[:10]]
            fig, ax = plt.subplots(figsize=(8, 4))
            bars = ax.bar(labels, counts, color=theme_color, alpha=0.85, edgecolor="white")
            ax.bar_label(bars, fmt="%d", fontsize=9, padding=2)
            ax.set_title(f"Top valeurs — {col.nom}", fontsize=13, fontweight="bold", pad=12)
            ax.set_ylabel("Nombre", fontsize=10)
            plt.xticks(rotation=35, ha="right", fontsize=9)
            fig.tight_layout()
            graphiques.append(GraphiqueAnalyse(
                titre=f"Distribution catégorielle — {col.nom}",
                type_graphique="bar",
                image_base64=_fig_to_b64(fig),
                colonne=col.nom,
                description=f"Répartition des valeurs de {col.nom} ({col.nb_uniques} catégories distinctes)",
            ))
            plt.close(fig)

    # 3. Matrice de corrélation si ≥ 2 colonnes numériques
    if len(cols_num) >= 2:
        noms_num = [c.nom for c in cols_num[:10]]
        corr_df = df[noms_num].corr()
        fig, ax = plt.subplots(figsize=(max(6, len(noms_num)), max(5, len(noms_num) - 1)))
        mask = np.zeros_like(corr_df, dtype=bool)
        mask[np.triu_indices_from(mask)] = True
        sns.heatmap(
            corr_df, mask=mask, annot=True, fmt=".2f", cmap="Blues",
            ax=ax, linewidths=0.5, cbar_kws={"shrink": 0.8}, annot_kws={"size": 9},
        )
        ax.set_title("Matrice de corrélations", fontsize=13, fontweight="bold", pad=12)
        fig.tight_layout()
        graphiques.append(GraphiqueAnalyse(
            titre="Matrice de corrélations",
            type_graphique="heatmap",
            image_base64=_fig_to_b64(fig),
            description="Corrélations de Pearson entre toutes les colonnes numériques",
        ))
        plt.close(fig)

    # 4. Évolution temporelle si colonne datetime + colonne numérique
    cols_dt = [c for c in colonnes if c.type_donnee == "datetime"]
    if cols_dt and cols_num:
        col_dt = cols_dt[0].nom
        col_val = cols_num[0].nom
        try:
            ts = df[[col_dt, col_val]].dropna().sort_values(col_dt)
            if len(ts) >= 5:
                fig, ax = plt.subplots(figsize=(9, 4))
                ax.plot(ts[col_dt], ts[col_val], color=theme_color, linewidth=2, marker="o", markersize=3)
                ax.fill_between(ts[col_dt], ts[col_val], alpha=0.15, color=theme_color)
                ax.set_title(f"Évolution de {col_val} dans le temps", fontsize=13, fontweight="bold", pad=12)
                ax.set_xlabel(col_dt, fontsize=10)
                ax.set_ylabel(col_val, fontsize=10)
                plt.xticks(rotation=30, ha="right", fontsize=8)
                fig.tight_layout()
                graphiques.append(GraphiqueAnalyse(
                    titre=f"Évolution — {col_val}",
                    type_graphique="line",
                    image_base64=_fig_to_b64(fig),
                    colonne=col_val,
                    description=f"Série temporelle de {col_val} par {col_dt}",
                ))
                plt.close(fig)
        except Exception:
            pass

    # 5. Camembert si colonne catégorielle avec ≤ 8 catégories
    for col in cols_cat:
        if col.nb_uniques <= 8 and col.top_valeurs:
            labels = [v[0][:20] for v in col.top_valeurs]
            sizes = [v[1] for v in col.top_valeurs]
            palette = plt.cm.get_cmap("tab10").colors
            fig, ax = plt.subplots(figsize=(6, 5))
            wedges, texts, autotexts = ax.pie(
                sizes, labels=labels, autopct="%1.1f%%",
                colors=palette[:len(labels)], startangle=140,
                textprops={"fontsize": 9},
            )
            for at in autotexts:
                at.set_fontsize(8)
            ax.set_title(f"Répartition — {col.nom}", fontsize=13, fontweight="bold", pad=12)
            fig.tight_layout()
            graphiques.append(GraphiqueAnalyse(
                titre=f"Répartition — {col.nom}",
                type_graphique="pie",
                image_base64=_fig_to_b64(fig),
                colonne=col.nom,
                description=f"Parts relatives des catégories de {col.nom}",
            ))
            plt.close(fig)
            break  # un seul camembert suffit

    # 6. Box plots si plusieurs colonnes numériques
    if len(cols_num) >= 3:
        noms = [c.nom for c in cols_num[:6]]
        fig, ax = plt.subplots(figsize=(max(8, len(noms) * 1.5), 5))
        data_box = [df[n].dropna().values for n in noms]
        bp = ax.boxplot(data_box, patch_artist=True, notch=False)
        colors = plt.cm.get_cmap("Blues")(np.linspace(0.3, 0.8, len(noms)))
        for patch, color in zip(bp["boxes"], colors):
            patch.set_facecolor(color)
        ax.set_xticklabels([n[:15] for n in noms], rotation=30, ha="right", fontsize=9)
        ax.set_title("Distribution des variables numériques (box plots)", fontsize=13, fontweight="bold", pad=12)
        ax.set_ylabel("Valeurs", fontsize=10)
        fig.tight_layout()
        graphiques.append(GraphiqueAnalyse(
            titre="Box plots — variables numériques",
            type_graphique="box",
            image_base64=_fig_to_b64(fig),
            description="Comparaison des distributions et détection des outliers",
        ))
        plt.close(fig)

    return graphiques


# ─── Analyse principale ───────────────────────────────────────────────────────

async def analyser_excel(
    contenu: bytes,
    nom_fichier: str = "fichier.xlsx",
    feuille: Optional[str] = None,
    contexte_utilisateur: str = "",
    claude_api_key: str = "",
    openai_api_key: str = "",
) -> ResultatAnalyse:
    """
    Point d'entrée principal : analyse complète d'un fichier Excel.

    Args:
        contenu          : bytes du fichier .xlsx / .xls
        nom_fichier      : nom d'affichage
        feuille          : feuille à analyser (None = première feuille)
        contexte_utilisateur: texte de contexte pour l'IA (secteur, objectif…)
        claude_api_key   : clé Anthropic
        openai_api_key   : clé OpenAI (fallback)

    Returns:
        ResultatAnalyse complet avec graphiques et commentaire IA
    """
    # ── Chargement ──────────────────────────────────────────────────────────
    try:
        engine = "openpyxl" if nom_fichier.lower().endswith(".xlsx") else "xlrd"
        xls = pd.ExcelFile(io.BytesIO(contenu), engine=engine)
    except Exception as e:
        logger.error(f"[Excel] Impossible de lire {nom_fichier}: {e}")
        raise ValueError(f"Fichier Excel invalide ou corrompu : {e}")

    feuilles = xls.sheet_names
    feuille_active = feuille if (feuille and feuille in feuilles) else feuilles[0]
    df = pd.read_excel(io.BytesIO(contenu), sheet_name=feuille_active, engine=engine)

    # Nettoyage colonnes dupliquées
    df.columns = [str(c).strip() for c in df.columns]
    df = df.loc[:, ~df.columns.duplicated()]

    # Conversion des colonnes datetime potentielles
    for col in df.columns:
        if df[col].dtype == object:
            try:
                converted = pd.to_datetime(df[col], dayfirst=True, errors="coerce")
                if converted.notna().sum() > len(df) * 0.5:
                    df[col] = converted
            except Exception:
                pass

    nb_lignes, nb_colonnes = df.shape

    # ── Analyse statistique ──────────────────────────────────────────────────
    colonnes_analyse = [_analyser_colonne(df[c]) for c in df.columns]

    # Matrice de corrélation
    cols_num = [c.nom for c in colonnes_analyse if c.type_donnee == "numeric"]
    correlations: Optional[Dict] = None
    if len(cols_num) >= 2:
        corr = df[cols_num].corr().round(3)
        correlations = {
            col: {other: _safe_float(corr.loc[col, other]) for other in cols_num}
            for col in cols_num
        }

    # ── Génération des graphiques ────────────────────────────────────────────
    try:
        graphiques = _generer_graphiques(df, colonnes_analyse)
    except Exception as e:
        logger.warning(f"[Excel] Erreur génération graphiques: {e}")
        graphiques = []

    # ── Tableau résumé (dashboard) ───────────────────────────────────────────
    tableau_resume = []
    for col in colonnes_analyse:
        row: Dict[str, Any] = {"colonne": col.nom, "type": col.type_donnee, "manquants_pct": col.pct_manquants}
        if col.type_donnee == "numeric":
            row.update({"min": col.min, "max": col.max, "moyenne": col.moyenne,
                        "mediane": col.mediane, "ecart_type": col.ecart_type, "outliers": col.nb_outliers})
        else:
            row["nb_uniques"] = col.nb_uniques
        tableau_resume.append(row)

    # ── Génération alertes automatiques ─────────────────────────────────────
    alertes: List[str] = []
    for col in colonnes_analyse:
        if col.pct_manquants > 20:
            alertes.append(f"⚠️ {col.nom} : {col.pct_manquants}% de valeurs manquantes")
        if col.type_donnee == "numeric" and col.nb_outliers and col.nb_valeurs > 0:
            pct_out = round(col.nb_outliers / col.nb_valeurs * 100, 1)
            if pct_out > 5:
                alertes.append(f"🔍 {col.nom} : {col.nb_outliers} outliers détectés ({pct_out}%)")

    if correlations:
        for c1, vals in correlations.items():
            for c2, r in vals.items():
                if c1 < c2 and r is not None and abs(r) > 0.85:
                    alertes.append(f"📊 Forte corrélation entre {c1} et {c2} (r={r})")

    # ── Points clés ─────────────────────────────────────────────────────────
    points_cles: List[str] = [
        f"Fichier : {nom_fichier} — {nb_lignes} lignes × {nb_colonnes} colonnes",
        f"Feuilles disponibles : {', '.join(feuilles)} (analyse sur « {feuille_active} »)",
    ]
    if cols_num:
        col_ref = next((c for c in colonnes_analyse if c.type_donnee == "numeric"), None)
        if col_ref and col_ref.moyenne is not None:
            points_cles.append(f"Variable principale ({col_ref.nom}) : moy={col_ref.moyenne}, σ={col_ref.ecart_type}")
    nb_man_total = sum(c.nb_manquants for c in colonnes_analyse)
    if nb_man_total > 0:
        points_cles.append(f"Données manquantes totales : {nb_man_total} cellules sur {nb_lignes * nb_colonnes}")

    # ── Commentaire IA ───────────────────────────────────────────────────────
    resume_ia = await _generer_commentaire_ia(
        nom_fichier=nom_fichier,
        feuille=feuille_active,
        nb_lignes=nb_lignes,
        nb_colonnes=nb_colonnes,
        colonnes=colonnes_analyse,
        alertes=alertes,
        contexte=contexte_utilisateur,
        claude_api_key=claude_api_key,
        openai_api_key=openai_api_key,
    )

    return ResultatAnalyse(
        nom_fichier=nom_fichier,
        nb_feuilles=len(feuilles),
        feuilles=feuilles,
        feuille_active=feuille_active,
        nb_lignes=nb_lignes,
        nb_colonnes=nb_colonnes,
        colonnes=colonnes_analyse,
        correlations=correlations,
        graphiques=graphiques,
        resume_ia=resume_ia,
        points_cles=points_cles,
        alertes=alertes,
        tableau_resume=tableau_resume,
    )


async def _generer_commentaire_ia(
    nom_fichier: str,
    feuille: str,
    nb_lignes: int,
    nb_colonnes: int,
    colonnes: List[ColonneAnalyse],
    alertes: List[str],
    contexte: str,
    claude_api_key: str,
    openai_api_key: str,
) -> str:
    """Génère un commentaire analytique via Claude (fallback GPT-4o)."""

    # Résumé compact des colonnes pour le prompt
    resume_cols = []
    for c in colonnes[:20]:  # max 20 colonnes pour le prompt
        if c.type_donnee == "numeric":
            resume_cols.append(
                f"- {c.nom} [numérique] : min={c.min}, max={c.max}, moy={c.moyenne}, "
                f"σ={c.ecart_type}, manquants={c.pct_manquants}%"
            )
        else:
            top = ", ".join(f"{v[0]}({v[1]})" for v in c.top_valeurs[:3])
            resume_cols.append(
                f"- {c.nom} [{c.type_donnee}] : {c.nb_uniques} valeurs distinctes, top: {top}, "
                f"manquants={c.pct_manquants}%"
            )

    alertes_str = "\n".join(alertes[:10]) if alertes else "Aucune alerte majeure"
    contexte_str = f"\nContexte fourni par l'utilisateur : {contexte}" if contexte else ""

    prompt = f"""Tu es un expert en analyse de données. Voici les statistiques d'un fichier Excel.
Génère un commentaire analytique professionnel en français (6-8 paragraphes), structuré ainsi :
1. Vue d'ensemble du fichier
2. Qualité des données (complétude, cohérence)
3. Analyse des variables clés
4. Tendances et patterns détectés
5. Anomalies et points d'attention
6. Recommandations concrètes{contexte_str}

Fichier : {nom_fichier} | Feuille : {feuille} | {nb_lignes} lignes × {nb_colonnes} colonnes

Statistiques des colonnes :
{chr(10).join(resume_cols)}

Alertes automatiques :
{alertes_str}

Réponds directement avec le commentaire, sans titre ni introduction répétant les données brutes."""

    # Essai Claude
    if claude_api_key:
        try:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=claude_api_key)
            msg = await client.messages.create(
                model="claude-opus-4-6",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text.strip()
        except Exception as e:
            logger.warning(f"[Excel/IA] Claude erreur: {e}")

    # Fallback GPT-4o
    if openai_api_key:
        try:
            import openai
            client = openai.AsyncOpenAI(api_key=openai_api_key)
            resp = await client.chat.completions.create(
                # Analyse Excel : tier mid — pattern detection + commentaire,
                # gpt-5-mini bat gpt-4o legacy en analyse structurée
                model="gpt-5-mini",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"[Excel/IA] GPT-4o erreur: {e}")

    return "Analyse automatique effectuée. Aucune clé IA disponible pour le commentaire narratif."


# ─── Chargement depuis le SI (ORASS / dossier CSV) ───────────────────────────

async def analyser_excel_depuis_si(
    chemin: str,
    contexte_utilisateur: str = "",
    claude_api_key: str = "",
    openai_api_key: str = "",
) -> ResultatAnalyse:
    """
    Charge et analyse un fichier Excel/CSV depuis le système de fichiers du SI.
    Supporte .xlsx, .xls, .csv (séparateur auto-détecté).
    """
    import os
    if not os.path.exists(chemin):
        raise FileNotFoundError(f"Fichier SI introuvable : {chemin}")

    nom_fichier = os.path.basename(chemin)
    with open(chemin, "rb") as f:
        contenu = f.read()

    # Cas CSV : conversion en DataFrame puis export en mémoire comme xlsx
    if chemin.lower().endswith(".csv"):
        try:
            df_csv = pd.read_csv(io.BytesIO(contenu), sep=None, engine="python", encoding_errors="replace")
            buf = io.BytesIO()
            df_csv.to_excel(buf, index=False, engine="openpyxl")
            contenu = buf.getvalue()
            nom_fichier = nom_fichier.replace(".csv", ".xlsx")
        except Exception as e:
            raise ValueError(f"CSV invalide : {e}")

    return await analyser_excel(
        contenu=contenu,
        nom_fichier=nom_fichier,
        contexte_utilisateur=contexte_utilisateur,
        claude_api_key=claude_api_key,
        openai_api_key=openai_api_key,
    )
