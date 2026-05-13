#!/bin/sh
# Sol B — Lance web (gunicorn) + worker Celery en parallèle dans le même
# container. Le worker partage le filesystem avec le web → les PDFs écrits
# par le worker dans /app/data/generated/bureau sont servis par le web sans
# transfert ni stockage externe.
#
# Si CELERY_ENABLED != "true", on ne lance QUE le web (legacy asyncio path).
# Permet un rollback rapide sans modifier le Dockerfile.

set -e

# Active le flag worker pour _job_set (Sol A skip worker_id check)
export CELERY_WORKER="${CELERY_WORKER:-false}"

if [ "${CELERY_ENABLED:-false}" = "true" ]; then
    echo "[entrypoint] CELERY_ENABLED=true — démarrage web + worker"

    # Démarre le worker Celery en arrière-plan. CELERY_WORKER=true signale
    # à `_job_set` que les updates viennent du worker (auto-tag via_celery).
    CELERY_WORKER=true celery -A core.celery_app worker \
        --loglevel=info \
        --concurrency=${CELERY_WORKER_CONCURRENCY:-2} \
        --max-tasks-per-child=50 \
        --pool=prefork \
        --without-gossip --without-mingle \
        &
    WORKER_PID=$!
    echo "[entrypoint] Celery worker PID=$WORKER_PID"

    # Trap SIGTERM (Fly graceful shutdown) → propage au worker pour qu'il
    # finisse sa tâche en cours avant exit (acks_late re-publie sinon).
    trap "echo '[entrypoint] SIGTERM reçu, arrêt gracieux du worker'; kill -TERM $WORKER_PID; wait $WORKER_PID" TERM INT
fi

# Démarre le web (gunicorn) en foreground = process principal du container
exec gunicorn api.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers "${WORKERS:-2}" \
    --bind "0.0.0.0:${PORT:-8080}" \
    --timeout 360 \
    --graceful-timeout 60 \
    --worker-tmp-dir /tmp \
    --max-requests 2000 \
    --max-requests-jitter 200 \
    --access-logfile - \
    --error-logfile - \
    --log-level info
