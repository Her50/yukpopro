"""
AgentONG — Agent IA pour les professionnels ONG / Développement / Bailleurs de fonds.

Outils métier :
  - logframe_construire     : Structure un cadre logique (objectif, résultats, activités, indicateurs)
  - budget_bailleur_calculer: Budget au format bailleurs (DFID/FCDO, AFD, BM, UE, USAID, BAfD)
  - rapport_bailleur_generer: Génère un rapport narratif d'avancement (MI/final)
  - gestion_projet_suivre   : Tableau de bord opérationnel (jalons, budget, risques)
  - conformite_ong_verifier : Checklist conformité ONG (statuts, déclaration, rapportage fiscal)

Référentiels :
  - Logique d'intervention (OCDE-DAC, théorie du changement)
  - Budget DFID/FCDO (budget lines, overhead ≤15%, T&S)
  - Formats AFD (cadre de mesure des résultats)
  - PCG ONG (comptabilité associative SYSCOHADA)
  - Loi 1901 + droit des associations africain (cameroun, côte d'ivoire, sénégal)
  - Évaluation PEFA / M&E

PATTERNS YUKPOASSURANCE :
  - Fonctions déterministes standalone
  - type_agent = TypeAgent.PRO_ONG
  - _necessite_validation() → hérité (False)
  - _prompt_questions_specifiques() implémenté
"""
from __future__ import annotations

import logging
from typing import Any

from core.agent_orchestrateur import TypeAgent
from modules.pro.agent_pro_base import AgentProBase

logger = logging.getLogger("yukpo_assurance.pro.agent_ong")


# ══════════════════════════════════════════════════════════════════════════════
# Référentiels standalone
# ══════════════════════════════════════════════════════════════════════════════

_FORMATS_BAILLEURS: dict[str, dict] = {
    "dfid_fcdo": {
        "nom": "DFID/FCDO (Royaume-Uni)",
        "devise": "GBP",
        "overhead_max_pct": 15,
        "lignes_budgetaires": [
            "Personnel national", "Personnel international", "Consultants",
            "Voyages et déplacements", "Équipements", "Fournitures et matériels",
            "Formation et renforcement de capacités", "Sous-contrats / partenaires",
            "Frais de communication", "Frais de bureau", "Frais généraux (overhead)",
        ],
        "indicateurs_requis": ["Output", "Outcome", "Impact"],
        "rapport_format": "Quarterly Progress Report (QPR)",
    },
    "afd": {
        "nom": "Agence Française de Développement",
        "devise": "EUR",
        "overhead_max_pct": 12,
        "lignes_budgetaires": [
            "Ressources humaines", "Déplacements et per diem", "Équipements",
            "Sous-traitance", "Frais indirects", "Imprévus (≤5%)",
        ],
        "indicateurs_requis": ["Réalisations", "Résultats", "Impact"],
        "rapport_format": "Rapport de mise en œuvre (RMO)",
    },
    "banque_mondiale": {
        "nom": "Banque Mondiale / IDA",
        "devise": "USD",
        "overhead_max_pct": 20,
        "lignes_budgetaires": [
            "Consultants individuels", "Firmes de consultants", "Biens",
            "Travaux", "Formation", "Coûts opérationnels",
        ],
        "indicateurs_requis": ["PDO Indicators", "Intermediate Results"],
        "rapport_format": "Implementation Status Report (ISR)",
    },
    "union_europeenne": {
        "nom": "Union Européenne / DG DEVCO",
        "devise": "EUR",
        "overhead_max_pct": 7,
        "lignes_budgetaires": [
            "Ressources humaines", "Voyages", "Équipements et fournitures",
            "Bureau local", "Autres coûts / services", "Sous-contrats",
            "Coûts indirects (overhead)",
        ],
        "indicateurs_requis": ["Extrants", "Résultats", "Objectif spécifique"],
        "rapport_format": "Rapport Intermédiaire / Rapport Final",
    },
    "usaid": {
        "nom": "USAID",
        "devise": "USD",
        "overhead_max_pct": 26,
        "lignes_budgetaires": [
            "Personnel", "Fringe Benefits", "Travel", "Equipment",
            "Supplies", "Contractual", "Other Direct Costs", "Indirect Costs",
        ],
        "indicateurs_requis": ["Performance Indicators", "PIRS"],
        "rapport_format": "Performance Monitoring Plan (PMP)",
    },
    "bafd": {
        "nom": "Banque Africaine de Développement",
        "devise": "USD",
        "overhead_max_pct": 15,
        "lignes_budgetaires": [
            "Services de consultants", "Biens", "Travaux",
            "Frais de fonctionnement", "Audit", "Imprévus",
        ],
        "indicateurs_requis": ["Extrants", "Effets", "Impact"],
        "rapport_format": "Rapport d'avancement du projet",
    },
}

_NIVEAUX_LOGFRAME = [
    ("Impact",      "Changement durable à long terme dans la société"),
    ("Outcome",     "Changement à moyen terme dans le comportement des bénéficiaires"),
    ("Output",      "Produits/services livrés directement par le projet"),
    ("Activités",   "Actions concrètes mises en œuvre pour produire les outputs"),
    ("Intrants",    "Ressources humaines, financières et matérielles mobilisées"),
]

_INDICATEURS_SMART = [
    "Spécifique : décrit précisément ce qui est mesuré",
    "Mesurable : peut être quantifié ou qualifié",
    "Atteignable : réaliste compte tenu des ressources",
    "Pertinent : lié directement au niveau logique",
    "Temporel : associé à une échéance précise",
]

_RISQUES_ONG = [
    ("Politique", "Instabilité gouvernementale, changement de priorités nationales"),
    ("Fiduciaire", "Détournement de fonds, mauvaise gestion financière"),
    ("Opérationnel", "Rotation du personnel, accès aux zones d'intervention"),
    ("Conformité", "Non-respect des conditions du bailleur, audit qualifié"),
    ("Reputationnel", "Communication sensible, implication politique locale"),
    ("Sécurité", "Conflits, insécurité dans les zones d'intervention"),
]

_TYPES_ONG_AFRIQUE = {
    "cameroun": {
        "loi": "Loi N°99/014 du 22 décembre 1999",
        "organe": "Ministère de l'Administration Territoriale (MINAT)",
        "reconnaissance": "Déclaration → Récépissé → Agrément",
        "capital_min": None,
        "duree_enregistrement": "30 jours ouvrables",
    },
    "cote_d_ivoire": {
        "loi": "Loi N°60-315 du 21 septembre 1960",
        "organe": "Ministère de l'Intérieur",
        "reconnaissance": "Déclaration → Récépissé provisoire → Récépissé définitif",
        "capital_min": None,
        "duree_enregistrement": "15 jours",
    },
    "senegal": {
        "loi": "Loi N°68-08 du 26 mars 1968",
        "organe": "Ministère de l'Intérieur / Direction des Libertés Publiques",
        "reconnaissance": "Déclaration → Récépissé",
        "capital_min": None,
        "duree_enregistrement": "30 jours",
    },
    "burkina_faso": {
        "loi": "Loi N°10-92/ADP du 15 décembre 1992",
        "organe": "Ministère de l'Administration Territoriale (MATD)",
        "reconnaissance": "Déclaration → Récépissé → Agrément pour ONG étrangères",
        "capital_min": None,
        "duree_enregistrement": "40 jours",
    },
}


# ── Fonctions standalone ───────────────────────────────────────────────────────

def _construire_logframe(
    titre: str,
    secteur: str,
    zone: str,
    duree_mois: int,
    beneficiaires: int,
    probleme_central: str,
    resultats: list[str],
    activites_par_resultat: dict[str, list[str]],
) -> dict:
    """Construit un cadre logique complet avec indicateurs SMART et hypothèses."""
    lignes = []

    # Impact
    impact = f"Amélioration durable des conditions de {secteur} pour les populations de {zone}"
    lignes.append({
        "niveau": "Impact",
        "enonce": impact,
        "indicateurs": [
            f"% de bénéficiaires ayant amélioré leur situation en {secteur} d'ici {duree_mois + 12} mois",
        ],
        "sources_verification": ["Enquête finale indépendante", "Données statistiques nationales"],
        "hypotheses": ["Stabilité politique et sécuritaire dans la zone d'intervention"],
    })

    # Outcome
    outcome = f"Les {beneficiaires:,} bénéficiaires directs ont renforcé leurs capacités en {secteur}"
    lignes.append({
        "niveau": "Outcome",
        "enonce": outcome,
        "indicateurs": [
            f"{int(beneficiaires * 0.8):,} bénéficiaires ({80}%) atteignent les résultats attendus",
            f"Score moyen d'évaluation ≥ 75/100 à la fin du projet",
        ],
        "sources_verification": ["Enquête de satisfaction", "Tests pré/post", "Rapports terrain"],
        "hypotheses": ["Les bénéficiaires maintiennent leur engagement", "Financement décaissé selon calendrier"],
    })

    # Outputs / Résultats
    for i, res in enumerate(resultats[:5], 1):
        activites_res = activites_par_resultat.get(f"R{i}", activites_par_resultat.get(res, []))
        lignes.append({
            "niveau": f"Output R{i}",
            "enonce": res,
            "indicateurs": [f"Nombre de {res.lower()} réalisés selon plan de travail"],
            "sources_verification": ["Rapports de mise en œuvre", "Listes de présence", "Photos"],
            "hypotheses": ["Disponibilité des parties prenantes locales"],
            "activites": [
                {"code": f"A{i}.{j}", "libelle": act}
                for j, act in enumerate(activites_res[:6], 1)
            ],
        })

    return {
        "titre": titre,
        "secteur": secteur,
        "zone_intervention": zone,
        "duree_mois": duree_mois,
        "beneficiaires_directs": beneficiaires,
        "probleme_central": probleme_central,
        "logframe": lignes,
        "niveaux_explication": dict(_NIVEAUX_LOGFRAME),
        "criteres_smart": _INDICATEURS_SMART,
        "nb_resultats": len(resultats),
        "nb_activites_total": sum(len(v) for v in activites_par_resultat.values()),
    }


def _calculer_budget_bailleur(
    bailleur: str,
    montant_total: float,
    duree_mois: int,
    lignes: list[dict],  # [{libelle, montant, unite, qte}]
    pays: str = "cameroun",
    avec_imprevu_pct: float = 5.0,
) -> dict:
    """Calcule et formate un budget selon les normes du bailleur spécifié."""
    fmt = _FORMATS_BAILLEURS.get(bailleur.lower(), _FORMATS_BAILLEURS["afd"])

    total_direct = sum(l.get("montant", 0) * l.get("qte", 1) for l in lignes)
    overhead_pct = fmt["overhead_max_pct"]
    overhead = total_direct * overhead_pct / 100
    imprevu = total_direct * avec_imprevu_pct / 100
    total_calcule = total_direct + overhead + imprevu

    ecart = montant_total - total_calcule
    taux_utilisation = (total_calcule / montant_total * 100) if montant_total else 0

    lignes_enrichies = []
    for l in lignes:
        cout_total = l.get("montant", 0) * l.get("qte", 1)
        lignes_enrichies.append({
            "libelle": l.get("libelle", ""),
            "unite": l.get("unite", "forfait"),
            "quantite": l.get("qte", 1),
            "cout_unitaire": l.get("montant", 0),
            "cout_total": cout_total,
            "pct_budget": round(cout_total / total_calcule * 100, 1) if total_calcule else 0,
        })

    return {
        "bailleur": fmt["nom"],
        "devise": fmt["devise"],
        "montant_sollicite": montant_total,
        "duree_mois": duree_mois,
        "lignes_budgetaires": lignes_enrichies,
        "sous_total_couts_directs": round(total_direct, 0),
        "frais_indirects_overhead": round(overhead, 0),
        "overhead_pct_applique": overhead_pct,
        "imprevu_pct": avec_imprevu_pct,
        "imprevu_montant": round(imprevu, 0),
        "total_projet": round(total_calcule, 0),
        "ecart_vs_enveloppe": round(ecart, 0),
        "taux_utilisation_pct": round(taux_utilisation, 1),
        "lignes_normatives": fmt["lignes_budgetaires"],
        "budget_mensuel_moyen": round(total_calcule / duree_mois, 0) if duree_mois else 0,
        "alerte_overhead": overhead_pct > fmt["overhead_max_pct"],
    }


def _generer_rapport_avancement(
    titre_projet: str,
    bailleur: str,
    periode: str,
    taux_exec_financier: float,
    taux_exec_physique: float,
    activites_realisees: list[str],
    activites_retard: list[str],
    indicateurs: list[dict],  # [{libelle, cible, realise}]
    defis: list[str],
    mesures_correctives: list[str],
    pays: str = "",
) -> dict:
    """Génère la structure d'un rapport narratif d'avancement pour bailleur."""
    fmt = _FORMATS_BAILLEURS.get(bailleur.lower(), _FORMATS_BAILLEURS["afd"])

    # Calcul taux de réalisation des indicateurs
    indicateurs_eval = []
    for ind in indicateurs:
        cible = float(ind.get("cible", 0) or 0)
        realise = float(ind.get("realise", 0) or 0)
        taux = (realise / cible * 100) if cible else 0
        statut = "✅ Atteint" if taux >= 100 else ("⚠️ En cours" if taux >= 50 else "❌ Insuffisant")
        indicateurs_eval.append({
            "libelle": ind.get("libelle", ""),
            "cible": cible,
            "realise": realise,
            "taux_realisation_pct": round(taux, 1),
            "statut": statut,
        })

    # Évaluation globale
    score = (taux_exec_financier + taux_exec_physique) / 2
    note_glob = "Satisfaisante" if score >= 75 else ("Modérée" if score >= 50 else "Insuffisante")

    return {
        "titre_projet": titre_projet,
        "bailleur": fmt["nom"],
        "format_rapport": fmt["rapport_format"],
        "periode_couverte": periode,
        "resume_executif": f"Durant la période {periode}, le projet {titre_projet} a atteint "
                           f"{taux_exec_physique:.1f}% de réalisation physique pour "
                           f"{taux_exec_financier:.1f}% d'exécution financière. "
                           f"Performance globale : {note_glob}.",
        "execution_financiere_pct": taux_exec_financier,
        "execution_physique_pct": taux_exec_physique,
        "note_globale": note_glob,
        "activites_realisees": activites_realisees,
        "activites_retard": activites_retard,
        "indicateurs_performance": indicateurs_eval,
        "defis_identifies": defis,
        "mesures_correctives": mesures_correctives,
        "sections_rapport": [
            "1. Résumé exécutif",
            "2. Avancement par rapport au plan de travail",
            "3. Performance des indicateurs",
            "4. Exécution financière",
            "5. Défis rencontrés et mesures correctives",
            "6. Risques et gestion des risques",
            "7. Leçons apprises",
            "8. Plan de travail période suivante",
            "9. Annexes (listes de présence, photos, pièces justificatives)",
        ],
        "indicateurs_requis_bailleur": fmt["indicateurs_requis"],
    }


def _verifier_conformite_ong(
    pays: str,
    type_ong: str,
    elements: list[str],
) -> dict:
    """Vérifie la conformité d'une ONG selon le cadre légal du pays."""
    pays_norm = pays.lower().replace(" ", "_").replace("'", "_")
    cadre = _TYPES_ONG_AFRIQUE.get(pays_norm, {
        "loi": "Loi sur les associations (à vérifier selon pays)",
        "organe": "Ministère de l'Intérieur / Administration territoriale",
        "reconnaissance": "Déclaration → Récépissé",
        "capital_min": None,
        "duree_enregistrement": "Variable selon pays",
    })

    checklist_base = [
        "Procès-verbal constitutif signé",
        "Statuts approuvés par l'assemblée générale constitutive",
        "Règlement intérieur",
        "Liste des membres fondateurs (avec CNI)",
        "Élection du bureau (PV)",
        "Déclaration au ministère compétent",
        "Récépissé de déclaration obtenu",
        "Compte bancaire ouvert au nom de l'association",
        "Numéro contribuable (pour ONG avec activités fiscales)",
        "Rapport financier annuel disponible",
    ]

    if type_ong == "internationale":
        checklist_base += [
            "Convention de siège avec le gouvernement",
            "Agrément du ministère des affaires étrangères",
            "Accord de partenariat avec structure locale",
        ]

    elements_lower = [e.lower() for e in elements]
    resultats = []
    for item in checklist_base:
        present = any(mot in item.lower() for mot in elements_lower) if elements else False
        resultats.append({"element": item, "statut": "✅ Présent" if present else "❌ Manquant"})

    nb_ok = sum(1 for r in resultats if "✅" in r["statut"])
    taux_conformite = nb_ok / len(resultats) * 100 if resultats else 0

    return {
        "pays": pays,
        "cadre_legal": cadre,
        "type_ong": type_ong,
        "checklist": resultats,
        "nb_elements_ok": nb_ok,
        "nb_elements_total": len(resultats),
        "taux_conformite_pct": round(taux_conformite, 1),
        "statut_global": "Conforme" if taux_conformite >= 80 else ("Partielle" if taux_conformite >= 50 else "Non conforme"),
    }


def _suivre_projet_ong(
    jalons: list[dict],  # [{libelle, date_prev, date_reelle, statut}]
    budget_total: float,
    depenses_reelles: list[dict],  # [{periode, montant}]
    risques: list[dict],  # [{libelle, probabilite, impact}]
) -> dict:
    """Tableau de bord de suivi de projet ONG."""
    # Jalons
    jalons_retard = [j for j in jalons if j.get("statut") == "retard"]
    jalons_ok = [j for j in jalons if j.get("statut") == "realise"]
    taux_jalons = len(jalons_ok) / len(jalons) * 100 if jalons else 0

    # Budget
    total_depense = sum(d.get("montant", 0) for d in depenses_reelles)
    solde = budget_total - total_depense
    taux_exec = total_depense / budget_total * 100 if budget_total else 0

    # Risques (matrice 1-5 × 1-5)
    risques_eval = []
    for r in risques:
        prob = int(r.get("probabilite", 1))
        imp = int(r.get("impact", 1))
        score = prob * imp
        niveau = "Critique" if score >= 15 else ("Élevé" if score >= 9 else ("Modéré" if score >= 4 else "Faible"))
        risques_eval.append({**r, "score_risque": score, "niveau": niveau})

    risques_eval.sort(key=lambda x: x["score_risque"], reverse=True)

    return {
        "jalons_total": len(jalons),
        "jalons_realises": len(jalons_ok),
        "jalons_retard": len(jalons_retard),
        "taux_jalons_pct": round(taux_jalons, 1),
        "jalons_en_retard": jalons_retard,
        "budget_total": budget_total,
        "total_depense": round(total_depense, 0),
        "solde_disponible": round(solde, 0),
        "taux_execution_pct": round(taux_exec, 1),
        "risques_evalues": risques_eval[:10],
        "nb_risques_critiques": sum(1 for r in risques_eval if r["niveau"] == "Critique"),
        "sante_projet": "Bonne" if taux_jalons >= 75 and taux_exec <= 80 else (
            "Attention" if taux_jalons >= 50 else "Critique"
        ),
    }


# ── Rendus texte ───────────────────────────────────────────────────────────────

def _rendu_logframe(lf: dict) -> str:
    lignes = [
        f"## Cadre Logique — {lf['titre']}",
        f"Secteur : {lf['secteur']} | Zone : {lf['zone_intervention']} | Durée : {lf['duree_mois']} mois",
        f"Bénéficiaires directs : {lf['beneficiaires_directs']:,}",
        f"Problème central : {lf['probleme_central']}",
        "",
        "### Niveaux logiques",
    ]
    for niveau in lf["logframe"]:
        lignes.append(f"\n**{niveau['niveau']}** — {niveau['enonce']}")
        lignes.append(f"  Indicateurs : {' | '.join(niveau['indicateurs'][:2])}")
        lignes.append(f"  Sources : {' | '.join(niveau['sources_verification'][:2])}")
        if "activites" in niveau:
            for act in niveau["activites"][:3]:
                lignes.append(f"    [{act['code']}] {act['libelle']}")
    return "\n".join(lignes)


def _rendu_budget_bailleur(b: dict) -> str:
    lignes = [
        f"## Budget Projet — {b['bailleur']}",
        f"Montant sollicité : {b['devise']} {b['montant_sollicite']:,.0f} | Durée : {b['duree_mois']} mois",
        "",
        "| Ligne budgétaire | Qté | Coût unitaire | Total | % Budget |",
        "|------------------|-----|---------------|-------|---------|",
    ]
    for l in b["lignes_budgetaires"]:
        lignes.append(
            f"| {l['libelle'][:40]} | {l['quantite']} | {l['cout_unitaire']:,.0f} "
            f"| {l['cout_total']:,.0f} | {l['pct_budget']}% |"
        )
    lignes += [
        f"\nSous-total coûts directs : {b['devise']} {b['sous_total_couts_directs']:,.0f}",
        f"Frais indirects (overhead {b['overhead_pct_applique']}%) : {b['devise']} {b['frais_indirects_overhead']:,.0f}",
        f"Imprévus ({b['imprevu_pct']}%) : {b['devise']} {b['imprevu_montant']:,.0f}",
        f"**TOTAL PROJET : {b['devise']} {b['total_projet']:,.0f}**",
        f"Budget mensuel moyen : {b['devise']} {b['budget_mensuel_moyen']:,.0f}",
    ]
    if b["alerte_overhead"]:
        lignes.append("⚠️ L'overhead dépasse la limite du bailleur — révision nécessaire.")
    return "\n".join(lignes)


# ══════════════════════════════════════════════════════════════════════════════
# Agent
# ══════════════════════════════════════════════════════════════════════════════

class AgentONG(AgentProBase):
    """
    Agent IA spécialisé pour les professionnels ONG, développement et gestion de projets bailleurs.
    Maîtrise : logframes, budgets multi-bailleurs, rapports d'avancement, M&E, conformité ONG.
    """

    type_agent = TypeAgent.PRO_ONG

    def _prompt_systeme_metier(self) -> str:
        return (
            "Tu es un expert senior en gestion de projets de développement et en management "
            "des organisations à but non lucratif (ONG) en Afrique francophone. "
            "Tu maîtrises : les méthodologies de gestion de projet (PCM, Logical Framework, "
            "Théorie du Changement), les formats bailleurs (DFID/FCDO, AFD, Banque Mondiale, "
            "Union Européenne, USAID, BAfD), la comptabilité des associations (SYSCOHADA-ONG), "
            "le droit des associations en Afrique francophone, et les systèmes de suivi-évaluation (M&E). "
            "Tu aides à structurer des cadres logiques, rédiger des rapports d'avancement, "
            "préparer des budgets aux formats bailleurs, et assurer la conformité institutionnelle. "
            "Réponds toujours en français professionnel adapté au secteur du développement."
        )

    def _prompt_questions_specifiques(self) -> str:
        return (
            "Questions spécifiques à clarifier pour les projets ONG :\n"
            "- Quel est le bailleur principal (DFID, AFD, BM, UE, USAID, BAfD) ?\n"
            "- Quelle est la durée du projet et la période concernée ?\n"
            "- Quels sont les secteurs d'intervention (santé, éducation, WASH, agriculture, etc.) ?\n"
            "- Combien de bénéficiaires directs sont ciblés ?\n"
            "- Quel est le montant total du financement ?\n"
            "- S'agit-il d'une ONG nationale ou internationale ?"
        )

    def _outils_metier(self) -> list[dict]:
        return [
            {
                "name": "logframe_construire",
                "description": (
                    "Construit un cadre logique (logframe) complet avec niveaux Impact/Outcome/Output/Activités, "
                    "indicateurs SMART, sources de vérification et hypothèses. "
                    "Utile pour la conception de projets et les dossiers de financement."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "titre": {"type": "string", "description": "Titre du projet"},
                        "secteur": {"type": "string", "description": "Secteur d'intervention (santé, éducation, WASH...)"},
                        "zone": {"type": "string", "description": "Zone géographique d'intervention"},
                        "duree_mois": {"type": "integer", "description": "Durée du projet en mois"},
                        "beneficiaires": {"type": "integer", "description": "Nombre de bénéficiaires directs"},
                        "probleme_central": {"type": "string", "description": "Problème que le projet cherche à résoudre"},
                        "resultats": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Liste des résultats attendus (outputs)",
                        },
                        "activites_par_resultat": {
                            "type": "object",
                            "description": "Dictionnaire résultat → liste d'activités (clé : R1, R2...)",
                        },
                    },
                    "required": ["titre", "secteur", "zone", "duree_mois", "beneficiaires", "probleme_central"],
                },
            },
            {
                "name": "budget_bailleur_calculer",
                "description": (
                    "Calcule et formate un budget selon les normes du bailleur (DFID, AFD, BM, UE, USAID, BAfD). "
                    "Respecte les plafonds overhead, inclut les imprévus, calcule les pourcentages par ligne."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "bailleur": {"type": "string", "description": "Bailleur (dfid_fcdo, afd, banque_mondiale, union_europeenne, usaid, bafd)"},
                        "montant_total": {"type": "number", "description": "Enveloppe budgétaire totale"},
                        "duree_mois": {"type": "integer", "description": "Durée du projet en mois"},
                        "lignes": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "libelle": {"type": "string"},
                                    "montant": {"type": "number"},
                                    "unite": {"type": "string"},
                                    "qte": {"type": "number"},
                                },
                            },
                            "description": "Lignes budgétaires détaillées",
                        },
                        "avec_imprevu_pct": {"type": "number", "description": "Taux imprévus en % (défaut 5)"},
                    },
                    "required": ["bailleur", "montant_total", "duree_mois"],
                },
            },
            {
                "name": "rapport_bailleur_generer",
                "description": (
                    "Génère la structure d'un rapport narratif d'avancement (intermédiaire ou final) "
                    "adapté aux exigences du bailleur. Évalue les indicateurs et documente les défis."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "titre_projet": {"type": "string"},
                        "bailleur": {"type": "string"},
                        "periode": {"type": "string", "description": "Ex: Janvier–Juin 2024"},
                        "taux_exec_financier": {"type": "number", "description": "% d'exécution financière"},
                        "taux_exec_physique": {"type": "number", "description": "% d'exécution physique"},
                        "activites_realisees": {"type": "array", "items": {"type": "string"}},
                        "activites_retard": {"type": "array", "items": {"type": "string"}},
                        "indicateurs": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "libelle": {"type": "string"},
                                    "cible": {"type": "number"},
                                    "realise": {"type": "number"},
                                },
                            },
                        },
                        "defis": {"type": "array", "items": {"type": "string"}},
                        "mesures_correctives": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["titre_projet", "bailleur", "periode", "taux_exec_financier", "taux_exec_physique"],
                },
            },
            {
                "name": "gestion_projet_suivre",
                "description": (
                    "Tableau de bord de suivi de projet ONG : avancement des jalons, "
                    "exécution budgétaire, matrice des risques, santé globale du projet."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "jalons": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "libelle": {"type": "string"},
                                    "date_prev": {"type": "string"},
                                    "statut": {"type": "string", "description": "realise/en_cours/retard"},
                                },
                            },
                        },
                        "budget_total": {"type": "number"},
                        "depenses_reelles": {
                            "type": "array",
                            "items": {"type": "object"},
                        },
                        "risques": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "libelle": {"type": "string"},
                                    "probabilite": {"type": "integer", "description": "1-5"},
                                    "impact": {"type": "integer", "description": "1-5"},
                                },
                            },
                        },
                    },
                    "required": ["budget_total"],
                },
            },
            {
                "name": "conformite_ong_verifier",
                "description": (
                    "Vérifie la conformité juridique et administrative d'une ONG selon le pays. "
                    "Checklist des documents requis, statut de conformité, démarches à faire."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pays": {"type": "string", "description": "Pays (cameroun, cote_d_ivoire, senegal, burkina_faso...)"},
                        "type_ong": {"type": "string", "description": "nationale ou internationale"},
                        "elements": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Documents/éléments déjà disponibles",
                        },
                    },
                    "required": ["pays", "type_ong"],
                },
            },
            {
                "name": "orchestrer_rapport_bailleur",
                "description": (
                    "Orchestre la production complète d'un rapport bailleur : liste des pièces, "
                    "délais internes, workflow de validation, check-list avant soumission."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "titre_projet": {"type": "string"},
                        "bailleur": {"type": "string"},
                        "type_rapport": {"type": "string", "description": "intermediaire ou final"},
                        "date_soumission": {"type": "string", "description": "Date limite soumission (AAAA-MM-JJ)"},
                        "taux_exec_financier": {"type": "number"},
                        "taux_exec_physique": {"type": "number"},
                    },
                    "required": ["titre_projet", "bailleur", "date_soumission"],
                },
            },
            {
                "name": "analyser_document_projet",
                "description": (
                    "Analyse un document projet soumis (convention, APD, termes de référence, "
                    "rapport d'évaluation) et extrait les engagements, indicateurs et risques."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "contenu_document": {"type": "string", "description": "Texte ou description du document"},
                        "type_document": {"type": "string", "description": "convention_financement/apd/termes_reference/rapport_evaluation/avenant"},
                        "bailleur": {"type": "string"},
                    },
                    "required": ["contenu_document"],
                },
            },
            {
                "name": "preparer_audit_bailleur",
                "description": (
                    "Génère un plan de préparation à l'audit bailleur : checklist documentaire, "
                    "points de contrôle financier, risques à anticiper."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "bailleur": {"type": "string"},
                        "date_audit": {"type": "string", "description": "Date prévue de l'audit (AAAA-MM-JJ)"},
                        "montant_projet": {"type": "number"},
                        "taux_exec_financier": {"type": "number"},
                    },
                    "required": ["bailleur", "date_audit"],
                },
            },
        ]

    async def _executer_outil(self, nom_outil: str, params: dict) -> Any:
        if nom_outil == "logframe_construire":
            r = _construire_logframe(
                titre=params.get("titre", "Projet"),
                secteur=params.get("secteur", "développement"),
                zone=params.get("zone", ""),
                duree_mois=int(params.get("duree_mois", 24)),
                beneficiaires=int(params.get("beneficiaires", 0)),
                probleme_central=params.get("probleme_central", ""),
                resultats=params.get("resultats", []),
                activites_par_resultat=params.get("activites_par_resultat", {}),
            )
            return _rendu_logframe(r)

        if nom_outil == "budget_bailleur_calculer":
            r = _calculer_budget_bailleur(
                bailleur=params.get("bailleur", "afd"),
                montant_total=float(params.get("montant_total", 0)),
                duree_mois=int(params.get("duree_mois", 12)),
                lignes=params.get("lignes", []),
                avec_imprevu_pct=float(params.get("avec_imprevu_pct", 5)),
            )
            return _rendu_budget_bailleur(r)

        if nom_outil == "rapport_bailleur_generer":
            r = _generer_rapport_avancement(
                titre_projet=params.get("titre_projet", ""),
                bailleur=params.get("bailleur", "afd"),
                periode=params.get("periode", ""),
                taux_exec_financier=float(params.get("taux_exec_financier", 0)),
                taux_exec_physique=float(params.get("taux_exec_physique", 0)),
                activites_realisees=params.get("activites_realisees", []),
                activites_retard=params.get("activites_retard", []),
                indicateurs=params.get("indicateurs", []),
                defis=params.get("defis", []),
                mesures_correctives=params.get("mesures_correctives", []),
            )
            # Retourne la structure enrichie sous forme lisible
            lignes = [
                f"## Rapport d'avancement — {r['titre_projet']}",
                f"Bailleur : {r['bailleur']} | Période : {r['periode_couverte']}",
                f"\n**Résumé exécutif :** {r['resume_executif']}",
                f"\n### Exécution",
                f"  Financière : {r['execution_financiere_pct']:.1f}% | Physique : {r['execution_physique_pct']:.1f}% | Note : {r['note_globale']}",
                "\n### Indicateurs de performance",
            ]
            for ind in r["indicateurs_performance"]:
                lignes.append(f"  {ind['statut']} {ind['libelle']} — Cible : {ind['cible']} | Réalisé : {ind['realise']} ({ind['taux_realisation_pct']}%)")
            if r["activites_retard"]:
                lignes.append(f"\n### Activités en retard")
                for a in r["activites_retard"]:
                    lignes.append(f"  ⚠️ {a}")
            if r["defis_identifies"]:
                lignes.append(f"\n### Défis & Mesures correctives")
                for d, m in zip(r["defis_identifies"], r["mesures_correctives"] + ["-"] * 10):
                    lignes.append(f"  Défi : {d} → {m}")
            lignes.append(f"\n### Structure du rapport {r['format_rapport']}")
            for s in r["sections_rapport"]:
                lignes.append(f"  {s}")
            return "\n".join(lignes)

        if nom_outil == "gestion_projet_suivre":
            r = _suivre_projet_ong(
                jalons=params.get("jalons", []),
                budget_total=float(params.get("budget_total", 0)),
                depenses_reelles=params.get("depenses_reelles", []),
                risques=params.get("risques", []),
            )
            lignes = [
                f"## Tableau de Bord Projet ONG",
                f"Santé globale : **{r['sante_projet']}**",
                f"\n### Jalons",
                f"  Réalisés : {r['jalons_realises']}/{r['jalons_total']} ({r['taux_jalons_pct']:.1f}%)",
            ]
            if r["jalons_en_retard"]:
                lignes.append("  En retard :")
                for j in r["jalons_en_retard"]:
                    lignes.append(f"    ⚠️ {j.get('libelle', '')} (prévu {j.get('date_prev', '')})")
            lignes += [
                f"\n### Budget",
                f"  Total : {r['budget_total']:,.0f} | Dépensé : {r['total_depense']:,.0f} ({r['taux_execution_pct']:.1f}%)",
                f"  Solde disponible : {r['solde_disponible']:,.0f}",
            ]
            if r["risques_evalues"]:
                lignes.append(f"\n### Risques principaux ({r['nb_risques_critiques']} critique(s))")
                for risk in r["risques_evalues"][:5]:
                    lignes.append(f"  {risk['niveau']} — {risk.get('libelle', '')} (score {risk['score_risque']})")
            return "\n".join(lignes)

        if nom_outil == "conformite_ong_verifier":
            r = _verifier_conformite_ong(
                pays=params.get("pays", "cameroun"),
                type_ong=params.get("type_ong", "nationale"),
                elements=params.get("elements", []),
            )
            lignes = [
                f"## Conformité ONG — {r['pays'].title()}",
                f"Statut : **{r['statut_global']}** ({r['taux_conformite_pct']}% — {r['nb_elements_ok']}/{r['nb_elements_total']} éléments)",
                f"Cadre légal : {r['cadre_legal']['loi']}",
                f"Organe compétent : {r['cadre_legal']['organe']}",
                f"Procédure : {r['cadre_legal']['reconnaissance']}",
                "\n### Checklist",
            ]
            for item in r["checklist"]:
                lignes.append(f"  {item['statut']} {item['element']}")
            return "\n".join(lignes)

        if nom_outil == "orchestrer_rapport_bailleur":
            return _orchestrer_rapport_bailleur(params)

        if nom_outil == "analyser_document_projet":
            from core.ia_client import ModeIA, ia_client
            prompt = _prompt_analyse_doc_projet(params)
            rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
            return rep.contenu

        if nom_outil == "preparer_audit_bailleur":
            return _preparer_audit_bailleur(params)

        return f"Outil '{nom_outil}' non reconnu."


# ---------------------------------------------------------------------------
# Fonctions standalone — nouvelles automatisations ONG
# ---------------------------------------------------------------------------

def _orchestrer_rapport_bailleur(params: dict) -> str:
    from datetime import date, datetime
    titre = params.get("titre_projet", "le projet")
    bailleur = params.get("bailleur", "bailleur").upper()
    type_rapport = params.get("type_rapport", "intermediaire")
    date_soumission = params.get("date_soumission", "")
    taux_fin = float(params.get("taux_exec_financier", 0))
    taux_phy = float(params.get("taux_exec_physique", 0))

    # Calcul jours restants
    jours_restants = "?"
    try:
        ds = datetime.strptime(date_soumission, "%Y-%m-%d").date()
        jours_restants = (ds - date.today()).days
    except Exception:
        pass

    alerte = ""
    if isinstance(jours_restants, int):
        if jours_restants < 0:
            alerte = "🔴 DATE DÉPASSÉE — soumission en retard"
        elif jours_restants <= 7:
            alerte = f"🔴 URGENT — {jours_restants} jours restants"
        elif jours_restants <= 14:
            alerte = f"🟡 ATTENTION — {jours_restants} jours restants"
        else:
            alerte = f"🟢 {jours_restants} jours restants"

    lignes = [
        f"## Orchestration Rapport Bailleur — {titre}",
        f"Bailleur : {bailleur} | Type : rapport {type_rapport} | Date limite : {date_soumission}",
        f"Exécution financière : {taux_fin:.1f}% | Physique : {taux_phy:.1f}%",
        f"Statut délai : {alerte}",
        "",
        "### Semaine 1 — Collecte données (J-21 à J-14)",
        "  ✅ Extraction états financiers intermédiaires",
        "  ✅ Collecte rapports d'activités des équipes terrain",
        "  ✅ Vérification relevés bancaires du compte projet",
        "  ✅ Compilation justificatifs de dépenses (factures, reçus)",
        "  ✅ Mise à jour tableau de suivi des indicateurs",
        "",
        "### Semaine 2 — Rédaction (J-14 à J-7)",
        "  ✅ Rédaction résumé exécutif",
        "  ✅ Rédaction section narrative par résultat",
        "  ✅ Élaboration tableau financier comparatif (prévu vs réalisé)",
        "  ✅ Documentation des dérogations budgétaires (si >10%)",
        "  ✅ Rédaction section défis et mesures correctives",
        "",
        "### Semaine 3 — Validation et finalisation (J-7 à J-2)",
        "  ✅ Relecture coordination nationale",
        "  ✅ Vérification conformité format bailleur",
        "  ✅ Validation comptable (concordance pièces justificatives)",
        "  ✅ Traduction si requise",
        "  ✅ Compilation annexes (photos, listes bénéficiaires, procès-verbaux)",
        "",
        "### J-1 à J0 — Soumission",
        "  ✅ Contrôle final checklist bailleur",
        "  ✅ Envoi rapport (portail en ligne / email officiel)",
        "  ✅ Accusé de réception et archivage",
        "",
        "### Points de vigilance",
        f"  • Taux d'exécution financière {taux_fin:.1f}% {'✅' if taux_fin >= 70 else '⚠️ à justifier si <70%'}",
        f"  • Taux physique {taux_phy:.1f}% {'✅' if taux_phy >= 70 else '⚠️ écart avec financier à expliquer'}",
        "  • Vérifier règle de fongibilité budgétaire selon convention",
    ]
    return "\n".join(lignes)


def _prompt_analyse_doc_projet(params: dict) -> str:
    contenu = params.get("contenu_document", "")
    type_doc = params.get("type_document", "convention_financement")
    bailleur = params.get("bailleur", "")

    types_labels = {
        "convention_financement": "convention de financement",
        "apd": "accord de partenariat pour le développement",
        "termes_reference": "termes de référence (TdR)",
        "rapport_evaluation": "rapport d'évaluation externe",
        "avenant": "avenant à la convention",
    }
    label = types_labels.get(type_doc, type_doc)

    return f"""Tu es un expert en gestion de projets de développement et en reporting bailleur (AFD, BM, UE, USAID, BAfD).

Analyse cette {label}{f' du bailleur {bailleur}' if bailleur else ''}.

DOCUMENT :
{contenu}

POINTS D'ANALYSE :
1. **Engagements clés** — obligations contractuelles pour l'organisation bénéficiaire
2. **Indicateurs et cibles** — liste exhaustive avec valeurs cibles et délais
3. **Conditions et conditionnalités** — déclencheurs de décaissement, clauses suspensives
4. **Risques et points d'attention** — clauses pouvant causer des problèmes opérationnels
5. **Obligations de reporting** — fréquence, format, contenu exigé
6. **Actions immédiates recommandées** — à mettre en place dès signature/réception

Format : structuré, actionnable, avec niveau d'importance (CRITIQUE / IMPORTANT / INFORMATIF)."""


def _preparer_audit_bailleur(params: dict) -> str:
    from datetime import date, datetime
    bailleur = params.get("bailleur", "bailleur").upper()
    date_audit = params.get("date_audit", "")
    montant = float(params.get("montant_projet", 0))
    taux_fin = float(params.get("taux_exec_financier", 0))

    jours_restants = "?"
    try:
        da = datetime.strptime(date_audit, "%Y-%m-%d").date()
        jours_restants = (da - date.today()).days
    except Exception:
        pass

    niveau_risque = "FAIBLE"
    if isinstance(jours_restants, int) and jours_restants < 14:
        niveau_risque = "ÉLEVÉ"
    elif taux_fin < 60 or taux_fin > 95:
        niveau_risque = "MOYEN"

    lignes = [
        f"## Plan de Préparation Audit — {bailleur}",
        f"Date audit : {date_audit} ({jours_restants} jours) | Montant projet : {montant:,.0f} FCFA",
        f"Taux d'exécution financière : {taux_fin:.1f}% | Niveau de risque audit : **{niveau_risque}**",
        "",
        "### Checklist Documentaire Obligatoire",
        "  ✅ Convention de financement signée + avenants",
        "  ✅ Rapports financiers intermédiaires soumis",
        "  ✅ Relevés bancaires compte projet (toute la période)",
        "  ✅ Grand livre comptable et journaux de caisse",
        "  ✅ Factures et pièces justificatives (classées par catégorie)",
        "  ✅ Procès-verbaux d'appels d'offres + contrats prestataires",
        "  ✅ Justificatifs de décaissements aux bénéficiaires",
        "  ✅ Feuilles de présence formations / ateliers",
        "",
        "### Points de Contrôle Financier",
        "  📋 Vérifier que toutes les dépenses sont dans le budget approuvé",
        "  📋 Contrôler les règles de modification budgétaire (seuil autorisation)",
        "  📋 Vérifier les taux de change appliqués si multi-devises",
        "  📋 S'assurer que les dépenses de personnel sont justifiées (feuilles de temps)",
        "  📋 Contrôler les marchés publics (seuils appel d'offres respectés)",
        "",
        "### Risques à Anticiper",
        f"  {'🔴' if taux_fin < 60 else '🟡'} Sous-exécution {taux_fin:.1f}% — préparer note explicative",
        "  🟡 Dépenses hors lignes budgétaires — identifier et justifier",
        "  🟡 Double financement — vérifier absence de chevauchement avec autres projets",
        "  📋 Préparer une note de contexte sur les difficultés opérationnelles rencontrées",
        "",
        "### Jour J — Logistique Audit",
        "  ✅ Prévoir salle de travail pour les auditeurs",
        "  ✅ Désigner un point focal disponible toute la durée",
        "  ✅ Préparer un classeur numérique (clé USB) avec tous les documents",
        "  ✅ Brief équipe sur conduite à tenir (réponses factuelles, pas d'interprétation)",
    ]
    return "\n".join(lignes)
