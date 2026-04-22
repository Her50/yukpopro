"""
YukpoAssurance — Module Transport Assurance (CIMA complet)
Branche 50 — Code CIMA Art. 212-229

Couvertures :
- Marchandises transportées (terrestre, maritime, aérien)
- CMR (Convention Marchandise Route — Art. CMR 1956)
- Responsabilité Civile Transporteur
- Corps de véhicule / flotte
- Avaries particulières, avaries communes, abandon
- Facultés All Risks (FAP)
- Multimodal, conteneurs

Conformité CIMA : Art. 212 à 229, OHADA, CNUDCI
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from core.ia_client import ModeIA, ia_client
from core.orchestrateur import ContexteRequete, DomaineMétier, orchestrateur
from core.orass_connector import orass

logger = logging.getLogger("yukpo_assurance.transport")

# ─── Barèmes Transport (CIMA zone CIMA 2024) ──────────────────────────────────

# Taux primes en ‰ de la valeur assurée (marchandises)
TAUX_MARCHANDISES: dict[str, float] = {
    # Terrestre
    "terrestre_national":       3.00,   # Cameroun, CI, Sénégal...
    "terrestre_regional":       4.50,   # CEMAC / UEMOA
    "terrestre_international":  6.00,   # Hors zone CIMA
    # Maritime
    "maritime_cabotage":        4.00,   # Côte nationale
    "maritime_regional":        6.50,   # Golfe de Guinée
    "maritime_international":   8.00,   # Long cours
    # Aérien
    "aerien_national":          2.50,
    "aerien_international":     3.50,
    # Conteneurs
    "conteneur_20pieds":        5.00,
    "conteneur_40pieds":        4.50,
    # Multimodal
    "multimodal":               7.00,
    # Denrées périssables
    "denrees_perissables":      8.00,
    # Matières dangereuses (ADR/IMDG)
    "matieres_dangereuses":    12.00,
    # Animaux vivants
    "animaux_vivants":          9.00,
}

# Taux RC Transporteur en ‰ du chiffre d'affaires transport
TAUX_RC_TRANSPORTEUR: dict[str, float] = {
    "vehicule_leger":           2.00,   # < 3,5 t
    "porteur":                  3.50,   # 3,5 – 12 t
    "semi_remorque":            5.00,   # > 12 t
    "tracteur_remorque":        6.00,
    "autocar_autobus":          4.50,
    "vehicule_frigorifique":    4.00,
    "citerne_carburant":       10.00,
    "citerne_produits_chimiques": 15.00,
    "fourgon_valeurs":         20.00,
}

# Taux corps de véhicule (% valeur à neuf ou vénale)
TAUX_CORPS_VEHICULE: dict[str, float] = {
    "camion_rigide":            4.00,   # % valeur assurée
    "semi_remorque":            3.50,
    "remorque":                 2.50,
    "autocar":                  4.50,
    "vehicule_leger_utilitaire": 5.00,
}

# Plafonds CMR par défaut (Art. 23 §3 Convention CMR)
CMR_PLAFOND_PAR_KG_SDR = 8.33         # 8,33 DTS/kg — Convention CMR 1956
SDR_TO_FCFA = 815.0                    # Taux approximatif 2024

# Franchises standard (FCFA)
FRANCHISES_TRANSPORT: dict[str, int] = {
    "avaries_ordinaires":       100_000,
    "vol_total":                200_000,
    "vol_partiel":              250_000,
    "avaries_particulieres":    150_000,
    "desistement":              100_000,
    "freinte_route":            0,      # Non assurable
    "matieres_dangereuses":     500_000,
}

# Coefficients risques spéciaux
COEFFICIENTS_RISQUES: dict[str, float] = {
    "zone_conflit":             2.50,
    "saison_pluies":            1.30,
    "route_degradee":           1.40,
    "valeur_elevee_gt5M":       1.20,
    "sinistralite_elevee":      1.60,   # > 50% S/P l'an dernier
    "client_fidele_3ans":       0.85,   # Bonus fidélité
    "flotte_gt10":              0.80,   # Économie de portefeuille
}


# ─── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class DossierTransport:
    """Dossier de souscription transport marchandises."""
    # Type de couverture
    type_couverture: str = "marchandises"   # "marchandises" | "rc_transporteur" | "corps" | "cmr" | "flotte"
    type_transport: str = "terrestre_national"

    # Expéditeur/assuré
    nom_assure: str = ""
    telephone: str = ""
    email: str = ""
    numero_registre_commerce: str = ""

    # Marchandises
    description_marchandises: str = ""
    valeur_marchandises_fcfa: float = 0
    poids_total_kg: float = 0
    nb_colis: int = 0
    conditionnement: str = ""           # "palette", "vrac", "conteneur", "citerne"...

    # Trajet
    lieu_chargement: str = ""
    lieu_livraison: str = ""
    distance_km: float = 0
    pays_transit: list[str] = field(default_factory=list)
    date_chargement: Optional[str] = None
    date_livraison_prevue: Optional[str] = None

    # RC Transporteur
    chiffre_affaires_transport_fcfa: float = 0
    type_vehicule: str = "porteur"
    nb_vehicules: int = 1
    capacite_charge_totale_tonnes: float = 0

    # Corps véhicule
    valeur_vehicule_neuf_fcfa: float = 0
    valeur_venale_vehicule_fcfa: float = 0
    annee_vehicule: int = 2020

    # Options
    garanties_supplementaires: list[str] = field(default_factory=list)
    # ["avaries_particulieres", "vol", "cmr_complementaire", "greve_emeutes", "risques_politiques"]
    risques_speciaux: list[str] = field(default_factory=list)

    # Abonnement ou voyage unique
    mode_tarification: str = "voyage_unique"    # "voyage_unique" | "abonnement_annuel"
    nb_voyages_annuels: int = 1
    valeur_annuelle_fcfa: float = 0             # Pour abonnement

    # Contrat
    agent_code: Optional[str] = None
    courtier_code: Optional[str] = None
    date_effet: Optional[str] = None


@dataclass
class DevisTransport:
    """Résultat du calcul de prime transport."""
    prime_nette: float
    taxes_cima: float               # 5% taxe CIMA
    taxes_locales: float            # TVA + taxes nationales
    prime_ttc: float

    garanties_incluses: list[str]
    franchises: dict[str, int]
    exclusions: list[str]

    type_couverture: str
    plafond_indemnisation_fcfa: float
    plafond_cmr_fcfa: Optional[float]

    detail_calcul: dict
    recommandations_ia: Optional[str] = None
    score_risque: str = "standard"  # "faible" | "standard" | "eleve" | "inassurable"


@dataclass
class PoliceTransport:
    """Police d'assurance transport émise."""
    numero_police: str
    type_couverture: str
    statut: str                     # "actif" | "suspendu" | "sinistré" | "résilié"
    dossier: DossierTransport
    devis: DevisTransport
    cree_le: str
    date_effet: str
    date_echeance: str


# ─── Moteur de tarification Transport ────────────────────────────────────────

class MoteurTarifTransport:
    """
    Calcul actuariel transport conforme CIMA.
    Méthodologie : valeur assurée × taux × coefficients risques.
    """

    # Taux de taxation par pays CIMA
    TAXE_LOCALE_PAR_PAYS: dict[str, float] = {
        "CM": 0.1925,   # Cameroun
        "CI": 0.1800,   # Côte d'Ivoire
        "SN": 0.1800,   # Sénégal
        "BF": 0.1800,   # Burkina Faso
        "ML": 0.1800,   # Mali
        "NE": 0.1800,   # Niger
        "TG": 0.1800,   # Togo
        "BJ": 0.1800,   # Bénin
        "GN": 0.1800,   # Guinée Conakry
        "GA": 0.1800,   # Gabon
        "CG": 0.1800,   # Congo
        "CF": 0.1800,   # RCA
        "TD": 0.1800,   # Tchad
        "GQ": 0.1800,   # Guinée Équatoriale
        "CD": 0.1600,   # RDC (CIMA)
    }
    TAXE_CIMA = 0.05    # 5% taxe paramétrique CIMA

    def calculer_prime_marchandises(self, dossier: DossierTransport, pays: str = "CM") -> DevisTransport:
        """
        Calcul prime marchandises transportées.
        Base : valeur_assurée × taux_pour_mille × coefficients
        """
        # Valeur assurée = valeur marchandises + 10% frais (practice CIMA)
        valeur_assuree = dossier.valeur_marchandises_fcfa * 1.10

        # Taux de base
        taux_base = TAUX_MARCHANDISES.get(dossier.type_transport, 5.0)

        # Coefficients de risque
        coeff_global = 1.0
        risques_appliques = []
        for risque in dossier.risques_speciaux:
            c = COEFFICIENTS_RISQUES.get(risque, 1.0)
            coeff_global *= c
            risques_appliques.append(f"{risque}: ×{c}")

        # Dégressivité pour abonnement annuel
        if dossier.mode_tarification == "abonnement_annuel":
            if dossier.nb_voyages_annuels >= 24:
                coeff_global *= 0.65
            elif dossier.nb_voyages_annuels >= 12:
                coeff_global *= 0.80
            elif dossier.nb_voyages_annuels >= 6:
                coeff_global *= 0.90

        # Taux effectif en ‰
        taux_effectif = taux_base * coeff_global

        # Prime de base
        if dossier.mode_tarification == "abonnement_annuel":
            prime_base = round(
                (dossier.valeur_annuelle_fcfa or valeur_assuree * dossier.nb_voyages_annuels)
                / 1000 * taux_effectif
            )
        else:
            prime_base = round(valeur_assuree / 1000 * taux_effectif)

        # Plafond CMR (si terrestre international)
        plafond_cmr = None
        if "terrestre" in dossier.type_transport and dossier.poids_total_kg > 0:
            plafond_cmr = round(dossier.poids_total_kg * CMR_PLAFOND_PAR_KG_SDR * SDR_TO_FCFA)

        # Garanties et franchises
        garanties, franchises, exclusions = self._garanties_transport(dossier)

        # Majoration garanties optionnelles
        for g in dossier.garanties_supplementaires:
            if g == "avaries_particulieres":
                prime_base = round(prime_base * 1.20)
            elif g == "vol":
                prime_base = round(prime_base * 1.15)
            elif g == "greve_emeutes":
                prime_base = round(prime_base * 1.10)
            elif g == "risques_politiques":
                prime_base = round(prime_base * 1.30)
            elif g == "cmr_complementaire":
                prime_base = round(prime_base * 1.08)
            if g not in garanties:
                garanties.append(g.replace("_", " ").title())

        # Taxes
        taxe_cima = round(prime_base * self.TAXE_CIMA)
        taux_local = self.TAXE_LOCALE_PAR_PAYS.get(pays, 0.18)
        taxe_locale = round(prime_base * taux_local)
        prime_ttc = prime_base + taxe_cima + taxe_locale

        # Score risque
        score = "faible" if taux_effectif < 4 else ("eleve" if taux_effectif > 8 else "standard")

        return DevisTransport(
            prime_nette=prime_base,
            taxes_cima=taxe_cima,
            taxes_locales=taxe_locale,
            prime_ttc=prime_ttc,
            garanties_incluses=garanties,
            franchises=franchises,
            exclusions=exclusions,
            type_couverture="marchandises",
            plafond_indemnisation_fcfa=valeur_assuree,
            plafond_cmr_fcfa=plafond_cmr,
            detail_calcul={
                "valeur_assuree_fcfa": round(valeur_assuree),
                "taux_base_pour_mille": taux_base,
                "coeff_global": round(coeff_global, 3),
                "taux_effectif_pour_mille": round(taux_effectif, 3),
                "risques_appliques": risques_appliques,
                "mode": dossier.mode_tarification,
                "nb_voyages": dossier.nb_voyages_annuels,
            },
            score_risque=score,
        )

    def calculer_prime_rc_transporteur(self, dossier: DossierTransport, pays: str = "CM") -> DevisTransport:
        """RC Transporteur : taux sur CA transport."""
        taux = TAUX_RC_TRANSPORTEUR.get(dossier.type_vehicule, 4.0)
        ca = dossier.chiffre_affaires_transport_fcfa

        # Dégressivité flotte
        coeff_flotte = 1.0
        if dossier.nb_vehicules >= 10:
            coeff_flotte = COEFFICIENTS_RISQUES.get("flotte_gt10", 0.80)
        elif dossier.nb_vehicules >= 5:
            coeff_flotte = 0.90

        prime_base = round(ca / 1000 * taux * coeff_flotte)
        # Minimum de prime (Art. 12 CIMA)
        prime_minimum = 150_000 * dossier.nb_vehicules
        prime_base = max(prime_base, prime_minimum)

        garanties = [
            "RC pour dommages corporels aux tiers",
            "RC pour dommages matériels aux tiers",
            "RC pour pertes et avaries des marchandises confiées",
            "Défense et recours",
            "Frais de déplacement et remorquage",
        ]
        if dossier.type_vehicule in ("citerne_carburant", "citerne_produits_chimiques"):
            garanties.append("Dépollution et décontamination (Art. 229 CIMA)")

        franchises = {
            "dommages_corporels": "Néant (RC obligatoire)",
            "dommages_materiels": "50 000 FCFA",
            "pertes_marchandises": "100 000 FCFA ou 5% du sinistre",
        }
        exclusions = [
            "Dommages intentionnels",
            "Guerre et risques assimilés (sauf option)",
            "Nucléaire",
            "Transport illicite",
        ]

        plafond = max(50_000_000, ca * 0.20)  # Min 50M FCFA ou 20% CA

        taxe_cima = round(prime_base * self.TAXE_CIMA)
        taxe_locale = round(prime_base * self.TAXE_LOCALE_PAR_PAYS.get(pays, 0.18))
        prime_ttc = prime_base + taxe_cima + taxe_locale

        return DevisTransport(
            prime_nette=prime_base,
            taxes_cima=taxe_cima,
            taxes_locales=taxe_locale,
            prime_ttc=prime_ttc,
            garanties_incluses=garanties,
            franchises=franchises,
            exclusions=exclusions,
            type_couverture="rc_transporteur",
            plafond_indemnisation_fcfa=plafond,
            plafond_cmr_fcfa=None,
            detail_calcul={
                "chiffre_affaires_fcfa": ca,
                "taux_pour_mille": taux,
                "type_vehicule": dossier.type_vehicule,
                "nb_vehicules": dossier.nb_vehicules,
                "coeff_flotte": coeff_flotte,
                "prime_minimum": prime_minimum,
            },
            score_risque="eleve" if dossier.type_vehicule in (
                "citerne_carburant", "citerne_produits_chimiques", "fourgon_valeurs"
            ) else "standard",
        )

    def calculer_prime_corps_vehicule(self, dossier: DossierTransport, pays: str = "CM") -> DevisTransport:
        """Corps de véhicule de transport."""
        taux = TAUX_CORPS_VEHICULE.get(dossier.type_vehicule, 4.0)
        valeur = dossier.valeur_venale_vehicule_fcfa or dossier.valeur_vehicule_neuf_fcfa

        # Dégressivité ancienneté
        age = datetime.now().year - dossier.annee_vehicule
        coeff_age = 1.0
        if age <= 2:
            coeff_age = 0.90    # Neuf : bonus
        elif age >= 10:
            coeff_age = 1.30    # Vieux : malus

        prime_base = round(valeur / 100 * taux * coeff_age * dossier.nb_vehicules)

        garanties = [
            "Dommages collision tous risques",
            "Vol et tentative de vol",
            "Incendie et explosion",
            "Catastrophes naturelles",
            "Bris de glace pare-brise",
            "Vandalisme",
        ]
        if dossier.type_vehicule in ("citerne_carburant", "citerne_produits_chimiques"):
            garanties.append("Corps citerne / équipements spéciaux")

        franchises = {
            "collision": "100 000 FCFA ou 5% du sinistre",
            "vol_total": "200 000 FCFA",
            "incendie": "50 000 FCFA",
            "bris_glace": "30 000 FCFA",
        }
        exclusions = [
            "Usure et vétusté normales",
            "Surcharge volontaire",
            "Saisie judiciaire",
            "Usage hors objet du contrat",
        ]

        taxe_cima = round(prime_base * self.TAXE_CIMA)
        taxe_locale = round(prime_base * self.TAXE_LOCALE_PAR_PAYS.get(pays, 0.18))
        prime_ttc = prime_base + taxe_cima + taxe_locale

        return DevisTransport(
            prime_nette=prime_base,
            taxes_cima=taxe_cima,
            taxes_locales=taxe_locale,
            prime_ttc=prime_ttc,
            garanties_incluses=garanties,
            franchises=franchises,
            exclusions=exclusions,
            type_couverture="corps_vehicule",
            plafond_indemnisation_fcfa=valeur * dossier.nb_vehicules,
            plafond_cmr_fcfa=None,
            detail_calcul={
                "valeur_vehicule_fcfa": valeur,
                "nb_vehicules": dossier.nb_vehicules,
                "taux_pct": taux,
                "age_vehicule": age,
                "coeff_age": coeff_age,
            },
            score_risque="eleve" if age >= 10 else "standard",
        )

    def _garanties_transport(self, dossier: DossierTransport) -> tuple[list[str], dict, list[str]]:
        """Garanties de base selon le type de transport."""
        garanties = [
            "Pertes totales (chargement, naufrage, voie de fait)",
            "Avaries communes (sacrifice, contribution)",
            "Frais de sauvetage",
            "Contribution aux avaries communes",
        ]

        # Garanties selon le mode
        if "maritime" in dossier.type_transport:
            garanties += [
                "Corps du navire (si affréteur)",
                "Frais de déchargement d'urgence",
                "Avaries de mer",
            ]
        elif "aerien" in dossier.type_transport:
            garanties += [
                "Pertes et avaries en soute",
                "Rupture de la chaîne du froid (si frigo)",
            ]
        elif "terrestre" in dossier.type_transport:
            garanties += [
                "Bris et casses en cours de manutention",
                "Mouille et contamination",
                "Disparition inexpliquée après inventaire",
            ]

        exclusions = [
            "Freinte de route (pertes normales de poids)",
            "Emballages inadaptés",
            "Vice propre de la marchandise",
            "Dommages intentionnels de l'assuré",
            "Guerre et risques de guerre (sauf option)",
            "Grèves et émeutes (sauf option)",
            "Nucléaire et contamination radioactive",
            "Insolvabilité du transporteur",
        ]

        franchises = dict(FRANCHISES_TRANSPORT)

        return garanties, franchises, exclusions


# ─── Service Transport principal ──────────────────────────────────────────────

class ServiceTransport:
    """
    Service complet transport assurance.
    Intègre tarification, émission police, gestion déclarations,
    analyse IA des risques, et conformité CMR/CIMA.
    """

    def __init__(self):
        self._moteur = MoteurTarifTransport()
        self._polices: dict[str, PoliceTransport] = {}

    # ─── Calcul de devis ─────────────────────────────────────────────

    async def calculer_devis(
        self,
        dossier: DossierTransport,
        pays: str = "CM",
        enrichir_ia: bool = True,
    ) -> DevisTransport:
        """
        Calcule un devis transport complet.
        Option enrichir_ia : analyse IA du risque pour recommandations personnalisées.
        """
        # Tarification selon le type de couverture
        if dossier.type_couverture == "marchandises":
            devis = self._moteur.calculer_prime_marchandises(dossier, pays)
        elif dossier.type_couverture == "rc_transporteur":
            devis = self._moteur.calculer_prime_rc_transporteur(dossier, pays)
        elif dossier.type_couverture == "corps":
            devis = self._moteur.calculer_prime_corps_vehicule(dossier, pays)
        elif dossier.type_couverture == "cmr":
            # CMR = RC transporteur + marchandises combinés
            rc = self._moteur.calculer_prime_rc_transporteur(dossier, pays)
            marc = self._moteur.calculer_prime_marchandises(dossier, pays)
            # Prime combinée avec réduction 15%
            prime_comb = round((rc.prime_nette + marc.prime_nette) * 0.85)
            taxe_cima = round(prime_comb * MoteurTarifTransport.TAXE_CIMA)
            taxe_locale = round(prime_comb * MoteurTarifTransport.TAXE_LOCALE_PAR_PAYS.get(pays, 0.18))
            devis = DevisTransport(
                prime_nette=prime_comb,
                taxes_cima=taxe_cima,
                taxes_locales=taxe_locale,
                prime_ttc=prime_comb + taxe_cima + taxe_locale,
                garanties_incluses=rc.garanties_incluses + marc.garanties_incluses,
                franchises={**rc.franchises, **marc.franchises},
                exclusions=list(set(rc.exclusions + marc.exclusions)),
                type_couverture="cmr_complet",
                plafond_indemnisation_fcfa=marc.plafond_indemnisation_fcfa,
                plafond_cmr_fcfa=marc.plafond_cmr_fcfa,
                detail_calcul={
                    "prime_rc": rc.prime_nette,
                    "prime_marchandises": marc.prime_nette,
                    "reduction_combinaison": "15%",
                },
                score_risque=max(rc.score_risque, marc.score_risque,
                                 key=lambda x: {"faible": 0, "standard": 1, "eleve": 2}.get(x, 1)),
            )
        elif dossier.type_couverture == "flotte":
            devis = await self._calculer_devis_flotte(dossier, pays)
        else:
            devis = self._moteur.calculer_prime_marchandises(dossier, pays)

        # Enrichissement IA
        if enrichir_ia and devis.score_risque == "eleve":
            devis.recommandations_ia = await self._analyser_risque_ia(dossier, devis)

        return devis

    async def _calculer_devis_flotte(self, dossier: DossierTransport, pays: str) -> DevisTransport:
        """Calcul devis flotte : corps + RC pour plusieurs véhicules."""
        corps = self._moteur.calculer_prime_corps_vehicule(dossier, pays)
        rc = self._moteur.calculer_prime_rc_transporteur(dossier, pays)
        prime_flotte = round((corps.prime_nette + rc.prime_nette) * 0.88)  # -12% flotte
        taxe_cima = round(prime_flotte * MoteurTarifTransport.TAXE_CIMA)
        taxe_locale = round(prime_flotte * MoteurTarifTransport.TAXE_LOCALE_PAR_PAYS.get(pays, 0.18))
        return DevisTransport(
            prime_nette=prime_flotte,
            taxes_cima=taxe_cima,
            taxes_locales=taxe_locale,
            prime_ttc=prime_flotte + taxe_cima + taxe_locale,
            garanties_incluses=corps.garanties_incluses + rc.garanties_incluses,
            franchises={**corps.franchises, **rc.franchises},
            exclusions=list(set(corps.exclusions + rc.exclusions)),
            type_couverture="flotte_complete",
            plafond_indemnisation_fcfa=corps.plafond_indemnisation_fcfa,
            plafond_cmr_fcfa=None,
            detail_calcul={
                "nb_vehicules": dossier.nb_vehicules,
                "prime_corps_total": corps.prime_nette,
                "prime_rc_total": rc.prime_nette,
                "reduction_flotte": "12%",
            },
            score_risque=corps.score_risque,
        )

    async def _analyser_risque_ia(self, dossier: DossierTransport, devis: DevisTransport) -> str:
        """Analyse IA du risque transport pour profils élevés."""
        prompt = f"""Tu es souscripteur transport senior dans une compagnie d'assurance CIMA.

Profil risque à analyser :
- Type couverture : {dossier.type_couverture}
- Transport : {dossier.type_transport}
- Marchandises : {dossier.description_marchandises or 'non précisé'}
- Valeur : {dossier.valeur_marchandises_fcfa:,.0f} FCFA
- Trajet : {dossier.lieu_chargement} → {dossier.lieu_livraison}
- Pays transit : {', '.join(dossier.pays_transit) or 'direct'}
- Risques spéciaux : {', '.join(dossier.risques_speciaux) or 'aucun'}
- Score calculé : {devis.score_risque}
- Prime nette : {devis.prime_nette:,.0f} FCFA

En 3-4 phrases, donne :
1. L'évaluation du risque (points critiques)
2. Les recommandations de prévention pour l'assuré
3. Si une inspection préalable ou pré-acceptation est recommandée
"""
        try:
            result = await orchestrateur.orchestrer(
                ContexteRequete(domaine=DomaineMétier.SINISTRES, texte=prompt)
            )
            return result.reponse
        except Exception:
            return "Risque élevé — vérifier l'emballage et l'itinéraire avant souscription."

    # ─── Émission police ──────────────────────────────────────────────

    async def emettre_police(
        self,
        dossier: DossierTransport,
        devis: DevisTransport,
        numero_police: str,
    ) -> PoliceTransport:
        """Émet une police transport et l'enregistre dans ORASS."""
        date_effet = dossier.date_effet or date.today().isoformat()
        if dossier.mode_tarification == "abonnement_annuel":
            date_echeance = (date.fromisoformat(date_effet) + timedelta(days=365)).isoformat()
        elif dossier.date_livraison_prevue:
            # Voyage unique : jusqu'à la livraison + 30 jours tampon
            d_liv = date.fromisoformat(dossier.date_livraison_prevue)
            date_echeance = (d_liv + timedelta(days=30)).isoformat()
        else:
            date_echeance = (date.fromisoformat(date_effet) + timedelta(days=30)).isoformat()

        police = PoliceTransport(
            numero_police=numero_police,
            type_couverture=dossier.type_couverture,
            statut="actif",
            dossier=dossier,
            devis=devis,
            cree_le=datetime.now().isoformat(),
            date_effet=date_effet,
            date_echeance=date_echeance,
        )

        self._polices[numero_police] = police

        # Intégration ORASS
        try:
            await orass.creer_contrat({
                "nom": dossier.nom_assure,
                "telephone": dossier.telephone,
                "branche": "transport",
                "type_couverture": dossier.type_couverture,
                "prime_nette": devis.prime_nette,
                "prime_ttc": devis.prime_ttc,
                "date_effet": date_effet,
                "date_echeance": date_echeance,
                "numero_police_local": numero_police,
                "agent_code": dossier.agent_code,
                "courtier_code": dossier.courtier_code,
                "description_marchandises": dossier.description_marchandises,
                "valeur_assuree": dossier.valeur_marchandises_fcfa,
                "plafond_indemnisation": devis.plafond_indemnisation_fcfa,
                "garanties": devis.garanties_incluses,
            })
            logger.info(f"[Transport] Police {numero_police} enregistrée dans ORASS")
        except Exception as e:
            logger.debug(f"[Transport] ORASS non disponible ({e}) — police enregistrée localement")

        return police

    # ─── Déclaration de sinistre ──────────────────────────────────────

    async def declarer_sinistre_transport(
        self,
        numero_police: str,
        description_sinistre: str,
        valeur_dommages_fcfa: float,
        lieu_sinistre: str,
        date_sinistre: str,
        documents_b64: Optional[list[str]] = None,
    ) -> dict:
        """
        Déclare un sinistre transport.
        L'IA évalue la couverture, applique les franchises, et propose un règlement.
        """
        police = self._polices.get(numero_police)
        if not police:
            return {"succes": False, "erreur": f"Police {numero_police} introuvable"}

        devis = police.devis
        dossier = police.dossier

        # Franchise applicable
        franchise = 0
        if "vol" in description_sinistre.lower():
            franchise = devis.franchises.get("vol_total", 200_000)
        elif "avari" in description_sinistre.lower():
            franchise = devis.franchises.get("avaries_particulieres", 150_000)
        else:
            franchise = devis.franchises.get("avaries_ordinaires", 100_000)

        # Règlement net
        indemnite_brute = min(valeur_dommages_fcfa, devis.plafond_indemnisation_fcfa)
        indemnite_nette = max(0, indemnite_brute - franchise)

        # Analyse IA
        prompt = f"""Tu es expert sinistres transport CIMA.

Sinistre déclaré :
- Police : {numero_police} ({devis.type_couverture})
- Type transport : {dossier.type_transport}
- Description : {description_sinistre}
- Lieu : {lieu_sinistre}
- Date : {date_sinistre}
- Valeur dommages déclarée : {valeur_dommages_fcfa:,.0f} FCFA
- Plafond police : {devis.plafond_indemnisation_fcfa:,.0f} FCFA
- Franchise applicable : {franchise:,.0f} FCFA
- Indemnité nette calculée : {indemnite_nette:,.0f} FCFA

Garanties couvertes : {', '.join(devis.garanties_incluses[:5])}
Exclusions : {', '.join(devis.exclusions[:4])}

Évalue :
1. La couverture (sinistre couvert ? partiellement ? exclusion applicable ?)
2. Les pièces justificatives requises (connaissement, expertise, factures...)
3. Le délai de règlement recommandé (max 30 jours Art. 12 CIMA)
4. Recommandation de règlement en JSON : {{"couvert": true, "indemnite_recommandee_fcfa": 0, "reserves": "", "pieces_requises": []}}
"""
        try:
            result = await orchestrateur.orchestrer(
                ContexteRequete(domaine=DomaineMétier.SINISTRES, texte=prompt)
            )
            analyse = result.reponse
        except Exception:
            analyse = f"Sinistre en cours d'instruction. Indemnité estimée : {indemnite_nette:,.0f} FCFA."

        # Enregistrement ORASS
        numero_sinistre = f"SIN-TR-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        try:
            await orass.enregistrer_sinistre({
                "numero_sinistre": numero_sinistre,
                "numero_police": numero_police,
                "date_sinistre": date_sinistre,
                "description": description_sinistre,
                "valeur_declaree": valeur_dommages_fcfa,
                "indemnite_estimee": indemnite_nette,
                "statut": "ouvert",
                "branche": "transport",
            })
        except Exception as e:
            logger.debug(f"[Transport] ORASS sinistre: {e}")

        return {
            "succes": True,
            "numero_sinistre": numero_sinistre,
            "numero_police": numero_police,
            "valeur_declaree_fcfa": valeur_dommages_fcfa,
            "franchise_fcfa": franchise,
            "indemnite_brute_fcfa": round(indemnite_brute),
            "indemnite_nette_estimee_fcfa": round(indemnite_nette),
            "plafond_police_fcfa": devis.plafond_indemnisation_fcfa,
            "plafond_cmr_fcfa": devis.plafond_cmr_fcfa,
            "analyse_ia": analyse,
            "delai_reglementaire_jours": 30,
            "article_cima": "Art. 12 Code CIMA — délai maximum de règlement",
        }

    # ─── Calcul CMR ───────────────────────────────────────────────────

    def calculer_plafond_cmr(self, poids_kg: float, poids_brut_kg: float = None) -> dict:
        """
        Calcul du plafond d'indemnisation selon Convention CMR.
        Plafond CMR = poids × 8,33 DTS/kg.
        """
        poids_ref = poids_brut_kg or poids_kg
        plafond_dts = poids_ref * CMR_PLAFOND_PAR_KG_SDR
        plafond_fcfa = round(plafond_dts * SDR_TO_FCFA)

        return {
            "convention": "CMR 1956 — Art. 23 §3",
            "poids_kg": poids_ref,
            "plafond_dts": round(plafond_dts, 2),
            "taux_dts_par_kg": CMR_PLAFOND_PAR_KG_SDR,
            "taux_change_sdr_fcfa": SDR_TO_FCFA,
            "plafond_indemnisation_fcfa": plafond_fcfa,
            "note": "Le plafond CMR s'applique uniquement au transport routier international. "
                    "Pour dépasser ce plafond, déclarer une valeur spéciale (Art. 24 CMR).",
        }

    # ─── Attestation voyage ────────────────────────────────────────────

    def generer_attestation_voyage(self, police: PoliceTransport) -> dict:
        """
        Génère les données pour un certificat de transport / lettre de voiture.
        Utilisé avec le module générateur_contrats pour la sortie PDF.
        """
        return {
            "type_document": "certificat_transport_cima",
            "numero_police": police.numero_police,
            "nom_assure": police.dossier.nom_assure,
            "type_couverture": police.type_couverture,
            "marchandises": police.dossier.description_marchandises,
            "valeur_assuree": police.dossier.valeur_marchandises_fcfa,
            "trajet": f"{police.dossier.lieu_chargement} → {police.dossier.lieu_livraison}",
            "date_effet": police.date_effet,
            "date_echeance": police.date_echeance,
            "prime_ttc": police.devis.prime_ttc,
            "garanties": police.devis.garanties_incluses,
            "franchises": police.devis.franchises,
            "plafond_fcfa": police.devis.plafond_indemnisation_fcfa,
            "plafond_cmr_fcfa": police.devis.plafond_cmr_fcfa,
            "base_reglementaire": "Art. 212-229 Code CIMA — Livre II Branche Transport",
        }

    # ─── Statistiques portefeuille transport ─────────────────────────

    def statistiques_portefeuille(self) -> dict:
        """Analyse du portefeuille transport pour le tableau de bord."""
        polices = list(self._polices.values())
        actives = [p for p in polices if p.statut == "actif"]
        primes_totales = sum(p.devis.prime_ttc for p in actives)
        valeurs_assurees = sum(p.dossier.valeur_marchandises_fcfa for p in actives)

        par_type: dict[str, int] = {}
        for p in polices:
            t = p.type_couverture
            par_type[t] = par_type.get(t, 0) + 1

        return {
            "total_polices": len(polices),
            "polices_actives": len(actives),
            "primes_ttc_totales_fcfa": round(primes_totales),
            "valeurs_assurees_totales_fcfa": round(valeurs_assurees),
            "repartition_par_type": par_type,
            "prime_moyenne_fcfa": round(primes_totales / len(actives)) if actives else 0,
        }


# Instance singleton
service_transport = ServiceTransport()
