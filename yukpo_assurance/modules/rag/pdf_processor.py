"""
PDF Processor — Extraction de texte et découpage en chunks.

Moteur : pdfplumber (meilleure extraction sur PDF natifs et scannés).
Fallback : PyMuPDF (fitz) pour les PDF complexes ou corrompus.

Stratégie de chunking :
  - Découpe sur séparateurs juridiques : "Article", "Chapitre", "Titre", "Livre"
  - Taille max 900 caractères, overlap 150 caractères
  - Chaque chunk conserve ses metadata (page, doc_id, domaine, pays…)
"""
import json
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger("yukpo_assurance.rag.pdf_processor")

# ─── Séparateurs juridiques (ordre du plus précis au plus générique) ──────────
_SEPARATEURS = [
    r"\n(?=Article\s+\d)",          # "Article 47"
    r"\n(?=Art\.\s+\d)",            # "Art. 47"
    r"\n(?=ARTICLE\s+\d)",          # "ARTICLE 47" (majuscules)
    r"\n(?=Chapitre\s+[IVX\d])",    # "Chapitre III"
    r"\n(?=CHAPITRE\s+[IVX\d])",
    r"\n(?=Titre\s+[IVX\d])",       # "Titre II"
    r"\n(?=TITRE\s+[IVX\d])",
    r"\n(?=Livre\s+[IVX\d])",       # "Livre Premier"
    r"\n(?=LIVRE\s+[IVX\d])",
    r"\n(?=Section\s+[IVX\d])",
    r"\n\n\n",                       # Triple saut de ligne
    r"\n\n",                         # Double saut de ligne
    r"\n",
    r"\. ",
]

_CHUNK_MAX   = 900    # Taille max d'un chunk en caractères
_CHUNK_OVER  = 150   # Overlap entre chunks consécutifs


# ══════════════════════════════════════════════════════════════════════════════
# Extraction texte depuis PDF
# ══════════════════════════════════════════════════════════════════════════════

def extraire_texte_pdf(pdf_bytes: bytes) -> str:
    """
    Extrait le texte d'un PDF.
    Essaie pdfplumber d'abord, puis PyMuPDF en fallback.
    Retourne une chaîne vide si aucune extraction n'est possible.
    """
    texte = _extraire_avec_pdfplumber(pdf_bytes)
    if len(texte.strip()) < 200:
        logger.info("[PDFProcessor] pdfplumber insuffisant — tentative PyMuPDF")
        texte = _extraire_avec_pymupdf(pdf_bytes)

    if not texte.strip():
        logger.warning("[PDFProcessor] Extraction texte échouée (PDF scanné sans OCR ?)")

    return _nettoyer_texte(texte)


def _extraire_avec_pdfplumber(pdf_bytes: bytes) -> str:
    """Extraction via pdfplumber — optimal pour PDF natifs."""
    try:
        import io
        import pdfplumber
        parties = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    parties.append(t)
        return "\n\n".join(parties)
    except Exception as e:
        logger.debug(f"[PDFProcessor] pdfplumber erreur : {e}")
        return ""


def _extraire_avec_pymupdf(pdf_bytes: bytes) -> str:
    """Extraction via PyMuPDF (fitz) — fallback robuste."""
    try:
        import fitz  # PyMuPDF
        parties = []
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for page in doc:
                t = page.get_text("text")
                if t:
                    parties.append(t)
        return "\n\n".join(parties)
    except Exception as e:
        logger.debug(f"[PDFProcessor] PyMuPDF erreur : {e}")
        return ""


def _nettoyer_texte(texte: str) -> str:
    """
    Nettoyage du texte extrait :
    - Supprime les numéros de pages isolés
    - Réduit les espaces multiples
    - Normalise les sauts de ligne
    - Supprime les en-têtes/pieds répétitifs
    """
    if not texte:
        return ""

    # Supprimer les numéros de page seuls sur une ligne
    texte = re.sub(r"^\s*\d+\s*$", "", texte, flags=re.MULTILINE)

    # Normaliser les espaces dans les mots coupés par césure
    texte = re.sub(r"(\w)-\n(\w)", r"\1\2", texte)

    # Réduire les espaces multiples
    texte = re.sub(r" {3,}", "  ", texte)

    # Réduire les sauts de ligne multiples
    texte = re.sub(r"\n{4,}", "\n\n\n", texte)

    return texte.strip()


# ══════════════════════════════════════════════════════════════════════════════
# Découpage en chunks
# ══════════════════════════════════════════════════════════════════════════════

def decouper_en_chunks(
    texte: str,
    metadata: dict,
    chunk_max: int = _CHUNK_MAX,
    overlap: int   = _CHUNK_OVER,
) -> list[dict]:
    """
    Découpe un texte en chunks avec overlap et metadata enrichie.
    Retourne une liste de dicts :
      {"texte": str, "metadata": {...}, "texte_embed": str}
    """
    if not texte.strip():
        return []

    # Découpe initiale sur séparateurs juridiques
    segments = _decouper_par_separateurs(texte)

    # Fusionner les segments trop courts, diviser les trop longs
    chunks_texte = _normaliser_taille(segments, chunk_max, overlap)

    # Enrichir avec metadata
    chunks = []
    for i, chunk in enumerate(chunks_texte):
        if not chunk.strip():
            continue
        chunks.append({
            "texte": chunk.strip(),
            "metadata": {
                **metadata,
                "chunk_index": i,
                "chunk_total": len(chunks_texte),
                "nb_chars":    len(chunk),
            },
            # Texte d'indexation enrichi avec les metadata pour le RAG
            "texte_embed": _enrichir_pour_embed(chunk, metadata),
        })

    return chunks


def _decouper_par_separateurs(texte: str) -> list[str]:
    """Découpe en utilisant les séparateurs juridiques par ordre de priorité."""
    segments = [texte]

    for sep_pattern in _SEPARATEURS:
        nouveaux = []
        for seg in segments:
            if len(seg) <= _CHUNK_MAX:
                nouveaux.append(seg)
                continue
            parties = re.split(sep_pattern, seg)
            nouveaux.extend(parties)
        segments = nouveaux

    return [s for s in segments if s.strip()]


def _normaliser_taille(
    segments: list[str],
    chunk_max: int,
    overlap: int,
) -> list[str]:
    """
    Fusionne les segments trop courts (< 100 chars) avec le suivant.
    Divise les segments trop longs en sous-chunks avec overlap.
    """
    # Fusion des très courts
    fusionnes = []
    tampon = ""
    for seg in segments:
        if len(tampon) + len(seg) < chunk_max:
            tampon = (tampon + "\n\n" + seg).strip()
        else:
            if tampon:
                fusionnes.append(tampon)
            tampon = seg
    if tampon:
        fusionnes.append(tampon)

    # Division des trop longs avec overlap
    result = []
    for seg in fusionnes:
        if len(seg) <= chunk_max:
            result.append(seg)
        else:
            # Diviser par mots avec overlap
            mots   = seg.split()
            debut  = 0
            while debut < len(mots):
                # Construire chunk jusqu'à chunk_max
                fin = debut
                courant = ""
                while fin < len(mots) and len(courant) + len(mots[fin]) + 1 < chunk_max:
                    courant += (" " if courant else "") + mots[fin]
                    fin += 1
                if not courant:
                    fin = debut + 1
                    courant = mots[debut]
                result.append(courant)
                # Reculer de overlap_mots pour le prochain chunk
                overlap_mots = max(1, overlap // 6)
                debut = max(debut + 1, fin - overlap_mots)

    return result


def _enrichir_pour_embed(chunk: str, metadata: dict) -> str:
    """
    Construit le texte d'embedding enrichi avec contexte pays/domaine.
    Cela améliore la précision de la recherche sémantique.
    Ex: "Sénégal fiscal Code Général des Impôts Article 47 ..."
    """
    prefixe_parts = []
    if metadata.get("pays") and metadata["pays"] != "TRANSNATIONAL":
        prefixe_parts.append(metadata["pays"])
    if metadata.get("domaine"):
        prefixe_parts.append(metadata["domaine"])
    if metadata.get("nom_doc"):
        prefixe_parts.append(metadata["nom_doc"])

    prefixe = " — ".join(prefixe_parts)
    return f"{prefixe}\n{chunk}".strip() if prefixe else chunk


# ══════════════════════════════════════════════════════════════════════════════
# Pipeline complet : PDF bytes → fichier chunks.json
# ══════════════════════════════════════════════════════════════════════════════

_HTML_TEXT_MARKER = b"##HTML_TEXT_DOC##"


def traiter_pdf(
    pdf_bytes: bytes,
    doc_id:    str,
    metadata:  dict,
    chemin_sortie: Path,
) -> int:
    """
    Pipeline complet :
      PDF bytes → extraction texte → chunks → sauvegarde chunks.json

    Accepte aussi les pseudo-PDFs HTML générés par downloader._html_legal_vers_pseudo_pdf().
    Retourne le nombre de chunks générés (0 si échec).
    """
    # Détecter si c'est un texte HTML converti (ILO WEBTEXT, Refworld…)
    if pdf_bytes.startswith(_HTML_TEXT_MARKER):
        texte_brut = pdf_bytes.decode("utf-8", errors="replace")
        # Supprimer le header ##HTML_TEXT_DOC##doc_id##\n
        lignes = texte_brut.split("\n", 1)
        texte = _nettoyer_texte(lignes[1] if len(lignes) > 1 else texte_brut)
        logger.info(f"[PDFProcessor] {doc_id} — Traitement texte HTML direct ({len(texte):,} chars)")
    else:
        # 1. Extraction texte depuis PDF
        texte = extraire_texte_pdf(pdf_bytes)
    if not texte:
        logger.error(f"[PDFProcessor] {doc_id} — Extraction texte impossible")
        return 0
    # Fin du bloc conditionnel HTML vs PDF

    nb_chars = len(texte)
    logger.info(f"[PDFProcessor] {doc_id} — {nb_chars:,} caractères extraits")

    # 2. Découpage
    meta_complete = {
        "doc_id":  doc_id,
        "nom_doc": metadata.get("nom", doc_id),
        **metadata,
    }
    chunks = decouper_en_chunks(texte, meta_complete)
    if not chunks:
        logger.error(f"[PDFProcessor] {doc_id} — Découpage a produit 0 chunks")
        return 0

    logger.info(f"[PDFProcessor] {doc_id} — {len(chunks)} chunks générés")

    # 3. Sauvegarde
    try:
        chemin_sortie.parent.mkdir(parents=True, exist_ok=True)
        with open(chemin_sortie, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "doc_id":   doc_id,
                    "metadata": meta_complete,
                    "nb_chars": nb_chars,
                    "nb_chunks": len(chunks),
                    "chunks":   chunks,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        logger.info(f"[PDFProcessor] {doc_id} — Chunks sauvegardés : {chemin_sortie}")
    except Exception as e:
        logger.error(f"[PDFProcessor] {doc_id} — Sauvegarde échouée : {e}")
        return 0

    return len(chunks)


def charger_chunks(chemin: Path) -> Optional[list[dict]]:
    """Charge les chunks depuis un fichier JSON existant."""
    try:
        if not chemin.exists():
            return None
        data = json.loads(chemin.read_text(encoding="utf-8"))
        return data.get("chunks", [])
    except Exception as e:
        logger.warning(f"[PDFProcessor] Chargement chunks {chemin} échoué : {e}")
        return None
