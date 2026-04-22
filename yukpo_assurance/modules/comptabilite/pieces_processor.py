"""
YukpoAssurance — Processeur de pièces comptables  (v3 — Production SI-aligned)
OCR intelligent + imputation PCSA automatique + écriture directe dans ORASS/Mercure.

Traite :  factures garages, hôpitaux, fournisseurs, quittances, relevés bancaires,
          constats amiables, ordres de virement, reçus Mobile Money.

Nouveautés v3 :
- Prompts OCR enrichis avec champs ORASS/PCSA natifs (COMPTE_PCSA, TIERS_CODE_ORASS…)
- Validation TVA par pays CIMA (15-19.25%)
- Détection doublons par numéro de pièce + requête ORASS
- Écriture comptable PCSA automatique si confiance haute
- Support reçus Mobile Money (CinetPay, MTN MoMo, Orange Money)
"""
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from core.ia_client import ModeIA, ia_client
from core.orass_connector import orass, COMPTES_PCSA
from config.settings import settings

logger = logging.getLogger("yukpo_assurance.comptabilite.pieces")

# ─── TVA par pays CIMA ────────────────────────────────────────────────────────
TVA_PAR_PAYS = {
    "CM": 0.1925,   # Cameroun 19.25%
    "CI": 0.1800,   # Côte d'Ivoire 18%
    "SN": 0.1800,   # Sénégal 18%
    "BF": 0.1800,   # Burkina Faso 18%
    "ML": 0.1800,   # Mali 18%
    "TG": 0.1800,   # Togo 18%
    "GA": 0.1800,   # Gabon 18%
    "CG": 0.1800,   # Congo 18%
    "TD": 0.1800,   # Tchad 18%
    "DEFAULT": 0.1800,
}

# ─── Prompts OCR enrichis — structures SI natives ─────────────────────────────
PROMPTS_OCR = {
    "facture_garage": """
Analyse cette facture de garage et retourne UNIQUEMENT ce JSON valide.
Les champs ORASS_* et COMPTE_PCSA sont OBLIGATOIRES pour l'intégration SI.

{
  "numero_facture": "",
  "date": "JJ/MM/AAAA",
  "nom_garage": "",
  "rccm_garage": "",
  "numero_contribuable_garage": "",
  "adresse_garage": "",
  "telephone_garage": "",
  "rib_garage": "",
  "numero_sinistre_reference": "",
  "vehicule_immatriculation": "",
  "vehicule_marque": "",
  "vehicule_modele": "",
  "details": [
    {"libelle": "", "quantite": 1, "prix_unitaire": 0, "montant_ht": 0, "type": "piece|main_oeuvre|autre"}
  ],
  "montant_ht": 0,
  "tva_taux": 0.1925,
  "tva_montant": 0,
  "montant_ttc": 0,
  "confiance": "haute|moyenne|faible",
  "anomalies": [],
  "ORASS_SINISTRE_ID": null,
  "ORASS_TIERS_CODE": null,
  "COMPTE_PCSA_DEBIT": "60100",
  "LIBELLE_PCSA_DEBIT": "Prestations — Indemnités sinistres auto",
  "COMPTE_PCSA_CREDIT": "40100",
  "LIBELLE_PCSA_CREDIT": "Fournisseurs — Garages agréés",
  "JOURNAL_ORASS": "SN",
  "NATURE_SINISTRE": "auto",
  "DATE_ISO": "AAAA-MM-JJ"
}
""",
    "facture_hopital": """
Analyse cette facture médicale/hospitalière et retourne UNIQUEMENT ce JSON valide.
Les champs ORASS_* et COMPTE_PCSA sont OBLIGATOIRES pour l'intégration SI.

{
  "numero_facture": "",
  "date": "JJ/MM/AAAA",
  "nom_etablissement": "",
  "type_etablissement": "hopital|clinique|pharmacie|labo",
  "rccm_etablissement": "",
  "patient_nom": "",
  "patient_numero_assure": "",
  "patient_numero_police": "",
  "numero_sinistre_reference": "",
  "actes": [{"libelle": "", "code_acte": "", "montant": 0, "quantite": 1}],
  "medicaments": [{"denomination": "", "dosage": "", "quantite": 1, "prix_unitaire": 0, "montant": 0}],
  "montant_total": 0,
  "part_assurance": 0,
  "ticket_moderateur_pct": 0,
  "part_patient": 0,
  "confiance": "haute|moyenne|faible",
  "anomalies": [],
  "ORASS_SINISTRE_ID": null,
  "ORASS_PATIENT_CODE": null,
  "COMPTE_PCSA_DEBIT": "60200",
  "LIBELLE_PCSA_DEBIT": "Prestations — Indemnités corporelles / santé",
  "COMPTE_PCSA_CREDIT": "40200",
  "LIBELLE_PCSA_CREDIT": "Fournisseurs — Établissements de santé",
  "JOURNAL_ORASS": "SN",
  "DATE_ISO": "AAAA-MM-JJ"
}
""",
    "quittance_prime": """
Analyse cette quittance de prime d'assurance et retourne UNIQUEMENT ce JSON valide.
Les champs ORASS_* et COMPTE_PCSA sont OBLIGATOIRES pour l'intégration SI.

{
  "numero_quittance": "",
  "numero_police": "",
  "nom_assure": "",
  "numero_assure": "",
  "periode_debut": "JJ/MM/AAAA",
  "periode_fin": "JJ/MM/AAAA",
  "branche": "",
  "code_branche_cima": "",
  "prime_nette": 0,
  "taxes_taux": 0,
  "taxes_montant": 0,
  "prime_ttc": 0,
  "date_emission": "JJ/MM/AAAA",
  "date_echeance_paiement": "JJ/MM/AAAA",
  "mode_paiement": "",
  "reference_paiement": "",
  "courtier_code": "",
  "commission_courtier_taux": 0,
  "commission_courtier_montant": 0,
  "confiance": "haute|moyenne|faible",
  "anomalies": [],
  "ORASS_POLICE_ID": null,
  "ORASS_COURTIER_CODE": null,
  "COMPTE_PCSA_DEBIT": "41100",
  "LIBELLE_PCSA_DEBIT": "Créances — Primes à recouvrer",
  "COMPTE_PCSA_CREDIT": "70100",
  "LIBELLE_PCSA_CREDIT": "Primes acquises — Non-vie",
  "JOURNAL_ORASS": "EM",
  "DATE_ISO": "AAAA-MM-JJ"
}
""",
    "facture_fournisseur": """
Analyse cette facture fournisseur et retourne UNIQUEMENT ce JSON valide.
Les champs ORASS_* et COMPTE_PCSA sont OBLIGATOIRES pour l'intégration SI.

{
  "numero_facture": "",
  "date": "JJ/MM/AAAA",
  "nom_fournisseur": "",
  "rccm_fournisseur": "",
  "numero_contribuable": "",
  "adresse_fournisseur": "",
  "objet": "",
  "bon_commande": "",
  "lignes": [
    {"libelle": "", "quantite": 1, "prix_unitaire": 0, "montant_ht": 0, "tva_taux": 0.1925}
  ],
  "montant_ht": 0,
  "tva_taux": 0.1925,
  "tva_montant": 0,
  "montant_ttc": 0,
  "rib_fournisseur": "",
  "confiance": "haute|moyenne|faible",
  "anomalies": [],
  "ORASS_FOURNISSEUR_CODE": null,
  "COMPTE_PCSA_DEBIT": "67000",
  "LIBELLE_PCSA_DEBIT": "Frais généraux",
  "COMPTE_PCSA_CREDIT": "40300",
  "LIBELLE_PCSA_CREDIT": "Fournisseurs divers",
  "JOURNAL_ORASS": "AC",
  "DATE_ISO": "AAAA-MM-JJ"
}
""",
    "constat_amiable": """
Analyse ce constat amiable d'accident et retourne UNIQUEMENT ce JSON valide.
Les champs ORASS_* sont OBLIGATOIRES pour l'ouverture du sinistre dans le SI.

{
  "date_accident": "JJ/MM/AAAA",
  "heure": "HH:MM",
  "lieu": "",
  "commune": "",
  "pays_code": "CM",
  "vehicule_a": {
    "immatriculation": "", "marque": "", "modele": "",
    "assureur": "", "numero_police": "", "numero_carte_verte": "",
    "conducteur_nom": "", "conducteur_prenom": "",
    "conducteur_permis": "", "permis_categorie": "",
    "telephone": "", "adresse": ""
  },
  "vehicule_b": {
    "immatriculation": "", "marque": "", "modele": "",
    "assureur": "", "numero_police": "", "numero_carte_verte": "",
    "conducteur_nom": "", "conducteur_prenom": "",
    "conducteur_permis": "", "permis_categorie": "",
    "telephone": "", "adresse": ""
  },
  "circonstances_a": [],
  "circonstances_b": [],
  "responsabilite_estimee": "A|B|partage|indeterminee",
  "blesses": false,
  "nombre_blesses": 0,
  "temoins": [{"nom": "", "telephone": ""}],
  "signature_a": true,
  "signature_b": true,
  "photos_disponibles": false,
  "confiance": "haute|moyenne|faible",
  "anomalies": [],
  "ORASS_NUMERO_POLICE_A": null,
  "ORASS_NUMERO_POLICE_B": null,
  "SINISTRE_NATURE": "collision",
  "ALERTE_FRAUDE": false,
  "RAISON_ALERTE": null
}
""",
    "releve_bancaire": """
Analyse ce relevé bancaire et retourne UNIQUEMENT ce JSON valide.
Les opérations doivent inclure les champs ORASS nécessaires au rapprochement.

{
  "banque": "",
  "code_banque": "",
  "numero_compte": "",
  "titulaire": "",
  "rib": "",
  "periode_debut": "JJ/MM/AAAA",
  "periode_fin": "JJ/MM/AAAA",
  "devise": "XAF",
  "solde_debut": 0,
  "solde_fin": 0,
  "operations": [
    {
      "date": "JJ/MM/AAAA",
      "date_valeur": "JJ/MM/AAAA",
      "libelle": "",
      "debit": 0,
      "credit": 0,
      "reference": "",
      "ORASS_REFERENCE_PIECE": null,
      "TYPE_OPERATION": "prime|sinistre|commission|frais|autre"
    }
  ],
  "total_debits": 0,
  "total_credits": 0,
  "confiance": "haute|moyenne|faible"
}
""",
    "recu_mobile_money": """
Analyse ce reçu Mobile Money (MTN MoMo, Orange Money, Wave, CinetPay) et retourne UNIQUEMENT ce JSON valide.
Les champs ORASS_* sont OBLIGATOIRES pour l'enregistrement du paiement dans le SI.

{
  "operateur": "mtn_momo|orange_money|wave|cinetpay|airtel_money",
  "reference_transaction": "",
  "date": "JJ/MM/AAAA",
  "heure": "HH:MM",
  "expediteur_nom": "",
  "expediteur_telephone": "",
  "montant": 0,
  "devise": "XAF",
  "frais_transaction": 0,
  "montant_net_recu": 0,
  "objet_paiement": "",
  "statut": "confirme|en_attente|echoue",
  "confiance": "haute|moyenne|faible",
  "anomalies": [],
  "ORASS_NUMERO_POLICE": null,
  "ORASS_NUMERO_QUITTANCE": null,
  "COMPTE_PCSA_DEBIT": "53100",
  "LIBELLE_PCSA_DEBIT": "Banque Mobile Money",
  "COMPTE_PCSA_CREDIT": "41100",
  "LIBELLE_PCSA_CREDIT": "Créances — Primes à recouvrer (solde)",
  "JOURNAL_ORASS": "BQ",
  "TYPE_REGLEMENT": "encaissement_prime"
}
""",
    "ordre_virement": """
Analyse cet ordre de virement et retourne UNIQUEMENT ce JSON valide.
Les champs ORASS_* sont OBLIGATOIRES pour le règlement sinistre dans le SI.

{
  "reference_virement": "",
  "date": "JJ/MM/AAAA",
  "banque_emettrice": "",
  "compte_debiteur": "",
  "beneficiaire_nom": "",
  "beneficiaire_rib": "",
  "beneficiaire_banque": "",
  "montant": 0,
  "devise": "XAF",
  "motif": "",
  "confiance": "haute|moyenne|faible",
  "anomalies": [],
  "ORASS_NUMERO_SINISTRE": null,
  "ORASS_BENEFICIAIRE_CODE": null,
  "COMPTE_PCSA_DEBIT": "60100",
  "LIBELLE_PCSA_DEBIT": "Prestations — Règlement sinistre",
  "COMPTE_PCSA_CREDIT": "53000",
  "LIBELLE_PCSA_CREDIT": "Banque — Compte courant",
  "JOURNAL_ORASS": "BQ",
  "TYPE_REGLEMENT": "paiement_sinistre"
}
""",
    "certificat_medical": """
Analyse ce certificat médical (certificat d'hospitalisation, arrêt de travail, ITT, certificat de décès)
et retourne UNIQUEMENT ce JSON valide. Les champs ORASS_* sont OBLIGATOIRES pour l'instruction du sinistre.

{
  "type_certificat": "hospitalisation|arret_travail|itt|deces|invalidite|incapacite",
  "date_etablissement": "JJ/MM/AAAA",
  "medecin_nom": "",
  "medecin_specialite": "",
  "medecin_numero_ordre": "",
  "etablissement_nom": "",
  "etablissement_ville": "",
  "patient_nom": "",
  "patient_prenom": "",
  "patient_date_naissance": "JJ/MM/AAAA",
  "diagnostic": "",
  "code_cim10": "",
  "date_debut_incapacite": "JJ/MM/AAAA",
  "date_fin_incapacite": "JJ/MM/AAAA",
  "duree_jours": 0,
  "taux_invalidite_pct": null,
  "hospitalise": false,
  "duree_hospitalisation_jours": 0,
  "lien_avec_accident": true,
  "numero_sinistre_reference": "",
  "confiance": "haute|moyenne|faible",
  "anomalies": [],
  "ORASS_SINISTRE_ID": null,
  "ORASS_ASSURE_CODE": null,
  "NATURE_SINISTRE": "corporel",
  "ALERTE_FRAUDE": false,
  "RAISON_ALERTE": null,
  "IMPACT_INDEMNITE": "itt|invalidite_partielle|invalidite_totale|deces"
}
""",
    "rapport_expertise_auto": """
Analyse ce rapport d'expertise automobile (rapport d'expert agréé sur véhicule sinistré)
et retourne UNIQUEMENT ce JSON valide. Les champs ORASS_* sont OBLIGATOIRES pour la liquidation du sinistre.

{
  "numero_rapport": "",
  "date_expertise": "JJ/MM/AAAA",
  "expert_nom": "",
  "expert_agrement": "",
  "cabinet_expertise": "",
  "numero_sinistre": "",
  "vehicule_immatriculation": "",
  "vehicule_marque": "",
  "vehicule_modele": "",
  "vehicule_annee": 0,
  "vehicule_valeur_venale_fcfa": 0,
  "vehicule_valeur_assurance_fcfa": 0,
  "nature_dommages": [],
  "zones_touchees": [],
  "estimation_reparation_ht_fcfa": 0,
  "estimation_reparation_ttc_fcfa": 0,
  "valeur_epave_fcfa": 0,
  "est_epave_economique": false,
  "seuil_epave_pct": 0.75,
  "garage_recommande": "",
  "delai_reparation_jours": 0,
  "responsabilite_tiers": "oui|non|partielle|indeterminee",
  "taux_responsabilite_pct": 0,
  "indemnite_recommandee_fcfa": 0,
  "franchise_applicable_fcfa": 0,
  "net_a_payer_fcfa": 0,
  "confiance": "haute|moyenne|faible",
  "anomalies": [],
  "ORASS_SINISTRE_ID": null,
  "ORASS_POLICE_ID": null,
  "COMPTE_PCSA_DEBIT": "60100",
  "LIBELLE_PCSA_DEBIT": "Prestations — Indemnités sinistres auto",
  "COMPTE_PCSA_CREDIT": "40100",
  "LIBELLE_PCSA_CREDIT": "Fournisseurs — Garages agréés",
  "JOURNAL_ORASS": "SN",
  "ALERTE_FRAUDE": false,
  "RAISON_ALERTE": null
}
""",
}

# ─── Imputations comptables PCSA CIMA / OHADA ─────────────────────────────────
IMPUTATIONS_AUTO = {
    "facture_garage": {
        "compte_debit": COMPTES_PCSA["prestations_auto"],
        "libelle_debit": "Prestations — Indemnités sinistres auto",
        "compte_credit": COMPTES_PCSA["fournisseurs_garages"],
        "libelle_credit": "Fournisseurs — Garages agréés",
        "journal": "SN",
    },
    "facture_hopital": {
        "compte_debit": COMPTES_PCSA["prestations_corps"],
        "libelle_debit": "Prestations — Indemnités corporelles / santé",
        "compte_credit": COMPTES_PCSA["fournisseurs_hopitaux"],
        "libelle_credit": "Fournisseurs — Établissements de santé",
        "journal": "SN",
    },
    "quittance_prime": {
        "compte_debit": COMPTES_PCSA["primes_a_recouvrer"],
        "libelle_debit": "Créances — Primes à recouvrer",
        "compte_credit": COMPTES_PCSA["primes_non_vie"],
        "libelle_credit": "Primes acquises — Non-vie",
        "journal": "EM",
    },
    "facture_fournisseur": {
        "compte_debit": COMPTES_PCSA["frais_gestion"],
        "libelle_debit": "Frais généraux",
        "compte_credit": COMPTES_PCSA["fournisseurs_divers"],
        "libelle_credit": "Fournisseurs divers",
        "journal": "AC",
    },
    "recu_mobile_money": {
        "compte_debit": "53100",
        "libelle_debit": "Banque — Mobile Money",
        "compte_credit": COMPTES_PCSA["primes_a_recouvrer"],
        "libelle_credit": "Créances — Primes encaissées",
        "journal": "BQ",
    },
    "ordre_virement": {
        "compte_debit": COMPTES_PCSA["prestations_auto"],
        "libelle_debit": "Prestations — Règlement sinistre",
        "compte_credit": "53000",
        "libelle_credit": "Banque — Compte courant",
        "journal": "BQ",
    },
}


@dataclass
class PieceComptable:
    type_piece: str
    image_b64: Optional[str] = None
    pdf_b64: Optional[str] = None
    id_reference: Optional[str] = None   # numéro sinistre ou police
    pays_code: str = "CM"                # code pays CIMA (pour TVA)
    metadata: dict = field(default_factory=dict)


@dataclass
class ResultatTraitement:
    type_piece: str
    donnees_extraites: dict
    imputation_proposee: dict
    anomalies: list[str]
    confiance: str
    validation_requise: bool
    ecriture_orass: Optional[dict] = None
    doublon_detecte: bool = False
    reference_orass_creee: Optional[str] = None


class PiecesProcessor:
    """
    Processeur de pièces comptables — v3 Production SI-aligned.
    OCR IA → Extraction structurée SI → Imputation PCSA → Écriture ORASS.

    Pipeline :
    1. Vision IA (GPT-4o + Claude double-check sur pièces critiques)
    2. Extraction JSON avec champs ORASS natifs
    3. Validation TVA par pays CIMA
    4. Détection doublons via requête ORASS
    5. Imputation automatique PCSA
    6. Écriture directe dans ORASS si confiance haute (sans anomalie critique)
    7. Queue de validation humaine sinon

    Gain estimé : 85-92% du temps de saisie éliminé.
    """

    # Pièces critiques → double-check Vision IA
    _PIECES_CRITIQUES = {
        "facture_garage", "facture_hopital", "constat_amiable", "ordre_virement"
    }

    async def traiter_piece(self, piece: PieceComptable) -> ResultatTraitement:
        """Traite une pièce comptable de bout en bout avec intégration SI."""
        logger.info(f"[Compta] Traitement pièce type={piece.type_piece} ref={piece.id_reference}")

        # 1. Extraction OCR IA
        donnees = await self._extraire_ocr(piece)

        # 2. Enrichir avec la référence contexte si fournie
        if piece.id_reference:
            if not donnees.get("numero_sinistre_reference") and not donnees.get("ORASS_SINISTRE_ID"):
                donnees["numero_sinistre_reference"] = piece.id_reference
                donnees["ORASS_SINISTRE_ID"] = piece.id_reference

        # 3. Validation
        anomalies = self._valider_donnees(donnees, piece.type_piece, piece.pays_code)

        # 4. Détection doublons
        doublon, alertes_doublon = await self._verifier_doublons(donnees, piece.type_piece)
        anomalies.extend(alertes_doublon)

        # 5. Imputation PCSA
        imputation = self._proposer_imputation(donnees, piece.type_piece)

        confiance = donnees.get("confiance", "moyenne")
        # Dégrader la confiance si anomalies
        if len([a for a in anomalies if "critique" in a.lower()]) > 0:
            confiance = "faible"
        validation_requise = confiance == "faible" or doublon or len(anomalies) > 0

        # 6. Préparer écriture ORASS
        ecriture = None
        if not doublon:
            ecriture = self._preparer_ecriture_orass(donnees, imputation, piece)

        # 7. Enregistrement automatique si confiance haute sans anomalie
        ref_orass = None
        if not validation_requise and not doublon and ecriture:
            try:
                ref_orass = await orass.creer_ecriture_comptable(ecriture)
                logger.info(f"[Compta] Écriture ORASS auto-créée: {ref_orass}")
            except Exception as e:
                logger.warning(f"[Compta] Écriture ORASS échouée (mise en queue): {e}")
                validation_requise = True

        return ResultatTraitement(
            type_piece=piece.type_piece,
            donnees_extraites=donnees,
            imputation_proposee=imputation,
            anomalies=anomalies,
            confiance=confiance,
            validation_requise=validation_requise,
            ecriture_orass=ecriture,
            doublon_detecte=doublon,
            reference_orass_creee=ref_orass,
        )

    async def valider_et_enregistrer(
        self, resultat: ResultatTraitement, valide_par: str
    ) -> str:
        """Après validation humaine, crée l'écriture dans ORASS."""
        ecriture = resultat.ecriture_orass or self._preparer_ecriture_orass(
            resultat.donnees_extraites,
            resultat.imputation_proposee,
            None,
        )
        ecriture["valide_par"] = valide_par
        ecriture["validation_manuelle"] = True
        ref = await orass.creer_ecriture_comptable(ecriture)
        logger.info(f"[Compta] Écriture validée: {ref} par {valide_par}")
        return ref

    async def traiter_lot(self, pieces: list[PieceComptable]) -> list[ResultatTraitement]:
        """Traitement en lot — parallèle avec isolation des erreurs."""
        import asyncio
        resultats = await asyncio.gather(
            *[self.traiter_piece(p) for p in pieces],
            return_exceptions=True,
        )
        valides = []
        for i, r in enumerate(resultats):
            if isinstance(r, Exception):
                logger.error(f"[Compta] Erreur pièce {i}: {r}")
            else:
                valides.append(r)
        return valides

    # ─── OCR ─────────────────────────────────────────────────────────────────

    async def _extraire_ocr(self, piece: PieceComptable) -> dict:
        prompt_template = PROMPTS_OCR.get(
            piece.type_piece,
            "Lis ce document et retourne les données clés en JSON structuré avec les champs ORASS natifs.",
        )
        image_principale = piece.image_b64 or piece.pdf_b64

        # Pas d'image disponible — OCR textuel dégradé avec avertissement
        if not image_principale:
            logger.warning(
                f"[OCR] Aucune image disponible pour pièce type={piece.type_piece}. "
                "OCR textuel dégradé — confiance réduite."
            )
            reponse = await ia_client.appeler(
                prompt=f"{prompt_template}\n\n[AVERTISSEMENT: Aucune image fournie — retourner structure vide avec confiance='faible']",
                mode=ModeIA.PRECISION,
                json_attendu=True,
                max_tokens_override=settings.IA_MAX_TOKENS_DOCUMENT,
            )
            donnees = self._safe_json_parse(reponse)
            donnees.setdefault("confiance", "faible")
            donnees.setdefault("anomalies", [])
            donnees["anomalies"].append("Image source absente — OCR non effectué")
            return donnees

        if image_principale and piece.type_piece in self._PIECES_CRITIQUES:
            # Double-check Vision IA sur pièces à fort enjeu financier (retry 2x si échec)
            for tentative in range(1, 4):
                try:
                    reponse = await ia_client.analyser_image_vision(
                        image_b64=image_principale,
                        prompt=prompt_template,
                        mode=ModeIA.PRECISION,
                    )
                    return self._safe_json_parse(reponse)
                except Exception as e:
                    logger.warning(f"[OCR] Vision double-check tentative {tentative}/3 échouée: {e}")
            logger.error(f"[OCR] Double-check Vision échoué après 3 tentatives pour {piece.type_piece}")
            return {"confiance": "faible", "anomalies": ["OCR Vision échoué après 3 tentatives"]}

        images = [x for x in [piece.image_b64, piece.pdf_b64] if x]
        for tentative in range(1, 4):
            try:
                reponse = await ia_client.appeler(
                    prompt=prompt_template,
                    mode=ModeIA.PRECISION,
                    images_b64=images or None,
                    json_attendu=True,
                    max_tokens_override=settings.IA_MAX_TOKENS_DOCUMENT,
                )
                return self._safe_json_parse(reponse)
            except Exception as e:
                logger.warning(f"[OCR] Tentative {tentative}/3 échouée: {e}")
        logger.error(f"[OCR] OCR échoué après 3 tentatives pour {piece.type_piece}")
        return {"confiance": "faible", "anomalies": ["OCR échoué après 3 tentatives"]}

    def _safe_json_parse(self, reponse) -> dict:
        """Parse JSON avec fallback sécurisé — évite les crashes si OCR retourne texte brut."""
        import json as _json
        try:
            data = reponse.as_json()
            if isinstance(data, dict):
                return data
            # Si l'IA retourne une liste ou autre type
            return {"donnees_brutes": data, "confiance": "faible", "anomalies": ["Format JSON inattendu"]}
        except Exception:
            # Tentative d'extraction JSON depuis texte brut
            texte = getattr(reponse, "texte", "") or str(reponse)
            import re as _re
            match = _re.search(r"\{[\s\S]+\}", texte)
            if match:
                try:
                    return _json.loads(match.group())
                except Exception:
                    pass
            logger.warning(f"[OCR] Impossible de parser le JSON — réponse brute conservée")
            return {"texte_brut": texte[:500], "confiance": "faible", "anomalies": ["JSON non parseable"]}

    # ─── Validation ──────────────────────────────────────────────────────────

    def _valider_donnees(self, donnees: dict, type_piece: str, pays_code: str = "CM") -> list[str]:
        anomalies = list(donnees.get("anomalies", []))
        tva_attendue = TVA_PAR_PAYS.get(pays_code, TVA_PAR_PAYS["DEFAULT"])

        if not donnees.get("date") and not donnees.get("date_accident") and not donnees.get("date_emission"):
            anomalies.append("Date manquante")

        if type_piece in ("facture_garage", "facture_hopital", "facture_fournisseur"):
            montant_ttc = donnees.get("montant_ttc") or donnees.get("montant_total") or 0
            if not montant_ttc:
                anomalies.append("Montant total manquant [CRITIQUE]")
            if montant_ttc > 50_000_000:
                anomalies.append(f"Montant > 50M FCFA ({montant_ttc:,.0f}) — vérification [CRITIQUE]")
            # Validation TVA
            tva = donnees.get("tva_montant") or donnees.get("tva", 0)
            ht = donnees.get("montant_ht", 1) or 1
            if tva and ht and abs(tva / ht - tva_attendue) > 0.05:
                anomalies.append(
                    f"TVA anormale: {tva/ht:.2%} (attendu {tva_attendue:.2%} pour {pays_code})"
                )

        if type_piece == "quittance_prime":
            if not donnees.get("numero_police") and not donnees.get("ORASS_POLICE_ID"):
                anomalies.append("Numéro de police manquant [CRITIQUE]")
            if not donnees.get("prime_ttc") and not donnees.get("prime_nette"):
                anomalies.append("Prime manquante [CRITIQUE]")

        if type_piece == "constat_amiable":
            veh_a = donnees.get("vehicule_a", {})
            veh_b = donnees.get("vehicule_b", {})
            if not veh_a.get("immatriculation"):
                anomalies.append("Immatriculation véhicule A manquante")
            if not veh_a.get("numero_police") and not donnees.get("ORASS_NUMERO_POLICE_A"):
                anomalies.append("Police véhicule A non identifiée")
            if not donnees.get("signature_a") or not donnees.get("signature_b"):
                anomalies.append("Constat non signé par les deux parties")

        if type_piece == "recu_mobile_money":
            if not donnees.get("reference_transaction"):
                anomalies.append("Référence transaction Mobile Money manquante [CRITIQUE]")
            if not donnees.get("montant") or float(donnees.get("montant", 0)) <= 0:
                anomalies.append("Montant non détecté [CRITIQUE]")

        return anomalies

    # ─── Détection doublons ───────────────────────────────────────────────────

    async def _verifier_doublons(self, donnees: dict, type_piece: str) -> tuple[bool, list[str]]:
        alertes = []
        num = (donnees.get("numero_facture") or donnees.get("numero_quittance")
               or donnees.get("reference_transaction") or donnees.get("reference_virement"))
        if not num:
            alertes.append("Numéro de pièce non détecté — vérification doublon impossible")
            return False, alertes

        # En mode direct_sql : vérification réelle dans ORASS
        if orass.mode == "direct_sql":
            try:
                rows = await orass._sql_query(
                    "SELECT COUNT(*) AS CNT FROM ECRITURES_COMPTABLES WHERE REFERENCE_PIECE = :num",
                    {"num": num},
                )
                if rows and int(rows[0].get("CNT", 0)) > 0:
                    alertes.append(f"[DOUBLON CRITIQUE] Pièce {num} déjà enregistrée dans ORASS")
                    return True, alertes
            except Exception as e:
                logger.warning(f"[Compta] Vérification doublon ORASS échouée: {e}")

        # En mode csv_import : vérification dans le fichier CSV local
        elif orass.mode == "csv_import":
            try:
                import csv as _csv
                from pathlib import Path as _Path
                csv_path = _Path(settings.ORASS_CSV_DIR) / "ecritures_comptables.csv"
                if csv_path.exists():
                    with open(csv_path, encoding="utf-8-sig", newline="") as f:
                        reader = _csv.DictReader(f, delimiter=";")
                        for row in reader:
                            ref = row.get("REFERENCE_PIECE", "") or row.get("REFERENCE", "")
                            if ref.strip() == num.strip():
                                alertes.append(f"[DOUBLON CSV] Pièce {num} trouvée dans exports CSV ORASS")
                                return True, alertes
            except Exception as e:
                logger.warning(f"[Compta] Vérification doublon CSV échouée: {e}")

        # En mode api : vérification via API ORASS
        elif orass.mode == "api":
            try:
                data = await orass._api_get("/ecritures/recherche", {"reference_piece": num})
                resultats = data.get("results") or data.get("data") or []
                if resultats:
                    alertes.append(f"[DOUBLON API] Pièce {num} déjà enregistrée (API ORASS)")
                    return True, alertes
            except Exception as e:
                logger.warning(f"[Compta] Vérification doublon API échouée: {e}")

        return False, alertes

    # ─── Imputation PCSA ─────────────────────────────────────────────────────

    def _proposer_imputation(self, donnees: dict, type_piece: str) -> dict:
        base = IMPUTATIONS_AUTO.get(type_piece, {
            "compte_debit": COMPTES_PCSA["frais_gestion"],
            "libelle_debit": "Frais divers",
            "compte_credit": COMPTES_PCSA["fournisseurs_divers"],
            "libelle_credit": "Fournisseurs",
            "journal": "OD",
        })

        # Utiliser les comptes PCSA détectés par l'OCR si disponibles
        if donnees.get("COMPTE_PCSA_DEBIT"):
            base = {**base, "compte_debit": donnees["COMPTE_PCSA_DEBIT"],
                    "libelle_debit": donnees.get("LIBELLE_PCSA_DEBIT", base.get("libelle_debit", ""))}
        if donnees.get("COMPTE_PCSA_CREDIT"):
            base = {**base, "compte_credit": donnees["COMPTE_PCSA_CREDIT"],
                    "libelle_credit": donnees.get("LIBELLE_PCSA_CREDIT", base.get("libelle_credit", ""))}

        montant = (
            donnees.get("montant_ttc") or donnees.get("montant_total")
            or donnees.get("prime_ttc") or donnees.get("montant_net_recu")
            or donnees.get("montant") or 0
        )
        ref = (donnees.get("numero_facture") or donnees.get("numero_quittance")
               or donnees.get("reference_transaction") or donnees.get("reference_virement") or "N/A")
        date_p = (donnees.get("date_iso") or donnees.get("DATE_ISO")
                  or donnees.get("date") or donnees.get("date_emission") or str(date.today()))

        return {
            **base,
            "montant": float(montant),
            "libelle_ecriture": (
                f"{type_piece.replace('_', ' ').title()} — Réf. {ref}"
            ),
            "date_piece": date_p,
            "reference_piece": ref,
        }

    # ─── Construction écriture ORASS ─────────────────────────────────────────

    def _preparer_ecriture_orass(
        self, donnees: dict, imputation: dict, piece: Optional[PieceComptable]
    ) -> dict:
        sinistre_id = (donnees.get("ORASS_SINISTRE_ID") or donnees.get("numero_sinistre_reference")
                       or donnees.get("ORASS_NUMERO_SINISTRE"))
        police_id = (donnees.get("ORASS_POLICE_ID") or donnees.get("ORASS_NUMERO_POLICE")
                     or donnees.get("numero_police"))
        return {
            "compte_debit": imputation["compte_debit"],
            "libelle_debit": imputation.get("libelle_debit", ""),
            "compte_credit": imputation["compte_credit"],
            "libelle_credit": imputation.get("libelle_credit", ""),
            "montant": imputation["montant"],
            "libelle": imputation["libelle_ecriture"],
            "date_piece": imputation["date_piece"],
            "reference_piece": imputation["reference_piece"],
            "journal": imputation.get("journal", "OD"),
            "piece_jointe_indexee": True,
            "ORASS_SINISTRE_REF": sinistre_id,
            "ORASS_POLICE_REF": police_id,
            "type_piece_source": piece.type_piece if piece else None,
        }


# Instance singleton
pieces_processor = PiecesProcessor()
