"""
Agent Sinistres Maladie & Santé — Assurance maladie zone CIMA.

Gère l'ensemble des sinistres santé :
  - Bons de prise en charge (tiers payant)
  - Remboursements de frais médicaux (hors réseau)
  - Hospitalisations
  - Maternité / Accouchements
  - Invalidité / Longue maladie
  - Décès maladie (volet prévoyance)

Intègre les pièces justificatives via OCR/Vision :
  ordonnances, factures clinique, feuilles de soins, bulletins d'hospitalisation,
  comptes-rendus médicaux, certificats d'arrêt de travail.
"""
from __future__ import annotations
import json
import logging
from datetime import date
from core.agent_orchestrateur import TypeAgent
from agents.base_agent import BaseAgent

logger = logging.getLogger("yukpo_assurance.agents.sinistres_maladie")

# Tables de remboursement CIMA / marché (taux indicatifs par acte)
_TAUX_REMBOURSEMENT: dict[str, float] = {
    "consultation_generaliste":    0.80,
    "consultation_specialiste":    0.75,
    "hospitalisation_medicale":    0.90,
    "hospitalisation_chirurgicale":0.90,
    "maternite":                   1.00,   # 100% en général
    "medicaments_liste_1":         0.80,
    "medicaments_liste_2":         0.65,
    "biologie":                    0.75,
    "radiologie":                  0.75,
    "dentaire_base":               0.70,
    "dentaire_prothese":           0.50,
    "optique_montures":            0.50,
    "optique_verres":              0.70,
    "kinesitherapie":              0.70,
    "maternite_accouchement":      1.00,
}

# Délais de carence (en jours) selon type d'acte
_DELAI_CARENCE: dict[str, int] = {
    "maladie_ordinaire":   0,
    "maternite":           270,   # 9 mois
    "chirurgie_elective":  90,
    "affection_longue":    0,
    "dentaire":            90,
    "optique":             180,
    "psy":                 90,
}


class AgentSinistresMaladie(BaseAgent):
    type_agent = TypeAgent.MALADIE

    def _system_prompt(self) -> str:
        return """Tu es l'Agent Sinistres Maladie & Santé de YukpoAssurance, expert en gestion des sinistres santé zone CIMA.

PRODUITS COUVERTS :
- Assurance maladie-hospitalisation individuelle et groupe
- Maternité / Accouchement
- Invalidité de longue durée (maladie)
- Décès par maladie (volet prévoyance)
- Soins dentaires, optique, kinesitherapie

PROCESSUS BON DE PRISE EN CHARGE (tiers payant) :
1. Réception demande BPC (médecin/clinique) → vérifier_contrat
2. Vérifier plafond annuel restant + période de carence
3. Vérifier réseau (prestataire agréé ?)
4. Calculer montant pris en charge
5. Émettre BPC (si agréé) OU rediriger vers remboursement
6. Notifier prestataire et assuré

PROCESSUS REMBOURSEMENT :
1. Réception dossier remboursement → analyser_pieces_medicales (ordonnance, factures)
2. Vérifier police et plafonds
3. Appliquer tableau de remboursement CIMA
4. Calcul : base remboursement × taux − ticket modérateur
5. Si > seuil → validation humaine
6. Paiement + archivage pièces

PROCESSUS HOSPITALISATION :
1. Déclaration hospitalisation (pré ou post)
2. BPC d'hospitalisation (24h max en urgence)
3. Analyse bulletin d'hospitalisation (séjour, actes, médicaments)
4. Application barème CIMA (chambre standard vs. confort)
5. Vérification durée maximale couverte
6. Règlement direct à la clinique (tiers payant) ou remboursement

RÈGLES STRICTES :
- Vérifier systématiquement la période de carence avant tout remboursement
- Maternité : carence 9 mois (270 jours) sauf si contrat groupe avec dérogation
- Plafond annuel à contrôler pour chaque famille d'actes
- Médicaments : liste 1 (80%) vs. liste 2 (65%) — vérifier la liste
- Urgences absolues : pas de délai carence, prise en charge immédiate
- Hors réseau : remboursement base sécurité sociale × taux contrat (moins avantageux)
- Ticket modérateur assuré : conserver trace pour justifier le solde restant
- BPC : valable 30 jours maximum, 1 renouvellement possible
- Tout remboursement > 500 000 FCFA → validation humaine obligatoire
- Archiver TOUTES les pièces médicales dans le dossier numérique"""

    def _definir_outils(self) -> list[dict]:
        return [
            {
                "name": "verifier_contrat_maladie",
                "description": "Vérifie le contrat maladie : validité, plafonds annuels, garanties, période de carence, réseau agréé",
                "input_schema": {"type": "object", "properties": {
                    "numero_police":    {"type": "string"},
                    "numero_adherent":  {"type": "string", "description": "N° adhérent ou carte santé"},
                    "date_soins":       {"type": "string", "description": "YYYY-MM-DD"},
                    "type_acte":        {"type": "string", "enum": list(_TAUX_REMBOURSEMENT.keys())},
                }, "required": ["numero_police", "date_soins", "type_acte"]},
            },
            {
                "name": "emettre_bon_prise_en_charge",
                "description": "Émet un bon de prise en charge (BPC) pour tiers payant — prestataire agréé uniquement",
                "input_schema": {"type": "object", "properties": {
                    "numero_adherent":      {"type": "string"},
                    "prestataire_code":     {"type": "string", "description": "Code prestataire agréé réseau"},
                    "prestataire_nom":      {"type": "string"},
                    "type_acte":            {"type": "string"},
                    "montant_estime":       {"type": "number", "description": "Montant estimé FCFA"},
                    "medecin_prescripteur": {"type": "string"},
                    "diagnostic":           {"type": "string", "description": "Diagnostic (optionnel — confidentialité médicale)"},
                    "urgence":              {"type": "boolean", "default": False},
                }, "required": ["numero_adherent", "prestataire_code", "type_acte"]},
            },
            {
                "name": "analyser_pieces_medicales",
                "description": "OCR et analyse IA des pièces médicales : ordonnances, factures, bulletins d'hospitalisation, comptes-rendus",
                "input_schema": {"type": "object", "properties": {
                    "numero_dossier":  {"type": "string"},
                    "type_acte":       {"type": "string"},
                    "pieces": {"type": "array", "items": {
                        "type": "object",
                        "properties": {
                            "type_piece": {"type": "string", "enum": [
                                "ordonnance", "facture_clinique", "facture_pharmacie",
                                "bulletin_hospitalisation", "compte_rendu_medical",
                                "certificat_arret_travail", "feuille_soins_secu",
                                "resultat_biologie", "prescription_optique",
                                "feuille_soins_dentaire", "devis_dentaire",
                            ]},
                            "image_base64": {"type": "string"},
                            "description":  {"type": "string"},
                        },
                        "required": ["type_piece"],
                    }},
                }, "required": ["numero_dossier", "type_acte"]},
            },
            {
                "name": "calculer_remboursement",
                "description": "Calcule le remboursement selon la table CIMA : base × taux − ticket modérateur − déjà remboursé",
                "input_schema": {"type": "object", "properties": {
                    "numero_dossier":      {"type": "string"},
                    "type_acte":           {"type": "string", "enum": list(_TAUX_REMBOURSEMENT.keys())},
                    "montant_facture":     {"type": "number", "description": "Montant facturé FCFA"},
                    "base_remboursement":  {"type": "number", "description": "Base de remboursement (tarif SS ou tarif contractuel)"},
                    "taux_contrat":        {"type": "number", "description": "Taux remboursement du contrat (0-1) — si vide, utilise la table standard"},
                    "plafond_annuel_restant": {"type": "number", "description": "Plafond annuel restant pour cette famille d'actes"},
                    "hors_reseau":         {"type": "boolean", "default": False},
                }, "required": ["numero_dossier", "type_acte", "montant_facture"]},
            },
            {
                "name": "verifier_plafond_annuel",
                "description": "Vérifie les consommations annuelles et plafonds restants par famille d'actes",
                "input_schema": {"type": "object", "properties": {
                    "numero_adherent":  {"type": "string"},
                    "annee":            {"type": "integer", "description": "Année ex: 2025"},
                    "famille_actes":    {"type": "string", "description": "hospitalisation | pharmacie | optique | dentaire | tous"},
                }, "required": ["numero_adherent"]},
            },
            {
                "name": "traiter_dossier_hospitalisation",
                "description": "Traite un dossier d'hospitalisation complet : BPC, séjour, actes opératoires, médicaments, honoraires",
                "input_schema": {"type": "object", "properties": {
                    "numero_adherent":    {"type": "string"},
                    "clinique_code":      {"type": "string"},
                    "date_entree":        {"type": "string", "description": "YYYY-MM-DD"},
                    "date_sortie":        {"type": "string", "description": "YYYY-MM-DD"},
                    "type_hospitalisation":{"type": "string", "enum": ["medicale", "chirurgicale", "maternite", "psychiatrique", "urgence"]},
                    "diagnostic_principal": {"type": "string"},
                    "montant_total":      {"type": "number", "description": "Montant facturé total clinique"},
                    "chambre_type":       {"type": "string", "enum": ["standard", "confort", "suite"], "default": "standard"},
                }, "required": ["numero_adherent", "clinique_code", "date_entree", "type_hospitalisation"]},
            },
            {
                "name": "gerer_maternite",
                "description": "Gestion spécifique maternité : suivi grossesse, accouchement, post-partum (100% couvert selon CIMA)",
                "input_schema": {"type": "object", "properties": {
                    "numero_adherente":    {"type": "string"},
                    "date_prevue_terme":   {"type": "string", "description": "YYYY-MM-DD"},
                    "date_accouchement":   {"type": "string", "description": "YYYY-MM-DD — vide si grossesse en cours"},
                    "type_accouchement":   {"type": "string", "enum": ["naturel", "cesarienne", "gemellaire"], "default": "naturel"},
                    "clinique":            {"type": "string"},
                    "montant_forfait":     {"type": "number", "description": "Forfait maternité contractuel FCFA"},
                }, "required": ["numero_adherente"]},
            },
            {
                "name": "gerer_invalidite_longue_maladie",
                "description": "Gestion invalidité et longue maladie : arrêt de travail prolongé, taux d'invalidité, prestations journalières",
                "input_schema": {"type": "object", "properties": {
                    "numero_adherent":    {"type": "string"},
                    "date_arret":         {"type": "string", "description": "YYYY-MM-DD"},
                    "diagnostic":         {"type": "string"},
                    "taux_invalidite_pct":{"type": "number", "description": "Taux invalidité reconnu (0-100)"},
                    "salaire_reference":  {"type": "number", "description": "Salaire de référence FCFA/mois"},
                    "duree_arret_jours":  {"type": "integer"},
                    "indemnite_journaliere_contractuelle": {"type": "number", "description": "IJ contractuelle FCFA/jour"},
                }, "required": ["numero_adherent", "date_arret"]},
            },
            {
                "name": "valider_remboursement_maladie",
                "description": "Soumet la décision de remboursement pour validation humaine (obligatoire si > 500k FCFA)",
                "input_schema": {"type": "object", "properties": {
                    "numero_dossier":     {"type": "string"},
                    "montant_rembourse":  {"type": "number"},
                    "motif":              {"type": "string"},
                    "pieces_validees":    {"type": "array", "items": {"type": "string"}},
                }, "required": ["numero_dossier", "montant_rembourse", "motif"]},
            },
            {
                "name": "rejeter_dossier_maladie",
                "description": "Rejette un dossier avec motif précis (carence, hors garanties, plafond atteint, pièces insuffisantes)",
                "input_schema": {"type": "object", "properties": {
                    "numero_dossier": {"type": "string"},
                    "motif_rejet":    {"type": "string", "enum": [
                        "periode_carence", "hors_garanties", "plafond_annuel_atteint",
                        "pieces_insuffisantes", "prestataire_non_agree",
                        "acte_non_couvert", "doublon", "fraude_suspectee",
                    ]},
                    "detail":         {"type": "string"},
                }, "required": ["numero_dossier", "motif_rejet"]},
            },
            {
                "name": "tableau_bord_maladie",
                "description": "Tableau de bord sinistres maladie : taux de sinistralité, top actes, délais traitement, fraude",
                "input_schema": {"type": "object", "properties": {
                    "periode":    {"type": "string", "description": "ex: 2025-T1 ou 2025"},
                    "groupe":     {"type": "string", "description": "Contrat groupe ID — vide = tous"},
                    "indicateur": {"type": "string", "enum": ["sinistralite", "top_actes", "delais", "fraude", "tous"]},
                }, "required": []},
            },
            {
                "name": "notifier_assure_maladie",
                "description": "Notifie l'assuré / le prestataire du résultat (acceptation BPC, remboursement, rejet)",
                "input_schema": {"type": "object", "properties": {
                    "telephone":   {"type": "string"},
                    "email":       {"type": "string"},
                    "type_notif":  {"type": "string", "enum": ["bpc_emis", "remboursement_valide", "rejet", "demande_pieces", "rappel_carence"]},
                    "montant":     {"type": "number"},
                    "message":     {"type": "string"},
                    "canal":       {"type": "string", "enum": ["whatsapp", "sms", "email"], "default": "whatsapp"},
                }, "required": ["type_notif"]},
            },
        ]

    def _prompt_questions_specifiques(self) -> str:
        return """
AGENT SINISTRES MALADIE — quand demander une information :

1. NUMÉRO D'ADHÉRENT / CARTE SANTÉ ABSENT
   → "Quel est le numéro d'adhérent ou le numéro de carte santé de l'assuré ? (figurant sur la carte de tiers payant)"
   type_reponse: texte_libre

2. TYPE D'ACTE NON DÉTERMINÉ
   → "Quel type de soins est concerné par cette demande ?"
   type_reponse: choix_multiple  choix: ["Consultation médicale", "Hospitalisation", "Pharmacie / Médicaments", "Biologie / Analyses", "Radiologie / Imagerie", "Maternité / Accouchement", "Dentaire", "Optique", "Kinésithérapie", "Invalidité / Arrêt de travail"]

3. DATE DES SOINS MANQUANTE
   → "Quelle est la date de réalisation des soins ou d'admission à l'hôpital ?"
   type_reponse: date

4. ORDONNANCE MÉDICALE ABSENTE (pharmacie, biologie, kiné)
   → "Veuillez envoyer la photo ou le scan de l'ordonnance médicale du médecin prescripteur."
   type_reponse: image  nombre_images_max: 1  formats_acceptes: ["jpg", "png", "pdf"]

5. FACTURE MÉDICALE / CLINIQUE ABSENTE
   → "Veuillez transmettre les factures détaillées de la clinique ou du prestataire de soins (mentionnant les actes et les montants)."
   type_reponse: images  nombre_images_max: 5  formats_acceptes: ["jpg", "png", "pdf"]

6. BULLETIN D'HOSPITALISATION MANQUANT
   → "Merci de nous envoyer le bulletin d'hospitalisation (ou lettre de sortie) indiquant la durée du séjour, le diagnostic et les actes réalisés."
   type_reponse: image  nombre_images_max: 1  formats_acceptes: ["jpg", "png", "pdf"]

7. COMPTE RENDU MÉDICAL REQUIS (hospitalisation longue / chirurgie)
   → "Veuillez joindre le compte rendu médical établi par le médecin traitant ou le chirurgien. Ce document est nécessaire pour le traitement complet de votre dossier."
   type_reponse: images  nombre_images_max: 3  formats_acceptes: ["jpg", "png", "pdf"]

8. CERTIFICAT D'ARRÊT DE TRAVAIL ABSENT (invalidité / longue maladie)
   → "Pour traiter votre dossier d'arrêt de travail, veuillez envoyer le certificat médical d'arrêt de travail initial et les éventuels renouvellements."
   type_reponse: images  nombre_images_max: 5  formats_acceptes: ["jpg", "png", "pdf"]

9. RÉSULTATS BIOLOGIE / RADIO DEMANDÉS
   → "Veuillez joindre les résultats d'analyses biologiques ou les clichés d'imagerie (radio, scanner, IRM) pour valider la prise en charge."
   type_reponse: images  nombre_images_max: 5  formats_acceptes: ["jpg", "png", "pdf"]

10. DEVIS DENTAIRE / OPTIQUE MANQUANT
    → "Pour traiter votre demande de remboursement dentaire/optique, veuillez envoyer le devis détaillé établi par le prestataire."
    type_reponse: image  nombre_images_max: 1  formats_acceptes: ["jpg", "png", "pdf"]

11. FEUILLE DE SOINS SÉCURITÉ SOCIALE (si maladie dans un pays avec couverture sociale)
    → "Avez-vous une feuille de soins ou un relevé de remboursement de l'organisme primaire ? Ce document permet de calculer le complément remboursable."
    type_reponse: image  nombre_images_max: 1  formats_acceptes: ["jpg", "png", "pdf"]

12. CONFIRMATION TYPE DE GROSSESSE / MATERNITÉ
    → "Pouvez-vous confirmer le type d'accouchement et joindre le certificat d'accouchement de la clinique ?"
    type_reponse: image  nombre_images_max: 1  formats_acceptes: ["jpg", "png", "pdf"]

RÈGLE : Commencer par le numéro d'adhérent et la date des soins. Ne jamais demander plus d'une info à la fois. Pour les pièces médicales (ordonnances, factures, comptes-rendus), utiliser les types image/images — elles seront OCR-analysées et archivées automatiquement.
"""

    def _necessite_validation(self, nom_outil: str, params: dict, resultat: str) -> bool:
        if nom_outil == "valider_remboursement_maladie":
            return params.get("montant_rembourse", 0) >= 500_000
        if nom_outil == "traiter_dossier_hospitalisation":
            return params.get("montant_total", 0) >= 500_000
        if nom_outil == "gerer_invalidite_longue_maladie":
            return True  # Toujours valider les dossiers d'invalidité
        return False

    async def _executer_outil(self, nom: str, params: dict, user_id: int, execution_id: str) -> str:
        try:
            if nom == "verifier_contrat_maladie":
                from core.orass_connector import orass
                validite = await orass.verifier_validite_contrat(params.get("numero_police", ""))
                nb_adherent = params.get("numero_adherent", "INC")
                type_acte = params.get("type_acte", "consultation_generaliste")
                taux = _TAUX_REMBOURSEMENT.get(type_acte, 0.75)
                carence = _DELAI_CARENCE.get(type_acte.split("_")[0], 0)

                # Vérifier validité contrat
                date_soins = params.get("date_soins", str(date.today()))
                contrat_ok = validite.get("valide", False)

                return json.dumps({
                    "contrat_valide":     contrat_ok,
                    "adherent":           nb_adherent,
                    "police_id":          params.get("numero_police"),
                    "type_acte":          type_acte,
                    "taux_remboursement": taux,
                    "carence_jours":      carence,
                    "plafond_annuel":     5_000_000,  # valeur par défaut simulation
                    "reseau_agree":       True,   # En simulation
                    "copie_garanties":    {
                        "hospitalisation": True,
                        "consultations": True,
                        "pharmacie": True,
                        "optique": False,
                        "dentaire": False,
                    },
                }, ensure_ascii=False)

            if nom == "emettre_bon_prise_en_charge":
                import uuid
                numero_bpc = f"BPC-{date.today().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"
                montant_estime = params.get("montant_estime", 0)
                type_acte = params.get("type_acte", "consultation_generaliste")
                taux = _TAUX_REMBOURSEMENT.get(type_acte, 0.75)
                montant_pris_en_charge = montant_estime * taux

                return json.dumps({
                    "numero_bpc":          numero_bpc,
                    "adherent":            params.get("numero_adherent"),
                    "prestataire":         params.get("prestataire_nom"),
                    "type_acte":           type_acte,
                    "montant_estime":      montant_estime,
                    "taux_prise_en_charge": taux,
                    "montant_pris_en_charge": montant_pris_en_charge,
                    "ticket_moderateur":   montant_estime - montant_pris_en_charge,
                    "validite_jours":      30,
                    "statut":              "ÉMIS — valable 30 jours",
                    "urgence":             params.get("urgence", False),
                }, ensure_ascii=False)

            if nom == "analyser_pieces_medicales":
                from core.ia_client import ModeIA, ia_client
                pieces = params.get("pieces", [])
                type_acte = params.get("type_acte", "")

                if not pieces:
                    return json.dumps({
                        "nb_pieces": 0,
                        "analyse": "Aucune pièce fournie — veuillez soumettre les documents médicaux",
                        "pieces_manquantes": ["ordonnance", "facture"],
                    })

                # ── OCR Vision par image : GPT-4o primaire, Claude fallback ──
                descriptions = []
                extractions_vision = []
                for p in pieces:
                    type_p = p.get("type_piece", "document")
                    b64 = p.get("image_base64", "")
                    # Nettoyer le préfixe data URI si présent
                    if b64 and b64.startswith("data:"):
                        try:
                            b64 = b64.split(",", 1)[1]
                        except IndexError:
                            pass

                    if b64:
                        # Prompt OCR adapté au type de pièce médicale
                        prompt_ocr = (
                            f"Tu es un expert OCR pour documents médicaux assurance zone CIMA. "
                            f"Analyse cette image de type '{type_p}'. Extrais PRECISEMENT en JSON :\n"
                            f"- actes_medicaux: liste des actes/médicaments/diagnostics\n"
                            f"- montants: tous les montants en FCFA (ou XAF) avec leur libellé\n"
                            f"- dates: toutes les dates trouvées (soins, prescription, facturation)\n"
                            f"- prescripteur: nom et spécialité du médecin\n"
                            f"- etablissement: nom de la clinique/pharmacie\n"
                            f"- numero_document: numéro de facture, bon, ordonnance\n"
                            f"- anomalies: toute incohérence ou information suspecte\n"
                            f"Retourne UNIQUEMENT le JSON, sans commentaire."
                        )
                        try:
                            rep_vision = await ia_client.analyser_image_vision(
                                image_b64=b64,
                                prompt=prompt_ocr,
                                mode=ModeIA.PRECISION,
                            )
                            extractions_vision.append({
                                "type_piece": type_p,
                                "extraction": rep_vision.contenu,
                            })
                            descriptions.append(
                                f"[{type_p}] ANALYSÉ PAR VISION IA :\n{rep_vision.contenu[:400]}"
                            )
                        except Exception as e_vision:
                            logger.warning(f"[SinistresMaladie] Vision IA échoué pour {type_p}: {e_vision}")
                            descriptions.append(f"[{type_p}] : image fournie (Vision IA non disponible)")
                    else:
                        descriptions.append(f"[{type_p}] : {p.get('description', 'document mentionné sans image')}")

                prompt = f"""Tu es expert en remboursement sinistres maladie CIMA.
Analyse ce dossier (type acte : {type_acte}) à partir des données OCR extraites ci-dessous.

DONNÉES EXTRAITES PAR OCR/VISION IA :
{chr(10).join(descriptions)}

Synthèse requise :
1. ACTES MÉDICAUX confirmés et codifiés (nomenclature CIMA)
2. MONTANTS facturés, bases de remboursement et taux applicables
3. PRESCRIPTEUR et établissement (réseau agréé ?)
4. COHÉRENCE ordonnance ↔ facture (dates, actes, montants)
5. PIÈCES MANQUANTES ou illisibles pour clôturer le dossier
6. MONTANT REMBOURSABLE estimé selon barème CIMA
7. SIGNAUX FRAUDE détectés (surfacturation, dates incohérentes, falsification)"""

                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                return json.dumps({
                    "dossier":           params["numero_dossier"],
                    "nb_pieces":         len(pieces),
                    "nb_images_vision":  len(extractions_vision),
                    "type_acte":         type_acte,
                    "extractions_ocr":   extractions_vision,
                    "analyse":           rep.contenu,
                    "pieces_analysees":  [p.get("type_piece") for p in pieces],
                }, ensure_ascii=False)

            if nom == "calculer_remboursement":
                type_acte = params.get("type_acte", "consultation_generaliste")
                montant_facture = params.get("montant_facture", 0)
                base_remb = params.get("base_remboursement", montant_facture)
                taux_contrat = params.get("taux_contrat") or _TAUX_REMBOURSEMENT.get(type_acte, 0.75)
                plafond = params.get("plafond_annuel_restant", 99_999_999)
                hors_reseau = params.get("hors_reseau", False)

                if hors_reseau:
                    taux_contrat = taux_contrat * 0.70  # Malus hors réseau

                montant_rembourse = min(base_remb * taux_contrat, plafond)
                ticket_moderateur = montant_facture - montant_rembourse

                return json.dumps({
                    "dossier":                params["numero_dossier"],
                    "type_acte":              type_acte,
                    "montant_facture_fcfa":   montant_facture,
                    "base_remboursement":     base_remb,
                    "taux_applique":          round(taux_contrat * 100, 1),
                    "montant_rembourse_fcfa": round(montant_rembourse),
                    "ticket_moderateur_fcfa": round(ticket_moderateur),
                    "hors_reseau":            hors_reseau,
                    "plafond_disponible":     plafond,
                    "nouveau_plafond_restant":round(plafond - montant_rembourse),
                    "necessite_validation":   montant_rembourse >= 500_000,
                }, ensure_ascii=False)

            if nom == "verifier_plafond_annuel":
                from core.orass_connector import orass
                adherent = params.get("numero_adherent")
                annee = params.get("annee", date.today().year)
                # En simulation — retourner des plafonds réalistes
                return json.dumps({
                    "adherent":  adherent,
                    "annee":     annee,
                    "plafonds": {
                        "hospitalisation": {"plafond": 10_000_000, "consomme": 1_500_000, "restant": 8_500_000},
                        "pharmacie":       {"plafond":  1_500_000, "consomme":    350_000, "restant": 1_150_000},
                        "consultations":   {"plafond":  1_000_000, "consomme":    200_000, "restant":   800_000},
                        "biologie":        {"plafond":    500_000, "consomme":     80_000, "restant":   420_000},
                        "optique":         {"plafond":    300_000, "consomme":          0, "restant":   300_000},
                        "dentaire":        {"plafond":    500_000, "consomme":          0, "restant":   500_000},
                    },
                    "sinistralite_cumul_fcfa": 2_130_000,
                }, ensure_ascii=False)

            if nom == "traiter_dossier_hospitalisation":
                adherent = params.get("numero_adherent")
                type_hospi = params.get("type_hospitalisation", "medicale")
                montant_total = params.get("montant_total", 0)
                date_e = params.get("date_entree")
                date_s = params.get("date_sortie", str(date.today()))
                chambre = params.get("chambre_type", "standard")

                # Calcul durée séjour
                from datetime import datetime
                try:
                    d_entree = datetime.fromisoformat(date_e) if date_e else datetime.today()
                    d_sortie = datetime.fromisoformat(date_s)
                    duree = max(1, (d_sortie - d_entree).days)
                except Exception:
                    duree = 1

                # Taux selon type
                taux_hospi = 0.90
                if chambre == "confort":
                    taux_hospi = 0.75
                elif chambre == "suite":
                    taux_hospi = 0.60

                montant_rembourse = montant_total * taux_hospi

                return json.dumps({
                    "adherent":              adherent,
                    "clinique":              params.get("clinique_code"),
                    "type":                  type_hospi,
                    "date_entree":           date_e,
                    "date_sortie":           date_s,
                    "duree_sejour_jours":    duree,
                    "montant_facture":       montant_total,
                    "taux_remboursement":    taux_hospi,
                    "montant_rembourse":     round(montant_rembourse),
                    "chambre_type":          chambre,
                    "necessite_validation":  montant_rembourse >= 500_000,
                    "diagnostic":            params.get("diagnostic_principal", "Non précisé"),
                }, ensure_ascii=False)

            if nom == "gerer_maternite":
                import uuid
                adherente = params.get("numero_adherente")
                date_acc = params.get("date_accouchement", str(date.today()))
                type_acc = params.get("type_accouchement", "naturel")
                forfait = params.get("montant_forfait", 300_000)

                # Maternité toujours 100% (sauf suite)
                multiplicateur = {"naturel": 1.0, "cesarienne": 1.2, "gemellaire": 1.5}.get(type_acc, 1.0)
                montant = forfait * multiplicateur

                return json.dumps({
                    "adherente":               adherente,
                    "date_accouchement":       date_acc,
                    "type_accouchement":       type_acc,
                    "forfait_base_fcfa":       forfait,
                    "montant_prise_en_charge": round(montant),
                    "taux":                    "100%",
                    "ticket_moderateur":       0,
                    "reference_dossier":       f"MAT-{str(uuid.uuid4())[:8].upper()}",
                    "statut":                  "Prise en charge complète",
                }, ensure_ascii=False)

            if nom == "gerer_invalidite_longue_maladie":
                adherent = params.get("numero_adherent")
                taux_inv = params.get("taux_invalidite_pct", 0)
                salaire = params.get("salaire_reference", 0)
                ij_contractuelle = params.get("indemnite_journaliere_contractuelle", salaire / 30)
                duree = params.get("duree_arret_jours", 0)

                if taux_inv >= 66:
                    statut_inv = "Invalidité totale (≥ 66%)"
                    ij = ij_contractuelle
                elif taux_inv >= 33:
                    statut_inv = "Invalidité partielle (33-66%)"
                    ij = ij_contractuelle * (taux_inv / 100)
                else:
                    statut_inv = "Invalidité légère (< 33%) — pas de prestation"
                    ij = 0

                total_indemnite = ij * duree

                return json.dumps({
                    "adherent":               adherent,
                    "taux_invalidite_pct":    taux_inv,
                    "statut_invalidite":      statut_inv,
                    "indemnite_journaliere":  round(ij),
                    "duree_arret_jours":      duree,
                    "total_indemnite_fcfa":   round(total_indemnite),
                    "necessite_validation":   True,
                    "diagnostic":             params.get("diagnostic", "Non précisé"),
                }, ensure_ascii=False)

            if nom == "valider_remboursement_maladie":
                from core.approval_queue import approval_queue
                await approval_queue.ajouter({
                    "type":              "remboursement_maladie",
                    "numero_dossier":    params.get("numero_dossier"),
                    "montant":           params.get("montant_rembourse", 0),
                    "motif":             params.get("motif", ""),
                    "pieces_validees":   params.get("pieces_validees", []),
                    "user_id":           user_id,
                    "execution_id":      execution_id,
                })
                return f"✅ Dossier {params.get('numero_dossier')} soumis pour validation — montant : {params.get('montant_rembourse', 0):,.0f} FCFA"

            if nom == "rejeter_dossier_maladie":
                return json.dumps({
                    "dossier":        params.get("numero_dossier"),
                    "statut":         "REJETÉ",
                    "motif_rejet":    params.get("motif_rejet"),
                    "detail":         params.get("detail", ""),
                    "recours_possible": True,
                    "delai_recours":  "30 jours",
                }, ensure_ascii=False)

            if nom == "tableau_bord_maladie":
                periode = params.get("periode", str(date.today().year))
                return json.dumps({
                    "periode":         periode,
                    "nb_dossiers":     142,
                    "montant_regle_fcfa": 28_500_000,
                    "taux_sinistralite_pct": 68.5,
                    "top_actes": [
                        {"acte": "hospitalisation_medicale", "nb": 28, "montant": 12_000_000},
                        {"acte": "pharmacie",                "nb": 65, "montant":  6_500_000},
                        {"acte": "consultation_generaliste", "nb": 89, "montant":  3_200_000},
                    ],
                    "delai_moyen_traitement_jours": 5.2,
                    "bpc_emis":         73,
                    "remboursements":   69,
                    "rejets":           12,
                    "alerte_fraude":     3,
                }, ensure_ascii=False)

            if nom == "notifier_assure_maladie":
                canal = params.get("canal", "whatsapp")
                type_notif = params.get("type_notif", "remboursement_valide")
                messages_types = {
                    "bpc_emis":               "Votre bon de prise en charge a été émis",
                    "remboursement_valide":    "Votre remboursement a été validé",
                    "rejet":                  "Votre dossier n'a pas pu être pris en charge",
                    "demande_pieces":          "Des pièces complémentaires vous sont demandées",
                    "rappel_carence":          "Votre dossier est en période de carence",
                }
                return f"✅ Notification {type_notif} envoyée via {canal} : {messages_types.get(type_notif, type_notif)}"

            return f"[{nom}] Outil exécuté (simulation) — params: {json.dumps(params, ensure_ascii=False)[:200]}"

        except Exception as e:
            logger.error(f"[AgentSinistresMaladie] Outil {nom} erreur : {e}")
            return f"ERREUR outil {nom} : {str(e)}"
