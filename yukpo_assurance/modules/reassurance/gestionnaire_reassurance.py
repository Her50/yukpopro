"""
YukpoAssurance — Module Réassurance (CIMA complet)
Art. 308-310 Code CIMA + Livre VI (Art. 700-710)

Types de traités implémentés :
1. Quote-part (proportionnel) — cession d'un % fixe sur toutes les affaires
2. Excédent de plein (proportionnel) — cession au-delà du plein de conservation
3. Stop-loss (non-proportionnel) — protection du ratio sinistres/primes
4. XL par risque — Excess of Loss par risque (non-proportionnel)
5. XL par événement — catastrophe XL (non-proportionnel)
6. Facultative — réassurance au cas par cas

Fonctions :
- Calcul des cessions et rétrocessions
- Calcul des primes de réassurance
- Calcul des sinistres récupérables
- Analyse PML (Probable Maximum Loss)
- Suivi des comptes de réassurance (bordereau)
- Conformité CIMA Art. 308 (max 50% cession)
- Génération états réglementaires (état C12 — réassurance)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from core.ia_client import ModeIA, ia_client
from core.orchestrateur import ContexteRequete, DomaineMétier, orchestrateur

logger = logging.getLogger("yukpo_assurance.reassurance")


# ─── Types de traités ──────────────────────────────────────────────────────────

TYPES_TRAITES = {
    "quote_part":           "Traité Quote-Part (proportionnel)",
    "excedent_plein":       "Traité Excédent de Plein (proportionnel)",
    "stop_loss":            "Traité Stop-Loss (non-proportionnel)",
    "xl_risque":            "XL par Risque (non-proportionnel)",
    "xl_evenement":         "XL par Événement / Catastrophe (non-proportionnel)",
    "facultative":          "Réassurance Facultative",
}

# Réassureurs agréés zone CIMA (liste indicative — à compléter via BDD)
REASSUREURS_AGREES_CIMA = [
    {"nom": "Africa Re (African Reinsurance Corporation)", "pays": "Nigeria", "notation": "A-"},
    {"nom": "CICA-Re (Compagnie Commune de Réassurance des États membres de la CIMA)", "pays": "Togo", "notation": "BBB+"},
    {"nom": "ZEP-Re (PTA Reinsurance Company)", "pays": "Kenya", "notation": "BBB+"},
    {"nom": "SCR (Société Centrale de Réassurance)", "pays": "Maroc", "notation": "BBB"},
    {"nom": "Munich Re", "pays": "Allemagne", "notation": "AA-"},
    {"nom": "Swiss Re", "pays": "Suisse", "notation": "AA-"},
    {"nom": "Hannover Re", "pays": "Allemagne", "notation": "AA-"},
    {"nom": "Scor", "pays": "France", "notation": "A+"},
    {"nom": "Gen Re", "pays": "USA", "notation": "AA+"},
]

# Plafonds réglementaires CIMA
PLAFOND_CESSION_LEGALE_PCT = 50.0   # Art. 308 : max 50% de cession
PRIORITE_REASSUREUR_AGREE = True    # Art. 308 : priorité aux réassureurs agréés CIMA


# ─── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class TraiteReassurance:
    """Définition d'un traité de réassurance."""
    id_traite: str
    nom_traite: str
    type_traite: str                    # Voir TYPES_TRAITES
    reassureur: str
    branche: str                        # "auto" | "vie" | "ird" | "rc" | "transport" | "mrh" | "all"
    date_debut: str
    date_fin: str

    # Proportionnel (quote-part / excédent de plein)
    taux_cession_pct: float = 0.0       # % cédé au réassureur (quote-part)
    commission_reassureur_pct: float = 0.0  # Commission de réassurance reçue
    plein_conservation_fcfa: float = 0.0   # Plein de conservation (excédent de plein)
    nb_pleins_traite: int = 0             # Nombre de pleins couverts (excédent)

    # Non-proportionnel (stop-loss / XL)
    priorite_cedante_fcfa: float = 0.0  # Franchise / priorité à charge de la cédante
    portee_xl_fcfa: float = 0.0         # Portée de la couverture (limite XL)
    ratio_stop_loss_priorite_pct: float = 0.0  # Seuil S/P déclencheur stop-loss
    ratio_stop_loss_limite_pct: float = 0.0    # Plafond S/P couvert
    prime_xl_pct: float = 0.0           # Prime XL en % des primes cédantes

    # Commun
    statut: str = "actif"               # "actif" | "expiré" | "suspendu"
    notation_reassureur: str = ""
    commentaires: str = ""


@dataclass
class LigneCessionReassurance:
    """Ligne de cession individuelle (bordereau de réassurance)."""
    id_police: str
    branche: str
    prime_brute_fcfa: float
    prime_cedee_fcfa: float
    commission_recue_fcfa: float
    plafond_couvert_fcfa: float
    date_effet: str
    date_echeance: str
    id_traite: str
    type_traite: str


@dataclass
class SinistreRecuperable:
    """Sinistre récupérable sur réassurance."""
    numero_sinistre: str
    id_police: str
    id_traite: str
    montant_sinistre_total_fcfa: float
    part_cedante_fcfa: float            # À charge cédante
    part_recuperable_fcfa: float        # Récupérable sur réassureur
    statut_recouvrement: str            # "a_recuperer" | "recupere" | "litige"
    date_declaration: str


# ─── Gestionnaire Réassurance ─────────────────────────────────────────────────

class GestionnaireReassurance:
    """
    Gestionnaire complet de réassurance YukpoAssurance.
    Conforme CIMA Art. 308-310 et Livre VI Art. 700-710.
    """

    def __init__(self):
        self._traites: dict[str, TraiteReassurance] = {}
        self._cessions: list[LigneCessionReassurance] = []
        self._sinistres_recuperables: list[SinistreRecuperable] = []
        self._initialiser_traites_exemple()

    def _initialiser_traites_exemple(self) -> None:
        """Initialise des traités de référence (modèles pré-configurés)."""
        # Traité quote-part auto (exemple standard zone CIMA)
        self._traites["QP-AUTO-2024"] = TraiteReassurance(
            id_traite="QP-AUTO-2024",
            nom_traite="Quote-Part Auto 2024",
            type_traite="quote_part",
            reassureur="Africa Re (African Reinsurance Corporation)",
            branche="auto",
            date_debut="2024-01-01",
            date_fin="2024-12-31",
            taux_cession_pct=30.0,
            commission_reassureur_pct=25.0,
            notation_reassureur="A-",
        )
        # Traité XL par risque IRD
        self._traites["XL-IRD-2024"] = TraiteReassurance(
            id_traite="XL-IRD-2024",
            nom_traite="XL par Risque IRD 2024",
            type_traite="xl_risque",
            reassureur="Munich Re",
            branche="ird",
            date_debut="2024-01-01",
            date_fin="2024-12-31",
            priorite_cedante_fcfa=20_000_000,
            portee_xl_fcfa=200_000_000,
            prime_xl_pct=2.50,
            notation_reassureur="AA-",
        )
        # Stop-loss toutes branches
        self._traites["SL-GLOBAL-2024"] = TraiteReassurance(
            id_traite="SL-GLOBAL-2024",
            nom_traite="Stop-Loss Global 2024",
            type_traite="stop_loss",
            reassureur="Swiss Re",
            branche="all",
            date_debut="2024-01-01",
            date_fin="2024-12-31",
            ratio_stop_loss_priorite_pct=80.0,
            ratio_stop_loss_limite_pct=110.0,
            prime_xl_pct=1.80,
            notation_reassureur="AA-",
        )

    # ─── Gestion des traités ──────────────────────────────────────────

    def creer_traite(self, traite: TraiteReassurance) -> dict:
        """
        Crée un nouveau traité de réassurance.
        Vérifie la conformité CIMA Art. 308 (taux de cession max 50%).
        """
        alertes = []

        # Vérification Art. 308 CIMA
        if traite.taux_cession_pct > PLAFOND_CESSION_LEGALE_PCT:
            return {
                "succes": False,
                "erreur": (
                    f"Taux de cession {traite.taux_cession_pct}% dépasse le plafond légal "
                    f"de {PLAFOND_CESSION_LEGALE_PCT}% (Art. 308 Code CIMA). "
                    f"Demander une dérogation à la CRCA."
                ),
            }

        # Vérification réassureur agréé CIMA
        reassureurs_noms = [r["nom"] for r in REASSUREURS_AGREES_CIMA]
        if traite.reassureur not in reassureurs_noms:
            alertes.append(
                f"⚠️ Réassureur '{traite.reassureur}' non trouvé dans la liste CIMA agréée. "
                f"Vérifier l'agrément CRCA avant placement (Art. 308 al.2)."
            )

        # Vérification cohérence commission (quote-part)
        if traite.type_traite == "quote_part":
            if traite.commission_reassureur_pct > traite.taux_cession_pct * 0.40:
                alertes.append(
                    f"Commission réassureur ({traite.commission_reassureur_pct}%) "
                    f"élevée par rapport au taux cédé ({traite.taux_cession_pct}%). "
                    f"Vérifier la négociation."
                )

        self._traites[traite.id_traite] = traite
        logger.info(f"[Réassurance] Traité {traite.id_traite} créé — {traite.type_traite} / {traite.reassureur}")

        return {
            "succes": True,
            "id_traite": traite.id_traite,
            "alertes": alertes,
            "message": f"Traité {traite.nom_traite} créé avec succès.",
        }

    def lister_traites(self, branche: Optional[str] = None, actifs_seulement: bool = True) -> list[dict]:
        """Liste les traités actifs, optionnellement filtrés par branche."""
        traites = list(self._traites.values())
        if actifs_seulement:
            traites = [t for t in traites if t.statut == "actif"]
        if branche:
            traites = [t for t in traites if t.branche in (branche, "all")]
        return [self._traite_to_dict(t) for t in traites]

    def _traite_to_dict(self, t: TraiteReassurance) -> dict:
        return {
            "id_traite": t.id_traite,
            "nom_traite": t.nom_traite,
            "type_traite": t.type_traite,
            "type_traite_libelle": TYPES_TRAITES.get(t.type_traite, t.type_traite),
            "reassureur": t.reassureur,
            "notation": t.notation_reassureur,
            "branche": t.branche,
            "date_debut": t.date_debut,
            "date_fin": t.date_fin,
            "taux_cession_pct": t.taux_cession_pct,
            "commission_pct": t.commission_reassureur_pct,
            "plein_conservation_fcfa": t.plein_conservation_fcfa,
            "priorite_fcfa": t.priorite_cedante_fcfa,
            "portee_fcfa": t.portee_xl_fcfa,
            "statut": t.statut,
        }

    # ─── Calcul de cession par traité ────────────────────────────────

    def calculer_cession_quote_part(
        self,
        id_traite: str,
        prime_brute_fcfa: float,
        capital_assure_fcfa: float,
        sinistre_fcfa: float = 0.0,
    ) -> dict:
        """
        Calcul de cession pour un traité quote-part.
        Formules :
        - Prime cédée = Prime brute × taux_cession
        - Commission reçue = Prime cédée × commission_reassureur
        - Part sinistre réassureur = Sinistre × taux_cession
        """
        traite = self._traites.get(id_traite)
        if not traite or traite.type_traite != "quote_part":
            return {"erreur": f"Traité {id_traite} non trouvé ou type incorrect"}

        taux = traite.taux_cession_pct / 100
        prime_cedee = round(prime_brute_fcfa * taux)
        prime_conservee = round(prime_brute_fcfa * (1 - taux))
        commission = round(prime_cedee * traite.commission_reassureur_pct / 100)
        capital_cede = round(capital_assure_fcfa * taux)
        capital_conserve = capital_assure_fcfa - capital_cede

        # Sinistre récupérable
        recuperation_sinistre = round(sinistre_fcfa * taux) if sinistre_fcfa > 0 else 0
        sinistre_charge_cedante = sinistre_fcfa - recuperation_sinistre

        # Vérification Art. 308
        taux_cession_global = self._calculer_taux_cession_global()
        alerte_308 = None
        if taux_cession_global > PLAFOND_CESSION_LEGALE_PCT:
            alerte_308 = (
                f"⚠️ Art. 308 CIMA : taux de cession global {taux_cession_global:.1f}% "
                f"dépasse la limite légale de {PLAFOND_CESSION_LEGALE_PCT}%."
            )

        return {
            "traite": traite.nom_traite,
            "type": "quote_part",
            "reassureur": traite.reassureur,
            "taux_cession_pct": traite.taux_cession_pct,
            "prime_brute_fcfa": round(prime_brute_fcfa),
            "prime_cedee_fcfa": prime_cedee,
            "prime_conservee_fcfa": prime_conservee,
            "commission_recue_fcfa": commission,
            "prime_nette_cedante": prime_conservee + commission,
            "capital_assure_fcfa": round(capital_assure_fcfa),
            "capital_cede_fcfa": capital_cede,
            "capital_conserve_cedante_fcfa": capital_conserve,
            "sinistre_total_fcfa": round(sinistre_fcfa),
            "recuperation_reassureur_fcfa": recuperation_sinistre,
            "sinistre_charge_cedante_fcfa": round(sinistre_charge_cedante),
            "article_cima": "Art. 308 Code CIMA",
            "alerte_art_308": alerte_308,
        }

    def calculer_cession_excedent_plein(
        self,
        id_traite: str,
        prime_brute_fcfa: float,
        capital_assure_fcfa: float,
        sinistre_fcfa: float = 0.0,
    ) -> dict:
        """
        Calcul de cession pour un traité excédent de plein.
        - Si capital ≤ plein_conservation : aucune cession
        - Si capital > plein : cession du surplus jusqu'à (nb_pleins × plein_conservation)
        """
        traite = self._traites.get(id_traite)
        if not traite or traite.type_traite != "excedent_plein":
            return {"erreur": f"Traité {id_traite} non trouvé ou type incorrect"}

        plein = traite.plein_conservation_fcfa
        capacite_totale = plein * (1 + traite.nb_pleins_traite)

        if capital_assure_fcfa <= plein:
            # Tout en conservation — pas de cession
            return {
                "traite": traite.nom_traite,
                "type": "excedent_plein",
                "capital_assure_fcfa": round(capital_assure_fcfa),
                "plein_conservation_fcfa": round(plein),
                "en_conservation": True,
                "prime_cedee_fcfa": 0,
                "capital_cede_fcfa": 0,
                "taux_cession_pct": 0.0,
                "recuperation_reassureur_fcfa": 0,
                "message": "Capital ≤ plein de conservation — affaire en 100% conservation.",
            }

        # Calcul de la part cédée
        capital_cede = min(capital_assure_fcfa - plein, plein * traite.nb_pleins_traite)
        capital_cede = min(capital_cede, capacite_totale - plein)
        capital_au_dela_capacite = max(0, capital_assure_fcfa - capacite_totale)

        taux_cession = capital_cede / capital_assure_fcfa
        prime_cedee = round(prime_brute_fcfa * taux_cession)
        commission = round(prime_cedee * traite.commission_reassureur_pct / 100)

        # Sinistre récupérable (au prorata)
        recuperation = round(sinistre_fcfa * taux_cession) if sinistre_fcfa > 0 else 0
        # Mais limité au capital cédé
        recuperation = min(recuperation, capital_cede)

        return {
            "traite": traite.nom_traite,
            "type": "excedent_plein",
            "reassureur": traite.reassureur,
            "capital_assure_fcfa": round(capital_assure_fcfa),
            "plein_conservation_fcfa": round(plein),
            "nb_pleins_traite": traite.nb_pleins_traite,
            "capacite_totale_fcfa": round(capacite_totale),
            "capital_conserve_cedante_fcfa": round(capital_assure_fcfa - capital_cede),
            "capital_cede_fcfa": round(capital_cede),
            "capital_non_couvert_fcfa": round(capital_au_dela_capacite),
            "taux_cession_pct": round(taux_cession * 100, 2),
            "prime_brute_fcfa": round(prime_brute_fcfa),
            "prime_cedee_fcfa": prime_cedee,
            "commission_recue_fcfa": commission,
            "sinistre_fcfa": round(sinistre_fcfa),
            "recuperation_reassureur_fcfa": recuperation,
            "sinistre_charge_cedante_fcfa": round(sinistre_fcfa - recuperation),
            "alerte_depassement": (
                f"⚠️ Capital {capital_assure_fcfa:,.0f} FCFA dépasse la capacité du traité "
                f"({capacite_totale:,.0f} FCFA). "
                f"Risque non couvert à hauteur de {capital_au_dela_capacite:,.0f} FCFA — "
                f"placement facultatif requis."
            ) if capital_au_dela_capacite > 0 else None,
        }

    def calculer_cession_xl_risque(
        self,
        id_traite: str,
        sinistre_fcfa: float,
        prime_assiette_fcfa: float,
    ) -> dict:
        """
        Calcul récupération XL par risque.
        Formule :
        - Si sinistre < priorité : 100% à charge cédante
        - Si priorité < sinistre < priorité + portée : (sinistre - priorité) récupérable
        - Si sinistre > priorité + portée : portée max récupérable
        """
        traite = self._traites.get(id_traite)
        if not traite or traite.type_traite not in ("xl_risque", "xl_evenement"):
            return {"erreur": f"Traité {id_traite} non trouvé ou type incorrect"}

        priorite = traite.priorite_cedante_fcfa
        portee = traite.portee_xl_fcfa
        limite_xl = priorite + portee

        # Prime XL à payer au réassureur
        prime_xl = round(prime_assiette_fcfa * traite.prime_xl_pct / 100)

        if sinistre_fcfa <= priorite:
            recuperation = 0.0
            charge_cedante = sinistre_fcfa
            statut = "en_franchise"
        elif sinistre_fcfa <= limite_xl:
            recuperation = sinistre_fcfa - priorite
            charge_cedante = priorite
            statut = "dans_portee"
        else:
            recuperation = portee
            charge_cedante = sinistre_fcfa - portee
            statut = "au_dela_portee"

        return {
            "traite": traite.nom_traite,
            "type": f"xl_{traite.type_traite.replace('xl_', '')}",
            "reassureur": traite.reassureur,
            "sinistre_total_fcfa": round(sinistre_fcfa),
            "priorite_cedante_fcfa": round(priorite),
            "portee_xl_fcfa": round(portee),
            "limite_xl_fcfa": round(limite_xl),
            "recuperation_reassureur_fcfa": round(recuperation),
            "charge_cedante_fcfa": round(charge_cedante),
            "prime_xl_fcfa": prime_xl,
            "statut_declenchement": statut,
            "declenche": recuperation > 0,
            "taux_recuperation_pct": round(recuperation / sinistre_fcfa * 100, 2) if sinistre_fcfa > 0 else 0,
        }

    def calculer_cession_stop_loss(
        self,
        id_traite: str,
        sinistres_payes_fcfa: float,
        primes_nettes_exercice_fcfa: float,
    ) -> dict:
        """
        Calcul récupération Stop-Loss.
        Déclenché quand le ratio S/P dépasse la priorité.
        Formule :
        - Ratio S/P = sinistres_payes / primes_nettes
        - Si ratio > priorité_pct : récupération = (ratio - priorité) × primes, limité à (limite - priorité) × primes
        """
        traite = self._traites.get(id_traite)
        if not traite or traite.type_traite != "stop_loss":
            return {"erreur": f"Traité {id_traite} non trouvé ou type incorrect"}

        priorite_pct = traite.ratio_stop_loss_priorite_pct / 100
        limite_pct = traite.ratio_stop_loss_limite_pct / 100
        prime_xl = round(primes_nettes_exercice_fcfa * traite.prime_xl_pct / 100)

        if primes_nettes_exercice_fcfa <= 0:
            return {"erreur": "Primes nettes nulles — calcul stop-loss impossible"}

        ratio_sp = sinistres_payes_fcfa / primes_nettes_exercice_fcfa

        if ratio_sp <= priorite_pct:
            recuperation = 0
            statut = "non_declenche"
        elif ratio_sp <= limite_pct:
            recuperation = round((ratio_sp - priorite_pct) * primes_nettes_exercice_fcfa)
            statut = "declenche_dans_portee"
        else:
            recuperation = round((limite_pct - priorite_pct) * primes_nettes_exercice_fcfa)
            statut = "declenche_au_plafond"

        charge_residuelle = sinistres_payes_fcfa - recuperation

        return {
            "traite": traite.nom_traite,
            "type": "stop_loss",
            "reassureur": traite.reassureur,
            "sinistres_payes_fcfa": round(sinistres_payes_fcfa),
            "primes_nettes_fcfa": round(primes_nettes_exercice_fcfa),
            "ratio_sp_reel_pct": round(ratio_sp * 100, 2),
            "ratio_priorite_pct": traite.ratio_stop_loss_priorite_pct,
            "ratio_limite_pct": traite.ratio_stop_loss_limite_pct,
            "declenche": recuperation > 0,
            "recuperation_reassureur_fcfa": recuperation,
            "charge_residuelle_cedante_fcfa": round(charge_residuelle),
            "prime_xl_fcfa": prime_xl,
            "statut": statut,
            "protection_annuelle_fcfa": round(
                (limite_pct - priorite_pct) * primes_nettes_exercice_fcfa
            ),
        }

    # ─── Analyse PML ──────────────────────────────────────────────────

    def analyser_pml(
        self,
        portefeuille: list[dict],
        scenario: str = "standard",
    ) -> dict:
        """
        Analyse du PML (Probable Maximum Loss) du portefeuille.
        Utilisé pour dimensionner les couvertures XL catastrophe.

        Scénarios :
        - "standard" : 1 sinistre majeur sur 100 ans (probabilité 1%)
        - "moderé" : 1 sinistre majeur sur 25 ans (4%)
        - "extreme" : 1 sinistre majeur sur 250 ans (0.4%)

        Paramètre portefeuille :
        [{"branche": "auto", "capital_assure_fcfa": 5000000, "ville": "Douala"}, ...]
        """
        if not portefeuille:
            return {"erreur": "Portefeuille vide"}

        total_capitaux = sum(p.get("capital_assure_fcfa", 0) for p in portefeuille)

        # Taux PML par scénario et branche (% du total capitaux assurés exposés)
        TAUX_PML: dict[str, dict[str, float]] = {
            "standard": {
                "auto":      0.0050,   # 0,5% (sinistres dispersés)
                "ird":       0.0150,   # 1,5% (incendie : concentration possible)
                "mrh":       0.0200,
                "transport": 0.0080,
                "vie":       0.0030,
                "rc":        0.0100,
                "default":   0.0100,
            },
            "moderé": {
                "auto":      0.0020, "ird": 0.0080, "mrh": 0.0100,
                "transport": 0.0040, "vie": 0.0015, "rc": 0.0050, "default": 0.0050,
            },
            "extreme": {
                "auto":      0.0150, "ird": 0.0500, "mrh": 0.0600,
                "transport": 0.0200, "vie": 0.0100, "rc": 0.0300, "default": 0.0300,
            },
        }

        taux_scenario = TAUX_PML.get(scenario, TAUX_PML["standard"])

        # PML par branche
        pml_par_branche: dict[str, float] = {}
        for p in portefeuille:
            b = p.get("branche", "default")
            cap = float(p.get("capital_assure_fcfa", 0))
            taux = taux_scenario.get(b, taux_scenario["default"])
            pml_par_branche[b] = pml_par_branche.get(b, 0) + cap * taux

        pml_total = sum(pml_par_branche.values())

        # Besoins de couverture XL catastrophe
        xl_cat_recommande = {
            "priorite_recommandee_fcfa": round(pml_total * 0.20),   # 20% auto-conservation
            "portee_recommandee_fcfa": round(pml_total * 0.80),      # 80% couvert
            "capacite_necessaire_fcfa": round(pml_total),
        }

        # Vérification couverture existante
        couverture_xl_existante = sum(
            t.portee_xl_fcfa for t in self._traites.values()
            if t.type_traite in ("xl_evenement", "xl_risque") and t.statut == "actif"
        )
        deficit_couverture = max(0, pml_total - couverture_xl_existante)

        return {
            "scenario": scenario,
            "total_capitaux_assures_fcfa": round(total_capitaux),
            "pml_total_fcfa": round(pml_total),
            "pml_par_branche": {b: round(v) for b, v in pml_par_branche.items()},
            "xl_cat_recommande": xl_cat_recommande,
            "couverture_xl_existante_fcfa": round(couverture_xl_existante),
            "deficit_couverture_fcfa": round(deficit_couverture),
            "couverture_adequate": deficit_couverture == 0,
            "alerte": (
                f"⚠️ Déficit de couverture XL catastrophe : {deficit_couverture:,.0f} FCFA. "
                f"Renforcer la couverture XL événement pour le scénario {scenario}."
            ) if deficit_couverture > 0 else None,
        }

    # ─── Bordereau de cession ─────────────────────────────────────────

    def generer_bordereau_cession(
        self,
        periode_debut: str,
        periode_fin: str,
        branche: Optional[str] = None,
    ) -> dict:
        """
        Génère le bordereau de cession réassurance pour une période.
        Utilisé pour la réconciliation comptable avec les réassureurs.
        """
        cessions = [
            c for c in self._cessions
            if c.date_effet >= periode_debut and c.date_echeance <= periode_fin
            and (branche is None or c.branche == branche)
        ]

        totaux: dict[str, float] = {
            "primes_brutes": 0, "primes_cedees": 0,
            "commissions_recues": 0, "plafonds_couverts": 0,
        }
        par_traite: dict[str, dict] = {}

        for c in cessions:
            totaux["primes_brutes"] += c.prime_brute_fcfa
            totaux["primes_cedees"] += c.prime_cedee_fcfa
            totaux["commissions_recues"] += c.commission_recue_fcfa
            totaux["plafonds_couverts"] += c.plafond_couvert_fcfa

            traite_id = c.id_traite
            if traite_id not in par_traite:
                traite = self._traites.get(traite_id)
                par_traite[traite_id] = {
                    "traite": traite.nom_traite if traite else traite_id,
                    "reassureur": traite.reassureur if traite else "inconnu",
                    "nb_polices": 0, "primes_cedees": 0, "commissions": 0,
                }
            par_traite[traite_id]["nb_polices"] += 1
            par_traite[traite_id]["primes_cedees"] += c.prime_cedee_fcfa
            par_traite[traite_id]["commissions"] += c.commission_recue_fcfa

        taux_cession_global = (
            round(totaux["primes_cedees"] / totaux["primes_brutes"] * 100, 2)
            if totaux["primes_brutes"] > 0 else 0
        )

        alerte_308 = None
        if taux_cession_global > PLAFOND_CESSION_LEGALE_PCT:
            alerte_308 = (
                f"🚨 Art. 308 CIMA : taux de cession global {taux_cession_global}% "
                f"dépasse la limite légale de 50%. Action requise."
            )

        return {
            "titre": "Bordereau de Cession Réassurance",
            "base_reglementaire": "Art. 308-310 Code CIMA",
            "periode": f"{periode_debut} → {periode_fin}",
            "branche": branche or "toutes branches",
            "nb_lignes": len(cessions),
            "totaux": {k: round(v) for k, v in totaux.items()},
            "taux_cession_global_pct": taux_cession_global,
            "par_traite": par_traite,
            "alerte_art_308": alerte_308,
            "genere_le": datetime.now().isoformat(),
        }

    def enregistrer_cession(self, cession: LigneCessionReassurance) -> None:
        """Enregistre une ligne de cession dans le bordereau."""
        self._cessions.append(cession)

    # ─── Sinistres récupérables ───────────────────────────────────────

    def calculer_sinistres_recuperables_total(self) -> dict:
        """Calcule le total des sinistres récupérables sur réassureurs (bilan actif)."""
        a_recuperer = [
            s for s in self._sinistres_recuperables
            if s.statut_recouvrement == "a_recuperer"
        ]
        recuperes = [
            s for s in self._sinistres_recuperables
            if s.statut_recouvrement == "recupere"
        ]
        litige = [
            s for s in self._sinistres_recuperables
            if s.statut_recouvrement == "litige"
        ]

        total_recuperable = sum(s.part_recuperable_fcfa for s in a_recuperer)
        total_recupere = sum(s.part_recuperable_fcfa for s in recuperes)
        total_litige = sum(s.part_recuperable_fcfa for s in litige)

        return {
            "sinistres_a_recuperer": {
                "nb": len(a_recuperer),
                "montant_fcfa": round(total_recuperable),
            },
            "sinistres_recuperes": {
                "nb": len(recuperes),
                "montant_fcfa": round(total_recupere),
            },
            "sinistres_en_litige": {
                "nb": len(litige),
                "montant_fcfa": round(total_litige),
            },
            "total_creance_reassureurs_fcfa": round(total_recuperable + total_litige),
            "note": "Créances réassureurs à inscrire à l'actif du bilan (poste 25 PCSA).",
        }

    # ─── Conformité CIMA Art. 308 ─────────────────────────────────────

    def _calculer_taux_cession_global(self) -> float:
        """Calcule le taux de cession global sur tous les traités actifs."""
        taux_total = sum(
            t.taux_cession_pct
            for t in self._traites.values()
            if t.type_traite == "quote_part" and t.statut == "actif"
        )
        return min(taux_total, 100.0)

    def verifier_conformite_art308(self) -> dict:
        """
        Vérifie la conformité au plafond de cession CIMA Art. 308.
        Retourne un rapport de conformité complet.
        """
        taux_global = self._calculer_taux_cession_global()
        conforme = taux_global <= PLAFOND_CESSION_LEGALE_PCT

        traites_actifs = [t for t in self._traites.values() if t.statut == "actif"]
        reassureurs_agrees = [r["nom"] for r in REASSUREURS_AGREES_CIMA]

        traites_non_agrees = [
            t.nom_traite for t in traites_actifs
            if t.reassureur not in reassureurs_agrees
        ]

        return {
            "article": "Art. 308 Code CIMA",
            "taux_cession_global_pct": round(taux_global, 2),
            "plafond_legal_pct": PLAFOND_CESSION_LEGALE_PCT,
            "conforme": conforme,
            "nb_traites_actifs": len(traites_actifs),
            "reassureurs_non_agrees": traites_non_agrees,
            "alerte": None if conforme else (
                f"🚨 Taux de cession global ({taux_global:.1f}%) dépasse le plafond légal "
                f"de {PLAFOND_CESSION_LEGALE_PCT}% (Art. 308 CIMA). "
                f"Informer la CRCA et réduire les cessions."
            ),
            "recommandation_reassureurs_agrees": (
                f"Privilégier Africa Re, CICA-Re et ZEP-Re conformément à Art. 308 al.2."
            ),
        }

    # ─── Rapport État C12 (CRCA) ──────────────────────────────────────

    def generer_etat_c12(
        self,
        exercice: str,
        primes_brutes_par_branche: dict[str, float],
        sinistres_par_branche: dict[str, float],
    ) -> dict:
        """
        Génère les données pour l'État C12 (Réassurance acceptée et cédée).
        Obligatoire pour le reporting CRCA annuel.
        """
        traites = list(self._traites.values())
        tableau_c12 = []

        for branche, primes in primes_brutes_par_branche.items():
            traites_branche = [t for t in traites if t.branche in (branche, "all") and t.statut == "actif"]

            primes_cedees = 0.0
            commissions = 0.0
            recuperations = 0.0
            sinistres = sinistres_par_branche.get(branche, 0)

            for t in traites_branche:
                if t.type_traite == "quote_part":
                    pc = primes * t.taux_cession_pct / 100
                    primes_cedees += pc
                    commissions += pc * t.commission_reassureur_pct / 100
                    recuperations += sinistres * t.taux_cession_pct / 100
                elif t.type_traite == "excedent_plein" and t.plein_conservation_fcfa > 0:
                    # Estimation 20% des affaires au-delà du plein (statistique)
                    primes_cedees += primes * 0.20 * (t.nb_pleins_traite / (t.nb_pleins_traite + 1))
                elif t.type_traite in ("xl_risque", "stop_loss"):
                    # Prime XL
                    primes_cedees += primes * t.prime_xl_pct / 100

            taux_cession_branche = round(primes_cedees / primes * 100, 2) if primes > 0 else 0

            tableau_c12.append({
                "branche": branche,
                "primes_brutes_fcfa": round(primes),
                "primes_cedees_fcfa": round(primes_cedees),
                "primes_nettes_cedantes_fcfa": round(primes - primes_cedees + commissions),
                "commissions_recues_fcfa": round(commissions),
                "sinistres_bruts_fcfa": round(sinistres),
                "recuperations_reassureurs_fcfa": round(recuperations),
                "sinistres_nets_cedante_fcfa": round(sinistres - recuperations),
                "taux_cession_pct": taux_cession_branche,
            })

        totaux = {
            "primes_brutes": sum(r["primes_brutes_fcfa"] for r in tableau_c12),
            "primes_cedees": sum(r["primes_cedees_fcfa"] for r in tableau_c12),
            "commissions": sum(r["commissions_recues_fcfa"] for r in tableau_c12),
            "sinistres_bruts": sum(r["sinistres_bruts_fcfa"] for r in tableau_c12),
            "recuperations": sum(r["recuperations_reassureurs_fcfa"] for r in tableau_c12),
        }
        taux_global = round(
            totaux["primes_cedees"] / totaux["primes_brutes"] * 100, 2
        ) if totaux["primes_brutes"] > 0 else 0

        conformite = self.verifier_conformite_art308()

        return {
            "titre": "État C12 — Réassurance Acceptée et Cédée",
            "base_reglementaire": "Art. 308-310 Code CIMA",
            "exercice": exercice,
            "genere_le": datetime.now().isoformat(),
            "tableau": tableau_c12,
            "totaux": totaux,
            "taux_cession_global_pct": taux_global,
            "conformite_art308": conformite,
            "traites_en_vigueur": [self._traite_to_dict(t) for t in traites if t.statut == "actif"],
            "reassureurs_agrees_cima": REASSUREURS_AGREES_CIMA,
        }

    # ─── Analyse IA du programme de réassurance ───────────────────────

    async def analyser_programme_ia(self) -> dict:
        """
        Analyse IA du programme de réassurance global.
        Recommandations de structuration selon la taille du portefeuille et les risques.
        """
        traites_actifs = [self._traite_to_dict(t) for t in self._traites.values() if t.statut == "actif"]
        conformite = self.verifier_conformite_art308()

        prompt = f"""Tu es consultant réassurance expert zone CIMA.

Programme de réassurance actuel :
- Nombre de traités actifs : {len(traites_actifs)}
- Taux de cession global : {conformite['taux_cession_global_pct']}%
- Conforme Art. 308 : {conformite['conforme']}
- Traités : {[t['type_traite'] + ' / ' + t['reassureur'] for t in traites_actifs]}

Analyse le programme et propose :
1. Les forces et faiblesses du programme actuel
2. Les lacunes de couverture éventuelles
3. Une recommandation de structure optimale (types de traités, niveaux)
4. Les réassureurs agréés CIMA à privilégier (Africa Re, CICA-Re, ZEP-Re en priorité)
5. Le niveau de rétention recommandé selon les normes CIMA

Sois précis et pragmatique — contexte : compagnie d'assurance de taille moyenne en zone CIMA.
"""
        try:
            result = await orchestrateur.orchestrer(
                ContexteRequete(domaine=DomaineMétier.CIMA, texte=prompt)
            )
            analyse = result.reponse
        except Exception:
            analyse = "Analyse IA du programme de réassurance non disponible — vérifier la configuration IA."

        return {
            "programme_actuel": traites_actifs,
            "conformite_art308": conformite,
            "analyse_ia": analyse,
            "reassureurs_recommandes": REASSUREURS_AGREES_CIMA[:5],
        }


# Instance singleton
gestionnaire_reassurance = GestionnaireReassurance()
