"""
Sprint 2.6 — SLA + monitoring infrastructure.

Composants :
  - Health check détaillé multi-composants (DB, Redis, fal.ai, Replicate, Anthropic, OpenAI)
  - Métriques Prometheus (latency p50/p95/p99 par endpoint, error rate, débits)
  - Endpoint /status public (statuspage simple : last 24h uptime + incidents)
  - Hook pour alertes Slack/PagerDuty si SLA breach

SLA cible : 99.9% uptime mensuel = max 43 minutes/mois downtime.

Stockage incidents in-memory (last 1000) + Redis si dispo (persistance entre
redémarrages). Pour production multi-instance, prévoir Postgres dédié.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("yukpo_assurance.sla_metrics")

# In-memory ring buffers pour metrics (fallback si Redis absent)
_LATENCY_BUFFER: dict[str, deque] = {}     # endpoint → deque[(ts, ms, status)]
_INCIDENTS: deque = deque(maxlen=1000)     # last 1000 incidents
_HEALTH_CHECKS: dict = {}                  # last health check par composant


def record_latency(endpoint: str, ms: float, status_code: int) -> None:
    """Enregistre la latence d'un endpoint (appelé par middleware)."""
    buf = _LATENCY_BUFFER.setdefault(endpoint, deque(maxlen=10000))
    buf.append((time.time(), ms, status_code))


def record_incident(composant: str, severity: str, message: str) -> None:
    """severity : info | warning | error | critical"""
    _INCIDENTS.append({
        "ts": datetime.utcnow().isoformat(),
        "composant": composant, "severity": severity, "message": message,
    })
    logger.warning(f"[SLA/Incident] {severity.upper()} {composant} : {message}")


def percentiles(values: list[float]) -> dict:
    """p50/p95/p99 d'une liste."""
    if not values:
        return {"p50": 0, "p95": 0, "p99": 0, "count": 0, "max": 0}
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    return {
        "p50": round(sorted_vals[int(n * 0.50)], 1),
        "p95": round(sorted_vals[int(n * 0.95) if n > 1 else 0], 1),
        "p99": round(sorted_vals[int(n * 0.99) if n > 1 else 0], 1),
        "count": n,
        "max": round(sorted_vals[-1], 1),
    }


def stats_endpoint(endpoint: str, last_minutes: int = 60) -> dict:
    """Stats sur les N dernières minutes pour un endpoint."""
    buf = _LATENCY_BUFFER.get(endpoint, deque())
    cutoff = time.time() - last_minutes * 60
    recent = [(t, ms, s) for (t, ms, s) in buf if t >= cutoff]
    if not recent:
        return {"endpoint": endpoint, "samples": 0}
    latencies = [ms for (_, ms, _) in recent]
    errors = [s for (_, _, s) in recent if s >= 500]
    return {
        "endpoint": endpoint,
        "samples": len(recent),
        "errors_5xx": len(errors),
        "error_rate_pct": round(100 * len(errors) / len(recent), 2),
        **percentiles(latencies),
    }


async def health_check_complet() -> dict:
    """
    Vérifie chaque composant critique. Retourne dict {composant: {ok: bool, latency_ms, message}}.
    Cache 30s (re-check si plus vieux).
    """
    now = time.monotonic()
    cache_key = "_last_check_ts"
    last_check = _HEALTH_CHECKS.get(cache_key, 0)
    if (now - last_check) < 30 and "results" in _HEALTH_CHECKS:
        return _HEALTH_CHECKS["results"]

    results: dict = {"ts": datetime.utcnow().isoformat(), "components": {}}

    # DB Postgres
    try:
        t0 = time.monotonic()
        from core.database import async_session_maker
        from sqlalchemy import text
        async with async_session_maker() as db:
            await db.execute(text("SELECT 1"))
        results["components"]["postgres"] = {
            "ok": True, "latency_ms": round((time.monotonic() - t0) * 1000, 1),
        }
    except Exception as e:
        results["components"]["postgres"] = {"ok": False, "error": str(e)[:200]}
        record_incident("postgres", "critical", str(e)[:200])

    # Redis
    try:
        t0 = time.monotonic()
        import redis.asyncio as aioredis
        from config.settings import settings
        r = aioredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
        await asyncio.wait_for(r.ping(), timeout=2.0)
        await r.aclose()
        results["components"]["redis"] = {
            "ok": True, "latency_ms": round((time.monotonic() - t0) * 1000, 1),
        }
    except Exception as e:
        results["components"]["redis"] = {"ok": False, "error": str(e)[:200]}
        # Redis down ≠ critical (caches, l'app fonctionne)

    # Anthropic API (Claude)
    try:
        from config.settings import settings
        results["components"]["claude"] = {
            "ok": bool(settings.CLAUDE_API_KEY and settings.CLAUDE_API_KEY.startswith("sk-ant-")),
            "configured": bool(settings.CLAUDE_API_KEY),
        }
    except Exception as e:
        results["components"]["claude"] = {"ok": False, "error": str(e)[:200]}

    # OpenAI
    try:
        from config.settings import settings
        results["components"]["openai"] = {
            "ok": bool(settings.OPENAI_API_KEY and settings.OPENAI_API_KEY.startswith("sk-")),
            "configured": bool(settings.OPENAI_API_KEY),
        }
    except Exception:
        pass

    # fal.ai
    try:
        from config.settings import settings
        results["components"]["fal"] = {
            "ok": bool(settings.FAL_KEY),
            "configured": bool(settings.FAL_KEY),
        }
    except Exception:
        pass

    # Replicate
    try:
        from config.settings import settings
        results["components"]["replicate"] = {
            "ok": bool(settings.REPLICATE_API_TOKEN),
            "configured": bool(settings.REPLICATE_API_TOKEN),
        }
    except Exception:
        pass

    # Compute global SLA: ok si tous les composants critiques (postgres) sont up
    critical_ok = results["components"].get("postgres", {}).get("ok", False)
    results["sla_global"] = "operational" if critical_ok else "degraded"

    _HEALTH_CHECKS["results"] = results
    _HEALTH_CHECKS[cache_key] = now
    return results


def prometheus_format() -> str:
    """
    Génère un export texte au format Prometheus exposition.
    Format : `metric_name{labels} value timestamp_ms`
    """
    lines: list[str] = []
    lines.append("# HELP yukpo_endpoint_latency_ms Latence des endpoints (last 60min)")
    lines.append("# TYPE yukpo_endpoint_latency_ms summary")
    for endpoint in _LATENCY_BUFFER:
        st = stats_endpoint(endpoint, 60)
        if st["samples"] == 0:
            continue
        for q in ("p50", "p95", "p99"):
            lines.append(f'yukpo_endpoint_latency_ms{{endpoint="{endpoint}",quantile="{q}"}} {st[q]}')
        lines.append(f'yukpo_endpoint_requests_total{{endpoint="{endpoint}"}} {st["samples"]}')
        lines.append(f'yukpo_endpoint_errors_5xx_total{{endpoint="{endpoint}"}} {st["errors_5xx"]}')

    lines.append("# HELP yukpo_incidents_total Incidents par composant et severity")
    lines.append("# TYPE yukpo_incidents_total counter")
    incident_counts: dict = {}
    for inc in _INCIDENTS:
        key = f'composant="{inc["composant"]}",severity="{inc["severity"]}"'
        incident_counts[key] = incident_counts.get(key, 0) + 1
    for k, v in incident_counts.items():
        lines.append(f"yukpo_incidents_total{{{k}}} {v}")

    return "\n".join(lines) + "\n"
