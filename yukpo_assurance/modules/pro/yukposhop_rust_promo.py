"""Bridge YukpoShop → Yukpo Rust marketplace pour features promo.

Rust expose les services existants via le router bridge HMAC dédié
(`integrations_yukposhop_promo_routes.rs`, ajouté 2026-05-15) sous
`/api/v1/integrations/yukposhop/...`.

Routes utilisées :
  • POST /loyalty/credit
  • GET  /loyalty/balance
  • GET  /similar
  • POST /abandoned-carts/track
  • POST /flash-promos
  • GET  /global-promos/catalog
  • POST /global-promos/events/{event_id}/entries

HMAC scheme : identique à Piste 1 (sync produits) — header X-Yukpo-Signature
contient base64(HMAC-SHA256(timestamp + "." + body)) avec la clé partagée
`YUKPOSHOP_BRIDGE_HMAC_KEY` (décodée base64 si valide, sinon brute).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json as _json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import httpx

logger = logging.getLogger("yukpo_assurance.pro.yukposhop_rust_promo")

_BRIDGE_PREFIX = "/api/v1/integrations/yukposhop"


def _rust_base_url() -> str:
    """Aligné sur les autres bridges (`RUST_BRIDGE_URL`).

    Pour migrer de Fly vers GCP/autre : changer 1 seule variable d'env (ou
    pointer un domaine custom stable via DNS, sans toucher aux env vars).
    """
    return (
        os.getenv("RUST_BRIDGE_URL")
        or os.getenv("YUKPO_RUST_BASE_URL")
        or "https://yukpo-fly-backend.fly.dev"
    ).rstrip("/")


def _hmac_key() -> Optional[str]:
    return os.getenv("YUKPOSHOP_BRIDGE_HMAC_KEY") or None


def _sign(timestamp: str, body: bytes, key_raw: str) -> str:
    """HMAC-SHA256(timestamp + "." + body) en base64 — aligné Piste 1."""
    try:
        key = base64.b64decode(key_raw)
    except Exception:
        key = key_raw.encode("utf-8")
    msg = timestamp.encode("ascii") + b"." + body
    sig = hmac.new(key, msg, hashlib.sha256).digest()
    return base64.b64encode(sig).decode("ascii")


def _is_enabled() -> bool:
    return (os.getenv("RUST_BRIDGE_ENABLED", "true").lower() == "true") and bool(_hmac_key())


@dataclass
class RustPromoResult:
    success: bool
    rust_id: Optional[str] = None
    error: Optional[str] = None
    raw: Optional[dict[str, Any]] = None


def _build_headers(body: bytes) -> dict:
    ts = str(int(datetime.utcnow().timestamp()))
    sig = _sign(ts, body, _hmac_key() or "")
    return {
        "Content-Type": "application/json",
        "X-Yukpo-Signature": sig,
        "X-Yukpo-Timestamp": ts,
    }


async def _post_rust(path: str, payload: dict, timeout: float = 15.0) -> RustPromoResult:
    if not _is_enabled():
        return RustPromoResult(False, error="Rust bridge désactivé")
    url = f"{_rust_base_url()}{_BRIDGE_PREFIX}{path}"
    body = _json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = _build_headers(body)
    try:
        async with httpx.AsyncClient(timeout=timeout) as cli:
            r = await cli.post(url, content=body, headers=headers)
        if r.status_code >= 400:
            return RustPromoResult(False, error=f"Rust HTTP {r.status_code} : {r.text[:200]}")
        data = r.json() if r.text else {}
        return RustPromoResult(
            True,
            rust_id=str(
                data.get("id") or data.get("event_id") or data.get("flash_sale_id")
                or data.get("entry_id") or data.get("job_id") or ""
            ),
            raw=data,
        )
    except Exception as e:
        return RustPromoResult(False, error=f"réseau : {e}")


async def _get_rust(path: str, params: dict, timeout: float = 10.0) -> tuple[bool, dict]:
    if not _is_enabled():
        return False, {"error": "bridge désactivé"}
    url = f"{_rust_base_url()}{_BRIDGE_PREFIX}{path}"
    # GET → signe une chaîne vide (alignement Rust check_hmac_get)
    headers = _build_headers(b"")
    try:
        async with httpx.AsyncClient(timeout=timeout) as cli:
            r = await cli.get(url, params=params, headers=headers)
        if r.status_code >= 400:
            return False, {"error": f"HTTP {r.status_code}", "body": r.text[:200]}
        return True, r.json() if r.text else {}
    except Exception as e:
        return False, {"error": str(e)}


# ─── Flash sales ────────────────────────────────────────────────────────────


async def creer_flash_sale_rust(
    *, produit_id: int, prix_initial: float, prix_flash: float,
    debut: datetime, fin: datetime, stock_target: int,
    vendeur_email: str, devise: str = "XAF",
) -> RustPromoResult:
    """Crée une vente flash sur Rust (apparaît dans le flux mobile Yukpo +
    section flash-sales du marketplace + notifications push abonnés)."""
    payload = {
        "external_product_id": str(produit_id),
        "vendeur_email": vendeur_email,
        "prix_initial": prix_initial,
        "prix_flash": prix_flash,
        "devise": devise,
        "debut": debut.isoformat(),
        "fin": fin.isoformat(),
        "stock_target": stock_target,
    }
    return await _post_rust("/flash-promos", payload)


# ─── Global promos / Black Friday Yukpo ─────────────────────────────────────


async def joindre_global_promo_rust(
    *, event_id: str, produit_ids: list[int], reduction_pct: int,
    vendeur_email: str,
) -> RustPromoResult:
    """Inscrit des produits YukpoShop à un événement global (Black Friday Yukpo,
    Soldes de Noël, etc.) géré par l'admin Yukpo. Visibilité maximale —
    listing dédié + push notif tous utilisateurs Yukpo."""
    payload = {
        "external_product_ids": [str(p) for p in produit_ids],
        "vendeur_email": vendeur_email,
        "reduction_pct": reduction_pct,
        "origin": "yukposhop",
    }
    return await _post_rust(f"/global-promos/events/{event_id}/entries", payload)


async def lister_global_promos_actives_rust() -> list[dict[str, Any]]:
    """Liste les événements promo globaux ouverts à inscription (commerçant
    YukpoShop voit dans MaBoutique 'Black Friday Yukpo - 28 nov' avec bouton
    'Inscrire mes produits')."""
    ok, data = await _get_rust("/global-promos/catalog", {})
    if not ok:
        logger.info(f"[GlobalPromo] catalog indisponible : {data.get('error')}")
        return []
    return data.get("items") or []


# ─── Loyalty points ─────────────────────────────────────────────────────────


async def crediter_loyalty_rust(
    *, user_email: str, points: int, motif: str = "yukposhop_order",
    reference_id: Optional[str] = None,
) -> RustPromoResult:
    """Crédite N points fidélité sur le compte Yukpo du client après une
    commande YukpoShop. Le client peut ensuite les utiliser pour discount
    sur n'importe quelle boutique Yukpo (LoyaltyService.redeem)."""
    payload = {
        "user_email": user_email,
        "points": int(points),
        "motif": motif,
        "reference_id": reference_id,
        "origin": "yukposhop",
    }
    return await _post_rust("/loyalty/credit", payload)


async def get_balance_loyalty_rust(user_email: str) -> Optional[int]:
    ok, data = await _get_rust("/loyalty/balance", {"user_email": user_email})
    if not ok:
        return None
    try:
        return int(data.get("balance") or 0)
    except Exception:
        return None


# ─── Cross-sell similar ─────────────────────────────────────────────────────


async def chercher_similar_rust(
    *, produit_ids: list[int], limit: int = 6,
) -> list[dict[str, Any]]:
    """Recherche produits similaires pour un panier multi-items. Combine
    `similar` de chaque produit du panier (dédup par id Rust).
    """
    if not _is_enabled() or not produit_ids:
        return []
    out: list[dict[str, Any]] = []
    seen: set = set()
    for pid in produit_ids[:5]:
        ok, data = await _get_rust(
            "/similar",
            {"external_product_id": str(pid), "limit": limit},
        )
        if not ok:
            continue
        for it in data.get("items") or []:
            rid = it.get("id")
            if rid and rid not in seen and len(out) < limit:
                seen.add(rid)
                out.append(it)
    return out


# ─── Abandoned cart trigger ─────────────────────────────────────────────────


async def push_cart_abandoned_rust(
    *, vendeur_email: str, visitor_telephone: str,
    cart_items: list[dict], boutique_slug: str, total: float, devise: str,
) -> RustPromoResult:
    """Pousse un événement 'panier abandonné' vers Rust qui programmera un
    rappel WhatsApp ~2h plus tard (via abandoned_cart_jobs + social-ai
    worker). Récupère 10-15 % des ventes perdues."""
    payload = {
        "vendeur_email": vendeur_email,
        "visitor_telephone": visitor_telephone,
        "boutique_slug": boutique_slug,
        "cart_items": cart_items,
        "total": total,
        "devise": devise,
    }
    return await _post_rust("/abandoned-carts/track", payload)
