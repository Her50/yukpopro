"""
YukpoAssurance — OCR batch pour PDF scannés (multi-pages via Claude Vision)

Stratégie :
1. Tente extraction texte native (pdfplumber/PyPDF2). Si texte suffisant → renvoyé tel quel.
2. Sinon, rastérise chaque page en PNG (PyMuPDF / pdf2image) et envoie par lots
   parallèles à Claude Vision (lots de 20 pages, max 4 lots concurrents).
3. Concatène les textes par page dans l'ordre.

Utilisé par :
  - routes_documents.traduire-fichier (préextraction avant traduction)
  - routes_pro_generateurs.analyser-et-generer (extraction rapport source)
  - routes_bureau_ocr
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
from typing import Optional

logger = logging.getLogger("yukpo_assurance.pdf_ocr_batch")

# Seuil en caractères / page en dessous duquel on considère le PDF scanné
_SEUIL_TEXTE_PAR_PAGE = 50

# Concurrence par défaut : 4 lots de 20 pages simultanés → 80 pages en vol
_BATCH_PAGES = 20
_PARALLEL_BATCHES = 4


def _extraire_texte_natif(contenu: bytes) -> tuple[str, int]:
    """Extraction texte native — retourne (texte_total, nb_pages)."""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(contenu)) as pdf:
            pages_txt = [(p.extract_text() or "") for p in pdf.pages]
            return "\n\n".join(pages_txt), len(pages_txt)
    except Exception:
        pass
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(contenu))
        pages_txt = [(p.extract_text() or "") for p in reader.pages]
        return "\n\n".join(pages_txt), len(pages_txt)
    except Exception:
        return "", 0


def _rasteriser_pages(contenu: bytes, dpi: int = 180) -> list[bytes]:
    """Convertit chaque page PDF en PNG bytes. Essaie PyMuPDF d'abord, puis pdf2image."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=contenu, filetype="pdf")
        images: list[bytes] = []
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        for page in doc:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            images.append(pix.tobytes("png"))
        doc.close()
        return images
    except Exception as e_mupdf:
        logger.debug(f"[pdf_ocr_batch] PyMuPDF indisponible ({e_mupdf}) — fallback pdf2image")
    try:
        from pdf2image import convert_from_bytes
        pages_pil = convert_from_bytes(contenu, dpi=dpi, fmt="png")
        out: list[bytes] = []
        for img in pages_pil:
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            out.append(buf.getvalue())
        return out
    except Exception as e_pdf2img:
        logger.error(f"[pdf_ocr_batch] Rasterisation impossible: {e_pdf2img}")
        return []


async def _ocr_une_page(image_png: bytes, num_page: int) -> tuple[int, str]:
    """Appel Claude Vision pour une page."""
    from core.ia_client import ia_client, ModeIA

    b64 = base64.standard_b64encode(image_png).decode("utf-8")
    try:
        reponse = await ia_client.analyser_image_vision(
            image_b64=b64,
            prompt=(
                "Extrais TOUT le texte visible de cette page de document. "
                "Préserve la mise en page, les tableaux (format Markdown), les titres et les listes. "
                "Retourne uniquement le texte extrait, sans commentaire."
            ),
            mode=ModeIA.PRECISION,
        )
        return num_page, (reponse.contenu or "").strip()
    except Exception as e:
        logger.warning(f"[pdf_ocr_batch] Page {num_page + 1} OCR échec: {e}")
        return num_page, ""


async def _ocr_batch(pages_png: list[bytes]) -> str:
    """Lance l'OCR sur toutes les pages en parallèle contrôlé."""
    sema = asyncio.Semaphore(_BATCH_PAGES * _PARALLEL_BATCHES)

    async def _run(i: int, img: bytes) -> tuple[int, str]:
        async with sema:
            return await _ocr_une_page(img, i)

    logger.info(f"[pdf_ocr_batch] OCR Claude Vision sur {len(pages_png)} pages")
    resultats = await asyncio.gather(*[_run(i, img) for i, img in enumerate(pages_png)])
    resultats.sort(key=lambda x: x[0])
    return "\n\n".join(texte for _, texte in resultats if texte)


async def extraire_texte_pdf(
    contenu: bytes,
    *,
    forcer_ocr: bool = False,
    seuil_texte_par_page: int = _SEUIL_TEXTE_PAR_PAGE,
    user_id: Optional[int] = None,
    module: str = "pdf_ocr_batch",
) -> str:
    """
    Point d'entrée unique : extrait le texte d'un PDF en choisissant automatiquement
    entre extraction native et OCR Claude Vision selon la qualité du texte natif.

    Args:
        contenu: bytes du PDF
        forcer_ocr: si True, saute l'extraction native et fait directement OCR
        seuil_texte_par_page: caractères minimum/page pour considérer le texte exploitable
        user_id: si fourni, débite les crédits Yukpo pour chaque page OCR (marge 20×)
        module: label pour le journal de consommation

    Returns:
        Texte extrait (concaténation des pages).
    """
    if not forcer_ocr:
        texte_natif, nb_pages = _extraire_texte_natif(contenu)
        if nb_pages > 0:
            moyenne_chars = len(texte_natif) / nb_pages
            if moyenne_chars >= seuil_texte_par_page:
                logger.info(
                    f"[pdf_ocr_batch] Extraction native OK — {nb_pages} pages, "
                    f"{moyenne_chars:.0f} chars/page"
                )
                return texte_natif
            logger.info(
                f"[pdf_ocr_batch] Extraction native faible ({moyenne_chars:.0f} chars/page) "
                f"→ bascule OCR Claude Vision"
            )

    # OCR Claude Vision par pages
    pages_png = _rasteriser_pages(contenu)
    if not pages_png:
        raise RuntimeError(
            "Impossible de rasteriser le PDF. Installez PyMuPDF (pip install pymupdf) "
            "ou pdf2image + poppler."
        )

    # Pré-check crédits avant d'engager un batch OCR potentiellement coûteux
    if user_id is not None:
        try:
            from modules.pro.service_credits import verifier_solde_suffisant
            ok, _r, _p, msg = await verifier_solde_suffisant(user_id)
            if not ok:
                raise RuntimeError(msg)   # relayé en 402 par la couche route
        except RuntimeError:
            raise
        except Exception as _e:
            logger.debug(f"[pdf_ocr_batch] pré-check crédits non bloquant: {_e}")

    texte = await _ocr_batch(pages_png)

    # Débit LLM à la page (chaque page = 1 appel Claude Vision)
    if user_id is not None:
        try:
            from modules.pro.service_credits import verifier_et_debiter
            nb = len(pages_png)
            await verifier_et_debiter(
                user_id=user_id,
                modele="claude-sonnet-4-6",
                tokens_input=1500 * nb,
                tokens_output=800 * nb,
                module=module,
            )
        except Exception as _e:
            logger.warning(f"[pdf_ocr_batch] Débit crédits échoué: {_e}")

    return texte
