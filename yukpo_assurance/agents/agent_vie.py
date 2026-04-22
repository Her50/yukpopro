"""
Agent Vie & Prévoyance — Livre II Code CIMA (Art. 57-100).

Produits gérés :
  - Temporaire décès (protection pure)
  - Vie entière (décès à tout moment)
  - Épargne mixte (décès + capitalisation)
  - Retraite / capitalisation
  - Prévoyance collective (groupe employeur)
  - Assurance emprunteur (adossée au crédit)
  - Micro-assurance vie (Art. 300+ CIMA)
  - Rente viagère / rente invalidité

Opérations en cours de vie :
  - Calcul et révision des PM (Provisions Mathématiques)
  - Avance sur police (Art. 75 CIMA — max 80% PM)
  - Rachat total ou partiel (Art. 65 CIMA — après 2 ans)
  - Réduction (Art. 64 — arrêt cotisations)
  - Transformation de contrat
  - Changement de bénéficiaire
  - Arbitrage (unités de compte)
"""
from __future__ import annotations
import json
import logging
from datetime import date, timedelta
from core.agent_orchestrateur import TypeAgent
from core.workflow_engine import (
    calculer_prime_vie, calculer_valeur_rachat_vie,
    calculer_avance_police_vie, calculer_indemnite_sinistre_vie,
    calculer_marge_solvabilite_vie,
)
from agents.base_agent import BaseAgent

logger = logging.getLogger("yukpo_assurance.agents.vie")


class AgentVie(BaseAgent):
    type_agent = TypeAgent.VIE

    def _system_prompt(self) -> str:
        return """Tu es l'Agent Vie & Prévoyance de YukpoAssurance, expert en assurance de personnes zone CIMA (Livre II).

PRODUITS :
1. Protection (temporaire décès, vie entière, prévoyance décès/invalidité)
2. Épargne (mixte, capitalisation, retraite)
3. Emprunteur (assurance crédit immobilier et consommation)
4. Collectif groupe (prévoyance entreprise)
5. Micro-assurance vie (Art. 300+ CIMA — primes < 15 000 FCFA/mois)
6. Rentes (viagère, invalidité, éducation)

OPÉRATIONS COURANTES :
- Souscription → calcul prime actuariel → collecte → émission certificat
- Avance sur police (Art. 75 CIMA) : demande → calcul → validation → virement
- Rachat (Art. 65) : demande → vérification délai 2 ans → calcul valeur → validation
- Réduction (Art. 64) : arrêt cotisations → calcul capital réduit
- Sinistre vie : réception déclaration → vérification pièces → calcul prestation → paiement

RÈGLES FONDAMENTALES (Livre II CIMA) :
- Art. 57 : Définition contrat assurance vie
- Art. 63 : Provisions mathématiques obligatoires (taux min 3,5%)
- Art. 64 : Valeur de réduction (pas de rachat < 2 ans)
- Art. 65 : Valeur de rachat (min 2 ans cotisations)
- Art. 73 : Sinistres vie — paiement dans 30 jours après pièces complètes
- Art. 74 : Désignation bénéficiaire libre, irrévocable si acceptée
- Art. 75 : Avance sur police — max 80% PM

CALCULS ACTUARIELS : TOUJOURS déterministes (tables mortalité CIMA)
COMMUNICATION : WhatsApp + email + courrier officiel selon importance"""

    def _definir_outils(self) -> list[dict]:
        return [
            {
                "name": "calculer_prime_vie",
                "description": "Calcule la prime d'assurance vie selon méthode actuarielle CIMA (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "type_produit":       {"type": "string", "enum": [
                        "temporaire_deces", "vie_entiere", "epargne_mixte",
                        "retraite", "emprunteur", "prevoyance_deces",
                        "rente", "micro_assurance"
                    ]},
                    "age_souscription":   {"type": "integer"},
                    "duree_annees":       {"type": "integer"},
                    "capital_garanti":    {"type": "number"},
                    "sexe":               {"type": "string", "enum": ["M", "F"]},
                    "periodicite":        {"type": "string", "enum": ["annuelle", "semestrielle", "trimestrielle", "mensuelle"]},
                    "avec_exoneration":   {"type": "boolean", "description": "Clause exonération cotisations en cas d'invalidité"},
                }, "required": ["type_produit", "age_souscription", "duree_annees", "capital_garanti"]},
            },
            {
                "name": "souscrire_contrat_vie",
                "description": "Souscrit un contrat vie : questionnaire médical + émission",
                "input_schema": {"type": "object", "properties": {
                    "assure_nom":         {"type": "string"},
                    "assure_tel":         {"type": "string"},
                    "assure_ddn":         {"type": "string", "description": "Date naissance YYYY-MM-DD"},
                    "type_produit":       {"type": "string"},
                    "capital_garanti":    {"type": "number"},
                    "duree_annees":       {"type": "integer"},
                    "prime_periodique":   {"type": "number"},
                    "beneficiaires":      {"type": "array", "items": {"type": "object"}},
                    "questionnaire_sante": {"type": "object", "description": "Réponses au questionnaire médical"},
                }, "required": ["assure_nom", "type_produit", "capital_garanti"]},
            },
            {
                "name": "evaluer_risque_medical",
                "description": "Évalue le risque médical via IA pour surprime ou exclusion (sélection médicale)",
                "input_schema": {"type": "object", "properties": {
                    "questionnaire_sante": {"type": "object"},
                    "age":                {"type": "integer"},
                    "type_produit":       {"type": "string"},
                    "capital_demande":    {"type": "number"},
                }, "required": ["questionnaire_sante", "age"]},
            },
            {
                "name": "calculer_pm",
                "description": "Calcule les provisions mathématiques d'un contrat (déterministe — méthode prospective)",
                "input_schema": {"type": "object", "properties": {
                    "police_id":          {"type": "string"},
                    "pm_initiale":        {"type": "number"},
                    "prime_annuelle":     {"type": "number"},
                    "duree_ecoulee":      {"type": "integer"},
                    "duree_totale":       {"type": "integer"},
                    "taux_technique":     {"type": "number", "description": "3.5% minimum CIMA"},
                }, "required": ["police_id", "pm_initiale"]},
            },
            {
                "name": "traiter_rachat",
                "description": "Traite une demande de rachat total ou partiel (Art. 65 CIMA)",
                "input_schema": {"type": "object", "properties": {
                    "police_id":              {"type": "string"},
                    "pm_actuelle":            {"type": "number"},
                    "duree_ecoulee_annees":   {"type": "integer"},
                    "duree_totale_annees":    {"type": "integer"},
                    "type_rachat":            {"type": "string", "enum": ["total", "partiel"]},
                    "montant_partiel":        {"type": "number"},
                }, "required": ["police_id", "pm_actuelle", "duree_ecoulee_annees", "duree_totale_annees"]},
            },
            {
                "name": "traiter_avance",
                "description": "Traite une demande d'avance sur police (Art. 75 CIMA — max 80% PM)",
                "input_schema": {"type": "object", "properties": {
                    "police_id":      {"type": "string"},
                    "pm_actuelle":    {"type": "number"},
                    "montant_demande": {"type": "number"},
                    "duree_mois":     {"type": "integer", "description": "Durée de remboursement souhaitée"},
                }, "required": ["police_id", "pm_actuelle"]},
            },
            {
                "name": "traiter_reduction",
                "description": "Calcule le capital réduit en cas d'arrêt des cotisations (Art. 64 CIMA)",
                "input_schema": {"type": "object", "properties": {
                    "police_id":       {"type": "string"},
                    "capital_initial": {"type": "number"},
                    "pm_actuelle":     {"type": "number"},
                    "prime_unique_eq": {"type": "number", "description": "Prime unique équivalente du contrat initial"},
                }, "required": ["police_id", "capital_initial", "pm_actuelle"]},
            },
            {
                "name": "instruire_sinistre_vie",
                "description": "Instruit un sinistre vie : vérification pièces, calcul prestation, paiement",
                "input_schema": {"type": "object", "properties": {
                    "police_id":              {"type": "string"},
                    "type_sinistre":          {"type": "string", "enum": ["deces", "invalidite_totale", "invalidite_partielle", "echeance", "accident"]},
                    "date_sinistre":          {"type": "string"},
                    "capital_contrat":        {"type": "number"},
                    "ipp_pct":                {"type": "number"},
                    "pieces_fournies":        {"type": "array", "items": {"type": "string"}},
                    "double_capital_accident": {"type": "boolean"},
                }, "required": ["police_id", "type_sinistre", "capital_contrat"]},
            },
            {
                "name": "gerer_prevoyance_groupe",
                "description": "Gère un contrat prévoyance collective employeur (souscription, sinistre, révision)",
                "input_schema": {"type": "object", "properties": {
                    "action":         {"type": "string", "enum": ["souscrire", "sinistre", "revision_annuelle", "adhesion_salarie", "radiation"]},
                    "entreprise_nom": {"type": "string"},
                    "nb_salaries":    {"type": "integer"},
                    "masse_salariale": {"type": "number"},
                    "garanties":      {"type": "array", "items": {"type": "string"}, "description": "['deces','invalidite','incapacite','hospitalisation']"},
                    "sinistre_data":  {"type": "object"},
                }, "required": ["action"]},
            },
            {
                "name": "verifier_pieces_sinistre_vie",
                "description": "Vérifie que le dossier sinistre vie est complet (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "type_sinistre":  {"type": "string"},
                    "pieces_reçues":  {"type": "array", "items": {"type": "string"}},
                }, "required": ["type_sinistre", "pieces_reçues"]},
            },
            {
                "name": "changer_beneficiaire",
                "description": "Traite une demande de changement de bénéficiaire (Art. 74 CIMA — irrévocable si acceptée)",
                "input_schema": {"type": "object", "properties": {
                    "police_id":            {"type": "string"},
                    "ancien_beneficiaire":  {"type": "object"},
                    "nouveau_beneficiaire": {"type": "object"},
                    "beneficiaire_a_accepte": {"type": "boolean", "description": "True si l'ancien a accepté irrévocablement"},
                }, "required": ["police_id", "nouveau_beneficiaire"]},
            },
            {
                "name": "resilier_contrat_vie",
                "description": "Traite une résiliation de contrat vie : calcul valeur de rachat ou réduction, validation",
                "input_schema": {"type": "object", "properties": {
                    "police_id":           {"type": "string"},
                    "motif_resiliation":   {"type": "string", "enum": ["demande_assure", "non_paiement", "fausse_declaration", "expiration"]},
                    "pm_actuelle":         {"type": "number"},
                    "duree_ecoulee_annees": {"type": "integer"},
                    "duree_totale_annees": {"type": "integer"},
                }, "required": ["police_id", "motif_resiliation", "pm_actuelle"]},
            },
            {
                "name": "monitoring_portefeuille_vie",
                "description": "Suivi du portefeuille vie : PM totales, rachats, primes à encaisser, polices en risque (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "periode":   {"type": "string"},
                    "type_produit": {"type": "string", "description": "Filtrer par produit ou 'tous'"},
                    "alertes_seuil": {"type": "boolean", "description": "Inclure alertes: PM insuffisantes, primes impayées"},
                }, "required": []},
            },
        ]

    def _prompt_questions_specifiques(self) -> str:
        return """
AGENT VIE & PRÉVOYANCE — quand demander une information :

1. ÂGE DU SOUSCRIPTEUR MANQUANT (calcul actuariel obligatoire)
   → "Quel est l'âge du souscripteur à la date d'effet souhaitée ? (L'âge est indispensable au calcul actuariel de la prime selon les tables CIMA)"
   type_reponse: nombre

2. STATUT FUMEUR / NON-FUMEUR (surcharge mortalité)
   → "Le souscripteur est-il fumeur ? (Cette information est requise pour l'évaluation du risque décès selon l'Art. 57 CIMA)"
   type_reponse: oui_non

3. TYPE DE PRODUIT VIE NON PRÉCISÉ
   → "Quel type de produit d'assurance vie souhaitez-vous souscrire ?"
   type_reponse: choix_multiple  choix: ["Temporaire décès (protection famille)", "Vie entière (capital au décès)", "Épargne mixte (capital + protection)", "Retraite / capitalisation", "Prévoyance décès-invalidité", "Emprunteur (assurance crédit)", "Prévoyance collective entreprise"]

4. CAPITAL SOUHAITÉ NON PRÉCISÉ
   → "Quel est le capital assuré souhaité (en FCFA) ? Pour une épargne : précisez également si vous souhaitez une prime mensuelle ou un versement unique."
   type_reponse: nombre

5. DURÉE DU CONTRAT ABSENTE (calcul de la PM Art. 63)
   → "Sur quelle durée souhaitez-vous le contrat ? (Durée minimum 1 an, détermine les provisions mathématiques obligatoires)"
   type_reponse: choix_multiple  choix: ["5 ans", "10 ans", "15 ans", "20 ans", "25 ans", "30 ans", "Jusqu'à l'âge de 60 ans", "Jusqu'à l'âge de 65 ans"]

6. BÉNÉFICIAIRES NON DÉSIGNÉS (Art. 74 CIMA)
   → "Qui sont les bénéficiaires désignés en cas de décès ? (Indiquez nom complet, lien de parenté et répartition en % si plusieurs bénéficiaires)"
   type_reponse: texte_libre

7. ÉTAT DE SANTÉ (déclaration médicale pour capitaux élevés)
   → "Le souscripteur a-t-il des antécédents médicaux significatifs ? (Pour les capitaux > 5 000 000 FCFA, une déclaration de santé est requise)"
   type_reponse: choix_multiple  choix: ["Aucun antécédent — bonne santé", "Hypertension artérielle", "Diabète", "Maladie cardiaque", "Autre pathologie chronique", "Refus de déclaration"]

8. OPÉRATION SUR CONTRAT EXISTANT (rachat / avance / réduction)
   → "Quel est le numéro de police du contrat vie concerné par cette opération ?"
   type_reponse: texte_libre

9. PRIME SOUHAITÉE vs CAPITAL (épargne : l'un détermine l'autre)
   → "Préférez-vous définir votre objectif par le capital final souhaité ou par la prime mensuelle que vous pouvez verser ?"
   type_reponse: choix_multiple  choix: ["Par le capital final (je connais le montant cible)", "Par la prime mensuelle (je connais ma capacité d'épargne)", "Les deux (vérifier la cohérence)"]

10. PIÈCE D'IDENTITÉ ASSURÉ (KYC vie — obligatoire Art. 5 CIMA)
    → "Merci de scanner votre pièce d'identité en cours de validité (CNI recto/verso ou passeport). Elle est obligatoire pour l'établissement du contrat vie conformément à la réglementation CIMA."
    type_reponse: images  nombre_images_max: 2  formats_acceptes: ["jpg", "png", "pdf"]

11. CERTIFICAT MÉDICAL (contrats vie > 5 000 000 FCFA ou profil risque élevé)
    → "Votre dossier nécessite un certificat médical établi par un médecin agréé (capital demandé > 5M FCFA). Veuillez en transmettre une copie."
    type_reponse: image  nombre_images_max: 1  formats_acceptes: ["jpg", "png", "pdf"]

12. ACTE DE DÉCÈS / CERTIFICAT MÉDICAL (sinistre décès en assurance vie)
    → "Pour le règlement du capital décès, veuillez transmettre l'acte de décès certifié et le certificat médical de décès. Documents obligatoires pour application de l'Art. 73 CIMA."
    type_reponse: images  nombre_images_max: 3  formats_acceptes: ["jpg", "png", "pdf"]

PROGRESSION : Type produit → Âge → Fumeur → Capital/Durée → Bénéficiaires → État de santé → KYC (pièce d'identité).
"""

    async def _executer_outil(self, nom: str, params: dict, user_id: int, execution_id: str) -> str:
        try:
            if nom == "calculer_prime_vie":
                result = calculer_prime_vie(
                    age_souscription=params["age_souscription"],
                    duree_annees=params["duree_annees"],
                    capital_garanti=params["capital_garanti"],
                    type_produit=params["type_produit"],
                    sexe=params.get("sexe", "M"),
                )
                # Calcul périodicités
                donnees = dict(result.donnees)
                periodicite = params.get("periodicite", "annuelle")
                if periodicite == "mensuelle":
                    donnees["prime_periodique"] = donnees["prime_mensuelle"]
                elif periodicite == "trimestrielle":
                    donnees["prime_periodique"] = round(donnees["prime_annuelle"] / 4 * 1.02)
                elif periodicite == "semestrielle":
                    donnees["prime_periodique"] = round(donnees["prime_annuelle"] / 2 * 1.01)
                else:
                    donnees["prime_periodique"] = donnees["prime_annuelle"]
                donnees["periodicite"] = periodicite
                if params.get("avec_exoneration"):
                    donnees["surprime_exoneration"] = round(donnees.get("prime_periodique", 0) * 0.05)
                return json.dumps(donnees, ensure_ascii=False)

            if nom == "souscrire_contrat_vie":
                from core.approval_queue import approval_queue
                # Calcul auto de l'âge depuis date naissance
                if params.get("assure_ddn"):
                    naissance = date.fromisoformat(params["assure_ddn"])
                    age = (date.today() - naissance).days // 365
                else:
                    age = 35  # défaut
                prime_result = calculer_prime_vie(
                    age_souscription=age,
                    duree_annees=params.get("duree_annees", 10),
                    capital_garanti=params["capital_garanti"],
                    type_produit=params["type_produit"],
                )
                prime = params.get("prime_periodique") or prime_result.donnees.get("prime_annuelle", 0)
                await approval_queue.ajouter({
                    "type": "emission_police",
                    "assure": params["assure_nom"],
                    "type_produit": params["type_produit"],
                    "capital_garanti": params["capital_garanti"],
                    "prime_ttc": prime,
                    "beneficiaires": params.get("beneficiaires", []),
                    "montant": prime,
                    "user_id": user_id,
                    "execution_id": execution_id,
                })
                return f"Souscription vie {params['type_produit']} soumise — prime : {prime:,} FCFA/an — en attente validation".replace(",", " ")

            if nom == "evaluer_risque_medical":
                from core.ia_client import ModeIA, ia_client
                prompt = f"""Évalue le risque médical pour une souscription d'assurance vie.

Questionnaire santé :
{json.dumps(params['questionnaire_sante'], ensure_ascii=False, indent=2)}

Âge : {params['age']} ans
Produit : {params.get('type_produit', 'temporaire_deces')}
Capital demandé : {params.get('capital_demande', 0):,} FCFA

Analyse :
1. Pathologies déclarées et impact sur l'espérance de vie
2. Risques aggravés (surprime recommandée en %)
3. Exclusions de garanties recommandées
4. Nécessité d'un examen médical complémentaire
5. Décision : acceptation normale / surprime X% / exclusion partielle / refus"""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                return rep.contenu

            if nom == "calculer_pm":
                from core.orass_connector import orass
                # Méthode prospective simplifiée
                await orass.verifier_validite_contrat(params["police_id"])  # vérification existence contrat
                pm = params["pm_initiale"]
                prime = params.get("prime_annuelle", 0)
                taux = params.get("taux_technique", 0.035)
                duree_ecoulee = params.get("duree_ecoulee", 1)
                # PM(t) = PM(t-1) × (1 + taux) + prime - prestation_risque_annuelle
                for _ in range(duree_ecoulee):
                    pm = pm * (1 + taux) + prime * 0.90  # 10% frais
                return json.dumps({
                    "police_id": params["police_id"],
                    "pm_calculee": round(pm),
                    "duree_ecoulee": duree_ecoulee,
                    "taux_technique": taux,
                    "base_legale": "Art. 63 Code CIMA — Provisions mathématiques",
                }, ensure_ascii=False)

            if nom == "traiter_rachat":
                result = calculer_valeur_rachat_vie(
                    pm_actuelle=params["pm_actuelle"],
                    duree_ecoulee_annees=params["duree_ecoulee_annees"],
                    duree_totale_annees=params["duree_totale_annees"],
                )
                if result.donnees.get("autorise"):
                    montant = result.donnees["valeur_rachat"]
                    if params.get("type_rachat") == "partiel" and params.get("montant_partiel"):
                        montant = min(params["montant_partiel"], result.donnees["valeur_rachat"])
                    from core.approval_queue import approval_queue
                    await approval_queue.ajouter({
                        "type": "rachat_vie",
                        "police_id": params["police_id"],
                        "type_rachat": params.get("type_rachat", "total"),
                        "montant": montant,
                        "pm_actuelle": params["pm_actuelle"],
                        "user_id": user_id,
                        "execution_id": execution_id,
                    })
                    return f"Rachat {params.get('type_rachat', 'total')} soumis : {montant:,} FCFA — Art. 65 CIMA — en attente validation".replace(",", " ")
                return result.message

            if nom == "traiter_avance":
                result = calculer_avance_police_vie(
                    pm_actuelle=params["pm_actuelle"],
                    montant_demande=params.get("montant_demande"),
                )
                if result.donnees.get("autorise"):
                    from core.approval_queue import approval_queue
                    await approval_queue.ajouter({
                        "type": "avance_police_vie",
                        "police_id": params["police_id"],
                        "montant": result.donnees["montant_avance"],
                        "interet_mensuel": result.donnees["interet_mensuel"],
                        "user_id": user_id,
                        "execution_id": execution_id,
                    })
                    return f"Avance {result.donnees['montant_avance']:,} FCFA soumise — intérêts {result.donnees['interet_mensuel']:,} FCFA/mois — Art. 75 CIMA".replace(",", " ")
                return result.message

            if nom == "traiter_reduction":
                # Capital réduit = capital × (PM actuelle / prime unique équivalente initiale)
                pm = params["pm_actuelle"]
                cap = params["capital_initial"]
                prime_unique = params.get("prime_unique_eq", cap * 0.60)  # estimation
                capital_reduit = round(cap * pm / prime_unique) if prime_unique else 0
                return json.dumps({
                    "police_id": params["police_id"],
                    "capital_initial": cap,
                    "capital_reduit": capital_reduit,
                    "reduction_pct": round((1 - capital_reduit / cap) * 100, 1) if cap else 0,
                    "base_legale": "Art. 64 Code CIMA — Valeur de réduction",
                }, ensure_ascii=False)

            if nom == "instruire_sinistre_vie":
                # Vérifier pièces manquantes d'abord
                pieces_requises = _pieces_requises_sinistre_vie(params["type_sinistre"])
                pieces_fournies = set(params.get("pieces_fournies", []))
                pieces_manquantes = [p for p in pieces_requises if p not in pieces_fournies]
                if pieces_manquantes:
                    return json.dumps({
                        "dossier_complet": False,
                        "pieces_manquantes": pieces_manquantes,
                        "message": f"Dossier incomplet — {len(pieces_manquantes)} pièce(s) manquante(s)",
                        "base_legale": "Art. 73 CIMA — délai 30j court à reception pièces COMPLÈTES",
                    }, ensure_ascii=False)

                # Dossier complet → calculer prestation
                result = calculer_indemnite_sinistre_vie(
                    type_sinistre=params["type_sinistre"],
                    capital_contrat=params["capital_contrat"],
                    ipp_pct=params.get("ipp_pct", 0),
                    double_capital_accident=params.get("double_capital_accident", False),
                )
                from core.approval_queue import approval_queue
                await approval_queue.ajouter({
                    "type": "sinistre",
                    "reference": params["police_id"],
                    "decision": "accepte",
                    "montant": result.donnees.get("montant_prestation", 0),
                    "motif": f"Sinistre vie {params['type_sinistre']} — dossier complet",
                    "user_id": user_id,
                    "execution_id": execution_id,
                })
                return json.dumps({
                    "dossier_complet": True,
                    "prestation": result.donnees,
                    "delai_paiement": "30 jours Art. 73 CIMA",
                }, ensure_ascii=False)

            if nom == "gerer_prevoyance_groupe":
                from core.ia_client import ModeIA, ia_client
                action = params["action"]
                if action == "souscrire":
                    masse = params.get("masse_salariale", 0)
                    nb = params.get("nb_salaries", 1)
                    garanties = params.get("garanties", ["deces", "invalidite"])
                    # Taux prévoyance groupe : 1.5 à 3% masse salariale selon garanties
                    taux = 0.015 * len(garanties)
                    prime_annuelle = round(masse * taux)
                    from core.approval_queue import approval_queue
                    await approval_queue.ajouter({
                        "type": "emission_police",
                        "assure": params.get("entreprise_nom", ""),
                        "type_produit": "prevoyance_groupe",
                        "nb_salaries": nb,
                        "garanties": garanties,
                        "montant": prime_annuelle,
                        "user_id": user_id,
                        "execution_id": execution_id,
                    })
                    return f"Prévoyance groupe {params.get('entreprise_nom')} — {nb} salariés — prime : {prime_annuelle:,} FCFA/an soumise".replace(",", " ")
                if action == "sinistre":
                    prompt = f"""Traite ce sinistre prévoyance groupe.
Entreprise : {params.get('entreprise_nom')}
Données sinistre : {json.dumps(params.get('sinistre_data', {}), ensure_ascii=False)}
Garanties actives : {params.get('garanties', [])}
Vérifier : pièces requises, calcul prestation, délais CIMA."""
                    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                    return rep.contenu
                return f"Action prévoyance groupe '{action}' enregistrée"

            if nom == "verifier_pieces_sinistre_vie":
                requises = _pieces_requises_sinistre_vie(params["type_sinistre"])
                fournies = set(params.get("pieces_reçues", []))
                manquantes = [p for p in requises if p not in fournies]
                return json.dumps({
                    "type_sinistre": params["type_sinistre"],
                    "pieces_requises": requises,
                    "pieces_fournies": list(fournies),
                    "pieces_manquantes": manquantes,
                    "dossier_complet": len(manquantes) == 0,
                    "base_legale": "Art. 73 Code CIMA",
                }, ensure_ascii=False)

            if nom == "changer_beneficiaire":
                from core.approval_queue import approval_queue
                ancien = params.get("ancien_beneficiaire", {})
                nouveau = params["nouveau_beneficiaire"]
                police_id = params["police_id"]
                accepte_irrevocable = params.get("beneficiaire_a_accepte", False)
                if accepte_irrevocable:
                    return (
                        f"⚠️ BLOCAGE Art. 74 CIMA — Le bénéficiaire a accepté irrévocablement la désignation.\n"
                        f"Le changement de bénéficiaire n'est plus possible sans son accord écrit.\n"
                        f"Police {police_id} — Bénéficiaire actuel : {ancien.get('nom', 'N/A')}"
                    )
                # Validation obligatoire — modification contrat
                await approval_queue.ajouter({
                    "type": "changement_beneficiaire_vie",
                    "police_id": police_id,
                    "ancien_beneficiaire": ancien,
                    "nouveau_beneficiaire": nouveau,
                    "user_id": user_id,
                    "execution_id": execution_id,
                    "description": f"Changement bénéficiaire police {police_id} — Art. 74 CIMA",
                })
                return (
                    f"Changement bénéficiaire police {police_id} soumis pour validation.\n"
                    f"Ancien : {ancien.get('nom', 'N/A')} → Nouveau : {nouveau.get('nom', 'N/A')}\n"
                    f"Base légale : Art. 74 CIMA — En attente d'approbation."
                )

            if nom == "resilier_contrat_vie":
                motif = params["motif_resiliation"]
                pm = params["pm_actuelle"]
                duree_ec = params.get("duree_ecoulee_annees", 0)
                duree_tot = params.get("duree_totale_annees", 10)
                police_id = params["police_id"]
                # Calcul valeur de rachat si applicable
                from core.approval_queue import approval_queue
                if motif == "demande_assure":
                    rachat = calculer_valeur_rachat_vie(
                        pm_actuelle=pm,
                        duree_ecoulee_annees=duree_ec,
                        duree_totale_annees=duree_tot,
                    )
                    if not rachat.donnees.get("autorise"):
                        return (
                            f"Résiliation impossible — {rachat.message}\n"
                            f"Art. 65 CIMA : rachat autorisé après 2 ans de cotisations seulement."
                        )
                    montant_rachat = rachat.donnees.get("valeur_rachat", 0)
                    await approval_queue.ajouter({
                        "type": "resiliation_vie_rachat",
                        "police_id": police_id,
                        "motif": motif,
                        "montant_rachat": montant_rachat,
                        "pm_actuelle": pm,
                        "user_id": user_id,
                        "execution_id": execution_id,
                    })
                    return f"Résiliation police {police_id} soumise — valeur de rachat : {montant_rachat:,} FCFA — Art. 65 CIMA — en attente validation.".replace(",", " ")
                else:
                    # Résiliation pour non-paiement, fausse déclaration, expiration
                    await approval_queue.ajouter({
                        "type": "resiliation_vie",
                        "police_id": police_id,
                        "motif": motif,
                        "pm_actuelle": pm,
                        "user_id": user_id,
                        "execution_id": execution_id,
                        "description": f"Résiliation police vie {police_id} — motif : {motif}",
                    })
                    return f"Résiliation police {police_id} soumise pour validation — motif : {motif}."

            if nom == "monitoring_portefeuille_vie":
                from core.orass_connector import orass
                data = await orass.get_portefeuille_vie(
                    periode=params.get("periode"),
                    type_produit=params.get("type_produit", "tous"),
                )
                pm_totales = data.get("pm_totales", 0)
                primes_attendues = data.get("primes_attendues_mois", 0)
                primes_encaissees = data.get("primes_encaissees_mois", 0)
                rachats_mois = data.get("rachats_mois", 0)
                nb_polices = data.get("nb_polices_actives", 0)
                taux_collecte = round(primes_encaissees / max(primes_attendues, 1) * 100, 1)
                alertes = []
                if params.get("alertes_seuil"):
                    if taux_collecte < 80:
                        alertes.append(f"Taux collecte faible : {taux_collecte}% (seuil 80%)")
                    if rachats_mois > pm_totales * 0.05:
                        alertes.append(f"Rachats élevés ce mois : {rachats_mois:,} FCFA (> 5% PM totales)".replace(",", " "))
                    polices_impayees = data.get("nb_polices_primes_impayees", 0)
                    if polices_impayees > 0:
                        alertes.append(f"{polices_impayees} police(s) avec primes impayées — risque résiliation automatique")
                return json.dumps({
                    "periode": params.get("periode", "en cours"),
                    "nb_polices_actives": nb_polices,
                    "pm_totales_fcfa": pm_totales,
                    "primes_attendues_mois_fcfa": primes_attendues,
                    "primes_encaissees_mois_fcfa": primes_encaissees,
                    "taux_collecte_pct": taux_collecte,
                    "rachats_mois_fcfa": rachats_mois,
                    "alertes": alertes,
                    "base_legale": "Art. 63 CIMA — provisions mathématiques obligatoires taux min 3.5%",
                }, ensure_ascii=False, default=str)

            return f"Outil '{nom}' non reconnu"
        except Exception as e:
            logger.error(f"[AgentVie] Erreur outil {nom} : {e}")
            return f"ERREUR {nom} : {e}"


def _pieces_requises_sinistre_vie(type_sinistre: str) -> list[str]:
    """Pièces réglementaires requises selon type de sinistre vie (Art. 73 CIMA)."""
    commun = ["police_originale", "formulaire_declaration", "piece_identite_beneficiaire"]
    specifiques = {
        "deces": [
            "certificat_deces",
            "acte_naissance_assure",
            "iml_ou_rapport_medical",  # IML = Information Médico-Légale
            "jugement_heredite_ou_acte_notarie",
        ],
        "invalidite_totale": [
            "certificat_medical_expert",
            "certificat_non_exercice_profession",
            "decision_securite_sociale_invalidite",
        ],
        "invalidite_partielle": [
            "certificat_medical_avec_taux_ipp",
            "rapport_expertise_medicale",
        ],
        "accident": [
            "certificat_medical_initial",
            "pv_police_si_accident_route",
            "rapport_expertise_medicale",
        ],
        "echeance": [
            "demande_ecrite_assure",
            "rib_ou_coordonnees_bancaires",
        ],
    }
    return commun + specifiques.get(type_sinistre, [])
