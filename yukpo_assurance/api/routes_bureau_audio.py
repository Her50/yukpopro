"""
Bureau Audio — Routes FastAPI pour transcription audio → document.

Endpoints :
  POST /api/v1/bureau/audio/transcrire      — Audio → document formaté (.docx)
  GET  /api/v1/bureau/audio/types           — Types de documents cibles disponibles
  GET  /api/v1/bureau/audio/fichier/{id}    — Télécharge le .docx résultant
"""
import base64
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from core.auth import TokenData, get_current_user

logger = logging.getLogger("yukpo_assurance.api.bureau_audio")
router = APIRouter()

_DATA_DIR = Path(__file__).parent.parent / "data" / "generated" / "bureau"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

_MIME_AUDIO = {
    "audio/mpeg", "audio/mp3", "audio/mp4", "audio/m4a",
    "audio/wav", "audio/wave", "audio/webm", "audio/ogg",
    "audio/x-m4a", "audio/x-wav",
}
_TAILLE_MAX_BYTES = 50 * 1024 * 1024  # 50 Mo


@router.get("/types", tags=["Bureau — Audio"])
async def lister_types_documents():
    """Retourne les types de documents cibles disponibles après transcription."""
    from modules.bureau.transcripteur import TYPES_DOCUMENT_CIBLE
    return {
        "types": [
            {"cle": cle, "label": label}
            for cle, label in TYPES_DOCUMENT_CIBLE.items()
        ]
    }


@router.post("/transcrire", tags=["Bureau — Audio"])
async def transcrire_audio(
    fichier: UploadFile = File(..., description="Fichier audio (MP3/WAV/M4A/WebM/OGG, max 50 Mo)"),
    type_document_cible: str = Form(default="dictee", description="Type de document à produire"),
    pays: str = Form(default="CM", description="Pays/contexte : CM SN CI TG BJ"),
    contexte: Optional[str] = Form(None, description="Contexte JSON : participants, objet réunion, etc."),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Transcrit un enregistrement audio via Whisper puis le reformate en document professionnel via Claude.

    Cas d'usage typiques :
    - Secrétaire dicte une lettre → type_document_cible=lettre
    - Réunion enregistrée → type_document_cible=pv_reunion
    - Notes vocales → type_document_cible=dictee ou liste_taches
    """
    from modules.bureau.transcripteur import transcrire_audio as _transcrire, TYPES_DOCUMENT_CIBLE
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde, debiter_forfait, debiter_llm,
    )
    import json as json_lib

    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "audio")
    if not autorise:
        raise HTTPException(403, msg)
    ok_solde, restants, _ = await verifier_solde(current_user.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")

    if type_document_cible not in TYPES_DOCUMENT_CIBLE:
        raise HTTPException(
            status_code=400,
            detail=f"Type invalide. Disponibles : {list(TYPES_DOCUMENT_CIBLE.keys())}",
        )

    # Validation audio — on accepte aussi application/octet-stream (certains navigateurs)
    content_type = fichier.content_type or ""
    if content_type not in _MIME_AUDIO and content_type != "application/octet-stream":
        # Vérification par extension comme fallback
        ext = Path(fichier.filename or "").suffix.lower()
        from modules.bureau.transcripteur import FORMATS_AUDIO_ACCEPTES
        if ext not in FORMATS_AUDIO_ACCEPTES:
            raise HTTPException(
                status_code=400,
                detail=f"Format audio non supporté : {content_type}. Acceptés : MP3, WAV, M4A, WebM, OGG",
            )

    contenu = await fichier.read()
    if len(contenu) > _TAILLE_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Fichier audio trop grand (max 50 Mo)")

    # Parse contexte JSON optionnel
    informations_contexte = None
    if contexte:
        try:
            informations_contexte = json_lib.loads(contexte)
        except json_lib.JSONDecodeError:
            informations_contexte = {"notes": contexte}

    try:
        resultat = await _transcrire(
            audio_bytes=contenu,
            nom_fichier=fichier.filename or f"audio.{(fichier.content_type or 'audio/wav').split('/')[-1]}",
            type_document_cible=type_document_cible,
            pays=pays,
            informations_contexte=informations_contexte,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error(f"[Bureau Audio] Transcription échouée : {e}")
        raise HTTPException(status_code=500, detail=f"Transcription échouée : {e}")

    fichier_id = None
    word_b64 = None
    if resultat.contenu_word:
        fichier_id = f"bureau_audio_{current_user.user_id}_{int(__import__('time').time())}.docx"
        (_DATA_DIR / fichier_id).write_bytes(resultat.contenu_word)
        word_b64 = base64.b64encode(resultat.contenu_word).decode()

    # Débit crédits : forfait par minute audio + LLM reformatage + DOCX
    try:
        duree_min = max(1.0, (resultat.duree_secondes or 0) / 60.0)
        await debiter_forfait(
            current_user.user_id, "audio_transcription",
            module="audio", multiplicateur=duree_min,
        )
        meta = resultat.meta or {}
        if meta.get("tokens_input") or meta.get("tokens_output"):
            await debiter_llm(
                current_user.user_id,
                modele=meta.get("modele", "default"),
                tokens_input=int(meta.get("tokens_input", 0) or 0),
                tokens_output=int(meta.get("tokens_output", 0) or 0),
                module="audio",
            )
        if resultat.contenu_word:
            await debiter_forfait(current_user.user_id, "docx_generation", module="audio")
    except Exception as _e:
        logger.warning(f"[Bureau/Crédits] Debit audio échoué : {_e}")

    return {
        "transcription_brute": resultat.transcription_brute,
        "document_formate": resultat.document_formate,
        "type_document": resultat.type_document,
        "langue_detectee": resultat.langue_detectee,
        "duree_secondes": resultat.duree_secondes,
        "a_fichier_word": bool(resultat.contenu_word),
        "fichier_id": fichier_id,
        "word_base64": word_b64,
        "meta": resultat.meta,
    }


@router.get("/fichier/{fichier_id}", tags=["Bureau — Audio"])
async def telecharger_audio_doc(
    fichier_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Télécharge le document Word généré après transcription audio."""
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
