"""
Downloader RAG — Téléchargement et détection de changement.

Stratégie de détection (du plus léger au plus lourd) :
  1. Headers HTTP (ETag + Last-Modified + Content-Length) → sans télécharger
  2. Hash SHA-256 du contenu → si les headers ne sont pas fiables
  3. Fallback sur l'URL secondaire si la principale est inaccessible

Scraping HTML : pour les pages qui contiennent un lien vers le PDF (type HTML_PAGE),
on extrait le premier lien .pdf avec BeautifulSoup.

Persistance des hashes : data/rag_knowledge/hashes.json
"""
import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime
from typing import Optional
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from modules.rag.sources_registry import SourceDoc, SourceType

logger = logging.getLogger("yukpo_assurance.rag.downloader")

# ─── Chemins ──────────────────────────────────────────────────────────────────
_BASE_DIR = Path(__file__).parent.parent.parent  # yukpo_assurance/
_RAG_DATA  = _BASE_DIR / "data" / "rag_knowledge"
_HASH_FILE = _RAG_DATA / "hashes.json"

# ─── HTTP Configuration ───────────────────────────────────────────────────────
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,text/html,*/*",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}
_TIMEOUT   = httpx.Timeout(60.0, connect=15.0)
_MAX_SIZE  = 50 * 1024 * 1024  # 50 Mo — sécurité anti-bombes PDF

# ─── Headers spécifiques par domaine (anti-hotlink bypass) ────────────────────
_DOMAIN_HEADERS: dict[str, dict] = {
    "droit-afrique.com": {
        "Referer": "https://www.droit-afrique.com/",
        "Origin":  "https://www.droit-afrique.com",
    },
    "juriafrica.com": {
        "Referer": "https://www.juriafrica.com/",
    },
    "ohada.com": {
        "Referer": "https://www.ohada.com/",
    },
    "wikipedia.org": {
        # Wikipedia bloque les UA qui annoncent PDF — surcharger Accept et UA
        "User-Agent": "YukpoAssurance-RAG/1.0 (educational; contact:lelehernandez2007@yahoo.fr) python-httpx",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    },
}


def _headers_pour_url(url: str) -> dict:
    """Retourne les headers adaptés selon le domaine de l'URL."""
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lower()
    for key, extra in _DOMAIN_HEADERS.items():
        if key in domain:
            return {**_HEADERS, **extra}
    return _HEADERS


# ══════════════════════════════════════════════════════════════════════════════
# Persistance des hashes
# ══════════════════════════════════════════════════════════════════════════════

def _charger_hashes() -> dict:
    try:
        if _HASH_FILE.exists():
            return json.loads(_HASH_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[Downloader] Lecture hashes.json échouée : {e}")
    return {}


def _sauvegarder_hashes(hashes: dict) -> None:
    try:
        _RAG_DATA.mkdir(parents=True, exist_ok=True)
        _HASH_FILE.write_text(
            json.dumps(hashes, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning(f"[Downloader] Sauvegarde hashes.json échouée : {e}")


def _maj_hash(doc_id: str, hash_contenu: str, url_utilisee: str) -> None:
    hashes = _charger_hashes()
    hashes[doc_id] = {
        "hash":        hash_contenu,
        "url":         url_utilisee,
        "verifie_le":  datetime.utcnow().isoformat(),
    }
    _sauvegarder_hashes(hashes)


def get_hash_connu(doc_id: str) -> Optional[str]:
    return _charger_hashes().get(doc_id, {}).get("hash")


# ══════════════════════════════════════════════════════════════════════════════
# Scraping HTML → extraction du lien PDF
# ══════════════════════════════════════════════════════════════════════════════

def _extraire_url_pdf_depuis_html(html: str, base_url: str) -> Optional[str]:
    """
    Extrait le premier lien .pdf (absolu ou relatif) trouvé dans la page HTML.
    Gère les liens relatifs en les résolvant avec base_url.
    Retourne None si aucun lien PDF trouvé (le texte HTML sera traité directement).
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all("a", href=True):
            href: str = tag["href"].strip()
            # Lien direct .pdf
            if href.lower().endswith(".pdf"):
                if href.startswith("http"):
                    return href
                # Lien relatif → construire URL absolue
                from urllib.parse import urljoin
                return urljoin(base_url, href)
            # Lien avec /pdf/ ou download dans le chemin
            if "/pdf/" in href.lower() or "download" in href.lower() or "telecharger" in href.lower():
                if href.startswith("http"):
                    return href
                from urllib.parse import urljoin
                return urljoin(base_url, href)
    except Exception as e:
        logger.debug(f"[Downloader] Scraping HTML échoué : {e}")
    return None


def _html_legal_vers_pseudo_pdf(html: str, doc_id: str) -> bytes:
    """
    Convertit le texte d'une page HTML légale (ILO WEBTEXT, Refworld, etc.)
    en bytes UTF-8 encodés avec un marqueur spécial pour le pdf_processor.
    Le pdf_processor détecte ce format et extrait le texte directement.
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    # Supprimer scripts, styles, nav
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    texte = soup.get_text(separator="\n", strip=True)
    # Encoder avec un en-tête identifiable par pdf_processor
    contenu = f"##HTML_TEXT_DOC##{doc_id}##\n{texte}".encode("utf-8")
    return contenu


# ══════════════════════════════════════════════════════════════════════════════
# Téléchargement principal
# ══════════════════════════════════════════════════════════════════════════════

class ResultatTelechargement:
    """Résultat d'une tentative de téléchargement."""
    __slots__ = ("doc_id", "a_change", "contenu", "hash", "url_utilisee", "erreur")

    def __init__(
        self,
        doc_id: str,
        a_change: bool = False,
        contenu: Optional[bytes] = None,
        hash: str = "",
        url_utilisee: str = "",
        erreur: Optional[str] = None,
    ):
        self.doc_id       = doc_id
        self.a_change     = a_change
        self.contenu      = contenu
        self.hash         = hash
        self.url_utilisee = url_utilisee
        self.erreur       = erreur


async def telecharger_si_change(source: SourceDoc) -> ResultatTelechargement:
    """
    Vérifie si le document a changé et le télécharge si nécessaire.
    Essaie l'URL principale d'abord, puis le fallback.
    """
    hash_connu = get_hash_connu(source.doc_id)
    urls = [u for u in [source.url_principale, source.url_fallback] if u]

    for url in urls:
        try:
            result = await _tenter_telechargement(source, url, hash_connu)
            if result.erreur is None:
                return result
            logger.warning(
                f"[Downloader] {source.doc_id} — URL {url[:60]}… échouée : {result.erreur}"
            )
        except Exception as e:
            logger.warning(f"[Downloader] {source.doc_id} — Exception sur {url[:60]}… : {e}")
            continue

    return ResultatTelechargement(
        doc_id=source.doc_id,
        erreur=f"Toutes les URLs ont échoué ({len(urls)} tentatives)",
    )


async def _tenter_telechargement(
    source: SourceDoc,
    url: str,
    hash_connu: Optional[str],
) -> ResultatTelechargement:
    """
    Tentative de téléchargement sur une URL donnée.
    Pour les pages HTML : scraping du lien PDF d'abord.
    """
    async with httpx.AsyncClient(
        headers=_headers_pour_url(url),
        timeout=_TIMEOUT,
        follow_redirects=True,
        verify=False,  # Certains sites africains ont des certificats auto-signés
    ) as client:

        # ── Étape 1 : si page HTML → extraire l'URL du PDF ────────────────────
        # Domaines pour lesquels on saute la recherche de PDF et on lit le HTML directement
        _FORCE_HTML_DOMAINS = {
            "wikipedia.org", "afnor.org", "brvm.org", "boad.org",
            # Portails juridiques : ne pas télécharger les PDF liés (souvent scannés)
            # → extraire le texte HTML de la page directement
            "wageindicator.org", "juriafrica.com", "refworld.org",
            "ilo.org",  # ILO webtext pages — texte HTML meilleur que les PDFs NATLEX scannés
        }
        pdf_url = url
        if source.source_type == SourceType.HTML_PAGE:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")

                from urllib.parse import urlparse as _urlparse
                _domain = _urlparse(url).netloc.lower()
                _force_html = any(d in _domain for d in _FORCE_HTML_DOMAINS)

                if "pdf" in content_type.lower():
                    # La page répond directement avec un PDF
                    pdf_url = url
                    contenu = resp.content
                elif _force_html:
                    # Domaine à lecture HTML directe — pas de recherche de lien PDF
                    logger.info(
                        f"[Downloader] {source.doc_id} — "
                        "Extraction texte HTML direct (domaine force-HTML)"
                    )
                    contenu = _html_legal_vers_pseudo_pdf(resp.text, source.doc_id)
                else:
                    # C'est du HTML → essayer d'extraire un lien PDF
                    extracted = _extraire_url_pdf_depuis_html(resp.text, url)
                    if extracted:
                        pdf_url = extracted
                        resp = await client.get(pdf_url)
                        resp.raise_for_status()
                        contenu = resp.content
                    else:
                        # Pas de lien PDF → traiter le HTML directement (ILO WEBTEXT, Refworld…)
                        logger.info(
                            f"[Downloader] {source.doc_id} — "
                            "Pas de lien PDF dans la page, extraction texte HTML direct"
                        )
                        contenu = _html_legal_vers_pseudo_pdf(resp.text, source.doc_id)
            except httpx.HTTPStatusError as e:
                return ResultatTelechargement(
                    doc_id=source.doc_id,
                    erreur=f"HTTP {e.response.status_code} sur {url[:60]}",
                )

        else:
            # ── Étape 1 bis : DIRECT_PDF — tenter HEAD d'abord (léger) ─────────
            try:
                head = await client.head(url)
                etag          = head.headers.get("etag", "")
                last_modified = head.headers.get("last-modified", "")
                content_len   = head.headers.get("content-length", "")
                sig_headers   = f"{etag}|{last_modified}|{content_len}"

                # Stocker la signature des headers pour détecter changement rapide
                hashes = _charger_hashes()
                stored_sig = hashes.get(source.doc_id, {}).get("header_sig", "INCONNU")

                if (
                    stored_sig == sig_headers
                    and sig_headers != "||"
                    and hash_connu
                ):
                    # Headers identiques → pas de changement probable
                    _maj_hash(source.doc_id, hash_connu, url)
                    return ResultatTelechargement(
                        doc_id=source.doc_id,
                        a_change=False,
                        hash=hash_connu,
                        url_utilisee=url,
                    )
            except Exception:
                pass  # HEAD non supporté → on passe au GET direct

            # ── GET complet ────────────────────────────────────────────────────
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                contenu = resp.content
            except httpx.HTTPStatusError as e:
                return ResultatTelechargement(
                    doc_id=source.doc_id,
                    erreur=f"HTTP {e.response.status_code}",
                )

        # ── Sécurité taille ───────────────────────────────────────────────────
        if len(contenu) > _MAX_SIZE:
            return ResultatTelechargement(
                doc_id=source.doc_id,
                erreur=f"Fichier trop volumineux : {len(contenu) // 1024 / 1024:.1f} Mo",
            )

        if len(contenu) < 1024:
            return ResultatTelechargement(
                doc_id=source.doc_id,
                erreur=f"Fichier trop petit ({len(contenu)} octets) — probablement une erreur",
            )

        # ── Hash SHA-256 ──────────────────────────────────────────────────────
        nouveau_hash = hashlib.sha256(contenu).hexdigest()

        if nouveau_hash == hash_connu:
            _maj_hash(source.doc_id, nouveau_hash, pdf_url)
            return ResultatTelechargement(
                doc_id=source.doc_id,
                a_change=False,
                hash=nouveau_hash,
                url_utilisee=pdf_url,
            )

        # ── Nouveau contenu ───────────────────────────────────────────────────
        logger.info(
            f"[Downloader] {source.doc_id} — Nouveau contenu détecté "
            f"({len(contenu) // 1024} Ko, hash: {nouveau_hash[:12]}…)"
        )

        # Sauvegarder le PDF brut dans data/rag_knowledge/{doc_id}/source.pdf
        _sauvegarder_pdf_brut(source.doc_id, contenu)
        _maj_hash(source.doc_id, nouveau_hash, pdf_url)

        return ResultatTelechargement(
            doc_id=source.doc_id,
            a_change=True,
            contenu=contenu,
            hash=nouveau_hash,
            url_utilisee=pdf_url,
        )


def _sauvegarder_pdf_brut(doc_id: str, contenu: bytes) -> None:
    """Sauvegarde le PDF brut sur disque pour réingestion future si besoin."""
    try:
        dossier = _RAG_DATA / doc_id
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / "source.pdf").write_bytes(contenu)
    except Exception as e:
        logger.warning(f"[Downloader] Sauvegarde PDF brut {doc_id} échouée : {e}")


def chemin_pdf_brut(doc_id: str) -> Path:
    return _RAG_DATA / doc_id / "source.pdf"


def chemin_json_chunks(doc_id: str) -> Path:
    return _RAG_DATA / doc_id / "chunks.json"


def chemin_embeddings(doc_id: str) -> Path:
    return _RAG_DATA / doc_id / "embeddings.npz"
