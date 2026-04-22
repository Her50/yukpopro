"""
YukpoAssurance — Module Ressources Humaines
Gestion complète du personnel : employés, congés, paie, évaluations, recrutement, formations.
"""
import logging
from datetime import date, datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger("yukpo_assurance.rh")


# ─── Calculs salaire & paie ───────────────────────────────────────────────────

TRANCHES_IR_CIMA = [
    (0,        500_000,   0.0),
    (500_001,  1_500_000, 0.10),
    (1_500_001, 3_000_000, 0.20),
    (3_000_001, float("inf"), 0.30),
]

TAUX_CNPS = 0.042      # Part salariale CNPS (4,2 %)
TAUX_CNPS_PATRON = 0.168  # Part patronale CNPS (16,8 %)


def calculer_bulletin_paie(
    salaire_brut: float,
    primes: float = 0,
    avances: float = 0,
    absences_jours: int = 0,
    jours_ouvres: int = 22,
) -> dict:
    """Calcul complet du bulletin de paie selon le droit OHADA / zone CIMA."""
    salaire_base_brut = salaire_brut
    if absences_jours > 0:
        retenue_absence = (salaire_brut / jours_ouvres) * absences_jours
        salaire_base_brut = max(0, salaire_brut - retenue_absence)
    else:
        retenue_absence = 0.0

    revenu_imposable = salaire_base_brut + primes

    # CNPS salarié
    cnps_salarie = round(revenu_imposable * TAUX_CNPS)

    # Impôt sur le revenu (barème progressif)
    base_ir = max(0, revenu_imposable - cnps_salarie)
    ir = 0.0
    for plancher, plafond, taux in TRANCHES_IR_CIMA:
        if base_ir <= plancher:
            break
        montant_tranche = min(base_ir, plafond) - plancher
        ir += montant_tranche * taux

    net_a_payer = revenu_imposable - cnps_salarie - round(ir) - avances
    charge_patronale = round(revenu_imposable * TAUX_CNPS_PATRON)

    return {
        "salaire_brut": salaire_brut,
        "primes": primes,
        "retenue_absence_jours": absences_jours,
        "retenue_absence_fcfa": round(retenue_absence),
        "revenu_imposable": round(revenu_imposable),
        "cnps_salarie": cnps_salarie,
        "impot_revenu": round(ir),
        "avances_deduites": avances,
        "net_a_payer": round(net_a_payer),
        "charge_patronale_cnps": charge_patronale,
        "cout_total_employeur": round(revenu_imposable + charge_patronale),
    }


# ─── Congés ──────────────────────────────────────────────────────────────────

CONGES_ANNUELS_PAR_AN = 24  # jours ouvrables — norme OHADA

def calculer_solde_conges(
    date_embauche: date,
    conges_pris: int = 0,
    date_calcul: Optional[date] = None,
) -> dict:
    """Calcule le solde de congés acquis selon l'ancienneté."""
    ref = date_calcul or date.today()
    anciennete_mois = (ref.year - date_embauche.year) * 12 + (ref.month - date_embauche.month)
    acquis = round((anciennete_mois / 12) * CONGES_ANNUELS_PAR_AN)
    solde = max(0, acquis - conges_pris)
    return {
        "anciennete_mois": anciennete_mois,
        "conges_acquis": acquis,
        "conges_pris": conges_pris,
        "solde_disponible": solde,
    }


# ─── Évaluation de performance ────────────────────────────────────────────────

CRITERES_EVALUATION = [
    "qualite_travail",
    "respect_delais",
    "esprit_equipe",
    "initiative_innovation",
    "respect_procedures",
    "satisfaction_clients_internes",
]

def calculer_score_evaluation(notes: dict[str, float]) -> dict:
    """
    notes : dict {critere: note_sur_5}
    Retourne le score global et la mention.
    """
    valides = {k: v for k, v in notes.items() if k in CRITERES_EVALUATION}
    if not valides:
        return {"score": 0, "mention": "Non évalué", "notes_detaillees": {}}
    moyenne = sum(valides.values()) / len(valides)
    if moyenne >= 4.5:
        mention = "Excellent"
    elif moyenne >= 3.5:
        mention = "Très bien"
    elif moyenne >= 2.5:
        mention = "Bien"
    elif moyenne >= 1.5:
        mention = "Insuffisant"
    else:
        mention = "Très insuffisant"
    return {
        "score": round(moyenne, 2),
        "mention": mention,
        "notes_detaillees": valides,
        "nb_criteres_evalues": len(valides),
    }


# ─── Organigramme & structure ─────────────────────────────────────────────────

DEPARTEMENTS_ASSURANCE = [
    "Direction Générale",
    "Direction Technique",
    "Sinistres",
    "Souscription",
    "Comptabilité / Finance",
    "Ressources Humaines",
    "Commercial / Marketing",
    "Informatique",
    "Juridique & Conformité",
    "Réassurance",
    "Actuariat",
    "Audit Interne",
]

POSTES_PAR_DEPARTEMENT = {
    "Direction Générale": ["Directeur Général", "Secrétaire de Direction", "Chargé de Stratégie"],
    "Sinistres": ["Chef de Service Sinistres", "Gestionnaire Sinistres", "Expert Automobile", "Rédacteur Sinistres"],
    "Souscription": ["Chef de Service Souscription", "Chargé de Souscription", "Rédacteur Polices"],
    "Comptabilité / Finance": ["DAF", "Chef Comptable", "Comptable", "Caissier"],
    "Ressources Humaines": ["DRH", "Responsable RH", "Chargé de Formation", "Gestionnaire Paie"],
    "Commercial / Marketing": ["Directeur Commercial", "Inspecteur Commercial", "Agent Commercial"],
    "Informatique": ["DSI", "Développeur", "Administrateur Système"],
    "Juridique & Conformité": ["Juriste", "Responsable Conformité CIMA"],
    "Actuariat": ["Actuaire", "Actuaire Stagiaire"],
}

logger.info("[RH] Module Ressources Humaines initialisé")
