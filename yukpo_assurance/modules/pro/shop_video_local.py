"""Génération vidéo publicitaire produit YukpoShop — flux LOCAL YukpoPro.

Remplace l'ancien bridge Rust Remotion (`yukposhop_rust_video`) par le flux
vidéo natif YukpoPro (`modules.bureau.video_gen`) qui :
  • Génère via fal.ai Kling (5-10s) ou Replicate fallback
  • Étend à 15-60s via stitching FFmpeg multi-clips (generer_video_long)
  • Permet l'option image-to-video à partir d'une photo produit
  • Coûts maîtrisés côté forfait YukpoPro (pas de double facturation Rust)

Le ton choisi par le commerçant (dynamique / luxueux / chaleureux / fun)
oriente le prompt vidéo. Le résultat MP4 est persisté dans le storage
shop_branding (R2 → URL publique) puis attaché au produit.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("yukpo_assurance.pro.shop_video_local")


@dataclass
class VideoGenResult:
    success: bool
    video_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration_s: Optional[int] = None
    duree_render_s: Optional[float] = None
    error: Optional[str] = None


_TON_STYLES = {
    "dynamique":  "dynamic energetic cinematography, fast cuts, vibrant colors, upbeat mood",
    "luxueux":    "luxurious cinematic style, slow motion, premium lighting, elegant",
    "chaleureux": "warm welcoming atmosphere, soft natural lighting, friendly tone",
    "fun":        "playful fun vibe, bright pop colors, dynamic motion, cheerful",
    "pro":        "professional product showcase, clean studio lighting, smooth pans",
    "minimal":    "minimalist aesthetic, white background, focused product highlight",
}


def _construire_prompt_video(
    titre: str, description: str, ton: str, devise: str, prix: float,
) -> str:
    style = _TON_STYLES.get(ton.lower(), _TON_STYLES["pro"])
    desc_trim = (description or "")[:300].replace("\n", " ").strip()
    return (
        f"Advertising commercial video for the product '{titre}'. "
        f"{desc_trim} "
        f"Style: {style}. "
        f"Showcase the product with appealing angles, smooth camera motion, "
        f"high quality production. End with a clear hero shot of the product. "
        f"No text overlays needed. Photorealistic, marketing quality."
    )


async def _persister_video(boutique_id: int, produit_id: int, mp4: bytes) -> str:
    """Persiste le MP4 sur le storage YukpoPro (R2 / volume local fallback)."""
    from core.storage import save_artifact
    name = f"shop_video_{boutique_id}_{produit_id}_{int(time.time())}.mp4"
    info = save_artifact(
        category="shop_branding", name=name,
        content=mp4, content_type="video/mp4",
    )
    import os
    if info.get("storage") == "r2":
        public_base = os.getenv("R2_PUBLIC_BASE_URL", "").rstrip("/")
        if public_base:
            return f"{public_base}/{info['key']}"
        return f"/api/v1/storage/shop_branding/{name}"
    return f"/api/v1/storage/shop_branding/{name}"


async def generer_video_produit_local(
    *, boutique_id: int, produit_id: int, titre: str, description: str,
    ton: str = "dynamique", duree_s: int = 15, aspect_ratio: str = "9:16",
    devise: str = "XAF", prix: float = 0.0,
) -> VideoGenResult:
    """Génère une vidéo pub IA pour un produit via le flux YukpoPro interne.

    duree_s 5-10 → 1 clip natif Kling
    duree_s 11-60 → stitching FFmpeg multi-clips
    aspect_ratio 9:16 par défaut (mobile + VideoFeed Yukpo Rust)
    """
    if duree_s < 5 or duree_s > 60:
        return VideoGenResult(False, error="durée doit être entre 5s et 60s")

    prompt = _construire_prompt_video(titre, description, ton, devise, prix)
    t0 = time.time()
    try:
        if duree_s <= 10:
            from modules.bureau.video_gen import generer_video
            mp4 = await generer_video(
                prompt=prompt, duree_s=duree_s,
                mode="premium", aspect_ratio=aspect_ratio,
            )
        else:
            from modules.bureau.video_gen import generer_video_long
            mp4 = await generer_video_long(
                prompt=prompt, duree_s=duree_s,
                mode="premium", aspect_ratio=aspect_ratio,
            )
    except Exception as e:
        logger.warning(f"[shop_video_local] génération échec : {e}")
        return VideoGenResult(False, error=f"Génération vidéo échouée : {str(e)[:200]}")

    if not mp4:
        return VideoGenResult(False, error="aucun MP4 produit")

    try:
        url = await _persister_video(boutique_id, produit_id, mp4)
    except Exception as e:
        return VideoGenResult(False, error=f"persistance échouée : {e}")

    duree_render = round(time.time() - t0, 1)
    return VideoGenResult(
        success=True,
        video_url=url,
        thumbnail_url=None,
        duration_s=duree_s,
        duree_render_s=duree_render,
    )
