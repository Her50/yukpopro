"""
Client ElevenLabs TTS pour YukpoTranslate Live.

Modèle : eleven_multilingual_v2 (supporte FR, EN, ES, PT, DE, AR, ZH, et +).
Voix par genre :
  - Homme  : Adam  (pNInz6obpgDQGcFmaJgB) — naturel, clair, multilangue
  - Femme  : Sarah (EXAVITQu4vr4xnSDxMaL) — chaleureuse, multilangue

Tarification réelle ElevenLabs Starter : $0.30 / 1 000 caractères.
Coût FCFA réel ≈ 0.18 FCFA/char (@ 600 FCFA/$).
Facturation Yukpo : via debiter_forfait_fcfa → ×20 marge incluse automatiquement.
Coût transmis = 0.5 FCFA/utterance (utterance moyenne ~55 chars, légèrement subventionné
pour rester accessible, couvert par la marge globale Yukpo).
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger("yukpo_assurance.translate_live.elevenlabs")

ELEVENLABS_MODEL = "eleven_multilingual_v2"

VOICES: dict[str, str] = {
    "male":   "pNInz6obpgDQGcFmaJgB",  # Adam
    "female": "EXAVITQu4vr4xnSDxMaL",  # Sarah
}

# Coût réel en FCFA par utterance transmis à debiter_forfait_fcfa.
# La marge ×20 Yukpo est appliquée automatiquement dans le service.
COUT_FCFA_PAR_UTTERANCE: float = 0.54   # ≈ 60 chars × 0.18 FCFA/char / 2 (subvention)

VOICE_SETTINGS = {
    "stability":        0.50,
    "similarity_boost": 0.75,
    "style":            0.00,
    "use_speaker_boost": True,
}


async def synthesize(
    text: str,
    gender: str,
    api_key: str,
    timeout: float = 12.0,
) -> Optional[bytes]:
    """
    Synthétise `text` avec ElevenLabs en fonction du genre détecté.
    Retourne les octets MP3 ou None en cas d'échec.
    """
    if not api_key or not text.strip():
        return None

    voice_id = VOICES.get(gender, VOICES["female"])
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    headers = {
        "xi-api-key":    api_key,
        "Content-Type":  "application/json",
        "Accept":        "audio/mpeg",
    }
    payload = {
        "text":          text[:2_500],  # sécurité
        "model_id":      ELEVENLABS_MODEL,
        "voice_settings": VOICE_SETTINGS,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)

        if resp.status_code == 200:
            logger.debug(
                f"[ElevenLabs] TTS OK — voix={gender} len={len(resp.content)} bytes"
            )
            return resp.content

        logger.warning(
            f"[ElevenLabs] TTS erreur HTTP {resp.status_code} : {resp.text[:200]}"
        )
        return None

    except httpx.TimeoutException:
        logger.warning("[ElevenLabs] TTS timeout")
        return None
    except Exception as exc:
        logger.warning(f"[ElevenLabs] TTS exception : {exc}")
        return None


def elevenlabs_disponible(api_key: str) -> bool:
    return bool(api_key and len(api_key) > 10)
