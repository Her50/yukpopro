"""Tâches Celery — exécutées par le worker dédié (process group `worker`).

Pour ajouter une nouvelle tâche :
  1. Créer `tasks/mon_pipeline_tasks.py` avec `@celery_app.task` décorateur
  2. Ajouter le module dans `core.celery_app.celery_app.include`
  3. Côté route HTTP : `from tasks.mon_pipeline_tasks import ma_tache`
     puis `ma_tache.delay(job_id, ...)` au lieu de
     `asyncio.create_task(...)`.
"""
