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
    Query,
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
)

logger = logging.getLogger("yukpo_assurance.translate_live")
router = APIRouter()


# ─── Statut & référentiel ────────────────────────────────────────────────────

@router.get("/status")
async def status(current_user: TokenData = Depends(get_current_user)) -> dict:
    """Retourne la disponibilité du service et la tarification active."""
    return {
        "stt_available": deepgram_disponible(),
        "translator_available": True,  # GPT-4o-mini via ia_client — toujours dispo si clé OpenAI OK
        "tts_available": False,        # Sprint 2
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
    await websocket.accept()
    session = TranslateLiveSession(
        websocket,
        user_id=user_id,
        user_plan=plan,
        source_lang=source,
        target_lang=target,
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
