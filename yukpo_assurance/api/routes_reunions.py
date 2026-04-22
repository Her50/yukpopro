"""Routes Réunions — gestion complète, transcription, PV, agenda"""
from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from typing import Optional
import base64

from modules.reunions.gestionnaire import gestionnaire_reunions
from core.auth import TokenData, get_current_user, require_permission

WHISPER_MAX_BYTES = 24 * 1024 * 1024  # 24 MB safety margin (Whisper limit is 25 MB)


async def _transcrire_chunks(
    contenu: bytes,
    nom_fichier: str,
    mime: str,
    client_oai,
    langue: str = "auto",
) -> str:
    """Transcrit en chunks ≤ 24 MB si nécessaire, concatène les parties."""
    ext = nom_fichier.rsplit(".", 1)[-1] if "." in nom_fichier else "m4a"
    parties: list[str] = []
    offset = 0
    idx = 0

    while offset < len(contenu):
        chunk = contenu[offset: offset + WHISPER_MAX_BYTES]
        offset += WHISPER_MAX_BYTES
        idx += 1
        nom_chunk = f"chunk_{idx:02d}.{ext}"
        kwargs: dict = {
            "model": "whisper-1",
            "file": (nom_chunk, chunk, mime),
            "response_format": "text",
        }
        if langue and langue != "auto":
            kwargs["language"] = langue
        resp = await client_oai.audio.transcriptions.create(**kwargs)
        texte = str(resp).strip()
        if texte:
            parties.append(texte)

    return "\n".join(parties)

router = APIRouter(dependencies=[Depends(require_permission("reunions"))])


class NouvelleReunionRequest(BaseModel):
    titre: str
    type_reunion: str = "ordinaire"
    ordre_du_jour: list[str] = []
    participants: list[dict] = []
    lieu: str = ""
    president_seance: str = ""


class NotesRequest(BaseModel):
    notes: str


class MajActionRequest(BaseModel):
    index_action: int
    nouveau_statut: str  # "en_attente" | "en_cours" | "réalisé" | "reporté"


@router.post("/")
async def creer_reunion(req: NouvelleReunionRequest):
    """Crée une nouvelle réunion avec son ordre du jour"""
    reunion = gestionnaire_reunions.creer_reunion(
        titre=req.titre,
        type_reunion=req.type_reunion,
        ordre_du_jour=req.ordre_du_jour,
        participants=req.participants,
        lieu=req.lieu,
        president_seance=req.president_seance,
    )
    return {
        "reunion_id": reunion.reunion_id,
        "titre": reunion.titre,
        "date": reunion.date_reunion.isoformat(),
        "type": reunion.type_reunion,
        "nb_participants": len(reunion.participants),
        "ordre_du_jour": reunion.ordre_du_jour,
    }


@router.get("/")
async def lister_reunions(skip: int = 0, limit: int = 50):
    """Liste toutes les réunions (paginée)"""
    toutes = gestionnaire_reunions.lister_reunions()
    return {"total": len(toutes), "skip": skip, "limit": limit, "reunions": toutes[skip:skip + limit]}


# IMPORTANT : cette route statique doit être déclarée AVANT /{reunion_id}
@router.get("/actions/tableau")
async def tableau_actions():
    """Vue consolidée de toutes les actions en cours (toutes réunions)"""
    return gestionnaire_reunions.tableau_actions()


@router.get("/{reunion_id}")
async def get_reunion(reunion_id: str):
    """Détail d'une réunion"""
    reunion = gestionnaire_reunions.get_reunion(reunion_id)
    if not reunion:
        raise HTTPException(404, "Réunion introuvable")
    return {
        "reunion_id": reunion.reunion_id,
        "titre": reunion.titre,
        "date": reunion.date_reunion.isoformat(),
        "statut": reunion.statut,
        "synthese": reunion.synthese,
        "decisions": reunion.decisions,
        "actions": [
            {
                "responsable": a.responsable,
                "description": a.description,
                "echeance": a.echeance.isoformat() if a.echeance else None,
                "statut": a.statut,
                "priorite": a.priorite,
            }
            for a in reunion.actions
        ],
        "points_reportes": reunion.points_reportes,
    }


@router.post("/{reunion_id}/notes")
async def ajouter_notes(reunion_id: str, req: NotesRequest):
    """Ajoute des notes manuelles à une réunion"""
    reunion = gestionnaire_reunions.get_reunion(reunion_id)
    if not reunion:
        raise HTTPException(404, "Réunion introuvable")
    reunion.notes_manuelles = req.notes
    return {"reunion_id": reunion_id, "notes_enregistrees": True}


@router.post("/transcrire-direct", summary="Transcription audio directe (sans réunion_id)")
async def transcrire_direct(
    audio: UploadFile = File(...),
    langue: str = Form("auto"),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Transcrit directement un fichier audio sans avoir besoin d'un reunion_id.
    Utilisé par la page Réunions pour la transcription en temps réel.
    Langues supportées : auto (détection auto), fr, en, ar, sw, pt, es, de, zh, ...
    """
    contenu = await audio.read()
    taille_mb = len(contenu) / (1024 * 1024)
    mime = audio.content_type or "audio/webm"
    nom_fichier = audio.filename or f"enregistrement.{mime.split('/')[-1]}"

    try:
        from config.settings import settings
        import openai

        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        texte = await _transcrire_chunks(contenu, nom_fichier, mime, client, langue)

        # Débit Whisper : ~3.6 FCFA/min, 1 MB ≈ 1 min (M4A/MP3 128 kbps)
        import asyncio as _asyncio
        from modules.pro.service_credits import debiter_forfait_fcfa as _debiter
        _asyncio.create_task(_debiter(current_user.user_id, max(1.0, taille_mb * 3.6), "whisper_transcription"))

        return {
            "transcription": texte,
            "longueur": len(texte),
            "langue_demandee": langue,
        }
    except Exception as e:
        # Fallback IA : si Whisper indisponible, utiliser Claude pour transcription approximative
        raise HTTPException(500, f"Erreur transcription Whisper: {str(e)[:200]}")


@router.post("/{reunion_id}/transcrire-audio")
async def transcrire_audio(
    reunion_id: str,
    audio: UploadFile = File(...),
    langue: str = Query("auto", description="Langue : auto, fr, en, ar, sw, pt, ..."),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Transcrit l'enregistrement audio d'une réunion via Whisper.
    Formats acceptés : mp3, mp4, wav, m4a, webm.
    """
    reunion = gestionnaire_reunions.get_reunion(reunion_id)
    if not reunion:
        raise HTTPException(404, "Réunion introuvable")

    contenu = await audio.read()
    taille_mb = len(contenu) / (1024 * 1024)
    audio_b64 = base64.standard_b64encode(contenu).decode()
    mime = audio.content_type or "audio/mp4"

    try:
        from config.settings import settings
        import openai

        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        nom_fichier = f"reunion_{reunion_id}.{mime.split('/')[-1]}"
        texte = await _transcrire_chunks(contenu, nom_fichier, mime, client, langue)

        import asyncio as _asyncio
        from modules.pro.service_credits import debiter_forfait_fcfa as _debiter
        _asyncio.create_task(_debiter(current_user.user_id, max(1.0, taille_mb * 3.6), "whisper_transcription"))

        reunion.transcription_brute = texte
        reunion.audio_b64 = audio_b64

        return {
            "reunion_id": reunion_id,
            "transcription": texte,
            "longueur": len(texte),
        }
    except Exception as e:
        raise HTTPException(500, f"Erreur transcription: {str(e)}")


@router.post("/{reunion_id}/analyser")
async def analyser_reunion(reunion_id: str):
    """
    Analyse complète de la réunion par IA :
    synthèse, décisions, actions, points reportés.
    Requiert : transcription audio OU notes manuelles.
    """
    try:
        return await gestionnaire_reunions.analyser_reunion(reunion_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur analyse: {str(e)}")


@router.post("/{reunion_id}/pv")
async def generer_pv(reunion_id: str, format: str = "docx"):
    """
    Génère le procès-verbal officiel de la réunion.
    Formats : docx (Word) ou pdf.
    Requiert : réunion analysée.
    """
    try:
        doc = await gestionnaire_reunions.generer_pv(reunion_id, format)
        if not doc:
            raise HTTPException(500, "Échec génération PV")
        return doc
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{reunion_id}/agenda-prochain")
async def agenda_prochain(reunion_id: str):
    """
    Propose l'agenda de la prochaine réunion basé sur :
    - Points reportés de cette réunion
    - Actions urgentes en attente
    - Échéances réglementaires CIMA
    """
    try:
        return await gestionnaire_reunions.proposer_agenda_prochain(reunion_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.patch("/{reunion_id}/actions")
async def mettre_a_jour_action(reunion_id: str, req: MajActionRequest):
    """Met à jour le statut d'une action"""
    succes = gestionnaire_reunions.mettre_a_jour_action(
        reunion_id=reunion_id,
        index_action=req.index_action,
        nouveau_statut=req.nouveau_statut,
    )
    if not succes:
        raise HTTPException(400, "Action introuvable ou index invalide")
    return {"succes": True, "nouveau_statut": req.nouveau_statut}
