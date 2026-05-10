"""
Sprint R1 — Client Replicate.com pour Yukpo Designer Pro.

3 capacités clés que ce module apporte :

  1. PARITÉ avec fal.ai sur Flux Pro Ultra / Flux dev / Flux schnell — utilisable
     comme provider alternatif ou en fallback automatique (cf image_gen.py).

  2. Brand LoRA training PAR CLIENT (~$5 vs ~$200 chez fal.ai). Permet de vendre
     un "kit visuel marque" intégré dans toutes les générations futures de l'org.

  3. Modèles communautaires exotiques que fal.ai n'héberge pas : Recraft v3 SVG,
     Ideogram v2 (parité possible mais Replicate plus rapide souvent), styles
     spécifiques (anime corporate, watercolor africain, line art, etc.).

API Replicate :
  - Endpoint POST https://api.replicate.com/v1/predictions   → crée une prediction
  - Polling GET  https://api.replicate.com/v1/predictions/{id} jusqu'à status="succeeded"
  - LoRA training : POST /v1/trainings/{owner}/{model}/versions/{version_id}
                     → renvoie un training_id à poller

Auth : header `Authorization: Bearer <REPLICATE_API_TOKEN>`.
Sur Windows local sans clé : import OK (httpx présent), endpoints retournent
None / lèvent ReplicateNotConfigured. Jamais de crash.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from io import BytesIO
from typing import Literal, Optional

import httpx

from config.settings import settings

logger = logging.getLogger("yukpo_assurance.bureau.replicate_client")

# ── Configuration ────────────────────────────────────────────────────────────

ReplicateMode = Literal["sans", "standard", "premium", "ultra", "ultra_plus"]

_REPLICATE_BASE = "https://api.replicate.com/v1"

# Versions Replicate (pinnées pour stabilité — bumper périodiquement après QA)
# Format : "<owner>/<model>" (Replicate accepte sans version pour prendre la
# dernière) ou "<owner>/<model>:<version_hash>" pour pin strict.
_MODEL_FLUX_PRO_ULTRA = "black-forest-labs/flux-1.1-pro-ultra"
_MODEL_FLUX_PRO       = "black-forest-labs/flux-1.1-pro"
_MODEL_FLUX_DEV       = "black-forest-labs/flux-dev"
_MODEL_FLUX_SCHNELL   = "black-forest-labs/flux-schnell"
_MODEL_FLUX_DEV_LORA  = "black-forest-labs/flux-dev-lora"     # mode Brand LoRA
_MODEL_RECRAFT_V3     = "recraft-ai/recraft-v3"               # alt fal.ai
_MODEL_RECRAFT_V3_SVG = "recraft-ai/recraft-v3-svg"           # SVG pur (unique à Replicate)
_MODEL_IDEOGRAM_V2    = "ideogram-ai/ideogram-v2"

# Modèle d'entraînement LoRA Flux (Replicate hébergé par Ostris) — SOTA training
_LORA_TRAINER = "ostris/flux-dev-lora-trainer"

# Format payload Replicate aspect_ratio
_AR_MAP = {
    "square_hd":      "1:1",
    "portrait_4_3":   "3:4",
    "portrait_16_9":  "9:16",
    "landscape_4_3":  "4:3",
    "landscape_16_9": "16:9",
}


# ── Erreurs ──────────────────────────────────────────────────────────────────


class ReplicateError(Exception):
    """Erreur générique Replicate (réseau, quota, contenu refusé, échec polling)."""


class ReplicateNotConfigured(ReplicateError):
    """REPLICATE_API_TOKEN absent — appel en mode dégradé silencieux."""


class ReplicateTimeout(ReplicateError):
    """Polling dépassé (training/prediction trop long)."""


# ── Core HTTP ────────────────────────────────────────────────────────────────


def _api_token() -> str:
    tok = settings.REPLICATE_API_TOKEN
    if not tok:
        raise ReplicateNotConfigured("REPLICATE_API_TOKEN non configuré")
    return tok


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_api_token()}",
        "Content-Type": "application/json",
        "Prefer": "wait=60",   # Replicate sync mode si <60s, sinon retourne async + polling
    }


async def _create_prediction(
    model_path: str, payload_input: dict, timeout_s: float = 60.0,
) -> dict:
    """
    POST /v1/predictions → crée la prediction. Avec header `Prefer: wait=60`,
    Replicate attend jusqu'à 60s avant de retourner (sync). Sinon retourne
    avec status=processing → on poll.
    """
    url = f"{_REPLICATE_BASE}/models/{model_path}/predictions"
    body = {"input": payload_input}
    async with httpx.AsyncClient(timeout=timeout_s + 5.0) as client:
        r = await client.post(url, json=body, headers=_headers())
    if r.status_code not in (200, 201):
        raise ReplicateError(f"Replicate POST {model_path} HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


async def _get_prediction(prediction_id: str) -> dict:
    url = f"{_REPLICATE_BASE}/predictions/{prediction_id}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(url, headers=_headers())
    if r.status_code != 200:
        raise ReplicateError(f"Replicate GET HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


async def _poll_until_done(
    prediction_id: str,
    poll_interval_s: float = 2.0,
    max_poll_s: float = 180.0,
) -> dict:
    """Poll jusqu'à status ∈ {succeeded, failed, canceled}. Lève ReplicateTimeout."""
    elapsed = 0.0
    while elapsed < max_poll_s:
        data = await _get_prediction(prediction_id)
        status = data.get("status")
        if status in ("succeeded", "failed", "canceled"):
            return data
        await asyncio.sleep(poll_interval_s)
        elapsed += poll_interval_s
    raise ReplicateTimeout(f"Polling >{max_poll_s}s pour {prediction_id}")


async def _telecharger_image(url: str, timeout_s: float = 30.0) -> bytes:
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.content


# ── API publique : génération d'image ────────────────────────────────────────


async def generer_image_replicate(
    prompt: str,
    mode: ReplicateMode = "standard",
    format_: str = "portrait_4_3",
    seed: Optional[int] = None,
    timeout_s: float = 90.0,
    reference_url: Optional[str] = None,
    reference_strength: float = 0.65,
    brand_lora_url: Optional[str] = None,
    brand_lora_scale: float = 0.85,
    style_recraft: str = "any",   # any | digital_illustration | realistic_image | vector_illustration
) -> bytes:
    """
    Génère 1 image via Replicate. API miroir de image_gen.generer_image.

    Lève ReplicateNotConfigured si token absent (caller fallback).
    Lève ReplicateError pour autres erreurs (timeout, quota…).
    """
    if mode == "sans":
        raise ReplicateError("Mode 'sans' — aucune image à générer")

    # Sélection du modèle selon mode + présence LoRA
    if brand_lora_url and mode in ("premium", "ultra"):
        # Brand LoRA → flux-dev-lora obligatoire (Pro Ultra ne supporte pas LoRA)
        model = _MODEL_FLUX_DEV_LORA
    elif mode == "ultra" or mode == "ultra_plus":
        model = _MODEL_FLUX_PRO_ULTRA
    elif mode == "premium":
        model = _MODEL_FLUX_DEV
    else:
        model = _MODEL_FLUX_SCHNELL

    aspect_ratio = _AR_MAP.get(format_, "3:4")
    payload: dict = {
        "prompt": prompt[:4000],
        "aspect_ratio": aspect_ratio,
        "output_format": "png",
    }
    if seed is not None:
        payload["seed"] = seed

    # IP-Adapter Flux Pro Ultra
    if reference_url and model == _MODEL_FLUX_PRO_ULTRA:
        payload["image_prompt"] = reference_url
        payload["image_prompt_strength"] = max(0.0, min(1.0, reference_strength))
    # Brand LoRA — flux-dev-lora
    if brand_lora_url and model == _MODEL_FLUX_DEV_LORA:
        payload["lora_weights"] = brand_lora_url
        payload["lora_scale"] = max(0.0, min(1.5, brand_lora_scale))
        payload["num_inference_steps"] = 28

    pred = await _create_prediction(model, payload, timeout_s=timeout_s)
    if pred.get("status") in ("starting", "processing"):
        pred = await _poll_until_done(pred["id"], max_poll_s=timeout_s)
    if pred.get("status") != "succeeded":
        raise ReplicateError(f"Replicate {model} : status={pred.get('status')} error={str(pred.get('error'))[:200]}")
    output = pred.get("output")
    # Replicate output est soit string URL soit list[URL]
    img_url = output if isinstance(output, str) else (output[0] if isinstance(output, list) and output else None)
    if not img_url:
        raise ReplicateError(f"Replicate {model} : pas d'output.url")
    return await _telecharger_image(img_url)


async def generer_recraft_replicate(
    prompt: str,
    format_: str = "portrait_4_3",
    style: str = "any",
    svg_pur: bool = False,
    timeout_s: float = 60.0,
) -> bytes:
    """Recraft v3 via Replicate (alt fal.ai) — SOTA illustrations vectorielles.
    Si svg_pur=True → recraft-v3-svg (renvoie un SVG, pas un PNG)."""
    model = _MODEL_RECRAFT_V3_SVG if svg_pur else _MODEL_RECRAFT_V3
    payload = {
        "prompt": prompt[:1000],
        "size": "1024x1024" if format_ == "square_hd" else "1024x1365",
        "style": style,
    }
    pred = await _create_prediction(model, payload, timeout_s=timeout_s)
    if pred.get("status") in ("starting", "processing"):
        pred = await _poll_until_done(pred["id"], max_poll_s=timeout_s)
    if pred.get("status") != "succeeded":
        raise ReplicateError(f"Recraft Replicate : status={pred.get('status')}")
    out = pred.get("output")
    url = out if isinstance(out, str) else (out[0] if isinstance(out, list) and out else None)
    if not url:
        raise ReplicateError("Recraft Replicate : pas d'output")
    return await _telecharger_image(url)


async def generer_ideogram_replicate(
    prompt: str,
    format_: str = "portrait_4_3",
    timeout_s: float = 60.0,
) -> bytes:
    """Ideogram v2 via Replicate (alt fal.ai) — SOTA texte intégré."""
    payload = {
        "prompt": prompt[:1000],
        "aspect_ratio": _AR_MAP.get(format_, "3:4"),
        "style_type": "Auto",
    }
    pred = await _create_prediction(_MODEL_IDEOGRAM_V2, payload, timeout_s=timeout_s)
    if pred.get("status") in ("starting", "processing"):
        pred = await _poll_until_done(pred["id"], max_poll_s=timeout_s)
    if pred.get("status") != "succeeded":
        raise ReplicateError(f"Ideogram Replicate : status={pred.get('status')}")
    out = pred.get("output")
    url = out if isinstance(out, str) else (out[0] if isinstance(out, list) and out else None)
    if not url:
        raise ReplicateError("Ideogram Replicate : pas d'output")
    return await _telecharger_image(url)


# ── Brand LoRA training (Sprint R3) ──────────────────────────────────────────


async def entrainer_lora(
    images_zip_url: str,
    trigger_word: str,
    steps: int = 1000,
    lora_rank: int = 16,
    learning_rate: float = 4e-4,
    timeout_polling_s: float = 1800.0,
) -> dict:
    """
    Lance un training Flux LoRA via Replicate (ostris/flux-dev-lora-trainer).
    Coût ~$5 (vs ~$200 chez fal.ai). Training ~15-30 min selon dataset.

    `images_zip_url` : URL publique d'un ZIP contenant 10-30 images training.
    `trigger_word`   : mot unique injecté dans les prompts pour activer le LoRA
                       (ex: "ACMECORP", "MARQUEX2026").

    Retourne {"status": "succeeded"|"failed", "lora_url": str|None,
              "training_id": str, "error": str|None}.
    """
    if not settings.REPLICATE_API_TOKEN:
        raise ReplicateNotConfigured("REPLICATE_API_TOKEN absent — training impossible")

    # Replicate API training : POST /v1/models/{owner}/{model}/versions/{version_id}/trainings
    # On utilise la dernière version d'ostris/flux-dev-lora-trainer.
    # Pour simplifier on passe par l'API simplifiée /v1/trainings avec destination.
    # Note : Replicate exige un destination (où stocker le LoRA produit).
    # On laisse Replicate gérer le storage (gratuit chez eux).
    url = f"{_REPLICATE_BASE}/models/{_LORA_TRAINER}/predictions"   # alias prédictions
    payload_input = {
        "input_images": images_zip_url,
        "trigger_word": trigger_word,
        "steps": int(max(500, min(2000, steps))),
        "lora_rank": int(lora_rank),
        "learning_rate": float(learning_rate),
        "batch_size": 1,
        "resolution": "1024",
        "autocaption": True,
    }
    pred = await _create_prediction(_LORA_TRAINER, payload_input, timeout_s=120.0)
    pid = pred.get("id")
    if not pid:
        return {"status": "failed", "lora_url": None, "training_id": None,
                "error": "Pas d'id de prediction"}
    final = await _poll_until_done(pid, poll_interval_s=10.0, max_poll_s=timeout_polling_s)
    if final.get("status") != "succeeded":
        return {"status": final.get("status", "failed"), "lora_url": None,
                "training_id": pid, "error": str(final.get("error"))[:500]}
    out = final.get("output") or {}
    # Le trainer renvoie typiquement {"weights": "https://...lora.safetensors", ...}
    lora_url = out.get("weights") if isinstance(out, dict) else None
    if not lora_url and isinstance(out, str):
        lora_url = out
    return {
        "status": "succeeded",
        "lora_url": lora_url, "training_id": pid,
        "error": None,
    }


def is_available() -> bool:
    """True si REPLICATE_API_TOKEN est configuré."""
    return bool(settings.REPLICATE_API_TOKEN)
