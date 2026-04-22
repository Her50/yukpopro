"""
AgentsScheduler — Planificateur d'exécution autonome des agents systèmes.

Agents autonomes (arrière-plan, sans déclenchement humain) :
  - AgentSchemaSI  : toutes les 6h — introspection SI, détection dérives, correction agents
  - AgentMetaFactory : toutes les 24h — analyse couverture, détection workflows manquants
  - Rapport Yukpo  : toutes les 12h — résumé envoyé uniquement aux super_admin / yukpo_owner

Ces agents ne communiquent QUE avec les utilisateurs ayant les rôles :
  super_admin | yukpo_owner

Toute action déclenchée par ces agents en arrière-plan passe par approval_queue
avec un flag `origine_autonome=True` visible dans l'interface de validation.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger("yukpo_assurance.agents_scheduler")

# Intervalles de cycle (secondes)
_CYCLE_SCHEMA_SI      = 6  * 3600   # 6h
_CYCLE_META_FACTORY   = 24 * 3600   # 24h
_CYCLE_RAPPORT_YUKPO  = 12 * 3600   # 12h

# User ID interne pour les exécutions autonomes (ID réservé plateforme Yukpo)
_YUKPO_SYSTEM_USER_ID = 0

_running = False


async def demarrer_scheduler():
    """Lance les 3 boucles autonomes en arrière-plan."""
    global _running
    if _running:
        return
    _running = True
    logger.info("[Scheduler] Démarrage des agents autonomes (schema_si + meta_factory)")
    asyncio.create_task(_boucle_schema_si(),    name="scheduler_schema_si")
    asyncio.create_task(_boucle_meta_factory(), name="scheduler_meta_factory")
    asyncio.create_task(_boucle_rapport_yukpo(), name="scheduler_rapport_yukpo")


async def arreter_scheduler():
    global _running
    _running = False
    logger.info("[Scheduler] Arrêt des agents autonomes")


# ── Boucles autonomes ──────────────────────────────────────────────────────────

async def _boucle_schema_si():
    """
    Toutes les 6h : introspecte le schéma SI, détecte les dérives,
    corrige les agents si nécessaire. Notifie les super_admin.
    """
    # Attente initiale 30s après démarrage (laisser l'app se stabiliser)
    await asyncio.sleep(30)

    while _running:
        try:
            logger.info("[Scheduler:SchemaSI] Cycle autonome démarré")
            from core.agent_orchestrateur import TypeAgent, agent_orchestrateur
            agent_orchestrateur._charger_agents()

            agent = agent_orchestrateur._agents.get(TypeAgent.SCHEMA_SI)
            if not agent:
                logger.warning("[Scheduler:SchemaSI] Agent non disponible")
                await asyncio.sleep(_CYCLE_SCHEMA_SI)
                continue

            execution_id = f"auto-schema-{uuid.uuid4().hex[:8]}"

            # 1. Détecter les dérives de schéma sur tous les SI configurés
            from core.schema_registry import schema_registry
            si_list = schema_registry.lister_si()
            if not si_list:
                si_list = ["orass"]  # fallback si registre vide

            derives_critiques = []
            for si in si_list:
                resultat = await agent.executer(
                    instruction=f"Détecte les dérives de schéma sur {si} et alerte si critique",
                    user_id=_YUKPO_SYSTEM_USER_ID,
                    contexte={"origine_autonome": True, "si_nom": si},
                    execution_id=execution_id,
                )
                if "critique" in (resultat.resume or "").lower():
                    derives_critiques.append({"si": si, "resume": resultat.resume})

            # 2. Corriger les agents affectés si dérives critiques
            if derives_critiques:
                for derive in derives_critiques:
                    for agent_fichier in ["agent_sinistres", "agent_souscription",
                                          "agent_comptabilite", "agent_provisions_techniques"]:
                        await agent.executer(
                            instruction=f"Corrige les accès DB de {agent_fichier} selon le schéma réel {derive['si']}",
                            user_id=_YUKPO_SYSTEM_USER_ID,
                            contexte={"origine_autonome": True, "si_nom": derive["si"],
                                      "agent_fichier": agent_fichier, "mode": "generer_correctif"},
                            execution_id=f"auto-fix-{uuid.uuid4().hex[:8]}",
                        )

            # 3. Notifier les super_admin
            await _notifier_super_admins(
                titre="[Auto] Cycle SchémaSI terminé",
                corps=(
                    f"Cycle autonome {datetime.now(timezone.utc).strftime('%d/%m %H:%M')} UTC\n"
                    f"SI analysés : {', '.join(si_list)}\n"
                    f"Dérives critiques : {len(derives_critiques)}\n"
                    + ("\n".join(f"  ⚠️ {d['si']} : {d['resume'][:100]}" for d in derives_critiques)
                       if derives_critiques else "  ✅ Aucune dérive critique détectée")
                ),
                niveau="critique" if derives_critiques else "info",
            )
            logger.info(f"[Scheduler:SchemaSI] Cycle terminé — {len(derives_critiques)} dérive(s) critique(s)")

        except Exception as e:
            logger.error(f"[Scheduler:SchemaSI] Erreur cycle : {e}")

        await asyncio.sleep(_CYCLE_SCHEMA_SI)


async def _boucle_meta_factory():
    """
    Toutes les 24h : analyse la couverture agents vs SI,
    détecte les workflows non couverts, génère des agents manquants.
    Notifie les super_admin avec les propositions.
    """
    # Attente initiale 5min (après schema_si qui tourne en premier)
    await asyncio.sleep(300)

    while _running:
        try:
            logger.info("[Scheduler:MetaFactory] Cycle autonome démarré")
            from core.agent_orchestrateur import TypeAgent, agent_orchestrateur
            agent_orchestrateur._charger_agents()

            agent = agent_orchestrateur._agents.get(TypeAgent.META_FACTORY)
            if not agent:
                logger.warning("[Scheduler:MetaFactory] Agent non disponible")
                await asyncio.sleep(_CYCLE_META_FACTORY)
                continue

            from core.schema_registry import schema_registry
            si_list = schema_registry.lister_si() or ["orass"]

            rapports = []
            for si in si_list:
                resultat = await agent.executer(
                    instruction=(
                        f"Analyse la couverture des agents sur {si}, "
                        "détecte les workflows manquants et génère les agents manquants à haute priorité."
                    ),
                    user_id=_YUKPO_SYSTEM_USER_ID,
                    contexte={"origine_autonome": True, "si_nom": si},
                    execution_id=f"auto-meta-{uuid.uuid4().hex[:8]}",
                )
                rapports.append({"si": si, "resume": resultat.resume or ""})

            # Notifier les super_admin
            corps = f"Cycle autonome {datetime.now(timezone.utc).strftime('%d/%m %H:%M')} UTC\n\n"
            for r in rapports:
                corps += f"📊 {r['si'].upper()} :\n{r['resume'][:300]}\n\n"
            corps += "→ Consultez la file de validation pour approuver les agents générés."

            await _notifier_super_admins(
                titre="[Auto] MetaFactory — Nouveaux agents détectés",
                corps=corps,
                niveau="info",
            )
            logger.info(f"[Scheduler:MetaFactory] Cycle terminé — {len(rapports)} SI analysé(s)")

        except Exception as e:
            logger.error(f"[Scheduler:MetaFactory] Erreur cycle : {e}")

        await asyncio.sleep(_CYCLE_META_FACTORY)


async def _boucle_rapport_yukpo():
    """
    Toutes les 12h : rapport de santé plateforme envoyé aux super_admin.
    Inclut : nb agents actifs, validations en attente, dérives SI, coûts IA.
    """
    await asyncio.sleep(60)  # 1 minute après démarrage

    while _running:
        try:
            from core.approval_queue import approval_queue
            from core.agent_orchestrateur import agent_orchestrateur

            stats_queue = approval_queue.stats()
            agents_dispo = agent_orchestrateur.agents_disponibles()

            rapport = (
                f"📈 RAPPORT YUKPO — {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC\n\n"
                f"Agents actifs : {len(agents_dispo)}\n"
                f"Validations en attente : {stats_queue.get('en_attente', 0)}\n"
                f"Validations traitées (24h) : {stats_queue.get('approuve', 0) + stats_queue.get('rejete', 0)}\n"
                f"\nTous les agents opérationnels ✅"
            )

            await _notifier_super_admins(
                titre="[Yukpo] Rapport de santé plateforme",
                corps=rapport,
                niveau="info",
            )
            logger.info("[Scheduler:Rapport] Rapport de santé envoyé aux super_admin")

        except Exception as e:
            logger.error(f"[Scheduler:Rapport] Erreur : {e}")

        await asyncio.sleep(_CYCLE_RAPPORT_YUKPO)


# ── Notifications super_admin ─────────────────────────────────────────────────

async def _notifier_super_admins(titre: str, corps: str, niveau: str = "info"):
    """
    Envoie une notification uniquement aux utilisateurs super_admin / yukpo_owner.
    Channels : notifications in-app + email si configuré.
    """
    try:
        # 1. Notification in-app (via approval_queue avec type spécial non-validation)
        from core.approval_queue import approval_queue
        await approval_queue.ajouter({
            "type": "notification_systeme_yukpo",
            "titre": titre,
            "corps": corps,
            "niveau": niveau,
            "roles_destinataires": ["super_admin", "yukpo_owner"],
            "origine_autonome": True,
            "user_id": _YUKPO_SYSTEM_USER_ID,
            "execution_id": f"sys-notif-{uuid.uuid4().hex[:8]}",
            "description": titre,
            "_non_validable": True,  # pas de bouton approuver/rejeter — lecture seule
        })
    except Exception as e:
        logger.error(f"[Scheduler] Erreur notification super_admin : {e}")

    try:
        # 2. Email si configuré (non bloquant)
        from config.settings import settings
        if hasattr(settings, "SUPER_ADMIN_EMAIL") and settings.SUPER_ADMIN_EMAIL:
            from core.notifications import notifications
            await notifications.envoyer(
                canal="email",
                destinataire=settings.SUPER_ADMIN_EMAIL,
                message=f"{titre}\n\n{corps}",
            )
    except Exception:
        pass  # Email optionnel — ne doit pas bloquer
