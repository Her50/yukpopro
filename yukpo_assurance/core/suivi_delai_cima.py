"""
SuiviDelaiCima — Moteur de suivi des délais réglementaires CIMA par sinistre.

PRINCIPE :
  Chaque étape d'un workflow sinistre est horodatée à sa complétion.
  Le moteur vérifie automatiquement :
    1. Si l'étape suivante est autorisée (prérequis + délais respectés)
    2. Les délais restants avant dépassement légal
    3. Les alertes à envoyer (J-30, J-15, J-7, J+0 = dépassé)

DÉLAIS RÉGLEMENTAIRES CIMA IMPLÉMENTÉS :

  RC Auto (Art. 200-264 Code CIMA) :
    - Art. 205       : Déclaration → Accusé réception : 10 jours ouvrés
    - Art. 12-bis    : Déclaration → Offre indemnisation : 90 jours
    - Art. 12-bis    : Offre → Réponse client : 30 jours (fenêtre de réflexion)
    - Art. 12-ter    : Accord client → Paiement : 45 jours
    - Art. 12-quater : Dépassement → Intérêts moratoires 12%/an
    - Cahier des charges experts CIMA :
        Expertise mandatée → Rapport auto : 30 jours
        Expertise médicale mandatée → Rapport médical : 30 jours
        Rapport médical → Consolidation : variable (suivi mensuel)

  Maladie / Santé (Art. 76-86) :
    - Art. 76 : Dossier complet → Remboursement : 30 jours
    - BPC émis → Prise en charge effective : 0 jours (immédiat)
    - Hospitalisation programmée → Accord préalable : 5 jours
    - Hospitalisation urgence → Accord préalable : 1 jour (24h)

  Vie & Prévoyance (Art. 73-74) :
    - Art. 73 : Dossier complet → Règlement vie : 30 jours

  Non-Vie générale (MRH, Transport, RC Pro) :
    - Art. 12-bis : 90 jours offre indemnisation
    - Art. 12-ter : 45 jours paiement après accord

STRUCTURE DONNÉES :
  _timelines: dict[reference_sinistre → TimelineSinistre]
  _alertes_envoyees: dict[reference → set[str]]

PERSISTENCE : JSON fichier (compatible avec Redis en production)
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("yukpo_assurance.suivi_delai_cima")

# ─── Fichier de persistence ───────────────────────────────────────────────────
_FICHIER_TIMELINES = os.path.join(
    os.path.dirname(__file__), "..", "data", "timelines_sinistres.json"
)

# ─── Définition des étapes par branche ───────────────────────────────────────
# Chaque étape définit :
#   prerequis          : étape précédente obligatoire (None = première étape)
#   delai_max_depuis   : étape de référence pour le calcul du délai
#   delai_max_jours    : délai légal maximum en jours calendaires (None = pas de contrainte)
#   article_cima       : référence légale
#   concerne_externe   : type de partie externe concernée (None = interne uniquement)
#   seuil_alerte_jours : jours avant échéance pour alerter (liste décroissante)

_ETAPES_RC_AUTO: dict[str, dict] = {
    "declaration_recue": {
        "prerequis": None,
        "delai_max_depuis": None,
        "delai_max_jours": None,
        "article_cima": "Art. 205",
        "libelle": "Déclaration sinistre reçue",
        "concerne_externe": "assure",
    },
    "accuse_reception": {
        "prerequis": "declaration_recue",
        "delai_max_depuis": "declaration_recue",
        "delai_max_jours": 10,
        "article_cima": "Art. 205 CIMA",
        "libelle": "Accusé de réception envoyé à l'assuré",
        "concerne_externe": None,
        "seuil_alerte_jours": [3, 1],
    },
    "expertise_auto_mandatee": {
        "prerequis": "accuse_reception",
        "delai_max_depuis": None,  # Pas de délai légal — décision interne
        "delai_max_jours": None,
        "article_cima": None,
        "libelle": "Expert automobile mandaté",
        "concerne_externe": "expert_auto",
    },
    "rapport_expertise_auto_recu": {
        "prerequis": "expertise_auto_mandatee",
        "delai_max_depuis": "expertise_auto_mandatee",
        "delai_max_jours": 30,
        "article_cima": "Cahier des charges experts CIMA",
        "libelle": "Rapport d'expertise automobile reçu",
        "concerne_externe": "expert_auto",
        "seuil_alerte_jours": [15, 7, 3, 0],
    },
    "expertise_medicale_mandatee": {
        "prerequis": "accuse_reception",
        "delai_max_depuis": None,
        "delai_max_jours": None,
        "article_cima": "Art. 231 CIMA",
        "libelle": "Médecin expert mandaté",
        "concerne_externe": "medecin_expert",
    },
    "rapport_expertise_medicale_recu": {
        "prerequis": "expertise_medicale_mandatee",
        "delai_max_depuis": "expertise_medicale_mandatee",
        "delai_max_jours": 30,
        "article_cima": "Cahier des charges experts médicaux CIMA",
        "libelle": "Rapport d'expertise médicale reçu",
        "concerne_externe": "medecin_expert",
        "seuil_alerte_jours": [15, 7, 3, 0],
    },
    "consolidation_medicale": {
        "prerequis": "rapport_expertise_medicale_recu",
        "delai_max_depuis": None,  # Variable selon pathologie
        "delai_max_jours": None,
        "article_cima": "Art. 231 CIMA",
        "libelle": "Consolidation médicale confirmée (IPP définitif)",
        "concerne_externe": "medecin_expert",
    },
    "offre_indemnisation_envoyee": {
        "prerequis": "accuse_reception",
        # Délai absolu : 90j depuis DECLARATION (pas depuis prérequis direct)
        "delai_max_depuis": "declaration_recue",
        "delai_max_jours": 90,
        "article_cima": "Art. 12-bis Code CIMA",
        "libelle": "Offre d'indemnisation envoyée à l'assuré",
        "concerne_externe": "assure",
        "seuil_alerte_jours": [30, 15, 7, 3, 0],
        "critique": True,  # Dépassement = intérêts moratoires
    },
    "accord_client_recu": {
        "prerequis": "offre_indemnisation_envoyee",
        "delai_max_depuis": "offre_indemnisation_envoyee",
        "delai_max_jours": 30,  # Fenêtre de réflexion client Art. 12-bis
        "article_cima": "Art. 12-bis Code CIMA — délai de réflexion",
        "libelle": "Accord ou refus de l'assuré reçu",
        "concerne_externe": "assure",
        "seuil_alerte_jours": [15, 7, 3, 1],
        "note": "Après 30j sans réponse : relancer l'assuré avant clôture sans suite",
    },
    "paiement_effectue": {
        "prerequis": "accord_client_recu",
        "delai_max_depuis": "accord_client_recu",
        "delai_max_jours": 45,
        "article_cima": "Art. 12-ter Code CIMA",
        "libelle": "Règlement effectué",
        "concerne_externe": None,
        "seuil_alerte_jours": [15, 7, 3, 1, 0],
        "critique": True,
    },
    "subrogation_initiee": {
        "prerequis": "paiement_effectue",
        "delai_max_depuis": None,
        "delai_max_jours": None,
        "article_cima": "Art. 250 CIMA",
        "libelle": "Recours subrogatoire initié contre tiers responsable",
        "concerne_externe": "assureur_tiers",
    },
    "dossier_clos": {
        "prerequis": "paiement_effectue",
        "delai_max_depuis": None,
        "delai_max_jours": None,
        "article_cima": None,
        "libelle": "Dossier archivé et clôturé",
        "concerne_externe": None,
    },
}

_ETAPES_MALADIE: dict[str, dict] = {
    "declaration_recue": {
        "prerequis": None, "delai_max_depuis": None, "delai_max_jours": None,
        "libelle": "Déclaration / demande reçue", "concerne_externe": "assure",
    },
    "verification_contrat": {
        "prerequis": "declaration_recue",
        "delai_max_depuis": "declaration_recue", "delai_max_jours": 2,
        "article_cima": "Art. 76 CIMA",
        "libelle": "Vérification contrat et droits",
        "seuil_alerte_jours": [1],
    },
    "accord_prealable_hospitalisation": {
        "prerequis": "verification_contrat",
        "delai_max_depuis": "declaration_recue", "delai_max_jours": 5,
        "article_cima": "Art. 76-77 CIMA — accord préalable",
        "libelle": "Accord préalable hospitalisation émis",
        "concerne_externe": "assure",
        "seuil_alerte_jours": [2, 1, 0],
        "critique": True,
    },
    "accord_prealable_urgence": {
        "prerequis": "verification_contrat",
        "delai_max_depuis": "declaration_recue", "delai_max_jours": 1,
        "article_cima": "Art. 77 CIMA — urgence 24h",
        "libelle": "Accord préalable urgence émis (24h)",
        "concerne_externe": "assure",
        "seuil_alerte_jours": [0],
        "critique": True,
    },
    "bpc_emis": {
        "prerequis": "verification_contrat",
        "delai_max_depuis": None, "delai_max_jours": None,
        "libelle": "Bon de prise en charge émis",
        "concerne_externe": "prestataire_sante",
    },
    "pieces_medicales_recues": {
        "prerequis": "declaration_recue",
        "delai_max_depuis": None, "delai_max_jours": None,
        "libelle": "Pièces médicales complètes reçues",
        "concerne_externe": "assure",
    },
    "remboursement_effectue": {
        "prerequis": "pieces_medicales_recues",
        "delai_max_depuis": "pieces_medicales_recues", "delai_max_jours": 30,
        "article_cima": "Art. 76 Code CIMA",
        "libelle": "Remboursement versé à l'assuré",
        "concerne_externe": None,
        "seuil_alerte_jours": [15, 7, 3, 0],
        "critique": True,
    },
}

_ETAPES_VIE: dict[str, dict] = {
    "declaration_recue": {
        "prerequis": None, "delai_max_depuis": None, "delai_max_jours": None,
        "libelle": "Déclaration sinistre vie reçue", "concerne_externe": "assure",
    },
    "pieces_completes_recues": {
        "prerequis": "declaration_recue",
        "delai_max_depuis": None, "delai_max_jours": None,
        "libelle": "Dossier complet reçu (actes, certificats)",
        "concerne_externe": "assure",
    },
    "verification_beneficiaires": {
        "prerequis": "pieces_completes_recues",
        "delai_max_depuis": "pieces_completes_recues", "delai_max_jours": 5,
        "libelle": "Bénéficiaires vérifiés",
    },
    "paiement_effectue": {
        "prerequis": "verification_beneficiaires",
        "delai_max_depuis": "pieces_completes_recues", "delai_max_jours": 30,
        "article_cima": "Art. 73 Code CIMA",
        "libelle": "Prestations vie versées aux bénéficiaires",
        "seuil_alerte_jours": [15, 7, 3, 0],
        "critique": True,
    },
}

_ETAPES_NON_VIE_GENERAL: dict[str, dict] = {
    "declaration_recue": {"prerequis": None, "delai_max_depuis": None, "delai_max_jours": None, "libelle": "Déclaration reçue"},
    "accuse_reception": {"prerequis": "declaration_recue", "delai_max_depuis": "declaration_recue", "delai_max_jours": 10, "article_cima": "Art. 205 CIMA", "libelle": "Accusé réception envoyé", "seuil_alerte_jours": [3, 1]},
    "offre_indemnisation_envoyee": {"prerequis": "accuse_reception", "delai_max_depuis": "declaration_recue", "delai_max_jours": 90, "article_cima": "Art. 12-bis", "libelle": "Offre indemnisation envoyée", "seuil_alerte_jours": [30, 15, 7, 0], "critique": True},
    "accord_client_recu": {"prerequis": "offre_indemnisation_envoyee", "delai_max_depuis": "offre_indemnisation_envoyee", "delai_max_jours": 30, "libelle": "Accord client reçu", "seuil_alerte_jours": [15, 7, 1]},
    "paiement_effectue": {"prerequis": "accord_client_recu", "delai_max_depuis": "accord_client_recu", "delai_max_jours": 45, "article_cima": "Art. 12-ter", "libelle": "Règlement effectué", "seuil_alerte_jours": [15, 7, 0], "critique": True},
}

_ETAPES_PAR_BRANCHE: dict[str, dict] = {
    "rc_auto":   _ETAPES_RC_AUTO,
    "maladie":   _ETAPES_MALADIE,
    "sante":     _ETAPES_MALADIE,
    "vie":       _ETAPES_VIE,
    "prevoyance": _ETAPES_VIE,
    "mrh":       _ETAPES_NON_VIE_GENERAL,
    "transport": _ETAPES_NON_VIE_GENERAL,
    "rc_pro":    _ETAPES_NON_VIE_GENERAL,
    "accident":  _ETAPES_NON_VIE_GENERAL,
}

TAUX_MORATOIRE_ANNUEL = 0.12  # Art. 12-quater CIMA


@dataclass
class TimelineSinistre:
    reference:          str
    branche:            str
    user_id:            int
    # Dict étape → datetime ISO string de complétion
    etapes_completees:  dict[str, str] = field(default_factory=dict)
    # Alertes déjà envoyées (pour ne pas répéter)
    alertes_envoyees:   list[str]      = field(default_factory=list)
    # Métadonnées
    cree_le:            str            = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    mis_a_jour:         str            = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class AlerteDelai:
    reference:       str
    etape:           str
    libelle_etape:   str
    article_cima:    str
    jours_restants:  int          # négatif = dépassé
    date_echeance:   str
    critique:        bool = False
    interet_moratoire_indicatif: float = 0.0  # FCFA si montant connu


@dataclass
class AutorisationEtape:
    autorisee:          bool
    etape:              str
    motif_blocage:      str = ""
    jours_manquants:    int = 0
    date_disponible:    str = ""
    prerequis_manquant: str = ""


# ─── Mémoire en cours de session (complétée par persistence JSON) ─────────────
_timelines: dict[str, TimelineSinistre] = {}


def _charger_timelines():
    """Charge les timelines depuis le fichier JSON si disponible."""
    global _timelines
    try:
        os.makedirs(os.path.dirname(_FICHIER_TIMELINES), exist_ok=True)
        if os.path.exists(_FICHIER_TIMELINES):
            with open(_FICHIER_TIMELINES, encoding="utf-8") as f:
                data = json.load(f)
            _timelines = {
                ref: TimelineSinistre(**tl)
                for ref, tl in data.items()
            }
    except Exception as e:
        logger.error(f"[SuiviDelai] Erreur chargement timelines : {e}")


def _sauvegarder_timelines():
    """Sauvegarde les timelines sur disque."""
    try:
        os.makedirs(os.path.dirname(_FICHIER_TIMELINES), exist_ok=True)
        with open(_FICHIER_TIMELINES, "w", encoding="utf-8") as f:
            json.dump(
                {ref: asdict(tl) for ref, tl in _timelines.items()},
                f, ensure_ascii=False, indent=2,
            )
    except Exception as e:
        logger.error(f"[SuiviDelai] Erreur sauvegarde timelines : {e}")


# Chargement initial
_charger_timelines()


class SuiviDelaiCima:
    """
    Moteur de suivi des délais réglementaires CIMA.
    Utilisé par les agents pour enregistrer les étapes et vérifier les contraintes.
    """

    def initialiser_sinistre(
        self,
        reference: str,
        branche:   str,
        user_id:   int,
        date_declaration: Optional[str] = None,
    ) -> TimelineSinistre:
        """
        Initialise la timeline d'un nouveau sinistre.
        Appeler dès la réception de la déclaration.
        """
        if reference in _timelines:
            return _timelines[reference]

        tl = TimelineSinistre(reference=reference, branche=branche.lower(), user_id=user_id)
        if date_declaration:
            tl.etapes_completees["declaration_recue"] = date_declaration
        else:
            tl.etapes_completees["declaration_recue"] = datetime.now(timezone.utc).isoformat()

        _timelines[reference] = tl
        _sauvegarder_timelines()
        logger.info(f"[SuiviDelai] Timeline initialisée : {reference} ({branche})")
        return tl

    def enregistrer_etape(
        self,
        reference:  str,
        etape:      str,
        timestamp:  Optional[str] = None,
    ) -> dict:
        """
        Enregistre la complétion d'une étape workflow.
        Retourne un résumé : prochaine étape + délai restant.
        """
        tl = _timelines.get(reference)
        if not tl:
            return {"erreur": f"Sinistre {reference} non trouvé — appeler initialiser_sinistre d'abord"}

        ts = timestamp or datetime.now(timezone.utc).isoformat()
        tl.etapes_completees[etape] = ts
        tl.mis_a_jour = datetime.now(timezone.utc).isoformat()
        _sauvegarder_timelines()

        etapes_branche = _ETAPES_PAR_BRANCHE.get(tl.branche, _ETAPES_NON_VIE_GENERAL)
        etape_def = etapes_branche.get(etape, {})
        libelle = etape_def.get("libelle", etape)

        # Calculer les délais restants pour l'étape suivante
        prochaines = self._calculer_prochaines_echeances(reference)
        logger.info(f"[SuiviDelai] Étape '{etape}' enregistrée pour {reference}")
        return {
            "reference": reference,
            "etape_completee": etape,
            "libelle": libelle,
            "timestamp": ts,
            "prochaines_echeances": prochaines[:3],
            "message": f"✅ Étape '{libelle}' enregistrée",
        }

    def verifier_etape_autorisee(
        self,
        reference: str,
        etape:     str,
    ) -> AutorisationEtape:
        """
        Vérifie si une étape peut être lancée maintenant.
        Contrôle : prérequis complété ET délai minimum respecté.
        """
        tl = _timelines.get(reference)
        if not tl:
            return AutorisationEtape(
                autorisee=False, etape=etape,
                motif_blocage=f"Sinistre {reference} non trouvé dans le suivi des délais",
            )

        etapes_branche = _ETAPES_PAR_BRANCHE.get(tl.branche, _ETAPES_NON_VIE_GENERAL)
        etape_def = etapes_branche.get(etape)
        if not etape_def:
            # Étape non définie dans les contraintes → autorisée par défaut
            return AutorisationEtape(autorisee=True, etape=etape)

        # Vérifier le prérequis
        prerequis = etape_def.get("prerequis")
        if prerequis and prerequis not in tl.etapes_completees:
            return AutorisationEtape(
                autorisee=False,
                etape=etape,
                motif_blocage=f"Prérequis '{prerequis}' non complété",
                prerequis_manquant=prerequis,
            )

        # Étape déjà complétée → toujours autorisée (idempotent)
        if etape in tl.etapes_completees:
            return AutorisationEtape(autorisee=True, etape=etape)

        return AutorisationEtape(autorisee=True, etape=etape)

    def calculer_delai_restant(
        self,
        reference: str,
        etape:     str,
        montant_sinistre: float = 0,
    ) -> dict:
        """
        Calcule le délai restant avant dépassement légal pour une étape donnée.
        Si montant fourni, calcule également les intérêts moratoires potentiels.
        """
        tl = _timelines.get(reference)
        if not tl:
            return {"erreur": f"Sinistre {reference} non trouvé"}

        etapes_branche = _ETAPES_PAR_BRANCHE.get(tl.branche, _ETAPES_NON_VIE_GENERAL)
        etape_def = etapes_branche.get(etape, {})
        delai_max   = etape_def.get("delai_max_jours")
        depuis_etape = etape_def.get("delai_max_depuis")

        if not delai_max or not depuis_etape:
            return {"reference": reference, "etape": etape, "message": "Aucun délai légal défini pour cette étape"}

        if depuis_etape not in tl.etapes_completees:
            return {"reference": reference, "etape": etape, "erreur": f"Étape de référence '{depuis_etape}' non complétée"}

        date_debut   = datetime.fromisoformat(tl.etapes_completees[depuis_etape]).date()
        date_limite  = date_debut + timedelta(days=delai_max)
        aujourd_hui  = date.today()
        jours_restants = (date_limite - aujourd_hui).days

        # Si l'étape est déjà complétée — calculer le respect du délai
        if etape in tl.etapes_completees:
            date_completion = datetime.fromisoformat(tl.etapes_completees[etape]).date()
            retard = (date_completion - date_limite).days
            en_retard = retard > 0
            interets = 0.0
            if en_retard and montant_sinistre > 0:
                interets = round(montant_sinistre * TAUX_MORATOIRE_ANNUEL * retard / 365)
            return {
                "reference": reference, "etape": etape,
                "completee": True,
                "date_limite_legale": date_limite.isoformat(),
                "date_completion_effective": date_completion.isoformat(),
                "respect_delai": not en_retard,
                "retard_jours": max(0, retard),
                "interets_moratoires_fcfa": interets,
                "article_cima": etape_def.get("article_cima", ""),
            }

        # Étape non encore complétée
        interets_potentiels = 0.0
        if jours_restants < 0 and montant_sinistre > 0:
            interets_potentiels = round(montant_sinistre * TAUX_MORATOIRE_ANNUEL * abs(jours_restants) / 365)

        return {
            "reference": reference,
            "etape": etape,
            "completee": False,
            "date_limite_legale": date_limite.isoformat(),
            "jours_restants": jours_restants,
            "en_retard": jours_restants < 0,
            "jours_retard": max(0, -jours_restants),
            "interets_moratoires_potentiels_fcfa": interets_potentiels,
            "article_cima": etape_def.get("article_cima", ""),
            "critique": etape_def.get("critique", False),
        }

    def _calculer_prochaines_echeances(self, reference: str) -> list[dict]:
        """Retourne les prochaines étapes avec leurs délais restants."""
        tl = _timelines.get(reference)
        if not tl:
            return []
        etapes_branche = _ETAPES_PAR_BRANCHE.get(tl.branche, _ETAPES_NON_VIE_GENERAL)
        resultats = []
        for etape, definition in etapes_branche.items():
            if etape in tl.etapes_completees:
                continue  # Déjà fait
            delai_max   = definition.get("delai_max_jours")
            depuis_etape = definition.get("delai_max_depuis")
            if not delai_max or not depuis_etape:
                continue
            if depuis_etape not in tl.etapes_completees:
                continue
            date_debut  = datetime.fromisoformat(tl.etapes_completees[depuis_etape]).date()
            date_limite = date_debut + timedelta(days=delai_max)
            jours       = (date_limite - date.today()).days
            resultats.append({
                "etape": etape,
                "libelle": definition.get("libelle", etape),
                "article_cima": definition.get("article_cima", ""),
                "date_limite": date_limite.isoformat(),
                "jours_restants": jours,
                "en_retard": jours < 0,
                "critique": definition.get("critique", False),
            })
        resultats.sort(key=lambda x: x["jours_restants"])
        return resultats

    def calculer_alertes_a_envoyer(self, reference: str) -> list[AlerteDelai]:
        """
        Calcule les alertes qui doivent être envoyées aujourd'hui.
        Respecte le dédoublonnage (alertes déjà envoyées ignorées).
        """
        tl = _timelines.get(reference)
        if not tl:
            return []

        etapes_branche = _ETAPES_PAR_BRANCHE.get(tl.branche, _ETAPES_NON_VIE_GENERAL)
        alertes: list[AlerteDelai] = []

        for etape, definition in etapes_branche.items():
            if etape in tl.etapes_completees:
                continue

            delai_max    = definition.get("delai_max_jours")
            depuis_etape = definition.get("delai_max_depuis")
            seuils       = definition.get("seuil_alerte_jours", [])

            if not delai_max or not depuis_etape or not seuils:
                continue
            if depuis_etape not in tl.etapes_completees:
                continue

            date_debut  = datetime.fromisoformat(tl.etapes_completees[depuis_etape]).date()
            date_limite = date_debut + timedelta(days=delai_max)
            jours       = (date_limite - date.today()).days

            for seuil in seuils:
                cle_alerte = f"{etape}_J{'+' if seuil < 0 else '-'}{abs(seuil)}"
                if cle_alerte in tl.alertes_envoyees:
                    continue
                if jours <= seuil:
                    alertes.append(AlerteDelai(
                        reference=reference,
                        etape=etape,
                        libelle_etape=definition.get("libelle", etape),
                        article_cima=definition.get("article_cima", ""),
                        jours_restants=jours,
                        date_echeance=date_limite.isoformat(),
                        critique=definition.get("critique", False),
                    ))
                    tl.alertes_envoyees.append(cle_alerte)
                    break  # Un seul seuil par étape par jour

        if alertes:
            _sauvegarder_timelines()
        return alertes

    def tableau_bord_delais(
        self,
        branche:    Optional[str] = None,
        user_id:    Optional[int] = None,
    ) -> dict:
        """
        Tableau de bord synthétique des délais CIMA pour tous les sinistres actifs.
        Retourne : nombre en retard, alertes proches, détail par sinistre.
        """
        resultats = []
        en_retard = 0
        alerte_proche = 0  # J-7 ou moins

        for ref, tl in _timelines.items():
            if branche and tl.branche != branche.lower():
                continue
            if user_id and tl.user_id != user_id:
                continue

            echeances = self._calculer_prochaines_echeances(ref)
            if not echeances:
                continue

            premiere = echeances[0]
            if premiere["en_retard"]:
                en_retard += 1
            elif premiere["jours_restants"] <= 7:
                alerte_proche += 1

            resultats.append({
                "reference": ref,
                "branche": tl.branche,
                "nb_etapes_completees": len(tl.etapes_completees),
                "prochaine_echeance": premiere,
                "toutes_echeances": echeances,
            })

        resultats.sort(key=lambda x: x["prochaine_echeance"]["jours_restants"])

        return {
            "nb_sinistres_actifs": len(resultats),
            "nb_en_retard_cima": en_retard,
            "nb_alerte_7_jours": alerte_proche,
            "conformite_globale": "NON CONFORME" if en_retard > 0 else (
                "VIGILANCE" if alerte_proche > 0 else "CONFORME"
            ),
            "sinistres": resultats[:50],
        }

    def get_timeline(self, reference: str) -> Optional[dict]:
        """Retourne la timeline complète d'un sinistre."""
        tl = _timelines.get(reference)
        if not tl:
            return None
        etapes_branche = _ETAPES_PAR_BRANCHE.get(tl.branche, _ETAPES_NON_VIE_GENERAL)
        etapes_detail = {}
        for etape, definition in etapes_branche.items():
            etapes_detail[etape] = {
                "libelle": definition.get("libelle", etape),
                "article_cima": definition.get("article_cima", ""),
                "completee": etape in tl.etapes_completees,
                "date_completion": tl.etapes_completees.get(etape),
                "critique": definition.get("critique", False),
                "concerne_externe": definition.get("concerne_externe"),
            }
            if definition.get("delai_max_jours"):
                info_delai = self.calculer_delai_restant(reference, etape)
                etapes_detail[etape]["delai"] = info_delai

        return {
            "reference": tl.reference,
            "branche": tl.branche,
            "cree_le": tl.cree_le,
            "mis_a_jour": tl.mis_a_jour,
            "etapes": etapes_detail,
            "prochaines_echeances": self._calculer_prochaines_echeances(reference),
        }


# ─── Singleton ────────────────────────────────────────────────────────────────
suivi_delai_cima = SuiviDelaiCima()
