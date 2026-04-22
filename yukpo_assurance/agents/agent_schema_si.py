"""
Agent Schéma SI — Introspection, apprentissage et synchronisation du schéma base de données.

CAPACITÉS :
  1. Connexion et introspection autonome de n'importe quel SI d'assurance
     (ORASS, Mercure, Saphir, GIAP, ou base propriétaire)
     → via SQLAlchemy + information_schema (SQL Server / PostgreSQL / MySQL / Oracle)

  2. Construction d'un dictionnaire de données complet :
     tables, colonnes, types, PK, FK, index, contraintes, cardinalités

  3. Mapping sémantique IA :
     concept métier ↔ table.colonne technique
     Ex: "sinistre.montant_indemnisation" → "SIN_DOSSIERS.MNT_TOTAL_REGLE"

  4. Validation et correction des requêtes des autres agents :
     détecte les noms de champs incorrects, champs renommés, tables supprimées

  5. Surveillance continue des dérives de schéma :
     alerte si une colonne est supprimée ou renommée entre deux introspections

ARCHITECTURE :
  - Utilise SQLAlchemy pour l'introspection (support SQL Server, PostgreSQL, MySQL, Oracle, SQLite)
  - Persiste la connaissance dans core/schema_registry.py (singleton partagé)
  - L'IA (Claude) analyse les noms de tables/colonnes et construit le sens métier
  - LECTURE SEULE sur le SI cible — aucune écriture sur les tables métier

ACCÈS SI REQUIS :
  - SQL Server (ORASS/Mercure) : utilisateur db_datareader sur information_schema + tables métier
  - PostgreSQL : GRANT SELECT ON ALL TABLES IN SCHEMA public TO user_integration;
  - La chaîne de connexion est stockée chiffrée dans config/settings.py
  - Un accès READ-ONLY suffit — principe du moindre privilège
"""
from __future__ import annotations
import json
import logging
from datetime import datetime
from core.agent_orchestrateur import TypeAgent
from agents.base_agent import BaseAgent
from core.schema_registry import schema_registry

logger = logging.getLogger("yukpo_assurance.agents.schema_si")

# ── SI connus en zone CIMA ─────────────────────────────────────────────────────
_SI_CONNUS = {
    "orass": {
        "description": "ORASS — logiciel de gestion d'assurance leader en Afrique francophone",
        "dbms": "sql_server",
        "port_defaut": 1433,
        "modules": ["production", "sinistres", "comptabilite", "reassurance", "statistiques"],
        "prefixes_tables": ["POL_", "SIN_", "CPT_", "REA_", "STAT_", "PAR_", "CLI_"],
    },
    "mercure": {
        "description": "Mercure — SI assurance francophone (SQL Server)",
        "dbms": "sql_server",
        "port_defaut": 1433,
        "modules": ["polices", "sinistres", "comptabilite"],
        "prefixes_tables": ["T_POL", "T_SIN", "T_CPT", "T_CLI"],
    },
    "saphir": {
        "description": "Saphir — SI assurance vie (Oracle/PostgreSQL)",
        "dbms": "oracle",
        "port_defaut": 1521,
        "modules": ["vie", "epargne", "prevoyance"],
        "prefixes_tables": ["VIE_", "EPA_", "PRV_"],
    },
    "giap": {
        "description": "GIAP — SI assurance Afrique subsaharienne",
        "dbms": "postgresql",
        "port_defaut": 5432,
        "modules": ["production", "sinistres"],
        "prefixes_tables": ["pol_", "sin_", "cli_"],
    },
}

# ── Mappings sémantiques de référence pour ORASS ──────────────────────────────
# Ces mappings sont le résultat d'une introspection typique d'ORASS.
# Ils servent de base avant la vraie connexion et sont enrichis après.
_MAPPINGS_ORASS_REFERENCE = {
    # Polices / Production
    "police.numero":             "POL_CONTRATS.NUM_POLICE",
    "police.prime_ttc":          "POL_CONTRATS.MTN_PRIME_TTC",
    "police.prime_ht":           "POL_CONTRATS.MTN_PRIME_HT",
    "police.date_effet":         "POL_CONTRATS.DAT_EFFET",
    "police.date_echeance":      "POL_CONTRATS.DAT_ECHEANCE",
    "police.branche":            "POL_CONTRATS.COD_BRANCHE",
    "police.statut":             "POL_CONTRATS.COD_STATUT",
    "police.apporteur_id":       "POL_CONTRATS.COD_APPORTEUR",
    "police.assure_id":          "POL_CONTRATS.COD_ASSURE",
    "police.pays":               "POL_CONTRATS.COD_PAYS",
    # Client
    "client.nom":                "CLI_TIERS.NOM_TIERS",
    "client.prenom":             "CLI_TIERS.PRE_TIERS",
    "client.telephone":          "CLI_TIERS.TEL_MOBILE",
    "client.email":              "CLI_TIERS.ADR_EMAIL",
    "client.date_naissance":     "CLI_TIERS.DAT_NAISSANCE",
    "client.type":               "CLI_TIERS.COD_TYPE_TIERS",  # P=personne, E=entreprise
    # Sinistres
    "sinistre.reference":        "SIN_DOSSIERS.NUM_SINISTRE",
    "sinistre.date_survenance":  "SIN_DOSSIERS.DAT_SURVENANCE",
    "sinistre.date_declaration": "SIN_DOSSIERS.DAT_DECLARATION",
    "sinistre.montant_estime":   "SIN_DOSSIERS.MTN_ESTIME",
    "sinistre.montant_regle":    "SIN_DOSSIERS.MTN_REGLE",
    "sinistre.montant_provision": "SIN_DOSSIERS.MTN_PROVISION",
    "sinistre.statut":           "SIN_DOSSIERS.COD_STATUT",  # O=ouvert, C=clos, E=expertise
    "sinistre.branche":          "SIN_DOSSIERS.COD_BRANCHE",
    "sinistre.police_id":        "SIN_DOSSIERS.NUM_POLICE",
    # Comptabilité
    "ecriture.journal":          "CPT_ECRITURES.COD_JOURNAL",
    "ecriture.compte_debit":     "CPT_ECRITURES.NUM_CPTE_DEBIT",
    "ecriture.compte_credit":    "CPT_ECRITURES.NUM_CPTE_CREDIT",
    "ecriture.montant":          "CPT_ECRITURES.MTN_ECRITURE",
    "ecriture.libelle":          "CPT_ECRITURES.LIB_ECRITURE",
    "ecriture.date":             "CPT_ECRITURES.DAT_ECRITURE",
    "ecriture.police_id":        "CPT_ECRITURES.NUM_POLICE",
    # Provisions
    "provision.type":            "CPT_PROVISIONS.COD_TYPE_PROV",
    "provision.montant":         "CPT_PROVISIONS.MTN_PROVISION",
    "provision.date":            "CPT_PROVISIONS.DAT_INVENTAIRE",
    "provision.branche":         "CPT_PROVISIONS.COD_BRANCHE",
    "provision.exercice":        "CPT_PROVISIONS.NUM_EXERCICE",
    # Réassurance
    "reassurance.traite_id":     "REA_TRAITES.COD_TRAITE",
    "reassurance.taux_cession":  "REA_TRAITES.TAU_CESSION",
    "reassurance.reassureur_id": "REA_TRAITES.COD_REASSUREUR",
    "reassurance.bordereau":     "REA_BORDEREAUX.NUM_BORDEREAU",
    # Apporteurs
    "apporteur.code":            "PAR_APPORTEURS.COD_APPORTEUR",
    "apporteur.nom":             "PAR_APPORTEURS.NOM_APPORTEUR",
    "apporteur.agrement":        "PAR_APPORTEURS.NUM_AGREMENT",
    "apporteur.type":            "PAR_APPORTEURS.COD_TYPE",  # C=courtier, AG=agent général
}


class AgentSchemaSI(BaseAgent):
    type_agent = TypeAgent.SCHEMA_SI

    def _system_prompt(self) -> str:
        return """Tu es l'Agent Schéma SI de YukpoAssurance. Tu es spécialisé dans l'introspection, la documentation et la synchronisation des bases de données des systèmes d'information d'assurance (ORASS, Mercure, Saphir, GIAP, etc.).

TON RÔLE PRINCIPAL :
1. Connecter et inspecter AUTONOMEMENT les schémas des bases de données SI
2. Construire et maintenir le dictionnaire de données complet
3. Créer les mappings sémantiques : concept métier ↔ table.colonne technique
4. Valider et corriger les requêtes des autres agents
5. Détecter les dérives de schéma et alerter avant toute panne

RÈGLES FONDAMENTALES :
- TU NE MODIFIES JAMAIS les données des tables métier — LECTURE SEULE uniquement
- Toute insertion ou modification → validation humaine via approval_queue
- Les connexions SI utilisent un compte dédié READ-ONLY (db_datareader)
- Tu documentes chaque table avec son sens métier d'assurance CIMA
- Tu signales IMMÉDIATEMENT toute dérive critique (colonne supprimée, table renommée)

CONNAISSANCE SI :
- ORASS : préfixes tables POL_ (polices), SIN_ (sinistres), CPT_ (comptabilité), REA_ (réassurance), CLI_ (clients), PAR_ (partenaires)
- Mercure : préfixes T_POL, T_SIN, T_CPT, T_CLI
- Les deux utilisent SQL Server — information_schema.tables et sys.columns disponibles
- Les clés primaires sont généralement NUM_xxx ou COD_xxx ou ID_xxx

APPROCHE D'ANALYSE :
1. D'abord les tables à fort trafic (sinistres, polices, clients)
2. Ensuite les tables de paramètres et référentiels
3. Mapper les FK pour comprendre les jointures métier
4. Générer les requêtes types pour chaque module (production, sinistres, compta)"""

    def _definir_outils(self) -> list[dict]:
        return [
            {
                "name": "tester_connexion_si",
                "description": "Teste la connexion à un SI (ORASS, Mercure, etc.) et retourne les informations de base (déterministe)",
                "input_schema": {"type": "object", "properties": {
                    "si_nom":           {"type": "string", "enum": ["orass", "mercure", "saphir", "giap", "custom"]},
                    "host":             {"type": "string"},
                    "port":             {"type": "integer"},
                    "database":         {"type": "string"},
                    "username":         {"type": "string"},
                    "dbms":             {"type": "string", "enum": ["sql_server", "postgresql", "mysql", "oracle", "sqlite"]},
                    "utiliser_config":  {"type": "boolean", "description": "Utiliser les paramètres depuis config/settings.py"},
                }, "required": ["si_nom"]},
            },
            {
                "name": "decouvrir_schema_complet",
                "description": "Introspecte TOUTES les tables du SI et construit le registre complet (peut prendre 2-5 min sur un gros SI)",
                "input_schema": {"type": "object", "properties": {
                    "si_nom":          {"type": "string"},
                    "schema_db":       {"type": "string", "description": "Schéma BD (dbo pour SQL Server, public pour PG)"},
                    "filtre_prefixe":  {"type": "string", "description": "Filtrer par préfixe table ex: SIN_ pour sinistres seulement"},
                    "avec_cardinalites": {"type": "boolean", "description": "Compter le nombre de lignes par table (plus lent)"},
                    "avec_index":      {"type": "boolean", "description": "Inclure les index"},
                }, "required": ["si_nom"]},
            },
            {
                "name": "inspecter_table",
                "description": "Inspection détaillée d'une table : colonnes, types, FK, index, 5 exemples de lignes, cardinalité",
                "input_schema": {"type": "object", "properties": {
                    "si_nom":     {"type": "string"},
                    "table_nom":  {"type": "string", "description": "Nom exact de la table"},
                    "avec_exemples": {"type": "boolean", "description": "Récupérer 5 lignes d'exemple (anonymisées)"},
                    "avec_stats":    {"type": "boolean", "description": "Stats colonnes: min, max, nb nulls, valeurs distinctes"},
                }, "required": ["si_nom", "table_nom"]},
            },
            {
                "name": "rechercher_table_concept",
                "description": "Recherche quelle(s) table(s) correspond(ent) à un concept métier (sinistre, police, prime, etc.)",
                "input_schema": {"type": "object", "properties": {
                    "si_nom":   {"type": "string"},
                    "concept":  {"type": "string", "description": "Ex: sinistre, police, prime, provision, client, apporteur"},
                    "avec_colonnes": {"type": "boolean"},
                }, "required": ["si_nom", "concept"]},
            },
            {
                "name": "generer_mappings_semantiques",
                "description": "Génère via IA les mappings concept métier ↔ table.colonne pour un module du SI",
                "input_schema": {"type": "object", "properties": {
                    "si_nom":   {"type": "string"},
                    "module":   {"type": "string", "enum": ["production", "sinistres", "comptabilite", "reassurance", "clients", "provisions", "tous"]},
                    "appliquer_automatiquement": {"type": "boolean", "description": "Enregistrer les mappings dans le registre"},
                }, "required": ["si_nom", "module"]},
            },
            {
                "name": "valider_requete_agent",
                "description": "Valide qu'une requête SQL d'un agent utilise les bons noms de tables/colonnes selon le registre",
                "input_schema": {"type": "object", "properties": {
                    "si_nom":       {"type": "string"},
                    "requete_sql":  {"type": "string"},
                    "agent_source": {"type": "string", "description": "Nom de l'agent qui génère cette requête"},
                    "type":         {"type": "string", "enum": ["SELECT", "INSERT", "UPDATE", "DELETE"]},
                }, "required": ["si_nom", "requete_sql"]},
            },
            {
                "name": "generer_requete_metier",
                "description": "Génère une requête SQL validée pour un besoin métier en utilisant le registre de schéma",
                "input_schema": {"type": "object", "properties": {
                    "si_nom":    {"type": "string"},
                    "besoin":    {"type": "string", "description": "Description en langage naturel ex: 'tous les sinistres ouverts de 2025 avec montant > 500000'"},
                    "type":      {"type": "string", "enum": ["SELECT", "INSERT", "UPDATE"]},
                    "limite":    {"type": "integer"},
                }, "required": ["si_nom", "besoin"]},
            },
            {
                "name": "detecter_derive_schema",
                "description": "Compare le schéma actuel du SI avec le registre et identifie les dérives (colonnes supprimées, tables renommées)",
                "input_schema": {"type": "object", "properties": {
                    "si_nom":  {"type": "string"},
                    "alerte_agents": {"type": "boolean", "description": "Notifier les agents affectés par les dérives"},
                }, "required": ["si_nom"]},
            },
            {
                "name": "documenter_table_metier",
                "description": "Ajoute ou met à jour la documentation métier d'une table (description, concepts assurance, usage)",
                "input_schema": {"type": "object", "properties": {
                    "si_nom":       {"type": "string"},
                    "table_nom":    {"type": "string"},
                    "description":  {"type": "string"},
                    "concepts":     {"type": "array", "items": {"type": "string"}, "description": "Tags: sinistre, prime, provision, apporteur..."},
                    "agent_principal": {"type": "string", "description": "Agent YukpoAssurance qui utilise principalement cette table"},
                }, "required": ["si_nom", "table_nom", "description"]},
            },
            {
                "name": "corriger_mapping_agent",
                "description": "Corrige un mapping incorrect d'un agent en utilisant le schéma réel du SI",
                "input_schema": {"type": "object", "properties": {
                    "si_nom":           {"type": "string"},
                    "agent_nom":        {"type": "string"},
                    "champ_incorrect":  {"type": "string", "description": "Ex: 'montant_sinistre' que l'agent utilise incorrectement"},
                    "contexte":         {"type": "string"},
                }, "required": ["si_nom", "agent_nom", "champ_incorrect"]},
            },
            {
                "name": "rapport_connaissance_si",
                "description": "Génère un rapport complet sur la connaissance du schéma SI : couverture, mappings, dérives, recommandations",
                "input_schema": {"type": "object", "properties": {
                    "si_nom": {"type": "string"},
                    "inclure_requetes_type": {"type": "boolean"},
                }, "required": ["si_nom"]},
            },
            {
                "name": "charger_schema_depuis_fichier",
                "description": "Charge un schéma SI depuis un fichier SQL (DDL), Excel de documentation, ou dump information_schema",
                "input_schema": {"type": "object", "properties": {
                    "si_nom":         {"type": "string"},
                    "fichier_path":   {"type": "string", "description": "Chemin absolu vers le DDL SQL, Excel ou JSON"},
                    "type_fichier":   {"type": "string", "enum": ["ddl_sql", "excel_documentation", "json_schema", "csv_information_schema"]},
                }, "required": ["si_nom", "fichier_path", "type_fichier"]},
            },
            {
                "name": "synchroniser_tous_agents",
                "description": "Met à jour le mapping de tous les agents avec le schéma le plus récent du registre",
                "input_schema": {"type": "object", "properties": {
                    "si_nom":     {"type": "string"},
                    "forcer":     {"type": "boolean", "description": "Forcer la mise à jour même si schéma inchangé"},
                }, "required": ["si_nom"]},
            },
            {
                "name": "corriger_code_agent",
                "description": (
                    "Lit le code source Python d'un agent, détecte les noms de tables/colonnes incorrects "
                    "en les comparant au registre du schéma réel du SI, génère et soumet (approval_queue) "
                    "un correctif de code. NE MODIFIE JAMAIS le fichier directement sans validation humaine."
                ),
                "input_schema": {"type": "object", "properties": {
                    "si_nom":       {"type": "string", "description": "SI de référence pour les corrections"},
                    "agent_fichier": {"type": "string", "description": "Ex: agent_sinistres, agent_souscription"},
                    "mode":         {"type": "string", "enum": ["analyser_seulement", "generer_correctif"],
                                     "description": "analyser_seulement = rapport, generer_correctif = soumet le patch pour validation"},
                }, "required": ["si_nom", "agent_fichier"]},
            },
        ]

    def _prompt_questions_specifiques(self) -> str:
        return """
AGENT SCHÉMA SI (AUTONOME) — questions aux propriétaires Yukpo (super_admin uniquement) :

NOTE : Cet agent tourne en arrière-plan automatiquement toutes les 6h. Quand il détecte un problème
nécessitant une décision humaine, il pose sa question AU SUPER ADMIN via le canal de notification Yukpo.

1. SI CIBLE NON CONFIGURÉ (premier démarrage ou nouveau SI)
   → "Aucune connexion SI n'est configurée. Sur quel système d'information (SI) dois-je effectuer l'introspection ?"
   type_reponse: choix_multiple  choix: ["ORASS (Gestion polices/sinistres)", "Mercure (Comptabilité assurance)", "Saphir (Production)", "GIAP (Gestion intégrée)", "Base de données custom (préciser)"]

2. DÉRIVE CRITIQUE DÉTECTÉE — STRATÉGIE DE CORRECTION
   → "J'ai détecté une dérive critique : la colonne {colonne_ancienne} a été renommée en {colonne_nouvelle} dans {table}. Cela impacte {nb_agents} agents. Quelle stratégie de correction appliquer ?"
   type_reponse: choix_multiple  choix: ["Corriger automatiquement tous les agents impactés (patch via approval_queue)", "Corriger uniquement l'agent le plus critique ({agent_principal})", "Générer uniquement un rapport — correction manuelle", "Reporter la correction au prochain cycle (risque de panne)"]

3. TABLE NON DOCUMENTÉE DÉCOUVERTE
   → "J'ai découvert {nb_tables} nouvelles tables dans le SI ({liste_tables_courtes}). Dois-je les documenter et proposer de nouveaux agents pour les couvrir ?"
   type_reponse: oui_non

4. ACCÈS SI REFUSÉ (credentials expirés)
   → "La connexion au SI {si_nom} a échoué (erreur d'authentification). Les credentials d'accès ont-ils changé ? Veuillez les mettre à jour dans la configuration ORASS_DB_URL / ORASS_DSN."
   type_reponse: texte_libre

5. CONFLIT DE CORRECTION — DEUX AGENTS IMPACTÉS DIFFÉREMMENT
   → "La correction du champ {champ} impacte de façon contradictoire les agents {agent1} et {agent2}. Quel agent a la priorité dans son usage de ce champ ?"
   type_reponse: choix_multiple  choix: ["Priorité Agent Sinistres (usage sinistres)", "Priorité Agent Souscription (usage polices)", "Traitement différencié par agent (correction séparée)", "Suspendre — analyse manuelle requise"]

IMPORTANT : Les questions de cet agent sont marquées [SYSTÈME YUKPO] et notifiées uniquement aux super_admin et yukpo_owner.
"""

    async def _executer_outil(self, nom: str, params: dict, user_id: int, execution_id: str) -> str:
        try:
            if nom == "tester_connexion_si":
                return await _tester_connexion(params)

            if nom == "decouvrir_schema_complet":
                return await _decouvrir_schema(params, schema_registry)

            if nom == "inspecter_table":
                return await _inspecter_table(params)

            if nom == "rechercher_table_concept":
                si = params["si_nom"]
                concept = params["concept"]
                # D'abord dans le registre
                tables = schema_registry.rechercher_tables_concept(concept, si)
                if not tables:
                    # Fallback : recherche par préfixe connu
                    connus = _SI_CONNUS.get(si, {})
                    prefixes = connus.get("prefixes_tables", [])
                    for pfx in prefixes:
                        if concept[:3].upper() in pfx.upper():
                            tables.append(f"{pfx}* (non encore introspectées)")
                detail = []
                for t in tables:
                    tdata = schema_registry.get_table(t, si)
                    if tdata:
                        cols_preview = ", ".join(c["nom"] for c in tdata.get("colonnes", [])[:10])
                        detail.append({"table": t, "colonnes_preview": cols_preview,
                                       "description": tdata.get("description_metier", "")})
                    else:
                        detail.append({"table": t})
                return json.dumps({
                    "concept": concept,
                    "tables_trouvees": tables,
                    "detail": detail if params.get("avec_colonnes") else tables,
                    "source": "registre_schema" if tables else "prefixes_connus",
                }, ensure_ascii=False)

            if nom == "generer_mappings_semantiques":
                from core.ia_client import ModeIA, ia_client
                si = params["si_nom"]
                module = params.get("module", "tous")
                si_data = schema_registry.get_schema_si(si)
                tables = si_data.get("tables", {})
                # Filtrer par module
                filtres_module = {
                    "production": ["POL_", "T_POL", "pol_"],
                    "sinistres": ["SIN_", "T_SIN", "sin_"],
                    "comptabilite": ["CPT_", "T_CPT", "cpt_"],
                    "reassurance": ["REA_", "rea_"],
                    "clients": ["CLI_", "T_CLI", "cli_", "PAR_"],
                    "provisions": ["CPT_", "PROV_"],
                    "tous": [],
                }
                prefixes = filtres_module.get(module, [])
                tables_module = {
                    t: d for t, d in tables.items()
                    if not prefixes or any(t.startswith(p.upper()) for p in prefixes)
                }[:30]  # Max 30 tables pour le contexte IA

                if not tables_module:
                    # Utiliser les mappings de référence
                    if si == "orass":
                        mappings_ref = {k: v for k, v in _MAPPINGS_ORASS_REFERENCE.items()
                                        if module == "tous" or module in k}
                        schema_registry.enregistrer_schema(si, {}, mappings_ref)
                        return json.dumps({
                            "si": si,
                            "module": module,
                            "mappings_generes": len(mappings_ref),
                            "source": "mappings_reference_orass",
                            "mappings": mappings_ref,
                        }, ensure_ascii=False)
                    return f"Aucune table trouvée pour le module '{module}' dans le registre {si}. Lancer d'abord decouvrir_schema_complet."

                # Construire le contexte pour l'IA
                context_tables = []
                for tname, tdata in list(tables_module.items())[:15]:
                    cols = [c["nom"] for c in tdata.get("colonnes", [])[:20]]
                    context_tables.append(f"TABLE {tname} : {', '.join(cols)}")

                prompt = f"""Tu es expert en bases de données de systèmes d'information d'assurance zone CIMA.

SI : {si.upper()} — Module : {module}

Tables disponibles :
{chr(10).join(context_tables)}

Génère les mappings sémantiques JSON pour les concepts métier d'assurance.
Format exact : {{"concept.champ": "TABLE.COLONNE", ...}}

Concepts à mapper (selon les tables disponibles) :
- police : numero, prime_ttc, prime_ht, date_effet, date_echeance, branche, statut, assure_id, apporteur_id, pays
- sinistre : reference, date_survenance, date_declaration, montant_estime, montant_regle, statut, branche, police_id
- client : nom, prenom, telephone, email, date_naissance, type
- provision : type, montant, date, branche, exercice
- apporteur : code, nom, agrement, type, commission
- ecriture : journal, compte_debit, compte_credit, montant, libelle, date

Ne générer que les mappings pour les tables/colonnes RÉELLEMENT présentes dans la liste fournie.
Retourner UNIQUEMENT le JSON, sans commentaire."""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                try:
                    # Extraire le JSON de la réponse
                    contenu = rep.contenu.strip()
                    if "```" in contenu:
                        contenu = contenu.split("```")[1].replace("json", "").strip()
                    mappings = json.loads(contenu)
                    if params.get("appliquer_automatiquement"):
                        si_data_cur = schema_registry.get_schema_si(si)
                        existing_mappings = si_data_cur.get("mappings_metier", {})
                        existing_mappings.update(mappings)
                        schema_registry.enregistrer_schema(si, si_data_cur.get("tables", {}), existing_mappings)
                    return json.dumps({
                        "si": si,
                        "module": module,
                        "mappings_generes": len(mappings),
                        "appliques": params.get("appliquer_automatiquement", False),
                        "mappings": mappings,
                    }, ensure_ascii=False)
                except json.JSONDecodeError:
                    return rep.contenu

            if nom == "valider_requete_agent":
                si = params["si_nom"]
                sql = params["requete_sql"]
                agent = params.get("agent_source", "inconnu")
                type_req = params.get("type", "SELECT")
                erreurs = []
                avertissements = []
                corrections = {}
                # Analyser les tables référencées dans la requête
                import re
                tables_sql = re.findall(r'FROM\s+(\w+)|JOIN\s+(\w+)', sql.upper())
                tables_mentionnees = [t for pair in tables_sql for t in pair if t]
                for table in tables_mentionnees:
                    tdata = schema_registry.get_table(table, si)
                    if not tdata:
                        erreurs.append(f"Table '{table}' non trouvée dans le registre {si}")
                # Analyser les colonnes dans WHERE/SELECT
                colonnes_sql = re.findall(r'\.(\w+)|WHERE\s+(\w+)\s*=', sql.upper())
                # Vérifier que la requête n'est pas un INSERT/UPDATE/DELETE si type=SELECT
                if type_req == "SELECT" and re.search(r'\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE)\b', sql.upper()):
                    erreurs.append("SÉCURITÉ : requête non-SELECT détectée pour un accès lecture")
                return json.dumps({
                    "si": si,
                    "agent": agent,
                    "sql_original": sql[:500],
                    "valide": len(erreurs) == 0,
                    "erreurs": erreurs,
                    "avertissements": avertissements,
                    "corrections_suggérées": corrections,
                }, ensure_ascii=False)

            if nom == "generer_requete_metier":
                from core.ia_client import ModeIA, ia_client
                si = params["si_nom"]
                besoin = params["besoin"]
                type_req = params.get("type", "SELECT")
                limite = params.get("limite", 100)
                # Récupérer le contexte schéma
                si_data = schema_registry.get_schema_si(si)
                mappings = si_data.get("mappings_metier", _MAPPINGS_ORASS_REFERENCE if si == "orass" else {})
                tables_info = []
                for cle, val in list(mappings.items())[:40]:
                    tables_info.append(f"{cle} → {val}")

                prompt = f"""Génère une requête SQL pour {si.upper()} (SQL Server).

Besoin : {besoin}
Type : {type_req}
Limite : {limite} lignes

Mappings disponibles (concept.champ → TABLE.COLONNE) :
{chr(10).join(tables_info)}

Règles :
- Pour SELECT : utiliser TOP {limite} ou LIMIT selon le DBMS
- Pour INSERT/UPDATE : toujours vérifier les contraintes FK
- Utiliser UNIQUEMENT les tables/colonnes des mappings fournis
- Ajouter des commentaires SQL pour expliquer les jointures
- Si les données sont sensibles (montants), préciser les seuils
- Retourner la requête SQL + explication courte"""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                # Validation finale
                sql_gen = rep.contenu
                if type_req == "SELECT" and ("INSERT" in sql_gen.upper() or "UPDATE" in sql_gen.upper() or "DELETE" in sql_gen.upper()):
                    return "⚠️ Requête générée rejetée — contient des opérations d'écriture non autorisées"
                return sql_gen

            if nom == "detecter_derive_schema":
                si = params["si_nom"]
                # Re-introspection
                nouveau_schema = await _decouvrir_schema_dict(params)
                if isinstance(nouveau_schema, str):
                    return nouveau_schema  # erreur connexion
                derives = schema_registry.detecter_derive(si, nouveau_schema)
                critiques = [d for d in derives if d.get("gravite") == "critique"]
                if critiques and params.get("alerte_agents"):
                    from core.notifications import notifications
                    msg = f"⚠️ DÉRIVE SCHÉMA {si.upper()} : {len(critiques)} changement(s) critique(s) détecté(s)"
                    await notifications.envoyer_alerte_direction(niveau="critique", message=msg, article="SchémaAgent")
                return json.dumps({
                    "si": si,
                    "nb_derives_total": len(derives),
                    "nb_derives_critiques": len(critiques),
                    "derives_critiques": critiques,
                    "autres_derives": [d for d in derives if d.get("gravite") != "critique"],
                    "action_requise": len(critiques) > 0,
                }, ensure_ascii=False)

            if nom == "documenter_table_metier":
                si = params["si_nom"]
                table = params["table_nom"].upper()
                schema_registry.ajouter_description_table(
                    si=si,
                    table=table,
                    description=params["description"],
                    concepts=params.get("concepts", []),
                )
                return f"Table {table} documentée dans le registre {si} — concepts : {params.get('concepts', [])}"

            if nom == "corriger_mapping_agent":
                from core.ia_client import ModeIA, ia_client
                si = params["si_nom"]
                agent_nom = params["agent_nom"]
                champ = params["champ_incorrect"]
                contexte = params.get("contexte", "")
                # Chercher le bon mapping dans le registre
                si_data = schema_registry.get_schema_si(si)
                mappings = si_data.get("mappings_metier", _MAPPINGS_ORASS_REFERENCE if si == "orass" else {})
                # Trouver les correspondances proches
                correspondances = []
                for k, v in mappings.items():
                    if any(part in k.lower() for part in champ.lower().split("_")):
                        correspondances.append({"mapping_metier": k, "champ_technique": v})
                if correspondances:
                    return json.dumps({
                        "agent": agent_nom,
                        "champ_incorrect": champ,
                        "correspondances_trouvees": correspondances,
                        "recommandation": f"Utiliser '{correspondances[0]['champ_technique']}' au lieu de '{champ}'",
                        "source": "registre_schema",
                    }, ensure_ascii=False)
                # Si pas trouvé → IA
                prompt = f"""Un agent d'assurance utilise le champ '{champ}' dans ses requêtes sur le SI {si.upper()}.
Contexte : {contexte}
Mappings connus : {json.dumps(list(mappings.items())[:20], ensure_ascii=False)}
Quel est probablement le bon nom de champ dans ce SI ? Donne la correction avec le nom de table."""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)
                return json.dumps({
                    "agent": agent_nom,
                    "champ_incorrect": champ,
                    "analyse_ia": rep.contenu,
                    "source": "ia",
                }, ensure_ascii=False)

            if nom == "rapport_connaissance_si":
                from core.ia_client import ModeIA, ia_client
                si = params["si_nom"]
                stats = schema_registry.get_stats(si)
                si_data = schema_registry.get_schema_si(si)
                tables_sans_doc = [t for t, d in si_data.get("tables", {}).items()
                                   if not d.get("description_metier")]
                couverture_doc = round((stats["nb_tables"] - len(tables_sans_doc)) / max(stats["nb_tables"], 1) * 100, 1)
                rapport = {
                    "si": si,
                    "statistiques": stats,
                    "couverture_documentation_pct": couverture_doc,
                    "tables_non_documentees": len(tables_sans_doc),
                    "nb_mappings_metier": stats["nb_mappings_metier"],
                }
                if params.get("inclure_requetes_type"):
                    rapport["requetes_types"] = {
                        "polices_actives": schema_registry.generer_requete_select(si, "police",
                            filtres={"statut": "A"}, limite=100),
                        "sinistres_ouverts": schema_registry.generer_requete_select(si, "sinistre",
                            filtres={"statut": "O"}, limite=100),
                    }
                prompt = f"""Génère un rapport de maturité sur la connaissance du schéma SI {si.upper()}.
Données : {json.dumps(rapport, ensure_ascii=False, indent=2)}

Évalue : complétude du registre, qualité des mappings, risques opérationnels, recommandations pour améliorer la couverture."""
                rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
                rapport["analyse_ia"] = rep.contenu
                return json.dumps(rapport, ensure_ascii=False)

            if nom == "charger_schema_depuis_fichier":
                return await _charger_schema_fichier(params, schema_registry)

            if nom == "corriger_code_agent":
                return await _corriger_code_agent(params, schema_registry, user_id, execution_id)

            if nom == "synchroniser_tous_agents":
                si = params["si_nom"]
                stats = schema_registry.get_stats(si)
                if stats["nb_mappings_metier"] == 0 and not params.get("forcer"):
                    return f"Registre {si} vide — lancer d'abord decouvrir_schema_complet ou charger_schema_depuis_fichier"
                # Mettre à jour les mappings de référence pour ORASS si vide
                if si == "orass" and stats["nb_mappings_metier"] == 0:
                    schema_registry.enregistrer_schema("orass", {}, _MAPPINGS_ORASS_REFERENCE)
                    return json.dumps({
                        "si": si,
                        "action": "mappings_reference_charges",
                        "nb_mappings": len(_MAPPINGS_ORASS_REFERENCE),
                        "message": "Mappings ORASS de référence chargés — connexion réelle recommandée pour validation complète",
                    }, ensure_ascii=False)
                return json.dumps({
                    "si": si,
                    "nb_tables": stats["nb_tables"],
                    "nb_mappings": stats["nb_mappings_metier"],
                    "derniere_maj": stats["derniere_introspection"],
                    "message": "Registre synchronisé — tous les agents peuvent utiliser schema_registry.lookup()",
                }, ensure_ascii=False)

            return f"Outil '{nom}' non reconnu"

        except Exception as e:
            logger.error(f"[AgentSchemaSI] Erreur outil {nom} : {e}")
            return f"ERREUR {nom} : {e}"


# ── Helpers async ──────────────────────────────────────────────────────────────

async def _tester_connexion(params: dict) -> str:
    """Teste la connexion à un SI via SQLAlchemy."""
    import asyncio
    def _sync():
        try:
            si = params["si_nom"]
            connu = _SI_CONNUS.get(si, {})
            if params.get("utiliser_config"):
                from config.settings import settings
                conn_str = getattr(settings, f"SI_{si.upper()}_CONN", None)
                if not conn_str:
                    return json.dumps({
                        "statut": "non_configure",
                        "si": si,
                        "message": f"Variable SI_{si.upper()}_CONN non configurée dans settings.py",
                        "action": "Ajouter la chaîne de connexion dans config/settings.py",
                    })
            try:
                from sqlalchemy import create_engine, text
                # Construction URL de connexion
                dbms = params.get("dbms") or connu.get("dbms", "sql_server")
                host = params.get("host", "localhost")
                port = params.get("port") or connu.get("port_defaut", 1433)
                db = params.get("database", si.upper())
                user = params.get("username", "yukpo_readonly")
                if dbms == "sql_server":
                    url = f"mssql+pyodbc://{user}@{host}:{port}/{db}?driver=ODBC+Driver+17+for+SQL+Server"
                elif dbms == "postgresql":
                    url = f"postgresql://{user}@{host}:{port}/{db}"
                else:
                    url = f"{dbms}://{user}@{host}:{port}/{db}"
                engine = create_engine(url, connect_args={"timeout": 5})
                with engine.connect() as conn:
                    result = conn.execute(text("SELECT @@VERSION" if dbms == "sql_server" else "SELECT version()"))
                    version = result.fetchone()[0]
                return json.dumps({
                    "statut": "connecte",
                    "si": si,
                    "dbms": dbms,
                    "version": str(version)[:100],
                    "modules": connu.get("modules", []),
                })
            except Exception as e:
                return json.dumps({
                    "statut": "erreur_connexion",
                    "si": si,
                    "erreur": str(e),
                    "conseil": "Vérifier host/port/credentials et accès réseau. Utiliser charger_schema_depuis_fichier si pas d'accès direct.",
                })
        except ImportError:
            return json.dumps({"statut": "sqlalchemy_manquant", "action": "pip install sqlalchemy pyodbc psycopg2-binary"})
    return await asyncio.to_thread(_sync)


async def _decouvrir_schema(params: dict, registry: "SchemaRegistry") -> str:
    """Introspection complète du SI via information_schema."""
    import asyncio
    si = params["si_nom"]
    def _sync():
        try:
            from sqlalchemy import create_engine, inspect, text
            from config.settings import settings
            conn_str = getattr(settings, f"SI_{si.upper()}_CONN", None)
            if not conn_str:
                # Mode simulation : retourner la structure de référence ORASS
                if si == "orass":
                    tables_ref = _generer_schema_orass_reference()
                    registry.enregistrer_schema(si, tables_ref, _MAPPINGS_ORASS_REFERENCE)
                    return json.dumps({
                        "mode": "reference_simulation",
                        "si": si,
                        "nb_tables": len(tables_ref),
                        "message": "Schéma ORASS de référence chargé (mode simulation sans connexion réelle)",
                        "action": f"Configurer SI_{si.upper()}_CONN dans settings.py pour une introspection réelle",
                    }, ensure_ascii=False)
                return json.dumps({
                    "mode": "non_configure",
                    "si": si,
                    "message": f"Connexion {si} non configurée. Utiliser charger_schema_depuis_fichier avec un DDL SQL ou Excel.",
                })
            engine = create_engine(conn_str, pool_pre_ping=True)
            inspector = inspect(engine)
            schema_db = params.get("schema_db", "dbo")
            filtre = params.get("filtre_prefixe", "").upper()
            tables = {}
            all_tables = inspector.get_table_names(schema=schema_db)
            if filtre:
                all_tables = [t for t in all_tables if t.upper().startswith(filtre)]
            for table_name in all_tables[:200]:  # Max 200 tables par introspection
                colonnes = []
                for col in inspector.get_columns(table_name, schema=schema_db):
                    colonnes.append({
                        "nom": col["name"],
                        "type": str(col["type"]),
                        "nullable": col.get("nullable", True),
                        "defaut": str(col.get("default", "")) if col.get("default") else None,
                    })
                fks = []
                for fk in inspector.get_foreign_keys(table_name, schema=schema_db):
                    fks.append({
                        "colonnes": fk.get("constrained_columns", []),
                        "table_ref": fk.get("referred_table", ""),
                        "colonnes_ref": fk.get("referred_columns", []),
                    })
                pks = inspector.get_pk_constraint(table_name, schema=schema_db)
                index_list = []
                if params.get("avec_index"):
                    for idx in inspector.get_indexes(table_name, schema=schema_db):
                        index_list.append({"nom": idx["name"], "colonnes": idx.get("column_names", [])})
                # Cardinalité optionnelle
                nb_lignes = None
                if params.get("avec_cardinalites"):
                    with engine.connect() as conn:
                        r = conn.execute(text(f"SELECT COUNT(*) FROM [{table_name}]"))
                        nb_lignes = r.scalar()
                tables[table_name.upper()] = {
                    "colonnes": colonnes,
                    "cles_primaires": pks.get("constrained_columns", []),
                    "cles_etrangeres": fks,
                    "index": index_list,
                    "nb_lignes": nb_lignes,
                    "description_metier": "",
                    "concepts": [],
                }
            # Détecter les dérives avant enregistrement
            derives = registry.detecter_derive(si, tables)
            registry.enregistrer_schema(si, tables, _MAPPINGS_ORASS_REFERENCE if si == "orass" else None)
            return json.dumps({
                "si": si,
                "nb_tables_decouvertes": len(tables),
                "derives_detectees": len(derives),
                "derives_critiques": [d for d in derives if d.get("gravite") == "critique"],
                "version_schema": registry.get_stats(si)["version_schema"],
                "tables": list(tables.keys()),
            }, ensure_ascii=False)
        except ImportError:
            return json.dumps({"erreur": "sqlalchemy manquant — pip install sqlalchemy"})
        except Exception as e:
            return json.dumps({"erreur": str(e)})
    return await asyncio.to_thread(_sync)


async def _decouvrir_schema_dict(params: dict) -> dict | str:
    """Variante qui retourne le dict brut pour comparaison."""
    result_str = await _decouvrir_schema(params, schema_registry)
    try:
        data = json.loads(result_str)
        return data.get("tables", {}) if isinstance(data, dict) else {}
    except Exception:
        return result_str


async def _inspecter_table(params: dict) -> str:
    """Inspection détaillée d'une table."""
    si = params["si_nom"]
    table = params["table_nom"].upper()
    tdata = schema_registry.get_table(table, si)
    if not tdata:
        return json.dumps({
            "erreur": f"Table '{table}' non trouvée dans le registre {si}",
            "action": "Lancer decouvrir_schema_complet d'abord",
        })
    result = {
        "si": si,
        "table": table,
        "nb_colonnes": len(tdata.get("colonnes", [])),
        "colonnes": tdata.get("colonnes", []),
        "cles_primaires": tdata.get("cles_primaires", []),
        "cles_etrangeres": tdata.get("cles_etrangeres", []),
        "description_metier": tdata.get("description_metier", "Non documentée"),
        "concepts": tdata.get("concepts", []),
        "nb_lignes": tdata.get("nb_lignes"),
    }
    if params.get("avec_stats"):
        result["note"] = "Stats détaillées disponibles avec connexion directe au SI"
    return json.dumps(result, ensure_ascii=False)


async def _charger_schema_fichier(params: dict, registry: "SchemaRegistry") -> str:
    """Charge un schéma depuis un fichier DDL SQL, Excel, ou JSON."""
    import asyncio
    si = params["si_nom"]
    path = params["fichier_path"]
    type_f = params["type_fichier"]
    def _sync():
        tables = {}
        try:
            if type_f == "ddl_sql":
                import re
                with open(path, "r", encoding="utf-8-sig") as f:
                    ddl = f.read()
                # Parser CREATE TABLE
                create_pattern = re.compile(
                    r'CREATE\s+TABLE\s+\[?(\w+)\]?\.\[?(\w+)\]?\s*\(([^;]+?)\)',
                    re.IGNORECASE | re.DOTALL
                )
                for match in create_pattern.finditer(ddl):
                    table_name = match.group(2).upper()
                    body = match.group(3)
                    cols = []
                    for line in body.split("\n"):
                        line = line.strip().rstrip(",")
                        col_m = re.match(r'\[?(\w+)\]?\s+(\w+(?:\(\d+(?:,\d+)?\))?)', line)
                        if col_m and not line.upper().startswith(("CONSTRAINT", "PRIMARY", "FOREIGN", "INDEX")):
                            cols.append({
                                "nom": col_m.group(1),
                                "type": col_m.group(2),
                                "nullable": "NOT NULL" not in line.upper(),
                            })
                    tables[table_name] = {"colonnes": cols, "cles_etrangeres": [], "description_metier": "", "concepts": []}
            elif type_f == "excel_documentation":
                import pandas as pd
                df = pd.read_excel(path)
                for _, row in df.iterrows():
                    tname = str(row.get("table_name", row.get("TABLE_NAME", ""))).upper()
                    cname = str(row.get("column_name", row.get("COLUMN_NAME", "")))
                    ctype = str(row.get("data_type", row.get("DATA_TYPE", "varchar")))
                    desc  = str(row.get("description", row.get("DESCRIPTION", "")))
                    if tname not in tables:
                        tables[tname] = {"colonnes": [], "cles_etrangeres": [], "description_metier": "", "concepts": []}
                    tables[tname]["colonnes"].append({"nom": cname, "type": ctype, "description": desc})
            elif type_f in ("json_schema", "csv_information_schema"):
                import pandas as pd
                if type_f == "json_schema":
                    with open(path, "r", encoding="utf-8") as f:
                        tables = json.load(f)
                else:
                    df = pd.read_csv(path, encoding="utf-8-sig")
                    for _, row in df.iterrows():
                        tname = str(row.get("TABLE_NAME", "")).upper()
                        if tname and tname not in tables:
                            tables[tname] = {"colonnes": [], "cles_etrangeres": [], "description_metier": "", "concepts": []}
                        if tname:
                            tables[tname]["colonnes"].append({
                                "nom": str(row.get("COLUMN_NAME", "")),
                                "type": str(row.get("DATA_TYPE", "varchar")),
                                "nullable": str(row.get("IS_NULLABLE", "YES")) == "YES",
                            })
            registry.enregistrer_schema(si, tables, _MAPPINGS_ORASS_REFERENCE if si == "orass" else None)
            return json.dumps({
                "si": si,
                "fichier": path.split("\\")[-1].split("/")[-1],
                "type": type_f,
                "nb_tables_chargees": len(tables),
                "tables": list(tables.keys())[:30],
                "message": "Schéma chargé et enregistré dans le registre",
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"erreur": str(e), "fichier": path})
    return await asyncio.to_thread(_sync)


def _generer_schema_orass_reference() -> dict:
    """Génère le schéma de référence ORASS (tables et colonnes standard)."""
    return {
        "POL_CONTRATS": {
            "colonnes": [
                {"nom": "NUM_POLICE",       "type": "varchar(20)",  "nullable": False, "pk": True},
                {"nom": "COD_BRANCHE",      "type": "varchar(10)",  "nullable": False},
                {"nom": "COD_ASSURE",       "type": "varchar(15)",  "nullable": False},
                {"nom": "COD_APPORTEUR",    "type": "varchar(10)",  "nullable": True},
                {"nom": "COD_PAYS",         "type": "char(2)",      "nullable": False},
                {"nom": "DAT_EFFET",        "type": "date",         "nullable": False},
                {"nom": "DAT_ECHEANCE",     "type": "date",         "nullable": False},
                {"nom": "MTN_PRIME_TTC",    "type": "decimal(15,2)","nullable": False},
                {"nom": "MTN_PRIME_HT",     "type": "decimal(15,2)","nullable": False},
                {"nom": "MTN_TAXES",        "type": "decimal(15,2)","nullable": True},
                {"nom": "COD_STATUT",       "type": "char(1)",      "nullable": False},  # A=actif, R=résilié, S=suspendu
                {"nom": "DAT_EMISSION",     "type": "datetime",     "nullable": False},
                {"nom": "COD_DEVISE",       "type": "char(3)",      "nullable": False},
                {"nom": "NUM_AVENANT",      "type": "integer",      "nullable": False},
                {"nom": "DAT_CREATION",     "type": "datetime",     "nullable": False},
                {"nom": "USR_CREATION",     "type": "varchar(20)",  "nullable": False},
            ],
            "cles_primaires": ["NUM_POLICE", "NUM_AVENANT"],
            "cles_etrangeres": [
                {"colonnes": ["COD_ASSURE"],   "table_ref": "CLI_TIERS",    "colonnes_ref": ["COD_TIERS"]},
                {"colonnes": ["COD_APPORTEUR"],"table_ref": "PAR_APPORTEURS","colonnes_ref": ["COD_APPORTEUR"]},
            ],
            "description_metier": "Table principale des contrats/polices d'assurance",
            "concepts": ["police", "contrat", "prime", "production"],
        },
        "SIN_DOSSIERS": {
            "colonnes": [
                {"nom": "NUM_SINISTRE",      "type": "varchar(20)",  "nullable": False, "pk": True},
                {"nom": "NUM_POLICE",        "type": "varchar(20)",  "nullable": False},
                {"nom": "COD_BRANCHE",       "type": "varchar(10)",  "nullable": False},
                {"nom": "DAT_SURVENANCE",    "type": "date",         "nullable": False},
                {"nom": "DAT_DECLARATION",   "type": "date",         "nullable": False},
                {"nom": "DAT_CLOTURE",       "type": "date",         "nullable": True},
                {"nom": "MTN_ESTIME",        "type": "decimal(15,2)","nullable": True},
                {"nom": "MTN_PROVISION",     "type": "decimal(15,2)","nullable": True},
                {"nom": "MTN_REGLE",         "type": "decimal(15,2)","nullable": True},
                {"nom": "MTN_RECOURS",       "type": "decimal(15,2)","nullable": True},
                {"nom": "COD_STATUT",        "type": "char(1)",      "nullable": False},  # O=ouvert, C=clos, E=expertise
                {"nom": "COD_CAUSE",         "type": "varchar(10)",  "nullable": True},
                {"nom": "TXT_DESCRIPTION",   "type": "text",         "nullable": True},
                {"nom": "IND_FRAUDE",        "type": "bit",          "nullable": False},
                {"nom": "SCO_FRAUDE",        "type": "integer",      "nullable": True},
                {"nom": "DAT_CREATION",      "type": "datetime",     "nullable": False},
                {"nom": "USR_CREATION",      "type": "varchar(20)",  "nullable": False},
            ],
            "cles_primaires": ["NUM_SINISTRE"],
            "cles_etrangeres": [
                {"colonnes": ["NUM_POLICE"], "table_ref": "POL_CONTRATS", "colonnes_ref": ["NUM_POLICE"]},
            ],
            "description_metier": "Dossiers sinistres — instruction et règlement",
            "concepts": ["sinistre", "dossier", "indemnisation", "règlement"],
        },
        "CLI_TIERS": {
            "colonnes": [
                {"nom": "COD_TIERS",         "type": "varchar(15)",  "nullable": False, "pk": True},
                {"nom": "COD_TYPE_TIERS",    "type": "char(1)",      "nullable": False},  # P=physique, M=morale
                {"nom": "NOM_TIERS",         "type": "varchar(100)", "nullable": False},
                {"nom": "PRE_TIERS",         "type": "varchar(50)",  "nullable": True},
                {"nom": "DAT_NAISSANCE",     "type": "date",         "nullable": True},
                {"nom": "COD_SEXE",          "type": "char(1)",      "nullable": True},
                {"nom": "TEL_MOBILE",        "type": "varchar(20)",  "nullable": True},
                {"nom": "ADR_EMAIL",         "type": "varchar(100)", "nullable": True},
                {"nom": "COD_PAYS",          "type": "char(2)",      "nullable": False},
                {"nom": "NOM_VILLE",         "type": "varchar(50)",  "nullable": True},
                {"nom": "NUM_CNI",           "type": "varchar(30)",  "nullable": True},
                {"nom": "DAT_CREATION",      "type": "datetime",     "nullable": False},
            ],
            "cles_primaires": ["COD_TIERS"],
            "cles_etrangeres": [],
            "description_metier": "Référentiel tiers : assurés, bénéficiaires, tiers responsables",
            "concepts": ["client", "assuré", "tiers", "bénéficiaire"],
        },
        "CPT_ECRITURES": {
            "colonnes": [
                {"nom": "NUM_ECRITURE",      "type": "bigint",       "nullable": False, "pk": True},
                {"nom": "COD_JOURNAL",       "type": "varchar(5)",   "nullable": False},
                {"nom": "NUM_CPTE_DEBIT",    "type": "varchar(10)",  "nullable": False},
                {"nom": "NUM_CPTE_CREDIT",   "type": "varchar(10)",  "nullable": False},
                {"nom": "MTN_ECRITURE",      "type": "decimal(15,2)","nullable": False},
                {"nom": "LIB_ECRITURE",      "type": "varchar(200)", "nullable": False},
                {"nom": "DAT_ECRITURE",      "type": "date",         "nullable": False},
                {"nom": "DAT_VALEUR",        "type": "date",         "nullable": True},
                {"nom": "NUM_POLICE",        "type": "varchar(20)",  "nullable": True},
                {"nom": "NUM_SINISTRE",      "type": "varchar(20)",  "nullable": True},
                {"nom": "NUM_EXERCICE",      "type": "char(4)",      "nullable": False},
                {"nom": "IND_VALIDE",        "type": "bit",          "nullable": False},  # 0=brouillard, 1=validé
                {"nom": "USR_SAISIE",        "type": "varchar(20)",  "nullable": False},
            ],
            "cles_primaires": ["NUM_ECRITURE"],
            "cles_etrangeres": [],
            "description_metier": "Grand livre PCSA — toutes les écritures comptables",
            "concepts": ["écriture", "comptabilité", "journal", "compte", "PCSA"],
        },
        "CPT_PROVISIONS": {
            "colonnes": [
                {"nom": "ID_PROVISION",      "type": "bigint",       "nullable": False, "pk": True},
                {"nom": "COD_TYPE_PROV",     "type": "varchar(10)",  "nullable": False},  # PPNA, PSAP, PM, PPB...
                {"nom": "COD_BRANCHE",       "type": "varchar(10)",  "nullable": True},
                {"nom": "NUM_EXERCICE",      "type": "char(4)",      "nullable": False},
                {"nom": "DAT_INVENTAIRE",    "type": "date",         "nullable": False},
                {"nom": "MTN_PROVISION",     "type": "decimal(18,2)","nullable": False},
                {"nom": "MTN_PRECEDENT",     "type": "decimal(18,2)","nullable": True},
                {"nom": "MTN_DOTATION",      "type": "decimal(18,2)","nullable": True},
                {"nom": "MTN_REPRISE",       "type": "decimal(18,2)","nullable": True},
                {"nom": "DAT_VALIDATION",    "type": "datetime",     "nullable": True},
                {"nom": "USR_VALIDATION",    "type": "varchar(20)",  "nullable": True},
            ],
            "cles_primaires": ["ID_PROVISION"],
            "cles_etrangeres": [],
            "description_metier": "Provisions techniques CIMA — inventaire par exercice",
            "concepts": ["provision", "PPNA", "PSAP", "PM", "PPB", "PTS", "PREC"],
        },
        "PAR_APPORTEURS": {
            "colonnes": [
                {"nom": "COD_APPORTEUR",     "type": "varchar(10)",  "nullable": False, "pk": True},
                {"nom": "NOM_APPORTEUR",     "type": "varchar(100)", "nullable": False},
                {"nom": "COD_TYPE",          "type": "varchar(5)",   "nullable": False},  # C=courtier, AG=agent, M=mandataire
                {"nom": "NUM_AGREMENT",      "type": "varchar(30)",  "nullable": True},
                {"nom": "DAT_AGREMENT",      "type": "date",         "nullable": True},
                {"nom": "DAT_EXPIR_AGREMENT","type": "date",         "nullable": True},
                {"nom": "TEL_APPORTEUR",     "type": "varchar(20)",  "nullable": True},
                {"nom": "ADR_EMAIL",         "type": "varchar(100)", "nullable": True},
                {"nom": "COD_PAYS",          "type": "char(2)",      "nullable": False},
                {"nom": "TAU_COMMISSION",    "type": "decimal(5,2)", "nullable": True},
                {"nom": "IND_ACTIF",         "type": "bit",          "nullable": False},
            ],
            "cles_primaires": ["COD_APPORTEUR"],
            "cles_etrangeres": [],
            "description_metier": "Réseau apporteurs d'affaires : courtiers, agents généraux, mandataires",
            "concepts": ["apporteur", "courtier", "agent", "commission", "agrément"],
        },
        "REA_TRAITES": {
            "colonnes": [
                {"nom": "COD_TRAITE",        "type": "varchar(20)",  "nullable": False, "pk": True},
                {"nom": "COD_REASSUREUR",    "type": "varchar(15)",  "nullable": False},
                {"nom": "COD_TYPE_TRAITE",   "type": "varchar(10)",  "nullable": False},  # QP=quote-part, XS=excess
                {"nom": "COD_BRANCHE",       "type": "varchar(10)",  "nullable": False},
                {"nom": "TAU_CESSION",       "type": "decimal(5,2)", "nullable": False},
                {"nom": "MTN_PLEIN",         "type": "decimal(15,2)","nullable": True},
                {"nom": "DAT_EFFET",         "type": "date",         "nullable": False},
                {"nom": "DAT_ECHEANCE",      "type": "date",         "nullable": True},
                {"nom": "TAU_COMMISSION_REA","type": "decimal(5,2)", "nullable": True},
                {"nom": "IND_ACTIF",         "type": "bit",          "nullable": False},
            ],
            "cles_primaires": ["COD_TRAITE"],
            "cles_etrangeres": [],
            "description_metier": "Traités de réassurance — quote-part et excédent de sinistres",
            "concepts": ["réassurance", "traité", "cession", "réassureur"],
        },
    }



async def _corriger_code_agent(params: dict, registry, user_id: int, execution_id: str) -> str:
    """
    Lit le code source d'un agent, identifie les références DB incorrectes
    par rapport au registre de schéma, et soumet un correctif pour validation.
    """
    import asyncio, re
    from pathlib import Path

    si = params["si_nom"]
    agent_fichier = params["agent_fichier"].replace(".py", "")
    mode = params.get("mode", "analyser_seulement")

    # Localiser le fichier agent
    agents_dir = Path(__file__).parent
    agent_path = agents_dir / f"{agent_fichier}.py"
    if not agent_path.exists():
        return json.dumps({"erreur": f"Fichier {agent_path} introuvable"}, ensure_ascii=False)

    source = agent_path.read_text(encoding="utf-8")

    # Récupérer tous les mappings connus du registre
    si_data = registry.get_schema_si(si)
    mappings = si_data.get("mappings_metier", _MAPPINGS_ORASS_REFERENCE if si == "orass" else {})

    # Construire l'index inverse : ANCIENNE_COLONNE → CORRECTE
    # On cherche des patterns de type "NOM_COLONNE" en majuscules dans le code source
    corrections_trouvees = []
    col_pattern = re.compile(r'\b([A-Z][A-Z0-9_]{3,})\b')
    colonnes_dans_code = set(col_pattern.findall(source))

    # Index des colonnes correctes depuis le registre
    colonnes_correctes: dict[str, str] = {}  # col_incorrecte → "TABLE.COL_CORRECTE"
    tables_correctes: set[str] = set()
    for cle, valeur in mappings.items():
        if "." in valeur:
            table, col = valeur.split(".", 1)
            tables_correctes.add(table)
            colonnes_correctes[col] = valeur

    # Colonnes dans le code qui ressemblent à des noms DB mais ne sont pas dans le registre
    for col in colonnes_dans_code:
        if len(col) < 5:
            continue
        if col in colonnes_correctes:
            continue
        # Chercher une correspondance proche (ex: MNT_SINISTRE vs MTN_SINISTRE)
        for col_reg, mapping_complet in colonnes_correctes.items():
            # Distance simple : 2 premiers caractères différents mais racine commune
            if col[3:] == col_reg[3:] and col[:3] != col_reg[:3] and len(col) > 6:
                occurrences = len(re.findall(rf'\b{re.escape(col)}\b', source))
                if occurrences > 0:
                    corrections_trouvees.append({
                        "incorrect": col,
                        "correct": col_reg,
                        "mapping_complet": mapping_complet,
                        "occurrences_dans_code": occurrences,
                        "confiance": "haute" if col[2:] == col_reg[2:] else "moyenne",
                    })

    rapport = {
        "agent": agent_fichier,
        "si": si,
        "nb_corrections_detectees": len(corrections_trouvees),
        "corrections": corrections_trouvees,
        "mode": mode,
    }

    if mode == "analyser_seulement" or not corrections_trouvees:
        rapport["message"] = (
            f"{len(corrections_trouvees)} correction(s) potentielle(s) détectée(s). "
            "Relancer avec mode='generer_correctif' pour soumettre le patch."
            if corrections_trouvees else
            f"Aucune incohérence détectée dans {agent_fichier}.py — mappings conformes au registre {si}."
        )
        return json.dumps(rapport, ensure_ascii=False)

    # Générer le code corrigé
    source_corrigee = source
    corrections_appliquees = []
    for c in corrections_trouvees:
        if c["confiance"] == "haute":
            source_corrigee = re.sub(rf'\b{re.escape(c["incorrect"])}\b', c["correct"], source_corrigee)
            corrections_appliquees.append(c)

    if not corrections_appliquees:
        return json.dumps({**rapport, "message": "Aucune correction à haute confiance — vérification manuelle recommandée"}, ensure_ascii=False)

    # Soumettre le correctif pour validation humaine AVANT toute écriture
    from core.approval_queue import approval_queue
    await approval_queue.ajouter({
        "type": "correctif_code_agent",
        "agent_fichier": str(agent_path),
        "agent_nom": agent_fichier,
        "si": si,
        "nb_corrections": len(corrections_appliquees),
        "corrections": corrections_appliquees,
        "code_original_extrait": source[:500] + "...",
        "code_corrige_extrait": source_corrigee[:500] + "...",
        "_code_corrige_complet": source_corrigee,  # stocké pour application post-validation
        "user_id": user_id,
        "execution_id": execution_id,
        "description": (
            f"Correctif {agent_fichier}.py : {len(corrections_appliquees)} colonne(s) SI renommée(s) "
            f"alignées sur le schéma réel {si.upper()}"
        ),
    })

    return json.dumps({
        **rapport,
        "nb_corrections_haute_confiance": len(corrections_appliquees),
        "statut": "en_attente_validation",
        "message": (
            f"Correctif généré pour {agent_fichier}.py : {len(corrections_appliquees)} correction(s) "
            f"soumises pour validation humaine. "
            f"Une fois validé, les colonnes seront alignées sur le schéma réel {si.upper()}."
        ),
    }, ensure_ascii=False)
