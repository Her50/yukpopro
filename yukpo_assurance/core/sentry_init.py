"""
Sentry SDK init conditionnel — actif uniquement si SENTRY_DSN env présent.

Sans SENTRY_DSN : import sentry_sdk skip silencieux, zéro overhead. Permet
de garder le code de capture (sentry_sdk.capture_message) partout dans le
code sans avoir à protéger chaque appel.

Activation prod (quand prêt) :
  1. Créer projet Python sur https://sentry.io (gratuit jusqu'à 5k events/mois)
  2. fly secrets set SENTRY_DSN="https://abc@o123.ingest.sentry.io/456"
  3. Redéploiement automatique → exceptions backend remontent dans Sentry

Cas d'usage clés Yukpo :
  • Lease orphelin Fly : capture_message("lease_orphelin", level="error",
    extras={"machine_id": ..., "duree_lease_s": ...})
  • LLM provider down : capture_message("llm_provider_failed", ...)
  • Pipeline KO : capture_exception automatique sur les routes FastAPI
  • Performance trace : transaction sur les endpoints lents (>5s)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger("yukpo_assurance.sentry")

_initialized: bool = False
_sentry_sdk: Any = None  # type: ignore


def init_sentry_if_configured() -> bool:
    """Initialise Sentry si SENTRY_DSN env présent. Idempotent.

    À appeler une fois au démarrage de l'app (api/main.py startup event).
    Retourne True si Sentry actif, False sinon.
    """
    global _initialized, _sentry_sdk
    if _initialized:
        return _sentry_sdk is not None

    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        logger.info("[Sentry] SENTRY_DSN non configuré — monitoring désactivé")
        _initialized = True
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.redis import RedisIntegration
        from sentry_sdk.integrations.httpx import HttpxIntegration
    except ImportError as e:
        logger.warning(f"[Sentry] sentry-sdk pas installé : {e}")
        _initialized = True
        return False

    environment = os.getenv("FLY_REGION") or os.getenv("ENV") or "prod"
    release = os.getenv("FLY_MACHINE_VERSION") or os.getenv("APP_VERSION") or "unknown"
    sample_rate = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.05"))

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=f"yukpo@{release}",
        # Sample 5% des transactions par défaut — assez pour repérer les
        # patterns de perf sans exploser les events Sentry (cap 5k/mois free).
        traces_sample_rate=sample_rate,
        # Profile auto-sampling identique aux transactions
        profiles_sample_rate=sample_rate,
        # Capture les variables locales dans les stack traces
        send_default_pii=False,    # RGPD : pas d'IP user envoyée
        attach_stacktrace=True,
        max_breadcrumbs=100,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            StarletteIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
            RedisIntegration(),
            HttpxIntegration(),
        ],
        # Tags par défaut visibles sur tous les events
        before_send=_sentry_before_send,
    )
    _sentry_sdk = sentry_sdk
    _initialized = True
    logger.info(
        f"[Sentry] Monitoring actif — env={environment} "
        f"release=yukpo@{release} sample={sample_rate}"
    )
    return True


def _sentry_before_send(event: dict, hint: dict) -> Optional[dict]:
    """Filtre les events Sentry avant envoi (anti-spam + RGPD)."""
    # Ignore les erreurs de health check (bruit)
    request = event.get("request") or {}
    url = (request.get("url") or "").lower()
    if "/health" in url or "/metrics" in url:
        return None

    # Ignore les exceptions attendues (404, 401, 422 = erreurs client normales)
    response = event.get("response") or {}
    status_code = response.get("status_code") or 0
    if isinstance(status_code, int) and status_code in (401, 403, 404, 422):
        return None

    return event


def capture_lease_orphelin(
    machine_id: str,
    duree_lease_s: float,
    nb_requetes_bloquees: int = 0,
    contexte: Optional[dict] = None,
) -> None:
    """Alerte Sentry — lease Fly orphelin détecté.

    Appelé par le middleware proxy-error-detector quand une requête est
    bloquée >60s par un lease (PM01 errors). Niveau "error" pour
    déclencher notification Slack/email équipe.
    """
    if not _initialized:
        init_sentry_if_configured()
    if _sentry_sdk is None:
        logger.warning(
            f"[Lease/Orphan] machine={machine_id} duree={duree_lease_s:.1f}s "
            f"bloquees={nb_requetes_bloquees} (Sentry inactif)"
        )
        return
    try:
        with _sentry_sdk.push_scope() as scope:
            scope.level = "error"
            scope.set_tag("incident_type", "fly_lease_orphelin")
            scope.set_tag("machine_id", machine_id)
            scope.set_extra("duree_lease_s", duree_lease_s)
            scope.set_extra("nb_requetes_bloquees", nb_requetes_bloquees)
            if contexte:
                for k, v in contexte.items():
                    scope.set_extra(k, v)
            _sentry_sdk.capture_message(
                f"Fly lease orphelin détecté : machine {machine_id} bloquée "
                f"depuis {duree_lease_s:.1f}s ({nb_requetes_bloquees} req KO)",
                level="error",
            )
    except Exception as e:
        logger.warning(f"[Sentry/capture_lease] échec : {e}")


def capture_exception(exc: Exception, contexte: Optional[dict] = None) -> None:
    """Wrapper Sentry capture_exception — no-op si Sentry inactif."""
    if not _initialized:
        init_sentry_if_configured()
    if _sentry_sdk is None:
        return
    try:
        if contexte:
            with _sentry_sdk.push_scope() as scope:
                for k, v in contexte.items():
                    scope.set_extra(k, v)
                _sentry_sdk.capture_exception(exc)
        else:
            _sentry_sdk.capture_exception(exc)
    except Exception:
        pass


def capture_message(msg: str, level: str = "info", **extras) -> None:
    """Wrapper Sentry capture_message — no-op si Sentry inactif."""
    if not _initialized:
        init_sentry_if_configured()
    if _sentry_sdk is None:
        return
    try:
        with _sentry_sdk.push_scope() as scope:
            scope.level = level
            for k, v in extras.items():
                scope.set_extra(k, v)
            _sentry_sdk.capture_message(msg, level=level)
    except Exception:
        pass


__all__ = [
    "init_sentry_if_configured",
    "capture_lease_orphelin",
    "capture_exception",
    "capture_message",
]
