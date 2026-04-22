"""
AgentMicrofinance — Agent IA pour les professionnels de la microfinance et de l'inclusion financière.

Outils métier :
  - credit_micro_analyser   : Analyse de demande de crédit (scoring, ratio d'endettement, capacité)
  - par_calculer            : Calcul du Portfolio At Risk (PAR) et indicateurs de qualité du portefeuille
  - produit_micro_concevoir : Conception de produit d'épargne-crédit (taux, durée, garanties, conditions)
  - bilan_sfd_analyser      : Analyse de bilan d'un SFD (ratios prudentiels COBAC/BCEAO-SFD)
  - rapport_superviseur_gen : Génère un rapport réglementaire pour superviseur (COBAC, BCEAO, MINFI)

Référentiels :
  - Règlement COBAC 2017 sur les SFD (CEMAC)
  - Loi PARMEC (UEMOA) — Systèmes Financiers Décentralisés
  - Indicateurs de performance MIX Market (FPM, OSS, PAR30, ROA, ROE)
  - CGAP Performance Standards
  - Code OHADA applicable aux IMF
  - Taux usuraires COBAC/BCEAO

PATTERNS YUKPOASSURANCE :
  - Fonctions déterministes standalone
  - type_agent = TypeAgent.PRO_MICROFINANCE
  - _necessite_validation() → hérité (False)
  - _prompt_questions_specifiques() implémenté
"""
from __future__ import annotations

import logging
import math
from typing import Any

from core.agent_orchestrateur import TypeAgent
from modules.pro.agent_pro_base import AgentProBase

logger = logging.getLogger("yukpo_assurance.pro.agent_microfinance")


# ══════════════════════════════════════════════════════════════════════════════
# Référentiels
# ══════════════════════════════════════════════════════════════════════════════

# Taux directeurs et plafonds usuraires
_TAUX_USURAIRE: dict[str, float] = {
    "CEMAC":  27.0,   # COBAC : taux plafond 27% effectif global annuel
    "UEMOA":  24.0,   # BCEAO : taux usuraire 24% (instruction 008-05-2015)
    "CM":     27.0,
    "GA":     27.0,
    "CG":     27.0,
    "CF":     27.0,
    "TD":     27.0,
    "GQ":     27.0,
    "CI":     24.0,
    "SN":     24.0,
    "BF":     24.0,
    "ML":     24.0,
    "BJ":     24.0,
    "TG":     24.0,
    "GN":     24.0,
    "NE":     24.0,
}

# Ratios prudentiels SFD (COBAC EMF 2017 + PARMEC)
_RATIOS_PRUDENTIELS_SFD = {
    "solvabilite_min_pct":     10.0,   # Fonds propres / total risques ≥ 10%
    "liquidite_min_pct":       100.0,  # Actifs liquides / passifs exigibles ≥ 100%
    "transformation_max_pct":   200.0, # Emplois LT / ressources LT ≤ 200%
    "par30_alerte_pct":         5.0,   # PAR>30j ≤ 5% (best practice)
    "par30_critique_pct":       15.0,  # PAR>30j > 15% = situation critique
    "oss_min_pct":              100.0, # Autosuffisance opérationnelle ≥ 100%
}

# Critères de scoring microfinance
_SCORING_MICRO = {
    "capacite_remboursement": {
        "poids": 35,
        "description": "Revenu net / mensualité ≥ 3 (idéal ≥ 5)",
        "criteres": {
            "ratio_>=5": 35, "ratio_4-5": 28, "ratio_3-4": 20,
            "ratio_2-3": 10, "ratio_<2": 0,
        },
    },
    "garanties": {
        "poids": 20,
        "description": "Qualité et couverture des garanties",
        "criteres": {
            "hypotheque_immeuble": 20, "nantissement_vehicule": 15,
            "caution_solidaire_groupe": 12, "depot_garantie": 10,
            "epargne_obligatoire": 8, "sans_garantie": 0,
        },
    },
    "anciennete_client": {
        "poids": 15,
        "description": "Historique avec l'institution",
        "criteres": {
            ">=3ans_bon_historique": 15, "1-3ans_bon": 10,
            "nouveau_recommande": 7, "nouveau_sans_ref": 3,
        },
    },
    "activite_economique": {
        "poids": 15,
        "description": "Stabilité et nature de l'activité",
        "criteres": {
            "salariale_stable": 15, "commerce_etabli": 12,
            "agriculture_perenee": 10, "artisanat_regulier": 8,
            "activite_saisonniere": 5, "sans_activite": 0,
        },
    },
    "historique_credit": {
        "poids": 15,
        "description": "Comportement crédit antérieur",
        "criteres": {
            "remboursements_parfaits": 15, "1-2_retards_mineurs": 10,
            "restructuration_reussie": 6, "incident_rembourse": 3,
            "premier_credit": 8,
        },
    },
}

# Produits types microfinance
_PRODUITS_MICRO = {
    "credit_groupe": {
        "nom": "Crédit solidaire de groupe",
        "duree_max_mois": 12,
        "montant_max_fcfa": 500_000,
        "garantie": "Caution solidaire groupe (5-10 membres)",
        "periodicite": "Hebdomadaire ou bimensuelle",
        "taux_interet_mois": 3.0,
        "methode_calcul": "Taux dégressif ou flat",
    },
    "credit_individuel": {
        "nom": "Crédit individuel micro-entreprise",
        "duree_max_mois": 24,
        "montant_max_fcfa": 5_000_000,
        "garantie": "Nantissement ou caution personnelle",
        "periodicite": "Mensuelle",
        "taux_interet_mois": 2.5,
        "methode_calcul": "Taux dégressif",
    },
    "credit_agricole": {
        "nom": "Crédit agricole de campagne",
        "duree_max_mois": 9,
        "montant_max_fcfa": 2_000_000,
        "garantie": "Warrant agricole ou caution",
        "periodicite": "In fine (remboursement récolte)",
        "taux_interet_mois": 2.0,
        "methode_calcul": "Taux flat",
    },
    "epargne_credit": {
        "nom": "Épargne à terme (DAT)",
        "duree_max_mois": 12,
        "montant_max_fcfa": None,
        "garantie": "N/A — produit d'épargne",
        "periodicite": "À échéance",
        "taux_remuneration_an": 6.0,
        "methode_calcul": "Intérêts à terme échu",
    },
}


# ── Fonctions standalone ───────────────────────────────────────────────────────

def _calculer_par(
    encours_total: float,
    credits_en_retard: list[dict],  # [{montant_echu, jours_retard}]
) -> dict:
    """
    Calcule le Portfolio At Risk (PAR) par tranches de retard.
    PAR = encours des crédits avec retard > N jours / encours total.
    """
    if not encours_total:
        return {"erreur": "Encours total requis"}

    tranches = {
        "par1":  {"seuil": 1,   "montant": 0.0, "nb": 0},
        "par30": {"seuil": 30,  "montant": 0.0, "nb": 0},
        "par60": {"seuil": 60,  "montant": 0.0, "nb": 0},
        "par90": {"seuil": 90,  "montant": 0.0, "nb": 0},
        "par180": {"seuil": 180, "montant": 0.0, "nb": 0},
    }

    for cr in credits_en_retard:
        jours = int(cr.get("jours_retard", 0))
        montant = float(cr.get("montant_echu", 0))
        for key, tranche in tranches.items():
            if jours >= tranche["seuil"]:
                tranche["montant"] += montant
                tranche["nb"] += 1

    resultats_par = {}
    for key, tr in tranches.items():
        taux = tr["montant"] / encours_total * 100
        seuil_alerte = _RATIOS_PRUDENTIELS_SFD["par30_alerte_pct"]
        seuil_critique = _RATIOS_PRUDENTIELS_SFD["par30_critique_pct"]
        if key == "par30":
            statut = "✅ Satisfaisant" if taux <= seuil_alerte else (
                "⚠️ Attention" if taux <= seuil_critique else "❌ Critique"
            )
        else:
            statut = "✅" if taux <= 10 else ("⚠️" if taux <= 20 else "❌")
        resultats_par[key] = {
            "seuil_jours": tr["seuil"],
            "montant": round(tr["montant"], 0),
            "nombre_credits": tr["nb"],
            "taux_pct": round(taux, 2),
            "statut": statut,
        }

    return {
        "encours_total": encours_total,
        "nb_credits_en_retard": len(credits_en_retard),
        "par": resultats_par,
        "qualite_portefeuille": (
            "Bonne" if resultats_par["par30"]["taux_pct"] <= 5 else
            ("Fragile" if resultats_par["par30"]["taux_pct"] <= 15 else "Mauvaise")
        ),
        "reference_cobac": "PAR30 ≤ 5% (best practice) / > 15% = situation critique (COBAC 2017)",
    }


def _scorer_credit_micro(
    revenu_mensuel: float,
    mensualite_demandee: float,
    dette_existante_mensuelle: float,
    type_garantie: str,
    anciennete_client: str,
    type_activite: str,
    historique_credit: str,
) -> dict:
    """Score de crédit microfinance (sur 100 points)."""
    score_total = 0
    details = {}

    # Capacité de remboursement (35 pts)
    revenu_net = revenu_mensuel - dette_existante_mensuelle
    ratio = revenu_net / mensualite_demandee if mensualite_demandee else 0
    if ratio >= 5:
        pts_cap = 35
    elif ratio >= 4:
        pts_cap = 28
    elif ratio >= 3:
        pts_cap = 20
    elif ratio >= 2:
        pts_cap = 10
    else:
        pts_cap = 0
    score_total += pts_cap
    details["capacite_remboursement"] = {
        "points": pts_cap,
        "max": 35,
        "ratio_calculé": round(ratio, 2),
        "interpretation": f"Revenu net {revenu_net:,.0f} / Mensualité {mensualite_demandee:,.0f} = {ratio:.2f}",
    }

    # Garanties (20 pts)
    garantie_pts = {
        "hypotheque_immeuble": 20, "nantissement_vehicule": 15,
        "caution_solidaire_groupe": 12, "depot_garantie": 10,
        "epargne_obligatoire": 8, "sans_garantie": 0,
    }
    pts_gar = garantie_pts.get(type_garantie, 5)
    score_total += pts_gar
    details["garanties"] = {"points": pts_gar, "max": 20, "type": type_garantie}

    # Ancienneté (15 pts)
    anciennete_pts = {
        ">=3ans_bon_historique": 15, "1-3ans_bon": 10,
        "nouveau_recommande": 7, "nouveau_sans_ref": 3,
    }
    pts_anc = anciennete_pts.get(anciennete_client, 5)
    score_total += pts_anc
    details["anciennete_client"] = {"points": pts_anc, "max": 15}

    # Activité (15 pts)
    activite_pts = {
        "salariale_stable": 15, "commerce_etabli": 12,
        "agriculture_perenee": 10, "artisanat_regulier": 8,
        "activite_saisonniere": 5, "sans_activite": 0,
    }
    pts_act = activite_pts.get(type_activite, 5)
    score_total += pts_act
    details["activite_economique"] = {"points": pts_act, "max": 15}

    # Historique crédit (15 pts)
    historique_pts = {
        "remboursements_parfaits": 15, "1-2_retards_mineurs": 10,
        "restructuration_reussie": 6, "incident_rembourse": 3,
        "premier_credit": 8,
    }
    pts_hist = historique_pts.get(historique_credit, 5)
    score_total += pts_hist
    details["historique_credit"] = {"points": pts_hist, "max": 15}

    # Décision
    if score_total >= 75:
        decision = "✅ ACCORDÉ"
        couleur = "vert"
    elif score_total >= 55:
        decision = "⚠️ ACCORDÉ SOUS CONDITIONS"
        couleur = "orange"
    elif score_total >= 40:
        decision = "⚠️ DOSSIER À RENFORCER"
        couleur = "jaune"
    else:
        decision = "❌ REFUSÉ"
        couleur = "rouge"

    return {
        "score_total": score_total,
        "score_max": 100,
        "decision": decision,
        "couleur": couleur,
        "details": details,
        "ratio_endettement_pct": round((mensualite_demandee + dette_existante_mensuelle) / revenu_mensuel * 100, 1) if revenu_mensuel else 0,
        "recommandation": (
            "Dossier solide, accordez le crédit" if score_total >= 75 else
            "Demandez une garantie supplémentaire ou réduisez le montant" if score_total >= 55 else
            "Accompagnement nécessaire avant octroi" if score_total >= 40 else
            "Dossier insuffisant — refusez ou proposez un crédit groupe"
        ),
    }


def _calculer_tableau_micro(
    montant: float,
    taux_mensuel_pct: float,
    duree_mois: int,
    methode: str = "degressif",
    frais_dossier: float = 0,
) -> dict:
    """
    Calcule le tableau d'amortissement d'un microcrédit.
    methode : 'degressif' (taux sur capital restant) ou 'flat' (taux sur capital initial)
    """
    taux = taux_mensuel_pct / 100
    echeances = []

    if methode == "degressif":
        if taux > 0:
            mensualite = montant * taux / (1 - (1 + taux) ** (-duree_mois))
        else:
            mensualite = montant / duree_mois
        capital_restant = montant
        for i in range(1, duree_mois + 1):
            interet = capital_restant * taux
            principal = mensualite - interet
            capital_restant -= principal
            echeances.append({
                "echeance": i,
                "mensualite": round(mensualite, 0),
                "interet": round(interet, 0),
                "principal": round(principal, 0),
                "capital_restant": round(max(0, capital_restant), 0),
            })
        total_interets = sum(e["interet"] for e in echeances)

    else:  # flat
        interet_mensuel = montant * taux
        principal_mensuel = montant / duree_mois
        for i in range(1, duree_mois + 1):
            echeances.append({
                "echeance": i,
                "mensualite": round(principal_mensuel + interet_mensuel, 0),
                "interet": round(interet_mensuel, 0),
                "principal": round(principal_mensuel, 0),
                "capital_restant": round(montant - principal_mensuel * i, 0),
            })
        total_interets = interet_mensuel * duree_mois

    # TEG approximatif (méthode actuarielle simplifiée)
    cout_total = montant + total_interets + frais_dossier
    mensualite_teg = echeances[0]["mensualite"] if echeances else 0
    teg_mensuel = taux  # approximation
    teg_annuel = ((1 + teg_mensuel) ** 12 - 1) * 100

    return {
        "montant": montant,
        "taux_mensuel_pct": taux_mensuel_pct,
        "methode": methode,
        "duree_mois": duree_mois,
        "mensualite": echeances[0]["mensualite"] if echeances else 0,
        "total_remboursable": round(montant + total_interets + frais_dossier, 0),
        "total_interets": round(total_interets, 0),
        "frais_dossier": frais_dossier,
        "teg_annuel_approx_pct": round(teg_annuel, 2),
        "tableau": echeances[:6],  # Premières 6 échéances
        "nb_echeances_totales": len(echeances),
        "cout_credit_pct": round(total_interets / montant * 100, 1) if montant else 0,
    }


def _analyser_bilan_sfd(
    actif_total: float,
    credits_actifs: float,
    actifs_liquides: float,
    fonds_propres: float,
    depots_clients: float,
    emprunts: float,
    produits_exploitation: float,
    charges_exploitation: float,
    charges_provisions: float,
) -> dict:
    """Calcule les ratios de performance d'un SFD selon normes COBAC/BCEAO."""
    ratios = {}

    # Solvabilité : Fonds propres / Total actif pondéré (simplifié)
    solvabilite = fonds_propres / actif_total * 100 if actif_total else 0
    ratios["solvabilite"] = {
        "valeur_pct": round(solvabilite, 2),
        "norme": "≥ 10% (COBAC)",
        "statut": "✅" if solvabilite >= 10 else "❌",
    }

    # Liquidité
    liquidite = actifs_liquides / (depots_clients + emprunts) * 100 if (depots_clients + emprunts) else 0
    ratios["liquidite"] = {
        "valeur_pct": round(liquidite, 2),
        "norme": "≥ 100%",
        "statut": "✅" if liquidite >= 100 else "❌",
    }

    # Autosuffisance opérationnelle (OSS)
    oss = produits_exploitation / (charges_exploitation + charges_provisions) * 100 if (charges_exploitation + charges_provisions) else 0
    ratios["oss"] = {
        "valeur_pct": round(oss, 2),
        "norme": "≥ 100% (autofinancement)",
        "statut": "✅" if oss >= 100 else "❌",
    }

    # Rendement du portefeuille (YOP)
    charges_financieres = produits_exploitation * 0.3  # Approximation
    yop = produits_exploitation / credits_actifs * 100 if credits_actifs else 0
    ratios["rendement_portefeuille"] = {
        "valeur_pct": round(yop, 2),
        "norme": "Variable selon taux pratiqués",
        "statut": "ℹ️",
    }

    # Ratio de couverture dépôts
    couverture_depots = credits_actifs / depots_clients * 100 if depots_clients else 0
    ratios["couverture_depots"] = {
        "valeur_pct": round(couverture_depots, 2),
        "norme": "≤ 200% (transformation)",
        "statut": "✅" if couverture_depots <= 200 else "⚠️",
    }

    # ROA
    resultat_net = produits_exploitation - charges_exploitation - charges_provisions
    roa = resultat_net / actif_total * 100 if actif_total else 0
    ratios["roa"] = {
        "valeur_pct": round(roa, 2),
        "norme": "> 0% (rentabilité positive)",
        "statut": "✅" if roa > 0 else "❌",
    }

    nb_ok = sum(1 for r in ratios.values() if "✅" in str(r.get("statut", "")))
    score_global = nb_ok / len(ratios) * 100

    return {
        "actif_total": actif_total,
        "credits_actifs": credits_actifs,
        "taux_transformation": round(credits_actifs / actif_total * 100, 1) if actif_total else 0,
        "ratios": ratios,
        "resultat_net": round(resultat_net, 0),
        "score_sante_pct": round(score_global, 0),
        "sante_globale": "Solide" if score_global >= 80 else ("Fragile" if score_global >= 50 else "Critique"),
    }


def _concevoir_produit_micro(
    type_produit: str,
    montant_min: float,
    montant_max: float,
    duree_mois: int,
    taux_mensuel_pct: float,
    garantie: str,
    cible: str,
    pays: str = "CM",
) -> dict:
    """Conçoit les caractéristiques d'un produit de microfinance."""
    taux_usuraire = _TAUX_USURAIRE.get(pays, 27.0)
    teg_annuel = ((1 + taux_mensuel_pct / 100) ** 12 - 1) * 100

    template = _PRODUITS_MICRO.get(type_produit, {})

    alertes = []
    if teg_annuel > taux_usuraire:
        alertes.append(f"⚠️ TEG {teg_annuel:.1f}% > taux usuraire {taux_usuraire}% — illégal en {pays}")
    if montant_max > 10_000_000:
        alertes.append("ℹ️ Montant > 10M FCFA — vérifier si ce n'est pas un crédit bancaire")

    # Simulation mensualité typique (montant moyen, méthode dégressif)
    montant_moyen = (montant_min + montant_max) / 2
    taux = taux_mensuel_pct / 100
    if taux > 0:
        mensualite_typique = montant_moyen * taux / (1 - (1 + taux) ** (-duree_mois))
    else:
        mensualite_typique = montant_moyen / duree_mois

    return {
        "type_produit": type_produit,
        "nom_produit": template.get("nom", f"Microcrédit {type_produit}"),
        "montant_min": montant_min,
        "montant_max": montant_max,
        "duree_mois": duree_mois,
        "taux_mensuel_pct": taux_mensuel_pct,
        "teg_annuel_approx_pct": round(teg_annuel, 2),
        "taux_usuraire_pays_pct": taux_usuraire,
        "conforme_taux_usuraire": teg_annuel <= taux_usuraire,
        "garantie_requise": garantie,
        "cible_beneficiaires": cible,
        "pays": pays,
        "mensualite_typique_montant_moyen": round(mensualite_typique, 0),
        "alertes": alertes,
        "caracteristiques_recommandees": {
            "periodicite": template.get("periodicite", "Mensuelle"),
            "methode_calcul": template.get("methode_calcul", "Dégressif"),
            "apport_personnel": "10-20% du montant demandé",
            "assurance_obligatoire": "Vie et invalidité recommandée",
            "fonds_de_solidarite": "1-3% du montant (pour crédits groupes)",
        },
        "conditions_eligibilite_suggerees": [
            "Activité génératrice de revenus depuis ≥ 6 mois",
            f"Revenu mensuel ≥ 3× la mensualité ({round(mensualite_typique * 3, 0):,.0f} FCFA)",
            "Résidence dans la zone d'intervention",
            f"Garantie : {garantie}",
            "Pas d'incident de crédit non soldé",
        ],
    }


# ── Rendus ─────────────────────────────────────────────────────────────────────

def _rendu_par(r: dict) -> str:
    if "erreur" in r:
        return f"Erreur : {r['erreur']}"
    lignes = [
        f"## Portfolio At Risk (PAR)",
        f"Encours total : {r['encours_total']:,.0f} FCFA | Crédits en retard : {r['nb_credits_en_retard']}",
        f"Qualité du portefeuille : **{r['qualite_portefeuille']}**",
        "",
        "| Indicateur | Montant | Nb crédits | Taux | Statut |",
        "|-----------|---------|-----------|------|--------|",
    ]
    for key, val in r["par"].items():
        lignes.append(
            f"| PAR>{val['seuil_jours']}j | {val['montant']:,.0f} | {val['nombre_credits']} | {val['taux_pct']}% | {val['statut']} |"
        )
    lignes.append(f"\n*{r['reference_cobac']}*")
    return "\n".join(lignes)


def _rendu_score_micro(s: dict) -> str:
    lignes = [
        f"## Score de Crédit Microfinance",
        f"**Score : {s['score_total']}/100 — {s['decision']}**",
        f"Taux d'endettement global : {s['ratio_endettement_pct']}%",
        f"Recommandation : {s['recommandation']}",
        "",
        "| Critère | Points obtenus | Max |",
        "|---------|---------------|-----|",
    ]
    for crit, detail in s["details"].items():
        lignes.append(f"| {crit.replace('_', ' ').title()} | {detail['points']} | {detail['max']} |")
    return "\n".join(lignes)


# ══════════════════════════════════════════════════════════════════════════════
# Agent
# ══════════════════════════════════════════════════════════════════════════════

class AgentMicrofinance(AgentProBase):
    """
    Agent IA spécialisé pour les professionnels de la microfinance en Afrique francophone.
    Maîtrise : scoring crédit, PAR, produits SFD, ratios prudentiels COBAC/BCEAO, PARMEC.
    """

    type_agent = TypeAgent.PRO_MICROFINANCE

    def _prompt_systeme_metier(self) -> str:
        return (
            "Tu es un expert senior en microfinance et inclusion financière en Afrique francophone. "
            "Tu maîtrises : les systèmes financiers décentralisés (SFD/IMF/coopératives d'épargne-crédit), "
            "la réglementation COBAC pour les EMF (Établissements de Microfinance) en zone CEMAC, "
            "la loi PARMEC en zone UEMOA, les indicateurs de performance MIX Market "
            "(PAR30, OSS, ROA, rendement du portefeuille), et les techniques d'analyse crédit "
            "adaptées aux populations non bancarisées. "
            "Tu calcules des scores de crédit microfinance, des tableaux d'amortissement, "
            "des Portfolio At Risk et des ratios prudentiels. "
            "Tu connais les produits spécifiques (crédit solidaire, crédit agricole, tontine digitale). "
            "Réponds en français professionnel avec précision technique."
        )

    def _prompt_questions_specifiques(self) -> str:
        return (
            "Questions clés pour l'analyse microfinance :\n"
            "- S'agit-il d'une zone CEMAC ou UEMOA (impacts les ratios et taux usuraires) ?\n"
            "- Quel type de produit de crédit (solidaire, individuel, agricole) ?\n"
            "- Quel est le profil du demandeur (salarié, commerçant, agriculteur) ?\n"
            "- Quelle est la nature des garanties disponibles ?\n"
            "- S'agit-il d'un premier crédit ou d'un renouvellement ?"
        )

    def _outils_metier(self) -> list[dict]:
        return [
            {
                "name": "credit_micro_analyser",
                "description": (
                    "Analyse une demande de microcrédit : scoring, capacité de remboursement, "
                    "ratio d'endettement, décision d'octroi avec recommandations."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "revenu_mensuel": {"type": "number", "description": "Revenu mensuel net du demandeur (FCFA)"},
                        "mensualite_demandee": {"type": "number", "description": "Mensualité du crédit sollicité"},
                        "dette_existante_mensuelle": {"type": "number", "description": "Dettes en cours (mensualités)"},
                        "type_garantie": {"type": "string", "description": "hypotheque_immeuble/nantissement_vehicule/caution_solidaire_groupe/depot_garantie/epargne_obligatoire/sans_garantie"},
                        "anciennete_client": {"type": "string", "description": ">=3ans_bon_historique/1-3ans_bon/nouveau_recommande/nouveau_sans_ref"},
                        "type_activite": {"type": "string", "description": "salariale_stable/commerce_etabli/agriculture_perenee/artisanat_regulier/activite_saisonniere/sans_activite"},
                        "historique_credit": {"type": "string", "description": "remboursements_parfaits/1-2_retards_mineurs/restructuration_reussie/incident_rembourse/premier_credit"},
                    },
                    "required": ["revenu_mensuel", "mensualite_demandee"],
                },
            },
            {
                "name": "par_calculer",
                "description": (
                    "Calcule le Portfolio At Risk (PAR) par tranches de retard "
                    "(PAR1, PAR30, PAR60, PAR90, PAR180) selon normes COBAC/BCEAO."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "encours_total": {"type": "number", "description": "Encours total du portefeuille (FCFA)"},
                        "credits_en_retard": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "montant_echu": {"type": "number"},
                                    "jours_retard": {"type": "integer"},
                                },
                            },
                            "description": "Liste des crédits en impayé avec montant échu et jours de retard",
                        },
                    },
                    "required": ["encours_total"],
                },
            },
            {
                "name": "produit_micro_concevoir",
                "description": (
                    "Conçoit les caractéristiques d'un produit de microfinance : "
                    "taux, durée, garanties, éligibilité. Vérifie la conformité aux taux usuraires COBAC/BCEAO."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "type_produit": {"type": "string", "description": "credit_groupe/credit_individuel/credit_agricole/epargne_credit"},
                        "montant_min": {"type": "number"},
                        "montant_max": {"type": "number"},
                        "duree_mois": {"type": "integer"},
                        "taux_mensuel_pct": {"type": "number", "description": "Taux d'intérêt mensuel en %"},
                        "garantie": {"type": "string"},
                        "cible": {"type": "string", "description": "Cible bénéficiaires"},
                        "pays": {"type": "string", "description": "Code pays (CM, CI, SN, BF...)"},
                    },
                    "required": ["type_produit", "montant_min", "montant_max", "duree_mois", "taux_mensuel_pct"],
                },
            },
            {
                "name": "bilan_sfd_analyser",
                "description": (
                    "Analyse le bilan d'un SFD/IMF : calcule les ratios prudentiels "
                    "(solvabilité, liquidité, OSS, ROA, PAR) selon normes COBAC 2017 / PARMEC."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "actif_total": {"type": "number"},
                        "credits_actifs": {"type": "number"},
                        "actifs_liquides": {"type": "number"},
                        "fonds_propres": {"type": "number"},
                        "depots_clients": {"type": "number"},
                        "emprunts": {"type": "number"},
                        "produits_exploitation": {"type": "number"},
                        "charges_exploitation": {"type": "number"},
                        "charges_provisions": {"type": "number"},
                    },
                    "required": ["actif_total", "credits_actifs", "fonds_propres", "produits_exploitation", "charges_exploitation"],
                },
            },
            {
                "name": "tableau_amortissement_micro",
                "description": (
                    "Calcule le tableau d'amortissement d'un microcrédit "
                    "(méthode dégressif ou flat), avec TEG annuel approximatif."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "montant": {"type": "number", "description": "Montant du crédit (FCFA)"},
                        "taux_mensuel_pct": {"type": "number", "description": "Taux mensuel en %"},
                        "duree_mois": {"type": "integer"},
                        "methode": {"type": "string", "description": "degressif ou flat"},
                        "frais_dossier": {"type": "number", "description": "Frais de dossier (FCFA)"},
                    },
                    "required": ["montant", "taux_mensuel_pct", "duree_mois"],
                },
            },
            {
                "name": "orchestrer_octroi_credit",
                "description": (
                    "Orchestre le workflow complet d'octroi d'un microcrédit : étapes, délais, "
                    "documents requis, scoring intégré et calendrier des décaissements."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "nom_client": {"type": "string", "description": "Nom du demandeur"},
                        "montant_demande": {"type": "number", "description": "Montant demandé (FCFA)"},
                        "revenu_mensuel": {"type": "number"},
                        "type_activite": {"type": "string"},
                        "type_garantie": {"type": "string"},
                        "duree_mois": {"type": "integer"},
                        "taux_mensuel_pct": {"type": "number"},
                        "pays": {"type": "string", "description": "Code pays"},
                    },
                    "required": ["montant_demande", "revenu_mensuel"],
                },
            },
            {
                "name": "analyser_dossier_emprunteur",
                "description": (
                    "Analyse un dossier emprunteur soumis en texte (demande manuscrite, fiche client, "
                    "attestation de revenus) et extrait les informations clés avec évaluation du risque."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "contenu_dossier": {"type": "string", "description": "Texte ou description du dossier emprunteur"},
                        "type_document": {"type": "string", "description": "fiche_client/demande_credit/attestation_revenu/rapport_visite"},
                    },
                    "required": ["contenu_dossier"],
                },
            },
            {
                "name": "calendrier_sfd",
                "description": (
                    "Génère le calendrier réglementaire et opérationnel mensuel d'un SFD : "
                    "reporting COBAC/BCEAO, réunions groupe, échéances remboursement."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pays": {"type": "string", "description": "Code pays (CM, CI, SN, BF...)"},
                        "mois": {"type": "integer", "description": "Mois (1-12)"},
                        "annee": {"type": "integer"},
                        "credits_actifs": {"type": "integer", "description": "Nombre de crédits en cours"},
                    },
                    "required": ["pays"],
                },
            },
        ]

    async def _executer_outil(self, nom_outil: str, params: dict) -> Any:
        if nom_outil == "credit_micro_analyser":
            r = _scorer_credit_micro(
                revenu_mensuel=float(params.get("revenu_mensuel", 0)),
                mensualite_demandee=float(params.get("mensualite_demandee", 0)),
                dette_existante_mensuelle=float(params.get("dette_existante_mensuelle", 0)),
                type_garantie=params.get("type_garantie", "sans_garantie"),
                anciennete_client=params.get("anciennete_client", "nouveau_sans_ref"),
                type_activite=params.get("type_activite", "commerce_etabli"),
                historique_credit=params.get("historique_credit", "premier_credit"),
            )
            return _rendu_score_micro(r)

        if nom_outil == "par_calculer":
            r = _calculer_par(
                encours_total=float(params.get("encours_total", 0)),
                credits_en_retard=params.get("credits_en_retard", []),
            )
            return _rendu_par(r)

        if nom_outil == "produit_micro_concevoir":
            r = _concevoir_produit_micro(
                type_produit=params.get("type_produit", "credit_individuel"),
                montant_min=float(params.get("montant_min", 50_000)),
                montant_max=float(params.get("montant_max", 2_000_000)),
                duree_mois=int(params.get("duree_mois", 12)),
                taux_mensuel_pct=float(params.get("taux_mensuel_pct", 2.5)),
                garantie=params.get("garantie", "caution_solidaire_groupe"),
                cible=params.get("cible", "Micro-entrepreneurs"),
                pays=params.get("pays", "CM"),
            )
            alertes_str = "\n".join(r["alertes"]) if r["alertes"] else "Aucune alerte"
            lignes = [
                f"## Produit Microfinance — {r['nom_produit']}",
                f"Type : {r['type_produit']} | Pays : {r['pays']}",
                f"Montant : {r['montant_min']:,.0f} – {r['montant_max']:,.0f} FCFA | Durée : {r['duree_mois']} mois",
                f"Taux mensuel : {r['taux_mensuel_pct']}% | TEG annuel ≈ {r['teg_annuel_approx_pct']}%",
                f"Taux usuraire {r['pays']} : {r['taux_usuraire_pays_pct']}% → {'✅ Conforme' if r['conforme_taux_usuraire'] else '❌ Non conforme'}",
                f"Mensualité type (montant moyen) : {r['mensualite_typique_montant_moyen']:,.0f} FCFA",
                f"\n### Alertes\n{alertes_str}",
                "\n### Conditions d'éligibilité",
            ]
            for c in r["conditions_eligibilite_suggerees"]:
                lignes.append(f"  • {c}")
            return "\n".join(lignes)

        if nom_outil == "bilan_sfd_analyser":
            r = _analyser_bilan_sfd(
                actif_total=float(params.get("actif_total", 1)),
                credits_actifs=float(params.get("credits_actifs", 0)),
                actifs_liquides=float(params.get("actifs_liquides", 0)),
                fonds_propres=float(params.get("fonds_propres", 0)),
                depots_clients=float(params.get("depots_clients", 0)),
                emprunts=float(params.get("emprunts", 0)),
                produits_exploitation=float(params.get("produits_exploitation", 1)),
                charges_exploitation=float(params.get("charges_exploitation", 0)),
                charges_provisions=float(params.get("charges_provisions", 0)),
            )
            lignes = [
                f"## Analyse Bilan SFD",
                f"Actif total : {r['actif_total']:,.0f} FCFA | Taux transformation : {r['taux_transformation']}%",
                f"Résultat net : {r['resultat_net']:,.0f} FCFA",
                f"Santé globale : **{r['sante_globale']}** (score {r['score_sante_pct']}%)",
                "",
                "| Ratio | Valeur | Norme | Statut |",
                "|-------|--------|-------|--------|",
            ]
            for nom, rat in r["ratios"].items():
                lignes.append(f"| {nom.replace('_', ' ').title()} | {rat['valeur_pct']}% | {rat['norme']} | {rat['statut']} |")
            return "\n".join(lignes)

        if nom_outil == "tableau_amortissement_micro":
            r = _calculer_tableau_micro(
                montant=float(params.get("montant", 0)),
                taux_mensuel_pct=float(params.get("taux_mensuel_pct", 2.5)),
                duree_mois=int(params.get("duree_mois", 12)),
                methode=params.get("methode", "degressif"),
                frais_dossier=float(params.get("frais_dossier", 0)),
            )
            lignes = [
                f"## Tableau d'Amortissement Microcrédit",
                f"Montant : {r['montant']:,.0f} FCFA | Taux : {r['taux_mensuel_pct']}%/mois | Durée : {r['duree_mois']} mois | Méthode : {r['methode']}",
                f"Mensualité : {r['mensualite']:,.0f} FCFA | Total remboursable : {r['total_remboursable']:,.0f} | Intérêts : {r['total_interets']:,.0f}",
                f"TEG annuel ≈ {r['teg_annuel_approx_pct']}% | Coût du crédit : {r['cout_credit_pct']}% du capital",
                "",
                "| Éch. | Mensualité | Intérêt | Capital | Capital restant |",
                "|------|-----------|---------|---------|-----------------|",
            ]
            for e in r["tableau"]:
                lignes.append(
                    f"| {e['echeance']} | {e['mensualite']:,.0f} | {e['interet']:,.0f} | {e['principal']:,.0f} | {e['capital_restant']:,.0f} |"
                )
            if r["nb_echeances_totales"] > 6:
                lignes.append(f"| ... | ({r['nb_echeances_totales'] - 6} autres échéances) | | | |")
            return "\n".join(lignes)

        if nom_outil == "orchestrer_octroi_credit":
            return _orchestrer_octroi_credit(params)

        if nom_outil == "analyser_dossier_emprunteur":
            from core.ia_client import ModeIA, ia_client
            prompt = _prompt_analyse_dossier_emprunteur(params)
            rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
            return rep.contenu

        if nom_outil == "calendrier_sfd":
            return _calendrier_sfd(params)

        return f"Outil '{nom_outil}' non reconnu."


# ---------------------------------------------------------------------------
# Fonctions standalone — nouvelles automatisations microfinance
# ---------------------------------------------------------------------------

def _orchestrer_octroi_credit(params: dict) -> str:
    nom_client = params.get("nom_client", "le demandeur")
    montant = float(params.get("montant_demande", 0))
    revenu = float(params.get("revenu_mensuel", 0))
    duree = int(params.get("duree_mois", 12))
    taux = float(params.get("taux_mensuel_pct", 2.5))
    garantie = params.get("type_garantie", "caution_solidaire_groupe")
    pays = params.get("pays", "CM")

    # Calcul mensualité dégressif
    r = taux / 100
    if r > 0:
        mensualite = montant * r * (1 + r) ** duree / ((1 + r) ** duree - 1)
    else:
        mensualite = montant / duree
    ratio_endettement = (mensualite / revenu * 100) if revenu > 0 else 999
    accord = ratio_endettement <= 33

    # Délai CNPS déclaration (si employé, J+8)
    delai_deblocage = 3 if accord else 0

    lignes = [
        f"## Workflow Octroi Crédit — {nom_client}",
        f"Montant : {montant:,.0f} FCFA | Durée : {duree} mois | Taux : {taux}%/mois",
        f"Mensualité estimée : {mensualite:,.0f} FCFA | Ratio endettement : {ratio_endettement:.1f}%",
        f"Décision préliminaire : {'✅ FAVORABLE' if accord else '⚠️ RATIO TROP ÉLEVÉ (>33%)'}",
        "",
        "### Étape 1 — Réception dossier (J0)",
        "  ✅ Fiche de demande signée par le client",
        "  ✅ CNI / pièce d'identité valide",
        "  ✅ Justificatif de revenus (3 derniers mois)",
        f"  ✅ Document garantie : {garantie.replace('_', ' ')}",
        "  ✅ Photo et fiche de visite terrain",
        "",
        "### Étape 2 — Scoring et analyse (J+1 à J+2)",
        "  ✅ Calcul ratio d'endettement et capacité remboursement",
        "  ✅ Vérification centrale des risques (si disponible)",
        "  ✅ Vérification antécédents de crédit en interne",
        "  ✅ Rédaction fiche d'analyse par l'agent de crédit",
        "",
        "### Étape 3 — Comité de crédit (J+2 à J+3)",
        "  ✅ Présentation dossier en comité",
        "  ✅ Décision : accord / refus / accord partiel",
        "  ✅ Notification écrite au client",
        "",
        f"### Étape 4 — Déblocage (J+{delai_deblocage + 3} si accord)",
        "  ✅ Signature contrat de prêt",
        "  ✅ Constitution et validation des garanties",
        "  ✅ Décaissement (espèces / mobile money / compte)",
        "  ✅ Enregistrement dans le système SIG",
        "",
        "### Étape 5 — Suivi remboursement",
        f"  ✅ Paramétrage des {duree} échéances dans le SIG",
        "  ✅ Alerte J-3 avant chaque échéance (SMS/appel)",
        "  ✅ Visite terrain si retard > 7 jours",
        "",
        f"Pays : {pays} | Taux usuraire max : {_TAUX_USURAIRE.get(pays, 27)}%",
    ]
    return "\n".join(lignes)


def _prompt_analyse_dossier_emprunteur(params: dict) -> str:
    contenu = params.get("contenu_dossier", "")
    type_doc = params.get("type_document", "fiche_client")

    types_labels = {
        "fiche_client": "fiche client / demande de crédit",
        "demande_credit": "demande de crédit manuscrite",
        "attestation_revenu": "attestation ou justificatif de revenus",
        "rapport_visite": "rapport de visite terrain",
    }
    label = types_labels.get(type_doc, type_doc)

    return f"""Tu es un analyste crédit spécialisé en microfinance africaine (COBAC/BCEAO).

Analyse ce {label} et fournis une évaluation structurée pour décision d'octroi.

DOCUMENT :
{contenu}

ANALYSE REQUISE :
1. **Informations client** — identité, activité, localisation
2. **Capacité de remboursement** — revenus déclarés, charges, ratio endettement estimé
3. **Profil de risque** — historique si mentionné, stabilité activité, garanties
4. **Documents manquants** — liste des pièces absentes du dossier
5. **Recommandation** — APPROUVER / APPROUVER SOUS CONDITIONS / REFUSER avec justification
6. **Conditions suggérées** — montant, durée, taux, garantie si approbation conditionnelle

Format : structuré, concis, orienté décision."""


def _calendrier_sfd(params: dict) -> str:
    from datetime import date
    pays = params.get("pays", "CM")
    mois = int(params.get("mois", date.today().month))
    annee = int(params.get("annee", date.today().year))
    credits_actifs = int(params.get("credits_actifs", 0))

    noms_mois = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
                 "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
    nom_mois = noms_mois[mois] if 1 <= mois <= 12 else f"Mois {mois}"

    zone = "CEMAC" if pays in ("CM", "GA", "CG", "CF", "TD", "GQ") else "UEMOA"

    echeances_cemac = [
        ("J+10 du mois", "Transmission situation hebdomadaire à la COBAC"),
        ("J+15 du mois", "Déclaration mensuelle de l'encours portefeuille"),
        ("J+20 du mois", "Rapport mensuel au Conseil d'Administration"),
        ("J+30 du trimestre", "Rapport trimestriel COBAC (états financiers)"),
    ]
    echeances_uemoa = [
        ("J+15 du mois", "Déclaration mensuelle BCEAO-SFD"),
        ("J+20 du mois", "Rapport mensuel à l'organe faîtier"),
        ("J+30 du trimestre", "États financiers trimestriels BCEAO"),
        ("31 mars (annuel)", "États financiers annuels certifiés"),
    ]

    echeances = echeances_cemac if zone == "CEMAC" else echeances_uemoa

    lignes = [
        f"## Calendrier SFD — {nom_mois} {annee} | {pays} ({zone})",
        f"Crédits actifs en portefeuille : {credits_actifs}",
        "",
        "### Obligations réglementaires",
    ]
    for date_ec, desc in echeances:
        lignes.append(f"  📅 {date_ec} : {desc}")

    lignes += [
        "",
        "### Opérations internes recommandées",
        f"  📅 J+5 : Rapprochement caisse et extraction des impayés",
        f"  📅 J+7 : Réunion groupes solidaires (si crédit groupe)",
        f"  📅 J+10 : Calcul PAR30 du mois précédent",
        f"  📅 J+15 : Suivi relances clients en retard > 7 jours",
        f"  📅 J+20 : Revue portefeuille avec directeur",
        f"  📅 J+25 : Provisionnement créances douteuses si nécessaire",
    ]
    if credits_actifs > 0:
        montant_echeances_estim = credits_actifs * 85_000  # estimation mensualité moyenne
        lignes.append(f"\nEstimation encaissements attendus ce mois : ~{montant_echeances_estim:,.0f} FCFA")

    return "\n".join(lignes)
