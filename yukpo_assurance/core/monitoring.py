"""
YukpoAssurance — Monitoring & Métriques
Prometheus + healthchecks avancés + alertes.
Expose /metrics pour scraping Prometheus et /health/detailed pour supervision.
"""
import time
import logging
from typing import Callable
from fastapi import FastAPI, Request, Response
from fastapi.routing import APIRoute

logger = logging.getLogger("yukpo_assurance.monitoring")

# ─── Métriques Prometheus ──────────────────────────────────────────────────────

try:
    from prometheus_client import (
        Counter, Histogram, Gauge, Summary, Info,
        generate_latest, CONTENT_TYPE_LATEST, CollectorRegistry,
        multiprocess, REGISTRY,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning("[Monitoring] prometheus_client non disponible — /metrics désactivé")


if PROMETHEUS_AVAILABLE:
    # ── Compteurs de requêtes ──────────────────────────────────────────────────
    REQUEST_COUNT = Counter(
        "yukpo_http_requests_total",
        "Nombre total de requêtes HTTP",
        ["method", "endpoint", "status_code"],
    )

    REQUEST_DURATION = Histogram(
        "yukpo_http_request_duration_seconds",
        "Durée des requêtes HTTP en secondes",
        ["method", "endpoint"],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    )

    # ── Métriques IA ──────────────────────────────────────────────────────────
    IA_CALLS = Counter(
        "yukpo_ia_calls_total",
        "Nombre d'appels aux modèles IA",
        ["model", "module", "status"],
    )

    IA_TOKENS = Counter(
        "yukpo_ia_tokens_total",
        "Tokens consommés par les modèles IA",
        ["model", "direction"],  # direction: "input" | "output"
    )

    IA_COST_USD = Counter(
        "yukpo_ia_cost_usd_total",
        "Coût total des appels IA en USD",
        ["model"],
    )

    IA_LATENCY = Histogram(
        "yukpo_ia_latency_seconds",
        "Latence des appels IA en secondes",
        ["model"],
        buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
    )

    # ── Sessions chat ─────────────────────────────────────────────────────────
    ACTIVE_CHAT_SESSIONS = Gauge(
        "yukpo_active_chat_sessions",
        "Nombre de sessions chat actives",
    )

    CHAT_MESSAGES = Counter(
        "yukpo_chat_messages_total",
        "Nombre de messages chat échangés",
        ["direction"],  # "user" | "assistant"
    )

    # ── Sinistres & Fraude ────────────────────────────────────────────────────
    SINISTRES_DECLARES = Counter(
        "yukpo_sinistres_declared_total",
        "Nombre de sinistres déclarés",
        ["branche"],
    )

    FRAUDE_SCORES = Histogram(
        "yukpo_fraude_score",
        "Distribution des scores de fraude (0-100)",
        buckets=[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
    )

    # ── Documents générés ─────────────────────────────────────────────────────
    DOCUMENTS_GENERES = Counter(
        "yukpo_documents_generated_total",
        "Nombre de documents générés",
        ["format"],  # "docx" | "pdf" | "pptx" | "xlsx"
    )

    # ── Authentification ──────────────────────────────────────────────────────
    AUTH_ATTEMPTS = Counter(
        "yukpo_auth_attempts_total",
        "Tentatives d'authentification",
        ["status"],  # "success" | "failure"
    )

    # ── Informations système ──────────────────────────────────────────────────
    APP_INFO = Info(
        "yukpo_app",
        "Informations sur l'application YukpoAssurance",
    )
    APP_INFO.info({
        "version": "1.0.0",
        "environment": "production",
        "orass_mode": "simulation",
    })

    UPTIME = Gauge(
        "yukpo_uptime_seconds",
        "Durée de fonctionnement de l'application en secondes",
    )

    _start_time = time.time()


# ─── Middleware de métriques ───────────────────────────────────────────────────

class MetricsMiddleware:
    """
    Middleware FastAPI qui collecte les métriques pour chaque requête.
    N'affecte pas la performance (overhead < 1ms).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if not PROMETHEUS_AVAILABLE:
            await self.app(scope, receive, send)
            return

        # Normaliser l'endpoint (éviter trop de labels)
        path = scope.get("path", "")
        endpoint = self._normaliser_endpoint(path)
        method = scope.get("method", "")

        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 500)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - start
            # Ne pas tracker /metrics et /health (trop de bruit)
            if path not in ("/metrics", "/health", "/"):
                REQUEST_COUNT.labels(
                    method=method,
                    endpoint=endpoint,
                    status_code=str(status_code),
                ).inc()
                REQUEST_DURATION.labels(
                    method=method,
                    endpoint=endpoint,
                ).observe(duration)
            # Mettre à jour l'uptime
            UPTIME.set(time.time() - _start_time)

    def _normaliser_endpoint(self, path: str) -> str:
        """Remplace les IDs dynamiques par des placeholders"""
        import re
        # UUIDs
        path = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "{id}", path)
        # Nombres
        path = re.sub(r"/\d{4,}/", "/{id}/", path)
        path = re.sub(r"/\d{4,}$", "/{id}", path)
        # Numéros de police/sinistre
        path = re.sub(r"[A-Z]+-\d{4}-\d+", "{ref}", path)
        return path


# ─── Endpoint /metrics ────────────────────────────────────────────────────────

def setup_metrics_endpoint(app: FastAPI):
    """
    Ajoute l'endpoint /metrics pour scraping Prometheus.
    À appeler depuis api/main.py après création de l'app FastAPI.
    """
    if not PROMETHEUS_AVAILABLE:
        @app.get("/metrics", include_in_schema=False)
        async def metrics_unavailable():
            return Response(
                content="# prometheus_client non installé\n# pip install prometheus-client\n",
                media_type="text/plain",
            )
        return

    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        """Endpoint Prometheus — scraped toutes les 15s"""
        return Response(
            content=generate_latest(REGISTRY),
            media_type=CONTENT_TYPE_LATEST,
        )

    # Ajouter le middleware de métriques
    app.middleware("http")(MetricsMiddleware(app).__call__)
    logger.info("[Monitoring] Prometheus activé → /metrics")


# ─── Healthcheck détaillé ──────────────────────────────────────────────────────

async def healthcheck_detaille() -> dict:
    """
    Healthcheck complet avec latences mesurées.
    Utilisé par /health/detailed et les alertes Prometheus.
    """
    checks = {}
    start_total = time.perf_counter()

    # ── Database ────────────────────────────────────────────────────────────
    t = time.perf_counter()
    try:
        from core.database import async_session_maker
        from sqlalchemy import text
        async with async_session_maker() as db:
            await db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok", "latency_ms": round((time.perf_counter() - t) * 1000, 1)}
    except Exception as e:
        checks["database"] = {"status": "error", "error": str(e)[:100]}

    # ── Redis ────────────────────────────────────────────────────────────────
    t = time.perf_counter()
    try:
        import redis.asyncio as aioredis
        from config.settings import settings
        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        await r.ping()
        await r.aclose()
        checks["redis"] = {"status": "ok", "latency_ms": round((time.perf_counter() - t) * 1000, 1)}
    except Exception:
        checks["redis"] = {"status": "unavailable"}

    # ── Clés IA ──────────────────────────────────────────────────────────────
    from config.settings import settings
    checks["claude_api"] = {
        "status": "configured" if settings.CLAUDE_API_KEY and "changez" not in settings.CLAUDE_API_KEY.lower() else "missing",
        "model_primaire": "claude-opus-4-6",
    }
    checks["openai_api"] = {
        "status": "configured" if settings.OPENAI_API_KEY and "votre" not in settings.OPENAI_API_KEY.lower() else "missing",
        "model_primaire": "gpt-4o",
    }

    # ── ORASS ────────────────────────────────────────────────────────────────
    checks["orass"] = {
        "status": "simulation",
        "mode": settings.ORASS_MODE,
        "note": "Mode simulation actif — données fictives réalistes",
    }

    # ── Sessions chat actives ────────────────────────────────────────────────
    try:
        from modules.chat.yukpo_ia_assurance import _sessions
        nb_sessions = len(_sessions)
        checks["chat_sessions"] = {"status": "ok", "active": nb_sessions}
        if PROMETHEUS_AVAILABLE:
            ACTIVE_CHAT_SESSIONS.set(nb_sessions)
    except Exception:
        checks["chat_sessions"] = {"status": "unknown"}

    # ── Orchestrateur ─────────────────────────────────────────────────────────
    try:
        from core.orchestrateur import orchestrateur
        stats = orchestrateur.statistiques()
        checks["orchestrateur"] = {"status": "ok", "stats": stats}
    except Exception as e:
        checks["orchestrateur"] = {"status": "error", "error": str(e)[:100]}

    total_ms = round((time.perf_counter() - start_total) * 1000, 1)

    # Statut global
    statuts = [c.get("status", "unknown") for c in checks.values() if isinstance(c, dict)]
    if any(s == "error" for s in statuts):
        global_status = "degraded"
    elif checks["database"]["status"] == "ok" and (
        checks["claude_api"]["status"] == "configured" or checks["openai_api"]["status"] == "configured"
    ):
        global_status = "healthy"
    else:
        global_status = "degraded"

    return {
        "status": global_status,
        "checks": checks,
        "total_check_ms": total_ms,
        "uptime_seconds": round(time.time() - _start_time) if PROMETHEUS_AVAILABLE else None,
    }


# ─── Helpers pour les autres modules ──────────────────────────────────────────

def record_ia_call(model: str, module: str, status: str, tokens_in: int = 0, tokens_out: int = 0, cost_usd: float = 0, latency_s: float = 0):
    """Enregistre les métriques d'un appel IA. À appeler depuis ia_client.py."""
    if not PROMETHEUS_AVAILABLE:
        return
    IA_CALLS.labels(model=model, module=module, status=status).inc()
    if tokens_in:
        IA_TOKENS.labels(model=model, direction="input").inc(tokens_in)
    if tokens_out:
        IA_TOKENS.labels(model=model, direction="output").inc(tokens_out)
    if cost_usd:
        IA_COST_USD.labels(model=model).inc(cost_usd)
    if latency_s:
        IA_LATENCY.labels(model=model).observe(latency_s)


def record_sinistre(branche: str):
    """Enregistre la déclaration d'un sinistre."""
    if PROMETHEUS_AVAILABLE:
        SINISTRES_DECLARES.labels(branche=branche).inc()


def record_fraude_score(score: int):
    """Enregistre un score de fraude."""
    if PROMETHEUS_AVAILABLE:
        FRAUDE_SCORES.observe(score)


def record_document(format_doc: str):
    """Enregistre la génération d'un document."""
    if PROMETHEUS_AVAILABLE:
        DOCUMENTS_GENERES.labels(format=format_doc).inc()


def record_auth(success: bool):
    """Enregistre une tentative d'authentification."""
    if PROMETHEUS_AVAILABLE:
        AUTH_ATTEMPTS.labels(status="success" if success else "failure").inc()
