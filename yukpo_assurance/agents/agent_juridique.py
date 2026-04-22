"""Agent Juridique & Contentieux — recours, contentieux, rédaction actes, veille CIMA."""
from __future__ import annotations
import json
import logging
from datetime import date, timedelta
from core.agent_orchestrateur import TypeAgent
from agents.base_agent import BaseAgent

logger = logging.getLogger("yukpo_assurance.agents.juridique")

# Délais prescription en matière d'assurance (Art. CIMA + droit commun OHADA)
_DELAIS_PRESCRIPTION = {
    "action_assure_contre_assureur":    730,   # 2 ans Art. 32 CIMA
    "recours_contre_tiers":             1095,  # 3 ans droit commun
    "subrogation":                      1095,  # 3 ans OHADA
    "recours_confrere":                 365,   # 1 an convention CIMA
    "contentieux_travail":              1095,  # 3 ans Code travail
    "contentieux_commercial":           1825,  # 5 ans OHADA
    "amende_regulatoire":               365,   # 1 an
}


class AgentJuridique(BaseAgent):
    type_agent = TypeAgent.JURIDIQUE

    def _system_prompt(self) -> str:
        return """Tu es l'Agent Juridique de YukpoAssurance, expert en droit des assurances CIMA et droit OHADA.

DOMAINES DE COMPÉTENCE :
1. Contentieux & recours : suivi dossiers, calcul prescriptions, assignations
2. Subrogation : recours contre responsables tiers après indemnisation
3. Rédaction actes : mises en demeure, transactions, accords
4. Veille réglementaire : circulaires CIMA, lois nationales, jurisprudence
5. Contrats : analyse clauses, avenants, conditions particulières
6. Litiges clients : contestations de règlement, réclamations, médiation
7. Expertise judiciaire : désignation d'experts, contradictoire, rapport
8. Amendes réglementaires : gestion sanctions CRCA, plans de régularisation
9. Archivage légal : durées de conservation, destruction documentaire

RÈGLES STRICTES :
- Les délais de prescription sont calculés DÉTERMINISTIQUEMENT (0 IA)
- Toute mise en demeure > 5M FCFA nécessite validation DG
- Les transactions sont soumises à validation juridique humaine
- Toute subrogation enregistrée en base → validation avant insertion
- Citer TOUJOURS l'article de loi applicable

FONDEMENTS LÉGAUX :
- Code CIMA : Art. 1-399 (assurances)
- Acte Uniforme OHADA sur le droit commercial
- Code civil applicable dans l'espace OHADA
- Code du travail (droit national)"""

    def _definir_outils(self) -> list[dict]:
        return [
            {
                "name": "analyser_dossier_contentieux",
                "description": "Analyse un dossier contentieux : prescription, chances de succès, stratégie",
                "input_schema": {"type": "object", "properties": {
                    "reference":      {"type": "string"},
                    "type_litige":    {"type": "string", "enum": ["recours_tiers", "subrogation", "assure", "travail", "commercial", "cima"]},
                    "date_fait":      {"type": "string", "description": "YYYY-MM-DD"},
                    "montant_litige": {"type": "number"},
                    "description":    {"type": "string"},
                }, "required": ["reference", "type_litige", "date_fait"]},
            },
            {
                "name": "verifier_prescription",
                "description": "Vérifie si un droit est prescrit (déterministe — délais légaux CIMA/OHADA)",
                "input_schema": {"type": "object", "properties": {
                    "type_action":                  {"type": "string"},
                    "date_fait_generateur":         {"type": "string", "description": "YYYY-MM-DD"},
                    "date_derniere_interruption":   {"type": "string", "description": "YYYY-MM-DD (optionnel)"},
                }, "required": ["type_action", "date_fait_generateur"]},
            },
            {
                "name": "rediger_acte_juridique",
                "description": "Rédige un acte juridique via IA (mise en demeure, transaction, recours, assignation)",
                "input_schema": {"type": "object", "properties": {
                    "type_acte":   {"type": "string", "enum": ["mise_en_demeure", "transaction", "recours_amiable", "assignation", "avenant_contrat", "clause_speciale", "protocole_accord"]},
                    "contexte":    {"type": "string"},
                    "parties":     {"type": "object"},
                    "montant":     {"type": "number"},
                    "delai_jours": {"type": "integer", "description": "Délai accordé (mise en demeure)"},
                }, "required": ["type_acte", "contexte"]},
            },
            {
                "name": "suivre_contentieux",
                "description": "Tableau de bord des dossiers contentieux actifs",
                "input_schema": {"type": "object", "properties": {
                    "statut":      {"type": "string", "enum": ["actif", "clos", "transaction", "tous"]},
                    "type_litige": {"type": "string"},
                    "urgence":     {"type": "boolean", "description": "Filtrer dossiers urgents (prescription < 60j)"},
                }, "required": []},
            },
            {
                "name": "enregistrer_subrogation",
                "description": "Présente un recours subrogatoire pour validation avant enregistrement en base",
                "input_schema": {"type": "object", "properties": {
                    "sinistre_id":          {"type": "string"},
                    "responsable_nom":      {"type": "string"},
                    "responsable_assureur": {"type": "string"},
                    "montant_indemnise":    {"type": "number"},
                    "date_paiement":        {"type": "string"},
                }, "required": ["sinistre_id", "montant_indemnise", "date_paiement"]},
            },
            {
                "name": "veille_reglementaire",
                "description": "Récupère les dernières circulaires CIMA et textes réglementaires",
                "input_schema": {"type": "object", "properties": {
                    "domaine": {"type": "string", "enum": ["cima", "ohada", "fiscal", "travail", "tous"]},
                    "depuis":  {"type": "string", "description": "Date ISO8601"},
                }, "required": ["domaine"]},
            },
            {
                "name": "valider_transaction",
                "description": "Soumet une transaction amiable pour validation humaine",
                "input_schema": {"type": "object", "properties": {
                    "reference":       {"type": "string"},
                    "montant_offert":  {"type": "number"},
                    "montant_reclame": {"type": "number"},
                    "conditions":      {"type": "string"},
                }, "required": ["reference", "montant_offert"]},
            },
            {
                "name": "traiter_litige_client",
                "description": "Instruit un litige ou réclamation client : analyse, réponse, médiation ou contentieux",
                "input_schema": {"type": "object", "properties": {
                    "client_id":        {"type": "string"},
                    "police_id":        {"type": "string"},
                    "objet_reclamation": {"type": "string"},
                    "montant_reclame":  {"type": "number"},
                    "pieces_jointes":   {"type": "array", "items": {"type": "string"}},
                    "action":           {"type": "string", "enum": ["analyser", "repondre", "proposer_mediation", "escalader_contentieux"]},
                }, "required": ["objet_reclamation", "action"]},
            },
            {
                "name": "gerer_expertise_judiciaire",
                "description": "Gère une expertise judiciaire : désignation contradictoire, suivi, rapport",
                "input_schema": {"type": "object", "properties": {
                    "sinistre_id":    {"type": "string"},
                    "type_expertise": {"type": "string", "enum": ["automobile", "batiment", "medicale", "judiciaire_neutre"]},
                    "expert_nom":     {"type": "string"},
                    "action":         {"type": "string", "enum": ["designer", "rapport_contradictoire", "contester_rapport", "accepter_rapport"]},
                    "rapport_data":   {"type": "object"},
                }, "required": ["sinistre_id", "action"]},
            },
            {
                "name": "gerer_amende_regulatoire",
                "description": "Traite une sanction/amende de la CRCA : analyse, contestation ou paiement",
                "input_schema": {"type": "object", "properties": {
                    "reference_amende": {"type": "string"},
                    "montant_amende":   {"type": "number"},
                    "motif":            {"type": "string"},
                    "date_notification": {"type": "string"},
                    "action":           {"type": "string", "enum": ["analyser", "contester", "accepter_payer", "plan_regularisation"]},
                }, "required": ["reference_amende", "montant_amende", "motif", "action"]},
            },
            {
                "name": "archiver_documents_legaux",
                "description": "Présente une demande d'archivage ou destruction de documents légaux pour validation",
                "input_schema": {"type": "object", "properties": {
                    "type_document":   {"type": "string", "enum": ["contrat", "sinistre", "contentieux", "correspondance_crca", "rh", "comptable"]},
                    "action":          {"type": "string", "enum": ["archiver", "detruire", "verifier_duree"]},
                    "reference":       {"type": "string"},
                    "date_document":   {"type": "string"},
                    "duree_conservation_ans": {"type": "integer"},
                }, "required": ["type_document", "action", "reference"]},
            },
        ]

    def _prompt_questions_specifiques(self) -> str:
        return """
AGENT JURIDIQUE — quand demander une information :

1. RÉFÉRENCE DU DOSSIER CONTENTIEUX MANQUANTE
   → "Quel est le numéro ou la référence du dossier contentieux à traiter ? (Ex: CONT-2025-012 ou numéro de sinistre associé)"
   type_reponse: texte_libre

2. PARTIE ADVERSE NON IDENTIFIÉE
   → "Qui est la partie adverse dans ce litige ? (Nom, société, ou qualité : assuré / tiers / prestataire / administration)"
   type_reponse: texte_libre

3. NATURE DU LITIGE NON PRÉCISÉE
   → "Quelle est la nature du litige ou du contentieux ?"
   type_reponse: choix_multiple  choix: ["Contestation d'indemnisation sinistre", "Recours subrogatoire contre un tiers responsable", "Litige avec un courtier / intermédiaire", "Recouvrement de prime impayée", "Contentieux avec un prestataire (expert, réparateur)", "Contestation réglementaire (CRCA, DGSN)", "Litige RH / prud'hommes"]

4. MONTANT EN JEU NON QUANTIFIÉ
   → "Quel est le montant contesté ou en jeu dans ce litige (en FCFA) ? (Détermine si validation DG est requise pour les montants > 5M FCFA)"
   type_reponse: nombre

5. DÉLAI DE PRESCRIPTION — DATE DE L'ÉVÉNEMENT MANQUANTE
   → "Quelle est la date de l'événement déclencheur du litige ? (Sinistre, décision, contrat, etc. — nécessaire pour calculer la prescription Art. 32 CIMA : 2 ans)"
   type_reponse: date

6. TYPE D'ACTE À RÉDIGER
   → "Quel type d'acte juridique souhaitez-vous que je rédige ?"
   type_reponse: choix_multiple  choix: ["Mise en demeure (avant action judiciaire)", "Proposition de transaction amiable", "Accord transactionnel et quittance", "Rapport d'expertise contradictoire", "Notification de résiliation pour fausse déclaration", "Archivage légal — bordereau de destruction"]

7. PIÈCES DISPONIBLES (pour l'instruction)
   → "Quelles pièces justificatives avez-vous déjà en votre possession pour ce dossier ?"
   type_reponse: choix_multiple  choix: ["Contrat / police d'assurance", "Rapport d'expertise", "Correspondances avec la partie adverse", "Décision judiciaire antérieure", "Photos / éléments de preuve", "Aucune pièce — dossier à constituer"]

8. DOCUMENTS LÉGAUX À ANALYSER (assignation, jugement, contrat litigieux)
   → "Veuillez scanner et transmettre les documents légaux du dossier (assignation, jugement, contrat contesté). Je les analyserai pour identifier les arguments et délais applicables."
   type_reponse: images  nombre_images_max: 5  formats_acceptes: ["pdf", "jpg", "png"]

9. PIÈCES DE PREUVE À NUMÉRISER (photos, correspondances, expertises)
   → "Avez-vous des pièces de preuve physiques à joindre au dossier (photos des dommages, courriers recommandés, rapport d'expert indépendant) ? Envoyez-les pour constitution du dossier juridique complet."
   type_reponse: images  nombre_images_max: 8  formats_acceptes: ["jpg", "png", "pdf"]

PROGRESSION : Identification dossier → Nature litige → Documents légaux (scan) → Montant → Délais légaux → Acte à produire.
"""

    async def _executer_outil(self, nom: str, params: dict, user_id: int, execution_id: str) -> str:
        try:
            if nom == "analyser_dossier_contentieux":
                from core.ia_client import ModeIA, ia_client
                type_litige = params["type_litige"]
                _map = {
                    "recours_tiers": "recours_contre_tiers",
                    "subrogation": "subrogation",
                    "assure": "action_assure_contre_assureur",
                    "travail": "contentieux_travail",
                    "commercial": "contentieux_commercial",
                    "cima": "action_assure_contre_assureur",
                }
                cle = _map.get(type_litige, "recours_contre_tiers")
                delai = _DELAIS_PRESCRIPTION.get(cle, 1095)
                date_fait = date.fromisoformat(params["date_fait"])
                date_prescription = date_fait + timedelta(days=delai)
                jours_restants = (date_prescription - date.today()).days
                prescrit = jours_restants <= 0
                urgence = 0 < jours_restants <= 60

                prompt = f"""Analyse ce dossier contentieux d'assurance.
Référence : {params['reference']}
Type : {type_litige}
Date des faits : {params['date_fait']}
Montant : {params.get('montant_litige', 0):,} FCFA
Description : {params.get('description', 'Non fournie')}

DONNÉES PRESCRIPTION (déterministe) :
- Date prescription : {date_prescription.isoformat()} ({jours_restants} jours restants)
- Prescrit : {'OUI — ACTION URGENTE' if prescrit else 'NON'}
- Urgence : {'OUI — < 60 JOURS' if urgence else 'Non'}

Analyse : fondement juridique, probabilité de succès, stratégie recommandée, articles CIMA/OHADA applicables."""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                return json.dumps({
                    "reference": params["reference"],
                    "prescription": {
                        "date": date_prescription.isoformat(),
                        "jours_restants": jours_restants,
                        "prescrit": prescrit,
                        "urgence": urgence,
                    },
                    "analyse_ia": rep.contenu,
                }, ensure_ascii=False)

            if nom == "verifier_prescription":
                type_action = params["type_action"]
                delai = _DELAIS_PRESCRIPTION.get(type_action, 1095)
                date_fait = date.fromisoformat(params["date_fait_generateur"])
                date_ref = date_fait
                if params.get("date_derniere_interruption"):
                    date_ref = date.fromisoformat(params["date_derniere_interruption"])
                date_prescription = date_ref + timedelta(days=delai)
                jours_restants = (date_prescription - date.today()).days
                return json.dumps({
                    "type_action": type_action,
                    "delai_legal_jours": delai,
                    "date_fait_generateur": params["date_fait_generateur"],
                    "date_prescription": date_prescription.isoformat(),
                    "jours_restants": jours_restants,
                    "prescrit": jours_restants <= 0,
                    "urgence_60j": 0 < jours_restants <= 60,
                    "fondement": f"Art. CIMA / OHADA — délai {delai} jours",
                }, ensure_ascii=False)

            if nom == "rediger_acte_juridique":
                from core.ia_client import ModeIA, ia_client
                type_acte = params["type_acte"]
                parties = params.get("parties", {})
                montant = params.get("montant", 0)
                delai = params.get("delai_jours", 15)

                prompts_acte = {
                    "mise_en_demeure": f"""Rédige une mise en demeure formelle conforme au droit OHADA.
Contexte : {params['contexte']}
Parties : {json.dumps(parties, ensure_ascii=False)}
Montant réclamé : {montant:,} FCFA
Délai accordé : {delai} jours

Format : en-tête officiel, exposé des faits, fondement juridique (Art. précis), montant, délai, menace de procédure judiciaire, signature.""",
                    "transaction": f"""Rédige un protocole transactionnel d'assurance conforme au droit OHADA.
Contexte : {params['contexte']}
Parties : {json.dumps(parties, ensure_ascii=False)}
Montant de la transaction : {montant:,} FCFA

Format : préambule, rappel des faits, conditions de la transaction, quittance pour solde de tout compte, clauses résolutoires.""",
                    "assignation": f"""Rédige une assignation en justice conforme au droit OHADA.
Contexte : {params['contexte']}
Parties : {json.dumps(parties, ensure_ascii=False)}
Montant : {montant:,} FCFA

Format : tribunal compétent, identité des parties, exposé des faits, demandes, pièces jointes.""",
                }

                prompt = prompts_acte.get(type_acte, f"""Rédige un {type_acte} juridique.
Contexte : {params['contexte']}
Parties : {json.dumps(parties, ensure_ascii=False)}
Montant : {montant:,} FCFA""")

                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                # Mise en demeure > 5M FCFA → validation DG
                if type_acte == "mise_en_demeure" and montant > 5_000_000:
                    from core.approval_queue import approval_queue
                    await approval_queue.ajouter({
                        "type": "mise_en_demeure_importante",
                        "montant": montant,
                        "contexte": params["contexte"][:200],
                        "user_id": user_id,
                        "execution_id": execution_id,
                        "description": f"MDE > 5M FCFA — {montant:,} FCFA — validation DG requise".replace(",", " "),
                    })
                    return rep.contenu + "\n\n⚠️ Montant > 5 000 000 FCFA — soumis pour validation DG avant envoi."
                return rep.contenu

            if nom == "suivre_contentieux":
                from core.orass_connector import orass
                dossiers = await orass.get_contentieux(
                    statut=params.get("statut", "actif"),
                    type_litige=params.get("type_litige"),
                )
                if params.get("urgence"):
                    urgents = []
                    for d in dossiers:
                        date_presc = d.get("date_prescription")
                        if date_presc:
                            jours = (date.fromisoformat(date_presc) - date.today()).days
                            if 0 < jours <= 60:
                                d["jours_avant_prescription"] = jours
                                urgents.append(d)
                    return json.dumps({"urgents": urgents, "total": len(urgents)}, ensure_ascii=False, default=str)
                return json.dumps({"dossiers": dossiers, "total": len(dossiers)}, ensure_ascii=False, default=str)

            if nom == "enregistrer_subrogation":
                # VALIDATION HUMAINE avant insertion en base
                from core.approval_queue import approval_queue
                date_paie = date.fromisoformat(params["date_paiement"])
                date_presc = date_paie + timedelta(days=1095)  # 3 ans OHADA
                jours_restants = (date_presc - date.today()).days
                data_subrogation = {
                    "sinistre_id":          params["sinistre_id"],
                    "responsable_nom":      params.get("responsable_nom", ""),
                    "responsable_assureur": params.get("responsable_assureur", ""),
                    "montant_indemnise":    params["montant_indemnise"],
                    "date_paiement":        params["date_paiement"],
                    "date_prescription":    date_presc.isoformat(),
                    "date_creation":        date.today().isoformat(),
                    "statut":               "ouvert",
                }
                await approval_queue.ajouter({
                    "type": "creation_subrogation",
                    "donnees": data_subrogation,
                    "montant": params["montant_indemnise"],
                    "user_id": user_id,
                    "execution_id": execution_id,
                    "description": (
                        f"Recours subrogatoire — sinistre {params['sinistre_id']} — "
                        f"{params['montant_indemnise']:,} FCFA — "
                        f"responsable : {params.get('responsable_nom', 'inconnu')}"
                    ).replace(",", " "),
                })
                return json.dumps({
                    "statut": "en_attente_validation",
                    "sinistre_id": params["sinistre_id"],
                    "montant_indemnise": params["montant_indemnise"],
                    "date_prescription_calculee": date_presc.isoformat(),
                    "jours_avant_prescription": jours_restants,
                    "base_legale": "Subrogation OHADA — délai 3 ans depuis paiement",
                    "message": "Recours subrogatoire soumis pour validation avant enregistrement.",
                }, ensure_ascii=False)

            if nom == "veille_reglementaire":
                from core.ia_client import ModeIA, ia_client
                from modules.chat.cima_retriever import rechercher_articles
                domaine = params["domaine"]
                if domaine in ("cima", "tous"):
                    articles = rechercher_articles(f"dernières modifications réglementaires {domaine}")
                    return articles
                prompt = f"""Synthèse veille réglementaire domaine : {domaine}
Depuis : {params.get('depuis', '2024-01-01')}
Résume les principaux textes, circulaires, décisions pertinentes pour une compagnie d'assurance zone CIMA."""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
                return rep.contenu

            if nom == "valider_transaction":
                from core.approval_queue import approval_queue
                await approval_queue.ajouter({
                    "type": "transaction_juridique",
                    "reference": params["reference"],
                    "montant_offert": params["montant_offert"],
                    "montant_reclame": params.get("montant_reclame", 0),
                    "conditions": params.get("conditions", ""),
                    "user_id": user_id,
                    "execution_id": execution_id,
                })
                taux = round(params["montant_offert"] / params.get("montant_reclame", params["montant_offert"]) * 100, 1) if params.get("montant_reclame") else 100
                return f"Transaction soumise pour validation — {params['montant_offert']:,} FCFA ({taux}% de la réclamation)".replace(",", " ")

            if nom == "traiter_litige_client":
                from core.ia_client import ModeIA, ia_client
                action = params["action"]
                objet = params["objet_reclamation"]
                montant = params.get("montant_reclame", 0)

                if action == "analyser":
                    prompt = f"""Analyse cette réclamation client d'assurance.
Objet : {objet}
Montant réclamé : {montant:,} FCFA
Police : {params.get('police_id', 'non précisée')}
Pièces fournies : {params.get('pieces_jointes', [])}

Évaluer : bien-fondé de la réclamation, articles CIMA applicables, position recommandée (accorder / refuser / négocier), risque contentieux si refus."""
                    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                    return rep.contenu

                if action == "repondre":
                    prompt = f"""Rédige une réponse officielle à une réclamation client d'assurance.
Objet réclamation : {objet}
Montant : {montant:,} FCFA
Client ID : {params.get('client_id', 'N/A')}

Ton : professionnel, factuel, référence aux articles de la police et du Code CIMA. Expliquer clairement la décision."""
                    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                    return rep.contenu

                if action == "proposer_mediation":
                    prompt = f"""Rédige une proposition de médiation amiable pour résoudre un litige client.
Objet : {objet} — Montant : {montant:,} FCFA
Proposer : cadre de la médiation, délai, compromis envisageable, avantages pour les deux parties."""
                    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.CREATION)
                    return rep.contenu

                if action == "escalader_contentieux":
                    from core.approval_queue import approval_queue
                    await approval_queue.ajouter({
                        "type": "escalade_contentieux",
                        "client_id": params.get("client_id"),
                        "police_id": params.get("police_id"),
                        "objet": objet,
                        "montant_reclame": montant,
                        "user_id": user_id,
                        "execution_id": execution_id,
                    })
                    return f"Litige escaladé en contentieux — {objet} — {montant:,} FCFA — en attente validation DG/Juridique".replace(",", " ")

                return f"Action litige '{action}' non reconnue"

            if nom == "gerer_expertise_judiciaire":
                from core.ia_client import ModeIA, ia_client
                action = params["action"]
                sinistre_id = params["sinistre_id"]

                if action == "designer":
                    from core.approval_queue import approval_queue
                    await approval_queue.ajouter({
                        "type": "designation_expert_judiciaire",
                        "sinistre_id": sinistre_id,
                        "type_expertise": params.get("type_expertise"),
                        "expert_nom": params.get("expert_nom", ""),
                        "user_id": user_id,
                        "execution_id": execution_id,
                    })
                    return f"Désignation expert judiciaire soumise pour validation — sinistre {sinistre_id}"

                if action == "rapport_contradictoire":
                    rapport = params.get("rapport_data", {})
                    prompt = f"""Analyse ce rapport d'expertise judiciaire en position d'assureur.
Sinistre : {sinistre_id}
Rapport : {json.dumps(rapport, ensure_ascii=False, indent=2)}

Identifier : points favorables à l'assureur, points contestables, montants à valider ou réduire, recommandation (accepter / contester partiellement / contester totalement)."""
                    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                    return rep.contenu

                if action == "contester_rapport":
                    rapport = params.get("rapport_data", {})
                    prompt = f"""Rédige un dire contradictoire contre ce rapport d'expertise judiciaire.
Sinistre : {sinistre_id}
Points contestés : {json.dumps(rapport.get('points_contestes', []), ensure_ascii=False)}
Éléments de preuve contraires : {json.dumps(rapport.get('preuves', []), ensure_ascii=False)}

Format juridique : en-tête, exposé technique, articles de contestation, demande de contre-expertise."""
                    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                    return rep.contenu

                if action == "accepter_rapport":
                    from core.approval_queue import approval_queue
                    montant = params.get("rapport_data", {}).get("montant_retenu", 0)
                    await approval_queue.ajouter({
                        "type": "acceptation_rapport_expertise",
                        "sinistre_id": sinistre_id,
                        "montant_retenu": montant,
                        "user_id": user_id,
                        "execution_id": execution_id,
                    })
                    return f"Acceptation rapport expertise soumise pour validation — sinistre {sinistre_id} — {montant:,} FCFA".replace(",", " ")

                return f"Action expertise '{action}' non reconnue"

            if nom == "gerer_amende_regulatoire":
                from core.ia_client import ModeIA, ia_client
                action = params["action"]
                montant = params["montant_amende"]
                motif = params["motif"]
                ref = params["reference_amende"]

                if action == "analyser":
                    prompt = f"""Analyse cette sanction/amende de la CRCA.
Référence : {ref}
Montant : {montant:,} FCFA
Motif : {motif}
Date notification : {params.get('date_notification', 'N/A')}

Évaluer : base légale CIMA, proportionnalité de l'amende, délai de recours (Art. CIMA), possibilité de contestation, impact sur la compagnie."""
                    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                    # Calcul délai recours
                    if params.get("date_notification"):
                        date_notif = date.fromisoformat(params["date_notification"])
                        date_recours = date_notif + timedelta(days=30)  # Délai recours standard CIMA
                        jours_recours = (date_recours - date.today()).days
                        return json.dumps({
                            "reference": ref,
                            "montant": montant,
                            "date_limite_recours": date_recours.isoformat(),
                            "jours_restants_recours": jours_recours,
                            "urgence": jours_recours <= 10,
                            "analyse": rep.contenu,
                        }, ensure_ascii=False)
                    return rep.contenu

                if action == "contester":
                    prompt = f"""Rédige un recours en contestation d'une amende CRCA.
Référence amende : {ref} — Montant : {montant:,} FCFA — Motif : {motif}

Arguments de contestation : proportionnalité, absence de faute, circonstances atténuantes, régularisation déjà effectuée. Format juridique officiel."""
                    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                    from core.approval_queue import approval_queue
                    await approval_queue.ajouter({
                        "type": "contestation_amende_crca",
                        "reference": ref,
                        "montant": montant,
                        "user_id": user_id,
                        "execution_id": execution_id,
                    })
                    return rep.contenu + "\n\n[Contestation soumise pour validation DG avant envoi]"

                if action in ("accepter_payer", "plan_regularisation"):
                    from core.approval_queue import approval_queue
                    await approval_queue.ajouter({
                        "type": f"amende_crca_{action}",
                        "reference": ref,
                        "montant": montant,
                        "motif": motif,
                        "user_id": user_id,
                        "execution_id": execution_id,
                        "description": f"Amende CRCA {ref} — {montant:,} FCFA — {action}".replace(",", " "),
                    })
                    return f"Amende {ref} ({montant:,} FCFA) soumise pour validation — action : {action}".replace(",", " ")

                return f"Action amende '{action}' non reconnue"

            if nom == "archiver_documents_legaux":
                # Durées légales de conservation (OHADA + CIMA)
                _DUREES_CONSERVATION = {
                    "contrat":                  10,  # Art. CIMA — 10 ans après expiration
                    "sinistre":                 10,  # 10 ans après clôture
                    "contentieux":              10,  # 10 ans après décision définitive
                    "correspondance_crca":      10,  # 10 ans
                    "rh":                       5,   # 5 ans Code travail
                    "comptable":                10,  # 10 ans OHADA
                }
                type_doc = params["type_document"]
                action = params["action"]
                duree_requise = _DUREES_CONSERVATION.get(type_doc, 10)
                duree_proposee = params.get("duree_conservation_ans", duree_requise)

                if action == "verifier_duree":
                    return json.dumps({
                        "type_document": type_doc,
                        "duree_legale_ans": duree_requise,
                        "duree_proposee_ans": duree_proposee,
                        "conforme": duree_proposee >= duree_requise,
                        "base_legale": "OHADA / Code CIMA",
                    }, ensure_ascii=False)

                if action == "detruire":
                    # Destruction → validation obligatoire
                    from core.approval_queue import approval_queue
                    date_doc = date.fromisoformat(params.get("date_document", "2000-01-01"))
                    date_destruction_ok = date_doc + timedelta(days=duree_requise * 365)
                    peut_detruire = date.today() >= date_destruction_ok
                    await approval_queue.ajouter({
                        "type": "destruction_documents_legaux",
                        "reference": params["reference"],
                        "type_document": type_doc,
                        "date_document": params.get("date_document"),
                        "duree_legale_ans": duree_requise,
                        "peut_detruire": peut_detruire,
                        "user_id": user_id,
                        "execution_id": execution_id,
                        "description": f"Destruction documents {type_doc} — {params['reference']} — {'autorisé' if peut_detruire else 'PRÉMATURÉ'}",
                    })
                    return (
                        f"Demande destruction {type_doc} {params['reference']} soumise.\n"
                        f"Durée légale : {duree_requise} ans — {'Destruction autorisée' if peut_detruire else '⚠️ DESTRUCTION PRÉMATURÉE — vérifier conformité'}\n"
                        "En attente validation."
                    )

                # Archiver
                from core.approval_queue import approval_queue
                await approval_queue.ajouter({
                    "type": "archivage_document_legal",
                    "reference": params["reference"],
                    "type_document": type_doc,
                    "duree_conservation_ans": duree_proposee,
                    "user_id": user_id,
                    "execution_id": execution_id,
                })
                return f"Archivage {type_doc} {params['reference']} soumis — durée {duree_proposee} ans — en attente validation"

            return f"Outil '{nom}' non reconnu"
        except Exception as e:
            logger.error(f"[AgentJuridique] Erreur outil {nom} : {e}")
            return f"ERREUR {nom} : {e}"
