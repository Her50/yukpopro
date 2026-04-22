"""
RAG Embedder — Moteur d'embeddings dense multi-documents.

Reprend exactement le même pattern que CIMAEmbedder (sentence-transformers,
paraphrase-multilingual-MiniLM-L12-v2, cache .npz) mais généralisé à tous
les documents du corpus réglementaire.

Un index par document (doc_id) → isolation des mises à jour :
  - Seul le doc modifié est ré-indexé, pas tout le corpus.

Cache : data/rag_knowledge/{doc_id}/embeddings.npz
  - Invalidé automatiquement si chunks.json change (hash MD5)
  - Rechargé en ~200ms depuis le cache, ~20s si recalcul
"""
import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Optional

import numpy as np

from modules.rag.downloader import chemin_json_chunks, chemin_embeddings
from modules.rag.pdf_processor import charger_chunks

logger = logging.getLogger("yukpo_assurance.rag.embedder")

_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"  # 384 dims, multilingue


# ══════════════════════════════════════════════════════════════════════════════
# Index d'un document
# ══════════════════════════════════════════════════════════════════════════════

class IndexDocument:
    """
    Index d'embeddings pour un seul document (doc_id).
    Thread-safe.
    """

    def __init__(self, doc_id: str):
        self.doc_id      = doc_id
        self._chunks: list[dict] = []
        self._embeddings: Optional[np.ndarray] = None   # (N, 384)
        self._pret       = False
        self._lock       = threading.Lock()

    @property
    def pret(self) -> bool:
        return self._pret

    @property
    def nb_chunks(self) -> int:
        return len(self._chunks)

    def construire(self, model) -> bool:
        """
        Construit ou recharge l'index depuis le cache disque.
        model : SentenceTransformer déjà chargé (partagé entre tous les index).
        Retourne True si prêt.
        """
        with self._lock:
            chemin_chunks = chemin_json_chunks(self.doc_id)
            chemin_emb    = chemin_embeddings(self.doc_id)

            # Charger les chunks
            chunks = charger_chunks(chemin_chunks)
            if not chunks:
                logger.warning(f"[Embedder] {self.doc_id} — Aucun chunk disponible")
                return False

            self._chunks = chunks
            json_hash = _hash_fichier(chemin_chunks)

            # Essayer le cache disque
            if self._charger_cache(chemin_emb, json_hash):
                self._pret = True
                logger.info(
                    f"[Embedder] {self.doc_id} — Cache chargé "
                    f"({len(self._chunks)} chunks, dim={self._embeddings.shape[1]})"
                )
                return True

            # Calculer les embeddings
            logger.info(
                f"[Embedder] {self.doc_id} — Calcul embeddings "
                f"({len(self._chunks)} chunks)…"
            )
            corpus = [c["texte_embed"] for c in self._chunks]
            self._embeddings = model.encode(
                corpus,
                batch_size=64,
                show_progress_bar=False,
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
            self._pret = True
            self._sauvegarder_cache(chemin_emb, json_hash)
            return True

    def _charger_cache(self, chemin: Path, json_hash: str) -> bool:
        try:
            if not chemin.exists():
                return False
            loaded = np.load(chemin, allow_pickle=True)
            if str(loaded.get("hash", b"")) != json_hash:
                logger.info(f"[Embedder] {self.doc_id} — Cache invalidé (chunks modifiés)")
                return False
            self._embeddings = loaded["embeddings"]
            return True
        except Exception as e:
            logger.warning(f"[Embedder] {self.doc_id} — Cache illisible : {e}")
            return False

    def _sauvegarder_cache(self, chemin: Path, json_hash: str) -> None:
        try:
            chemin.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(
                chemin,
                embeddings=self._embeddings,
                hash=np.array(json_hash),
            )
            taille_ko = chemin.stat().st_size // 1024
            logger.info(
                f"[Embedder] {self.doc_id} — Cache sauvegardé "
                f"({taille_ko} Ko) : {chemin}"
            )
        except Exception as e:
            logger.warning(f"[Embedder] {self.doc_id} — Sauvegarde cache échouée : {e}")

    def rechercher(
        self,
        vecteur_question: np.ndarray,  # shape (384,) L2-normalisé
        top_k: int = 6,
        seuil_score: float = 0.35,
    ) -> list[dict]:
        """
        Recherche les chunks les plus proches par similarité cosinus.
        Retourne les chunks avec leur score.
        """
        if not self._pret or self._embeddings is None:
            return []

        scores = (self._embeddings @ vecteur_question).flatten()
        top_idx = np.argsort(scores)[::-1][: top_k * 2]

        resultats = []
        for idx in top_idx:
            if len(resultats) >= top_k:
                break
            score = float(scores[idx])
            if score < seuil_score:
                break
            resultats.append({
                **self._chunks[idx],
                "score":  score,
                "doc_id": self.doc_id,
            })
        return resultats

    def invalider(self) -> None:
        """Réinitialise l'index — forcera un recalcul au prochain construire()."""
        with self._lock:
            self._pret       = False
            self._chunks     = []
            self._embeddings = None


# ══════════════════════════════════════════════════════════════════════════════
# Gestionnaire global des index
# ══════════════════════════════════════════════════════════════════════════════

class RAGEmbedderManager:
    """
    Gère tous les index de documents du corpus réglementaire.
    Singleton — utiliser l'instance `rag_embedder_manager`.

    Le modèle sentence-transformers est chargé une seule fois et
    partagé par tous les index (économie mémoire).
    """

    def __init__(self):
        self._index: dict[str, IndexDocument] = {}  # doc_id → IndexDocument
        self._model = None
        self._model_lock = threading.Lock()
        self._global_lock = threading.Lock()

    @property
    def modele_pret(self) -> bool:
        """True si le modèle sentence-transformers est déjà chargé en mémoire."""
        return self._model is not None

    # ── Modèle (lazy, partagé) ─────────────────────────────────────────────

    def _charger_modele(self):
        """Charge le modèle sentence-transformers une seule fois."""
        if self._model is not None:
            return
        with self._model_lock:
            if self._model is not None:
                return
            import os
            os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(_MODEL_NAME)
            logger.info(f"[EmbedderManager] Modèle chargé : {_MODEL_NAME}")

    def encoder_question(self, question: str) -> Optional[np.ndarray]:
        """Encode une question en vecteur L2-normalisé."""
        try:
            self._charger_modele()
            return self._model.encode(
                [question],
                normalize_embeddings=True,
                convert_to_numpy=True,
            )[0]
        except Exception as e:
            logger.warning(f"[EmbedderManager] Encodage question échoué : {e}")
            return None

    # ── Gestion des index ─────────────────────────────────────────────────

    def charger_index(self, doc_id: str) -> bool:
        """Charge (ou recharge) l'index d'un document. Thread-safe."""
        self._charger_modele()
        with self._global_lock:
            if doc_id not in self._index:
                self._index[doc_id] = IndexDocument(doc_id)
            idx = self._index[doc_id]

        return idx.construire(self._model)

    def invalider_index(self, doc_id: str) -> None:
        """Invalide l'index d'un document (sera recalculé au prochain charger_index)."""
        with self._global_lock:
            if doc_id in self._index:
                self._index[doc_id].invalider()
                del self._index[doc_id]
        logger.info(f"[EmbedderManager] Index {doc_id} invalidé")

    def charger_tous_les_index(self) -> dict[str, bool]:
        """
        Charge tous les index disponibles sur disque au démarrage.
        Ne télécharge rien — charge uniquement ce qui existe déjà localement.
        """
        from modules.rag.downloader import _RAG_DATA
        resultats = {}
        if not _RAG_DATA.exists():
            return resultats

        for dossier in sorted(_RAG_DATA.iterdir()):
            if not dossier.is_dir():
                continue
            doc_id = dossier.name
            chunks_path = dossier / "chunks.json"
            if chunks_path.exists():
                ok = self.charger_index(doc_id)
                resultats[doc_id] = ok
                if ok:
                    logger.info(
                        f"[EmbedderManager] ✅ {doc_id} — "
                        f"{self._index[doc_id].nb_chunks} chunks"
                    )
                else:
                    logger.warning(f"[EmbedderManager] ⚠️  {doc_id} — Chargement échoué")

        return resultats

    # ── Recherche multi-documents ─────────────────────────────────────────

    def rechercher(
        self,
        question: str,
        doc_ids: Optional[list[str]] = None,  # None = tous les docs disponibles
        top_k_par_doc: int = 4,
        top_k_global: int = 10,
        seuil_score: float = 0.35,
    ) -> list[dict]:
        """
        Recherche dans un ou plusieurs documents.
        Résultats triés par score décroissant (inter-documents).
        """
        vecteur = self.encoder_question(question)
        if vecteur is None:
            return []

        # Sélectionner les index à interroger
        with self._global_lock:
            if doc_ids:
                index_a_interroger = {
                    did: idx for did, idx in self._index.items()
                    if did in doc_ids and idx.pret
                }
            else:
                index_a_interroger = {
                    did: idx for did, idx in self._index.items()
                    if idx.pret
                }

        if not index_a_interroger:
            return []

        # Recherche dans chaque index
        tous_resultats = []
        for doc_id, idx in index_a_interroger.items():
            resultats = idx.rechercher(vecteur, top_k=top_k_par_doc, seuil_score=seuil_score)
            tous_resultats.extend(resultats)

        # Tri global par score
        tous_resultats.sort(key=lambda x: x["score"], reverse=True)
        return tous_resultats[:top_k_global]

    def rechercher_par_pays_domaine(
        self,
        question: str,
        pays: Optional[str] = None,
        domaine: Optional[str] = None,
        top_k_global: int = 10,
    ) -> list[dict]:
        """
        Recherche filtrée par pays et/ou domaine.
        Utilise les metadata stockées dans les chunks.
        """
        from modules.rag.sources_registry import SOURCES

        # Identifier les doc_ids correspondant aux filtres
        doc_ids_filtres = []
        for source in SOURCES:
            if pays   and source.pays   != pays:   continue
            if domaine and source.domaine != domaine: continue
            doc_ids_filtres.append(source.doc_id)

        if not doc_ids_filtres:
            return self.rechercher(question, top_k_global=top_k_global)

        return self.rechercher(
            question,
            doc_ids=doc_ids_filtres,
            top_k_global=top_k_global,
        )

    # ── Recherche par mot-clé exact (pour numéros d'articles) ────────────

    def rechercher_par_mots_cles(
        self,
        patterns: list[str],
        doc_ids: Optional[list[str]] = None,
        top_k: int = 6,
    ) -> list[dict]:
        """
        Recherche les chunks dont le texte contient au moins un des patterns.
        Utilisé pour le lookup exact de numéros d'articles (ex: "article 13", "art. 1382").
        Retourne les chunks correspondants avec un score artificiel de 0.95
        pour qu'ils soient prioritaires sur les résultats sémantiques.
        """
        import re as _re
        compiled = [_re.compile(_re.escape(p), _re.IGNORECASE) for p in patterns]
        resultats = []

        with self._global_lock:
            index_cibles = {
                did: idx for did, idx in self._index.items()
                if idx.pret and (doc_ids is None or did in doc_ids)
            }

        for doc_id, idx in index_cibles.items():
            for chunk in idx._chunks:
                texte = chunk.get("texte", "") + " " + chunk.get("texte_embed", "")
                if any(pat.search(texte) for pat in compiled):
                    resultats.append({
                        **chunk,
                        "score":  0.95,
                        "doc_id": doc_id,
                    })
                    if len(resultats) >= top_k * 3:
                        break

        return resultats[:top_k]

    # ── Statistiques ─────────────────────────────────────────────────────

    def stats(self) -> dict:
        with self._global_lock:
            return {
                "index_charges": {
                    did: {
                        "pret":      idx.pret,
                        "nb_chunks": idx.nb_chunks,
                    }
                    for did, idx in self._index.items()
                },
                "nb_docs_charges": sum(1 for idx in self._index.values() if idx.pret),
                "nb_chunks_total": sum(idx.nb_chunks for idx in self._index.values() if idx.pret),
                "modele": _MODEL_NAME,
            }


# ─── Singleton ────────────────────────────────────────────────────────────────
rag_embedder_manager = RAGEmbedderManager()


# ─── Pre-warm au démarrage FastAPI ────────────────────────────────────────────

def prechauffer_index_rag() -> None:
    """
    Charge tous les index RAG disponibles sur disque.
    Appeler dans le lifespan FastAPI (même pattern que prechauffer_index CIMA).
    """
    resultats = rag_embedder_manager.charger_tous_les_index()
    nb_ok = sum(1 for ok in resultats.values() if ok)
    nb_total = len(resultats)

    if nb_total == 0:
        logger.info("[RAG] Aucun document indexé sur disque — ingestion initiale requise")
    else:
        logger.info(
            f"[RAG] Index chargés : {nb_ok}/{nb_total} documents "
            f"({rag_embedder_manager.stats()['nb_chunks_total']:,} chunks)"
        )


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _hash_fichier(chemin: Path) -> str:
    """Hash MD5 d'un fichier pour invalidation de cache."""
    try:
        import hashlib
        return hashlib.md5(chemin.read_bytes()).hexdigest()
    except Exception:
        return ""
