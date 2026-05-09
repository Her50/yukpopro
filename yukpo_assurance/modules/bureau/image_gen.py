"""
Designer Pro — génération d'images IA via fal.ai (Flux).

Trois modes (cf. niveau-3 hybride spec) :
- "standard"  : Flux schnell        (4-step,  ~1s,    ~$0.003/image)
- "premium"   : Flux dev            (28-step, ~5-10s, ~$0.025/image)
- "ultra"     : Flux 1.1 Pro Ultra  (raw cinematic SOTA, ~$0.06/image)

Modes "premium" et "ultra" génèrent **2 variantes** par slot puis Claude
Vision sélectionne la meilleure (composition / qualité / fidélité au prompt).

Marges Yukpo : voir COUTS_FORFAIT_FCFA["designerpro_image_*"] — débit par
image générée via debiter_forfait.
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

ImageMode = Literal["sans", "standard", "premium", "ultra"]

_FAL_BASE_URL = "https://fal.run"
_FAL_MODEL_SCHNELL = "fal-ai/flux/schnell"
_FAL_MODEL_DEV = "fal-ai/flux/dev"
_FAL_MODEL_PRO_ULTRA = "fal-ai/flux-pro/v1.1-ultra"

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

    if mode == "ultra":
        modele = _FAL_MODEL_PRO_ULTRA
    elif mode == "premium":
        modele = _FAL_MODEL_DEV
    else:
        modele = _FAL_MODEL_SCHNELL
    url = f"{_FAL_BASE_URL}/{modele}"
    image_size = _TAILLES_PAR_FORMAT.get(format_, "portrait_4_3")

    payload: dict = {
        "prompt": prompt[:4000],   # safety guard
        "num_images": 1,
        "enable_safety_checker": True,
    }
    # Flux Pro Ultra utilise aspect_ratio (3:4 / 16:9 / 1:1...) et raw=true
    # pour des sorties cinématographiques ; pas de num_inference_steps.
    if mode == "ultra":
        ar_map = {
            "square_hd":      "1:1",
            "portrait_4_3":   "3:4",
            "portrait_16_9":  "9:16",
            "landscape_4_3":  "4:3",
            "landscape_16_9": "16:9",
        }
        payload["aspect_ratio"] = ar_map.get(image_size, "3:4")
        payload["output_format"] = "png"
        payload["raw"] = True   # mode "raw" = qualité photo SOTA, moins post-traité
    else:
        payload["image_size"] = image_size
        if mode == "standard":
            payload["num_inference_steps"] = 4
        else:  # premium = Flux dev
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
    nb_variantes: int = 1,
) -> list[Optional[bytes]]:
    """
    Génère plusieurs images en parallèle (limit = `concurrence`).
    Si `nb_variantes > 1`, génère N variantes par slot et retourne la
    meilleure (sélection par Claude Vision en mode premium/ultra).
    Retourne une liste de même taille que `prompts` :
      - bytes PNG si la génération a réussi
      - None si elle a échoué (l'appelant utilise alors un placeholder)
    """
    if mode == "sans" or not prompts:
        return [None] * len(prompts)

    semaphore = asyncio.Semaphore(max(1, concurrence))

    async def _one_image(p: str, fmt: str, seed: Optional[int]) -> Optional[bytes]:
        async with semaphore:
            try:
                return await generer_image(p, mode=mode, format_=fmt, seed=seed)
            except ImageGenNotConfigured:
                return None
            except ImageGenError as e:
                logger.warning(f"[image_gen] échec génération : {e}")
                return None

    async def _one_slot(p: str, fmt: str) -> Optional[bytes]:
        if nb_variantes <= 1:
            return await _one_image(p, fmt, None)
        # Génère nb_variantes variantes en parallèle (seeds différents pour
        # de la diversité réelle), puis Claude Vision pick la meilleure.
        import random
        seeds = [random.randint(1, 2**31 - 1) for _ in range(nb_variantes)]
        candidates = await asyncio.gather(*(_one_image(p, fmt, s) for s in seeds))
        candidates = [c for c in candidates if c]
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        return await choisir_meilleure_variante(candidates, p)

    return await asyncio.gather(*(_one_slot(p, f) for p, f in prompts))


async def choisir_meilleure_variante(
    images: list[bytes],
    prompt_attendu: str,
) -> bytes:
    """
    Demande à Claude Vision de sélectionner la meilleure image parmi N
    candidates (qualité, fidélité au prompt, composition, absence d'artefacts).
    Retourne les bytes de la meilleure ; en cas d'échec, retourne la première.
    """
    if not images:
        raise ImageGenError("Aucune image à comparer")
    if len(images) == 1:
        return images[0]
    try:
        from core.ia_client import ia_client
        # On envoie les 2 premières images (vision API limit). Si N>2, on
        # garde la meilleure des 2 premières — la 3e est rarement meilleure.
        a, b = images[0], images[1]
        prompt = (
            f"Compare ces deux images générées pour le prompt : « {prompt_attendu[:400]} »\n\n"
            f"Réponds STRICTEMENT par 'A' ou 'B' :\n"
            f"- A si l'image A est meilleure (composition / qualité / fidélité au prompt / absence d'artefacts / éclairage)\n"
            f"- B si l'image B est meilleure\n\n"
            f"Considère AUSSI : visages réalistes, mains correctes, texte non buggé, "
            f"perspective cohérente, lumière naturelle. Pas d'explication, juste 'A' ou 'B'."
        )
        # Premier appel : image A
        b64_a = base64.b64encode(a).decode("ascii")
        b64_b = base64.b64encode(b).decode("ascii")
        # On envoie les 2 images l'une après l'autre — l'ia_client supporte
        # 1 image à la fois, donc on demande de noter chaque image et on compare.
        rep_a = await ia_client.analyser_image_vision(
            image_base64=b64_a, mime_type="image/png",
            prompt=f"Pour le prompt : « {prompt_attendu[:200]} » — note cette image sur 100 (qualité, composition, fidélité, absence d'artefacts). Réponds par UN SEUL nombre entre 0 et 100.",
        )
        rep_b = await ia_client.analyser_image_vision(
            image_base64=b64_b, mime_type="image/png",
            prompt=f"Pour le prompt : « {prompt_attendu[:200]} » — note cette image sur 100 (qualité, composition, fidélité, absence d'artefacts). Réponds par UN SEUL nombre entre 0 et 100.",
        )
        try:
            score_a = int("".join(c for c in (rep_a.contenu or "").strip() if c.isdigit())[:3] or "0")
            score_b = int("".join(c for c in (rep_b.contenu or "").strip() if c.isdigit())[:3] or "0")
        except Exception:
            score_a = score_b = 0
        logger.debug(f"[image_gen] variantes : A={score_a} B={score_b}")
        return a if score_a >= score_b else b
    except Exception as e:
        logger.debug(f"[image_gen] best-of pick fallback (premier) : {e}")
        return images[0]


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
