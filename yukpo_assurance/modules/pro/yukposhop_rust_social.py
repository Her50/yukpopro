"""Piste 4 — Distribution sociale unifiée via le marketplace Yukpo Rust.

Au lieu de dupliquer la logique OAuth Meta/IG/etc. côté YukpoPro Python
(`shop_social_sync.py`), on délègue à Yukpo Rust qui possède déjà les
credentials de chaque vendeur et les workers de publication.

Architecture :
  - Auth : même clé HMAC partagée que la Piste 1 (RUST_BRIDGE_HMAC_KEY)
  - 2 endpoints Rust exposés :
      GET  /api/v1/integrations/yukposhop/social-status?email=...
      POST /api/v1/integrations/yukposhop/distribute
  - Best-effort : si Rust est down, le module retourne des valeurs neutres
    (platforms vides / distribution non lancée) et le caller décide.

Pré-requis :
  - Piste 1 (bridge sync) déployée côté Rust pour que `external_product_links`
    soit alimenté. Sinon Rust ne peut pas résoudre les external_ids YukpoShop
    en rust_service_id.
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

logger = logging.getLogger("yukpo_assurance.pro.rust_social")


# ─── Config (partage avec rust_bridge) ──────────────────────────────────────

def _config() -> dict[str, Any]:
    base_url = os.getenv("RUST_BRIDGE_URL") or \
               "https://yukpo-fly-backend.fly.dev/api/v1/integrations/yukposhop/sync"
    # On enlève le suffixe "/sync" pour avoir le préfixe commun
    root = base_url.rsplit("/", 1)[0] if base_url.endswith("/sync") else base_url
    return {
        "enabled": (os.getenv("RUST_BRIDGE_ENABLED") or "false").lower() == "true",
        "url_social_status": f"{root}/social-status",
        "url_distribute": f"{root}/distribute",
        "hmac_key": os.getenv("RUST_BRIDGE_HMAC_KEY") or "",
        "timeout_s": float(os.getenv("RUST_BRIDGE_TIMEOUT_S") or "12"),
    }


def _sign(body_bytes: bytes, hmac_key: str, timestamp: str) -> str:
    """HMAC-SHA256(timestamp + "." + body) base64. Cf. Piste 1 yukposhop_rust_bridge."""
    if not hmac_key:
        return ""
    try:
        key = base64.b64decode(hmac_key)
    except Exception:
        key = hmac_key.encode("utf-8")
    msg = timestamp.encode("ascii") + b"." + body_bytes
    return base64.b64encode(hmac.new(key, msg, hashlib.sha256).digest()).decode("ascii")


def _headers(body_bytes: bytes) -> dict[str, str]:
    cfg = _config()
    ts = str(int(time.time()))
    sig = _sign(body_bytes, cfg["hmac_key"], ts)
    return {
        "Content-Type": "application/json",
        "X-Yukpo-Signature": sig,
        "X-Yukpo-Timestamp": ts,
        "X-Yukpo-Source": "yukposhop",
    }


# ─── Status comptes connectés ───────────────────────────────────────────────

@dataclass
class SocialPlatformStatus:
    platform: str           # facebook | instagram | whatsapp | tiktok | youtube
    account_name: Optional[str]
    is_active: bool


@dataclass
class SocialStatusResult:
    ok: bool
    rust_user_id: Optional[int]
    platforms: list[SocialPlatformStatus]
    connect_url: str
    error: Optional[str] = None


async def get_social_status(vendeur_email: str) -> SocialStatusResult:
    """Demande à Rust si le commerçant (identifié par email) a connecté
    des comptes Meta/IG/etc. côté Yukpo. Permet à l'UI YukpoShop d'afficher :
      - bouton "Publier sur Facebook" (si fb connecté)
      - bouton "Connecter Meta" → redirige vers connect_url côté Rust
    """
    cfg = _config()
    if not cfg["enabled"] or not cfg["hmac_key"]:
        return SocialStatusResult(
            ok=False, rust_user_id=None, platforms=[],
            connect_url="", error="RUST_BRIDGE désactivé",
        )

    # HMAC sur la query string canonique "email=..."
    synth_body = f"email={vendeur_email}".encode("utf-8")
    hdrs = _headers(synth_body)

    try:
        async with httpx.AsyncClient(timeout=cfg["timeout_s"]) as client:
            resp = await client.get(
                cfg["url_social_status"],
                params={"email": vendeur_email},
                headers=hdrs,
            )
        if resp.status_code != 200:
            return SocialStatusResult(
                ok=False, rust_user_id=None, platforms=[],
                connect_url="", error=f"HTTP {resp.status_code} : {resp.text[:200]}",
            )
        data = resp.json()
        platforms = [
            SocialPlatformStatus(
                platform=p.get("platform", ""),
                account_name=p.get("account_name"),
                is_active=bool(p.get("is_active", True)),
            )
            for p in (data.get("platforms") or [])
            if isinstance(p, dict)
        ]
        return SocialStatusResult(
            ok=True,
            rust_user_id=data.get("rust_user_id"),
            platforms=platforms,
            connect_url=data.get("connect_url") or "",
        )
    except (httpx.TimeoutException, httpx.NetworkError) as e:
        return SocialStatusResult(
            ok=False, rust_user_id=None, platforms=[],
            connect_url="", error=f"réseau : {e}",
        )
    except Exception as e:
        logger.warning(f"[RustSocial] status inattendu : {e}")
        return SocialStatusResult(
            ok=False, rust_user_id=None, platforms=[],
            connect_url="", error=f"inattendu : {e}",
        )


# ─── Distribution ───────────────────────────────────────────────────────────

@dataclass
class DistributeResult:
    success: bool
    jobs_created: int
    products_resolved: int
    platforms: list[str]
    note: str
    error: Optional[str] = None


async def distribuer_produits(
    vendeur_email: str,
    produit_ids: list[int],
    platforms: list[str],
    *,
    message_template: Optional[str] = None,
) -> DistributeResult:
    """Lance via Rust la publication de N produits YukpoShop vers M
    plateformes sociales (Meta/IG/WA/TikTok/YouTube selon ce que le user
    a connecté).

    Rust résout chaque produit_id (= shop_products.id) en rust_service_id
    via la table external_product_links (Piste 1). Puis enqueue un job
    dans yukposhop_distribution_requests qu'un worker Rust traite ensuite.

    Pré-requis : les produits doivent avoir été pushés via Piste 1
    (rust_sync_status='synced') sinon Rust ne peut pas les résoudre.
    """
    cfg = _config()
    if not cfg["enabled"] or not cfg["hmac_key"]:
        return DistributeResult(
            success=False, jobs_created=0, products_resolved=0,
            platforms=platforms, note="", error="RUST_BRIDGE désactivé",
        )
    if not produit_ids or not platforms:
        return DistributeResult(
            success=False, jobs_created=0, products_resolved=0,
            platforms=platforms, note="",
            error="produit_ids et platforms requis (>=1 chacun)",
        )

    payload = {
        "vendeur_email": vendeur_email,
        "external_ids": [str(pid) for pid in produit_ids],
        "platforms": platforms,
        "message_template": message_template,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    hdrs = _headers(body)

    try:
        async with httpx.AsyncClient(timeout=cfg["timeout_s"]) as client:
            resp = await client.post(cfg["url_distribute"], content=body, headers=hdrs)
        if resp.status_code not in (200, 201):
            return DistributeResult(
                success=False, jobs_created=0, products_resolved=0,
                platforms=platforms, note="",
                error=f"HTTP {resp.status_code} : {resp.text[:200]}",
            )
        data = resp.json()
        return DistributeResult(
            success=bool(data.get("ok", True)),
            jobs_created=int(data.get("jobs_created", 0)),
            products_resolved=int(data.get("products_resolved", 0)),
            platforms=data.get("platforms") or platforms,
            note=str(data.get("note") or ""),
        )
    except (httpx.TimeoutException, httpx.NetworkError) as e:
        return DistributeResult(
            success=False, jobs_created=0, products_resolved=0,
            platforms=platforms, note="", error=f"réseau : {e}",
        )
    except Exception as e:
        logger.warning(f"[RustSocial] distribute inattendu : {e}")
        return DistributeResult(
            success=False, jobs_created=0, products_resolved=0,
            platforms=platforms, note="", error=f"inattendu : {e}",
        )
