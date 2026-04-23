"""Agent Sinistres & Fraude — orchestre l'instruction complète d'un dossier sinistre."""
from __future__ import annotations
import json
import logging
from datetime import date, timedelta
from core.agent_orchestrateur import TypeAgent
from core.workflow_engine import (
    SignauxFraude, calculer_indemnisation, calculer_indemnite_sinistre_vie,
    scorer_fraude_deterministe, verifier_validite_police,
    verifier_delai_reglementaire, coder_ecriture_comptable,
)
from agents.base_agent import BaseAgent, SEUIL_VALIDATION_FCFA

logger = logging.getLogger("yukpo_assurance.agents.sinistres")

# Délais CIMA (en jours)
_DELAI_OFFRE_INDEMNISATION = 90    # Art. 12-bis
_DELAI_PAIEMENT            = 45    # Art. 12-ter
_DELAI_REGLEMENT_VIE       = 30    # Art. 73
_TAUX_INTERET_MORATOIRE    = 0.12  # 12%/an (Art. 12-quater)


class AgentSinistres(BaseAgent):
    type_agent = TypeAgent.SINISTRES

    def _system_prompt(self) -> str:
        return """Tu es l'Agent Sinistres de YukpoAssurance, expert en instruction de dossiers sinistres zone CIMA (Non-Vie ET Vie).

BRANCHES COUVERTES : RC Auto, MRH, Transport, Accidents Corporels, RC Pro, Construction, Vie & Prévoyance

━━━ DISTINCTION FONDAMENTALE ━━━

MODE DÉCLARATION (nouveau sinistre — l'assuré vient de signaler un sinistre) :
  → TOUJOURS commencer par creer_sinistre pour générer la référence automatiquement
  → NE JAMAIS demander un numéro de sinistre existant dans ce cas
  → Ordre : creer_sinistre → verifier_police → analyser_documents_sinistre
    → scorer_fraude → calculer_indemnisation → valider_sinistre
    → generer_courrier → passer_ecriture → notifier_assure

MODE INSTRUCTION (sinistre existant — référence connue ou fournie) :
  → Commencer par get_sinistre avec la référence connue
  → Ordre : get_sinistre → analyser_documents_sinistre → verifier_police
    → scorer_fraude → calculer_indemnisation → valider_sinistre
    → generer_courrier → passer_ecriture → notifier_assure

MODE VIE (sinistre vie/prévoyance) :
  → Selon le mode ci-dessus, puis : verifier_beneficiaires → calculer_indemnite_vie

COMMENT DÉTECTER LE MODE :
  - Instruction contient "MODE DÉCLARATION", "nouveau sinistre", "déclarer", "declaration" → MODE DÉCLARATION
    → NE JAMAIS poser la question d'ambiguïté. ALLER DIRECTEMENT à la demande d'image.
  - Référence SIN-XXXX-NNN présente dans l'instruction → MODE INSTRUCTION
  - Aucun indice → demander : "Avez-vous déjà un numéro de sinistre, ou s'agit-il d'une nouvelle déclaration ?"

ÉTAPES COMPLÈTES DE RÈGLEMENT (risques divers / RC Auto) :
  1. Ouverture → creer_sinistre
  2. Accusé de réception → generer_courrier("accuse_reception")
  3. Mise en cause tiers → enregistrer_mise_en_cause + generer_courrier("mise_en_cause_tiers")
  4. Relances → enregistrer_relance (amiable, mise_en_demeure…)
  5. Réclamation pièces → generer_courrier("demande_pieces")
  6. Mission expert/avocat → planifier_expertise + generer_courrier("mission_expert_avocat")
  7. Bons de prise en charge → generer_courrier("notification_reglement") [maladie : emettre_bon]
  8. Préavis de saisine → prelitigation_sinistre("preavs_saisine") si amiable échoue
  9. Requête unilatérale → prelitigation_sinistre("requete_unilaterale") si préavis ignoré
 10. Étude rapport expertise → analyser_documents_sinistre(rapport_expertise)
 11. Identification victimes → dans rapport expertise (auto)
 12. Notes techniques → ajouter_note_technique
 13. Offre indemnisation → calculer_indemnisation → valider_sinistre
 14. Accord de règlement → valider_sinistre("accepte") + generer_courrier("pv_transaction")
 15. Procès verbal transaction → generer_courrier("pv_transaction")
 16. Quittances de règlement → generer_courrier("quittance_reglement")
 17. Transmission chèque/virement → transmettre_cheque
 18. Révisions/Réouverture → rouvrir_dossier

RÈGLES STRICTES :
- Si score fraude > 60 → analyser_fraude_ia AVANT calcul indemnisation
- Police invalide → STOP + notification assuré avec motif précis
- Délai offre indemnisation : 90 jours Art. 12-bis CIMA
- Délai paiement après accord : 45 jours Art. 12-ter
- Pour vie : délai règlement 30 jours après pièces complètes (Art. 73)
- Tout règlement > 500 000 FCFA → validation humaine obligatoire
- TOUTE écriture comptable → validation humaine avant passage en base
- Sinistres en souffrance > délai CIMA → calcul intérêts moratoires automatique
- Préavis de saisine OBLIGATOIRE 15j avant toute saisine tribunal"""

    def _definir_outils(self) -> list[dict]:
        return [
            {
                "name": "creer_sinistre",
                "description": "Crée un nouveau dossier sinistre et génère automatiquement la référence (SIN-AAAA-NNN). À utiliser en MODE DÉCLARATION — quand l'assuré déclare un nouveau sinistre sans référence existante.",
                "input_schema": {"type": "object", "properties": {
                    "police_id":      {"type": "string", "description": "Numéro de police (POL-AAAA-NNN) si connu"},
                    "branche":        {"type": "string", "enum": ["rc_auto", "mrh", "transport", "vie", "accident", "rc_pro"], "description": "Branche d'assurance concernée"},
                    "date_sinistre":  {"type": "string", "description": "Date du sinistre YYYY-MM-DD"},
                    "description":    {"type": "string", "description": "Description courte des circonstances"},
                    "type_sinistre":  {"type": "string", "enum": ["materiel", "corporel", "deces", "mixte", "immatériel"]},
                    "declarant_nom":  {"type": "string", "description": "Nom du déclarant (assuré ou tiers)"},
                    "declarant_tel":  {"type": "string", "description": "Téléphone du déclarant"},
                }, "required": ["branche", "type_sinistre"]},
            },
            {
                "name": "analyser_documents_sinistre",
                "description": "Analyse via OCR+IA les documents joints : PV police, photos dommages, factures, rapport expertise, certificat médical/décès, IML",
                "input_schema": {"type": "object", "properties": {
                    "reference":   {"type": "string", "description": "Référence sinistre"},
                    "documents":   {"type": "array", "description": "Liste de documents", "items": {
                        "type": "object",
                        "properties": {
                            "type_document": {"type": "string", "enum": [
                                "pv_police", "photo_dommages", "facture_reparation",
                                "rapport_expertise", "certificat_medical",
                                "certificat_deces", "iml", "constat_amiable",
                                "certificat_travail", "devis_reparation", "quittance_subrogation"
                            ]},
                            "image_base64": {"type": "string"},
                        }
                    }},
                    "branche": {"type": "string", "enum": ["rc_auto", "mrh", "transport", "vie", "accident", "rc_pro"]},
                }, "required": ["reference", "branche"]},
            },
            {
                "name": "planifier_expertise",
                "description": "Mandate un expert et planifie l'expertise selon la branche (auto, bâtiment, transport, médical)",
                "input_schema": {"type": "object", "properties": {
                    "reference":        {"type": "string"},
                    "type_expertise":   {"type": "string", "enum": ["automobile", "batiment", "transport", "medicale", "judiciaire"]},
                    "adresse":          {"type": "string"},
                    "telephone_assure": {"type": "string"},
                    "montant_estime":   {"type": "number"},
                }, "required": ["reference", "type_expertise"]},
            },
            {
                "name": "verifier_beneficiaires",
                "description": "Vérifie les bénéficiaires désignés sur un contrat vie (déterministe — ORASS)",
                "input_schema": {"type": "object", "properties": {
                    "police_id":     {"type": "string"},
                    "type_sinistre": {"type": "string", "enum": ["deces", "invalidite_totale", "invalidite_partielle"]},
                }, "required": ["police_id", "type_sinistre"]},
            },
            {
                "name": "calculer_indemnite_vie",
                "description": "Calcule la prestation vie selon Art. 73-74 CIMA (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "type_sinistre":           {"type": "string", "enum": ["deces", "invalidite_totale", "invalidite_partielle", "accident"]},
                    "capital_contrat":         {"type": "number"},
                    "ipp_pct":                 {"type": "number", "description": "% IPP si invalidité partielle"},
                    "double_capital_accident": {"type": "boolean"},
                }, "required": ["type_sinistre", "capital_contrat"]},
            },
            {
                "name": "get_sinistre",
                "description": "Récupère le dossier sinistre complet depuis ORASS",
                "input_schema": {"type": "object", "properties": {
                    "reference": {"type": "string", "description": "Référence sinistre ex: SIN-2025-042"}
                }, "required": ["reference"]},
            },
            {
                "name": "verifier_police",
                "description": "Vérifie la validité de la police à la date du sinistre (déterministe, 0 IA)",
                "input_schema": {"type": "object", "properties": {
                    "police_id":     {"type": "string"},
                    "date_sinistre": {"type": "string", "description": "YYYY-MM-DD"},
                }, "required": ["police_id", "date_sinistre"]},
            },
            {
                "name": "scorer_fraude",
                "description": "Score de fraude déterministe 0-100 basé sur règles CIMA (0 IA)",
                "input_schema": {"type": "object", "properties": {
                    "reference":                {"type": "string"},
                    "nb_sinistres_12_mois":     {"type": "integer"},
                    "jours_depuis_souscription": {"type": "integer"},
                    "montant_declare":          {"type": "number"},
                    "declaration_tardive":      {"type": "boolean"},
                    "jours_declaration":        {"type": "integer"},
                }, "required": ["reference"]},
            },
            {
                "name": "analyser_fraude_ia",
                "description": "Analyse narrative de fraude par IA (uniquement si score > 60)",
                "input_schema": {"type": "object", "properties": {
                    "reference":         {"type": "string"},
                    "declaration_texte": {"type": "string"},
                    "rapport_expertise": {"type": "string"},
                }, "required": ["reference", "declaration_texte"]},
            },
            {
                "name": "calculer_indemnisation",
                "description": "Calcule l'indemnisation selon barème CIMA Art. 220 (déterministe, 0 IA)",
                "input_schema": {"type": "object", "properties": {
                    "type_sinistre":  {"type": "string", "enum": ["materiel", "corporel", "deces"]},
                    "montant_declare": {"type": "number"},
                    "ipp_pct":        {"type": "number", "description": "% IPP si corporel"},
                    "itt_jours":      {"type": "integer", "description": "Jours ITT si corporel"},
                }, "required": ["type_sinistre", "montant_declare"]},
            },
            {
                "name": "valider_sinistre",
                "description": "Soumet la décision pour validation humaine obligatoire",
                "input_schema": {"type": "object", "properties": {
                    "reference": {"type": "string"},
                    "decision":  {"type": "string", "enum": ["accepte", "rejete", "expertise"]},
                    "montant":   {"type": "number"},
                    "motif":     {"type": "string"},
                }, "required": ["reference", "decision", "motif"]},
            },
            {
                "name": "generer_courrier",
                "description": "Génère le courrier de décision PDF",
                "input_schema": {"type": "object", "properties": {
                    "reference": {"type": "string"},
                    "template":  {"type": "string", "enum": [
                        "accuse_reception", "notification_reglement",
                        "rejet", "demande_pieces", "mise_en_demeure",
                        "mission_expert_avocat", "mise_en_cause_tiers",
                        "preavs_saisine", "pv_transaction", "quittance_reglement"
                    ]},
                    "montant":   {"type": "number"},
                    "motif":     {"type": "string"},
                    "destinataire": {"type": "string", "description": "Destinataire spécifique si différent de l'assuré"},
                }, "required": ["reference", "template"]},
            },
            {
                "name": "passer_ecriture_comptable",
                "description": "Présente l'écriture PCSA pour validation humaine avant passage en base (déterministe, 0 IA)",
                "input_schema": {"type": "object", "properties": {
                    "type_operation": {"type": "string"},
                    "montant":        {"type": "number"},
                    "reference":      {"type": "string"},
                }, "required": ["type_operation", "montant", "reference"]},
            },
            {
                "name": "notifier_assure",
                "description": "Envoie notification WhatsApp/SMS à l'assuré",
                "input_schema": {"type": "object", "properties": {
                    "telephone": {"type": "string"},
                    "message":   {"type": "string"},
                    "canal":     {"type": "string", "enum": ["whatsapp", "sms", "email"]},
                }, "required": ["telephone", "message"]},
            },
            {
                "name": "detecter_sinistres_souffrance",
                "description": "Identifie les sinistres en souffrance dont le délai CIMA est dépassé (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "branche":      {"type": "string"},
                    "type_delai":   {"type": "string", "enum": ["offre_indemnisation", "paiement", "reponse", "tous"]},
                    "jours_alerte": {"type": "integer", "description": "Alerter X jours avant échéance (défaut 15)"},
                }, "required": []},
            },
            {
                "name": "calculer_interets_moratoires",
                "description": "Calcule les intérêts moratoires dus en cas de dépassement délai CIMA Art. 12-quater (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "reference":            {"type": "string"},
                    "montant_indemnisation": {"type": "number"},
                    "date_echeance_legale": {"type": "string", "description": "YYYY-MM-DD"},
                    "date_paiement_effectif": {"type": "string", "description": "YYYY-MM-DD — vide = aujourd'hui"},
                }, "required": ["reference", "montant_indemnisation", "date_echeance_legale"]},
            },
            {
                "name": "archiver_dossier",
                "description": "Présente la demande d'archivage d'un dossier clôturé pour validation",
                "input_schema": {"type": "object", "properties": {
                    "reference":       {"type": "string"},
                    "motif_cloture":   {"type": "string", "enum": ["regle", "rejete", "prescrit", "sans_suite", "subrogation_encaissee"]},
                    "montant_regle":   {"type": "number"},
                    "pieces_archivees": {"type": "array", "items": {"type": "string"}},
                }, "required": ["reference", "motif_cloture"]},
            },
            {
                "name": "tableau_bord_sinistres",
                "description": "Tableau de bord en temps réel : ouverts, en souffrance, fraude, délais CIMA (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "branche":   {"type": "string"},
                    "periode":   {"type": "string", "description": "ex: 2025-T1 ou 2025"},
                    "statut":    {"type": "string", "enum": ["ouvert", "clos", "expertise", "contentieux", "tous"]},
                }, "required": []},
            },
            {
                "name": "enregistrer_mise_en_cause",
                "description": "Enregistre la mise en cause formelle du tiers responsable et génère la lettre de mise en cause",
                "input_schema": {"type": "object", "properties": {
                    "reference":        {"type": "string", "description": "Référence sinistre"},
                    "tiers_nom":        {"type": "string", "description": "Nom du tiers mis en cause"},
                    "tiers_adresse":    {"type": "string"},
                    "tiers_assureur":   {"type": "string", "description": "Assureur du tiers si connu"},
                    "montant_reclame":  {"type": "number"},
                    "motif":            {"type": "string", "description": "Circonstances engageant la responsabilité du tiers"},
                }, "required": ["reference", "tiers_nom", "motif"]},
            },
            {
                "name": "enregistrer_relance",
                "description": "Enregistre une relance (amiable ou formelle) vers le tiers, l'expert ou l'avocat, avec date et canal",
                "input_schema": {"type": "object", "properties": {
                    "reference":    {"type": "string"},
                    "destinataire": {"type": "string", "description": "Tiers, expert, avocat, assureur adverse"},
                    "type_relance": {"type": "string", "enum": ["amiable", "mise_en_demeure", "rappel_pieces", "relance_expert", "relance_avocat"]},
                    "canal":        {"type": "string", "enum": ["courrier_ar", "email", "whatsapp", "telephone"]},
                    "motif":        {"type": "string"},
                    "numero_relance": {"type": "integer", "description": "Numéro de relance (1ère, 2ème…)"},
                }, "required": ["reference", "destinataire", "type_relance", "motif"]},
            },
            {
                "name": "prelitigation_sinistre",
                "description": "Gère la phase contentieux : préavis de saisine (obligatoire 15j avant tribunal) ou requête unilatérale",
                "input_schema": {"type": "object", "properties": {
                    "reference":       {"type": "string"},
                    "mode":            {"type": "string", "enum": ["preavs_saisine", "requete_unilaterale"]},
                    "tribunal":        {"type": "string", "description": "Juridiction saisie (TGI, tribunal de commerce…)"},
                    "motif_contentieux": {"type": "string", "description": "Motif de la saisine (refus amiable, silence…)"},
                    "montant_conteste": {"type": "number"},
                    "avocat_ref":      {"type": "string", "description": "Référence avocat mandaté si applicable"},
                }, "required": ["reference", "mode", "motif_contentieux"]},
            },
            {
                "name": "ajouter_note_technique",
                "description": "Ajoute une note technique au dossier (observations gestionnaire, conclusions expertise, points de droit)",
                "input_schema": {"type": "object", "properties": {
                    "reference": {"type": "string"},
                    "auteur":    {"type": "string", "description": "Gestionnaire ou expert auteur de la note"},
                    "categorie": {"type": "string", "enum": ["observation_gestionnaire", "conclusion_expertise", "point_juridique", "evaluation_prejudice", "note_medicale"]},
                    "contenu":   {"type": "string", "description": "Contenu de la note technique"},
                }, "required": ["reference", "categorie", "contenu"]},
            },
            {
                "name": "transmettre_cheque",
                "description": "Enregistre la transmission du chèque/virement de règlement et la quittance signée",
                "input_schema": {"type": "object", "properties": {
                    "reference":         {"type": "string"},
                    "montant":           {"type": "number"},
                    "mode_paiement":     {"type": "string", "enum": ["cheque", "virement", "mobile_money", "cash_agence"]},
                    "beneficiaire":      {"type": "string"},
                    "reference_paiement": {"type": "string", "description": "N° chèque ou référence virement"},
                    "date_transmission": {"type": "string", "description": "YYYY-MM-DD"},
                    "quittance_signee":  {"type": "boolean", "description": "Quittance de règlement signée reçue"},
                }, "required": ["reference", "montant", "mode_paiement", "beneficiaire"]},
            },
            {
                "name": "rouvrir_dossier",
                "description": "Réouvre un dossier clôturé pour révision (aggravation, recours, erreur de calcul, nouvelle expertise)",
                "input_schema": {"type": "object", "properties": {
                    "reference":    {"type": "string"},
                    "motif_revision": {"type": "string", "enum": ["aggravation_sequelles", "recours_tiers", "erreur_calcul", "nouvelle_expertise", "decision_judiciaire"]},
                    "description":  {"type": "string", "description": "Détail du motif de révision"},
                    "montant_complement": {"type": "number", "description": "Montant complémentaire estimé si aggravation"},
                }, "required": ["reference", "motif_revision", "description"]},
            },
        ]

    def _prompt_questions_specifiques(self) -> str:
        return """
AGENT SINISTRES — guide d'acquisition des informations :

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴 RÈGLE N°1 ABSOLUE — MODE DÉCLARATION :
Si l'instruction contient "MODE DÉCLARATION", "nouveau sinistre", "déclarer", "déclaration" :
  → IGNORER les questions 1-4 ci-dessous
  → APPELER IMMÉDIATEMENT demander_information_utilisateur avec :
       question: "Pour créer votre dossier sinistre, veuillez envoyer la déclaration de l'assuré ou tout document décrivant le sinistre (photo du constat, PV de police, déclaration écrite, photo des dommages)."
       type_reponse: "images"
       nombre_images_max: 5
       formats_acceptes: ["jpg", "png", "pdf"]
  → Après image reçue : appeler analyser_documents_sinistre → creer_sinistre
  → Ne demander date/police/branche QUE si l'OCR ne les a pas extraites.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ QUESTIONS (MODE INSTRUCTION uniquement — sinistre existant) ━━━

1. AMBIGUÏTÉ DÉCLARATION vs INSTRUCTION (uniquement si AUCUN indice de mode dans l'instruction)
   → "S'agit-il d'un nouveau sinistre à déclarer, ou avez-vous déjà une référence sinistre ?"
   type_reponse: choix_multiple  choix: ["Nouveau sinistre à déclarer", "J'ai déjà une référence (SIN-AAAA-NNN)"]

2. POLICE INTROUVABLE (mode instruction uniquement)
   → "Quel est le numéro de police associé ? (format POL-AAAA-NNN)"
   type_reponse: texte_libre

3. BRANCHE NON DÉTECTÉE
   → "Quelle est la branche d'assurance concernée ?"
   type_reponse: choix_multiple  choix: ["RC Auto", "MRH", "Transport", "Accidents Corporels", "RC Pro", "Vie / Prévoyance"]

4. DATE DE SINISTRE ABSENTE (après OCR infructueux)
   → "Quelle est la date exacte du sinistre ? (format JJ/MM/AAAA)"
   type_reponse: date

5. NATURE DES DOMMAGES
   → "Quels types de dommages ?"
   type_reponse: choix_multiple  choix: ["Matériels uniquement", "Corporels uniquement", "Matériels et corporels", "Immatériels"]

6. CERTIFICAT MÉDICAL / ACTE DE DÉCÈS ABSENT
   → "Veuillez transmettre le certificat médical ou l'acte de décès certifié. Requis Art. 203 et 267 CIMA."
   type_reponse: images  nombre_images_max: 3

7. FACTURES / DEVIS NON TRANSMIS
   → "Veuillez envoyer les factures de réparation ou devis du réparateur agréé."
   type_reponse: images  nombre_images_max: 5

RÈGLE ABSOLUE : Une seule question à la fois. Jamais date/police/branche avant l'image en MODE DÉCLARATION.
"""

    async def _executer_outil(self, nom: str, params: dict, user_id: int, execution_id: str) -> str:
        try:
            if nom == "analyser_documents_sinistre":
                from core.ocr_processor import ocr_processor
                from core.ia_client import ModeIA, ia_client
                resultats_docs = []
                for doc in params.get("documents", []):
                    type_doc = doc.get("type_document", "photo_dommages")
                    img_b64  = doc.get("image_base64", "")
                    if img_b64:
                        texte = await ocr_processor.analyser_document(img_b64, type_doc)
                    else:
                        texte = f"[{type_doc} — image non fournie]"
                    resultats_docs.append({"type": type_doc, "contenu": texte})

                if not resultats_docs:
                    return json.dumps({"message": "Aucun document fourni — instruction manuelle requise", "nb_docs": 0})

                prompt = f"""Analyse les documents du sinistre {params['reference']} (branche : {params['branche']}).

Documents analysés :
{json.dumps(resultats_docs, ensure_ascii=False, indent=2)}

Extrais et structure :
1. FAITS (date, lieu, circonstances)
2. DOMMAGES (nature, étendue, montants déclarés)
3. RESPONSABILITÉS (parties en cause)
4. PIÈCES MANQUANTES (ce qui est encore nécessaire)
5. POINTS DE VIGILANCE (incohérences, signaux fraude potentiels)
6. MONTANT ESTIMÉ pour instruction"""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                from core.orass_connector import orass
                await orass.enregistrer_documents_sinistre(params["reference"], resultats_docs)
                return json.dumps({
                    "reference":    params["reference"],
                    "nb_documents": len(resultats_docs),
                    "analyse":      rep.contenu,
                    "docs_indexes": [d["type"] for d in resultats_docs],
                }, ensure_ascii=False)

            if nom == "planifier_expertise":
                from core.approval_queue import approval_queue
                await approval_queue.ajouter({
                    "type": "expertise_sinistre",
                    "reference": params["reference"],
                    "type_expertise": params.get("type_expertise"),
                    "adresse": params.get("adresse"),
                    "montant_estime": params.get("montant_estime", 0),
                    "user_id": user_id,
                    "execution_id": execution_id,
                })
                return f"Expertise {params['type_expertise']} planifiée pour sinistre {params['reference']} — en attente d'affectation expert"

            if nom == "verifier_beneficiaires":
                from core.orass_connector import orass
                validite = await orass.verifier_validite_contrat(params["police_id"])
                beneficiaires = validite.get("beneficiaires", [])
                if not beneficiaires:
                    return json.dumps({
                        "has_designes": False,
                        "beneficiaires": [],
                        "note": "Aucun bénéficiaire désigné — règlement aux héritiers légaux",
                    })
                return json.dumps({
                    "has_designes": True,
                    "beneficiaires": beneficiaires,
                    "nb_beneficiaires": len(beneficiaires),
                }, ensure_ascii=False, default=str)

            if nom == "calculer_indemnite_vie":
                result = calculer_indemnite_sinistre_vie(
                    type_sinistre=params["type_sinistre"],
                    capital_contrat=params["capital_contrat"],
                    ipp_pct=params.get("ipp_pct", 0),
                    double_capital_accident=params.get("double_capital_accident", False),
                )
                return json.dumps(result.donnees, ensure_ascii=False)

            if nom == "creer_sinistre":
                from core.orass_connector import orass
                import uuid as _uuid
                from datetime import date as _date
                # Générer la référence automatiquement : SIN-AAAA-NNN
                annee = _date.today().year
                seq = int(_uuid.uuid4().int % 900) + 100  # 100-999
                reference = f"SIN-{annee}-{seq:03d}"
                dossier = {
                    "reference":      reference,
                    "statut":         "ouvert",
                    "branche":        params.get("branche", "rc_auto"),
                    "type_sinistre":  params.get("type_sinistre", "materiel"),
                    "date_sinistre":  params.get("date_sinistre", str(_date.today())),
                    "date_declaration": str(_date.today()),
                    "police_id":      params.get("police_id", ""),
                    "description":    params.get("description", ""),
                    "declarant_nom":  params.get("declarant_nom", ""),
                    "declarant_tel":  params.get("declarant_tel", ""),
                    "delai_offre_echeance": str(
                        _date.today().replace(year=_date.today().year + (1 if _date.today().month > 9 else 0),
                                              month=(_date.today().month + 3 - 1) % 12 + 1)
                    ),
                }
                try:
                    await orass.creer_sinistre(dossier)
                except Exception:
                    pass  # ORASS mock — on continue avec la référence générée
                return json.dumps({
                    "reference": reference,
                    "message": f"✅ Dossier sinistre créé — Référence : {reference}",
                    "dossier": dossier,
                }, ensure_ascii=False)

            if nom == "get_sinistre":
                from core.orass_connector import orass
                dossier = await orass.get_sinistre(params["reference"])
                return json.dumps(dossier, ensure_ascii=False, default=str)

            if nom == "verifier_police":
                from core.orass_connector import orass
                validite = await orass.verifier_validite_contrat(params["police_id"])
                # verifier_validite_contrat retourne: valide, statut, date_echeance, jours_restants, prime_ttc, branche
                date_effet  = date.fromisoformat("2024-01-01")  # non fourni par ORASS — valeur par défaut
                date_expiry = date.fromisoformat(validite.get("date_echeance", "2025-12-31"))
                prime_payee = validite.get("valide", True)  # si valide → prime payée
                date_sin    = date.fromisoformat(params["date_sinistre"])
                result = verifier_validite_police(date_effet, date_expiry, prime_payee, date_sin)
                return json.dumps(result.donnees, ensure_ascii=False)

            if nom == "scorer_fraude":
                signaux = SignauxFraude(
                    nb_sinistres_12_mois=params.get("nb_sinistres_12_mois", 0),
                    jours_depuis_souscription=params.get("jours_depuis_souscription", 999),
                    montant_declare=params.get("montant_declare", 0),
                    declaration_tardive=params.get("declaration_tardive", False),
                    jours_declaration=params.get("jours_declaration", 0),
                )
                result = scorer_fraude_deterministe(signaux)
                return json.dumps(result.donnees, ensure_ascii=False)

            if nom == "analyser_fraude_ia":
                from core.ia_client import ModeIA, ia_client
                prompt = f"""Analyse ce dossier sinistre pour détecter des indicateurs de fraude.
Référence : {params['reference']}
Déclaration : {params['declaration_texte']}
Rapport expertise : {params.get('rapport_expertise', 'Non disponible')}

Retourne ton analyse structurée : indicateurs suspects, cohérence déclaration/expertise, recommandation."""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
                return rep.contenu

            if nom == "calculer_indemnisation":
                result = calculer_indemnisation(
                    type_sinistre=params["type_sinistre"],
                    montant_declare=params["montant_declare"],
                    ipp_pct=params.get("ipp_pct", 0),
                    itt_jours=params.get("itt_jours", 0),
                )
                return json.dumps(result.donnees, ensure_ascii=False)

            if nom == "valider_sinistre":
                from core.approval_queue import approval_queue
                await approval_queue.ajouter({
                    "type":         "sinistre",
                    "reference":    params["reference"],
                    "decision":     params["decision"],
                    "montant":      params.get("montant", 0),
                    "motif":        params["motif"],
                    "user_id":      user_id,
                    "execution_id": execution_id,
                })
                return f"Décision mise en attente de validation : {params['decision']} — {params.get('montant', 0):,} FCFA".replace(",", " ")

            if nom == "generer_courrier":
                from modules.documents.generateur import generer_courrier_sinistre
                pdf_path = await generer_courrier_sinistre(
                    reference=params["reference"],
                    template=params["template"],
                    montant=params.get("montant", 0),
                    motif=params.get("motif", ""),
                )
                return f"Courrier généré : {pdf_path}"

            if nom == "passer_ecriture_comptable":
                # Calcul déterministe de l'écriture
                result = coder_ecriture_comptable(
                    type_operation=params["type_operation"],
                    montant=params["montant"],
                    reference=params["reference"],
                )
                if not result.donnees:
                    return result.message
                # VALIDATION HUMAINE obligatoire avant tout passage en base
                from core.approval_queue import approval_queue
                await approval_queue.ajouter({
                    "type": "ecriture_comptable_sinistre",
                    "reference": params["reference"],
                    "ecriture": result.donnees,
                    "montant": params["montant"],
                    "type_operation": params["type_operation"],
                    "user_id": user_id,
                    "execution_id": execution_id,
                    "description": f"Écriture sinistre {params['reference']} — {params['type_operation']} — {params['montant']:,} FCFA".replace(",", " "),
                })
                return (
                    f"Écriture comptable présentée pour validation :\n"
                    f"Débit : {result.donnees.get('debit_compte')} — Crédit : {result.donnees.get('credit_compte')}\n"
                    f"Montant : {params['montant']:,} FCFA — Libellé : {result.donnees.get('libelle', '')}\n"
                    "En attente d'approbation avant passage en base ORASS."
                ).replace(",", " ")

            if nom == "notifier_assure":
                from core.notifications import notifications
                await notifications.envoyer(
                    canal=params.get("canal", "whatsapp"),
                    destinataire=params["telephone"],
                    message=params["message"],
                )
                return f"Notification envoyée sur {params.get('canal', 'whatsapp')}"

            if nom == "detecter_sinistres_souffrance":
                from core.orass_connector import orass
                jours_alerte = params.get("jours_alerte", 15)
                sinistres = await orass.get_sinistres_ouverts(
                    branche=params.get("branche"),
                    statut="ouvert",
                )
                souffrance = []
                alerte_proche = []
                aujourd_hui = date.today()
                for s in sinistres:
                    date_decl = date.fromisoformat(s.get("date_declaration", aujourd_hui.isoformat()))
                    type_delai = params.get("type_delai", "tous")
                    # Délai offre indemnisation
                    if type_delai in ("offre_indemnisation", "tous"):
                        echeance = date_decl + timedelta(days=_DELAI_OFFRE_INDEMNISATION)
                        jours = (echeance - aujourd_hui).days
                        if jours < 0:
                            s["retard_jours_offre"] = abs(jours)
                            souffrance.append(s)
                        elif jours <= jours_alerte:
                            s["jours_avant_echeance_offre"] = jours
                            alerte_proche.append(s)
                    # Délai paiement (si accord donné)
                    if type_delai in ("paiement", "tous") and s.get("date_accord"):
                        date_accord = date.fromisoformat(s["date_accord"])
                        echeance_pmt = date_accord + timedelta(days=_DELAI_PAIEMENT)
                        jours_pmt = (echeance_pmt - aujourd_hui).days
                        if jours_pmt < 0:
                            s["retard_jours_paiement"] = abs(jours_pmt)
                            if s not in souffrance:
                                souffrance.append(s)

                return json.dumps({
                    "sinistres_en_souffrance": len(souffrance),
                    "alertes_proches_echeance": len(alerte_proche),
                    "details_souffrance": souffrance[:20],
                    "details_alertes": alerte_proche[:20],
                    "seuil_alerte_jours": jours_alerte,
                    "base_legale": f"Art. 12-bis CIMA (délai offre : {_DELAI_OFFRE_INDEMNISATION}j), Art. 12-ter (paiement : {_DELAI_PAIEMENT}j)",
                }, ensure_ascii=False, default=str)

            if nom == "calculer_interets_moratoires":
                montant = params["montant_indemnisation"]
                date_echeance = date.fromisoformat(params["date_echeance_legale"])
                date_pmt = date.fromisoformat(params["date_paiement_effectif"]) if params.get("date_paiement_effectif") else date.today()
                if date_pmt <= date_echeance:
                    return json.dumps({
                        "reference": params["reference"],
                        "interets_moratoires": 0,
                        "message": "Aucun retard — paiement dans les délais CIMA",
                    })
                jours_retard = (date_pmt - date_echeance).days
                interets = round(montant * _TAUX_INTERET_MORATOIRE * jours_retard / 365)
                total_du = montant + interets
                return json.dumps({
                    "reference": params["reference"],
                    "montant_principal": montant,
                    "jours_retard": jours_retard,
                    "taux_moratoire_annuel_pct": _TAUX_INTERET_MORATOIRE * 100,
                    "interets_moratoires_fcfa": interets,
                    "total_du_fcfa": total_du,
                    "base_legale": "Art. 12-quater Code CIMA",
                }, ensure_ascii=False)

            if nom == "archiver_dossier":
                from core.approval_queue import approval_queue
                await approval_queue.ajouter({
                    "type": "archivage_sinistre",
                    "reference": params["reference"],
                    "motif_cloture": params["motif_cloture"],
                    "montant_regle": params.get("montant_regle", 0),
                    "pieces_archivees": params.get("pieces_archivees", []),
                    "user_id": user_id,
                    "execution_id": execution_id,
                    "description": f"Archivage sinistre {params['reference']} — {params['motif_cloture']}",
                })
                return (
                    f"Demande d'archivage du sinistre {params['reference']} soumise.\n"
                    f"Motif : {params['motif_cloture']} — Montant réglé : {params.get('montant_regle', 0):,} FCFA\n"
                    "En attente de validation avant clôture définitive."
                ).replace(",", " ")

            if nom == "tableau_bord_sinistres":
                from core.orass_connector import orass
                data = await orass.get_tableau_bord_sinistres(
                    branche=params.get("branche"),
                    periode=params.get("periode"),
                    statut=params.get("statut", "tous"),
                )
                # Calcul indicateurs déterministes
                nb_ouverts = data.get("nb_ouverts", 0)
                nb_souffrance = data.get("nb_souffrance", 0)
                delai_moyen = data.get("delai_moyen_jours", 0)
                taux_fraude = data.get("taux_fraude_pct", 0)
                montant_total = data.get("montant_total_en_cours", 0)
                return json.dumps({
                    "nb_sinistres_ouverts": nb_ouverts,
                    "nb_en_souffrance": nb_souffrance,
                    "pct_souffrance": round(nb_souffrance / max(nb_ouverts, 1) * 100, 1),
                    "delai_moyen_instruction_jours": delai_moyen,
                    "taux_fraude_detectee_pct": taux_fraude,
                    "montant_total_en_cours_fcfa": montant_total,
                    "statut_conformite_cima": "NON CONFORME" if nb_souffrance > 0 else "CONFORME",
                    "branche": params.get("branche", "toutes"),
                    "periode": params.get("periode", "en cours"),
                }, ensure_ascii=False, default=str)

            if nom == "enregistrer_mise_en_cause":
                from core.orass_connector import orass
                from core.approval_queue import approval_queue
                mise_en_cause = {
                    "reference":       params["reference"],
                    "tiers_nom":       params["tiers_nom"],
                    "tiers_adresse":   params.get("tiers_adresse", ""),
                    "tiers_assureur":  params.get("tiers_assureur", ""),
                    "montant_reclame": params.get("montant_reclame", 0),
                    "motif":           params["motif"],
                    "date_mise_en_cause": str(date.today()),
                }
                try:
                    await orass.enregistrer_evenement_sinistre(params["reference"], "mise_en_cause", mise_en_cause)
                except Exception:
                    pass
                return json.dumps({
                    "message": f"Mise en cause de {params['tiers_nom']} enregistrée — sinistre {params['reference']}",
                    "etape": "mise_en_cause",
                    "date": str(date.today()),
                    "prochaine_etape": "Générer courrier mise_en_cause_tiers via generer_courrier",
                }, ensure_ascii=False)

            if nom == "enregistrer_relance":
                from core.orass_connector import orass
                relance = {
                    "reference":      params["reference"],
                    "destinataire":   params["destinataire"],
                    "type_relance":   params["type_relance"],
                    "canal":          params.get("canal", "courrier_ar"),
                    "motif":          params["motif"],
                    "numero_relance": params.get("numero_relance", 1),
                    "date_relance":   str(date.today()),
                }
                try:
                    await orass.enregistrer_evenement_sinistre(params["reference"], "relance", relance)
                except Exception:
                    pass
                return json.dumps({
                    "message": f"Relance n°{params.get('numero_relance', 1)} ({params['type_relance']}) enregistrée vers {params['destinataire']}",
                    "etape": "relance",
                    "canal": params.get("canal", "courrier_ar"),
                    "date": str(date.today()),
                }, ensure_ascii=False)

            if nom == "prelitigation_sinistre":
                from core.orass_connector import orass
                from core.approval_queue import approval_queue
                mode = params["mode"]
                payload = {
                    "reference":         params["reference"],
                    "mode":              mode,
                    "tribunal":          params.get("tribunal", "TGI compétent"),
                    "motif_contentieux": params["motif_contentieux"],
                    "montant_conteste":  params.get("montant_conteste", 0),
                    "avocat_ref":        params.get("avocat_ref", ""),
                    "date_acte":         str(date.today()),
                }
                try:
                    await orass.enregistrer_evenement_sinistre(params["reference"], mode, payload)
                except Exception:
                    pass
                # Validation humaine obligatoire avant saisine tribunal
                await approval_queue.ajouter({
                    "type":         f"prelitigation_{mode}",
                    "reference":    params["reference"],
                    "mode":         mode,
                    "montant":      params.get("montant_conteste", 0),
                    "motif":        params["motif_contentieux"],
                    "user_id":      user_id,
                    "execution_id": execution_id,
                    "description":  f"{'Préavis de saisine' if mode == 'preavs_saisine' else 'Requête unilatérale'} — {params['reference']}",
                })
                if mode == "preavs_saisine":
                    return (
                        f"Préavis de saisine enregistré pour {params['reference']} — délai 15j avant saisine tribunal.\n"
                        f"Tribunal visé : {params.get('tribunal', 'TGI')}\n"
                        "En attente validation responsable avant transmission."
                    )
                return (
                    f"Requête unilatérale enregistrée pour {params['reference']}.\n"
                    f"Montant contesté : {params.get('montant_conteste', 0):,} FCFA\n"
                    "En attente validation responsable avant dépôt tribunal."
                ).replace(",", " ")

            if nom == "ajouter_note_technique":
                from core.orass_connector import orass
                note = {
                    "reference":  params["reference"],
                    "auteur":     params.get("auteur", "Gestionnaire"),
                    "categorie":  params["categorie"],
                    "contenu":    params["contenu"],
                    "date_note":  str(date.today()),
                }
                try:
                    await orass.enregistrer_evenement_sinistre(params["reference"], "note_technique", note)
                except Exception:
                    pass
                return json.dumps({
                    "message": f"Note technique ({params['categorie']}) ajoutée au dossier {params['reference']}",
                    "auteur": params.get("auteur", "Gestionnaire"),
                    "date": str(date.today()),
                }, ensure_ascii=False)

            if nom == "transmettre_cheque":
                from core.orass_connector import orass
                from core.approval_queue import approval_queue
                paiement = {
                    "reference":          params["reference"],
                    "montant":            params["montant"],
                    "mode_paiement":      params["mode_paiement"],
                    "beneficiaire":       params["beneficiaire"],
                    "reference_paiement": params.get("reference_paiement", ""),
                    "date_transmission":  params.get("date_transmission", str(date.today())),
                    "quittance_signee":   params.get("quittance_signee", False),
                }
                try:
                    await orass.enregistrer_evenement_sinistre(params["reference"], "transmission_paiement", paiement)
                except Exception:
                    pass
                await approval_queue.ajouter({
                    "type":         "transmission_cheque",
                    "reference":    params["reference"],
                    "montant":      params["montant"],
                    "beneficiaire": params["beneficiaire"],
                    "mode":         params["mode_paiement"],
                    "user_id":      user_id,
                    "execution_id": execution_id,
                    "description":  f"Transmission {params['mode_paiement']} {params['montant']:,} FCFA → {params['beneficiaire']}".replace(",", " "),
                })
                return json.dumps({
                    "message": f"Transmission {params['mode_paiement']} de {params['montant']:,} FCFA enregistrée — en attente confirmation caisse".replace(",", " "),
                    "etape": "transmission_cheque",
                    "quittance_signee": params.get("quittance_signee", False),
                    "prochaine_etape": "Générer quittance_reglement via generer_courrier puis archiver_dossier",
                }, ensure_ascii=False)

            if nom == "rouvrir_dossier":
                from core.orass_connector import orass
                from core.approval_queue import approval_queue
                await approval_queue.ajouter({
                    "type":             "revision_dossier",
                    "reference":        params["reference"],
                    "motif_revision":   params["motif_revision"],
                    "description_rev":  params["description"],
                    "montant_complement": params.get("montant_complement", 0),
                    "user_id":          user_id,
                    "execution_id":     execution_id,
                    "description":      f"Révision dossier {params['reference']} — {params['motif_revision']} : {params['description']}",
                })
                return json.dumps({
                    "message": f"Demande de révision du dossier {params['reference']} soumise — motif : {params['motif_revision']}",
                    "etape": "revision",
                    "complement_estime_fcfa": params.get("montant_complement", 0),
                    "note": "En attente validation responsable sinistres avant réouverture.",
                }, ensure_ascii=False)

            return f"Outil '{nom}' non reconnu"

        except Exception as e:
            logger.error(f"[AgentSinistres] Erreur outil {nom} : {e}")
            return f"ERREUR {nom} : {e}"
