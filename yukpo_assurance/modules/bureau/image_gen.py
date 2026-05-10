"""
Designer Pro — génération d'images IA via fal.ai.

Quatre modes (Sprint 1.5 ajoute "ultra_plus") :
- "standard"   : Flux schnell                     (4-step,  ~1s,    ~$0.003/img)
- "premium"    : Flux dev                         (28-step, ~5-10s, ~$0.025/img)
- "ultra"      : Flux 1.1 Pro Ultra               (raw cinematic SOTA, ~$0.06/img)
- "ultra_plus" : Ensemble 3 modèles               (Flux Pro Ultra + Recraft v3 +
                                                   Ideogram 2 en parallèle ; vision
                                                   picker Sonnet choisit la meilleure)

Pourquoi ultra_plus :
  - Flux Pro Ultra : photoréaliste cinématique SOTA
  - Recraft v3     : illustrations vectorielles SOTA (logos, icônes, motifs)
  - Ideogram 2     : intégration texte dans visuel SOTA (slogans, baselines)
  Sonnet vision compare les 3 sorties et choisit la mieux adaptée à l'intention
  du prompt → couvre 100% des sujets visuels professionnels avec qualité maximale.

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

ImageMode = Literal["sans", "standard", "premium", "ultra", "ultra_plus"]

_FAL_BASE_URL = "https://fal.run"
_FAL_MODEL_SCHNELL = "fal-ai/flux/schnell"
_FAL_MODEL_DEV = "fal-ai/flux/dev"
_FAL_MODEL_PRO_ULTRA = "fal-ai/flux-pro/v1.1-ultra"
# Sprint 1.5 — Multi-model ensemble
_FAL_MODEL_RECRAFT = "fal-ai/recraft-v3"            # SOTA illustrations vectorielles
_FAL_MODEL_IDEOGRAM = "fal-ai/ideogram/v2"          # SOTA texte intégré au visuel

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
    reference_url: Optional[str] = None,        # Sprint 1.6 — IP-Adapter Flux
    reference_strength: float = 0.65,            # Sprint 1.6 — 0.0-1.0
    brand_lora_url: Optional[str] = None,        # Sprint 1.6 — Brand LoRA path
    brand_lora_scale: float = 0.85,              # Sprint 1.6 — 0.0-1.5
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

    # ultra_plus utilise generer_image_ensemble (3 modèles + vision picker)
    if mode == "ultra_plus":
        return await generer_image_ensemble(
            prompt, format_=format_, timeout_s=timeout_s, seed=seed,
            reference_url=reference_url, reference_strength=reference_strength,
            brand_lora_url=brand_lora_url, brand_lora_scale=brand_lora_scale,
        )
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

    # Sprint 1.6 — IP-Adapter Flux (référence image style)
    # Flux 1.1 Pro Ultra accepte `image_prompt` natif (IP-Adapter intégré).
    # Flux dev accepte `image_url` + `strength` pour image-to-image guidance.
    # Flux schnell ne supporte pas → on ignore silencieusement la référence.
    if reference_url:
        if mode == "ultra":
            payload["image_prompt"] = reference_url
            payload["image_prompt_strength"] = max(0.0, min(1.0, reference_strength))
        elif mode == "premium":
            payload["image_url"] = reference_url
            payload["strength"] = max(0.0, min(1.0, reference_strength))

    # Sprint 1.6 — Brand LoRA (sur Flux dev seulement)
    if brand_lora_url and mode == "premium":
        payload["loras"] = [{
            "path": brand_lora_url,
            "scale": max(0.0, min(1.5, brand_lora_scale)),
        }]

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


# ── Sprint 1.5 — Ensemble multi-modèles (Flux + Recraft + Ideogram) ──────────


async def _appel_fal_modele(
    modele_path: str,
    payload: dict,
    timeout_s: float = 60.0,
) -> Optional[bytes]:
    """Appel générique fal.ai → bytes PNG ou None si échec."""
    api_key = settings.FAL_KEY
    if not api_key:
        return None
    url = f"{_FAL_BASE_URL}/{modele_path}"
    headers = {"Authorization": f"Key {api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.post(url, json=payload, headers=headers)
        if r.status_code != 200:
            logger.warning(f"[image_gen/{modele_path}] HTTP {r.status_code}: {r.text[:120]}")
            return None
        data = r.json()
        images = data.get("images") or []
        if not images:
            return None
        img_url = images[0].get("url")
        if not img_url:
            return None
        async with httpx.AsyncClient(timeout=30.0) as client:
            r_img = await client.get(img_url)
            r_img.raise_for_status()
            return r_img.content
    except Exception as e:
        logger.warning(f"[image_gen/{modele_path}] échec : {e}")
        return None


async def _gen_flux_pro_ultra(
    prompt: str, format_: str, seed: Optional[int],
    reference_url: Optional[str] = None,
    reference_strength: float = 0.65,
) -> Optional[bytes]:
    image_size = _TAILLES_PAR_FORMAT.get(format_, "portrait_4_3")
    ar_map = {
        "square_hd": "1:1", "portrait_4_3": "3:4", "portrait_16_9": "9:16",
        "landscape_4_3": "4:3", "landscape_16_9": "16:9",
    }
    payload: dict = {
        "prompt": prompt[:4000], "num_images": 1, "enable_safety_checker": True,
        "aspect_ratio": ar_map.get(image_size, "3:4"),
        "output_format": "png", "raw": True,
    }
    if seed is not None:
        payload["seed"] = seed
    if reference_url:
        payload["image_prompt"] = reference_url
        payload["image_prompt_strength"] = max(0.0, min(1.0, reference_strength))
    return await _appel_fal_modele(_FAL_MODEL_PRO_ULTRA, payload)


async def _gen_recraft(prompt: str, format_: str, seed: Optional[int]) -> Optional[bytes]:
    """Recraft v3 — SOTA illustrations vectorielles, logos, motifs, icônes.
    Très bon pour visuels stylisés / non-photoréalistes."""
    sz_map = {
        "square_hd": "square_hd", "portrait_4_3": "portrait_4_3",
        "portrait_16_9": "portrait_16_9", "landscape_4_3": "landscape_4_3",
        "landscape_16_9": "landscape_16_9",
    }
    image_size = _TAILLES_PAR_FORMAT.get(format_, "portrait_4_3")
    payload: dict = {
        "prompt": prompt[:1000], "image_size": sz_map.get(image_size, "portrait_4_3"),
        "style": "any",   # any | digital_illustration | realistic_image | vector_illustration
    }
    return await _appel_fal_modele(_FAL_MODEL_RECRAFT, payload)


async def _gen_ideogram(prompt: str, format_: str, seed: Optional[int]) -> Optional[bytes]:
    """Ideogram 2 — SOTA pour visuels avec texte intégré (slogans, baselines,
    headlines, étiquettes typographiques)."""
    image_size = _TAILLES_PAR_FORMAT.get(format_, "portrait_4_3")
    ar_map = {
        "square_hd": "ASPECT_1_1", "portrait_4_3": "ASPECT_3_4",
        "portrait_16_9": "ASPECT_9_16", "landscape_4_3": "ASPECT_4_3",
        "landscape_16_9": "ASPECT_16_9",
    }
    payload: dict = {
        "prompt": prompt[:1000],
        "aspect_ratio": ar_map.get(image_size, "ASPECT_3_4"),
        "style": "auto",   # auto | general | realistic | design | render_3d | anime
        "expand_prompt": False,
    }
    if seed is not None:
        payload["seed"] = seed
    return await _appel_fal_modele(_FAL_MODEL_IDEOGRAM, payload)


async def generer_image_ensemble(
    prompt: str,
    format_: str = "portrait_4_3",
    timeout_s: float = 90.0,
    seed: Optional[int] = None,
    reference_url: Optional[str] = None,
    reference_strength: float = 0.65,
    brand_lora_url: Optional[str] = None,
    brand_lora_scale: float = 0.85,
) -> bytes:
    """
    Sprint 1.5 — Ensemble 3 modèles en parallèle :
      - Flux 1.1 Pro Ultra : photoréaliste cinématique
      - Recraft v3         : illustrations vectorielles SOTA
      - Ideogram 2         : intégration texte SOTA

    Sonnet vision picker compare les 3 sorties et choisit la mieux adaptée
    à l'intention du prompt (photo / illustration / texte+visuel).

    Lève ImageGenError si les 3 échouent. Sinon retourne la meilleure.
    """
    api_key = settings.FAL_KEY
    if not api_key:
        raise ImageGenNotConfigured("FAL_KEY non configuré")

    # Sprint 1.6 — IP-Adapter passé à Flux Pro Ultra (le seul des 3 qui le supporte
    # nativement via image_prompt). Recraft et Ideogram fonctionnent au prompt seul.
    # Brand LoRA n'est pas appliquée en mode ensemble (les 3 modèles ne partagent
    # pas le même format de LoRA — Brand LoRA est réservée au mode premium Flux dev).
    flux_t, recraft_t, ideogram_t = await asyncio.gather(
        _gen_flux_pro_ultra(prompt, format_, seed,
                             reference_url=reference_url,
                             reference_strength=reference_strength),
        _gen_recraft(prompt, format_, seed),
        _gen_ideogram(prompt, format_, seed),
        return_exceptions=False,
    )
    candidates: list[tuple[str, bytes]] = [
        (lbl, b) for lbl, b in (
            ("flux_pro_ultra", flux_t),
            ("recraft_v3", recraft_t),
            ("ideogram_v2", ideogram_t),
        ) if b
    ]
    if not candidates:
        raise ImageGenError("Ensemble : les 3 modèles ont échoué")
    if len(candidates) == 1:
        logger.info(f"[image_gen/ensemble] 1 candidat survivant ({candidates[0][0]})")
        return candidates[0][1]

    # Sonnet vision picker
    try:
        from core.ia_client import ia_client
        scores: dict[str, int] = {}
        for label, img in candidates:
            b64 = base64.b64encode(img).decode("ascii")
            try:
                rep = await ia_client.analyser_image_vision(
                    image_base64=b64, mime_type="image/png",
                    prompt=(
                        f"Pour le prompt : « {prompt[:300]} »\n\n"
                        f"Note cette image générée par IA sur 100, en évaluant :\n"
                        f"  - Qualité technique (résolution, netteté, absence d'artefact)\n"
                        f"  - Fidélité au prompt (sujet, ambiance, composition demandée)\n"
                        f"  - Adéquation au type de visuel (photo / illustration / typo)\n"
                        f"  - Impact pro / niveau Adobe-Canva\n"
                        f"Réponds par UN SEUL nombre entre 0 et 100. Pas d'explication."
                    ),
                )
                txt = (rep.contenu or "").strip()
                scores[label] = int("".join(c for c in txt if c.isdigit())[:3] or "0")
            except Exception as e:
                logger.debug(f"[image_gen/ensemble] note {label} échouée : {e}")
                scores[label] = 0
        best_label = max(scores, key=scores.get)
        best_img = next(b for lbl, b in candidates if lbl == best_label)
        logger.info(
            f"[image_gen/ensemble] picker scores : {scores} → {best_label} sélectionné"
        )
        return best_img
    except Exception as e:
        logger.debug(f"[image_gen/ensemble] picker fallback (premier) : {e}")
        return candidates[0][1]


async def generer_images_batch(
    prompts: list[tuple[str, str]],   # (prompt, format)
    mode: ImageMode = "standard",
    concurrence: int = 3,
    nb_variantes: int = 1,
    reference_url: Optional[str] = None,        # Sprint 1.6
    reference_strength: float = 0.65,
    brand_lora_url: Optional[str] = None,        # Sprint 1.6
    brand_lora_scale: float = 0.85,
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
                return await generer_image(
                    p, mode=mode, format_=fmt, seed=seed,
                    reference_url=reference_url,
                    reference_strength=reference_strength,
                    brand_lora_url=brand_lora_url,
                    brand_lora_scale=brand_lora_scale,
                )
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
