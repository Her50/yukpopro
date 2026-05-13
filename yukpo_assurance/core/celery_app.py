"""
Celery app — file de tâches durables pour les jobs longs.

Solution B : remplace `asyncio.create_task()` (qui meurt avec le process)
par un broker Redis + worker dédié → les tâches survivent aux redéploiements
et redémarrages de machine.

Architecture Fly.io :
  • Process `web` (gunicorn) : reçoit les requêtes HTTP, enqueue les tâches
    lourdes via `task.delay(job_id)`, retourne 202 + URL de polling.
  • Process `worker` (celery) : consomme la queue Redis, exécute les tâches
    (compose LLM, render PDF, image gen IA), met à jour le statut Redis
    via `_job_set()` au fur et à mesure.

Garanties :
  • `task_acks_late=True` : le worker ack la tâche APRÈS exécution complète.
    Si le worker meurt mid-task, Redis re-publie la tâche, un autre worker
    (ou le même après restart) reprend.
  • `task_reject_on_worker_lost=True` : kill -9 / OOM / redeploy → requeue.
  • `task_time_limit=1800` : hard timeout 30 min (gros render livret).
    Au-delà, la tâche est tuée et marquée failed (pas de zombie infini).

Configuration via env :
  • CELERY_BROKER_URL    : défaut = REDIS_URL
  • CELERY_RESULT_BACKEND: défaut = REDIS_URL
  • CELERY_WORKER_CONCURRENCY : nb tâches concurrentes par worker (défaut 2)

Démarrage :
  • web    : gunicorn api.main:app ... (déjà configuré)
  • worker : celery -A core.celery_app worker --loglevel=info --concurrency=2
"""
from __future__ import annotations

import logging
import os

from celery import Celery

logger = logging.getLogger("yukpo_assurance.celery")

# ── Sources URL ───────────────────────────────────────────────────────────────
# REDIS_URL est l'env partagé avec le reste de l'app (settings.REDIS_URL).
# CELERY_BROKER_URL / CELERY_RESULT_BACKEND override si on veut un Redis
# dédié (utile en prod multi-tenant à fort débit).

def _broker_url() -> str:
    return (
        os.getenv("CELERY_BROKER_URL")
        or os.getenv("REDIS_URL")
        or "redis://localhost:6379/0"
    )


def _result_url() -> str:
    return (
        os.getenv("CELERY_RESULT_BACKEND")
        or os.getenv("REDIS_URL")
        or "redis://localhost:6379/0"
    )


celery_app = Celery(
    "yukpo_assurance",
    broker=_broker_url(),
    backend=_result_url(),
    include=[
        # Module(s) exposant les @celery_app.task. Auto-discovery au démarrage
        # du worker.
        "tasks.freeform_tasks",
    ],
)


# ── Configuration ─────────────────────────────────────────────────────────────

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Track les transitions PENDING → STARTED → SUCCESS/FAILURE
    task_track_started=True,
    # Hard timeout 30 min — sécurité contre les LLM hung ou render
    # pathologique. Au-delà, la tâche est tuée (SoftTimeLimitExceeded
    # 60s avant pour permettre un cleanup gracieux).
    task_time_limit=1800,
    task_soft_time_limit=1740,
    # Prefetch=1 : 1 seule tâche en cours par worker à la fois. Évite qu'un
    # worker préempte 10 tâches longues et bloque les autres en file.
    worker_prefetch_multiplier=1,
    # Late ack : le job n'est ack qu'APRÈS exécution complète. Garantit
    # qu'un kill -9 / OOM / redeploy fait re-publier la tâche par Redis.
    task_acks_late=True,
    # Reject si le worker meurt en cours → re-queue (Redis broker)
    task_reject_on_worker_lost=True,
    # Réessais max 3, exponential backoff (Celery 5.2+)
    task_default_retry_delay=10,
    task_max_retries=3,
    # Throttling : empêche un user de saturer la queue
    task_default_rate_limit="60/m",
    # Worker concurrency configurable
    worker_concurrency=int(os.getenv("CELERY_WORKER_CONCURRENCY", "2")),
    # Logging clair
    worker_redirect_stdouts_level="INFO",
    # Heartbeat broker pour détecter workers morts
    broker_heartbeat=10,
    broker_connection_retry_on_startup=True,
    # ── Routing multi-queue : vidéo lourde séparée ────────────────────────
    # Les tâches `bureau.video.*` (Kling stitching 30-60s, FFmpeg concat)
    # consomment beaucoup de CPU/RAM et peuvent durer 5-10 min. Pour ne pas
    # bloquer les tâches courtes (freeform 1-3 min, slides web, landing),
    # on les route vers une queue dédiée `video_heavy`. Un worker dédié
    # (machine perf-8x typiquement) consomme cette queue uniquement.
    # Les autres tâches restent sur la queue `default`.
    task_routes={
        "bureau.video.*":           {"queue": "video_heavy"},
        "freeform.compose_render":  {"queue": "default"},
        # Pattern wildcard sur tasks futures (slides web background, etc.)
        "bureau.heavy.*":           {"queue": "video_heavy"},
    },
    task_default_queue="default",
)


@celery_app.on_after_configure.connect
def _setup_periodic_tasks(sender, **kwargs):
    """Hook pour ajouter des tâches périodiques (heartbeat, cleanup) plus tard."""
    logger.info(
        f"[celery] App configurée — broker={_broker_url().split('@')[-1]}, "
        f"concurrency={celery_app.conf.worker_concurrency}, "
        f"time_limit={celery_app.conf.task_time_limit}s"
    )


__all__ = ["celery_app"]
