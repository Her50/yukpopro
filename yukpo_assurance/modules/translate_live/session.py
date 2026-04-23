"""
Orchestrateur de session WebSocket pour YukpoTranslate Live.

Une session = une connexion WS cliente. Gère :
  - la connexion Deepgram STT (ou fallback si indisponible)
  - la traduction de chaque utterance finale via `translator.traduire_texte`
  - la facturation à la minute (via `service_credits.debiter_forfait_fcfa`)
  - le changement dynamique de langue cible / source
  - les clôtures propres (client stop, crédits épuisés, erreur upstream)

Protocole : voir docs/translate_live_spec.md.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect

from modules.translate_live.deepgram_client import (
    DeepgramStreamingClient,
    deepgram_disponible,
)
from modules.translate_live.translator import traduire_texte
from modules.translate_live.languages import normaliser_code_langue
from modules.translate_live.gender_detector import GenderBuffer
from modules.translate_live.elevenlabs_tts import (
    synthesize as elevenlabs_synthesize,
    elevenlabs_disponible,
    COUT_FCFA_PAR_UTTERANCE as EL_COUT_FCFA,
)

logger = logging.getLogger("yukpo_assurance.translate_live.session")

# ── Tarification ──────────────────────────────────────────────────────────────
# Coût Deepgram + GPT-4o-mini (cf. docs/translate_live_business.md) ≈ 168 FCFA/h
# = 2.8 FCFA/min. Avec marge Yukpo ×20 ça ferait 56 crédits/min — on arrondit
# à 120 pour absorber pics (TTS futur, latence Deepgram haut volume, infra).
COUT_FCFA_PAR_MINUTE: float = 6.0
CREDITS_PAR_MINUTE: int = 120

# Plafonds durs par plan (protection anti-abus, cf. business doc §4)
PLAFOND_MINUTES_PAR_MOIS: dict[str, int] = {
    "gratuit":  15,
    "starter":  60,
    "pro":      600,
    "business": 10_000,
}

# Sessions actives par user_id (anti-abus 2 sessions max)
_sessions_actives: dict[int, int] = {}
_MAX_SESSIONS_PAR_USER = 2


@dataclass
class _EtatSession:
    session_id: str
    user_id: int
    source_lang: str = "auto"
    target_lang: str = "fr"
    debut_ts: float = field(default_factory=time.monotonic)
    minutes_streamees: float = 0.0
    minutes_facturees: float = 0.0
    actif: bool = True


class TranslateLiveSession:
    """
    Orchestre une connexion WS client. Méthode d'entrée : `run()`.
    """

    def __init__(
        self,
        websocket: WebSocket,
        *,
        user_id: int,
        user_plan: str = "gratuit",
        source_lang: str = "auto",
        target_lang: str = "fr",
        elevenlabs_key: str = "",
    ):
        self.ws = websocket
        self.etat = _EtatSession(
            session_id=str(uuid.uuid4()),
            user_id=user_id,
            source_lang=normaliser_code_langue(source_lang, "auto"),
            target_lang=normaliser_code_langue(target_lang, "fr"),
        )
        self.user_plan = (user_plan or "gratuit").lower()
        self._dg: Optional[DeepgramStreamingClient] = None
        self._tache_facturation: Optional[asyncio.Task] = None
        self._derniere_utterance_id = 0
        self._el_key = elevenlabs_key
        self._gender_buf = GenderBuffer()
        self._current_gender: str = "female"  # défaut jusqu'à première détection
        # Compteur de traductions effectives dans le cycle de facturation courant.
        # 0 → marge 5× (STT-only) ; >0 → marge 20× (traduction effective).
        self._traductions_ce_cycle: int = 0

    # ── API publique ──────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Boucle principale de la session. Gère le cycle de vie complet."""
        user_id = self.etat.user_id

        # Anti-abus : limite sessions simultanées
        count = _sessions_actives.get(user_id, 0)
        if count >= _MAX_SESSIONS_PAR_USER:
            logger.info(f"[TranslateLive] user={user_id} — 2 sessions déjà actives, refus")
            await self._send_json({"type": "error", "code": "too_many_sessions",
                                   "message": "Vous avez déjà 2 sessions actives."})
            await self.ws.close(code=4003)
            return
        _sessions_actives[user_id] = count + 1

        try:
            await self._demarrer_deepgram()
            await self._send_ready()
            self._tache_facturation = asyncio.create_task(self._boucle_facturation())
            await self._boucle_messages()
        except WebSocketDisconnect:
            logger.info(f"[TranslateLive] session {self.etat.session_id} — déconnexion client")
        except Exception as e:
            logger.exception(f"[TranslateLive] erreur session : {e}")
            await self._send_json({"type": "error", "code": "internal",
                                   "message": str(e)[:200]})
        finally:
            self.etat.actif = False
            if self._tache_facturation:
                self._tache_facturation.cancel()
                try:
                    await self._tache_facturation
                except (asyncio.CancelledError, Exception):
                    pass
            # Facturation finale (résidu < 1 min)
            await self._facturer_residu()
            if self._dg:
                await self._dg.close()
            _sessions_actives[user_id] = max(0, _sessions_actives.get(user_id, 1) - 1)

    # ── Démarrage STT ─────────────────────────────────────────────────────────

    async def _demarrer_deepgram(self) -> None:
        if not deepgram_disponible():
            logger.warning("[TranslateLive] Deepgram indisponible — mode dégradé (pas de transcript)")
            self._dg = None
            return
        self._dg = DeepgramStreamingClient(
            on_transcript=self._on_transcript,
            source_lang=self.etat.source_lang,
        )
        try:
            await self._dg.start()
        except Exception as e:
            logger.warning(f"[TranslateLive] échec start Deepgram : {e}")
            self._dg = None

    # ── Messages serveur ──────────────────────────────────────────────────────

    async def _send_ready(self) -> None:
        await self._send_json({
            "type": "ready",
            "session_id": self.etat.session_id,
            "source": self.etat.source_lang,
            "target": self.etat.target_lang,
            "stt_available": self._dg is not None,
            "credits_per_minute": CREDITS_PAR_MINUTE,
            "ts": time.time(),
        })

    async def _send_json(self, obj: dict) -> None:
        try:
            await self.ws.send_text(json.dumps(obj, ensure_ascii=False))
        except Exception:
            pass  # WS déjà fermé ou plantant

    # ── Callback Deepgram ─────────────────────────────────────────────────────

    async def _on_transcript(self, texte: str, langue: str, is_final: bool) -> None:
        """Appelé par DeepgramStreamingClient à chaque résultat."""
        if not self.etat.actif:
            return
        self._derniere_utterance_id += 1
        utter_id = f"u{self._derniere_utterance_id}"

        # 1. Push transcript brut (interim + final)
        await self._send_json({
            "type": "transcript",
            "text": texte,
            "lang": langue,
            "is_final": is_final,
            "utterance_id": utter_id,
            "ts": time.time(),
        })

        # 2. Traduction uniquement sur final (éviter spam coûteux)
        if not is_final:
            return

        src = normaliser_code_langue(langue, self.etat.source_lang or "auto")
        tgt = self.etat.target_lang

        # Détection genre sur audio accumulé (mise à jour par utterance finale)
        self._current_gender = self._gender_buf.detect()
        self._gender_buf.clear()

        if src == tgt:
            # Même langue → pas de traduction, pas de TTS, pas de facturation EL
            await self._send_json({
                "type": "translation",
                "source_text": texte,
                "translated_text": texte,
                "source_lang": src,
                "target_lang": tgt,
                "gender": self._current_gender,
                "utterance_id": utter_id,
                "ts": time.time(),
            })
            return

        try:
            traduit = await traduire_texte(
                texte, source_lang=src, target_lang=tgt
            )
        except Exception as e:
            logger.warning(f"[TranslateLive] traduction échouée : {e}")
            traduit = texte

        await self._send_json({
            "type": "translation",
            "source_text": texte,
            "translated_text": traduit,
            "source_lang": src,
            "target_lang": tgt,
            "gender": self._current_gender,
            "utterance_id": utter_id,
            "ts": time.time(),
        })
        # Signale au cycle de facturation qu'une traduction a eu lieu → marge 20×
        self._traductions_ce_cycle += 1

        # ── TTS ElevenLabs — facturé seulement si traduction effective ────────
        if elevenlabs_disponible(self._el_key) and traduit and traduit != texte:
            audio_mp3 = await elevenlabs_synthesize(
                text=traduit,
                gender=self._current_gender,
                api_key=self._el_key,
            )
            if audio_mp3:
                # Envoie l'audio MP3 en binaire avec métadonnées en préambule JSON
                meta = json.dumps({
                    "type": "audio",
                    "utterance_id": utter_id,
                    "gender": self._current_gender,
                    "format": "mp3",
                }).encode()
                # Format : 4 octets longueur meta (big-endian) + meta JSON + MP3
                import struct
                frame = struct.pack(">I", len(meta)) + meta + audio_mp3
                try:
                    await self.ws.send_bytes(frame)
                except Exception:
                    pass

                # Facturation ElevenLabs (seulement si audio généré)
                try:
                    from modules.pro.service_credits import debiter_forfait_fcfa
                    await debiter_forfait_fcfa(
                        self.etat.user_id,
                        cout_fcfa=EL_COUT_FCFA,
                        module="translate_live_tts",
                    )
                except Exception as e:
                    logger.warning(f"[TranslateLive] facturation TTS échouée : {e}")

    # ── Boucle de messages client ─────────────────────────────────────────────

    async def _boucle_messages(self) -> None:
        while self.etat.actif:
            msg = await self.ws.receive()
            t = msg.get("type")
            if t == "websocket.disconnect":
                raise WebSocketDisconnect()

            # Audio binaire → buffer gender + forward vers Deepgram
            if "bytes" in msg and msg["bytes"] is not None:
                pcm = msg["bytes"]
                self._gender_buf.push(pcm)
                if self._dg:
                    await self._dg.send_audio(pcm)
                continue

            # Texte (JSON de contrôle ou ping)
            if "text" in msg and msg["text"] is not None:
                texte = msg["text"]
                if texte == "ping":
                    await self._send_json({"type": "pong"})
                    continue
                try:
                    obj = json.loads(texte)
                except Exception:
                    continue
                await self._handle_control(obj)

    async def _handle_control(self, obj: dict) -> None:
        mtype = (obj.get("type") or "").lower()
        if mtype == "config":
            nouvelle_src = normaliser_code_langue(obj.get("source"), self.etat.source_lang)
            nouvelle_tgt = normaliser_code_langue(obj.get("target"), self.etat.target_lang)
            if nouvelle_tgt:
                self.etat.target_lang = nouvelle_tgt
            if nouvelle_src:
                self.etat.source_lang = nouvelle_src
            await self._send_json({
                "type": "config_ack",
                "source": self.etat.source_lang,
                "target": self.etat.target_lang,
            })
        elif mtype == "stop":
            self.etat.actif = False
            await self._send_json({"type": "stopped"})

    # ── Facturation ───────────────────────────────────────────────────────────

    async def _boucle_facturation(self) -> None:
        """Toutes les 60s : débite 1 minute de crédits, vérifie le solde."""
        try:
            while self.etat.actif:
                await asyncio.sleep(60.0)
                if not self.etat.actif:
                    break
                self.etat.minutes_streamees += 1.0
                await self._facturer_une_minute()
        except asyncio.CancelledError:
            raise

    async def _facturer_une_minute(self) -> None:
        """Débite 1 minute. Si crédits insuffisants, ferme la session."""
        # Plafond dur par plan
        plafond = PLAFOND_MINUTES_PAR_MOIS.get(self.user_plan, 15)
        if self.etat.minutes_facturees + 1 > plafond:
            logger.info(
                f"[TranslateLive] user={self.etat.user_id} plafond {plafond}min atteint"
            )
            await self._send_json({"type": "error", "code": "plafond_mensuel_atteint",
                                   "message": f"Plafond de {plafond} min/mois atteint pour votre plan."})
            self.etat.actif = False
            try:
                await self.ws.close(code=4005)
            except Exception:
                pass
            return

        try:
            from modules.pro.service_credits import debiter_forfait_fcfa
            # 5× si STT-only (aucune traduction ce cycle), 20× si traduction effective
            marge = 20.0 if self._traductions_ce_cycle > 0 else 5.0
            self._traductions_ce_cycle = 0  # reset pour le prochain cycle
            ok, credits_debites, _ = await debiter_forfait_fcfa(
                user_id=self.etat.user_id,
                cout_fcfa=COUT_FCFA_PAR_MINUTE,
                module="translate_live",
                multiplicateur=marge,
            )
        except Exception as e:
            logger.warning(f"[TranslateLive] débit échoué (non bloquant) : {e}")
            ok, credits_debites = True, 0.0

        if not ok:
            await self._send_json({"type": "error", "code": "credits_epuises",
                                   "message": "Crédits épuisés. Rechargez pour continuer."})
            self.etat.actif = False
            try:
                await self.ws.close(code=4002)
            except Exception:
                pass
            return

        self.etat.minutes_facturees += 1.0
        await self._send_json({
            "type": "usage",
            "minutes": self.etat.minutes_facturees,
            "credits_debited_total": self.etat.minutes_facturees * CREDITS_PAR_MINUTE,
            "credits_debited_last": credits_debites,
        })

    async def _facturer_residu(self) -> None:
        """À la clôture, facture la fraction restante (arrondi au dixième de minute)."""
        ecoule = (time.monotonic() - self.etat.debut_ts) / 60.0
        a_facturer = round(max(0.0, ecoule - self.etat.minutes_facturees), 1)
        if a_facturer <= 0.0:
            return
        cout_fcfa = round(COUT_FCFA_PAR_MINUTE * a_facturer, 2)
        try:
            from modules.pro.service_credits import debiter_forfait_fcfa
            marge_residu = 20.0 if self._traductions_ce_cycle > 0 else 5.0
            await debiter_forfait_fcfa(
                user_id=self.etat.user_id,
                cout_fcfa=cout_fcfa,
                module="translate_live_residu",
                multiplicateur=marge_residu,
            )
            self.etat.minutes_facturees += a_facturer
            logger.info(
                f"[TranslateLive] résidu facturé user={self.etat.user_id} "
                f"{a_facturer:.1f}min ({cout_fcfa} FCFA)"
            )
        except Exception as e:
            logger.warning(f"[TranslateLive] résidu non facturé : {e}")
