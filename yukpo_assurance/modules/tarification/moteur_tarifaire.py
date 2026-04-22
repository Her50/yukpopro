"""
YukpoAssurance — Moteur de tarification prédictive
Moteur actuariel complet pour les branches CIMA : Auto, Vie, IRD, RC, Transport, Maladie.
Scoring de risque 0-100, optimisation par IA, comparaison multi-scénarios.

Données calibrées Cameroun / zone CIMA — aucune dépendance XGBoost externe.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

from core.ia_client import ModeIA, ia_client

logger = logging.getLogger("yukpo_assurance.tarification")


# ─── Tables de tarification calibrées (Cameroun / CIMA) ──────────────────────

# Auto : prime RC de base (FCFA) selon puissance fiscale (chevaux fiscaux)
BAREME_AUTO_RC: dict[str, int] = {
    "2cv":    45_000,
    "3cv":    55_000,
    "4cv":    68_000,
    "5cv":    82_000,
    "6cv":    98_000,
    "7cv":   118_000,
    "8cv":   142_000,
    "9cv":   170_000,
    "10cv":  200_000,
    "11cv":  235_000,
    "12cv":  272_000,
    "13cv+": 315_000,
}

# Coefficients usage Auto
COEFF_USAGE_AUTO: dict[str, float] = {
    "particulier":       1.00,
    "taxi":              2.20,
    "transport_commun":  2.50,
    "utilitaire":        1.60,
    "societe":           1.40,
}

# Coefficients zone géographique
COEFF_ZONE: dict[str, float] = {
    "yaounde":     1.10,
    "douala":      1.15,
    "bafoussam":   1.00,
    "garoua":      0.95,
    "maroua":      0.90,
    "bertoua":     0.90,
    "buea":        0.95,
    "ebolowa":     0.88,
    "ngaoundere":  0.92,
    "autres":      0.95,
}

# Coefficients ancienneté véhicule (réduction/majoration)
COEFF_AGE_VEHICULE: dict[tuple[int, int], float] = {
    (0, 2):    0.85,
    (3, 5):    0.95,
    (6, 8):    1.00,
    (9, 12):   1.15,
    (13, 18):  1.30,
    (19, 99):  1.55,
}

# Vie : taux de prime pure annuel pour 1 000 FCFA de capital (‰)
# selon tranches d'âge et durée, état de santé normal
BAREME_VIE_TAUX_POUR_MILLE: dict[str, dict[str, float]] = {
    # durée -> âge -> taux ‰
    "10ans": {
        "18-25": 4.2,
        "26-35": 5.8,
        "36-45": 9.5,
        "46-55": 16.0,
        "56-60": 26.0,
    },
    "15ans": {
        "18-25": 5.5,
        "26-35": 7.8,
        "36-45": 13.0,
        "46-55": 22.5,
        "56-60": 38.0,
    },
    "20ans": {
        "18-25": 6.8,
        "26-35": 9.5,
        "36-45": 16.5,
        "46-55": 29.0,
        "56-60": 50.0,
    },
}

COEFF_SANTE_VIE: dict[str, float] = {
    "excellent":  0.85,
    "bon":        1.00,
    "moyen":      1.30,
    "mauvais":    1.80,
}

# IRD : taux ‰ de la valeur assurée selon type de construction
BAREME_IRD_TAUX: dict[str, dict[str, float]] = {
    "incendie": {
        "dur_standing":  1.2,
        "dur_standard":  1.8,
        "semi_dur":      2.8,
        "bois_paille":   5.5,
        "industriel":    2.2,
    },
    "vol": {
        "dur_standing":  0.8,
        "dur_standard":  1.2,
        "semi_dur":      1.8,
        "bois_paille":   2.5,
        "industriel":    1.5,
    },
    "degats_eaux": {
        "dur_standing":  0.5,
        "dur_standard":  0.8,
        "semi_dur":      1.2,
        "bois_paille":   2.0,
        "industriel":    0.9,
    },
}

# RC Professionnelle : taux ‰ du chiffre d'affaires selon activité
BAREME_RC_TAUX: dict[str, float] = {
    "commerce_detail":     0.8,
    "commerce_gros":       0.6,
    "btp_construction":    2.5,
    "industrie":           1.5,
    "services_pro":        1.2,
    "transport_marchand":  3.0,
    "restauration":        1.0,
    "sante_clinique":      3.5,
    "enseignement":        0.9,
    "it_numerique":        0.7,
    "autres_services":     1.1,
}

# Transport marchandises : taux ‰ de la valeur des marchandises
BAREME_TRANSPORT_TAUX: dict[str, float] = {
    "terrestre_national":   3.5,
    "terrestre_regional":   4.5,
    "maritime_import":      7.0,
    "maritime_export":      5.5,
    "aerien":               3.0,
}

# Maladie : prime de base annuelle par personne selon tranche d'âge (FCFA)
BAREME_MALADIE_BASE: dict[str, int] = {
    "0-17":   60_000,
    "18-30": 110_000,
    "31-40": 145_000,
    "41-50": 198_000,
    "51-60": 280_000,
    "61+":   420_000,
}

COEFF_GARANTIES_MALADIE: dict[str, float] = {
    "hospitalisation_seule":   0.60,
    "pharmacie":               0.75,
    "consultation_hospit":     1.00,
    "complementaire_totale":   1.45,
    "dentaire_optique":        1.20,
}

# Taxe réglementaire CIMA (non-vie) et FGA
TAUX_TAXE_NON_VIE: float = 0.15   # 15% sur primes nettes
TAUX_TAXE_VIE:    float = 0.05    # 5% sur primes nettes (CIMA vie)
TAUX_FGA:         float = 0.005   # 0,5% Fonds de Garantie Auto


# ─── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class OffreTarifaire:
    libelle: str                    # "Basique" | "Standard" | "Premium"
    prime_nette: int
    taxes: int
    fga: int
    prime_ttc: int
    garanties: list[str]
    franchises: dict[str, str]
    marge_technique: float          # % marge cible
    description: str


@dataclass
class ResultatTarification:
    branche: str
    score_risque: int               # 0-100
    categorie_risque: str           # "faible" | "modéré" | "élevé" | "très élevé"
    prime_nette: int
    taxes: int
    fga: int
    prime_ttc: int
    garanties: list[str]
    franchises: dict[str, str]
    detail_calcul: dict[str, Any]
    justification_ia: str
    offres_comparatives: list[dict]
    recommandations_garanties: list[str]
    marge_technique_cible: float
    date_calcul: str = field(default_factory=lambda: datetime.now().isoformat())


# ─── Moteur tarifaire ─────────────────────────────────────────────────────────

class MoteurTarifaire:
    """
    Moteur de tarification actuarielle complet pour les branches CIMA.

    Usage :
        moteur = MoteurTarifaire()
        resultat = await moteur.calculer_prime(profil_risque)
    """

    # ──────────────────────────────────────────────────────────────
    # ENTRÉE PRINCIPALE
    # ──────────────────────────────────────────────────────────────

    async def calculer_prime(self, profil_risque: dict) -> dict:
        """
        Calcul complet : scoring risque + prime actuarielle + optimisation IA + 3 offres.

        profil_risque doit contenir au minimum :
            branche : "auto" | "vie" | "ird" | "rc" | "transport" | "maladie"
            ...champs spécifiques à la branche

        Retourne un dict sérialisable (ResultatTarification converti).
        """
        branche = profil_risque.get("branche", "auto").lower()
        logger.info(f"[Tarification] Calcul prime branche={branche}")

        # 1. Score de risque
        score = self._scorer_risque(profil_risque)

        # 2. Calcul actuariel selon la branche
        calcul = self._calculer_branche(branche, profil_risque, score)

        # 3. Application du coefficient de risque sur la prime nette
        prime_nette_ajustee = self._appliquer_coefficient_risque(
            calcul["prime_nette_base"], score
        )

        # 4. Taxes et frais réglementaires
        est_vie = branche == "vie"
        taux_taxe = TAUX_TAXE_VIE if est_vie else TAUX_TAXE_NON_VIE
        taxes = round(prime_nette_ajustee * taux_taxe)
        fga = round(prime_nette_ajustee * TAUX_FGA) if branche == "auto" else 0
        prime_ttc = prime_nette_ajustee + taxes + fga

        # 5. Garanties et franchises selon la branche
        garanties, franchises = self._garanties_par_branche(branche, profil_risque)

        # 6. Optimisation IA (analyse profil + ajustements)
        justification, recommandations = await self._optimiser_ia(
            branche, profil_risque, score, prime_nette_ajustee
        )

        # 7. Offres multi-scénarios (basique / standard / premium)
        offres = self._generer_offres_comparatives(
            branche, profil_risque, score, prime_nette_ajustee, taux_taxe
        )

        resultat = ResultatTarification(
            branche=branche,
            score_risque=score["score_global"],
            categorie_risque=score["categorie"],
            prime_nette=prime_nette_ajustee,
            taxes=taxes,
            fga=fga,
            prime_ttc=prime_ttc,
            garanties=garanties,
            franchises=franchises,
            detail_calcul={
                **calcul,
                "score_detail": score,
                "coefficient_risque_applique": round(
                    self._coefficient_par_score(score["score_global"]), 3
                ),
                "taux_taxe": f"{taux_taxe * 100:.0f}%",
            },
            justification_ia=justification,
            offres_comparatives=[
                {
                    "libelle": o.libelle,
                    "prime_nette": o.prime_nette,
                    "taxes": o.taxes,
                    "fga": o.fga,
                    "prime_ttc": o.prime_ttc,
                    "garanties": o.garanties,
                    "franchises": o.franchises,
                    "marge_technique": o.marge_technique,
                    "description": o.description,
                }
                for o in offres
            ],
            recommandations_garanties=recommandations,
            marge_technique_cible=0.20,
        )

        return self._to_dict(resultat)

    # ──────────────────────────────────────────────────────────────
    # SCORING DE RISQUE (0-100)
    # ──────────────────────────────────────────────────────────────

    def _scorer_risque(self, profil: dict) -> dict:
        """
        Score global 0-100 : plus le score est élevé, plus le risque est élevé.
        Agrégation pondérée de facteurs individuels, environnementaux, comportementaux.
        """
        scores: dict[str, int] = {}

        # ── Facteurs individuels (40 pts max) ──
        ind = 0

        # Âge (pour auto et vie)
        age = profil.get("age_assure", profil.get("age_conducteur", 35))
        if age < 25:
            ind += 15
        elif age < 30:
            ind += 8
        elif age < 55:
            ind += 2
        elif age < 65:
            ind += 6
        else:
            ind += 12

        # Antécédents sinistres (0-3+ sinistres sur 5 ans)
        sinistres_5ans = int(profil.get("sinistres_5_ans", 0))
        ind += min(sinistres_5ans * 6, 18)

        # Ancienneté client (fidélité réduit le risque)
        anciennete = int(profil.get("anciennete_client_ans", 0))
        ind -= min(anciennete, 5) * 1   # jusqu'à -5 pts pour 5+ ans

        # État de santé (pour vie/maladie)
        sante = profil.get("etat_sante", "bon")
        if sante == "mauvais":
            ind += 10
        elif sante == "moyen":
            ind += 5

        scores["individuel"] = max(0, min(40, ind))

        # ── Facteurs environnementaux (35 pts max) ──
        env = 0

        zone = profil.get("zone_geographique", "autres").lower()
        coeff_zone = COEFF_ZONE.get(zone, 0.95)
        env += round((coeff_zone - 0.85) / 0.30 * 20)  # 0-20 pts

        # Saison (saisonnalité des sinistres)
        mois = datetime.now().month
        if mois in (6, 7, 8, 9):   # saison des pluies → plus d'accidents
            env += 5
        elif mois in (12, 1):      # fêtes → plus de sinistres
            env += 3

        # Usage véhicule
        usage = profil.get("usage", "particulier").lower()
        coeff_usage = COEFF_USAGE_AUTO.get(usage, 1.0)
        env += round((coeff_usage - 1.0) * 10)

        scores["environnemental"] = max(0, min(35, env))

        # ── Facteurs comportementaux (25 pts max) ──
        comp = 0

        # Délai moyen de paiement
        delai_paiement = int(profil.get("delai_moyen_paiement_jours", 0))
        if delai_paiement > 60:
            comp += 12
        elif delai_paiement > 30:
            comp += 7
        elif delai_paiement > 15:
            comp += 3

        # Multi-produits (réduit le risque comportemental)
        nb_contrats = int(profil.get("nb_contrats_actifs", 1))
        comp -= min((nb_contrats - 1) * 3, 9)

        # Fidélité paiement (historique sans impayé)
        impaye = profil.get("historique_impaye", False)
        if impaye:
            comp += 8

        scores["comportemental"] = max(0, min(25, comp))

        score_global = scores["individuel"] + scores["environnemental"] + scores["comportemental"]
        score_global = max(0, min(100, score_global))

        if score_global < 25:
            categorie = "faible"
        elif score_global < 50:
            categorie = "modéré"
        elif score_global < 75:
            categorie = "élevé"
        else:
            categorie = "très élevé"

        return {
            "score_global": score_global,
            "categorie": categorie,
            "detail": scores,
            "facteurs_majeurs": self._facteurs_majeurs(profil, scores),
        }

    def _facteurs_majeurs(self, profil: dict, scores: dict) -> list[str]:
        facteurs = []
        if scores.get("individuel", 0) > 20:
            facteurs.append("Profil individuel à risque élevé (âge ou antécédents)")
        if scores.get("environnemental", 0) > 18:
            facteurs.append("Zone géographique ou usage à sinistralité élevée")
        if scores.get("comportemental", 0) > 12:
            facteurs.append("Comportement de paiement dégradé ou mono-produit")
        if int(profil.get("sinistres_5_ans", 0)) >= 3:
            facteurs.append(f"{profil.get('sinistres_5_ans')} sinistres déclarés sur 5 ans")
        if profil.get("age_conducteur", profil.get("age_assure", 35)) < 25:
            facteurs.append("Conducteur / assuré jeune (< 25 ans) : sur-sinistralité statistique")
        return facteurs

    def _coefficient_par_score(self, score: int) -> float:
        """Traduit le score de risque en coefficient multiplicateur de prime."""
        if score < 15:
            return 0.80
        elif score < 25:
            return 0.90
        elif score < 40:
            return 1.00
        elif score < 55:
            return 1.15
        elif score < 70:
            return 1.35
        elif score < 85:
            return 1.60
        else:
            return 2.00

    def _appliquer_coefficient_risque(self, prime_base: int, score: dict) -> int:
        coeff = self._coefficient_par_score(score["score_global"])
        return round(prime_base * coeff)

    # ──────────────────────────────────────────────────────────────
    # CALCUL ACTUARIEL PAR BRANCHE
    # ──────────────────────────────────────────────────────────────

    def _calculer_branche(self, branche: str, profil: dict, score: dict) -> dict:
        if branche == "auto":
            return self._calc_auto(profil)
        elif branche == "vie":
            return self._calc_vie(profil)
        elif branche == "ird":
            return self._calc_ird(profil)
        elif branche == "rc":
            return self._calc_rc(profil)
        elif branche == "transport":
            return self._calc_transport(profil)
        elif branche == "maladie":
            return self._calc_maladie(profil)
        else:
            logger.warning(f"[Tarification] Branche inconnue: {branche}, fallback auto")
            return self._calc_auto(profil)

    def _calc_auto(self, profil: dict) -> dict:
        cv_raw = int(profil.get("puissance_fiscale_cv", 6))
        cv_key = f"{cv_raw}cv" if cv_raw <= 12 else "13cv+"
        prime_rc_base = BAREME_AUTO_RC.get(cv_key, BAREME_AUTO_RC["6cv"])

        usage = profil.get("usage", "particulier").lower()
        coeff_u = COEFF_USAGE_AUTO.get(usage, 1.0)

        annee_vehicule = int(profil.get("annee_vehicule", datetime.now().year - 5))
        age_vehicule = datetime.now().year - annee_vehicule
        coeff_age = 1.0
        for (a, b), c in COEFF_AGE_VEHICULE.items():
            if a <= age_vehicule <= b:
                coeff_age = c
                break

        zone = profil.get("zone_geographique", "autres").lower()
        coeff_z = COEFF_ZONE.get(zone, 0.95)

        prime_rc = round(prime_rc_base * coeff_u * coeff_age * coeff_z)

        # Tous risques (optionnel) basé sur la valeur vénale
        valeur_venale = int(profil.get("valeur_venale_fcfa", 0))
        prime_tr = round(valeur_venale * 0.040) if valeur_venale > 0 else 0  # 4% valeur vénale

        prime_base = prime_rc + prime_tr

        return {
            "type_calcul": "auto_rc" + ("_tous_risques" if prime_tr else ""),
            "prime_nette_base": prime_base,
            "prime_rc_base": prime_rc,
            "prime_tr": prime_tr,
            "puissance_fiscale": f"{cv_raw} CV",
            "coeff_usage": coeff_u,
            "coeff_age_vehicule": coeff_age,
            "coeff_zone": coeff_z,
            "valeur_venale": valeur_venale,
        }

    def _calc_vie(self, profil: dict) -> dict:
        age = int(profil.get("age_assure", 35))
        capital = int(profil.get("capital_fcfa", 5_000_000))
        duree_ans = int(profil.get("duree_ans", 10))
        etat_sante = profil.get("etat_sante", "bon")

        # Tranche de durée
        if duree_ans <= 10:
            cle_duree = "10ans"
        elif duree_ans <= 15:
            cle_duree = "15ans"
        else:
            cle_duree = "20ans"

        # Tranche d'âge
        if age <= 25:
            cle_age = "18-25"
        elif age <= 35:
            cle_age = "26-35"
        elif age <= 45:
            cle_age = "36-45"
        elif age <= 55:
            cle_age = "46-55"
        else:
            cle_age = "56-60"

        taux = BAREME_VIE_TAUX_POUR_MILLE[cle_duree][cle_age]
        coeff_s = COEFF_SANTE_VIE.get(etat_sante, 1.0)

        prime_pure = round(capital / 1000 * taux * coeff_s)
        # Chargement technique 25% + chargement commercial 12%
        prime_base = round(prime_pure * 1.37)

        return {
            "type_calcul": "vie_temporaire_deces",
            "prime_nette_base": prime_base,
            "prime_pure": prime_pure,
            "taux_pour_mille": taux,
            "capital_assure": capital,
            "duree_ans": duree_ans,
            "tranche_age": cle_age,
            "coeff_sante": coeff_s,
        }

    def _calc_ird(self, profil: dict) -> dict:
        valeur_bien = int(profil.get("valeur_bien_fcfa", 10_000_000))
        type_construction = profil.get("type_construction", "dur_standard").lower().replace(" ", "_")
        garanties_souhaitees = profil.get("garanties_ird", ["incendie", "vol"])

        prime_base = 0
        detail_garanties: dict[str, int] = {}
        for garantie in garanties_souhaitees:
            taux = BAREME_IRD_TAUX.get(garantie, {}).get(type_construction, 2.0)
            prime_g = round(valeur_bien / 1000 * taux)
            detail_garanties[garantie] = prime_g
            prime_base += prime_g

        # Zone (influence sur l'IRD via coefficient de risque naturel)
        zone = profil.get("zone_geographique", "autres").lower()
        coeff_z = COEFF_ZONE.get(zone, 0.95)
        prime_base = round(prime_base * coeff_z)

        return {
            "type_calcul": "ird_multirisques",
            "prime_nette_base": prime_base,
            "valeur_bien": valeur_bien,
            "type_construction": type_construction,
            "detail_par_garantie": detail_garanties,
            "coeff_zone": coeff_z,
        }

    def _calc_rc(self, profil: dict) -> dict:
        activite = profil.get("activite_professionnelle", "autres_services").lower().replace(" ", "_")
        chiffre_affaires = int(profil.get("chiffre_affaires_fcfa", 50_000_000))
        nb_employes = int(profil.get("nb_employes", 5))

        taux = BAREME_RC_TAUX.get(activite, 1.1)
        prime_base = round(chiffre_affaires / 1000 * taux)

        # Majoration selon taille de l'entreprise
        if nb_employes > 100:
            prime_base = round(prime_base * 1.30)
        elif nb_employes > 20:
            prime_base = round(prime_base * 1.15)

        # Prime minimale RC pro
        prime_base = max(prime_base, 85_000)

        return {
            "type_calcul": "rc_professionnelle",
            "prime_nette_base": prime_base,
            "chiffre_affaires": chiffre_affaires,
            "activite": activite,
            "taux_pour_mille_ca": taux,
            "nb_employes": nb_employes,
        }

    def _calc_transport(self, profil: dict) -> dict:
        valeur_marchandises = int(profil.get("valeur_marchandises_fcfa", 5_000_000))
        type_transport = profil.get("type_transport", "terrestre_national").lower().replace(" ", "_")
        nb_voyages_an = int(profil.get("nb_voyages_annuels", 12))

        taux = BAREME_TRANSPORT_TAUX.get(type_transport, 3.5)
        prime_unitaire = round(valeur_marchandises / 1000 * taux)

        # Abonnement annuel avec dégressivité sur volume
        if nb_voyages_an >= 24:
            prime_base = round(prime_unitaire * nb_voyages_an * 0.65)
        elif nb_voyages_an >= 12:
            prime_base = round(prime_unitaire * nb_voyages_an * 0.80)
        else:
            prime_base = round(prime_unitaire * nb_voyages_an)

        return {
            "type_calcul": "transport_abonnement_annuel",
            "prime_nette_base": prime_base,
            "valeur_marchandises": valeur_marchandises,
            "type_transport": type_transport,
            "taux_pour_mille": taux,
            "nb_voyages_an": nb_voyages_an,
            "prime_par_voyage": prime_unitaire,
        }

    def _calc_maladie(self, profil: dict) -> dict:
        age = int(profil.get("age_assure", 35))
        nb_assures = int(profil.get("nb_personnes_couvertes", 1))
        formule = profil.get("formule_maladie", "consultation_hospit").lower().replace(" ", "_")

        # Tranche d'âge
        if age <= 17:
            cle_age = "0-17"
        elif age <= 30:
            cle_age = "18-30"
        elif age <= 40:
            cle_age = "31-40"
        elif age <= 50:
            cle_age = "41-50"
        elif age <= 60:
            cle_age = "51-60"
        else:
            cle_age = "61+"

        prime_unitaire = BAREME_MALADIE_BASE[cle_age]
        coeff_formule = COEFF_GARANTIES_MALADIE.get(formule, 1.0)
        prime_base = round(prime_unitaire * coeff_formule * nb_assures)

        # Dégressivité famille
        if nb_assures >= 4:
            prime_base = round(prime_base * 0.85)
        elif nb_assures >= 2:
            prime_base = round(prime_base * 0.92)

        return {
            "type_calcul": "maladie_individuelle_ou_groupe",
            "prime_nette_base": prime_base,
            "tranche_age": cle_age,
            "formule": formule,
            "nb_personnes": nb_assures,
            "prime_unitaire_base": prime_unitaire,
            "coeff_formule": coeff_formule,
        }

    # ──────────────────────────────────────────────────────────────
    # GARANTIES ET FRANCHISES PAR BRANCHE
    # ──────────────────────────────────────────────────────────────

    def _garanties_par_branche(
        self, branche: str, profil: dict
    ) -> tuple[list[str], dict[str, str]]:
        if branche == "auto":
            usage = profil.get("usage", "particulier")
            garanties = [
                "Responsabilité Civile (RC obligatoire)",
                "Défense et recours",
                "Individuelle accident conducteur",
            ]
            if profil.get("valeur_venale_fcfa", 0) > 0:
                garanties += ["Tous risques collision", "Vol et incendie", "Bris de glace"]
            franchises = {
                "collision": "50 000 FCFA ou 10% du dommage",
                "vol": "100 000 FCFA",
                "bris_glace": "25 000 FCFA",
            }
            if usage == "taxi":
                garanties.append("Transport de personnes à titre onéreux")
        elif branche == "vie":
            garanties = [
                "Capital décès toutes causes",
                "Double capital accidentel",
                "Exonération de primes en cas d'invalidité",
            ]
            franchises = {"invalidite": "Délai de carence 6 mois"}
        elif branche == "ird":
            garanties = [
                "Incendie et périls annexes (explosion, foudre)",
                "Dégâts des eaux",
                "Vol avec effraction",
                "Responsabilité civile locative",
            ]
            franchises = {
                "incendie": "25 000 FCFA",
                "vol": "50 000 FCFA ou 10% dommage",
                "degats_eaux": "15 000 FCFA",
            }
        elif branche == "rc":
            garanties = [
                "RC exploitation (dommages causés à des tiers)",
                "RC après livraison",
                "Défense pénale",
                "Dommages corporels tiers",
            ]
            franchises = {
                "dommages_corporels": "Néant",
                "dommages_materiels": "50 000 FCFA par sinistre",
            }
        elif branche == "transport":
            garanties = [
                "Dommages aux marchandises (tous risques ou FAP sauf)",
                "Vol et détournement",
                "Avaries communes",
                "Frais de sauvetage",
            ]
            franchises = {"dommages": "1% de la valeur assurée, min 25 000 FCFA"}
        else:  # maladie
            garanties = [
                "Frais d'hospitalisation (80% tarif secteur public)",
                "Consultations médicales et spécialistes",
                "Médicaments sur ordonnance (75%)",
                "Frais chirurgicaux et anesthésie",
            ]
            franchises = {
                "hospitalisation": "Ticket modérateur 20%",
                "pharmacie": "Ticket modérateur 25%",
            }

        return garanties, franchises

    # ──────────────────────────────────────────────────────────────
    # OPTIMISATION IA
    # ──────────────────────────────────────────────────────────────

    async def _optimiser_ia(
        self, branche: str, profil: dict, score: dict, prime: int
    ) -> tuple[str, list[str]]:
        """Appel IA pour justification et recommandations de garanties complémentaires."""
        prompt = f"""Tu es actuaire senior dans une compagnie d'assurance en zone CIMA (Cameroun).

Profil de risque soumis :
- Branche : {branche.upper()}
- Score de risque calculé : {score['score_global']}/100 ({score['categorie']})
- Prime nette actuarielle : {prime:,} FCFA
- Facteurs de risque identifiés : {', '.join(score.get('facteurs_majeurs', ['Aucun particulier'])) or 'Aucun particulier'}
- Données profil : {profil}

Ta mission :
1. En 3-4 phrases, justifie le niveau de prime en citant les facteurs techniques retenus et les normes CIMA applicables.
2. Propose exactement 3 recommandations de garanties complémentaires pertinentes pour ce profil, avec le bénéfice attendu et une estimation de surprime en FCFA.

Réponds sous ce format :
JUSTIFICATION: [texte]
RECOMMANDATIONS:
- [Garantie 1] : [bénéfice] (~XX 000 FCFA de surprime annuelle)
- [Garantie 2] : [bénéfice] (~XX 000 FCFA de surprime annuelle)
- [Garantie 3] : [bénéfice] (~XX 000 FCFA de surprime annuelle)
"""
        try:
            reponse = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
            texte = reponse.contenu

            # Extraction justification
            justification = ""
            recommandations = []
            for ligne in texte.splitlines():
                if ligne.startswith("JUSTIFICATION:"):
                    justification = ligne.replace("JUSTIFICATION:", "").strip()
                elif ligne.strip().startswith("- "):
                    recommandations.append(ligne.strip()[2:])

            if not justification:
                justification = texte[:400]
            if not recommandations:
                recommandations = [
                    "Extension garanties complémentaires adaptée au profil",
                    "Assistance 24h/24 et protection juridique",
                    "Garantie perte financière et capital complémentaire",
                ]
            return justification, recommandations

        except Exception as e:
            logger.warning(f"[Tarification] Optimisation IA échouée: {e}")
            justification_fallback = (
                f"Prime de {prime:,} FCFA calculée selon le barème CIMA pour la branche {branche}. "
                f"Score de risque {score['score_global']}/100 — catégorie {score['categorie']}. "
                f"Les facteurs individuels, environnementaux et comportementaux ont été intégrés "
                f"conformément aux normes actuarielles en vigueur en zone CIMA."
            )
            recommandations_fallback = [
                "Garantie assistance dépannage 24h/24 (surprime estimée : 15 000 FCFA/an)",
                "Protection juridique étendue (surprime estimée : 20 000 FCFA/an)",
                "Couverture complémentaire capital décès accidentel (surprime estimée : 25 000 FCFA/an)",
            ]
            return justification_fallback, recommandations_fallback

    # ──────────────────────────────────────────────────────────────
    # OFFRES MULTI-SCÉNARIOS
    # ──────────────────────────────────────────────────────────────

    def _generer_offres_comparatives(
        self,
        branche: str,
        profil: dict,
        score: dict,
        prime_standard: int,
        taux_taxe: float,
    ) -> list[OffreTarifaire]:
        """Génère 3 offres tarifaires : Basique, Standard, Premium."""

        def _construire_offre(libelle: str, coeff: float, desc: str) -> OffreTarifaire:
            prime_n = round(prime_standard * coeff)
            taxes = round(prime_n * taux_taxe)
            fga = round(prime_n * TAUX_FGA) if branche == "auto" else 0
            ttc = prime_n + taxes + fga
            garanties_offre, franchises_offre = self._garanties_par_offre(branche, libelle, profil)
            marge = 0.12 if libelle == "Basique" else (0.20 if libelle == "Standard" else 0.28)
            return OffreTarifaire(
                libelle=libelle,
                prime_nette=prime_n,
                taxes=taxes,
                fga=fga,
                prime_ttc=ttc,
                garanties=garanties_offre,
                franchises=franchises_offre,
                marge_technique=marge,
                description=desc,
            )

        offre_basique = _construire_offre(
            "Basique",
            0.80,
            "Couverture minimale réglementaire CIMA. Franchises élevées.",
        )
        offre_standard = _construire_offre(
            "Standard",
            1.00,
            "Couverture équilibrée recommandée. Rapport protection/prix optimal.",
        )
        offre_premium = _construire_offre(
            "Premium",
            1.35,
            "Couverture maximale, franchises réduites, assistance premium 24h/24.",
        )

        return [offre_basique, offre_standard, offre_premium]

    def _garanties_par_offre(
        self, branche: str, libelle: str, profil: dict
    ) -> tuple[list[str], dict[str, str]]:
        base_garanties, base_franchises = self._garanties_par_branche(branche, profil)

        if libelle == "Basique":
            return base_garanties[:2], {k: v for i, (k, v) in enumerate(base_franchises.items()) if i < 2}

        if libelle == "Premium":
            extra: dict[str, list[str]] = {
                "auto": ["Assistance dépannage 24h/24", "Véhicule de remplacement 30j", "Protection juridique routière"],
                "vie": ["Rente invalidité totale permanente", "Majoration capital maladies graves"],
                "ird": ["Catastrophes naturelles et émeutes", "Perte d'exploitation"],
                "rc": ["RC croisée dirigeants", "Cyber-risques et données"],
                "transport": ["Délais de livraison (perte financière)", "Assurance valeur à neuf"],
                "maladie": ["Soins dentaires et optique 100%", "Médecine douce remboursée", "Évacuation sanitaire internationale"],
            }
            garanties_premium = base_garanties + extra.get(branche, [])
            franchises_premium = {k: "Néant" for k in base_franchises}
            return garanties_premium, franchises_premium

        return base_garanties, base_franchises

    # ──────────────────────────────────────────────────────────────
    # BARÈME PUBLIC PAR BRANCHE
    # ──────────────────────────────────────────────────────────────

    def get_bareme(self, branche: str) -> dict:
        """Retourne les tables de tarification publiques d'une branche."""
        bareme: dict[str, Any] = {"branche": branche}
        if branche == "auto":
            bareme["rc_base_fcfa"] = BAREME_AUTO_RC
            bareme["coefficients_usage"] = COEFF_USAGE_AUTO
            bareme["coefficients_zone"] = COEFF_ZONE
            bareme["coefficients_age_vehicule"] = {
                f"{a}-{b} ans": c for (a, b), c in COEFF_AGE_VEHICULE.items()
            }
            bareme["taxe_cima"] = f"{TAUX_TAXE_NON_VIE * 100:.0f}%"
            bareme["fga"] = f"{TAUX_FGA * 100:.1f}%"
        elif branche == "vie":
            bareme["taux_pour_mille_capital"] = BAREME_VIE_TAUX_POUR_MILLE
            bareme["coefficients_sante"] = COEFF_SANTE_VIE
            bareme["chargement_technique"] = "25%"
            bareme["chargement_commercial"] = "12%"
            bareme["taxe_cima"] = f"{TAUX_TAXE_VIE * 100:.0f}%"
        elif branche == "ird":
            bareme["taux_pour_mille_valeur_bien"] = BAREME_IRD_TAUX
            bareme["coefficients_zone"] = COEFF_ZONE
            bareme["taxe_cima"] = f"{TAUX_TAXE_NON_VIE * 100:.0f}%"
        elif branche == "rc":
            bareme["taux_pour_mille_ca"] = BAREME_RC_TAUX
            bareme["prime_minimum"] = "85 000 FCFA"
            bareme["taxe_cima"] = f"{TAUX_TAXE_NON_VIE * 100:.0f}%"
        elif branche == "transport":
            bareme["taux_pour_mille_valeur_marchandises"] = BAREME_TRANSPORT_TAUX
            bareme["degressivite_volume"] = {
                "moins_12_voyages": "tarif plein",
                "12_a_23_voyages": "-20%",
                "24_voyages_et_plus": "-35%",
            }
            bareme["taxe_cima"] = f"{TAUX_TAXE_NON_VIE * 100:.0f}%"
        elif branche == "maladie":
            bareme["prime_annuelle_base_par_age"] = BAREME_MALADIE_BASE
            bareme["coefficients_formule"] = COEFF_GARANTIES_MALADIE
            bareme["degressivite_famille"] = {"2-3_personnes": "-8%", "4_personnes_et_plus": "-15%"}
            bareme["taxe_cima"] = f"{TAUX_TAXE_NON_VIE * 100:.0f}%"
        else:
            bareme["erreur"] = f"Branche {branche} non reconnue"
            bareme["branches_disponibles"] = ["auto", "vie", "ird", "rc", "transport", "maladie"]
        return bareme

    # ──────────────────────────────────────────────────────────────
    # VALIDATION ACTUARIELLE
    # ──────────────────────────────────────────────────────────────

    def valider_prime(self, branche: str, prime_proposee: int, profil: dict) -> dict:
        """
        Vérifie si une prime proposée est actuariellement saine (>= prime technique minimale).
        Retourne : valide, prime_minimale, ecart_pct, recommandation.
        """
        score = self._scorer_risque(profil)
        calcul = self._calculer_branche(branche, profil, score)
        prime_min = self._appliquer_coefficient_risque(calcul["prime_nette_base"], score)
        # Marge technique minimale 10%
        prime_min_avec_marge = round(prime_min * 1.10)

        ecart = ((prime_proposee - prime_min_avec_marge) / prime_min_avec_marge * 100) if prime_min_avec_marge else 0
        valide = prime_proposee >= prime_min_avec_marge

        taxes = round(prime_proposee * (TAUX_TAXE_VIE if branche == "vie" else TAUX_TAXE_NON_VIE))
        fga = round(prime_proposee * TAUX_FGA) if branche == "auto" else 0

        return {
            "valide": valide,
            "prime_proposee": prime_proposee,
            "prime_technique_minimale": prime_min,
            "prime_minimale_avec_marge": prime_min_avec_marge,
            "prime_ttc_estimee": prime_proposee + taxes + fga,
            "ecart_pct": round(ecart, 1),
            "score_risque": score["score_global"],
            "recommandation": (
                "Prime conforme aux normes actuarielles CIMA."
                if valide
                else (
                    f"Prime insuffisante : écart de {abs(ecart):.1f}% sous le seuil technique. "
                    f"Prime minimale recommandée : {prime_min_avec_marge:,} FCFA."
                )
            ),
        }

    # ──────────────────────────────────────────────────────────────
    # UTILITAIRES
    # ──────────────────────────────────────────────────────────────

    def _to_dict(self, r: ResultatTarification) -> dict:
        return {
            "branche": r.branche,
            "score_risque": r.score_risque,
            "categorie_risque": r.categorie_risque,
            "prime_nette": r.prime_nette,
            "taxes": r.taxes,
            "fga": r.fga,
            "prime_ttc": r.prime_ttc,
            "garanties": r.garanties,
            "franchises": r.franchises,
            "detail_calcul": r.detail_calcul,
            "justification_ia": r.justification_ia,
            "offres_comparatives": r.offres_comparatives,
            "recommandations_garanties": r.recommandations_garanties,
            "marge_technique_cible": r.marge_technique_cible,
            "date_calcul": r.date_calcul,
        }


# Instance singleton
moteur_tarifaire = MoteurTarifaire()
