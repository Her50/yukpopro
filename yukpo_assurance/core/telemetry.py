"""
YukpoAssurance — Observabilité : OpenTelemetry + Prometheus

Implémente :
1. Traces distribuées OpenTelemetry (OTLP → Jaeger / Grafana Tempo)
2. Spans automatiques sur les appels IA, CIMA, sinistres, souscription
3. Propagation du contexte de trace (W3C TraceContext)
4. Métriques business Prometheus (primes calculées, sinistres créés, OCR latence...)
5. Decorator @trace_span pour instrumenter facilement n'importe quelle fonction

Démarrage sans dépendances : si opentelemetry n'est pas installé,
les décorateurs et fonctions deviennent des no-ops transparents.
"""
from __future__ import annotations

import functools
import logging
import time
from contextlib import contextmanager
from typing import Any, Callable, Optional

logger = logging.getLogger("yukpo_assurance.telemetry")

# ── Tentative d'import OpenTelemetry ─────────────────────────────────────────
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.propagate import set_global_textmap
    from opentelemetry.propagators.b3 import B3MultiFormat
    _OTEL_OK = True
except ImportError:
    _OTEL_OK = False
    logger.info("[Telemetry] opentelemetry non installé — tracing désactivé (no-op)")

# ── Tentative d'import Prometheus ─────────────────────────────────────────────
try:
    from prometheus_client import Counter, Histogram, Gauge, Summary
    _PROM_OK = True
except ImportError:
    _PROM_OK = False

    class _NoOp:
        def labels(self, **kw): return self
        def inc(self, v=1): pass
        def observe(self, v): pass
        def set(self, v): pass

    Counter = Histogram = Gauge = Summary = lambda *a, **kw: _NoOp()


# ── Métriques Prometheus MÉTIER ───────────────────────────────────────────────

# IA
ia_appels_total = Counter(
    "yukpo_ia_appels_total",
    "Nombre total d'appels aux modèles IA",
    ["modele", "mode", "statut"],
)
ia_duree_secondes = Histogram(
    "yukpo_ia_duree_secondes",
    "Durée des appels IA (secondes)",
    ["modele", "mode"],
    buckets=[0.5, 1, 2, 5, 10, 20, 30, 60],
)
ia_cout_usd_total = Counter(
    "yukpo_ia_cout_usd_total",
    "Coût total des appels IA en USD",
    ["modele"],
)
ia_tokens_total = Counter(
    "yukpo_ia_tokens_total",
    "Nombre total de tokens consommés",
    ["modele", "type"],
)

# Sinistres
sinistres_crees = Counter(
    "yukpo_sinistres_crees_total",
    "Nombre de sinistres créés",
    ["branche", "compagnie_id"],
)
sinistres_fraude_detectee = Counter(
    "yukpo_sinistres_fraude_detectee_total",
    "Nombre de sinistres avec alerte fraude",
    ["score_tranche"],  # 0-50|50-75|75-100
)

# Tarification
primes_calculees = Counter(
    "yukpo_primes_calculees_total",
    "Nombre de primes calculées",
    ["branche"],
)
prime_montant_fcfa = Histogram(
    "yukpo_prime_montant_fcfa",
    "Montant des primes calculées (FCFA)",
    ["branche"],
    buckets=[50_000, 100_000, 250_000, 500_000, 1_000_000, 5_000_000],
)

# OCR / KYC
ocr_duree_secondes = Histogram(
    "yukpo_ocr_duree_secondes",
    "Durée des analyses OCR Vision IA (secondes)",
    ["type_doc", "double_check"],
    buckets=[1, 2, 5, 10, 20, 30],
)
ocr_double_check = Counter(
    "yukpo_ocr_double_check_total",
    "Nombre d'OCR avec double-check Claude+GPT-4o",
    ["type_doc", "confiance"],
)

# CIMA
cima_questions = Counter(
    "yukpo_cima_questions_total",
    "Questions posées au moteur CIMA",
    ["role_utilisateur"],
)
conformite_alertes = Counter(
    "yukpo_conformite_alertes_total",
    "Alertes de conformité CIMA générées",
    ["niveau", "type"],  # niveau: CRITIQUE|ATTENTION, type: solvabilite|provisions|reassurance
)

# Paiements
paiements_total = Counter(
    "yukpo_paiements_total",
    "Transactions de paiement Mobile Money",
    ["operateur", "statut"],
)
paiements_montant_fcfa = Histogram(
    "yukpo_paiements_montant_fcfa",
    "Montant des paiements (FCFA)",
    ["operateur"],
    buckets=[1_000, 5_000, 25_000, 100_000, 500_000],
)

# API
sessions_chat_actives = Gauge(
    "yukpo_sessions_chat_actives",
    "Nombre de sessions chat actives en mémoire",
)
cache_hits = Counter(
    "yukpo_cache_hits_total",
    "Nombre de hits sur le cache IA",
    ["type"],  # redis|local
)

# Signatures
signatures_total = Counter(
    "yukpo_signatures_electroniques_total",
    "Documents signés électroniquement",
    ["type_document"],
)


# ── Tracer global ──────────────────────────────────────────────────────────────

_tracer: Optional[Any] = None


def initialiser_telemetry(
    service_name: str = "yukpo-assurance",
    service_version: str = "1.0.0",
    otlp_endpoint: str = "http://localhost:4317",
) -> bool:
    """
    Initialise OpenTelemetry avec exporter OTLP (Jaeger / Grafana Tempo).
    Retourne True si initialisé, False si OTEL non dispo.
    """
    global _tracer
    if not _OTEL_OK:
        logger.info("[Telemetry] OTEL non disponible — tracing désactivé")
        return False

    try:
        resource = Resource.create({
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
        })

        provider = TracerProvider(resource=resource)

        try:
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info(f"[Telemetry] OTLP exporter → {otlp_endpoint}")
        except Exception as e:
            logger.warning(f"[Telemetry] OTLP exporter échoué ({e}) — traces en mémoire seulement")

        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(service_name, service_version)

        # Propagation W3C TraceContext (compatible Jaeger, Zipkin, Grafana Tempo)
        if hasattr(trace, "get_current_span"):
            try:
                from opentelemetry.propagators.composite import CompositePropagator
                from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
                set_global_textmap(CompositePropagator([
                    TraceContextTextMapPropagator(),
                ]))
            except Exception:
                pass

        logger.info(f"[Telemetry] OpenTelemetry initialisé — service={service_name}")
        return True

    except Exception as e:
        logger.warning(f"[Telemetry] Init échouée: {e}")
        return False


def instrumenter_fastapi(app) -> None:
    """Instrumente l'app FastAPI pour le tracing automatique."""
    if not _OTEL_OK:
        return
    try:
        FastAPIInstrumentor.instrument_app(app)
        logger.info("[Telemetry] FastAPI instrumenté")
    except Exception as e:
        logger.warning(f"[Telemetry] FastAPI instrumentation échouée: {e}")


def instrumenter_sqlalchemy(engine) -> None:
    """Instrumente SQLAlchemy pour le tracing des requêtes DB."""
    if not _OTEL_OK:
        return
    try:
        SQLAlchemyInstrumentor().instrument(engine=engine)
        logger.info("[Telemetry] SQLAlchemy instrumenté")
    except Exception as e:
        logger.warning(f"[Telemetry] SQLAlchemy instrumentation échouée: {e}")


# ── Decorator @trace_span ─────────────────────────────────────────────────────

def trace_span(
    span_name: Optional[str] = None,
    attributes: Optional[dict] = None,
):
    """
    Decorator qui enveloppe une fonction async dans un span OpenTelemetry.

    Usage :
        @trace_span("cima.calculer_marge_solvabilite", {"branche": "auto"})
        async def calculer_marge_solvabilite_non_vie(...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        name = span_name or f"{func.__module__}.{func.__qualname__}"

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if _tracer is None:
                return await func(*args, **kwargs)
            with _tracer.start_as_current_span(name) as span:
                if attributes:
                    for k, v in attributes.items():
                        span.set_attribute(k, str(v))
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(trace.StatusCode.OK if _OTEL_OK else None)
                    return result
                except Exception as e:
                    if _OTEL_OK:
                        span.record_exception(e)
                        span.set_status(trace.StatusCode.ERROR, str(e))
                    raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            if _tracer is None:
                return func(*args, **kwargs)
            with _tracer.start_as_current_span(name) as span:
                if attributes:
                    for k, v in attributes.items():
                        span.set_attribute(k, str(v))
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    if _OTEL_OK:
                        span.record_exception(e)
                    raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


@contextmanager
def span(name: str, **attrs):
    """
    Context manager pour créer un span OTEL manuellement.

    Usage :
        with span("ia.call", modele="gpt-4o", mode="precision"):
            response = await ia_client.appeler(...)
    """
    if _tracer is None:
        yield None
        return

    with _tracer.start_as_current_span(name) as s:
        for k, v in attrs.items():
            s.set_attribute(k, str(v))
        yield s


def span_set_attribute(key: str, value: Any) -> None:
    """Ajoute un attribut au span courant (si OTEL actif)."""
    if not _OTEL_OK:
        return
    current = trace.get_current_span()
    if current and current.is_recording():
        current.set_attribute(key, str(value))


def span_record_error(error: Exception) -> None:
    """Enregistre une exception dans le span courant."""
    if not _OTEL_OK:
        return
    current = trace.get_current_span()
    if current and current.is_recording():
        current.record_exception(error)
        current.set_status(trace.StatusCode.ERROR, str(error))


# ── Endpoint /metrics (Prometheus scrape) ─────────────────────────────────────

def creer_endpoint_metrics(app) -> None:
    """
    Ajoute l'endpoint /metrics pour le scraping Prometheus.
    Compatible avec Grafana / alertmanager.
    """
    if not _PROM_OK:
        logger.info("[Telemetry] prometheus_client non installé — /metrics désactivé")
        return

    from fastapi import Response as FastAPIResponse
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

    @app.get("/metrics", include_in_schema=False, tags=["Observabilité"])
    async def metrics_endpoint():
        """Endpoint Prometheus — scraping des métriques métier YukpoAssurance."""
        return FastAPIResponse(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    logger.info("[Telemetry] Endpoint /metrics Prometheus enregistré")
