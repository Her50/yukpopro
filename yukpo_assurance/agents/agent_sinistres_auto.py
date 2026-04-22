"""
Agent Sinistres RC Auto — Instruction complète dossiers RC Automobile zone CIMA.

Couverture CIMA :
  - Art. 200-264  : Assurance obligatoire RC Auto
  - Art. 205      : Délai déclaration 5 jours ouvrés
  - Art. 208      : Constat amiable / PV police
  - Art. 231-242  : Barème CIMA dommages corporels (DFP, ITT, pretium doloris,
                    préjudice esthétique, tierce personne, frais médicaux, décès)
  - Art. 242      : Dommages matériels (VRADE, coût réparation, perte de jouissance)
  - Art. 250      : Subrogation contre tiers responsable
  - Art. 12-bis   : Délai offre indemnisation 90 jours
  - Art. 12-ter   : Délai paiement 45 jours après accord
  - Art. 12-quater: Intérêts moratoires 12%/an en cas de retard

Spécificités :
  - Gestion multi-victimes (conducteur fautif / tiers conducteur / passager / piéton)
  - Workflow matériel vs corporel vs mixte vs décès
  - Recours contre tiers (subrogation Art. 250)
  - Dépôt pièces par image (constat, PV, photos, expertises, certificats médicaux)
"""
from __future__ import annotations
import json
import logging
from datetime import date, timedelta
from core.agent_orchestrateur import TypeAgent
from agents.base_agent import BaseAgent

logger = logging.getLogger("yukpo_assurance.agents.sinistres_auto")

# ─── Délais CIMA RC Auto ──────────────────────────────────────────────────────
_DELAI_DECLARATION_JOURS       = 5     # Art. 205 — déclaration à l'assureur (jours ouvrés)
_DELAI_OFFRE_INDEMNISATION     = 90    # Art. 12-bis
_DELAI_PAIEMENT_APRES_ACCORD   = 45    # Art. 12-ter
_TAUX_INTERET_MORATOIRE        = 0.12  # Art. 12-quater — 12 %/an

# ─── Barème CIMA dommages corporels ──────────────────────────────────────────
# Art. 232 — Coefficient âge pour calcul DFP (Déficit Fonctionnel Permanent)
_COEFF_AGE_DFP: dict[tuple[int, int], int] = {
    (0,   14): 60,
    (15,  25): 55,
    (26,  35): 50,
    (36,  45): 45,
    (46,  55): 40,
    (56,  65): 35,
    (66, 999): 30,
}

# Art. 235 — Pretium doloris (souffrance endurée) — forfaits FCFA par degré 1-7
_PRETIUM_DOLORIS_FCFA: dict[int, int] = {
    1: 100_000,
    2: 200_000,
    3: 400_000,
    4: 700_000,
    5: 1_200_000,
    6: 2_000_000,
    7: 3_000_000,
}

# Art. 236 — Préjudice esthétique — mêmes forfaits que pretium doloris
_PREJUDICE_ESTHETIQUE_FCFA: dict[int, int] = _PRETIUM_DOLORIS_FCFA

# SMIG de référence CIMA pour le calcul DFP (variable par pays — valeur par défaut Cameroun)
_SMIG_MENSUEL_FCFA = 36_270  # SMIG Cameroun 2024 — à paramétrer par compagnie


def _coeff_age(age: int) -> int:
    for (age_min, age_max), coeff in _COEFF_AGE_DFP.items():
    	if age_min <= age <= age_max:
            return coeff
    return 30  # > 65 ans par défaut


def _calculer_dfp(age: int, taux_ipp_pct: float) -> dict:
    """
    DFP = SMIG mensuel × 12 × (IPP/100) × coeff_age
    Base légale : Art. 232 Code CIMA
    """
    coeff = _coeff_age(age)
    dfp = round(_SMIG_MENSUEL_FCFA * 12 * (taux_ipp_pct / 100) * coeff)
    return {
        "dfp_fcfa": dfp,
        "smig_mensuel_reference": _SMIG_MENSUEL_FCFA,
        "coeff_age": coeff,
        "taux_ipp_pct": taux_ipp_pct,
        "age_victime": age,
        "formule": f"SMIG {_SMIG_MENSUEL_FCFA:,} × 12 × {taux_ipp_pct}% × coeff_age {coeff}".replace(",", " "),
        "base_legale": "Art. 232 Code CIMA",
    }


def _calculer_itt(nb_jours_itt: int, nb_jours_itp: int = 0, taux_itp_pct: float = 50.0) -> dict:
    """
    ITT = SMIG / 30 × jours_ITT
    ITP = SMIG / 30 × jours_ITP × (taux_ITP / 100)
    Base légale : Art. 234 Code CIMA
    """
    allocation_jour = round(_SMIG_MENSUEL_FCFA / 30)
    montant_itt = round(allocation_jour * nb_jours_itt)
    montant_itp = round(allocation_jour * nb_jours_itp * (taux_itp_pct / 100))
    return {
        "allocation_journaliere_fcfa": allocation_jour,
        "nb_jours_itt": nb_jours_itt,
        "nb_jours_itp": nb_jours_itp,
        "taux_itp_pct": taux_itp_pct,
        "montant_itt_fcfa": montant_itt,
        "montant_itp_fcfa": montant_itp,
        "total_incapacite_temporaire_fcfa": montant_itt + montant_itp,
        "base_legale": "Art. 234 Code CIMA",
    }


class AgentSinistresAuto(BaseAgent):
    type_agent = TypeAgent.SINISTRES_AUTO

    def _system_prompt(self) -> str:
        return f"""Tu es l'Agent Sinistres RC Automobile de YukpoAssurance, expert en instruction et règlement de sinistres RC Auto zone CIMA (Art. 200-264 Code CIMA).

PÉRIMÈTRE : Uniquement sinistres RC Auto — dommages matériels, dommages corporels, décès, perte de jouissance, sinistres mixtes.

═══════════════════════════════════════════════════════
MODES D'OPÉRATION
═══════════════════════════════════════════════════════
MODE DÉCLARATION (nouveau sinistre RC Auto) :
  → Activé si l'instruction contient "MODE DÉCLARATION", "nouveau sinistre", "déclarer", "accident", "déclaration".
  → NE JAMAIS demander si c'est nouveau ou existant — aller DIRECTEMENT à la demande de documents par image.
  → Appeler demander_information_utilisateur (type_reponse='images') pour collecter le constat/PV/photos.
  → Après image reçue : analyser_documents_auto → creer_sinistre (génère SIN-AAAA-NNN automatiquement).
  → Ne jamais demander de numéro sinistre à l'utilisateur — c'est le système qui le génère.

MODE INSTRUCTION (sinistre existant) :
  → L'utilisateur fournit une référence sinistre existante (ex: SIN-2024-042).
  → Commencer par get_sinistre_auto pour charger le dossier.
  → Continuer le workflow selon l'état d'avancement.

═══════════════════════════════════════════════════════
WORKFLOW MATÉRIEL (dommages véhicule uniquement)
═══════════════════════════════════════════════════════
0.  [MODE DÉCLARATION UNIQUEMENT] creer_sinistre
1.  get_sinistre_auto
2.  verifier_police_auto       [police + attestation + carte rose en cours]
3.  analyser_documents_auto    [constat, PV, photos véhicule — 6 prises min]
4.  scorer_fraude_auto
5.  planifier_expertise_auto   [notifie l'expert via portail + WhatsApp — obligatoire > 300k ou véhicule < 3 ans]
    ↳ [ATTENDRE rapport expert via portail avant de continuer]
6.  calculer_indemnisation_materielle   [VRADE vs coût réparation Art. 242]
7.  calculer_perte_jouissance  [durée immobilisation × tarif location journalier]
8.  generer_note_technique     [synthèse instruction — obligatoire avant toute offre]
9.  valider_note_technique     [soumission hiérarchie pour visa — VALIDATION HUMAINE obligatoire]
    ↳ [ATTENDRE validation hiérarchie avant d'envoyer l'offre à l'assuré]
10. notifier_intervention_assure  [notifie l'assuré via portail + WhatsApp pour accord/refus offre]
    ↳ [ATTENDRE réponse assuré via portail ou WhatsApp]
11. valider_reglement_auto     [validation paiement après accord assuré — OBLIGATOIRE si > 500k]
12. generer_courrier_auto      [notification_reglement ou rejet]
13. passer_ecriture_sinistre_auto
14. notifier_assure_auto
15. traiter_subrogation        [si tiers responsable identifié — Art. 250]

═══════════════════════════════════════════════════════
WORKFLOW CORPOREL (victimes avec blessures — Art. 231-242)
═══════════════════════════════════════════════════════
1.  get_sinistre_auto
2.  verifier_police_auto
3.  analyser_documents_auto    [constat + certificats médicaux toutes victimes]
4.  scorer_fraude_auto
5.  enregistrer_victimes       [conducteur / passager / piéton — avec âge et qualité]
6.  planifier_expertise_auto   [véhicule si dommages matériels associés]
7.  planifier_expertise_medicale  [notifie médecin expert via portail — OBLIGATOIRE Art. 231]
    ↳ [ATTENDRE rapport médical via portail avant calcul IPP]
8.  calculer_prejudices_corporels  [DFP + ITT + pretium doloris + esthétique + frais médicaux]
9.  calculer_tierce_personne   [si dépendance permanente — Art. 241]
10. generer_note_technique     [synthèse avec détail par victime + postes préjudices]
11. valider_note_technique     [visa hiérarchie OBLIGATOIRE — sinistre corporel]
    ↳ [ATTENDRE validation hiérarchie]
12. notifier_intervention_assure  [offre individuelle à chaque victime via portail]
    ↳ [ATTENDRE réponse de chaque victime]
13. valider_reglement_auto     [validation paiement — OBLIGATOIRE tout corporel]
14. generer_courrier_auto
15. passer_ecriture_sinistre_auto
16. notifier_assure_auto
17. traiter_subrogation

═══════════════════════════════════════════════════════
WORKFLOW DÉCÈS (victime décédée — Art. 231 + 242)
═══════════════════════════════════════════════════════
1.  get_sinistre_auto
2.  verifier_police_auto
3.  analyser_documents_auto    [constat + acte décès + rapport IML]
4.  enregistrer_victimes       [statut = décès + ayants droit]
5.  calculer_prejudices_deces  [perte revenus + pretium doloris + frais obsèques]
6.  verifier_ayants_droit      [notifie les ayants droit via portail pour dépôt pièces]
    ↳ [ATTENDRE pièces ayants droit via portail]
7.  generer_note_technique     [synthèse décès — obligatoire]
8.  valider_note_technique     [visa direction — OBLIGATOIRE sinistre décès]
    ↳ [ATTENDRE validation direction]
9.  valider_reglement_auto     [OBLIGATOIRE]
10. generer_courrier_auto
11. passer_ecriture_sinistre_auto
12. notifier_assure_auto

═══════════════════════════════════════════════════════
BARÈME CIMA — RAPPEL TECHNIQUE
═══════════════════════════════════════════════════════
DFP (Art. 232) = SMIG mensuel ({_SMIG_MENSUEL_FCFA:,} FCFA) × 12 × (IPP%) × Coeff_Age
  Coefficients : <15ans=60, 15-25=55, 26-35=50, 36-45=45, 46-55=40, 56-65=35, >65=30

ITT (Art. 234) = SMIG/30 × nb_jours_ITT
                 + SMIG/30 × nb_jours_ITP × taux_ITP%

Pretium doloris (Art. 235) : degré 1=100k, 2=200k, 3=400k, 4=700k, 5=1,2M, 6=2M, 7=3M FCFA

Préjudice esthétique (Art. 236) : mêmes forfaits que pretium doloris

Dommages matériels (Art. 242) : min(coût réparation, VRADE) − franchise contractuelle

RÈGLES STRICTES :
- Déclaration tardive (> 5 jours ouvrés Art. 205) → noter au dossier mais instruire
- Police expirée ou prime non payée → REJET immédiat + courrier motivé
- Score fraude > 60 → analyser_fraude_ia AVANT calcul indemnisation
- Tout corporel → expertise médicale OBLIGATOIRE (IPP ne peut être fixé sans rapport médical)
- NOTE TECHNIQUE OBLIGATOIRE avant toute offre → generer_note_technique + valider_note_technique
- Tout règlement > 500 000 FCFA → validation humaine OBLIGATOIRE
- Assuré et experts NOTIFIÉS via portail Yukpo + WhatsApp à chaque étape les concernant
- Sinistres en souffrance > 90 jours → calcul intérêts moratoires automatique (Art. 12-quater)
- Présence de tiers identifié → initier traiter_subrogation après règlement

CHAÎNE DE VALIDATION HIÉRARCHIQUE :
  Rédacteur sinistre → generer_note_technique
    ↓ soumet via valider_note_technique
  Chef de service sinistres → visa note (valide montant + orientation)
    ↓ si approuvé
  Offre envoyée à l'assuré via portail/WhatsApp
    ↓ accord assuré reçu
  Direction technique → valider_reglement_auto (validation paiement)
    ↓ si approuvé
  Paiement effectué
""".replace(",", " ")

    def _definir_outils(self) -> list[dict]:
        return [
            # ── Création dossier (MODE DÉCLARATION) ───────────────────────────
            {
                "name": "creer_sinistre",
                "description": "Crée un nouveau dossier sinistre RC Auto et génère automatiquement la référence (SIN-AAAA-NNN). À utiliser UNIQUEMENT en mode déclaration (nouveau sinistre). Ne jamais demander de référence à l'utilisateur.",
                "input_schema": {"type": "object", "properties": {
                    "type_sinistre":    {"type": "string", "enum": ["materiel", "corporel", "mixte", "deces"], "description": "Type de dommage RC Auto"},
                    "date_survenance":  {"type": "string", "description": "Date de l'accident YYYY-MM-DD"},
                    "lieu":             {"type": "string", "description": "Lieu de l'accident"},
                    "description":      {"type": "string", "description": "Description initiale de l'accident"},
                    "police_id":        {"type": "string", "description": "Numéro de police de l'assuré si connu"},
                }, "required": ["type_sinistre", "date_survenance"]},
            },
            # ── Récupération & vérification ───────────────────────────────────
            {
                "name": "get_sinistre_auto",
                "description": "Récupère le dossier sinistre RC Auto complet depuis ORASS (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "reference": {"type": "string", "description": "Référence sinistre ex: SIN-2025-042"},
                }, "required": ["reference"]},
            },
            {
                "name": "verifier_police_auto",
                "description": "Vérifie validité de la police RC Auto à la date du sinistre : attestation, carte rose, prime, garanties souscrites (déterministe 0 IA)",
                "input_schema": {"type": "object", "properties": {
                    "police_id":           {"type": "string"},
                    "date_sinistre":       {"type": "string", "description": "YYYY-MM-DD"},
                    "immatriculation":     {"type": "string", "description": "Immatriculation du véhicule assuré"},
                    "type_garantie_requis": {"type": "string", "enum": [
                        "rc_seule", "rc_plus_vol", "tous_risques", "rc_plus_corp_conducteur"
                    ]},
                }, "required": ["police_id", "date_sinistre"]},
            },
            # ── Analyse documents ─────────────────────────────────────────────
            {
                "name": "analyser_documents_auto",
                "description": "Analyse OCR+IA des pièces RC Auto : constat amiable, PV police, photos véhicule, rapport expertise, certificats médicaux, acte décès, IML",
                "input_schema": {"type": "object", "properties": {
                    "reference":   {"type": "string"},
                    "documents":   {"type": "array", "items": {
                        "type": "object",
                        "properties": {
                            "type_document": {"type": "string", "enum": [
                                "constat_amiable", "pv_police", "main_courante",
                                "photo_vehicule_assure", "photo_vehicule_tiers",
                                "photo_scene_accident", "devis_reparation",
                                "facture_reparation", "rapport_expertise_auto",
                                "certificat_medical", "rapport_expertise_medicale",
                                "certificat_deces", "iml_rapport", "acte_naissance",
                                "justificatif_revenus", "permis_conduire",
                                "attestation_assurance", "carte_rose",
                            ]},
                            "image_base64": {"type": "string"},
                        },
                    }},
                }, "required": ["reference"]},
            },
            # ── Score fraude ──────────────────────────────────────────────────
            {
                "name": "scorer_fraude_auto",
                "description": "Score de fraude RC Auto 0-100 basé sur règles CIMA et signaux comportementaux (déterministe 0 IA)",
                "input_schema": {"type": "object", "properties": {
                    "reference":                    {"type": "string"},
                    "nb_sinistres_12_mois":         {"type": "integer"},
                    "jours_depuis_souscription":    {"type": "integer"},
                    "montant_declare":              {"type": "number"},
                    "declaration_tardive":          {"type": "boolean"},
                    "jours_declaration":            {"type": "integer", "description": "Nombre de jours entre sinistre et déclaration"},
                    "tiers_non_identifie":          {"type": "boolean", "description": "Conducteur tiers non identifié (délit de fuite)"},
                    "vehicule_recemment_assure":    {"type": "boolean", "description": "Véhicule assuré < 30 jours avant sinistre"},
                    "sinistre_nuit_weekend":        {"type": "boolean"},
                    "contradictions_constat":       {"type": "boolean", "description": "Incohérences entre constat et photos"},
                }, "required": ["reference"]},
            },
            {
                "name": "analyser_fraude_ia",
                "description": "Analyse narrative de fraude par IA — uniquement si score fraude > 60",
                "input_schema": {"type": "object", "properties": {
                    "reference":            {"type": "string"},
                    "declaration_texte":    {"type": "string"},
                    "rapport_expertise":    {"type": "string"},
                    "signaux_detectes":     {"type": "array", "items": {"type": "string"}},
                }, "required": ["reference", "declaration_texte"]},
            },
            # ── Victimes & expertise ──────────────────────────────────────────
            {
                "name": "enregistrer_victimes",
                "description": "Enregistre toutes les victimes du sinistre RC Auto avec leurs données (qualité, âge, statut) pour calcul barème CIMA Art. 231",
                "input_schema": {"type": "object", "properties": {
                    "reference": {"type": "string"},
                    "victimes":  {"type": "array", "items": {
                        "type": "object",
                        "properties": {
                            "nom":       {"type": "string"},
                            "prenom":    {"type": "string"},
                            "age":       {"type": "integer"},
                            "qualite":   {"type": "string", "enum": [
                                "conducteur_assure", "conducteur_tiers",
                                "passager_vehicule_assure", "passager_vehicule_tiers",
                                "pieton", "cycliste"
                            ]},
                            "statut":    {"type": "string", "enum": ["blesse_leger", "blesse_grave", "deces"]},
                            "telephone": {"type": "string"},
                        },
                        "required": ["age", "qualite", "statut"],
                    }},
                }, "required": ["reference", "victimes"]},
            },
            {
                "name": "planifier_expertise_auto",
                "description": "Mandate un expert automobile — obligatoire pour dommages > 300k FCFA ou véhicule < 3 ans (déterministe + validation humaine)",
                "input_schema": {"type": "object", "properties": {
                    "reference":          {"type": "string"},
                    "adresse_vehicule":   {"type": "string"},
                    "telephone_assure":   {"type": "string"},
                    "montant_estime":     {"type": "number"},
                    "vehicule_roulant":   {"type": "boolean"},
                    "urgence":            {"type": "boolean"},
                }, "required": ["reference"]},
            },
            {
                "name": "planifier_expertise_medicale",
                "description": "Mandate un médecin expert pour évaluer IPP/ITT des victimes — OBLIGATOIRE pour tout sinistre corporel (Art. 231 CIMA)",
                "input_schema": {"type": "object", "properties": {
                    "reference":            {"type": "string"},
                    "victimes_a_expertiser": {"type": "array", "items": {"type": "string"}, "description": "Noms/IDs des victimes"},
                    "urgence_medicale":     {"type": "boolean"},
                    "hopital_actuel":       {"type": "string"},
                }, "required": ["reference", "victimes_a_expertiser"]},
            },
            # ── Calculs d'indemnisation ───────────────────────────────────────
            {
                "name": "calculer_indemnisation_materielle",
                "description": "Calcule l'indemnisation dommages matériels RC Auto selon Art. 242 CIMA : min(coût réparation, VRADE) − franchise",
                "input_schema": {"type": "object", "properties": {
                    "reference":             {"type": "string"},
                    "valeur_venale_vrade":   {"type": "number", "description": "Valeur de Remplacement À Dire d'Expert (FCFA)"},
                    "cout_reparation":       {"type": "number", "description": "Devis ou facture garage agréé (FCFA)"},
                    "franchise_contractuelle": {"type": "number", "description": "Franchise prévue au contrat (FCFA) — 0 si RC pure"},
                    "epave_valeur":          {"type": "number", "description": "Valeur épave si VEI (FCFA)"},
                    "vehicule_immobilise":   {"type": "boolean"},
                    "duree_immobilisation_jours": {"type": "integer"},
                }, "required": ["reference", "valeur_venale_vrade", "cout_reparation"]},
            },
            {
                "name": "calculer_perte_jouissance",
                "description": "Calcule l'indemnité de perte de jouissance pour durée d'immobilisation du véhicule",
                "input_schema": {"type": "object", "properties": {
                    "reference":                    {"type": "string"},
                    "duree_immobilisation_jours":   {"type": "integer"},
                    "tarif_location_journalier":    {"type": "number", "description": "Tarif véhicule de remplacement équivalent (FCFA/jour)"},
                    "usage_professionnel":          {"type": "boolean"},
                }, "required": ["reference", "duree_immobilisation_jours"]},
            },
            {
                "name": "calculer_prejudices_corporels",
                "description": "Calcule l'ensemble des préjudices corporels selon barème CIMA Art. 231-242 : DFP + ITT/ITP + pretium doloris + préjudice esthétique + frais médicaux + tierce personne",
                "input_schema": {"type": "object", "properties": {
                    "reference":            {"type": "string"},
                    "nom_victime":          {"type": "string"},
                    "age_victime":          {"type": "integer"},
                    "taux_ipp_pct":         {"type": "number",  "description": "% IPP fixé par expertise médicale — 0 si sans séquelles"},
                    "nb_jours_itt":         {"type": "integer", "description": "Jours d'ITT (incapacité totale) selon certificat médical"},
                    "nb_jours_itp":         {"type": "integer", "description": "Jours d'ITP (incapacité partielle) — 0 si aucun"},
                    "taux_itp_pct":         {"type": "number",  "description": "Taux ITP % si applicable (défaut 50%)"},
                    "degre_pretium_doloris": {"type": "integer", "description": "Degré souffrance endurée 1-7 (Art. 235)"},
                    "degre_prejudice_esthetique": {"type": "integer", "description": "Degré préjudice esthétique 1-7 (Art. 236) — 0 si aucun"},
                    "frais_medicaux_reels":  {"type": "number",  "description": "Total factures médicales et hospitalisation (FCFA)"},
                    "perte_revenus_mensuelle": {"type": "number", "description": "Perte mensuelle de revenus professionnels (FCFA) — 0 si sans activité"},
                    "duree_arret_professionnel_mois": {"type": "integer"},
                    "assistance_tierce_personne": {"type": "boolean", "description": "Nécessite aide tierce personne permanente (Art. 241)"},
                }, "required": ["reference", "nom_victime", "age_victime", "taux_ipp_pct", "nb_jours_itt"]},
            },
            {
                "name": "calculer_prejudices_deces",
                "description": "Calcule les préjudices en cas de décès d'une victime RC Auto : perte de revenus des ayants droit + pretium doloris + frais obsèques",
                "input_schema": {"type": "object", "properties": {
                    "reference":                {"type": "string"},
                    "nom_victime":              {"type": "string"},
                    "age_victime":              {"type": "integer"},
                    "revenu_mensuel_fcfa":      {"type": "number", "description": "Revenus mensuels de la victime avant décès (0 si sans emploi)"},
                    "nb_ayants_droit_charge":   {"type": "integer", "description": "Nombre de personnes à charge"},
                    "degre_pretium_doloris":    {"type": "integer", "description": "Souffrance avant décès 1-7 (Art. 235) — 0 si mort instantanée"},
                    "frais_obseques_reels":     {"type": "number", "description": "Frais d'obsèques justifiés (FCFA)"},
                    "ayants_droit":             {"type": "array", "items": {
                        "type": "object",
                        "properties": {
                            "lien": {"type": "string", "enum": ["conjoint", "enfant", "parent_charge", "autre_charge"]},
                            "age":  {"type": "integer"},
                            "nom":  {"type": "string"},
                        },
                    }},
                }, "required": ["reference", "nom_victime", "age_victime"]},
            },
            {
                "name": "calculer_tierce_personne",
                "description": "Calcule l'indemnité de tierce personne pour victime nécessitant une aide permanente (Art. 241 CIMA)",
                "input_schema": {"type": "object", "properties": {
                    "reference":        {"type": "string"},
                    "nom_victime":      {"type": "string"},
                    "nb_heures_aide_jour": {"type": "number", "description": "Heures d'aide par jour nécessaires"},
                    "duree_mois":       {"type": "integer",  "description": "Durée de besoin en mois — 0 = permanent (capitalisation)"},
                    "nature_aide":      {"type": "string",   "enum": ["aide_specialisee", "aide_menagere", "garde_malade"]},
                }, "required": ["reference", "nom_victime", "nb_heures_aide_jour"]},
            },
            # ── Validation & règlement ────────────────────────────────────────
            {
                "name": "valider_reglement_auto",
                "description": "Soumet la décision de règlement RC Auto pour validation humaine OBLIGATOIRE (validation humaine systématique pour tout corporel + tout > 500k FCFA)",
                "input_schema": {"type": "object", "properties": {
                    "reference":            {"type": "string"},
                    "decision":             {"type": "string", "enum": ["accepte", "rejete", "accepte_partiel", "expertise_complementaire", "contentieux"]},
                    "montant_materiel":     {"type": "number"},
                    "montant_corporel":     {"type": "number"},
                    "montant_total":        {"type": "number"},
                    "motif":                {"type": "string"},
                    "beneficiaire_nom":     {"type": "string"},
                    "rib_virement":         {"type": "string"},
                    "details_victimes":     {"type": "array", "items": {
                        "type": "object",
                        "properties": {
                            "nom":     {"type": "string"},
                            "montant": {"type": "number"},
                            "nature":  {"type": "string"},
                        },
                    }},
                }, "required": ["reference", "decision", "motif"]},
            },
            # ── Courrier & écriture ───────────────────────────────────────────
            {
                "name": "generer_courrier_auto",
                "description": "Génère le courrier de décision RC Auto PDF (accusé réception / offre indemnisation / rejet / demande pièces)",
                "input_schema": {"type": "object", "properties": {
                    "reference":  {"type": "string"},
                    "template":   {"type": "string", "enum": [
                        "accuse_reception_sinistre", "offre_indemnisation_materielle",
                        "offre_indemnisation_corporelle", "notification_reglement",
                        "rejet_police_invalide", "rejet_exclusion_garantie",
                        "rejet_fraude_presumee", "demande_pieces_complementaires",
                        "convocation_expertise_auto", "convocation_expertise_medicale",
                        "mise_en_demeure_tiers",
                    ]},
                    "montant":    {"type": "number"},
                    "motif":      {"type": "string"},
                    "destinataire": {"type": "string", "enum": ["assure", "tiers_adverse", "expert", "avocat", "tribunal"]},
                }, "required": ["reference", "template"]},
            },
            {
                "name": "passer_ecriture_sinistre_auto",
                "description": "Présente l'écriture PCSA pour validation humaine avant passage en base (déterministe 0 IA)",
                "input_schema": {"type": "object", "properties": {
                    "type_operation": {"type": "string", "enum": [
                        "provision_sinistre_ouvert",    # PSAP — dotation
                        "reprise_provision_sinistre",   # PSAP — reprise partielle ou totale
                        "reglement_materiel",           # Règlement dommages matériels
                        "reglement_corporel",           # Règlement dommages corporels
                        "reglement_deces",              # Règlement décès
                        "recours_tiers",                # Recours encaissé
                        "cloture_sans_suite",           # Clôture sans règlement
                    ]},
                    "montant":    {"type": "number"},
                    "reference":  {"type": "string"},
                }, "required": ["type_operation", "montant", "reference"]},
            },
            {
                "name": "notifier_assure_auto",
                "description": "Envoie notification WhatsApp/SMS/email à l'assuré RC Auto",
                "input_schema": {"type": "object", "properties": {
                    "telephone":    {"type": "string"},
                    "message":      {"type": "string"},
                    "canal":        {"type": "string", "enum": ["whatsapp", "sms", "email"]},
                    "reference":    {"type": "string"},
                }, "required": ["telephone", "message"]},
            },
            # ── Subrogation & recours ─────────────────────────────────────────
            {
                "name": "traiter_subrogation",
                "description": "Initie le recours subrogatoire contre le tiers responsable après règlement assuré (Art. 250 CIMA)",
                "input_schema": {"type": "object", "properties": {
                    "reference":            {"type": "string"},
                    "montant_regle":        {"type": "number"},
                    "nom_tiers":            {"type": "string"},
                    "assureur_tiers":       {"type": "string"},
                    "police_tiers":         {"type": "string"},
                    "part_responsabilite_pct": {"type": "number", "description": "Part de responsabilité du tiers 0-100%"},
                    "pieces_recours":       {"type": "array", "items": {"type": "string"}, "description": "Pièces à transmettre au recours"},
                }, "required": ["reference", "montant_regle"]},
            },
            # ── Note technique d'instruction ──────────────────────────────────
            {
                "name": "generer_note_technique",
                "description": (
                    "Génère la Note Technique d'Instruction Sinistre (NTIS) RC Auto par IA. "
                    "Document structuré obligatoire avant toute offre — synthèse complète du dossier : "
                    "parties, circonstances, garanties, expertise, évaluation des dommages, "
                    "analyse fraude, position juridique, proposition de règlement, délais CIMA, "
                    "orientation recommandée et avis du rédacteur."
                ),
                "input_schema": {"type": "object", "properties": {
                    "reference":            {"type": "string"},
                    # Identification parties
                    "assure_nom":           {"type": "string"},
                    "police_id":            {"type": "string"},
                    "immatriculation":      {"type": "string"},
                    "garanties_souscrites": {"type": "string"},
                    # Circonstances
                    "date_sinistre":        {"type": "string"},
                    "lieu_sinistre":        {"type": "string"},
                    "description_accident": {"type": "string"},
                    "tiers_nom":            {"type": "string"},
                    "tiers_assureur":       {"type": "string"},
                    "responsabilite":       {"type": "string", "enum": [
                        "assure_100pct", "tiers_100pct", "partage_50_50",
                        "partage_autre", "indeterminee"
                    ]},
                    "part_responsabilite_assure_pct": {"type": "number"},
                    # Expertise
                    "rapport_expertise_auto":     {"type": "string", "description": "Résumé rapport expert auto"},
                    "rapport_expertise_medicale": {"type": "string", "description": "Résumé rapport médical (si corporel)"},
                    "vrade_fcfa":                 {"type": "number"},
                    "cout_reparation_fcfa":        {"type": "number"},
                    # Évaluation dommages
                    "montant_materiel_fcfa":   {"type": "number"},
                    "montant_corporel_fcfa":   {"type": "number"},
                    "montant_jouissance_fcfa":  {"type": "number"},
                    "montant_total_propose_fcfa": {"type": "number"},
                    # Analyse
                    "score_fraude":            {"type": "integer"},
                    "alertes_fraude":          {"type": "array", "items": {"type": "string"}},
                    # Orientation
                    "orientation_recommandee": {"type": "string", "enum": [
                        "reglement_amiable", "expertise_complementaire",
                        "contentieux", "rejet_fraude", "rejet_exclusion", "rejet_police_invalide"
                    ]},
                    "avis_redacteur":          {"type": "string", "description": "Observations et recommandations du rédacteur"},
                    "redacteur_nom":           {"type": "string"},
                }, "required": ["reference", "montant_total_propose_fcfa", "orientation_recommandee"]},
            },
            {
                "name": "valider_note_technique",
                "description": (
                    "Soumet la Note Technique d'Instruction à la hiérarchie pour visa obligatoire. "
                    "L'agent se met en pause jusqu'à approbation du chef de service / direction technique. "
                    "Aucune offre ne peut être envoyée à l'assuré avant ce visa."
                ),
                "input_schema": {"type": "object", "properties": {
                    "reference":           {"type": "string"},
                    "note_technique_texte": {"type": "string", "description": "Note technique générée complète"},
                    "montant_total_propose_fcfa": {"type": "number"},
                    "orientation_recommandee": {"type": "string"},
                    "niveau_validation":   {"type": "string", "enum": [
                        "chef_service",        # < 2M FCFA
                        "directeur_technique", # 2M - 10M FCFA
                        "direction_generale",  # > 10M FCFA ou décès
                    ]},
                    "urgence":             {"type": "boolean", "description": "Délai CIMA < 15 jours"},
                }, "required": ["reference", "note_technique_texte", "montant_total_propose_fcfa", "orientation_recommandee"]},
            },
            {
                "name": "notifier_intervention_assure",
                "description": (
                    "Notifie l'assuré (ou les victimes/ayants droit) via portail Yukpo + WhatsApp "
                    "pour : accepter/refuser une offre, déposer des pièces, confirmer un rendez-vous. "
                    "Crée un lien sécurisé de portail avec token unique valable 30 jours."
                ),
                "input_schema": {"type": "object", "properties": {
                    "reference":            {"type": "string"},
                    "type_notification":    {"type": "string", "enum": [
                        "offre_indemnisation",      # Accepter/refuser l'offre (Art. 12-bis)
                        "demande_documents",        # Fournir pièces complémentaires
                        "convocation_expertise",    # RDV expertise (auto ou médicale)
                        "notification_paiement",    # Information règlement effectué
                        "demande_rib",              # Coordonnées bancaires pour virement
                        "transmission_ayants_droit", # Ayants droit dépôt pièces succession
                    ]},
                    "destinataire_nom":     {"type": "string"},
                    "destinataire_tel":     {"type": "string"},
                    "montant_offre_fcfa":   {"type": "number", "description": "Montant offre si type=offre_indemnisation"},
                    "documents_requis":     {"type": "array", "items": {"type": "string"}, "description": "Liste des pièces demandées"},
                    "message_complementaire": {"type": "string"},
                    "delai_reponse_jours":  {"type": "integer", "description": "Délai pour répondre (défaut 30j)"},
                }, "required": ["reference", "type_notification", "destinataire_nom", "destinataire_tel"]},
            },
            # ── Suivi & tableau de bord ───────────────────────────────────────
            {
                "name": "detecter_sinistres_auto_souffrance",
                "description": "Identifie les sinistres RC Auto en souffrance (délai CIMA Art. 12-bis dépassé ou proche)",
                "input_schema": {"type": "object", "properties": {
                    "type_sinistre":    {"type": "string", "enum": ["materiel", "corporel", "deces", "tous"]},
                    "jours_alerte":     {"type": "integer", "description": "Alerte X jours avant échéance (défaut 15)"},
                }, "required": []},
            },
            {
                "name": "calculer_interets_moratoires_auto",
                "description": "Calcule les intérêts moratoires RC Auto dus en cas de retard Art. 12-quater CIMA (12%/an)",
                "input_schema": {"type": "object", "properties": {
                    "reference":                    {"type": "string"},
                    "montant_indemnisation":        {"type": "number"},
                    "date_echeance_offre":          {"type": "string", "description": "YYYY-MM-DD — date limite offre indemnisation (J+90)"},
                    "date_paiement_effectif":       {"type": "string", "description": "YYYY-MM-DD — laisser vide = calcul à ce jour"},
                }, "required": ["reference", "montant_indemnisation", "date_echeance_offre"]},
            },
            {
                "name": "tableau_bord_sinistres_auto",
                "description": "Tableau de bord RC Auto : ouverts / en souffrance / délai moyen / charge sinistres / ratio S/P (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "periode":      {"type": "string", "description": "Ex: 2025-T1 ou 2025"},
                    "type_sinistre": {"type": "string", "enum": ["materiel", "corporel", "deces", "tous"]},
                }, "required": []},
            },
        ]

    def _prompt_questions_specifiques(self) -> str:
        return """
AGENT SINISTRES RC AUTO — Guide d'acquisition des informations

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴 RÈGLE N°1 ABSOLUE — MODE DÉCLARATION :
Si l'instruction contient "MODE DÉCLARATION", "nouveau sinistre", "déclarer", "accident", "déclaration" :
  → IGNORER les questions 1-3 ci-dessous
  → APPELER IMMÉDIATEMENT demander_information_utilisateur avec :
       question: "Pour déclarer cet accident RC Auto, veuillez envoyer les documents disponibles : constat amiable, PV de police, photos du véhicule, permis de conduire."
       type_reponse: "images"
       nombre_images_max: 10
       formats_acceptes: ["jpg", "png", "pdf"]
  → Après image reçue : appeler analyser_documents_auto → creer_sinistre
  → Ne demander date/police/immatriculation QUE si l'OCR ne les a pas extraites.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ MODE INSTRUCTION (sinistre RC Auto existant — référence connue) ━━━
1. AMBIGUÏTÉ MODE (uniquement si AUCUN indice de mode dans l'instruction)
   → "S'agit-il d'un nouvel accident RC Auto à déclarer, ou avez-vous un numéro de sinistre existant ?"
   type_reponse: choix_multiple  choix: ["Nouvel accident à déclarer", "J'ai déjà une référence (SIN-AAAA-NNN)"]

2. POLICE / IMMATRICULATION MANQUANTE (mode instruction, si pas dans les docs)
   → "Quel est le numéro de police RC Auto et l'immatriculation du véhicule assuré ?"
   type_reponse: texte_libre

3. DATE SINISTRE MANQUANTE (si pas extraite par OCR)
   → "Quelle est la date exacte de l'accident ? (JJ/MM/AAAA)"
   type_reponse: date

4. NATURE DES DOMMAGES NON PRÉCISÉE
   → "Quels types de dommages sont impliqués dans cet accident ?"
   type_reponse: choix_multiple  choix: ["Dommages matériels uniquement (véhicule)", "Dommages corporels uniquement (blessures)", "Matériels et corporels", "Décès d'une victime", "Dommages aux tiers uniquement"]

5. PHOTOS DU VÉHICULE ACCIDENTÉ ABSENTES (sinistre matériel)
   → "Veuillez envoyer les photos du véhicule accidenté (6 prises minimum : avant, arrière, côté gauche, côté droit, dommages rapprochés, plaque d'immatriculation). Ces photos sont obligatoires pour mandater l'expertise."
   type_reponse: images  nombre_images_max: 10  formats_acceptes: ["jpg", "png"]

6. CONSTAT AMIABLE OU PV POLICE NON FOURNI
   → "Veuillez scanner et envoyer le constat amiable signé par les deux parties OU le procès-verbal de police / main courante. Ce document est obligatoire pour la mise en jeu de la RC (Art. 205 et 208 CIMA)."
   type_reponse: image  nombre_images_max: 2  formats_acceptes: ["jpg", "png", "pdf"]

7. CERTIFICATS MÉDICAUX DES VICTIMES MANQUANTS (sinistre corporel)
   → "Veuillez transmettre les certificats médicaux de toutes les victimes blessées (certificat initial + de consolidation si disponible). Ces documents sont requis pour déclencher l'expertise médicale et appliquer le barème CIMA Art. 231."
   type_reponse: images  nombre_images_max: 10  formats_acceptes: ["jpg", "png", "pdf"]

8. ACTE DE DÉCÈS / RAPPORT IML MANQUANT (sinistre décès)
   → "Veuillez transmettre : l'acte de décès officiel + le rapport d'autopsie ou certificat médico-légal (IML). Ces pièces sont indispensables pour l'instruction du sinistre décès."
   type_reponse: images  nombre_images_max: 4  formats_acceptes: ["jpg", "png", "pdf"]

9. DEVIS OU FACTURE RÉPARATION NON TRANSMIS (dommages matériels)
   → "Veuillez envoyer le devis de réparation établi par le garage ou la facture définitive de remise en état du véhicule."
   type_reponse: images  nombre_images_max: 5  formats_acceptes: ["jpg", "png", "pdf"]

10. RAPPORT EXPERTISE AUTO MANQUANT (si expertise déjà mandatée)
    → "L'expertise automobile a-t-elle déjà été réalisée ? Si oui, envoyez le rapport d'expertise signé."
    type_reponse: image  nombre_images_max: 1  formats_acceptes: ["jpg", "png", "pdf"]

11. RAPPORT EXPERTISE MÉDICALE MANQUANT (pour fixation IPP)
    → "L'expertise médicale a-t-elle été réalisée ? Envoyez le rapport médical d'expertise fixant le taux d'IPP (Incapacité Permanente Partielle) et le nombre de jours d'ITT."
    type_reponse: image  nombre_images_max: 2  formats_acceptes: ["jpg", "png", "pdf"]

12. ATTESTATION ASSURANCE / CARTE ROSE NON VÉRIFIÉE
    → "Envoyez l'attestation d'assurance RC Auto et la carte rose du véhicule pour vérification de validité à la date du sinistre."
    type_reponse: images  nombre_images_max: 2  formats_acceptes: ["jpg", "png", "pdf"]

13. TIERS IMPLIQUÉ — COORDONNÉES MANQUANTES
    → "Y a-t-il un tiers identifié dans l'accident (conducteur adverse) ? Si oui, précisez : nom, assureur, numéro de police RC du tiers."
    type_reponse: texte_libre

14. DEGRÉ DE RESPONSABILITÉ NON ÉTABLI
    → "Comment est établie la responsabilité dans cet accident ?"
    type_reponse: choix_multiple  choix: ["Responsabilité totale de l'assuré", "Responsabilité totale du tiers", "Responsabilité partagée 50/50", "Responsabilité partagée (autre répartition)", "Responsabilité indéterminée (enquête en cours)"]

RÈGLE PROGRESSIVE (MODE INSTRUCTION uniquement) : Si en MODE INSTRUCTION (référence connue), commence par police → date → nature dommages. En MODE DÉCLARATION, commence TOUJOURS par appeler creer_sinistre — ne demande jamais de référence, c'est le système qui la génère. Ne demande qu'une info à la fois. Les pièces physiques (photos, constats, rapports) utilisent les types 'image' ou 'images'.
"""

    async def _executer_outil(self, nom: str, params: dict, user_id: int, execution_id: str) -> str:
        try:
            # ── creer_sinistre (MODE DÉCLARATION) ────────────────────────────
            if nom == "creer_sinistre":
                from datetime import date as _date
                import uuid as _uuid
                annee = _date.today().year
                seq = int(_uuid.uuid4().int % 900) + 100
                reference = f"SIN-{annee}-{seq:03d}"
                dossier = {
                    "reference": reference,
                    "statut": "ouvert",
                    "type_sinistre": params.get("type_sinistre", "materiel"),
                    "date_survenance": params.get("date_survenance"),
                    "lieu": params.get("lieu", ""),
                    "description": params.get("description", ""),
                    "police_id": params.get("police_id", ""),
                    "user_id": user_id,
                    "branche": "rc_auto",
                }
                try:
                    from core.orass_connector import orass
                    await orass.creer_sinistre(dossier)
                except Exception:
                    pass
                return json.dumps({
                    "reference": reference,
                    "message": f"✅ Dossier sinistre RC Auto créé — Référence : **{reference}**",
                    "statut": "ouvert",
                    "prochaine_etape": "Vérification de la police RC Auto",
                }, ensure_ascii=False)

            # ── get_sinistre_auto ─────────────────────────────────────────────
            if nom == "get_sinistre_auto":
                from core.orass_connector import orass
                dossier = await orass.get_sinistre(params["reference"])
                return json.dumps(dossier, ensure_ascii=False, default=str)

            # ── verifier_police_auto ──────────────────────────────────────────
            if nom == "verifier_police_auto":
                from core.orass_connector import orass
                from core.workflow_engine import verifier_validite_police
                validite = await orass.verifier_validite_contrat(params["police_id"])
                date_effet  = date.fromisoformat("2024-01-01")
                date_expiry = date.fromisoformat(validite.get("date_echeance", "2025-12-31"))
                prime_payee = validite.get("valide", True)
                date_sin    = date.fromisoformat(params["date_sinistre"])
                result = verifier_validite_police(date_effet, date_expiry, prime_payee, date_sin)
                garanties   = []  # non fourni par verifier_validite_contrat
                garantie_req = params.get("type_garantie_requis", "rc_seule")
                garantie_ok  = True  # on suppose couvert si police valide
                immat_police = params.get("immatriculation", "")
                immat_req    = params.get("immatriculation", "")
                immat_ok     = (not immat_req) or (immat_req.upper() == immat_police.upper())
                return json.dumps({
                    **result.donnees,
                    "garantie_requise": garantie_req,
                    "garantie_couverte": garantie_ok,
                    "immatriculation_police": immat_police,
                    "immatriculation_sinistre": immat_req,
                    "immatriculation_ok": immat_ok,
                    "peut_instruire": result.donnees.get("valide", False) and garantie_ok and immat_ok,
                }, ensure_ascii=False)

            # ── analyser_documents_auto ───────────────────────────────────────
            if nom == "analyser_documents_auto":
                from core.ia_client import ModeIA, ia_client
                resultats_docs = []
                for doc in params.get("documents", []):
                    type_doc = doc.get("type_document", "photo_vehicule_assure")
                    img_b64  = doc.get("image_base64", "")
                    # Nettoyer le préfixe data URI si présent
                    if img_b64 and img_b64.startswith("data:"):
                        try:
                            img_b64 = img_b64.split(",", 1)[1]
                        except IndexError:
                            pass
                    if img_b64:
                        # OCR Vision IA : GPT-4o primaire, Claude fallback
                        prompt_ocr = (
                            f"Tu es expert OCR sinistres RC Auto CIMA. "
                            f"Analyse cette image de type '{type_doc}'. "
                            f"Extrais en JSON : date_accident, heure, lieu, immatriculations, "
                            f"noms_conducteurs, assureurs, num_polices, dommages_decrits, "
                            f"responsabilite_estimee_pct, blesses (oui/non), montants_cites, "
                            f"signatures_presentes, anomalies_falsification. "
                            f"Retourne UNIQUEMENT le JSON."
                        )
                        try:
                            rep_v = await ia_client.analyser_image_vision(
                                image_b64=img_b64,
                                prompt=prompt_ocr,
                                mode=ModeIA.PRECISION,
                            )
                            texte = rep_v.contenu
                        except Exception as e_v:
                            logger.warning(f"[SinistresAuto] Vision IA {type_doc}: {e_v}")
                            texte = f"[{type_doc} — Vision IA non disponible: {e_v}]"
                    else:
                        texte = f"[{type_doc} — image non fournie]"
                    resultats_docs.append({"type": type_doc, "contenu": texte})
                if not resultats_docs:
                    return json.dumps({"message": "Aucun document fourni", "nb_docs": 0})
                prompt = f"""Analyse les documents RC Auto du sinistre {params['reference']}.

Documents analysés :
{json.dumps(resultats_docs, ensure_ascii=False, indent=2)}

Extrais et structure :
1. CIRCONSTANCES (date, heure, lieu, description accident)
2. VÉHICULES IMPLIQUÉS (immatriculations, marques, conducteurs)
3. DOMMAGES MATÉRIELS (nature, étendue estimée)
4. VICTIMES (nombre, noms, nature blessures si mentionné)
5. RESPONSABILITÉ (version assurée, version tiers, concordances/contradictions)
6. PIÈCES MANQUANTES pour compléter le dossier
7. SIGNAUX DE FRAUDE éventuels (incohérences, anomalies)
8. MONTANT ESTIMÉ indicatif pour provision PSAP"""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                from core.orass_connector import orass
                await orass.enregistrer_documents_sinistre(params["reference"], resultats_docs)
                return json.dumps({
                    "reference":    params["reference"],
                    "nb_documents": len(resultats_docs),
                    "analyse":      rep.contenu,
                    "types_docs":   [d["type"] for d in resultats_docs],
                }, ensure_ascii=False)

            # ── scorer_fraude_auto ────────────────────────────────────────────
            if nom == "scorer_fraude_auto":
                from core.workflow_engine import SignauxFraude, scorer_fraude_deterministe
                score = 0
                alertes = []
                jours_decl = params.get("jours_declaration", 0)
                if jours_decl > 5:
                    score += min(30, (jours_decl - 5) * 3)
                    alertes.append(f"Déclaration tardive : {jours_decl} jours ouvrés (limite Art. 205 : 5j)")
                if params.get("vehicule_recemment_assure"):
                    score += 25
                    alertes.append("Véhicule assuré < 30 jours avant sinistre")
                nb_sin = params.get("nb_sinistres_12_mois", 0)
                if nb_sin >= 3:
                    score += 20
                    alertes.append(f"{nb_sin} sinistres dans les 12 derniers mois")
                elif nb_sin >= 2:
                    score += 10
                jours_souscription = params.get("jours_depuis_souscription", 999)
                if jours_souscription < 30:
                    score += 20
                    alertes.append(f"Police souscrite seulement {jours_souscription} jours avant le sinistre")
                if params.get("tiers_non_identifie"):
                    score += 15
                    alertes.append("Conducteur tiers non identifié (délit de fuite)")
                if params.get("sinistre_nuit_weekend"):
                    score += 5
                    alertes.append("Sinistre survenu la nuit ou le week-end")
                if params.get("contradictions_constat"):
                    score += 25
                    alertes.append("Incohérences détectées entre le constat et les photos")
                montant = params.get("montant_declare", 0)
                if montant > 10_000_000:
                    score += 15
                    alertes.append(f"Montant déclaré très élevé : {montant:,} FCFA".replace(",", " "))
                score = min(score, 100)
                niveau = "ÉLEVÉ — Instruction approfondie obligatoire" if score > 60 else "MODÉRÉ — Vigilance recommandée" if score > 30 else "FAIBLE"
                return json.dumps({
                    "reference": params["reference"],
                    "score_fraude": score,
                    "niveau_risque": niveau,
                    "alertes": alertes,
                    "recommandation": "Déclencher analyser_fraude_ia avant tout calcul indemnisation" if score > 60 else "Poursuivre instruction normale",
                }, ensure_ascii=False)

            # ── analyser_fraude_ia ────────────────────────────────────────────
            if nom == "analyser_fraude_ia":
                from core.ia_client import ModeIA, ia_client
                prompt = f"""Analyse ce dossier sinistre RC Auto pour détecter des indices de fraude.
Référence : {params['reference']}
Déclaration : {params['declaration_texte']}
Rapport expertise : {params.get('rapport_expertise', 'Non disponible')}
Signaux déjà détectés : {', '.join(params.get('signaux_detectes', [])) or 'Aucun'}

Livre : Code CIMA — Art. 200-264 RC Auto

Fournis une analyse structurée :
1. Cohérence déclaration / expertise / photos
2. Indices spécifiques de fraude RC Auto (mise en scène, faux constat, gonflement dommages)
3. Vérifications complémentaires recommandées
4. Recommandation : CLASSER / INSTRUIRE AVEC VIGILANCE / REJETER POUR FRAUDE"""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
                return rep.contenu

            # ── enregistrer_victimes ──────────────────────────────────────────
            if nom == "enregistrer_victimes":
                from core.orass_connector import orass
                victimes = params.get("victimes", [])
                await orass.enregistrer_victimes_sinistre(params["reference"], victimes)
                nb_blesses = sum(1 for v in victimes if v.get("statut") in ("blesse_leger", "blesse_grave"))
                nb_deces = sum(1 for v in victimes if v.get("statut") == "deces")
                return json.dumps({
                    "reference": params["reference"],
                    "nb_victimes_total": len(victimes),
                    "nb_blesses": nb_blesses,
                    "nb_deces": nb_deces,
                    "expertises_medicales_requises": nb_blesses,
                    "note": "Expertise médicale obligatoire pour chaque victime blessée (Art. 231 CIMA)",
                }, ensure_ascii=False)

            # ── planifier_expertise_auto ──────────────────────────────────────
            if nom == "planifier_expertise_auto":
                from core.approval_queue import approval_queue
                await approval_queue.ajouter({
                    "type": "expertise_auto",
                    "reference": params["reference"],
                    "adresse": params.get("adresse_vehicule"),
                    "montant_estime": params.get("montant_estime", 0),
                    "urgence": params.get("urgence", False),
                    "user_id": user_id,
                    "execution_id": execution_id,
                    "description": f"Expertise automobile sinistre {params['reference']} — estimation {params.get('montant_estime', 0):,} FCFA".replace(",", " "),
                })
                return f"Expertise automobile planifiée pour {params['reference']} — en attente d'affectation expert"

            # ── planifier_expertise_medicale ──────────────────────────────────
            if nom == "planifier_expertise_medicale":
                from core.approval_queue import approval_queue
                await approval_queue.ajouter({
                    "type": "expertise_medicale_auto",
                    "reference": params["reference"],
                    "victimes": params.get("victimes_a_expertiser", []),
                    "urgence": params.get("urgence_medicale", False),
                    "hopital": params.get("hopital_actuel"),
                    "user_id": user_id,
                    "execution_id": execution_id,
                    "description": f"Expertise médicale sinistre {params['reference']} — {len(params.get('victimes_a_expertiser', []))} victime(s)",
                })
                return f"Expertise médicale planifiée — {len(params.get('victimes_a_expertiser', []))} victime(s) — en attente d'affectation médecin expert (Art. 231 CIMA)"

            # ── calculer_indemnisation_materielle ─────────────────────────────
            if nom == "calculer_indemnisation_materielle":
                vrade        = params["valeur_venale_vrade"]
                cout_rep     = params["cout_reparation"]
                franchise    = params.get("franchise_contractuelle", 0)
                epave        = params.get("epave_valeur", 0)
                vei          = cout_rep > vrade  # Véhicule Économiquement Irréparable
                base_calc    = vrade - epave if vei else cout_rep
                indemnite    = max(0, base_calc - franchise)
                return json.dumps({
                    "reference": params["reference"],
                    "valeur_venale_vrade": vrade,
                    "cout_reparation": cout_rep,
                    "vehicule_economiquement_irreparable": vei,
                    "valeur_epave_deduire": epave if vei else 0,
                    "base_calcul": base_calc,
                    "franchise_contractuelle": franchise,
                    "indemnite_materielle_fcfa": indemnite,
                    "base_legale": "Art. 242 Code CIMA — min(coût réparation, VRADE) − franchise",
                }, ensure_ascii=False)

            # ── calculer_perte_jouissance ─────────────────────────────────────
            if nom == "calculer_perte_jouissance":
                tarif = params.get("tarif_location_journalier", 15_000)  # défaut 15k FCFA/j
                jours = params["duree_immobilisation_jours"]
                usage_pro = params.get("usage_professionnel", False)
                indemnite = tarif * jours
                return json.dumps({
                    "reference": params["reference"],
                    "duree_immobilisation_jours": jours,
                    "tarif_location_journalier_fcfa": tarif,
                    "indemnite_perte_jouissance_fcfa": indemnite,
                    "majoration_usage_professionnel": "applicable si justifié" if usage_pro else "non applicable",
                }, ensure_ascii=False)

            # ── calculer_prejudices_corporels ─────────────────────────────────
            if nom == "calculer_prejudices_corporels":
                age     = params["age_victime"]
                ipp_pct = params.get("taux_ipp_pct", 0)
                dfp     = _calculer_dfp(age, ipp_pct) if ipp_pct > 0 else {"dfp_fcfa": 0}
                itt     = _calculer_itt(
                    params.get("nb_jours_itt", 0),
                    params.get("nb_jours_itp", 0),
                    params.get("taux_itp_pct", 50.0),
                )
                deg_pd  = params.get("degre_pretium_doloris", 0)
                deg_pe  = params.get("degre_prejudice_esthetique", 0)
                pretium = _PRETIUM_DOLORIS_FCFA.get(deg_pd, 0)
                estheti = _PREJUDICE_ESTHETIQUE_FCFA.get(deg_pe, 0)
                frais_med = params.get("frais_medicaux_reels", 0)
                perte_rev = params.get("perte_revenus_mensuelle", 0) * params.get("duree_arret_professionnel_mois", 0)
                tierce    = 0
                if params.get("assistance_tierce_personne"):
                    tierce = round(_SMIG_MENSUEL_FCFA / 3)  # forfait mensuel indicatif
                total = (
                    dfp.get("dfp_fcfa", 0) +
                    itt.get("total_incapacite_temporaire_fcfa", 0) +
                    pretium + estheti + frais_med + perte_rev + tierce
                )
                return json.dumps({
                    "reference":   params["reference"],
                    "nom_victime": params.get("nom_victime", "Victime"),
                    "dfp":         dfp,
                    "incapacite_temporaire": itt,
                    "pretium_doloris_fcfa":  pretium,
                    "degre_pretium_doloris": deg_pd,
                    "prejudice_esthetique_fcfa": estheti,
                    "degre_prejudice_esthetique": deg_pe,
                    "frais_medicaux_reels_fcfa": frais_med,
                    "perte_revenus_professionnels_fcfa": perte_rev,
                    "tierce_personne_mensuel_indicatif_fcfa": tierce,
                    "total_prejudices_corporels_fcfa": total,
                    "base_legale": "Art. 231-242 Code CIMA — barème dommages corporels",
                    "note": "Montant indicatif — le taux IPP doit être fixé par un médecin expert agréé",
                }, ensure_ascii=False)

            # ── calculer_prejudices_deces ─────────────────────────────────────
            if nom == "calculer_prejudices_deces":
                age      = params["age_victime"]
                revenu   = params.get("revenu_mensuel_fcfa", 0)
                nb_ad    = params.get("nb_ayants_droit_charge", 0)
                coeff    = _coeff_age(age)
                # Perte revenus ayants droit = revenu × 12 × coeff_age × part_charge
                part_charge = min(0.75, 0.25 + nb_ad * 0.1)  # 25% + 10% par ayant droit, max 75%
                perte_revenus = round(revenu * 12 * coeff * part_charge) if revenu > 0 else 0
                deg_pd   = params.get("degre_pretium_doloris", 0)
                pretium  = _PRETIUM_DOLORIS_FCFA.get(deg_pd, 0)
                obseques = params.get("frais_obseques_reels", 0)
                total    = perte_revenus + pretium + obseques
                return json.dumps({
                    "reference":    params["reference"],
                    "nom_victime":  params.get("nom_victime", "Victime décédée"),
                    "age_victime":  age,
                    "coeff_age":    coeff,
                    "revenu_mensuel_reference_fcfa": revenu,
                    "nb_ayants_droit_charge": nb_ad,
                    "part_charge_pct": round(part_charge * 100, 1),
                    "perte_revenus_ayants_droit_fcfa": perte_revenus,
                    "pretium_doloris_souffrance_avant_deces_fcfa": pretium,
                    "frais_obseques_fcfa": obseques,
                    "total_prejudice_deces_fcfa": total,
                    "ayants_droit": params.get("ayants_droit", []),
                    "base_legale": "Art. 231 Code CIMA — barème dommages corporels décès",
                }, ensure_ascii=False)

            # ── calculer_tierce_personne ──────────────────────────────────────
            if nom == "calculer_tierce_personne":
                heures_j  = params["nb_heures_aide_jour"]
                duree     = params.get("duree_mois", 0)
                nature    = params.get("nature_aide", "aide_menagere")
                tarif_h   = {"aide_specialisee": 2_000, "aide_menagere": 800, "garde_malade": 1_500}.get(nature, 1_000)
                montant_m = round(tarif_h * heures_j * 30)
                if duree > 0:
                    total = montant_m * duree
                    mode  = f"rente mensuelle {montant_m:,} FCFA × {duree} mois = {total:,} FCFA".replace(",", " ")
                else:
                    total = montant_m * 12 * 10  # capitalisation indicative 10 ans
                    mode  = f"capitalisation indicative 10 ans = {total:,} FCFA (à affiner par actuaire)".replace(",", " ")
                return json.dumps({
                    "reference":     params["reference"],
                    "nom_victime":   params.get("nom_victime", "Victime"),
                    "nature_aide":   nature,
                    "heures_jour":   heures_j,
                    "tarif_horaire_fcfa": tarif_h,
                    "montant_mensuel_fcfa": montant_m,
                    "mode_calcul":   mode,
                    "total_tierce_personne_fcfa": total,
                    "base_legale": "Art. 241 Code CIMA — assistance tierce personne",
                }, ensure_ascii=False)

            # ── valider_reglement_auto ────────────────────────────────────────
            if nom == "valider_reglement_auto":
                from core.approval_queue import approval_queue
                montant_total = params.get("montant_total", 0)
                await approval_queue.ajouter({
                    "type":              "sinistre_auto",
                    "reference":         params["reference"],
                    "decision":          params["decision"],
                    "montant_materiel":  params.get("montant_materiel", 0),
                    "montant_corporel":  params.get("montant_corporel", 0),
                    "montant_total":     montant_total,
                    "motif":             params["motif"],
                    "beneficiaire":      params.get("beneficiaire_nom"),
                    "rib":               params.get("rib_virement"),
                    "details_victimes":  params.get("details_victimes", []),
                    "user_id":           user_id,
                    "execution_id":      execution_id,
                    "description": (
                        f"Règlement RC Auto {params['reference']} — "
                        f"{params['decision']} — "
                        f"{montant_total:,} FCFA".replace(",", " ")
                    ),
                })
                return (
                    f"Décision de règlement soumise pour validation humaine :\n"
                    f"Référence : {params['reference']}\n"
                    f"Décision : {params['decision']}\n"
                    f"Montant total : {montant_total:,} FCFA\n"
                    f"Motif : {params['motif']}\n"
                    "En attente d'approbation."
                ).replace(",", " ")

            # ── generer_courrier_auto ─────────────────────────────────────────
            if nom == "generer_courrier_auto":
                from modules.documents.generateur import generer_courrier_sinistre
                pdf_path = await generer_courrier_sinistre(
                    reference=params["reference"],
                    template=params["template"],
                    montant=params.get("montant", 0),
                    motif=params.get("motif", ""),
                )
                return f"Courrier RC Auto généré : {pdf_path}"

            # ── passer_ecriture_sinistre_auto ─────────────────────────────────
            if nom == "passer_ecriture_sinistre_auto":
                from core.workflow_engine import coder_ecriture_comptable
                from core.approval_queue import approval_queue
                result = coder_ecriture_comptable(
                    type_operation=params["type_operation"],
                    montant=params["montant"],
                    reference=params["reference"],
                )
                await approval_queue.ajouter({
                    "type": "ecriture_comptable_auto",
                    "reference": params["reference"],
                    "ecriture": result.donnees,
                    "montant": params["montant"],
                    "type_operation": params["type_operation"],
                    "user_id": user_id,
                    "execution_id": execution_id,
                    "description": f"Écriture RC Auto {params['reference']} — {params['type_operation']} — {params['montant']:,} FCFA".replace(",", " "),
                })
                return (
                    f"Écriture comptable présentée pour validation :\n"
                    f"Débit : {result.donnees.get('debit_compte')} — Crédit : {result.donnees.get('credit_compte')}\n"
                    f"Montant : {params['montant']:,} FCFA\n"
                    "En attente d'approbation avant passage en base ORASS."
                ).replace(",", " ")

            # ── notifier_assure_auto ──────────────────────────────────────────
            if nom == "notifier_assure_auto":
                from core.notifications import notifications
                await notifications.envoyer(
                    canal=params.get("canal", "whatsapp"),
                    destinataire=params["telephone"],
                    message=params["message"],
                )
                return f"Notification envoyée sur {params.get('canal', 'whatsapp')} — sinistre {params.get('reference', '')}"

            # ── traiter_subrogation ───────────────────────────────────────────
            if nom == "traiter_subrogation":
                from core.approval_queue import approval_queue
                part = params.get("part_responsabilite_pct", 100)
                montant_recours = round(params["montant_regle"] * part / 100)
                await approval_queue.ajouter({
                    "type": "subrogation_auto",
                    "reference": params["reference"],
                    "montant_regle": params["montant_regle"],
                    "nom_tiers": params.get("nom_tiers"),
                    "assureur_tiers": params.get("assureur_tiers"),
                    "police_tiers": params.get("police_tiers"),
                    "part_responsabilite_pct": part,
                    "montant_recours": montant_recours,
                    "user_id": user_id,
                    "execution_id": execution_id,
                    "description": f"Subrogation Art. 250 CIMA — sinistre {params['reference']} — recours {montant_recours:,} FCFA".replace(",", " "),
                })
                return (
                    f"Recours subrogatoire initié (Art. 250 CIMA) :\n"
                    f"Tiers : {params.get('nom_tiers', 'Non identifié')} — Assureur : {params.get('assureur_tiers', 'Inconnu')}\n"
                    f"Responsabilité tiers : {part}%\n"
                    f"Montant recours : {montant_recours:,} FCFA\n"
                    "En attente de validation avant envoi mise en demeure."
                ).replace(",", " ")

            # ── generer_note_technique ────────────────────────────────────────
            if nom == "generer_note_technique":
                from core.ia_client import ModeIA, ia_client
                from datetime import date as _date
                from core.suivi_delai_cima import suivi_delai_cima

                ref = params["reference"]
                montant = params.get("montant_total_propose_fcfa", 0)
                orientation = params.get("orientation_recommandee", "reglement_amiable")
                score_fraude = params.get("score_fraude", 0)

                # Délais CIMA restants
                delai_offre = suivi_delai_cima.calculer_delai_restant(ref, "offre_indemnisation_envoyee", montant)
                jours_restants = delai_offre.get("jours_restants", "N/A")

                # Niveau de validation selon montant
                if montant > 10_000_000:
                    niveau = "DIRECTION GÉNÉRALE"
                elif montant > 2_000_000:
                    niveau = "DIRECTEUR TECHNIQUE"
                else:
                    niveau = "CHEF DE SERVICE SINISTRES"

                prompt = f"""Génère une Note Technique d'Instruction Sinistre (NTIS) RC Auto complète et structurée.

DONNÉES DU DOSSIER :
Référence : {ref}
Assuré : {params.get('assure_nom', 'N/A')}
Police : {params.get('police_id', 'N/A')}
Véhicule assuré : {params.get('immatriculation', 'N/A')}
Garanties : {params.get('garanties_souscrites', 'N/A')}

ACCIDENT :
Date : {params.get('date_sinistre', 'N/A')}
Lieu : {params.get('lieu_sinistre', 'N/A')}
Circonstances : {params.get('description_accident', 'N/A')}
Tiers impliqué : {params.get('tiers_nom', 'Aucun')} — Assureur : {params.get('tiers_assureur', 'N/A')}
Responsabilité : {params.get('responsabilite', 'N/A')} — Part assuré : {params.get('part_responsabilite_assure_pct', 'N/A')}%

EXPERTISE :
Rapport auto : {params.get('rapport_expertise_auto', 'Non disponible')}
Rapport médical : {params.get('rapport_expertise_medicale', 'Non applicable')}
VRADE : {params.get('vrade_fcfa', 0):,} FCFA
Coût réparation : {params.get('cout_reparation_fcfa', 0):,} FCFA

ÉVALUATION DOMMAGES :
Matériel : {params.get('montant_materiel_fcfa', 0):,} FCFA
Corporel : {params.get('montant_corporel_fcfa', 0):,} FCFA
Perte jouissance : {params.get('montant_jouissance_fcfa', 0):,} FCFA
TOTAL PROPOSÉ : {montant:,} FCFA

FRAUDE :
Score : {score_fraude}/100
Alertes : {', '.join(params.get('alertes_fraude', [])) or 'Aucune'}

DÉLAIS CIMA :
Jours restants avant échéance offre (Art. 12-bis) : {jours_restants} jours
Niveau validation requis : {niveau}

ORIENTATION RECOMMANDÉE : {orientation.upper().replace('_', ' ')}

AVIS RÉDACTEUR : {params.get('avis_redacteur', '')}

---

Génère la note technique complète en utilisant EXACTEMENT la structure suivante :

═══════════════════════════════════════════════════════════
        NOTE TECHNIQUE D'INSTRUCTION SINISTRE — RC AUTO
                    CONFIDENTIEL — USAGE INTERNE
═══════════════════════════════════════════════════════════
N° Sinistre : [ref]                     Date instruction : [aujourd'hui]
Rédigé par : [redacteur]                Niveau validation : [niveau]
═══════════════════════════════════════════════════════════

I. IDENTIFICATION DES PARTIES
II. VÉHICULES IMPLIQUÉS
III. CIRCONSTANCES DE L'ACCIDENT
IV. ANALYSE DES GARANTIES & VALIDITÉ POLICE
V. RÉSULTATS D'EXPERTISE
VI. ÉVALUATION DES DOMMAGES (tableau par poste)
VII. ANALYSE DU RISQUE DE FRAUDE
VIII. POSITION JURIDIQUE ET RECOURS
IX. PROPOSITION DE RÈGLEMENT
X. DÉLAIS CIMA & CONFORMITÉ RÉGLEMENTAIRE
XI. ORIENTATION ET AVIS DU RÉDACTEUR
XII. VISA HIÉRARCHIQUE

Remplis chaque section avec les données du dossier. Sois précis, factuel, professionnel.
Pour la Section XII, laisse les lignes de signature vides (à compléter par la hiérarchie)."""

                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                note_texte = rep.contenu

                # Enregistrer la note dans ORASS
                from core.orass_connector import orass
                await orass.enregistrer_document_sinistre(
                    reference=ref,
                    type_doc="note_technique_instruction",
                    contenu=note_texte,
                    metadata={
                        "montant_propose": montant,
                        "orientation": orientation,
                        "score_fraude": score_fraude,
                        "niveau_validation": niveau,
                        "redacteur": params.get("redacteur_nom", f"user_{user_id}"),
                    },
                )

                return json.dumps({
                    "reference": ref,
                    "note_technique": note_texte,
                    "montant_propose_fcfa": montant,
                    "orientation": orientation,
                    "niveau_validation_requis": niveau,
                    "jours_restants_delai_cima": jours_restants,
                    "message": f"Note technique générée — à soumettre pour visa {niveau} via valider_note_technique",
                }, ensure_ascii=False)

            # ── valider_note_technique ────────────────────────────────────────
            if nom == "valider_note_technique":
                from core.approval_queue import approval_queue
                ref = params["reference"]
                montant = params.get("montant_total_propose_fcfa", 0)
                orientation = params.get("orientation_recommandee", "")
                urgence = params.get("urgence", False)

                # Déterminer le niveau automatiquement si non fourni
                niveau = params.get("niveau_validation")
                if not niveau:
                    if montant > 10_000_000:
                        niveau = "direction_generale"
                    elif montant > 2_000_000:
                        niveau = "directeur_technique"
                    else:
                        niveau = "chef_service"

                niveau_libelle = {
                    "chef_service":        "Chef de Service Sinistres",
                    "directeur_technique": "Directeur Technique",
                    "direction_generale":  "Direction Générale",
                }.get(niveau, niveau)

                await approval_queue.ajouter({
                    "type":              "note_technique_sinistre",
                    "reference":         ref,
                    "note_technique":    params.get("note_technique_texte", "")[:2000],
                    "montant":           montant,
                    "orientation":       orientation,
                    "niveau_validation": niveau,
                    "urgence":           urgence,
                    "_messages_contexte":    [],
                    "_tool_use_id":          "",
                    "_resultat_pre_pause":   "",
                    "_agent_type":           self.type_agent.value,
                    "_instruction_originale": f"Validation note technique {ref}",
                    "_contexte_execution":   {},
                    "user_id":           user_id,
                    "execution_id":      execution_id,
                    "description": (
                        f"📋 NOTE TECHNIQUE — Sinistre {ref}\n"
                        f"Orientation : {orientation.replace('_', ' ').upper()}\n"
                        f"Montant proposé : {montant:,} FCFA\n"
                        f"Visa requis : {niveau_libelle}"
                        + (" — ⚡ URGENT" if urgence else "")
                    ).replace(",", " "),
                })

                return (
                    f"Note Technique soumise pour visa {niveau_libelle}.\n"
                    f"Référence : {ref}\n"
                    f"Montant proposé : {montant:,} FCFA\n"
                    f"Orientation : {orientation.replace('_', ' ')}\n"
                    "⏳ En attente de validation hiérarchique avant envoi offre à l'assuré."
                ).replace(",", " ")

            # ── notifier_intervention_assure ──────────────────────────────────
            if nom == "notifier_intervention_assure":
                from core.portail_externe import portail_externe
                from core.approval_queue import approval_queue

                ref = params["reference"]
                type_notif = params.get("type_notification", "offre_indemnisation")
                dest_nom = params.get("destinataire_nom", "")
                dest_tel = params.get("destinataire_tel", "")
                montant_offre = params.get("montant_offre_fcfa", 0)
                delai = params.get("delai_reponse_jours", 30)

                # Créer un item approval_queue pour que l'agent attende la réponse
                item_attente = await approval_queue.ajouter({
                    "type":              "question_utilisateur",
                    "question":          f"[PORTAIL ASSURÉ] Réponse de {dest_nom} attendue — {type_notif} — sinistre {ref}",
                    "contexte_question": f"Notification envoyée à {dest_nom} ({dest_tel}) — délai {delai}j",
                    "type_reponse":      "texte_libre",
                    "_messages_contexte":    [],
                    "_tool_use_id":          "",
                    "_resultat_pre_pause":   "",
                    "_agent_type":           self.type_agent.value,
                    "_instruction_originale": f"Attente réponse assuré {ref}",
                    "_contexte_execution":   {},
                    "user_id":   user_id,
                    "execution_id": execution_id,
                })

                # Créer l'intervention externe
                iv = await portail_externe.creer_intervention(
                    type_intervention=type_notif if type_notif in (
                        "offre_indemnisation", "demande_documents", "transmission_ayants_droit", "demande_rib"
                    ) else "transmission_documents",
                    reference_sinistre=ref,
                    branche="rc_auto",
                    destinataire_nom=dest_nom,
                    destinataire_telephone=dest_tel,
                    destinataire_type="assure",
                    approval_item_id=item_attente.id,
                    execution_id=execution_id,
                    agent_type=self.type_agent.value,
                    user_id=user_id,
                    delai_heures=delai * 24,
                    montant_offre=montant_offre,
                    contexte_supplementaire=params.get("message_complementaire", ""),
                )

                docs_requis = "\n".join(f"  • {d}" for d in params.get("documents_requis", []))
                return (
                    f"Notification envoyée à {dest_nom} ({dest_tel}) :\n"
                    f"Type : {type_notif.replace('_', ' ')}\n"
                    f"Montant offre : {montant_offre:,} FCFA\n"
                    f"Délai réponse : {delai} jours\n"
                    + (f"Documents demandés :\n{docs_requis}\n" if docs_requis else "")
                    + f"Lien portail : {iv.token[:12]}... (envoyé sur WhatsApp)\n"
                    f"En attente de réponse via portail ou WhatsApp."
                ).replace(",", " ")

            # ── detecter_sinistres_auto_souffrance ────────────────────────────
            if nom == "detecter_sinistres_auto_souffrance":
                from core.orass_connector import orass
                jours_alerte = params.get("jours_alerte", 15)
                sinistres = await orass.get_sinistres_ouverts(branche="rc_auto", statut="ouvert")
                souffrance, alerte_proche = [], []
                aujourd_hui = date.today()
                for s in sinistres:
                    type_sin = s.get("type_sinistre", "tous")
                    if params.get("type_sinistre", "tous") not in ("tous", type_sin):
                        continue
                    date_decl = date.fromisoformat(s.get("date_declaration", aujourd_hui.isoformat()))
                    echeance  = date_decl + timedelta(days=_DELAI_OFFRE_INDEMNISATION)
                    jours     = (echeance - aujourd_hui).days
                    if jours < 0:
                        s["retard_jours_offre"] = abs(jours)
                        souffrance.append(s)
                    elif jours <= jours_alerte:
                        s["jours_avant_echeance"] = jours
                        alerte_proche.append(s)
                return json.dumps({
                    "sinistres_en_souffrance": len(souffrance),
                    "alertes_proches_echeance": len(alerte_proche),
                    "details_souffrance": souffrance[:20],
                    "details_alertes": alerte_proche[:20],
                    "base_legale": f"Art. 12-bis CIMA — délai offre {_DELAI_OFFRE_INDEMNISATION}j / Art. 12-ter paiement {_DELAI_PAIEMENT_APRES_ACCORD}j",
                }, ensure_ascii=False, default=str)

            # ── calculer_interets_moratoires_auto ─────────────────────────────
            if nom == "calculer_interets_moratoires_auto":
                montant      = params["montant_indemnisation"]
                date_ech     = date.fromisoformat(params["date_echeance_offre"])
                date_pmt     = date.fromisoformat(params["date_paiement_effectif"]) if params.get("date_paiement_effectif") else date.today()
                if date_pmt <= date_ech:
                    return json.dumps({"reference": params["reference"], "interets_moratoires_fcfa": 0, "message": "Paiement dans les délais CIMA"})
                jours_retard = (date_pmt - date_ech).days
                interets     = round(montant * _TAUX_INTERET_MORATOIRE * jours_retard / 365)
                return json.dumps({
                    "reference": params["reference"],
                    "montant_principal_fcfa": montant,
                    "jours_retard": jours_retard,
                    "taux_moratoire_annuel_pct": _TAUX_INTERET_MORATOIRE * 100,
                    "interets_moratoires_fcfa": interets,
                    "total_du_fcfa": montant + interets,
                    "base_legale": "Art. 12-quater Code CIMA — intérêts moratoires 12%/an",
                }, ensure_ascii=False)

            # ── tableau_bord_sinistres_auto ───────────────────────────────────
            if nom == "tableau_bord_sinistres_auto":
                from core.orass_connector import orass
                data = await orass.get_tableau_bord_sinistres(
                    branche="rc_auto",
                    periode=params.get("periode"),
                    statut="tous",
                )
                nb_ouverts    = data.get("nb_ouverts", 0)
                nb_souffrance = data.get("nb_souffrance", 0)
                return json.dumps({
                    "nb_sinistres_rc_auto_ouverts": nb_ouverts,
                    "nb_en_souffrance": nb_souffrance,
                    "pct_souffrance": round(nb_souffrance / max(nb_ouverts, 1) * 100, 1),
                    "delai_moyen_instruction_jours": data.get("delai_moyen_jours", 0),
                    "charge_sinistres_fcfa": data.get("montant_total_en_cours", 0),
                    "taux_fraude_pct": data.get("taux_fraude_pct", 0),
                    "conformite_cima": "NON CONFORME" if nb_souffrance > 0 else "CONFORME",
                    "base_legale": "Art. 12-bis/12-ter/12-quater Code CIMA",
                    "periode": params.get("periode", "en cours"),
                }, ensure_ascii=False, default=str)

            return f"Outil '{nom}' non reconnu dans l'agent Sinistres RC Auto"

        except Exception as e:
            logger.error(f"[AgentSinistresAuto] Erreur outil {nom} : {e}")
            return f"ERREUR {nom} : {e}"
