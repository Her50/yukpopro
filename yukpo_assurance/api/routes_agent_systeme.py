"""
Routes Agent Système — API réservée aux propriétaires Yukpo.

ACCÈS : super_admin et yukpo_owner UNIQUEMENT.
Les agents schema_si et meta_factory sont des outils de plateforme,
pas des outils compagnie. Ils ne doivent jamais être accessibles
aux utilisateurs normaux d'une compagnie cliente.

Endpoints :
  POST   /agent/systeme/instruire        — Lancer schema_si ou meta_factory manuellement
  GET    /agent/systeme/couverture       — Rapport couverture agents vs SI
  GET    /agent/systeme/scheduler/status — État du scheduler autonome
  POST   /agent/systeme/scheduler/cycle  — Forcer un cycle immédiat
  GET    /agent/systeme/notifications    — Notifications système (super_admin inbox)
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.auth import get_current_user, TokenData

logger = logging.getLogger("yukpo_assurance.api.routes_agent_systeme")

router = APIRouter(prefix="/api/v1/agent/systeme", tags=["Agents Système Yukpo"])

_ROLES_SYSTEME = {"super_admin", "yukpo_owner"}


def _verifier_super_admin(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """Vérifie que l'utilisateur est super_admin ou yukpo_owner."""
    if current_user.role not in _ROLES_SYSTEME:
        raise HTTPException(
            status_code=403,
            detail=(
                "Accès refusé — agents système réservés aux propriétaires Yukpo. "
                f"Votre rôle : {current_user.role}"
            ),
        )
    return current_user


class SystemeInstruireRequest(BaseModel):
    instruction: str
    agent_type:  str = "schema_si"   # schema_si | meta_factory
    si_nom:      Optional[str] = "orass"
    contexte:    Optional[dict] = {}


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/instruire")
async def instruire_agent_systeme(
    body: SystemeInstruireRequest,
    current_user: TokenData = Depends(_verifier_super_admin),
):
    """Lance manuellement un agent système (schema_si ou meta_factory)."""
    from core.agent_orchestrateur import TypeAgent, agent_orchestrateur

    # Seuls ces deux agents sont accessibles via cette route
    agents_autorises = {"schema_si": TypeAgent.SCHEMA_SI, "meta_factory": TypeAgent.META_FACTORY}
    if body.agent_type not in agents_autorises:
        raise HTTPException(
            status_code=400,
            detail=f"Agent système invalide : {body.agent_type}. Valeurs : {list(agents_autorises)}"
        )

    agent_type = agents_autorises[body.agent_type]
    user_id    = int(current_user.user_id)
    exec_id    = str(uuid.uuid4())

    agent_orchestrateur._charger_agents()
    agent = agent_orchestrateur._agents.get(agent_type)
    if not agent:
        raise HTTPException(status_code=503, detail=f"Agent {body.agent_type} non disponible")

    contexte = {**(body.contexte or {}), "si_nom": body.si_nom, "declencheur": current_user.user_nom}
    resultat = await agent.executer(
        instruction=body.instruction,
        user_id=user_id,
        contexte=contexte,
        execution_id=exec_id,
    )

    return {
        "execution_id":  resultat.execution_id,
        "agent":         resultat.agent.value,
        "statut":        resultat.statut.value,
        "resume":        resultat.resume,
        "etapes":        [_e(e) for e in resultat.etapes],
        "actions_requises": len(resultat.actions_requises),
        "duree_ms":      resultat.duree_totale_ms,
        "ia_appelee":    resultat.ia_appelee,
    }


@router.get("/couverture")
async def rapport_couverture(
    si_nom: str = Query("orass"),
    avec_ia: bool = Query(True),
    current_user: TokenData = Depends(_verifier_super_admin),
):
    """Rapport complet : couverture agents vs schéma SI + recommandations."""
    from core.agent_orchestrateur import TypeAgent, agent_orchestrateur

    agent_orchestrateur._charger_agents()
    agent = agent_orchestrateur._agents.get(TypeAgent.META_FACTORY)
    if not agent:
        raise HTTPException(status_code=503, detail="AgentMetaFactory non disponible")

    resultat = await agent.executer(
        instruction=f"Génère le rapport complet de couverture agents pour {si_nom}",
        user_id=int(current_user.user_id),
        contexte={"si_nom": si_nom, "avec_recommandations_ia": avec_ia},
        execution_id=str(uuid.uuid4()),
    )
    return {"rapport": resultat.resume, "etapes": [_e(e) for e in resultat.etapes]}


@router.get("/scheduler/status")
async def statut_scheduler(
    current_user: TokenData = Depends(_verifier_super_admin),
):
    """État du scheduler autonome."""
    from core.agents_scheduler import _running, _CYCLE_SCHEMA_SI, _CYCLE_META_FACTORY
    return {
        "scheduler_actif": _running,
        "cycles": {
            "schema_si": {
                "intervalle_h": _CYCLE_SCHEMA_SI // 3600,
                "description":  "Introspection SI, détection dérives, correction agents",
            },
            "meta_factory": {
                "intervalle_h": _CYCLE_META_FACTORY // 3600,
                "description":  "Analyse couverture, détection workflows manquants",
            },
        },
        "nota": "Tous les résultats sont envoyés uniquement aux super_admin et yukpo_owner",
    }


@router.post("/scheduler/cycle")
async def forcer_cycle(
    agent_type: str = Query("schema_si", description="schema_si | meta_factory"),
    si_nom:     str = Query("orass"),
    current_user: TokenData = Depends(_verifier_super_admin),
):
    """Force l'exécution immédiate d'un cycle unique (hors planification)."""
    from core.agent_orchestrateur import TypeAgent, agent_orchestrateur
    import asyncio

    mapping = {"schema_si": TypeAgent.SCHEMA_SI, "meta_factory": TypeAgent.META_FACTORY}
    if agent_type not in mapping:
        raise HTTPException(status_code=400, detail=f"Agent inconnu : {agent_type}")

    agent_orchestrateur._charger_agents()
    agent = agent_orchestrateur._agents.get(mapping[agent_type])
    if not agent:
        raise HTTPException(status_code=503, detail=f"Agent {agent_type} non disponible")

    instr_map = {
        "schema_si":     f"Détecte les dérives de schéma sur {si_nom} et corrige les agents si nécessaire",
        "meta_factory":  f"Analyse la couverture agents sur {si_nom} et génère les agents manquants à haute priorité",
    }

    # Exécution en arrière-plan (non bloquante)
    exec_id = str(uuid.uuid4())
    asyncio.create_task(agent.executer(
        instruction=instr_map[agent_type],
        user_id=int(current_user.user_id),
        contexte={"si_nom": si_nom, "origine_forcee": True, "declencheur": current_user.user_nom},
        execution_id=exec_id,
    ))

    return {
        "message": f"Cycle {agent_type} lancé en arrière-plan",
        "execution_id": exec_id,
        "si_nom": si_nom,
        "nota": "Résultats disponibles dans la file de validation et notifications système",
    }


@router.get("/notifications")
async def notifications_systeme(
    limit: int = Query(50),
    current_user: TokenData = Depends(_verifier_super_admin),
):
    """
    Notifications système réservées aux super_admin.
    Retourne les rapports automatiques des agents schema_si et meta_factory.
    """
    from core.approval_queue import approval_queue
    items = approval_queue.lister(
        statut="tous",
        type_item="notification_systeme_yukpo",
        limit=limit,
    )
    return {
        "notifications": items,
        "total": len(items),
        "nota": f"Visible uniquement pour : {', '.join(_ROLES_SYSTEME)}",
    }


def _e(etape) -> dict:
    return {
        "libelle": etape.libelle,
        "detail":  etape.detail[:200],
        "statut":  etape.statut,
        "duree_ms": etape.duree_ms,
    }
