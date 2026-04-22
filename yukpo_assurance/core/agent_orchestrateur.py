"""
AgentOrchestrateur — Cerveau central de la plateforme YukpoAssurance v2.

Principe :
  1. Reçoit une instruction en langage naturel
  2. Détecte l'agent spécialisé concerné
  3. Délègue à l'agent (qui tourne sa boucle outil autonome)
  4. Collecte les résultats + actions en attente de validation
  5. Stream les étapes en temps réel (SSE)

Couches :
  COUCHE 1 — Workflows déterministes (workflow_engine.py) → 0 IA
  COUCHE 2 — Agents spécialisés (IA uniquement si nécessaire)
  COUCHE 3 — Validation humaine (approval_queue.py)
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import AsyncGenerator, Optional

logger = logging.getLogger("yukpo_assurance.agent_orchestrateur")


# ─── Types ────────────────────────────────────────────────────────────────────

class TypeAgent(str, Enum):
    SINISTRES     = "sinistres"
    SOUSCRIPTION  = "souscription"
    CONFORMITE    = "conformite"
    COMMERCIAL    = "commercial"
    RH            = "rh"
    JURIDIQUE     = "juridique"
    COMPTABILITE  = "comptabilite"
    INTELLIGENCE  = "intelligence"
    VIE           = "vie"
    REASSURANCE   = "reassurance"
    PLACEMENT     = "placement"
    PROVISIONS    = "provisions"     # Provisions techniques CIMA
    ETATS_CIMA    = "etats_cima"     # États réglementés C1-C12
    SCHEMA_SI       = "schema_si"        # Découverte et cartographie SI
    META_FACTORY    = "meta_factory"     # Création autonome de nouveaux agents
    DEPLOIEMENT_SI  = "deploiement_si"   # Déploiement & intégration SI compagnies
    MALADIE         = "maladie"          # Sinistres maladie, BPC, remboursements médicaux
    SINISTRES_AUTO  = "sinistres_auto"   # Sinistres RC Auto — barème CIMA Art. 200-264
    RISQUES_DIVERS  = "risques_divers"   # RC Pro, DO, ACI, Agriculture, Crédit, Protection Juridique, MRH
    AUTO            = "auto"             # détection automatique
    # ── Plateforme Pro (professionnels africains) ─────────────────────────
    PRO_COMPTABLE   = "pro_comptable"    # Comptable / Expert-comptable / Fiscaliste
    PRO_DRH         = "pro_drh"          # DRH / Gestionnaire RH / Paie
    PRO_DAF         = "pro_daf"          # DAF / Contrôleur de gestion / Finance
    PRO_JURISTE     = "pro_juriste"      # Juriste / Avocat
    PRO_BANQUIER    = "pro_banquier"     # Banquier / Analyste crédit / Trader
    PRO_INGENIEUR   = "pro_ingenieur"    # Ingénieur / Chef de projet / Architecte BTP
    PRO_DAA         = "pro_daa"          # Data Analyst / Business Analyst
    PRO_COMMERCIAL  = "pro_commercial"   # Directeur commercial / Marketing
    PRO_ONG         = "pro_ong"          # Chargé de projet ONG / Développement / Bailleurs
    PRO_MICROFINANCE = "pro_microfinance" # Responsable SFD/IMF / Crédit officer
    PRO_DOUANIER         = "pro_douanier"          # Transitaire / Douanier / Commerce international
    PRO_GENERIQUE        = "pro_generique"         # Tout professionnel (fallback Pro)
    PRO_CV_EMPLOI        = "pro_cv_emploi"         # Rédaction CV / lettre de motivation
    PRO_RECHERCHE_EMPLOI = "pro_recherche_emploi"  # Veille et recherche d'emploi automatique


class StatutExecution(str, Enum):
    EN_COURS      = "en_cours"
    TERMINE       = "termine"
    ERREUR        = "erreur"
    EN_ATTENTE    = "en_attente_validation"


@dataclass
class EtapeAgent:
    """Une étape d'exécution de l'agent — streamée en temps réel."""
    id:           str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    type:         str = "action"          # action | ia | validation | resultat
    libelle:      str = ""
    detail:       str = ""
    statut:       str = "en_cours"        # en_cours | ok | erreur | ia
    duree_ms:     int = 0
    donnees:      dict = field(default_factory=dict)
    timestamp:    str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ResultatAgent:
    execution_id:     str
    agent:            TypeAgent
    instruction:      str
    statut:           StatutExecution
    etapes:           list[EtapeAgent]    = field(default_factory=list)
    resume:           str                 = ""
    actions_requises: list[dict]          = field(default_factory=list)  # validations en attente
    donnees_finales:  dict                = field(default_factory=dict)
    erreur:           Optional[str]       = None
    duree_totale_ms:  int                 = 0
    ia_appelee:       bool                = False   # True si au moins 1 appel IA
    cout_ia_usd:      float               = 0.0


# ─── Détecteur d'agent ────────────────────────────────────────────────────────

_MOTS_CLES_AGENTS: dict[TypeAgent, list[str]] = {
    TypeAgent.SINISTRES: [
        "sinistre", "accident", "indemnis", "régler", "regler", "rembours",
        "fraude", "dossier sinistre", "sin-", "expertise", "victime",
        "dommage", "perte", "déclaration sinistre",
    ],
    TypeAgent.SOUSCRIPTION: [
        "souscrire", "souscription", "police", "contrat", "assure", "assuré",
        "devis", "prime", "tarif", "émettre", "emettre", "renouveler",
        "kyc", "carte rose", "attestation", "garantie",
    ],
    TypeAgent.CONFORMITE: [
        "conformité", "conformite", "crca", "ratio", "solvabilité",
        "solvabilite", "audit", "rapport crca",
        "réglementaire", "reglementaire", "prudentiel",
    ],
    TypeAgent.PROVISIONS: [
        "provision technique", "ppna", "psap", "ibnr", "chain ladder",
        "provision mathématique", "provision pm", "ppb", "pts",
        "prec", "prc", "réserve technique", "dotation provision",
        "bornhuetter", "adequation provisions", "provisions cima",
    ],
    TypeAgent.ETATS_CIMA: [
        "état c1", "état c2", "état c3", "état c4", "état c5",
        "état c6", "état c7", "état c8", "état c9", "état c10",
        "état c11", "état c12", "etat cima", "liasse cima",
        "cohérence états", "coherence etats", "soumettre crca",
        "états réglementés", "etats reglementes", "contrôle cohérence",
    ],
    TypeAgent.SCHEMA_SI: [
        "schéma base", "schema base", "structure si", "introspection",
        "orass", "mercure", "saphir", "giap", "mapping métier",
        "découverte schéma", "schema_registry", "connaissance si",
        "table base données", "colonnes base", "schéma données",
    ],
    TypeAgent.META_FACTORY: [
        "créer agent", "creer agent", "nouvel agent", "nouveau agent",
        "générer agent", "generer agent", "agent manquant", "agent factory",
        "couverture agents", "workflow manquant", "workflows non couverts",
        "agent supplémentaire", "agent supplementaire", "détecter workflow",
        "analyser couverture", "meta factory", "fabrique agent",
    ],
    TypeAgent.COMMERCIAL: [
        "prospect", "client", "vente", "commercial", "relance", "campagne",
        "courtier", "apporteur", "commission", "portefeuille client",
        "fidélisation", "fidelisation", "churn", "résiliation",
    ],
    TypeAgent.RH: [
        "employé", "employe", "congé", "conge", "recrutement", "paie",
        "formation", "évaluation", "evaluation", "rh ", " rh", "équipe",
        "agenda", "réunion", "reunion", "planning",
    ],
    TypeAgent.JURIDIQUE: [
        "juridique", "recours", "contentieux", "tribunal", "litige",
        "mise en demeure", "assignation", "clause", "contrat", "accord",
        "transaction", "avocat", "procédure",
    ],
    TypeAgent.COMPTABILITE: [
        "comptab", "facture", "écriture", "ecriture", "bilan", "clôture",
        "cloture", "rapprochement", "bancaire", "trésorerie", "tresorerie",
        "pcsa", "charge", "produit", "résultat financier",
    ],
    TypeAgent.INTELLIGENCE: [
        "rapport", "analyse", "tableau de bord", "kpi", "tendance",
        "marché", "marche", "veille", "statistique", "performance",
        "direction", "conseil d'administration", "comité", "stratégie",
    ],
    TypeAgent.VIE: [
        "vie", "épargne", "epargne", "décès", "deces", "retraite",
        "prévoyance", "prevoyance", "rente", "capital", "emprunteur",
        "rachat", "avance sur police", "réduction", "reduction",
        "temporaire", "mixte", "bénéficiaire", "beneficiaire",
        "pm ", " pm ", "provision mathématique", "assurance vie",
    ],
    TypeAgent.REASSURANCE: [
        "réassurance", "reassurance", "cession", "cédante", "cedante",
        "traité", "traite proportionnel", "quote-part", "excess",
        "bordereau", "sinistre réassuré", "ristourne", "commission réassureur",
        "pool", "rétrocession", "retrocession", "réassureur",
    ],
    TypeAgent.PLACEMENT: [
        "placement", "investissement", "obligation", "action", "immobilier",
        "portefeuille", "actif", "rendement", "duration", "actuariat",
        "tables de mortalité", "projection", "stress test", "alm",
        "adossement", "actif passif", "taux de rendement",
    ],
    TypeAgent.SINISTRES_AUTO: [
        "sinistre auto", "sinistre rc auto", "accident voiture", "accident véhicule",
        "accident vehicule", "rc automobile", "rc auto", "constat amiable",
        "pv police auto", "dommage vehicule", "dommage matériel auto",
        "dommage materiel auto", "victime accident route", "blessé accident",
        "blesse accident", "décès accident route", "deces accident route",
        "expertise auto", "vrade", "valeur vénale", "valeur venale",
        "réparation véhicule", "reparation vehicule", "garage agréé",
        "franchise auto", "indemnisation auto", "corporel auto",
        "barème cima auto", "bareme cima auto", "ipp auto", "itt auto",
        "pretium doloris", "tierce personne auto", "subrogation auto",
        "conducteur fautif", "tiers adverse", "assureur tiers",
        "délit de fuite", "delit de fuite", "fleeing driver",
    ],
    TypeAgent.MALADIE: [
        "maladie", "santé", "sante", "bon de prise en charge", "bpc",
        "remboursement médical", "remboursement medical", "hospitalisation",
        "ordonnance", "maternité", "maternite", "accouchement",
        "consultation médecin", "médicament", "medicament",
        "dentaire", "optique", "lunettes", "chirurgie", "clinique",
        "tiers payant", "réseau agréé", "réseau agree",
        "invalidité", "invalidite", "longue maladie", "arrêt maladie",
        "carence maladie", "plafond remboursement", "sinistre maladie",
        "bulletin hospitalisation", "facture médicale",
    ],
    TypeAgent.DEPLOIEMENT_SI: [
        "déployer", "deployer", "déploiement", "deploiement",
        "intégrer", "integrer", "intégration si", "integration si",
        "connecter base", "connexion base", "connecteur si",
        "migration données", "migration base", "script migration",
        "si compagnie", "base de données compagnie",
        "déploiement yukpo", "deploiement yukpo",
        "orass intégr", "mercure intégr", "saphir intégr", "giap intégr",
        "sage intégr", "sage 100", "sage 1000",
        "webhook compagnie", "api compagnie",
        "installer plateforme", "configurer connecteur",
    ],
    TypeAgent.RISQUES_DIVERS: [
        "rc générale", "rc generale", "rc professionnelle", "rc pro",
        "rc décennale", "rc decennale", "dommages ouvrage", "do sinistre",
        "construction sinistre", "garantie décennale", "garantie decennale",
        "accidents corporels", "aci", "accident corporel individuel",
        "invalidité partielle", "invalidite partielle", "capital invalidité",
        "agriculture sinistre", "récolte sinistre", "bétail sinistre",
        "grêle sinistre", "sécheresse sinistre", "inondation récolte",
        "crédit impayé", "credit impaye", "caution défaillance",
        "protection juridique", "frais avocat", "honoraires avocat",
        "litige couvert", "défense juridique", "defense juridique",
        "assistance voyage", "rapatriement", "hospitalisation étranger",
        "panne véhicule assistance", "avance frais médicaux étranger",
        "mrh", "multirisques habitation", "sinistre habitation",
        "incendie habitation", "dégâts des eaux", "vol cambriolage",
        "risques divers", "sinistre divers", "branche diverse",
    ],
    TypeAgent.PRO_CV_EMPLOI: [
        "cv", "curriculum vitae", "lettre de motivation", "candidature",
        "postuler", "offre d'emploi", "offre emploi", "fiche de poste",
        "rédiger mon cv", "rediger mon cv", "adapter mon cv",
        "lettre motivation", "cover letter", "annonce emploi",
        "mise à jour cv", "mise a jour cv", "reformuler cv",
        "profil linkedin", "linkedin", "portfolio professionnel",
    ],
    TypeAgent.PRO_RECHERCHE_EMPLOI: [
        "recherche d'emploi", "recherche emploi", "cherche un poste",
        "cherche un emploi", "offres disponibles", "veille emploi",
        "alerte emploi", "trouver un travail", "trouver un poste",
        "recrutement actif", "opportunités emploi", "opportunites emploi",
        "marché de l'emploi", "marche emploi", "job market",
        "activer recherche", "configurer alerte", "offres récentes",
    ],
}


def detecter_agent(instruction: str) -> TypeAgent:
    """Détecte quel agent spécialisé doit traiter l'instruction."""
    instr_lower = instruction.lower()
    scores: dict[TypeAgent, int] = {}

    for agent, mots in _MOTS_CLES_AGENTS.items():
        score = sum(len(mot) for mot in mots if mot in instr_lower)
        if score > 0:
            scores[agent] = score

    if not scores or max(scores.values()) < 3:
        return TypeAgent.INTELLIGENCE  # défaut — agent le plus généraliste

    return max(scores, key=scores.get)


# ─── Orchestrateur principal ──────────────────────────────────────────────────

class AgentOrchestrateur:
    """
    Point d'entrée unique pour toutes les instructions agents.
    Délègue aux agents spécialisés selon le contenu de l'instruction.
    """

    def __init__(self):
        self._agents: dict[TypeAgent, any] = {}
        self._initialise = False

    def _charger_agents(self):
        """Chargement lazy des agents spécialisés."""
        if self._initialise:
            return
        try:
            from agents.agent_sinistres               import AgentSinistres
            from agents.agent_souscription            import AgentSouscription
            from agents.agent_conformite              import AgentConformite
            from agents.agent_commercial              import AgentCommercial
            from agents.agent_rh                      import AgentRH
            from agents.agent_juridique               import AgentJuridique
            from agents.agent_comptabilite            import AgentComptabilite
            from agents.agent_intelligence            import AgentIntelligence
            from agents.agent_vie                     import AgentVie
            from agents.agent_reassurance             import AgentReassurance
            from agents.agent_placement_actuariat     import AgentPlacementActuariat
            from agents.agent_provisions_techniques   import AgentProvisionsTechniques
            from agents.agent_etats_cima              import AgentEtatsCima
            from agents.agent_schema_si               import AgentSchemaSI
            from agents.agent_meta_factory            import AgentMetaFactory
            from agents.agent_deploiement_si          import AgentDeploiementSI
            from agents.agent_sinistres_maladie       import AgentSinistresMaladie
            from agents.agent_sinistres_auto          import AgentSinistresAuto
            from agents.agent_risques_divers          import AgentRisquesDivers

            self._agents = {
                TypeAgent.SINISTRES:      AgentSinistres(),
                TypeAgent.SOUSCRIPTION:   AgentSouscription(),
                TypeAgent.CONFORMITE:     AgentConformite(),
                TypeAgent.COMMERCIAL:     AgentCommercial(),
                TypeAgent.RH:             AgentRH(),
                TypeAgent.JURIDIQUE:      AgentJuridique(),
                TypeAgent.COMPTABILITE:   AgentComptabilite(),
                TypeAgent.INTELLIGENCE:   AgentIntelligence(),
                TypeAgent.VIE:            AgentVie(),
                TypeAgent.REASSURANCE:    AgentReassurance(),
                TypeAgent.PLACEMENT:      AgentPlacementActuariat(),
                TypeAgent.PROVISIONS:     AgentProvisionsTechniques(),
                TypeAgent.ETATS_CIMA:     AgentEtatsCima(),
                TypeAgent.SCHEMA_SI:      AgentSchemaSI(),
                TypeAgent.META_FACTORY:   AgentMetaFactory(),
                TypeAgent.DEPLOIEMENT_SI: AgentDeploiementSI(),
                TypeAgent.MALADIE:        AgentSinistresMaladie(),
                TypeAgent.SINISTRES_AUTO: AgentSinistresAuto(),
                TypeAgent.RISQUES_DIVERS: AgentRisquesDivers(),
            }
            self._initialise = True
        except Exception as e:
            logger.error(f"[Orchestrateur] Erreur chargement agents : {e}")

    async def executer(
        self,
        instruction: str,
        user_id: int,
        agent_type: TypeAgent = TypeAgent.AUTO,
        contexte: dict = None,
    ) -> ResultatAgent:
        """Exécute une instruction et retourne le résultat complet."""
        self._charger_agents()
        execution_id = str(uuid.uuid4())
        debut = asyncio.get_event_loop().time()

        # Détection automatique de l'agent
        if agent_type == TypeAgent.AUTO:
            agent_type = detecter_agent(instruction)
            logger.info(f"[Orchestrateur] Agent détecté : {agent_type} pour : {instruction[:60]}")

        agent = self._agents.get(agent_type)
        if not agent:
            return ResultatAgent(
                execution_id=execution_id,
                agent=agent_type,
                instruction=instruction,
                statut=StatutExecution.ERREUR,
                erreur=f"Agent {agent_type} non disponible",
            )

        try:
            resultat = await agent.executer(
                instruction=instruction,
                user_id=user_id,
                contexte=contexte or {},
                execution_id=execution_id,
            )
            resultat.duree_totale_ms = int((asyncio.get_event_loop().time() - debut) * 1000)
            return resultat
        except Exception as e:
            logger.error(f"[Orchestrateur] Erreur agent {agent_type} : {e}")
            return ResultatAgent(
                execution_id=execution_id,
                agent=agent_type,
                instruction=instruction,
                statut=StatutExecution.ERREUR,
                erreur=str(e),
                duree_totale_ms=int((asyncio.get_event_loop().time() - debut) * 1000),
            )

    async def stream_executer(
        self,
        instruction: str,
        user_id: int,
        agent_type: TypeAgent = TypeAgent.AUTO,
        contexte: dict = None,
    ) -> AsyncGenerator[EtapeAgent, None]:
        """
        Exécute une instruction en streamant les étapes en temps réel.
        Utilisé pour l'interface SSE du frontend.
        """
        self._charger_agents()

        if agent_type == TypeAgent.AUTO:
            agent_type = detecter_agent(instruction)

        # Étape initiale
        yield EtapeAgent(
            type="action",
            libelle=f"Agent {agent_type.value} activé",
            detail=f"Analyse de l'instruction : {instruction[:80]}...",
            statut="en_cours",
        )

        agent = self._agents.get(agent_type)
        if not agent:
            yield EtapeAgent(
                type="action",
                libelle="Erreur",
                detail=f"Agent {agent_type} non disponible",
                statut="erreur",
            )
            return

        # Stream depuis l'agent spécialisé
        if hasattr(agent, "stream_executer"):
            async for etape in agent.stream_executer(
                instruction=instruction,
                user_id=user_id,
                contexte=contexte or {},
            ):
                yield etape
        else:
            # Fallback : exécution synchrone puis résultat
            exec_id = str(uuid.uuid4())
            resultat = await agent.executer(
                instruction=instruction,
                user_id=user_id,
                contexte=contexte or {},
                execution_id=exec_id,
            )
            for etape in resultat.etapes:
                yield etape
            # Toujours émettre une étape "resultat" finale pour que le frontend
            # appelle setExecutionCourante et sache que le processus est terminé
            validation_en_cours = len(resultat.actions_requises) > 0
            yield EtapeAgent(
                type="resultat",
                libelle=(
                    "En attente de votre réponse" if validation_en_cours
                    else "Processus terminé" if resultat.statut == StatutExecution.TERMINE
                    else f"Erreur agent"
                ),
                detail=resultat.resume or resultat.erreur or "",
                statut=(
                    "en_cours" if validation_en_cours
                    else "ok" if resultat.statut == StatutExecution.TERMINE
                    else "erreur"
                ),
                donnees={
                    "execution_id":      resultat.execution_id,
                    "validation_en_cours": validation_en_cours,
                    "statut":            resultat.statut.value,
                    "duree_ms":          resultat.duree_totale_ms,
                    "ia_appelee":        resultat.ia_appelee,
                },
            )

    def agents_disponibles(self) -> list[dict]:
        """Retourne l'état de tous les agents."""
        self._charger_agents()
        etats = []
        for type_agent, agent in self._agents.items():
            nb_actifs = getattr(agent, "executions_actives", 0)
            etats.append({
                "type":       type_agent.value,
                "nom":        _NOM_AGENT[type_agent],
                "description":_DESC_AGENT[type_agent],
                "nb_actifs":  nb_actifs,
                "disponible": True,
            })
        return etats


_NOM_AGENT = {
    TypeAgent.SINISTRES:    "Agent Sinistres & Fraude",
    TypeAgent.SOUSCRIPTION: "Agent Souscription & Tarification",
    TypeAgent.CONFORMITE:   "Agent Conformité CIMA",
    TypeAgent.COMMERCIAL:   "Agent Commercial & Apporteurs",
    TypeAgent.RH:           "Agent RH & Organisation",
    TypeAgent.JURIDIQUE:    "Agent Juridique & Contentieux",
    TypeAgent.COMPTABILITE: "Agent Comptabilité & Finance",
    TypeAgent.INTELLIGENCE: "Agent Intelligence & Veille",
    TypeAgent.VIE:          "Agent Assurance Vie & Prévoyance",
    TypeAgent.REASSURANCE:  "Agent Réassurance & Cessions",
    TypeAgent.PLACEMENT:    "Agent Placement & Actuariat",
    TypeAgent.PROVISIONS:   "Agent Provisions Techniques CIMA",
    TypeAgent.ETATS_CIMA:   "Agent États Réglementés CIMA",
    TypeAgent.SCHEMA_SI:       "Agent Schéma & Connaissance SI",
    TypeAgent.META_FACTORY:    "Agent MetaFactory — Création autonome d'agents",
    TypeAgent.DEPLOIEMENT_SI:  "Agent Déploiement SI — Intégration compagnies",
    TypeAgent.MALADIE:         "Agent Sinistres Maladie & Santé",
    TypeAgent.SINISTRES_AUTO:  "Agent Sinistres RC Auto — Barème CIMA Art. 200-264",
    TypeAgent.RISQUES_DIVERS:  "Agent Risques Divers — RC Pro, DO, ACI, Agriculture, Crédit, Protection Juridique, MRH",
}

_DESC_AGENT = {
    TypeAgent.SINISTRES:    "Instruction, règlement et détection fraude sinistres",
    TypeAgent.SOUSCRIPTION: "Souscription, tarification CIMA et émission de polices non-vie",
    TypeAgent.CONFORMITE:   "Ratios CIMA, états réglementaires, audit conformité",
    TypeAgent.COMMERCIAL:   "Prospection, relances, commissions apporteurs",
    TypeAgent.RH:           "Congés, recrutement, paie, formations, réunions",
    TypeAgent.JURIDIQUE:    "Recours, contentieux, rédaction actes, veille réglementaire",
    TypeAgent.COMPTABILITE: "OCR pièces, rapprochement bancaire, clôtures PCSA",
    TypeAgent.INTELLIGENCE: "Rapports direction, veille marché, détection risques",
    TypeAgent.VIE:          "Contrats vie, prévoyance, épargne-retraite, rachat, sinistres vie",
    TypeAgent.REASSURANCE:  "Traités proportionnels/XS, bordereaux, récupération sinistres",
    TypeAgent.PLACEMENT:    "Portefeuille actifs, ALM, projections actuarielles, stress tests",
    TypeAgent.PROVISIONS:   "PPNA, PSAP, IBNR, PM, PPB, PTS, PREC — calcul et dotation provisions CIMA",
    TypeAgent.ETATS_CIMA:   "Génération C1-C12, contrôle cohérence inter-états, soumission CRCA",
    TypeAgent.SCHEMA_SI:      "Introspection ORASS/Mercure, cartographie schéma, correction accès données agents",
    TypeAgent.META_FACTORY:   "Détecte les workflows SI non couverts, génère de nouveaux agents, met à jour frontend/mobile",
    TypeAgent.DEPLOIEMENT_SI: "Déploie YukpoAssurance dans le SI d'une compagnie : connexion BD, intégration ORASS/Mercure/Sage, migration données, webhooks",
    TypeAgent.MALADIE:        "BPC, remboursements médicaux, hospitalisation, maternité, invalidité longue maladie — assurance santé collective et individuelle",
    TypeAgent.SINISTRES_AUTO: "RC Auto : dommages matériels (VRADE Art.242), corporels (DFP/ITT/pretium doloris Art.231-241), décès, subrogation Art.250 — barème CIMA complet",
    TypeAgent.RISQUES_DIVERS: "RC Générale, RC Pro, Dommages Ouvrage, ACI, Agriculture, Crédit/Caution, Protection Juridique, Assistance, MRH — note technique NTIS obligatoire",
}


# ─── Singleton ────────────────────────────────────────────────────────────────
agent_orchestrateur = AgentOrchestrateur()
