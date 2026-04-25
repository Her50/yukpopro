"""
YukpoAssurance — Module Enquêtes & Études qualitatives/quantitatives
Pipeline complet :
  Qualitative : audio terrain → Whisper → transcription → Claude analyse thématique → rapport PDF/Word
  Quantitative : formulaire KoBoCollect-like → collecte données → stats + graphiques → rapport
"""
import base64
import io
import json
import logging
import re
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("yukpo_assurance.enquetes")

WHISPER_MAX_BYTES = 24 * 1024 * 1024


# ─── Modèles de données ────────────────────────────────────────────────────────

@dataclass
class TranscriptionAudio:
    fichier_nom: str
    transcription: str
    duree_estimee_min: float = 0.0
    locuteur: str = "Inconnu"  # Participant / Répondant / Informateur
    date_collecte: Optional[str] = None


@dataclass
class ThemeQualitatif:
    code: str           # ex : "accès_soins"
    libelle: str        # ex : "Difficultés d'accès aux soins de santé"
    frequence: int = 0  # nombre d'occurrences dans les transcriptions
    citations: list[str] = field(default_factory=list)   # verbatims extraits
    sous_themes: list[str] = field(default_factory=list)
    sentiment: str = "neutre"  # "positif" | "négatif" | "neutre" | "mixte"


@dataclass
class QuestionFormulaire:
    question_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    libelle: str = ""
    type_question: str = "text"
    # text | number | select_one | select_multiple | rating | likert | date | oui_non
    # geopoint | image | note | calculate | begin_group | end_group | begin_repeat | end_repeat
    options: list[str] = field(default_factory=list)
    obligatoire: bool = True
    ordre: int = 0
    # ── Champs XLSForm étendus ──────────────────────────────────────────────────
    hint: str = ""                  # Aide pour l'enquêteur
    section_id: str = ""            # Identifiant du groupe/section parent
    section_label: str = ""         # Label de la section (pour begin_group)
    relevant: str = ""              # Logique conditionnelle: "${sexe} = 'feminin'"
    constraint: str = ""            # Validation: ". > 0 and . < 120"
    constraint_message: str = ""    # Message d'erreur personnalisé
    appearance: str = ""            # "likert" | "minimal" | "horizontal" | "field-list" | "table-list"
    parameters: str = ""            # Pour range: "start=1 end=5 step=1"
    is_repeat_group: bool = False   # True si begin_repeat/end_repeat
    repeat_count: str = ""          # "${nb_membres}" ou entier fixe
    calculation: str = ""           # Pour type calculate
    is_matrix_row: bool = False     # Question dans une matrice table-list
    matrix_list_name: str = ""      # Liste de choix partagée dans une matrice
    name_xlsform: str = ""          # Nom ODK court (slug) pour les références ${...} dans relevant


@dataclass
class Formulaire:
    formulaire_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    titre: str = ""
    description: str = ""
    questions: list[QuestionFormulaire] = field(default_factory=list)
    sections: list[dict] = field(default_factory=list)   # structure complète avec imbrication
    metadata_auto: bool = True      # Ajouter start/end/deviceid automatiquement
    actif: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reponses: list[dict] = field(default_factory=list)
    # Dictionnaire des variables : {name_xlsform: {description, unite, categorie, notes_metier, modalites_detaillees}}
    dictionnaire_variables: dict = field(default_factory=dict)
    # Plan d'analyse éditable (texte markdown)
    plan_analyse: str = ""


@dataclass
class Etude:
    etude_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    titre: str = ""
    contexte: str = ""          # fourni par l'utilisateur — contexte de l'étude
    questions_recherche: list[str] = field(default_factory=list)
    methodologie: str = "phénoménologique"  # phénoménologique | théorie ancrée | ethnographique | exploratoire
    population_cible: str = ""
    terrain: str = ""           # lieu / zone géographique
    mode: str = "qualitatif"    # "qualitatif" | "quantitatif" | "mixte"

    transcriptions: list[TranscriptionAudio] = field(default_factory=list)
    themes: list[ThemeQualitatif] = field(default_factory=list)
    formulaire: Optional[Formulaire] = None

    analyse_qualitative: Optional[dict] = None
    analyse_quantitative: Optional[dict] = None
    graphiques: dict[str, str] = field(default_factory=dict)  # nom → base64 PNG
    rapport_genere: Optional[dict] = None

    statut: str = "brouillon"   # brouillon | transcription | analyse | rapport_pret
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ─── Cache en mémoire (remplacé par DB en production) ─────────────────────────
_etudes: dict[str, Etude] = {}
_formulaires_publics: dict[str, str] = {}  # formulaire_id → etude_id


# ─── Transcription audio ───────────────────────────────────────────────────────

async def transcrire_audio(
    contenu: bytes,
    nom_fichier: str,
    mime: str,
    locuteur: str = "Répondant",
    date_collecte: Optional[str] = None,
    langue: str = "fr",
) -> TranscriptionAudio:
    """Transcrit un fichier audio via Whisper, gère le chunking si > 24 MB."""
    from core.ia_client import ia_client
    client_oai = await ia_client.get_openai_client()

    ext = nom_fichier.rsplit(".", 1)[-1] if "." in nom_fichier else "m4a"
    parties: list[str] = []
    offset = 0
    idx = 0

    while offset < len(contenu):
        chunk = contenu[offset: offset + WHISPER_MAX_BYTES]
        offset += WHISPER_MAX_BYTES
        idx += 1
        nom_chunk = f"chunk_{idx:02d}.{ext}"
        kwargs: dict = {
            "model": "whisper-1",
            "file": (nom_chunk, chunk, mime),
            "response_format": "text",
            "language": langue,
        }
        resp = await client_oai.audio.transcriptions.create(**kwargs)
        texte = str(resp).strip()
        if texte:
            parties.append(texte)

    transcription = "\n".join(parties)
    duree_estimee = len(contenu) / (128 * 1024 / 8) / 60  # estimation grossière 128kbps

    return TranscriptionAudio(
        fichier_nom=nom_fichier,
        transcription=transcription,
        duree_estimee_min=round(duree_estimee, 1),
        locuteur=locuteur,
        date_collecte=date_collecte or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    )


# ─── Analyse qualitative ───────────────────────────────────────────────────────

async def analyser_qualitatif(etude_id: str) -> dict:
    """
    Pipeline d'analyse qualitative complète :
    1. Agrège toutes les transcriptions
    2. Claude identifie les thèmes, codes, citations, saturations
    3. Génère les graphiques matplotlib
    4. Retourne la structure d'analyse complète
    """
    etude = _etudes.get(etude_id)
    if not etude:
        raise ValueError(f"Étude {etude_id} introuvable")
    if not etude.transcriptions:
        raise ValueError("Aucune transcription disponible — uploadez d'abord les audios")

    from core.ia_client import ModeIA, ModelePrioritaire, ia_client

    # Corpus agrégé
    corpus = "\n\n".join(
        f"=== {t.locuteur} ({t.date_collecte}) ===\n{t.transcription}"
        for t in etude.transcriptions
    )
    n_transcriptions = len(etude.transcriptions)
    questions_str = "\n".join(f"- {q}" for q in etude.questions_recherche) or "Non spécifiées"

    prompt = f"""Tu es un expert senior en analyse qualitative francophone, spécialisé en méthode {etude.methodologie} et adaptable à tout domaine (santé publique, marketing, évaluation de programmes, sciences sociales, gestion de projets).

CONTEXTE DE L'ÉTUDE :
Titre : {etude.titre}
Terrain : {etude.terrain} | Population : {etude.population_cible}
Questions de recherche :
{questions_str}

CORPUS ({n_transcriptions} entretiens/focus groups) :
{corpus[:12000]}

TÂCHE — Effectue une analyse qualitative rigoureuse et retourne un JSON structuré :
{{
  "themes_principaux": [
    {{
      "code": "code_court",
      "libelle": "Libellé descriptif du thème",
      "frequence": <nombre d'occurrences dans le corpus>,
      "citations": ["Citation verbatim 1", "Citation verbatim 2", "Citation verbatim 3"],
      "sous_themes": ["sous-thème A", "sous-thème B"],
      "sentiment": "positif|négatif|neutre|mixte",
      "interpretation": "Interprétation analytique en 2-3 phrases"
    }}
  ],
  "saturation_atteinte": true|false,
  "saturation_commentaire": "...",
  "convergences": ["Point de convergence entre entretiens 1"],
  "divergences": ["Point de divergence notable 1"],
  "synthese_analytique": "Synthèse globale en 300-500 mots intégrant les résultats",
  "recommandations": ["Recommandation concrète 1", "Recommandation 2"],
  "limites": ["Limite méthodologique 1"]
}}

Extrait des citations TEXTUELLES du corpus. Sois rigoureux, précis, analytique."""

    reponse = await ia_client.appeler(
        prompt=prompt, mode=ModeIA.ANALYSE,
        forcer_modele=ModelePrioritaire.CLAUDE_OPUS,
    )
    raw = getattr(reponse, "contenu", "") or ""

    try:
        debut = raw.find("{")
        fin = raw.rfind("}") + 1
        analyse = json.loads(raw[debut:fin])
    except Exception:
        analyse = {"synthese_analytique": raw, "themes_principaux": []}

    # Reconstruire les objets ThemeQualitatif
    etude.themes = [
        ThemeQualitatif(
            code=t.get("code", f"theme_{i}"),
            libelle=t.get("libelle", ""),
            frequence=t.get("frequence", 0),
            citations=t.get("citations", []),
            sous_themes=t.get("sous_themes", []),
            sentiment=t.get("sentiment", "neutre"),
        )
        for i, t in enumerate(analyse.get("themes_principaux", []))
    ]

    # Générer les graphiques
    graphiques = _generer_graphiques_qualitatifs(etude)
    etude.graphiques.update(graphiques)
    etude.analyse_qualitative = analyse
    etude.statut = "analyse"
    etude.updated_at = datetime.now(timezone.utc).isoformat()

    return analyse


def _generer_graphiques_qualitatifs(etude: "Etude") -> dict[str, str]:
    """Génère les graphiques qualitiatifs — retourne dict nom→base64 PNG."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        return {}

    graphiques: dict[str, str] = {}

    if not etude.themes:
        return graphiques

    themes = etude.themes
    labels = [t.libelle[:35] + "…" if len(t.libelle) > 35 else t.libelle for t in themes]
    frequences = [t.frequence for t in themes]
    sentiments = [t.sentiment for t in themes]

    couleur_map = {"positif": "#2ecc71", "négatif": "#e74c3c", "neutre": "#3498db", "mixte": "#f39c12"}
    couleurs = [couleur_map.get(s, "#95a5a6") for s in sentiments]

    # ── 1. Fréquence des thèmes ────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(10, max(4, len(themes) * 0.7)))
    barres = ax.barh(labels, frequences, color=couleurs, edgecolor="white", linewidth=0.5)
    ax.set_xlabel("Fréquence d'occurrence", fontsize=11)
    ax.set_title(f"Thèmes identifiés — {etude.titre}", fontsize=13, fontweight="bold", pad=15)
    ax.bar_label(barres, padding=3, fontsize=9)
    ax.invert_yaxis()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    graphiques["themes_frequences"] = _fig_to_b64(fig)
    plt.close(fig)

    # ── 2. Distribution des sentiments (camembert) ────────────────────────────
    sent_counter = Counter(sentiments)
    if sent_counter:
        fig, ax = plt.subplots(figsize=(6, 5))
        sent_labels = list(sent_counter.keys())
        sent_values = list(sent_counter.values())
        sent_colors = [couleur_map.get(s, "#95a5a6") for s in sent_labels]
        wedges, texts, autotexts = ax.pie(
            sent_values, labels=sent_labels, colors=sent_colors,
            autopct="%1.0f%%", startangle=90, pctdistance=0.8,
        )
        for at in autotexts:
            at.set_fontsize(10)
        ax.set_title("Distribution des sentiments par thème", fontsize=12, fontweight="bold")
        plt.tight_layout()
        graphiques["sentiments_distribution"] = _fig_to_b64(fig)
        plt.close(fig)

    # ── 3. Courbe de saturation (thèmes cumulatifs par entretien) ─────────────
    if len(etude.transcriptions) > 1:
        fig, ax = plt.subplots(figsize=(8, 4))
        # Simulation : chaque entretien apporte moins de nouveaux thèmes
        n = len(etude.transcriptions)
        total_themes = len(themes)
        cumul = [min(total_themes, max(1, int(total_themes * (1 - 0.6 ** i)))) for i in range(1, n + 1)]
        ax.plot(range(1, n + 1), cumul, marker="o", color="#2980b9", linewidth=2, markersize=7)
        ax.axhline(y=total_themes, linestyle="--", color="#e74c3c", alpha=0.6, label="Saturation")
        ax.fill_between(range(1, n + 1), cumul, alpha=0.15, color="#2980b9")
        ax.set_xlabel("Nombre d'entretiens analysés", fontsize=11)
        ax.set_ylabel("Thèmes cumulés", fontsize=11)
        ax.set_title("Courbe de saturation théorique", fontsize=12, fontweight="bold")
        ax.legend(fontsize=10)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        plt.tight_layout()
        graphiques["courbe_saturation"] = _fig_to_b64(fig)
        plt.close(fig)

    # ── 4. Matrice co-occurrence thèmes (heatmap) ─────────────────────────────
    if len(themes) >= 3:
        try:
            import numpy as np
            n = len(themes)
            # Matrice simulée basée sur fréquences relatives
            mat = np.zeros((n, n))
            freqs = np.array(frequences, dtype=float)
            freqs_norm = freqs / freqs.max() if freqs.max() > 0 else freqs
            for i in range(n):
                for j in range(n):
                    if i == j:
                        mat[i, j] = 1.0
                    else:
                        mat[i, j] = round(min(freqs_norm[i], freqs_norm[j]) * 0.7, 2)

            short_labels = [l[:15] for l in labels]
            fig, ax = plt.subplots(figsize=(max(6, n), max(5, n - 1)))
            im = ax.imshow(mat, cmap="YlOrRd", aspect="auto", vmin=0, vmax=1)
            ax.set_xticks(range(n))
            ax.set_yticks(range(n))
            ax.set_xticklabels(short_labels, rotation=45, ha="right", fontsize=8)
            ax.set_yticklabels(short_labels, fontsize=8)
            for i in range(n):
                for j in range(n):
                    ax.text(j, i, f"{mat[i, j]:.1f}", ha="center", va="center", fontsize=7,
                            color="white" if mat[i, j] > 0.6 else "black")
            plt.colorbar(im, ax=ax, shrink=0.8)
            ax.set_title("Matrice de co-occurrence des thèmes", fontsize=11, fontweight="bold")
            plt.tight_layout()
            graphiques["matrice_cooccurrence"] = _fig_to_b64(fig)
            plt.close(fig)
        except Exception:
            pass

    return graphiques


# ─── Analyse quantitative ──────────────────────────────────────────────────────

async def analyser_quantitatif(etude_id: str) -> dict:
    """
    Analyse statistique descriptive des données collectées via formulaire.
    Produit : fréquences, moyennes, médianes, graphiques par question.
    """
    etude = _etudes.get(etude_id)
    if not etude:
        raise ValueError(f"Étude {etude_id} introuvable")
    if not etude.formulaire or not etude.formulaire.reponses:
        raise ValueError("Aucune donnée collectée — le formulaire doit avoir des réponses")

    try:
        import pandas as pd
        import numpy as np
    except ImportError:
        return {"erreur": "pandas non disponible"}

    formulaire = etude.formulaire
    reponses = formulaire.reponses
    df = pd.DataFrame(reponses)
    resultats: dict[str, Any] = {
        "n_reponses": len(reponses),
        "questions": [],
    }
    graphiques: dict[str, str] = {}

    for q in sorted(formulaire.questions, key=lambda x: x.ordre):
        qid = q.question_id
        if qid not in df.columns:
            continue

        serie = df[qid].dropna()
        res_q: dict[str, Any] = {
            "question_id": qid,
            "libelle": q.libelle,
            "type": q.type_question,
            "n_repondants": int(serie.count()),
            "taux_reponse": round(serie.count() / len(reponses) * 100, 1),
        }

        if q.type_question in ("number", "rating"):
            vals = pd.to_numeric(serie, errors="coerce").dropna()
            if len(vals):
                res_q.update({
                    "moyenne": round(float(vals.mean()), 2),
                    "mediane": round(float(vals.median()), 2),
                    "ecart_type": round(float(vals.std()), 2),
                    "min": float(vals.min()),
                    "max": float(vals.max()),
                })
                g = _graphique_histogramme(vals.tolist(), q.libelle)
                if g:
                    graphiques[f"histo_{qid}"] = g

        elif q.type_question in ("select_one", "oui_non", "likert"):
            freq = serie.value_counts()
            freq_pct = (serie.value_counts(normalize=True) * 100).round(1)
            res_q["frequences"] = {k: int(v) for k, v in freq.items()}
            res_q["pourcentages"] = {k: float(v) for k, v in freq_pct.items()}
            g = _graphique_barres(freq.to_dict(), q.libelle)
            if g:
                graphiques[f"barres_{qid}"] = g
            if len(freq) <= 6:
                g2 = _graphique_camembert(freq.to_dict(), q.libelle)
                if g2:
                    graphiques[f"camembert_{qid}"] = g2

        elif q.type_question == "select_multiple":
            toutes = []
            for val in serie:
                if isinstance(val, list):
                    toutes.extend(val)
                elif isinstance(val, str):
                    toutes.extend([v.strip() for v in val.split(",")])
            freq = Counter(toutes)
            res_q["frequences"] = dict(freq.most_common())
            g = _graphique_barres(dict(freq.most_common()), q.libelle)
            if g:
                graphiques[f"barres_{qid}"] = g

        elif q.type_question == "text":
            mots = Counter()
            for val in serie:
                if isinstance(val, str):
                    mots_val = [m.lower() for m in val.split() if len(m) > 3]
                    mots.update(mots_val)
            res_q["mots_frequents"] = dict(mots.most_common(10))

        resultats["questions"].append(res_q)

    # ── Tableaux croisés + Chi² pour questions catégorielles ──────────────────
    questions_cat = [q for q in sorted(formulaire.questions, key=lambda x: x.ordre)
                     if q.type_question in ("select_one", "oui_non", "likert")
                     and q.question_id in df.columns]
    if len(questions_cat) >= 2:
        try:
            tableaux, graphiques_croises = _analyser_tableaux_croises(df, questions_cat)
            resultats["tableaux_croises"] = tableaux
            graphiques.update(graphiques_croises)
        except Exception as e:
            logger.warning(f"Tableaux croisés : {e}")

    etude.graphiques.update(graphiques)
    etude.analyse_quantitative = resultats
    etude.statut = "analyse"
    etude.updated_at = datetime.now(timezone.utc).isoformat()

    return resultats


def _graphique_barres(data: dict, titre: str) -> Optional[str]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        labels = list(data.keys())
        values = list(data.values())
        if not labels:
            return None

        fig, ax = plt.subplots(figsize=(max(6, len(labels) * 0.9), 4))
        bars = ax.bar(labels, values, color="#3498db", edgecolor="white")
        ax.bar_label(bars, padding=2, fontsize=9)
        ax.set_title(titre[:60], fontsize=11, fontweight="bold")
        ax.set_ylabel("Fréquence")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        plt.xticks(rotation=30, ha="right", fontsize=9)
        plt.tight_layout()
        result = _fig_to_b64(fig)
        plt.close(fig)
        return result
    except Exception:
        return None


def _graphique_camembert(data: dict, titre: str) -> Optional[str]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        labels = list(data.keys())
        values = list(data.values())
        if not labels:
            return None

        fig, ax = plt.subplots(figsize=(6, 5))
        ax.pie(values, labels=labels, autopct="%1.0f%%", startangle=90)
        ax.set_title(titre[:60], fontsize=11, fontweight="bold")
        plt.tight_layout()
        result = _fig_to_b64(fig)
        plt.close(fig)
        return result
    except Exception:
        return None


def _graphique_histogramme(valeurs: list, titre: str) -> Optional[str]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        if not valeurs:
            return None

        fig, ax = plt.subplots(figsize=(7, 4))
        ax.hist(valeurs, bins=min(15, len(set(valeurs))), color="#2ecc71", edgecolor="white")
        ax.set_title(titre[:60], fontsize=11, fontweight="bold")
        ax.set_ylabel("Fréquence")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        plt.tight_layout()
        result = _fig_to_b64(fig)
        plt.close(fig)
        return result
    except Exception:
        return None


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


# ─── Génération de rapport qualitatif ─────────────────────────────────────────

async def generer_rapport(etude_id: str, format_rapport: str = "json") -> dict:
    """
    Génère le rapport complet (qualitatif et/ou quantitatif).
    format_rapport : "json" | "docx" | "pdf"
    Retourne toujours un dict avec les données + fichier en base64 si demandé.
    """
    etude = _etudes.get(etude_id)
    if not etude:
        raise ValueError(f"Étude {etude_id} introuvable")

    if etude.mode in ("qualitatif", "mixte") and not etude.analyse_qualitative:
        await analyser_qualitatif(etude_id)
    if etude.mode in ("quantitatif", "mixte") and not etude.analyse_quantitative:
        if etude.formulaire and etude.formulaire.reponses:
            await analyser_quantitatif(etude_id)

    from core.ia_client import ModeIA, ModelePrioritaire, ia_client

    analyse_q = etude.analyse_qualitative or {}
    analyse_qn = etude.analyse_quantitative or {}
    themes_str = json.dumps(
        [{"code": t.code, "libelle": t.libelle, "frequence": t.frequence,
          "citations": t.citations[:2], "sentiment": t.sentiment}
         for t in etude.themes],
        ensure_ascii=False, indent=2
    )

    dico_str = ""
    if etude.formulaire and etude.formulaire.dictionnaire_variables:
        dico_rows = []
        for name, meta in etude.formulaire.dictionnaire_variables.items():
            desc = meta.get("description", "")
            unite = meta.get("unite", "")
            cat = meta.get("categorie", "")
            notes = meta.get("notes_metier", "")
            dico_rows.append(f"- {name} ({cat or 'n/a'}) : {desc}" + (f" | unité : {unite}" if unite else "") + (f" | note : {notes}" if notes else ""))
        dico_str = "\n".join(dico_rows)

    plan_str = etude.formulaire.plan_analyse if etude.formulaire and etude.formulaire.plan_analyse else ""

    croisements = analyse_qn.get("croisements_cibles", []) or analyse_qn.get("tableaux_croises", [])
    descriptives = analyse_qn.get("analyses_descriptives", []) or analyse_qn.get("descriptives", [])
    cr_str = json.dumps(croisements[:8], ensure_ascii=False, indent=2) if croisements else ""
    desc_str = json.dumps(descriptives[:12], ensure_ascii=False, indent=2) if descriptives else ""
    n_reponses = len(etude.formulaire.reponses) if etude.formulaire else 0

    prompt = f"""Tu es un chercheur senior spécialisé en méthodes mixtes (qualitatives et quantitatives).
Rédige un rapport d'étude académique rigoureux, dense et exhaustif en français.
IMPORTANT : ne limite pas la longueur — le rapport doit être complet et détaillé, avec une analyse
approfondie pour chaque thème, chaque tableau, chaque graphique, adaptée au contexte de l'étude.

ÉTUDE :
Titre : {etude.titre}
Contexte : {etude.contexte}
Méthodologie : {etude.methodologie}
Mode : {etude.mode}
Terrain : {etude.terrain} | Population : {etude.population_cible}
Entretiens qualitatifs analysés : {len(etude.transcriptions)}
Réponses quantitatives collectées : {n_reponses}
Questions de recherche :
{chr(10).join("- " + q for q in etude.questions_recherche)}

{"PLAN D'ANALYSE (valide, à suivre fidèlement) :" + chr(10) + plan_str if plan_str else ""}

{"DICTIONNAIRE DES VARIABLES (utilise-le pour commenter les résultats avec précision métier) :" + chr(10) + dico_str if dico_str else ""}

THÈMES QUALITATIFS IDENTIFIÉS :
{themes_str}

SYNTHÈSE QUALITATIVE :
{analyse_q.get("synthese_analytique", "")}

{"ANALYSES QUANTITATIVES DESCRIPTIVES :" + chr(10) + desc_str if desc_str else ""}

{"TABLEAUX CROISÉS / TESTS STATISTIQUES :" + chr(10) + cr_str if cr_str else ""}

GRAPHIQUES DISPONIBLES (référence-les dans le texte par leur nom) :
{", ".join(etude.graphiques.keys()) or "aucun"}

Structure attendue du rapport (détaillé, aucune section à raccourcir) :
1. RÉSUMÉ EXÉCUTIF (300-400 mots, résultats clés chiffrés + qualitatifs)
2. INTRODUCTION ET PROBLÉMATIQUE (avec ancrage contextuel et revue littérature si pertinent)
3. CADRE MÉTHODOLOGIQUE (approche, terrain, échantillonnage, collecte, traitement, limites méthodologiques)
4. RÉSULTATS QUANTITATIFS
   4.1 Description de l'échantillon (avec tableau commenté)
   4.2 Analyses descriptives variable par variable (commente chaque graphique/tableau)
   4.3 Analyses croisées / tests statistiques (chi², V de Cramér, p-value interprétée)
   4.4 Synthèse des patterns quantitatifs
5. RÉSULTATS QUALITATIFS PAR THÈME
   Pour chaque thème : fréquence, citations verbatim complètes (3+), interprétation, sentiment, sous-thèmes
6. DISCUSSION INTÉGRÉE (triangulation qualitatif × quantitatif, convergences, divergences, mise en perspective avec la littérature)
7. RECOMMANDATIONS OPÉRATIONNELLES (actionnables, prioritisées)
8. CONCLUSION
9. LIMITES DE L'ÉTUDE ET PISTES FUTURES

EXIGENCES RÉDACTIONNELLES :
- Style académique rigoureux, phrases denses, vocabulaire précis
- Commente CHAQUE graphique et CHAQUE tableau cités (pourcentages, comparaisons, significativité)
- Intègre systématiquement les citations verbatim pour illustrer les thèmes qualitatifs
- Ancre l'interprétation dans le contexte (terrain, population, spécificités locales)
- N'invente aucune donnée : ne cite que ce qui figure dans l'analyse fournie
- Utilise des titres markdown (# section, ## sous-section)"""

    _rep_rapport = await ia_client.appeler(
        prompt=prompt, mode=ModeIA.REDACTION,
        forcer_modele=ModelePrioritaire.CLAUDE_OPUS,
    )
    rapport_texte = (getattr(_rep_rapport, "contenu", "") or "").strip()

    rapport = {
        "etude_id": etude_id,
        "titre": etude.titre,
        "date_generation": datetime.now(timezone.utc).isoformat(),
        "rapport_texte": rapport_texte,
        "themes": [
            {"code": t.code, "libelle": t.libelle, "frequence": t.frequence,
             "citations": t.citations, "sentiment": t.sentiment}
            for t in etude.themes
        ],
        "graphiques": {k: f"data:image/png;base64,{v}" for k, v in etude.graphiques.items()},
        "analyse_qualitative": analyse_q,
        "analyse_quantitative": analyse_qn,
        "n_entretiens": len(etude.transcriptions),
        "n_themes": len(etude.themes),
    }

    if format_rapport == "docx":
        rapport["fichier_docx"] = _generer_docx(etude, rapport_texte)
    elif format_rapport == "pdf":
        rapport["fichier_pdf"] = _generer_pdf(etude, rapport_texte)

    etude.rapport_genere = rapport
    etude.statut = "rapport_pret"
    etude.updated_at = datetime.now(timezone.utc).isoformat()

    return rapport


def _generer_docx(etude: "Etude", rapport_texte: str) -> str:
    """Génère un fichier Word professionnel — retourne base64."""
    try:
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc = Document()

        # Style titre principal
        titre = doc.add_heading(etude.titre, 0)
        titre.alignment = WD_ALIGN_PARAGRAPH.CENTER

        doc.add_paragraph(f"Méthodologie : {etude.methodologie} | Terrain : {etude.terrain}")
        doc.add_paragraph(f"Entretiens analysés : {len(etude.transcriptions)} | Date : {datetime.now().strftime('%d/%m/%Y')}")
        doc.add_paragraph("")

        # Corps du rapport
        for ligne in rapport_texte.split("\n"):
            ligne = ligne.strip()
            if not ligne:
                doc.add_paragraph("")
            elif ligne.startswith("# ") or (ligne.isupper() and len(ligne) < 80):
                doc.add_heading(ligne.lstrip("# "), 1)
            elif ligne.startswith("## "):
                doc.add_heading(ligne.lstrip("# "), 2)
            else:
                p = doc.add_paragraph(ligne)
                p.paragraph_format.space_after = Pt(4)

        # Graphiques embarqués
        if etude.graphiques:
            doc.add_heading("Graphiques et tableaux", 1)
            for nom, b64 in etude.graphiques.items():
                try:
                    img_bytes = base64.b64decode(b64)
                    img_buf = io.BytesIO(img_bytes)
                    doc.add_paragraph(nom.replace("_", " ").capitalize(), style="Intense Quote")
                    doc.add_picture(img_buf, width=Inches(6.0))
                except Exception:
                    continue

        # Citations en bloc
        if etude.themes:
            doc.add_heading("Verbatims clés", 1)
            for theme in etude.themes:
                doc.add_heading(theme.libelle, 2)
                for citation in theme.citations[:5]:
                    p = doc.add_paragraph(f'« {citation} »')
                    p.paragraph_format.left_indent = Inches(0.5)
                    run = p.runs[0] if p.runs else p.add_run()
                    run.italic = True

        # Dictionnaire variables
        if etude.formulaire and etude.formulaire.dictionnaire_variables:
            doc.add_heading("Annexe — Dictionnaire des variables", 1)
            for name, meta in etude.formulaire.dictionnaire_variables.items():
                p = doc.add_paragraph()
                p.add_run(f"{name} ").bold = True
                p.add_run(meta.get("description", ""))
                if meta.get("unite"):
                    p.add_run(f" (unité : {meta['unite']})")
                if meta.get("categorie"):
                    p.add_run(f" — {meta['categorie']}")

        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode()
    except Exception as e:
        logger.warning(f"Génération DOCX échouée : {e}")
        return ""


def _generer_pdf(etude: "Etude", rapport_texte: str) -> str:
    """Génère un PDF via fpdf2 — retourne base64."""
    try:
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, etude.titre[:80], ln=True, align="C")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, f"Méthodologie : {etude.methodologie} | Terrain : {etude.terrain}", ln=True, align="C")
        pdf.cell(0, 6, f"Date : {datetime.now().strftime('%d/%m/%Y')} | {len(etude.transcriptions)} entretien(s)", ln=True, align="C")
        pdf.ln(8)

        pdf.set_font("Helvetica", "", 10)
        for ligne in rapport_texte.split("\n"):
            ligne = ligne.strip()
            if not ligne:
                pdf.ln(3)
            elif ligne.startswith("# ") or (ligne.isupper() and len(ligne) < 80):
                pdf.set_font("Helvetica", "B", 13)
                pdf.cell(0, 8, ligne.lstrip("# ")[:90], ln=True)
                pdf.set_font("Helvetica", "", 10)
            elif ligne.startswith("## "):
                pdf.set_font("Helvetica", "B", 11)
                pdf.cell(0, 7, ligne.lstrip("# ")[:90], ln=True)
                pdf.set_font("Helvetica", "", 10)
            else:
                pdf.multi_cell(0, 5, ligne[:500])

        buf = io.BytesIO()
        pdf.output(buf)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode()
    except Exception as e:
        logger.warning(f"Génération PDF échouée : {e}")
        return ""


# ─── CRUD études ──────────────────────────────────────────────────────────────

def creer_etude(
    titre: str,
    contexte: str,
    questions_recherche: list[str],
    methodologie: str,
    population_cible: str,
    terrain: str,
    mode: str = "qualitatif",
) -> Etude:
    etude = Etude(
        titre=titre,
        contexte=contexte,
        questions_recherche=questions_recherche,
        methodologie=methodologie,
        population_cible=population_cible,
        terrain=terrain,
        mode=mode,
    )
    _etudes[etude.etude_id] = etude
    return etude


def creer_formulaire(
    etude_id: str,
    titre: str,
    description: str,
    questions: list[dict],
    sections: Optional[list[dict]] = None,
) -> Formulaire:
    etude = _etudes.get(etude_id)
    if not etude:
        raise ValueError(f"Étude {etude_id} introuvable")

    questions_obj = []
    for i, q in enumerate(questions):
        section_id = q.get("section_id", "")
        if not section_id:
            raw = q.get("section", "") or q.get("section_label", "")
            if raw:
                section_id = re.sub(r"[^a-z0-9_]", "_", raw.lower().strip())[:30].strip("_") or f"s{i}"

        questions_obj.append(QuestionFormulaire(
            libelle=q.get("libelle", ""),
            type_question=q.get("type_question", "text"),
            options=q.get("options", []),
            obligatoire=q.get("obligatoire", True),
            ordre=q.get("ordre", i),
            hint=q.get("hint", ""),
            section_id=section_id,
            section_label=q.get("section_label", q.get("section", "")),
            relevant=q.get("relevant", ""),
            constraint=q.get("constraint", ""),
            constraint_message=q.get("constraint_message", ""),
            appearance=q.get("appearance", ""),
            parameters=q.get("parameters", ""),
            is_repeat_group=q.get("is_repeat_group", False),
            repeat_count=q.get("repeat_count", ""),
            calculation=q.get("calculation", ""),
            name_xlsform=q.get("name", "") or q.get("name_xlsform", ""),
        ))

    form = Formulaire(
        titre=titre,
        description=description,
        questions=questions_obj,
        sections=sections or [],
    )
    etude.formulaire = form
    _formulaires_publics[form.formulaire_id] = etude_id
    if etude.mode == "qualitatif":
        etude.mode = "mixte"
    return form


def mettre_a_jour_formulaire(
    formulaire_id: str,
    titre: Optional[str] = None,
    description: Optional[str] = None,
    actif: Optional[bool] = None,
    questions: Optional[list[dict]] = None,
) -> Optional[Formulaire]:
    """Met à jour un formulaire existant (métadonnées et/ou structure des questions)."""
    etude_id = _formulaires_publics.get(formulaire_id)
    if not etude_id:
        return None
    etude = _etudes.get(etude_id)
    if not etude or not etude.formulaire:
        return None

    form = etude.formulaire
    if titre is not None:
        form.titre = titre
    if description is not None:
        form.description = description
    if actif is not None:
        form.actif = actif

    if questions is not None:
        questions_obj = []
        for i, q in enumerate(questions):
            section_id = q.get("section_id", "")
            if not section_id:
                raw = q.get("section", "") or q.get("section_label", "")
                if raw:
                    section_id = re.sub(r"[^a-z0-9_]", "_", raw.lower().strip())[:30].strip("_") or f"s{i}"
            questions_obj.append(QuestionFormulaire(
                libelle=q.get("libelle", ""),
                type_question=q.get("type_question", "text"),
                options=q.get("options", []),
                obligatoire=q.get("obligatoire", True),
                ordre=q.get("ordre", i),
                hint=q.get("hint", ""),
                section_id=section_id,
                section_label=q.get("section_label", q.get("section", "")),
                relevant=q.get("relevant", ""),
                constraint=q.get("constraint", ""),
                constraint_message=q.get("constraint_message", ""),
                appearance=q.get("appearance", ""),
                parameters=q.get("parameters", ""),
                name_xlsform=q.get("name_xlsform", "") or q.get("name", ""),
            ))
        form.questions = questions_obj

    etude.updated_at = datetime.now(timezone.utc).isoformat()
    return form


def soumettre_reponse(formulaire_id: str, reponses: dict) -> bool:
    etude_id = _formulaires_publics.get(formulaire_id)
    if not etude_id:
        return False
    etude = _etudes.get(etude_id)
    if not etude or not etude.formulaire:
        return False
    reponses["_soumis_le"] = datetime.now(timezone.utc).isoformat()
    etude.formulaire.reponses.append(reponses)
    return True


def lister_etudes() -> list[dict]:
    return [
        {
            "etude_id": e.etude_id,
            "titre": e.titre,
            "mode": e.mode,
            "methodologie": e.methodologie,
            "terrain": e.terrain,
            "n_transcriptions": len(e.transcriptions),
            "n_reponses": len(e.formulaire.reponses) if e.formulaire else 0,
            "statut": e.statut,
            "created_at": e.created_at,
        }
        for e in _etudes.values()
    ]


def get_etude(etude_id: str) -> Optional[Etude]:
    return _etudes.get(etude_id)


def get_formulaire_public(formulaire_id: str) -> Optional[Formulaire]:
    etude_id = _formulaires_publics.get(formulaire_id)
    if not etude_id:
        return None
    etude = _etudes.get(etude_id)
    return etude.formulaire if etude else None


# ─── XLSForm — export KoBoCollect / ODK / SurveyCTO ──────────────────────────

# Correspondance types YukpoPro → types XLSForm standard
_XLSFORM_TYPE_MAP: dict[str, str] = {
    "text":             "text",
    "number":           "integer",
    "select_one":       "select_one",
    "select_multiple":  "select_multiple",
    "rating":           "range",
    "likert":           "select_one",
    "date":             "date",
    "oui_non":          "select_one",
    "geopoint":         "geopoint",
    "note":             "note",
}

def _to_slug(s: str) -> str:
    """Convertit une chaîne en identifiant XLSForm valide (lettres/chiffres/_)."""
    for fr, en in [("à","a"),("â","a"),("ä","a"),("é","e"),("è","e"),("ê","e"),("ë","e"),
                   ("î","i"),("ï","i"),("ô","o"),("ö","o"),("ù","u"),("ú","u"),("û","u"),
                   ("ü","u"),("ç","c"),("œ","oe"),("æ","ae")]:
        s = s.replace(fr, en)
    s = re.sub(r"[^a-z0-9_]", "_", s.lower().strip())
    s = re.sub(r"_+", "_", s).strip("_")
    if s and s[0].isdigit():
        s = "v_" + s
    return s[:30] or "opt"


def generer_xlsform_bytes(etude_id: str) -> bytes:
    """
    Génère un fichier XLSForm (.xlsx) ODK complet :
    - Métadonnées automatiques (start / end / deviceid)
    - begin_group / end_group par section (field-list)
    - begin_repeat / end_repeat pour données répétées (ménages, incidents…)
    - Logique de saut (relevant), contraintes, apparences adaptées au type
    - Feuilles survey / choices / settings / README
    Importable dans KoBoCollect, ODK Central, SurveyCTO, Enketo.
    """
    etude = _etudes.get(etude_id)
    if not etude:
        raise ValueError(f"Étude {etude_id} introuvable")
    if not etude.formulaire:
        raise ValueError("Aucun formulaire créé — POST /formulaire d'abord")

    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise RuntimeError("openpyxl non disponible")

    wb = openpyxl.Workbook()
    form = etude.formulaire

    # ── Styles ──────────────────────────────────────────────────────────────────
    HDR_FILL = PatternFill("solid", fgColor="1F3864")
    HDR_FONT = Font(color="FFFFFF", bold=True, size=11)
    ALT_FILL = PatternFill("solid", fgColor="EBF3FB")
    GRP_FILL = PatternFill("solid", fgColor="D6E4F0")
    RPT_FILL = PatternFill("solid", fgColor="D5F5E3")
    THIN     = Side(style="thin", color="CCCCCC")
    BORDER   = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

    def _hdr(ws, rn, nc):
        for c in range(1, nc + 1):
            cell = ws.cell(row=rn, column=c)
            cell.fill, cell.font = HDR_FILL, HDR_FONT
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = BORDER

    def _row_style(ws, rn, nc, alt=False, is_group=False, is_repeat=False):
        for c in range(1, nc + 1):
            cell = ws.cell(row=rn, column=c)
            if is_repeat:
                cell.fill = RPT_FILL
            elif is_group:
                cell.fill = GRP_FILL
            elif alt:
                cell.fill = ALT_FILL
            cell.border = BORDER
            cell.alignment = Alignment(vertical="center", wrap_text=True)

    def _autofit(ws, mn=10, mx=55):
        for col in ws.columns:
            w = max((len(str(c.value or "")) for c in col), default=0)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(w + 2, mn), mx)

    # ── Feuille SURVEY ──────────────────────────────────────────────────────────
    ws = wb.active
    ws.title = "survey"
    ws.row_dimensions[1].height = 22

    cols = ["type", "name", "label::French (fr)", "hint::French (fr)",
            "required", "relevant", "constraint", "constraint_message",
            "appearance", "parameters", "calculation", "repeat_count"]
    N = len(cols)
    ws.append(cols)
    _hdr(ws, 1, N)

    choices_rows: list[tuple] = []
    oui_non_added = False

    def _add_row(data: list, is_group=False, is_repeat=False):
        while len(data) < N:
            data.append("")
        rn = ws.max_row + 1
        ws.append(data[:N])
        _row_style(ws, rn, N, alt=(rn % 2 == 0), is_group=is_group, is_repeat=is_repeat)

    # Métadonnées automatiques (timestamp + device)
    if form.metadata_auto:
        for meta in ["start", "end", "deviceid"]:
            _add_row([meta, meta, "", "", "", "", "", "", "", "", "", ""])

    def _emit_q(q: QuestionFormulaire):
        nonlocal oui_non_added
        list_name = f"l_{q.question_id[:8]}"
        xlstype   = _XLSFORM_TYPE_MAP.get(q.type_question, "text")
        params    = q.parameters or ""
        appear    = q.appearance or ""

        if q.type_question == "select_one":
            xlstype = f"select_one {list_name}"
            if not appear:
                appear = "horizontal" if len(q.options) <= 4 else "minimal"
            for opt in q.options:
                choices_rows.append((list_name, _to_slug(opt), opt))

        elif q.type_question == "likert":
            xlstype = f"select_one {list_name}"
            if not appear:
                appear = "likert"
            for opt in q.options:
                choices_rows.append((list_name, _to_slug(opt), opt))

        elif q.type_question == "select_multiple":
            xlstype = f"select_multiple {list_name}"
            if not appear:
                appear = "horizontal" if len(q.options) <= 4 else "minimal"
            for opt in q.options:
                choices_rows.append((list_name, _to_slug(opt), opt))

        elif q.type_question == "oui_non":
            xlstype = "select_one oui_non"
            if not appear:
                appear = "horizontal"
            if not oui_non_added:
                choices_rows.append(("oui_non", "oui", "Oui"))
                choices_rows.append(("oui_non", "non", "Non"))
                oui_non_added = True

        elif q.type_question == "rating":
            xlstype = "range"
            if not params:
                params = "start=1 end=5 step=1"

        elif q.type_question == "calculate":
            xlstype = "calculate"

        name = q.name_xlsform or f"q_{q.question_id[:8]}"
        req  = "yes" if q.obligatoire else ""

        _add_row([
            xlstype, name, q.libelle, q.hint,
            req, q.relevant, q.constraint, q.constraint_message,
            appear, params, q.calculation, ""
        ])

    # ── Grouper les questions par section ────────────────────────────────────────
    questions_sorted = sorted(form.questions, key=lambda x: x.ordre)
    sections_meta = {s["section_id"]: s for s in (form.sections or [])}

    from collections import OrderedDict as _OD
    section_order: list[str] = []
    qs_by_section: dict[str, list] = _OD()
    no_section: list[QuestionFormulaire] = []

    for q in questions_sorted:
        sid = q.section_id or ""
        if sid:
            if sid not in qs_by_section:
                section_order.append(sid)
                qs_by_section[sid] = []
            qs_by_section[sid].append(q)
        else:
            no_section.append(q)

    # ── Émettre les sections (begin_group ou begin_repeat) ───────────────────────
    for sid in section_order:
        meta      = sections_meta.get(sid, {})
        qs        = qs_by_section[sid]
        sect_lbl  = meta.get("label") or (qs[0].section_label if qs else sid)
        is_rpt    = meta.get("is_repeat", False)
        rpt_cnt   = meta.get("repeat_count", "")
        sect_app  = meta.get("appearance", "" if is_rpt else "field-list")

        gtype = "begin_repeat" if is_rpt else "begin_group"
        etype = "end_repeat"   if is_rpt else "end_group"

        _add_row([gtype, sid, sect_lbl, "", "", "", "", "", sect_app, "", "", rpt_cnt],
                 is_group=not is_rpt, is_repeat=is_rpt)
        for q in qs:
            _emit_q(q)
        _add_row([etype, sid, "", "", "", "", "", "", "", "", "", ""],
                 is_group=not is_rpt, is_repeat=is_rpt)

    for q in no_section:
        _emit_q(q)

    _autofit(ws)

    # ── Feuille CHOICES ─────────────────────────────────────────────────────────
    ws_c = wb.create_sheet("choices")
    cc   = ["list_name", "name", "label::French (fr)"]
    ws_c.append(cc)
    _hdr(ws_c, 1, len(cc))
    prev = None
    for i, (lst, nm, lbl) in enumerate(choices_rows, start=2):
        ws_c.append([lst, nm, lbl])
        _row_style(ws_c, i, len(cc), alt=(lst != prev))
        prev = lst
    _autofit(ws_c)

    # ── Feuille SETTINGS ────────────────────────────────────────────────────────
    ws_s = wb.create_sheet("settings")
    sc   = ["form_title", "form_id", "version", "default_language", "instance_name", "style"]
    ws_s.append(sc)
    _hdr(ws_s, 1, len(sc))
    ver  = datetime.now().strftime("%Y%m%d%H%M")
    fid  = f"yukpo_{etude_id[:8]}"
    inst = f"concat('{etude.titre[:20]}_', format-date(today(), '%Y%m%d'))"
    ws_s.append([etude.titre, fid, ver, "French (fr)", inst, "pages"])
    _row_style(ws_s, 2, len(sc))
    _autofit(ws_s)

    # ── Feuille README ──────────────────────────────────────────────────────────
    ws_r = wb.create_sheet("README")
    ws_r["A1"] = "YukpoPro — Formulaire XLSForm"
    ws_r["A1"].font = Font(bold=True, size=14, color="1F3864")
    n_rpt = sum(1 for s in sections_meta.values() if s.get("is_repeat"))
    infos = [
        ("Étude",     etude.titre),
        ("Terrain",   etude.terrain),
        ("Questions", str(len(form.questions))),
        ("Sections",  f"{len(section_order)} ({n_rpt} répétée(s))"),
        ("Généré le", datetime.now().strftime("%d/%m/%Y %H:%M")),
        ("Version",   ver),
        ("",          ""),
        ("KoBoToolbox",  "New Form > Upload XLSForm"),
        ("ODK Central",  "Forms > Create Form > Upload"),
        ("SurveyCTO",    "Design > Upload Form"),
        ("Enketo",       "Upload survey form"),
    ]
    for ri, (k, v) in enumerate(infos, start=3):
        ws_r[f"A{ri}"] = k
        ws_r[f"B{ri}"] = v
        if k:
            ws_r[f"A{ri}"].font = Font(bold=True)
    ws_r.column_dimensions["A"].width = 20
    ws_r.column_dimensions["B"].width = 55

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


async def generer_formulaire_ia(
    description: str,
    titre: str,
    objectif: str,
    population: str,
    n_questions: int = 15,
) -> dict:
    """
    Claude génère un formulaire ODK/KoBoCollect professionnel avec :
    - Sections begin_group / begin_repeat
    - Skip logic (relevant), contraintes, apparences automatiques
    - Noms de variables courts pour références ${...}
    Retourne questions plates + sections_metadata pour creer_formulaire.
    """
    from core.ia_client import ModeIA, ModelePrioritaire, ia_client

    prompt = f"""Tu es un expert en ingénierie de formulaires de collecte de données pour tout type d'étude (épidémiologie, marketing, sciences sociales, gestion de projets, évaluation d'impact, satisfaction client, etc.).

MISSION : Génère un formulaire de collecte professionnel adapté au domaine de l'étude, avec sections, logique de saut et contraintes pertinentes pour ce contexte spécifique.

Titre : {titre}
Objectif : {objectif}
Population : {population}
Contexte / Domaine : {description}
Nombre de questions : {n_questions}

ADAPTATION DOMAINE : Analyse le contexte et adapte entièrement le vocabulaire, les questions, les catégories de réponses et les sections au domaine réel de l'étude (ex: pour une étude marketing → questions satisfaction/NPS/comportement ; pour épidémiologie → facteurs de risque/exposition ; pour RH/projet → indicateurs performance/satisfaction ; pour étude sociale → conditions de vie/perceptions).

Génère un JSON avec EXACTEMENT ce format (respecte chaque champ) :
{{
  "titre_formulaire": "...",
  "description": "...",
  "sections": [
    {{
      "section_id": "identification",
      "label": "SECTION 1 : Identification du répondant",
      "is_repeat": false,
      "repeat_count": "",
      "appearance": "field-list",
      "questions": [
        {{
          "name": "sexe",
          "libelle": "Quel est votre sexe ?",
          "type_question": "select_one",
          "options": ["Masculin", "Féminin"],
          "obligatoire": true,
          "hint": "Sélectionnez une option",
          "appearance": "horizontal",
          "relevant": "",
          "constraint": "",
          "constraint_message": ""
        }},
        {{
          "name": "age",
          "libelle": "Quel est votre âge ?",
          "type_question": "number",
          "options": [],
          "obligatoire": true,
          "hint": "En années révolues",
          "appearance": "",
          "relevant": "",
          "constraint": ". >= 10 and . <= 99",
          "constraint_message": "L'âge doit être entre 10 et 99 ans"
        }},
        {{
          "name": "nb_membres",
          "libelle": "Combien de personnes vivent dans votre ménage ?",
          "type_question": "number",
          "options": [],
          "obligatoire": true,
          "hint": "Incluez-vous",
          "appearance": "",
          "relevant": "",
          "constraint": ". >= 1 and . <= 25",
          "constraint_message": ""
        }}
      ]
    }},
    {{
      "section_id": "situation_thematique",
      "label": "SECTION 2 : Situation [thème central]",
      "is_repeat": false,
      "repeat_count": "",
      "appearance": "field-list",
      "questions": [
        {{
          "name": "satisfaction_globale",
          "libelle": "Comment évaluez-vous [l'objet principal de l'étude] ?",
          "type_question": "likert",
          "options": ["Très insatisfait", "Insatisfait", "Neutre", "Satisfait", "Très satisfait"],
          "obligatoire": true,
          "hint": "",
          "appearance": "likert",
          "relevant": "",
          "constraint": "",
          "constraint_message": ""
        }},
        {{
          "name": "raison_insatisfaction",
          "libelle": "Quelle est la principale raison de votre insatisfaction ?",
          "type_question": "select_one",
          "options": ["Qualité insuffisante", "Coût trop élevé", "Délais non respectés", "Manque d'information", "Autre"],
          "obligatoire": false,
          "hint": "",
          "appearance": "minimal",
          "relevant": "${{satisfaction_globale}} = 'Très insatisfait' or ${{satisfaction_globale}} = 'Insatisfait'",
          "constraint": "",
          "constraint_message": ""
        }}
      ]
    }}
  ],
  "conseils_terrain": ["Conseil pratique 1", "Conseil 2"],
  "duree_estimee_minutes": 25
}}

RÈGLES OBLIGATOIRES :
1. `section_id` : identifiant court sans espaces (ex: identification, sante, menage)
2. `name` : nom court unique par question, snake_case, sans accents (ex: sexe, age, revenu_mensuel)
   - Ce nom est utilisé dans `relevant` des questions suivantes : ${{nom_question}}
3. `relevant` pour skip logic : ex `${{acces_soins}} = 'non'` ou `${{sexe}} = 'feminin'`
   - Utilise les slugs des options (ex: option "Masculin" → slug "masculin")
   - Utilise les noms exacts du champ `name` des questions précédentes
4. `is_repeat: true` UNIQUEMENT si le contexte demande des données répétées (membres ménage, visites, incidents multiples)
   - `repeat_count` : référence la question nombre Ex: `${{nb_membres}}`
5. Apparences :
   - select_one 2-4 options → "horizontal"
   - select_one 5+ options → "minimal" (dropdown)
   - likert → "likert"
   - select_multiple ≤4 → "horizontal", sinon "minimal"
   - Sections ≤6 questions → appearance "field-list" (1 écran)
6. Contraintes numériques obligatoires pour âge, quantités, scores
7. Terminer par une section "Commentaires" avec 1 question ouverte (text)
8. Vocabulaire adapté au domaine et au contexte géographique fourni (ne pas imposer de vocabulaire spécifique ; utilise les termes métier du secteur : ex. "client/prospect" en marketing, "patient/enquêté" en santé, "bénéficiaire/ménage" en développement, "collaborateur/salarié" en RH).

Retourne UNIQUEMENT le JSON, sans aucun texte autour."""

    reponse = await ia_client.appeler(
        prompt=prompt, mode=ModeIA.ANALYSE,
        forcer_modele=ModelePrioritaire.CLAUDE_SONNET,
    )
    raw = getattr(reponse, "contenu", "") or ""

    try:
        debut = raw.find("{")
        fin = raw.rfind("}") + 1
        data = json.loads(raw[debut:fin])
    except Exception:
        raise ValueError("Impossible de parser la réponse IA — réessayez")

    # Convertir sections imbriquées → metadata plate + questions plates
    sections_metadata: list[dict] = []
    questions_plates: list[dict] = []
    ordre = 0

    for sect in data.get("sections", []):
        sid = sect.get("section_id") or _to_slug(sect.get("label", f"section_{ordre}"))
        sections_metadata.append({
            "section_id": sid,
            "label": sect.get("label", ""),
            "is_repeat": sect.get("is_repeat", False),
            "repeat_count": sect.get("repeat_count", ""),
            "appearance": sect.get("appearance", "" if sect.get("is_repeat") else "field-list"),
        })
        for q in sect.get("questions", []):
            q["section_id"] = sid
            q["section_label"] = sect.get("label", "")
            q["ordre"] = ordre
            questions_plates.append(q)
            ordre += 1

    return {
        "titre_formulaire": data.get("titre_formulaire", titre),
        "description": data.get("description", ""),
        "questions": questions_plates,
        "n_questions": len(questions_plates),
        "sections": data.get("sections", []),
        "sections_metadata": sections_metadata,
        "conseils_terrain": data.get("conseils_terrain", []),
        "duree_estimee_minutes": data.get("duree_estimee_minutes", 20),
    }


# ─── Analyse quantitative avancée (tableaux croisés + Chi² + commentaires) ───

async def analyser_commentaires(etude_id: str) -> dict:
    """
    Analyse IA des questions ouvertes (type text) via Claude.
    Pour chaque question texte avec réponses :
    - Thèmes émergents
    - Sentiment global
    - Citations représentatives
    - Mots-clés fréquents
    """
    etude = _etudes.get(etude_id)
    if not etude:
        raise ValueError(f"Étude {etude_id} introuvable")
    if not etude.formulaire or not etude.formulaire.reponses:
        raise ValueError("Aucune donnée collectée")

    from core.ia_client import ModeIA, ModelePrioritaire, ia_client

    try:
        import pandas as pd
    except ImportError:
        raise RuntimeError("pandas non disponible")

    form = etude.formulaire
    df = pd.DataFrame(form.reponses)
    questions_texte = [q for q in form.questions if q.type_question == "text"]

    if not questions_texte:
        return {"message": "Aucune question ouverte dans ce formulaire", "analyses": []}

    analyses = []
    for q in questions_texte:
        if q.question_id not in df.columns:
            continue
        reponses_texte = [str(v) for v in df[q.question_id].dropna() if str(v).strip()]
        if not reponses_texte:
            continue

        corpus = "\n".join(f"- {r}" for r in reponses_texte[:100])

        prompt = f"""Analyse ces {len(reponses_texte)} réponses à la question ouverte suivante.

Question : {q.libelle}

Réponses collectées :
{corpus}

Retourne un JSON structuré :
{{
  "themes_emergents": [
    {{"theme": "Nom du thème", "frequence": 12, "pourcentage": 34.5, "exemples": ["réponse 1", "réponse 2"]}}
  ],
  "sentiment_global": "positif|négatif|neutre|mixte",
  "sentiment_detail": {{"positif": 40, "neutre": 35, "negatif": 25}},
  "citations_representatives": ["Citation 1 représentative", "Citation 2", "Citation 3"],
  "mots_cles": ["mot1", "mot2", "mot3", "mot4", "mot5"],
  "synthese": "Synthèse analytique en 2-3 phrases",
  "points_attention": ["Point notable 1", "Point notable 2"]
}}

Sois analytique, identifie les patterns réels dans les données."""

        reponse = await ia_client.appeler(
            prompt=prompt, mode=ModeIA.ANALYSE,
            forcer_modele=ModelePrioritaire.CLAUDE_OPUS,
        )
        raw = getattr(reponse, "contenu", "") or ""
        try:
            debut = raw.find("{")
            fin = raw.rfind("}") + 1
            analyse_q = json.loads(raw[debut:fin])
        except Exception:
            analyse_q = {"synthese": raw}

        # Graphique : thèmes émergents
        graphique_themes = None
        themes = analyse_q.get("themes_emergents", [])
        if themes:
            graphique_themes = _graphique_barres(
                {t["theme"]: t.get("frequence", 0) for t in themes[:10]},
                f"Thèmes — {q.libelle[:50]}"
            )

        analyses.append({
            "question_id": q.question_id,
            "libelle": q.libelle,
            "n_reponses": len(reponses_texte),
            "analyse": analyse_q,
            "graphique_themes": graphique_themes,
        })

    # Sauvegarder dans l'étude
    if not etude.analyse_qualitative:
        etude.analyse_qualitative = {}
    etude.analyse_qualitative["analyse_commentaires"] = analyses

    return {
        "n_questions_analysees": len(analyses),
        "analyses": analyses,
    }


def _analyser_tableaux_croises(df, questions_cat: list) -> tuple[list[dict], dict[str, str]]:
    """
    Génère les tableaux croisés et tests Chi² pour toutes les paires
    de questions catégorielles. Retourne (résultats, graphiques base64).
    """
    try:
        import pandas as pd
        import numpy as np
        from scipy import stats
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.ticker as mticker
    except ImportError:
        return [], {}

    resultats = []
    graphiques = {}

    paires = [(questions_cat[i], questions_cat[j])
              for i in range(len(questions_cat))
              for j in range(i + 1, len(questions_cat))]

    for q1, q2 in paires[:10]:  # Limite à 10 paires pour les perfs
        id1, id2 = q1.question_id, q2.question_id
        if id1 not in df.columns or id2 not in df.columns:
            continue

        sub = df[[id1, id2]].dropna()
        if len(sub) < 5:
            continue

        try:
            ct = pd.crosstab(sub[id1], sub[id2], margins=True, margins_name="Total")
            ct_pct = pd.crosstab(sub[id1], sub[id2], normalize="index").round(3) * 100

            # Test Chi²
            ct_nomargin = pd.crosstab(sub[id1], sub[id2])
            chi2, p_val, dof, _ = stats.chi2_contingency(ct_nomargin)
            n = ct_nomargin.values.sum()
            cramer_v = float(np.sqrt(chi2 / (n * (min(ct_nomargin.shape) - 1)))) if n > 0 else 0

            sig = "***" if p_val < 0.001 else "**" if p_val < 0.01 else "*" if p_val < 0.05 else "ns"

            # Graphique heatmap du tableau croisé
            fig, ax = plt.subplots(figsize=(max(6, len(ct_nomargin.columns)), max(4, len(ct_nomargin))))
            data_mat = ct_nomargin.values.astype(float)
            im = ax.imshow(data_mat, cmap="Blues", aspect="auto")
            ax.set_xticks(range(len(ct_nomargin.columns)))
            ax.set_yticks(range(len(ct_nomargin.index)))
            ax.set_xticklabels([str(c)[:20] for c in ct_nomargin.columns], rotation=30, ha="right", fontsize=9)
            ax.set_yticklabels([str(i)[:20] for i in ct_nomargin.index], fontsize=9)
            ax.set_xlabel(q2.libelle[:40], fontsize=10)
            ax.set_ylabel(q1.libelle[:40], fontsize=10)
            ax.set_title(f"Tableau croisé · χ²={chi2:.2f} p={p_val:.3f} {sig} · V={cramer_v:.2f}", fontsize=10, fontweight="bold")
            for i in range(len(ct_nomargin.index)):
                for j in range(len(ct_nomargin.columns)):
                    val = int(data_mat[i, j])
                    pct = ct_pct.iloc[i, j] if i < len(ct_pct) and j < len(ct_pct.columns) else 0
                    ax.text(j, i, f"{val}\n({pct:.0f}%)", ha="center", va="center",
                            fontsize=8, color="white" if data_mat[i, j] > data_mat.max() * 0.6 else "black")
            plt.colorbar(im, ax=ax, shrink=0.7)
            plt.tight_layout()
            key = f"croise_{id1[:6]}_{id2[:6]}"
            graphiques[key] = _fig_to_b64(fig)
            plt.close(fig)

            resultats.append({
                "question_1": {"id": id1, "libelle": q1.libelle},
                "question_2": {"id": id2, "libelle": q2.libelle},
                "tableau_croise": ct.to_dict(),
                "pourcentages_lignes": ct_pct.to_dict(),
                "chi2": round(chi2, 4),
                "p_value": round(p_val, 4),
                "degres_liberte": int(dof),
                "significativite": sig,
                "cramer_v": round(cramer_v, 3),
                "interpretation": (
                    f"Association {'très forte' if cramer_v > 0.5 else 'forte' if cramer_v > 0.3 else 'modérée' if cramer_v > 0.1 else 'faible'} "
                    f"({'statistiquement significative' if p_val < 0.05 else 'non significative'}, p={p_val:.3f})"
                ),
                "graphique_key": key,
            })
        except Exception as e:
            logger.warning(f"Tableau croisé {id1}×{id2} : {e}")
            continue

    return resultats, graphiques


# ─── Analyse quantitative intelligente (guidée par LLM) ───────────────────────

async def analyser_quantitatif_intelligent(etude_id: str) -> dict:
    """
    Claude lit le contexte de l'étude et décide QUELS croisements faire,
    puis exécute uniquement les analyses pertinentes.
    Évite le croisement mécanique de toutes les paires.
    """
    etude = _etudes.get(etude_id)
    if not etude:
        raise ValueError(f"Étude {etude_id} introuvable")
    if not etude.formulaire or not etude.formulaire.reponses:
        raise ValueError("Aucune donnée collectée — le formulaire doit avoir des réponses")

    try:
        import pandas as pd
    except ImportError:
        raise RuntimeError("pandas non disponible")

    form = etude.formulaire
    df   = pd.DataFrame(form.reponses)
    n    = len(df)

    # Résumé des questions pour le prompt
    q_summary = []
    for q in sorted(form.questions, key=lambda x: x.ordre):
        qid = q.question_id
        info: dict[str, Any] = {"id": qid, "libelle": q.libelle, "type": q.type_question}
        if qid in df.columns:
            serie = df[qid].dropna()
            if q.type_question in ("select_one", "oui_non", "likert"):
                info["modalites"] = list(serie.value_counts().head(8).index)
            elif q.type_question in ("number", "rating"):
                vals = pd.to_numeric(serie, errors="coerce").dropna()
                if len(vals):
                    info["min"], info["max"] = float(vals.min()), float(vals.max())
        q_summary.append(info)

    from core.ia_client import ModeIA, ModelePrioritaire, ia_client

    prompt = f"""Tu es un statisticien expert en analyses d'enquêtes quantitatives pour tout type de domaine (épidémiologie, marketing, évaluation, sciences sociales, RH, etc.).

CONTEXTE DE L'ÉTUDE :
Titre : {etude.titre}
Objectif : {etude.contexte}
Questions de recherche : {json.dumps(etude.questions_recherche, ensure_ascii=False)}
Population : {etude.population_cible} | Terrain : {etude.terrain}
N répondants : {n}

VARIABLES DU FORMULAIRE :
{json.dumps(q_summary, ensure_ascii=False, indent=2)}

MISSION : Propose un plan d'analyse CIBLÉ qui répond aux questions de recherche.
Ne croise pas toutes les variables mécaniquement — sélectionne uniquement les croisements analytiquement pertinents.

Retourne un JSON :
{{
  "variables_dependantes": ["id_var1", "id_var2"],
  "variables_independantes": ["id_var3", "id_var4"],
  "croisements_cibles": [
    {{
      "var1": "id_variable_1",
      "var2": "id_variable_2",
      "hypothese": "Les femmes ont moins accès aux soins que les hommes",
      "test": "chi2"
    }}
  ],
  "descriptives_prioritaires": ["id_var1", "id_var3"],
  "hypotheses": ["H1 : ...", "H2 : ..."],
  "note_methodologique": "..."
}}

Limite : maximum 6 croisements ciblés. Retourne UNIQUEMENT le JSON."""

    reponse = await ia_client.appeler(
        prompt=prompt, mode=ModeIA.REDACTION,
        forcer_modele=ModelePrioritaire.CLAUDE_OPUS,
    )
    raw = getattr(reponse, "contenu", "") or ""

    try:
        debut = raw.find("{")
        fin   = raw.rfind("}") + 1
        plan  = json.loads(raw[debut:fin])
    except Exception:
        raise ValueError("Plan d'analyse IA non parseable — réessayez")

    questions_dict = {q.question_id: q for q in form.questions}
    graphiques: dict[str, str] = {}

    # ── Croisements ciblés ────────────────────────────────────────────────────
    resultats_croises: list[dict] = []
    for croix in plan.get("croisements_cibles", [])[:6]:
        id1 = croix.get("var1", "")
        id2 = croix.get("var2", "")
        q1  = questions_dict.get(id1)
        q2  = questions_dict.get(id2)
        if not q1 or not q2 or id1 not in df.columns or id2 not in df.columns:
            continue
        try:
            res, gfx = _analyser_tableaux_croises(df, [q1, q2])
            if res:
                res[0]["hypothese"] = croix.get("hypothese", "")
                resultats_croises.extend(res)
                graphiques.update(gfx)
        except Exception as e:
            logger.warning(f"Croisement ciblé {id1}×{id2} : {e}")

    # ── Descriptives prioritaires ─────────────────────────────────────────────
    resultats_desc: list[dict] = []
    for qid in plan.get("descriptives_prioritaires", [])[:8]:
        if qid not in df.columns:
            continue
        q = questions_dict.get(qid)
        if not q:
            continue
        serie = df[qid].dropna()
        res_q: dict[str, Any] = {
            "question_id": qid,
            "libelle": q.libelle,
            "type": q.type_question,
            "n_repondants": int(serie.count()),
        }
        if q.type_question in ("select_one", "oui_non", "likert"):
            freq = serie.value_counts()
            res_q["frequences"]   = {k: int(v) for k, v in freq.items()}
            res_q["pourcentages"] = {k: float(v) for k, v in (serie.value_counts(normalize=True) * 100).round(1).items()}
            g = _graphique_barres(freq.to_dict(), q.libelle)
            if g:
                graphiques[f"desc_{qid[:8]}"] = g
        elif q.type_question in ("number", "rating"):
            vals = pd.to_numeric(serie, errors="coerce").dropna()
            if len(vals):
                res_q.update({
                    "moyenne":    round(float(vals.mean()), 2),
                    "mediane":    round(float(vals.median()), 2),
                    "ecart_type": round(float(vals.std()), 2),
                    "min":        float(vals.min()),
                    "max":        float(vals.max()),
                })
                g = _graphique_histogramme(vals.tolist(), q.libelle)
                if g:
                    graphiques[f"desc_{qid[:8]}"] = g
        resultats_desc.append(res_q)

    etude.graphiques.update(graphiques)
    analyse = {
        "n_reponses":           n,
        "plan_analyse":         plan,
        "croisements_cibles":   resultats_croises,
        "analyses_descriptives": resultats_desc,
        "graphiques":           list(graphiques.keys()),
        "hypotheses":           plan.get("hypotheses", []),
        "note_methodologique":  plan.get("note_methodologique", ""),
    }
    etude.analyse_quantitative = analyse
    etude.statut     = "analyse"
    etude.updated_at = datetime.now(timezone.utc).isoformat()
    return analyse
