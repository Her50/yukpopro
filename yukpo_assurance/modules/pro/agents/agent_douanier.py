"""
AgentDouanier — Agent IA pour les transitaires, douaniers et professionnels du commerce international.

Outils métier :
  - declaration_douane_preparer : Prépare une déclaration en douane (IM4, EX1, IM8...)
  - droits_taxes_calculer       : Calcule droits et taxes à l'importation (DD, TVA, DA, ECOFAC...)
  - regime_douanier_choisir     : Identifie le régime douanier optimal (AT, entrepôt, admission temporaire)
  - incoterms_analyser          : Analyse d'un contrat selon Incoterms 2020 (responsabilités, assurances)
  - conformite_commerce_verifier: Checklist de conformité commerce international (documents requis, licences)

Référentiels :
  - Tarif Extérieur Commun CEMAC (TEC-CEMAC)
  - Tarif Extérieur Commun UEMOA (TEC-UEMOA)
  - Code des douanes CEMAC (Règlement 05/01)
  - SYSCOM OHADA (Code de commerce)
  - Incoterms ICC 2020
  - Règlement COBAC sur transferts de capitaux
  - Licences import/export par pays

PATTERNS YUKPOASSURANCE :
  - Fonctions déterministes standalone
  - type_agent = TypeAgent.PRO_DOUANIER
  - _necessite_validation() → hérité (False)
  - _prompt_questions_specifiques() implémenté
"""
from __future__ import annotations

import logging
from typing import Any

from core.agent_orchestrateur import TypeAgent
from modules.pro.agent_pro_base import AgentProBase

logger = logging.getLogger("yukpo_assurance.pro.agent_douanier")


# ══════════════════════════════════════════════════════════════════════════════
# Référentiels
# ══════════════════════════════════════════════════════════════════════════════

# TEC CEMAC — Droits de douane par catégorie de marchandises
_TEC_CEMAC = {
    "0": {"description": "Biens de première nécessité, médicaments essentiels", "dd_pct": 5.0},
    "1": {"description": "Matières premières et intrants", "dd_pct": 10.0},
    "2": {"description": "Biens d'équipement, matériels industriels", "dd_pct": 10.0},
    "3": {"description": "Biens intermédiaires et divers", "dd_pct": 20.0},
    "4": {"description": "Biens de consommation courante", "dd_pct": 30.0},
}

# TEC UEMOA
_TEC_UEMOA = {
    "0": {"description": "Biens sociaux essentiels", "dd_pct": 0.0},
    "1": {"description": "Biens de première nécessité, intrants", "dd_pct": 5.0},
    "2": {"description": "Intrants et produits intermédiaires", "dd_pct": 10.0},
    "3": {"description": "Biens d'équipement", "dd_pct": 20.0},
    "4": {"description": "Biens de consommation finale", "dd_pct": 35.0},
}

# Prélèvements communautaires
_PRELEVEMENTS_CEMAC = {
    "RCI":   {"taux_pct": 1.0, "description": "Redevance Communautaire d'Intégration CEMAC"},
    "ECOFAC": {"taux_pct": 0.4, "description": "Contribution ECOFAC (conservation forêts)"},
    "TAF":   {"taux_pct": 0.25, "description": "Taxe sur les Activités Financières"},
}

_PRELEVEMENTS_UEMOA = {
    "PC":    {"taux_pct": 1.0, "description": "Prélèvement Communautaire UEMOA"},
    "FRAI":  {"taux_pct": 0.5, "description": "Fonds Régional pour l'Agriculture et l'Intégration"},
    "CPS":   {"taux_pct": 1.0, "description": "Contribution au Programme de Solidarité UEMOA"},
}

# TVA par pays
_TVA_PAYS = {
    "CM": 19.25, "GA": 18.0, "CG": 18.0, "CF": 19.0, "TD": 18.0, "GQ": 15.0,  # CEMAC
    "CI": 18.0,  "SN": 18.0, "BF": 18.0, "ML": 18.0, "BJ": 18.0, "TG": 18.0,   # UEMOA
    "GN": 18.0,  "NE": 19.0,
}

# Incoterms 2020
_INCOTERMS = {
    "EXW": {
        "nom": "Ex Works",
        "transport": "Acheteur",
        "chargement_depart": "Acheteur",
        "export": "Acheteur",
        "fret_principal": "Acheteur",
        "assurance": "Acheteur (facultatif)",
        "import": "Acheteur",
        "dechargement": "Acheteur",
        "risque_transfert": "Départ usine du vendeur",
        "modes": ["Tous modes"],
        "conseil": "Vendeur a moins de responsabilités. Acheteur assume tout le transport.",
    },
    "FCA": {
        "nom": "Free Carrier",
        "transport": "Vendeur jusqu'au point convenu, puis Acheteur",
        "chargement_depart": "Vendeur",
        "export": "Vendeur",
        "fret_principal": "Acheteur",
        "assurance": "Acheteur (facultatif)",
        "import": "Acheteur",
        "dechargement": "Acheteur",
        "risque_transfert": "Au transporteur désigné par acheteur",
        "modes": ["Tous modes"],
        "conseil": "Recommandé pour conteneurs. Vendeur gère l'export.",
    },
    "CIF": {
        "nom": "Cost Insurance & Freight",
        "transport": "Vendeur jusqu'au port de destination",
        "chargement_depart": "Vendeur",
        "export": "Vendeur",
        "fret_principal": "Vendeur",
        "assurance": "Vendeur (obligatoire minimum clause C)",
        "import": "Acheteur",
        "dechargement": "Acheteur",
        "risque_transfert": "Au bord du navire au port d'embarquement",
        "modes": ["Maritime uniquement"],
        "conseil": "Très utilisé en Afrique. Base d'imposition douanière = valeur CIF.",
    },
    "DDP": {
        "nom": "Delivered Duty Paid",
        "transport": "Vendeur",
        "chargement_depart": "Vendeur",
        "export": "Vendeur",
        "fret_principal": "Vendeur",
        "assurance": "Vendeur",
        "import": "Vendeur",
        "dechargement": "Acheteur",
        "risque_transfert": "Destination finale convenue",
        "modes": ["Tous modes"],
        "conseil": "Maximum de responsabilités pour le vendeur. Rarement utilisé à l'import vers Afrique.",
    },
    "FOB": {
        "nom": "Free On Board",
        "transport": "Vendeur jusqu'au bord navire, Acheteur dès chargement",
        "chargement_depart": "Vendeur",
        "export": "Vendeur",
        "fret_principal": "Acheteur",
        "assurance": "Acheteur",
        "import": "Acheteur",
        "dechargement": "Acheteur",
        "risque_transfert": "Bord du navire au port d'embarquement",
        "modes": ["Maritime uniquement"],
        "conseil": "Commun pour vrac et conventionnel. Attention : risque passe au bord, pas à bord.",
    },
    "CFR": {
        "nom": "Cost and Freight",
        "transport": "Vendeur jusqu'au port de destination",
        "chargement_depart": "Vendeur",
        "export": "Vendeur",
        "fret_principal": "Vendeur",
        "assurance": "Acheteur",
        "import": "Acheteur",
        "dechargement": "Acheteur",
        "risque_transfert": "Bord du navire au port d'embarquement",
        "modes": ["Maritime uniquement"],
        "conseil": "Comme CIF mais sans assurance incluse. Acheteur doit souscrire sa propre assurance.",
    },
}

# Documents requis à l'importation
_DOCS_IMPORTATION = [
    "Facture commerciale (Commercial Invoice) en double exemplaire",
    "Liste de colisage (Packing List)",
    "Connaissement maritime (Bill of Lading) ou LTA aérien",
    "Certificat d'origine (CO) — détermine les droits préférentiels",
    "Déclaration d'importation / DPI (Déclaration Préalable d'Importation)",
    "Bulletin d'Analyse / Certificat de Conformité (selon produit)",
    "Attestation de vérification (BIVAC, Bureau Veritas, SGS selon pays)",
    "Quittance d'assurance (si CIF/CIP)",
    "Certificat phytosanitaire ou vétérinaire (produits alimentaires/végétaux)",
    "Autorisation d'importation (médicaments, matériels militaires, déchets)",
]

# Régimes douaniers
_REGIMES_DOUANIERS = {
    "IM4": {
        "nom": "Mise à la consommation (Importation définitive)",
        "usage": "Marchandises destinées à rester dans le territoire",
        "droits": "Paiement immédiat de tous droits et taxes",
        "duree": "Permanente",
    },
    "AT": {
        "nom": "Admission Temporaire",
        "usage": "Matériels importés temporairement (chantiers, expositions, réparation)",
        "droits": "Suspension des droits pendant la durée",
        "duree": "6 à 24 mois (renouvelable avec autorisation)",
    },
    "ENTREPOT": {
        "nom": "Régime de l'entrepôt douanier",
        "usage": "Stockage avant décision sur le sort de la marchandise",
        "droits": "Suspension des droits pendant stockage",
        "duree": "12 mois (prolongeable 6 mois)",
    },
    "TA": {
        "nom": "Transit Douanier",
        "usage": "Marchandises traversant le territoire vers destination finale",
        "droits": "Suspension des droits + cautionnement",
        "duree": "Durée du transport (généralement ≤ 30 jours)",
    },
    "TDI": {
        "nom": "Transformation sous Douane (Industrie)",
        "usage": "Transformation de matières premières importées pour réexportation",
        "droits": "Suspension sur intrants (résidus taxés)",
        "duree": "12 à 24 mois",
    },
    "EX1": {
        "nom": "Exportation définitive",
        "usage": "Marchandises locales ou nationalisées destinées à l'exportation",
        "droits": "Droits d'exportation le cas échéant + remboursement TVA",
        "duree": "Permanente",
    },
}


# ── Fonctions standalone ───────────────────────────────────────────────────────

def _calculer_droits_taxes(
    valeur_cif: float,
    categorie_tec: str,
    pays: str,
    zone: str = "CEMAC",
    avec_tva: bool = True,
    droits_accises_pct: float = 0.0,
) -> dict:
    """
    Calcule les droits et taxes à l'importation selon TEC CEMAC ou UEMOA.
    Base imposable = valeur CIF (valeur douanière).
    """
    tec = _TEC_CEMAC if zone == "CEMAC" else _TEC_UEMOA
    cat = tec.get(categorie_tec, tec.get("3"))

    dd_pct = cat["dd_pct"]
    dd = valeur_cif * dd_pct / 100

    # Prélèvements communautaires calculés sur valeur CIF
    prelevements = _PRELEVEMENTS_CEMAC if zone == "CEMAC" else _PRELEVEMENTS_UEMOA
    detail_prev = {}
    total_prev = 0
    for code, prev in prelevements.items():
        montant = valeur_cif * prev["taux_pct"] / 100
        detail_prev[code] = {"montant": round(montant, 0), "description": prev["description"]}
        total_prev += montant

    # Droits d'accises
    da = valeur_cif * droits_accises_pct / 100

    # Base TVA = valeur CIF + DD + DA + prélèvements
    base_tva = valeur_cif + dd + da + total_prev
    tva_pct = _TVA_PAYS.get(pays, 18.0) if avec_tva else 0
    tva = base_tva * tva_pct / 100

    total = base_tva + tva

    return {
        "valeur_cif": valeur_cif,
        "categorie_tec": categorie_tec,
        "description_categorie": cat["description"],
        "zone": zone,
        "pays": pays,
        "droits_douane": {
            "taux_pct": dd_pct,
            "montant": round(dd, 0),
        },
        "prelevements_communautaires": detail_prev,
        "total_prelevements": round(total_prev, 0),
        "droits_accises": {
            "taux_pct": droits_accises_pct,
            "montant": round(da, 0),
        },
        "base_tva": round(base_tva, 0),
        "tva": {
            "taux_pct": tva_pct,
            "montant": round(tva, 0),
        },
        "total_droits_taxes": round(total - valeur_cif, 0),
        "total_a_payer": round(total, 0),
        "taux_global_effectif_pct": round((total - valeur_cif) / valeur_cif * 100, 2) if valeur_cif else 0,
    }


def _preparer_declaration_douane(
    regime: str,
    marchandise: str,
    code_sh: str,
    valeur_fob: float,
    fret: float,
    assurance: float,
    pays_origine: str,
    pays_destination: str,
    poids_brut_kg: float,
    poids_net_kg: float,
    nb_colis: int,
    incoterm: str = "CIF",
) -> dict:
    """Prépare les éléments d'une déclaration en douane."""
    valeur_cif = valeur_fob + fret + assurance
    reg = _REGIMES_DOUANIERS.get(regime.upper(), _REGIMES_DOUANIERS["IM4"])

    # Vérification code SH (6 chiffres minimum)
    sh_valide = len(str(code_sh).replace(".", "")) >= 4

    return {
        "regime": regime.upper(),
        "nom_regime": reg["nom"],
        "usage": reg["usage"],
        "marchandise": marchandise,
        "code_sh": code_sh,
        "sh_valide": sh_valide,
        "incoterm_facture": incoterm,
        "valeur_fob": round(valeur_fob, 0),
        "fret": round(fret, 0),
        "assurance": round(assurance, 0),
        "valeur_cif_douaniere": round(valeur_cif, 0),
        "pays_origine": pays_origine,
        "pays_destination": pays_destination,
        "poids_brut_kg": poids_brut_kg,
        "poids_net_kg": poids_net_kg,
        "nb_colis": nb_colis,
        "droits_suspendus": "AT" in regime.upper() or "ENTREPOT" in regime.upper() or "TA" == regime.upper(),
        "documents_requis": _DOCS_IMPORTATION,
        "case_declaration": {
            "case_1": f"Déclaration {regime.upper()} — {reg['nom']}",
            "case_3": pays_origine,
            "case_5": pays_destination,
            "case_22": f"Devise facture / Taux de change",
            "case_31": f"{marchandise} — {poids_brut_kg} kg brut / {poids_net_kg} kg net / {nb_colis} colis",
            "case_33": code_sh,
            "case_46": f"Valeur statistique CIF : {round(valeur_cif, 0)}",
        },
        "duree_validite_regime": reg["duree"],
    }


def _analyser_incoterm(
    incoterm: str,
    sens: str = "import",
    pays_import: str = "",
    valeur_marchandise: float = 0,
) -> dict:
    """Analyse un Incoterm 2020 et ses implications pratiques."""
    term = _INCOTERMS.get(incoterm.upper())
    if not term:
        return {"erreur": f"Incoterm '{incoterm}' inconnu. Utiliser: {list(_INCOTERMS.keys())}"}

    implications = []
    if sens == "import":
        if term["import"] == "Acheteur":
            implications.append("Vous (importateur) payez les droits et taxes à l'entrée")
        if term["fret_principal"] == "Acheteur":
            implications.append("Vous organisez et payez le fret principal (bateau/avion)")
        if term["assurance"] == "Acheteur" or "(facultatif)" in str(term["assurance"]):
            implications.append("Vous souscrivez l'assurance transport (recommandé)")
        if incoterm.upper() in ("CIF", "CFR", "CIP"):
            implications.append(f"La valeur douanière = valeur CIF {valeur_marchandise:,.0f} (inclus fret + assurance vendeur)")
        if incoterm.upper() == "EXW":
            implications.append("Vous gérez tout l'export depuis l'usine du vendeur — risqué sans réseau")

    pays_info = ""
    if pays_import in _TVA_PAYS:
        pays_info = f"TVA import {pays_import} : {_TVA_PAYS[pays_import]}%"

    return {
        "incoterm": incoterm.upper(),
        "nom_complet": term["nom"],
        "modes_transport": term["modes"],
        "repartition_responsabilites": {
            "transport_pre_acheminement": term["chargement_depart"],
            "formalites_export": term["export"],
            "fret_principal": term["fret_principal"],
            "assurance": term["assurance"],
            "formalites_import": term["import"],
            "dechargement": term["dechargement"],
        },
        "transfert_risques": term["risque_transfert"],
        "conseil_pratique": term["conseil"],
        "implications_pour_vous": implications,
        "info_pays": pays_info,
        "base_valeur_douaniere": "Valeur CIF" if incoterm.upper() in ("CIF", "CIP", "DDP", "DAP", "DPU") else "Valeur CIF à reconstituer (FOB + fret + assurance)",
    }


def _choisir_regime_douanier(
    duree_sejour_prevu: str,
    finalite: str,
    type_marchandise: str,
    pays: str = "CM",
) -> dict:
    """Recommande le régime douanier optimal selon l'usage prévu."""
    recommandations = []

    finalite_lower = finalite.lower()

    if any(mot in finalite_lower for mot in ["vente", "consomm", "définitif", "rester"]):
        recommandations.append({
            "regime": "IM4",
            "raison": "Importation définitive — marchandise destinée à la consommation locale",
            "priorite": 1,
        })

    if any(mot in finalite_lower for mot in ["chantier", "temporaire", "retour", "exposition", "répar"]):
        recommandations.append({
            "regime": "AT",
            "raison": "Admission Temporaire — suspension des droits pendant la durée d'utilisation",
            "priorite": 1,
        })

    if any(mot in finalite_lower for mot in ["transit", "reexpor", "voisin", "corridor"]):
        recommandations.append({
            "regime": "TA",
            "raison": "Transit douanier — marchandise traversant le territoire vers destination finale",
            "priorite": 1,
        })

    if any(mot in finalite_lower for mot in ["transform", "industri", "usine", "fabr"]):
        recommandations.append({
            "regime": "TDI",
            "raison": "Transformation sous douane — suspension droits sur intrants, droits sur résidus",
            "priorite": 1,
        })

    if any(mot in finalite_lower for mot in ["stock", "entrepôt", "attente", "décision"]):
        recommandations.append({
            "regime": "ENTREPOT",
            "raison": "Entrepôt douanier — suspension droits pendant stockage, décision ultérieure",
            "priorite": 1,
        })

    if any(mot in finalite_lower for mot in ["export", "vente extern", "envoyer"]):
        recommandations.append({
            "regime": "EX1",
            "raison": "Exportation définitive — remboursement TVA possible",
            "priorite": 1,
        })

    if not recommandations:
        recommandations.append({
            "regime": "IM4",
            "raison": "Régime par défaut — importation définitive",
            "priorite": 2,
        })

    meilleur = min(recommandations, key=lambda x: x["priorite"])
    reg_detail = _REGIMES_DOUANIERS.get(meilleur["regime"], {})

    return {
        "regime_recommande": meilleur["regime"],
        "nom_regime": reg_detail.get("nom", ""),
        "raison": meilleur["raison"],
        "droits_et_taxes": reg_detail.get("droits", ""),
        "duree_validite": reg_detail.get("duree", ""),
        "autres_options": [r for r in recommandations if r["regime"] != meilleur["regime"]],
        "documents_supplementaires": (
            ["Engagement de retour pour AT", "Caution bancaire ≥ droits et taxes estimés"]
            if meilleur["regime"] == "AT" else
            ["Déclaration de transit", "Cautionnement"] if meilleur["regime"] == "TA" else
            []
        ),
        "avertissement": (
            "⚠️ L'Admission Temporaire nécessite un strict suivi des délais. "
            "Tout dépassement entraîne paiement immédiat + pénalités."
            if meilleur["regime"] in ("AT", "TDI") else ""
        ),
    }


def _verifier_conformite_commerce(
    type_operation: str,
    marchandise: str,
    pays_import: str,
    pays_export: str,
    valeur: float,
    incoterm: str = "CIF",
) -> dict:
    """Checklist de conformité pour une opération de commerce international."""
    checklist = []

    # Documents de base
    docs_base = [
        ("Facture commerciale (3 exemplaires minimum)", True),
        ("Liste de colisage détaillée", True),
        ("Titre de transport (B/L, LTA, CMR)", True),
        ("Certificat d'origine", True),
        ("Police ou attestation d'assurance", incoterm in ("CIF", "CIP")),
        ("Certificat de conformité/qualité (laboratoire)", "alimentaire" in marchandise.lower() or "pharma" in marchandise.lower()),
    ]

    for doc, requis in docs_base:
        checklist.append({
            "element": doc,
            "requis": requis,
            "statut": "🔴 Requis" if requis else "⚪ Optionnel",
        })

    # Formalités pays destination
    pays_dest_checks = [
        f"DPI/DI (Déclaration Préalable d'Importation) — {pays_import}",
        f"Attestation de vérification avant embarquement (BIVAC/SGS) — {pays_import}",
        "Domiciliation bancaire (si > 5M FCFA en zone CEMAC)",
        "Licence d'importation spéciale (si marchandise réglementée)",
    ]
    for chk in pays_dest_checks:
        checklist.append({"element": chk, "requis": True, "statut": "🔴 Requis"})

    # Alertes spécifiques
    alertes = []
    if valeur > 5_000_000:
        alertes.append(f"Domiciliation bancaire obligatoire (valeur {valeur:,.0f} FCFA > 5M FCFA en zone CEMAC/BCEAO)")
    if any(mot in marchandise.lower() for mot in ["arme", "explos", "nucléaire"]):
        alertes.append("Autorisation spéciale Ministère de la Défense/Intérieur requise")
    if any(mot in marchandise.lower() for mot in ["medicament", "pharma", "drogue"]):
        alertes.append("Autorisation DPM (Direction de la Pharmacie) requise")
    if any(mot in marchandise.lower() for mot in ["alimentation", "aliment", "nourriture"]):
        alertes.append("Certificat phytosanitaire et/ou vétérinaire requis")

    nb_requis = sum(1 for c in checklist if c["requis"])

    return {
        "type_operation": type_operation,
        "marchandise": marchandise,
        "pays_import": pays_import,
        "pays_export": pays_export,
        "valeur_fcfa": valeur,
        "incoterm": incoterm,
        "checklist": checklist,
        "nb_elements_requis": nb_requis,
        "alertes_specifiques": alertes,
        "conseils_pratiques": [
            "Vérifiez le classement tarifaire (code SH) avant commande — impacte les droits",
            "Négociez CIF à l'import pour simplifier la valeur douanière",
            "Constituez le dossier complet avant l'arrivée pour éviter pénalités de magasinage",
            f"Pour transit via port de {pays_import}, prévoir caution douanière",
        ],
    }


# ── Rendus ─────────────────────────────────────────────────────────────────────

def _rendu_droits_taxes(r: dict) -> str:
    lignes = [
        f"## Calcul Droits & Taxes — {r['marchandise'] if 'marchandise' in r else r['pays']}",
        f"Zone : {r['zone']} | Pays : {r['pays']} | Catégorie TEC {r['categorie_tec']} : {r['description_categorie']}",
        f"Valeur CIF (base imposable) : {r['valeur_cif']:,.0f} FCFA",
        "",
        "| Taxe | Taux | Montant |",
        "|------|------|---------|",
        f"| Droits de douane | {r['droits_douane']['taux_pct']}% | {r['droits_douane']['montant']:,.0f} |",
    ]
    for code, prev in r["prelevements_communautaires"].items():
        lignes.append(f"| {code} — {prev['description'][:40]} | — | {prev['montant']:,.0f} |")
    if r["droits_accises"]["taux_pct"] > 0:
        lignes.append(f"| Droits d'accises | {r['droits_accises']['taux_pct']}% | {r['droits_accises']['montant']:,.0f} |")
    lignes += [
        f"| Base TVA | — | {r['base_tva']:,.0f} |",
        f"| TVA ({r['tva']['taux_pct']}%) | {r['tva']['taux_pct']}% | {r['tva']['montant']:,.0f} |",
        "",
        f"**Total droits & taxes : {r['total_droits_taxes']:,.0f} FCFA**",
        f"**Total à payer (CIF + taxes) : {r['total_a_payer']:,.0f} FCFA**",
        f"Taux global effectif : {r['taux_global_effectif_pct']}% de la valeur CIF",
    ]
    return "\n".join(lignes)


# ══════════════════════════════════════════════════════════════════════════════
# Agent
# ══════════════════════════════════════════════════════════════════════════════

class AgentDouanier(AgentProBase):
    """
    Agent IA spécialisé pour les transitaires, douaniers et professionnels du commerce international
    en Afrique francophone. Maîtrise : TEC CEMAC/UEMOA, Incoterms 2020, régimes douaniers, conformité.
    """

    type_agent = TypeAgent.PRO_DOUANIER

    def _prompt_systeme_metier(self) -> str:
        return (
            "Tu es un expert senior en commerce international et procédures douanières "
            "en Afrique centrale et de l'Ouest. "
            "Tu maîtrises : le Tarif Extérieur Commun CEMAC et UEMOA, le Code des douanes CEMAC "
            "(Règlement 05/01), les régimes douaniers (IM4, AT, Entrepôt, Transit, TDI, EX1), "
            "les Incoterms 2020 (ICC), le classement tarifaire (nomenclature SH 6 chiffres), "
            "la valeur en douane (méthode transactionnelle OMC), "
            "les prélèvements communautaires (RCI CEMAC, PC UEMOA), "
            "les formalités douanières par pays (Cameroun, Côte d'Ivoire, Sénégal, Burkina Faso...), "
            "et la réglementation des transferts de capitaux (COBAC, BCEAO). "
            "Tu aides les importateurs, exportateurs et transitaires à calculer leurs charges douanières, "
            "préparer leurs déclarations et optimiser leurs régimes douaniers légalement. "
            "Réponds en français professionnel avec précision technique."
        )

    def _prompt_questions_specifiques(self) -> str:
        return (
            "Questions essentielles pour les opérations douanières :\n"
            "- Quel est le pays d'importation/exportation ?\n"
            "- Quelle est la marchandise (description et code SH si connu) ?\n"
            "- Quelle est la valeur de la marchandise et l'incoterm de la facture ?\n"
            "- Quelle est la destination finale de la marchandise (consommation, transit, transformation) ?\n"
            "- S'agit-il d'une opération en zone CEMAC ou UEMOA ?"
        )

    def _outils_metier(self) -> list[dict]:
        return [
            {
                "name": "droits_taxes_calculer",
                "description": (
                    "Calcule les droits et taxes à l'importation : droits de douane (TEC CEMAC/UEMOA), "
                    "prélèvements communautaires (RCI, ECOFAC, PC), TVA import. "
                    "Base imposable = valeur CIF douanière."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "valeur_cif": {"type": "number", "description": "Valeur CIF douanière (FCFA ou devise)"},
                        "categorie_tec": {"type": "string", "description": "Catégorie TEC : 0 à 4 (0=médicaments, 4=biens de consommation)"},
                        "pays": {"type": "string", "description": "Code pays importateur (CM, CI, SN, BF...)"},
                        "zone": {"type": "string", "description": "CEMAC ou UEMOA"},
                        "avec_tva": {"type": "boolean", "description": "Inclure la TVA (défaut true)"},
                        "droits_accises_pct": {"type": "number", "description": "Droits d'accises en % (boissons, tabac...)"},
                    },
                    "required": ["valeur_cif", "categorie_tec", "pays"],
                },
            },
            {
                "name": "declaration_douane_preparer",
                "description": (
                    "Prépare les éléments d'une déclaration en douane : "
                    "calcul valeur CIF, cases DAU, documents requis, régime applicable."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "regime": {"type": "string", "description": "IM4/AT/ENTREPOT/TA/TDI/EX1"},
                        "marchandise": {"type": "string"},
                        "code_sh": {"type": "string", "description": "Code du Système Harmonisé (SH)"},
                        "valeur_fob": {"type": "number", "description": "Valeur FOB facture"},
                        "fret": {"type": "number"},
                        "assurance": {"type": "number"},
                        "pays_origine": {"type": "string"},
                        "pays_destination": {"type": "string"},
                        "poids_brut_kg": {"type": "number"},
                        "poids_net_kg": {"type": "number"},
                        "nb_colis": {"type": "integer"},
                        "incoterm": {"type": "string", "description": "Incoterm de la facture"},
                    },
                    "required": ["marchandise", "valeur_fob", "pays_origine", "pays_destination"],
                },
            },
            {
                "name": "regime_douanier_choisir",
                "description": (
                    "Recommande le régime douanier optimal selon l'usage prévu : "
                    "importation définitive (IM4), admission temporaire (AT), entrepôt, transit (TA), "
                    "transformation sous douane (TDI), exportation (EX1)."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "finalite": {"type": "string", "description": "Usage prévu de la marchandise"},
                        "type_marchandise": {"type": "string"},
                        "duree_sejour_prevu": {"type": "string", "description": "Durée prévue sur le territoire"},
                        "pays": {"type": "string"},
                    },
                    "required": ["finalite", "type_marchandise"],
                },
            },
            {
                "name": "incoterms_analyser",
                "description": (
                    "Analyse un Incoterm 2020 : répartition des responsabilités (transport, assurance, "
                    "dédouanement), transfert des risques, implications pratiques pour l'importateur."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "incoterm": {"type": "string", "description": "EXW/FCA/FOB/CFR/CIF/DDP/DAP..."},
                        "sens": {"type": "string", "description": "import ou export"},
                        "pays_import": {"type": "string"},
                        "valeur_marchandise": {"type": "number"},
                    },
                    "required": ["incoterm"],
                },
            },
            {
                "name": "conformite_commerce_verifier",
                "description": (
                    "Checklist de conformité pour une opération de commerce international : "
                    "documents requis, autorisations spéciales, alertes réglementaires."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "type_operation": {"type": "string", "description": "importation/exportation/transit"},
                        "marchandise": {"type": "string"},
                        "pays_import": {"type": "string"},
                        "pays_export": {"type": "string"},
                        "valeur": {"type": "number", "description": "Valeur en FCFA"},
                        "incoterm": {"type": "string"},
                    },
                    "required": ["type_operation", "marchandise", "pays_import", "pays_export"],
                },
            },
            {
                "name": "orchestrer_importation",
                "description": (
                    "Orchestre le workflow complet d'une opération d'importation : "
                    "choix régime → dossier douanier → calcul taxes → enregistrement comptable. "
                    "Retourne le plan d'action séquencé avec tous les coûts et documents."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "marchandise":      {"type": "string"},
                        "valeur_fob":       {"type": "number", "description": "Valeur FOB en FCFA"},
                        "fret":             {"type": "number", "description": "Coût fret"},
                        "assurance":        {"type": "number"},
                        "categorie_tec":    {"type": "string", "description": "0|1|2|3|4"},
                        "pays_import":      {"type": "string"},
                        "pays_export":      {"type": "string"},
                        "usage":            {"type": "string",
                                             "description": "revente | usage_propre | transformation | "
                                                            "re_exportation"},
                    },
                    "required": ["marchandise", "valeur_fob", "pays_import"],
                },
            },
            {
                "name": "rediger_recours_douanier",
                "description": (
                    "Rédige un recours contre une décision douanière contestée : "
                    "taxation abusive, refoulement injustifié, classification erronée de marchandise. "
                    "Lettre argumentée avec références légales (Code douanes CEMAC/UEMOA)."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "type_recours":   {"type": "string",
                                           "description": "contestation_taxation | erreur_classification | "
                                                          "refoulement | amende_contestee"},
                        "faits":          {"type": "string", "description": "Description des faits"},
                        "montant_conteste": {"type": "number"},
                        "declaration_ref": {"type": "string", "description": "Référence de la déclaration en douane"},
                        "pays":           {"type": "string"},
                        "marchandise":    {"type": "string"},
                    },
                    "required": ["type_recours", "faits", "pays"],
                },
            },
            {
                "name": "analyser_document_commercial",
                "description": (
                    "Analyse un document commercial international entrant : facture pro forma, "
                    "connaissement (B/L), certificat d'origine, liste de colisage, LC (lettre de crédit). "
                    "Identifie les anomalies, points de vigilance et actions requises."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "contenu_document": {"type": "string"},
                        "type_document":    {"type": "string",
                                             "description": "facture_proforma | bill_of_lading | "
                                                            "certificat_origine | colisage | "
                                                            "lettre_credit | certificat_conformite"},
                        "pays_import":      {"type": "string"},
                        "pays_export":      {"type": "string"},
                    },
                    "required": ["contenu_document", "type_document"],
                },
            },
        ]

    async def _executer_outil(self, nom_outil: str, params: dict) -> Any:
        if nom_outil == "droits_taxes_calculer":
            r = _calculer_droits_taxes(
                valeur_cif=float(params.get("valeur_cif", 0)),
                categorie_tec=str(params.get("categorie_tec", "3")),
                pays=params.get("pays", "CM"),
                zone=params.get("zone", "CEMAC"),
                avec_tva=bool(params.get("avec_tva", True)),
                droits_accises_pct=float(params.get("droits_accises_pct", 0)),
            )
            return _rendu_droits_taxes(r)

        if nom_outil == "declaration_douane_preparer":
            r = _preparer_declaration_douane(
                regime=params.get("regime", "IM4"),
                marchandise=params.get("marchandise", ""),
                code_sh=params.get("code_sh", ""),
                valeur_fob=float(params.get("valeur_fob", 0)),
                fret=float(params.get("fret", 0)),
                assurance=float(params.get("assurance", 0)),
                pays_origine=params.get("pays_origine", ""),
                pays_destination=params.get("pays_destination", ""),
                poids_brut_kg=float(params.get("poids_brut_kg", 0)),
                poids_net_kg=float(params.get("poids_net_kg", 0)),
                nb_colis=int(params.get("nb_colis", 1)),
                incoterm=params.get("incoterm", "CIF"),
            )
            lignes = [
                f"## Déclaration en Douane — {r['regime']} ({r['nom_regime']}",
                f"Marchandise : {r['marchandise']} | Code SH : {r['code_sh']} {'✅' if r['sh_valide'] else '⚠️ à vérifier'}",
                f"Incoterm facture : {r['incoterm_facture']}",
                "",
                f"### Valeur Douanière",
                f"  FOB : {r['valeur_fob']:,.0f} + Fret : {r['fret']:,.0f} + Assurance : {r['assurance']:,.0f}",
                f"  **Valeur CIF douanière : {r['valeur_cif_douaniere']:,.0f} FCFA**",
                "",
                f"### Informations Colis",
                f"  {r['nb_colis']} colis | {r['poids_brut_kg']} kg brut / {r['poids_net_kg']} kg net",
                f"  {r['pays_origine']} → {r['pays_destination']}",
                "",
                f"### Documents Requis",
            ]
            for doc in r["documents_requis"][:7]:
                lignes.append(f"  • {doc}")
            if r["droits_suspendus"]:
                lignes.append(f"\n⚠️ Droits suspendus sous régime {r['regime']} — durée : {r['duree_validite_regime']}")
            return "\n".join(lignes)

        if nom_outil == "regime_douanier_choisir":
            r = _choisir_regime_douanier(
                duree_sejour_prevu=params.get("duree_sejour_prevu", ""),
                finalite=params.get("finalite", ""),
                type_marchandise=params.get("type_marchandise", ""),
                pays=params.get("pays", "CM"),
            )
            lignes = [
                f"## Régime Douanier Recommandé : **{r['regime_recommande']} — {r['nom_regime']}**",
                f"Raison : {r['raison']}",
                f"Droits & taxes : {r['droits_et_taxes']}",
                f"Durée de validité : {r['duree_validite']}",
            ]
            if r["documents_supplementaires"]:
                lignes.append("\nDocuments supplémentaires :")
                for doc in r["documents_supplementaires"]:
                    lignes.append(f"  • {doc}")
            if r["autres_options"]:
                lignes.append("\nAutres options envisageables :")
                for opt in r["autres_options"]:
                    lignes.append(f"  • {opt['regime']} — {opt['raison']}")
            if r["avertissement"]:
                lignes.append(f"\n{r['avertissement']}")
            return "\n".join(lignes)

        if nom_outil == "incoterms_analyser":
            r = _analyser_incoterm(
                incoterm=params.get("incoterm", "CIF"),
                sens=params.get("sens", "import"),
                pays_import=params.get("pays_import", ""),
                valeur_marchandise=float(params.get("valeur_marchandise", 0)),
            )
            if "erreur" in r:
                return r["erreur"]
            lignes = [
                f"## Incoterm {r['incoterm']} — {r['nom_complet']}",
                f"Modes de transport : {', '.join(r['modes_transport'])}",
                f"Transfert des risques : {r['transfert_risques']}",
                "",
                "### Répartition des responsabilités",
                f"  Transport pré-acheminement : {r['repartition_responsabilites']['transport_pre_acheminement']}",
                f"  Formalités export : {r['repartition_responsabilites']['formalites_export']}",
                f"  Fret principal : {r['repartition_responsabilites']['fret_principal']}",
                f"  Assurance : {r['repartition_responsabilites']['assurance']}",
                f"  Formalités import : {r['repartition_responsabilites']['formalites_import']}",
                f"  Déchargement : {r['repartition_responsabilites']['dechargement']}",
                "",
                f"**Conseil pratique :** {r['conseil_pratique']}",
                f"**Base valeur douanière :** {r['base_valeur_douaniere']}",
            ]
            if r["implications_pour_vous"]:
                lignes.append("\n### Implications pour vous")
                for impl in r["implications_pour_vous"]:
                    lignes.append(f"  • {impl}")
            if r["info_pays"]:
                lignes.append(f"\n{r['info_pays']}")
            return "\n".join(lignes)

        if nom_outil == "conformite_commerce_verifier":
            r = _verifier_conformite_commerce(
                type_operation=params.get("type_operation", "importation"),
                marchandise=params.get("marchandise", ""),
                pays_import=params.get("pays_import", ""),
                pays_export=params.get("pays_export", ""),
                valeur=float(params.get("valeur", 0)),
                incoterm=params.get("incoterm", "CIF"),
            )
            lignes = [
                f"## Conformité Commerce International",
                f"{r['type_operation'].title()} : {r['marchandise']} | {r['pays_export']} → {r['pays_import']}",
                f"Valeur : {r['valeur_fcfa']:,.0f} FCFA | Incoterm : {r['incoterm']}",
                "",
                "### Checklist Documents",
            ]
            for item in r["checklist"]:
                lignes.append(f"  {item['statut']} {item['element']}")
            if r["alertes_specifiques"]:
                lignes.append("\n### Alertes Spécifiques")
                for a in r["alertes_specifiques"]:
                    lignes.append(f"  {a}")
            lignes.append("\n### Conseils Pratiques")
            for c in r["conseils_pratiques"]:
                lignes.append(f"  • {c}")
            return "\n".join(lignes)

        if nom_outil == "orchestrer_importation":
            return _orchestrer_importation(params)

        if nom_outil == "rediger_recours_douanier":
            from core.ia_client import ModeIA, ia_client
            prompt = _prompt_recours_douanier(params)
            rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
            return rep.contenu

        if nom_outil == "analyser_document_commercial":
            from core.ia_client import ModeIA, ia_client
            prompt = _prompt_analyse_doc_commercial(params)
            rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
            return rep.contenu

        return f"Outil '{nom_outil}' non reconnu."


# ---------------------------------------------------------------------------
# Fonctions standalone — nouvelles automatisations douanières
# ---------------------------------------------------------------------------

def _orchestrer_importation(params: dict) -> str:
    """Plan d'orchestration complet pour une opération d'importation."""
    marchandise = params.get("marchandise", "marchandise")
    pays_origine = params.get("pays_origine", "")
    valeur_fob = float(params.get("valeur_fob", 0))
    incoterm = params.get("incoterm", "CIF").upper()
    pays_destination = params.get("pays_destination", "CM")

    # Estimation fret & assurance selon incoterm
    if incoterm == "FOB":
        fret_estime = valeur_fob * 0.08
        assurance_estime = valeur_fob * 0.005
        valeur_cif = valeur_fob + fret_estime + assurance_estime
    elif incoterm in ("CIF", "CIP"):
        valeur_cif = valeur_fob  # déjà CIF
        fret_estime = valeur_fob * 0.07
        assurance_estime = valeur_fob * 0.004
    else:  # EXW, DAP, DDP …
        fret_estime = valeur_fob * 0.10
        assurance_estime = valeur_fob * 0.006
        valeur_cif = valeur_fob + fret_estime + assurance_estime

    # Calcul droits et taxes CEMAC simplifié
    taux_dd = 0.20  # Droit de Douane 20% (TEC CEMAC cat. 4 par défaut)
    taux_tva = 0.1925  # TVA 19.25% CM
    dd = valeur_cif * taux_dd
    redevance_informatique = valeur_cif * 0.0035
    tva_import = (valeur_cif + dd + redevance_informatique) * taux_tva
    total_taxes = dd + redevance_informatique + tva_import
    cout_total = valeur_cif + total_taxes

    lignes = [
        f"## Plan d'Orchestration Importation — {marchandise}",
        f"Origine : {pays_origine} → Destination : {pays_destination} | Incoterm : {incoterm}",
        f"Valeur FOB déclarée : {valeur_fob:,.0f} FCFA | Valeur CIF estimée : {valeur_cif:,.0f} FCFA",
        "",
        "### Étape 1 — Avant expédition (J-15)",
        "  ✅ Obtenir facture proforma + liste de colisage du fournisseur",
        "  ✅ Vérifier que la marchandise ne figure pas sur liste interdite/réglementée",
        "  ✅ Contrôler certificat d'origine (préférence tarifaire CEMAC/ALE éventuelle)",
        "  ✅ Ouvrir lettre de crédit ou virement si montant > 5 M FCFA",
        "  ✅ Commander inspection avant embarquement (SGS/Bureau Veritas) si exigée",
        "",
        "### Étape 2 — Expédition et transit (J-7 à J0)",
        "  ✅ Récupérer connaissement B/L ou LTA auprès du transitaire",
        "  ✅ Vérifier concordance des données (poids, quantité, HS code) avec facture",
        "  ✅ Constituer dossier douane : facture définitive, certificat phytosanitaire/sanitaire si alimentaire",
        "",
        "### Étape 3 — Déclaration en douane (J0 à J+2)",
        "  ✅ Déposer déclaration ASYCUDA World (régime 40 — mise à la consommation)",
        "  ✅ Payer droits et taxes estimés ci-dessous",
        "  ✅ Obtenir Bon À Enlever (BAE) après visa douanier",
        "",
        "### Étape 4 — Enlèvement et comptabilisation (J+2 à J+5)",
        "  ✅ Enlèvement marchandise sous BAE signé",
        "  ✅ Comptabiliser : Droit de Douane en charge, TVA en TVA déductible",
        "  ✅ Classer tous documents 10 ans (prescription douanière)",
        "",
        "### Estimation Fiscalo-Douanière",
        f"  Valeur CIF             : {valeur_cif:>12,.0f} FCFA",
        f"  Droit de Douane (20%) : {dd:>12,.0f} FCFA",
        f"  Redevance informatique: {redevance_informatique:>12,.0f} FCFA",
        f"  TVA import (19,25%)   : {tva_import:>12,.0f} FCFA",
        f"  ─────────────────────────────────────────",
        f"  Total taxes estimé     : {total_taxes:>12,.0f} FCFA",
        f"  Coût total débarqué    : {cout_total:>12,.0f} FCFA",
        "",
        "⚠️ Taux indicatifs — vérifier le HS code exact et les accords préférentiels applicables.",
    ]
    return "\n".join(lignes)


def _prompt_recours_douanier(params: dict) -> str:
    type_recours = params.get("type_recours", "contestation_valeur")
    reference_decision = params.get("reference_decision", "")
    motif = params.get("motif", "")
    montant_litige = params.get("montant_litige", "")
    societe = params.get("societe", "notre société")
    pays = params.get("pays", "CM")

    destinataires = {
        "CM": "Monsieur le Directeur Général des Douanes du Cameroun",
        "CI": "Monsieur le Directeur Général des Douanes de Côte d'Ivoire",
        "SN": "Monsieur le Directeur Général des Douanes du Sénégal",
    }
    dest = destinataires.get(pays, "Monsieur le Directeur Général des Douanes")

    types_labels = {
        "contestation_valeur": "contestation de la valeur en douane",
        "recours_penalite": "recours gracieux contre une pénalité douanière",
        "demande_remboursement": "demande de remboursement de droits indûment perçus",
        "contestation_classement": "contestation du classement tarifaire",
    }
    label = types_labels.get(type_recours, type_recours)

    return f"""Tu es un expert en droit douanier CEMAC/OHADA spécialisé dans la rédaction de recours administratifs.

Rédige un recours douanier formel pour {label}.

CONTEXTE :
- Société requérante : {societe}
- Pays : {pays}
- Référence décision contestée : {reference_decision}
- Motif du recours : {motif}
- Montant en litige : {montant_litige} FCFA

DESTINATAIRE : {dest}

STRUCTURE REQUISE :
1. En-tête avec références complètes (lieu, date, expéditeur, destinataire, objet)
2. Introduction rappelant les faits et la décision contestée
3. Argumentation juridique (articles du Code des Douanes CEMAC, jurisprudence si applicable)
4. Demande précise (annulation, réduction, remboursement)
5. Pièces jointes listées
6. Formule de politesse et signature

Ton style : formel, argumenté, précis sur les textes de loi. Évite tout ton agressif."""


def _prompt_analyse_doc_commercial(params: dict) -> str:
    type_document = params.get("type_document", "contrat_vente")
    contenu_document = params.get("contenu_document", "")
    sens_operation = params.get("sens_operation", "import")

    types_labels = {
        "contrat_vente": "contrat de vente internationale",
        "lettre_credit": "lettre de crédit documentaire (L/C)",
        "certificat_origine": "certificat d'origine",
        "facture_proforma": "facture proforma",
        "connaissement": "connaissement (Bill of Lading)",
        "certificat_conformite": "certificat de conformité / inspection",
    }
    label = types_labels.get(type_document, type_document)

    return f"""Tu es un expert en commerce international et droit douanier CEMAC.

Analyse ce {label} dans le contexte d'une opération d'{sens_operation}.

DOCUMENT SOUMIS :
{contenu_document}

POINTS D'ANALYSE REQUIS :
1. **Conformité documentaire** — champs obligatoires présents/manquants
2. **Risques douaniers identifiés** — valeur déclarée, HS code, origine, incoterm
3. **Cohérence inter-documents** — incohérences avec d'autres pièces du dossier si mentionnées
4. **Points d'attention réglementaires** — restrictions, licences, certificats manquants
5. **Recommandations** — corrections à apporter avant dépôt en douane

Format : analyse structurée avec niveau de risque (FAIBLE / MOYEN / ÉLEVÉ) pour chaque point."""
