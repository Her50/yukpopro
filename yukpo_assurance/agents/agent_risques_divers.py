"""
Agent Risques Divers — Assurance non-vie zone CIMA.

Branches couvertes :
  - RC Générale / RC Professionnelle / RC Décennale
  - Dommages Ouvrage (DO) / Construction
  - Accidents Corporels Individuels (ACI)
  - Assurance Agriculture (récoltes, bétail, matériels agricoles)
  - Crédit / Caution / Garantie financière
  - Protection Juridique
  - Assistance (voyage, rapatriement, panne)
  - Risques divers non classés (incendie industriel, vol, etc.)
  - MRH (Multirisques Habitation)

Intègre :
  - Note Technique d'Instruction Sinistre (NTIS) — visa hiérarchique avant règlement
  - Portail prestataires (experts, entrepreneurs, avocats, médecins ACI)
  - Suivi délais réglementaires CIMA
  - OCR / Vision pour pièces justificatives
"""
from __future__ import annotations
import json
import logging
import uuid
from datetime import date, datetime, timezone
from core.agent_orchestrateur import TypeAgent
from agents.base_agent import BaseAgent

logger = logging.getLogger("yukpo_assurance.agents.risques_divers")

# ─── Tables réglementaires ────────────────────────────────────────────────────

# Barème ACI — Accidents Corporels Individuels (Art. 151-160 CIMA)
_SMIG_MENSUEL_FCFA = 36_270

_CAPITAL_DECES_DEFAUT   = 5_000_000   # FCFA — à lire dans la police
_TAUX_REMBOURSEMENT_ACI: dict[str, float] = {
    "frais_medicaux":   0.80,
    "frais_chirurgie":  0.90,
    "hospitalisation":  0.90,
    "kine_readaptation": 0.70,
}

# Délais réglementaires CIMA risques divers (Art. 12-bis / 12-ter)
_DELAIS_CIMA_RD: dict[str, int] = {
    "declaration_sinistre_max_jours":   5,    # Art. 12 — délai déclaration assuré
    "expertise_max_jours":             30,    # Art. 12 — convocation expert
    "rapport_expertise_max_jours":     30,    # Art. 12 — remise rapport après expertise
    "offre_reglement_max_jours":       90,    # Art. 12-bis — offre règlement
    "paiement_apres_accord_jours":     45,    # Art. 12-ter
    "interet_moratoire_taux_annuel": 0.12,    # 12 % / an au-delà du délai
}

# Seuils validation hiérarchique
_SEUIL_CHEF_SERVICE   =  2_000_000   # < 2M FCFA : visa chef de service
_SEUIL_DIR_TECHNIQUE  = 10_000_000   # < 10M FCFA : visa directeur technique
# ≥ 10M FCFA : direction générale


class AgentRisquesDivers(BaseAgent):
    type_agent = TypeAgent.RISQUES_DIVERS

    def _system_prompt(self) -> str:
        return """Tu es l'Agent Risques Divers de YukpoAssurance, expert en gestion des sinistres non-vie zone CIMA (hors RC Auto et Maladie).

BRANCHES GÉRÉES :
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
A. RC GÉNÉRALE / RC PROFESSIONNELLE
   Dommages causés à des tiers par l'activité professionnelle ou privée.
   Éléments clés : lien de causalité, mise en cause assurée, garantie RC, franchise.

B. RC DÉCENNALE / DOMMAGES OUVRAGE (CONSTRUCTION)
   DO : Assureur de l'ouvrage → règle vite, subroge contre constructeur.
   RC Décennale : Couvre le constructeur pour vice caché 10 ans.
   Points : rapport d'expertise technique bâtiment, DAACT, réception des travaux.

C. ACCIDENTS CORPORELS INDIVIDUELS (ACI)
   Capital décès, invalidité permanente (IP), ITT, frais médicaux.
   Barème : IP selon tableau contractuel, ITT = IJ contractuelle × jours.

D. AGRICULTURE
   Récoltes (grêle, sécheresse, inondation), bétail (épizootie, accident),
   matériels agricoles, RC exploitation agricole.
   Points : constats météo, expertise agricole, calendrier cultural.

E. CRÉDIT / CAUTION
   Non-remboursement emprunteur, défaillance caution.
   Points : mise en demeure préalable, justificatifs impayés, créance certaine.

F. PROTECTION JURIDIQUE
   Prise en charge frais de justice, honoraires avocat, expertise amiable.
   Points : litiges couverts, plafond défense, choix libre de l'avocat.

G. ASSISTANCE (VOYAGE / RAPATRIEMENT)
   Rapatriement médical, avance de frais médicaux à l'étranger, retour anticipé.
   Points : certificat médical sur place, coordination 24h/24.

H. MRH (MULTIRISQUES HABITATION)
   Incendie, dégâts des eaux, vol, catastrophes naturelles, RC vie privée.
   Points : état des lieux, PV de police (vol), rapport expertise immobilière.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WORKFLOW GÉNÉRAL RÈGLEMENT SINISTRE RISQUES DIVERS :

ÉTAPE 1 — Ouverture dossier
  → Recueillir : N° police, date sinistre, nature, circonstances, montant estimé
  → Vérifier couverture (get_police_risques_divers)

ÉTAPE 2 — Analyse déclaration
  → Analyser les pièces transmises (OCR/IA)
  → Scorer fraude si anomalie détectée

ÉTAPE 3 — Expertise
  → Planifier expert (RC, bâtiment, agricole, judiciaire selon branche)
  → Notifier assuré + expert via portail (token sécurisé + WhatsApp)
  → Attendre rapport d'expertise (délai CIMA ≤ 30 j)

ÉTAPE 4 — Calcul indemnisation
  → Appliquer garanties contractuelles, franchise, plafonds
  → ACI : calcul IP/ITT/décès selon barème contractuel
  → RC : évaluation préjudice tiers
  → DO : coût travaux réfection selon devis entrepreneur

ÉTAPE 5 — Note Technique d'Instruction Sinistre (NTIS)
  → Rédiger la note via IA (generer_note_technique)
  → Soumettre pour validation hiérarchique (valider_note_technique)
  → NE PAS soumettre d'offre avant visa hiérarchique

ÉTAPE 6 — Offre de règlement
  → Envoyer offre assuré via portail (notifier_intervention_assure_rd)
  → Délai réponse assuré : 15 jours
  → Art. 12-bis : offre envoyée ≤ 90 j après déclaration sinistre

ÉTAPE 7 — Accord et paiement
  → Accord assuré → passer écriture règlement (passer_ecriture_rd)
  → Virement ≤ 45 j après accord (Art. 12-ter)
  → Clôture dossier

ÉTAPE 8 — Subrogatoire (si tiers responsable)
  → Identifier responsable, diligenter recours (traiter_recours_rd)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NOTE TECHNIQUE D'INSTRUCTION SINISTRE (NTIS) — OBLIGATOIRE :
Toute proposition de règlement doit être précédée d'une note technique
validée par la hiérarchie. La note comprend :
  1. Identité des parties
  2. Circonstances et chronologie
  3. Analyse de la garantie
  4. Analyse des responsabilités
  5. Rapport d'expertise (synthèse)
  6. Évaluation des préjudices
  7. Proposition d'indemnisation
  8. Déduction franchise / vétusté
  9. Montant net proposé
  10. Délais réglementaires respectés ?
  11. Risques et réserves juridiques
  12. Recommandation de règlement

RÈGLES STRICTES :
- Jamais d'offre sans NTIS validée
- Franchise toujours déduite avant proposition
- Vétusté à appliquer sur matériels et bâtiments selon âge
- RC : vérifier que le tiers blessé est bien couvert par la police
- DO : préjudice limité aux dommages de nature décennale
- ACI : IP partielle → prorata du capital assuré
- Crédit : vérifier épuisement recours amiable avant indemnisation
- Protection juridique : vérifier litiges exclus (famille, pénal, fiscalité)
- Agriculture : attendre expertise agricole officielle (direction agriculture)
- Assistance : coordination directe avec prestataires médicaux locaux
- Tout règlement ≥ 2 000 000 FCFA → visa chef de service minimum
- Tout règlement ≥ 10 000 000 FCFA → visa directeur général"""

    def _definir_outils(self) -> list[dict]:
        return [
            # ── 1. Ouverture & Vérification ────────────────────────────────────
            {
                "name": "get_sinistre_rd",
                "description": "Récupère le dossier sinistre risques divers depuis ORASS",
                "input_schema": {"type": "object", "properties": {
                    "reference_sinistre": {"type": "string"},
                }, "required": ["reference_sinistre"]},
            },
            {
                "name": "verifier_police_rd",
                "description": "Vérifie la police : validité, branche couverte, garanties, plafonds, franchise, exclusions",
                "input_schema": {"type": "object", "properties": {
                    "numero_police":  {"type": "string"},
                    "date_sinistre":  {"type": "string", "description": "YYYY-MM-DD"},
                    "branche":        {"type": "string", "enum": [
                        "rc_generale", "rc_professionnelle", "rc_decennale",
                        "dommages_ouvrage", "accidents_corporels", "agriculture",
                        "credit_caution", "protection_juridique", "assistance",
                        "mrh", "risques_divers_nc",
                    ]},
                }, "required": ["numero_police", "date_sinistre", "branche"]},
            },
            {
                "name": "analyser_declaration_sinistre_rd",
                "description": "Analyse IA de la déclaration de sinistre : cohérence, circonstances, pièces jointes (OCR/Vision)",
                "input_schema": {"type": "object", "properties": {
                    "reference_sinistre": {"type": "string"},
                    "branche":            {"type": "string"},
                    "declaration_texte":  {"type": "string", "description": "Texte de la déclaration"},
                    "pieces": {"type": "array", "items": {
                        "type": "object",
                        "properties": {
                            "type_piece": {"type": "string", "enum": [
                                "declaration_sinistre", "pv_police", "constat_amiable",
                                "rapport_expertise", "photos_degats", "devis_reparation",
                                "factures_reparation", "certificat_medical_aci",
                                "attestation_hospitalisation", "rapport_agricole",
                                "mise_en_demeure", "jugement_tribunal",
                                "facture_avocat", "facture_assistance",
                                "daact_reception_travaux", "permis_construire",
                                "autre",
                            ]},
                            "image_base64": {"type": "string"},
                            "description":  {"type": "string"},
                        },
                        "required": ["type_piece"],
                    }},
                }, "required": ["reference_sinistre", "branche"]},
            },
            {
                "name": "scorer_fraude_rd",
                "description": "Détection de fraude : incohérences chronologiques, déclarations multiples, montants suspects, tiers complices",
                "input_schema": {"type": "object", "properties": {
                    "reference_sinistre": {"type": "string"},
                    "branche":            {"type": "string"},
                    "montant_declare":    {"type": "number"},
                    "circonstances":      {"type": "string"},
                }, "required": ["reference_sinistre", "branche"]},
            },
            # ── 2. Expertise ───────────────────────────────────────────────────
            {
                "name": "planifier_expertise_rd",
                "description": "Planifie et notifie l'expert (bâtiment, agricole, judiciaire, RC) via portail sécurisé + WhatsApp",
                "input_schema": {"type": "object", "properties": {
                    "reference_sinistre": {"type": "string"},
                    "type_expert":        {"type": "string", "enum": [
                        "expert_batiment", "expert_agricole", "expert_judiciaire",
                        "expert_rc_generale", "expert_incendie", "expert_vol",
                        "medecin_expert_aci", "conseiller_juridique",
                    ]},
                    "nom_expert":         {"type": "string"},
                    "telephone_expert":   {"type": "string"},
                    "date_expertise":     {"type": "string", "description": "YYYY-MM-DD"},
                    "lieu_expertise":     {"type": "string"},
                }, "required": ["reference_sinistre", "type_expert"]},
            },
            {
                "name": "enregistrer_rapport_expertise_rd",
                "description": "Enregistre le rapport d'expertise : conclusions, montant évalué, réserves, photos",
                "input_schema": {"type": "object", "properties": {
                    "reference_sinistre":  {"type": "string"},
                    "nom_expert":          {"type": "string"},
                    "date_expertise":      {"type": "string"},
                    "conclusions":         {"type": "string"},
                    "montant_evalue":      {"type": "number", "description": "Montant de préjudice évalué FCFA"},
                    "vetuste_pct":         {"type": "number", "description": "Taux de vétusté appliqué (0-100)"},
                    "reserves":            {"type": "string", "description": "Réserves et points litigieux"},
                    "pieces_jointes":      {"type": "array", "items": {"type": "string"}, "description": "URLs/IDs photos expertises"},
                }, "required": ["reference_sinistre", "conclusions", "montant_evalue"]},
            },
            # ── 3. Calcul indemnisation par branche ────────────────────────────
            {
                "name": "calculer_indemnisation_rc",
                "description": "Calcul indemnisation RC générale/RC Pro : préjudice tiers (matériel + corporel + moral), franchise déduite",
                "input_schema": {"type": "object", "properties": {
                    "reference_sinistre":   {"type": "string"},
                    "montant_prejudice_tiers": {"type": "number"},
                    "franchise":            {"type": "number", "default": 0},
                    "plafond_garantie":     {"type": "number"},
                    "type_prejudice":       {"type": "string", "enum": [
                        "materiel", "corporel_leger", "corporel_grave", "moral", "mixte"
                    ]},
                    "partage_responsabilite_pct": {"type": "number", "description": "% responsabilité assuré (0-100)", "default": 100},
                }, "required": ["reference_sinistre", "montant_prejudice_tiers", "franchise", "plafond_garantie"]},
            },
            {
                "name": "calculer_indemnisation_do",
                "description": "Calcul indemnisation Dommages Ouvrage : coût réfection travaux, vétusté, franchise DO",
                "input_schema": {"type": "object", "properties": {
                    "reference_sinistre":  {"type": "string"},
                    "nature_desordre":     {"type": "string", "description": "Description du désordre décennal"},
                    "montant_devis_refection": {"type": "number"},
                    "vetuste_pct":         {"type": "number", "description": "Taux vétusté (0-30% max en DO)", "default": 0},
                    "franchise_do":        {"type": "number"},
                    "plafond_garantie":    {"type": "number"},
                    "subrogation_constructeur": {"type": "boolean", "default": True},
                }, "required": ["reference_sinistre", "nature_desordre", "montant_devis_refection", "franchise_do"]},
            },
            {
                "name": "calculer_indemnisation_aci",
                "description": "Calcul indemnisation ACI : décès, IP partielle/totale, ITT, frais médicaux — selon barème contractuel",
                "input_schema": {"type": "object", "properties": {
                    "reference_sinistre":  {"type": "string"},
                    "type_sinistre":       {"type": "string", "enum": ["deces", "ip_totale", "ip_partielle", "itt", "frais_medicaux"]},
                    "capital_assure":      {"type": "number", "description": "Capital ACI souscrit FCFA"},
                    "taux_ip_pct":         {"type": "number", "description": "Taux IP reconnu (0-100) — si IP"},
                    "nb_jours_itt":        {"type": "integer", "description": "Nombre jours ITT"},
                    "ij_contractuelle":    {"type": "number", "description": "Indemnité journalière contractuelle FCFA/jour"},
                    "montant_frais_medicaux": {"type": "number"},
                    "franchise_jours":     {"type": "integer", "description": "Franchise carence ITT en jours", "default": 3},
                }, "required": ["reference_sinistre", "type_sinistre", "capital_assure"]},
            },
            {
                "name": "calculer_indemnisation_mrh",
                "description": "Calcul indemnisation MRH : incendie, dégâts des eaux, vol, catastrophe naturelle",
                "input_schema": {"type": "object", "properties": {
                    "reference_sinistre":  {"type": "string"},
                    "peril":               {"type": "string", "enum": [
                        "incendie", "degats_eaux", "vol_cambriolage",
                        "catastrophe_naturelle", "rc_vie_privee", "bris_glace", "autre"
                    ]},
                    "valeur_bien_assure":  {"type": "number"},
                    "montant_dommage":     {"type": "number"},
                    "vetuste_pct":         {"type": "number", "default": 0},
                    "franchise":           {"type": "number", "default": 0},
                    "valeur_neuf":         {"type": "boolean", "default": False, "description": "Garantie valeur à neuf souscrite ?"},
                }, "required": ["reference_sinistre", "peril", "montant_dommage", "franchise"]},
            },
            {
                "name": "calculer_indemnisation_agriculture",
                "description": "Calcul indemnisation agriculture : récoltes, bétail, matériels — selon constats et barèmes agricoles",
                "input_schema": {"type": "object", "properties": {
                    "reference_sinistre":  {"type": "string"},
                    "type_sinistre_agri":  {"type": "string", "enum": [
                        "recoltes_grele", "recoltes_secheresse", "recoltes_inondation",
                        "betail_epizootie", "betail_accident", "materiel_agricole", "rc_exploitation"
                    ]},
                    "surface_ha":          {"type": "number", "description": "Surface sinistrée (hectares)"},
                    "rendement_declare":   {"type": "number", "description": "Rendement déclaré (T/ha ou équivalent)"},
                    "taux_perte_constate_pct": {"type": "number", "description": "% perte constatée par l'expert agricole"},
                    "prix_unitaire_marche": {"type": "number"},
                    "franchise_pct":       {"type": "number", "default": 20, "description": "Franchise en % de la perte"},
                }, "required": ["reference_sinistre", "type_sinistre_agri"]},
            },
            # ── 4. Note Technique ──────────────────────────────────────────────
            {
                "name": "generer_note_technique",
                "description": "Génère la Note Technique d'Instruction Sinistre (NTIS) via IA — document obligatoire avant toute offre",
                "input_schema": {"type": "object", "properties": {
                    "reference_sinistre":     {"type": "string"},
                    "branche":                {"type": "string"},
                    "redacteur_nom":          {"type": "string"},
                    "resume_circonstances":   {"type": "string"},
                    "analyse_garantie":       {"type": "string"},
                    "analyse_responsabilite": {"type": "string"},
                    "synthese_expertise":     {"type": "string"},
                    "montant_expertise":      {"type": "number"},
                    "montant_propose":        {"type": "number"},
                    "franchise_deduite":      {"type": "number", "default": 0},
                    "vetuste_deduite_pct":    {"type": "number", "default": 0},
                    "reserves_juridiques":    {"type": "string"},
                    "recommandation":         {"type": "string", "enum": [
                        "regler_amiable", "regler_partiel", "rejeter", "soumettre_recours", "attendre_expertise"
                    ]},
                }, "required": [
                    "reference_sinistre", "branche", "redacteur_nom",
                    "resume_circonstances", "montant_propose", "recommandation",
                ]},
            },
            {
                "name": "valider_note_technique",
                "description": "Soumet la NTIS pour visa hiérarchique : chef service (<2M), directeur technique (2-10M), DG (≥10M)",
                "input_schema": {"type": "object", "properties": {
                    "reference_sinistre": {"type": "string"},
                    "note_id":            {"type": "string"},
                    "montant_propose":    {"type": "number"},
                    "urgence":            {"type": "boolean", "default": False},
                    "commentaire":        {"type": "string"},
                }, "required": ["reference_sinistre", "note_id", "montant_propose"]},
            },
            # ── 5. Interaction externe ─────────────────────────────────────────
            {
                "name": "notifier_intervention_assure_rd",
                "description": "Notifie l'assuré via portail sécurisé + WhatsApp (offre de règlement, demande de pièces, accord)",
                "input_schema": {"type": "object", "properties": {
                    "reference_sinistre": {"type": "string"},
                    "telephone_assure":   {"type": "string"},
                    "type_notification":  {"type": "string", "enum": [
                        "demande_pieces", "planification_expertise",
                        "offre_reglement", "accord_prealable",
                        "rejet_sinistre", "complement_information",
                    ]},
                    "montant_offre":      {"type": "number", "description": "Montant de l'offre (si offre_reglement)"},
                    "pieces_demandees":   {"type": "array", "items": {"type": "string"}},
                    "message_personnalise": {"type": "string"},
                }, "required": ["reference_sinistre", "telephone_assure", "type_notification"]},
            },
            {
                "name": "notifier_prestataire_rd",
                "description": "Notifie un prestataire externe (expert, entrepreneur, avocat, médecin) avec checklist de documents attendus",
                "input_schema": {"type": "object", "properties": {
                    "reference_sinistre": {"type": "string"},
                    "type_prestataire":   {"type": "string", "enum": [
                        "expert_batiment", "expert_agricole", "medecin_expert_aci",
                        "entrepreneur_refection", "avocat_protection_juridique",
                        "prestataire_assistance", "laboratoire_expertise",
                    ]},
                    "nom_prestataire":    {"type": "string"},
                    "telephone":          {"type": "string"},
                    "email":              {"type": "string"},
                    "documents_attendus": {"type": "array", "items": {"type": "string"}},
                    "date_limite":        {"type": "string", "description": "YYYY-MM-DD"},
                }, "required": ["reference_sinistre", "type_prestataire", "telephone"]},
            },
            # ── 6. Protection Juridique & Crédit ───────────────────────────────
            {
                "name": "gerer_protection_juridique",
                "description": "Gère un dossier protection juridique : validation litige couvert, budget défense, désignation avocat",
                "input_schema": {"type": "object", "properties": {
                    "reference_sinistre": {"type": "string"},
                    "nature_litige":      {"type": "string", "description": "Description du litige"},
                    "montant_enjeu":      {"type": "number"},
                    "nom_avocat":         {"type": "string"},
                    "plafond_defense":    {"type": "number"},
                    "stade_procedure":    {"type": "string", "enum": [
                        "amiable", "tribunal_premiere_instance", "appel", "cassation", "autre"
                    ]},
                }, "required": ["reference_sinistre", "nature_litige", "montant_enjeu"]},
            },
            {
                "name": "gerer_credit_caution",
                "description": "Traite un sinistre crédit/caution : vérification impayés, appel en garantie, subrogation débiteur",
                "input_schema": {"type": "object", "properties": {
                    "reference_sinistre": {"type": "string"},
                    "montant_creance":    {"type": "number", "description": "Montant total de la créance impayée"},
                    "nombre_echeances_impayees": {"type": "integer"},
                    "mise_en_demeure_effectuee": {"type": "boolean"},
                    "date_premiere_mise_en_demeure": {"type": "string"},
                    "recours_amiable_epuise": {"type": "boolean", "default": False},
                }, "required": ["reference_sinistre", "montant_creance", "mise_en_demeure_effectuee"]},
            },
            {
                "name": "gerer_assistance",
                "description": "Coordonne une demande d'assistance : rapatriement, hospitalisation à l'étranger, panne véhicule",
                "input_schema": {"type": "object", "properties": {
                    "reference_sinistre": {"type": "string"},
                    "type_assistance":    {"type": "string", "enum": [
                        "rapatriement_medical", "hospitalisation_etranger",
                        "retour_anticipé", "panne_vehicule", "recherche_medecin_local",
                        "avance_frais_medicaux", "autre"
                    ]},
                    "pays":               {"type": "string"},
                    "description":        {"type": "string"},
                    "montant_frais":      {"type": "number"},
                    "prestataire_local":  {"type": "string"},
                }, "required": ["reference_sinistre", "type_assistance", "pays"]},
            },
            # ── 7. Règlement & Clôture ─────────────────────────────────────────
            {
                "name": "valider_reglement_rd",
                "description": "Soumet la décision de règlement pour validation humaine finale",
                "input_schema": {"type": "object", "properties": {
                    "reference_sinistre": {"type": "string"},
                    "montant_net":        {"type": "number"},
                    "mode_paiement":      {"type": "string", "enum": ["virement", "cheque", "especes", "tiers_direct"]},
                    "beneficiaire":       {"type": "string"},
                    "rib_iban":           {"type": "string"},
                    "motif":              {"type": "string"},
                }, "required": ["reference_sinistre", "montant_net", "mode_paiement", "beneficiaire"]},
            },
            {
                "name": "passer_ecriture_rd",
                "description": "Passe les écritures comptables du règlement sinistre risques divers (PCSA-CIMA)",
                "input_schema": {"type": "object", "properties": {
                    "reference_sinistre": {"type": "string"},
                    "montant_reglement":  {"type": "number"},
                    "branche":            {"type": "string"},
                    "mode_paiement":      {"type": "string"},
                }, "required": ["reference_sinistre", "montant_reglement", "branche", "mode_paiement"]},
            },
            {
                "name": "traiter_recours_rd",
                "description": "Initie un recours subrogatoire contre le tiers responsable (RC, DO, assistance)",
                "input_schema": {"type": "object", "properties": {
                    "reference_sinistre":  {"type": "string"},
                    "identite_tiers":      {"type": "string"},
                    "assureur_tiers":      {"type": "string"},
                    "montant_recours":     {"type": "number"},
                    "type_recours":        {"type": "string", "enum": ["amiable", "judiciaire"]},
                    "pieces_subrogation":  {"type": "array", "items": {"type": "string"}},
                }, "required": ["reference_sinistre", "montant_recours", "type_recours"]},
            },
            {
                "name": "calculer_interets_moratoires_rd",
                "description": "Calcule les intérêts moratoires si les délais réglementaires CIMA ont été dépassés (12%/an)",
                "input_schema": {"type": "object", "properties": {
                    "reference_sinistre": {"type": "string"},
                    "montant_principal":  {"type": "number"},
                    "date_delai_depasse": {"type": "string", "description": "YYYY-MM-DD"},
                    "date_calcul":        {"type": "string", "description": "YYYY-MM-DD — par défaut aujourd'hui"},
                }, "required": ["reference_sinistre", "montant_principal", "date_delai_depasse"]},
            },
            # ── 8. Tableau de bord ─────────────────────────────────────────────
            {
                "name": "detecter_sinistres_rd_souffrance",
                "description": "Détecte les dossiers en souffrance : délais CIMA dépassés, expertises manquantes, NTIS non validées",
                "input_schema": {"type": "object", "properties": {
                    "branche":    {"type": "string", "description": "Filtrer par branche — vide = toutes"},
                    "seuil_jours": {"type": "integer", "default": 30, "description": "Sinistres ouverts depuis X jours"},
                }, "required": []},
            },
            {
                "name": "tableau_bord_rd",
                "description": "Tableau de bord sinistres risques divers : S/P par branche, délais, taux règlement, provisions",
                "input_schema": {"type": "object", "properties": {
                    "periode":    {"type": "string", "description": "ex: 2025-T1 ou 2025"},
                    "branche":    {"type": "string", "description": "Filtrer par branche — vide = toutes"},
                    "indicateur": {"type": "string", "enum": [
                        "sp_branche", "delais", "taux_reglement", "provisions", "fraude", "tous"
                    ]},
                }, "required": []},
            },
        ]

    def _prompt_questions_specifiques(self) -> str:
        return """
AGENT RISQUES DIVERS — quand demander une information :

1. BRANCHE D'ASSURANCE NON IDENTIFIÉE
   → "De quel type d'assurance s'agit-il pour ce sinistre ?"
   type_reponse: choix_multiple  choix: [
     "RC Générale / RC Professionnelle",
     "RC Décennale / Dommages Ouvrage (Construction)",
     "Accidents Corporels Individuels",
     "Agriculture (récoltes, bétail, matériels)",
     "Crédit / Caution",
     "Protection Juridique",
     "Assistance (voyage, rapatriement)",
     "Multirisques Habitation (MRH)",
     "Autre / Non classé"
   ]

2. NUMÉRO DE POLICE MANQUANT
   → "Quel est le numéro de la police d'assurance concernée par ce sinistre ?"
   type_reponse: texte_libre

3. DATE DU SINISTRE MANQUANTE
   → "Quelle est la date exacte à laquelle le sinistre s'est produit ?"
   type_reponse: date

4. DÉCLARATION DE SINISTRE ABSENTE
   → "Veuillez envoyer la déclaration de sinistre signée ou décrire les circonstances complètes de l'événement."
   type_reponse: texte_libre

5. PHOTOS / RAPPORT D'EXPERTISE MANQUANTS (MRH, RC, DO)
   → "Veuillez transmettre les photos des dégâts et/ou le rapport d'expertise technique."
   type_reponse: images  nombre_images_max: 10  formats_acceptes: ["jpg", "png", "pdf"]

6. PV DE POLICE ABSENT (vol, cambriolage)
   → "Pour un sinistre vol, le procès-verbal de la police est obligatoire. Pouvez-vous le transmettre ?"
   type_reponse: image  nombre_images_max: 1  formats_acceptes: ["jpg", "png", "pdf"]

7. CERTIFICAT MÉDICAL ACI ABSENT
   → "Pour un sinistre Accidents Corporels, veuillez joindre le certificat médical initial et le rapport d'invalidité établi par le médecin traitant ou l'expert médical."
   type_reponse: images  nombre_images_max: 3  formats_acceptes: ["jpg", "png", "pdf"]

8. DEVIS DE RÉFECTION ABSENT (Dommages Ouvrage / MRH incendie)
   → "Veuillez transmettre le(s) devis d'entrepreneur(s) agréé(s) pour les travaux de réfection."
   type_reponse: images  nombre_images_max: 5  formats_acceptes: ["jpg", "png", "pdf"]

9. RAPPORT EXPERTISE AGRICOLE ABSENT
   → "Pour un sinistre agricole, le rapport de l'expert agréé par la Direction de l'Agriculture est requis. Pouvez-vous le fournir ?"
   type_reponse: image  nombre_images_max: 2  formats_acceptes: ["jpg", "png", "pdf"]

10. JUSTIFICATIFS IMPAYÉS CRÉDIT / CAUTION ABSENTS
    → "Veuillez transmettre les relevés de compte attestant les impayés, la mise en demeure envoyée au débiteur et l'accusé de réception."
    type_reponse: images  nombre_images_max: 5  formats_acceptes: ["jpg", "png", "pdf"]

11. FACTURE AVOCAT / JUSTIFICATIF PROTECTION JURIDIQUE ABSENT
    → "Pour la prise en charge Protection Juridique, veuillez transmettre la convention d'honoraires ou la facture de l'avocat ainsi que la nature précise du litige."
    type_reponse: images  nombre_images_max: 3  formats_acceptes: ["jpg", "png", "pdf"]

12. TAUX D'INVALIDITÉ NON PRÉCISÉ (ACI)
    → "Quel est le taux d'invalidité permanente reconnu par le médecin expert ? (entre 0 et 100%)"
    type_reponse: texte_libre

13. MONTANT DU SINISTRE NON PRÉCISÉ
    → "Quel est le montant estimé des dégâts ou du préjudice subi ? (en FCFA)"
    type_reponse: texte_libre

14. IDENTITÉ DU TIERS RESPONSABLE INCONNUE (RC)
    → "Avez-vous les coordonnées de la personne ou société responsable du sinistre ? (nom, adresse, assureur si connu)"
    type_reponse: texte_libre

15. DAACT / RÉCEPTION TRAVAUX ABSENTE (Dommages Ouvrage)
    → "Veuillez fournir la Déclaration Attestant l'Achèvement et la Conformité des Travaux (DAACT) ou le procès-verbal de réception des travaux."
    type_reponse: image  nombre_images_max: 1  formats_acceptes: ["jpg", "png", "pdf"]

16. PRESTATAIRE ASSISTANCE NON IDENTIFIÉ
    → "Quel est le prestataire médical ou d'assistance sur place ? (nom de la clinique, médecin, ou société d'assistance locale)"
    type_reponse: texte_libre

RÈGLE : Identifier branche et numéro police en premier. Pour les pièces justificatives, utiliser les types image/images. Ne jamais proposer de règlement avant validation de la Note Technique d'Instruction Sinistre (NTIS).
"""

    def _necessite_validation(self, nom_outil: str, params: dict, resultat: str) -> bool:
        if nom_outil == "valider_reglement_rd":
            return params.get("montant_net", 0) >= 500_000
        if nom_outil in ("calculer_indemnisation_rc", "calculer_indemnisation_do"):
            return True   # Toujours valider RC et DO
        if nom_outil == "calculer_indemnisation_aci" and params.get("type_sinistre") == "deces":
            return True
        if nom_outil == "gerer_credit_caution":
            return True
        return False

    async def _executer_outil(self, nom: str, params: dict, user_id: int, execution_id: str) -> str:
        try:
            # ── get_sinistre_rd ──────────────────────────────────────────────
            if nom == "get_sinistre_rd":
                from core.orass_connector import orass
                ref = params.get("reference_sinistre", "")
                sinistre = await orass.get_sinistre(ref)
                return json.dumps(sinistre or {"reference": ref, "statut": "non_trouve"}, ensure_ascii=False)

            # ── verifier_police_rd ───────────────────────────────────────────
            if nom == "verifier_police_rd":
                from core.orass_connector import orass
                validite = await orass.verifier_validite_contrat(params.get("numero_police", ""))
                branche = params.get("branche", validite.get("branche", ""))
                return json.dumps({
                    "police_valide":   validite.get("valide", False),
                    "branche":         branche,
                    "garanties":       {},  # non fourni par verifier_validite_contrat
                    "plafond_garantie": 50_000_000,
                    "franchise":       50_000,
                    "exclusions":      [],
                    "prime_payee":     validite.get("valide", True),
                }, ensure_ascii=False)

            # ── analyser_declaration_sinistre_rd ─────────────────────────────
            if nom == "analyser_declaration_sinistre_rd":
                from core.ia_client import ModeIA, ia_client
                pieces = params.get("pieces", [])
                branche = params.get("branche", "inconnu")
                types_pieces = [p.get("type_piece") for p in pieces]

                # ── OCR Vision par image ──────────────────────────────────────
                descriptions_vision = []
                nb_vision_ok = 0
                for p in pieces:
                    type_p = p.get("type_piece", "document")
                    b64 = p.get("image_base64", "")
                    if b64 and b64.startswith("data:"):
                        try:
                            b64 = b64.split(",", 1)[1]
                        except IndexError:
                            pass

                    if b64:
                        prompt_ocr = (
                            f"Tu es expert OCR pour documents d'assurance CIMA zone Afrique. "
                            f"Analyse cette image de type '{type_p}' (sinistre branche {branche}). "
                            f"Extrais en JSON : dates, montants (FCFA), parties impliquées, "
                            f"numéros de référence, description des dommages, signatures/cachets présents, "
                            f"anomalies ou signes de falsification. Retourne UNIQUEMENT le JSON."
                        )
                        try:
                            rep_vision = await ia_client.analyser_image_vision(
                                image_b64=b64,
                                prompt=prompt_ocr,
                                mode=ModeIA.PRECISION,
                            )
                            descriptions_vision.append(
                                f"[{type_p}] OCR OK:\n{rep_vision.contenu[:400]}"
                            )
                            nb_vision_ok += 1
                        except Exception as e_v:
                            logger.warning(f"[RisquesDivers] Vision IA {type_p}: {e_v}")
                            descriptions_vision.append(f"[{type_p}] : image fournie (Vision IA non disponible)")
                    elif p.get("description"):
                        descriptions_vision.append(f"[{type_p}] : {p['description']}")

                # Synthèse IA sur la déclaration + données OCR
                prompt_synthese = f"""Tu es expert sinistres CIMA, branche {branche}.
Analyse cette déclaration de sinistre :

DÉCLARATION : {params.get('declaration_texte', 'non fournie')}

DONNÉES EXTRAITES PAR OCR/VISION IA ({nb_vision_ok}/{len(pieces)} images analysées) :
{chr(10).join(descriptions_vision) if descriptions_vision else 'Aucune image fournie'}

Évalue :
1. COHÉRENCE de la déclaration avec les pièces jointes
2. POINTS D'ATTENTION et risques fraude
3. PIÈCES MANQUANTES pour instruire le dossier
4. PROCHAINES ÉTAPES recommandées"""

                rep = await ia_client.appeler(prompt=prompt_synthese, mode=ModeIA.PRECISION)
                return json.dumps({
                    "branche":           branche,
                    "nb_pieces":         len(pieces),
                    "nb_vision_ok":      nb_vision_ok,
                    "types_pieces":      types_pieces,
                    "extractions_ocr":   descriptions_vision,
                    "analyse_coherence": rep.contenu,
                }, ensure_ascii=False)

            # ── scorer_fraude_rd ─────────────────────────────────────────────
            if nom == "scorer_fraude_rd":
                montant = params.get("montant_declare", 0)
                branche = params.get("branche", "")
                score = 0.15   # Score de base
                # Heuristiques fraude
                if montant > 50_000_000:
                    score += 0.20
                if branche in ("vol_cambriolage", "mrh") and montant > 10_000_000:
                    score += 0.10
                return json.dumps({
                    "score_fraude":  round(min(score, 1.0), 2),
                    "niveau_risque": "ÉLEVÉ" if score > 0.6 else ("MOYEN" if score > 0.3 else "FAIBLE"),
                    "enquete_requise": score > 0.5,
                }, ensure_ascii=False)

            # ── planifier_expertise_rd ───────────────────────────────────────
            if nom == "planifier_expertise_rd":
                from core.portail_externe import portail_externe
                ref = params.get("reference_sinistre", "")
                type_expert = params.get("type_expert", "")
                tel = params.get("telephone_expert", "")

                if tel:
                    intervention = await portail_externe.creer_intervention(
                        type_intervention=type_expert,
                        reference_sinistre=ref,
                        branche="risques_divers",
                        destinataire_nom=params.get("nom_expert", "Expert"),
                        destinataire_telephone=tel,
                        documents_requis=["rapport_expertise", "photos_degats"],
                    )
                    return json.dumps({
                        "expertise_planifiee": True,
                        "type_expert":   type_expert,
                        "date_prevue":   params.get("date_expertise", "À confirmer"),
                        "intervention_id": intervention.get("id"),
                        "lien_portail":  intervention.get("lien_portail"),
                    }, ensure_ascii=False)

                return json.dumps({
                    "expertise_planifiee": True,
                    "type_expert": type_expert,
                    "message": "Expert notifié (coordonnées téléphoniques non fournies — contact manuel requis)",
                }, ensure_ascii=False)

            # ── enregistrer_rapport_expertise_rd ────────────────────────────
            if nom == "enregistrer_rapport_expertise_rd":
                from core.orass_connector import orass
                ref = params.get("reference_sinistre", "")
                await orass.enregistrer_rapport_expertise(ref, params)
                return json.dumps({
                    "rapport_enregistre": True,
                    "montant_evalue":     params.get("montant_evalue", 0),
                    "vetuste_pct":        params.get("vetuste_pct", 0),
                    "reserves":           params.get("reserves", ""),
                    "statut":             "Rapport intégré — NTIS peut être rédigée",
                }, ensure_ascii=False)

            # ── calculer_indemnisation_rc ────────────────────────────────────
            if nom == "calculer_indemnisation_rc":
                prejudice = params.get("montant_prejudice_tiers", 0)
                franchise = params.get("franchise", 0)
                plafond = params.get("plafond_garantie", 50_000_000)
                taux_resp = params.get("partage_responsabilite_pct", 100) / 100
                montant_brut = prejudice * taux_resp
                montant_net = max(0, min(montant_brut - franchise, plafond))
                return json.dumps({
                    "prejudice_tiers":   prejudice,
                    "partage_resp_pct":  params.get("partage_responsabilite_pct", 100),
                    "montant_brut":      round(montant_brut, 0),
                    "franchise":         franchise,
                    "plafond_garantie":  plafond,
                    "montant_net_fcfa":  round(montant_net, 0),
                    "depasse_plafond":   montant_brut > plafond,
                }, ensure_ascii=False)

            # ── calculer_indemnisation_do ────────────────────────────────────
            if nom == "calculer_indemnisation_do":
                devis = params.get("montant_devis_refection", 0)
                vetuste = params.get("vetuste_pct", 0) / 100
                franchise = params.get("franchise_do", 0)
                plafond = params.get("plafond_garantie", 100_000_000)
                montant_brut = devis * (1 - vetuste)
                montant_net = max(0, min(montant_brut - franchise, plafond))
                return json.dumps({
                    "devis_refection":   devis,
                    "vetuste_appliquee_pct": params.get("vetuste_pct", 0),
                    "apres_vetuste":     round(montant_brut, 0),
                    "franchise_do":      franchise,
                    "montant_net_fcfa":  round(montant_net, 0),
                    "subrogation_constructeur": params.get("subrogation_constructeur", True),
                }, ensure_ascii=False)

            # ── calculer_indemnisation_aci ───────────────────────────────────
            if nom == "calculer_indemnisation_aci":
                capital = params.get("capital_assure", 0)
                type_s = params.get("type_sinistre", "")
                montant = 0.0

                if type_s == "deces":
                    montant = capital
                elif type_s == "ip_totale":
                    montant = capital
                elif type_s == "ip_partielle":
                    taux = params.get("taux_ip_pct", 0) / 100
                    montant = capital * taux
                elif type_s == "itt":
                    jours = params.get("nb_jours_itt", 0)
                    franchise = params.get("franchise_jours", 3)
                    ij = params.get("ij_contractuelle", _SMIG_MENSUEL_FCFA / 30)
                    montant = max(0, jours - franchise) * ij
                elif type_s == "frais_medicaux":
                    montant_fm = params.get("montant_frais_medicaux", 0)
                    taux = _TAUX_REMBOURSEMENT_ACI.get("frais_medicaux", 0.80)
                    montant = montant_fm * taux

                return json.dumps({
                    "type_sinistre":    type_s,
                    "capital_assure":   capital,
                    "montant_fcfa":     round(montant, 0),
                    "detail_calcul":    f"{type_s} — capital {capital:,.0f} FCFA",
                }, ensure_ascii=False)

            # ── calculer_indemnisation_mrh ───────────────────────────────────
            if nom == "calculer_indemnisation_mrh":
                montant = params.get("montant_dommage", 0)
                vetuste = params.get("vetuste_pct", 0) / 100
                franchise = params.get("franchise", 0)
                valeur_neuf = params.get("valeur_neuf", False)
                if not valeur_neuf:
                    montant_brut = montant * (1 - vetuste)
                else:
                    montant_brut = montant
                montant_net = max(0, montant_brut - franchise)
                return json.dumps({
                    "peril":           params.get("peril"),
                    "montant_dommage": montant,
                    "vetuste_pct":     params.get("vetuste_pct", 0),
                    "valeur_neuf":     valeur_neuf,
                    "montant_net_fcfa": round(montant_net, 0),
                    "franchise":       franchise,
                }, ensure_ascii=False)

            # ── calculer_indemnisation_agriculture ───────────────────────────
            if nom == "calculer_indemnisation_agriculture":
                surface = params.get("surface_ha", 0)
                taux_perte = params.get("taux_perte_constate_pct", 0) / 100
                prix = params.get("prix_unitaire_marche", 0)
                rendement = params.get("rendement_declare", 0)
                franchise = params.get("franchise_pct", 20) / 100

                valeur_recolte = surface * rendement * prix
                perte_brute = valeur_recolte * taux_perte
                franchise_fcfa = perte_brute * franchise
                montant_net = max(0, perte_brute - franchise_fcfa)
                return json.dumps({
                    "surface_ha":       surface,
                    "valeur_recolte":   round(valeur_recolte, 0),
                    "taux_perte_pct":   params.get("taux_perte_constate_pct", 0),
                    "perte_brute":      round(perte_brute, 0),
                    "franchise_pct":    params.get("franchise_pct", 20),
                    "franchise_fcfa":   round(franchise_fcfa, 0),
                    "montant_net_fcfa": round(montant_net, 0),
                }, ensure_ascii=False)

            # ── generer_note_technique ───────────────────────────────────────
            if nom == "generer_note_technique":
                from core.ia_client import ModeIA, ia_client
                from core.orass_connector import orass
                ref = params.get("reference_sinistre", "")
                montant = params.get("montant_propose", 0)
                branche = params.get("branche", "risques_divers")

                # Niveau de validation requis
                if montant >= _SEUIL_DIR_TECHNIQUE:
                    niveau = "direction_generale"
                elif montant >= _SEUIL_CHEF_SERVICE:
                    niveau = "directeur_technique"
                else:
                    niveau = "chef_service"

                # Génération IA de la NTIS
                prompt_ntis = f"""Rédige une Note Technique d'Instruction Sinistre (NTIS) formelle pour une compagnie d'assurance CIMA.

Dossier : {ref}
Branche : {branche}
Rédacteur : {params.get('redacteur_nom', 'Non précisé')}
Montant proposé : {montant:,.0f} FCFA

Circonstances : {params.get('resume_circonstances', 'Non renseigné')}
Analyse garantie : {params.get('analyse_garantie', 'Voir dossier')}
Analyse responsabilité : {params.get('analyse_responsabilite', 'Voir dossier')}
Synthèse expertise : {params.get('synthese_expertise', 'Rapport joint')}
Montant expertise : {params.get('montant_expertise', montant):,.0f} FCFA
Franchise : {params.get('franchise_deduite', 0):,.0f} FCFA
Vétusté : {params.get('vetuste_deduite_pct', 0)}%
Réserves : {params.get('reserves_juridiques', 'Aucune réserve particulière')}
Recommandation : {params.get('recommandation', 'regler_amiable')}

Structure la note en 12 sections numérotées selon la nomenclature NTIS CIMA.
Adopte un style technique, factuel et professionnel.
La note doit justifier la recommandation et le montant proposé."""

                _rep_ntis = await ia_client.appeler(prompt=prompt_ntis, mode=ModeIA.REDACTION)
                ntis_texte = _rep_ntis.contenu
                note_id = f"NTIS-{ref}-{date.today().strftime('%Y%m%d')}-{str(uuid.uuid4())[:4].upper()}"

                # Enregistrement en base
                await orass.enregistrer_document(ref, {
                    "type": "ntis",
                    "id":   note_id,
                    "branche": branche,
                    "montant_propose": montant,
                    "niveau_validation": niveau,
                    "contenu": ntis_texte,
                    "statut": "RÉDIGÉE — en attente de validation",
                    "date_redaction": datetime.now(timezone.utc).isoformat(),
                })

                return json.dumps({
                    "note_id":           note_id,
                    "statut":            "RÉDIGÉE",
                    "niveau_validation": niveau,
                    "montant_propose":   montant,
                    "branche":           branche,
                    "prochaine_etape":   f"Soumettre via valider_note_technique — niveau requis : {niveau}",
                }, ensure_ascii=False)

            # ── valider_note_technique ───────────────────────────────────────
            if nom == "valider_note_technique":
                from core.approval_queue import approval_queue
                ref = params.get("reference_sinistre", "")
                note_id = params.get("note_id", "")
                montant = params.get("montant_propose", 0)

                if montant >= _SEUIL_DIR_TECHNIQUE:
                    niveau = "direction_generale"
                    approvers = ["Directeur Général", "Directeur Technique"]
                elif montant >= _SEUIL_CHEF_SERVICE:
                    niveau = "directeur_technique"
                    approvers = ["Directeur Technique"]
                else:
                    niveau = "chef_service"
                    approvers = ["Chef de Service Sinistres"]

                item_id = await approval_queue.soumettre(
                    execution_id=execution_id,
                    type_action="validation_ntis_risques_divers",
                    description=f"NTIS {note_id} — {ref} — {montant:,.0f} FCFA",
                    donnees={
                        "note_id":    note_id,
                        "reference":  ref,
                        "montant":    montant,
                        "niveau":     niveau,
                        "urgence":    params.get("urgence", False),
                    },
                    approbateurs=approvers,
                )

                return json.dumps({
                    "note_id":     note_id,
                    "item_id":     item_id,
                    "niveau":      niveau,
                    "approvers":   approvers,
                    "statut":      "EN_ATTENTE_VALIDATION",
                    "message":     f"NTIS transmise pour visa {niveau}. Aucune offre ne peut être envoyée avant retour.",
                }, ensure_ascii=False)

            # ── notifier_intervention_assure_rd ──────────────────────────────
            if nom == "notifier_intervention_assure_rd":
                from core.portail_externe import portail_externe
                ref = params.get("reference_sinistre", "")
                type_notif = params.get("type_notification", "")
                tel = params.get("telephone_assure", "")

                intervention = await portail_externe.creer_intervention(
                    type_intervention=type_notif,
                    reference_sinistre=ref,
                    branche="risques_divers",
                    destinataire_nom="Assuré",
                    destinataire_telephone=tel,
                    montant_offre=params.get("montant_offre"),
                    documents_requis=params.get("pieces_demandees", []),
                    message_personnalise=params.get("message_personnalise", ""),
                )

                return json.dumps({
                    "notifie":       True,
                    "type_notif":    type_notif,
                    "canal":         "whatsapp + portail",
                    "lien_portail":  intervention.get("lien_portail"),
                    "token":         intervention.get("token"),
                }, ensure_ascii=False)

            # ── notifier_prestataire_rd ───────────────────────────────────────
            if nom == "notifier_prestataire_rd":
                from core.portail_externe import portail_externe
                ref = params.get("reference_sinistre", "")
                tel = params.get("telephone", "")
                type_prest = params.get("type_prestataire", "")

                intervention = await portail_externe.creer_intervention(
                    type_intervention=type_prest,
                    reference_sinistre=ref,
                    branche="risques_divers",
                    destinataire_nom=params.get("nom_prestataire", "Prestataire"),
                    destinataire_telephone=tel,
                    destinataire_email=params.get("email", ""),
                    documents_requis=params.get("documents_attendus", []),
                    date_limite=params.get("date_limite"),
                )

                return json.dumps({
                    "prestataire_notifie": True,
                    "type_prestataire":    type_prest,
                    "lien_portail":        intervention.get("lien_portail"),
                    "intervention_id":     intervention.get("id"),
                }, ensure_ascii=False)

            # ── gerer_protection_juridique ────────────────────────────────────
            if nom == "gerer_protection_juridique":
                ref = params.get("reference_sinistre", "")
                plafond = params.get("plafond_defense", 5_000_000)
                montant_enjeu = params.get("montant_enjeu", 0)
                return json.dumps({
                    "prise_en_charge":  True,
                    "plafond_defense":  plafond,
                    "montant_enjeu":    montant_enjeu,
                    "stade_procedure":  params.get("stade_procedure", "amiable"),
                    "avocat_libre":     True,
                    "conditions":       "Honoraires facturés directement à l'assureur dans la limite du plafond",
                }, ensure_ascii=False)

            # ── gerer_credit_caution ──────────────────────────────────────────
            if nom == "gerer_credit_caution":
                ref = params.get("reference_sinistre", "")
                creance = params.get("montant_creance", 0)
                md_ok = params.get("mise_en_demeure_effectuee", False)
                recours_epuise = params.get("recours_amiable_epuise", False)
                eligible = md_ok and recours_epuise
                return json.dumps({
                    "reference":                ref,
                    "montant_creance":          creance,
                    "eligible_indemnisation":   eligible,
                    "mise_en_demeure_ok":        md_ok,
                    "recours_amiable_epuise":    recours_epuise,
                    "blocage":                   "" if eligible else "Recours amiable non épuisé ou mise en demeure manquante",
                }, ensure_ascii=False)

            # ── gerer_assistance ─────────────────────────────────────────────
            if nom == "gerer_assistance":
                return json.dumps({
                    "prise_en_charge":  True,
                    "type_assistance":  params.get("type_assistance"),
                    "pays":             params.get("pays"),
                    "montant_frais":    params.get("montant_frais", 0),
                    "coordination":     "Centrale d'assistance notifiée — coordination en cours 24h/24",
                    "prestataire_local": params.get("prestataire_local", "À confirmer"),
                }, ensure_ascii=False)

            # ── valider_reglement_rd ──────────────────────────────────────────
            if nom == "valider_reglement_rd":
                from core.approval_queue import approval_queue
                montant = params.get("montant_net", 0)
                approvers = []
                if montant >= _SEUIL_DIR_TECHNIQUE:
                    approvers = ["Directeur Général", "Directeur Financier"]
                elif montant >= _SEUIL_CHEF_SERVICE:
                    approvers = ["Directeur Technique"]
                else:
                    approvers = ["Chef de Service Sinistres"]

                item_id = await approval_queue.soumettre(
                    execution_id=execution_id,
                    type_action="reglement_sinistre_rd",
                    description=f"Règlement {params.get('reference_sinistre')} — {montant:,.0f} FCFA",
                    donnees=params,
                    approbateurs=approvers,
                )
                return json.dumps({
                    "valide": False,
                    "item_id": item_id,
                    "approbateurs": approvers,
                    "statut": "EN_ATTENTE_VALIDATION",
                }, ensure_ascii=False)

            # ── passer_ecriture_rd ────────────────────────────────────────────
            if nom == "passer_ecriture_rd":
                from core.orass_connector import orass
                ref = params.get("reference_sinistre", "")
                montant = params.get("montant_reglement", 0)
                ecriture_id = f"ECR-RD-{str(uuid.uuid4())[:8].upper()}"
                await orass.passer_ecriture({
                    "id": ecriture_id,
                    "reference_sinistre": ref,
                    "branche": params.get("branche", "risques_divers"),
                    "debit_compte":  "4111_sinistres_a_payer",
                    "credit_compte": "512_banque",
                    "montant": montant,
                    "libelle": f"Règlement sinistre RD {ref}",
                    "date": date.today().isoformat(),
                })
                return json.dumps({
                    "ecriture_id": ecriture_id,
                    "montant": montant,
                    "statut": "PASSÉE — en attente de signature bancaire",
                }, ensure_ascii=False)

            # ── traiter_recours_rd ────────────────────────────────────────────
            if nom == "traiter_recours_rd":
                recours_id = f"REC-RD-{str(uuid.uuid4())[:8].upper()}"
                return json.dumps({
                    "recours_id":      recours_id,
                    "type_recours":    params.get("type_recours"),
                    "tiers":           params.get("identite_tiers"),
                    "assureur_tiers":  params.get("assureur_tiers"),
                    "montant":         params.get("montant_recours"),
                    "statut":          "INITIÉ",
                }, ensure_ascii=False)

            # ── calculer_interets_moratoires_rd ───────────────────────────────
            if nom == "calculer_interets_moratoires_rd":
                from datetime import date as dt_date
                principal = params.get("montant_principal", 0)
                date_dep = params.get("date_delai_depasse", str(dt_date.today()))
                date_calc = params.get("date_calcul", str(dt_date.today()))
                d1 = dt_date.fromisoformat(date_dep)
                d2 = dt_date.fromisoformat(date_calc)
                jours = max(0, (d2 - d1).days)
                taux_annuel = _DELAIS_CIMA_RD["interet_moratoire_taux_annuel"]
                interets = principal * taux_annuel * jours / 365
                return json.dumps({
                    "montant_principal":    principal,
                    "jours_retard":         jours,
                    "taux_annuel_pct":      taux_annuel * 100,
                    "interets_moratoires":  round(interets, 0),
                    "montant_total":        round(principal + interets, 0),
                }, ensure_ascii=False)

            # ── detecter_sinistres_rd_souffrance ─────────────────────────────
            if nom == "detecter_sinistres_rd_souffrance":
                from core.orass_connector import orass
                seuil = params.get("seuil_jours", 30)
                branche = params.get("branche", "")
                sinistres = await orass.get_sinistres_souffrance(
                    branche=branche, seuil_jours=seuil
                )
                return json.dumps({
                    "nb_sinistres_souffrance": len(sinistres),
                    "seuil_jours": seuil,
                    "sinistres": sinistres[:20],
                }, ensure_ascii=False)

            # ── tableau_bord_rd ───────────────────────────────────────────────
            if nom == "tableau_bord_rd":
                from core.orass_connector import orass
                kpis = await orass.get_kpis_sinistres(
                    branche=params.get("branche", ""),
                    periode=params.get("periode", ""),
                )
                return json.dumps({
                    "periode":    params.get("periode", "en_cours"),
                    "branche":    params.get("branche", "toutes"),
                    "indicateur": params.get("indicateur", "tous"),
                    "kpis":       kpis,
                }, ensure_ascii=False)

            return json.dumps({"erreur": f"Outil '{nom}' non implémenté"})

        except Exception as exc:
            logger.error("AgentRisquesDivers._executer_outil %s: %s", nom, exc, exc_info=True)
            return json.dumps({"erreur": str(exc)})
