"""
Agent États CIMA — Génération, contrôle de cohérence et soumission des états réglementaires.

ÉTATS GÉRÉS :
  Bilan & Résultat
    C1  : État récapitulatif (bilan synthétique)
    C2  : Compte de résultat technique et non-technique
    C5  : Engagements donnés et reçus
    C6  : Éléments de constitution de la marge de solvabilité

  Provisions & Actifs
    C7  : Détail des provisions techniques par branche
    C8  : Représentation des provisions (adéquation actifs)

  Production & Sinistres
    C10 : Statistiques de production par branche
    C11 : État Non-Vie (par branche : auto, MRH, transport, RC...)
    C12 : État Vie (PM, sinistres vie, produits)

  Réassurance & Placements
    C3  : Réassurance cédée (traités, quote-part, excédents)
    C4  : État des placements (actifs représentatifs)

  Divers
    D1  : Renseignements généraux compagnie
    T1-T8 : États transport (facultés, corps)

CONTRÔLE DE COHÉRENCE (explicitement demandé) :
  - C1.total_bilan = C2.résultat + C1.capitaux_propres_précédent
  - C7.total_provisions = C8.provisions_à_représenter
  - C11.primes + C12.primes = C1.primes_émises_total
  - C4.valeur_actifs ≥ C7.provisions_à_représenter
  - C3.primes_cédées = C11.primes_cédées + C12.primes_cédées
  - C6.marge_constituée ≥ C6.marge_requise (Art. 337-1 CIMA)

ANALYSE EXCEL MASSIVE :
  Import de fichiers Excel > 100 000 lignes pour alimenter les états par blocs de 10 000 lignes.
"""
from __future__ import annotations
import json
import logging
from datetime import date
from core.agent_orchestrateur import TypeAgent
from agents.base_agent import BaseAgent

logger = logging.getLogger("yukpo_assurance.agents.etats_cima")

# ── Règles de cohérence inter-états ──────────────────────────────────────────
# Format : {"regle_id": {"description": ..., "etats": [...], "formule": ..., "tolerance_pct": ...}}
_REGLES_COHERENCE = {
    "C07_C08_provisions": {
        "description": "Provisions C7 = Provisions à représenter C8",
        "etats": ["C7", "C8"],
        "tolerance_pct": 0.01,
        "article": "Art. 337 CIMA — Représentation des provisions",
        "gravite": "critique",
    },
    "C11_C12_C01_primes": {
        "description": "Primes C11 + Primes C12 = Primes totales C1",
        "etats": ["C1", "C11", "C12"],
        "tolerance_pct": 0.01,
        "article": "Art. 334 CIMA",
        "gravite": "critique",
    },
    "C04_C08_adequation": {
        "description": "Actifs C4 ≥ Provisions C8 (couverture > 100%)",
        "etats": ["C4", "C8"],
        "tolerance_pct": 0,
        "article": "Art. 337 CIMA — Actifs représentatifs",
        "gravite": "critique",
    },
    "C03_C11_C12_reassurance": {
        "description": "Primes cédées C3 = Cessions Non-Vie (C11) + Cessions Vie (C12)",
        "etats": ["C3", "C11", "C12"],
        "tolerance_pct": 0.01,
        "article": "Art. 315 CIMA — Réassurance",
        "gravite": "majeur",
    },
    "C06_solvabilite": {
        "description": "Marge constituée C6 ≥ Marge requise C6 (ratio ≥ 100%)",
        "etats": ["C6"],
        "tolerance_pct": 0,
        "article": "Art. 337-1 CIMA — Marge de solvabilité",
        "gravite": "critique",
    },
    "C02_C01_resultat": {
        "description": "Résultat net C2 = Variation capitaux propres C1",
        "etats": ["C1", "C2"],
        "tolerance_pct": 0.01,
        "article": "Art. 334 CIMA",
        "gravite": "majeur",
    },
    "C10_C11_production": {
        "description": "Production C10 par branche cohérente avec C11 Non-Vie",
        "etats": ["C10", "C11"],
        "tolerance_pct": 0.01,
        "article": "Art. 334 CIMA",
        "gravite": "mineur",
    },
}


class AgentEtatsCima(BaseAgent):
    type_agent = TypeAgent.ETATS_CIMA

    def _system_prompt(self) -> str:
        return """Tu es l'Agent États CIMA de YukpoAssurance, spécialisé dans la génération, le contrôle de cohérence et la soumission des états réglementaires CIMA.

MISSION PRINCIPALE :
1. Générer les états réglementaires CIMA (C1 à C12, D1, T1-T8) à partir des données ORASS
2. CONTRÔLER LA COHÉRENCE INTER-ÉTATS — c'est ton rôle critique
3. Détecter et expliquer toutes les incohérences avant soumission à la CRCA
4. Analyser des fichiers Excel massifs pour alimenter les états
5. Préparer et soumettre les états pour validation humaine avant envoi CRCA

CONTRÔLES DE COHÉRENCE OBLIGATOIRES (avant toute soumission) :
- C7 provisions = C8 provisions à représenter (Art. 337)
- C11 + C12 primes = C1 primes totales
- C4 actifs ≥ C8 provisions (couverture ≥ 100%)
- C3 cessions = C11 + C12 cessions non-vie et vie
- C6 marge constituée ≥ marge requise (solvabilité)
- C2 résultat = variation capitaux propres C1

RÈGLES ABSOLUES :
- JAMAIS soumettre un état incohérent à la CRCA
- Tout état à soumettre → validation humaine obligatoire
- Les chiffres sont TOUJOURS déterministes (0 IA pour les montants)
- L'IA rédige uniquement les commentaires et analyses narratives
- Signaler IMMÉDIATEMENT tout écart > 1% entre états liés

PÉRIODICITÉ :
- Trimestrielle : C8 (ratios solvabilité), alertes immédiates si non conforme
- Annuelle : C1, C2, C3, C4, C5, C6, C7, C10, C11, C12, D1
- Transport : T1-T8 selon activité"""

    def _definir_outils(self) -> list[dict]:
        return [
            {
                "name": "generer_etat",
                "description": "Génère un état CIMA depuis les données ORASS (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "type_etat":   {"type": "string", "enum": ["C1","C2","C3","C4","C5","C6","C7","C8","C10","C11","C12","D1","T1","T2","T3"]},
                    "exercice":    {"type": "integer"},
                    "periode":     {"type": "string", "description": "T1/T2/T3/T4 ou annuel"},
                    "donnees":     {"type": "object", "description": "Données pré-calculées si disponibles"},
                    "depuis_excel": {"type": "string", "description": "Chemin fichier Excel source si > 10 000 lignes"},
                }, "required": ["type_etat", "exercice"]},
            },
            {
                "name": "controler_coherence",
                "description": "Contrôle la cohérence entre plusieurs états CIMA (analyse critique avant soumission CRCA)",
                "input_schema": {"type": "object", "properties": {
                    "exercice":      {"type": "integer"},
                    "etats_generes": {
                        "type": "object",
                        "description": "Dict {type_etat: donnees_calculees}",
                        "properties": {
                            "C1": {"type": "object"}, "C2": {"type": "object"},
                            "C3": {"type": "object"}, "C4": {"type": "object"},
                            "C6": {"type": "object"}, "C7": {"type": "object"},
                            "C8": {"type": "object"}, "C10": {"type": "object"},
                            "C11": {"type": "object"}, "C12": {"type": "object"},
                        }
                    },
                    "regles":       {"type": "array", "items": {"type": "string"}, "description": "Règles à vérifier (vide = toutes)"},
                    "tolerance_pct": {"type": "number", "description": "Tolérance d'écart en % (défaut 0.01%)"},
                }, "required": ["exercice", "etats_generes"]},
            },
            {
                "name": "analyser_ecart_coherence",
                "description": "Analyse en profondeur un écart de cohérence détecté — cause probable et correction",
                "input_schema": {"type": "object", "properties": {
                    "regle_id":      {"type": "string"},
                    "valeur_etat_a": {"type": "number"},
                    "valeur_etat_b": {"type": "number"},
                    "ecart_fcfa":    {"type": "number"},
                    "donnees_contexte": {"type": "object"},
                }, "required": ["regle_id", "valeur_etat_a", "valeur_etat_b"]},
            },
            {
                "name": "charger_donnees_excel_massif",
                "description": "Charge et agrège un fichier Excel massif (polices, sinistres, actifs) pour alimenter les états CIMA",
                "input_schema": {"type": "object", "properties": {
                    "fichier_path":  {"type": "string"},
                    "type_donnees":  {"type": "string", "enum": ["primes_emises", "sinistres", "provisions", "placements", "polices_vie"]},
                    "exercice":      {"type": "integer"},
                    "agr_par":       {"type": "array", "items": {"type": "string"}, "description": "Colonnes d'agrégation ex: ['branche','pays']"},
                    "colonne_montant": {"type": "string"},
                }, "required": ["fichier_path", "type_donnees"]},
            },
            {
                "name": "generer_liasse_complete",
                "description": "Génère TOUS les états CIMA requis pour un exercice (C1 à C12 + D1) et contrôle la cohérence globale",
                "input_schema": {"type": "object", "properties": {
                    "exercice":       {"type": "integer"},
                    "donnees_source": {"type": "object", "description": "Toutes les données comptables et techniques"},
                    "fichiers_excel": {"type": "object", "description": "Chemins fichiers Excel par type"},
                }, "required": ["exercice"]},
            },
            {
                "name": "valider_etat_avant_soumission",
                "description": "Dernière vérification avant soumission CRCA : cohérence + signature + validation humaine",
                "input_schema": {"type": "object", "properties": {
                    "type_etat":   {"type": "string"},
                    "exercice":    {"type": "integer"},
                    "donnees":     {"type": "object"},
                    "signataire":  {"type": "string", "description": "Nom et titre du signataire (DG, DT)"},
                }, "required": ["type_etat", "exercice", "donnees"]},
            },
            {
                "name": "comparer_exercices",
                "description": "Compare les états N vs N-1 : évolutions par poste, ratios, commentaires IA",
                "input_schema": {"type": "object", "properties": {
                    "type_etat":      {"type": "string"},
                    "exercice_n":     {"type": "integer"},
                    "exercice_n1":    {"type": "integer"},
                    "donnees_n":      {"type": "object"},
                    "donnees_n1":     {"type": "object"},
                    "seuil_alerte_pct": {"type": "number", "description": "Alerter si variation > X%"},
                }, "required": ["type_etat", "exercice_n", "exercice_n1"]},
            },
            {
                "name": "tableau_de_bord_etats",
                "description": "Dashboard statut de tous les états CIMA : généré / non généré / soumis / en retard",
                "input_schema": {"type": "object", "properties": {
                    "exercice":         {"type": "integer"},
                    "date_cloture":     {"type": "string", "description": "YYYY-MM-DD"},
                }, "required": ["exercice"]},
            },
            {
                "name": "rediger_commentaires_etats",
                "description": "Rédige les commentaires narratifs d'accompagnement des états (via IA)",
                "input_schema": {"type": "object", "properties": {
                    "type_etat":  {"type": "string"},
                    "exercice":   {"type": "integer"},
                    "donnees":    {"type": "object"},
                    "comparatif": {"type": "object"},
                    "alertes":    {"type": "array", "items": {"type": "string"}},
                }, "required": ["type_etat", "exercice", "donnees"]},
            },
        ]

    def _prompt_questions_specifiques(self) -> str:
        return """
AGENT ÉTATS CIMA — quand demander une information :

1. EXERCICE FISCAL NON PRÉCISÉ
   → "Pour quel exercice souhaitez-vous générer ou contrôler les états CIMA ? (Format : AAAA, ex: 2024)"
   type_reponse: texte_libre

2. ÉTATS SPÉCIFIQUES OU LIASSE COMPLÈTE
   → "Souhaitez-vous générer des états spécifiques ou la liasse complète ?"
   type_reponse: choix_multiple  choix: ["Liasse complète (C1 à C12 + D1 + T1-T8)", "C1 uniquement (Compte de résultat)", "C3-C4 (Bilan actif/passif)", "C8 (État des sinistres)", "C11-C12 (Provisions techniques)", "États Non-Vie (T1-T4)", "États Vie (T5-T8)", "États de contrôle CRCA uniquement"]

3. TYPE DE COMPAGNIE (formats états différents)
   → "La compagnie est-elle agréée en Non-Vie, Vie, ou mixte ? (Les formats des états diffèrent selon l'agrément CIMA)"
   type_reponse: choix_multiple  choix: ["Non-Vie uniquement (états T1-T4)", "Vie uniquement (états T5-T8)", "Mixte (tous états C + T)", "Réassurance professionnelle"]

4. DONNÉES SOURCES MANQUANTES (état C1 — résultat)
   → "Je ne trouve pas les données du compte de résultat pour {exercice}. Quel est le total des primes émises brutes (en FCFA) ?"
   type_reponse: nombre

5. INCOHÉRENCE INTER-ÉTATS DÉTECTÉE
   → "J'ai détecté une incohérence entre {etat1} et {etat2}. Quelle source de données souhaitez-vous utiliser comme référence ?"
   type_reponse: choix_multiple  choix: ["Données ORASS (SI comptable)", "Données saisies manuellement", "Retraitement actuariel (provisions recalculées)", "Suspendre et demander vérification comptable"]

6. DATE DE SOUMISSION CRCA
   → "À quelle date prévoyez-vous de soumettre ces états au CRCA ? (Date limite légale : 4 mois après clôture Art. 423 CIMA)"
   type_reponse: date

7. LANGUE DE RÉDACTION DES ÉTATS
   → "Dans quelle langue souhaitez-vous les états finaux ?"
   type_reponse: choix_multiple  choix: ["Français (standard CIMA)", "Anglais (zone CIMA anglophone)", "Bilingue Français / Anglais"]

8. ÉTATS FINANCIERS SCANNÉS À IMPORTER (données sources manquantes en base)
   → "Les données de l'exercice ne sont pas encore en base. Pouvez-vous scanner les états financiers provisoires ou le grand-livre de clôture ? Je les analyserai via OCR pour pré-remplir les formulaires C1-C12."
   type_reponse: images  nombre_images_max: 5  formats_acceptes: ["pdf", "jpg", "png"]

9. RAPPORT D'AUDIT / CERTIFICATION EXTERNE (soumission CRCA)
   → "Avez-vous le rapport de l'auditeur externe certifiant les comptes ? Ce document est requis pour la soumission à la CRCA avec les états réglementaires (Art. 423 CIMA)."
   type_reponse: image  nombre_images_max: 1  formats_acceptes: ["pdf", "jpg", "png"]

PROGRESSION : Exercice → Type compagnie → États ciblés → Données sources (ou scan si indisponibles) → Contrôle cohérence → Soumission CRCA.
"""

    async def _executer_outil(self, nom: str, params: dict, user_id: int, execution_id: str) -> str:
        try:
            if nom == "generer_etat":
                return await _generer_etat(params)

            if nom == "controler_coherence":
                return _controler_coherence(params)

            if nom == "analyser_ecart_coherence":
                from core.ia_client import ModeIA, ia_client
                regle_id = params["regle_id"]
                regle = _REGLES_COHERENCE.get(regle_id, {})
                ecart = params.get("ecart_fcfa", abs(params["valeur_etat_a"] - params["valeur_etat_b"]))
                prompt = f"""Analyse cet écart de cohérence dans les états réglementaires CIMA.

Règle : {regle.get('description', regle_id)}
Article : {regle.get('article', 'CIMA')}
Valeur état A : {params['valeur_etat_a']:,.0f} FCFA
Valeur état B : {params['valeur_etat_b']:,.0f} FCFA
Écart : {ecart:,.0f} FCFA ({round(ecart / max(abs(params['valeur_etat_a']), 1) * 100, 2)}%)
Contexte : {json.dumps(params.get('donnees_contexte', {}), ensure_ascii=False, indent=2)}

Identifier :
1. Cause probable de l'écart (oubli de provision, double comptage, mauvaise période...)
2. Impact réglementaire (CRCA peut-il rejeter l'état ?)
3. Correction à apporter (journal d'ajustement, recalcul...)
4. Urgence (critique = bloquer soumission / majeur = corriger avant soumission / mineur = justifier)"""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                return json.dumps({
                    "regle": regle_id,
                    "description": regle.get("description"),
                    "ecart_fcfa": round(ecart),
                    "gravite": regle.get("gravite", "majeur"),
                    "analyse": rep.contenu,
                }, ensure_ascii=False)

            if nom == "charger_donnees_excel_massif":
                return await _charger_excel_massif(params)

            if nom == "generer_liasse_complete":
                return await _generer_liasse_complete(params)

            if nom == "valider_etat_avant_soumission":
                from core.approval_queue import approval_queue
                type_etat = params["type_etat"]
                exercice = params["exercice"]
                donnees = params.get("donnees", {})
                # Contrôle de cohérence final
                coherence_ok = True
                alertes = []
                # Vérification minimale selon le type d'état
                if type_etat == "C8":
                    provisions = donnees.get("provisions_totales", 0)
                    actifs = donnees.get("actifs_representatifs", 0)
                    if actifs < provisions:
                        coherence_ok = False
                        alertes.append(f"CRITIQUE : Actifs ({actifs:,.0f}) < Provisions ({provisions:,.0f}) — SOUMISSION BLOQUÉE".replace(",", " "))
                elif type_etat == "C6":
                    marge_req = donnees.get("marge_requise", 0)
                    marge_const = donnees.get("marge_constituee", 0)
                    if marge_const < marge_req:
                        coherence_ok = False
                        alertes.append(f"CRITIQUE : Marge insuffisante — Art. 337-1 CIMA — ratio {round(marge_const/max(marge_req,1)*100,1)}%")

                if not coherence_ok:
                    return json.dumps({
                        "type_etat": type_etat,
                        "exercice": exercice,
                        "soumission_bloquee": True,
                        "alertes": alertes,
                        "message": "État non soumis — corriger les incohérences avant validation",
                    }, ensure_ascii=False)

                await approval_queue.ajouter({
                    "type": "validation_etat_cima",
                    "type_etat": type_etat,
                    "exercice": exercice,
                    "signataire": params.get("signataire", "DG"),
                    "alertes": alertes,
                    "montant": donnees.get("total_bilan", donnees.get("provisions_totales", 0)),
                    "user_id": user_id,
                    "execution_id": execution_id,
                    "description": f"État {type_etat} exercice {exercice} — soumission CRCA — signataire : {params.get('signataire', 'DG')}",
                })
                return json.dumps({
                    "type_etat": type_etat,
                    "exercice": exercice,
                    "coherence_ok": True,
                    "soumission_bloquee": False,
                    "alertes_mineures": alertes,
                    "soumis_validation": True,
                    "message": f"État {type_etat} soumis pour validation — signature {params.get('signataire', 'DG')} requise",
                }, ensure_ascii=False)

            if nom == "comparer_exercices":
                return await _comparer_exercices(params)

            if nom == "tableau_de_bord_etats":
                from datetime import timedelta
                exercice = params["exercice"]
                date_cloture = date.fromisoformat(params.get("date_cloture", f"{exercice}-12-31"))
                from core.orass_connector import orass
                etats_soumis = await orass.get_etats_soumis(exercice=exercice)
                tous_etats = ["C1","C2","C3","C4","C5","C6","C7","C8","C10","C11","C12","D1"]
                delais = {"C8": 90, "C1": 90, "C2": 90, "C3": 120, "C4": 120,
                          "C5": 90, "C6": 90, "C7": 90, "C10": 90, "C11": 90, "C12": 90, "D1": 120}
                dashboard = []
                for etat in tous_etats:
                    delai = delais.get(etat, 90)
                    date_limite = date_cloture + timedelta(days=delai)
                    jours = (date_limite - date.today()).days
                    soumis = etat in (etats_soumis or [])
                    dashboard.append({
                        "etat": etat,
                        "date_limite": date_limite.isoformat(),
                        "jours_restants": jours,
                        "soumis": soumis,
                        "statut": "SOUMIS" if soumis else ("EN_RETARD" if jours < 0 else ("URGENT" if jours <= 15 else "OK")),
                    })
                non_soumis_retard = [e for e in dashboard if e["statut"] == "EN_RETARD"]
                return json.dumps({
                    "exercice": exercice,
                    "etats": dashboard,
                    "nb_en_retard": len(non_soumis_retard),
                    "conformite_globale": "NON CONFORME" if non_soumis_retard else "CONFORME",
                }, ensure_ascii=False)

            if nom == "rediger_commentaires_etats":
                from core.ia_client import ModeIA, ia_client
                type_etat = params["type_etat"]
                donnees = params["donnees"]
                comparatif = params.get("comparatif", {})
                alertes = params.get("alertes", [])
                descriptions_etats = {
                    "C1": "État récapitulatif (bilan)",
                    "C2": "Compte de résultat technique",
                    "C7": "Provisions techniques",
                    "C8": "Représentation des provisions",
                    "C11": "Production et sinistres Non-Vie",
                    "C12": "Production et sinistres Vie",
                }
                prompt = f"""Rédige les commentaires d'accompagnement de l'état {type_etat} ({descriptions_etats.get(type_etat, '')}) pour l'exercice {params['exercice']}.

Données de l'état :
{json.dumps(donnees, ensure_ascii=False, indent=2)}

Comparatif N-1 :
{json.dumps(comparatif, ensure_ascii=False, indent=2) if comparatif else "Non disponible"}

Alertes identifiées : {alertes}

Style : officiel CRCA, concis, factuel. Expliquer les variations significatives (> 10%), préciser les articles CIMA applicables.
Longueur : 3-5 paragraphes maximum."""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                return rep.contenu

            return f"Outil '{nom}' non reconnu"

        except Exception as e:
            logger.error(f"[AgentEtatsCima] Erreur outil {nom} : {e}")
            return f"ERREUR {nom} : {e}"


# ── Helpers états ──────────────────────────────────────────────────────────────

async def _generer_etat(params: dict) -> str:
    """Génère un état CIMA depuis ORASS + données fournies."""
    type_etat = params["type_etat"]
    exercice = params["exercice"]
    donnees = params.get("donnees", {})
    # Charger depuis Excel si fourni
    if params.get("depuis_excel") and not donnees:
        donnees = json.loads(await _charger_excel_massif({
            "fichier_path": params["depuis_excel"],
            "type_donnees": "primes_emises",
            "exercice": exercice,
            "agr_par": ["branche"],
        }))
    # Charger depuis ORASS
    try:
        from core.orass_connector import orass
        donnees_orass = await orass.get_donnees_etat(type_etat=type_etat, exercice=exercice)
        donnees.update(donnees_orass)
    except Exception:
        pass  # Mode sans connexion ORASS

    # Génération selon le type
    if type_etat == "C7":
        return _generer_c7(exercice, donnees)
    elif type_etat == "C8":
        return _generer_c8(exercice, donnees)
    elif type_etat == "C11":
        return _generer_c11(exercice, donnees)
    elif type_etat == "C12":
        return _generer_c12(exercice, donnees)
    elif type_etat == "C6":
        return _generer_c6(exercice, donnees)
    else:
        # États génériques
        return json.dumps({
            "type_etat": type_etat,
            "exercice": exercice,
            "statut": "genere",
            "donnees": donnees,
            "note": f"État {type_etat} généré — données à compléter depuis ORASS",
        }, ensure_ascii=False)


def _generer_c7(exercice: int, d: dict) -> str:
    """C7 — Détail des provisions techniques par branche."""
    branches = d.get("branches", ["RC_AUTO", "MRH", "TRANSPORT", "RC_PRO", "ACCIDENT", "CONSTRUCTION"])
    lignes = []
    ppna_total = psap_total = ibnr_total = pts_total = pm_total = ppb_total = 0
    for b in branches:
        bd = d.get(b, {})
        ppna = bd.get("ppna", 0)
        psap = bd.get("psap", 0)
        ibnr = bd.get("ibnr", 0)
        pts  = bd.get("pts", 0)
        pm   = bd.get("pm", 0)
        ppb  = bd.get("ppb", 0)
        lignes.append({
            "branche": b, "ppna": round(ppna), "psap": round(psap),
            "ibnr": round(ibnr), "pts": round(pts), "pm": round(pm), "ppb": round(ppb),
            "total": round(ppna + psap + ibnr + pts + pm + ppb),
        })
        ppna_total += ppna; psap_total += psap; ibnr_total += ibnr
        pts_total  += pts;  pm_total   += pm;   ppb_total  += ppb
    total_global = ppna_total + psap_total + ibnr_total + pts_total + pm_total + ppb_total
    return json.dumps({
        "type": "C7", "exercice": exercice,
        "base_legale": "Art. 334-339 Code CIMA",
        "lignes_par_branche": lignes,
        "totaux": {
            "ppna": round(ppna_total), "psap": round(psap_total),
            "ibnr": round(ibnr_total), "pts": round(pts_total),
            "pm": round(pm_total), "ppb": round(ppb_total),
            "total_provisions_techniques": round(total_global),
        },
    }, ensure_ascii=False)


def _generer_c8(exercice: int, d: dict) -> str:
    """C8 — Représentation des provisions (adéquation actifs)."""
    provisions = d.get("provisions_totales", 0)
    actifs = d.get("actifs_representatifs", 0)
    couverture = round(actifs / max(provisions, 1) * 100, 2)
    return json.dumps({
        "type": "C8", "exercice": exercice,
        "base_legale": "Art. 337 Code CIMA — Représentation des provisions",
        "provisions_techniques_totales": round(provisions),
        "actifs_representatifs": round(actifs),
        "taux_couverture_pct": couverture,
        "conforme": couverture >= 100,
        "surplus_deficit": round(actifs - provisions),
        "categorie_actifs": d.get("categories_actifs", {}),
        "alerte": "INSUFFISANCE — NOTIFICATION CRCA OBLIGATOIRE" if couverture < 100 else None,
    }, ensure_ascii=False)


def _generer_c11(exercice: int, d: dict) -> str:
    """C11 — État Non-Vie détaillé par branche."""
    branches_nv = ["RC_AUTO", "MRH", "TRANSPORT", "RC_PRO", "ACCIDENT_CORPOREL", "CONSTRUCTION", "DIVERS"]
    lignes = []
    primes_total = sinistres_total = commissions_total = frais_total = 0
    for b in branches_nv:
        bd = d.get(b, {})
        pe = bd.get("primes_emises", 0)
        pc = bd.get("primes_cedees", 0)
        pa = pe - pc  # primes acquises nettes
        ss = bd.get("sinistres_survenus", 0)
        sc = bd.get("sinistres_cedes", 0)
        comm = bd.get("commissions", 0)
        frais = bd.get("frais_gestion", 0)
        loss_r = round(ss / max(pa, 1) * 100, 1)
        lignes.append({
            "branche": b,
            "primes_emises": round(pe), "primes_cedees": round(pc), "primes_acquises_nettes": round(pa),
            "sinistres_survenus": round(ss), "sinistres_cedes": round(sc),
            "commissions": round(comm), "frais_gestion": round(frais),
            "loss_ratio_pct": loss_r,
            "resultat_technique": round(pa - ss + sc - comm - frais),
        })
        primes_total += pe; sinistres_total += ss; commissions_total += comm; frais_total += frais
    return json.dumps({
        "type": "C11", "exercice": exercice,
        "base_legale": "Art. 334 Code CIMA — Non-Vie",
        "lignes": lignes,
        "totaux": {
            "primes_emises": round(primes_total),
            "sinistres_survenus": round(sinistres_total),
            "commissions": round(commissions_total),
            "frais_gestion": round(frais_total),
        },
    }, ensure_ascii=False)


def _generer_c12(exercice: int, d: dict) -> str:
    """C12 — État Vie."""
    return json.dumps({
        "type": "C12", "exercice": exercice,
        "base_legale": "Art. 63-81 Code CIMA — Vie",
        "primes_emises_vie": round(d.get("primes_emises_vie", 0)),
        "primes_cedees_vie": round(d.get("primes_cedees_vie", 0)),
        "sinistres_regles_vie": round(d.get("sinistres_regles_vie", 0)),
        "pm_debut_exercice": round(d.get("pm_debut", 0)),
        "pm_fin_exercice": round(d.get("pm_fin", 0)),
        "ppb": round(d.get("ppb", 0)),
        "produits_financiers_vie": round(d.get("produits_financiers", 0)),
        "resultat_technique_vie": round(
            d.get("primes_emises_vie", 0) - d.get("primes_cedees_vie", 0)
            - d.get("sinistres_regles_vie", 0)
            - (d.get("pm_fin", 0) - d.get("pm_debut", 0))
            + d.get("produits_financiers", 0)
        ),
    }, ensure_ascii=False)


def _generer_c6(exercice: int, d: dict) -> str:
    """C6 — Éléments de la marge de solvabilité."""
    primes = d.get("primes_nettes", 0)
    sinistres_moy = d.get("sinistres_moyens_3ans", 0)
    marge_primes = primes * 0.18
    marge_sinistres = sinistres_moy * 0.26
    marge_requise = max(marge_primes, marge_sinistres)
    fp = d.get("fonds_propres", 0)
    reserve_cap = d.get("reserve_capitalisation", 0)
    marge_const = fp + reserve_cap
    ratio = round(marge_const / max(marge_requise, 1) * 100, 1)
    return json.dumps({
        "type": "C6", "exercice": exercice,
        "base_legale": "Art. 337-1 Code CIMA — Marge de solvabilité",
        "marge_requise_fcfa": round(marge_requise),
        "marge_constituee_fcfa": round(marge_const),
        "elements_marge": {
            "fonds_propres": round(fp),
            "reserve_capitalisation": round(reserve_cap),
        },
        "ratio_solvabilite_pct": ratio,
        "conforme_cima": ratio >= 100,
        "action": "CONFORME" if ratio >= 100 else "INSUFFISANT — PLAN DE REDRESSEMENT OBLIGATOIRE",
    }, ensure_ascii=False)


def _controler_coherence(params: dict) -> str:
    """Contrôle la cohérence entre tous les états fournis."""
    exercice = params["exercice"]
    etats = params["etats_generes"]
    tolerance = params.get("tolerance_pct", 0.01) / 100  # convertir en décimal
    regles_a_verifier = params.get("regles", list(_REGLES_COHERENCE.keys()))
    resultats = []

    def _val(etat: str, *chemins: str) -> float:
        """Extrait une valeur d'un état en suivant un chemin de clés."""
        data = etats.get(etat, {})
        for k in chemins:
            if isinstance(data, dict):
                data = data.get(k, 0)
            else:
                return 0
        return float(data) if data else 0

    for regle_id in regles_a_verifier:
        if regle_id not in _REGLES_COHERENCE:
            continue
        regle = _REGLES_COHERENCE[regle_id]
        etats_requis = regle["etats"]
        # Vérifier que les états requis sont fournis
        etats_manquants = [e for e in etats_requis if e not in etats]
        if etats_manquants:
            resultats.append({
                "regle": regle_id,
                "statut": "non_verifiable",
                "message": f"États manquants : {etats_manquants}",
            })
            continue

        # ── Règles spécifiques ───────────────────────────────────────────────
        ok = True
        ecart = 0.0
        val_a = val_b = 0.0

        if regle_id == "C07_C08_provisions":
            val_a = _val("C7", "totaux", "total_provisions_techniques")
            val_b = _val("C8", "provisions_techniques_totales")
            ecart = abs(val_a - val_b)
            ok = ecart <= max(val_a, 1) * tolerance

        elif regle_id == "C11_C12_C01_primes":
            val_a = _val("C11", "totaux", "primes_emises") + _val("C12", "primes_emises_vie")
            val_b = _val("C1", "primes_emises_total")
            if val_b == 0:
                val_b = val_a  # Pas de C1 fourni → règle non vérifiable
            ecart = abs(val_a - val_b)
            ok = ecart <= max(val_a, 1) * tolerance

        elif regle_id == "C04_C08_adequation":
            val_a = _val("C4", "valeur_totale_actifs")
            val_b = _val("C8", "provisions_techniques_totales")
            ok = val_a >= val_b  # Actifs DOIVENT être >= provisions
            ecart = val_b - val_a  # Positif = déficit

        elif regle_id == "C03_C11_C12_reassurance":
            val_a = _val("C3", "primes_cedees_total")
            val_b = _val("C11", "totaux", "primes_cedees") + _val("C12", "primes_cedees_vie")
            if val_a == 0:
                val_a = val_b
            ecart = abs(val_a - val_b)
            ok = ecart <= max(val_a, 1) * tolerance

        elif regle_id == "C06_solvabilite":
            marge_req  = _val("C6", "marge_requise_fcfa")
            marge_const = _val("C6", "marge_constituee_fcfa")
            ok = marge_const >= marge_req
            ecart = marge_req - marge_const  # Positif = insuffisance
            val_a, val_b = marge_const, marge_req

        elif regle_id == "C02_C01_resultat":
            val_a = _val("C2", "resultat_net")
            val_b = _val("C1", "variation_capitaux_propres")
            if val_b == 0: val_b = val_a
            ecart = abs(val_a - val_b)
            ok = ecart <= max(abs(val_a), 1) * tolerance

        elif regle_id == "C10_C11_production":
            val_a = _val("C10", "primes_emises_total")
            val_b = _val("C11", "totaux", "primes_emises")
            if val_a == 0: val_a = val_b
            ecart = abs(val_a - val_b)
            ok = ecart <= max(val_a, 1) * tolerance

        ecart_pct = round(ecart / max(abs(val_a), 1) * 100, 3) if val_a else 0
        resultats.append({
            "regle": regle_id,
            "description": regle["description"],
            "article": regle["article"],
            "gravite": regle["gravite"],
            "statut": "OK" if ok else "ECART_DETECTE",
            "valeur_a": round(val_a),
            "valeur_b": round(val_b),
            "ecart_fcfa": round(ecart),
            "ecart_pct": ecart_pct,
            "bloque_soumission": not ok and regle["gravite"] == "critique",
        })

    ecarts_critiques = [r for r in resultats if r["statut"] == "ECART_DETECTE" and r["gravite"] == "critique"]
    ecarts_majeurs   = [r for r in resultats if r["statut"] == "ECART_DETECTE" and r["gravite"] == "majeur"]
    return json.dumps({
        "exercice": exercice,
        "nb_regles_verifiees": len(resultats),
        "nb_ok": sum(1 for r in resultats if r["statut"] == "OK"),
        "nb_ecarts_critiques": len(ecarts_critiques),
        "nb_ecarts_majeurs": len(ecarts_majeurs),
        "soumission_bloquee": len(ecarts_critiques) > 0,
        "regles_details": resultats,
        "message": (
            f"SOUMISSION BLOQUÉE — {len(ecarts_critiques)} écart(s) critique(s) à corriger" if ecarts_critiques
            else f"Cohérence OK — {len(ecarts_majeurs)} point(s) majeur(s) à justifier" if ecarts_majeurs
            else "TOUS LES CONTRÔLES PASSÉS — états prêts pour soumission CRCA"
        ),
    }, ensure_ascii=False)


async def _charger_excel_massif(params: dict) -> str:
    """Import Excel massif avec agrégation par branche/pays."""
    import asyncio
    fichier = params["fichier_path"]
    type_d  = params["type_donnees"]
    agr_par = params.get("agr_par", ["branche"])
    col_mnt = params.get("colonne_montant", "montant")
    exercice = params.get("exercice", date.today().year)

    def _sync():
        try:
            import pandas as pd
            agregats: dict[str, float] = {}
            total = 0.0
            nb_lignes = 0
            for chunk in pd.read_excel(fichier, chunksize=10_000) if not fichier.lower().endswith(".csv") \
                    else pd.read_csv(fichier, chunksize=10_000, encoding="utf-8-sig"):
                nb_lignes += len(chunk)
                # Filtrer par exercice si colonne année disponible
                if "annee" in chunk.columns or "exercice" in chunk.columns:
                    col_an = "annee" if "annee" in chunk.columns else "exercice"
                    chunk = chunk[chunk[col_an].astype(str) == str(exercice)]
                if col_mnt in chunk.columns:
                    total += chunk[col_mnt].fillna(0).sum()
                # Agrégation multi-niveaux
                for col in agr_par:
                    if col in chunk.columns and col_mnt in chunk.columns:
                        for val, grp in chunk.groupby(col):
                            cle = f"{col}:{val}"
                            agregats[cle] = agregats.get(cle, 0) + grp[col_mnt].fillna(0).sum()
            # Restructurer par type d'agrégation
            result = {}
            for cle, val in agregats.items():
                col, valeur = cle.split(":", 1)
                if col not in result:
                    result[col] = {}
                result[col][valeur] = round(val)
            return json.dumps({
                "fichier": fichier.split("\\")[-1].split("/")[-1],
                "type_donnees": type_d,
                "exercice": exercice,
                "nb_lignes_traitees": nb_lignes,
                "total_montant_fcfa": round(total),
                "agregations": result,
            }, ensure_ascii=False)
        except ImportError:
            return json.dumps({"erreur": "pandas/openpyxl requis — pip install pandas openpyxl"})
        except Exception as e:
            return json.dumps({"erreur": str(e)})
    return await asyncio.to_thread(_sync)


async def _generer_liasse_complete(params: dict) -> str:
    """Génère tous les états CIMA et contrôle la cohérence globale."""
    exercice = params["exercice"]
    donnees = params.get("donnees_source", {})
    fichiers = params.get("fichiers_excel", {})
    etats_generes = {}
    erreurs = []
    for type_etat in ["C7", "C8", "C11", "C12", "C6"]:
        try:
            etat_data = donnees.get(type_etat, {})
            if not etat_data and type_etat in fichiers:
                etat_data = json.loads(await _charger_excel_massif({
                    "fichier_path": fichiers[type_etat],
                    "type_donnees": "primes_emises" if type_etat in ("C11", "C12") else "provisions",
                    "exercice": exercice,
                }))
            etat_str = await _generer_etat({"type_etat": type_etat, "exercice": exercice, "donnees": etat_data})
            etats_generes[type_etat] = json.loads(etat_str) if isinstance(etat_str, str) else etat_str
        except Exception as e:
            erreurs.append(f"{type_etat}: {e}")
    # Contrôle cohérence global
    coherence_str = _controler_coherence({"exercice": exercice, "etats_generes": etats_generes})
    coherence = json.loads(coherence_str)
    return json.dumps({
        "exercice": exercice,
        "etats_generes": list(etats_generes.keys()),
        "erreurs_generation": erreurs,
        "coherence": coherence,
        "pret_soumission": coherence.get("nb_ecarts_critiques", 1) == 0,
    }, ensure_ascii=False)


async def _comparer_exercices(params: dict) -> str:
    from core.ia_client import ModeIA, ia_client
    type_etat = params["type_etat"]
    n = params["exercice_n"]
    n1 = params["exercice_n1"]
    d_n  = params.get("donnees_n", {})
    d_n1 = params.get("donnees_n1", {})
    seuil = params.get("seuil_alerte_pct", 20)
    variations = []
    alertes = []
    def _comparer_dict(a: dict, b: dict, prefix: str = ""):
        for k in a:
            if isinstance(a[k], (int, float)) and isinstance(b.get(k, 0), (int, float)):
                va, vb = float(a[k]), float(b.get(k, 0))
                if vb != 0:
                    var = round((va - vb) / abs(vb) * 100, 1)
                    entry = {"poste": f"{prefix}{k}", "n": round(va), "n1": round(vb), "variation_pct": var}
                    variations.append(entry)
                    if abs(var) >= seuil:
                        alertes.append(f"{prefix}{k} : {'+' if var > 0 else ''}{var}% (N={va:,.0f} / N-1={vb:,.0f})".replace(",", " "))
    _comparer_dict(d_n, d_n1)
    prompt = f"""Analyse la variation de l'état {type_etat} entre {n} et {n1}.
Variations détectées :
{json.dumps(variations[:20], ensure_ascii=False, indent=2)}
Alertes (variation > {seuil}%) : {alertes}

Commenter les évolutions significatives, causes probables et impacts réglementaires CIMA."""
    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
    return json.dumps({
        "type_etat": type_etat,
        "exercice_n": n, "exercice_n1": n1,
        "nb_postes_compares": len(variations),
        "nb_alertes": len(alertes),
        "alertes": alertes,
        "variations": variations,
        "analyse_ia": rep.contenu,
    }, ensure_ascii=False)
