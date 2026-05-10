"""
Génération vidéo IA — text-to-video via fal.ai (Kling 1.6, LTX-Video) ou
Replicate (Wan2.1) en fallback.

Cas d'usage :
- Vidéo promo 5-10s pour campagne marketing (réseaux sociaux)
- Animation produit packaging
- Teaser événement (mariage, conférence, lancement)
- Vidéo explicative pour rapport (embed dans slides PPTX)

Coût indicatif (mai 2026) :
- fal.ai Kling 1.6 standard : ~$0.20 / 5s
- fal.ai Kling 1.6 pro      : ~$0.50 / 5s
- fal.ai LTX-Video          : ~$0.05 / 5s (rapide, qualité moindre)
- Replicate Wan2.1          : ~$0.10 / 5s

Forfait Yukpo : `bureau_video_5s` = 60 FCFA/vidéo (marge ~12× sur LTX-Video).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from config.settings import settings

logger = logging.getLogger("yukpo_assurance.bureau.video_gen")


class VideoGenError(Exception):
    """Erreur générique génération vidéo."""


class VideoGenNotConfigured(VideoGenError):
    """Aucune clé API vidéo configurée."""


_FAL_BASE_URL = "https://fal.run"
_FAL_KLING_STD = "fal-ai/kling-video/v1.6/standard/text-to-video"
_FAL_KLING_PRO = "fal-ai/kling-video/v1.6/pro/text-to-video"
_FAL_LTX = "fal-ai/ltx-video"

# Mapping modes → (modele, latence_estimee_s, cout_usd_estime)
_MODES_VIDEO: dict[str, tuple[str, int, float]] = {
    "standard": (_FAL_LTX,        15, 0.05),
    "premium":  (_FAL_KLING_STD,  60, 0.20),
    "ultra":    (_FAL_KLING_PRO, 180, 0.50),
}


async def generer_video(
    prompt: str,
    duree_s: int = 5,
    mode: str = "standard",
    aspect_ratio: str = "16:9",
    seed: Optional[int] = None,
    timeout_s: int = 240,
) -> bytes:
    """
    Génère une vidéo MP4 depuis un prompt textuel.

    Args:
        prompt       : description scène (anglais recommandé pour qualité max)
        duree_s      : 5 ou 10 secondes (Kling supporte les 2)
        mode         : standard | premium | ultra
        aspect_ratio : '16:9' | '9:16' | '1:1' | '4:3'
        seed         : graine reproductible
        timeout_s    : timeout HTTP

    Returns: MP4 bytes (H.264).
    Raises VideoGenNotConfigured si FAL_KEY absent et Replicate aussi.
    """
    api_key = settings.FAL_KEY
    if not api_key:
        # Fallback Replicate
        try:
            from .replicate_client import generer_video as _rep_video
            return await _rep_video(prompt, duree_s=duree_s, aspect_ratio=aspect_ratio,
                                     seed=seed, timeout_s=timeout_s)
        except Exception as e:
            logger.warning(f"[video_gen] FAL_KEY absent + Replicate KO : {e}")
            raise VideoGenNotConfigured(
                "Aucune clé API vidéo configurée (FAL_KEY ou REPLICATE_API_TOKEN)."
            )

    modele, _lat, _cout = _MODES_VIDEO.get(mode, _MODES_VIDEO["standard"])
    payload: dict = {
        "prompt": prompt[:2000],
        "aspect_ratio": aspect_ratio,
        "duration": str(duree_s),
    }
    if seed is not None:
        payload["seed"] = int(seed)

    headers = {
        "Authorization": f"Key {api_key}",
        "Content-Type": "application/json",
    }
    url = f"{_FAL_BASE_URL}/{modele}"

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        try:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as e:
            raise VideoGenError(
                f"fal.ai {modele} HTTP {e.response.status_code} : "
                f"{e.response.text[:300]}"
            )
        except httpx.HTTPError as e:
            # Tentative de fallback Replicate
            try:
                from .replicate_client import generer_video as _rep_video
                logger.info(f"[video_gen] fal.ai KO → Replicate fallback")
                return await _rep_video(
                    prompt, duree_s=duree_s, aspect_ratio=aspect_ratio,
                    seed=seed, timeout_s=timeout_s,
                )
            except Exception:
                raise VideoGenError(f"fal.ai {modele} indisponible : {e}")

        # fal.ai retourne {"video": {"url": "..."}}
        video_obj = data.get("video") or {}
        video_url = video_obj.get("url") if isinstance(video_obj, dict) else None
        if not video_url:
            raise VideoGenError(f"fal.ai {modele} : pas de video.url dans la réponse")

        # Télécharger le MP4
        try:
            r2 = await client.get(video_url, timeout=120)
            r2.raise_for_status()
            return r2.content
        except httpx.HTTPError as e:
            raise VideoGenError(f"Téléchargement vidéo échoué : {e}")
