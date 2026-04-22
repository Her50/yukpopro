"""Agent Souscription & Tarification — de la demande à la police émise."""
from __future__ import annotations
import json, logging
from core.agent_orchestrateur import TypeAgent
from core.workflow_engine import (
    calculer_prime_rc_auto, calculer_prime_mrh,
    calculer_prime_transport, calculer_prime_rc_pro,
    calculer_prime_accident_corporel, calculer_regularisation_avenant,
)
from agents.base_agent import BaseAgent

logger = logging.getLogger("yukpo_assurance.agents.souscription")

# ── Zones carte rose / attestation frontière ────────────────────────────────
# CEMAC : 6 pays Afrique Centrale (attestation verte CEMAC)
_PAYS_CEMAC = {"CM", "CF", "CG", "GA", "GQ", "TD"}
# CEDEAO : 15 pays Afrique de l'Ouest (carte brune CEDEAO)
_PAYS_CEDEAO = {"BJ", "BF", "CV", "CI", "GM", "GH", "GN", "GW", "LR", "ML", "MR", "NE", "NG", "SN", "SL", "TG"}

# Surcharges annuelles attestation frontière (FCFA, par zone de destination)
_SURTAXE_CEMAC_FCFA  = 15_000   # Attestation CEMAC (Art. 105 Code CIMA)
_SURTAXE_CEDEAO_FCFA = 20_000   # Carte brune CEDEAO (Accord inter-États)


class AgentSouscription(BaseAgent):
    type_agent = TypeAgent.SOUSCRIPTION

    def _system_prompt(self) -> str:
        return """Tu es l'Agent Souscription de YukpoAssurance, expert en tarification et émission de polices CIMA (Vie ET Non-Vie).

BRANCHES COUVERTES :
- NON-VIE : RC Auto, MRH (locataire/propriétaire), Transport (facultés/corps), RC Professionnelle,
            Accidents Corporels (individuel/collectif), Construction (DO/TRC/RCD), Assistance
- VIE : Déléguer à l'Agent Vie pour tout produit vie/prévoyance/épargne/retraite

CARTE ROSE / ATTESTATION FRONTIÈRE RC AUTO :
- NATIONALE : carte rose CIMA standard, 0 surtaxe
- CEMAC (CM, CF, CG, GA, GQ, TD) : Attestation d'assurance CEMAC (verte), surtaxe 15 000 FCFA
  → Art. 105 Code CIMA + Protocole CEMAC sur le transport
- CEDEAO (BJ, BF, CI, GH, NG, SN, TG…) : Carte brune CEDEAO, surtaxe 20 000 FCFA
  → Accord CEDEAO sur la libre circulation
→ Toujours utiliser generer_carte_rose pour tout transit frontière

ORDRE D'EXÉCUTION (souscription nouvelle) :
1. analyser_kyc (si document fourni)
2. verifier_antecedents → historique sinistres, CRM, bonus-malus
3. calculer_prime → tarification DÉTERMINISTE selon branche
4. evaluer_risque_ia → SEULEMENT si risque atypique ou hors barème
5. emettre_police → validation humaine obligatoire
6. collecter_prime → paiement Mobile Money
7. envoyer_police → WhatsApp/email + carte rose si RC auto
8. generer_carte_rose → si transit CEMAC ou CEDEAO demandé

OPÉRATIONS EN COURS DE CONTRAT :
- Avenant : modification garanties, changement véhicule/bâtiment, changement usage
- Résiliation : à l'échéance, en cours d'année (remboursement prorata)
- Renouvellement : relance automatique J-60, conditions identiques ou révisées

RÈGLES ABSOLUES :
- Tarification = 0 IA (barèmes CIMA + tables actuarielles)
- IA uniquement pour risques atypiques et évaluation narrative
- Toute émission, résiliation, avenant, attestation frontière → validation humaine"""

    def _definir_outils(self) -> list[dict]:
        return [
            {
                "name": "analyser_kyc",
                "description": "Analyse CNI/permis/carte grise via OCR IA — extrait les données structurées",
                "input_schema": {"type": "object", "properties": {
                    "type_document": {"type": "string", "enum": ["cni", "permis", "carte_grise"]},
                    "image_base64":  {"type": "string"},
                }, "required": ["type_document"]},
            },
            {
                "name": "verifier_antecedents",
                "description": "Vérifie l'historique sinistres et calcule le CRM (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "client_id":  {"type": "string"},
                    "telephone":  {"type": "string"},
                }, "required": []},
            },
            {
                "name": "calculer_prime",
                "description": "Calcule la prime selon la branche CIMA (déterministe, 0 IA) — RC auto, MRH, transport, RC pro, accident",
                "input_schema": {"type": "object", "properties": {
                    "branche":    {"type": "string", "enum": ["rc_auto", "mrh", "transport", "rc_pro", "accident_corporel", "construction"]},
                    # RC Auto
                    "pays":       {"type": "string", "description": "Code ISO pays ex: CM, CI, SN"},
                    "categorie":  {"type": "string", "enum": ["VP_inf_1600","VP_sup_1600","UT_inf_3500","taxi","bus","moto"]},
                    "usage":      {"type": "string", "enum": ["personnel","commercial","taxi","transport","location"]},
                    "crm":        {"type": "number", "description": "Coefficient bonus-malus"},
                    # MRH
                    "valeur_batiment": {"type": "number"},
                    "valeur_contenu":  {"type": "number"},
                    "profil_mrh":      {"type": "string", "enum": ["locataire","proprietaire_occupant","bailleur"]},
                    "garanties_mrh":   {"type": "array", "items": {"type": "string"}},
                    "zone_mrh":        {"type": "string", "enum": ["zone_A","zone_B","zone_C"]},
                    # Transport
                    "type_transport":  {"type": "string", "enum": ["maritime","aerien","terrestre"]},
                    "type_garantie_transport": {"type": "string", "enum": ["all_risks","fautes_communes","fap_sauf","corps"]},
                    "valeur_marchandise": {"type": "number"},
                    "trajet":          {"type": "string", "enum": ["import","export","cabotage"]},
                    # RC Pro
                    "profession":         {"type": "string"},
                    "chiffre_affaires":   {"type": "number"},
                    "plafond_garantie":   {"type": "number"},
                    # Accident corporel
                    "capital_deces":      {"type": "number"},
                    "capital_invalide":   {"type": "number"},
                    "nb_personnes":       {"type": "integer"},
                    "profession_risque":  {"type": "string", "enum": ["bureau","terrain","risque_eleve"]},
                }, "required": ["branche"]},
            },
            {
                "name": "gerer_avenant",
                "description": "Traite un avenant en cours de contrat : calcul prorata, modification garanties (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "police_id":          {"type": "string"},
                    "type_avenant":       {"type": "string", "enum": ["extension_garantie","changement_vehicule","changement_usage","suspension","adjonction_conducteur"]},
                    "date_avenant":       {"type": "string"},
                    "prime_actuelle":     {"type": "number"},
                    "prime_nouvelle":     {"type": "number"},
                    "date_echeance":      {"type": "string"},
                    "description":        {"type": "string"},
                }, "required": ["police_id", "type_avenant", "date_avenant"]},
            },
            {
                "name": "gerer_resiliation",
                "description": "Traite une résiliation de contrat avec calcul ristourne (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "police_id":     {"type": "string"},
                    "motif":         {"type": "string", "enum": ["echeance","non_paiement","accord_parties","sinistralite","vente_vehicule","deces","changement_assureur"]},
                    "date_resil":    {"type": "string"},
                    "prime_annuelle": {"type": "number"},
                    "date_echeance": {"type": "string"},
                }, "required": ["police_id", "motif", "date_resil"]},
            },
            {
                "name": "evaluer_risque_ia",
                "description": "Évalue un risque atypique via IA (véhicule spécial, usage inhabituel)",
                "input_schema": {"type": "object", "properties": {
                    "description_risque": {"type": "string"},
                    "prime_standard":     {"type": "number"},
                }, "required": ["description_risque"]},
            },
            {
                "name": "emettre_police",
                "description": "Soumet l'émission de police pour validation humaine",
                "input_schema": {"type": "object", "properties": {
                    "assure_nom":    {"type": "string"},
                    "assure_tel":    {"type": "string"},
                    "vehicule":      {"type": "string"},
                    "garanties":     {"type": "array", "items": {"type": "string"}},
                    "prime_ttc":     {"type": "number"},
                    "pays":          {"type": "string"},
                    "duree_mois":    {"type": "integer"},
                }, "required": ["assure_nom", "prime_ttc"]},
            },
            {
                "name": "collecter_prime",
                "description": "Initie la collecte de prime via Mobile Money (MTN/Orange)",
                "input_schema": {"type": "object", "properties": {
                    "telephone":     {"type": "string"},
                    "montant":       {"type": "number"},
                    "operateur":     {"type": "string", "enum": ["mtn", "orange", "wave"]},
                    "reference":     {"type": "string"},
                }, "required": ["telephone", "montant"]},
            },
            {
                "name": "envoyer_police",
                "description": "Envoie la police et carte rose par WhatsApp/email",
                "input_schema": {"type": "object", "properties": {
                    "police_id":  {"type": "string"},
                    "telephone":  {"type": "string"},
                    "email":      {"type": "string"},
                    "canal":      {"type": "string", "enum": ["whatsapp", "email", "les_deux"]},
                }, "required": ["police_id"]},
            },
            {
                "name": "generer_carte_rose",
                "description": (
                    "Génère l'attestation frontière RC auto (carte rose CIMA, attestation CEMAC ou carte brune CEDEAO) "
                    "selon la zone de destination. "
                    "CEMAC : CM, CF, CG, GA, GQ, TD — attestation verte CEMAC, surtaxe 15 000 FCFA. "
                    "CEDEAO : BJ, BF, CI, GH, NG, SN, TG… — carte brune CEDEAO, surtaxe 20 000 FCFA. "
                    "Intérieur pays : carte rose CIMA nationale, 0 surtaxe."
                ),
                "input_schema": {"type": "object", "properties": {
                    "police_id":        {"type": "string", "description": "Identifiant de la police RC auto"},
                    "pays_immatriculation": {"type": "string", "description": "Code ISO pays ex: CM"},
                    "pays_destination": {"type": "string", "description": "Code ISO pays de destination ex: GA, CI, NG"},
                    "immatriculation":  {"type": "string"},
                    "marque_modele":    {"type": "string"},
                    "nom_assure":       {"type": "string"},
                    "date_debut":       {"type": "string", "description": "Format YYYY-MM-DD"},
                    "date_fin":         {"type": "string", "description": "Format YYYY-MM-DD"},
                    "prime_rc_auto":    {"type": "number", "description": "Prime RC auto de base en FCFA"},
                }, "required": ["police_id", "pays_destination", "nom_assure"]},
            },
        ]

    def _prompt_questions_specifiques(self) -> str:
        return """
AGENT SOUSCRIPTION — quand demander une information :

1. IDENTITÉ ASSURÉ INCOMPLÈTE (nom, date de naissance, CNI manquants)
   → "Pour établir la police, j'ai besoin des coordonnées complètes de l'assuré. Pouvez-vous me communiquer : nom complet, date de naissance (JJ/MM/AAAA) et numéro CNI/passeport ?"
   type_reponse: texte_libre

2. PRODUIT OU BRANCHE NON PRÉCISÉ
   → "Quel type d'assurance souhaitez-vous souscrire pour cet assuré ?"
   type_reponse: choix_multiple  choix: ["RC Auto", "MRH (Multirisque Habitation)", "RC Professionnelle", "Transport de marchandises", "Accidents Corporels", "Assistance Voyage"]

3. USAGE DU VÉHICULE AMBIGU (RC Auto — détermine le tarif CIMA)
   → "Quel est l'usage principal du véhicule à assurer ? (Ce critère détermine la prime selon le barème CIMA Art. 200)"
   type_reponse: choix_multiple  choix: ["Personnel / familial", "Professionnel (déplacements professionnels)", "Commercial / livraison de marchandises", "Transport rémunéré de personnes (taxi, VTC)", "Engin agricole ou de chantier"]

4. PUISSANCE FISCALE MANQUANTE (RC Auto)
   → "Quelle est la puissance fiscale du véhicule en chevaux fiscaux (CV) ? Cette information figure sur la carte grise du véhicule."
   type_reponse: nombre

5. VALEUR DU BIEN À ASSURER MANQUANTE (MRH / Transport)
   → "Quelle est la valeur totale à assurer (en FCFA) ? Pour MRH : valeur du mobilier et équipements ; pour Transport : valeur facture des marchandises."
   type_reponse: nombre

6. ZONE DE CIRCULATION (Carte Rose — surtaxe CEMAC/CEDEAO)
   → "Le véhicule est-il destiné à circuler hors du territoire national ?"
   type_reponse: choix_multiple  choix: ["Cameroun uniquement (pas de surtaxe)", "Zone CEMAC uniquement (CM, CF, CG, GA, GQ, TD) — surtaxe 15 000 FCFA", "Zone CEDEAO (15 pays Afrique de l'Ouest) — surtaxe 20 000 FCFA", "Zone mixte CEMAC + CEDEAO"]

7. ANTÉCÉDENTS SINISTRES (bonus/malus)
   → "Combien de sinistres déclarés l'assuré a-t-il eu au cours des 3 dernières années ? (Impacte le coefficient bonus/malus)"
   type_reponse: choix_multiple  choix: ["Aucun sinistre (bonus maximum)", "1 sinistre", "2 sinistres", "3 sinistres ou plus (malus)", "Première souscription — pas d'historique"]

8. DATE D'EFFET SOUHAITÉE
   → "À quelle date souhaitez-vous que la couverture débute ?"
   type_reponse: date

9. DURÉE DE LA POLICE NON PRÉCISÉE
   → "Pour quelle durée souhaitez-vous cette police d'assurance ?"
   type_reponse: choix_multiple  choix: ["1 mois", "3 mois", "6 mois", "1 an (police annuelle)", "Durée spécifique à préciser"]

10. CNI / PASSEPORT DE L'ASSURÉ REQUIS (KYC obligatoire)
    → "Veuillez scanner et envoyer la CNI ou le passeport de l'assuré (recto/verso). Obligatoire pour le KYC réglementaire avant émission de la police."
    type_reponse: images  nombre_images_max: 2  formats_acceptes: ["jpg", "png", "pdf"]

11. CARTE GRISE DU VÉHICULE ABSENTE (RC Auto — données techniques)
    → "Pouvez-vous envoyer une photo de la carte grise du véhicule ? Elle permet de vérifier la puissance fiscale, le numéro de châssis et la catégorie pour le tarif CIMA."
    type_reponse: image  nombre_images_max: 1  formats_acceptes: ["jpg", "png"]

12. PHOTOS DU VÉHICULE POUR ÉTAT DES LIEUX (clause dommages — tous risques)
    → "Pour la garantie Tous Risques, nous avons besoin de 4 photos du véhicule (avant, arrière, côté gauche, côté droit) attestant son état avant souscription."
    type_reponse: images  nombre_images_max: 6  formats_acceptes: ["jpg", "png"]

PROGRESSION : Produit → Identité assuré → Pièces KYC (CNI/carte grise) → Caractéristiques du risque → Zone circulation → Durée → Date d'effet.
"""

    async def _executer_outil(self, nom: str, params: dict, user_id: int, execution_id: str) -> str:
        try:
            if nom == "analyser_kyc":
                from core.ocr_processor import ocr_processor
                return await ocr_processor.analyser_document(
                    params.get("image_base64", ""),
                    params["type_document"],
                )

            if nom == "verifier_antecedents":
                from core.orass_connector import orass
                hist = await orass.get_historique_client(
                    params.get("client_id"),
                    params.get("telephone"),
                )
                nb_sin = hist.get("nb_sinistres_12_mois", 0)
                crm = max(0.50, min(3.50, 1.0 - nb_sin * 0.05))
                return json.dumps({"nb_sinistres_12_mois": nb_sin, "crm": crm}, ensure_ascii=False)

            if nom == "calculer_prime":
                branche = params.get("branche", "rc_auto")
                if branche == "rc_auto":
                    result = calculer_prime_rc_auto(
                        pays=params.get("pays", "CM"),
                        categorie=params.get("categorie", "VP_inf_1600"),
                        usage=params.get("usage", "personnel"),
                        crm=params.get("crm", 1.0),
                    )
                elif branche == "mrh":
                    result = calculer_prime_mrh(
                        valeur_batiment=params.get("valeur_batiment", 0),
                        valeur_contenu=params.get("valeur_contenu", 0),
                        profil=params.get("profil_mrh", "locataire"),
                        garanties=params.get("garanties_mrh"),
                        zone=params.get("zone_mrh", "zone_A"),
                    )
                elif branche == "transport":
                    result = calculer_prime_transport(
                        type_transport=params.get("type_transport", "terrestre"),
                        type_garantie=params.get("type_garantie_transport", "all_risks"),
                        valeur_marchandise=params.get("valeur_marchandise", 0),
                        trajet=params.get("trajet", "import"),
                    )
                elif branche == "rc_pro":
                    result = calculer_prime_rc_pro(
                        profession=params.get("profession", "default"),
                        chiffre_affaires=params.get("chiffre_affaires", 0),
                        plafond_garantie=params.get("plafond_garantie", 100_000_000),
                    )
                elif branche == "accident_corporel":
                    result = calculer_prime_accident_corporel(
                        capital_deces=params.get("capital_deces", 5_000_000),
                        capital_invalide_totale=params.get("capital_invalide", 5_000_000),
                        nb_personnes=params.get("nb_personnes", 1),
                        profession_risque=params.get("profession_risque", "bureau"),
                    )
                else:
                    return f"Branche '{branche}' non gérée ici — consulter l'Agent Vie pour les produits vie"
                return json.dumps(result.donnees, ensure_ascii=False)

            if nom == "gerer_avenant":
                from datetime import date as _date
                result = calculer_regularisation_avenant(
                    type_avenant=params["type_avenant"],
                    prime_annuelle_actuelle=params.get("prime_actuelle", 0),
                    date_avenant=_date.fromisoformat(params["date_avenant"]),
                    date_echeance=_date.fromisoformat(params["date_echeance"]) if params.get("date_echeance") else _date.today().replace(month=12, day=31),
                    prime_nouvelle=params.get("prime_nouvelle", 0),
                )
                from core.approval_queue import approval_queue
                await approval_queue.ajouter({
                    "type": "avenant_police",
                    "police_id": params["police_id"],
                    "type_avenant": params["type_avenant"],
                    "regularisation": result.donnees,
                    "description": params.get("description", ""),
                    "user_id": user_id,
                    "execution_id": execution_id,
                })
                return f"Avenant {params['type_avenant']} soumis — {result.message}"

            if nom == "gerer_resiliation":
                from datetime import date as _date
                prime_a = params.get("prime_annuelle", 0)
                date_r = _date.fromisoformat(params["date_resil"])
                motif = params["motif"]
                # Résiliation non-paiement : 0 ristourne (Art. 10 CIMA)
                if motif == "non_paiement":
                    ristourne = 0
                    result_msg = "Résiliation non-paiement — aucune ristourne (Art. 10 CIMA)"
                else:
                    date_ech = _date.fromisoformat(params["date_echeance"]) if params.get("date_echeance") else date_r.replace(month=12, day=31)
                    result = calculer_regularisation_avenant(
                        type_avenant="suspension",
                        prime_annuelle_actuelle=prime_a,
                        date_avenant=date_r,
                        date_echeance=date_ech,
                    )
                    ristourne = result.donnees.get("ristourne_fcfa", 0)
                    result_msg = result.message

                from core.approval_queue import approval_queue
                await approval_queue.ajouter({
                    "type": "resiliation_police",
                    "police_id": params["police_id"],
                    "motif": motif,
                    "ristourne_fcfa": ristourne,
                    "montant": ristourne,
                    "user_id": user_id,
                    "execution_id": execution_id,
                })
                return f"Résiliation soumise — {result_msg}"

            if nom == "evaluer_risque_ia":
                from core.ia_client import ModeIA, ia_client
                prompt = f"""Évalue ce risque d'assurance automobile non standard.
Description : {params['description_risque']}
Prime standard calculée : {params.get('prime_standard', 0):,} FCFA

Recommande : surprime (%), motif, conditions particulières à appliquer."""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
                return rep.contenu

            if nom == "emettre_police":
                from core.approval_queue import approval_queue
                await approval_queue.ajouter({
                    "type":         "emission_police",
                    "assure":       params.get("assure_nom"),
                    "prime_ttc":    params.get("prime_ttc"),
                    "vehicule":     params.get("vehicule"),
                    "user_id":      user_id,
                    "execution_id": execution_id,
                })
                return f"Police en attente de validation — Prime : {params.get('prime_ttc', 0):,} FCFA".replace(",", " ")

            if nom == "collecter_prime":
                from modules.paiement.gestionnaire_paiement import GestionnairePaiement
                gp = GestionnairePaiement()
                ref = await gp.initier_paiement(
                    telephone=params["telephone"],
                    montant=params["montant"],
                    operateur=params.get("operateur", "mtn"),
                    reference=params.get("reference", ""),
                )
                return f"Paiement initié : {ref}"

            if nom == "envoyer_police":
                from core.notifications import notifications
                if params.get("telephone") and params.get("canal") in ("whatsapp", "les_deux"):
                    await notifications.envoyer(
                        canal="whatsapp",
                        destinataire=params["telephone"],
                        message=f"Votre police {params['police_id']} est émise. Document joint.",
                    )
                return "Police envoyée"

            if nom == "generer_carte_rose":
                dest = (params.get("pays_destination") or "").upper()
                prime_base = params.get("prime_rc_auto", 0)

                # Déterminer zone et type d'attestation
                if dest in _PAYS_CEMAC:
                    zone       = "CEMAC"
                    type_doc   = "Attestation d'assurance CEMAC (verte)"
                    surtaxe    = _SURTAXE_CEMAC_FCFA
                    pays_couverts = sorted(_PAYS_CEMAC)
                    base_legale = "Art. 105 Code CIMA — Protocole CEMAC transport"
                elif dest in _PAYS_CEDEAO:
                    zone       = "CEDEAO"
                    type_doc   = "Carte brune d'assurance CEDEAO"
                    surtaxe    = _SURTAXE_CEDEAO_FCFA
                    pays_couverts = sorted(_PAYS_CEDEAO)
                    base_legale = "Accord CEDEAO sur la libre circulation — Carte brune inter-États"
                else:
                    zone       = "NATIONALE"
                    type_doc   = "Carte rose RC auto CIMA (nationale)"
                    surtaxe    = 0
                    pays_couverts = [params.get("pays_immatriculation", "CM")]
                    base_legale = "Art. 201 Code CIMA — RC obligatoire véhicule terrestre à moteur"

                prime_totale = prime_base + surtaxe

                attestation = {
                    "police_id":       params["police_id"],
                    "type_document":   type_doc,
                    "zone":            zone,
                    "pays_destination": dest,
                    "pays_couverts":   pays_couverts,
                    "nom_assure":      params["nom_assure"],
                    "immatriculation": params.get("immatriculation", ""),
                    "marque_modele":   params.get("marque_modele", ""),
                    "date_debut":      params.get("date_debut", ""),
                    "date_fin":        params.get("date_fin", ""),
                    "prime_rc_base_fcfa": prime_base,
                    "surtaxe_frontiere_fcfa": surtaxe,
                    "prime_totale_fcfa": prime_totale,
                    "base_legale":     base_legale,
                    "statut":          "en_attente_emission",
                }

                # Soumettre pour validation avant émission physique
                from core.approval_queue import approval_queue
                await approval_queue.ajouter({
                    "type":         "emission_attestation_frontiere",
                    "zone":         zone,
                    "police_id":    params["police_id"],
                    "nom_assure":   params["nom_assure"],
                    "destination":  dest,
                    "surtaxe_fcfa": surtaxe,
                    "prime_totale_fcfa": prime_totale,
                    "donnees":      attestation,
                    "user_id":      user_id,
                    "execution_id": execution_id,
                    "description":  (
                        f"{type_doc} — {params['nom_assure']} → {dest} "
                        f"| Surtaxe : {surtaxe:,} FCFA | Total : {prime_totale:,} FCFA"
                    ).replace(",", " "),
                })

                return json.dumps({
                    "statut":      "en_attente_validation",
                    "zone":        zone,
                    "type_doc":    type_doc,
                    "surtaxe_fcfa": surtaxe,
                    "prime_totale_fcfa": prime_totale,
                    "pays_couverts": pays_couverts,
                    "message": (
                        f"{type_doc} soumise pour validation.\n"
                        f"Zone : {zone} | Destination : {dest}\n"
                        f"Surtaxe frontière : {surtaxe:,} FCFA\n"
                        f"Prime totale : {prime_totale:,} FCFA\n"
                        f"Pays couverts : {', '.join(pays_couverts)}\n"
                        f"Base légale : {base_legale}"
                    ).replace(",", " "),
                }, ensure_ascii=False)

            return f"Outil '{nom}' non reconnu"
        except Exception as e:
            logger.error(f"[AgentSouscription] Erreur outil {nom} : {e}")
            return f"ERREUR {nom} : {e}"
