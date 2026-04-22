"""
PortailExterne — Gestion des interventions des parties externes.

Permet à des prestataires (experts, garages, médecins, cliniques) et aux assurés
de participer au workflow sinistre depuis :
  - Le portail web Yukpo (lien sécurisé avec token unique)
  - L'application mobile
  - WhatsApp Business API (réception + traitement messages entrants)

FLUX :
  1. Agent crée une InterventionExterne via creer_intervention()
  2. Notification envoyée au destinataire avec lien + instructions
  3. Destinataire accède au portail OU répond sur WhatsApp
  4. Soumission traitée par traiter_soumission()
  5. Contenu injecté dans l'approval_queue → agent reprend

TYPES D'INTERVENTIONS SUPPORTÉS :
  - expertise_auto          : Expert automobile transmet rapport + photos
  - expertise_medicale      : Médecin expert transmet rapport IPP/ITT
  - rapport_garage          : Garage transmet devis / facture réparation
  - rapport_hopital         : Hôpital transmet bulletin + factures hospitalisation
  - rapport_medecin         : Médecin traitant transmet certificats médicaux
  - acceptation_offre       : Assuré accepte/refuse offre d'indemnisation
  - transmission_documents  : Assuré transmet pièces complémentaires
  - attestation_prestataire : Prestataire santé confirme prise en charge BPC

SÉCURITÉ :
  - Token UUID unique par intervention (non-devinable)
  - Expiration configurable (défaut 72h)
  - Lien à usage unique après soumission
  - Logs complets de toutes les actions
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("yukpo_assurance.portail_externe")

_FICHIER_INTERVENTIONS = os.path.join(
    os.path.dirname(__file__), "..", "data", "interventions_externes.json"
)
_BASE_URL_PORTAIL = os.environ.get("BASE_URL_PORTAIL", "http://localhost:3000/portail")
_EXPIRATION_HEURES_DEFAUT = 72


@dataclass
class InterventionExterne:
    id:                     str   = field(default_factory=lambda: str(uuid.uuid4()))
    token:                  str   = field(default_factory=lambda: secrets.token_urlsafe(32))
    type_intervention:      str   = ""   # expertise_auto | expertise_medicale | acceptation_offre | ...
    reference_sinistre:     str   = ""
    branche:                str   = ""

    # ── Destinataire ──────────────────────────────────────────────────────────
    destinataire_nom:       str   = ""
    destinataire_telephone: str   = ""
    destinataire_email:     str   = ""
    destinataire_type:      str   = ""   # expert_auto | medecin_expert | assure | garage | hopital | ...

    # ── Contenu de la demande ─────────────────────────────────────────────────
    titre:                  str   = ""
    message_instruction:    str   = ""
    champs_requis:          list  = field(default_factory=list)  # Champs que le prestataire doit remplir
    documents_requis:       list  = field(default_factory=list)  # Types de docs attendus
    nb_docs_max:            int   = 5

    # ── Liaison avec l'agent ──────────────────────────────────────────────────
    approval_item_id:       str   = ""   # Lien vers l'item approval_queue à résoudre
    execution_id:           str   = ""
    agent_type:             str   = ""
    user_id:                int   = 0

    # ── Statut et soumission ──────────────────────────────────────────────────
    statut:                 str   = "en_attente"   # en_attente | soumis | expire | annule
    soumission_texte:       str   = ""
    soumission_docs_urls:   list  = field(default_factory=list)
    soumission_docs_b64:    list  = field(default_factory=list)
    soumission_champs:      dict  = field(default_factory=dict)

    # ── Traçabilité ───────────────────────────────────────────────────────────
    cree_le:                str   = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_le:             str   = field(default_factory=lambda: (
        datetime.now(timezone.utc) + timedelta(hours=_EXPIRATION_HEURES_DEFAUT)
    ).isoformat())
    soumis_le:              Optional[str] = None

    # Canal de soumission reçue
    canal_reception:        str   = ""   # portail_web | whatsapp | mobile | api

    # État de la conversation WhatsApp (pour multi-étapes)
    whatsapp_etat:          str   = "init"  # init | attente_doc | attente_texte | complete


# ─── Stockage en mémoire ──────────────────────────────────────────────────────
_interventions: dict[str, InterventionExterne] = {}         # id → intervention
_token_index:   dict[str, str]                 = {}         # token → id
_telephone_idx: dict[str, list[str]]           = {}         # telephone → [ids en_attente]


def _charger():
    global _interventions, _token_index, _telephone_idx
    try:
        os.makedirs(os.path.dirname(_FICHIER_INTERVENTIONS), exist_ok=True)
        if os.path.exists(_FICHIER_INTERVENTIONS):
            with open(_FICHIER_INTERVENTIONS, encoding="utf-8") as f:
                data = json.load(f)
            _interventions = {k: InterventionExterne(**v) for k, v in data.items()}
            _token_index = {iv.token: iv.id for iv in _interventions.values()}
            _telephone_idx = {}
            for iv in _interventions.values():
                if iv.destinataire_telephone and iv.statut == "en_attente":
                    tel = iv.destinataire_telephone
                    _telephone_idx.setdefault(tel, []).append(iv.id)
    except Exception as e:
        logger.error(f"[PortailExterne] Erreur chargement : {e}")


def _sauvegarder():
    try:
        os.makedirs(os.path.dirname(_FICHIER_INTERVENTIONS), exist_ok=True)
        with open(_FICHIER_INTERVENTIONS, "w", encoding="utf-8") as f:
            json.dump({k: asdict(v) for k, v in _interventions.items()}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[PortailExterne] Erreur sauvegarde : {e}")


_charger()


# ─── Templates de messages de notification ───────────────────────────────────
# ─── Checklist documents attendus par type de prestataire/assuré ─────────────
CHECKLIST_DOCUMENTS: dict[str, dict] = {
    # ── RC Auto ──────────────────────────────────────────────────────────────
    "assure_rc_auto": {
        "libelle": "Assuré RC Auto",
        "documents_obligatoires": [
            "Constat amiable signé (ou PV police / main courante)",
            "Attestation d'assurance RC à jour",
            "Carte rose (carte de circulation) du véhicule",
            "Copie permis de conduire du conducteur",
            "Photos du véhicule (6 minimum : avant, arrière, côtés, dommages)",
        ],
        "documents_complementaires": [
            "Facture ou devis de réparation (après expertise)",
            "RIB ou coordonnées pour virement de l'indemnisation",
            "Certificats médicaux si blessures corporelles",
        ],
        "delai_standard_jours": 30,
    },
    "expert_auto": {
        "libelle": "Expert Automobile",
        "documents_obligatoires": [
            "Rapport d'expertise automobile signé (PDF)",
            "Valeur VRADE estimée (FCFA)",
            "Coût de réparation estimé (FCFA)",
            "Avis sur VEI (Véhicule Économiquement Irréparable) — Oui/Non",
            "Photos des dommages prises lors de l'expertise",
        ],
        "documents_complementaires": [
            "Devis garage agréé si VEI",
            "Valeur épave si applicable",
        ],
        "champs_requis": ["vrade_estime_fcfa", "cout_reparation_fcfa", "vei_oui_non", "avis_expert"],
        "delai_standard_jours": 30,
    },
    "medecin_expert": {
        "libelle": "Médecin Expert",
        "documents_obligatoires": [
            "Rapport d'expertise médicale signé (PDF)",
            "Taux d'IPP en pourcentage (%)",
            "Nombre de jours d'ITT (Incapacité Temporaire Totale)",
            "Nombre de jours d'ITP (Incapacité Temporaire Partielle) si applicable",
            "Date de consolidation médicale",
            "Degré de pretium doloris (1 à 7) — Art. 235 CIMA",
        ],
        "documents_complementaires": [
            "Degré de préjudice esthétique (1 à 7) si applicable",
            "Avis sur besoin tierce personne permanente",
            "Rapports d'examens complémentaires",
        ],
        "champs_requis": ["taux_ipp_pct", "nb_jours_itt", "nb_jours_itp", "date_consolidation", "degre_pretium_doloris"],
        "delai_standard_jours": 30,
    },
    "garage_carrosserie": {
        "libelle": "Garage / Carrosserie",
        "documents_obligatoires": [
            "Devis de réparation détaillé (pièces + main d'œuvre)",
            "Durée d'immobilisation du véhicule prévue (jours)",
        ],
        "documents_complementaires": [
            "Facture définitive après travaux",
            "Photos véhicule avant et après réparation",
            "Certificat de restitution du véhicule au client",
        ],
        "champs_requis": ["montant_devis_fcfa", "duree_immobilisation_jours"],
        "delai_standard_jours": 7,
    },
    "assureur_tiers": {
        "libelle": "Assureur du Tiers",
        "documents_obligatoires": [
            "Attestation d'assurance RC du véhicule tiers",
            "Position sur la responsabilité (% accepté)",
        ],
        "documents_complementaires": [
            "Police d'assurance du tiers (si disponible)",
            "Rapport expertise du tiers (si disponible)",
        ],
        "champs_requis": ["part_responsabilite_acceptee_pct", "reference_police_tiers"],
        "delai_standard_jours": 15,
    },

    # ── Maladie / Santé ───────────────────────────────────────────────────────
    "assure_maladie": {
        "libelle": "Assuré / Patient",
        "documents_obligatoires": [
            "Ordonnance médicale originale datée et signée",
            "Facture(s) de soins détaillée(s) acquittée(s)",
            "Certificat médical justifiant l'acte",
        ],
        "documents_complementaires": [
            "Bulletin d'hospitalisation si hospitalisation",
            "Résultats d'examens complémentaires",
            "Justificatif identité + n° assuré",
            "RIB pour remboursement par virement",
        ],
        "delai_standard_jours": 30,
    },
    "medecin_traitant": {
        "libelle": "Médecin Traitant",
        "documents_obligatoires": [
            "Certificat médical initial daté et signé",
            "Description des soins effectués",
        ],
        "documents_complementaires": [
            "Certificat de consolidation / guérison",
            "Prescription médicale détaillée",
            "Lettre de référence vers spécialiste si applicable",
        ],
        "champs_requis": ["diagnostic", "actes_realises", "date_debut_traitement", "date_fin_prevue"],
        "delai_standard_jours": 5,
    },
    "clinique_hopital": {
        "libelle": "Clinique / Hôpital",
        "documents_obligatoires": [
            "Bulletin d'hospitalisation (admission + sortie)",
            "Compte rendu opératoire / médical signé",
            "Facture détaillée par poste (honoraires, hébergement, médicaments, actes)",
        ],
        "documents_complementaires": [
            "Bulletin de sortie avec diagnostic de sortie",
            "Prescriptions à la sortie",
            "Résultats examens réalisés pendant le séjour",
            "Attestation de tiers payant si applicable",
        ],
        "champs_requis": [
            "date_entree", "date_sortie", "diagnostic_principal",
            "actes_chirurgicaux", "montant_total_fcfa"
        ],
        "delai_standard_jours": 7,
    },
    "pharmacie": {
        "libelle": "Pharmacie",
        "documents_obligatoires": [
            "Ordonnance originale prescrite par médecin agréé",
            "Facture détaillée avec DCI (Dénomination Commune Internationale) et quantités",
        ],
        "documents_complementaires": [
            "Ticket de caisse si disponible",
        ],
        "champs_requis": ["montant_medicaments_fcfa", "date_delivrance"],
        "delai_standard_jours": 3,
    },
    "laboratoire": {
        "libelle": "Laboratoire d'Analyses",
        "documents_obligatoires": [
            "Prescription médicale pour les analyses",
            "Résultats des analyses signés",
            "Facture des analyses effectuées",
        ],
        "champs_requis": ["types_analyses", "montant_fcfa", "date_analyses"],
        "delai_standard_jours": 3,
    },
    "prestataire_sante": {
        "libelle": "Prestataire Réseau Agréé",
        "documents_obligatoires": [
            "Confirmation de la prise en charge effective sur BPC",
            "Facture détaillée des soins / actes réalisés",
            "Signature du patient sur le BPC (attestation de soins reçus)",
        ],
        "documents_complementaires": [
            "Rapport de soins si actes multiples",
        ],
        "champs_requis": ["montant_facture_fcfa", "date_prise_en_charge", "actes_realises"],
        "delai_standard_jours": 5,
    },

    # ── Vie & Prévoyance ──────────────────────────────────────────────────────
    "ayants_droit": {
        "libelle": "Ayants Droit / Bénéficiaires",
        "documents_obligatoires": [
            "Acte de décès certifié conforme",
            "Copie CNI / Passeport de chaque bénéficiaire",
            "Livret de famille ou acte de mariage",
            "RIB de chaque bénéficiaire pour virement",
        ],
        "documents_complementaires": [
            "Certificat de non-remariage (pour conjoint)",
            "Jugement de tutelle si enfants mineurs",
            "Actes de naissance des enfants bénéficiaires",
            "Certificat de vie commune si concubin désigné",
        ],
        "delai_standard_jours": 30,
    },
    "iml_medecin_legal": {
        "libelle": "Institut Médico-Légal / Médecin Légiste",
        "documents_obligatoires": [
            "Rapport d'autopsie ou certificat médico-légal",
            "Cause du décès certifiée",
        ],
        "documents_complementaires": [
            "Rapport de circonstances si mort violente",
            "Résultats toxicologiques si applicable",
        ],
        "champs_requis": ["cause_deces", "date_deces", "circonstances"],
        "delai_standard_jours": 15,
    },

    # ── Tous sinistres — Actions assuré ───────────────────────────────────────
    "assure_acceptation_offre": {
        "libelle": "Assuré — Réponse à l'offre d'indemnisation",
        "documents_obligatoires": [
            "Décision : ACCEPTER ou REFUSER l'offre",
        ],
        "documents_complementaires": [
            "Motif de refus si applicable",
            "Contre-proposition chiffrée si contestation",
            "RIB pour virement si acceptation",
        ],
        "champs_requis": ["decision", "commentaire"],
        "delai_standard_jours": 30,
        "note_legale": "Art. 12-bis CIMA — délai de réflexion 30 jours",
    },
}

_MESSAGES_NOTIFICATION: dict[str, dict] = {
    "expertise_auto": {
        "titre": "Demande de rapport d'expertise automobile",
        "message_whatsapp": (
            "Bonjour {nom},\n\n"
            "YukpoAssurance vous mandate pour une expertise automobile sur le sinistre {reference}.\n\n"
            "📋 Votre rapport est attendu sous *{delai_jours} jours*.\n\n"
            "Vous pouvez transmettre votre rapport ici :\n🔗 {lien_portail}\n\n"
            "Ou répondre directement à ce message WhatsApp avec :\n"
            "1. Votre rapport en PDF\n"
            "2. Les photos des dommages\n"
            "3. La valeur VRADE estimée\n\n"
            "_Référence dossier : {reference}_"
        ),
        "champs_requis": ["vrade_estime_fcfa", "cout_reparation_fcfa", "avis_expert"],
        "documents_requis": ["rapport_expertise_auto", "photos_dommages"],
    },
    "expertise_medicale": {
        "titre": "Demande de rapport d'expertise médicale",
        "message_whatsapp": (
            "Bonjour Dr {nom},\n\n"
            "YukpoAssurance vous mandate pour l'expertise médicale du sinistre {reference}.\n\n"
            "📋 Votre rapport doit préciser :\n"
            "• Taux d'IPP (%)\n"
            "• Durée ITT (jours)\n"
            "• Date de consolidation\n"
            "• Degré pretium doloris (1-7)\n\n"
            "Délai : *{delai_jours} jours*\n\n"
            "Portail de transmission sécurisé :\n🔗 {lien_portail}\n\n"
            "_Référence : {reference}_"
        ),
        "champs_requis": ["taux_ipp_pct", "nb_jours_itt", "date_consolidation", "degre_pretium_doloris"],
        "documents_requis": ["rapport_expertise_medicale", "certificat_medical"],
    },
    "rapport_garage": {
        "titre": "Transmission devis / facture de réparation",
        "message_whatsapp": (
            "Bonjour {nom},\n\n"
            "Nous avons besoin de votre devis ou facture de réparation pour le sinistre {reference}.\n\n"
            "📎 Envoyez le document (PDF ou photo) ici :\n🔗 {lien_portail}\n\n"
            "Ou répondez directement à ce message WhatsApp avec la photo/PDF de votre devis.\n\n"
            "_Réf. : {reference}_"
        ),
        "champs_requis": ["montant_devis_fcfa"],
        "documents_requis": ["devis_reparation", "facture_reparation"],
    },
    "rapport_hopital": {
        "titre": "Transmission bulletin d'hospitalisation et factures",
        "message_whatsapp": (
            "Bonjour,\n\n"
            "Pour le dossier sinistre {reference}, veuillez transmettre :\n"
            "• Le bulletin d'hospitalisation\n"
            "• Les factures détaillées\n"
            "• Les ordonnances médicales\n\n"
            "📎 Portail de transmission :\n🔗 {lien_portail}\n\n"
            "_Réf. : {reference}_"
        ),
        "champs_requis": ["montant_total_fcfa", "dates_hospitalisation"],
        "documents_requis": ["bulletin_hospitalisation", "factures_medicales", "ordonnances"],
    },
    "acceptation_offre": {
        "titre": "Offre d'indemnisation — Votre réponse est attendue",
        "message_whatsapp": (
            "Bonjour {nom},\n\n"
            "Suite au sinistre {reference}, YukpoAssurance vous soumet une offre d'indemnisation "
            "de *{montant_offre} FCFA*.\n\n"
            "⏳ Vous avez *30 jours* pour répondre (Art. 12-bis CIMA).\n\n"
            "Consultez et acceptez/refusez l'offre ici :\n🔗 {lien_portail}\n\n"
            "Ou répondez à ce message :\n"
            "• Tapez *ACCEPTE* pour accepter\n"
            "• Tapez *REFUSE* suivi de votre motif pour refuser\n\n"
            "_Réf. : {reference}_"
        ),
        "champs_requis": ["decision", "commentaire"],
        "documents_requis": [],
    },
    "transmission_documents": {
        "titre": "Envoi de pièces complémentaires demandées",
        "message_whatsapp": (
            "Bonjour {nom},\n\n"
            "Pour compléter votre dossier sinistre {reference}, nous avons besoin des documents suivants :\n"
            "{liste_documents}\n\n"
            "📎 Envoyez-les ici :\n🔗 {lien_portail}\n\n"
            "Ou directement sur WhatsApp en répondant à ce message.\n\n"
            "_Réf. : {reference}_"
        ),
        "champs_requis": [],
        "documents_requis": [],
    },
    "attestation_prestataire": {
        "titre": "Confirmation prise en charge BPC",
        "message_whatsapp": (
            "Bonjour,\n\n"
            "Veuillez confirmer la prise en charge du patient sur le BPC {reference}.\n\n"
            "Confirmez ici :\n🔗 {lien_portail}\n\n"
            "Ou répondez *CONFIRME* à ce message.\n\n"
            "_Réf. BPC : {reference}_"
        ),
        "champs_requis": ["montant_facture_fcfa", "date_prise_en_charge", "actes_realises"],
        "documents_requis": ["facture_prestataire", "bulletin_soin"],
    },
    # ── Maladie ───────────────────────────────────────────────────────────────
    "accord_prealable_hospitalisation": {
        "titre": "Demande d'accord préalable pour hospitalisation",
        "message_whatsapp": (
            "Bonjour {nom},\n\n"
            "YukpoAssurance a reçu votre demande d'accord préalable pour hospitalisation (dossier {reference}).\n\n"
            "📋 Documents nécessaires pour traitement rapide :\n"
            "• Devis d'hospitalisation\n"
            "• Certificat médical d'indication d'hospitalisation\n"
            "• Compte rendu médical préopératoire si chirurgie\n\n"
            "Transmettez vos documents ici :\n🔗 {lien_portail}\n\n"
            "⏱ Délai de traitement : *{delai_jours} jours ouvrés*\n\n"
            "_Réf. : {reference}_"
        ),
        "champs_requis": ["etablissement_soin", "date_prevue_entree", "type_hospitalisation"],
        "documents_requis": ["certificat_medical_indication", "devis_hospitalisation"],
    },
    "remboursement_frais_medicaux": {
        "titre": "Demande de remboursement frais médicaux",
        "message_whatsapp": (
            "Bonjour {nom},\n\n"
            "Pour traiter votre demande de remboursement (dossier {reference}), "
            "veuillez transmettre vos justificatifs :\n\n"
            "📎 Documents attendus :\n"
            "• Ordonnance médicale\n"
            "• Facture(s) acquittée(s) avec détail des actes\n"
            "• Certificat médical si hospitalisation\n\n"
            "Envoyez ici :\n🔗 {lien_portail}\n\n"
            "Ou directement sur WhatsApp (photos ou PDF).\n\n"
            "_Réf. : {reference}_"
        ),
        "champs_requis": ["montant_total_fcfa", "nature_soins"],
        "documents_requis": ["ordonnance", "factures_medicales"],
    },
    "transmission_rapport_medical": {
        "titre": "Transmission rapport médical / certificat",
        "message_whatsapp": (
            "Bonjour Dr {nom},\n\n"
            "Dans le cadre du dossier sinistre {reference}, "
            "nous attendons votre rapport médical / certificat de consolidation.\n\n"
            "📎 Envoyez le document ici :\n🔗 {lien_portail}\n\n"
            "Ou par WhatsApp directement (PDF ou photo).\n\n"
            "_Réf. : {reference}_"
        ),
        "champs_requis": ["type_rapport", "diagnostic", "date_consolidation"],
        "documents_requis": ["rapport_medical", "certificat_consolidation"],
    },
    "transmission_facture_clinique": {
        "titre": "Transmission bulletin et factures d'hospitalisation",
        "message_whatsapp": (
            "Bonjour,\n\n"
            "Pour le dossier {reference}, veuillez transmettre :\n\n"
            "📋 Documents obligatoires :\n"
            "• Bulletin d'hospitalisation (entrée + sortie)\n"
            "• Compte rendu opératoire / médical\n"
            "• Facture détaillée par poste\n\n"
            "📎 Portail de transmission :\n🔗 {lien_portail}\n\n"
            "_Réf. : {reference}_"
        ),
        "champs_requis": ["date_entree", "date_sortie", "montant_total_fcfa", "diagnostic_principal"],
        "documents_requis": ["bulletin_hospitalisation", "compte_rendu_operatoire", "facture_detaillee"],
    },
    # ── Vie & Prévoyance ──────────────────────────────────────────────────────
    "depot_pieces_ayants_droit": {
        "titre": "Dépôt des pièces — Bénéficiaires assurance vie",
        "message_whatsapp": (
            "Bonjour {nom},\n\n"
            "Suite au décès de votre proche, YukpoAssurance est prête à traiter "
            "votre dossier de prestations (réf. {reference}).\n\n"
            "📋 Pièces obligatoires pour chaque bénéficiaire :\n"
            "• Acte de décès certifié conforme\n"
            "• Copie CNI / Passeport\n"
            "• Livret de famille ou acte de mariage\n"
            "• RIB pour virement des prestations\n\n"
            "📎 Déposez vos documents ici :\n🔗 {lien_portail}\n\n"
            "Notre équipe vous contactera sous *{delai_jours} jours* après réception du dossier complet.\n\n"
            "_Réf. : {reference}_"
        ),
        "champs_requis": ["lien_avec_assure", "nb_beneficiaires"],
        "documents_requis": ["acte_deces", "cni_beneficiaire", "livret_famille", "rib_beneficiaire"],
    },
}


class PortailExterne:
    """
    Gestion complète des interventions externes dans le workflow sinistre.
    """

    async def creer_intervention(
        self,
        type_intervention:      str,
        reference_sinistre:     str,
        branche:                str,
        destinataire_nom:       str,
        destinataire_telephone: str,
        destinataire_type:      str,
        approval_item_id:       str,
        execution_id:           str,
        agent_type:             str,
        user_id:                int,
        destinataire_email:     str = "",
        delai_heures:           int = _EXPIRATION_HEURES_DEFAUT,
        contexte_supplementaire: str = "",
        montant_offre:          float = 0,
    ) -> InterventionExterne:
        """
        Crée une intervention externe et envoie la notification au destinataire.
        Retourne l'intervention créée avec son token sécurisé.
        """
        template = _MESSAGES_NOTIFICATION.get(type_intervention, {})

        # Construire le lien sécurisé
        iv = InterventionExterne(
            type_intervention=type_intervention,
            reference_sinistre=reference_sinistre,
            branche=branche,
            destinataire_nom=destinataire_nom,
            destinataire_telephone=destinataire_telephone,
            destinataire_email=destinataire_email,
            destinataire_type=destinataire_type,
            titre=template.get("titre", type_intervention),
            champs_requis=template.get("champs_requis", []),
            documents_requis=template.get("documents_requis", []),
            approval_item_id=approval_item_id,
            execution_id=execution_id,
            agent_type=agent_type,
            user_id=user_id,
            expires_le=(datetime.now(timezone.utc) + timedelta(hours=delai_heures)).isoformat(),
        )

        lien_portail = f"{_BASE_URL_PORTAIL}/{iv.token}"
        delai_jours = delai_heures // 24

        # Construire le message WhatsApp depuis le template
        msg_template = template.get("message_whatsapp", "")
        msg_whatsapp = msg_template.format(
            nom=destinataire_nom,
            reference=reference_sinistre,
            lien_portail=lien_portail,
            delai_jours=delai_jours,
            montant_offre=f"{montant_offre:,.0f}".replace(",", " ") if montant_offre else "à définir",
            liste_documents="\n".join(f"• {d}" for d in template.get("documents_requis", [])),
        )
        if contexte_supplementaire:
            msg_whatsapp += f"\n\n📌 Informations complémentaires : {contexte_supplementaire}"

        iv.message_instruction = msg_whatsapp

        # Stocker
        _interventions[iv.id] = iv
        _token_index[iv.token] = iv.id
        if destinataire_telephone:
            _telephone_idx.setdefault(destinataire_telephone, []).append(iv.id)

        _sauvegarder()

        # Envoyer la notification
        await self._envoyer_notification(iv, msg_whatsapp)

        logger.info(
            f"[PortailExterne] Intervention créée : {iv.id} "
            f"type={type_intervention} ref={reference_sinistre} "
            f"destinataire={destinataire_nom} ({destinataire_type})"
        )
        return iv

    async def _envoyer_notification(self, iv: InterventionExterne, message: str):
        """Envoie la notification WhatsApp/SMS au destinataire."""
        try:
            from core.notifications import notifications
            await notifications.envoyer(
                canal="whatsapp",
                destinataire=iv.destinataire_telephone,
                message=message,
            )
        except Exception as e:
            logger.error(f"[PortailExterne] Erreur envoi notification {iv.id} : {e}")

    def get_par_token(self, token: str) -> Optional[InterventionExterne]:
        """Récupère une intervention par son token de portail."""
        iv_id = _token_index.get(token)
        if not iv_id:
            return None
        iv = _interventions.get(iv_id)
        if not iv:
            return None
        # Vérifier expiration
        if datetime.now(timezone.utc) > datetime.fromisoformat(iv.expires_le):
            iv.statut = "expire"
            _sauvegarder()
        return iv

    def get_par_telephone(self, telephone: str) -> list[InterventionExterne]:
        """Retourne les interventions en attente pour un numéro de téléphone donné."""
        ids = _telephone_idx.get(telephone, [])
        result = []
        for iv_id in ids:
            iv = _interventions.get(iv_id)
            if iv and iv.statut == "en_attente":
                result.append(iv)
        return result

    async def traiter_soumission(
        self,
        token:          str,
        texte:          str,
        docs_urls:      list[str] | None = None,
        docs_base64:    list[str] | None = None,
        champs:         dict | None = None,
        canal:          str = "portail_web",
    ) -> dict:
        """
        Traite la soumission d'une intervention externe.
        Résout l'approval_queue item correspondant pour reprendre l'agent.
        """
        iv = self.get_par_token(token)
        if not iv:
            return {"succes": False, "erreur": "Lien invalide ou expiré"}
        if iv.statut != "en_attente":
            return {"succes": False, "erreur": f"Cette demande a déjà été traitée (statut: {iv.statut})"}

        # Enregistrer la soumission
        iv.statut              = "soumis"
        iv.soumission_texte    = texte
        iv.soumission_docs_urls  = docs_urls or []
        iv.soumission_docs_b64   = docs_base64 or []
        iv.soumission_champs   = champs or {}
        iv.soumis_le           = datetime.now(timezone.utc).isoformat()
        iv.canal_reception     = canal

        _sauvegarder()

        # Construire le résumé pour l'agent
        resume = self._construire_resume_soumission(iv)

        # Résoudre l'approval_queue item → reprendre l'agent
        from core.approval_queue import approval_queue
        try:
            resultat_agent = await approval_queue.repondre_question(
                item_id=iv.approval_item_id,
                reponse=resume,
                user_id=iv.user_id,
                user_nom=f"{iv.destinataire_nom} ({iv.destinataire_type})",
                medias_urls=iv.soumission_docs_urls,
                medias_base64=iv.soumission_docs_b64,
            )
            logger.info(
                f"[PortailExterne] Soumission traitée : {iv.id} "
                f"— agent repris via approval_queue {iv.approval_item_id}"
            )
            return {
                "succes": True,
                "message": "Votre soumission a bien été reçue. Le traitement du dossier reprend automatiquement.",
                "reference": iv.reference_sinistre,
                "soumis_le": iv.soumis_le,
            }
        except Exception as e:
            logger.error(f"[PortailExterne] Erreur reprise agent {iv.approval_item_id} : {e}")
            return {
                "succes": True,  # La soumission est bien enregistrée
                "message": "Soumission reçue — traitement en cours (reprise agent en attente)",
                "reference": iv.reference_sinistre,
                "avertissement": str(e),
            }

    def _construire_resume_soumission(self, iv: InterventionExterne) -> str:
        """Construit un résumé structuré de la soumission pour injection dans l'agent."""
        lignes = [
            f"SOUMISSION {iv.type_intervention.upper()} — {iv.reference_sinistre}",
            f"Soumis par : {iv.destinataire_nom} ({iv.destinataire_type})",
            f"Canal : {iv.canal_reception}",
            f"Date : {iv.soumis_le}",
            "",
        ]
        if iv.soumission_texte:
            lignes.append(f"Contenu :\n{iv.soumission_texte}")
        if iv.soumission_champs:
            lignes.append("\nChamps renseignés :")
            for k, v in iv.soumission_champs.items():
                lignes.append(f"  {k} : {v}")
        nb_docs = len(iv.soumission_docs_urls) + len(iv.soumission_docs_b64)
        if nb_docs > 0:
            lignes.append(f"\n{nb_docs} document(s) transmis")
        return "\n".join(lignes)

    async def traiter_message_whatsapp(
        self,
        telephone:  str,
        message:    str,
        docs_b64:   list[str] | None = None,
    ) -> dict:
        """
        Traite un message WhatsApp entrant d'un prestataire ou assuré.
        Identifie l'intervention en attente par numéro de téléphone.
        Gère le dialogue multi-étapes pour guider la soumission.
        """
        # Normaliser le numéro (supprimer + ou espaces)
        tel_norm = telephone.strip().replace(" ", "").replace("-", "")

        interventions_en_attente = self.get_par_telephone(tel_norm)
        if not interventions_en_attente:
            # Pas d'intervention connue — message informatif
            return {
                "reponse": (
                    "Bonjour,\nNous n'avons pas trouvé de demande en attente pour votre numéro.\n"
                    "Contactez votre gestionnaire YukpoAssurance pour plus d'informations."
                ),
                "traite": False,
            }

        # Prendre la plus récente intervention en attente
        iv = interventions_en_attente[-1]
        msg_lower = message.lower().strip()

        # ── Gestion dialogue WhatsApp selon type d'intervention ──────────────
        if iv.type_intervention == "acceptation_offre":
            if msg_lower in ("accepte", "accepté", "j'accepte", "je l'accepte", "oui", "ok"):
                await self.traiter_soumission(
                    token=iv.token,
                    texte=f"DÉCISION ASSURÉ : ACCEPTÉ\nMessage WhatsApp : {message}",
                    champs={"decision": "accepte", "commentaire": message},
                    canal="whatsapp",
                )
                return {
                    "reponse": (
                        f"✅ Merci {iv.destinataire_nom}.\n"
                        f"Votre acceptation de l'offre d'indemnisation pour le sinistre {iv.reference_sinistre} "
                        f"a bien été enregistrée.\n"
                        f"Le règlement sera effectué sous 45 jours (Art. 12-ter CIMA)."
                    ),
                    "traite": True,
                    "intervention_id": iv.id,
                }
            elif msg_lower.startswith("refuse") or msg_lower.startswith("refusé"):
                motif = message[7:].strip() or "Refus sans motif précisé"
                await self.traiter_soumission(
                    token=iv.token,
                    texte=f"DÉCISION ASSURÉ : REFUSÉ\nMotif : {motif}",
                    champs={"decision": "refuse", "commentaire": motif},
                    canal="whatsapp",
                )
                return {
                    "reponse": (
                        f"Votre refus a été enregistré pour le sinistre {iv.reference_sinistre}.\n"
                        "Votre gestionnaire va vous contacter pour discuter de la suite."
                    ),
                    "traite": True,
                    "intervention_id": iv.id,
                }
            else:
                return {
                    "reponse": (
                        f"Bonjour {iv.destinataire_nom},\n\n"
                        f"Pour le sinistre {iv.reference_sinistre}, tapez :\n"
                        "• *ACCEPTE* pour accepter l'offre\n"
                        "• *REFUSE [votre motif]* pour refuser\n\n"
                        f"Ou consultez l'offre complète : {_BASE_URL_PORTAIL}/{iv.token}"
                    ),
                    "traite": False,
                }

        elif iv.type_intervention == "attestation_prestataire":
            if msg_lower in ("confirme", "confirmé", "oui", "ok", "pris en charge"):
                await self.traiter_soumission(
                    token=iv.token,
                    texte=f"CONFIRMATION PRISE EN CHARGE\nMessage : {message}",
                    docs_base64=docs_b64 or [],
                    champs={"confirmation": "oui"},
                    canal="whatsapp",
                )
                return {
                    "reponse": f"✅ Prise en charge confirmée pour le BPC {iv.reference_sinistre}. Merci.",
                    "traite": True,
                }
            else:
                return {
                    "reponse": (
                        f"Bonjour,\nPour confirmer la prise en charge du BPC {iv.reference_sinistre} :\n"
                        "Tapez *CONFIRME* ou envoyez directement vos documents (PDF/photo) ici."
                    ),
                    "traite": False,
                }

        else:
            # Pour les autres types (expertise, garage, hôpital) :
            # Si des documents reçus → soumettre directement
            if docs_b64 or (message and len(message) > 30):
                await self.traiter_soumission(
                    token=iv.token,
                    texte=message,
                    docs_base64=docs_b64 or [],
                    canal="whatsapp",
                )
                nb_docs = len(docs_b64 or [])
                return {
                    "reponse": (
                        f"✅ Merci {iv.destinataire_nom}.\n"
                        f"Votre transmission pour le sinistre {iv.reference_sinistre} a été reçue "
                        f"({nb_docs} document(s)).\n"
                        "Le gestionnaire va traiter votre dossier."
                    ),
                    "traite": True,
                    "intervention_id": iv.id,
                }
            else:
                # Guider le prestataire
                docs_requis = "\n".join(f"  • {d}" for d in iv.documents_requis) or "  • Documents justificatifs"
                return {
                    "reponse": (
                        f"Bonjour {iv.destinataire_nom},\n\n"
                        f"📋 {iv.titre}\nDossier : {iv.reference_sinistre}\n\n"
                        f"Documents attendus :\n{docs_requis}\n\n"
                        "Envoyez directement vos documents ici (PDF ou photo),\n"
                        f"ou utilisez le portail sécurisé : {_BASE_URL_PORTAIL}/{iv.token}"
                    ),
                    "traite": False,
                }

    def lister(
        self,
        statut:          Optional[str] = None,
        reference:       Optional[str] = None,
        destinataire_type: Optional[str] = None,
    ) -> list[dict]:
        """Liste les interventions avec filtres optionnels."""
        items = list(_interventions.values())
        if statut:
            items = [i for i in items if i.statut == statut]
        if reference:
            items = [i for i in items if i.reference_sinistre == reference]
        if destinataire_type:
            items = [i for i in items if i.destinataire_type == destinataire_type]
        items.sort(key=lambda i: i.cree_le, reverse=True)
        return [_serialiser(i) for i in items[:100]]

    def get(self, iv_id: str) -> Optional[dict]:
        iv = _interventions.get(iv_id)
        return _serialiser(iv) if iv else None


def _serialiser(iv: InterventionExterne) -> dict:
    return {
        "id":                   iv.id,
        "type_intervention":    iv.type_intervention,
        "reference_sinistre":   iv.reference_sinistre,
        "branche":              iv.branche,
        "destinataire_nom":     iv.destinataire_nom,
        "destinataire_telephone": iv.destinataire_telephone,
        "destinataire_type":    iv.destinataire_type,
        "titre":                iv.titre,
        "statut":               iv.statut,
        "cree_le":              iv.cree_le,
        "expires_le":           iv.expires_le,
        "soumis_le":            iv.soumis_le,
        "canal_reception":      iv.canal_reception,
        "lien_portail":         f"{_BASE_URL_PORTAIL}/{iv.token}",
        "nb_docs_soumis":       len(iv.soumission_docs_urls) + len(iv.soumission_docs_b64),
        "peut_soumettre":       iv.statut == "en_attente",
    }


# ─── Singleton ────────────────────────────────────────────────────────────────
portail_externe = PortailExterne()
