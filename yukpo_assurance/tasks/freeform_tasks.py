"""
Tâches Celery — pipeline Freeform Layout (visuels print-ready PDF).

Wrap `_compose_et_render_background()` (async) dans une tâche Celery (sync)
via `asyncio.run()`. La tâche survit au redéploiement (Sol B) :

  • État Redis maintenu par `_job_set()` au fil de l'exécution
  • Si le worker meurt mid-task, Celery (task_reject_on_worker_lost) re-publie
  • Un autre worker reprend depuis le début (idempotent : on régénère le job)

Interface minimale : la tâche reçoit le `job_id` + un `context` dict
sérialisé en JSON dans Redis (clé `freeform:job:{job_id}:context`).
Avantage : le payload Celery reste petit (juste job_id), tout le contexte
volumineux (descripteurs médias, brand_kit) est dans Redis et persiste.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

from core.celery_app import celery_app

logger = logging.getLogger("yukpo_assurance.tasks.freeform")

_CONTEXT_KEY_TPL = "freeform:job:{job_id}:context"
_CONTEXT_TTL_S = 7200  # 2h, doit couvrir TTL job + retries


async def context_set(job_id: str, context: dict) -> None:
    """Stocke le contexte d'un job freeform dans Redis pour que le worker
    Celery puisse le récupérer (le payload Celery ne contient que le job_id).
    """
    try:
        import redis.asyncio as aioredis
        from config.settings import settings
        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=1.0)
        await r.set(
            _CONTEXT_KEY_TPL.format(job_id=job_id),
            json.dumps(context, default=str),
            ex=_CONTEXT_TTL_S,
        )
        await r.aclose()
    except Exception as e:
        logger.error(f"[freeform/context_set] {job_id[:8]} : {e}")
        raise


async def context_get(job_id: str) -> dict | None:
    """Récupère le contexte stocké via context_set."""
    try:
        import redis.asyncio as aioredis
        from config.settings import settings
        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=1.0)
        raw = await r.get(_CONTEXT_KEY_TPL.format(job_id=job_id))
        await r.aclose()
        if raw:
            return json.loads(raw if isinstance(raw, str) else raw.decode())
    except Exception as e:
        logger.error(f"[freeform/context_get] {job_id[:8]} : {e}")
    return None


@celery_app.task(
    name="freeform.compose_render",
    bind=True,
    max_retries=2,
    default_retry_delay=15,
    autoretry_for=(ConnectionError, TimeoutError),
)
def freeform_compose_render(self, job_id: str) -> dict:
    """Tâche Celery — orchestrate composer LLM + render PDF pour un job
    freeform. Idempotente : récupère son contexte depuis Redis via job_id.

    Le retour `{ok, job_id, duree_ms}` est stocké par Celery dans son backend
    (Redis aussi) — mais on s'appuie surtout sur les transitions de statut
    écrites dans `freeform:job:{job_id}` par `_job_set()` à l'intérieur du
    pipeline (composing → running → done / failed).
    """
    from api.routes_bureau_freeform import (
        _compose_et_render_background, DemandeFreeform,
    )
    from modules.bureau import mediatheque_session as _msm

    jid8 = job_id[:8]
    t0 = time.time()
    logger.info(f"[celery/freeform] job {jid8} reçu (retry={self.request.retries})")

    # 1. Charger le contexte depuis Redis
    context = asyncio.run(context_get(job_id))
    if context is None:
        msg = f"context_get({jid8}) → None (TTL expiré ou jamais set)"
        logger.error(f"[celery/freeform] {msg}")
        # Marque le job failed pour le frontend
        from api.routes_bureau_freeform import _job_set as _set
        asyncio.run(_set(job_id, {
            "statut": "failed", "erreur": msg, "user_id": 0,
        }))
        return {"ok": False, "job_id": job_id, "erreur": msg}

    # 2. Reconstruction des objets typés
    try:
        demande = DemandeFreeform(**context["demande"])
    except Exception as e:
        msg = f"reconstruction DemandeFreeform échouée : {e}"
        logger.error(f"[celery/freeform] {jid8} : {msg}")
        from api.routes_bureau_freeform import _job_set as _set
        asyncio.run(_set(job_id, {
            "statut": "failed", "erreur": msg,
            "user_id": context.get("user_id", 0),
        }))
        return {"ok": False, "job_id": job_id, "erreur": msg}

    # 3. Re-résolution médias depuis refs (la session_id est dans le contexte)
    medias = {}
    refs = demande.medias_refs or []
    if refs:
        try:
            medias = _msm.resoudre_refs(
                refs,
                str(context["user_id"]),
                context["session_id"],
            )
        except Exception as e:
            logger.warning(f"[celery/freeform] {jid8} medias resolve KO : {e}")

    # 4. Exécution du pipeline async (composer + render) via asyncio.run
    try:
        asyncio.run(_compose_et_render_background(
            job_id=job_id,
            fichier_id=context["fichier_id"],
            demande=demande,
            medias=medias,
            descripteurs_medias=context.get("descripteurs_medias") or [],
            descripteur_vert=context.get("descripteur_vert"),
            brand_kit=context.get("brand_kit"),
            export_cmyk=bool(context.get("export_cmyk", True)),
            user_id=int(context["user_id"]),
        ))
        duree_ms = int((time.time() - t0) * 1000)
        logger.info(f"[celery/freeform] job {jid8} OK en {duree_ms}ms")
        return {"ok": True, "job_id": job_id, "duree_ms": duree_ms}
    except Exception as exc:
        logger.exception(f"[celery/freeform] job {jid8} échec : {exc}")
        # _compose_et_render_background marque déjà failed en Redis ; mais
        # si l'exception remonte avant que le statut soit écrit, on fallback.
        try:
            from api.routes_bureau_freeform import _job_get as _get, _job_set as _set
            current = asyncio.run(_get(job_id)) or {}
            if current.get("statut") not in ("done", "failed"):
                asyncio.run(_set(job_id, {
                    **current,
                    "statut": "failed",
                    "erreur": f"task_exception: {str(exc)[:300]}",
                }))
        except Exception:
            pass
        # Retry automatique si erreur transitoire (réseau LLM)
        try:
            raise self.retry(exc=exc) from exc
        except self.MaxRetriesExceededError:
            return {"ok": False, "job_id": job_id, "erreur": str(exc)[:300]}
