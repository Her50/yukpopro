"""
Wrapper Deepgram streaming (Nova-3) pour YukpoTranslate Live.

- Utilise le SDK `deepgram-sdk` si installé (v3), sinon tombe en mode « indisponible ».
- Expose `DeepgramStreamingClient` : une session duplex qui consomme des chunks PCM16
  et appelle un callback async à chaque utterance (interim + final).

Notes :
- Nova-3 supporte `language=multi` → détection automatique à l'utterance.
- Encodage requis : linear16, 16 kHz, mono.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from config.settings import settings

logger = logging.getLogger("yukpo_assurance.translate_live.deepgram")

# Callback : (texte, langue_detectee_iso, is_final) → coroutine
TranscriptCallback = Callable[[str, str, bool], Awaitable[None]]


def deepgram_disponible() -> bool:
    """Retourne True si la clé et le SDK sont disponibles."""
    cle = _cle_deepgram()
    if not cle or len(cle) < 20:
        return False
    try:
        import deepgram  # noqa: F401
        return True
    except ImportError:
        return False


def _cle_deepgram() -> str:
    """Lit la clé depuis settings ou env."""
    cle = getattr(settings, "DEEPGRAM_API_KEY", "") or ""
    return cle.strip()


class DeepgramStreamingClient:
    """
    Session Deepgram Live. Gère une connexion WS sortante vers api.deepgram.com.

    Usage :
        client = DeepgramStreamingClient(on_transcript=..., source_lang='auto', target_lang_hint='en')
        await client.start()
        await client.send_audio(pcm16_bytes)
        ...
        await client.close()

    Si Deepgram indisponible (clé manquante ou SDK absent), `start()` lève
    RuntimeError. L'appelant doit vérifier `deepgram_disponible()` avant.
    """

    def __init__(
        self,
        *,
        on_transcript: TranscriptCallback,
        source_lang: str = "auto",
        sample_rate: int = 16000,
    ):
        self._on_transcript = on_transcript
        self._source_lang = source_lang
        self._sample_rate = sample_rate
        self._dg_connection = None
        self._started = False

    async def start(self) -> None:
        """Ouvre la connexion Deepgram. Lève RuntimeError si indisponible."""
        if not deepgram_disponible():
            raise RuntimeError("Deepgram indisponible (clé DEEPGRAM_API_KEY absente ou SDK non installé)")

        try:
            from deepgram import (
                DeepgramClient,
                LiveOptions,
                LiveTranscriptionEvents,
            )
        except Exception as e:
            raise RuntimeError(f"deepgram-sdk v3+ requis : {e}")

        dg = DeepgramClient(_cle_deepgram())

        # Utiliser la version asynchrone (asyncwebsocket) pour compat event loop FastAPI
        try:
            conn = dg.listen.asyncwebsocket.v("1")
        except AttributeError:
            # Très vieux SDK — fallback sync
            conn = dg.listen.websocket.v("1")

        options_kwargs = dict(
            model="nova-3",
            smart_format=True,
            interim_results=True,
            encoding="linear16",
            sample_rate=self._sample_rate,
            channels=1,
            punctuate=True,
            vad_events=True,
        )
        # Nova-3 supporte language=multi pour auto-detect
        options_kwargs["language"] = "multi" if self._source_lang == "auto" else self._source_lang

        async def _on_message(_self, result, **kwargs):  # pragma: no cover — dépend SDK
            try:
                alt = result.channel.alternatives[0]
                texte = (alt.transcript or "").strip()
                if not texte:
                    return
                is_final = bool(getattr(result, "is_final", False))
                langue = (
                    getattr(result.channel, "detected_language", None)
                    or getattr(result, "language", None)
                    or (self._source_lang if self._source_lang != "auto" else "en")
                )
                await self._on_transcript(texte, str(langue)[:2], is_final)
            except Exception as e:
                logger.warning(f"[Deepgram] parse message: {e}")

        async def _on_error(_self, error, **kwargs):  # pragma: no cover
            logger.warning(f"[Deepgram] erreur : {error}")

        async def _on_close(_self, close, **kwargs):  # pragma: no cover
            logger.info("[Deepgram] connexion fermée")

        conn.on(LiveTranscriptionEvents.Transcript, _on_message)
        conn.on(LiveTranscriptionEvents.Error, _on_error)
        conn.on(LiveTranscriptionEvents.Close, _on_close)

        try:
            ok = await conn.start(LiveOptions(**options_kwargs))
            if not ok:
                raise RuntimeError("conn.start() a retourné False")
        except TypeError:
            # API plus ancienne (sync start)
            ok = conn.start(LiveOptions(**options_kwargs))  # type: ignore
            if not ok:
                raise RuntimeError("conn.start() a retourné False (sync)")

        self._dg_connection = conn
        self._started = True
        logger.info(f"[Deepgram] session ouverte (source={self._source_lang}, sr={self._sample_rate})")

    async def send_audio(self, pcm16: bytes) -> None:
        """Envoie un chunk PCM16 à Deepgram."""
        if not self._started or not self._dg_connection:
            return
        try:
            send = self._dg_connection.send
            res = send(pcm16)
            if asyncio.iscoroutine(res):
                await res
        except Exception as e:
            logger.warning(f"[Deepgram] send audio: {e}")

    async def close(self) -> None:
        if not self._dg_connection:
            return
        try:
            res = self._dg_connection.finish()
            if asyncio.iscoroutine(res):
                await res
        except Exception as e:
            logger.debug(f"[Deepgram] close: {e}")
        self._dg_connection = None
        self._started = False
