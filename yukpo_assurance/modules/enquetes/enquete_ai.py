"""Phase E — Enquêtes AI-powered (génération par prompt + analyse conversationnelle).

Deux pipelines clés greffés sur le module `enquetes` existant :

  1. `generer_etude_et_formulaire_par_prompt(brief)` :
     Sonnet compose une étude COMPLÈTE (titre, contexte, méthodologie,
     population, questions de recherche) + un formulaire XLSForm-class
     (10-40 questions structurées select_one/select_multiple/integer/
     decimal/text/date/time/geopoint/image/audio + relevant + constraint)
     en un seul appel LLM long.

  2. `analyser_par_prompt(etude_id, prompt)` :
     Sonnet compose un PLAN JSON d'opérations pandas (filter/groupby/agg/
     chart/llm_synthese), le backend l'exécute dans un sandbox restreint
     sur le DataFrame des réponses, génère graphiques + synthèse Sonnet
     finale. Pas d'exec Python arbitraire.

Réutilise `gestionnaire_enquetes.creer_etude/creer_formulaire`,
`Etude`, `Formulaire`, `QuestionFormulaire`, et les helpers de graphiques
(`_graphique_barres`, `_graphique_camembert`, `_graphique_histogramme`,
`_fig_to_b64`).
"""
from __future__ import annotations

import base64
import io
import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger("yukpo_assurance.enquetes.ai")


# ─── E1 — Génération étude + formulaire par prompt ───────────────────────────

_PROMPT_SYSTEME_ENQUETE = """Tu es un expert SENIOR en méthodologie d'enquête \
et collecte de données (XLSForm/KoboCollect), capable de composer un \
formulaire structuré pour N'IMPORTE QUEL domaine sans limite :

  • Santé (maternelle, infantile, mentale, nutritionnelle, épidémiologique, hôpital)
  • Droit / Audit (conformité OHADA, CIMA, ISO, RSE, sécurité sociale, fiscal)
  • RH (recrutement, 360°, climat social, formation, départ, NPS employé, intégration)
  • Marketing (satisfaction, NPS, étude marché, test produit, prix, brand awareness)
  • ONG / humanitaire (recensement bénéficiaires, évaluation impact, suivi programme,
    vulnérabilité, sécurité alimentaire, eau-hygiène-assainissement WASH, protection)
  • Éducation (évaluation pédagogique, satisfaction parents, suivi élèves, absentéisme)
  • Agriculture / élevage (recensement exploitants, accès intrants, post-récolte)
  • Urbanisme / mobilité (déplacements, accès services, qualité de vie quartier)
  • Gouvernance / opinion publique (sondages, consultations citoyennes, élections)
  • Recherche académique (mémoires, thèses, enquêtes terrain qualitatives)
  • Finance / microcrédit (scoring social, suivi remboursement, éducation financière)
  • Tourisme (satisfaction visiteurs, attractivité destination)
  • Industrie (sécurité, qualité, supply chain, audit fournisseur)
  • Et TOUT autre domaine que l'utilisateur demande.

Tu n'es JAMAIS limité par un catalogue prédéfini. Adapte la méthodologie, \
les questions, les sections au contexte exact du brief utilisateur — y \
compris contextes très spécifiques (étude ethnographique pêcheurs Sénégal, \
audit conformité ISO 22000 unité agro-alimentaire CI, sondage politique \
intercommunalité, suivi cohorte longitudinale d'élèves Bamako, etc.).

Tu reçois un brief utilisateur et tu RENVOIES UN JSON strict (pas de texte avant/après) :

{
  "etude": {
    "titre": "Titre clair (max 120 chars)",
    "contexte": "Contexte 2-4 phrases — pourquoi cette étude, sur quel \
problème, dans quel cadre",
    "questions_recherche": ["3-6 questions de recherche claires"],
    "methodologie": "qualitatif | quantitatif | mixte",
    "population_cible": "Description précise de la cible",
    "terrain": "Lieu de collecte (ville/pays/secteur)"
  },
  "formulaire": {
    "titre": "Titre du formulaire (max 120 chars)",
    "description": "1-2 phrases d'intro affichées au répondant",
    "sections": [
      {"id": "intro",       "titre": "Présentation"},
      {"id": "profil",      "titre": "Profil du répondant"},
      {"id": "experience",  "titre": "Expérience"},
      {"id": "satisfaction","titre": "Satisfaction et améliorations"}
    ],
    "questions": [
      {
        "id":          "q1_age",
        "section":     "profil",
        "type":        "integer",
        "label":       "Quel est votre âge ?",
        "hint":        "En années",
        "required":    true,
        "constraint":  ". >= 12 and . <= 100",
        "constraint_message": "Âge entre 12 et 100 ans"
      },
      {
        "id":        "q2_genre",
        "section":   "profil",
        "type":      "select_one",
        "label":     "Quel est votre genre ?",
        "required":  true,
        "choices":   [
          {"value": "h", "label": "Homme"},
          {"value": "f", "label": "Femme"},
          {"value": "autre", "label": "Autre / Ne souhaite pas préciser"}
        ]
      },
      {
        "id":        "q3_satisfaction",
        "section":   "satisfaction",
        "type":      "select_one",
        "label":     "Quel est votre niveau de satisfaction ?",
        "required":  true,
        "choices": [
          {"value": "1", "label": "Très insatisfait"},
          {"value": "2", "label": "Insatisfait"},
          {"value": "3", "label": "Neutre"},
          {"value": "4", "label": "Satisfait"},
          {"value": "5", "label": "Très satisfait"}
        ]
      },
      {
        "id":      "q4_raisons",
        "section": "satisfaction",
        "type":    "select_multiple",
        "label":   "Pour quelles raisons ?",
        "relevant": "${q3_satisfaction} = '1' or ${q3_satisfaction} = '2'",
        "choices": [
          {"value": "prix",  "label": "Prix trop élevé"},
          {"value": "qual",  "label": "Qualité"},
          ...3-6 choix pertinents
        ]
      },
      {
        "id": "q5_commentaire",
        "section": "satisfaction",
        "type": "text",
        "label": "Avez-vous un commentaire libre ?",
        "required": false
      }
      ... 10-40 questions au total
    ],
    "dictionnaire_variables": {
      "q1_age": {"label": "Âge en années", "type": "integer", "unit": "ans"},
      ...une entrée par question
    }
  },
  "analyses_suggerees": [
    "Distribution des âges par genre",
    "Score NPS calculé sur q3_satisfaction",
    "Top 3 raisons d'insatisfaction par tranche d'âge",
    ...5-10 angles d'analyse pertinents pour aval E4
  ]
}

Règles XLSForm :
1. Types supportés : select_one, select_multiple, integer, decimal, text, \
note, date, time, dateTime, geopoint, image, audio, barcode, calculate
2. `relevant` : expressions ${q_id} = 'value' (logique conditionnelle)
3. `constraint` : expressions . >= X (validation valeur)
4. Sections groupent les questions thématiquement (begin_group côté XLSForm)
5. IDs en snake_case, préfixés q1_/q2_/… pour ordre
6. Choices courtes (max 60 chars) avec value snake_case ASCII
7. Crédibilité géographique selon le brief — pas par défaut Afrique francophone, \
   adapte au pays/zone mentionné par l'utilisateur (Maghreb, Europe, Asie, etc.)
8. Si méthodologie = qualitatif → max 10 questions ouvertes courtes
9. Si méthodologie = quantitatif → 20-50 questions, beaucoup de select_one
10. Mixte → équilibré 15-30 questions
11. UTILISE TON EXPERTISE DOMAINE : si le brief mentionne "OHADA" → cite les \
   articles pertinents en hint ; si "ISO 14001" → questions calées sur les \
   clauses normatives ; si "OMS santé maternelle" → indicateurs OMS standard ; \
   si "NPS" → échelle 0-10 standard.
12. NE PAS sous-traiter : compose AUTANT de questions que nécessaire pour \
    couvrir SÉRIEUSEMENT le sujet (pas de version light/superficielle).
"""


async def generer_etude_et_formulaire_par_prompt(
    brief: str,
    *,
    nb_questions_cible: Optional[int] = None,
    profil_cible: Optional[str] = None,
    langue: str = "fr",
) -> tuple[Any, Any, list[dict]]:
    """LLM Sonnet compose Etude + Formulaire complet depuis un brief.

    Returns:
        (etude, formulaire, usages_llm) — etude et formulaire sont des
        instances de `gestionnaire_enquetes.Etude` / `Formulaire` déjà
        persistées dans le `_etudes` in-memory dict du gestionnaire.
    """
    from core.ia_client import ia_client, ModeIA
    from modules.enquetes import gestionnaire_enquetes as ge

    user_prompt = f"BRIEF UTILISATEUR : {brief}\nLANGUE : {langue}\n"
    if nb_questions_cible:
        user_prompt += f"NOMBRE DE QUESTIONS CIBLE : ~{nb_questions_cible}\n"
    if profil_cible:
        user_prompt += f"PROFIL CIBLE : {profil_cible}\n"
    user_prompt += "\nProduis le JSON spec strict."

    # Modèle PUISSANT (Opus 4.7 / gpt-4-turbo) + beaucoup de tokens pour
    # composer un formulaire sérieux et adapté à n'importe quel domaine.
    # L'universalité du système repose sur ce prompt système + ce modèle.
    from core.ia_client import ModelePrioritaire
    rep = await ia_client.appeler(
        prompt=user_prompt,
        systeme=_PROMPT_SYSTEME_ENQUETE,
        mode=ModeIA.RAISONNEMENT,
        max_tokens_override=24000,
        json_attendu=True,
        utiliser_cache=False,
        forcer_modele=ModelePrioritaire.CLAUDE_OPUS,
    )
    texte = rep.contenu if hasattr(rep, "contenu") else str(rep)
    m = re.search(r"\{[\s\S]*\}", texte)
    if not m:
        raise ValueError("LLM n'a pas produit de JSON parseable")
    spec = json.loads(m.group(0))

    etude_spec = spec.get("etude") or {}
    formulaire_spec = spec.get("formulaire") or {}

    # 1. Créer l'étude
    etude = ge.creer_etude(
        titre=etude_spec.get("titre", "Étude")[:120],
        contexte=etude_spec.get("contexte", ""),
        questions_recherche=etude_spec.get("questions_recherche", []),
        methodologie=etude_spec.get("methodologie", "mixte"),
        population_cible=etude_spec.get("population_cible", ""),
        terrain=etude_spec.get("terrain", ""),
        mode=etude_spec.get("methodologie", "mixte"),
    )

    # 2. Créer le formulaire associé
    formulaire = ge.creer_formulaire(
        etude_id=etude.etude_id,
        titre=formulaire_spec.get("titre", etude.titre)[:120],
        description=formulaire_spec.get("description", ""),
        questions=formulaire_spec.get("questions", []),
        sections=formulaire_spec.get("sections"),
    )

    # 3. Dictionnaire variables (pour analyse aval)
    if formulaire_spec.get("dictionnaire_variables"):
        formulaire.dictionnaire_variables = formulaire_spec["dictionnaire_variables"]

    # 4. Stocke les analyses suggérées sur l'étude (utilisées en E4)
    etude.analyses_suggerees = spec.get("analyses_suggerees", [])

    usage = {
        "tokens_in":  getattr(rep, "tokens_input", 0),
        "tokens_out": getattr(rep, "tokens_output", 0),
        "modele":     getattr(rep, "modele_utilise", "sonnet"),
        "etape":      "enquete_generer_prompt",
    }
    return etude, formulaire, [usage]


# ─── E4 — Analyse conversationnelle "à la demande" ───────────────────────────

_PROMPT_SYSTEME_ANALYSE = """Tu es un analyste de données expert. Tu reçois :
  • Le schéma des variables (id → label + type)
  • Le nombre de réponses collectées
  • La demande d'analyse de l'utilisateur en langage naturel

Tu RENVOIES UN JSON strict décrivant un PLAN d'opérations à exécuter sur \
le DataFrame pandas des réponses. Le backend exécutera ce plan dans un \
sandbox restreint (pas d'exec Python arbitraire).

Format :
{
  "titre_analyse": "Titre court du résultat",
  "description": "1-2 phrases résumant la démarche",
  "operations": [
    {"type": "filter", "colonne": "q1_age", "predicat": ">=", "valeur": 18},
    {"type": "groupby", "colonnes": ["q2_genre"]},
    {"type": "agg", "agg": "mean", "colonne": "q3_satisfaction"},
    {"type": "agg", "agg": "count", "colonne": "*"},
    {"type": "sort", "colonne": "mean_q3_satisfaction", "desc": true},
    {"type": "chart", "chart_type": "bar", "x": "q2_genre", "y": "mean_q3_satisfaction", \
     "titre": "Satisfaction moyenne par genre"}
  ],
  "synthese_instruction": "Décris en 4-6 bullets les insights principaux \
des résultats agrégés, en pointant les écarts notables et 2 recommandations \
actionnables pour le marchand."
}

Types d'opérations supportés :
  • filter   : {colonne, predicat (==/!=/>/>=/</<=/in), valeur}
  • groupby  : {colonnes: [...]}
  • agg      : {agg: mean|sum|count|nunique|min|max|std, colonne (* pour count global)}
  • sort     : {colonne, desc: bool}
  • limit    : {n: 20}
  • chart    : {chart_type: bar|line|pie|histogram|heatmap, x, y, titre}
  • nps      : {colonne_score} → calcule promoteurs%-détracteurs%
  • llm_synthese : {instruction} (généralement la dernière étape)

Règles :
1. Ne réfère à des colonnes que si elles existent dans le schéma fourni
2. Maximum 8 opérations (sinon coûteux à exécuter)
3. Toujours finir par 1 chart + 1 llm_synthese si analyse non triviale
4. Pas d'opération destructive — uniquement lecture
"""


async def analyser_par_prompt(
    etude_id: str, prompt_analyse: str,
) -> dict:
    """LLM Sonnet → plan JSON → exécution sandbox pandas → graphiques + synthèse.

    Returns dict :
      {
        "titre_analyse": "...",
        "description": "...",
        "tableaux": [{titre, donnees: [[...]]}],
        "graphiques": {nom: base64_png},
        "synthese_md": "...",
        "plan_execute": [...]
      }
    """
    from core.ia_client import ia_client, ModeIA
    from modules.enquetes import gestionnaire_enquetes as ge

    etude = ge.get_etude(etude_id)
    if not etude or not etude.formulaire:
        raise ValueError("Étude / formulaire introuvable")

    reponses = etude.formulaire.reponses or []
    if not reponses:
        return {
            "titre_analyse": "Aucune donnée",
            "description": "Aucune réponse collectée pour le moment.",
            "tableaux": [], "graphiques": {}, "synthese_md": "",
            "plan_execute": [],
        }

    # 1. Schéma compact pour Sonnet
    schema = []
    for q in etude.formulaire.questions:
        schema.append({
            "id":    q.id,
            "label": q.label[:80],
            "type":  q.type,
            "choices": (
                [c.get("value") for c in (q.choices or [])][:8]
                if q.choices else None
            ),
        })
    schema_str = json.dumps(schema, ensure_ascii=False)
    user_prompt = (
        f"SCHÉMA :\n{schema_str}\n\n"
        f"NOMBRE DE RÉPONSES : {len(reponses)}\n\n"
        f"DEMANDE D'ANALYSE :\n{prompt_analyse}"
    )

    # Plan d'analyse → modèle puissant pour gérer la complexité statistique
    from core.ia_client import ModelePrioritaire
    rep = await ia_client.appeler(
        prompt=user_prompt,
        systeme=_PROMPT_SYSTEME_ANALYSE,
        mode=ModeIA.RAISONNEMENT,
        max_tokens_override=6000,
        json_attendu=True,
        utiliser_cache=False,
        forcer_modele=ModelePrioritaire.CLAUDE_OPUS,
    )
    texte = rep.contenu if hasattr(rep, "contenu") else str(rep)
    m = re.search(r"\{[\s\S]*\}", texte)
    if not m:
        raise ValueError("LLM n'a pas produit de JSON parseable")
    plan = json.loads(m.group(0))

    # 2. Exécution sandbox
    try:
        import pandas as pd
    except ImportError:
        raise RuntimeError("pandas requis pour les analyses")

    df = pd.DataFrame(reponses)
    if df.empty:
        return {
            "titre_analyse": plan.get("titre_analyse", "Analyse"),
            "description": "Aucune réponse à analyser.",
            "tableaux": [], "graphiques": {}, "synthese_md": "",
            "plan_execute": plan.get("operations", []),
        }

    tableaux: list[dict] = []
    graphiques: dict[str, str] = {}
    current = df  # df qui mute au fil des operations
    instruction_synthese: Optional[str] = None
    nps_result: Optional[dict] = None

    for op in plan.get("operations", []):
        try:
            t = op.get("type")
            if t == "filter":
                col = op.get("colonne")
                pred = op.get("predicat", "==")
                val = op.get("valeur")
                if col in current.columns:
                    if pred == "==":  current = current[current[col] == val]
                    elif pred == "!=": current = current[current[col] != val]
                    elif pred == ">":  current = current[current[col] > val]
                    elif pred == ">=": current = current[current[col] >= val]
                    elif pred == "<":  current = current[current[col] < val]
                    elif pred == "<=": current = current[current[col] <= val]
                    elif pred == "in" and isinstance(val, list):
                        current = current[current[col].isin(val)]
            elif t == "groupby":
                cols = op.get("colonnes", [])
                cols = [c for c in cols if c in current.columns]
                if cols:
                    current = current.groupby(cols).size().reset_index(name="count")
            elif t == "agg":
                agg = op.get("agg", "count")
                col = op.get("colonne")
                if col == "*":
                    tableaux.append({"titre": "Comptage", "donnees": [["Total", len(current)]]})
                elif col in current.columns:
                    try:
                        if agg == "mean":      val = float(current[col].astype(float).mean())
                        elif agg == "sum":     val = float(current[col].astype(float).sum())
                        elif agg == "count":   val = int(current[col].count())
                        elif agg == "nunique": val = int(current[col].nunique())
                        elif agg == "min":     val = float(current[col].astype(float).min())
                        elif agg == "max":     val = float(current[col].astype(float).max())
                        elif agg == "std":     val = float(current[col].astype(float).std())
                        else: continue
                        tableaux.append({
                            "titre": f"{agg.upper()} {col}",
                            "donnees": [[f"{agg} {col}", round(val, 3)]],
                        })
                    except Exception:
                        pass
            elif t == "sort":
                col = op.get("colonne")
                if col in current.columns:
                    current = current.sort_values(col, ascending=not op.get("desc", False))
            elif t == "limit":
                n = int(op.get("n", 20))
                current = current.head(n)
            elif t == "chart":
                chart_type = op.get("chart_type", "bar")
                titre = op.get("titre", "Graphique")
                x = op.get("x")
                y = op.get("y")
                if x and x in current.columns:
                    try:
                        b64 = _generer_chart_simple(
                            current, x, y, chart_type, titre,
                        )
                        if b64:
                            graphiques[titre[:60]] = b64
                    except Exception as e:
                        logger.warning(f"[Analyse/chart] {titre}: {e}")
            elif t == "nps":
                col = op.get("colonne_score")
                if col and col in current.columns:
                    try:
                        scores = current[col].astype(float)
                        promoteurs = (scores >= 9).sum() / len(scores) * 100
                        detracteurs = (scores <= 6).sum() / len(scores) * 100
                        nps = promoteurs - detracteurs
                        nps_result = {
                            "nps": round(nps, 1),
                            "promoteurs_pct": round(promoteurs, 1),
                            "detracteurs_pct": round(detracteurs, 1),
                            "neutres_pct": round(100 - promoteurs - detracteurs, 1),
                        }
                        tableaux.append({
                            "titre": "Score NPS",
                            "donnees": [[k, v] for k, v in nps_result.items()],
                        })
                    except Exception as e:
                        logger.warning(f"[Analyse/nps] {e}")
            elif t == "llm_synthese":
                instruction_synthese = op.get("instruction")
        except Exception as e:
            logger.warning(f"[Analyse/op] {op}: {e}")
            continue

    # 3. Synthèse Sonnet finale
    synthese_md = ""
    if instruction_synthese or plan.get("synthese_instruction"):
        instruction = instruction_synthese or plan.get("synthese_instruction")
        contexte_donnees = json.dumps({
            "tableaux": tableaux[:20], "nps": nps_result,
            "n_reponses_filtrees": len(current),
        }, ensure_ascii=False, default=str)
        try:
            rep_s = await ia_client.appeler(
                prompt=(
                    f"INSTRUCTION : {instruction}\n\n"
                    f"DONNÉES AGRÉGÉES :\n{contexte_donnees[:8000]}\n\n"
                    f"Produis une synthèse en markdown (4-6 bullets max, "
                    f"insights actionnables, écarts notables, "
                    f"2 recommandations concrètes pour le marchand)."
                ),
                systeme="Tu es un analyste de données. Sois concis, pointu, "
                        "concret. Pas de blabla méthodologique.",
                mode=ModeIA.REDACTION,
                max_tokens_override=1500,
                utiliser_cache=False,
            )
            synthese_md = rep_s.contenu if hasattr(rep_s, "contenu") else str(rep_s)
        except Exception as e:
            logger.warning(f"[Analyse/synthese] {e}")
            synthese_md = "_(Synthèse non disponible.)_"

    return {
        "titre_analyse": plan.get("titre_analyse", "Analyse"),
        "description": plan.get("description", ""),
        "tableaux": tableaux,
        "graphiques": graphiques,
        "synthese_md": synthese_md,
        "plan_execute": plan.get("operations", []),
        "n_reponses_analyses": len(current),
    }


def _generer_chart_simple(
    df, x: str, y: Optional[str], chart_type: str, titre: str,
) -> Optional[str]:
    """Génère un graphique simple (PNG base64) via matplotlib."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    fig, ax = plt.subplots(figsize=(8, 5))
    try:
        if chart_type == "bar" and y:
            df.plot(kind="bar", x=x, y=y, ax=ax, legend=False)
        elif chart_type == "line" and y:
            df.plot(kind="line", x=x, y=y, ax=ax, legend=False)
        elif chart_type == "pie":
            counts = df[x].value_counts().head(8)
            ax.pie(counts.values, labels=counts.index.astype(str), autopct="%1.0f%%")
        elif chart_type == "histogram":
            df[x].hist(ax=ax, bins=15)
        else:
            counts = df[x].value_counts().head(15)
            ax.bar(counts.index.astype(str), counts.values)
        ax.set_title(titre)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
        plt.close(fig)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        plt.close(fig)
        logger.warning(f"[Chart] {titre} échec : {e}")
        return None
