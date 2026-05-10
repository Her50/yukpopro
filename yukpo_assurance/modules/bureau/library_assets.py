"""
Bibliothèque d'assets — illustrations photo (Unsplash) + icônes SVG vectorielles
(Iconify, 200 000+ icônes de 100+ collections : Material, Tabler, Phosphor,
Heroicons, Lucide, FontAwesome, Carbon IBM, Mingcute, etc.).

API publiques utilisées :
- Unsplash : https://api.unsplash.com (clé gratuite, 50 req/h sans clé via
  source.unsplash.com pour les preview, ou Access Key pour metadata)
- Iconify  : https://api.iconify.design (gratuit, sans clé requise)

Sécurité : pas de stockage local des assets externes — on retourne l'URL
publique (pour Unsplash) ou le SVG inline (pour Iconify) que le générateur
embed dans le PDF/PPTX/DOCX.

Usage :
- Designer Pro : zone `image_ia` → si prompt contient mots-clés type
  "photo réelle de", utilise Unsplash au lieu de fal.ai (gratuit + rapide)
- Slides : icônes contextuelles (chart, plus, info, tendance) embedées via
  Iconify → SVG vectoriel zoomable infiniment
- DOCX/PDF : assets décoratifs en watermark ou en-tête
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from config.settings import settings

logger = logging.getLogger("yukpo_assurance.bureau.library_assets")


# ─── Unsplash photos ─────────────────────────────────────────────────────────


_UNSPLASH_API = "https://api.unsplash.com"
_UNSPLASH_SOURCE = "https://source.unsplash.com"  # fallback sans clé

_UNSPLASH_KEY = getattr(settings, "UNSPLASH_ACCESS_KEY", None) or ""


async def chercher_photos_unsplash(
    query: str,
    page: int = 1,
    per_page: int = 12,
    orientation: Optional[str] = None,   # 'landscape' | 'portrait' | 'squarish'
    color: Optional[str] = None,          # 'black_and_white' | 'red' | 'orange' | 'yellow' | 'green' | 'teal' | 'blue' | 'purple' | 'magenta' | 'white' | 'black'
    timeout_s: int = 12,
) -> list[dict]:
    """
    Recherche des photos sur Unsplash. Retourne une liste de dicts :
    [{id, alt, urls: {small, regular, full, raw}, user: {name, link}, color, width, height}]

    Si UNSPLASH_ACCESS_KEY absent → fallback URL générique (qualité moindre,
    pas de metadata mais URL utilisable directement).
    """
    if not query or len(query.strip()) < 2:
        return []

    if _UNSPLASH_KEY:
        params = {
            "query": query[:200],
            "page": max(1, page),
            "per_page": max(1, min(30, per_page)),
        }
        if orientation:
            params["orientation"] = orientation
        if color:
            params["color"] = color
        headers = {
            "Authorization": f"Client-ID {_UNSPLASH_KEY}",
            "Accept-Version": "v1",
        }
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as c:
                r = await c.get(f"{_UNSPLASH_API}/search/photos",
                                 params=params, headers=headers)
                r.raise_for_status()
                data = r.json()
            return [
                {
                    "id": h.get("id"),
                    "alt": h.get("alt_description") or h.get("description") or query,
                    "urls": h.get("urls") or {},
                    "user": {
                        "name": (h.get("user") or {}).get("name"),
                        "link": (h.get("user") or {}).get("links", {}).get("html"),
                    },
                    "color": h.get("color"),
                    "width": h.get("width"), "height": h.get("height"),
                }
                for h in (data.get("results") or [])
            ]
        except httpx.HTTPError as e:
            logger.warning(f"[Unsplash] API échoué : {e} → fallback source URL")

    # Fallback sans clé : on retourne 1 URL générique (source.unsplash.com)
    # qui répond avec une photo aléatoire matchant le query. Pas de metadata.
    encoded = httpx.QueryParams({"q": query[:200]}).get("q")
    return [{
        "id": None,
        "alt": query,
        "urls": {
            "regular": f"{_UNSPLASH_SOURCE}/featured/?{encoded}",
            "small":   f"{_UNSPLASH_SOURCE}/400x300/?{encoded}",
        },
        "user": {"name": None, "link": None},
        "color": None, "width": None, "height": None,
    }]


# ─── Iconify icônes SVG ──────────────────────────────────────────────────────


_ICONIFY_API = "https://api.iconify.design"
# Collections privilégiées (haute qualité, designs cohérents)
_COLLECTIONS_PRIORITAIRES = [
    "lucide", "tabler", "heroicons", "ph", "carbon", "mdi", "material-symbols",
    "fluent", "solar", "iconamoon", "hugeicons", "mingcute", "stash", "icon-park",
]


async def chercher_icones_iconify(
    query: str,
    limite: int = 24,
    collections: Optional[list[str]] = None,
    timeout_s: int = 8,
) -> list[dict]:
    """
    Recherche des icônes sur Iconify. Retourne :
    [{name, prefix, body, svg_url, full}]

    `collections` : liste de prefixes Iconify (ex: ['lucide', 'tabler']).
    Sans : utilise les collections prioritaires.
    `body` : non récupéré ici (économie bande passante) ; utiliser
    `recuperer_svg_iconify(prefix, name)` à la demande.
    """
    if not query or len(query.strip()) < 2:
        return []
    cols = collections or _COLLECTIONS_PRIORITAIRES
    params = {
        "query": query[:80],
        "limit": max(1, min(64, limite)),
        "prefixes": ",".join(cols)[:500],
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as c:
            r = await c.get(f"{_ICONIFY_API}/search", params=params)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as e:
        logger.info(f"[Iconify] Search KO : {e}")
        return []

    icons_full = data.get("icons") or []
    out: list[dict] = []
    for full in icons_full:
        # full = "lucide:home" → prefix=lucide, name=home
        if ":" not in full:
            continue
        prefix, name = full.split(":", 1)
        out.append({
            "full": full,
            "prefix": prefix,
            "name": name,
            "svg_url": f"{_ICONIFY_API}/{prefix}/{name}.svg",
            "embed_html": f'<iconify-icon icon="{full}"></iconify-icon>',
        })
    return out


async def recuperer_svg_iconify(
    prefix: str, name: str,
    color: str = "currentColor",
    width: int = 24, height: int = 24,
    timeout_s: int = 8,
) -> Optional[str]:
    """Récupère le SVG inline d'une icône Iconify précise."""
    params: dict = {}
    if color and color != "currentColor":
        params["color"] = color
    if width != 24:
        params["width"] = width
    if height != 24:
        params["height"] = height
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as c:
            r = await c.get(f"{_ICONIFY_API}/{prefix}/{name}.svg", params=params)
            r.raise_for_status()
            return r.text
    except httpx.HTTPError as e:
        logger.info(f"[Iconify] {prefix}:{name} KO : {e}")
        return None


# ─── Helper pour générateurs ─────────────────────────────────────────────────


async def telecharger_photo_unsplash(
    url: str, taille: str = "regular", timeout_s: int = 30,
) -> Optional[bytes]:
    """Télécharge une photo Unsplash en bytes (PNG/JPG) pour embed PDF/PPTX/DOCX."""
    try:
        async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as c:
            r = await c.get(url)
            r.raise_for_status()
            return r.content
    except httpx.HTTPError as e:
        logger.warning(f"[Unsplash] Download échoué : {e}")
        return None
