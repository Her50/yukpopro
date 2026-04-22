"""Agent Conformité CIMA — ratios prudentiels, états réglementaires, audit interne, FCR."""
from __future__ import annotations
import json, logging
from datetime import date, timedelta
from core.agent_orchestrateur import TypeAgent
from core.workflow_engine import (
    calculer_marge_solvabilite_non_vie,
    calculer_marge_solvabilite_vie,
    verifier_delai_reglementaire,
)
from agents.base_agent import BaseAgent

logger = logging.getLogger("yukpo_assurance.agents.conformite")

# Taux FCR (Fonds de Caution et de Réserve) — Art. 312 CIMA
_TAUX_FCR_MIN = 0.01   # 1% des primes nettes
_TAUX_FCR_MAX = 0.03   # Plafond autorisé

# Délais réglementaires soumission états CIMA (jours après clôture exercice)
_DELAIS_ETATS = {
    "C1":  90,   # État récapitulatif
    "C11": 90,   # Non-vie
    "C12": 90,   # Vie
    "C3":  120,  # Réassurance
    "C4":  120,  # Placements
    "C8":  90,   # Compte de résultat
}


class AgentConformite(BaseAgent):
    type_agent = TypeAgent.CONFORMITE

    def _system_prompt(self) -> str:
        return """Tu es l'Agent Conformité CIMA de YukpoAssurance.

Tu maîtrises parfaitement le Code CIMA (399 articles, 6 Livres) et les exigences CRCA.

DOMAINES :
1. Ratios prudentiels : marge solvabilité, couverture PM, ratio sinistres/primes
2. États réglementaires : C1, C11, C12, C3, C4, C8 — soumission CRCA
3. Audit interne : plan annuel, missions, recommandations, suivi
4. FCR (Fonds de Caution et de Réserve) : calcul, vérification, alimentation
5. Sinistres tardifs : détection non-conformités délais Art. 12-bis/ter/quater
6. Mises en demeure réglementaires : suivi, réponses, plans de redressement

PRIORITÉS :
1. Calculs réglementaires : TOUJOURS déterministes (0 IA pour les chiffres)
2. Interprétation des résultats et rédaction des rapports : IA autorisée
3. Toute alerte de non-conformité → notification DG immédiate
4. Tout envoi officiel CRCA → validation humaine obligatoire
5. Baser chaque observation sur l'article CIMA précis"""

    def _definir_outils(self) -> list[dict]:
        return [
            {
                "name": "calculer_ratios_prudentiels",
                "description": "Calcule marge solvabilité, couverture provisions, ratio sinistres/primes (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "periode":             {"type": "string", "description": "ex: 2025-T1"},
                    "primes_nettes":       {"type": "number"},
                    "sinistres_moy_3ans":  {"type": "number"},
                    "pm_brutes":           {"type": "number"},
                    "capital_sous_risque": {"type": "number"},
                    "fonds_propres":       {"type": "number"},
                }, "required": ["periode"]},
            },
            {
                "name": "rechercher_articles_cima",
                "description": "Recherche les articles CIMA applicables (RAG, 0 IA générative)",
                "input_schema": {"type": "object", "properties": {
                    "question": {"type": "string"},
                }, "required": ["question"]},
            },
            {
                "name": "generer_etat_reglementaire",
                "description": "Génère un état CIMA (C1, C11, C12, etc.) et soumet pour validation avant envoi CRCA",
                "input_schema": {"type": "object", "properties": {
                    "type_etat": {"type": "string", "enum": ["C1", "C11", "C12", "C8", "C3", "C4"]},
                    "periode":   {"type": "string"},
                    "annee":     {"type": "integer"},
                    "soumettre_crca": {"type": "boolean", "description": "Soumettre officiellement à la CRCA après validation"},
                }, "required": ["type_etat", "annee"]},
            },
            {
                "name": "rediger_rapport_conformite",
                "description": "Rédige le rapport de conformité narratif via IA",
                "input_schema": {"type": "object", "properties": {
                    "donnees_ratios": {"type": "object"},
                    "periode":        {"type": "string"},
                    "alertes":        {"type": "array", "items": {"type": "string"}},
                }, "required": ["donnees_ratios", "periode"]},
            },
            {
                "name": "verifier_delais_reglementaires",
                "description": "Vérifie le respect des délais CIMA sur les dossiers en cours (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "type_delai":      {"type": "string"},
                    "date_evenement":  {"type": "string"},
                    "date_action":     {"type": "string"},
                }, "required": ["type_delai", "date_evenement"]},
            },
            {
                "name": "alerter_direction",
                "description": "Envoie une alerte conformité à la direction",
                "input_schema": {"type": "object", "properties": {
                    "niveau":  {"type": "string", "enum": ["info", "avertissement", "critique"]},
                    "message": {"type": "string"},
                    "article": {"type": "string"},
                }, "required": ["niveau", "message"]},
            },
            {
                "name": "auditer_interne",
                "description": "Planifie, conduit ou reporte une mission d'audit interne (déterministe + IA)",
                "input_schema": {"type": "object", "properties": {
                    "action":       {"type": "string", "enum": ["planifier_annuel", "lancer_mission", "rapport_mission", "suivi_recommandations"]},
                    "domaine":      {"type": "string", "enum": ["sinistres", "souscription", "comptabilite", "rh", "conformite", "placements", "tous"]},
                    "mission_id":   {"type": "string"},
                    "exercice":     {"type": "integer"},
                    "constats":     {"type": "array", "items": {"type": "object"}},
                }, "required": ["action"]},
            },
            {
                "name": "calculer_fcr",
                "description": "Calcule et vérifie la conformité du Fonds de Caution et de Réserve Art. 312 CIMA (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "primes_nettes_annuelles": {"type": "number"},
                    "fcr_actuel":              {"type": "number", "description": "Montant FCR constitué"},
                    "alimentation_proposee":   {"type": "number", "description": "Dotation à valider"},
                }, "required": ["primes_nettes_annuelles", "fcr_actuel"]},
            },
            {
                "name": "gerer_mise_en_demeure_regulatoire",
                "description": "Traite une mise en demeure de la CRCA : analyse, plan de redressement, réponse officielle",
                "input_schema": {"type": "object", "properties": {
                    "reference_mde":    {"type": "string"},
                    "date_reception":   {"type": "string", "description": "YYYY-MM-DD"},
                    "objet":            {"type": "string"},
                    "delai_reponse_j":  {"type": "integer", "description": "Délai accordé par la CRCA (jours)"},
                    "action":           {"type": "string", "enum": ["analyser", "rediger_plan_redressement", "valider_reponse"]},
                    "plan_data":        {"type": "object"},
                }, "required": ["reference_mde", "date_reception", "objet", "action"]},
            },
            {
                "name": "auditer_sinistres_tardifs",
                "description": "Audit CIMA des sinistres en retard de règlement : liste, calcul pénalités potentielles, rapport",
                "input_schema": {"type": "object", "properties": {
                    "periode":   {"type": "string"},
                    "branche":   {"type": "string"},
                    "avec_interets_moratoires": {"type": "boolean"},
                }, "required": ["periode"]},
            },
            {
                "name": "verifier_soumission_etats",
                "description": "Vérifie que tous les états CIMA requis ont été soumis dans les délais (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "annee":      {"type": "integer"},
                    "date_cloture": {"type": "string", "description": "Date clôture exercice YYYY-MM-DD"},
                }, "required": ["annee"]},
            },
        ]

    def _prompt_questions_specifiques(self) -> str:
        return """
AGENT CONFORMITÉ CIMA — quand demander une information :

1. EXERCICE FISCAL / PÉRIODE D'ANALYSE NON PRÉCISÉ
   → "Pour quel exercice ou quelle période souhaitez-vous l'analyse de conformité ? (Ex: Exercice 2024 annuel, ou T1/T2/T3/T4 2025)"
   type_reponse: texte_libre

2. TYPE DE COMPAGNIE NON IDENTIFIÉ (impacte les ratios Art. 337 CIMA)
   → "La compagnie est-elle agréée en Vie, Non-Vie, ou les deux (compagnie mixte) ? (Détermine les ratios prudentiels applicables)"
   type_reponse: choix_multiple  choix: ["Non-Vie uniquement", "Vie uniquement", "Mixte Vie + Non-Vie", "Courtier / Intermédiaire"]

3. DONNÉES FINANCIÈRES MANQUANTES (primes, capitaux propres, provisions)
   → "Je n'ai pas accès aux données financières de l'exercice {annee}. Pouvez-vous me confirmer le montant des primes nettes émises (en FCFA) ?"
   type_reponse: nombre

4. CAPITAUX PROPRES INTROUVABLES EN BASE
   → "Quel est le montant des capitaux propres de la compagnie au {date} (en FCFA) ? (Requis pour le calcul de la marge de solvabilité Art. 337-1)"
   type_reponse: nombre

5. PROVISIONS TECHNIQUES NON RENSEIGNÉES
   → "Quel est le montant total des provisions techniques constituées à la clôture (en FCFA) ? (PSAP + PPNA + PM pour les contrats vie)"
   type_reponse: nombre

6. PÉRIMÈTRE DE L'AUDIT INTERNE
   → "Sur quel périmètre souhaitez-vous l'audit de conformité ?"
   type_reponse: choix_multiple  choix: ["Conformité réglementaire globale (tous ratios CIMA)", "Audit sinistres uniquement", "Audit souscription / tarification", "Audit comptable / provisionnement", "Préparation contrôle CRCA"]

7. RAPPORT CRCA — DONNÉES INCOMPLÈTES
   → "La soumission au CRCA requiert des données complémentaires. Quelle est la date de clôture de l'exercice à soumettre ?"
   type_reponse: date

PROGRESSION : Exercice → Type compagnie → Données financières (primes, capitaux, provisions) → Périmètre.
"""

    async def _executer_outil(self, nom: str, params: dict, user_id: int, execution_id: str) -> str:
        try:
            if nom == "calculer_ratios_prudentiels":
                resultats = {}
                if params.get("primes_nettes") and params.get("sinistres_moy_3ans"):
                    r = calculer_marge_solvabilite_non_vie(
                        params["primes_nettes"], params["sinistres_moy_3ans"]
                    )
                    resultats["marge_non_vie"] = r.donnees
                if params.get("pm_brutes"):
                    r = calculer_marge_solvabilite_vie(
                        params["pm_brutes"], params.get("capital_sous_risque", 0)
                    )
                    resultats["marge_vie"] = r.donnees
                if params.get("fonds_propres") and resultats.get("marge_non_vie"):
                    requis = resultats["marge_non_vie"]["marge_requise"]
                    fp     = params["fonds_propres"]
                    resultats["couverture_pct"] = round(fp / requis * 100, 1) if requis else 0
                    resultats["conforme"]       = resultats["couverture_pct"] >= 100
                resultats["periode"] = params["periode"]
                return json.dumps(resultats, ensure_ascii=False)

            if nom == "rechercher_articles_cima":
                from modules.chat.cima_retriever import rechercher_articles
                return rechercher_articles(params["question"])

            if nom == "generer_etat_reglementaire":
                from modules.cima.etats_reglementaires import generer_etat
                contenu = await generer_etat(
                    type_etat=params["type_etat"],
                    annee=params["annee"],
                    periode=params.get("periode", ""),
                )
                if params.get("soumettre_crca"):
                    # Validation humaine obligatoire avant envoi officiel à la CRCA
                    from core.approval_queue import approval_queue
                    await approval_queue.ajouter({
                        "type": "soumission_etat_crca",
                        "type_etat": params["type_etat"],
                        "annee": params["annee"],
                        "contenu_apercu": str(contenu)[:300],
                        "user_id": user_id,
                        "execution_id": execution_id,
                        "description": f"État {params['type_etat']} exercice {params['annee']} — soumission officielle CRCA",
                    })
                    return str(contenu) + "\n\n[État soumis pour validation avant transmission CRCA]"
                return str(contenu)

            if nom == "rediger_rapport_conformite":
                from core.ia_client import ModeIA, ia_client
                prompt = f"""Rédige un rapport de conformité CIMA professionnel.

Période : {params['periode']}
Données ratios : {json.dumps(params['donnees_ratios'], ensure_ascii=False, indent=2)}
Alertes : {params.get('alertes', [])}

Structure : Résumé exécutif → Ratios prudentiels → Points de vigilance → Recommandations → Articles CIMA applicables"""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                return rep.contenu

            if nom == "verifier_delais_reglementaires":
                result = verifier_delai_reglementaire(
                    type_delai=params["type_delai"],
                    date_evenement=date.fromisoformat(params["date_evenement"]),
                    date_action=date.fromisoformat(params["date_action"]) if params.get("date_action") else None,
                )
                return json.dumps(result.donnees, ensure_ascii=False)

            if nom == "alerter_direction":
                from core.notifications import notifications
                await notifications.envoyer_alerte_direction(
                    niveau=params["niveau"],
                    message=params["message"],
                    article=params.get("article", ""),
                )
                return f"Alerte {params['niveau']} envoyée à la direction"

            if nom == "auditer_interne":
                from core.ia_client import ModeIA, ia_client
                action = params["action"]
                if action == "planifier_annuel":
                    exercice = params.get("exercice", date.today().year)
                    prompt = f"""Établis le plan d'audit interne annuel pour une compagnie d'assurance zone CIMA, exercice {exercice}.

Domaines à couvrir : sinistres, souscription, comptabilité, RH, conformité CIMA, placements, réassurance.

Pour chaque domaine : objectifs de la mission, risques ciblés, périmètre, calendrier (T1/T2/T3/T4), ressources.
Conformément aux exigences CIMA Livre IV sur le contrôle interne."""
                    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                    return rep.contenu

                if action == "lancer_mission":
                    domaine = params.get("domaine", "tous")
                    prompt = f"""Rédige le programme de travail d'une mission d'audit interne pour le domaine : {domaine}.

Compagnie d'assurance zone CIMA.
Inclure : objectifs, risques évalués, procédures d'audit (tests de contrôle, tests de substance), livrables, calendrier."""
                    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                    return rep.contenu

                if action == "rapport_mission":
                    constats = params.get("constats", [])
                    prompt = f"""Rédige le rapport d'une mission d'audit interne.
Mission ID : {params.get('mission_id', 'N/A')}
Domaine : {params.get('domaine', 'N/A')}
Constats :
{json.dumps(constats, ensure_ascii=False, indent=2)}

Structure : synthèse, constats et risques associés, recommandations par priorité (critique/majeur/mineur), plan d'action suggéré."""
                    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                    # Rapport d'audit → validation avant diffusion
                    from core.approval_queue import approval_queue
                    await approval_queue.ajouter({
                        "type": "rapport_audit_interne",
                        "mission_id": params.get("mission_id"),
                        "domaine": params.get("domaine"),
                        "nb_constats": len(constats),
                        "user_id": user_id,
                        "execution_id": execution_id,
                    })
                    return rep.contenu + "\n\n[Rapport soumis pour validation DG avant diffusion]"

                if action == "suivi_recommandations":
                    from core.orass_connector import orass
                    suivi = await orass.get_suivi_audit(mission_id=params.get("mission_id"))
                    ouvertes = [r for r in suivi if r.get("statut") != "clos"]
                    en_retard = [r for r in ouvertes if date.fromisoformat(r.get("echeance", "9999-12-31")) < date.today()]
                    return json.dumps({
                        "recommandations_total": len(suivi),
                        "ouvertes": len(ouvertes),
                        "en_retard": len(en_retard),
                        "taux_mise_en_oeuvre_pct": round((len(suivi) - len(ouvertes)) / max(len(suivi), 1) * 100, 1),
                        "details_retard": en_retard,
                    }, ensure_ascii=False, default=str)

                return f"Action audit '{action}' non reconnue"

            if nom == "calculer_fcr":
                primes = params["primes_nettes_annuelles"]
                fcr_actuel = params["fcr_actuel"]
                fcr_min_requis = round(primes * _TAUX_FCR_MIN)
                fcr_max_autorise = round(primes * _TAUX_FCR_MAX)
                conforme = fcr_actuel >= fcr_min_requis
                ecart = fcr_actuel - fcr_min_requis
                alimentation = params.get("alimentation_proposee", 0)
                if alimentation and not conforme:
                    # Validation humaine pour dotation FCR
                    from core.approval_queue import approval_queue
                    await approval_queue.ajouter({
                        "type": "dotation_fcr",
                        "montant": alimentation,
                        "fcr_avant": fcr_actuel,
                        "fcr_apres": fcr_actuel + alimentation,
                        "fcr_min_requis": fcr_min_requis,
                        "user_id": user_id,
                        "execution_id": execution_id,
                        "description": f"Dotation FCR : {alimentation:,} FCFA — Art. 312 CIMA".replace(",", " "),
                    })
                return json.dumps({
                    "primes_nettes_annuelles": primes,
                    "fcr_actuel": fcr_actuel,
                    "fcr_minimum_requis": fcr_min_requis,
                    "fcr_maximum_autorise": fcr_max_autorise,
                    "conforme_art_312": conforme,
                    "ecart_fcfa": ecart,
                    "action": "COMPLETER" if not conforme else "CONFORME",
                    "base_legale": "Art. 312 Code CIMA — Fonds de Caution et de Réserve",
                    "alimentation_soumise_validation": alimentation > 0 and not conforme,
                }, ensure_ascii=False)

            if nom == "gerer_mise_en_demeure_regulatoire":
                from core.ia_client import ModeIA, ia_client
                date_rec = date.fromisoformat(params["date_reception"])
                delai = params.get("delai_reponse_j", 30)
                date_echeance = date_rec + timedelta(days=delai)
                jours_restants = (date_echeance - date.today()).days
                action = params["action"]

                if action == "analyser":
                    prompt = f"""Analyse cette mise en demeure de la CRCA.
Référence : {params['reference_mde']}
Date réception : {params['date_reception']}
Objet : {params['objet']}
Délai de réponse : {delai} jours (échéance : {date_echeance.isoformat()}) — {jours_restants}j restants

Fournir : analyse juridique (articles CIMA en cause), gravité, risques (sanctions Art. 312 à 320 CIMA), éléments de réponse requis."""
                    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                    return json.dumps({
                        "reference": params["reference_mde"],
                        "date_echeance": date_echeance.isoformat(),
                        "jours_restants": jours_restants,
                        "urgence": jours_restants <= 7,
                        "analyse": rep.contenu,
                    }, ensure_ascii=False)

                if action == "rediger_plan_redressement":
                    prompt = f"""Rédige un plan de redressement en réponse à la mise en demeure CRCA.
Référence : {params['reference_mde']} — Objet : {params['objet']}
Données : {json.dumps(params.get('plan_data', {}), ensure_ascii=False)}

Structure : reconnaissance des faits, mesures correctives immédiates, calendrier de mise en conformité, engagements formels, indicateurs de suivi."""
                    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                    return rep.contenu

                if action == "valider_reponse":
                    from core.approval_queue import approval_queue
                    await approval_queue.ajouter({
                        "type": "reponse_mise_en_demeure_crca",
                        "reference_mde": params["reference_mde"],
                        "date_echeance": date_echeance.isoformat(),
                        "jours_restants": jours_restants,
                        "user_id": user_id,
                        "execution_id": execution_id,
                        "description": f"Réponse officielle CRCA — MDE {params['reference_mde']} — {jours_restants}j restants",
                    })
                    return f"Réponse à la MDE {params['reference_mde']} soumise pour validation DG — échéance : {date_echeance.isoformat()} ({jours_restants}j)"

                return f"Action mise en demeure '{action}' non reconnue"

            if nom == "auditer_sinistres_tardifs":
                from core.orass_connector import orass
                sinistres = await orass.get_sinistres_ouverts(
                    branche=params.get("branche"),
                    statut="ouvert",
                )
                tardifs = []
                total_interets = 0
                aujourd_hui = date.today()
                for s in sinistres:
                    date_decl = date.fromisoformat(s.get("date_declaration", aujourd_hui.isoformat()))
                    date_echeance = date_decl + timedelta(days=90)  # Art. 12-bis
                    if date_echeance < aujourd_hui:
                        retard = (aujourd_hui - date_echeance).days
                        montant = s.get("montant_estime", 0)
                        interets = 0
                        if params.get("avec_interets_moratoires") and montant:
                            interets = round(montant * 0.12 * retard / 365)
                            total_interets += interets
                        tardifs.append({
                            **s,
                            "retard_jours": retard,
                            "echeance_cima": date_echeance.isoformat(),
                            "interets_moratoires_fcfa": interets,
                        })
                return json.dumps({
                    "periode": params["periode"],
                    "sinistres_tardifs": len(tardifs),
                    "total_interets_moratoires_fcfa": total_interets,
                    "base_legale": "Art. 12-bis/ter/quater Code CIMA",
                    "conformite": "NON CONFORME" if tardifs else "CONFORME",
                    "details": tardifs[:30],
                }, ensure_ascii=False, default=str)

            if nom == "verifier_soumission_etats":
                annee = params["annee"]
                date_cloture = date.fromisoformat(params.get("date_cloture", f"{annee}-12-31"))
                etats_status = []
                for type_etat, delai in _DELAIS_ETATS.items():
                    date_limite = date_cloture + timedelta(days=delai)
                    jours_restants = (date_limite - date.today()).days
                    etats_status.append({
                        "type_etat": type_etat,
                        "date_limite": date_limite.isoformat(),
                        "jours_restants": jours_restants,
                        "statut": "EN RETARD" if jours_restants < 0 else "URGENT" if jours_restants <= 15 else "OK",
                    })
                non_conformes = [e for e in etats_status if e["statut"] == "EN RETARD"]
                return json.dumps({
                    "annee": annee,
                    "etats": etats_status,
                    "nb_non_conformes": len(non_conformes),
                    "conformite_globale": "NON CONFORME" if non_conformes else "CONFORME",
                    "base_legale": "Art. CIMA — délais soumission états réglementaires CRCA",
                }, ensure_ascii=False)

            return f"Outil '{nom}' non reconnu"
        except Exception as e:
            logger.error(f"[AgentConformite] Erreur outil {nom} : {e}")
            return f"ERREUR {nom} : {e}"
