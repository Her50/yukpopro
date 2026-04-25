"""
Routes RAG — Administration et recherche du corpus réglementaire.

Endpoints :
  GET  /api/v1/rag/status          — État du corpus (docs indexés, chunks)
  GET  /api/v1/rag/sources         — Liste toutes les sources configurées
  POST /api/v1/rag/rechercher      — Recherche dans le corpus
  POST /api/v1/rag/ingestion       — Lance l'ingestion initiale (admin)
  POST /api/v1/rag/forcer/{doc_id} — Force la MAJ d'un document (admin)
  GET  /api/v1/rag/planning        — Prochaines vérifications planifiées
  GET  /api/v1/rag/hashes          — Hashes connus (debug admin)
"""
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel

from core.auth import TokenData, get_current_user, require_permission

logger = logging.getLogger("yukpo_assurance.api.rag")

router = APIRouter()


# ── Modèles Pydantic ──────────────────────────────────────────────────────────

class RechercheRAGRequest(BaseModel):
    question:    str
    pays:        Optional[str] = None    # "CI", "CM", "SN"…
    domaine:     Optional[str] = None    # "fiscal", "travail"…
    metier:      Optional[str] = None    # "comptable", "DRH"…
    doc_ids:     Optional[list[str]] = None
    top_k:       int   = 8
    seuil_score: float = 0.35


# ══════════════════════════════════════════════════════════════════════════════
# Routes publiques (lecture)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/status", summary="État du corpus RAG")
async def statut_corpus():
    """
    Retourne l'état du corpus réglementaire :
    - Nombre de documents indexés
    - Nombre total de chunks
    - Pays et domaines couverts
    """
    from modules.rag.rag_retriever import stats_corpus
    try:
        return stats_corpus()
    except Exception as e:
        logger.error(f"[routes_rag.py] {e}")
        raise HTTPException(status_code=500, detail="Erreur serveur interne")


@router.get("/sources", summary="Liste des sources configurées")
async def lister_sources(
    pays:    Optional[str] = None,
    domaine: Optional[str] = None,
):
    """Liste toutes les sources RAG avec leur état d'indexation."""
    from modules.rag.sources_registry import SOURCES
    from modules.rag.downloader import chemin_json_chunks, _charger_hashes

    hashes = _charger_hashes()

    sources_info = []
    for s in SOURCES:
        if pays    and s.pays    != pays:    continue
        if domaine and s.domaine != domaine: continue

        chunks_path = chemin_json_chunks(s.doc_id)
        hash_info   = hashes.get(s.doc_id, {})

        sources_info.append({
            "doc_id":           s.doc_id,
            "nom":              s.nom,
            "pays":             s.pays,
            "zone":             s.zone,
            "domaine":          s.domaine,
            "metier_tags":      s.metier_tags,
            "fiabilite":        s.fiabilite.value,
            "check_freq_heures": s.check_freq_heures,
            "indexe":           chunks_path.exists(),
            "derniere_maj":     hash_info.get("verifie_le"),
            "url_principale":   s.url_principale,
        })

    return {
        "total":   len(sources_info),
        "sources": sources_info,
    }


@router.post("/rechercher", summary="Recherche dans le corpus réglementaire")
async def rechercher(req: RechercheRAGRequest):
    """
    Recherche sémantique dans le corpus réglementaire africain.
    Supporte les filtres par pays, domaine et profil métier.
    """
    from modules.rag.rag_retriever import (
        rechercher_corpus_reglementaire,
        rechercher_pour_metier,
    )

    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question vide")

    try:
        if req.metier:
            contexte = rechercher_pour_metier(
                question=req.question,
                metier=req.metier,
                pays=req.pays,
                top_k=req.top_k,
            )
        else:
            contexte = rechercher_corpus_reglementaire(
                question=req.question,
                pays=req.pays,
                domaine=req.domaine,
                doc_ids=req.doc_ids,
                top_k=req.top_k,
                seuil_score=req.seuil_score,
            )

        return {
            "question":     req.question,
            "contexte_rag": contexte,
            "nb_passages":  contexte.count("####"),
            "filtres":      {
                "pays":    req.pays,
                "domaine": req.domaine,
                "metier":  req.metier,
            },
        }
    except Exception as e:
        logger.error(f"[routes_rag] Recherche échouée : {e}")
        logger.error(f"[routes_rag.py] {e}")
        raise HTTPException(status_code=500, detail="Erreur serveur interne")


# ══════════════════════════════════════════════════════════════════════════════
# Routes admin (super_admin uniquement)
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/ingestion",
    summary="Lance l'ingestion initiale de toutes les sources",
    dependencies=[Depends(require_permission("super_admin"))],
)
async def lancer_ingestion_initiale(
    background_tasks: BackgroundTasks,
    max_parallele: int = 3,
):
    """
    Ingère toutes les sources non encore indexées.
    Exécuté en arrière-plan pour ne pas bloquer la requête.
    """
    from modules.rag.updater import ingestion_initiale

    background_tasks.add_task(ingestion_initiale, max_parallele)
    return {
        "message": f"Ingestion initiale lancée en arrière-plan ({max_parallele} sources en parallèle)",
        "statut":  "en_cours",
    }


@router.post(
    "/forcer/{doc_id}",
    summary="Force la mise à jour d'un document spécifique",
    dependencies=[Depends(require_permission("super_admin"))],
)
async def forcer_mise_a_jour(doc_id: str, background_tasks: BackgroundTasks):
    """
    Force le re-téléchargement et la ré-indexation d'un document
    (ignore la détection de changement par hash).
    """
    from modules.rag.sources_registry import SOURCES
    from modules.rag.updater import forcer_mise_a_jour as _forcer

    if not any(s.doc_id == doc_id for s in SOURCES):
        raise HTTPException(
            status_code=404,
            detail=f"Source inconnue : {doc_id}. "
                   f"Docs disponibles : {[s.doc_id for s in SOURCES]}",
        )

    background_tasks.add_task(_forcer, doc_id)
    return {
        "message": f"Mise à jour forcée de '{doc_id}' lancée en arrière-plan",
        "statut":  "en_cours",
    }


@router.get(
    "/planning",
    summary="Prochaines vérifications planifiées",
    dependencies=[Depends(require_permission("super_admin"))],
)
async def planning_verifications():
    """Retourne les prochaines vérifications planifiées par le scheduler."""
    from modules.rag.updater import rag_scheduler
    return {
        "planning":    rag_scheduler.prochaines_verifications(),
        "nb_sources":  len(rag_scheduler._prochaine),
        "scheduler_actif": rag_scheduler._actif,
    }


@router.get(
    "/hashes",
    summary="Hashes connus (debug)",
    dependencies=[Depends(require_permission("super_admin"))],
)
async def lister_hashes():
    """Retourne les hashes connus pour chaque document (debug admin)."""
    from modules.rag.downloader import _charger_hashes
    return _charger_hashes()


@router.delete(
    "/invalidate/{doc_id}",
    summary="Invalide le cache embeddings d'un document",
    dependencies=[Depends(require_permission("super_admin"))],
)
async def invalider_cache(doc_id: str):
    """Invalide le cache embeddings en mémoire pour un document."""
    from modules.rag.rag_embedder import rag_embedder_manager
    rag_embedder_manager.invalider_index(doc_id)
    return {"message": f"Cache mémoire de '{doc_id}' invalidé"}


@router.get(
    "/stats/embedder",
    summary="Statistiques du gestionnaire d'embeddings",
    dependencies=[Depends(require_permission("super_admin"))],
)
async def stats_embedder():
    """Statistiques détaillées du gestionnaire d'embeddings."""
    from modules.rag.rag_embedder import rag_embedder_manager
    return rag_embedder_manager.stats()
