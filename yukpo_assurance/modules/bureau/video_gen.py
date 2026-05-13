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


# ─── Vidéo longue durée (15s → 60s) via stitching multi-clips ─────────────

import math
import os
import subprocess
import tempfile


def _decouper_prompt_en_plans(prompt: str, n_plans: int) -> list[str]:
    """Découpe un prompt en N plans cohérents.

    Si l'user a explicitement structuré son prompt avec "Plan 1: ... Plan 2:..."
    ou "Scène 1: ... Scène 2:...", on extrait ces blocs. Sinon, on ajoute un
    préfixe progression à un prompt unique pour donner continuité narrative
    aux N clips générés par Kling (chaque clip = même prompt + un hint de
    moment dans l'histoire).
    """
    import re
    # Pattern Plan/Scène N
    pattern = re.compile(
        r"(?:^|\n)\s*(?:plan|sc[èe]ne|shot|étape|seq)\s*\d+\s*[:.\)\-]\s*(.+?)(?=\n\s*(?:plan|sc[èe]ne|shot|étape|seq)\s*\d+|$)",
        re.IGNORECASE | re.DOTALL,
    )
    matches = [m.strip() for m in pattern.findall(prompt) if m.strip()]
    if len(matches) >= n_plans:
        return matches[:n_plans]
    if len(matches) > 0:
        # User a donné quelques plans mais pas assez → on étend avec
        # variations sur le dernier
        out = list(matches)
        while len(out) < n_plans:
            out.append(matches[-1] + f" (suite plan {len(out) + 1})")
        return out

    # Auto-narratif : ajoute marqueurs temporels au prompt unique
    repere = [
        "opening shot, establishing the scene",
        "main action unfolding",
        "rising tension, dynamic motion",
        "climax of the action",
        "transition to next moment",
        "concluding shot, final composition",
    ]
    return [
        f"{prompt.strip()} — {repere[i] if i < len(repere) else 'next moment'}"
        for i in range(n_plans)
    ]


async def generer_video_long(
    prompt: str,
    duree_s: int,
    mode: str = "premium",
    aspect_ratio: str = "16:9",
    seed: Optional[int] = None,
    crossfade_s: float = 0.5,
) -> bytes:
    """
    Génère une vidéo longue (15s → 60s) par stitching parallèle de N clips
    de 10s + concat FFmpeg avec crossfade.

    Algorithme :
      1. Découpe duree_s en chunks de 10s : N = ceil(duree_s/10).
         (Pour duree_s=15 → 2 clips de 10s, le 2e tronqué à 5s)
      2. Découpe le prompt en N plans narratifs (détecte "Plan N: ..." ou
         génère des marqueurs temporels auto).
      3. Génère N clips en parallèle via fal.ai Kling (asyncio.gather).
         Seed varie de +1 par clip pour cohérence visuelle progressive.
      4. Écrit chaque clip sur disque temporaire.
      5. FFmpeg concat avec filter xfade (crossfade 0.5s) → MP4 final.

    Returns: MP4 bytes.
    """
    if duree_s <= 10:
        return await generer_video(
            prompt, duree_s=duree_s, mode=mode,
            aspect_ratio=aspect_ratio, seed=seed,
        )

    n_clips = math.ceil(duree_s / 10)
    duree_par_clip = 10  # Kling cap natif
    # Le dernier clip est tronqué à la sortie pour matcher duree_s exact :
    # ex 25s → 3 clips de 10s, on trim les 5 dernières secondes du dernier
    duree_finale_target = float(duree_s)

    plans = _decouper_prompt_en_plans(prompt, n_clips)
    base_seed = seed if seed is not None else int.from_bytes(os.urandom(2), "little")

    logger.info(
        f"[video_gen/long] {duree_s}s = {n_clips} clips × 10s, mode={mode}, "
        f"plans détectés/générés = {len(plans)}"
    )

    # Génération parallèle (×N appels fal.ai concurrents)
    async def _one(idx: int, plan_prompt: str) -> bytes:
        return await generer_video(
            plan_prompt, duree_s=duree_par_clip, mode=mode,
            aspect_ratio=aspect_ratio, seed=base_seed + idx,
            timeout_s=300,
        )

    clips_bytes = await asyncio.gather(
        *(_one(i, p) for i, p in enumerate(plans)),
        return_exceptions=True,
    )
    # Échec partiel → on garde ce qui marche, on échoue si rien n'a marché
    valides: list[bytes] = []
    for i, c in enumerate(clips_bytes):
        if isinstance(c, BaseException):
            logger.warning(f"[video_gen/long] clip {i+1}/{n_clips} échec : {c}")
            continue
        valides.append(c)
    if not valides:
        raise VideoGenError("Tous les clips ont échoué — vidéo longue impossible")
    if len(valides) < n_clips:
        logger.warning(
            f"[video_gen/long] dégrade {n_clips}→{len(valides)} clips (échecs partiels)"
        )

    # Concat FFmpeg
    return await asyncio.to_thread(
        _stitch_clips_ffmpeg, valides, crossfade_s, duree_finale_target,
    )


def _stitch_clips_ffmpeg(
    clips: list[bytes],
    crossfade_s: float,
    duree_target_s: float,
) -> bytes:
    """Concatène N clips MP4 en un seul via FFmpeg, avec crossfade optionnel.

    Si crossfade_s > 0 : utilise filter_complex `xfade` (transitions fluides).
    Sinon : `concat` demuxer (fast, mais coupures dures aux joints).

    Trim la sortie à `duree_target_s` pour matcher exactement la durée
    demandée (ex: 5×10s = 50s d'entrée → trim à 45s si target=45).
    """
    if len(clips) == 1:
        return clips[0]

    with tempfile.TemporaryDirectory(prefix="yukpo_vid_stitch_") as tmpdir:
        paths: list[str] = []
        for i, content in enumerate(clips):
            p = os.path.join(tmpdir, f"clip_{i:02d}.mp4")
            with open(p, "wb") as f:
                f.write(content)
            paths.append(p)

        out_path = os.path.join(tmpdir, "out.mp4")

        if crossfade_s > 0:
            # Construit dynamiquement la chaîne xfade pour N inputs.
            # Chaque clip est ~10s, offset = 10 - crossfade pour chevaucher.
            inputs = []
            for p in paths:
                inputs += ["-i", p]
            duree_par_clip = 10.0  # cohérent avec generer_video_long
            offset = duree_par_clip - crossfade_s
            filtre_v = ""
            filtre_a = ""
            prev_v = "[0:v]"
            prev_a = "[0:a]"
            for i in range(1, len(paths)):
                cur_offset = i * offset
                next_v = f"[v{i}]"
                next_a = f"[a{i}]"
                filtre_v += (
                    f"{prev_v}[{i}:v]xfade=transition=fade:"
                    f"duration={crossfade_s}:offset={cur_offset:.3f}{next_v};"
                )
                filtre_a += (
                    f"{prev_a}[{i}:a]acrossfade=duration={crossfade_s}{next_a};"
                )
                prev_v = next_v
                prev_a = next_a
            filtre_complet = filtre_v + filtre_a
            # Retire le dernier ; et map les dernières refs
            filtre_complet = filtre_complet.rstrip(";")
            cmd = ["ffmpeg", "-y", *inputs,
                   "-filter_complex", filtre_complet,
                   "-map", prev_v, "-map", prev_a,
                   "-t", f"{duree_target_s:.3f}",
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                   "-c:a", "aac", "-b:a", "128k",
                   out_path]
        else:
            # Concat demuxer fast — pas de crossfade, joints francs.
            list_path = os.path.join(tmpdir, "list.txt")
            with open(list_path, "w") as f:
                for p in paths:
                    f.write(f"file '{p}'\n")
            cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                   "-i", list_path,
                   "-t", f"{duree_target_s:.3f}",
                   "-c", "copy", out_path]

        try:
            res = subprocess.run(
                cmd, capture_output=True, timeout=180,
                check=False,
            )
            if res.returncode != 0:
                # Si xfade échoue (codec mismatch), fallback concat
                if crossfade_s > 0:
                    logger.warning(
                        f"[video_gen/stitch] xfade KO, fallback concat. "
                        f"stderr={res.stderr.decode('utf-8', 'ignore')[:300]}"
                    )
                    return _stitch_clips_ffmpeg(clips, crossfade_s=0.0,
                                                duree_target_s=duree_target_s)
                raise VideoGenError(
                    f"FFmpeg concat KO (rc={res.returncode}) : "
                    f"{res.stderr.decode('utf-8', 'ignore')[:300]}"
                )
        except subprocess.TimeoutExpired:
            raise VideoGenError("FFmpeg concat timeout 180s")
        except FileNotFoundError:
            raise VideoGenError(
                "ffmpeg binary introuvable dans le container — "
                "ajouter `apt-get install -y ffmpeg` au Dockerfile"
            )

        with open(out_path, "rb") as f:
            return f.read()
