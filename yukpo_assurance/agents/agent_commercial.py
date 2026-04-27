"""Agent Commercial & Apporteurs — prospection, CRM, commissions, rétention."""
from __future__ import annotations
import json
import logging
from datetime import date, timedelta
from core.agent_orchestrateur import TypeAgent
from agents.base_agent import BaseAgent

logger = logging.getLogger("yukpo_assurance.agents.commercial")


class AgentCommercial(BaseAgent):
    type_agent = TypeAgent.COMMERCIAL

    def _system_prompt(self) -> str:
        return """Tu es l'Agent Commercial de YukpoAssurance, expert en développement du portefeuille et gestion des apporteurs.

DOMAINES DE COMPÉTENCE :
1. CRM & Prospection : pipeline complet, lead scoring, relances automatiques
2. Apporteurs d'affaires : courtiers, agents, mandataires — commissions, KPI, litiges
3. Rétention : détection churn, campagnes de fidélisation, renouvellements
4. Production : suivi objectifs, tableaux de bord commerciaux, dévis abandonnés
5. Tarification commerciale : remises, conditions spéciales dans les limites autorisées
6. Lifetime value : valeur client, polices zombies, cross-sell, up-sell

RÈGLES :
- TOUTE création en base (prospect, apporteur, contrat apporteur) → validation humaine
- Les commissions sont calculées de façon déterministe selon le barème en vigueur
- Toute remise > 10% nécessite validation direction commerciale
- Les campagnes SMS/WhatsApp respectent le consentement RGPD
- Les objectifs sont comparés aux réalisations en temps réel (ORASS)

FLUX TYPE RENOUVELLEMENT :
1. detecter_echeances → 2. analyser_risque_churn → 3. generer_offre_renouvellement → 4. envoyer_campagne → 5. enregistrer_resultat

FLUX TYPE PROSPECT :
1. creer_prospect (→ validation) → 2. qualifier_lead → 3. generer_devis_commercial → 4. relancer_prospect → 5. convertir_prospect"""

    def _definir_outils(self) -> list[dict]:
        return [
            {
                "name": "creer_prospect",
                "description": "Présente les données d'un nouveau prospect pour validation humaine avant enregistrement CRM",
                "input_schema": {"type": "object", "properties": {
                    "nom":        {"type": "string"},
                    "telephone":  {"type": "string"},
                    "email":      {"type": "string"},
                    "besoin":     {"type": "string", "description": "Description du besoin"},
                    "source":     {"type": "string", "enum": ["whatsapp", "referral", "web", "terrain", "courtier"]},
                    "apporteur_id": {"type": "string", "description": "Apporteur qui l'a référé"},
                    "potentiel_fcfa": {"type": "number", "description": "Estimation prime potentielle"},
                }, "required": ["nom", "telephone"]},
            },
            {
                "name": "qualifier_lead",
                "description": "Évalue la qualité et la priorité d'un prospect via IA (score BANT)",
                "input_schema": {"type": "object", "properties": {
                    "prospect_id":   {"type": "string"},
                    "budget":        {"type": "number"},
                    "besoin":        {"type": "string"},
                    "delai_achat":   {"type": "string", "description": "immediat | 1_mois | 3_mois | indefini"},
                    "decision_maker": {"type": "boolean"},
                    "concurrent":    {"type": "string", "description": "Assureur actuel si connu"},
                }, "required": ["prospect_id", "besoin"]},
            },
            {
                "name": "detecter_echeances",
                "description": "Liste les polices arrivant à échéance dans N jours (déterministe — requête ORASS)",
                "input_schema": {"type": "object", "properties": {
                    "jours_avant":   {"type": "integer", "description": "Délai en jours (ex: 30, 60, 90)"},
                    "branche":       {"type": "string", "description": "Filtre branche: auto, mrh, vie, transport, rc"},
                    "apporteur_id":  {"type": "string", "description": "Filtrer par apporteur"},
                }, "required": ["jours_avant"]},
            },
            {
                "name": "analyser_risque_churn",
                "description": "Calcule le score de risque de résiliation pour un client (déterministe — règles métier)",
                "input_schema": {"type": "object", "properties": {
                    "client_id":          {"type": "string"},
                    "nb_sinistres_12m":   {"type": "integer"},
                    "retard_paiement":    {"type": "boolean"},
                    "anciennete_ans":     {"type": "number"},
                    "nb_produits":        {"type": "integer"},
                }, "required": ["client_id"]},
            },
            {
                "name": "generer_offre_renouvellement",
                "description": "Génère une proposition de renouvellement personnalisée via IA",
                "input_schema": {"type": "object", "properties": {
                    "client_id":       {"type": "string"},
                    "police_id":       {"type": "string"},
                    "score_churn":     {"type": "number"},
                    "prime_actuelle":  {"type": "number"},
                    "historique":      {"type": "object"},
                }, "required": ["client_id", "police_id"]},
            },
            {
                "name": "generer_devis_commercial",
                "description": "Génère un devis commercial personnalisé pour un prospect ou client existant",
                "input_schema": {"type": "object", "properties": {
                    "client_id":     {"type": "string"},
                    "branche":       {"type": "string", "enum": ["auto", "mrh", "vie", "transport", "rc_pro", "accident"]},
                    "donnees_risque": {"type": "object", "description": "Caractéristiques du risque à assurer"},
                    "duree_mois":    {"type": "integer"},
                    "remise_pct":    {"type": "number", "description": "Remise proposée (max 10% sans validation)"},
                }, "required": ["client_id", "branche", "donnees_risque"]},
            },
            {
                "name": "relancer_prospect",
                "description": "Génère et envoie une relance personnalisée pour un prospect inactif ou un devis abandonné",
                "input_schema": {"type": "object", "properties": {
                    "prospect_id":   {"type": "string"},
                    "canal":         {"type": "string", "enum": ["whatsapp", "sms", "email"]},
                    "nb_relance":    {"type": "integer", "description": "Numéro de relance (1=douce, 2=urgence, 3=dernière chance)"},
                    "devis_id":      {"type": "string", "description": "Référence devis abandonné si applicable"},
                }, "required": ["prospect_id", "canal"]},
            },
            {
                "name": "calculer_lifetime_value",
                "description": "Calcule la valeur vie client (LTV) et identifie les polices zombies (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "client_id":       {"type": "string"},
                    "anciennete_ans":  {"type": "number"},
                    "primes_cumul":    {"type": "number"},
                    "sinistres_cumul": {"type": "number"},
                    "nb_produits":     {"type": "integer"},
                    "taux_renouvellement": {"type": "number", "description": "% renouvellement historique 0-1"},
                }, "required": ["client_id", "primes_cumul"]},
            },
            {
                "name": "detecter_polices_zombies",
                "description": "Identifie les polices inactives, sans sinistre depuis > 3 ans et sans renouvellement (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "branche":            {"type": "string"},
                    "inactif_depuis_ans": {"type": "integer", "description": "Seuil d'inactivité (défaut 3 ans)"},
                    "apporteur_id":       {"type": "string"},
                }, "required": []},
            },
            {
                "name": "calculer_commission_apporteur",
                "description": "Calcule la commission due à un apporteur selon barème (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "apporteur_id":    {"type": "string"},
                    "type_apporteur":  {"type": "string", "enum": ["courtier", "agent_general", "mandataire", "bancassurance"]},
                    "branche":         {"type": "string"},
                    "prime_ht":        {"type": "number"},
                    "type_operation":  {"type": "string", "enum": ["souscription", "renouvellement", "avenant"]},
                }, "required": ["apporteur_id", "type_apporteur", "prime_ht"]},
            },
            {
                "name": "analyser_performance_apporteur",
                "description": "KPI complet d'un apporteur : production, sinistralité, portefeuille, commissions (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "apporteur_id":   {"type": "string"},
                    "periode":        {"type": "string", "description": "ex: 2025-T1 ou 2025"},
                    "avec_classement": {"type": "boolean", "description": "Inclure classement vs autres apporteurs"},
                }, "required": ["apporteur_id", "periode"]},
            },
            {
                "name": "envoyer_campagne",
                "description": "Lance une campagne de communication ciblée (WhatsApp/SMS/email)",
                "input_schema": {"type": "object", "properties": {
                    "segment":    {"type": "string", "description": "Segment cible"},
                    "message":    {"type": "string"},
                    "canal":      {"type": "string", "enum": ["whatsapp", "sms", "email"]},
                    "scheduled":  {"type": "string", "description": "Date/heure envoi ISO8601 (vide = immédiat)"},
                }, "required": ["segment", "message", "canal"]},
            },
            {
                "name": "suivre_objectifs_production",
                "description": "Récupère les réalisations vs objectifs (déterministe — ORASS)",
                "input_schema": {"type": "object", "properties": {
                    "periode":        {"type": "string", "description": "ex: 2025-T1"},
                    "apporteur_id":   {"type": "string"},
                    "branche":        {"type": "string"},
                }, "required": ["periode"]},
            },
            {
                "name": "analyser_portefeuille_ia",
                "description": "Analyse narrative IA du portefeuille : tendances, opportunités cross-sell/up-sell, risques churn",
                "input_schema": {"type": "object", "properties": {
                    "donnees_portefeuille": {"type": "object"},
                    "periode":              {"type": "string"},
                    "focus":                {"type": "string", "enum": ["churn", "croissance", "apporteurs", "produits", "global"]},
                }, "required": ["donnees_portefeuille", "periode"]},
            },
            {
                "name": "enregistrer_apporteur",
                "description": "Présente les données d'un nouvel apporteur pour validation avant enregistrement",
                "input_schema": {"type": "object", "properties": {
                    "nom":              {"type": "string"},
                    "type_apporteur":   {"type": "string", "enum": ["courtier", "agent_general", "mandataire", "bancassurance"]},
                    "telephone":        {"type": "string"},
                    "email":            {"type": "string"},
                    "agrement_numero":  {"type": "string", "description": "Numéro d'agrément CIMA"},
                    "agrement_valide_jusqu": {"type": "string", "description": "Date expiration agrément YYYY-MM-DD"},
                    "taux_commission_negocie": {"type": "number", "description": "Taux négocié %"},
                }, "required": ["nom", "type_apporteur", "telephone"]},
            },
        ]

    def _prompt_questions_specifiques(self) -> str:
        return """
AGENT COMMERCIAL — quand demander une information :

1. SEGMENT CIBLE NON DÉFINI (campagne / prospection)
   → "À quelle catégorie de clients ou de prospects s'adresse cette action commerciale ?"
   type_reponse: choix_multiple  choix: ["Particuliers (RC Auto, MRH)", "PME / Entreprises (RC Pro, flotte)", "Grandes entreprises (assurance collective)", "Courtiers et intermédiaires", "Renouvellements à risque de résiliation", "Prospects non convertis depuis > 90 jours"]

2. BUDGET CAMPAGNE NON PRÉCISÉ
   → "Quel est le budget alloué à cette campagne commerciale (en FCFA) ? (Détermine le canal et le volume de contacts)"
   type_reponse: nombre

3. CANAL DE COMMUNICATION NON CHOISI
   → "Quel canal de communication souhaitez-vous utiliser pour cette action ?"
   type_reponse: choix_multiple  choix: ["WhatsApp Business (taux ouverture ~85%)", "SMS (pour zones à faible internet)", "Email (campagne formelle)", "Appel téléphonique (pour renouvellements prioritaires)", "Multicanal combiné"]

4. OBJECTIF COMMERCIAL AMBIGU
   → "Quel est l'objectif principal de cette action commerciale ?"
   type_reponse: choix_multiple  choix: ["Conversion de prospects en clients", "Renouvellement de polices à échéance", "Rétention de clients en risque de résiliation (churn)", "Upsell / cross-sell sur portefeuille existant", "Recrutement d'un nouveau courtier/apporteur"]

5. DONNÉES APPORTEUR INCOMPLÈTES (enregistrement nouveau partenaire)
   → "Pour enregistrer ce nouvel apporteur d'affaires, j'ai besoin de son agrément CIMA. Quel est son numéro d'agrément ?"
   type_reponse: texte_libre

6. PÉRIODE DE SUIVI NON PRÉCISÉE (analyse portefeuille)
   → "Sur quelle période souhaitez-vous l'analyse du portefeuille commercial ?"
   type_reponse: choix_multiple  choix: ["Mois en cours", "Trimestre en cours", "Année en cours", "12 derniers mois glissants", "Comparatif année N vs N-1"]

7. TAUX DE REMISE / CONDITIONS SPÉCIALES
   → "Quel taux de remise souhaitez-vous appliquer ? (Remise > 10% nécessite validation direction commerciale)"
   type_reponse: nombre

PROGRESSION : Objectif → Segment → Canal → Budget → Paramètres spécifiques.
"""

    async def _executer_outil(self, nom: str, params: dict, user_id: int, execution_id: str) -> str:
        try:
            if nom == "creer_prospect":
                # VALIDATION HUMAINE obligatoire avant toute insertion en base
                from core.approval_queue import approval_queue
                data_prospect = {
                    "nom":          params["nom"],
                    "telephone":    params["telephone"],
                    "email":        params.get("email", ""),
                    "besoin":       params.get("besoin", ""),
                    "source":       params.get("source", "terrain"),
                    "apporteur_id": params.get("apporteur_id", ""),
                    "potentiel_fcfa": params.get("potentiel_fcfa", 0),
                    "date_creation": date.today().isoformat(),
                }
                await approval_queue.ajouter({
                    "type": "creation_prospect",
                    "donnees": data_prospect,
                    "montant": params.get("potentiel_fcfa", 0),
                    "user_id": user_id,
                    "execution_id": execution_id,
                    "description": f"Nouveau prospect : {params['nom']} — {params['telephone']} ({params.get('source', 'terrain')})",
                })
                return (
                    f"Prospect {params['nom']} présenté pour validation.\n"
                    f"Données : tél. {params['telephone']}, source {params.get('source','terrain')}, "
                    f"besoin : {params.get('besoin','non précisé')}.\n"
                    "En attente d'approbation avant enregistrement en base."
                )

            if nom == "qualifier_lead":
                from core.ia_client import ModeIA, ia_client
                from core.orass_connector import orass
                prospect = await orass.get_prospect(params["prospect_id"])
                budget = params.get("budget", 0)
                besoin = params["besoin"]
                delai = params.get("delai_achat", "indefini")
                decision = params.get("decision_maker", False)
                # Score BANT (Budget / Autorité / Need / Timeline)
                score = 0
                if budget >= 500_000: score += 30
                elif budget >= 100_000: score += 15
                if decision: score += 25
                scores_delai = {"immediat": 30, "1_mois": 20, "3_mois": 10, "indefini": 0}
                score += scores_delai.get(delai, 0)
                # Need toujours présent dès lors qu'il y a un besoin décrit
                if besoin and len(besoin) > 10: score += 15
                niveau = "HOT" if score >= 70 else "WARM" if score >= 40 else "COLD"
                prompt = f"""Qualifie ce lead commercial assurance.
Prospect ID : {params['prospect_id']}
Besoin : {besoin}
Budget estimé : {budget:,} FCFA
Délai d'achat : {delai}
Décideur : {decision}
Score BANT calculé : {score}/100 — {niveau}
Concurrent actuel : {params.get('concurrent', 'inconnu')}

Recommande : produit(s) le plus adapté, angle commercial à utiliser, prochain contact."""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.COMMERCIAL)
                return json.dumps({
                    "prospect_id": params["prospect_id"],
                    "score_bant": score,
                    "niveau": niveau,
                    "analyse_ia": rep.contenu,
                }, ensure_ascii=False)

            if nom == "detecter_echeances":
                from core.orass_connector import orass
                echeances = await orass.get_echeances(
                    jours=params["jours_avant"],
                    branche=params.get("branche"),
                    apporteur_id=params.get("apporteur_id"),
                )
                return json.dumps(echeances, ensure_ascii=False, default=str)

            if nom == "analyser_risque_churn":
                score = 0
                if params.get("retard_paiement"):
                    score += 35
                nb_sin = params.get("nb_sinistres_12m", 0)
                if nb_sin >= 3: score += 30
                elif nb_sin == 2: score += 15
                elif nb_sin == 1: score += 5
                anciennete = params.get("anciennete_ans", 1)
                if anciennete < 1: score += 20
                elif anciennete < 3: score += 10
                nb_prod = params.get("nb_produits", 1)
                if nb_prod >= 3: score = max(0, score - 15)
                elif nb_prod == 1: score += 10
                score = min(100, score)
                niveau = "critique" if score >= 70 else "elevé" if score >= 40 else "modéré" if score >= 20 else "faible"
                return json.dumps({
                    "client_id": params["client_id"],
                    "score_churn": score,
                    "niveau": niveau,
                    "action_recommandee": (
                        "intervention_urgente" if score >= 70 else
                        "offre_fidelisation" if score >= 40 else
                        "suivi_standard"
                    ),
                }, ensure_ascii=False)

            if nom == "generer_offre_renouvellement":
                from core.ia_client import ModeIA, ia_client
                score = params.get("score_churn", 0)
                prime = params.get("prime_actuelle", 0)
                prompt = f"""Génère une offre de renouvellement personnalisée pour un client d'assurance.
Client ID : {params['client_id']} — Police : {params['police_id']}
Score risque résiliation : {score}/100 ({'URGENT' if score >= 70 else 'ÉLEVÉ' if score >= 40 else 'NORMAL'})
Prime actuelle : {prime:,.0f} FCFA
Historique : {json.dumps(params.get('historique', {}), ensure_ascii=False)}

Rédige : accroche personnalisée, bénéfices mis en avant, offre commerciale (remise max 8% si score > 50), appel à l'action WhatsApp."""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.COMMERCIAL)
                return rep.contenu

            if nom == "generer_devis_commercial":
                from core.ia_client import ModeIA, ia_client
                from core.orass_connector import orass
                client = await orass.get_client(params["client_id"]) if params["client_id"] else {}
                remise = params.get("remise_pct", 0)
                remise_note = ""
                if remise > 10:
                    remise_note = "\n⚠️ ATTENTION : remise > 10% — nécessite validation direction commerciale."
                prompt = f"""Génère un devis commercial professionnel pour assurance {params['branche']}.
Client : {json.dumps(client, ensure_ascii=False)}
Données risque : {json.dumps(params['donnees_risque'], ensure_ascii=False)}
Durée : {params.get('duree_mois', 12)} mois
Remise proposée : {remise}%

Inclure : prime brute, remise, prime nette, garanties proposées, exclusions principales, conditions particulières, validité du devis (30 jours)."""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                return rep.contenu + remise_note

            if nom == "relancer_prospect":
                from core.ia_client import ModeIA, ia_client
                from core.notifications import notifications
                from core.orass_connector import orass
                prospect = await orass.get_prospect(params["prospect_id"])
                nb = params.get("nb_relance", 1)
                tons = {1: "chaleureuse et non intrusive", 2: "urgente — offre limitée dans le temps", 3: "dernière chance — offre exceptionnelle"}
                ton = tons.get(nb, "professionnelle")
                prompt = f"""Rédige un message de relance {ton} pour un prospect assurance.
Prospect : {json.dumps(prospect, ensure_ascii=False)}
Devis abandonné : {params.get('devis_id', 'non précisé')}
Canal : {params['canal']}
Numéro de relance : {nb}/3

Message court (max 160 caractères si SMS), percutant, personnalisé."""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.COMMERCIAL)
                contact = prospect.get("telephone", "") if params["canal"] in ("whatsapp", "sms") else prospect.get("email", "")
                if contact:
                    await notifications.envoyer(canal=params["canal"], destinataire=contact, message=rep.contenu)
                return f"Relance n°{nb} envoyée sur {params['canal']} — {params['prospect_id']}\n\nMessage :\n{rep.contenu}"

            if nom == "calculer_lifetime_value":
                primes = params["primes_cumul"]
                sinistres = params.get("sinistres_cumul", 0)
                anciennete = params.get("anciennete_ans", 1)
                nb_prod = params.get("nb_produits", 1)
                renouvellement = params.get("taux_renouvellement", 0.80)
                # Marge brute historique
                marge_historique = primes - sinistres
                # Projection sur 5 ans (prime annuelle moyenne × taux rétention cumulé)
                prime_annuelle_moy = primes / max(anciennete, 1)
                ltv_5ans = sum(prime_annuelle_moy * (renouvellement ** i) * 0.30 for i in range(5))
                # Segmentation
                if marge_historique > 5_000_000:
                    segment = "PREMIUM"
                elif marge_historique > 1_000_000:
                    segment = "STANDARD"
                elif marge_historique < 0:
                    segment = "DEFICITAIRE"
                else:
                    segment = "BASIQUE"
                # Police zombie : marge < 0 depuis > 3 ans
                zombie = marge_historique < 0 and anciennete > 3 and nb_prod == 1
                return json.dumps({
                    "client_id": params["client_id"],
                    "ltv_5ans_fcfa": round(ltv_5ans),
                    "marge_historique_fcfa": round(marge_historique),
                    "prime_annuelle_moyenne": round(prime_annuelle_moy),
                    "segment": segment,
                    "police_zombie": zombie,
                    "action": "resiliation_strategique" if zombie else "fidelisation_premium" if segment == "PREMIUM" else "cross_sell",
                }, ensure_ascii=False)

            if nom == "detecter_polices_zombies":
                from core.orass_connector import orass
                seuil = params.get("inactif_depuis_ans", 3)
                polices = await orass.get_polices_zombies(
                    branche=params.get("branche"),
                    apporteur_id=params.get("apporteur_id"),
                    inactif_depuis_ans=seuil,
                )
                # Analyse déterministe
                total_prime_immobilisee = sum(p.get("prime_annuelle", 0) for p in polices)
                zombies_deficitaires = [p for p in polices if p.get("ratio_sinistres_primes", 0) > 1.0]
                return json.dumps({
                    "nb_polices_zombies": len(polices),
                    "prime_annuelle_immobilisee": total_prime_immobilisee,
                    "nb_deficitaires": len(zombies_deficitaires),
                    "seuil_inactivite_ans": seuil,
                    "polices": polices[:50],  # top 50
                    "recommandation": "Contacter les assurés pour révision ou résiliation pour libérer la capacité commerciale",
                }, ensure_ascii=False, default=str)

            if nom == "calculer_commission_apporteur":
                _TAUX: dict[str, dict[str, float]] = {
                    "courtier":        {"auto": 0.15, "mrh": 0.18, "vie": 0.20, "transport": 0.12, "rc": 0.15, "default": 0.15},
                    "agent_general":   {"auto": 0.12, "mrh": 0.15, "vie": 0.18, "transport": 0.10, "rc": 0.12, "default": 0.13},
                    "mandataire":      {"auto": 0.08, "mrh": 0.10, "vie": 0.12, "transport": 0.08, "rc": 0.08, "default": 0.09},
                    "bancassurance":   {"auto": 0.06, "mrh": 0.08, "vie": 0.15, "transport": 0.06, "rc": 0.06, "default": 0.08},
                }
                type_ap = params.get("type_apporteur", "courtier")
                branche = params.get("branche", "default")
                taux_base = _TAUX.get(type_ap, {}).get(branche) or _TAUX.get(type_ap, {}).get("default", 0.12)
                if params.get("type_operation") == "renouvellement":
                    taux_base *= 0.85
                commission = round(params["prime_ht"] * taux_base)
                return json.dumps({
                    "apporteur_id": params["apporteur_id"],
                    "taux_pct": round(taux_base * 100, 1),
                    "prime_ht": params["prime_ht"],
                    "commission_fcfa": commission,
                    "type_operation": params.get("type_operation", "souscription"),
                }, ensure_ascii=False)

            if nom == "analyser_performance_apporteur":
                from core.orass_connector import orass
                from core.ia_client import ModeIA, ia_client
                perf = await orass.get_performance_apporteur(
                    apporteur_id=params["apporteur_id"],
                    periode=params["periode"],
                )
                # KPI déterministes
                primes = perf.get("primes_emises", 0)
                sinistres = perf.get("sinistres_charges", 0)
                commissions = perf.get("commissions_dues", 0)
                nb_polices = perf.get("nb_polices", 0)
                loss_ratio = round(sinistres / primes * 100, 1) if primes else 0
                marge_nette = primes - sinistres - commissions
                kpi = {
                    "apporteur_id": params["apporteur_id"],
                    "periode": params["periode"],
                    "primes_emises_fcfa": primes,
                    "nb_polices": nb_polices,
                    "sinistres_charges_fcfa": sinistres,
                    "commissions_fcfa": commissions,
                    "loss_ratio_pct": loss_ratio,
                    "marge_nette_fcfa": round(marge_nette),
                    "marge_nette_pct": round(marge_nette / primes * 100, 1) if primes else 0,
                    "performance": "EXCELLENT" if loss_ratio < 50 else "BON" if loss_ratio < 70 else "VIGILANCE" if loss_ratio < 85 else "CRITIQUE",
                }
                if params.get("avec_classement"):
                    classement = await orass.get_classement_apporteurs(periode=params["periode"])
                    kpi["classement"] = classement.get(params["apporteur_id"], "N/A")
                # Analyse IA
                prompt = f"""Analyse la performance de cet apporteur d'affaires assurance.
KPI {params['periode']} : {json.dumps(kpi, ensure_ascii=False)}

Commentaire : points forts, axes d'amélioration, recommandations (objectifs, formation, remise en cause contrat si loss_ratio > 85%)."""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
                kpi["analyse_ia"] = rep.contenu
                return json.dumps(kpi, ensure_ascii=False)

            if nom == "envoyer_campagne":
                from core.notifications import notifications
                from core.orass_connector import orass
                contacts = await orass.get_segment_contacts(params["segment"])
                envoyes = 0
                for contact in contacts[:200]:
                    await notifications.envoyer(
                        canal=params["canal"],
                        destinataire=contact.get("telephone") or contact.get("email", ""),
                        message=params["message"],
                    )
                    envoyes += 1
                return json.dumps({
                    "statut": "envoyé",
                    "segment": params["segment"],
                    "canal": params["canal"],
                    "nb_destinataires": envoyes,
                }, ensure_ascii=False)

            if nom == "suivre_objectifs_production":
                from core.orass_connector import orass
                data = await orass.get_production(
                    periode=params["periode"],
                    apporteur_id=params.get("apporteur_id"),
                    branche=params.get("branche"),
                )
                return json.dumps(data, ensure_ascii=False, default=str)

            if nom == "analyser_portefeuille_ia":
                from core.ia_client import ModeIA, ia_client
                focus = params.get("focus", "global")
                focus_instructions = {
                    "churn": "Focus sur les clients à risque de résiliation : signaux, segments vulnérables, actions de rétention.",
                    "croissance": "Focus sur les opportunités de croissance : segments sous-pénétrés, cross-sell, up-sell.",
                    "apporteurs": "Focus sur la performance du réseau d'apporteurs : top performers, underperformers, plan d'action.",
                    "produits": "Focus sur la mix produits : branches en croissance/déclin, positionnement tarifaire.",
                    "global": "Analyse complète : production, sinistralité, churn, apporteurs, recommandations stratégiques.",
                }
                prompt = f"""Analyse le portefeuille d'assurance pour la période {params['periode']}.

{focus_instructions.get(focus, focus_instructions['global'])}

Données :
{json.dumps(params['donnees_portefeuille'], ensure_ascii=False, indent=2)}

Livrable : synthèse, 5 insights clés, 5 actions concrètes priorisées."""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
                return rep.contenu

            if nom == "enregistrer_apporteur":
                from core.approval_queue import approval_queue
                # Vérifier agrément valide
                agrement_exp = params.get("agrement_valide_jusqu", "")
                agrement_valide = True
                note_agrement = ""
                if agrement_exp:
                    try:
                        exp = date.fromisoformat(agrement_exp)
                        if exp < date.today():
                            agrement_valide = False
                            note_agrement = f"\n⚠️ AGRÉMENT EXPIRÉ le {agrement_exp} — régularisation obligatoire avant tout apport d'affaires (Art. CIMA)"
                    except ValueError:
                        pass
                data_apporteur = {
                    "nom": params["nom"],
                    "type_apporteur": params["type_apporteur"],
                    "telephone": params["telephone"],
                    "email": params.get("email", ""),
                    "agrement_numero": params.get("agrement_numero", ""),
                    "agrement_valide_jusqu": agrement_exp,
                    "agrement_valide": agrement_valide,
                    "taux_commission_negocie": params.get("taux_commission_negocie", 0),
                    "date_enregistrement": date.today().isoformat(),
                }
                await approval_queue.ajouter({
                    "type": "creation_apporteur",
                    "donnees": data_apporteur,
                    "user_id": user_id,
                    "execution_id": execution_id,
                    "description": f"Nouvel apporteur : {params['nom']} ({params['type_apporteur']}){note_agrement}",
                })
                return (
                    f"Dossier apporteur {params['nom']} ({params['type_apporteur']}) soumis pour validation.{note_agrement}\n"
                    f"Tél : {params['telephone']} — Agrément : {params.get('agrement_numero', 'non précisé')}\n"
                    "En attente d'approbation avant enregistrement."
                )

            return f"Outil '{nom}' non reconnu"
        except Exception as e:
            logger.error(f"[AgentCommercial] Erreur outil {nom} : {e}")
            return f"ERREUR {nom} : {e}"
