"""
Routes Marketing Visuel — Agent Yukpo Studio Marketing
POST /api/v1/pro/marketing/visuel/generer   — Génère un visuel (PNG/JPEG) + sauvegarde
GET  /api/v1/pro/marketing/visuels          — Liste des visuels sauvegardés
GET  /api/v1/pro/marketing/visuels/{id}     — Télécharge un visuel
DELETE /api/v1/pro/marketing/visuels/{id}   — Supprime un visuel
GET  /api/v1/pro/marketing/types            — Types + formats + thèmes disponibles
"""
import base64
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import TokenData, get_current_user
from core.database import async_session_maker, DocumentGenereDB

logger = logging.getLogger("yukpo_assurance.api.pro_marketing")
router = APIRouter()

_DATA_DIR = Path(__file__).parent.parent / "data" / "generated" / "marketing"
_DATA_DIR.mkdir(parents=True, exist_ok=True)


async def get_db():
    async with async_session_maker() as session:
        yield session


# ─── Modèles Pydantic ─────────────────────────────────────────────────────────

class GenererVisuelRequest(BaseModel):
    visual_type:     str   = Field("poster", description="poster|flyer|banner|social_post|invitation|certificate|business_card")
    format:          str   = Field("portrait", description="square|portrait|landscape|story|banner_wide|a4|business_card")
    theme:           str   = Field("purple", description="blue|green|purple|orange|dark|light|gold|elegant|red|corporate")
    title:           str   = Field(..., min_length=1, max_length=200)
    subtitle:        Optional[str] = None
    description:     Optional[str] = None
    brand_name:      Optional[str] = None
    brand_color:     Optional[str] = None
    badge:           Optional[str] = None
    badge_color:     Optional[str] = None
    contact:         Optional[str] = None
    date:            Optional[str] = None
    time:            Optional[str] = None
    location:        Optional[str] = None
    price:           Optional[str] = None
    organizer:       Optional[str] = None
    bullets:         List[str] = Field(default_factory=list)
    hashtags:        List[str] = Field(default_factory=list)
    logo_base64:     Optional[str] = None
    bg_image_base64: Optional[str] = None
    bg_opacity:      float  = 0.28
    output_format:   str   = "png"
    sauvegarder:     bool  = True
    titre_document:  Optional[str] = None


class VisuelSummary(BaseModel):
    id:          int
    titre:       str
    visual_type: str
    format:      str
    theme:       str
    dimensions:  str
    cree_le:     str
    fichier:     Optional[str]


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/visuel/generer", summary="Générer un visuel marketing")
async def generer_visuel(
    req: GenererVisuelRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Génère un visuel marketing professionnel (PIL/Pillow, local, zéro coût).
    Retourne l'image en base64 + la sauvegarde dans Mes Documents si sauvegarder=true.
    """
    try:
        from modules.marketing.visual_generator import generate_visual, FORMATS
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Module visual_generator non disponible : {e}")

    data = req.model_dump()
    try:
        image_bytes = generate_visual(data)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception("[Marketing] Erreur génération visuel")
        raise HTTPException(status_code=500, detail=f"Erreur génération : {e}")

    image_b64 = base64.b64encode(image_bytes).decode()
    mime = "image/jpeg" if req.output_format in ("jpg","jpeg") else "image/png"

    # Débit forfait : 3 FCFA par visuel généré (service local Pillow)
    import asyncio as _asyncio
    from modules.pro.service_credits import debiter_forfait_fcfa as _debiter
    _asyncio.create_task(_debiter(int(current_user.user_id), 3.0, "marketing_visuel"))
    W, H = FORMATS.get(req.format, (1080,1350))
    ext  = "jpg" if req.output_format in ("jpg","jpeg") else "png"
    doc_id = None

    if req.sauvegarder:
        titre = req.titre_document or req.title[:100]
        ts    = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        fname = f"visuel_{current_user.user_id}_{ts}.{ext}"
        fpath = _DATA_DIR / fname
        try:
            fpath.write_bytes(image_bytes)
        except Exception as fe:
            logger.warning(f"[Marketing] Écriture fichier échouée : {fe}")
            fname = None

        try:
            doc = DocumentGenereDB(
                user_id       = int(current_user.user_id),
                titre         = titre,
                type_doc      = "visuel_marketing",
                fichier       = str(fname) if fname else None,
                contenu_source= req.title,
                contenu_genere= f"[Visuel {req.visual_type} | {req.format} | {req.theme}]",
                meta          = {
                    "visual_type": req.visual_type,
                    "format":      req.format,
                    "theme":       req.theme,
                    "dimensions":  f"{W}×{H}",
                    "output_format": req.output_format,
                    "image_b64_preview": image_b64[:2000],
                },
                cree_le    = datetime.utcnow(),
                modifie_le = datetime.utcnow(),
            )
            db.add(doc)
            await db.commit()
            await db.refresh(doc)
            doc_id = doc.id
        except Exception as de:
            logger.warning(f"[Marketing] Sauvegarde DB échouée : {de}")

    return {
        "image_base64":   image_b64,
        "format_mime":    mime,
        "dimensions":     {"w": W, "h": H},
        "doc_id":         doc_id,
        "sauvegarde":     req.sauvegarder and doc_id is not None,
    }


@router.get("/visuels", summary="Liste des visuels marketing sauvegardés")
async def lister_visuels(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
):
    result = await db.execute(
        select(DocumentGenereDB)
        .where(
            DocumentGenereDB.user_id == int(current_user.user_id),
            DocumentGenereDB.type_doc == "visuel_marketing",
        )
        .order_by(desc(DocumentGenereDB.cree_le))
        .limit(limit)
    )
    docs = result.scalars().all()
    return {
        "visuels": [
            {
                "id":          d.id,
                "titre":       d.titre,
                "visual_type": (d.meta or {}).get("visual_type", ""),
                "format":      (d.meta or {}).get("format", ""),
                "theme":       (d.meta or {}).get("theme", ""),
                "dimensions":  (d.meta or {}).get("dimensions", ""),
                "image_preview": (d.meta or {}).get("image_b64_preview", ""),
                "cree_le":     d.cree_le.isoformat() if d.cree_le else "",
                "fichier":     d.fichier,
            }
            for d in docs
        ]
    }


@router.get("/visuels/{doc_id}", summary="Télécharger un visuel sauvegardé")
async def telecharger_visuel(
    doc_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DocumentGenereDB).where(
            DocumentGenereDB.id      == doc_id,
            DocumentGenereDB.user_id == int(current_user.user_id),
            DocumentGenereDB.type_doc == "visuel_marketing",
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Visuel introuvable")

    if doc.fichier:
        fpath = _DATA_DIR / doc.fichier
        if fpath.exists():
            ext  = Path(doc.fichier).suffix.lower()
            mime = "image/jpeg" if ext in (".jpg",".jpeg") else "image/png"
            return Response(content=fpath.read_bytes(), media_type=mime,
                            headers={"Content-Disposition": f"attachment; filename={doc.fichier}"})

    preview = (doc.meta or {}).get("image_b64_preview", "")
    if preview:
        return {"image_base64": preview, "complet": False}

    raise HTTPException(status_code=404, detail="Fichier visuel introuvable")


@router.delete("/visuels/{doc_id}", summary="Supprimer un visuel")
async def supprimer_visuel(
    doc_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DocumentGenereDB).where(
            DocumentGenereDB.id      == doc_id,
            DocumentGenereDB.user_id == int(current_user.user_id),
            DocumentGenereDB.type_doc == "visuel_marketing",
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Visuel introuvable")
    if doc.fichier:
        try:
            (  _DATA_DIR / doc.fichier).unlink(missing_ok=True)
        except Exception:
            pass
    await db.delete(doc)
    await db.commit()
    return {"supprime": True, "id": doc_id}


@router.get("/types", summary="Types, formats et thèmes disponibles")
async def types_disponibles():
    from modules.marketing.visual_generator import formats_disponibles, themes_disponibles, types_disponibles as td
    return {
        "visual_types": td(),
        "formats":      formats_disponibles(),
        "themes":       themes_disponibles(),
    }
