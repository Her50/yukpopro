"""
WorkflowEngine — Moteur de workflows déterministes SANS IA.

Principe : toutes les tâches dont la logique est connue et règlementaire
sont exécutées en Python pur. L'IA n'est appelée QUE pour :
  - Langage naturel (comprendre une instruction floue)
  - Documents non structurés (OCR narratif)
  - Rédaction de textes
  - Décisions sur cas ambigus hors règles

Avantages :
  - 0 coût API pour les calculs déterministes
  - Instantané (< 5ms vs 300ms pour un appel Claude)
  - 100% prévisible et auditable
  - Testable unitairement sans mock IA
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger("yukpo_assurance.workflow_engine")


# ─── Types de résultats ───────────────────────────────────────────────────────

class StatutWorkflow(str, Enum):
    OK          = "ok"
    ECHEC       = "echec"
    EN_ATTENTE  = "en_attente"   # nécessite intervention humaine
    IA_REQUISE  = "ia_requise"   # cas ambigu → déléguer à l'IA


@dataclass
class ResultatWorkflow:
    statut:   StatutWorkflow
    donnees:  dict = field(default_factory=dict)
    message:  str  = ""
    erreur:   Optional[str] = None
    necessite_validation: bool = False
    raison_validation:    str  = ""


# ─── Calculs de primes RC Auto (déterministe) ─────────────────────────────────

# Barèmes CIMA par pays — prime RC seule en FCFA
_BAREME_RC: dict[str, dict] = {
    "CM": {  # Cameroun
        "VP_inf_1600":  {"min": 75_000,  "moy": 120_000},
        "VP_sup_1600":  {"min": 90_000,  "moy": 160_000},
        "UT_inf_3500":  {"min": 120_000, "moy": 200_000},
        "taxi":         {"min": 150_000, "moy": 280_000},
        "bus":          {"min": 250_000, "moy": 500_000},
        "moto":         {"min": 25_000,  "moy": 45_000},
    },
    "CI": {  # Côte d'Ivoire
        "VP_inf_1600":  {"min": 70_000,  "moy": 115_000},
        "VP_sup_1600":  {"min": 85_000,  "moy": 155_000},
        "UT_inf_3500":  {"min": 115_000, "moy": 190_000},
        "taxi":         {"min": 145_000, "moy": 270_000},
        "bus":          {"min": 240_000, "moy": 480_000},
        "moto":         {"min": 22_000,  "moy": 42_000},
    },
    "SN": {  # Sénégal
        "VP_inf_1600":  {"min": 72_000,  "moy": 118_000},
        "VP_sup_1600":  {"min": 88_000,  "moy": 158_000},
        "UT_inf_3500":  {"min": 118_000, "moy": 195_000},
        "taxi":         {"min": 148_000, "moy": 275_000},
        "bus":          {"min": 245_000, "moy": 490_000},
        "moto":         {"min": 23_000,  "moy": 43_000},
    },
}
# Taux taxes RC par pays
_TAXES_RC: dict[str, float] = {
    "CM": 0.15, "CI": 0.15, "SN": 0.14, "GA": 0.15,
    "CG": 0.15, "CF": 0.15, "TD": 0.15, "NE": 0.15,
    "ML": 0.15, "BF": 0.15, "TG": 0.15, "BJ": 0.15,
    "GW": 0.10, "GQ": 0.15, "KM": 0.12,
}
_FGA: dict[str, float] = {k: 0.02 for k in _TAXES_RC}  # 2% partout

# Coefficients usage
_COEFF_USAGE = {
    "personnel":   1.00,
    "commercial":  1.50,
    "taxi":        2.20,
    "transport":   2.50,
    "location":    1.80,
}

# CRM (bonus-malus) : bornes Art. 217 CIMA
_CRM_MIN = 0.50
_CRM_MAX = 3.50


def calculer_prime_rc_auto(
    pays: str,
    categorie: str,        # VP_inf_1600 | VP_sup_1600 | UT_inf_3500 | taxi | bus | moto
    usage: str = "personnel",
    crm: float = 1.00,
    utiliser_prime_min: bool = False,
) -> ResultatWorkflow:
    """Calcule la prime RC auto selon le barème CIMA — 0 appel IA."""
    pays = pays.upper()
    bareme = _BAREME_RC.get(pays, _BAREME_RC["CM"])
    cat = bareme.get(categorie)
    if not cat:
        return ResultatWorkflow(
            statut=StatutWorkflow.IA_REQUISE,
            message=f"Catégorie '{categorie}' inconnue — analyse IA requise",
        )

    prime_base = cat["min"] if utiliser_prime_min else cat["moy"]
    coeff = _COEFF_USAGE.get(usage, 1.00)
    crm = max(_CRM_MIN, min(_CRM_MAX, crm))
    prime_nette = round(prime_base * coeff * crm)
    taxe = round(prime_nette * _TAXES_RC.get(pays, 0.15))
    fga  = round(prime_nette * _FGA.get(pays, 0.02))
    prime_ttc = prime_nette + taxe + fga

    return ResultatWorkflow(
        statut=StatutWorkflow.OK,
        donnees={
            "prime_nette_fcfa":   prime_nette,
            "taxe_fcfa":          taxe,
            "fga_fcfa":           fga,
            "prime_ttc_fcfa":     prime_ttc,
            "crm_applique":       crm,
            "pays":               pays,
            "categorie":          categorie,
            "usage":              usage,
            "base_legale":        "Art. 200-201 Code CIMA",
        },
        message=f"Prime RC calculée : {prime_ttc:,} FCFA TTC".replace(",", " "),
    )


# ─── Vérification validité police (déterministe) ─────────────────────────────

def verifier_validite_police(
    date_effet: date,
    date_expiry: date,
    prime_payee: bool,
    date_sinistre: Optional[date] = None,
) -> ResultatWorkflow:
    """Vérifie si une police est valide à une date donnée — 0 appel IA."""
    cible = date_sinistre or date.today()

    if not (date_effet <= cible <= date_expiry):
        return ResultatWorkflow(
            statut=StatutWorkflow.ECHEC,
            message=f"Police non valide au {cible} (période : {date_effet} → {date_expiry})",
            donnees={"valide": False, "raison": "hors_periode"},
        )
    if not prime_payee:
        return ResultatWorkflow(
            statut=StatutWorkflow.ECHEC,
            message="Prime non payée — police suspendue",
            donnees={"valide": False, "raison": "prime_impayee"},
        )
    return ResultatWorkflow(
        statut=StatutWorkflow.OK,
        donnees={"valide": True},
        message="Police valide",
    )


# ─── Règles de fraude déterministes (Art. 12 CIMA) ───────────────────────────

@dataclass
class SignauxFraude:
    nb_sinistres_12_mois:     int   = 0
    jours_depuis_souscription:int   = 9999
    montant_declare:          float = 0
    montant_expertise:        float = 0
    declaration_tardive:      bool  = False
    jours_declaration:        int   = 0
    force_majeure_declaree:   bool  = False


def scorer_fraude_deterministe(s: SignauxFraude) -> ResultatWorkflow:
    """
    Score de fraude 0-100 basé sur règles connues.
    Ne nécessite PAS l'IA — règles pures CIMA.
    Score > 60 → déléguer à l'IA pour analyse narrative.
    """
    score = 0
    indicateurs: list[str] = []

    # Fréquence sinistres
    if s.nb_sinistres_12_mois >= 3:
        score += 40
        indicateurs.append(f"{s.nb_sinistres_12_mois} sinistres en 12 mois")
    elif s.nb_sinistres_12_mois == 2:
        score += 20
        indicateurs.append("2 sinistres en 12 mois")

    # Délai depuis souscription (fraude classique : sinistre très tôt)
    if s.jours_depuis_souscription < 30:
        score += 35
        indicateurs.append(f"Sinistre {s.jours_depuis_souscription}j après souscription")
    elif s.jours_depuis_souscription < 90:
        score += 15
        indicateurs.append(f"Sinistre {s.jours_depuis_souscription}j après souscription")

    # Écart déclaré vs expertisé
    if s.montant_expertise > 0:
        ecart = abs(s.montant_declare - s.montant_expertise) / s.montant_expertise
        if ecart > 0.5:
            score += 25
            indicateurs.append(f"Écart déclaré/expertisé : {ecart*100:.0f}%")

    # Déclaration tardive sans force majeure (Art. 12 : 5 jours)
    if s.declaration_tardive and not s.force_majeure_declaree:
        if s.jours_declaration > 15:
            score += 15
            indicateurs.append(f"Déclaration {s.jours_declaration}j après sinistre")
        elif s.jours_declaration > 5:
            score += 5

    score = min(100, score)

    # > 60 : cas ambigu → analyse IA narrative recommandée
    if score > 60:
        return ResultatWorkflow(
            statut=StatutWorkflow.IA_REQUISE,
            donnees={"score": score, "indicateurs": indicateurs},
            message=f"Score fraude élevé ({score}/100) — analyse IA requise",
        )

    return ResultatWorkflow(
        statut=StatutWorkflow.OK,
        donnees={"score": score, "indicateurs": indicateurs, "niveau": _niveau_fraude(score)},
        message=f"Score fraude : {score}/100 ({_niveau_fraude(score)})",
    )


def _niveau_fraude(score: int) -> str:
    if score < 20:  return "faible"
    if score < 40:  return "modéré"
    if score < 60:  return "élevé"
    return "critique"


# ─── Calcul indemnisation (déterministe) ──────────────────────────────────────

# Barème corporel CIMA (Art. 220) — capital référence en FCFA
_CAPITAL_REF_CIMA = 12_000_000  # FCFA

def calculer_indemnisation(
    type_sinistre: str,      # "materiel" | "corporel" | "deces"
    montant_declare: float,
    ipp_pct: float = 0,      # Incapacité Permanente Partielle (0-100%)
    itt_jours: int = 0,      # Incapacité Temporaire de Travail
    franchise: float = 50_000,
) -> ResultatWorkflow:
    """Calcule l'indemnisation selon barème CIMA — 0 appel IA."""

    if type_sinistre == "materiel":
        base = max(0, montant_declare - franchise)
        return ResultatWorkflow(
            statut=StatutWorkflow.OK,
            donnees={
                "montant_propose": base,
                "franchise":       franchise,
                "base_legale":     "Conditions générales contrat",
            },
            message=f"Indemnisation matérielle : {base:,.0f} FCFA".replace(",", " "),
        )

    if type_sinistre == "corporel":
        montant_ipp  = round(_CAPITAL_REF_CIMA * (ipp_pct / 100))
        montant_itt  = round(itt_jours * 15_000)  # 15 000 FCFA/jour ITT standard
        total        = montant_ipp + montant_itt
        return ResultatWorkflow(
            statut=StatutWorkflow.OK,
            donnees={
                "montant_ipp_fcfa":  montant_ipp,
                "montant_itt_fcfa":  montant_itt,
                "montant_total":     total,
                "ipp_pct":           ipp_pct,
                "itt_jours":         itt_jours,
                "base_legale":       "Art. 220 Code CIMA",
            },
            message=f"Indemnisation corporelle : {total:,.0f} FCFA".replace(",", " "),
        )

    if type_sinistre == "deces":
        # Barème décès CIMA : capital référence × 100%
        return ResultatWorkflow(
            statut=StatutWorkflow.OK,
            donnees={
                "montant_propose": _CAPITAL_REF_CIMA,
                "base_legale":     "Art. 220 Code CIMA — décès",
            },
            message=f"Indemnisation décès : {_CAPITAL_REF_CIMA:,} FCFA".replace(",", " "),
        )

    return ResultatWorkflow(
        statut=StatutWorkflow.IA_REQUISE,
        message=f"Type sinistre '{type_sinistre}' non standard — analyse IA requise",
    )


# ─── Calcul ratios prudentiels CIMA (déterministe) ───────────────────────────

def calculer_marge_solvabilite_non_vie(
    primes_nettes: float,
    sinistres_moy_3ans: float,
) -> ResultatWorkflow:
    """Art. 337-1 CIMA — marge solvabilité Non-Vie."""
    methode1 = primes_nettes * 0.23
    methode2 = sinistres_moy_3ans * 0.26
    minimum  = 300_000_000
    marge    = max(methode1, methode2, minimum)
    return ResultatWorkflow(
        statut=StatutWorkflow.OK,
        donnees={
            "marge_requise":      marge,
            "methode1_primes":    methode1,
            "methode2_sinistres": methode2,
            "minimum_regl":       minimum,
            "base_legale":        "Art. 337-1 Code CIMA",
        },
        message=f"Marge solvabilité Non-Vie requise : {marge:,.0f} FCFA".replace(",", " "),
    )


def calculer_marge_solvabilite_vie(
    pm_brutes: float,
    capital_sous_risque_net: float,
) -> ResultatWorkflow:
    """Art. 338-1 CIMA — marge solvabilité Vie."""
    composante1 = pm_brutes * 0.04
    composante2 = capital_sous_risque_net * 0.003
    minimum     = 500_000_000
    marge       = max(composante1 + composante2, minimum)
    return ResultatWorkflow(
        statut=StatutWorkflow.OK,
        donnees={
            "marge_requise":   marge,
            "composante_pm":   composante1,
            "composante_csr":  composante2,
            "minimum_regl":    minimum,
            "base_legale":     "Art. 338-1 Code CIMA",
        },
        message=f"Marge solvabilité Vie requise : {marge:,.0f} FCFA".replace(",", " "),
    )


# ─── Vérification délais réglementaires (déterministe) ───────────────────────

def verifier_delai_reglementaire(
    type_delai: str,
    date_evenement: date,
    date_action: Optional[date] = None,
) -> ResultatWorkflow:
    """Vérifie le respect des délais CIMA — 0 appel IA."""
    cible = date_action or date.today()
    jours_ecoules = (cible - date_evenement).days

    delais = {
        "declaration_sinistre":       5,   # Art. 12 — jours ouvrés
        "accuse_reception":           10,  # Art. 12-bis
        "offre_indemnisation":        90,  # Art. 12-bis — 3 mois
        "paiement_apres_accord":      45,  # Art. 12-ter
        "offre_corporelle_rc_auto":   90,  # Art. 210
        "reglement_rc_auto":          30,  # Art. 231
        "reglement_sinistre_vie":     30,  # Art. 73
        "resiliation_preavis":        60,  # Art. 9
        "resiliation_non_paiement":   30,  # Art. 10
        "aggravation_risque":         8,   # Art. 17
    }

    limite = delais.get(type_delai)
    if not limite:
        return ResultatWorkflow(
            statut=StatutWorkflow.IA_REQUISE,
            message=f"Délai '{type_delai}' non référencé — vérification IA requise",
        )

    respecte = jours_ecoules <= limite
    return ResultatWorkflow(
        statut=StatutWorkflow.OK if respecte else StatutWorkflow.ECHEC,
        donnees={
            "respecte":       respecte,
            "jours_ecoules":  jours_ecoules,
            "limite_jours":   limite,
            "depassement":    max(0, jours_ecoules - limite),
        },
        message=(
            f"Délai respecté ({jours_ecoules}/{limite} jours)"
            if respecte
            else f"⚠ Délai dépassé de {jours_ecoules - limite} jours"
        ),
    )


# ─── Codification comptable PCSA (déterministe) ──────────────────────────────

_PLAN_COMPTABLE_PCSA = {
    "prime_rc_auto":           ("7011", "4411", "Primes RC Auto"),
    "prime_dta":               ("7012", "4411", "Primes DTA"),
    "prime_vie":               ("7021", "4411", "Primes Vie"),
    "sinistre_rc_auto":        ("6011", "4311", "Sinistres RC Auto"),
    "sinistre_corporel":       ("6012", "4311", "Sinistres corporels"),
    "sinistre_vie":            ("6021", "4311", "Sinistres Vie"),
    "commission_courtier":     ("6511", "4611", "Commissions courtiers"),
    "provision_psap":          ("3911", "6911", "Provision PSAP"),
    "provision_pm":            ("3921", "6921", "Provision mathématique"),
    "cession_reassurance":     ("7411", "4711", "Cessions réassurance"),
    "taxe_rc_auto":            ("4451", "4452", "Taxes RC Auto"),
    "fga":                     ("6541", "4541", "Cotisation FGA"),
}

# ─── Tarification MRH (Multirisque Habitation) ───────────────────────────────

_TAUX_MRH = {
    # (taux_incendie, taux_dgeau, taux_vol, taux_rc) selon valeur assurée
    "zone_A":  (0.0025, 0.0015, 0.0020, 0.0008),  # grandes villes
    "zone_B":  (0.0030, 0.0012, 0.0018, 0.0008),  # villes moyennes
    "zone_C":  (0.0035, 0.0010, 0.0015, 0.0008),  # zones rurales
}

def calculer_prime_mrh(
    valeur_batiment: float,
    valeur_contenu: float,
    profil: str = "locataire",         # "locataire" | "proprietaire_occupant" | "bailleur"
    garanties: list = None,             # ["incendie","dgeau","vol","rc","bris_glaces"]
    zone: str = "zone_A",
    franchise_vol_pct: float = 0.10,
) -> ResultatWorkflow:
    """Calcule la prime MRH selon garanties choisies — 0 IA."""
    if garanties is None:
        garanties = ["incendie", "dgeau", "vol", "rc"]

    taux = _TAUX_MRH.get(zone, _TAUX_MRH["zone_A"])
    t_inc, t_dgeau, t_vol, t_rc = taux

    base_batiment = valeur_batiment if profil in ("proprietaire_occupant", "bailleur") else 0
    base_contenu  = valeur_contenu

    prime_incendie  = round((base_batiment + base_contenu) * t_inc)  if "incendie" in garanties else 0
    prime_dgeau     = round((base_batiment + base_contenu) * t_dgeau) if "dgeau"   in garanties else 0
    prime_vol       = round(base_contenu * t_vol * (1 - franchise_vol_pct)) if "vol" in garanties else 0
    prime_rc        = round(100_000 * t_rc * 50)                             if "rc"  in garanties else 0
    prime_bris      = round(base_contenu * 0.0008)                           if "bris_glaces" in garanties else 0
    prime_nette     = prime_incendie + prime_dgeau + prime_vol + prime_rc + prime_bris

    taxe            = round(prime_nette * 0.14)   # 14% taxe assurance
    prime_ttc       = prime_nette + taxe

    return ResultatWorkflow(
        statut=StatutWorkflow.OK,
        donnees={
            "prime_incendie":   prime_incendie,
            "prime_dgeau":      prime_dgeau,
            "prime_vol":        prime_vol,
            "prime_rc":         prime_rc,
            "prime_bris_glaces": prime_bris,
            "prime_nette":      prime_nette,
            "taxe":             taxe,
            "prime_ttc":        prime_ttc,
            "garanties":        garanties,
            "profil":           profil,
            "base_legale":      "Conditions générales MRH CIMA",
        },
        message=f"Prime MRH : {prime_ttc:,} FCFA TTC".replace(",", " "),
    )


# ─── Tarification Transport (Facultés + Corps) ────────────────────────────────

def calculer_prime_transport(
    type_transport: str,         # "maritime" | "aerien" | "terrestre"
    type_garantie:  str,         # "all_risks" | "fautes_communes" | "fap_sauf" | "corps"
    valeur_marchandise: float,
    franchise_pct: float = 0.05,
    trajet: str = "import",      # "import" | "export" | "cabotage"
) -> ResultatWorkflow:
    """Calcule la prime transport (facultés marchandises et corps véhicules) — 0 IA."""

    # Taux de base par mode et garantie
    _TAUX_TRANSPORT = {
        ("maritime", "all_risks"):        0.0080,
        ("maritime", "fautes_communes"):  0.0050,
        ("maritime", "fap_sauf"):         0.0040,
        ("aerien",   "all_risks"):        0.0060,
        ("aerien",   "fautes_communes"):  0.0035,
        ("terrestre","all_risks"):        0.0120,
        ("terrestre","fautes_communes"):  0.0070,
        ("terrestre","corps"):            0.0150,
    }

    taux = _TAUX_TRANSPORT.get((type_transport, type_garantie), 0.0080)

    # Majoration selon trajet
    coeff_trajet = 1.0 if trajet == "export" else 1.15 if trajet == "import" else 1.05

    # Base de calcul = valeur + 10% frais
    base = valeur_marchandise * 1.10
    prime_nette = round(base * taux * coeff_trajet)
    franchise   = round(base * franchise_pct)
    taxe        = round(prime_nette * 0.10)
    prime_ttc   = prime_nette + taxe

    return ResultatWorkflow(
        statut=StatutWorkflow.OK,
        donnees={
            "type_transport":   type_transport,
            "type_garantie":    type_garantie,
            "valeur_assurance": round(base),
            "prime_nette":      prime_nette,
            "franchise_fcfa":   franchise,
            "taxe":             taxe,
            "prime_ttc":        prime_ttc,
            "base_legale":      "Art. 100-110 Code CIMA — Transport",
        },
        message=f"Prime transport : {prime_ttc:,} FCFA TTC".replace(",", " "),
    )


# ─── Tarification RC Professionnelle ─────────────────────────────────────────

_TAUX_RC_PRO = {
    "medecin":          0.0035,
    "avocat":           0.0025,
    "architecte":       0.0045,
    "expert_comptable": 0.0020,
    "garagiste":        0.0060,
    "pharmacien":       0.0030,
    "notaire":          0.0020,
    "commissaire":      0.0025,
    "ingenieur":        0.0035,
    "agent_immobilier": 0.0030,
    "default":          0.0040,
}

def calculer_prime_rc_pro(
    profession: str,
    chiffre_affaires: float,
    plafond_garantie: float,
    avec_rc_exploitation: bool = True,
) -> ResultatWorkflow:
    """Calcule la prime RC Professionnelle — 0 IA."""
    taux_base = _TAUX_RC_PRO.get(profession.lower(), _TAUX_RC_PRO["default"])

    # Dégressivité du taux selon CA
    if chiffre_affaires > 500_000_000:
        facteur = 0.70
    elif chiffre_affaires > 100_000_000:
        facteur = 0.85
    else:
        facteur = 1.00

    prime_rc_pro       = round(chiffre_affaires * taux_base * facteur)
    prime_rc_exploit   = round(prime_rc_pro * 0.25) if avec_rc_exploitation else 0

    # Majoration selon plafond (log dégressif)
    if plafond_garantie > 500_000_000:
        prime_rc_pro = round(prime_rc_pro * 1.20)

    prime_nette = prime_rc_pro + prime_rc_exploit
    taxe        = round(prime_nette * 0.14)
    prime_ttc   = prime_nette + taxe

    return ResultatWorkflow(
        statut=StatutWorkflow.OK,
        donnees={
            "profession":         profession,
            "prime_rc_pro":       prime_rc_pro,
            "prime_rc_exploitation": prime_rc_exploit,
            "plafond_garantie":   plafond_garantie,
            "prime_nette":        prime_nette,
            "taxe":               taxe,
            "prime_ttc":          prime_ttc,
            "base_legale":        "Code CIMA Livre I — RC Professionnelle",
        },
        message=f"Prime RC Pro : {prime_ttc:,} FCFA TTC".replace(",", " "),
    )


# ─── Tarification Accidents Corporels ────────────────────────────────────────

def calculer_prime_accident_corporel(
    capital_deces: float,           # FCFA
    capital_invalide_totale: float, # FCFA
    capital_invalide_partielle: float = 0,
    indemnite_itt_jour: float = 5_000,
    nb_personnes: int = 1,
    profession_risque: str = "bureau",  # "bureau" | "terrain" | "risque_eleve"
) -> ResultatWorkflow:
    """Calcule la prime accidents corporels individuels ou collectifs — 0 IA."""

    _TAUX_ACC = {
        "bureau":       {"deces": 0.0015, "invalide": 0.0020, "itt": 0.0010},
        "terrain":      {"deces": 0.0025, "invalide": 0.0035, "itt": 0.0018},
        "risque_eleve": {"deces": 0.0060, "invalide": 0.0080, "itt": 0.0040},
    }

    taux = _TAUX_ACC.get(profession_risque, _TAUX_ACC["bureau"])
    prime_deces   = round(capital_deces * taux["deces"])
    prime_inv_tot = round(capital_invalide_totale * taux["invalide"])
    prime_inv_par = round(capital_invalide_partielle * taux["invalide"] * 0.5) if capital_invalide_partielle else 0
    prime_itt     = round(indemnite_itt_jour * 365 * taux["itt"])

    prime_unitaire = prime_deces + prime_inv_tot + prime_inv_par + prime_itt
    prime_nette    = round(prime_unitaire * nb_personnes)

    # Dégressivité groupe
    if nb_personnes >= 50:
        prime_nette = round(prime_nette * 0.85)
    elif nb_personnes >= 10:
        prime_nette = round(prime_nette * 0.92)

    taxe       = round(prime_nette * 0.10)
    prime_ttc  = prime_nette + taxe

    return ResultatWorkflow(
        statut=StatutWorkflow.OK,
        donnees={
            "prime_deces_fcfa":        prime_deces,
            "prime_invalide_tot":      prime_inv_tot,
            "prime_invalide_par":      prime_inv_par,
            "prime_itt":               prime_itt,
            "nb_personnes":            nb_personnes,
            "prime_nette":             prime_nette,
            "taxe":                    taxe,
            "prime_ttc":               prime_ttc,
            "base_legale":             "Code CIMA Livre I — Accidents corporels",
        },
        message=f"Prime accident corporel : {prime_ttc:,} FCFA TTC".replace(",", " "),
    )


# ─── Tarification Vie & Prévoyance (Livre II CIMA) ───────────────────────────

# Tables de mortalité simplifiées CRRAE/CIMA (taux de décès annuels ‰)
# Base TD 88-90 adaptée zone CIMA (60 ans plafond pratique)
_TABLE_MORTALITE_CIMA = {
    20: 1.5, 25: 1.8, 30: 2.2, 35: 2.8, 40: 4.0,
    45: 6.5, 50: 10.0, 55: 16.0, 60: 25.0, 65: 40.0, 70: 65.0,
}

def _taux_mortalite(age: int) -> float:
    """Interpolation linéaire du taux de mortalité par âge."""
    bornes = sorted(_TABLE_MORTALITE_CIMA.keys())
    for i in range(len(bornes) - 1):
        if bornes[i] <= age <= bornes[i + 1]:
            t0, t1 = _TABLE_MORTALITE_CIMA[bornes[i]], _TABLE_MORTALITE_CIMA[bornes[i+1]]
            alpha = (age - bornes[i]) / (bornes[i+1] - bornes[i])
            return (t0 + alpha * (t1 - t0)) / 1000  # en fraction
    return _TABLE_MORTALITE_CIMA.get(min(bornes, key=lambda b: abs(b - age)), 10.0) / 1000


def calculer_prime_vie(
    age_souscription: int,
    duree_annees: int,
    capital_garanti: float,
    type_produit: str,           # "temporaire_deces" | "epargne_mixte" | "rente" | "emprunteur" | "prevoyance_deces"
    sexe: str = "M",             # "M" | "F" (majoration/minoration mortalité)
    taux_technique: float = 0.035,  # taux minimum garanti CIMA : 3,5%
) -> ResultatWorkflow:
    """
    Calcule la prime d'assurance vie selon méthode actuarielle CIMA.
    Formule : prime pure = capital × probabilité décès actualisée
    Art. 57-100 Livre II Code CIMA.
    """
    q_x = _taux_mortalite(age_souscription)
    if sexe == "F":
        q_x *= 0.85  # mortalité féminine inférieure de ~15%

    if type_produit == "temporaire_deces":
        # Prime annuelle = Capital × q(x) × facteur chargement
        prime_pure  = capital_garanti * q_x
        chargements = 0.30   # 30% chargements gestion
        prime_commerciale = round(prime_pure * (1 + chargements))
        prime_annuelle = prime_commerciale
        prime_mensuelle = round(prime_annuelle / 12 * 1.04)  # 4% surcoût mensualisation

    elif type_produit == "epargne_mixte":
        # Mixte = décès + épargne (capitalisation au taux technique)
        prime_risque    = capital_garanti * q_x
        # Part épargne : annuité de capitalisation
        facteur_cap     = ((1 + taux_technique) ** duree_annees - 1) / taux_technique
        prime_epargne   = capital_garanti / facteur_cap if facteur_cap else 0
        prime_pure      = prime_risque + prime_epargne
        prime_annuelle  = round(prime_pure * 1.35)
        prime_mensuelle = round(prime_annuelle / 12 * 1.04)

    elif type_produit == "emprunteur":
        # Assurance crédit : prime annuelle sur capital restant dû
        prime_annuelle  = round(capital_garanti * q_x * 1.40)
        prime_mensuelle = round(prime_annuelle / 12)

    elif type_produit in ("rente", "prevoyance_deces"):
        prime_annuelle  = round(capital_garanti * q_x * 1.25)
        prime_mensuelle = round(prime_annuelle / 12 * 1.04)

    else:
        prime_annuelle  = round(capital_garanti * q_x * 1.30)
        prime_mensuelle = round(prime_annuelle / 12 * 1.04)

    # PM projetée fin d'année 1 (méthode prospective simplifiée)
    pm_1an = round(capital_garanti * (1 - q_x))

    return ResultatWorkflow(
        statut=StatutWorkflow.OK,
        donnees={
            "type_produit":     type_produit,
            "age":              age_souscription,
            "duree_annees":     duree_annees,
            "capital_garanti":  capital_garanti,
            "taux_mortalite_q": round(q_x * 1000, 2),  # en ‰
            "taux_technique":   taux_technique,
            "prime_annuelle":   prime_annuelle,
            "prime_mensuelle":  prime_mensuelle,
            "pm_fin_an1":       pm_1an,
            "base_legale":      "Art. 57-100 Code CIMA Livre II",
        },
        message=f"Prime vie annuelle : {prime_annuelle:,} FCFA".replace(",", " "),
    )


def calculer_valeur_rachat_vie(
    pm_actuelle: float,
    duree_ecoulee_annees: int,
    duree_totale_annees: int,
    frais_rachat_pct: float = 0.05,   # Art. 65 CIMA : max 5% des PM
) -> ResultatWorkflow:
    """
    Calcule la valeur de rachat d'un contrat vie.
    Art. 65 Code CIMA — Valeur de rachat.
    """
    if duree_ecoulee_annees < 2:
        return ResultatWorkflow(
            statut=StatutWorkflow.ECHEC,
            message="Rachat non autorisé avant 2 ans de cotisation (Art. 65 CIMA)",
            donnees={"autorise": False},
        )

    # Proportionnel à la durée écoulée avec abattement dégressif
    pct_ecoul = min(1.0, duree_ecoulee_annees / duree_totale_annees)
    abattement = max(0.0, 0.15 - pct_ecoul * 0.10)   # abattement max 15% an2, 0% après 10 ans
    frais = min(frais_rachat_pct, 0.05) * pm_actuelle
    valeur_rachat = round(pm_actuelle * (1 - abattement) - frais)

    return ResultatWorkflow(
        statut=StatutWorkflow.OK,
        donnees={
            "pm_actuelle":        pm_actuelle,
            "valeur_rachat":      valeur_rachat,
            "abattement_pct":     round(abattement * 100, 1),
            "frais_rachat":       round(frais),
            "duree_ecoulee":      duree_ecoulee_annees,
            "autorise":           True,
            "base_legale":        "Art. 65 Code CIMA",
        },
        message=f"Valeur de rachat : {valeur_rachat:,} FCFA".replace(",", " "),
    )


def calculer_avance_police_vie(
    pm_actuelle: float,
    taux_interet_avance: float = 0.08,  # 8% courant dans la zone
    montant_demande: Optional[float] = None,
) -> ResultatWorkflow:
    """
    Calcule l'avance sur police (Art. 75 CIMA).
    Maximum : 80% des provisions mathématiques.
    """
    plafond = round(pm_actuelle * 0.80)
    montant = montant_demande or plafond
    if montant > plafond:
        return ResultatWorkflow(
            statut=StatutWorkflow.ECHEC,
            message=f"Montant demandé ({montant:,.0f}) dépasse le plafond autorisé ({plafond:,.0f}) — 80% des PM",
            donnees={"autorise": False, "plafond_fcfa": plafond},
        )

    interet_annuel = round(montant * taux_interet_avance)
    interet_mensuel = round(interet_annuel / 12)

    return ResultatWorkflow(
        statut=StatutWorkflow.OK,
        donnees={
            "pm_actuelle":        pm_actuelle,
            "plafond_avance":     plafond,
            "montant_avance":     montant,
            "taux_interet":       taux_interet_avance,
            "interet_annuel":     interet_annuel,
            "interet_mensuel":    interet_mensuel,
            "autorise":           True,
            "base_legale":        "Art. 75 Code CIMA",
        },
        message=f"Avance autorisée : {montant:,} FCFA (intérêts : {interet_mensuel:,} FCFA/mois)".replace(",", " "),
    )


def calculer_indemnite_sinistre_vie(
    type_sinistre: str,          # "deces" | "invalidite_totale" | "invalidite_partielle" | "maladie" | "accident"
    capital_contrat: float,
    ipp_pct: float = 0,          # pour invalidité partielle (0-100%)
    beneficiaire_type: str = "designe",  # "designe" | "heritier" | "conjoint"
    double_capital_accident: bool = False,  # clause doublement capital si accidentel
) -> ResultatWorkflow:
    """
    Calcule l'indemnité d'un sinistre vie selon le type.
    Art. 73-74 Code CIMA Livre II.
    """
    if type_sinistre == "deces":
        montant = capital_contrat * (2 if double_capital_accident else 1)
        return ResultatWorkflow(
            statut=StatutWorkflow.OK,
            donnees={
                "montant_prestation": round(montant),
                "beneficiaire_type":  beneficiaire_type,
                "double_capital":     double_capital_accident,
                "base_legale":        "Art. 74 Code CIMA — Capital décès",
            },
            message=f"Capital décès dû : {round(montant):,} FCFA".replace(",", " "),
        )

    if type_sinistre == "invalidite_totale":
        montant = capital_contrat  # 100% du capital
        return ResultatWorkflow(
            statut=StatutWorkflow.OK,
            donnees={
                "montant_prestation": montant,
                "taux_invalidite":    100,
                "base_legale":        "Art. 73 Code CIMA — Invalidité totale",
            },
            message=f"Prestation invalidité totale : {montant:,} FCFA".replace(",", " "),
        )

    if type_sinistre == "invalidite_partielle":
        montant = round(capital_contrat * ipp_pct / 100)
        return ResultatWorkflow(
            statut=StatutWorkflow.OK,
            donnees={
                "montant_prestation": montant,
                "taux_invalidite":    ipp_pct,
                "base_legale":        "Art. 73 Code CIMA — IPP",
            },
            message=f"Prestation IPP {ipp_pct}% : {montant:,} FCFA".replace(",", " "),
        )

    return ResultatWorkflow(
        statut=StatutWorkflow.IA_REQUISE,
        message=f"Sinistre vie type '{type_sinistre}' — analyse IA requise",
    )


# ─── Calcul avenant (modification de contrat) ────────────────────────────────

def calculer_regularisation_avenant(
    type_avenant: str,      # "extension_garantie" | "changement_vehicule" | "changement_usage" | "suspension"
    prime_annuelle_actuelle: float,
    date_avenant: date,
    date_echeance: date,
    prime_nouvelle: float = 0,
) -> ResultatWorkflow:
    """Calcule la prime au prorata pour un avenant en cours d'année."""
    jours_restants = (date_echeance - date_avenant).days
    if jours_restants <= 0:
        return ResultatWorkflow(statut=StatutWorkflow.ECHEC, message="Date avenant postérieure à l'échéance")

    if type_avenant == "suspension":
        # Remboursement au prorata, moins frais (Art. 9 CIMA)
        ristourne = round(prime_annuelle_actuelle * jours_restants / 365 * 0.90)  # 90% (frais non remboursables)
        return ResultatWorkflow(
            statut=StatutWorkflow.OK,
            donnees={"ristourne_fcfa": ristourne, "jours_restants": jours_restants, "base_legale": "Art. 9 CIMA"},
            message=f"Ristourne suspension : {ristourne:,} FCFA".replace(",", " "),
        )

    if prime_nouvelle > 0:
        diff_annuelle   = prime_nouvelle - prime_annuelle_actuelle
        complement      = round(diff_annuelle * jours_restants / 365)
        return ResultatWorkflow(
            statut=StatutWorkflow.OK,
            donnees={
                "complement_prime":    complement,
                "ristourne_prime":     abs(complement) if complement < 0 else 0,
                "jours_restants":      jours_restants,
                "type_avenant":        type_avenant,
            },
            message=f"{'Complément' if complement >= 0 else 'Ristourne'} avenant : {abs(complement):,} FCFA".replace(",", " "),
        )

    return ResultatWorkflow(statut=StatutWorkflow.OK, donnees={}, message="Avenant sans impact financier")


def coder_ecriture_comptable(
    type_operation: str,
    montant: float,
    reference: str,
    date_op: Optional[date] = None,
) -> ResultatWorkflow:
    """Génère l'écriture PCSA — 0 appel IA."""
    code = _PLAN_COMPTABLE_PCSA.get(type_operation)
    if not code:
        return ResultatWorkflow(
            statut=StatutWorkflow.IA_REQUISE,
            message=f"Opération '{type_operation}' non codifiée — analyse IA requise",
        )

    compte_debit, compte_credit, libelle = code
    return ResultatWorkflow(
        statut=StatutWorkflow.OK,
        donnees={
            "compte_debit":   compte_debit,
            "compte_credit":  compte_credit,
            "libelle":        libelle,
            "montant":        montant,
            "reference":      reference,
            "date_operation": str(date_op or date.today()),
            "plan":           "PCSA CIMA",
        },
        message=f"Écriture : D/{compte_debit} C/{compte_credit} — {montant:,.0f} FCFA".replace(",", " "),
    )
