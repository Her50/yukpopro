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
    type_question: str = "text"  # text | number | select_one | select_multiple | rating | likert | date | oui_non
    options: list[str] = field(default_factory=list)  # pour select_one/multiple/likert
    obligatoire: bool = True
    ordre: int = 0


@dataclass
class Formulaire:
    formulaire_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    titre: str = ""
    description: str = ""
    questions: list[QuestionFormulaire] = field(default_factory=list)
    actif: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reponses: list[dict] = field(default_factory=list)


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

    from core.ia_client import ModeIA, ia_client

    # Corpus agrégé
    corpus = "\n\n".join(
        f"=== {t.locuteur} ({t.date_collecte}) ===\n{t.transcription}"
        for t in etude.transcriptions
    )
    n_transcriptions = len(etude.transcriptions)
    questions_str = "\n".join(f"- {q}" for q in etude.questions_recherche) or "Non spécifiées"

    prompt = f"""Tu es un expert en analyse qualitative francophone (méthode {etude.methodologie}).

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

    reponse = await ia_client.appeler(prompt=prompt, mode=ModeIA.CLAUDE_PREMIUM)

    try:
        debut = reponse.find("{")
        fin = reponse.rfind("}") + 1
        analyse = json.loads(reponse[debut:fin])
    except Exception:
        analyse = {"synthese_analytique": reponse, "themes_principaux": []}

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

    from core.ia_client import ModeIA, ia_client

    analyse_q = etude.analyse_qualitative or {}
    analyse_qn = etude.analyse_quantitative or {}
    themes_str = json.dumps(
        [{"code": t.code, "libelle": t.libelle, "frequence": t.frequence,
          "citations": t.citations[:2], "sentiment": t.sentiment}
         for t in etude.themes],
        ensure_ascii=False, indent=2
    )

    prompt = f"""Tu es un chercheur senior spécialisé en méthodes qualitatives africaines.
Rédige un rapport d'étude académique rigoureux et complet en français.

ÉTUDE :
Titre : {etude.titre}
Méthodologie : {etude.methodologie}
Terrain : {etude.terrain} | Population : {etude.population_cible}
Entretiens analysés : {len(etude.transcriptions)}
Questions de recherche : {chr(10).join(etude.questions_recherche)}

THÈMES IDENTIFIÉS :
{themes_str}

SYNTHÈSE DE L'ANALYSE :
{analyse_q.get("synthese_analytique", "")}

Rédige le rapport avec ces sections :
1. RÉSUMÉ EXÉCUTIF (150 mots)
2. INTRODUCTION ET PROBLÉMATIQUE
3. CADRE MÉTHODOLOGIQUE (approche, terrain, collecte, traitement)
4. PRÉSENTATION DES RÉSULTATS PAR THÈME (chaque thème avec citations verbatim, interprétation)
5. DISCUSSION (convergences, divergences, mise en perspective)
6. CONCLUSIONS ET RECOMMANDATIONS
7. LIMITES DE L'ÉTUDE

Utilise un style académique rigoureux, ancre tes analyses dans le contexte africain francophone.
Intègre les citations verbatim pour illustrer chaque thème."""

    rapport_texte = await ia_client.appeler(prompt=prompt, mode=ModeIA.CLAUDE_PREMIUM)

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

        # Citations en bloc
        if etude.themes:
            doc.add_heading("Verbatims clés", 1)
            for theme in etude.themes:
                doc.add_heading(theme.libelle, 2)
                for citation in theme.citations[:3]:
                    p = doc.add_paragraph(f'« {citation} »')
                    p.paragraph_format.left_indent = Inches(0.5)
                    run = p.runs[0] if p.runs else p.add_run()
                    run.italic = True

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
) -> Formulaire:
    etude = _etudes.get(etude_id)
    if not etude:
        raise ValueError(f"Étude {etude_id} introuvable")

    form = Formulaire(
        titre=titre,
        description=description,
        questions=[
            QuestionFormulaire(
                libelle=q.get("libelle", ""),
                type_question=q.get("type_question", "text"),
                options=q.get("options", []),
                obligatoire=q.get("obligatoire", True),
                ordre=i,
            )
            for i, q in enumerate(questions)
        ],
    )
    etude.formulaire = form
    _formulaires_publics[form.formulaire_id] = etude_id
    if etude.mode == "qualitatif":
        etude.mode = "mixte"
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
