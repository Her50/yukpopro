"""Agent Intelligence & Veille — KPI, rapports direction, veille marché, détection risques."""
from __future__ import annotations
import json
import logging
from datetime import date, timedelta
from core.agent_orchestrateur import TypeAgent
from agents.base_agent import BaseAgent

logger = logging.getLogger("yukpo_assurance.agents.intelligence")


class AgentIntelligence(BaseAgent):
    type_agent = TypeAgent.INTELLIGENCE

    def _system_prompt(self) -> str:
        return """Tu es l'Agent Intelligence de YukpoAssurance, expert en analyse stratégique et reporting direction.

DOMAINES :
1. Tableaux de bord : KPI en temps réel, comparatifs période, alertes seuils
2. Rapports direction : CA, conseil d'administration, comités
3. Veille marché : concurrents, tendances, nouvelles réglementations
4. Détection risques : anomalies portefeuille, concentration risque, Early Warning
5. Benchmarking : comparaison avec marché CIMA, positionnement
6. Prévisions : projections primes, sinistralité, résultats

RÈGLES :
- Les KPI sont calculés DÉTERMINISTIQUEMENT depuis ORASS (0 IA pour les chiffres)
- L'IA intervient uniquement pour l'interprétation, la rédaction, les insights
- Tout rapport direction passe par validation avant diffusion
- Les alertes de risque systémique sont notifiées à la DG immédiatement

INDICATEURS CLÉS ASSURANCE :
- Combined Ratio (< 100% = rentable)
- Loss Ratio = sinistres / primes acquises
- Expense Ratio = frais / primes
- Taux de renouvellement (objectif > 80%)
- Taux de sinistralité par branche
- Ratio de solvabilité (CIMA : min 100%)"""

    def _definir_outils(self) -> list[dict]:
        return [
            {
                "name": "calculer_kpi_temps_reel",
                "description": "Calcule tous les KPI clés de la compagnie en temps réel (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "periode":    {"type": "string", "description": "ex: 2025-T1, 2025-M03, 2025"},
                    "branche":    {"type": "string", "description": "auto | vie | mrh | transport | tous"},
                    "granularite": {"type": "string", "enum": ["global", "branche", "apporteur", "region"]},
                }, "required": ["periode"]},
            },
            {
                "name": "generer_rapport_direction",
                "description": "Génère un rapport exécutif direction/CA via IA",
                "input_schema": {"type": "object", "properties": {
                    "type_rapport": {"type": "string", "enum": ["mensuel", "trimestriel", "annuel", "ca", "comite_risque"]},
                    "periode":      {"type": "string"},
                    "kpi_data":     {"type": "object"},
                    "destinataires": {"type": "array", "items": {"type": "string"}},
                }, "required": ["type_rapport", "periode"]},
            },
            {
                "name": "detecter_anomalies",
                "description": "Détecte les anomalies et signaux faibles dans le portefeuille (déterministe + IA)",
                "input_schema": {"type": "object", "properties": {
                    "type_analyse": {"type": "string", "enum": ["sinistralite", "production", "fraude_portfolio", "concentration_risque", "tous"]},
                    "periode":      {"type": "string"},
                    "seuil_alerte": {"type": "number", "description": "% d'écart déclenchant une alerte"},
                }, "required": ["type_analyse", "periode"]},
            },
            {
                "name": "veille_marche",
                "description": "Analyse IA de la veille concurrentielle et réglementaire",
                "input_schema": {"type": "object", "properties": {
                    "domaine":    {"type": "string", "enum": ["concurrents", "reglementaire", "produits", "digital", "tous"]},
                    "pays":       {"type": "string", "description": "Code ISO pays ou 'CIMA' pour zone"},
                }, "required": ["domaine"]},
            },
            {
                "name": "projection_financiere",
                "description": "Projections financières N+1 à N+3 basées sur tendances actuelles",
                "input_schema": {"type": "object", "properties": {
                    "horizon":        {"type": "integer", "description": "Nombre d'années (1, 2 ou 3)"},
                    "scenarios":      {"type": "array", "items": {"type": "string"}, "description": "['optimiste','base','pessimiste']"},
                    "hypotheses":     {"type": "object"},
                }, "required": ["horizon"]},
            },
            {
                "name": "alerte_risque_systemique",
                "description": "Notifie la direction d'un risque systémique détecté (validation non requise — urgence)",
                "input_schema": {"type": "object", "properties": {
                    "type_risque":    {"type": "string"},
                    "description":    {"type": "string"},
                    "impact_estime":  {"type": "number"},
                    "urgence":        {"type": "string", "enum": ["info", "avertissement", "critique"]},
                }, "required": ["type_risque", "description", "urgence"]},
            },
            {
                "name": "benchmarking_marche",
                "description": "Compare les indicateurs de la compagnie avec le marché CIMA",
                "input_schema": {"type": "object", "properties": {
                    "indicateurs": {"type": "array", "items": {"type": "string"}},
                    "periode":     {"type": "string"},
                }, "required": ["periode"]},
            },
            {
                "name": "stress_test_portefeuille",
                "description": "Simule des scénarios de stress sur le portefeuille (catastrophe, choc financier, épidémie) — déterministe",
                "input_schema": {"type": "object", "properties": {
                    "scenarios": {"type": "array", "items": {"type": "string"}, "description": "['solvency_ii','catastrophe_naturelle','choc_taux_200bp','epidemie','recession']"},
                    "fonds_propres":      {"type": "number"},
                    "pm_totales":         {"type": "number"},
                    "primes_annuelles":   {"type": "number"},
                    "sinistres_annuels":  {"type": "number"},
                }, "required": ["scenarios"]},
            },
            {
                "name": "predire_churn_portefeuille",
                "description": "Modélise le risque de churn à l'échelle du portefeuille par segment (IA + déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "periode":   {"type": "string"},
                    "branche":   {"type": "string"},
                    "horizon_mois": {"type": "integer", "description": "Horizon de prédiction en mois (3, 6 ou 12)"},
                    "avec_recommandations": {"type": "boolean"},
                }, "required": ["periode"]},
            },
            {
                "name": "dashboard_quotidien",
                "description": "Génère le dashboard opérationnel quotidien : KPI du jour vs J-1 et vs objectif mois (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "date_rapport":  {"type": "string", "description": "YYYY-MM-DD (défaut = aujourd'hui)"},
                    "destinataires": {"type": "array", "items": {"type": "string"}},
                    "format":        {"type": "string", "enum": ["texte", "html", "json"]},
                }, "required": []},
            },
        ]

    def _prompt_questions_specifiques(self) -> str:
        return """
AGENT INTELLIGENCE & VEILLE — quand demander une information :

1. PÉRIODE D'ANALYSE NON DÉFINIE
   → "Sur quelle période souhaitez-vous cette analyse stratégique ?"
   type_reponse: choix_multiple  choix: ["Mois en cours", "Trimestre en cours (T1/T2/T3/T4)", "Année en cours (cumul YTD)", "12 derniers mois glissants", "Comparatif N vs N-1", "Période personnalisée"]

2. TYPE DE RAPPORT NON PRÉCISÉ
   → "Quel type de rapport souhaitez-vous produire ?"
   type_reponse: choix_multiple  choix: ["Tableau de bord mensuel Direction Générale", "Rapport Conseil d'Administration (annuel)", "Rapport sinistralité par branche", "Analyse concurrentielle marché", "Rapport de veille réglementaire CIMA", "Détection anomalies / risques portefeuille", "KPI commerciaux et production"]

3. DESTINATAIRES DU RAPPORT
   → "À qui ce rapport est-il destiné ? (Détermine le niveau de détail et le format)"
   type_reponse: choix_multiple  choix: ["Direction Générale", "Conseil d'Administration", "Direction Technique / Actuariat", "Direction Commerciale", "CRCA (soumission réglementaire)", "Tous les comités de direction"]

4. INDICATEURS PRIORITAIRES NON DÉFINIS
   → "Quels indicateurs clés souhaitez-vous mettre en avant dans ce tableau de bord ?"
   type_reponse: choix_multiple  choix: ["Chiffre d'affaires et primes émises", "Ratio sinistres/primes (S/P)", "Ratio combiné", "Marge de solvabilité", "Taux de rétention clientèle", "Performance des apporteurs", "Indicateurs de fraude détectée"]

5. COMPARAISON CONCURRENTIELLE — SOCIÉTÉS CIBLES
   → "Par rapport à quels concurrents souhaitez-vous positionner la compagnie sur le marché ?"
   type_reponse: texte_libre

6. FORMAT DE SORTIE SOUHAITÉ
   → "Sous quel format souhaitez-vous ce rapport ?"
   type_reponse: choix_multiple  choix: ["Document Word (.docx) avec graphiques", "Présentation PowerPoint", "Tableau Excel avec données brutes", "Dashboard interactif (JSON)", "Texte résumé pour WhatsApp / email"]

PROGRESSION : Type rapport → Période → Destinataires → Indicateurs → Format.
"""

    async def _executer_outil(self, nom: str, params: dict, user_id: int, execution_id: str) -> str:
        try:
            if nom == "calculer_kpi_temps_reel":
                from core.orass_connector import orass
                data = await orass.get_kpi(
                    periode=params["periode"],
                    branche=params.get("branche", "tous"),
                    granularite=params.get("granularite", "global"),
                )
                # Calculs déterministes
                primes = data.get("primes_acquises", 0)
                sinistres = data.get("sinistres_survenus", 0)
                frais = data.get("frais_gestion", 0)
                commissions = data.get("commissions", 0)
                placements = data.get("produits_placement", 0)

                kpis = {
                    "periode": params["periode"],
                    "primes_acquises_fcfa": primes,
                    "sinistres_survenus_fcfa": sinistres,
                    "loss_ratio_pct": round(sinistres / primes * 100, 1) if primes else 0,
                    "expense_ratio_pct": round((frais + commissions) / primes * 100, 1) if primes else 0,
                    "combined_ratio_pct": round((sinistres + frais + commissions) / primes * 100, 1) if primes else 0,
                    "resultat_technique_fcfa": round(primes - sinistres - frais - commissions + placements),
                    "taux_renouvellement_pct": data.get("taux_renouvellement", 0),
                    "nb_polices_actives": data.get("nb_polices", 0),
                    "nb_sinistres_ouverts": data.get("nb_sinistres_ouverts", 0),
                    "nb_recours_actifs": data.get("nb_recours", 0),
                    "solvabilite_pct": data.get("solvabilite_pct", 0),
                }
                kpis["statut_global"] = (
                    "CRITIQUE" if kpis["combined_ratio_pct"] > 110 or kpis["solvabilite_pct"] < 100 else
                    "VIGILANCE" if kpis["combined_ratio_pct"] > 100 else
                    "SAIN"
                )
                return json.dumps(kpis, ensure_ascii=False)

            if nom == "generer_rapport_direction":
                from core.ia_client import ModeIA, ia_client
                from core.orass_connector import orass

                kpi_data = params.get("kpi_data") or await orass.get_kpi(periode=params["periode"])
                type_r = params["type_rapport"]

                structures = {
                    "mensuel": "Faits marquants du mois → Production → Sinistralité → Trésorerie → Actions en cours → Prochains rendez-vous",
                    "trimestriel": "Résumé exécutif → Analyse production → Résultats techniques → Solvabilité CIMA → Contentieux → Perspectives",
                    "annuel": "Message DG → Chiffres clés → Bilan activité par branche → Résultat financier → Conformité CIMA → Stratégie N+1",
                    "ca": "Gouvernance → Résultats exercice → Affectation résultat → Résolutions → Questions diverses",
                    "comite_risque": "Cartographie risques → Sinistralité atypique → Fraude → Solvabilité → Plan de mitigation",
                }

                prompt = f"""Rédige un rapport {type_r} professionnel pour {', '.join(params.get('destinataires', ['Direction générale']))}.
Période : {params['periode']}

Données KPI :
{json.dumps(kpi_data, ensure_ascii=False, indent=2)}

Structure imposée : {structures.get(type_r, 'Résumé → Analyse → Recommandations')}

Ton : professionnel, concis, orienté décision. Inclure tableaux si pertinent."""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)

                if params.get("destinataires"):
                    from core.approval_queue import approval_queue
                    await approval_queue.ajouter({
                        "type": "rapport_direction",
                        "type_rapport": type_r,
                        "periode": params["periode"],
                        "destinataires": params["destinataires"],
                        "contenu": rep.contenu[:500],  # extrait pour aperçu
                        "user_id": user_id,
                        "execution_id": execution_id,
                    })
                    return rep.contenu + "\n\n[Rapport soumis pour validation avant diffusion]"
                return rep.contenu

            if nom == "detecter_anomalies":
                from core.orass_connector import orass
                from core.ia_client import ModeIA, ia_client
                seuil = params.get("seuil_alerte", 15.0)
                data = await orass.get_donnees_analyse(
                    type_analyse=params["type_analyse"],
                    periode=params["periode"],
                )
                # Détection déterministe des écarts
                anomalies = []
                for indicateur, valeurs in data.get("historique", {}).items():
                    if len(valeurs) >= 2:
                        actuel = valeurs[-1].get("valeur", 0)
                        precedent = valeurs[-2].get("valeur", 1)
                        ecart = abs(actuel - precedent) / max(abs(precedent), 1) * 100
                        if ecart >= seuil:
                            anomalies.append({
                                "indicateur": indicateur,
                                "ecart_pct": round(ecart, 1),
                                "actuel": actuel,
                                "precedent": precedent,
                                "direction": "hausse" if actuel > precedent else "baisse",
                            })

                if anomalies:
                    prompt = f"""Analyse ces anomalies détectées dans le portefeuille ({params['type_analyse']}, {params['periode']}) :
{json.dumps(anomalies, ensure_ascii=False, indent=2)}

Pour chaque anomalie : cause probable, risque associé, action recommandée."""
                    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
                    return json.dumps({
                        "anomalies_detectees": len(anomalies),
                        "anomalies": anomalies,
                        "analyse_ia": rep.contenu,
                    }, ensure_ascii=False)

                return json.dumps({"anomalies_detectees": 0, "message": f"Aucune anomalie > {seuil}% détectée"})

            if nom == "veille_marche":
                from core.ia_client import ModeIA, ia_client
                prompt = f"""Réalise une analyse de veille concurrentielle et réglementaire dans le secteur des assurances.
Domaine : {params['domaine']}
Zone géographique : {params.get('pays', 'Zone CIMA (14 pays)')}

Analyse : tendances actuelles, innovations produits, évolutions réglementaires récentes, opportunités, menaces pour une compagnie d'assurance en Afrique subsaharienne.
Recommandations stratégiques concrètes (top 5)."""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
                return rep.contenu

            if nom == "projection_financiere":
                from core.orass_connector import orass
                from core.ia_client import ModeIA, ia_client
                historique = await orass.get_historique_financier(annees=3)
                scenarios = params.get("scenarios", ["base"])
                horizon = params["horizon"]

                prompt = f"""Génère des projections financières sur {horizon} an(s) pour une compagnie d'assurance.

Historique 3 ans :
{json.dumps(historique, ensure_ascii=False, indent=2)}

Scénarios demandés : {', '.join(scenarios)}
Hypothèses spécifiques : {json.dumps(params.get('hypotheses', {}), ensure_ascii=False)}

Format : tableau annuel par scénario avec primes, sinistres, combined ratio, résultat technique, solvabilité CIMA. Hypothèses clés explicitées."""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                return rep.contenu

            if nom == "alerte_risque_systemique":
                from core.notifications import notifications
                await notifications.envoyer_alerte_direction(
                    niveau=params["urgence"],
                    message=f"[RISQUE {params['type_risque'].upper()}] {params['description']} — Impact estimé : {params.get('impact_estime', 0):,} FCFA",
                    article="Détection automatique AgentIntelligence",
                )
                return f"Alerte {params['urgence']} envoyée à la direction — {params['type_risque']}"

            if nom == "benchmarking_marche":
                from core.orass_connector import orass
                from core.ia_client import ModeIA, ia_client
                data_interne = await orass.get_kpi(periode=params["periode"])
                prompt = f"""Compare les indicateurs de cette compagnie d'assurance avec les benchmarks du marché CIMA.

Données internes ({params['periode']}) :
{json.dumps(data_interne, ensure_ascii=False, indent=2)}

Indicateurs à analyser : {', '.join(params.get('indicateurs', ['combined_ratio', 'loss_ratio', 'taux_renouvellement', 'solvabilite']))}

Fournir : positionnement marché, points forts/faibles vs pairs, recommandations pour améliorer le positionnement."""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
                return rep.contenu

            if nom == "stress_test_portefeuille":
                # Paramètres choc par scénario (déterministe — Art. 337-1 CIMA)
                _CHOCS: dict[str, dict] = {
                    "solvency_ii":          {"sinistres_plus_pct": 20, "fonds_propres_moins_pct": 0,  "pm_plus_pct": 5},
                    "catastrophe_naturelle": {"sinistres_plus_pct": 50, "fonds_propres_moins_pct": 10, "pm_plus_pct": 0},
                    "choc_taux_200bp":       {"sinistres_plus_pct": 0,  "fonds_propres_moins_pct": 15, "pm_plus_pct": 10},
                    "epidemie":              {"sinistres_plus_pct": 80, "fonds_propres_moins_pct": 0,  "pm_plus_pct": 15},
                    "recession":             {"sinistres_plus_pct": 15, "fonds_propres_moins_pct": 20, "pm_plus_pct": 0},
                }
                fp = params.get("fonds_propres", 0)
                pm = params.get("pm_totales", 0)
                primes = params.get("primes_annuelles", 0)
                sinistres = params.get("sinistres_annuels", 0)
                resultats = []
                for scenario in params.get("scenarios", ["solvency_ii"]):
                    choc = _CHOCS.get(scenario, {"sinistres_plus_pct": 20, "fonds_propres_moins_pct": 0, "pm_plus_pct": 0})
                    sinistres_stresses = round(sinistres * (1 + choc["sinistres_plus_pct"] / 100))
                    fp_stresses = round(fp * (1 - choc["fonds_propres_moins_pct"] / 100))
                    pm_stressees = round(pm * (1 + choc["pm_plus_pct"] / 100))
                    # Marge solvabilité stressée (approximation Art. 337-1)
                    marge_requise = max(primes * 0.18, sinistres_stresses * 0.26)
                    solvabilite_stressee = round(fp_stresses / max(marge_requise, 1) * 100, 1)
                    resultats.append({
                        "scenario": scenario,
                        "chocs_appliques": choc,
                        "sinistres_stresses_fcfa": sinistres_stresses,
                        "fp_stresses_fcfa": fp_stresses,
                        "pm_stressees_fcfa": pm_stressees,
                        "solvabilite_post_stress_pct": solvabilite_stressee,
                        "conforme_cima": solvabilite_stressee >= 100,
                        "statut": "RESILIENT" if solvabilite_stressee >= 120 else "ADEQUATE" if solvabilite_stressee >= 100 else "INSUFFISANT",
                    })
                return json.dumps({
                    "base_legale": "Art. 337-1 Code CIMA — Tests de résistance",
                    "resultats_scenarios": resultats,
                    "scenarios_critiques": [r["scenario"] for r in resultats if not r["conforme_cima"]],
                }, ensure_ascii=False)

            if nom == "predire_churn_portefeuille":
                from core.orass_connector import orass
                from core.ia_client import ModeIA, ia_client
                # Données historiques déterministes
                data = await orass.get_donnees_churn(
                    periode=params["periode"],
                    branche=params.get("branche", "tous"),
                )
                horizon = params.get("horizon_mois", 6)
                # Calcul taux churn observé par segment
                segments = data.get("segments", [])
                predictions = []
                for seg in segments:
                    taux_obs = seg.get("taux_resiliation_historique", 0.10)
                    # Facteurs aggravants
                    facteur = 1.0
                    if seg.get("retards_paiement_pct", 0) > 0.15: facteur += 0.2
                    if seg.get("nb_sinistres_moy", 0) > 2: facteur += 0.15
                    if seg.get("anciennete_moy_ans", 5) < 2: facteur += 0.10
                    taux_pred = min(taux_obs * facteur, 1.0)
                    nb_polices = seg.get("nb_polices", 0)
                    predictions.append({
                        "segment": seg.get("nom", "N/A"),
                        "nb_polices": nb_polices,
                        "taux_churn_observe_pct": round(taux_obs * 100, 1),
                        "taux_churn_predit_pct": round(taux_pred * 100, 1),
                        "polices_a_risque": round(nb_polices * taux_pred),
                        "prime_a_risque_fcfa": round(nb_polices * taux_pred * seg.get("prime_moyenne", 0)),
                        "risque": "CRITIQUE" if taux_pred > 0.25 else "ÉLEVÉ" if taux_pred > 0.15 else "MODÉRÉ",
                    })

                result = {
                    "periode": params["periode"],
                    "horizon_mois": horizon,
                    "predictions_segments": predictions,
                    "polices_a_risque_total": sum(p["polices_a_risque"] for p in predictions),
                    "prime_a_risque_total_fcfa": sum(p["prime_a_risque_fcfa"] for p in predictions),
                }

                if params.get("avec_recommandations"):
                    prompt = f"""Sur la base de ces prédictions de churn portefeuille assurance, formule 5 recommandations concrètes de rétention.
Prédictions :
{json.dumps(predictions, ensure_ascii=False, indent=2)}

Horizon : {horizon} mois. Recommandations : actions ciblées par segment, offres de fidélisation, renouvellements proactifs."""
                    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
                    result["recommandations_ia"] = rep.contenu

                return json.dumps(result, ensure_ascii=False)

            if nom == "dashboard_quotidien":
                from core.orass_connector import orass
                from core.ia_client import ModeIA, ia_client
                date_rapport = params.get("date_rapport", date.today().isoformat())
                # KPI du jour
                kpi_jour = await orass.get_kpi(periode=date_rapport)
                kpi_hier = await orass.get_kpi(periode=(date.fromisoformat(date_rapport) - timedelta(days=1)).isoformat())
                kpi_mois = await orass.get_kpi(periode=date_rapport[:7])  # YYYY-MM
                # Calcul variations
                def variation(actuel, precedent):
                    if not precedent: return 0
                    return round((actuel - precedent) / precedent * 100, 1)
                dashboard = {
                    "date": date_rapport,
                    "primes_jour": kpi_jour.get("primes_acquises", 0),
                    "primes_variation_j1_pct": variation(kpi_jour.get("primes_acquises", 0), kpi_hier.get("primes_acquises", 0)),
                    "sinistres_ouverts": kpi_jour.get("nb_sinistres_ouverts", 0),
                    "validations_en_attente": kpi_jour.get("nb_validations_attente", 0),
                    "taux_renouvellement_mois_pct": kpi_mois.get("taux_renouvellement", 0),
                    "combined_ratio_mois_pct": kpi_mois.get("combined_ratio", 0),
                    "alertes": [],
                }
                # Alertes automatiques
                if dashboard["sinistres_ouverts"] > 50:
                    dashboard["alertes"].append(f"Volume sinistres élevé : {dashboard['sinistres_ouverts']} dossiers ouverts")
                if dashboard["validations_en_attente"] > 10:
                    dashboard["alertes"].append(f"{dashboard['validations_en_attente']} validations en attente — action requise")
                if dashboard["combined_ratio_mois_pct"] > 100:
                    dashboard["alertes"].append(f"Combined ratio > 100% : {dashboard['combined_ratio_mois_pct']}%")

                if params.get("destinataires") and params.get("format") != "json":
                    from core.notifications import notifications
                    message = f"""📊 Dashboard {date_rapport} | Primes : {dashboard['primes_jour']:,} FCFA ({'+' if dashboard['primes_variation_j1_pct'] >= 0 else ''}{dashboard['primes_variation_j1_pct']}% vs J-1) | Sinistres ouverts : {dashboard['sinistres_ouverts']} | Combined ratio mois : {dashboard['combined_ratio_mois_pct']}%""".replace(",", " ")
                    for dest in params["destinataires"]:
                        await notifications.envoyer(canal="email", destinataire=dest, message=message)

                return json.dumps(dashboard, ensure_ascii=False)

            return f"Outil '{nom}' non reconnu"
        except Exception as e:
            logger.error(f"[AgentIntelligence] Erreur outil {nom} : {e}")
            return f"ERREUR {nom} : {e}"
