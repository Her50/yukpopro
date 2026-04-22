"""
AgentBanquier — Agent IA spécialisé pour les banquiers et analystes crédit africains.

Outils métier :
  - credit_analyser        : Scoring et analyse risque crédit (entreprise / particulier)
  - financement_structurer : Structure un financement (dette senior, mezzanine, leasing)
  - conformite_kyc         : Checklist KYC / AML selon FATF et réglementation locale
  - taux_calculer          : Calculs financiers bancaires (TEG, amortissement, swap)
  - marche_analyser        : Analyse de marché financier / BRVM / CEMAC

Référentiels :
  - Réglementation COBAC (CEMAC) — Règlements, instructions, circulaires
  - Réglementation BCEAO (UEMOA) — Instructions, règlements
  - Règles Bâle II / Bâle III adaptées COBAC
  - FATF / GAFI recommandations AML/CFT
  - Code monétaire et financier local

PATTERNS YUKPOASSURANCE :
  - Fonctions déterministes standalone
  - type_agent = TypeAgent.PRO_BANQUIER
  - _necessite_validation() → hérité (False)
  - _prompt_questions_specifiques() implémenté
"""
from __future__ import annotations

import logging
from math import inf, log

from core.agent_orchestrateur import TypeAgent
from modules.pro.agent_pro_base import AgentProBase

logger = logging.getLogger("yukpo_assurance.pro.agent_banquier")


# ══════════════════════════════════════════════════════════════════════════════
# Constantes bancaires COBAC / BCEAO
# ══════════════════════════════════════════════════════════════════════════════

# Ratios prudentiels COBAC (Règlement COBAC R-2016/01)
_RATIOS_COBAC = {
    "solvabilite_min":       0.10,   # Tier 1 + Tier 2 / RWA ≥ 10%
    "liquidite_min":         1.0,    # Ratio de liquidité ≥ 100%
    "transformation_max":    0.50,   # Emplois LT / Ressources LT ≤ 50% (illustratif)
    "division_risques_max":  0.45,   # Grand risque / FP ≤ 45%
}

# Ratios prudentiels BCEAO/UEMOA
_RATIOS_BCEAO = {
    "solvabilite_min":       0.085,  # 8,5%
    "liquidite_min":         0.75,
}

# Taux de base directeur par zone (approximatifs)
_TAUX_DIRECTEUR = {
    "CEMAC": 0.04,    # Taux directeur BEAC
    "UEMOA": 0.035,   # Taux directeur BCEAO
}

# Pondérations risque (Basel simplifié)
_PONDERATION_RISQUE = {
    "souverain_aaa":    0.00,
    "entreprise":       1.00,
    "pme":              0.75,
    "retail":           0.75,
    "immobilier_resid": 0.35,
    "hors_bilan":       0.50,
}

# Grille scoring crédit simplifiée
_SCORING_CRITERES = [
    ("capacite_remboursement", "Ratio service dette / revenu net ≤ 35%",  25),
    ("anciennete_activite",    "Activité ≥ 2 ans",                         15),
    ("garanties",              "Garanties réelles ou personnelles solides", 20),
    ("historique_credit",      "Aucun incident de paiement passé",         20),
    ("secteur_activite",       "Secteur non cyclique / régulé",            10),
    ("fonds_propres",          "Capitaux propres / Total bilan ≥ 20%",     10),
]


# ══════════════════════════════════════════════════════════════════════════════
# Fonctions standalone
# ══════════════════════════════════════════════════════════════════════════════

def _calculer_teg(
    capital:     float,
    taux_nominal: float,
    duree_mois:  int,
    frais:       float = 0.0,
    assurance:   float = 0.0,
) -> dict:
    """
    Calcule le TEG (Taux Effectif Global) et la mensualité d'un crédit.
    Méthode actuarielle mensuelle.
    """
    r = taux_nominal / 12  # taux mensuel nominal

    if r == 0:
        mensualite = (capital + frais + assurance * duree_mois) / duree_mois
    else:
        mensualite = capital * r / (1 - (1 + r) ** (-duree_mois))

    # TEG = résolution de l'équation actuarielle (dichotomie)
    total_paye = mensualite * duree_mois + frais + assurance * duree_mois

    def _val_actuelle(r_mens):
        if r_mens == 0:
            return mensualite * duree_mois
        return mensualite * (1 - (1 + r_mens) ** (-duree_mois)) / r_mens

    teg_mens = None
    try:
        lo, hi = 0.000001, 0.10
        for _ in range(100):
            mid = (lo + hi) / 2
            if _val_actuelle(mid) > capital:
                lo = mid
            else:
                hi = mid
        teg_mens = (lo + hi) / 2
    except Exception:
        teg_mens = r

    teg_annuel   = (1 + teg_mens) ** 12 - 1
    cout_total   = mensualite * duree_mois - capital
    interets_tot = mensualite * duree_mois - capital

    return {
        "capital":         capital,
        "taux_nominal_pct": round(taux_nominal * 100, 3),
        "duree_mois":      duree_mois,
        "mensualite":      round(mensualite, 0),
        "teg_pct":         round(teg_annuel * 100, 3),
        "cout_total":      round(cout_total, 0),
        "total_rembourse": round(mensualite * duree_mois, 0),
        "frais":           frais,
        "assurance":       assurance,
    }


def _tableau_amortissement(capital: float, taux_nominal: float, duree_mois: int) -> list[dict]:
    """Génère le tableau d'amortissement complet d'un crédit."""
    r          = taux_nominal / 12
    mensualite = capital * r / (1 - (1 + r) ** (-duree_mois)) if r > 0 else capital / duree_mois
    solde      = capital
    tableau    = []

    for i in range(1, duree_mois + 1):
        interet   = round(solde * r, 0)
        principal = round(mensualite - interet, 0)
        solde     = max(0, round(solde - principal, 0))
        tableau.append({
            "mois":       i,
            "mensualite": round(mensualite, 0),
            "capital":    principal,
            "interet":    interet,
            "solde":      solde,
        })

    return tableau


def _scorer_credit(criteres_remplis: dict[str, bool], montant: float) -> dict:
    """
    Score crédit simplifié sur 100 points.
    criteres_remplis : {"capacite_remboursement": True, "anciennete_activite": False, ...}
    """
    score     = 0
    details   = []
    for nom, label, poids in _SCORING_CRITERES:
        satisfait = criteres_remplis.get(nom, False)
        pts       = poids if satisfait else 0
        score    += pts
        details.append({"critere": nom, "label": label, "poids": poids, "obtenu": pts, "ok": satisfait})

    if score >= 80:
        decision, risque = "ACCORD PROBABLE", "Faible"
    elif score >= 60:
        decision, risque = "ÉTUDE APPROFONDIE", "Modéré"
    elif score >= 40:
        decision, risque = "RÉSERVÉ — Garanties renforcées", "Élevé"
    else:
        decision, risque = "REFUS PROBABLE", "Très élevé"

    return {
        "score":      score,
        "max":        100,
        "decision":   decision,
        "risque":     risque,
        "details":    details,
        "montant":    montant,
    }


def _structurer_financement(
    besoin:     float,
    type_fin:   str,
    duree_ans:  float,
    garanties:  list[str],
    pays:       str,
) -> str:
    """Structure une solution de financement adaptée au contexte africain."""
    zone = "CEMAC" if pays in ("CM", "GA", "CG", "CF", "TD", "GQ") else "UEMOA"
    taux_base = _TAUX_DIRECTEUR.get(zone, 0.04)

    lignes = [f"STRUCTURATION FINANCEMENT — {type_fin.upper()} ({pays}/{zone})\n"]
    lignes.append(f"Besoin : {besoin:,.0f} FCFA  |  Durée : {duree_ans:.1f} ans\n")

    if type_fin == "dette_senior":
        taux   = taux_base + 0.03  # spread 3%
        mensua = _calculer_teg(besoin, taux, int(duree_ans * 12))["mensualite"]
        lignes += [
            "DETTE SENIOR BANCAIRE :",
            f"  Taux indicatif     : {taux*100:.1f}%/an ({zone}, spread 3%)",
            f"  Mensualité estimée : {mensua:,.0f} FCFA",
            f"  Durée              : {duree_ans:.0f} ans\n",
            "CONDITIONS HABITUELLES :",
            "  - Ratio service dette (DSCR) ≥ 1.25",
            "  - Capitaux propres ≥ 30% du total bilan",
            "  - Garanties réelles : hypothèque de 1er rang ou nantissement",
        ]

    elif type_fin == "leasing":
        taux   = taux_base + 0.035
        loyer  = besoin * (taux / 12) / (1 - (1 + taux / 12) ** (-duree_ans * 12))
        lignes += [
            "CRÉDIT-BAIL (LEASING) :",
            f"  Loyer mensuel estimé    : {loyer:,.0f} FCFA",
            f"  Option d'achat en fin   : 1% à 5% de la valeur d'origine",
            "  Avantage : déductibilité des loyers en charges (IS)\n",
            "CONDITIONS HABITUELLES :",
            "  - Apport initial : 15-20% du coût du bien",
            "  - Bonne situation financière (3 derniers bilans)",
        ]

    elif type_fin == "obligations":
        lignes += [
            "EMPRUNT OBLIGATAIRE (BRVM / BVMAC) :",
            f"  Coupon indicatif   : {(taux_base + 0.02)*100:.1f}% à {(taux_base + 0.04)*100:.1f}%",
            f"  Taille minimum     : 1-2 Mds FCFA (marché primaire BRVM)",
            "  Durée standard     : 3-7 ans\n",
            "PROCESSUS :",
            "  1. Mandat arrangeur / chef de file",
            "  2. Due diligence et rating (BLOOMFIELD, GCR Ratings…)",
            "  3. Visa CREPMF (UEMOA) ou COSUMAF (CEMAC)",
            "  4. Road show investisseurs",
            "  5. Émission et cotation BRVM/BVMAC",
        ]

    else:
        lignes += [
            "FINANCEMENTS DISPONIBLES :",
            "  - Dette bancaire senior  : taux dirigeant + 2-5% spread",
            "  - Crédit-bail            : flexible, fiscal avantageux",
            "  - Financement export     : Afreximbank, Banque Africaine d'Import-Export",
            "  - Capital-investissement : fonds PE locaux ou régionaux",
            "  - Obligations           : BRVM / BVMAC (> 1 Md FCFA)",
        ]

    if garanties:
        lignes.append(f"\nGARANTIES PROPOSÉES : {', '.join(garanties)}")
        lignes.append("  → Vérifier l'éligibilité et la valeur des garanties auprès de votre banque")

    lignes.append(f"\n⚠️  Taux indicatifs — Négocier avec votre banque selon votre profil de risque.")
    return "\n".join(lignes)


def _checklist_kyc(type_client: str, pays: str) -> str:
    """Génère la checklist KYC/AML selon le type de client."""
    lignes = [f"CHECKLIST KYC / AML — {type_client.upper()} ({pays})\n"]
    lignes.append("Base réglementaire : GAFI / GABAC (CEMAC) / GIABA (UEMOA)\n")

    doc_pp = [
        "☐ Pièce d'identité nationale en cours de validité (CNI, passeport)",
        "☐ Justificatif de domicile récent (< 3 mois)",
        "☐ Justificatif de revenus (3 derniers bulletins ou dernière déclaration IS)",
        "☐ Déclaration d'origine des fonds (si dépôt > seuil)",
        "☐ Photo d'identité récente",
    ]

    doc_pm = [
        "☐ Statuts constitutifs certifiés",
        "☐ Extrait RCCM récent (< 3 mois)",
        "☐ Liste des actionnaires / bénéficiaires effectifs (> 25%)",
        "☐ Pièces d'identité des dirigeants et actionnaires ≥ 25%",
        "☐ Procès-verbal nommant le représentant légal",
        "☐ 3 derniers bilans certifiés ou liasses fiscales",
        "☐ Agrément professionnel si activité réglementée",
        "☐ Déclaration de bénéficiaire effectif (obligatoire FATF R.24)",
    ]

    if type_client == "particulier":
        lignes += doc_pp
    elif type_client == "entreprise":
        lignes += doc_pm
    else:
        lignes.append("PERSONNES PHYSIQUES :")
        lignes += doc_pp
        lignes.append("\nPERSONNES MORALES :")
        lignes += doc_pm

    lignes += [
        "\nDILIGENCE RENFORCÉE (si PPE ou pays à risque) :",
        "☐ Vérification OFAC, ONU, UE (listes sanctions)",
        "☐ Preuve source des fonds spécifique",
        "☐ Validation hiérarchique (Comité risques)",
        "☐ Surveillance des transactions renforcée",
        "\n⚠️  Seuils de déclaration de soupçon : variable selon pays (GABAC/GIABA/CFINANCES)",
    ]
    return "\n".join(lignes)


def _analyser_marche_financier(donnees: dict) -> str:
    """Analyse simple de marché financier / portefeuille."""
    cours    = float(donnees.get("cours_actuel", 0))
    achat    = float(donnees.get("prix_achat",   0))
    nb_titres = int(donnees.get("nb_titres",     0))
    dividende = float(donnees.get("dividende",   0))

    lignes = ["ANALYSE PORTEFEUILLE / TITRE\n"]

    if cours > 0 and achat > 0:
        pl     = (cours - achat) * nb_titres
        pl_pct = (cours - achat) / achat * 100
        lignes += [
            f"Prix d'achat            : {achat:,.0f} FCFA",
            f"Cours actuel            : {cours:,.0f} FCFA",
            f"Plus-value latente      : {pl:+,.0f} FCFA  ({pl_pct:+.1f}%)",
            f"Valeur portefeuille     : {cours * nb_titres:,.0f} FCFA",
        ]

    if cours > 0 and dividende > 0:
        rendement = dividende / cours * 100
        lignes.append(f"Rendement dividende     : {rendement:.2f}%")

    pe = donnees.get("per")
    if pe:
        lignes.append(f"PER                     : {pe}  {'✅ Correct' if float(pe) < 15 else '⚠️ Élevé'}")

    beta = donnees.get("beta")
    if beta:
        b = float(beta)
        lignes.append(f"Beta                    : {b:.2f}  ({'volatilité élevée' if b > 1 else 'défensif'})")

    lignes.append("\n⚠️  Analyse indicative. Consulter un conseiller en investissement agréé.")
    return "\n".join(lignes)


def _rendu_teg(r: dict) -> str:
    """Formate le calcul TEG en texte."""
    lignes = [
        "CALCUL CRÉDIT\n",
        f"Capital emprunté        : {r['capital']:,.0f} FCFA",
        f"Taux nominal            : {r['taux_nominal_pct']:.3f}%/an",
        f"Durée                   : {r['duree_mois']} mois ({r['duree_mois']//12} ans {r['duree_mois']%12} mois)",
        f"Frais de dossier        : {r['frais']:,.0f} FCFA",
        f"\nMENSUALITÉ             : {r['mensualite']:,.0f} FCFA",
        f"TEG (taux effectif)     : {r['teg_pct']:.3f}%/an",
        f"Total remboursé         : {r['total_rembourse']:,.0f} FCFA",
        f"Coût total crédit       : {r['cout_total']:,.0f} FCFA",
    ]
    return "\n".join(lignes)


def _rendu_score(s: dict) -> str:
    """Formate le scoring crédit en texte."""
    lignes = [
        f"SCORING CRÉDIT — {s['montant']:,.0f} FCFA\n",
        f"Score                   : {s['score']}/100",
        f"Décision recommandée    : {s['decision']}",
        f"Niveau de risque        : {s['risque']}\n",
        "DÉTAIL PAR CRITÈRE :",
    ]
    for d in s["details"]:
        icone = "✅" if d["ok"] else "❌"
        lignes.append(f"  {icone} {d['label']:<45} {d['obtenu']}/{d['poids']} pts")
    lignes.append(f"\n⚠️  Scoring indicatif — La décision finale appartient au comité de crédit.")
    return "\n".join(lignes)


# ══════════════════════════════════════════════════════════════════════════════
# Classe AgentBanquier
# ══════════════════════════════════════════════════════════════════════════════

class AgentBanquier(AgentProBase):
    """Agent spécialisé Banque / Finance / Marchés de capitaux."""

    type_agent = TypeAgent.PRO_BANQUIER

    def _system_prompt(self) -> str:
        base = super()._system_prompt()
        return base + """

EXPERTISE BANCAIRE ET FINANCIÈRE :
Tu es un banquier senior expert en finance africaine.

COMPÉTENCES CLÉS :
- Analyse et scoring crédit : entreprises, PME, particuliers
- Réglementation prudentielle : COBAC (CEMAC), BCEAO (UEMOA), Bâle III
- Structuration financements : dette senior, mezzanine, leasing, obligations BRVM
- Conformité bancaire : KYC, AML, FATF, déclarations de soupçon (GABAC/GIABA)
- Marchés financiers africains : BRVM (Abidjan), BVMAC (Douala), change XOF/XAF
- Gestion des risques : crédit, marché, liquidité, opérationnel

RÈGLES IMPORTANTES :
- Toujours exprimer les montants en FCFA (XAF/XOF selon la zone)
- Mentionner les ratios prudentiels applicables (COBAC ou BCEAO selon zone)
- Distinguer CEMAC (CM, GA, CG, CF, TD, GQ) et UEMOA (CI, SN, BF, ML, BJ, TG, GN, NE)
- Rappeler que les décisions de crédit appartiennent au comité de crédit
- Signaler les zones grises AML avec recommandation de diligence renforcée
"""

    def _prompt_questions_specifiques(self) -> str:
        return (
            "- Si calcul de crédit et montant/durée/taux non précisés : demander les 3\n"
            "- Si scoring crédit et chiffres financiers non fournis : "
            "demander CA, résultat net, dettes, garanties\n"
            "- Si pays non précisé : demander (détermine zone COBAC ou BCEAO)\n"
            "- Si structuration financement et type non précisé : "
            "proposer les options (dette senior, leasing, obligations)\n"
            "- Ne jamais redemander ce qui est dans le profil ou la conversation"
        )

    def _outils_metier(self) -> list[dict]:
        return [
            {
                "name": "credit_analyser",
                "description": (
                    "Score et analyse le risque crédit d'un dossier (entreprise ou particulier). "
                    "Retourne score /100, décision recommandée, et détail des critères."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "type_client": {
                            "type": "string",
                            "description": "particulier | pme | grande_entreprise",
                        },
                        "montant":    {"type": "number",  "description": "Montant du crédit en FCFA"},
                        "criteres":  {
                            "type": "object",
                            "description": (
                                "Critères de scoring : {'capacite_remboursement': true, "
                                "'anciennete_activite': true, 'garanties': false, "
                                "'historique_credit': true, 'secteur_activite': true, "
                                "'fonds_propres': false}"
                            ),
                        },
                        "pays": {"type": "string"},
                    },
                    "required": ["montant"],
                },
            },
            {
                "name": "taux_calculer",
                "description": (
                    "Calcule le TEG, la mensualité, le coût total et le tableau "
                    "d'amortissement d'un crédit bancaire."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "capital":        {"type": "number",  "description": "Montant emprunté en FCFA"},
                        "taux_nominal":   {"type": "number",  "description": "Taux nominal annuel (ex: 0.085 pour 8.5%)"},
                        "duree_mois":     {"type": "integer", "description": "Durée en mois"},
                        "frais_dossier":  {"type": "number",  "description": "Frais de dossier en FCFA"},
                        "assurance":      {"type": "number",  "description": "Assurance mensuelle en FCFA"},
                        "avec_tableau":   {"type": "boolean", "description": "Inclure le tableau d'amortissement"},
                    },
                    "required": ["capital", "taux_nominal", "duree_mois"],
                },
            },
            {
                "name": "financement_structurer",
                "description": (
                    "Structure une solution de financement adaptée au contexte africain "
                    "(CEMAC/UEMOA) : dette senior, leasing, obligations."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "besoin":      {"type": "number",  "description": "Besoin de financement en FCFA"},
                        "type_financement": {
                            "type": "string",
                            "description": "dette_senior | leasing | obligations | autre",
                        },
                        "duree_ans":   {"type": "number",  "description": "Durée souhaitée en années"},
                        "garanties":   {"type": "array",   "description": "Garanties disponibles"},
                        "pays":        {"type": "string"},
                    },
                    "required": ["besoin", "pays"],
                },
            },
            {
                "name": "conformite_kyc",
                "description": (
                    "Génère la checklist KYC/AML selon le type de client (particulier, entreprise) "
                    "et les obligations COBAC/BCEAO/FATF."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "type_client": {
                            "type": "string",
                            "description": "particulier | entreprise | les_deux",
                        },
                        "pays": {"type": "string"},
                        "ppe":  {
                            "type": "boolean",
                            "description": "Personne Politiquement Exposée (diligence renforcée)",
                        },
                    },
                    "required": ["type_client", "pays"],
                },
            },
            {
                "name": "marche_analyser",
                "description": (
                    "Analyse un titre boursier ou portefeuille sur la BRVM / BVMAC : "
                    "plus-value, rendement dividende, PER, béta."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "cours_actuel": {"type": "number"},
                        "prix_achat":   {"type": "number"},
                        "nb_titres":    {"type": "integer"},
                        "dividende":    {"type": "number",  "description": "Dividende annuel par action"},
                        "per":          {"type": "number",  "description": "Price-to-Earnings ratio"},
                        "beta":         {"type": "number",  "description": "Béta du titre"},
                        "ticker":       {"type": "string",  "description": "Code BRVM/BVMAC (ex: ONTBF, SNTS)"},
                    },
                    "required": [],
                },
            },
            {
                "name": "rediger_memo_credit",
                "description": (
                    "Rédige le mémo de crédit complet pour un comité de crédit : "
                    "présentation emprunteur, analyse financière, score risque, "
                    "structure du financement proposé, garanties, avis du chargé."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "emprunteur":       {"type": "string", "description": "Nom/raison sociale"},
                        "secteur":          {"type": "string"},
                        "montant_demande":  {"type": "number"},
                        "objet_credit":     {"type": "string"},
                        "duree_mois":       {"type": "integer"},
                        "ratios_financiers": {"type": "object",
                                              "description": "{'ca': 0, 'resultat_net': 0, 'dettes': 0, "
                                                             "'fonds_propres': 0, 'ebitda': 0}"},
                        "garanties":        {"type": "array", "items": {"type": "string"}},
                        "score_credit":     {"type": "integer", "description": "Score 0-100"},
                        "pays":             {"type": "string"},
                    },
                    "required": ["emprunteur", "montant_demande", "objet_credit", "pays"],
                },
            },
            {
                "name": "orchestrer_restructuration",
                "description": (
                    "Orchestre un plan de restructuration de dette pour un client en difficulté : "
                    "diagnostic situation, options de rééchelonnement, calcul nouvelles mensualités, "
                    "conditions de sortie de difficulté et calendrier de suivi."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "client":               {"type": "string"},
                        "encours_total":        {"type": "number", "description": "Total dettes bancaires (FCFA)"},
                        "mensualite_actuelle":  {"type": "number"},
                        "revenus_mensuels":     {"type": "number"},
                        "nb_mois_retard":       {"type": "integer"},
                        "motif_difficulte":     {"type": "string",
                                                  "description": "perte_marche | maladie | conjoncture | surdettemment"},
                        "duree_extension_mois": {"type": "integer", "description": "Durée de rééchelonnement souhaitée"},
                        "taux_nominal":         {"type": "number"},
                        "pays":                 {"type": "string"},
                    },
                    "required": ["encours_total", "mensualite_actuelle", "revenus_mensuels", "pays"],
                },
            },
            {
                "name": "analyser_document_financier",
                "description": (
                    "Analyse un document financier entrant : bilan client, compte de résultat, "
                    "relevé bancaire, rapport commissaire aux comptes, état de flux de trésorerie. "
                    "Extrait les ratios clés, détecte les signaux d'alerte et formule un avis."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "contenu_document": {"type": "string", "description": "Texte extrait du document"},
                        "type_document":    {"type": "string",
                                             "description": "bilan | compte_resultat | releve_bancaire | "
                                                            "rapport_cac | flux_tresorerie | liasse_fiscale"},
                        "exercice":         {"type": "string"},
                        "pays":             {"type": "string"},
                    },
                    "required": ["contenu_document", "type_document"],
                },
            },
            {
                "name": "calendrier_reglementaire_banque",
                "description": (
                    "Calendrier des obligations réglementaires bancaires COBAC/BCEAO : "
                    "reportings prudentiels, déclarations de créances classées, "
                    "états financiers superviseurs. Alerte sur les prochaines échéances."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "zone":    {"type": "string", "description": "CEMAC | UEMOA"},
                        "mois":    {"type": "string", "description": "YYYY-MM"},
                        "pays":    {"type": "string"},
                    },
                    "required": ["zone"],
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
        if nom == "credit_analyser":
            return _rendu_score(
                _scorer_credit(
                    criteres_remplis = params.get("criteres", {}),
                    montant          = float(params.get("montant", 0)),
                )
            )

        if nom == "taux_calculer":
            r = _calculer_teg(
                capital       = float(params.get("capital", 0)),
                taux_nominal  = float(params.get("taux_nominal", 0.085)),
                duree_mois    = int(params.get("duree_mois", 60)),
                frais         = float(params.get("frais_dossier", 0)),
                assurance     = float(params.get("assurance", 0)),
            )
            rendu = _rendu_teg(r)
            if params.get("avec_tableau"):
                tableau = _tableau_amortissement(r["capital"], float(params.get("taux_nominal", 0.085)), r["duree_mois"])
                rendu += "\n\nTABLEAU D'AMORTISSEMENT (10 premières échéances) :\n"
                rendu += f"{'Mois':>5} {'Capital':>14} {'Intérêt':>12} {'Mensualité':>13} {'Solde':>15}\n"
                rendu += "─" * 65 + "\n"
                for row in tableau[:10]:
                    rendu += f"{row['mois']:>5} {row['capital']:>14,.0f} {row['interet']:>12,.0f} {row['mensualite']:>13,.0f} {row['solde']:>15,.0f}\n"
                if len(tableau) > 10:
                    rendu += f"... ({len(tableau) - 10} échéances supprimées)\n"
            return rendu

        if nom == "financement_structurer":
            return _structurer_financement(
                besoin    = float(params.get("besoin", 0)),
                type_fin  = params.get("type_financement", "dette_senior"),
                duree_ans = float(params.get("duree_ans", 5)),
                garanties = params.get("garanties", []),
                pays      = params.get("pays") or self._pays or "CM",
            )

        if nom == "conformite_kyc":
            kyc = _checklist_kyc(
                type_client = params.get("type_client", "les_deux"),
                pays        = params.get("pays") or self._pays or "CM",
            )
            if params.get("ppe"):
                kyc += "\n\n🔴 PPE DÉTECTÉ — Diligence renforcée obligatoire (FATF R.12)"
            return kyc

        if nom == "marche_analyser":
            return _analyser_marche_financier(params)
        if nom == "rediger_memo_credit":
            from core.ia_client import ModeIA, ia_client
            prompt = _prompt_memo_credit(params)
            rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
            return rep.contenu
        if nom == "orchestrer_restructuration":
            return _orchestrer_restructuration(params)
        if nom == "analyser_document_financier":
            from core.ia_client import ModeIA, ia_client
            prompt = _prompt_analyse_doc_financier(params)
            rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
            return rep.contenu
        if nom == "calendrier_reglementaire_banque":
            return _calendrier_reglementaire_banque(params)

        return f"[Outil '{nom}' non reconnu par AgentBanquier]"


# ── Nouvelles fonctions haute valeur ─────────────────────────────────────────

def _prompt_memo_credit(params: dict) -> str:
    emprunteur  = params.get("emprunteur", "[Emprunteur]")
    secteur     = params.get("secteur", "Non précisé")
    montant     = float(params.get("montant_demande", 0))
    objet       = params.get("objet_credit", "")
    duree       = int(params.get("duree_mois", 60))
    ratios      = params.get("ratios_financiers", {})
    garanties   = params.get("garanties", [])
    score       = params.get("score_credit", "N/A")
    pays        = params.get("pays", "CM")

    gar_str = "\n".join(f"  - {g}" for g in garanties) if garanties else "  - À préciser"
    ratios_str = "\n".join(f"  {k}: {v}" for k, v in ratios.items()) if ratios else "  À compléter"

    return f"""Rédige un mémo de crédit complet pour présentation au comité de crédit.

DOSSIER :
Emprunteur   : {emprunteur} ({secteur})
Pays         : {pays}
Montant      : {montant:,.0f} FCFA sur {duree} mois
Objet        : {objet}
Score risque : {score}/100

RATIOS FINANCIERS :
{ratios_str}

GARANTIES PROPOSÉES :
{gar_str}

STRUCTURE DU MÉMO (à respecter) :
1. PRÉSENTATION DE L'EMPRUNTEUR (activité, historique, dirigeants clés)
2. OBJET ET STRUCTURE DU FINANCEMENT (montant, durée, taux proposé, modalités de remboursement)
3. ANALYSE FINANCIÈRE (ratios, capacité de remboursement, endettement, trésorerie)
4. ANALYSE DES RISQUES (risques sectoriels, opérationnels, financiers, mitigants)
5. GARANTIES ET SÛRETÉS (description, valeur estimée, rang)
6. AVIS DU CHARGÉ DE CLIENTÈLE (recommandation : accord / accord conditionnel / refus)
7. CONDITIONS PARTICULIÈRES PROPOSÉES

Ton professionnel bancaire. Citer la réglementation COBAC/BCEAO applicable.""".replace(",", " ")


def _orchestrer_restructuration(params: dict) -> str:
    """Plan de restructuration de dette avec calcul des nouvelles mensualités."""
    client      = params.get("client", "[Client]")
    encours     = float(params.get("encours_total", 0))
    mens_act    = float(params.get("mensualite_actuelle", 0))
    revenus     = float(params.get("revenus_mensuels", 0))
    retard      = int(params.get("nb_mois_retard", 0))
    motif       = params.get("motif_difficulte", "conjoncture")
    extension   = int(params.get("duree_extension_mois", 24))
    taux        = float(params.get("taux_nominal", 0.12))
    pays        = params.get("pays", "CM")

    # Nouvelle mensualité après rééchelonnement
    taux_mens = taux / 12
    if taux_mens > 0 and extension > 0:
        nouvelle_mens = encours * taux_mens / (1 - (1 + taux_mens) ** -extension)
    else:
        nouvelle_mens = encours / extension if extension else encours

    taux_endettement_avant = (mens_act / revenus * 100) if revenus else 0
    taux_endettement_apres = (nouvelle_mens / revenus * 100) if revenus else 0
    allegement = mens_act - nouvelle_mens

    lignes = [
        f"PLAN DE RESTRUCTURATION — {client} ({pays})\n{'═'*55}",
        "",
        "DIAGNOSTIC SITUATION ACTUELLE",
        f"  Encours total          : {encours:>14,.0f} FCFA".replace(",", " "),
        f"  Mensualité actuelle    : {mens_act:>14,.0f} FCFA".replace(",", " "),
        f"  Revenus mensuels       : {revenus:>14,.0f} FCFA".replace(",", " "),
        f"  Taux d'endettement     : {taux_endettement_avant:.1f}% {'🔴 CRITIQUE (>40%)' if taux_endettement_avant>40 else '🟡 ÉLEVÉ' if taux_endettement_avant>33 else '🟢'}",
        f"  Mois de retard         : {retard} mois",
        f"  Motif difficulté       : {motif.replace('_', ' ').title()}",
        "",
        "PROPOSITION DE RÉÉCHELONNEMENT",
        f"  Durée d'extension      : +{extension} mois",
        f"  Nouvelle mensualité    : {nouvelle_mens:>14,.0f} FCFA".replace(",", " "),
        f"  Allègement mensuel     : {allegement:>14,.0f} FCFA".replace(",", " "),
        f"  Nouveau taux endettement: {taux_endettement_apres:.1f}% {'✅ Acceptable' if taux_endettement_apres<=33 else '⚠️  Encore élevé'}",
        "",
        "CONDITIONS DE RESTRUCTURATION",
        "  □ Mise à jour immédiate des intérêts de retard",
        f"  □ Période de grâce recommandée : {min(3, retard)} mois (capital différé)",
        "  □ Clause de revue : point à 6 mois",
        "  □ Renforcement des garanties si insuffisantes",
        "  □ Engagement de non-distribution de dividendes pendant restructuration",
        "",
        "CALENDRIER DE SUIVI",
        "  M+0  : Signature avenant de rééchelonnement",
        "  M+1  : Première mensualité restructurée",
        "  M+3  : Visite terrain + vérification reprise d'activité",
        "  M+6  : Revue formelle — décision poursuite ou escalade contentieux",
        "",
        "⚠️  Toute restructuration > seuil prudentiel COBAC → déclassement obligatoire "
        f"en créance restructurée (provisionnement 20% minimum)",
    ]
    return "\n".join(lignes)


def _prompt_analyse_doc_financier(params: dict) -> str:
    contenu   = params.get("contenu_document", "")
    type_doc  = params.get("type_document", "bilan")
    exercice  = params.get("exercice", "N")
    pays      = params.get("pays", "CM")

    guides = {
        "bilan": "Calculer les ratios de solvabilité, liquidité, endettement. "
                  "Identifier les postes anormaux (surstock, créances > 90j, dettes fournisseurs anormales).",
        "compte_resultat": "Calculer les marges (brute, EBITDA, nette). Identifier les charges anormalement élevées. "
                            "Évaluer la capacité de remboursement.",
        "releve_bancaire": "Identifier les flux irréguliers, les prélèvements inhabituels, "
                            "les soldes négatifs récurrents, la saisonnalité de l'activité.",
        "rapport_cac": "Identifier les réserves, observations et risques signalés. "
                        "Évaluer la gravité des observations pour la décision de crédit.",
        "flux_tresorerie": "Évaluer la génération de cash opérationnelle. Identifier si le free cash flow "
                            "couvre le service de la dette. Détecter les cycles de trésorerie.",
    }
    guide = guides.get(type_doc, "Analyser les données financières et identifier les signaux d'alerte.")

    return f"""Tu es analyste crédit senior dans une banque en {pays}.

Analyse ce document financier ({type_doc.replace('_', ' ')}, exercice {exercice}).

DOCUMENT :
{contenu}

MISSION : {guide}

RETOURNER :
1. PRINCIPAUX INDICATEURS (tableau : indicateur | valeur | norme sectorielle | appréciation)
2. POINTS FORTS (max 3)
3. SIGNAUX D'ALERTE (max 5 — avec niveau de risque : faible/modéré/élevé/critique)
4. CAPACITÉ DE REMBOURSEMENT (dette/EBITDA, DSCR si possible)
5. AVIS CRÉDIT : favorable / réservé / défavorable + justification en 2 lignes
Utiliser les normes COBAC/BCEAO comme référence pour les seuils."""


def _calendrier_reglementaire_banque(params: dict) -> str:
    """Calendrier des obligations réglementaires bancaires."""
    import datetime
    zone  = params.get("zone", "CEMAC")
    mois  = params.get("mois", datetime.date.today().strftime("%Y-%m"))
    pays  = params.get("pays", "CM")

    try:
        annee, mois_n = int(mois[:4]), int(mois[5:7])
    except Exception:
        annee, mois_n = datetime.date.today().year, datetime.date.today().month

    # Reportings COBAC/BCEAO
    reportings = {
        "CEMAC": [
            (10, "mensuel", "États de synthèse prudentiels (ESP) — COBAC"),
            (10, "mensuel", "Déclaration créances douteuses et litigieuses"),
            (15, "mensuel", "Situation mensuelle des ressources et emplois"),
            (15, "trimestriel", [3,6,9,12], "Rapport trimestriel conformité COBAC"),
            (31, "trimestriel", [3,6,9,12], "États financiers trimestriels BEAC"),
            (30, "annuel", [3], "Rapport annuel — États financiers certifiés"),
            (30, "annuel", [3], "Déclaration ratios prudentiels annuels COBAC"),
        ],
        "UEMOA": [
            (10, "mensuel", "Situation mensuelle BCEAO"),
            (15, "mensuel", "Reporting crédit et dépôts BCEAO"),
            (20, "trimestriel", [1,4,7,10], "États prudentiels trimestriels BCEAO"),
            (30, "annuel", [4], "Rapport annuel et états certifiés"),
        ],
    }

    ref_zone = reportings.get(zone, reportings["CEMAC"])
    aujourd_hui = datetime.date.today()

    lignes = [f"CALENDRIER RÉGLEMENTAIRE BANCAIRE — {zone} ({pays}) — {mois}\n{'═'*55}"]
    lignes.append("OBLIGATIONS DU MOIS :\n")

    for item in ref_zone:
        if len(item) == 3:
            jour, period, label = item
            if period == "mensuel":
                date_ech = datetime.date(annee, mois_n, min(jour, 28))
                jours_r = (date_ech - aujourd_hui).days
                statut = "🔴 URGENT" if jours_r < 5 else "🟡 PROCHE" if jours_r < 10 else "🟢"
                lignes.append(f"  {statut} J{jour:02d} — {label}")
        elif len(item) == 4:
            jour, period, mois_list, label = item
            if mois_n in mois_list:
                date_ech = datetime.date(annee, mois_n, min(jour, 28))
                jours_r = (date_ech - aujourd_hui).days
                statut = "🔴 URGENT" if jours_r < 5 else "🟡 PROCHE" if jours_r < 10 else "🟢"
                lignes.append(f"  {statut} J{jour:02d} — {label} ({period.upper()})")

    lignes += [
        "",
        "SEUILS PRUDENTIELS À SURVEILLER EN CONTINU :",
        f"  {'Ratio solvabilité':30} ≥ {_RATIOS_COBAC['solvabilite_min']*100:.0f}% (COBAC)" if zone == "CEMAC"
            else f"  {'Ratio solvabilité':30} ≥ {_RATIOS_BCEAO['solvabilite_min']*100:.1f}% (BCEAO)",
        f"  {'Ratio de liquidité':30} ≥ 100%",
        f"  {'Division des risques':30} ≤ 45% des fonds propres",
        "",
        "⚠️  Tout franchissement de seuil → déclaration immédiate au superviseur.",
    ]
    return "\n".join(lignes)
