"""
RAG TF-IDF — Retriever cloud-compatible sans sentence_transformers.

Utilise sklearn TfidfVectorizer (déjà dans requirements-cloud.txt) pour
la recherche sémantique légère. Qualité comparable à des embeddings denses
pour des textes juridiques (terminologie stable et répétitive).

Avantages vs sentence_transformers :
  - Aucune dépendance PyTorch (2 GB+)
  - Démarre en <2s vs 10-30s pour charger un modèle Transformer
  - Très bon sur textes juridiques (termes exacts = haute précision)
  - Support multilingue natif (fr/en mélangés)

Pipeline :
  1. Au démarrage : TF-IDF vectorizer ajusté sur TOUS les chunks du corpus
  2. À la requête : cosine_similarity entre query et matrice corpus
  3. Lookup exact articles en parallèle (score 0.99)
  4. Fusion + déduplication + formatage contexte prompt
"""
from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger("yukpo_assurance.rag.tfidf")

_RAG_DATA = Path("data/rag_knowledge")

# Seuils
SEUIL_SCORE_TFIDF   = 0.08   # Plus bas que dense (TF-IDF scores < cosine dense)
MAX_CHUNKS_RETOURNES = 10
MAX_CHARS_CONTEXTE   = 10_000
MAX_CHARS_CHUNK      = 1_200


class TFIDFRetriever:
    """
    Retriever TF-IDF sur le corpus réglementaire entier.
    Thread-safe, singleton.
    """

    def __init__(self):
        self._lock       = threading.Lock()
        self._vectorizer = None          # TfidfVectorizer ajusté
        self._matrix     = None          # Matrice sparse (N_chunks, N_features)
        self._chunks_meta: list[dict] = []  # [{texte, doc_id, metadata, ...}]
        self._pret       = False

    @property
    def pret(self) -> bool:
        return self._pret

    # ── Initialisation ─────────────────────────────────────────────────────

    def construire_index(self) -> bool:
        """
        Lit tous les chunks.json du corpus et construit l'index TF-IDF.
        Bloquant — appeler dans un thread de démarrage.
        """
        with self._lock:
            if self._pret:
                return True

            try:
                from sklearn.feature_extraction.text import TfidfVectorizer
                from sklearn.preprocessing import normalize
            except ImportError:
                logger.warning("[TF-IDF] scikit-learn non disponible — RAG désactivé")
                return False

            if not _RAG_DATA.exists():
                logger.warning(f"[TF-IDF] Dossier corpus absent : {_RAG_DATA}")
                return False

            corpus_textes: list[str] = []

            import json
            for dossier in sorted(_RAG_DATA.iterdir()):
                if not dossier.is_dir():
                    continue
                chunks_path = dossier / "chunks.json"
                if not chunks_path.exists():
                    continue
                try:
                    data = json.loads(chunks_path.read_text(encoding="utf-8"))
                    doc_meta = data.get("metadata", {})
                    doc_id   = data.get("doc_id", dossier.name)
                    for chunk in data.get("chunks", []):
                        texte = chunk.get("texte", "").strip()
                        if not texte:
                            continue
                        corpus_textes.append(texte)
                        self._chunks_meta.append({
                            "texte":    texte,
                            "texte_embed": chunk.get("texte_embed", texte),
                            "doc_id":   doc_id,
                            "metadata": {**doc_meta, **chunk.get("metadata", {})},
                            "index":    chunk.get("index", 0),
                        })
                except Exception as e:
                    logger.warning(f"[TF-IDF] Erreur lecture {dossier.name}: {e}")

            if not corpus_textes:
                logger.warning("[TF-IDF] Corpus vide — index non construit")
                return False

            logger.info(f"[TF-IDF] Indexation de {len(corpus_textes)} chunks...")

            self._vectorizer = TfidfVectorizer(
                analyzer="word",
                ngram_range=(1, 2),        # unigrams + bigrams
                max_features=80_000,
                sublinear_tf=True,         # log(TF) — réduit l'impact des mots très fréquents
                min_df=2,                  # ignore les hapax
                strip_accents="unicode",
                token_pattern=r"(?u)\b\w{2,}\b",  # tokens ≥ 2 chars
            )

            self._matrix = self._vectorizer.fit_transform(corpus_textes)
            # L2-normalisation pour que cosine_similarity = dot product
            self._matrix = normalize(self._matrix, norm="l2")

            self._pret = True
            logger.info(
                f"[TF-IDF] Index prêt : {len(corpus_textes)} chunks, "
                f"{self._matrix.shape[1]} features"
            )
            return True

    # ── Recherche ─────────────────────────────────────────────────────────

    def rechercher(
        self,
        question: str,
        doc_ids:  Optional[list[str]] = None,
        top_k:    int                 = MAX_CHUNKS_RETOURNES,
        seuil:    float               = SEUIL_SCORE_TFIDF,
    ) -> list[dict]:
        """
        Recherche TF-IDF cosine + lookup exact articles.
        Retourne les chunks les plus pertinents triés par score décroissant.
        """
        if not self._pret or not question.strip():
            return []

        import numpy as np
        from sklearn.preprocessing import normalize

        # ── Lookup exact articles ────────────────────────────────────────
        resultats_exacts = self._lookup_articles(question, doc_ids=doc_ids, top_k=4)
        ids_exacts = {id(r) for r in resultats_exacts}  # déduplication par objet

        # ── Recherche TF-IDF ─────────────────────────────────────────────
        try:
            q_vec = self._vectorizer.transform([question])
            q_vec = normalize(q_vec, norm="l2")

            scores = (self._matrix @ q_vec.T).toarray().flatten()

            if doc_ids is not None:
                doc_ids_set = set(doc_ids)
                mask = np.array([
                    1.0 if self._chunks_meta[i]["doc_id"] in doc_ids_set else 0.0
                    for i in range(len(self._chunks_meta))
                ])
                scores = scores * mask

            top_idx = np.argsort(scores)[::-1][: top_k * 3]

            # Textes déjà dans les résultats exacts
            textes_exacts = {r["texte"] for r in resultats_exacts}

            resultats_sem = []
            for idx in top_idx:
                if len(resultats_sem) >= top_k:
                    break
                score = float(scores[idx])
                if score < seuil:
                    break
                chunk = self._chunks_meta[idx]
                if chunk["texte"] in textes_exacts:
                    continue
                resultats_sem.append({**chunk, "score": score})

        except Exception as e:
            logger.warning(f"[TF-IDF] Recherche échouée : {e}")
            resultats_sem = []

        # Fusionner : exacts d'abord, puis sémantiques
        tous = resultats_exacts + resultats_sem
        tous.sort(key=lambda x: x["score"], reverse=True)
        return tous[:top_k]

    def _lookup_articles(
        self,
        question: str,
        doc_ids:  Optional[list[str]] = None,
        top_k:    int = 4,
    ) -> list[dict]:
        """Lookup exact des numéros d'articles cités dans la question."""
        _RE_NUM_ARTICLE = re.compile(
            r"(?:article|art\.?)\s+(\d{1,4}(?:\s*(?:bis|ter|quater|nouveau))?)",
            re.IGNORECASE,
        )
        patterns_raw = [
            variant
            for m in _RE_NUM_ARTICLE.finditer(question)
            for num in [m.group(1).strip()]
            for variant in [
                f"article {num}", f"art. {num}", f"art {num}",
                f"Article {num}", f"ART. {num}",
            ]
        ]
        if not patterns_raw:
            return []

        compiled = [re.compile(re.escape(p), re.IGNORECASE) for p in patterns_raw]
        doc_ids_set = set(doc_ids) if doc_ids else None
        resultats = []

        for chunk in self._chunks_meta:
            if doc_ids_set and chunk["doc_id"] not in doc_ids_set:
                continue
            texte = chunk["texte"] + " " + chunk.get("texte_embed", "")
            if any(pat.search(texte) for pat in compiled):
                resultats.append({**chunk, "score": 0.99})
            if len(resultats) >= top_k * 2:
                break

        return resultats[:top_k]


# ─── Singleton ────────────────────────────────────────────────────────────────
tfidf_retriever = TFIDFRetriever()


def construire_index_tfidf_background() -> None:
    """Lance la construction de l'index dans un thread daemon au démarrage."""
    import threading
    t = threading.Thread(target=tfidf_retriever.construire_index, daemon=True, name="rag-tfidf-build")
    t.start()
    logger.info("[TF-IDF] Construction index lancée en arrière-plan")


def rechercher_tfidf(
    question:  str,
    pays:      Optional[str]       = None,
    domaine:   Optional[str]       = None,
    doc_ids:   Optional[list[str]] = None,
    metier:    Optional[str]       = None,
    top_k:     int                 = MAX_CHUNKS_RETOURNES,
) -> str:
    """
    Interface publique identique à `rechercher_corpus_reglementaire`.
    Retourne un bloc contexte formaté prêt pour injection dans le prompt IA.
    Retourne "" si aucun résultat.
    """
    if not tfidf_retriever.pret:
        return ""

    # Résoudre les doc_ids cibles selon les filtres
    doc_ids_cibles = doc_ids
    if not doc_ids_cibles and (pays or domaine or metier):
        try:
            from modules.rag.sources_registry import SOURCES
            cibles = []
            for source in SOURCES:
                if pays and source.pays != pays and source.pays != "TRANSNATIONAL":
                    continue
                if domaine and source.domaine != domaine:
                    continue
                if metier and metier not in getattr(source, "metier_tags", []):
                    continue
                cibles.append(source.doc_id)
            doc_ids_cibles = cibles if cibles else None
        except Exception:
            pass

    resultats = tfidf_retriever.rechercher(question, doc_ids=doc_ids_cibles, top_k=top_k)

    if not resultats:
        return ""

    return _formater_contexte(resultats, question)


def _formater_contexte(resultats: list[dict], question: str) -> str:
    parties = []
    total_chars = 0
    vus: set[str] = set()

    for res in resultats:
        if total_chars >= MAX_CHARS_CONTEXTE:
            break
        texte = res.get("texte", "").strip()
        if not texte or texte in vus:
            continue
        vus.add(texte)

        if len(texte) > MAX_CHARS_CHUNK:
            texte = texte[:MAX_CHARS_CHUNK] + "…"

        meta     = res.get("metadata", {})
        doc_id   = res.get("doc_id", "")
        score    = res.get("score", 0.0)
        nom_doc  = meta.get("nom_doc") or meta.get("nom", doc_id)
        pays     = meta.get("pays", "")
        domaine  = meta.get("domaine", "")

        parts = [f"**{nom_doc}**"]
        if pays and pays != "TRANSNATIONAL":
            parts.append(f"Pays : {pays}")
        if domaine:
            parts.append(f"Domaine : {domaine}")
        parts.append(f"Score : {score:.2f}")

        bloc = f"#### {' | '.join(parts)}\n{texte}"
        parties.append(bloc)
        total_chars += len(bloc)

    if not parties:
        return ""

    header = (
        "=== CORPUS RÉGLEMENTAIRE — PASSAGES PERTINENTS ===\n"
        f"Question : {question[:120]}\n"
        f"Sources : {len(parties)} passage(s) | Corpus : OHADA · CGI · Code Travail · CIMA · COBAC · UEMOA · CEMAC\n"
        "=" * 50 + "\n"
    )
    footer = (
        "\n" + "=" * 50 + "\n"
        "INSTRUCTIONS :\n"
        "1. Cite les passages ci-dessus avec leur source EXACTE (nom du texte, article, pays).\n"
        "2. Reproduis le texte officiel TEL QUEL — sans le modifier.\n"
        "3. Apporte ensuite une ANALYSE SÉPARÉE étiquetée '[ANALYSE]' : impact pratique, "
        "sanctions, articulation avec d'autres textes.\n"
        "4. Si l'information demandée N'EST PAS dans les passages ci-dessus, utilise ta "
        "connaissance de formation en indiquant '[Réponse mémoire IA — non indexé corpus Yukpo]'.\n"
        "=" * 50
    )
    return header + "\n\n".join(parties) + footer
