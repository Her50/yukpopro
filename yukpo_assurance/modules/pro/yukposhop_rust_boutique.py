"""Piste 6e — Enrichissement boutique via Google Places (côté Rust).

Au moment de `/shop/initialiser`, on appelle Rust pour trouver l'établissement
sur Google Places à partir de nom + ville + pays, et récupérer :
  - place_id, adresse_complete, gps "lat,lng", rating
  - photo_url (1 photo Google)
  - (Phase B : horaires + téléphone via Places Details API)

Best-effort : si Google indisponible, le shop est créé sans enrichissement.
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
from typing import Optional

import httpx

logger = logging.getLogger("yukpo_assurance.pro.rust_boutique")


def _config() -> dict:
    base = os.getenv("RUST_BRIDGE_URL") or \
           "https://yukpo-fly-backend.fly.dev/api/v1/integrations/yukposhop/sync"
    root = base.rsplit("/", 1)[0] if base.endswith("/sync") else base
    return {
        "enabled": (os.getenv("RUST_BRIDGE_ENABLED") or "false").lower() == "true",
        "url": f"{root}/boutique/enrich",
        "hmac_key": os.getenv("RUST_BRIDGE_HMAC_KEY") or "",
        "timeout_s": float(os.getenv("RUST_BRIDGE_TIMEOUT_S") or "10"),
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
class BoutiqueEnrichResult:
    success: bool
    place_id: Optional[str]
    adresse_complete: Optional[str]
    gps: Optional[str]
    rating: Optional[float]
    telephone: Optional[str]
    horaires_json: Optional[dict]
    photo_url: Optional[str]
    error: Optional[str] = None


async def enrichir_boutique_google_places(
    nom_boutique: str,
    *,
    ville: Optional[str] = None,
    pays: str = "CM",
) -> BoutiqueEnrichResult:
    """Best-effort. Retourne un result avec error si Rust/Google indispo."""
    cfg = _config()
    if not cfg["enabled"] or not cfg["hmac_key"]:
        return BoutiqueEnrichResult(False, None, None, None, None, None, None, None,
                                     "RUST_BRIDGE désactivé")

    payload = {"nom_boutique": nom_boutique, "ville": ville, "pays": pays}
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
        if resp.status_code != 200:
            return BoutiqueEnrichResult(
                False, None, None, None, None, None, None, None,
                f"HTTP {resp.status_code} : {resp.text[:200]}",
            )
        data = resp.json()
        return BoutiqueEnrichResult(
            success=bool(data.get("ok")),
            place_id=data.get("place_id"),
            adresse_complete=data.get("adresse_complete"),
            gps=data.get("gps"),
            rating=data.get("rating"),
            telephone=data.get("telephone"),
            horaires_json=data.get("horaires_json"),
            photo_url=data.get("photo_url"),
            error=data.get("error"),
        )
    except Exception as e:
        logger.info(f"[RustBoutique] enrich échec ({e}) — fallback sans enrichissement")
        return BoutiqueEnrichResult(False, None, None, None, None, None, None, None, str(e))
