"""
AgentDRH — Agent IA spécialisé pour les DRH africains.

Outils métier :
  - contrat_travail_rediger   : Rédaction de contrats de travail OHADA
  - paie_calculer             : Calcul de bulletin de paie (CNSS/CNPS, IRPP)
  - conge_calculer            : Calcul droits aux congés et allocations
  - licenciement_assister     : Assistance procédure disciplinaire/licenciement
  - hrreport_generer          : Rapport RH (effectifs, turnover, masse salariale)

Référentiels :
  - Code du travail (CM, CI, SN, BF, GA…)
  - Convention collective par secteur
  - OHADA Acte Uniforme sur le Droit du Travail
  - CNPS / CNSS / IPRES / CNRPS réglementation

PATTERNS YUKPOASSURANCE :
  - Calculs déterministes en fonctions standalone (hors classe)
  - type_agent = TypeAgent.PRO_DRH
  - _necessite_validation() → hérité de AgentProBase (retourne False)
  - _prompt_questions_specifiques() implémenté
  - Barème IRPP aligné avec agent_rh.py
"""
from __future__ import annotations

import logging
from math import inf

from core.agent_orchestrateur import TypeAgent
from modules.pro.agent_pro_base import AgentProBase
from modules.rag.sources_registry import SECTEURS_CC

logger = logging.getLogger("yukpo_assurance.pro.agent_drh")

# ══════════════════════════════════════════════════════════════════════════════
# Mapping secteur → doc_ids conventions collectives (priorité par ordre)
# ══════════════════════════════════════════════════════════════════════════════

# Pour chaque pays, liste ordonnée : CC sectorielle si disponible, sinon CCNI
_CC_PAR_SECTEUR_ET_PAYS: dict[str, dict[str, list[str]]] = {
    "CM": {
        "btp":       ["cc_cm_btp",        "cc_cm_interpro"],
        "banque":    ["cc_cm_banques",     "cc_cm_interpro"],
        "assurance": ["cc_cm_assurances",  "cc_cm_banques", "cc_cm_interpro"],
        "commerce":  ["cc_cm_commerce",    "cc_cm_interpro"],
        "default":   ["cc_cm_interpro"],
    },
    "CI": {
        "banque":    ["cc_ci_banques",  "cc_ci_interpro"],
        "assurance": ["cc_ci_banques",  "cc_ci_interpro"],
        "commerce":  ["cc_ci_commerce", "cc_ci_interpro"],
        "default":   ["cc_ci_interpro"],
    },
    "SN": {
        "banque":    ["cc_sn_banques",    "cc_sn_interpro"],
        "assurance": ["cc_sn_assurances", "cc_sn_banques", "cc_sn_interpro"],
        "commerce":  ["cc_sn_commerce",   "cc_sn_interpro"],
        "btp":       ["cc_sn_btp",        "cc_sn_interpro"],
        "hotellerie": ["cc_sn_hotellerie", "cc_sn_interpro"],
        "default":   ["cc_sn_interpro"],
    },
    "BF": {"default": ["cc_bf_interpro"]},
    "TG": {
        "banque":       ["cc_tg_banques",    "cc_tg_interpro"],
        "assurance":    ["cc_tg_assurances", "cc_tg_banques", "cc_tg_interpro"],
        "btp":          ["cc_tg_btp",        "cc_tg_interpro"],
        "mines_petrole": ["cc_tg_mines",     "cc_tg_interpro"],
        "default":      ["cc_tg_interpro"],
    },
    "BJ": {"default": ["cc_bj_interpro"]},
    "ML": {"default": ["cc_ml_interpro"]},
    "NE": {
        "banque":    ["cc_ne_banques", "cc_ne_interpro"],
        "assurance": ["cc_ne_banques", "cc_ne_interpro"],
        "default":   ["cc_ne_interpro"],
    },
    "GA": {
        "mines_petrole": ["cc_ga_mines_petrole", "cc_ga_interpro"],
        "default":       ["cc_ga_interpro"],
    },
    "CG": {"default": ["cc_cg_interpro"]},
    "CD": {"default": ["cc_cd_interpro"]},
    "GN": {"default": ["cc_gn_interpro"]},
    "TD": {"default": ["cc_td_interpro"]},
}


def _detecter_secteur(message: str) -> str | None:
    """
    Détecte le secteur d'activité depuis un message RH.
    Retourne la clé secteur de SECTEURS_CC, ou None si non détecté.
    """
    msg_lower = message.lower()
    # Ordre de priorité : secteurs spécifiques avant "interprofessionnel"
    for secteur, mots_cles in SECTEURS_CC.items():
        if secteur == "interprofessionnel":
            continue
        if any(mot in msg_lower for mot in mots_cles):
            return secteur
    return None


def _cc_doc_ids_pour(pays: str, secteur: str | None) -> list[str]:
    """
    Retourne la liste ordonnée des doc_ids CC à interroger
    pour un pays et un secteur donnés.
    """
    mapping = _CC_PAR_SECTEUR_ET_PAYS.get(pays.upper(), {})
    if secteur and secteur in mapping:
        return mapping[secteur]
    return mapping.get("default", [f"cc_{pays.lower()}_interpro"])

# ══════════════════════════════════════════════════════════════════════════════
# Constantes sociales — Source : Code du travail / CNPS officiels
# ══════════════════════════════════════════════════════════════════════════════

_SMIG = {
    "CM": 41_875,   # Cameroun — arrêté 2014
    "CI": 60_000,   # Côte d'Ivoire
    "SN": 58_900,   # Sénégal
    "BF": 34_664,   # Burkina Faso
    "GA": 150_000,  # Gabon
    "CG": 50_000,   # Congo Brazzaville
    "ML": 40_000,   # Mali
    "TG": 35_000,   # Togo
}

# Taux de cotisations sociales par pays
_COTISATIONS = {
    "CM": {
        "cnps_sal":    0.042,   # CNPS salarié (plafond 750 000 FCFA)
        "cnps_pat":    0.112,   # CNPS patronal (allocations familiales + retraite)
        "cfc_sal":     0.01,    # Crédit Foncier salarié
        "cfc_pat":     0.01,    # Crédit Foncier patronal
        "fne_pat":     0.01,    # FNE patronal
        "plafond":     750_000,
    },
    "CI": {
        "cnps_sal":    0.036,
        "cnps_pat":    0.14,
        "plafond":     None,    # Pas de plafond CI
    },
    "SN": {
        "ipres_sal":   0.0556,  # IPRES retraite salarié
        "css_sal":     0.035,   # CSS santé salarié
        "ipres_pat":   0.084,
        "css_pat":     0.07,
        "plafond":     None,
    },
    "BF": {
        "cnss_sal":    0.056,
        "cnss_pat":    0.16,
        "plafond":     None,
    },
    "GA": {
        "cnss_sal":    0.025,
        "cnamgs_sal":  0.025,   # Caisse nationale d'assurance maladie
        "cnss_pat":    0.20,
        "cnamgs_pat":  0.045,
        "plafond":     None,
    },
}

# Barème IRPP progressif — Cameroun (aligné avec agent_rh.py)
# Source : CGI Cameroun, articles 69-72
_IRPP_TRANCHES_CM: list[tuple[float, float, float]] = [
    (0,           2_000_000,  0.000),
    (2_000_000,   3_000_000,  0.100),
    (3_000_000,   5_000_000,  0.150),
    (5_000_000,  10_000_000,  0.250),
    (10_000_000, 15_000_000,  0.350),
    (15_000_000,         inf, 0.385),
]

# Préavis légaux selon ancienneté (généralisé Afrique francophone)
_PREAVIS: list[tuple[float, str]] = [
    (0,   "15 jours"),
    (1,   "1 mois"),
    (5,   "2 mois"),
    (10,  "3 mois"),
]

# Jours de congés légaux annuels par pays
_CONGES_BASE = {
    "CM": 24, "CI": 24, "SN": 24, "BF": 24,
    "GA": 30, "CG": 26, "ML": 24, "TG": 24,
}


# ══════════════════════════════════════════════════════════════════════════════
# Fonctions de calcul standalone — déterministes, testables hors classe
# ══════════════════════════════════════════════════════════════════════════════

def _taux_charges_sal(pays: str) -> float:
    """Somme des taux de cotisations salariales du pays."""
    cot = _COTISATIONS.get(pays, {})
    return sum(v for k, v in cot.items() if "sal" in k and k != "plafond")


def _taux_charges_pat(pays: str) -> float:
    """Somme des taux de cotisations patronales du pays."""
    cot = _COTISATIONS.get(pays, {})
    return sum(v for k, v in cot.items() if "pat" in k and k != "plafond")


def _plafond_cotisations(pays: str) -> float | None:
    """Plafond mensuel de cotisations sociales (None = pas de plafond)."""
    return _COTISATIONS.get(pays, {}).get("plafond")


def _calculer_irpp_annuel(revenu_annuel_imposable: float, pays: str = "CM") -> float:
    """
    Barème IRPP progressif annuel.
    Pays supportés : CM (tranches exactes CGI).
    Autres pays : approximation au taux moyen de 20%.
    """
    if pays != "CM":
        # Approximation pour pays sans barème implémenté
        return max(0.0, revenu_annuel_imposable * 0.20)

    irpp = 0.0
    for borne_inf, borne_sup, taux in _IRPP_TRANCHES_CM:
        if revenu_annuel_imposable <= borne_inf:
            break
        irpp += (min(revenu_annuel_imposable, borne_sup) - borne_inf) * taux
    return round(irpp, 2)


def _calculer_bulletin_paie(
    salaire_brut:  float,
    pays:          str,
    anciennete_an: float = 0,
    nb_enfants:    int   = 0,
    avantages:     dict  = None,
    primes:        dict  = None,
) -> dict:
    """
    Calcule les composantes d'un bulletin de paie.
    Retourne un dictionnaire structuré avec tous les éléments.
    """
    avantages = avantages or {}
    primes    = primes    or {}

    total_primes     = sum(float(v) for v in primes.values())
    total_avantages  = sum(float(v) for v in avantages.values())

    # Indemnité d'ancienneté (2% par tranche de 5 ans — pratique OHADA courante)
    indemnite_anciennete = 0.0
    if anciennete_an >= 5:
        indemnite_anciennete = salaire_brut * 0.02 * (anciennete_an // 5)

    brut_total = salaire_brut + total_primes + total_avantages + indemnite_anciennete

    # Charges salariales — assiette plafonnée si applicable
    plafond    = _plafond_cotisations(pays)
    assiette   = min(brut_total, plafond) if plafond else brut_total
    taux_sal   = _taux_charges_sal(pays)
    charges_sal = round(assiette * taux_sal, 0)

    # Revenu imposable IRPP = brut - charges sal - 30% frais professionnels
    deduction_fp        = brut_total * 0.30
    revenu_imp_mensuel  = max(0.0, brut_total - charges_sal - deduction_fp)
    irpp_mensuel        = round(_calculer_irpp_annuel(revenu_imp_mensuel * 12, pays) / 12, 0)

    salaire_net = round(brut_total - charges_sal - irpp_mensuel, 0)

    # Charges patronales
    taux_pat     = _taux_charges_pat(pays)
    charges_pat  = round(brut_total * taux_pat, 0)
    cout_employeur = brut_total + charges_pat

    return {
        "pays":                pays,
        "salaire_brut":        salaire_brut,
        "total_primes":        total_primes,
        "total_avantages":     total_avantages,
        "indemnite_anciennete": indemnite_anciennete,
        "brut_total":          brut_total,
        "taux_sal_pct":        round(taux_sal * 100, 3),
        "assiette_cotis":      assiette,
        "charges_sal":         charges_sal,
        "irpp_mensuel":        irpp_mensuel,
        "salaire_net":         salaire_net,
        "taux_pat_pct":        round(taux_pat * 100, 3),
        "charges_pat":         charges_pat,
        "cout_employeur":      cout_employeur,
    }


def _calculer_indemnite_licenciement(
    salaire_brut: float,
    anciennete_an: float,
    pays: str = "CM",
) -> dict:
    """
    Calcule les indemnités légales de licenciement.
    Source : Code du travail CM art. 40 et suivants.
    """
    # Indemnité de licenciement — barème OHADA/CM
    # Tranches : 0-5 ans : 20% ; 5-10 ans : 25% ; > 10 ans : 30%
    ind_lic = 0.0
    if anciennete_an > 0:
        t1 = min(anciennete_an, 5)
        t2 = max(0, min(anciennete_an - 5, 5))
        t3 = max(0, anciennete_an - 10)
        ind_lic = salaire_brut * (t1 * 0.20 + t2 * 0.25 + t3 * 0.30)

    # Préavis
    preavis_libelle = "15 jours"
    preavis_mois    = 0.5
    for seuil, libelle in _PREAVIS:
        if anciennete_an >= seuil:
            preavis_libelle = libelle
            preavis_mois    = {"15 jours": 0.5, "1 mois": 1, "2 mois": 2, "3 mois": 3}.get(libelle, 1)

    ind_preavis = salaire_brut * preavis_mois

    # Congés non pris (estimation 1 an)
    nb_jours_cong = _CONGES_BASE.get(pays, 24)
    ind_conges    = round(salaire_brut / 30 * nb_jours_cong, 0)

    total = round(ind_lic + ind_preavis + ind_conges, 0)

    return {
        "anciennete_an":    anciennete_an,
        "salaire_brut":     salaire_brut,
        "ind_licenciement": round(ind_lic, 0),
        "preavis":          preavis_libelle,
        "ind_preavis":      round(ind_preavis, 0),
        "conges_non_pris":  ind_conges,
        "total_indemnites": total,
    }


def _calculer_conges_payes(
    salaire_brut:  float,
    anciennete_an: float,
    pays:          str,
    jours_acquis:  float | None = None,
) -> dict:
    """Calcule les droits et l'indemnité de congés payés."""
    base = _CONGES_BASE.get(pays, 24)
    maj  = int(anciennete_an // 5) * 2  # 2 j supplémentaires par tranche de 5 ans
    total_jours = base + maj

    if jours_acquis is not None:
        total_jours = jours_acquis

    # Méthode 1/10e (10% des salaires perçus sur la période de référence)
    ind_dixieme = round(salaire_brut * 12 * 0.10 / 12 * (total_jours / 30), 0)
    # Méthode maintien salaire
    ind_maintien = round(salaire_brut / 30 * total_jours, 0)
    # Retenir la plus favorable
    indemnite = max(ind_dixieme, ind_maintien)

    return {
        "pays":         pays,
        "jours_base":   base,
        "maj_anc":      maj,
        "total_jours":  total_jours,
        "ind_dixieme":  ind_dixieme,
        "ind_maintien": ind_maintien,
        "indemnite":    indemnite,
    }


def _rendu_bulletin(b: dict) -> str:
    """Formate le dict bulletin de paie en texte."""
    sep = "─" * 52
    lignes = [f"BULLETIN DE PAIE SIMULÉ — {b['pays']}\n", sep]
    lignes.append(f"{'Salaire brut':35} : {b['salaire_brut']:>12,.0f} FCFA")
    if b["total_primes"]:
        lignes.append(f"{'Primes':35} : {b['total_primes']:>12,.0f} FCFA")
    if b["total_avantages"]:
        lignes.append(f"{'Avantages en nature':35} : {b['total_avantages']:>12,.0f} FCFA")
    if b["indemnite_anciennete"]:
        lignes.append(f"{'Indemnité ancienneté':35} : {b['indemnite_anciennete']:>12,.0f} FCFA")
    lignes.append(sep)
    lignes.append(f"{'Brut total':35} : {b['brut_total']:>12,.0f} FCFA")
    lignes.append(
        f"{'Cotisations sal. (' + str(b['taux_sal_pct']) + '%)':35}"
        f" : -{b['charges_sal']:>11,.0f} FCFA"
    )
    if b["assiette_cotis"] < b["brut_total"]:
        lignes.append(f"  (assiette plafonnée : {b['assiette_cotis']:,.0f} FCFA)")
    lignes.append(f"{'IRPP mensuel estimé':35} : -{b['irpp_mensuel']:>11,.0f} FCFA")
    lignes.append("═" * 52)
    lignes.append(f"{'SALAIRE NET':35} : {b['salaire_net']:>12,.0f} FCFA")
    lignes.append("")
    lignes.append(
        f"{'Charges patronales (' + str(b['taux_pat_pct']) + '%)':35}"
        f" :  {b['charges_pat']:>12,.0f} FCFA"
    )
    lignes.append(f"{'COÛT TOTAL EMPLOYEUR':35} :  {b['cout_employeur']:>12,.0f} FCFA")
    lignes.append("\n⚠️  Simulation indicative — Vérifier les taux CNPS/CNSS officiels en vigueur.")
    return "\n".join(lignes)


def _rendu_indemnites_lic(r: dict) -> str:
    """Formate les indemnités de licenciement en texte."""
    lignes = [
        "INDEMNITÉS DE LICENCIEMENT\n",
        f"Ancienneté          : {r['anciennete_an']:.1f} ans",
        f"Salaire brut mensuel: {r['salaire_brut']:,.0f} FCFA\n",
        f"Indemnité légale    : {r['ind_licenciement']:>12,.0f} FCFA",
        f"Indemnité préavis   : {r['ind_preavis']:>12,.0f} FCFA  ({r['preavis']})",
        f"Congés non pris     : {r['conges_non_pris']:>12,.0f} FCFA",
        "─" * 48,
        f"TOTAL ESTIMÉ        : {r['total_indemnites']:>12,.0f} FCFA",
        "\n⚠️  Calcul indicatif selon barème Code du travail — faire valider par un juriste.",
    ]
    return "\n".join(lignes)


def _rendu_conges(c: dict) -> str:
    """Formate le calcul de congés en texte."""
    lignes = [
        f"CONGÉS PAYÉS — {c['pays']}\n",
        f"Jours base légale   : {c['jours_base']} j/an",
        f"Majoration anc.     : +{c['maj_anc']} j  ({c['total_jours']} j total)\n",
        "INDEMNITÉ DE CONGÉ :",
        f"  Méthode 1/10e     : {c['ind_dixieme']:,.0f} FCFA",
        f"  Méthode maintien  : {c['ind_maintien']:,.0f} FCFA",
        f"  → Montant retenu  : {c['indemnite']:,.0f} FCFA  (plus favorable)",
    ]
    return "\n".join(lignes)


# ══════════════════════════════════════════════════════════════════════════════
# Classe AgentDRH
# ══════════════════════════════════════════════════════════════════════════════

class AgentDRH(AgentProBase):
    """Agent spécialisé Ressources Humaines — droit social africain."""

    type_agent = TypeAgent.PRO_DRH

    # ── Prompt ──────────────────────────────────────────────────────────────

    def _system_prompt(self) -> str:
        base = super()._system_prompt()
        return base + """

EXPERTISE RESSOURCES HUMAINES :
Tu es un DRH expert en droit social africain francophone.

COMPÉTENCES CLÉS :
- Code du travail africain : contrats, rupture, disciplinaire, conditions de travail
- Paie et charges sociales : CNPS (CM), CNSS (CI/BF), IPRES (SN), IRPP sur salaires
- Congés payés, maternité, maladie, accidents du travail
- Recrutement, gestion des compétences, GPEC
- Relations sociales : délégués du personnel, syndicats, négociation collective
- Droit disciplinaire : avertissement, mise à pied, licenciement

CONVENTIONS COLLECTIVES — RÈGLE D'OR :
La convention collective sectorielle prime sur la loi dès qu'elle est plus favorable au salarié.
Hiérarchie des normes : Loi → Convention collective → Accord d'entreprise → Contrat individuel.

Quand tu réponds sur : salaires minima, primes, classifications, congés supplémentaires,
période d'essai, préavis, indemnités de rupture — TOUJOURS vérifier si la convention collective
du secteur prévoit des dispositions plus favorables que le code du travail.

SECTEURS et leurs CC spécifiques :
- BTP : classifications ouvriers/techniciens/cadres, primes chantier, indemnités déplacement
- Banques/Assurances : salaires minima par catégorie, 13e mois, primes de rendement, congés supplémentaires
- Commerce : classifications employés de commerce, horaires décalés, primes dimanche
- Mines/Pétrole : primes de risque, logement de fonction, régimes spéciaux retraite
- Hôtellerie/Restauration : service compris, pourboires, travail de nuit, repos hebdomadaire
- Agriculture : hébergement, transport, primes saisonnières, jours fériés spéciaux
- Transport/Logistique : indemnités de conduite, durée conduite, repos entre trajets

RÈGLES IMPORTANTES :
- Toujours citer les articles du code du travail ET les articles de la CC applicables
- Préciser les délais légaux (préavis, entretien préalable, délégués du personnel)
- Souligner les risques de contentieux prud'homal
- Recommander la consultation d'un juriste pour les procédures disciplinaires complexes
- SMIG minimum : vérifier systématiquement + comparer avec le minimum CC du secteur
- Si secteur non précisé : répondre selon CCNI mais signaler l'importance du secteur
"""

    def _prompt_questions_specifiques(self) -> str:
        return (
            "- Si le pays d'exercice est inconnu : demander (impacte SMIG, cotisations, barèmes IRPP, CC applicable)\n"
            "- Si le secteur d'activité est inconnu : demander (BTP, banque, commerce, industrie, transport, mines, santé…)\n"
            "  → Le secteur détermine la convention collective applicable et ses avantages spécifiques\n"
            "- Si calcul de paie et salaire brut non précisé : demander le salaire brut mensuel\n"
            "- Si procédure disciplinaire et ancienneté non précisée : demander l'ancienneté\n"
            "- Si contrat et type (CDI/CDD/stage) non précisé : demander le type de contrat\n"
            "- Si classification professionnelle inconnue (catégorie, échelon) : demander\n"
            "  → Impacte le salaire minimum CC, les primes et avantages sectoriels\n"
            "- Ne jamais redemander des informations déjà présentes dans le profil ou la conversation"
        )

    # ── Outils métier ────────────────────────────────────────────────────────

    def _outils_metier(self) -> list[dict]:
        return [
            {
                "name": "contrat_travail_rediger",
                "description": (
                    "Rédige ou analyse un contrat de travail selon le code du travail "
                    "du pays spécifié. Vérifie les clauses obligatoires et les risques juridiques."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "type_contrat": {
                            "type": "string",
                            "description": "cdi | cdd | stage | apprentissage | temps_partiel",
                        },
                        "pays": {"type": "string"},
                        "poste": {"type": "string", "description": "Intitulé du poste"},
                        "salaire_brut": {
                            "type": "number",
                            "description": "Salaire brut mensuel en FCFA",
                        },
                        "duree": {
                            "type": "string",
                            "description": "Durée pour CDD/stage, ex: '6 mois'",
                        },
                        "clauses_spec": {
                            "type": "array",
                            "description": "Clauses spéciales (non-concurrence, mobilité, tél-travail…)",
                        },
                        "action": {
                            "type": "string",
                            "description": "rediger | verifier | analyser",
                        },
                        "contenu": {
                            "type": "string",
                            "description": "Contenu du contrat à analyser (si action=analyser)",
                        },
                    },
                    "required": ["type_contrat", "pays"],
                },
            },
            {
                "name": "paie_calculer",
                "description": (
                    "Calcule un bulletin de paie complet selon la législation sociale du pays : "
                    "salaire net, cotisations sociales (CNPS/CNSS/IPRES), IRPP sur salaires."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "salaire_brut":  {"type": "number",  "description": "Salaire brut mensuel en FCFA"},
                        "pays":          {"type": "string"},
                        "anciennete_an": {"type": "number",  "description": "Ancienneté en années"},
                        "nb_enfants":    {"type": "integer", "description": "Nombre d'enfants à charge"},
                        "avantages":     {
                            "type": "object",
                            "description": "Avantages en nature : {'logement': 50000, 'transport': 20000}",
                        },
                        "primes": {
                            "type": "object",
                            "description": "Primes du mois : {'prime_rendement': 30000}",
                        },
                    },
                    "required": ["salaire_brut", "pays"],
                },
            },
            {
                "name": "conge_calculer",
                "description": (
                    "Calcule les droits aux congés payés et l'indemnité de congé "
                    "selon le code du travail du pays (méthodes 1/10e et maintien salaire)."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "salaire_brut":  {"type": "number"},
                        "anciennete_an": {"type": "number",  "description": "Ancienneté en années"},
                        "jours_acquis":  {"type": "number",  "description": "Jours acquis si connus"},
                        "pays":          {"type": "string"},
                    },
                    "required": ["salaire_brut", "pays"],
                },
            },
            {
                "name": "licenciement_assister",
                "description": (
                    "Assiste la procédure de licenciement ou mesure disciplinaire. "
                    "Vérifie la légalité, rédige les courriers, calcule les indemnités légales."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "type_procedure": {
                            "type": "string",
                            "description": "avertissement | mise_a_pied | licenciement_faute | "
                                           "licenciement_economique | rupture_conventionnelle",
                        },
                        "motif":         {"type": "string",  "description": "Motif de la mesure"},
                        "anciennete_an": {"type": "number",  "description": "Ancienneté en années"},
                        "salaire_brut":  {"type": "number"},
                        "pays":          {"type": "string"},
                        "action": {
                            "type": "string",
                            "description": "conseiller | rediger_courrier | calculer_indemnites",
                        },
                    },
                    "required": ["type_procedure", "pays"],
                },
            },
            {
                "name": "cc_consulter",
                "description": (
                    "Consulte la convention collective applicable selon le pays et le secteur d'activité. "
                    "Retourne les dispositions spécifiques : salaires minima par catégorie, primes, "
                    "congés supplémentaires, préavis, indemnités, classifications. "
                    "Utiliser dès qu'une question porte sur des droits potentiellement plus favorables "
                    "que le code du travail (13e mois, primes sectorielles, classifications, etc.)."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pays":    {"type": "string", "description": "Code pays ISO : CM, CI, SN, BF, GA…"},
                        "secteur": {
                            "type": "string",
                            "description": (
                                "Secteur d'activité : btp | banque | assurance | commerce | industrie | "
                                "transport | mines_petrole | agriculture | hotellerie | sante | "
                                "telecom | education | securite | interprofessionnel"
                            ),
                        },
                        "question": {
                            "type": "string",
                            "description": "Question RH précise à rechercher dans la CC",
                        },
                    },
                    "required": ["pays", "question"],
                },
            },
            {
                "name": "hrreport_generer",
                "description": (
                    "Génère un rapport RH synthétique (effectifs, masse salariale, "
                    "absentéisme, turnover) avec analyse et recommandations."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "donnees_rh": {
                            "type": "object",
                            "description": "Données RH : {'nb_employes': 50, 'masse_salariale': 25000000, "
                                           "'turnover_pct': 12, 'absenteisme_pct': 3}",
                        },
                        "periode":   {"type": "string",  "description": "Période du rapport, ex: 'T3 2024'"},
                        "objectifs": {"type": "object",  "description": "Objectifs RH à comparer (optionnel)"},
                    },
                    "required": ["donnees_rh"],
                },
            },
            {
                "name": "orchestrer_embauche",
                "description": (
                    "Orchestre le workflow complet d'embauche : contrat → déclaration CNPS "
                    "→ intégration paie → checklist accès/matériel. Plan d'action séquencé "
                    "avec délais légaux et tous les documents à produire."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "nom_employe":  {"type": "string"},
                        "poste":        {"type": "string"},
                        "date_debut":   {"type": "string", "description": "YYYY-MM-DD"},
                        "type_contrat": {"type": "string", "description": "cdi | cdd | stage"},
                        "salaire_brut": {"type": "number"},
                        "pays":         {"type": "string"},
                        "departement":  {"type": "string"},
                    },
                    "required": ["nom_employe", "poste", "date_debut", "pays"],
                },
            },
            {
                "name": "orchestrer_depart",
                "description": (
                    "Orchestre le workflow complet de départ : calcul solde de tout compte "
                    "(indemnités + congés non pris + préavis), lettre de rupture, radiation CNPS, "
                    "checklist restitution matériel/accès. Tous les montants calculés."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "nom_employe":       {"type": "string"},
                        "type_depart":       {"type": "string",
                                              "description": "demission | licenciement_faute | "
                                                             "licenciement_economique | fin_cdd | retraite | "
                                                             "rupture_conventionnelle | deces"},
                        "anciennete_an":     {"type": "number"},
                        "salaire_brut":      {"type": "number"},
                        "conges_restants":   {"type": "number", "description": "Jours de congés non pris"},
                        "preavis_effectue":  {"type": "boolean"},
                        "pays":              {"type": "string"},
                        "date_depart":       {"type": "string", "description": "YYYY-MM-DD"},
                    },
                    "required": ["type_depart", "anciennete_an", "salaire_brut", "pays"],
                },
            },
            {
                "name": "analyser_document_rh",
                "description": (
                    "Analyse un document RH entrant (lettre de démission, arrêt maladie, "
                    "courrier inspection du travail, plainte harcèlement, accident de travail) "
                    "et retourne les actions obligatoires, délais légaux et risques."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "contenu_document": {"type": "string"},
                        "type_document":    {"type": "string",
                                             "description": "demission | arret_maladie | "
                                                            "inspection_travail | plainte_harcelement | "
                                                            "accident_travail | notification_syndicale"},
                        "pays":             {"type": "string"},
                    },
                    "required": ["contenu_document", "type_document"],
                },
            },
            {
                "name": "calendrier_social",
                "description": (
                    "Calendrier des obligations sociales du mois : CNPS, déclarations, "
                    "fins de période d'essai, renouvellements CDD. Alerte sur les "
                    "échéances imminentes et génère les actions à effectuer."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pays":     {"type": "string"},
                        "mois":     {"type": "string", "description": "YYYY-MM"},
                        "employes": {"type": "array",
                                     "description": "[{nom, date_fin_cdd, fin_periode_essai, date_embauche}]"},
                    },
                    "required": ["pays"],
                },
            },
        ]

    # ── Dispatch ─────────────────────────────────────────────────────────────

    async def _executer_outil_metier(
        self,
        nom:          str,
        params:       dict,
        user_id:      int,
        execution_id: str,
    ) -> str:
        if nom == "contrat_travail_rediger":
            return _traiter_contrat(params)
        if nom == "paie_calculer":
            return _rendu_bulletin(
                _calculer_bulletin_paie(
                    salaire_brut  = float(params.get("salaire_brut", 0)),
                    pays          = params.get("pays", "CM"),
                    anciennete_an = float(params.get("anciennete_an", 0)),
                    nb_enfants    = int(params.get("nb_enfants", 0)),
                    avantages     = params.get("avantages", {}),
                    primes        = params.get("primes", {}),
                )
            )
        if nom == "conge_calculer":
            return _rendu_conges(
                _calculer_conges_payes(
                    salaire_brut  = float(params.get("salaire_brut", 0)),
                    anciennete_an = float(params.get("anciennete_an", 0)),
                    pays          = params.get("pays", "CM"),
                    jours_acquis  = params.get("jours_acquis"),
                )
            )
        if nom == "licenciement_assister":
            return _traiter_licenciement(params)
        if nom == "cc_consulter":
            return await _consulter_cc_async(params)
        if nom == "hrreport_generer":
            return _generer_rapport_rh(params)
        if nom == "orchestrer_embauche":
            return _orchestrer_embauche(params)
        if nom == "orchestrer_depart":
            return _orchestrer_depart(params)
        if nom == "analyser_document_rh":
            from core.ia_client import ModeIA, ia_client
            prompt = _prompt_analyse_doc_rh(params)
            rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
            return rep.contenu
        if nom == "calendrier_social":
            return _calendrier_social(params)
        return f"[Outil '{nom}' non reconnu par AgentDRH]"


# ══════════════════════════════════════════════════════════════════════════════
# Consultation conventions collectives via RAG
# ══════════════════════════════════════════════════════════════════════════════

async def _consulter_cc_async(params: dict) -> str:
    """
    Recherche dans les conventions collectives via RAG.
    Sélectionne la CC sectorielle appropriée selon pays + secteur.
    """
    pays     = params.get("pays", "").upper()
    secteur  = params.get("secteur") or _detecter_secteur(params.get("question", ""))
    question = params.get("question", "")

    if not pays or not question:
        return "[cc_consulter] Paramètres manquants : pays et question requis."

    # Résoudre les doc_ids CC à interroger
    doc_ids = _cc_doc_ids_pour(pays, secteur)

    # Noms des CC pour l'en-tête de réponse
    from modules.rag.sources_registry import SOURCES
    noms_cc = [
        s.nom for s in SOURCES
        if s.doc_id in doc_ids
    ]
    cc_label = noms_cc[0] if noms_cc else f"Convention collective ({pays})"
    secteur_label = secteur.replace("_", "/").title() if secteur else "Interprofessionnel"

    # Interroger le RAG
    try:
        from modules.rag.rag_embedder import rag_embedder_manager
        resultats = rag_embedder_manager.rechercher(
            question,
            doc_ids=doc_ids,
            top_k_par_doc=4,
            top_k_global=6,
            seuil_score=0.25,
        )
    except Exception as e:
        logger.warning(f"[cc_consulter] RAG indisponible : {e}")
        resultats = []

    if not resultats:
        # Aucun résultat RAG → réponse guidée par le contexte
        return (
            f"CONVENTION COLLECTIVE — {cc_label}\n"
            f"Secteur : {secteur_label} | Pays : {pays}\n\n"
            "⚠️  Document non encore indexé dans le corpus RAG.\n"
            "En attendant l'indexation, voici les principes généraux applicables :\n\n"
            f"Pour le secteur {secteur_label} en {pays}, la convention collective "
            "complète le code du travail sur : classifications professionnelles, "
            "salaires minima par catégorie/échelon, primes spécifiques au secteur, "
            "durée du travail, congés supplémentaires d'ancienneté, préavis renforcés.\n\n"
            "Recommandation : Consulter le Ministère du Travail ou le syndicat patronal "
            f"du secteur {secteur_label} en {pays} pour obtenir le texte à jour."
        )

    # Formater les résultats
    lignes = [
        f"CONVENTION COLLECTIVE — {cc_label}",
        f"Secteur : {secteur_label} | Pays : {pays}",
        f"Question : {question}",
        "=" * 60,
        "",
    ]
    for i, res in enumerate(resultats, 1):
        score  = res.get("score", 0)
        texte  = res.get("texte", "").strip()
        meta   = res.get("metadata", {})
        source = meta.get("nom_doc", meta.get("nom", "CC"))
        lignes.append(f"[Extrait {i} | Pertinence: {score:.2f} | Source: {source}]")
        lignes.append(texte[:800])
        lignes.append("")

    lignes.append(
        "⚠️  Vérifier que la version de la CC est en vigueur. "
        "La CC sectorielle prime sur la CCNI si plus favorable au salarié."
    )
    return "\n".join(lignes)


# ══════════════════════════════════════════════════════════════════════════════
# Fonctions de rendu / assistance (non numériques, mais standalone)
# ══════════════════════════════════════════════════════════════════════════════

def _traiter_contrat(params: dict) -> str:
    """Génère ou vérifie un modèle de contrat de travail."""
    type_contrat = params.get("type_contrat", "cdi")
    pays         = params.get("pays", "CM")
    poste        = params.get("poste", "Poste à préciser")
    salaire      = float(params.get("salaire_brut", 0))
    action       = params.get("action", "rediger")

    lignes = [f"CONTRAT DE TRAVAIL — {type_contrat.upper()} ({pays})\n"]

    if action in ("rediger", "analyser"):
        lignes += [
            "CLAUSES OBLIGATOIRES (OHADA / Code du travail) :\n",
            "1. IDENTIFICATION DES PARTIES",
            "   - Employeur : [Raison sociale, RCCM, siège social]",
            "   - Employé   : [Nom, prénom, CNI, nationalité, domicile]\n",
            "2. NATURE ET DURÉE DU CONTRAT",
        ]
        if type_contrat == "cdi":
            lignes += [
                "   - Contrat à Durée Indéterminée",
                "   - Date de prise d'effet : [Date]",
                f"   - Période d'essai : 3 mois renouvelable 1 fois ({pays})",
            ]
        elif type_contrat == "cdd":
            duree = params.get("duree", "À préciser")
            lignes += [
                f"   - Contrat à Durée Déterminée : {duree}",
                "   - ⚠️  Max 2 renouvellements avant requalification CDI",
            ]
        elif type_contrat == "stage":
            duree = params.get("duree", "À préciser")
            lignes.append(f"   - Stage de formation : {duree}")

        lignes += [
            f"\n3. FONCTION ET LIEU DE TRAVAIL",
            f"   - Poste : {poste}",
            "   - Lieu de travail : [Adresse]",
            f"   - Durée légale : 40h/semaine ({pays})\n",
        ]

        if salaire > 0:
            smig = _SMIG.get(pays, 0)
            lignes.append("4. RÉMUNÉRATION")
            lignes.append(f"   - Salaire brut : {salaire:,.0f} FCFA/mois")
            if smig and salaire < smig:
                lignes.append(f"   ⚠️  Inférieur au SMIG {pays} = {smig:,} FCFA")

        lignes += [
            "\n5. CLAUSES COMPLÉMENTAIRES RECOMMANDÉES",
            "   - Confidentialité",
            "   - Propriété intellectuelle",
            "   - Convention collective applicable : [Secteur]",
            "   - Juridiction : Tribunal du travail de [Ville]\n",
            "⚠️  Modèle indicatif — Faire valider par un juriste du travail.",
        ]

    elif action == "verifier":
        lignes += [
            "POINTS DE VÉRIFICATION :",
            "☐ Période d'essai : ne pas dépasser les limites légales",
            f"☐ Salaire ≥ SMIG {pays} ({_SMIG.get(pays, 'N/A'):,} FCFA)" if _SMIG.get(pays) else "☐ Salaire ≥ SMIG applicable",
            "☐ Durée hebdomadaire conforme (40h légales)",
            "☐ Congés annuels : minimum légal (24-30 j selon pays)",
            "☐ Non-concurrence : limitée en durée, zone géographique et compensée",
            "☐ Convention collective du secteur respectée",
        ]

    return "\n".join(lignes)


def _traiter_licenciement(params: dict) -> str:
    """Assiste la procédure disciplinaire ou de licenciement."""
    type_proc  = params.get("type_procedure", "licenciement_faute")
    motif      = params.get("motif", "À préciser")
    anciennete = float(params.get("anciennete_an", 0))
    salaire    = float(params.get("salaire_brut", 0))
    pays       = params.get("pays", "CM")
    action     = params.get("action", "conseiller")

    lignes = [f"ASSISTANCE {type_proc.replace('_', ' ').upper()} — {pays}\n"]

    if action in ("conseiller", "calculer_indemnites"):
        if "licenciement" in type_proc:
            # Préavis
            preavis = "15 jours"
            for seuil, lib in _PREAVIS:
                if anciennete >= seuil:
                    preavis = lib

            lignes += [
                "PROCÉDURE LÉGALE OBLIGATOIRE :",
                "1. Lettre de convocation entretien préalable (LRAR ou remise en main propre)",
                "   Délai minimum : 5 jours ouvrables avant entretien",
                "2. Entretien préalable (l'employé peut se faire assister par un délégué du personnel)",
                "3. Lettre de licenciement motivée (LRAR)",
                f"   Préavis légal : {preavis}",
                "4. Documents de sortie :",
                "   - Certificat de travail",
                "   - Reçu pour solde de tout compte",
                "   - Attestation CNPS/CNSS",
                "",
            ]

            if anciennete > 0 and salaire > 0:
                indem = _calculer_indemnite_licenciement(salaire, anciennete, pays)
                lignes.append(_rendu_indemnites_lic(indem))

        elif "avertissement" in type_proc:
            lignes += [
                "PROCÉDURE AVERTISSEMENT :",
                "1. Lettre d'avertissement motivée",
                "2. Remise en main propre avec accusé ou LRAR",
                "3. Archivage au dossier personnel (max 3 ans en général)",
                "⚠️  Un seul avertissement ne peut constituer une faute grave",
            ]
        elif "mise_a_pied" in type_proc:
            lignes += [
                "PROCÉDURE MISE À PIED CONSERVATOIRE :",
                "1. Notification immédiate écrite de la mesure",
                "2. Durée maximale : 8 jours (selon pays — vérifier code local)",
                "3. Entretien préalable dans ce délai",
                "⚠️  La mise à pied conservatoire n'est pas une sanction, elle suspend le contrat",
            ]

    if action == "rediger_courrier":
        lignes += [
            "\nMODÈLE — CONVOCATION ENTRETIEN PRÉALABLE\n",
            "Objet : Convocation à un entretien préalable\n",
            "Madame/Monsieur [Nom Prénom],\n",
            f"Nous envisageons de prendre à votre égard une mesure de "
            f"{type_proc.replace('_', ' ')} pour le motif suivant :",
            f"{motif}\n",
            "En conséquence, vous êtes convoqué(e) à un entretien préalable :",
            "   Date : [DATE]   Heure : [HEURE]   Lieu : [ADRESSE]\n",
            "Vous pouvez vous faire assister par un délégué du personnel de votre choix.",
            "\n[Signature, nom et qualité du signataire]",
            "⚠️  Modèle indicatif — Adapter selon le code du travail local.",
        ]

    return "\n".join(lignes)


def _generer_rapport_rh(params: dict) -> str:
    """Génère un rapport RH synthétique avec indicateurs et recommandations."""
    donnees  = params.get("donnees_rh", {})
    periode  = params.get("periode", "Période")
    objectifs = params.get("objectifs", {})

    nb      = int(donnees.get("nb_employes", 0))
    masse   = float(donnees.get("masse_salariale", 0))
    turn    = float(donnees.get("turnover_pct", 0))
    absent  = float(donnees.get("absenteisme_pct", 0))
    recr    = int(donnees.get("recrutements", 0))
    departs = int(donnees.get("departs", 0))

    lignes = [f"RAPPORT RH — {periode}\n"]

    lignes.append("EFFECTIFS")
    lignes.append(f"  Total effectif        : {nb} collaborateurs")
    if recr:
        lignes.append(f"  Recrutements          : {recr}")
    if departs:
        lignes.append(f"  Départs               : {departs}")
    if turn:
        etat = "✅ Sain" if turn < 10 else ("⚠️  Élevé" if turn < 20 else "❌ Critique")
        lignes.append(f"  Taux de turnover      : {turn:.1f}%  {etat}  (référence < 10%)")

    lignes.append("\nMASSE SALARIALE")
    if masse > 0:
        lignes.append(f"  Masse salariale       : {masse:,.0f} FCFA")
        if nb > 0:
            lignes.append(f"  Salaire moyen         : {masse/nb:,.0f} FCFA")
        if recr and departs and nb > 0:
            taux_renouvellement = (min(recr, departs) / nb) * 100
            lignes.append(f"  Taux renouvellement   : {taux_renouvellement:.1f}%")

    lignes.append("\nABSENTÉISME")
    if absent:
        etat = "✅ Normal" if absent < 3 else ("⚠️  Élevé" if absent < 5 else "❌ Critique")
        lignes.append(f"  Taux d'absentéisme    : {absent:.1f}%  {etat}  (référence < 3%)")

    if objectifs:
        lignes.append("\nOBJECTIFS vs RÉALISÉ")
        for k, v in objectifs.items():
            reel = donnees.get(k)
            if reel is not None:
                ecart = float(reel) - float(v)
                icon  = "✅" if ecart >= 0 else "⚠️ "
                lignes.append(f"  {k:25} : Obj {v}  |  Réel {reel}  {icon}")

    recommandations = []
    if turn > 15:
        recommandations.append("⚠️  Turnover élevé : mener une enquête de satisfaction et auditer les conditions de travail")
    if absent > 4:
        recommandations.append("⚠️  Absentéisme : identifier les services et causes (RPS, conditions de travail)")
    if recr > departs and nb > 0:
        recommandations.append("Croissance des effectifs : structurer le plan d'intégration (onboarding)")
    if masse > 0 and nb > 0 and masse / nb < _SMIG.get("CM", 41_875) * 12:
        recommandations.append("⚠️  Salaire moyen potentiellement en-dessous du SMIG annualisé — vérifier")

    if recommandations:
        lignes.append("\nRECOMMANDATIONS")
        for r in recommandations:
            lignes.append(f"  - {r}")

    return "\n".join(lignes)


# ── Nouvelles fonctions haute valeur ─────────────────────────────────────────

def _orchestrer_embauche(params: dict) -> str:
    """Plan d'action séquencé pour une embauche — tous les workflows reliés."""
    import datetime
    nom          = params.get("nom_employe", "[Nom employé]")
    poste        = params.get("poste", "[Poste]")
    date_debut   = params.get("date_debut", datetime.date.today().isoformat())
    type_contrat = params.get("type_contrat", "cdi").upper()
    salaire      = float(params.get("salaire_brut", 0))
    pays         = params.get("pays", "CM")
    dept         = params.get("departement", "À préciser")

    smig = _SMIG.get(pays, 41_875)
    alerte_smig = f"\n   ⚠️  Salaire inférieur au SMIG ({pays} = {smig:,} FCFA/mois)".replace(",", " ") if salaire and salaire < smig else ""

    # Calcul période d'essai
    pe = {"cdi": "3 mois renouvelable 1 fois", "cdd": "1 mois", "stage": "15 jours"}.get(type_contrat.lower(), "3 mois")

    # Calcul bulletin premier mois
    bul = _calculer_bulletin_paie(salaire, pays, 0, 0) if salaire > 0 else None
    net_str = f"{bul['net_a_payer']:,.0f} FCFA".replace(",", " ") if bul else "À calculer"
    cnps_pat = f"{bul['total_patronal']:,.0f} FCFA".replace(",", " ") if bul else "À calculer"

    lignes = [
        f"WORKFLOW EMBAUCHE — {nom} ({poste})\n{'═'*55}",
        f"Date d'entrée : {date_debut} | Contrat : {type_contrat} | Pays : {pays}",
        f"Département   : {dept} | Salaire brut : {salaire:,.0f} FCFA{alerte_smig}".replace(",", " "),
        "",
        "ÉTAPE 1 — AVANT LE PREMIER JOUR (J-5)",
        f"  □ Rédiger et signer le contrat {type_contrat}",
        f"    → Période d'essai : {pe}",
        "  □ Collecter les documents : CNI/passeport, diplômes, extrait casier judiciaire",
        "  □ Obtenir le RIB bancaire pour virement salaire",
        "  □ Ouvrir le dossier physique et numérique",
        "",
        "ÉTAPE 2 — DÉCLARATION CNPS (J à J+8)",
        f"  □ Immatriculation CNPS si premier emploi (formulaire CNPS-01)",
        f"  □ Déclaration d'embauche à la CNPS ({pays}) — OBLIGATOIRE sous 8 jours",
        "  □ Obtenir le numéro d'immatriculation CNPS de l'employé",
        f"  □ Cotisations patronales estimées : {cnps_pat}/mois",
        "",
        "ÉTAPE 3 — INTÉGRATION PAIE (J)",
        f"  □ Ajouter dans le logiciel de paie : salaire brut {salaire:,.0f} FCFA".replace(",", " "),
        f"  □ Net à payer estimé premier mois : {net_str}",
        "  □ Paramétrer : ancienneté = 0, congés = 0 jour acquis",
        "  □ Vérifier classification convention collective applicable",
        "",
        "ÉTAPE 4 — ACCÈS ET MATÉRIEL (J)",
        "  □ Créer accès informatiques (email, SI, ERP)",
        "  □ Remettre badge/carte d'accès locaux",
        "  □ Préparer poste de travail + matériel (PC, téléphone)",
        "  □ Planifier visite médicale d'embauche (obligatoire avant prise de poste)",
        "",
        "ÉTAPE 5 — SUIVI PÉRIODE D'ESSAI",
        f"  □ Planifier point à mi-parcours ({pe.split()[0]} mois / 2)",
        "  □ Évaluation formelle avant fin de période d'essai",
        "  □ Décision : confirmation CDI ou rupture (lettre RAR obligatoire)",
        "",
        f"DOCUMENTS À PRODUIRE : Contrat {type_contrat} · Déclaration CNPS · "
        f"Bulletin paie mois 1 · Fiche de poste",
    ]
    return "\n".join(lignes)


def _orchestrer_depart(params: dict) -> str:
    """Calcule le solde de tout compte et orchestre le workflow de départ."""
    import datetime
    nom            = params.get("nom_employe", "[Employé]")
    type_depart    = params.get("type_depart", "demission")
    anciennete     = float(params.get("anciennete_an", 0))
    salaire        = float(params.get("salaire_brut", 0))
    conges_rest    = float(params.get("conges_restants", 0))
    preavis_fait   = params.get("preavis_effectue", True)
    pays           = params.get("pays", "CM")
    date_depart    = params.get("date_depart", datetime.date.today().isoformat())

    # Préavis légal
    preavis = "15 jours"
    for seuil, duree in _PREAVIS:
        if anciennete >= seuil:
            preavis = duree

    # Indemnité de licenciement (Cameroun — Code du travail Art. 39)
    indemnite_lic = 0.0
    if type_depart in ("licenciement_economique", "retraite") and anciennete >= 2:
        indemnite_lic = salaire * anciennete * 0.30  # 30% du salaire brut mensuel par année

    # Compensation congés non pris
    comp_conges = (salaire / 26) * conges_rest if conges_rest > 0 else 0

    # Compensation préavis si non effectué
    comp_preavis = 0.0
    if not preavis_fait and type_depart != "demission":
        jours = {"15 jours": 15, "1 mois": 30, "2 mois": 60, "3 mois": 90}
        j = jours.get(preavis, 30)
        comp_preavis = (salaire / 26) * j

    total_brut = indemnite_lic + comp_conges + comp_preavis

    type_labels = {
        "demission": "Démission",
        "licenciement_faute": "Licenciement pour faute",
        "licenciement_economique": "Licenciement économique",
        "fin_cdd": "Fin de CDD",
        "retraite": "Départ à la retraite",
        "rupture_conventionnelle": "Rupture conventionnelle",
        "deces": "Décès",
    }

    lignes = [
        f"WORKFLOW DÉPART — {nom}\n{'═'*55}",
        f"Type          : {type_labels.get(type_depart, type_depart)}",
        f"Ancienneté    : {anciennete} an(s) | Salaire brut : {salaire:,.0f} FCFA".replace(",", " "),
        f"Date départ   : {date_depart} | Pays : {pays}",
        "",
        "CALCUL SOLDE DE TOUT COMPTE",
        f"  Indemnité de {type_depart.replace('_', ' ')} : {indemnite_lic:>12,.0f} FCFA".replace(",", " "),
        f"  Compensation congés ({conges_rest:.0f}j)          : {comp_conges:>12,.0f} FCFA".replace(",", " "),
        f"  Compensation préavis ({preavis})       : {comp_preavis:>12,.0f} FCFA".replace(",", " "),
        f"  {'─'*48}",
        f"  TOTAL BRUT DÛ                          : {total_brut:>12,.0f} FCFA".replace(",", " "),
        "  (Déduire IRPP et cotisations sociales sur la part imposable)",
        "",
        "DOCUMENTS À PRODUIRE",
        f"  □ Lettre de {'rupture/licenciement' if 'licenciement' in type_depart else type_depart} (envoi RAR)",
        "  □ Reçu pour solde de tout compte (signé par les deux parties)",
        "  □ Certificat de travail (OBLIGATOIRE — Code du travail)",
        "  □ Attestation de salaire pour Pôle Emploi/CNPS",
        "  □ Attestation de fin de contrat CNPS",
        "",
        "ÉTAPES ADMINISTRATIVES",
        "  □ Radiation CNPS dans les 8 jours suivant le départ",
        "  □ Clôture accès informatiques le jour du départ",
        "  □ Restitution matériel (PC, badge, véhicule) — PV de restitution",
        "  □ Transfert des dossiers en cours",
    ]
    if type_depart == "licenciement_faute":
        lignes += [
            "",
            "⚠️  LICENCIEMENT POUR FAUTE — Vérifications obligatoires :",
            "  □ Convocation entretien préalable (RAR, 5 jours ouvrables avant)",
            "  □ Procès-verbal de l'entretien préalable",
            "  □ Notification de licenciement (RAR, minimum 48h après entretien)",
            "  □ Saisir l'Inspection du travail si licenciement économique (> 10 personnes)",
        ]
    return "\n".join(lignes)


def _prompt_analyse_doc_rh(params: dict) -> str:
    """Construit le prompt pour l'analyse IA d'un document RH entrant."""
    contenu   = params.get("contenu_document", "")
    type_doc  = params.get("type_document", "demission")
    pays      = params.get("pays", "CM")

    guides = {
        "demission": "Vérifier le délai de préavis, si la démission est formellement valide, "
                     "les indemnités éventuellement dues, et les étapes de traitement côté RH.",
        "arret_maladie": "Identifier la durée, le délai de transmission légal (48h), "
                          "les obligations de l'employeur (maintien salaire partiel), "
                          "et les démarches CNPS à effectuer.",
        "inspection_travail": "Identifier les manquements reprochés, les délais de réponse, "
                               "les pénalités potentielles et la stratégie de réponse recommandée.",
        "plainte_harcelement": "Identifier les faits allégués, les obligations légales immédiates "
                                "(protection du plaignant, enquête interne), et les risques juridiques.",
        "accident_travail": "Vérifier si la déclaration CNPS a été faite dans les 48h, "
                             "les obligations médicales et les responsabilités de l'employeur.",
        "notification_syndicale": "Identifier la nature de la revendication, les délais de réponse "
                                   "légaux et les obligations de négociation.",
    }

    guide = guides.get(type_doc, "Analyser le document et identifier les actions obligatoires.")

    return f"""Analyse ce document RH reçu par un DRH en {pays}.

Type de document : {type_doc.replace('_', ' ').title()}

CONTENU DU DOCUMENT :
{contenu}

MISSION D'ANALYSE :
{guide}

RETOURNER :
1. Résumé du document (2-3 lignes)
2. Actions OBLIGATOIRES à prendre (avec délais légaux précis)
3. Risques juridiques si inaction
4. Documents à produire en réponse
5. Recommandation sur la stratégie à adopter
Citer les articles du Code du travail {pays} applicables."""


def _calendrier_social(params: dict) -> str:
    """Calendrier des obligations sociales du mois avec alertes."""
    import datetime
    pays    = params.get("pays", "CM")
    mois    = params.get("mois", datetime.date.today().strftime("%Y-%m"))
    employes = params.get("employes", [])

    try:
        annee, mois_n = int(mois[:4]), int(mois[5:7])
    except Exception:
        annee, mois_n = datetime.date.today().year, datetime.date.today().month

    aujourd_hui = datetime.date.today()

    echeances_mensuelles = {
        "CM": [
            (15, "Déclaration et versement CNPS cotisations salariales/patronales"),
            (15, "Déclaration et versement RAS (retenues à la source sur salaires)"),
            (10, "Virements salaires (bonne pratique — pas de délai légal fixé)"),
        ],
        "CI": [
            (15, "Déclaration CNPS mensuelle"),
            (10, "Versement impôt sur salaires (IS)"),
        ],
        "SN": [
            (10, "Déclaration IPRES + CSS"),
            (15, "Versement retenues IRPP sur salaires"),
        ],
    }

    lignes = [f"CALENDRIER SOCIAL {pays} — {mois}\n{'═'*55}"]
    lignes.append("OBLIGATIONS MENSUELLES :\n")

    for jour, obligation in echeances_mensuelles.get(pays, echeances_mensuelles["CM"]):
        date_ech = datetime.date(annee, mois_n, min(jour, 28))
        jours_restants = (date_ech - aujourd_hui).days
        statut = "🔴 URGENT" if jours_restants < 5 else "🟡 PROCHE" if jours_restants < 10 else "🟢"
        lignes.append(f"  {statut} {date_ech.strftime('%d/%m/%Y')} — {obligation}")

    # Échéances spécifiques aux employés
    if employes:
        lignes.append("\nÉCHÉANCES INDIVIDUELLES DU MOIS :")
        for emp in employes:
            nom_emp = emp.get("nom", "Employé")
            fin_cdd = emp.get("date_fin_cdd")
            fin_pe  = emp.get("fin_periode_essai")
            if fin_cdd:
                try:
                    d = datetime.date.fromisoformat(fin_cdd)
                    if d.year == annee and d.month == mois_n:
                        jours = (d - aujourd_hui).days
                        lignes.append(f"  ⏰ {d.strftime('%d/%m')} — CDD {nom_emp} expire ({jours}j) → Décider renouvellement ou non")
                except Exception:
                    pass
            if fin_pe:
                try:
                    d = datetime.date.fromisoformat(fin_pe)
                    if d.year == annee and d.month == mois_n:
                        jours = (d - aujourd_hui).days
                        lignes.append(f"  ⏰ {d.strftime('%d/%m')} — Période d'essai {nom_emp} expire ({jours}j) → Confirmer ou rompre")
                except Exception:
                    pass

    lignes += [
        "",
        "RAPPELS PERMANENTS :",
        "  • Toute embauche → déclaration CNPS sous 8 jours",
        "  • Tout départ → radiation CNPS sous 8 jours",
        "  • Accidents du travail → déclaration CNPS sous 48h",
        "  • Visites médicales annuelles obligatoires (médecine du travail)",
    ]
    return "\n".join(lignes)

    return "\n".join(lignes)
