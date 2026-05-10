"""
Bibliothèque assets — endpoints recherche photos Unsplash + icônes Iconify.

Cas d'usage frontend :
- Designer Pro : panneau "Choisir une photo" / "Choisir une icône" branchés
  ici → user pick → injecté dans le projet (zone image_user avec ref URL).
- Slides : icônes contextuelles dans textbox bullets/KPI.
- Rapports : illustrations décoratives en-tête de section.

Pas de débit crédits sur la recherche (gratuit pour Yukpo). Le download
photo finale (si embed dans PDF/PPTX) est facturé via le forfait du
document concerné.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from core.auth import get_current_user, TokenData
from modules.bureau import library_assets as la

router = APIRouter()


@router.get("/photos", tags=["Bureau — Bibliothèque"])
async def chercher_photos(
    q: str = Query(..., min_length=2, max_length=200),
    page: int = Query(default=1, ge=1, le=50),
    per_page: int = Query(default=12, ge=1, le=30),
    orientation: Optional[str] = Query(
        default=None, pattern="^(landscape|portrait|squarish)$"
    ),
    color: Optional[str] = Query(
        default=None,
        pattern="^(black_and_white|red|orange|yellow|green|teal|blue|purple|magenta|white|black)$",
    ),
    current_user: TokenData = Depends(get_current_user),
):
    """Recherche photos Unsplash. Retourne URLs (small/regular/full) + metadata.
    Le frontend embed l'URL `regular` directement dans Designer Pro / slides."""
    photos = await la.chercher_photos_unsplash(
        query=q, page=page, per_page=per_page,
        orientation=orientation, color=color,
    )
    return {
        "ok": True, "query": q, "page": page, "per_page": per_page,
        "items": photos, "total": len(photos),
        "credit": "Photos via Unsplash — license libre, attribution recommandée",
    }


@router.get("/icones", tags=["Bureau — Bibliothèque"])
async def chercher_icones(
    q: str = Query(..., min_length=2, max_length=80),
    limite: int = Query(default=24, ge=1, le=64),
    collections: Optional[str] = Query(
        default=None,
        description="Comma-separated Iconify prefixes (ex: 'lucide,tabler,heroicons')",
    ),
    current_user: TokenData = Depends(get_current_user),
):
    """Recherche icônes Iconify (200k+ icônes vectorielles SVG)."""
    cols = [c.strip() for c in (collections or "").split(",") if c.strip()] or None
    icones = await la.chercher_icones_iconify(
        query=q, limite=limite, collections=cols,
    )
    return {
        "ok": True, "query": q,
        "items": icones, "total": len(icones),
        "credit": "Icônes via Iconify — open source, license CC0/MIT/Apache selon collection",
    }


@router.get("/icone/{prefix}/{name}", tags=["Bureau — Bibliothèque"])
async def recuperer_icone_svg(
    prefix: str, name: str,
    color: str = Query(default="currentColor", max_length=30),
    width: int = Query(default=24, ge=8, le=512),
    height: int = Query(default=24, ge=8, le=512),
    current_user: TokenData = Depends(get_current_user),
):
    """Retourne le SVG inline d'une icône Iconify précise.
    Utilisable en data-URL (data:image/svg+xml;base64,...) côté frontend ou
    embed direct dans WeasyPrint HTML/CSS."""
    svg = await la.recuperer_svg_iconify(prefix, name, color=color, width=width, height=height)
    if not svg:
        raise HTTPException(404, f"Icône {prefix}:{name} introuvable")
    return {
        "ok": True, "prefix": prefix, "name": name,
        "svg": svg,
        "data_url": f"data:image/svg+xml;utf8,{svg}",
    }
