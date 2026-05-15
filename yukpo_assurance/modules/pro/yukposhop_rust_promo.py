"""Bridge YukpoShop → Yukpo Rust marketplace pour features promo.

Rust expose déjà toutes ces features (audit du 2026-05-15) :
  • Flash sales : POST /api/flash-promos (table live_flash_sales)
  • Global promos / Black Friday : POST /api/global-promos/events (table global_promo_events)
  • Similar / cross-sell : SimilarProductsService
  • Loyalty : LoyaltyService (table loyalty_points)
  • Abandoned cart : social-ai/abandoned-carts + WhatsApp recovery

Cette couche évite toute duplication Python — on push les events vers Rust qui
fait le travail. HMAC bridge identique à Piste 1 (YUKPOSHOP_BRIDGE_HMAC_KEY).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import httpx

logger = logging.getLogger("yukpo_assurance.pro.yukposhop_rust_promo")


def _rust_base_url() -> str:
    return os.getenv("YUKPO_RUST_BASE_URL", "https://yukpo-fly-backend.fly.dev").rstrip("/")


def _hmac_key() -> Optional[str]:
    return os.getenv("YUKPOSHOP_BRIDGE_HMAC_KEY") or None


def _sign(body: bytes, key: str) -> str:
    return hmac.new(key.encode(), body, hashlib.sha256).hexdigest()


def _is_enabled() -> bool:
    return (os.getenv("RUST_BRIDGE_ENABLED", "true").lower() == "true") and bool(_hmac_key())


@dataclass
class RustPromoResult:
    success: bool
    rust_id: Optional[str] = None
    error: Optional[str] = None
    raw: Optional[dict[str, Any]] = None


async def _call_rust(path: str, payload: dict, timeout: float = 15.0) -> RustPromoResult:
    if not _is_enabled():
        return RustPromoResult(False, error="Rust bridge désactivé")
    key = _hmac_key() or ""
    url = f"{_rust_base_url()}{path}"
    import json as _json
    body = _json.dumps(payload, ensure_ascii=False).encode("utf-8")
    sig = _sign(body, key)
    headers = {
        "Content-Type": "application/json",
        "X-YukpoShop-Signature": sig,
        "X-YukpoShop-Timestamp": str(int(datetime.utcnow().timestamp())),
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as cli:
            r = await cli.post(url, content=body, headers=headers)
        if r.status_code >= 400:
            return RustPromoResult(False, error=f"Rust HTTP {r.status_code} : {r.text[:200]}")
        data = r.json() if r.text else {}
        return RustPromoResult(
            True,
            rust_id=str(data.get("id") or data.get("event_id") or data.get("flash_sale_id") or ""),
            raw=data,
        )
    except Exception as e:
        return RustPromoResult(False, error=f"réseau : {e}")


# ─── Flash sales ────────────────────────────────────────────────────────────


async def creer_flash_sale_rust(
    *, produit_id: int, prix_initial: float, prix_flash: float,
    debut: datetime, fin: datetime, stock_target: int,
    vendeur_email: str, devise: str = "XAF",
) -> RustPromoResult:
    """Crée une vente flash sur Rust (apparaît dans le flux mobile Yukpo +
    section flash-sales du marketplace + notifications push abonnés)."""
    payload = {
        "external_product_id": produit_id,
        "vendeur_email": vendeur_email,
        "prix_initial": prix_initial,
        "prix_flash": prix_flash,
        "devise": devise,
        "debut": debut.isoformat(),
        "fin": fin.isoformat(),
        "stock_target": stock_target,
        "origin": "yukposhop",
    }
    return await _call_rust("/api/flash-promos", payload)


# ─── Global promos / Black Friday Yukpo ─────────────────────────────────────


async def joindre_global_promo_rust(
    *, event_id: str, produit_ids: list[int], reduction_pct: int,
    vendeur_email: str,
) -> RustPromoResult:
    """Inscrit des produits YukpoShop à un événement global (Black Friday Yukpo,
    Soldes de Noël, etc.) géré par l'admin Yukpo. Visibilité maximale —
    listing dédié + push notif tous utilisateurs Yukpo."""
    payload = {
        "external_product_ids": produit_ids,
        "vendeur_email": vendeur_email,
        "reduction_pct": reduction_pct,
        "origin": "yukposhop",
    }
    return await _call_rust(f"/api/global-promos/events/{event_id}/entries", payload)


async def lister_global_promos_actives_rust() -> list[dict[str, Any]]:
    """Liste les événements promo globaux ouverts à inscription (commerçant
    YukpoShop voit dans MaBoutique 'Black Friday Yukpo - 28 nov' avec bouton
    'Inscrire mes produits')."""
    if not _is_enabled():
        return []
    try:
        async with httpx.AsyncClient(timeout=10.0) as cli:
            r = await cli.get(f"{_rust_base_url()}/api/global-promos/catalog")
        if r.status_code == 200:
            data = r.json()
            return data.get("events") or data if isinstance(data, list) else []
    except Exception as e:
        logger.warning(f"[GlobalPromo] catalog fail : {e}")
    return []


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
    return await _call_rust("/api/loyalty/credit", payload)


async def get_balance_loyalty_rust(user_email: str) -> Optional[int]:
    if not _is_enabled():
        return None
    try:
        async with httpx.AsyncClient(timeout=8.0) as cli:
            r = await cli.get(
                f"{_rust_base_url()}/api/loyalty/balance",
                params={"user_email": user_email},
            )
        if r.status_code == 200:
            return int(r.json().get("balance") or 0)
    except Exception:
        pass
    return None


# ─── Cross-sell similar (déjà existant Rust /produits/{id}/similar) ─────────


async def chercher_similar_rust(
    *, produit_ids: list[int], limit: int = 6,
) -> list[dict[str, Any]]:
    """Recherche produits similaires pour un panier multi-items. Combine
    `similar` de chaque produit du panier (dédup par id Rust).
    """
    if not _is_enabled() or not produit_ids:
        return []
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    async with httpx.AsyncClient(timeout=8.0) as cli:
        for pid in produit_ids[:5]:
            try:
                # Le service_id Rust est dans external_product_links — on utilise
                # ici l'API publique que le storefront panier appellera.
                r = await cli.get(
                    f"{_rust_base_url()}/api/services/search/similar",
                    params={"external_product_id": pid, "limit": limit},
                )
                if r.status_code != 200:
                    continue
                items = r.json().get("items") or []
                for it in items:
                    rid = it.get("id")
                    if rid and rid not in seen and len(out) < limit:
                        seen.add(rid)
                        out.append(it)
            except Exception:
                continue
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
        "origin": "yukposhop",
    }
    return await _call_rust("/api/social-ai/abandoned-carts/track", payload)
