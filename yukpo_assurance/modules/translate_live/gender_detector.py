"""
Détection de genre vocal (homme/femme) par analyse de hauteur fondamentale (F0).

Algorithme : autocorrélation YIN-simplifié sur signal PCM16 16 kHz mono.
  - Voix masculine : F0 ∈ [85, 165] Hz
  - Voix féminine  : F0 ∈ [165, 280] Hz
  - Seuil de décision : 160 Hz

Utilise uniquement numpy (déjà dépendance du projet).
"""
from __future__ import annotations

import numpy as np
import logging

logger = logging.getLogger("yukpo_assurance.translate_live.gender")

SAMPLE_RATE     = 16_000   # Hz — Deepgram resampled output
F0_MALE_MAX     = 160      # Hz — seuil homme / femme
F0_MIN          = 80       # Hz — voix humaine min
F0_MAX          = 300      # Hz — voix humaine max
BUFFER_MAX_BYTES = SAMPLE_RATE * 2 * 3  # 3 secondes PCM16


class GenderBuffer:
    """
    Tampon circulaire PCM16 par session.
    Accumule les chunks audio et expose `detect()` sur les dernières secondes.
    """

    def __init__(self) -> None:
        self._buf: bytearray = bytearray()

    def push(self, pcm: bytes) -> None:
        self._buf.extend(pcm)
        # Tronque à 3 secondes max (FIFO)
        if len(self._buf) > BUFFER_MAX_BYTES:
            self._buf = self._buf[-BUFFER_MAX_BYTES:]

    def clear(self) -> None:
        self._buf.clear()

    def detect(self) -> str:
        """Retourne 'male' ou 'female'. Défaut 'female' si signal insuffisant."""
        if len(self._buf) < SAMPLE_RATE:  # < 0.5 s → pas assez
            return "female"
        try:
            return _detect_gender(bytes(self._buf))
        except Exception as exc:
            logger.debug(f"[GenderDetect] erreur analyse : {exc}")
            return "female"


def _detect_gender(pcm: bytes) -> str:
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    samples /= 32768.0

    # Centrage DC
    samples -= samples.mean()

    # Limites en échantillons pour la plage F0 voulue
    lag_min = int(SAMPLE_RATE / F0_MAX)   # 53 samples pour 300 Hz
    lag_max = int(SAMPLE_RATE / F0_MIN)   # 200 samples pour 80 Hz

    if lag_max >= len(samples):
        lag_max = len(samples) - 1
    if lag_min >= lag_max:
        return "female"

    # Autocorrélation (corrélation croisée signal avec lui-même)
    n = len(samples)
    ac = np.correlate(samples, samples, mode="full")
    ac = ac[n - 1:]   # partie causale

    # Normalisation
    if ac[0] == 0:
        return "female"
    ac /= ac[0]

    # Recherche du pic dominant dans la plage vocale
    segment = ac[lag_min:lag_max + 1]
    if segment.size == 0:
        return "female"

    peak_offset = int(np.argmax(segment))
    peak_lag    = lag_min + peak_offset
    peak_val    = segment[peak_offset]

    # Confiance minimale : pic doit être > 0.2 (signal périodique)
    if peak_val < 0.2:
        return "female"

    f0 = SAMPLE_RATE / peak_lag
    gender = "male" if f0 < F0_MALE_MAX else "female"
    logger.debug(f"[GenderDetect] F0={f0:.1f} Hz → {gender} (pic={peak_val:.2f})")
    return gender
