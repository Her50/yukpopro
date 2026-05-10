"""
Sprint 2.6 — SLA + monitoring endpoints.

PUBLICS (no auth) :
  GET /health                  → quick check (déjà existant ailleurs)
  GET /health/detailed         → check chaque composant (cache 30s)
  GET /status                  → statuspage public simple (uptime + SLA global)
  GET /metrics                 → Prometheus exposition format (TEXT)

ADMIN (JWT, role admin/dg) :
  GET /sla/incidents           → liste des derniers incidents
  GET /sla/endpoints           → stats latency par endpoint (p50/p95/p99 + error rate)
  POST /sla/incidents          → record un incident manuel (déclenche alertes)
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from core.auth import TokenData, get_current_user
from core import sla_metrics as sm

logger = logging.getLogger("yukpo_assurance.api.sla")
router = APIRouter()


# ─── PUBLICS ─────────────────────────────────────────────────────────────────


@router.get("/health/detailed", tags=["SLA & Monitoring"])
async def health_detailed():
    """Health check multi-composant. Cache 30s. No auth."""
    return await sm.health_check_complet()


@router.get("/status", tags=["SLA & Monitoring"])
async def public_status():
    """
    Statuspage public simple. Affiche le statut global + statut par composant.
    Format pensé pour iframe / page status.yukpomnang.com.
    """
    health = await sm.health_check_complet()
    components_status = {
        name: "operational" if c.get("ok") else "degraded"
        for name, c in health.get("components", {}).items()
    }
    incidents_24h = [
        i for i in list(sm._INCIDENTS)
        if i.get("severity") in ("error", "critical")
    ][-20:]
    return {
        "service": "Yukpo Designer Pro",
        "sla_engagement": "99.9% uptime mensuel",
        "global_status": health.get("sla_global", "unknown"),
        "components_status": components_status,
        "incidents_recents": incidents_24h,
        "ts": datetime.utcnow().isoformat(),
    }


@router.get("/metrics", response_class=PlainTextResponse, tags=["SLA & Monitoring"])
async def prometheus_metrics():
    """Prometheus exposition format. À scraper par un Prometheus externe."""
    return sm.prometheus_format()


# ─── ADMIN (JWT) ──────────────────────────────────────────────────────────────

_ROLES_ADMIN_SLA = {"admin", "dg", "daf"}


def _check_admin(user: TokenData):
    if (user.role or "").lower() not in _ROLES_ADMIN_SLA:
        raise HTTPException(403, f"Rôle admin/dg/daf requis (actuel: {user.role})")


@router.get("/sla/incidents", tags=["SLA & Monitoring"])
async def lister_incidents(
    severity: Optional[str] = None,
    limit: int = 100,
    current_user: TokenData = Depends(get_current_user),
):
    """Liste les derniers incidents (filtrable par severity)."""
    _check_admin(current_user)
    items = list(sm._INCIDENTS)
    if severity:
        items = [i for i in items if i.get("severity") == severity]
    return {"total": len(items), "incidents": items[-limit:][::-1]}


@router.get("/sla/endpoints", tags=["SLA & Monitoring"])
async def stats_endpoints(
    last_minutes: int = 60,
    current_user: TokenData = Depends(get_current_user),
):
    """Stats latency par endpoint (p50/p95/p99 + error rate)."""
    _check_admin(current_user)
    out = []
    for ep in sm._LATENCY_BUFFER:
        out.append(sm.stats_endpoint(ep, last_minutes))
    out.sort(key=lambda x: x.get("samples", 0), reverse=True)
    return {"window_minutes": last_minutes, "endpoints": out}


class IncidentManuel(BaseModel):
    composant: str = Field(..., max_length=80)
    severity: str = Field(..., pattern="^(info|warning|error|critical)$")
    message: str = Field(..., max_length=1000)


@router.post("/sla/incidents", tags=["SLA & Monitoring"])
async def record_incident_manuel(
    inc: IncidentManuel, current_user: TokenData = Depends(get_current_user),
):
    """Enregistre un incident manuellement (oncall who saw an issue)."""
    _check_admin(current_user)
    sm.record_incident(inc.composant, inc.severity, f"[{current_user.user_nom}] {inc.message}")
    # TODO Sprint 2.6b : webhook Slack/PagerDuty si severity ∈ {error, critical}
    return {"ok": True, "ts": datetime.utcnow().isoformat()}
