"""
YukpoTranslate Live — Endpoints HTTP + WebSocket.

Routes :
  GET  /api/v1/translate/live/status   — disponibilité, tarif
  GET  /api/v1/translate/live/langues  — liste ISO 639-1 supportées
  WS   /api/v1/translate/live/ws       — flux audio PCM16 → sous-titres bilingues

Auth WS : JWT via query param `?token=<jwt>` (convention déjà utilisée dans
`routes_collaboration.websocket_endpoint`, les navigateurs n'exposent pas
les headers aux WebSockets).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)

from core.auth import TokenData, _decoder_token, get_current_user
from modules.translate_live import (
    CREDITS_PAR_MINUTE,
    COUT_FCFA_PAR_MINUTE,
    LANGUES_SUPPORTEES,
    TranslateLiveSession,
    deepgram_disponible,
    traduire_texte,
)
from modules.translate_live.languages import normaliser_code_langue

logger = logging.getLogger("yukpo_assurance.translate_live")
router = APIRouter()


# ─── Statut & référentiel ────────────────────────────────────────────────────

@router.get("/status")
async def status(current_user: TokenData = Depends(get_current_user)) -> dict:
    """Retourne la disponibilité du service et la tarification active."""
    return {
        "stt_available": deepgram_disponible(),
        "translator_available": True,  # GPT-4o-mini via ia_client — toujours dispo si clé OpenAI OK
        "tts_available": bool(getattr(__import__("config.settings", fromlist=["settings"]).settings, "ELEVENLABS_API_KEY", "")),
        "price_per_minute_fcfa": COUT_FCFA_PAR_MINUTE,
        "price_per_minute_credits": CREDITS_PAR_MINUTE,
    }


@router.get("/langues")
async def liste_langues(current_user: TokenData = Depends(get_current_user)) -> dict:
    """Liste des langues supportées (ISO 639-1)."""
    return {"langues": LANGUES_SUPPORTEES}


# ─── WebSocket streaming ─────────────────────────────────────────────────────

@router.websocket("/ws")
async def websocket_translate_live(
    websocket: WebSocket,
    token: Optional[str] = Query(None, description="JWT utilisateur"),
    source: str = Query("auto", description="Code ISO 639-1 langue source ou 'auto'"),
    target: str = Query("fr", description="Code ISO 639-1 langue cible"),
):
    """
    Flux audio PCM16 16 kHz mono → sous-titres bilingues temps réel.

    Protocole (voir docs/translate_live_spec.md §3) :
      Client → serveur : frames binaires PCM16 + JSON de contrôle (`config`, `stop`, `ping`).
      Serveur → client : messages JSON `ready`, `transcript`, `translation`, `usage`, `error`, `pong`.
    """
    # Auth
    if not token:
        await websocket.close(code=4001)
        return
    try:
        td = _decoder_token(token)
    except Exception:
        await websocket.close(code=4001)
        return

    user_id = td.user_id

    # Récupérer le plan utilisateur pour plafond mensuel
    plan = "gratuit"
    try:
        from core.database import async_session_maker
        from modules.pro.service_credits import get_ou_creer_credits
        from modules.pro.service_profil import get_or_create as _get_profil
        async with async_session_maker() as db:
            try:
                profil, _ = await _get_profil(user_id, db)
                plan = (profil.preferences or {}).get("plan") or "gratuit"
            except Exception:
                pass
            try:
                credit = await get_ou_creer_credits(user_id, db)
                if credit.plan and credit.plan != "gratuit":
                    plan = credit.plan
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"[TranslateLive] plan par défaut gratuit (err : {e})")

    # Pré-check crédits
    try:
        from modules.pro.service_credits import verifier_solde_suffisant
        ok, restants, _plan, _msg = await verifier_solde_suffisant(user_id)
        if not ok:
            await websocket.accept()
            await websocket.send_json({
                "type": "error",
                "code": "credits_epuises",
                "message": f"Crédits épuisés ({int(restants)}). Rechargez pour utiliser la traduction live.",
            })
            await websocket.close(code=4002)
            return
    except Exception:
        pass  # Ne jamais bloquer en cas d'erreur DB

    # Accept + run session
    from config.settings import settings
    await websocket.accept()
    session = TranslateLiveSession(
        websocket,
        user_id=user_id,
        user_plan=plan,
        source_lang=source,
        target_lang=target,
        elevenlabs_key=settings.ELEVENLABS_API_KEY,
    )
    try:
        await session.run()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception(f"[TranslateLive] run: {e}")
        try:
            await websocket.close(code=4100)
        except Exception:
            pass


# ─── Endpoint batch (mobile : envoi de chunks audio via REST) ──────────────

@router.post("/chunk")
async def traduire_chunk_audio(
    audio: UploadFile = File(..., description="Chunk audio (m4a, mp4, wav, webm, ogg, 2-10s)"),
    source: str = Form("auto", description="ISO 639-1 ou 'auto'"),
    target: str = Form("fr", description="ISO 639-1 langue cible"),
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """
    Transcription + traduction d'un chunk audio court (mobile friendly).
    Contrairement au WebSocket, cet endpoint :
      - accepte des formats compressés (M4A, WebM…)
      - ne facture qu'en fin de traitement (durée du chunk)
      - convient aux apps Expo/React Native qui ne peuvent streamer PCM raw
    Retourne : {transcript, translation, source_lang, target_lang, duration_s}
    """
    from modules.pro.service_credits import (
        debiter_forfait_fcfa,
        verifier_solde_suffisant,
    )

    ok, _restants, _plan, msg = await verifier_solde_suffisant(current_user.user_id)
    if not ok:
        raise HTTPException(status_code=402, detail=msg)

    contenu = await audio.read()
    if len(contenu) < 500:
        raise HTTPException(status_code=400, detail="Chunk audio trop court ou vide")
    if len(contenu) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Chunk audio trop volumineux (max 8 MB / ~30s)")

    src = normaliser_code_langue(source, "auto")
    tgt = normaliser_code_langue(target, "fr")

    # 1. Transcription via Deepgram (prerecorded API — gère M4A/WebM natif)
    transcript_text = ""
    detected_lang = src
    duration_s = 0.0
    if deepgram_disponible():
        try:
            from deepgram import DeepgramClient, PrerecordedOptions, FileSource
            from config.settings import settings

            client = DeepgramClient(settings.DEEPGRAM_API_KEY)
            payload: FileSource = {"buffer": contenu}
            options = PrerecordedOptions(
                model="nova-3",
                smart_format=True,
                punctuate=True,
                language="multi" if src == "auto" else src,
                detect_language=(src == "auto"),
            )
            resp = await client.listen.asyncrest.v("1").transcribe_file(payload, options)
            if resp and resp.results:
                channel = resp.results.channels[0] if resp.results.channels else None
                if channel and channel.alternatives:
                    transcript_text = channel.alternatives[0].transcript or ""
                    detected = getattr(channel, "detected_language", None)
                    if detected:
                        detected_lang = normaliser_code_langue(detected, src)
                if resp.metadata:
                    duration_s = float(getattr(resp.metadata, "duration", 0.0) or 0.0)
        except Exception as e:
            logger.warning(f"[TranslateLive/chunk] Deepgram échec : {e}")

    # 2. Traduction si langue différente
    translation_text = transcript_text
    if transcript_text.strip() and detected_lang != tgt:
        try:
            translation_text = await traduire_texte(
                transcript_text, source_lang=detected_lang, target_lang=tgt,
            )
        except Exception as e:
            logger.warning(f"[TranslateLive/chunk] traduction échouée : {e}")

    # 3. Facturation proportionnelle à la durée
    if duration_s <= 0 and transcript_text:
        # Fallback : ~0.6s par mot transcrit
        duration_s = max(1.0, len(transcript_text.split()) * 0.6)
    minutes = max(0.1, round(duration_s / 60.0, 2))
    try:
        await debiter_forfait_fcfa(
            user_id=current_user.user_id,
            cout_fcfa=COUT_FCFA_PAR_MINUTE * minutes,
            module="translate_live_chunk",
        )
    except Exception as e:
        logger.debug(f"[TranslateLive/chunk] débit non bloquant : {e}")

    return {
        "transcript": transcript_text,
        "translation": translation_text,
        "source_lang": detected_lang,
        "target_lang": tgt,
        "duration_s": round(duration_s, 2),
        "credits_debited": int(CREDITS_PAR_MINUTE * minutes),
    }
