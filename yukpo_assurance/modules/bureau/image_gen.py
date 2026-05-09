"""
Designer Pro — génération d'images IA via fal.ai (Flux).

Deux modes :
- "standard"  : Flux schnell  (4-step diffusion, ~1s, ~$0.003/image)
- "premium"   : Flux dev      (28-step diffusion, ~5-10s, ~$0.025/image)

Le pipeline complet (prompt → image → vision check) est appelé depuis
`infographe_pro.construire_specification` quand la spec contient des slots
"image_genere" sans média utilisateur associé.

Marges Yukpo : voir COUTS_FORFAIT_FCFA["designerpro_image_standard"] et
"designerpro_image_premium" — débit par image générée via debiter_forfait.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from io import BytesIO
from typing import Literal, Optional

import httpx

from config.settings import settings

logger = logging.getLogger("yukpo_assurance.bureau.image_gen")


# ── Configuration ────────────────────────────────────────────────────────────

ImageMode = Literal["sans", "standard", "premium"]

_FAL_BASE_URL = "https://fal.run"
_FAL_MODEL_SCHNELL = "fal-ai/flux/schnell"
_FAL_MODEL_DEV = "fal-ai/flux/dev"

# Tailles d'image standard pour les slots de mise en page.
# fal.ai accepte : square_hd (1024×1024), portrait_4_3, portrait_16_9,
# landscape_4_3, landscape_16_9.
_TAILLES_PAR_FORMAT: dict[str, str] = {
    "square":         "square_hd",
    "portrait_4_3":   "portrait_4_3",
    "portrait":       "portrait_4_3",
    "portrait_16_9":  "portrait_16_9",
    "landscape_4_3":  "landscape_4_3",
    "landscape":      "landscape_4_3",
    "landscape_16_9": "landscape_16_9",
}


# ── Erreurs ──────────────────────────────────────────────────────────────────

class ImageGenError(Exception):
    """Échec de génération d'image (réseau, quota, contenu refusé…)."""


class ImageGenNotConfigured(ImageGenError):
    """FAL_KEY absent — appelé en mode dégradé silencieux."""


# ── API ───────────────────────────────────────────────────────────────────────

async def generer_image(
    prompt: str,
    mode: ImageMode = "standard",
    format_: str = "portrait_4_3",
    seed: Optional[int] = None,
    timeout_s: float = 60.0,
) -> bytes:
    """
    Génère 1 image via fal.ai et retourne les octets PNG.

    Lève `ImageGenNotConfigured` si FAL_KEY absent (no-op silencieux côté
    appelant : le pipeline tombera en placeholder).
    Lève `ImageGenError` pour toute autre erreur (timeout, quota, etc.).
    """
    if mode == "sans":
        raise ImageGenError("Mode 'sans' — aucune image à générer")

    api_key = settings.FAL_KEY
    if not api_key:
        raise ImageGenNotConfigured("FAL_KEY non configuré dans settings")

    modele = _FAL_MODEL_SCHNELL if mode == "standard" else _FAL_MODEL_DEV
    url = f"{_FAL_BASE_URL}/{modele}"
    image_size = _TAILLES_PAR_FORMAT.get(format_, "portrait_4_3")

    payload: dict = {
        "prompt": prompt[:4000],   # safety guard
        "image_size": image_size,
        "num_images": 1,
        # schnell = 4 steps fixes ; dev = 28 par défaut, on accepte le défaut
        "enable_safety_checker": True,
    }
    if mode == "standard":
        payload["num_inference_steps"] = 4
    else:
        payload["num_inference_steps"] = 28
        payload["guidance_scale"] = 3.5
    if seed is not None:
        payload["seed"] = seed

    headers = {
        "Authorization": f"Key {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.post(url, json=payload, headers=headers)
    except httpx.TimeoutException as e:
        raise ImageGenError(f"Timeout fal.ai après {timeout_s}s") from e
    except httpx.HTTPError as e:
        raise ImageGenError(f"Erreur réseau fal.ai : {e}") from e

    if r.status_code != 200:
        raise ImageGenError(f"fal.ai HTTP {r.status_code} : {r.text[:200]}")

    data = r.json()
    images = data.get("images") or []
    if not images:
        raise ImageGenError("fal.ai : réponse sans 'images'")

    img_url = images[0].get("url")
    if not img_url:
        raise ImageGenError("fal.ai : image sans URL")

    # Téléchargement de l'image générée
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r_img = await client.get(img_url)
            r_img.raise_for_status()
            return r_img.content
    except httpx.HTTPError as e:
        raise ImageGenError(f"Téléchargement image échoué : {e}") from e


async def generer_images_batch(
    prompts: list[tuple[str, str]],   # (prompt, format)
    mode: ImageMode = "standard",
    concurrence: int = 3,
) -> list[Optional[bytes]]:
    """
    Génère plusieurs images en parallèle (limit = `concurrence`).
    Retourne une liste de même taille que `prompts` :
      - bytes PNG si la génération a réussi
      - None si elle a échoué (l'appelant utilise alors un placeholder)
    """
    if mode == "sans" or not prompts:
        return [None] * len(prompts)

    semaphore = asyncio.Semaphore(max(1, concurrence))

    async def _one(p: str, fmt: str) -> Optional[bytes]:
        async with semaphore:
            try:
                return await generer_image(p, mode=mode, format_=fmt)
            except ImageGenNotConfigured:
                return None
            except ImageGenError as e:
                logger.warning(f"[image_gen] échec génération : {e}")
                return None

    return await asyncio.gather(*(_one(p, f) for p, f in prompts))


# ── Vision check (Premium uniquement) ────────────────────────────────────────

async def valider_image_vision(image_bytes: bytes, prompt_attendu: str) -> tuple[bool, str]:
    """
    Vérifie qu'une image générée correspond bien au prompt (Claude Vision).
    Retourne (ok: bool, raison: str). Si Vision échoue ou non disponible,
    retourne (True, "skip") pour ne pas bloquer le pipeline.
    """
    try:
        from core.ia_client import ia_client
        prompt_check = (
            f"Tu valides la qualité d'une image générée par IA.\n"
            f"Prompt demandé : « {prompt_attendu[:300]} »\n\n"
            f"Critères : (1) sujet correct, (2) pas d'artefact visible, "
            f"(3) pas de texte buggé, (4) qualité photo/illustration acceptable.\n\n"
            f"Réponds STRICTEMENT par 'OK' si l'image est utilisable, ou par "
            f"'REJET: <raison courte>' si elle doit être regénérée."
        )
        b64 = base64.b64encode(image_bytes).decode("ascii")
        reponse = await ia_client.analyser_image_vision(
            image_base64=b64,
            prompt=prompt_check,
            mime_type="image/png",
        )
        contenu = (reponse.contenu or "").strip()
        if contenu.upper().startswith("OK"):
            return True, "ok"
        return False, contenu[:120]
    except Exception as e:
        logger.debug(f"[image_gen] vision check skipped : {e}")
        return True, "skip"


# ── Helpers ──────────────────────────────────────────────────────────────────

def png_vers_bytesio(image_bytes: bytes) -> BytesIO:
    """Wrapper pour passer une image générée à ReportLab/Pillow."""
    return BytesIO(image_bytes)
