"""
Vidéo IA — text-to-video pour Sec et Pro (campagnes marketing, teasers,
animations packaging, vidéos promo réseaux sociaux).

Endpoint : POST /api/v1/bureau/video/generer
"""
from __future__ import annotations

import logging
import math
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core.auth import get_current_user, TokenData

router = APIRouter()
logger = logging.getLogger("yukpo_assurance.routes_bureau_video")

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "generated" / "bureau"
_DATA_DIR.mkdir(parents=True, exist_ok=True)


class DemandeVideo(BaseModel):
    prompt: str = Field(..., min_length=10, max_length=2000,
                         description="Description scène (anglais recommandé pour qualité max). "
                                     "Pour vidéos >10s, peut structurer avec 'Plan 1: ... Plan 2: ...' "
                                     "pour contrôler chaque chunk ; sinon découpe narrative auto.")
    duree_s: int = Field(default=5, ge=5, le=60,
                          description="Durée vidéo (5 à 60 secondes). "
                                      "5/10s = un seul appel Kling natif. "
                                      "15-60s = stitching parallèle de N×10s + FFmpeg concat "
                                      "avec crossfade 0.5s (~3 min latence pour 30s ultra).")
    mode: str = Field(default="standard",
                       pattern="^(standard|premium|ultra)$",
                       description="standard=LTX-Video (60 FCFA/5s) | premium=Kling 1.6 std (240 FCFA/5s) | ultra=Kling 1.6 pro (600 FCFA/5s)")
    aspect_ratio: str = Field(default="16:9",
                               pattern="^(16:9|9:16|1:1|4:3)$",
                               description="16:9 desktop, 9:16 reels/stories, 1:1 Instagram feed, 4:3 classique")
    seed: Optional[int] = Field(default=None, ge=0, le=2_147_483_647)
    crossfade_s: float = Field(default=0.5, ge=0.0, le=2.0,
                                description="Durée fondu enchaîné entre clips stitchés (0=cut net). Ignoré si duree_s ≤ 10.")


_FORFAITS_VIDEO_FCFA: dict[str, int] = {
    "standard": 60,    # LTX-Video ~$0.05/5s × 12× marge
    "premium":  240,   # Kling std ~$0.20/5s × 12× marge
    "ultra":    600,   # Kling pro ~$0.50/5s × 12× marge
}


@router.post("/generer", tags=["Bureau — Vidéo IA"])
async def generer_video_endpoint(
    demande: DemandeVideo,
    current_user: TokenData = Depends(get_current_user),
):
    """Génère une vidéo MP4 5-60s via fal.ai (Kling/LTX) ou Replicate fallback.

    • 5-10s : un appel natif Kling, latence 15s (LTX) / 60s (Kling std) / 3min (Kling pro)
    • 15-60s : stitching parallèle de N×10s clips + FFmpeg concat avec crossfade.
              Le prompt peut être structuré en "Plan 1: ... Plan 2: ..." pour
              contrôler chaque chunk ; sinon découpe narrative auto avec marqueurs
              temporels (opening shot / main action / climax / concluding shot).

    Coût : forfait `bureau_video_<mode>` × ceil(duree_s/5) débité avant génération.
    """
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde, debiter_forfait,
    )
    from modules.bureau import video_gen
    import math as _math

    autorise, plan, msg = await verifier_acces_module(
        current_user.user_id, "infographie"
    )
    if not autorise:
        raise HTTPException(403, msg)

    cout_fcfa = _FORFAITS_VIDEO_FCFA.get(demande.mode, 60)
    # Coût = ceil(duree_s / 5) × prix unitaire. Ex : 30s ultra = 6 × 600 = 3600 XAF.
    multiplier = max(1, _math.ceil(demande.duree_s / 5))
    cout_total = cout_fcfa * multiplier

    ok_solde, restants, _ = await verifier_solde(current_user.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")

    t0 = time.time()
    try:
        if demande.duree_s <= 10:
            # Chemin natif : un seul appel API
            mp4_bytes = await video_gen.generer_video(
                prompt=demande.prompt,
                duree_s=demande.duree_s,
                mode=demande.mode,
                aspect_ratio=demande.aspect_ratio,
                seed=demande.seed,
                timeout_s=240 if demande.mode != "ultra" else 480,
            )
        else:
            # Stitching : N×10s clips parallèles + FFmpeg concat
            mp4_bytes = await video_gen.generer_video_long(
                prompt=demande.prompt,
                duree_s=demande.duree_s,
                mode=demande.mode,
                aspect_ratio=demande.aspect_ratio,
                seed=demande.seed,
                crossfade_s=demande.crossfade_s,
            )
    except video_gen.VideoGenNotConfigured:
        raise HTTPException(
            503,
            "Service vidéo non configuré (clés FAL_KEY/REPLICATE_API_TOKEN absentes).",
        )
    except video_gen.VideoGenError as e:
        raise HTTPException(502, f"Génération vidéo échouée : {str(e)[:200]}")
    duree_ms = int((time.time() - t0) * 1000)

    # Sauvegarder MP4 — prefix bureau_ pour routing /bureau/documents +
    # slug du prompt pour filename parlant.
    import re as _re
    import unicodedata as _ud
    _norm = _ud.normalize("NFKD", demande.prompt[:80] or "video")
    _slug = _re.sub(r"_+", "_",
        _re.sub(r"[^a-zA-Z0-9]+", "_", _norm.encode("ascii", "ignore").decode().lower())
    ).strip("_")[:40] or "video"
    fichier_id = f"bureau_video_{current_user.user_id}_{_slug}_{demande.mode}_{int(time.time())}.mp4"
    chemin = _DATA_DIR / fichier_id
    chemin.write_bytes(mp4_bytes)

    # Débit forfait
    try:
        await debiter_forfait(
            current_user.user_id,
            type_forfait=f"bureau_video_{demande.mode}",
            multiplicateur=multiplier,
            module="infographie",
        )
    except Exception as e:
        logger.warning(f"[Vidéo] Débit forfait échoué (non bloquant) : {e}")

    return {
        "ok": True,
        "fichier": fichier_id,
        "fichier_id": fichier_id,
        # Sert via /bureau/documents/ (inline pour MP4 → lecture native browser)
        # Plus simple côté frontend que /bureau/video/fichier/ qui force download.
        "url_telechargement": f"/api/v1/bureau/documents/{fichier_id}",
        "size_kb": round(len(mp4_bytes) / 1024, 1),
        "taille_octets": len(mp4_bytes),
        "duree_generation_ms": duree_ms,
        "mode": demande.mode,
        "duree_video_s": demande.duree_s,
        "duree_s": demande.duree_s,
        "aspect_ratio": demande.aspect_ratio,
        "cout_fcfa": cout_total,
        "nb_clips_stitches": max(1, math.ceil(demande.duree_s / 10)),
    }


@router.get("/fichier/{nom_fichier}", tags=["Bureau — Vidéo IA"])
async def telecharger_video(
    nom_fichier: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Télécharge un MP4 généré. Sécurité : nom_fichier doit contenir l'user_id."""
    if "/" in nom_fichier or "\\" in nom_fichier or ".." in nom_fichier:
        raise HTTPException(400, "Nom fichier invalide")
    if not nom_fichier.endswith(".mp4"):
        raise HTTPException(400, "Type fichier invalide")
    if (
        f"_{current_user.user_id}_" not in nom_fichier
        and current_user.role not in ("admin", "super_admin", "yukpo_owner")
    ):
        raise HTTPException(403, "Accès refusé")
    chemin = _DATA_DIR / nom_fichier
    if not chemin.exists():
        raise HTTPException(404, "Fichier introuvable (peut-être expiré)")
    return FileResponse(
        path=str(chemin), media_type="video/mp4", filename=nom_fichier,
    )
