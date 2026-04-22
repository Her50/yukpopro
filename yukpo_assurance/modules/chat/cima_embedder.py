"""
CIMAEmbedder — Recherche sémantique dense pour le Code CIMA.

Modèle : paraphrase-multilingual-MiniLM-L12-v2 (sentence-transformers)
  - 384 dimensions, multilingue (50+ langues dont français)
  - Capture la sémantique : "fonds propres" ≈ "capital minimum"
  - 118 Mo, CPU-only, pas de GPU requis

Cache disque (data/cima_knowledge/cima_embeddings.npz) :
  - Calculé une seule fois (~15s premier démarrage)
  - Rechargé en ~200ms les fois suivantes
  - Invalidé automatiquement si le JSON CIMA change (hash MD5)

Thread-safe : threading.Lock sur la construction de l'index.
Pre-warm : appeler prechauffer_index() dans le lifespan FastAPI.
"""
import hashlib
import json
import logging
import os
import re
import threading
from typing import Optional

import numpy as np

logger = logging.getLogger("yukpo_assurance.cima.embedder")

_BASE_DIR = os.path.dirname(__file__)
_JSON_PATH = os.path.normpath(
    os.path.join(_BASE_DIR, "../../data/cima_knowledge/code_cima.json")
)
_CACHE_PATH = os.path.normpath(
    os.path.join(_BASE_DIR, "../../data/cima_knowledge/cima_embeddings.npz")
)
_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


# ─── Normalisation accents ────────────────────────────────────────────────────

_TABLE_ACCENTS: dict[int, str] = {
    ord(c): r for c, r in [
        ("\u00e9", "e"), ("\u00e8", "e"), ("\u00ea", "e"), ("\u00eb", "e"),
        ("\u00e0", "a"), ("\u00e2", "a"), ("\u00e4", "a"),
        ("\u00ee", "i"), ("\u00ef", "i"),
        ("\u00f4", "o"), ("\u00f6", "o"),
        ("\u00f9", "u"), ("\u00fb", "u"), ("\u00fc", "u"),
        ("\u00e7", "c"),
        ("\u00c9", "e"), ("\u00c8", "e"), ("\u00ca", "e"),
        ("\u00c0", "a"), ("\u00c2", "a"),
        ("\u00ce", "i"), ("\u00d4", "o"), ("\u00d9", "u"), ("\u00c7", "c"),
    ]
}


def _normaliser(texte: str) -> str:
    return texte.lower().translate(_TABLE_ACCENTS)


# ─── Hash du JSON pour invalider le cache ────────────────────────────────────

def _hash_json() -> str:
    with open(_JSON_PATH, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


# ─── Extraction des articles ─────────────────────────────────────────────────

def _normaliser_numero(cle: str) -> str:
    nom = re.sub(r"^art_", "", cle)
    nom = re.sub(r"_bis$", "-bis", nom)
    nom = re.sub(r"_ter$", "-ter", nom)
    nom = re.sub(r"_quater$", "-quater", nom)
    nom = nom.replace("_", "-")
    return f"Art. {nom}"


def _extraire_tous_articles(data: dict) -> list[dict]:
    """
    Extrait chaque article du JSON CIMA avec son texte d'indexation.
    Le texte d'indexation combine : numéro + texte officiel + portée.
    Les accents sont conservés (le modèle multilingue les gère nativement).
    """
    articles: list[dict] = []

    def _recursif(obj: dict, chemin: str):
        if not isinstance(obj, dict):
            return
        for k, v in obj.items():
            if not k.startswith("art_"):
                _recursif(v, f"{chemin}/{k}" if chemin else k)
                continue
            if isinstance(v, dict):
                texte = v.get("texte", "")
                portee = v.get("portee", "")
            elif isinstance(v, str):
                texte = v
                portee = ""
            else:
                continue
            if not texte.strip():
                continue
            numero = _normaliser_numero(k)
            # Texte complet pour l'embedding — on garde les accents,
            # le modèle multilingue les comprend mieux que la version normalisée
            texte_embed = f"{numero}. {texte} {portee}".strip()
            articles.append({
                "cle":         k,
                "numero":      numero,
                "texte":       texte,
                "portee":      portee,
                "chemin":      chemin,
                "contenu":     v,
                "_embed_text": texte_embed,
            })

    _recursif(data, "")
    return articles


# ─── Classe principale ───────────────────────────────────────────────────────

class CIMAEmbedder:
    """
    Moteur de recherche sémantique dense (sentence-transformers) sur le Code CIMA.

    Usage :
        from modules.chat.cima_embedder import cima_embedder
        resultats = cima_embedder.rechercher("marge de solvabilite non-vie", top_k=5)
    """

    def __init__(self):
        self._articles: list[dict] = []
        self._embeddings: Optional[np.ndarray] = None  # shape (N, 384)
        self._model = None                              # SentenceTransformer (lazy)
        self._pret = False
        self._lock = threading.Lock()

    # ──────────────────────────────────────────────────────────────────────────
    # Chargement du modèle (lazy)
    # ──────────────────────────────────────────────────────────────────────────

    def _charger_modele(self):
        """Charge le modèle sentence-transformers (une seule fois, ~3s)."""
        if self._model is None:
            import os as _os
            # Supprime l'avertissement symlink Windows (non critique)
            _os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(_MODEL_NAME)
            logger.info(f"[CIMAEmbedder] Modele charge : {_MODEL_NAME}")

    # ──────────────────────────────────────────────────────────────────────────
    # Construction / chargement de l'index
    # ──────────────────────────────────────────────────────────────────────────

    def construire_index(self) -> None:
        """
        Construit l'index d'embeddings denses.
        - Si un cache valide existe sur disque → le charge (~200ms)
        - Sinon → calcule les embeddings (~15s) et sauvegarde le cache
        Thread-safe : un seul thread construit, les autres attendent.
        """
        with self._lock:
            if self._pret:
                return

            try:
                json_hash = _hash_json()
                with open(_JSON_PATH, encoding="utf-8") as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError) as e:
                logger.error(f"[CIMAEmbedder] JSON inaccessible : {e}")
                return

            self._articles = _extraire_tous_articles(data)
            if not self._articles:
                logger.warning("[CIMAEmbedder] Aucun article extrait")
                return

            # ── Tentative de chargement du cache (AVANT le modèle) ───────────
            # Si le cache est valide, le modèle sera chargé en lazy à la première recherche.
            # Cela évite de bloquer le startup de 3-10s juste pour charger le modèle.
            if self._charger_cache(json_hash):
                self._pret = True
                logger.info(
                    f"[CIMAEmbedder] Cache charge : {len(self._articles)} articles, "
                    f"dim={self._embeddings.shape[1]}"
                )
                return

            # ── Pas de cache valide : charger le modèle pour calculer les embeddings ──
            self._charger_modele()

            # ── Calcul des embeddings (premier démarrage) ─────────────────────
            logger.info(
                f"[CIMAEmbedder] Calcul embeddings pour {len(self._articles)} articles "
                f"(modele : {_MODEL_NAME})..."
            )
            corpus = [a["_embed_text"] for a in self._articles]
            self._embeddings = self._model.encode(
                corpus,
                batch_size=64,
                show_progress_bar=False,
                normalize_embeddings=True,   # L2-normalisé → dot product = cosine
                convert_to_numpy=True,
            )
            self._pret = True
            self._sauvegarder_cache(json_hash)
            logger.info(
                f"[CIMAEmbedder] Index construit et cache : "
                f"{len(self._articles)} articles, dim={self._embeddings.shape[1]}"
            )

    def _charger_cache(self, json_hash: str) -> bool:
        """Charge le cache .npz si valide. Retourne True si succès."""
        try:
            if not os.path.exists(_CACHE_PATH):
                return False
            loaded = np.load(_CACHE_PATH, allow_pickle=True)
            if str(loaded.get("hash", b"")) != json_hash:
                logger.info("[CIMAEmbedder] Cache invalide (JSON modifie) — recalcul")
                return False
            self._embeddings = loaded["embeddings"]
            return True
        except Exception as e:
            logger.warning(f"[CIMAEmbedder] Cache illisible : {e}")
            return False

    def _sauvegarder_cache(self, json_hash: str) -> None:
        """Sauvegarde les embeddings sur disque pour les prochains démarrages."""
        try:
            os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
            np.savez_compressed(
                _CACHE_PATH,
                embeddings=self._embeddings,
                hash=np.array(json_hash),
            )
            taille_ko = os.path.getsize(_CACHE_PATH) // 1024
            logger.info(f"[CIMAEmbedder] Cache sauvegarde ({taille_ko} Ko) : {_CACHE_PATH}")
        except Exception as e:
            logger.warning(f"[CIMAEmbedder] Sauvegarde cache echouee : {e}")

    def _assurer_index(self) -> None:
        if not self._pret:
            self.construire_index()

    # ──────────────────────────────────────────────────────────────────────────
    # Recherche
    # ──────────────────────────────────────────────────────────────────────────

    def rechercher(
        self,
        question: str,
        top_k: int = 8,
        seuil_score: float = 0.40,
    ) -> list[dict]:
        """
        Retourne les top_k articles les plus pertinents (similarité cosinus dense).

        Seuil calibré pour paraphrase-multilingual-MiniLM-L12-v2 sur textes CIMA :
          > 0.65 = très pertinent (correspondance directe)
          0.50–0.65 = pertinent
          0.40–0.50 = possiblement pertinent
          < 0.40 = bruit → ignoré

        top_k=8 : suffisant pour couvrir plusieurs articles sur un même sujet.

        Retourne [] sans exception si l'index est indisponible.
        """
        self._assurer_index()
        if not self._pret or self._embeddings is None:
            return []

        try:
            self._charger_modele()
            q_emb = self._model.encode(
                [question],
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
        except Exception as e:
            logger.warning(f"[CIMAEmbedder] Encodage question echoue : {e}")
            return []

        # dot product sur vecteurs L2-normalisés = cosine similarity
        scores = (self._embeddings @ q_emb.T).flatten()
        top_indices = np.argsort(scores)[::-1][: top_k * 2]

        resultats: list[dict] = []
        seen_cles: set[str] = set()
        for idx in top_indices:
            if len(resultats) >= top_k:
                break
            score = float(scores[idx])
            if score < seuil_score:
                break
            art = self._articles[idx]
            if art["cle"] in seen_cles:
                continue
            seen_cles.add(art["cle"])
            resultats.append({**art, "score": score})

        return resultats

    def rechercher_par_cle(self, cle: str) -> Optional[dict]:
        """Cherche un article précis par sa clé (ex: 'art_337_1')."""
        self._assurer_index()
        for art in self._articles:
            if art["cle"] == cle:
                return art
        return None

    @property
    def nb_articles(self) -> int:
        self._assurer_index()
        return len(self._articles)

    @property
    def pret(self) -> bool:
        return self._pret


# ─── Singleton ────────────────────────────────────────────────────────────────
cima_embedder = CIMAEmbedder()


# ─── Pre-warm au démarrage FastAPI ────────────────────────────────────────────

def prechauffer_index() -> None:
    """
    Appeler dans le lifespan FastAPI pour absorber le cold-start au boot.
    Premier démarrage : ~15s (calcul embeddings + sauvegarde cache).
    Démarrages suivants : ~200ms (chargement cache disque).
    """
    if not cima_embedder.pret:
        logger.info("[CIMAEmbedder] Pre-chauffe de l'index semantique CIMA...")
        cima_embedder.construire_index()
        if cima_embedder.pret:
            logger.info(
                f"[CIMAEmbedder] Pret : {cima_embedder.nb_articles} articles indexes"
            )
        else:
            logger.warning("[CIMAEmbedder] Index non disponible — RAG keyword seul actif")
