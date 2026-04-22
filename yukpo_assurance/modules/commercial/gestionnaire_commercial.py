"""
YukpoAssurance — Module Commercial
Pipeline de ventes, prospects, objectifs, campagnes, relances automatiques.
"""
import logging
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger("yukpo_assurance.commercial")

# ─── Calculs pipeline ─────────────────────────────────────────────────────────

STATUTS_PIPELINE = ["nouveau", "contacte", "devis_envoye", "negociation", "souscrit", "perdu"]

TAUX_CONVERSION_MOYEN = {
    "nouveau → contacte": 0.70,
    "contacte → devis_envoye": 0.55,
    "devis_envoye → negociation": 0.40,
    "negociation → souscrit": 0.65,
}

def calculer_taux_conversion(nb_entree: int, nb_sortie: int) -> float:
    if nb_entree == 0:
        return 0.0
    return round(nb_sortie / nb_entree * 100, 1)

def score_prospect(donnees: dict) -> dict:
    """Score de qualification d'un prospect (0-100)."""
    score = 0
    raisons = []

    # Source de lead
    sources_chaudes = ["recommandation", "courtier", "parrainage"]
    if donnees.get("source") in sources_chaudes:
        score += 25
        raisons.append(f"Source chaude : {donnees.get('source')}")
    else:
        score += 10

    # Branche souhaitée
    branches_volume = ["auto", "mrh", "vie"]
    if donnees.get("branche_interesse") in branches_volume:
        score += 20
        raisons.append("Branche à fort volume")

    # Historique d'assurance
    if donnees.get("deja_assure"):
        score += 15
        raisons.append("Déjà assuré ailleurs — prospect chaud")

    # Budget déclaré
    budget = donnees.get("budget_fcfa", 0)
    if budget >= 200_000:
        score += 25
        raisons.append("Budget > 200k FCFA")
    elif budget >= 100_000:
        score += 15
    elif budget > 0:
        score += 5

    # Délai de décision
    delai = donnees.get("delai_decision_jours", 30)
    if delai <= 7:
        score += 15
        raisons.append("Décision urgente ≤7 jours")
    elif delai <= 30:
        score += 5

    niveau = "froid" if score < 30 else "tiède" if score < 60 else "chaud"
    return {"score": min(score, 100), "niveau": niveau, "raisons": raisons}


# ─── Objectifs commerciaux ───────────────────────────────────────────────────

def calculer_avancement_objectif(valeur_cible: float, valeur_atteinte: float) -> dict:
    if valeur_cible == 0:
        return {"taux_avancement": 0, "statut": "non_defini", "ecart": 0}
    taux = round(valeur_atteinte / valeur_cible * 100, 1)
    if taux >= 100:
        statut = "atteint"
    elif taux >= 75:
        statut = "en_bonne_voie"
    elif taux >= 50:
        statut = "attention"
    else:
        statut = "en_retard"
    return {
        "taux_avancement": taux,
        "statut": statut,
        "ecart": round(valeur_cible - valeur_atteinte),
    }


# ─── Relances automatiques ───────────────────────────────────────────────────

def prospects_a_relancer(prospects: list[dict], jours_sans_contact: int = 7) -> list[dict]:
    """Retourne la liste des prospects non contactés depuis N jours."""
    seuil = datetime.utcnow() - timedelta(days=jours_sans_contact)
    a_relancer = []
    for p in prospects:
        dernier_contact = p.get("dernier_contact")
        if not dernier_contact:
            a_relancer.append({**p, "raison": "Jamais contacté"})
            continue
        if isinstance(dernier_contact, str):
            dernier_contact = datetime.fromisoformat(dernier_contact)
        if dernier_contact < seuil:
            jours = (datetime.utcnow() - dernier_contact).days
            a_relancer.append({**p, "raison": f"{jours} jours sans contact"})
    return sorted(a_relancer, key=lambda x: x.get("score", 0), reverse=True)


# ─── Tableau de bord commercial ──────────────────────────────────────────────

def generer_tableau_bord_commercial(
    prospects: list[dict],
    objectifs: list[dict],
    contrats_mois: int,
    primes_mois: float,
) -> dict:
    total = len(prospects)
    par_statut = {s: sum(1 for p in prospects if p.get("statut") == s) for s in STATUTS_PIPELINE}
    taux_global = calculer_taux_conversion(
        par_statut.get("nouveau", 0) + par_statut.get("contacte", 0),
        par_statut.get("souscrit", 0),
    )
    return {
        "total_prospects": total,
        "par_statut": par_statut,
        "taux_conversion_global": taux_global,
        "contrats_ce_mois": contrats_mois,
        "primes_ce_mois_fcfa": primes_mois,
        "objectifs_resume": [
            {**o, **calculer_avancement_objectif(o.get("valeur_cible", 0), o.get("valeur_atteinte", 0))}
            for o in objectifs
        ],
    }


SOURCES_LEAD = ["appel_entrant", "courtier", "recommandation", "parrainage", "prospection_terrain",
                 "reseaux_sociaux", "site_web", "email_campagne", "salon_pro"]
BRANCHES_PRODUIT = ["auto", "moto", "mrh", "incendie", "vie", "rc", "transport", "accident_corporel"]

logger.info("[Commercial] Module Commercial initialisé")
