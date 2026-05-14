"""Piste 2 — Pull recherche Yukpo Rust marketplace pour cross-sell storefront.

Quand on génère le storefront d'un commerçant YukpoShop, on demande au
marketplace Rust quels autres services/produits proches pourraient intéresser
le visiteur, et on injecte un bloc « Autres marchands près de chez vous »
dans la page home + chaque page produit.

Architecture :
  - PULL GET vers https://yukpo-fly-backend.fly.dev/api/search/universal?q=...
  - Pas d'auth requise (endpoint public)
  - Cache in-process 30 min (clé = hash des params) pour ne pas marteler
    Rust quand on régénère le storefront plusieurs fois rapidement
  - Best-effort : si Rust est down, timeout, ou renvoie 5xx → on retourne
    [] silencieusement et le storefront se génère sans la section cross-sell.
  - Pas de cache Redis pour rester simple (le cache in-process suffit pour
    le pattern « publier 2-3 fois en 30 min puis tranquille »)

Configuration :
  - RUST_SEARCH_URL : URL complète (défaut https://yukpo-fly-backend.fly.dev/api/search/universal)
  - RUST_SEARCH_ENABLED : "true"/"false" — kill switch global (défaut true)
  - RUST_SEARCH_TIMEOUT_S : timeout HTTP (défaut 6s)
  - RUST_SEARCH_TTL_S : durée de vie du cache (défaut 1800 = 30 min)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger("yukpo_assurance.pro.rust_search")


# ─── Config ──────────────────────────────────────────────────────────────────

def _config() -> dict[str, Any]:
    enabled_raw = (os.getenv("RUST_SEARCH_ENABLED") or "true").lower()
    return {
        "enabled": enabled_raw == "true",
        "url": os.getenv("RUST_SEARCH_URL")
               or "https://yukpo-fly-backend.fly.dev/api/search/universal",
        "timeout_s": float(os.getenv("RUST_SEARCH_TIMEOUT_S") or "6"),
        "ttl_s": int(os.getenv("RUST_SEARCH_TTL_S") or "1800"),
    }


# ─── Cache in-process simple ────────────────────────────────────────────────

_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_CACHE_MAX_ENTRIES = 500  # auto-eviction LRU light


def _cache_key(params: dict[str, Any]) -> str:
    canonical = json.dumps(params, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _cache_get(key: str, ttl_s: int) -> Optional[list[dict[str, Any]]]:
    entry = _CACHE.get(key)
    if not entry:
        return None
    saved_at, value = entry
    if time.monotonic() - saved_at > ttl_s:
        _CACHE.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: list[dict[str, Any]]) -> None:
    if len(_CACHE) >= _CACHE_MAX_ENTRIES:
        # Eviction simple : drop des 10% plus anciens
        keys_sorted = sorted(_CACHE.items(), key=lambda kv: kv[1][0])
        for k, _ in keys_sorted[: _CACHE_MAX_ENTRIES // 10]:
            _CACHE.pop(k, None)
    _CACHE[key] = (time.monotonic(), value)


# ─── Appel principal ─────────────────────────────────────────────────────────

async def chercher_services_marketplace(
    query: str,
    *,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius_km: float = 30.0,
    limit: int = 6,
    categories: Optional[str] = None,
    exclude_external_source: Optional[str] = "yukposhop",
) -> list[dict[str, Any]]:
    """Cherche des services pertinents dans le marketplace Yukpo Rust.

    Args :
      query : terme de recherche (catégorie produit, marque, ville, etc.)
      lat, lng : GPS du commerçant (pour scoring distance Rust)
      radius_km : rayon max
      limit : nb de résultats à retourner (1-20, défaut 6)
      categories : filtre catégories séparées par virgule
      exclude_external_source : retire les services qui viennent eux-mêmes
        de YukpoShop via Piste 1 (sinon on s'auto-recommande, useless).
        Mettre None pour désactiver.

    Returns :
      Liste de dicts (jamais None). [] si Rust down ou aucun résultat.
      Forme d'un item (best-effort, Rust peut faire évoluer) :
        {
          "result_type": "product" | "service" | "menu_item",
          "id": int, "service_id": int,
          "titre": str, "prix": float, "devise": str,
          "categorie": str, "vendeur_nom": str,
          "boutique_url": str | None,
          "photo_url": str | None,
          "distance_km": float | None,
          "score": float | None,
        }
    """
    if not query or len(query.strip()) < 2:
        return []
    cfg = _config()
    if not cfg["enabled"]:
        return []

    limit = max(1, min(limit, 20))
    params = {
        "q": query.strip()[:200],
        "limit": limit + 4,  # marge pour filtrage côté nous
    }
    if lat is not None and lng is not None:
        params["lat"] = float(lat)
        params["lng"] = float(lng)
        params["radius_km"] = float(radius_km)
    if categories:
        params["categories"] = categories.strip()[:200]

    # Cache lookup
    key = _cache_key(params)
    cached = _cache_get(key, cfg["ttl_s"])
    if cached is not None:
        return cached[:limit]

    # HTTP
    try:
        async with httpx.AsyncClient(timeout=cfg["timeout_s"]) as client:
            resp = await client.get(cfg["url"], params=params)
        if resp.status_code != 200:
            logger.info(
                f"[RustSearch] {cfg['url']} HTTP {resp.status_code} pour q={params['q']!r}"
            )
            _cache_set(key, [])  # cache négatif pour ne pas re-cogner
            return []
        body = resp.json()
        results_raw = body.get("results") or []
    except (httpx.TimeoutException, httpx.NetworkError) as e:
        logger.info(f"[RustSearch] réseau échec ({e}) — fallback []")
        return []
    except Exception as e:
        logger.warning(f"[RustSearch] inattendu : {e}")
        return []

    items = []
    for r in results_raw:
        if not isinstance(r, dict):
            continue
        # Filtre exclusion auto-cross-sell
        if exclude_external_source:
            data = r.get("data") or {}
            if isinstance(data, dict) and data.get("external_source") == exclude_external_source:
                continue
        items.append(_normaliser_item(r))
    items = items[:limit]

    _cache_set(key, items)
    return items


def _normaliser_item(raw: dict[str, Any]) -> dict[str, Any]:
    """Aplatit la réponse Rust en un dict simple consommable côté Jinja/HTML."""
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    # Photos : Rust peut renvoyer photos_urls (Piste 1) ou photo_url single
    photo_url: Optional[str] = None
    photos = data.get("photos_urls") or raw.get("photos") or []
    if isinstance(photos, list) and photos:
        first = photos[0]
        if isinstance(first, str):
            photo_url = first
        elif isinstance(first, dict):
            photo_url = first.get("url") or first.get("src")
    if not photo_url and isinstance(raw.get("photo_url"), str):
        photo_url = raw.get("photo_url")

    titre = (
        data.get("titre")
        or raw.get("product_name")
        or raw.get("titre")
        or raw.get("nom")
        or "Service"
    )
    prix = data.get("prix") or raw.get("product_price") or raw.get("prix") or 0
    devise = data.get("devise") or raw.get("devise") or "XAF"
    vendeur = data.get("vendeur_nom") or raw.get("service_nom") or ""
    boutique_url = data.get("boutique_url") or raw.get("boutique_url")
    distance_km = raw.get("distance_km")
    if isinstance(distance_km, str):
        try:
            distance_km = float(distance_km)
        except ValueError:
            distance_km = None

    return {
        "result_type": raw.get("result_type") or "service",
        "id": raw.get("id"),
        "service_id": raw.get("service_id"),
        "titre": str(titre)[:120],
        "prix": float(prix) if isinstance(prix, (int, float)) else 0.0,
        "devise": str(devise)[:8],
        "categorie": str(raw.get("category") or raw.get("store_category") or "")[:80],
        "vendeur_nom": str(vendeur)[:80],
        "boutique_url": str(boutique_url)[:300] if boutique_url else None,
        "photo_url": photo_url,
        "distance_km": float(distance_km) if isinstance(distance_km, (int, float)) else None,
    }
