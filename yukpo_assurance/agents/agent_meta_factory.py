"""
AgentMetaFactory — Agent de création autonome de nouveaux agents IA.

CAPACITÉS :
  1. Analyse la couverture des agents existants vs le schéma SI réel
  2. Détecte les workflows métier non couverts (tables sans agent dédié)
  3. Génère le code Python complet d'un nouvel agent depuis un template IA
  4. Met à jour l'orchestrateur, le frontend et le mobile en arrière-plan
  5. TOUT passe par approval_queue — aucune écriture sans validation humaine

PHILOSOPHIE :
  Cet agent est un "agent d'agents" : il lit ce que le SI contient,
  comprend ce que les agents actuels font, et identifie les trous.
  Il propose des agents supplémentaires pour des workflows non encore couverts,
  puis génère le code, le branche, et met à jour les interfaces.

SÉCURITÉ :
  - Génération de code soumise à validation humaine avant écriture
  - Aucune suppression ou réécriture d'agent existant sans approbation
  - Les fichiers générés passent par le même approval_queue que les actions métier
"""
from __future__ import annotations
import json
import logging
import re
from pathlib import Path
from core.agent_orchestrateur import TypeAgent
from agents.base_agent import BaseAgent
from core.schema_registry import schema_registry

logger = logging.getLogger("yukpo_assurance.agents.meta_factory")

# Répertoires cibles
_AGENTS_DIR    = Path(__file__).parent
_ORCH_PATH     = Path(__file__).parent.parent / "core" / "agent_orchestrateur.py"
_STORE_PATH    = Path(__file__).parent.parent / "frontend" / "src" / "store" / "agentStore.ts"
_SELECTOR_PATH = Path(__file__).parent.parent / "frontend" / "src" / "components" / "AgentChat" / "AgentSelector.tsx"
_SIDEBAR_PATH  = Path(__file__).parent.parent / "frontend" / "src" / "components" / "Sidebar.tsx"
_MOBILE_PATH   = Path(__file__).parent.parent / "mobile" / "app" / "(tabs)" / "agent.tsx"

# Agents déjà existants — référence pour détecter les trous
_AGENTS_EXISTANTS = {
    "sinistres":    ["SIN_", "T_SIN", "sin_", "sinistre", "dossier sinistre", "règlement"],
    "souscription": ["POL_", "T_POL", "pol_", "police", "contrat", "prime"],
    "comptabilite": ["CPT_", "T_CPT", "cpt_", "écriture", "bilan", "journal"],
    "vie":          ["VIE_", "EPA_", "PRV_", "vie", "épargne", "retraite", "décès"],
    "reassurance":  ["REA_", "réassurance", "traité", "bordereau", "cession"],
    "provisions":   ["CPT_PROVISIONS", "provision", "ppna", "psap", "pm"],
    "commercial":   ["PAR_APPORTEURS", "prospect", "apporteur", "commission"],
    "rh":           ["rh", "employé", "congé", "paie"],
    "juridique":    ["juridique", "contentieux", "subrogation", "litige"],
    "conformite":   ["conformité", "crca", "ratio", "solvabilité"],
    "intelligence": ["rapport", "kpi", "tableau de bord", "performance"],
    "placement":    ["actif", "placement", "investissement", "alm"],
    "etats_cima":   ["état", "liasse", "C1", "C2", "C3"],
    "schema_si":    ["information_schema", "schéma", "introspection"],
}

# Template Python pour génération d'un nouvel agent
_TEMPLATE_AGENT = '''"""Agent {nom_classe} — Généré automatiquement par AgentMetaFactory le {date}.

Module : {module}
Tables SI couvertes : {tables_si}
Workflows détectés : {workflows}
"""
from __future__ import annotations
import json, logging
from core.agent_orchestrateur import TypeAgent
from agents.base_agent import BaseAgent

logger = logging.getLogger("yukpo_assurance.agents.{nom_fichier}")


class {nom_classe}(BaseAgent):
    type_agent = TypeAgent.{type_enum}

    def _system_prompt(self) -> str:
        return """{system_prompt}"""

    def _definir_outils(self) -> list[dict]:
        return {outils_json}

    async def _executer_outil(self, nom: str, params: dict, user_id: int, execution_id: str) -> str:
        try:
{execution_code}
            return f"Outil \'{{nom}}\' non reconnu"
        except Exception as e:
            logger.error(f"[{nom_classe}] Erreur outil {{nom}} : {{e}}")
            return f"ERREUR {{nom}} : {{e}}"
'''


class AgentMetaFactory(BaseAgent):
    type_agent = TypeAgent.META_FACTORY

    def _system_prompt(self) -> str:
        return """Tu es l'Agent MetaFactory de YukpoAssurance. Tu es un agent de second niveau : tu analyses les agents existants et le schéma SI pour créer de nouveaux agents manquants.

TON RÔLE :
1. Identifier les tables/modules du SI qui n'ont pas d'agent dédié
2. Comprendre le workflow métier derrière chaque groupe de tables
3. Générer le code Python complet d'un nouvel agent (class, tools, execution)
4. Mettre à jour orchestrateur + frontend + mobile de manière cohérente
5. Tout soumettre pour validation humaine via approval_queue

PRINCIPES :
- Un agent = un domaine métier cohérent (pas trop fin, pas trop large)
- Chaque outil d'agent doit correspondre à une action concrète (pas juste une lecture)
- Les insertions DB → approval_queue obligatoire
- Tu génères du code Python réel et compilable, pas du pseudocode
- Après génération, tu mets à jour TypeAgent enum + imports + frontend store + selector + sidebar + mobile

DOMAINES POTENTIELLEMENT MANQUANTS (selon les SI CIMA typiques) :
- Assistance routière / dépannage (tables ASST_)
- Micro-assurance (tables MICRO_)
- Statistiques réglementaires (tables STAT_)
- Gestion des sinistres corporels graves (tables SIN_CORP_)
- Gestion des agences / réseau de distribution (tables AGC_)
- Facturation courtiers / gestion des bordereaux commissionnement (tables COMM_)"""

    def _definir_outils(self) -> list[dict]:
        return [
            {
                "name": "analyser_couverture_agents",
                "description": (
                    "Compare les tables du registre SI avec la couverture des agents existants. "
                    "Retourne les tables/modules non couverts par aucun agent."
                ),
                "input_schema": {"type": "object", "properties": {
                    "si_nom": {"type": "string"},
                }, "required": ["si_nom"]},
            },
            {
                "name": "detecter_workflows_manquants",
                "description": (
                    "Utilise l'IA pour analyser les tables non couvertes et détecter "
                    "les workflows métier qui mériteraient un nouvel agent autonome."
                ),
                "input_schema": {"type": "object", "properties": {
                    "si_nom": {"type": "string"},
                    "tables_non_couvertes": {"type": "array", "items": {"type": "string"}},
                }, "required": ["si_nom"]},
            },
            {
                "name": "generer_agent_complet",
                "description": (
                    "Génère le code Python complet d'un nouvel agent (class, tools, execution logic) "
                    "adapté aux tables SI et workflows détectés. "
                    "Le code est soumis pour validation AVANT toute écriture sur disque."
                ),
                "input_schema": {"type": "object", "properties": {
                    "nom_agent":     {"type": "string", "description": "Ex: gestion_agences"},
                    "module_metier": {"type": "string", "description": "Description du domaine"},
                    "tables_si":     {"type": "array", "items": {"type": "string"}},
                    "workflows":     {"type": "array", "items": {"type": "string"},
                                      "description": "Liste des actions/processus à couvrir"},
                    "si_nom":        {"type": "string"},
                }, "required": ["nom_agent", "module_metier", "si_nom"]},
            },
            {
                "name": "enregistrer_agent_orchestrateur",
                "description": (
                    "Génère le patch pour ajouter le nouvel agent dans agent_orchestrateur.py "
                    "(TypeAgent enum + _charger_agents + mots-clés + _NOM_AGENT + _DESC_AGENT). "
                    "Soumet pour validation avant toute modification fichier."
                ),
                "input_schema": {"type": "object", "properties": {
                    "nom_agent":    {"type": "string"},
                    "type_enum":    {"type": "string", "description": "Ex: GESTION_AGENCES"},
                    "description":  {"type": "string"},
                    "mots_cles":    {"type": "array", "items": {"type": "string"}},
                    "nom_classe":   {"type": "string", "description": "Ex: AgentGestionAgences"},
                }, "required": ["nom_agent", "type_enum", "nom_classe"]},
            },
            {
                "name": "mettre_a_jour_frontend",
                "description": (
                    "Génère les patches pour agentStore.ts, AgentSelector.tsx et Sidebar.tsx "
                    "afin d'ajouter le nouvel agent dans les interfaces web. "
                    "Soumet pour validation avant toute modification."
                ),
                "input_schema": {"type": "object", "properties": {
                    "nom_agent":   {"type": "string"},
                    "label":       {"type": "string"},
                    "emoji":       {"type": "string"},
                    "description": {"type": "string"},
                    "instruction_exemple": {"type": "string"},
                }, "required": ["nom_agent", "label", "emoji"]},
            },
            {
                "name": "mettre_a_jour_mobile",
                "description": (
                    "Génère le patch pour le fichier mobile app/(tabs)/agent.tsx "
                    "afin d'ajouter le nouvel agent dans le sélecteur mobile. "
                    "Soumet pour validation avant toute modification."
                ),
                "input_schema": {"type": "object", "properties": {
                    "nom_agent": {"type": "string"},
                    "label":     {"type": "string"},
                    "emoji":     {"type": "string"},
                }, "required": ["nom_agent", "label", "emoji"]},
            },
            {
                "name": "rapport_couverture_complete",
                "description": (
                    "Rapport complet : agents existants vs SI, taux de couverture, "
                    "priorisation des agents manquants, roadmap de création."
                ),
                "input_schema": {"type": "object", "properties": {
                    "si_nom": {"type": "string"},
                    "avec_recommandations_ia": {"type": "boolean"},
                }, "required": ["si_nom"]},
            },
            {
                "name": "appliquer_agent_valide",
                "description": (
                    "Applique un agent précédemment validé dans approval_queue : "
                    "écrit le fichier .py, patche l'orchestrateur, le frontend et le mobile."
                ),
                "input_schema": {"type": "object", "properties": {
                    "validation_id": {"type": "string", "description": "ID de la validation approuvée"},
                }, "required": ["validation_id"]},
            },
        ]

    def _prompt_questions_specifiques(self) -> str:
        return """
AGENT META FACTORY (AUTONOME) — questions aux propriétaires Yukpo (super_admin uniquement) :

NOTE : Cet agent tourne en arrière-plan toutes les 24h. Il détecte les workflows SI non couverts,
génère de nouveaux agents, et demande validation avant tout déploiement.

1. WORKFLOWS NON COUVERTS DÉTECTÉS — PRIORITÉ DE CRÉATION
   → "J'ai détecté {nb} workflows SI non couverts par les agents existants : {liste_workflows}. Lesquels souhaitez-vous que je transforme en agents en priorité ?"
   type_reponse: choix_multiple  choix: ["{workflow1}", "{workflow2}", "{workflow3}", "Tous les workflows détectés", "Aucun pour l'instant — reporter"]

2. AGENT GÉNÉRÉ — NOM ET PÉRIMÈTRE À VALIDER
   → "J'ai généré un nouvel agent '{nom_agent}' couvrant les tables {tables}. Souhaitez-vous que je l'enregistre dans l'orchestrateur et le déploie sur frontend/mobile ?"
   type_reponse: oui_non

3. CONFLIT DE PÉRIMÈTRE ENTRE AGENTS
   → "Le nouvel agent '{agent_nouveau}' chevauche partiellement le périmètre de l'agent existant '{agent_existant}' sur les tables {tables_communes}. Comment gérer ce conflit ?"
   type_reponse: choix_multiple  choix: ["Créer le nouvel agent — périmètres complémentaires", "Fusionner dans l'agent existant (enrichissement)", "Créer uniquement si l'agent existant ne couvre pas le workflow X", "Annuler la création — trop de chevauchement"]

4. MISE À JOUR FRONTEND / MOBILE
   → "Le déploiement du nouvel agent '{nom_agent}' nécessite une mise à jour du frontend et de l'application mobile. Autoriser la mise à jour automatique ?"
   type_reponse: oui_non

5. LIMITE DE BUDGET IA ATTEINTE (génération code coûteuse)
   → "La génération automatique de {nb_agents} nouveaux agents dépasserait le budget IA journalier ({budget_usd} USD). Voulez-vous continuer ?"
   type_reponse: choix_multiple  choix: ["Continuer — autoriser le dépassement exceptionnel", "Limiter à {nb_max} agents aujourd'hui", "Reporter à demain (prochain cycle)", "Réduire la qualité de génération (modèle plus rapide)"]

6. ARCHITECTURE AGENT NON STANDARD DÉTECTÉE
   → "L'analyse du SI révèle un pattern d'architecture non standard pour {table}. Quelle convention de nommage utiliser pour le nouvel agent ?"
   type_reponse: choix_multiple  choix: ["Convention Yukpo standard (prefixe + _agent)", "Convention du SI source ({si_convention})", "Nommage métier pur (sans préfixe technique)", "Demander un nommage personnalisé"]

IMPORTANT : Toutes les questions de cet agent sont marquées [META FACTORY] et réservées exclusivement aux super_admin / yukpo_owner.
"""

    async def _executer_outil(self, nom: str, params: dict, user_id: int, execution_id: str) -> str:
        try:
            if nom == "analyser_couverture_agents":
                return await _analyser_couverture(params)

            if nom == "detecter_workflows_manquants":
                return await _detecter_workflows(params)

            if nom == "generer_agent_complet":
                return await _generer_agent(params, user_id, execution_id)

            if nom == "enregistrer_agent_orchestrateur":
                return await _patch_orchestrateur(params, user_id, execution_id)

            if nom == "mettre_a_jour_frontend":
                return await _patch_frontend(params, user_id, execution_id)

            if nom == "mettre_a_jour_mobile":
                return await _patch_mobile(params, user_id, execution_id)

            if nom == "rapport_couverture_complete":
                return await _rapport_couverture(params)

            if nom == "appliquer_agent_valide":
                return await _appliquer_agent_valide(params, user_id)

            return f"Outil '{nom}' non reconnu"
        except Exception as e:
            logger.error(f"[AgentMetaFactory] Erreur outil {nom} : {e}")
            return f"ERREUR {nom} : {e}"


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _analyser_couverture(params: dict) -> str:
    si = params["si_nom"]
    si_data = schema_registry.get_schema_si(si)
    tables = list(si_data.get("tables", {}).keys())

    couvertes: list[str] = []
    non_couvertes: list[str] = []

    for table in tables:
        couverte = False
        for agent_nom, patterns in _AGENTS_EXISTANTS.items():
            if any(table.upper().startswith(p.upper()) or p.lower() in table.lower() for p in patterns):
                couverte = True
                couvertes.append({"table": table, "agent": agent_nom})
                break
        if not couverte:
            non_couvertes.append(table)

    taux = round(len(couvertes) / max(len(tables), 1) * 100, 1)

    # Si le registre est vide → utiliser les préfixes connus comme base
    if not tables:
        non_couvertes = ["Registre vide — lancer decouvrir_schema_complet ou charger_schema_depuis_fichier d'abord"]

    return json.dumps({
        "si": si,
        "nb_tables_total": len(tables),
        "nb_tables_couvertes": len(couvertes),
        "nb_tables_non_couvertes": len(non_couvertes),
        "taux_couverture_pct": taux,
        "tables_non_couvertes": non_couvertes[:50],
        "tables_couvertes_apercu": couvertes[:20],
        "action_recommandee": (
            "Lancer detecter_workflows_manquants avec la liste tables_non_couvertes"
            if non_couvertes and non_couvertes[0] != "Registre vide — lancer decouvrir_schema_complet ou charger_schema_depuis_fichier d'abord"
            else "Introspection SI requise d'abord"
        ),
    }, ensure_ascii=False)


async def _detecter_workflows(params: dict) -> str:
    from core.ia_client import ModeIA, ia_client
    si = params["si_nom"]
    tables = params.get("tables_non_couvertes", [])

    if not tables:
        # Auto-charger depuis l'analyse de couverture
        result_str = await _analyser_couverture({"si_nom": si})
        result = json.loads(result_str)
        tables = result.get("tables_non_couvertes", [])

    if not tables or "Registre vide" in str(tables[0]):
        return json.dumps({
            "si": si,
            "message": "Aucune table non couverte détectée. Tous les modules SI ont un agent ou le registre est vide.",
            "workflows_detectes": [],
        }, ensure_ascii=False)

    prompt = f"""Tu es expert en systèmes d'information pour compagnies d'assurance CIMA (zone Afrique subsaharienne).

SI analysé : {si.upper()}
Tables non couvertes par les agents existants :
{chr(10).join(f"- {t}" for t in tables[:40])}

Pour chaque groupe de tables cohérent, identifie :
1. Le domaine métier (ex: "Gestion des agences et réseau commercial")
2. Les 3-5 workflows clés (ex: "Ouvrir une agence", "Gérer les objectifs agence", "Suivi performance réseau")
3. Un nom d'agent suggéré (ex: agent_gestion_agences)
4. La priorité (haute/moyenne/faible) selon la fréquence d'utilisation attendue

Retourne un JSON structuré :
{{
  "agents_suggeres": [
    {{
      "nom_fichier": "agent_xxx",
      "nom_classe": "AgentXxx",
      "type_enum": "XXX",
      "module_metier": "Description courte",
      "tables_si": ["TABLE_A", "TABLE_B"],
      "workflows": ["workflow 1", "workflow 2", "workflow 3"],
      "priorite": "haute|moyenne|faible",
      "emoji": "emoji représentatif",
      "label_frontend": "Libellé court (max 30 car)",
      "description_courte": "description une ligne"
    }}
  ]
}}

Si les tables ne correspondent à aucun domaine métier d'assurance distinct, retourner agents_suggeres=[].
Retourner UNIQUEMENT le JSON."""

    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
    try:
        contenu = rep.contenu.strip()
        if "```" in contenu:
            contenu = contenu.split("```")[1].replace("json", "").strip()
        result = json.loads(contenu)
        result["si"] = si
        result["tables_analysees"] = len(tables)
        return json.dumps(result, ensure_ascii=False)
    except Exception:
        return json.dumps({
            "si": si,
            "tables_analysees": len(tables),
            "analyse_brute": rep.contenu,
            "message": "Parsing JSON échoué — analyse brute disponible",
        }, ensure_ascii=False)


async def _generer_agent(params: dict, user_id: int, execution_id: str) -> str:
    from core.ia_client import ModeIA, ia_client
    from datetime import datetime

    nom_agent = params["nom_agent"].lower().replace(" ", "_")
    module = params["module_metier"]
    tables_si = params.get("tables_si", [])
    workflows = params.get("workflows", [])
    si = params["si_nom"]
    nom_classe = "Agent" + "".join(w.capitalize() for w in nom_agent.split("_"))
    type_enum = nom_agent.upper()

    # Récupérer le contexte schéma pour les tables concernées
    colonnes_contexte = []
    for t in tables_si[:10]:
        tdata = schema_registry.get_table(t, si)
        if tdata:
            cols = [c["nom"] for c in tdata.get("colonnes", [])[:15]]
            colonnes_contexte.append(f"TABLE {t} : {', '.join(cols)}")

    prompt = f"""Tu génères le code Python complet d'un agent IA pour une compagnie d'assurance CIMA.

AGENT À CRÉER :
- Nom fichier : {nom_agent}.py
- Nom classe  : {nom_classe}
- TypeAgent   : TypeAgent.{type_enum}
- Module      : {module}
- Tables SI   : {', '.join(tables_si)}
- Workflows   : {', '.join(workflows)}

CONTEXTE SCHÉMA {si.upper()} :
{chr(10).join(colonnes_contexte) if colonnes_contexte else "Non disponible (schéma non introspectés)"}

RÈGLES DE GÉNÉRATION :
1. Hériter de BaseAgent avec type_agent = TypeAgent.{type_enum}
2. _system_prompt() : rôle, branches CIMA concernées, règles absolues
3. _definir_outils() : 5 à 12 outils avec input_schema complet
4. _executer_outil() : logique complète — toute insertion DB passe par approval_queue
5. Imports : from __future__ import annotations, import json, logging
6. Pattern approval_queue (OBLIGATOIRE pour toute écriture) :
   from core.approval_queue import approval_queue
   await approval_queue.ajouter({{
       "type": "xxx", "donnees": ..., "user_id": user_id, "execution_id": execution_id,
       "description": "..."
   }})
7. Pattern IA (uniquement si analyse narrative nécessaire) :
   from core.ia_client import ModeIA, ia_client
   rep = await ia_client.appeler(prompt=..., mode=ModeIA.ANALYSE)

Génère le fichier Python COMPLET, syntaxe valide, prêt à être importé.
NE PAS inclure de commentaires TODO, NE PAS utiliser de fonctions non définies.
Commence directement par le docstring du module."""

    rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
    code_genere = rep.contenu.strip()
    if code_genere.startswith("```python"):
        code_genere = code_genere[9:]
    if code_genere.startswith("```"):
        code_genere = code_genere[3:]
    if code_genere.endswith("```"):
        code_genere = code_genere[:-3]
    code_genere = code_genere.strip()

    # Vérification syntaxique basique
    erreurs_syntaxe = []
    if "class " + nom_classe not in code_genere:
        erreurs_syntaxe.append(f"Classe {nom_classe} non trouvée dans le code généré")
    if "def _executer_outil" not in code_genere:
        erreurs_syntaxe.append("Méthode _executer_outil manquante")
    if "approval_queue" not in code_genere:
        erreurs_syntaxe.append("approval_queue non utilisé — écriture DB non sécurisée")

    from core.approval_queue import approval_queue
    await approval_queue.ajouter({
        "type": "creation_nouvel_agent",
        "nom_agent": nom_agent,
        "nom_classe": nom_classe,
        "type_enum": type_enum,
        "module_metier": module,
        "tables_si": tables_si,
        "workflows": workflows,
        "fichier_cible": str(_AGENTS_DIR / f"{nom_agent}.py"),
        "code_genere": code_genere,
        "erreurs_syntaxe": erreurs_syntaxe,
        "user_id": user_id,
        "execution_id": execution_id,
        "description": (
            f"Nouvel agent : {nom_classe} — {module} "
            f"({len(workflows)} workflows, tables : {', '.join(tables_si[:3])}...)"
        ),
    })

    return json.dumps({
        "statut": "en_attente_validation",
        "nom_agent": nom_agent,
        "nom_classe": nom_classe,
        "type_enum": type_enum,
        "nb_lignes_code": len(code_genere.split("\n")),
        "erreurs_syntaxe": erreurs_syntaxe,
        "message": (
            f"Agent {nom_classe} généré ({len(code_genere.split(chr(10)))} lignes). "
            "Soumis pour validation — une fois approuvé, le fichier sera écrit et "
            "l'orchestrateur + frontend + mobile seront mis à jour."
        ),
        "etapes_suivantes": [
            "1. Valider dans la file d'approbation",
            f"2. Lancer enregistrer_agent_orchestrateur avec type_enum='{type_enum}'",
            f"3. Lancer mettre_a_jour_frontend",
            f"4. Lancer mettre_a_jour_mobile",
        ],
    }, ensure_ascii=False)


async def _patch_orchestrateur(params: dict, user_id: int, execution_id: str) -> str:
    nom_agent   = params["nom_agent"].lower().replace(" ", "_")
    type_enum   = params["type_enum"].upper()
    description = params.get("description", f"Agent {nom_agent}")
    mots_cles   = params.get("mots_cles", [nom_agent.replace("_", " ")])
    nom_classe  = params["nom_classe"]

    # Lire l'orchestrateur actuel
    orch_source = _ORCH_PATH.read_text(encoding="utf-8")

    # Générer les lignes à ajouter
    patch_enum     = f'    {type_enum:<14}= "{nom_agent}"     # Auto-généré par AgentMetaFactory'
    patch_import   = f'            from agents.{nom_agent:<35} import {nom_classe}'
    patch_instance = f'                TypeAgent.{type_enum:<14}: {nom_classe}(),'
    patch_mots     = f'    TypeAgent.{type_enum}: {json.dumps(mots_cles, ensure_ascii=False)},'
    patch_nom      = f'    TypeAgent.{type_enum:<14}: "Agent {" ".join(w.capitalize() for w in nom_agent.split("_"))}",  # auto'
    patch_desc     = f'    TypeAgent.{type_enum:<14}: "{description}",  # auto'

    patch_resume = {
        "type": "patch_orchestrateur",
        "nom_agent": nom_agent,
        "type_enum": type_enum,
        "nom_classe": nom_classe,
        "lignes_a_ajouter": {
            "TypeAgent_enum": patch_enum,
            "import_agent": patch_import,
            "instanciation": patch_instance,
            "mots_cles_detection": patch_mots,
            "nom_agent": patch_nom,
            "description_agent": patch_desc,
        },
        "fichier_cible": str(_ORCH_PATH),
        "user_id": user_id,
        "execution_id": execution_id,
        "description": f"Patch orchestrateur : ajouter TypeAgent.{type_enum} pour {nom_classe}",
    }

    from core.approval_queue import approval_queue
    await approval_queue.ajouter(patch_resume)

    return json.dumps({
        "statut": "en_attente_validation",
        "message": (
            f"Patch orchestrateur généré pour {nom_classe}. "
            "Une fois validé : TypeAgent.{type_enum} sera ajouté, l'agent instancié, "
            "et les mots-clés de détection configurés."
        ),
        "patch_resume": patch_resume["lignes_a_ajouter"],
    }, ensure_ascii=False)


async def _patch_frontend(params: dict, user_id: int, execution_id: str) -> str:
    nom_agent   = params["nom_agent"].lower().replace(" ", "_")
    label       = params["label"]
    emoji       = params.get("emoji", "🤖")
    description = params.get("description", label)
    instruction = params.get("instruction_exemple", f"Instruis l'agent {label}")

    # Lire les fichiers cibles
    store_source    = _STORE_PATH.read_text(encoding="utf-8")
    selector_source = _SELECTOR_PATH.read_text(encoding="utf-8")
    sidebar_source  = _SIDEBAR_PATH.read_text(encoding="utf-8")

    # Détecter si déjà présent
    if f"'{nom_agent}'" in store_source:
        return json.dumps({
            "statut": "deja_present",
            "message": f"Agent '{nom_agent}' déjà déclaré dans agentStore.ts",
        }, ensure_ascii=False)

    patch_store    = f" | '{nom_agent}'"
    patch_selector = (f"  {{ value: '{nom_agent}', label: '{label}', emoji: '{emoji}', "
                      f"description: '{description}' }},")
    patch_sidebar  = f"  {{ emoji: '{emoji}', label: '{label}', instruction: '{instruction}' }},"

    from core.approval_queue import approval_queue
    await approval_queue.ajouter({
        "type": "patch_frontend_nouvel_agent",
        "nom_agent": nom_agent,
        "label": label,
        "emoji": emoji,
        "fichiers_a_modifier": [str(_STORE_PATH), str(_SELECTOR_PATH), str(_SIDEBAR_PATH)],
        "patches": {
            "agentStore_ts": {
                "rechercher": "| 'schema_si'",
                "remplacer": f"| 'schema_si' | '{nom_agent}'",
                "fichier": str(_STORE_PATH),
            },
            "AgentSelector_tsx": {
                "ajouter_apres": "{ value: 'schema_si'",
                "ligne": patch_selector,
                "fichier": str(_SELECTOR_PATH),
            },
            "Sidebar_tsx": {
                "ajouter_apres": "emoji: '🔬'",
                "ligne": patch_sidebar,
                "fichier": str(_SIDEBAR_PATH),
            },
        },
        "user_id": user_id,
        "execution_id": execution_id,
        "description": f"Mise à jour frontend : ajouter agent '{label}' ({emoji}) dans selector + sidebar",
    })

    return json.dumps({
        "statut": "en_attente_validation",
        "fichiers_impactes": ["agentStore.ts", "AgentSelector.tsx", "Sidebar.tsx"],
        "message": (
            f"Patches frontend générés pour l'agent '{label}'. "
            "Une fois validés : agentStore TypeScript étendu, agent visible dans le sélecteur, "
            "raccourci ajouté dans la sidebar."
        ),
    }, ensure_ascii=False)


async def _patch_mobile(params: dict, user_id: int, execution_id: str) -> str:
    nom_agent = params["nom_agent"].lower().replace(" ", "_")
    label     = params["label"]
    emoji     = params.get("emoji", "🤖")

    mobile_source = _MOBILE_PATH.read_text(encoding="utf-8")

    if f"'{nom_agent}'" in mobile_source:
        return json.dumps({
            "statut": "deja_present",
            "message": f"Agent '{nom_agent}' déjà déclaré dans agent.tsx mobile",
        }, ensure_ascii=False)

    patch_type   = f" | '{nom_agent}'"
    patch_agent  = f"  {{ value: '{nom_agent}', label: '{label}', emoji: '{emoji}' }},"

    from core.approval_queue import approval_queue
    await approval_queue.ajouter({
        "type": "patch_mobile_nouvel_agent",
        "nom_agent": nom_agent,
        "label": label,
        "emoji": emoji,
        "fichier_cible": str(_MOBILE_PATH),
        "patches": {
            "AgentType_union": {
                "rechercher": "| 'schema_si'",
                "remplacer": f"| 'schema_si' | '{nom_agent}'",
            },
            "AGENTS_array": {
                "ajouter_apres": "{ value: 'schema_si'",
                "ligne": patch_agent,
            },
        },
        "user_id": user_id,
        "execution_id": execution_id,
        "description": f"Mise à jour mobile : ajouter agent '{label}' ({emoji}) dans agent.tsx",
    })

    return json.dumps({
        "statut": "en_attente_validation",
        "fichier": "mobile/app/(tabs)/agent.tsx",
        "message": (
            f"Patch mobile généré pour l'agent '{label}'. "
            "Une fois validé : AgentType étendu, agent visible dans le carousel mobile."
        ),
    }, ensure_ascii=False)


async def _rapport_couverture(params: dict) -> str:
    from core.ia_client import ModeIA, ia_client
    si = params["si_nom"]

    # Récupérer analyse couverture
    couverture_str = await _analyser_couverture({"si_nom": si})
    couverture = json.loads(couverture_str)

    stats_registre = schema_registry.get_stats(si)
    agents_actifs = list(_AGENTS_EXISTANTS.keys())

    rapport_data = {
        "si": si,
        "agents_actifs": agents_actifs,
        "nb_agents": len(agents_actifs),
        "couverture_si": couverture,
        "registre_stats": stats_registre,
    }

    if params.get("avec_recommandations_ia"):
        prompt = f"""Analyse la couverture des agents IA pour une compagnie d'assurance CIMA.

Données :
{json.dumps(rapport_data, ensure_ascii=False, indent=2)}

Génère un rapport de synthèse avec :
1. Score de maturité IA (0-100)
2. Points forts (agents bien configurés)
3. Trous identifiés (domaines sans agent)
4. Top 3 agents à créer en priorité avec justification CIMA
5. Roadmap suggérée (court terme 0-3 mois, moyen terme 3-12 mois)

Style : rapport direction, concis, chiffres clés en tête."""
        rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
        rapport_data["analyse_ia"] = rep.contenu

    return json.dumps(rapport_data, ensure_ascii=False)


async def _appliquer_agent_valide(params: dict, user_id: int) -> str:
    """
    Applique physiquement un agent après validation humaine.
    Lit les données de l'approbation et écrit les fichiers.
    """
    from core.approval_queue import approval_queue
    validation_id = params["validation_id"]

    # Récupérer l'item de validation (get() est la méthode publique d'approval_queue)
    item = approval_queue.get(validation_id)
    if not item:
        return json.dumps({"erreur": f"Validation {validation_id} introuvable"}, ensure_ascii=False)
    if item.get("statut") != "approuve":
        return json.dumps({
            "erreur": f"Validation {validation_id} non approuvée (statut: {item.get('statut', 'inconnu')})"
        }, ensure_ascii=False)

    type_action = item.get("type")
    resultats = []

    if type_action == "creation_nouvel_agent":
        # Écrire le fichier agent
        code = item.get("code_genere", "")
        fichier = Path(item["fichier_cible"])
        if code and not fichier.exists():
            fichier.write_text(code, encoding="utf-8")
            resultats.append(f"Fichier écrit : {fichier.name}")
        elif fichier.exists():
            resultats.append(f"Fichier déjà existant : {fichier.name} — non écrasé")

    elif type_action == "patch_frontend_nouvel_agent":
        patches = item.get("patches", {})
        for patch_nom, patch_data in patches.items():
            fichier = Path(patch_data["fichier"])
            if fichier.exists():
                source = fichier.read_text(encoding="utf-8")
                source_mod = source.replace(patch_data["rechercher"], patch_data["remplacer"])
                if source_mod != source:
                    fichier.write_text(source_mod, encoding="utf-8")
                    resultats.append(f"Patché : {fichier.name}")

    elif type_action == "patch_mobile_nouvel_agent":
        fichier = Path(item["fichier_cible"])
        if fichier.exists():
            source = fichier.read_text(encoding="utf-8")
            for patch_data in item.get("patches", {}).values():
                source = source.replace(patch_data["rechercher"], patch_data["remplacer"])
            fichier.write_text(source, encoding="utf-8")
            resultats.append(f"Mobile patché : {fichier.name}")

    return json.dumps({
        "validation_id": validation_id,
        "type_action": type_action,
        "resultats": resultats,
        "message": f"{len(resultats)} fichier(s) mis à jour avec succès.",
    }, ensure_ascii=False)
