"""Piste 6 — Génération vidéo pub IA pour un produit YukpoShop via Yukpo Rust.

Délègue à Rust (qui possède le service Remotion renderer + IA video) la
génération d'une vidéo courte 5-60s à partir des photos + titre + prix
+ caption IA.

Architecture :
  - Push HMAC vers /api/v1/integrations/yukposhop/video/generate
  - Rust : compose un projet Remotion (photos + texte animé + musique
    libre de droits), rend en MP4 vertical 9:16 (optimal pour VideoFeed
    mobile Yukpo + Reels/TikTok/Shorts).
  - Retour : video_url (S3/R2 hébergé Rust) + thumbnail_url
  - Best-effort : si Rust down, retourne error et le caller raise.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx

logger = logging.getLogger("yukpo_assurance.pro.rust_video")


def _config() -> dict:
    base = os.getenv("RUST_BRIDGE_URL") or \
           "https://yukpo-fly-backend.fly.dev/api/v1/integrations/yukposhop/sync"
    root = base.rsplit("/", 1)[0] if base.endswith("/sync") else base
    return {
        "enabled": (os.getenv("RUST_BRIDGE_ENABLED") or "false").lower() == "true",
        "url": f"{root}/video/generate",
        "hmac_key": os.getenv("RUST_BRIDGE_HMAC_KEY") or "",
        "timeout_s": float(os.getenv("RUST_VIDEO_TIMEOUT_S") or "60"),  # rendu = lent
    }


def _sign(body: bytes, key: str, ts: str) -> str:
    if not key:
        return ""
    try:
        kb = base64.b64decode(key)
    except Exception:
        kb = key.encode("utf-8")
    return base64.b64encode(
        hmac.new(kb, ts.encode("ascii") + b"." + body, hashlib.sha256).digest()
    ).decode("ascii")


@dataclass
class VideoResult:
    success: bool
    video_url: Optional[str]
    thumbnail_url: Optional[str]
    duration_s: Optional[int]
    duree_render_s: Optional[int]
    error: Optional[str] = None


async def generer_video_produit_via_rust(
    produit: Any,    # ShopProductDB
    *,
    ton: str = "dynamique",
    duree_s: int = 15,
) -> VideoResult:
    cfg = _config()
    if not cfg["enabled"] or not cfg["hmac_key"]:
        return VideoResult(False, None, None, None, None,
                            "RUST_BRIDGE désactivé (génération vidéo Rust hors-ligne)")

    photos = produit.photos_urls_json or []
    if not isinstance(photos, list) or not photos:
        return VideoResult(False, None, None, None, None,
                            "Aucune photo source pour générer la vidéo")

    payload = {
        "source": "yukposhop",
        "external_id": str(produit.id),
        "titre": produit.titre,
        "prix": float(produit.prix_unit_promo or produit.prix_unit or 0),
        "devise": produit.devise or "XAF",
        "photos_urls": [str(p) for p in photos if isinstance(p, str)][:5],
        "description": (produit.description_longue or produit.description_courte or "")[:600],
        "ton": ton,
        "duree_s": int(duree_s),
        "format": "vertical_9_16",   # optimal mobile / Reels / Shorts
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    ts = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        "X-Yukpo-Signature": _sign(body, cfg["hmac_key"], ts),
        "X-Yukpo-Timestamp": ts,
        "X-Yukpo-Source": "yukposhop",
    }

    try:
        async with httpx.AsyncClient(timeout=cfg["timeout_s"]) as client:
            resp = await client.post(cfg["url"], content=body, headers=headers)
        if resp.status_code not in (200, 201):
            return VideoResult(False, None, None, None, None,
                                f"HTTP {resp.status_code} : {resp.text[:200]}")
        data = resp.json()
        return VideoResult(
            success=bool(data.get("ok")),
            video_url=data.get("video_url"),
            thumbnail_url=data.get("thumbnail_url"),
            duration_s=data.get("duration_s"),
            duree_render_s=data.get("duree_render_s"),
            error=data.get("error"),
        )
    except Exception as e:
        logger.warning(f"[RustVideo] échec : {e}")
        return VideoResult(False, None, None, None, None, str(e))
