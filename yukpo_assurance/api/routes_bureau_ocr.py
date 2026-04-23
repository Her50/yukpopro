"""
Bureau OCR — Routes FastAPI pour scan et numérisation.

Endpoints :
  POST /api/v1/bureau/ocr/scanner          — Image → texte structuré + .docx
  POST /api/v1/bureau/ocr/manuscrit        — Notes manuscrites → document formaté
  GET  /api/v1/bureau/ocr/fichier/{id}     — Télécharge le .docx résultant
"""
import base64
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from core.auth import TokenData, get_current_user

logger = logging.getLogger("yukpo_assurance.api.bureau_ocr")
router = APIRouter()

_DATA_DIR = Path(__file__).parent.parent / "data" / "generated" / "bureau"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

_MIME_AUTORISES = {
    "image/jpeg", "image/jpg", "image/png", "image/tiff",
    "image/webp", "image/bmp",
}
_TAILLE_MAX_BYTES = 20 * 1024 * 1024  # 20 Mo


def _valider_upload(file: UploadFile) -> None:
    if file.content_type not in _MIME_AUTORISES:
        raise HTTPException(
            status_code=400,
            detail=f"Format non supporté : {file.content_type}. Acceptés : JPG, PNG, TIFF, WEBP, BMP",
        )


@router.post("/scanner", tags=["Bureau — OCR"])
async def scanner_image(
    fichier: UploadFile = File(..., description="Image à numériser (JPG/PNG/TIFF/WEBP)"),
    type_attendu: Optional[str] = Form(None, description="lettre | formulaire | recu | manuscrit | tableau"),
    export_word: bool = Form(True),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Numérise une image (scan, photo) et extrait le texte structuré.
    Retourne le texte en Markdown + (optionnel) .docx en base64.
    """
    from modules.bureau.ocr_scanner import scanner_image as _scanner
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde, debiter_forfait,
    )

    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "ocr")
    if not autorise:
        raise HTTPException(403, msg)
    ok_solde, restants, _ = await verifier_solde(current_user.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")

    _valider_upload(fichier)
    contenu = await fichier.read()
    if len(contenu) > _TAILLE_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Image trop grande (max 20 Mo)")

    try:
        resultat = await _scanner(
            image_bytes=contenu,
            mime=fichier.content_type,
            type_attendu=type_attendu,
            export_word=export_word,
        )
    except Exception as e:
        logger.error(f"[Bureau OCR] Scan échoué : {e}")
        raise HTTPException(status_code=500, detail=f"OCR échoué : {e}")

    try:
        await debiter_forfait(current_user.user_id, "ocr_scan", module="ocr")
        if resultat.contenu_word:
            await debiter_forfait(current_user.user_id, "docx_generation", module="ocr")
    except Exception as _e:
        logger.warning(f"[Bureau/Crédits] Debit OCR échoué : {_e}")

    fichier_id = None
    word_b64 = None
    if resultat.contenu_word:
        fichier_id = f"bureau_ocr_{current_user.user_id}_{int(__import__('time').time())}.docx"
        (_DATA_DIR / fichier_id).write_bytes(resultat.contenu_word)
        word_b64 = base64.b64encode(resultat.contenu_word).decode()

    return {
        "texte_brut": resultat.texte_brut,
        "texte_structure": resultat.texte_structure,
        "type_document": resultat.type_document,
        "confiance": resultat.confiance,
        "a_fichier_word": bool(resultat.contenu_word),
        "fichier_id": fichier_id,
        "word_base64": word_b64,
        "meta": resultat.meta,
    }


@router.post("/manuscrit", tags=["Bureau — OCR"])
async def scanner_manuscrit(
    fichier: UploadFile = File(..., description="Photo de notes manuscrites"),
    formater_en: str = Form(default="paragraphe", description="lettre | rapport | liste | paragraphe"),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Lit des notes manuscrites (écriture cursive africaine) et les formate en document propre.
    """
    from modules.bureau.ocr_scanner import scanner_notes_manuscrites
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde, debiter_forfait,
    )

    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "ocr")
    if not autorise:
        raise HTTPException(403, msg)
    ok_solde, restants, _ = await verifier_solde(current_user.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")

    _valider_upload(fichier)
    contenu = await fichier.read()
    if len(contenu) > _TAILLE_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Image trop grande (max 20 Mo)")

    formats_valides = {"lettre", "rapport", "liste", "paragraphe"}
    if formater_en not in formats_valides:
        raise HTTPException(status_code=400, detail=f"Format invalide. Valides : {formats_valides}")

    try:
        resultat = await scanner_notes_manuscrites(
            image_bytes=contenu,
            mime=fichier.content_type,
            formater_en=formater_en,
        )
    except Exception as e:
        logger.error(f"[Bureau OCR Manuscrit] Erreur : {e}")
        raise HTTPException(status_code=500, detail=str(e))

    try:
        await debiter_forfait(current_user.user_id, "ocr_manuscrit", module="ocr")
        if resultat.contenu_word:
            await debiter_forfait(current_user.user_id, "docx_generation", module="ocr")
    except Exception as _e:
        logger.warning(f"[Bureau/Crédits] Debit OCR manuscrit échoué : {_e}")

    fichier_id = None
    word_b64 = None
    if resultat.contenu_word:
        fichier_id = f"bureau_manuscrit_{current_user.user_id}_{int(__import__('time').time())}.docx"
        (_DATA_DIR / fichier_id).write_bytes(resultat.contenu_word)
        word_b64 = base64.b64encode(resultat.contenu_word).decode()

    return {
        "texte_structure": resultat.texte_structure,
        "type_document": "manuscrit",
        "confiance": resultat.confiance,
        "a_fichier_word": bool(resultat.contenu_word),
        "fichier_id": fichier_id,
        "word_base64": word_b64,
    }


@router.get("/fichier/{fichier_id}", tags=["Bureau — OCR"])
async def telecharger_ocr(
    fichier_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Télécharge un document Word généré après OCR."""
    if "/" in fichier_id or "\\" in fichier_id or ".." in fichier_id:
        raise HTTPException(status_code=400, detail="Nom de fichier invalide")

    chemin = _DATA_DIR / fichier_id
    if not chemin.exists():
        raise HTTPException(status_code=404, detail="Fichier introuvable")

    if f"_{current_user.user_id}_" not in fichier_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Accès refusé")

    return Response(
        content=chemin.read_bytes(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{fichier_id}"'},
    )
