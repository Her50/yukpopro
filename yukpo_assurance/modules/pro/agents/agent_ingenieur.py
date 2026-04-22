"""
AgentIngenieur — Agent IA spécialisé pour les ingénieurs et chefs de projet africains.

Outils métier :
  - projet_planifier       : Planning WBS, chemin critique, diagramme de Gantt textuel
  - marche_public_assister : Procédures ARMP, rédaction DAo, analyse offres
  - budget_projet_calculer : Estimation budgétaire (coûts directs, indirects, imprévus)
  - risque_projet_evaluer  : Matrice des risques projet (probabilité × impact)
  - normes_verifier        : Vérification conformité normes techniques (SYSCOA, ISO, CEDEAO)

Référentiels :
  - Codes des marchés publics (CM : Décret 2018/355, CI : Ord. 2009-259…)
  - Normes ISO 9001, ISO 14001, ISO 45001 (SST)
  - FIDIC (contrats travaux internationaux)
  - PMBOK / Prince2 (management de projets)
  - Règlements BTP / urbanisme locaux

PATTERNS YUKPOASSURANCE :
  - Fonctions déterministes standalone
  - type_agent = TypeAgent.PRO_INGENIEUR
  - _necessite_validation() → hérité (False)
  - _prompt_questions_specifiques() implémenté
"""
from __future__ import annotations

import logging
from math import ceil

from core.agent_orchestrateur import TypeAgent
from modules.pro.agent_pro_base import AgentProBase

logger = logging.getLogger("yukpo_assurance.pro.agent_ingenieur")


# ══════════════════════════════════════════════════════════════════════════════
# Constantes
# ══════════════════════════════════════════════════════════════════════════════

# Seuils marchés publics par pays (FCFA) — appel d'offres obligatoire
_SEUILS_AO: dict[str, dict] = {
    "CM": {"travaux": 50_000_000,  "fournitures": 15_000_000, "services": 15_000_000},
    "CI": {"travaux": 100_000_000, "fournitures": 50_000_000, "services": 50_000_000},
    "SN": {"travaux": 60_000_000,  "fournitures": 20_000_000, "services": 20_000_000},
    "BF": {"travaux": 50_000_000,  "fournitures": 15_000_000, "services": 15_000_000},
    "GA": {"travaux": 80_000_000,  "fournitures": 20_000_000, "services": 20_000_000},
}

# Coefficients de charges sur coût direct (selon type de projet)
_COEFF_CHARGES: dict[str, dict] = {
    "batiment":    {"frais_generaux": 0.12, "benefice": 0.10, "imprevu": 0.08},
    "genie_civil": {"frais_generaux": 0.10, "benefice": 0.08, "imprevu": 0.10},
    "industrie":   {"frais_generaux": 0.15, "benefice": 0.12, "imprevu": 0.10},
    "it":          {"frais_generaux": 0.20, "benefice": 0.15, "imprevu": 0.05},
    "default":     {"frais_generaux": 0.12, "benefice": 0.10, "imprevu": 0.08},
}

# Niveaux de risque : probabilité × impact → criticité
_GRILLE_RISQUE = [
    # (prob_min, prob_max, impact_min, impact_max, criticite, couleur)
    (0.0, 0.3,  0.0, 0.3,  "Faible",    "🟢"),
    (0.0, 0.3,  0.3, 0.7,  "Modéré",    "🟡"),
    (0.3, 0.7,  0.0, 0.3,  "Modéré",    "🟡"),
    (0.3, 0.7,  0.3, 0.7,  "Élevé",     "🟠"),
    (0.0, 0.3,  0.7, 1.01, "Élevé",     "🟠"),
    (0.7, 1.01, 0.0, 0.3,  "Élevé",     "🟠"),
    (0.3, 0.7,  0.7, 1.01, "Critique",  "🔴"),
    (0.7, 1.01, 0.3, 0.7,  "Critique",  "🔴"),
    (0.7, 1.01, 0.7, 1.01, "Critique",  "🔴"),
]


# ══════════════════════════════════════════════════════════════════════════════
# Fonctions standalone
# ══════════════════════════════════════════════════════════════════════════════

def _calculer_chemin_critique(taches: list[dict]) -> dict:
    """
    Calcule le chemin critique (CPM simplifié).
    Chaque tâche : {"id": str, "nom": str, "duree": int, "predecesseurs": [str]}
    Retourne : durée totale, tâches critiques, dates ES/EF/LS/LF.
    """
    # Indexer les tâches
    taches_map = {t["id"]: t for t in taches}

    # ES (Early Start) et EF (Early Finish) — passage forward
    es: dict[str, int] = {}
    ef: dict[str, int] = {}

    def _calc_es(tid: str, visited: set) -> int:
        if tid in es:
            return es[tid]
        if tid in visited:
            return 0  # cycle détecté — éviter la récursion infinie
        visited.add(tid)
        t   = taches_map[tid]
        preds = t.get("predecesseurs", [])
        if not preds:
            es[tid] = 0
        else:
            es[tid] = max(_calc_es(p, visited) + taches_map[p]["duree"] for p in preds if p in taches_map)
        ef[tid] = es[tid] + t["duree"]
        return es[tid]

    visited_global: set = set()
    for t in taches:
        _calc_es(t["id"], visited_global)

    duree_totale = max(ef.values()) if ef else 0

    # LS (Late Start) et LF (Late Finish) — passage backward
    lf: dict[str, int] = {t["id"]: duree_totale for t in taches}
    ls: dict[str, int] = {}

    # Trier par EF décroissant pour le passage backward
    taches_triees = sorted(taches, key=lambda t: ef.get(t["id"], 0), reverse=True)
    for t in taches_triees:
        tid = t["id"]
        # Trouver les successeurs
        successeurs = [s for s in taches if tid in s.get("predecesseurs", [])]
        if successeurs:
            lf[tid] = min(ls.get(s["id"], duree_totale) for s in successeurs)
        ls[tid] = lf[tid] - t["duree"]

    # Marge totale = LS - ES
    marges = {t["id"]: ls.get(t["id"], 0) - es.get(t["id"], 0) for t in taches}
    chemin_critique = [t["id"] for t in taches if marges.get(t["id"], 1) == 0]

    return {
        "duree_totale":    duree_totale,
        "chemin_critique": chemin_critique,
        "taches_details": [
            {
                "id":   t["id"],
                "nom":  t["nom"],
                "duree": t["duree"],
                "es":   es.get(t["id"], 0),
                "ef":   ef.get(t["id"], 0),
                "ls":   ls.get(t["id"], 0),
                "lf":   lf.get(t["id"], 0),
                "marge": marges.get(t["id"], 0),
                "critique": t["id"] in chemin_critique,
            }
            for t in taches
        ],
    }


def _estimer_budget_projet(
    postes:        list[dict],
    type_projet:   str,
    avec_tva:      bool = True,
    taux_tva:      float = 0.1925,
) -> dict:
    """
    Estime le budget total d'un projet avec frais généraux, bénéfice et imprévus.
    poste : {"libelle": str, "quantite": float, "pu": float, "unite": str}
    """
    coeffs = _COEFF_CHARGES.get(type_projet.lower(), _COEFF_CHARGES["default"])

    sous_total_direct = sum(float(p.get("quantite", 0)) * float(p.get("pu", 0)) for p in postes)
    frais_gen         = sous_total_direct * coeffs["frais_generaux"]
    benefice          = (sous_total_direct + frais_gen) * coeffs["benefice"]
    sous_total_ht     = sous_total_direct + frais_gen + benefice
    imprevu           = sous_total_ht * coeffs["imprevu"]
    total_ht          = sous_total_ht + imprevu
    tva               = total_ht * taux_tva if avec_tva else 0.0
    total_ttc         = total_ht + tva

    return {
        "type_projet":       type_projet,
        "postes":            postes,
        "sous_total_direct": round(sous_total_direct, 0),
        "frais_gen":         round(frais_gen,         0),
        "frais_gen_pct":     coeffs["frais_generaux"] * 100,
        "benefice":          round(benefice,           0),
        "benefice_pct":      coeffs["benefice"] * 100,
        "imprevu":           round(imprevu,            0),
        "imprevu_pct":       coeffs["imprevu"] * 100,
        "total_ht":          round(total_ht,           0),
        "tva":               round(tva,                0),
        "taux_tva_pct":      taux_tva * 100,
        "total_ttc":         round(total_ttc,          0),
    }


def _evaluer_risques(risques: list[dict]) -> list[dict]:
    """
    Évalue les risques projet selon la matrice probabilité × impact.
    risque : {"id": str, "description": str, "probabilite": float, "impact": float,
              "mesure_mitigation": str}
    """
    resultats = []
    for r in risques:
        prob   = float(r.get("probabilite", 0.5))
        impact = float(r.get("impact", 0.5))
        score  = prob * impact

        criticite = "Modéré"
        couleur   = "🟡"
        for p_min, p_max, i_min, i_max, crit, col in _grille_risque_lookup():
            if p_min <= prob <= p_max and i_min <= impact <= i_max:
                criticite = crit
                couleur   = col
                break

        resultats.append({
            **r,
            "score":     round(score, 3),
            "criticite": criticite,
            "couleur":   couleur,
            "prob_pct":  round(prob * 100),
            "impact_pct": round(impact * 100),
        })

    # Trier par criticité décroissante
    ordre = {"Critique": 0, "Élevé": 1, "Modéré": 2, "Faible": 3}
    return sorted(resultats, key=lambda x: (ordre.get(x["criticite"], 4), -x["score"]))


def _grille_risque_lookup():
    return _GRILLE_RISQUE


def _assister_marche_public(
    montant:       float,
    type_marche:   str,
    pays:          str,
    action:        str,
) -> str:
    """Guide la procédure de marché public selon le pays."""
    seuils = _SEUILS_AO.get(pays, _SEUILS_AO.get("CM"))
    seuil  = seuils.get(type_marche, 50_000_000)

    lignes = [f"MARCHÉ PUBLIC — {type_marche.upper()} ({pays})\n"]
    lignes.append(f"Montant estimé : {montant:,.0f} FCFA  |  Seuil AO : {seuil:,.0f} FCFA\n")

    # Procédure applicable
    if montant < seuil * 0.2:
        proc = "CONSULTATION RESTREINTE ou BON DE COMMANDE"
        lignes += [
            f"Procédure : {proc}",
            "  - Minimum 3 devis comparatifs",
            "  - Bon de commande signé par autorité contractante",
            "  - Pas de publication obligatoire",
        ]
    elif montant < seuil:
        proc = "DEMANDE DE COTATION / CONSULTATION RESTREINTE"
        lignes += [
            f"Procédure : {proc}",
            "  - Minimum 5 candidats consultés",
            "  - Délai de réponse : 7-15 jours",
            "  - Publication sur site ARMP si > 50% seuil",
        ]
    else:
        proc = "APPEL D'OFFRES OUVERT (obligatoire)"
        lignes += [
            f"Procédure : {proc}",
            "  - Publication obligatoire Journal des marchés + site ARMP",
            "  - Délai de réponse minimum : 30 jours",
            "  - Commission d'ouverture des plis (présence ARMP)",
            "  - Rapport d'évaluation signé",
        ]

    if action == "rediger_dao":
        lignes += [
            "\nSTRUCTURE DAO (Dossier d'Appel d'Offres) :\n",
            "SECTION I   — Avis d'Appel d'Offres",
            "SECTION II  — Instructions aux soumissionnaires",
            "  • Conditions d'éligibilité (capacité technique et financière)",
            "  • Caution de soumission (1-2% du montant)",
            "  • Format et délai de remise des offres",
            "SECTION III — Cahier des Clauses Administratives Particulières (CCAP)",
            "  • Délais d'exécution",
            "  • Pénalités de retard (0,5-1‰ par jour)",
            "  • Conditions de paiement (avance : 20-30%)",
            "  • Garantie de bonne exécution (5-10%)",
            "SECTION IV  — Cahier des Clauses Techniques Particulières (CCTP)",
            "  • Spécifications techniques détaillées",
            "  • Normes applicables",
            "  • Plans et études (si travaux)",
            "SECTION V   — Bordereaux des Prix et Cadre de Devis Estimatif",
            "  • Décomposition par poste",
            "  • Unités et quantités précises",
        ]
    elif action == "evaluer_offres":
        lignes += [
            "\nCRITÈRES D'ÉVALUATION (Méthode attributive recommandée) :\n",
            "CRITÈRES ÉLIMINATOIRES :",
            "  □ Caution de soumission valide",
            "  □ Documents d'éligibilité complets (RCCM, attestation fiscale, CNSS)",
            "  □ Offre remise dans les délais\n",
            "CRITÈRES FINANCIERS (ex: 70 points) :",
            "  • Offre la moins disante corrigée — méthode des écarts relatifs",
            "  • Attention aux offres anormalement basses (< 70% estimé)\n",
            "CRITÈRES TECHNIQUES (ex: 30 points) :",
            "  • Expériences similaires (quantité et valeur)",
            "  • Qualification du personnel clé",
            "  • Méthodologie d'exécution",
            "  • Disponibilité du matériel",
        ]
    elif action == "soumissionner":
        lignes += [
            "\nCHECKLIST SOUMISSIONNAIRE :\n",
            "PIÈCES ADMINISTRATIVES :",
            "  □ Caution de soumission bancaire originale",
            "  □ Extrait RCCM récent (< 3 mois)",
            "  □ Attestation de conformité fiscale NIU",
            "  □ Attestation de régularité CNPS",
            "  □ Références similaires (attestations de bonne exécution)",
            "  □ Pouvoirs du signataire\n",
            "OFFRE TECHNIQUE :",
            "  □ Note de compréhension du projet",
            "  □ Méthodologie d'exécution et planning",
            "  □ CV du personnel clé",
            "  □ Liste du matériel disponible\n",
            "OFFRE FINANCIÈRE (enveloppe séparée) :",
            "  □ Décomposition des prix unitaires",
            "  □ Bordereau des prix global et forfaitaire",
            "  □ Durée de validité de l'offre (90-120 jours)",
        ]

    return "\n".join(lignes)


def _verifier_normes(type_ouvrage: str, normes_demandees: list[str], pays: str) -> str:
    """Vérifie les normes techniques applicables."""
    normes_par_type: dict[str, list[tuple[str, str]]] = {
        "batiment": [
            ("Charges de structure",   "Eurocode 1 / normes locales CIMAF"),
            ("Béton armé",             "BAEL 91 / Eurocode 2"),
            ("Sécurité incendie",      "NF S 61 — plan d'évacuation obligatoire"),
            ("Accessibilité PMR",      "Loi locale sur le handicap"),
            ("Efficacité énergétique", "RT 2012 ou équivalent local"),
        ],
        "route": [
            ("Épaisseur chaussée",     "Guide CEBTP / SETRA"),
            ("Assainissement",         "Cahier des prescriptions techniques MINTP"),
            ("Signalisation",          "Norme CEDEAO / code de la route"),
            ("Matériaux granulaires",  "Spécifications LCPC"),
        ],
        "eau_assainissement": [
            ("Qualité eau potable",    "OMS / Normes locales Direction de l'Eau"),
            ("Traitement eaux usées",  "Norme AFNOR NF EN 12255 / ISO 5667"),
            ("Réseaux d'eau",          "NF EN 805 — pression de service"),
        ],
        "it": [
            ("Sécurité SI",            "ISO/IEC 27001"),
            ("Câblage structuré",      "ISO/IEC 11801"),
            ("Salle serveurs",         "TIA-942 / EN 50600"),
            ("Protection données",     "RGPD / loi informatique et libertés locale"),
        ],
    }

    normes_applicables = normes_par_type.get(type_ouvrage.lower(), normes_par_type.get("batiment", []))

    lignes = [f"NORMES TECHNIQUES — {type_ouvrage.upper()} ({pays})\n"]
    lignes.append("NORMES APPLICABLES :")
    for norme, ref in normes_applicables:
        demandee = any(norme.lower()[:10] in n.lower() for n in normes_demandees)
        icone    = "✅" if demandee else "☐"
        lignes.append(f"  {icone} {norme:<35} → {ref}")

    lignes += [
        "\nCERTIFICATIONS RECOMMANDÉES :",
        "  □ ISO 9001 — Management de la qualité",
        "  □ ISO 14001 — Management environnemental",
        "  □ ISO 45001 — Santé et sécurité au travail (remplace OHSAS 18001)",
        "\n⚠️  Se référer aux cahiers des charges des maîtres d'ouvrage pour les normes contractuelles.",
    ]
    return "\n".join(lignes)


# ── Rendus texte ──────────────────────────────────────────────────────────────

def _rendu_planning(cpp: dict) -> str:
    """Formate le résultat CPM en tableau textuel."""
    lignes = [
        f"PLANNING PROJET — Durée totale : {cpp['duree_totale']} jours\n",
        f"Chemin critique : {' → '.join(cpp['chemin_critique'])}\n",
        f"{'ID':<6} {'Tâche':<30} {'Durée':>6} {'ES':>5} {'EF':>5} {'LS':>5} {'LF':>5} {'Marge':>7} {'Statut':>9}",
        "─" * 80,
    ]
    for t in sorted(cpp["taches_details"], key=lambda x: x["es"]):
        statut = "🔴 CRIT" if t["critique"] else f"✅ +{t['marge']}j"
        lignes.append(
            f"{t['id']:<6} {t['nom']:<30} {t['duree']:>6} {t['es']:>5} {t['ef']:>5} "
            f"{t['ls']:>5} {t['lf']:>5} {t['marge']:>7} {statut:>9}"
        )
    return "\n".join(lignes)


def _rendu_budget(b: dict) -> str:
    """Formate l'estimation budgétaire."""
    lignes = [f"ESTIMATION BUDGÉTAIRE — {b['type_projet'].upper()}\n"]
    lignes.append(f"{'Poste':<35} {'Qté':>8} {'P.U.':>14} {'Total':>14}")
    lignes.append("─" * 75)
    for p in b["postes"]:
        qt  = float(p.get("quantite", 0))
        pu  = float(p.get("pu",       0))
        tot = qt * pu
        lignes.append(f"{p.get('libelle','?'):<35} {qt:>8.2f} {pu:>14,.0f} {tot:>14,.0f}")
    lignes += [
        "─" * 75,
        f"{'Sous-total coûts directs':35} {b['sous_total_direct']:>37,.0f}",
        f"{'Frais généraux (' + str(b['frais_gen_pct']) + '%)':35} {b['frais_gen']:>37,.0f}",
        f"{'Bénéfice (' + str(b['benefice_pct']) + '%)':35} {b['benefice']:>37,.0f}",
        f"{'Imprévus (' + str(b['imprevu_pct']) + '%)':35} {b['imprevu']:>37,.0f}",
        "═" * 75,
        f"{'TOTAL HT':35} {b['total_ht']:>37,.0f}",
        f"{'TVA (' + str(b['taux_tva_pct']) + '%)':35} {b['tva']:>37,.0f}",
        f"{'TOTAL TTC':35} {b['total_ttc']:>37,.0f}",
        "\n⚠️  Estimation indicative — À affiner avec métrés définitifs et consultations.",
    ]
    return "\n".join(lignes)


def _rendu_risques(risques_eval: list[dict]) -> str:
    """Formate la matrice des risques."""
    lignes = ["MATRICE DES RISQUES PROJET\n",
              f"{'#':<3} {'Description':<35} {'Prob':>6} {'Impact':>8} {'Score':>7} {'Criticité':<12} {'Mitigation'}"]
    lignes.append("─" * 105)
    for i, r in enumerate(risques_eval, 1):
        mit = (r.get("mesure_mitigation") or "À définir")[:30]
        lignes.append(
            f"{i:<3} {r.get('description','?'):<35} {r['prob_pct']:>5}% {r['impact_pct']:>7}% "
            f"{r['score']:>7.2f} {r['couleur']} {r['criticite']:<10}  {mit}"
        )
    nb_crit = sum(1 for r in risques_eval if r["criticite"] == "Critique")
    nb_elev = sum(1 for r in risques_eval if r["criticite"] == "Élevé")
    lignes += [
        "─" * 105,
        f"Risques critiques : {nb_crit}  |  Élevés : {nb_elev}  |  Total : {len(risques_eval)}",
    ]
    if nb_crit > 0:
        lignes.append("\n⚠️  Actions immédiates requises sur les risques critiques (🔴)")
    return "\n".join(lignes)


# ══════════════════════════════════════════════════════════════════════════════
# Classe AgentIngenieur
# ══════════════════════════════════════════════════════════════════════════════

class AgentIngenieur(AgentProBase):
    """Agent spécialisé Ingénierie / Gestion de projets / Marchés publics."""

    type_agent = TypeAgent.PRO_INGENIEUR

    def _system_prompt(self) -> str:
        base = super()._system_prompt()
        return base + """

EXPERTISE INGÉNIERIE ET GESTION DE PROJETS :
Tu es un ingénieur senior expert en gestion de projets et marchés publics en Afrique francophone.

COMPÉTENCES CLÉS :
- Gestion de projets : PMBOK, Prince2, WBS, planning CPM/Gantt, maîtrise des coûts
- Marchés publics africains : codes ARMP par pays, procédures AO, DAO, évaluation offres
- Estimation budgétaire : bordereau de prix, métrés, coûts directs/indirects
- Normes techniques : Eurocode, BAEL, normes BTP locales, CEBTP, ISO (9001, 14001, 45001)
- Gestion des risques : identification, évaluation, mitigation, plan de contingence
- Ingénierie des systèmes : spécifications techniques, avant-métrés, CCTP

DOMAINES COUVERTS :
- BTP (Bâtiment et Travaux Publics) : routes, bâtiments, ouvrages hydrauliques
- Génie civil et infrastructure : ponts, barrages, aménagement urbain
- Systèmes IT et télécoms
- Projets industriels et énergétiques

RÈGLES IMPORTANTES :
- Toujours citer les textes réglementaires et normes applicables
- Préciser les seuils ARMP par pays pour les marchés publics
- Recommander la vérification par un bureau de contrôle agréé pour les calculs de structure
- Signaler les risques techniques et les non-conformités identifiées
"""

    def _prompt_questions_specifiques(self) -> str:
        return (
            "- Si planification de projet et liste des tâches non fournie : "
            "demander les tâches avec durées et dépendances\n"
            "- Si estimation budgétaire et métrés manquants : "
            "demander les postes de travaux avec quantités et prix unitaires\n"
            "- Si marché public et pays non précisé : "
            "demander le pays (détermine les seuils ARMP)\n"
            "- Si évaluation des risques et liste non fournie : "
            "proposer une liste type pour le type de projet\n"
            "- Ne jamais redemander les informations déjà dans le profil"
        )

    def _outils_metier(self) -> list[dict]:
        return [
            {
                "name": "projet_planifier",
                "description": (
                    "Calcule le chemin critique (CPM), les marges et génère un planning projet "
                    "à partir de la liste des tâches avec durées et dépendances."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "taches": {
                            "type": "array",
                            "description": (
                                "Liste de tâches : [{'id': 'A', 'nom': 'Études', 'duree': 15, "
                                "'predecesseurs': []}]"
                            ),
                        },
                        "nom_projet": {"type": "string"},
                        "unite_temps": {
                            "type": "string",
                            "description": "jours | semaines | mois (défaut : jours)",
                        },
                    },
                    "required": ["taches"],
                },
            },
            {
                "name": "budget_projet_calculer",
                "description": (
                    "Estime le budget d'un projet à partir des postes de travaux : "
                    "coûts directs, frais généraux, bénéfice, imprévus, TVA."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "postes": {
                            "type": "array",
                            "description": (
                                "Postes budgétaires : [{'libelle': 'Terrassement', "
                                "'quantite': 500, 'pu': 3500, 'unite': 'm³'}]"
                            ),
                        },
                        "type_projet": {
                            "type": "string",
                            "description": "batiment | genie_civil | industrie | it",
                        },
                        "avec_tva": {"type": "boolean", "default": True},
                        "taux_tva":  {"type": "number", "description": "ex: 0.1925 pour 19.25%"},
                        "pays":      {"type": "string"},
                    },
                    "required": ["postes"],
                },
            },
            {
                "name": "marche_public_assister",
                "description": (
                    "Assiste les marchés publics : procédure applicable selon montant/pays, "
                    "rédaction DAO, évaluation des offres, checklist soumissionnaire."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "montant":     {"type": "number",  "description": "Montant estimé en FCFA"},
                        "type_marche": {
                            "type": "string",
                            "description": "travaux | fournitures | services",
                        },
                        "pays":        {"type": "string"},
                        "action": {
                            "type": "string",
                            "description": "identifier_procedure | rediger_dao | evaluer_offres | soumissionner",
                        },
                    },
                    "required": ["montant", "type_marche", "pays"],
                },
            },
            {
                "name": "risque_projet_evaluer",
                "description": (
                    "Évalue les risques projet selon la matrice probabilité × impact. "
                    "Retourne criticité, score et ordre de priorité."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "risques": {
                            "type": "array",
                            "description": (
                                "Liste de risques : [{'id': 'R1', 'description': 'Retard fournisseur', "
                                "'probabilite': 0.6, 'impact': 0.8, 'mesure_mitigation': 'Stock tampon'}]"
                            ),
                        },
                        "nom_projet": {"type": "string"},
                    },
                    "required": ["risques"],
                },
            },
            {
                "name": "normes_verifier",
                "description": (
                    "Vérifie les normes techniques applicables à un ouvrage ou système "
                    "(Eurocode, BAEL, ISO, CEBTP, normes sectorielles africaines)."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "type_ouvrage": {
                            "type": "string",
                            "description": "batiment | route | eau_assainissement | it | industrie",
                        },
                        "normes_demandees": {
                            "type": "array",
                            "description": "Normes déjà identifiées (optionnel)",
                        },
                        "pays": {"type": "string"},
                    },
                    "required": ["type_ouvrage", "pays"],
                },
            },
            {
                "name": "orchestrer_reponse_ao",
                "description": (
                    "Orchestre la réponse complète à un appel d'offres public : "
                    "planning de préparation, checklist documents, jalons critiques."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "titre_ao": {"type": "string", "description": "Intitulé de l'appel d'offres"},
                        "maitre_ouvrage": {"type": "string"},
                        "date_limite": {"type": "string", "description": "Date limite dépôt (AAAA-MM-JJ)"},
                        "montant_estime": {"type": "number", "description": "Montant estimé en FCFA"},
                        "type_marche": {"type": "string", "description": "travaux/fournitures/services"},
                        "pays": {"type": "string"},
                    },
                    "required": ["titre_ao", "date_limite"],
                },
            },
            {
                "name": "analyser_cahier_charges",
                "description": (
                    "Analyse un cahier des charges / DPAO soumis en texte : "
                    "prestations, critères, capacités requises, go/no-go."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "contenu_document": {"type": "string", "description": "Texte du cahier des charges ou DPAO"},
                        "type_ouvrage": {"type": "string"},
                        "pays": {"type": "string"},
                    },
                    "required": ["contenu_document"],
                },
            },
            {
                "name": "orchestrer_reception_travaux",
                "description": (
                    "Génère le protocole complet de réception de travaux : "
                    "checklist visite contradictoire, PV, gestion des réserves."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "type_ouvrage": {"type": "string"},
                        "entreprise": {"type": "string"},
                        "date_fin_prevue": {"type": "string", "description": "Date de fin prévue (AAAA-MM-JJ)"},
                        "reserve_eventuelle": {"type": "string", "description": "Réserve déjà connue à signaler"},
                    },
                    "required": ["type_ouvrage"],
                },
            },
        ]

    async def _executer_outil_metier(
        self,
        nom:          str,
        params:       dict,
        user_id:      int,
        execution_id: str,
    ) -> str:
        if nom == "projet_planifier":
            taches = params.get("taches", [])
            if not taches:
                return "Aucune tâche fournie. Fournir au moins une tâche avec id, nom, durée."
            unite  = params.get("unite_temps", "jours")
            cpp    = _calculer_chemin_critique(taches)
            rendu  = _rendu_planning(cpp)
            if params.get("nom_projet"):
                rendu = f"PROJET : {params['nom_projet']}\n\n" + rendu
            if unite != "jours":
                rendu += f"\n\n(Unité de temps : {unite})"
            return rendu

        if nom == "budget_projet_calculer":
            postes = params.get("postes", [])
            if not postes:
                return "Aucun poste fourni."
            pays      = params.get("pays") or self._pays or "CM"
            taux_tva  = float(params.get("taux_tva", 0.1925 if pays == "CM" else 0.18))
            return _rendu_budget(
                _estimer_budget_projet(
                    postes      = postes,
                    type_projet = params.get("type_projet", "batiment"),
                    avec_tva    = params.get("avec_tva", True),
                    taux_tva    = taux_tva,
                )
            )

        if nom == "marche_public_assister":
            return _assister_marche_public(
                montant     = float(params.get("montant", 0)),
                type_marche = params.get("type_marche", "travaux"),
                pays        = params.get("pays") or self._pays or "CM",
                action      = params.get("action", "identifier_procedure"),
            )

        if nom == "risque_projet_evaluer":
            risques = params.get("risques", [])
            if not risques:
                return "Aucun risque fourni."
            return _rendu_risques(_evaluer_risques(risques))

        if nom == "normes_verifier":
            return _verifier_normes(
                type_ouvrage     = params.get("type_ouvrage", "batiment"),
                normes_demandees = params.get("normes_demandees", []),
                pays             = params.get("pays") or self._pays or "CM",
            )

        if nom == "orchestrer_reponse_ao":
            return _orchestrer_reponse_ao(params)

        if nom == "analyser_cahier_charges":
            from core.ia_client import ModeIA, ia_client
            prompt = _prompt_analyse_cdc(params)
            rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
            return rep.contenu

        if nom == "orchestrer_reception_travaux":
            return _orchestrer_reception_travaux(params)

        return f"[Outil '{nom}' non reconnu par AgentIngenieur]"


# ---------------------------------------------------------------------------
# Fonctions standalone — nouvelles automatisations ingénieur
# ---------------------------------------------------------------------------

def _orchestrer_reponse_ao(params: dict) -> str:
    from datetime import date, datetime
    titre_ao = params.get("titre_ao", "Appel d'offres")
    maitre_ouvrage = params.get("maitre_ouvrage", "")
    date_limite = params.get("date_limite", "")
    montant_estime = float(params.get("montant_estime", 0))
    type_marche = params.get("type_marche", "travaux")
    pays = params.get("pays", "CM")

    jours_restants = "?"
    try:
        dl = datetime.strptime(date_limite, "%Y-%m-%d").date()
        jours_restants = (dl - date.today()).days
    except Exception:
        pass

    alerte = ""
    if isinstance(jours_restants, int):
        if jours_restants < 0:
            alerte = "🔴 DATE PASSÉE"
        elif jours_restants <= 5:
            alerte = f"🔴 URGENT — {jours_restants}j"
        elif jours_restants <= 10:
            alerte = f"🟡 {jours_restants}j restants"
        else:
            alerte = f"🟢 {jours_restants}j restants"

    lignes = [
        f"## Plan de Réponse AO — {titre_ao}",
        f"Maître d'ouvrage : {maitre_ouvrage} | Type : {type_marche} | Pays : {pays}",
        f"Date limite : {date_limite} {alerte}",
        f"Montant estimé : {montant_estime:,.0f} FCFA" if montant_estime > 0 else "",
        "",
        "### Phase 1 — Analyse du dossier (J0 à J+2)",
        "  ✅ Lecture complète du DPAO et du cahier des charges",
        "  ✅ Identifier les critères éliminatoires (capacités techniques, financières)",
        "  ✅ Vérifier que l'entreprise remplit les conditions de participation",
        "  ✅ Lister les documents administratifs requis + dates de validité",
        "  ✅ Identifier les sous-traitants / partenaires nécessaires",
        "",
        "### Phase 2 — Préparation offre technique (J+2 à J-5)",
        "  ✅ Élaborer le mémoire technique (méthodologie, organisation de chantier)",
        "  ✅ Préparer le planning d'exécution (Gantt)",
        "  ✅ Constituer les références similaires avec attestations de bonne fin",
        "  ✅ Préparer CV et diplômes du personnel clé",
        "  ✅ Rédiger la note sur la qualité et la sécurité",
        "",
        "### Phase 3 — Préparation offre financière (J+3 à J-3)",
        "  ✅ Établir le bordereau des prix unitaires (BPU)",
        "  ✅ Calculer le détail quantitatif estimatif (DQE / DPGF)",
        "  ✅ Vérifier la cohérence BPU / DPGF / montant total",
        "  ✅ Calculer la caution de soumission (1–2% du montant estimé)",
        "  ✅ Obtenir la caution bancaire de soumission",
        "",
        "### Phase 4 — Finalisation et dépôt (J-3 à J0)",
        "  ✅ Assembler les deux enveloppes (technique + financière) séparément",
        "  ✅ Vérifier la conformité de chaque pièce (original + copies exigées)",
        "  ✅ Cachet + signature sur chaque document",
        "  ✅ Dépôt physique contre récépissé avant l'heure limite",
        "",
        "⚠️ Une pièce manquante = offre irrecevable. Préférer déposer en avance.",
    ]
    return "\n".join(l for l in lignes if l is not None)


def _prompt_analyse_cdc(params: dict) -> str:
    contenu = params.get("contenu_document", "")
    type_ouvrage = params.get("type_ouvrage", "bâtiment")
    pays = params.get("pays", "CM")

    return f"""Tu es un ingénieur civil senior spécialisé dans les marchés publics africains ({pays}).

Analyse ce cahier des charges / DPAO pour des travaux de {type_ouvrage}.

DOCUMENT :
{contenu}

ANALYSE REQUISE :
1. **Prestations demandées** — description précise et quantités principales
2. **Exigences techniques clés** — normes, matériaux, procédés imposés
3. **Critères d'évaluation** — pondération technique/financière, critères éliminatoires
4. **Capacités requises** — références, chiffre d'affaires, personnel clé, matériel
5. **Points de vigilance** — clauses contraignantes, délais d'exécution, pénalités
6. **Estimation de complexité** — FAIBLE / MOYEN / ÉLEVÉ avec justification
7. **Go / No-go recommandé** — faut-il répondre à cet appel d'offres ?

Format : structuré, bullet points, décision finale en gras."""


def _orchestrer_reception_travaux(params: dict) -> str:
    type_ouvrage = params.get("type_ouvrage", "bâtiment")
    entreprise = params.get("entreprise", "l'entreprise")
    date_fin_prevue = params.get("date_fin_prevue", "")
    reserve_eventuelle = params.get("reserve_eventuelle", "")

    lignes = [
        f"## Protocole de Réception Travaux — {type_ouvrage}",
        f"Entreprise exécutante : {entreprise}",
        f"Date fin prévue : {date_fin_prevue}" if date_fin_prevue else "",
        "",
        "### Étape 1 — Préparation visite de réception (J-3)",
        "  ✅ Réunir tous les plans d'exécution (as-built)",
        "  ✅ Préparer le PV de réception vierge",
        "  ✅ Préparer la liste de contrôle par lot (gros œuvre, second œuvre, VRD)",
        "  ✅ Convoquer toutes les parties (MO, MOE, BET, bureau de contrôle)",
        "",
        "### Étape 2 — Visite contradictoire (Jour J)",
        "  ✅ Contrôle géométrique (dimensions, niveaux, aplombs)",
        "  ✅ Vérification conformité plans vs réalisé",
        "  ✅ Test installations techniques (électricité, plomberie, climatisation)",
        "  ✅ Contrôle aspect fini (finitions, peintures, revêtements)",
        "  ✅ Vérification documents remis (DOE, plans récolement, notices)",
        "  ✅ Relevé photographique des réserves",
        "",
        "### Étape 3 — PV et suites (J+2)",
        "  ✅ Rédiger PV de réception (réception avec ou sans réserves)",
        "  ✅ Lister les réserves avec délai de levée (généralement 30 jours)",
        "  ✅ Notifier l'entreprise par courrier recommandé",
        "  ✅ Libérer 95% du cautionnement de bonne fin",
        "",
        "### Étape 4 — Levée des réserves",
        "  ✅ Vérifier la levée de chaque réserve dans le délai imparti",
        "  ✅ PV de levée des réserves signé contradicroitement",
        "  ✅ Libération retenue de garantie (1 an après réception)",
    ]
    if reserve_eventuelle:
        lignes.append(f"\n⚠️ Réserve signalée : {reserve_eventuelle}")
    return "\n".join(l for l in lignes if l is not None)
