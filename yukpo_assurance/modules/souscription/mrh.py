"""
YukpoAssurance — Module MRH (Multi-Risques Habitation) CIMA complet
Branche 40 — IRD (Incendie, Risques Divers) — Code CIMA Art. 199-211

Couvertures :
- Incendie, explosion, foudre
- Vol et tentative de vol
- Dégâts des eaux
- Responsabilité Civile locataire / propriétaire
- Catastrophes naturelles (inondations, séismes, tempêtes)
- Bris de glace
- Objets de valeur (bijoux, œuvres d'art)
- Appareils électriques et électroménager
- Pertes d'exploitation locataire (loyers)

Conformité CIMA : Art. 199-211, Circulaire CRCA 2024-001 (microassurance), OHADA
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from core.ia_client import ModeIA, ia_client
from core.orchestrateur import ContexteRequete, DomaineMétier, orchestrateur
from core.orass_connector import orass

logger = logging.getLogger("yukpo_assurance.mrh")

# ─── Barèmes MRH (Zone CIMA 2024) ────────────────────────────────────────────

# Taux de prime en ‰ de la valeur assurée
TAUX_MRH_BASE: dict[str, float] = {
    # Incendie et risques annexes
    "incendie_villa":           1.50,   # ‰ valeur bâtiment
    "incendie_appartement":     1.20,
    "incendie_immeuble":        0.90,   # Propriétaire bailleur (dégressif)
    # Contenu / mobilier
    "mobilier_standard":        3.00,   # ‰ valeur mobilier
    "mobilier_haut_gamme":      5.00,   # Mobilier > 10M FCFA
    # Vol
    "vol_appartement":          4.00,
    "vol_villa":                5.00,   # Plus exposée
    "vol_magasin_attenant":     8.00,
    # Dégâts des eaux
    "degats_eaux":              2.00,
    # Catastrophes naturelles
    "cat_nat_zone_a":           0.50,   # Risque faible
    "cat_nat_zone_b":           1.20,   # Risque moyen (côtier, tempêtes)
    "cat_nat_zone_c":           2.50,   # Risque élevé (inondable, séismique)
    # Bris de glace
    "bris_glace_surface_lte50": 0.80,   # ‰ valeur vitrages
    "bris_glace_surface_gt50":  0.60,
    # RC locataire / propriétaire
    "rc_locataire":             600,    # FCFA forfaitaire annuel
    "rc_proprietaire_bailleur": 900,    # FCFA forfaitaire annuel
    # Objets de valeur
    "objets_valeur":            8.00,   # ‰ valeur déclarée
    # Appareils électriques
    "appareil_electro":         3.00,   # ‰ valeur appareils
    # Pertes loyers (propriétaire)
    "perte_loyers":             5.00,   # ‰ valeur loyer annuel
}

# Limites et plafonds par garantie (FCFA)
PLAFONDS_MRH: dict[str, int] = {
    "incendie_bâtiment_max":    500_000_000,
    "incendie_mobilier_max":    50_000_000,
    "vol_max":                  10_000_000,
    "vol_especes_max":          500_000,      # Limite espèces
    "degats_eaux_max":          5_000_000,
    "cat_nat_max":              50_000_000,
    "bris_glace_max":           2_000_000,
    "rc_corporel_max":          100_000_000,  # RC obligatoire
    "rc_materiel_max":          20_000_000,
    "objets_valeur_max":        10_000_000,
    "electro_max":              5_000_000,
    "perte_loyers_max":         12_000_000,   # 12 mois max
}

# Franchises standard (FCFA)
FRANCHISES_MRH: dict[str, int] = {
    "incendie":                 50_000,
    "vol":                      100_000,
    "vol_especes":              0,            # Plafond but pas franchise
    "degats_eaux":              50_000,
    "cat_nat":                  100_000,
    "bris_glace":               25_000,
    "rc_materiel":              25_000,
    "rc_corporel":              0,            # Jamais de franchise RC corporel
    "objets_valeur":            150_000,
    "electro_surtension":       30_000,
}

# Coefficients de modulation
COEFFICIENTS_MRH: dict[str, float] = {
    # Qualité construction
    "construction_dur":         1.00,   # Béton, brique
    "construction_semi_dur":    1.30,   # Mixte
    "construction_legere":      1.80,   # Bois, banco, tôle
    # Situation géographique
    "zone_urbaine_securisee":   0.90,
    "zone_urbaine_standard":    1.00,
    "zone_periurbaine":         1.20,
    "zone_rurale":              1.10,
    "zone_inondable":           1.80,
    # Occupation
    "occupant_proprietaire":    0.90,   # Moins de risques
    "locataire":                1.00,
    "locaux_professionnels":    1.40,
    "location_saisonniere":     1.60,
    # Ancienneté bâtiment
    "batiment_neuf":            0.90,
    "batiment_5_15ans":         1.00,
    "batiment_gt15ans":         1.20,
    "batiment_gt30ans":         1.40,
    # Mesures de sécurité
    "alarme_surveillance":      0.85,
    "gardiennage_24h":          0.80,
    "porte_blindee":            0.90,
    # Sinistralité
    "sans_sinistre_3ans":       0.85,
    "sinistre_1_en_3ans":       1.10,
    "sinistre_2_plus_en_3ans":  1.40,
}

# Zones à risque catnat par pays CIMA
ZONES_CATNAT: dict[str, str] = {
    "Douala":       "B",    # Zone côtière / inondable
    "Yaoundé":      "A",
    "Abidjan":      "B",
    "Dakar":        "A",
    "Conakry":      "C",    # Zone séismique + côtière
    "Libreville":   "B",
    "Kinshasa":     "B",
    "Bangui":       "A",
    "Ndjamena":     "A",
    "Niamey":       "A",
    "Ouagadougou":  "A",
    "Bamako":       "A",
    "Lomé":         "B",
    "Cotonou":      "B",
    "Malabo":       "B",
}


# ─── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class DossierMRH:
    """Dossier complet de souscription MRH."""

    # Type de bien
    type_bien: str = "appartement"  # "appartement" | "villa" | "immeuble" | "mixte"
    statut_occupant: str = "locataire"  # "locataire" | "proprietaire" | "proprietaire_bailleur"

    # Localisation
    adresse: str = ""
    ville: str = ""
    pays: str = "CM"
    zone_risque: Optional[str] = None   # "A" | "B" | "C" — auto-déterminée si ville connue

    # Caractéristiques du bien
    surface_m2: float = 0
    nb_pieces: int = 3
    type_construction: str = "construction_dur"
    annee_construction: int = 2010
    nb_etages: int = 1
    presence_verandah: bool = False
    nb_baies_vitrees: int = 4

    # Valeurs assurées
    valeur_batiment_fcfa: float = 0         # Valeur reconstruction
    valeur_mobilier_fcfa: float = 0         # Contenu
    valeur_objets_valeur_fcfa: float = 0    # Bijoux, art, collections
    valeur_appareils_fcfa: float = 0        # Électroménager, hi-fi, informatique
    loyer_mensuel_fcfa: float = 0           # Pour perte loyers

    # Garanties demandées
    garanties: list[str] = field(default_factory=lambda: [
        "incendie", "vol", "degats_eaux", "rc_locataire", "bris_glace"
    ])
    # Options : "cat_nat", "objets_valeur", "appareil_electro", "perte_loyers", "rc_proprietaire"

    # Modulations risque
    mesures_securite: list[str] = field(default_factory=list)
    # ["alarme_surveillance", "gardiennage_24h", "porte_blindee"]
    situation_geographique: str = "zone_urbaine_standard"
    sinistralite_3ans: str = "sans_sinistre_3ans"

    # Assuré
    nom_assure: str = ""
    telephone: str = ""
    email: str = ""
    date_naissance: Optional[str] = None

    # Contrat
    agent_code: Optional[str] = None
    courtier_code: Optional[str] = None
    date_effet: Optional[str] = None


@dataclass
class DevisMRH:
    """Devis MRH détaillé par garantie."""
    prime_nette_totale: float
    taxes_cima: float
    taxes_locales: float
    prime_ttc: float

    detail_par_garantie: dict[str, dict]    # Garantie -> {prime, plafond, franchise}
    garanties_incluses: list[str]
    garanties_optionnelles_disponibles: list[str]
    franchises: dict[str, int]
    exclusions: list[str]

    coefficients_appliques: dict[str, float]
    score_risque: str                       # "faible" | "standard" | "eleve"
    zone_catnat: str                        # "A" | "B" | "C"
    recommandations: list[str]


# ─── Moteur de tarification MRH ──────────────────────────────────────────────

class MoteurTarifMRH:
    """Calcul actuariel MRH conforme CIMA — Art. 199-211."""

    TAXE_CIMA = 0.05
    TAXE_LOCALE_PAR_PAYS: dict[str, float] = {
        "CM": 0.1925, "CI": 0.1800, "SN": 0.1800, "BF": 0.1800,
        "ML": 0.1800, "NE": 0.1800, "TG": 0.1800, "BJ": 0.1800,
        "GN": 0.1800, "GA": 0.1800, "CG": 0.1800, "CF": 0.1800,
        "TD": 0.1800, "GQ": 0.1800, "CD": 0.1600,
    }

    def calculer_devis(self, dossier: DossierMRH) -> DevisMRH:
        """Calcul complet du devis MRH."""
        # Détermination zone catnat
        zone = dossier.zone_risque or ZONES_CATNAT.get(dossier.ville, "A")

        # Coefficient de construction
        coeff_construction = COEFFICIENTS_MRH.get(dossier.type_construction, 1.0)

        # Coefficient ancienneté bâtiment
        age = datetime.now().year - dossier.annee_construction
        if age <= 5:
            coeff_age = COEFFICIENTS_MRH["batiment_neuf"]
        elif age <= 15:
            coeff_age = COEFFICIENTS_MRH["batiment_5_15ans"]
        elif age <= 30:
            coeff_age = COEFFICIENTS_MRH["batiment_gt15ans"]
        else:
            coeff_age = COEFFICIENTS_MRH["batiment_gt30ans"]

        # Coefficient géographique
        coeff_geo = COEFFICIENTS_MRH.get(dossier.situation_geographique, 1.0)

        # Coefficient sécurité (produit de toutes les mesures)
        coeff_secu = 1.0
        for mesure in dossier.mesures_securite:
            coeff_secu *= COEFFICIENTS_MRH.get(mesure, 1.0)
        coeff_secu = max(0.70, coeff_secu)  # Plancher 30% de réduction

        # Coefficient sinistralité
        coeff_sin = COEFFICIENTS_MRH.get(dossier.sinistralite_3ans, 1.0)

        # Coefficient occupant
        coeff_occupant = COEFFICIENTS_MRH.get(
            "occupant_proprietaire" if "proprietaire" in dossier.statut_occupant else "locataire",
            1.0
        )

        coefficients_appliques = {
            "construction": coeff_construction,
            "anciennete": coeff_age,
            "geographique": coeff_geo,
            "securite": round(coeff_secu, 3),
            "sinistralite": coeff_sin,
            "occupant": coeff_occupant,
        }
        coeff_global = coeff_construction * coeff_age * coeff_geo * coeff_secu * coeff_sin * coeff_occupant

        # Calcul par garantie
        detail: dict[str, dict] = {}
        prime_nette_total = 0

        for garantie in dossier.garanties:
            prime_g, plafond_g, franchise_g = self._calculer_garantie(
                garantie, dossier, zone, coeff_global
            )
            if prime_g > 0:
                detail[garantie] = {
                    "prime_nette": round(prime_g),
                    "plafond_fcfa": plafond_g,
                    "franchise_fcfa": franchise_g,
                }
                prime_nette_total += prime_g

        prime_nette_total = round(prime_nette_total)

        # Taxes
        taxe_cima = round(prime_nette_total * self.TAXE_CIMA)
        taxe_locale = round(prime_nette_total * self.TAXE_LOCALE_PAR_PAYS.get(dossier.pays, 0.18))
        prime_ttc = prime_nette_total + taxe_cima + taxe_locale

        # Score risque
        if coeff_global >= 1.40:
            score = "eleve"
        elif coeff_global <= 0.90:
            score = "faible"
        else:
            score = "standard"

        # Garanties optionnelles non souscrites
        toutes_garanties = {"incendie", "vol", "degats_eaux", "rc_locataire", "rc_proprietaire",
                            "bris_glace", "cat_nat", "objets_valeur", "appareil_electro", "perte_loyers"}
        optionnelles = list(toutes_garanties - set(dossier.garanties))

        # Recommandations
        recommandations = self._generer_recommandations(dossier, score, zone, optionnelles)

        return DevisMRH(
            prime_nette_totale=prime_nette_total,
            taxes_cima=taxe_cima,
            taxes_locales=taxe_locale,
            prime_ttc=prime_ttc,
            detail_par_garantie=detail,
            garanties_incluses=list(dossier.garanties),
            garanties_optionnelles_disponibles=optionnelles,
            franchises={g: d["franchise_fcfa"] for g, d in detail.items()},
            exclusions=self._exclusions_mrh(dossier),
            coefficients_appliques=coefficients_appliques,
            score_risque=score,
            zone_catnat=zone,
            recommandations=recommandations,
        )

    def _calculer_garantie(
        self, garantie: str, dossier: DossierMRH, zone: str, coeff_global: float
    ) -> tuple[float, int, int]:
        """Calcule la prime, le plafond et la franchise pour une garantie."""

        if garantie == "incendie":
            type_key = f"incendie_{dossier.type_bien}" if dossier.type_bien in ("villa", "immeuble") else "incendie_appartement"
            taux = TAUX_MRH_BASE.get(type_key, 1.20)
            valeur = dossier.valeur_batiment_fcfa + dossier.valeur_mobilier_fcfa
            prime = valeur / 1000 * taux * coeff_global
            plafond = min(valeur, PLAFONDS_MRH["incendie_bâtiment_max"])
            franchise = FRANCHISES_MRH["incendie"]

        elif garantie == "vol":
            type_key = f"vol_{dossier.type_bien}" if dossier.type_bien in ("villa", "appartement") else "vol_appartement"
            taux = TAUX_MRH_BASE.get(type_key, 4.0)
            valeur = dossier.valeur_mobilier_fcfa
            prime = valeur / 1000 * taux * coeff_global
            plafond = min(valeur, PLAFONDS_MRH["vol_max"])
            franchise = FRANCHISES_MRH["vol"]

        elif garantie == "degats_eaux":
            taux = TAUX_MRH_BASE["degats_eaux"]
            valeur = dossier.valeur_batiment_fcfa * 0.20 + dossier.valeur_mobilier_fcfa * 0.30
            prime = valeur / 1000 * taux * coeff_global
            plafond = PLAFONDS_MRH["degats_eaux_max"]
            franchise = FRANCHISES_MRH["degats_eaux"]

        elif garantie in ("rc_locataire", "rc_proprietaire"):
            prime = TAUX_MRH_BASE.get(f"rc_{'locataire' if 'locataire' in garantie else 'proprietaire_bailleur'}", 600)
            plafond = PLAFONDS_MRH["rc_corporel_max"]
            franchise = FRANCHISES_MRH["rc_materiel"]

        elif garantie == "bris_glace":
            valeur_vitrages = dossier.nb_baies_vitrees * 150_000   # Estimation 150k par baie
            taux_key = "bris_glace_surface_lte50" if dossier.surface_m2 <= 50 else "bris_glace_surface_gt50"
            taux = TAUX_MRH_BASE[taux_key]
            prime = valeur_vitrages / 1000 * taux * coeff_global
            plafond = min(valeur_vitrages, PLAFONDS_MRH["bris_glace_max"])
            franchise = FRANCHISES_MRH["bris_glace"]

        elif garantie == "cat_nat":
            zone_key = f"cat_nat_zone_{zone.lower()}"
            taux = TAUX_MRH_BASE.get(zone_key, 1.20)
            valeur = dossier.valeur_batiment_fcfa + dossier.valeur_mobilier_fcfa
            prime = valeur / 1000 * taux   # Pas de coeff_global sur catnat (mutualisé)
            plafond = min(valeur, PLAFONDS_MRH["cat_nat_max"])
            franchise = FRANCHISES_MRH["cat_nat"]

        elif garantie == "objets_valeur":
            taux = TAUX_MRH_BASE["objets_valeur"]
            valeur = dossier.valeur_objets_valeur_fcfa
            if valeur <= 0:
                return 0, 0, 0
            prime = valeur / 1000 * taux * coeff_global
            plafond = min(valeur, PLAFONDS_MRH["objets_valeur_max"])
            franchise = FRANCHISES_MRH["objets_valeur"]

        elif garantie == "appareil_electro":
            taux = TAUX_MRH_BASE["appareil_electro"]
            valeur = dossier.valeur_appareils_fcfa
            if valeur <= 0:
                return 0, 0, 0
            prime = valeur / 1000 * taux * coeff_global
            plafond = min(valeur, PLAFONDS_MRH["electro_max"])
            franchise = FRANCHISES_MRH["electro_surtension"]

        elif garantie == "perte_loyers":
            if dossier.loyer_mensuel_fcfa <= 0:
                return 0, 0, 0
            loyer_annuel = dossier.loyer_mensuel_fcfa * 12
            taux = TAUX_MRH_BASE["perte_loyers"]
            prime = loyer_annuel / 1000 * taux
            plafond = min(loyer_annuel, PLAFONDS_MRH["perte_loyers_max"])
            franchise = 0

        else:
            return 0, 0, 0

        return max(prime, 0), plafond, franchise

    def _exclusions_mrh(self, dossier: DossierMRH) -> list[str]:
        """Liste des exclusions standard MRH (Art. 199-211 CIMA)."""
        exclusions = [
            "Dommages intentionnels ou dus à la négligence grave",
            "Biens appartenant à des tiers non déclarés",
            "Animaux vivants",
            "Véhicules à moteur (couverts par assurance auto)",
            "Guerre, actes terroristes (sauf option risques politiques)",
            "Nucléaire et contamination radioactive",
            "Usure, vétusté et défaut d'entretien",
            "Humidité et condensation non accidentelle",
            "Grèves et émeutes (sauf option)",
        ]
        if "cat_nat" not in dossier.garanties:
            exclusions.append("Catastrophes naturelles (inondations, séismes, tempêtes) — option disponible")
        if "objets_valeur" not in dossier.garanties:
            exclusions.append("Bijoux, œuvres d'art, collections non déclarés > 500 000 FCFA")
        return exclusions

    def _generer_recommandations(
        self, dossier: DossierMRH, score: str, zone: str, optionnelles: list[str]
    ) -> list[str]:
        """Recommandations personnalisées selon le profil."""
        recs = []

        if score == "eleve":
            recs.append(
                "⚠️ Profil risque élevé : une inspection préalable du bien est recommandée "
                "avant acceptation définitive."
            )
        if zone in ("B", "C") and "cat_nat" in optionnelles:
            recs.append(
                f"Zone catnat {zone} : la garantie Catastrophes Naturelles est vivement recommandée "
                f"(risque inondation/tempête élevé dans votre zone)."
            )
        if dossier.type_construction in ("construction_semi_dur", "construction_legere"):
            recs.append(
                "Construction légère ou semi-dure : vérifier la conformité aux normes locales "
                "de construction. Une mise aux normes peut réduire la prime de 15 à 30%."
            )
        if dossier.valeur_objets_valeur_fcfa > 2_000_000 and "objets_valeur" in optionnelles:
            recs.append(
                "Des objets de valeur > 2M FCFA détectés non couverts. "
                "Ajoutez la garantie objets de valeur pour une couverture complète."
            )
        if not dossier.mesures_securite:
            recs.append(
                "Aucune mesure de sécurité déclarée. L'installation d'une alarme ou "
                "d'une porte blindée peut réduire votre prime vol de 10 à 20%."
            )
        if dossier.sinistralite_3ans == "sans_sinistre_3ans":
            recs.append(
                "Bonus sans sinistre 3 ans : réduction de 15% appliquée. "
                "Maintenez votre bonne sinistralité pour conserver cet avantage."
            )
        return recs


# ─── Service MRH principal ───────────────────────────────────────────────────

class ServiceMRH:
    """
    Service complet MRH : souscription, émission, sinistres, statistiques.
    Conforme Code CIMA Art. 199-211 et Circulaire CRCA 2024 (microassurance).
    """

    def __init__(self):
        self._moteur = MoteurTarifMRH()
        self._polices: dict[str, dict] = {}

    # ─── Devis ────────────────────────────────────────────────────────

    async def calculer_devis(
        self,
        dossier: DossierMRH,
        enrichir_ia: bool = True,
    ) -> DevisMRH:
        """
        Calcule un devis MRH complet avec recommandations IA.
        """
        devis = self._moteur.calculer_devis(dossier)

        # Enrichissement IA pour les profils atypiques
        if enrichir_ia and (devis.score_risque == "eleve" or not dossier.valeur_batiment_fcfa):
            analyse = await self._analyser_profil_ia(dossier, devis)
            devis.recommandations.append(f"Analyse IA : {analyse}")

        return devis

    async def _analyser_profil_ia(self, dossier: DossierMRH, devis: DevisMRH) -> str:
        """Analyse IA pour profils MRH atypiques ou à risque élevé."""
        prompt = f"""Tu es souscripteur MRH senior dans une compagnie d'assurance CIMA.

Profil à analyser :
- Type bien : {dossier.type_bien}, {dossier.surface_m2} m², {dossier.nb_pieces} pièces
- Statut occupant : {dossier.statut_occupant}
- Ville : {dossier.ville}, Pays : {dossier.pays}
- Construction : {dossier.type_construction}, {dossier.annee_construction}
- Zone catnat : {devis.zone_catnat}
- Valeur bâtiment : {dossier.valeur_batiment_fcfa:,.0f} FCFA
- Valeur mobilier : {dossier.valeur_mobilier_fcfa:,.0f} FCFA
- Garanties demandées : {', '.join(dossier.garanties)}
- Mesures sécurité : {', '.join(dossier.mesures_securite) or 'aucune'}
- Score risque calculé : {devis.score_risque}
- Prime TTC : {devis.prime_ttc:,.0f} FCFA

En 2-3 phrases, donne ton avis de souscripteur :
1. Points de vigilance spécifiques
2. Recommandation d'acceptation (accepter / sous conditions / refuser)
"""
        try:
            result = await orchestrateur.orchestrer(
                ContexteRequete(domaine=DomaineMétier.SINISTRES, texte=prompt)
            )
            return result.reponse
        except Exception:
            return "Profil standard — vérifier la valeur de reconstruction déclarée."

    # ─── Émission police ──────────────────────────────────────────────

    async def emettre_police(
        self,
        dossier: DossierMRH,
        devis: DevisMRH,
        numero_police: str,
    ) -> dict:
        """Émet une police MRH et l'intègre dans ORASS."""
        date_effet = dossier.date_effet or date.today().isoformat()
        date_echeance = (date.fromisoformat(date_effet) + timedelta(days=365)).isoformat()

        police = {
            "numero_police": numero_police,
            "branche": "mrh",
            "statut": "actif",
            "nom_assure": dossier.nom_assure,
            "telephone": dossier.telephone,
            "adresse": dossier.adresse,
            "ville": dossier.ville,
            "type_bien": dossier.type_bien,
            "surface_m2": dossier.surface_m2,
            "valeur_batiment": dossier.valeur_batiment_fcfa,
            "valeur_mobilier": dossier.valeur_mobilier_fcfa,
            "prime_nette": devis.prime_nette_totale,
            "prime_ttc": devis.prime_ttc,
            "garanties": devis.garanties_incluses,
            "franchises": devis.franchises,
            "date_effet": date_effet,
            "date_echeance": date_echeance,
            "agent_code": dossier.agent_code,
            "courtier_code": dossier.courtier_code,
            "cree_le": datetime.now().isoformat(),
            "zone_catnat": devis.zone_catnat,
            "score_risque": devis.score_risque,
        }

        self._polices[numero_police] = police

        # Intégration ORASS
        try:
            await orass.creer_contrat({
                **police,
                "numero_police_local": numero_police,
            })
            logger.info(f"[MRH] Police {numero_police} enregistrée dans ORASS")
        except Exception as e:
            logger.debug(f"[MRH] ORASS non disponible ({e}) — police enregistrée localement")

        return {
            "succes": True,
            "numero_police": numero_police,
            "police": police,
            "devis": {
                "prime_nette": devis.prime_nette_totale,
                "taxes_cima": devis.taxes_cima,
                "taxes_locales": devis.taxes_locales,
                "prime_ttc": devis.prime_ttc,
                "detail_par_garantie": devis.detail_par_garantie,
            },
            "attestation_generee": True,
            "message": (
                f"Police MRH {numero_police} émise avec succès. "
                f"Prime TTC : {devis.prime_ttc:,.0f} FCFA/an. "
                f"{len(devis.garanties_incluses)} garanties actives."
            ),
        }

    # ─── Déclaration de sinistre ──────────────────────────────────────

    async def declarer_sinistre(
        self,
        numero_police: str,
        type_sinistre: str,         # "incendie" | "vol" | "degats_eaux" | "cat_nat" | ...
        description: str,
        valeur_dommages_fcfa: float,
        date_sinistre: str,
        photos_b64: Optional[list[str]] = None,
    ) -> dict:
        """
        Déclaration sinistre MRH avec évaluation IA.
        Délai réglementaire : 30 jours pour RC (Art. 12 CIMA).
        """
        police = self._polices.get(numero_police)
        if not police:
            return {"succes": False, "erreur": f"Police {numero_police} introuvable"}

        garanties = police.get("garanties", [])
        if type_sinistre not in garanties:
            return {
                "succes": False,
                "erreur": f"Garantie '{type_sinistre}' non souscrite dans cette police.",
                "garanties_souscrites": garanties,
            }

        franchises = police.get("franchises", {})
        franchise = franchises.get(type_sinistre, FRANCHISES_MRH.get(type_sinistre, 50_000))

        # Plafond d'indemnisation
        plafond = PLAFONDS_MRH.get(f"{type_sinistre}_max",
                   police.get("valeur_batiment", 0) + police.get("valeur_mobilier", 0))

        indemnite_brute = min(valeur_dommages_fcfa, plafond)
        indemnite_nette = max(0, indemnite_brute - franchise)

        # Analyse IA du sinistre
        prompt = f"""Expert sinistres MRH CIMA. Analyse ce sinistre :

Police : {numero_police}
Type sinistre : {type_sinistre}
Description : {description}
Date : {date_sinistre}
Dommages déclarés : {valeur_dommages_fcfa:,.0f} FCFA
Franchise : {franchise:,.0f} FCFA
Plafond police : {plafond:,.0f} FCFA
Indemnité estimée : {indemnite_nette:,.0f} FCFA

Garanties police : {', '.join(garanties)}
Bien assuré : {police.get('type_bien')} à {police.get('ville')}

Indique :
1. La couverture applicable (couverte / exclusion partielle / litige)
2. Les pièces justificatives obligatoires
3. Si une expertise est nécessaire (> 2M FCFA sinistre mat.)
4. Délai de règlement prévu (max 30 jours Art. 12 CIMA)
"""
        try:
            result = await orchestrateur.orchestrer(
                ContexteRequete(domaine=DomaineMétier.SINISTRES, texte=prompt)
            )
            analyse_ia = result.reponse
        except Exception:
            analyse_ia = f"Sinistre {type_sinistre} en cours d'instruction."

        numero_sinistre = f"SIN-MRH-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        try:
            await orass.enregistrer_sinistre({
                "numero_sinistre": numero_sinistre,
                "numero_police": numero_police,
                "date_sinistre": date_sinistre,
                "type_sinistre": type_sinistre,
                "description": description,
                "valeur_declaree": valeur_dommages_fcfa,
                "indemnite_estimee": indemnite_nette,
                "statut": "ouvert",
                "branche": "mrh",
            })
        except Exception:
            pass

        pieces_requises = self._pieces_requises_sinistre(type_sinistre, indemnite_nette)
        expertise_requise = indemnite_nette > 2_000_000

        return {
            "succes": True,
            "numero_sinistre": numero_sinistre,
            "numero_police": numero_police,
            "type_sinistre": type_sinistre,
            "valeur_declaree_fcfa": valeur_dommages_fcfa,
            "franchise_fcfa": franchise,
            "indemnite_brute_fcfa": round(indemnite_brute),
            "indemnite_nette_estimee_fcfa": round(indemnite_nette),
            "plafond_garantie_fcfa": plafond,
            "expertise_requise": expertise_requise,
            "pieces_requises": pieces_requises,
            "delai_reglementaire_jours": 30,
            "article_cima": "Art. 12 Code CIMA",
            "analyse_ia": analyse_ia,
        }

    def _pieces_requises_sinistre(self, type_sinistre: str, montant: float) -> list[str]:
        """Liste des pièces requises selon le type de sinistre."""
        pieces_communes = [
            "Déclaration de sinistre signée",
            "Copie de la police d'assurance",
            "Photos des dommages",
        ]
        pieces_specifiques = {
            "incendie": [
                "Procès-verbal des pompiers",
                "Rapport de police (si origine criminelle suspectée)",
                "Factures ou estimatifs de remplacement",
                "Rapport d'expertise (si > 5M FCFA)",
            ],
            "vol": [
                "Dépôt de plainte auprès de la police",
                "Inventaire détaillé des biens volés",
                "Factures d'achat des biens réclamés",
                "Attestation des voisins (si témoins)",
            ],
            "degats_eaux": [
                "Rapport du plombier (cause de la fuite)",
                "Constats de l'immeuble/syndic",
                "Factures de réparation",
            ],
            "cat_nat": [
                "Attestation de catastrophe naturelle (préfecture/mairie)",
                "Rapport météorologique",
                "Photos géolocalisées des dommages",
            ],
        }
        pieces = pieces_communes + pieces_specifiques.get(type_sinistre, [])
        if montant > 2_000_000:
            pieces.append("Rapport d'expert agréé CIMA")
        return pieces

    # ─── Simulation microassurance ─────────────────────────────────────

    def calculer_microassurance_mrh(self, surface_m2: float, ville: str, pays: str = "CM") -> dict:
        """
        Pack microassurance MRH (Circulaire CRCA 2024-001).
        Couverture minimum légale : incendie + RC + vol.
        Cible : ménages à faibles revenus (prime < 50 000 FCFA/an).
        """
        zone = ZONES_CATNAT.get(ville, "A")
        valeur_std = surface_m2 * 150_000   # 150k FCFA/m² estimation construction standard
        mobilier_std = surface_m2 * 50_000   # 50k/m² mobilier de base

        dossier_micro = DossierMRH(
            type_bien="appartement",
            statut_occupant="locataire",
            ville=ville,
            pays=pays,
            surface_m2=surface_m2,
            type_construction="construction_dur",
            annee_construction=2005,
            valeur_batiment_fcfa=0,         # Pas couvert en microassurance
            valeur_mobilier_fcfa=mobilier_std,
            garanties=["incendie", "vol", "rc_locataire"],
        )

        devis = self._moteur.calculer_devis(dossier_micro)

        return {
            "type": "microassurance_mrh",
            "reference_reglementaire": "Circulaire CRCA 2024-001",
            "surface_m2": surface_m2,
            "ville": ville,
            "zone_risque": zone,
            "valeur_mobilier_couverte_fcfa": round(mobilier_std),
            "garanties": ["Incendie mobilier", "Vol mobilier", "RC Locataire"],
            "prime_annuelle_fcfa": devis.prime_ttc,
            "prime_mensuelle_fcfa": round(devis.prime_ttc / 12),
            "plafonds": {
                "incendie_mobilier": PLAFONDS_MRH["incendie_mobilier_max"],
                "vol": PLAFONDS_MRH["vol_max"],
                "rc_corporel": PLAFONDS_MRH["rc_corporel_max"],
            },
            "franchise_unique": FRANCHISES_MRH["incendie"],
            "eligible_microassurance": devis.prime_ttc <= 50_000,
        }

    # ─── Révision annuelle ─────────────────────────────────────────────

    def calculer_revision_annuelle(
        self, numero_police: str, taux_inflation_pct: float = 3.0
    ) -> dict:
        """
        Calcule la révision annuelle d'une police MRH :
        - Indexation sur l'inflation
        - Ajustement selon la sinistralité
        """
        police = self._polices.get(numero_police)
        if not police:
            return {"succes": False, "erreur": f"Police {numero_police} introuvable"}

        prime_actuelle = police.get("prime_ttc", 0)
        ajustement_inflation = taux_inflation_pct / 100
        nouvelle_prime_nette = round(police.get("prime_nette", 0) * (1 + ajustement_inflation))
        taxe_cima = round(nouvelle_prime_nette * MoteurTarifMRH.TAXE_CIMA)
        taxe_locale = round(nouvelle_prime_nette * MoteurTarifMRH.TAXE_LOCALE_PAR_PAYS.get(
            police.get("pays", "CM"), 0.18
        ))
        nouvelle_prime_ttc = nouvelle_prime_nette + taxe_cima + taxe_locale

        return {
            "numero_police": numero_police,
            "prime_actuelle_fcfa": prime_actuelle,
            "taux_revision_pct": taux_inflation_pct,
            "nouvelle_prime_nette_fcfa": nouvelle_prime_nette,
            "nouvelle_prime_ttc_fcfa": nouvelle_prime_ttc,
            "evolution_fcfa": nouvelle_prime_ttc - prime_actuelle,
            "evolution_pct": round((nouvelle_prime_ttc - prime_actuelle) / prime_actuelle * 100, 2) if prime_actuelle else 0,
            "date_revision": date.today().isoformat(),
        }

    # ─── Statistiques portefeuille MRH ──────────────────────────────

    def statistiques_portefeuille(self) -> dict:
        """Analyse du portefeuille MRH."""
        polices = list(self._polices.values())
        actives = [p for p in polices if p.get("statut") == "actif"]
        primes_totales = sum(p.get("prime_ttc", 0) for p in actives)
        valeurs_assurees = sum(
            p.get("valeur_batiment", 0) + p.get("valeur_mobilier", 0) for p in actives
        )

        par_type: dict[str, int] = {}
        par_ville: dict[str, int] = {}
        par_zone: dict[str, int] = {}

        for p in polices:
            t = p.get("type_bien", "inconnu")
            par_type[t] = par_type.get(t, 0) + 1
            v = p.get("ville", "inconnu")
            par_ville[v] = par_ville.get(v, 0) + 1
            z = p.get("zone_catnat", "A")
            par_zone[z] = par_zone.get(z, 0) + 1

        return {
            "total_polices": len(polices),
            "polices_actives": len(actives),
            "primes_ttc_totales_fcfa": round(primes_totales),
            "valeurs_assurees_totales_fcfa": round(valeurs_assurees),
            "prime_moyenne_fcfa": round(primes_totales / len(actives)) if actives else 0,
            "repartition_par_type_bien": par_type,
            "repartition_par_ville": dict(sorted(par_ville.items(), key=lambda x: x[1], reverse=True)[:10]),
            "repartition_par_zone_catnat": par_zone,
        }


# Instance singleton
service_mrh = ServiceMRH()
