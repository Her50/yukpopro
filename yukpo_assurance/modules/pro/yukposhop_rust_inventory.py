"""Piste 5 — Sync inventaire YukpoShop -> Yukpo Rust marketplace.

Quand une commande arrive sur le storefront YukpoShop, le stock local est
décrémenté ; on doit AUSSI décrémenter le stock côté Rust marketplace
(où le même produit apparaît via la Piste 1) pour éviter qu'un consommateur
Yukpo achète un produit déjà épuisé.

Architecture :
  - Push HMAC YukpoShop -> Rust (event = "decrement", external_id, delta)
  - Idempotency via event_id (uuid4 généré par YukpoShop)
  - Best-effort : si Rust down, on logue mais l'order YukpoShop reste valide
    (le stock Rust diverge temporairement — sera resync au prochain push
     via Piste 1 quand le produit sera modifié)
  - Pas de retry sur 4xx (Rust dit explicitement "produit inconnu"), retry
    1 fois sur 5xx ou timeout (back-off 3s).

Sens inverse (Rust -> YukpoShop, événement vente marketplace) = Phase B :
nécessite des hooks dans le flow d'order Rust pour POSTer vers YukpoPro
qui décrémentera localement. Pas livré v1.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger("yukpo_assurance.pro.rust_inventory")


def _config() -> dict:
    base_url = (os.getenv("RUST_BRIDGE_URL") or
                "https://yukpo-fly-backend.fly.dev/api/v1/integrations/yukposhop/sync")
    root = base_url.rsplit("/", 1)[0] if base_url.endswith("/sync") else base_url
    return {
        "enabled": (os.getenv("RUST_BRIDGE_ENABLED") or "false").lower() == "true",
        "url": f"{root}/inventory/decrement",
        "hmac_key": os.getenv("RUST_BRIDGE_HMAC_KEY") or "",
        "timeout_s": float(os.getenv("RUST_BRIDGE_TIMEOUT_S") or "10"),
    }


def _sign(body_bytes: bytes, key: str, ts: str) -> str:
    if not key:
        return ""
    try:
        kb = base64.b64decode(key)
    except Exception:
        kb = key.encode("utf-8")
    return base64.b64encode(
        hmac.new(kb, ts.encode("ascii") + b"." + body_bytes, hashlib.sha256).digest()
    ).decode("ascii")


@dataclass
class InventoryDecrementResult:
    success: bool
    event_id: str
    rust_service_id: Optional[int]
    new_stock: Optional[int]
    error: Optional[str] = None


async def decrementer_stock_rust(
    produit_id: int,
    quantite: int,
    *,
    order_numero: Optional[str] = None,
) -> InventoryDecrementResult:
    """Pousse un événement de décrément stock vers Rust marketplace.

    Args :
      produit_id : shop_products.id (external_id côté Rust via Piste 1)
      quantite : nombre d'unités vendues (positif)
      order_numero : pour audit côté Rust

    Returns :
      Best-effort. On ne lève jamais d'exception — le caller continue
      même si Rust down. Le stock divergera jusqu'au prochain sync via
      Piste 1 (re-push complet lors d'une modif produit).
    """
    cfg = _config()
    event_id = str(uuid.uuid4())
    if not cfg["enabled"] or not cfg["hmac_key"]:
        return InventoryDecrementResult(
            False, event_id, None, None, "RUST_BRIDGE désactivé",
        )
    if quantite <= 0:
        return InventoryDecrementResult(
            False, event_id, None, None, "quantite doit être > 0",
        )

    payload = {
        "event_id": event_id,           # idempotency
        "source": "yukposhop",
        "external_id": str(produit_id),
        "delta": -int(quantite),         # négatif = décrément
        "raison": "order_yukposhop",
        "order_numero": order_numero,
        "ts": int(time.time()),
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    ts = str(int(time.time()))
    sig = _sign(body, cfg["hmac_key"], ts)
    headers = {
        "Content-Type": "application/json",
        "X-Yukpo-Signature": sig,
        "X-Yukpo-Timestamp": ts,
        "X-Yukpo-Source": "yukposhop",
    }

    # Tentative + 1 retry sur 5xx/timeout
    last_err: Optional[str] = None
    last_status: Optional[int] = None
    last_data: dict = {}
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=cfg["timeout_s"]) as client:
                resp = await client.post(cfg["url"], content=body, headers=headers)
            last_status = resp.status_code
            if resp.status_code in (200, 201):
                last_data = resp.json()
                return InventoryDecrementResult(
                    success=True,
                    event_id=event_id,
                    rust_service_id=last_data.get("rust_service_id"),
                    new_stock=last_data.get("new_stock"),
                )
            if 400 <= resp.status_code < 500:
                # 4xx = pas la peine de retry (produit inconnu, etc.)
                last_err = f"HTTP {resp.status_code} : {resp.text[:200]}"
                break
            last_err = f"HTTP {resp.status_code} : {resp.text[:200]}"
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_err = f"réseau : {e}"
        except Exception as e:
            last_err = f"inattendu : {e}"
            break
        if attempt == 0:
            import asyncio
            await asyncio.sleep(3.0)

    logger.info(
        f"[RustInventory] decrement produit_id={produit_id} qte={quantite} "
        f"event_id={event_id} ÉCHEC ({last_err}) — sync divergence "
        f"jusqu'au prochain push Piste 1"
    )
    return InventoryDecrementResult(
        success=False,
        event_id=event_id,
        rust_service_id=None,
        new_stock=None,
        error=last_err,
    )
