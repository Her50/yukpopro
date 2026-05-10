"""
Marketplace templates communautaire — UGC.

Workflow :
1. user crée un template (POST /soumettre)
2. statut=pending, modération admin (POST /admin/{id}/moderer)
3. statut=published → visible dans /browse
4. autre user clone (POST /{id}/cloner) → copie payload dans son scope
5. utilisateurs notent (POST /{id}/noter, 1-5 étoiles)

Types supportés (couvre toute l'app Yukpo Pro+Sec) :
- designerpro_projet : structure projet Designer Pro (cle_projet + pages)
- slides             : structure slides PPTX (slides_data, type_pres)
- rapport            : structure rapport DOCX (type_rapport, structure)
- redaction          : modèle de document admin (type_doc, prompt_template)
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, and_, or_

from core.auth import get_current_user, TokenData
from core.database import async_session_maker, MarketplaceTemplateDB, MarketplaceRatingDB

router = APIRouter()
logger = logging.getLogger("yukpo_assurance.routes_marketplace")


def _require_admin(current_user: TokenData):
    if current_user.role not in ("admin", "super_admin", "yukpo_owner"):
        raise HTTPException(403, "Admin only")


def _serialiser(t: MarketplaceTemplateDB, with_payload: bool = False) -> dict:
    avg = round(t.rating_sum / t.rating_count, 2) if t.rating_count else None
    out = {
        "id": t.id,
        "user_id": t.user_id,
        "type": t.type_template,
        "label": t.label,
        "description": t.description,
        "tags": t.tags or [],
        "pays": t.pays,
        "langue": t.langue,
        "preview_url": t.preview_url,
        "statut": t.statut,
        "is_public": t.is_public,
        "is_featured": t.is_featured,
        "downloads_count": t.downloads_count or 0,
        "rating_avg": avg,
        "rating_count": t.rating_count or 0,
        "cree_le": t.cree_le.isoformat() if t.cree_le else None,
        "publie_le": t.publie_le.isoformat() if t.publie_le else None,
    }
    if with_payload:
        out["payload"] = t.payload
    return out


# ─── Soumettre un template ────────────────────────────────────────────────────


class DemandeSoumission(BaseModel):
    type: str = Field(..., pattern="^(designerpro_projet|slides|rapport|redaction)$")
    label: str = Field(..., min_length=5, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=10)
    pays: Optional[str] = Field(default=None, max_length=3)
    langue: str = Field(default="fr", max_length=8)
    payload: dict = Field(..., description="Contenu réel du template")
    preview_url: Optional[str] = Field(default=None, max_length=500)


@router.post("/soumettre", tags=["Marketplace"])
async def soumettre_template(
    demande: DemandeSoumission,
    current_user: TokenData = Depends(get_current_user),
):
    """Soumet un template. Statut initial = 'pending', en attente modération."""
    if not isinstance(demande.payload, dict) or not demande.payload:
        raise HTTPException(400, "payload doit être un objet JSON non vide")
    cid = getattr(current_user, "compagnie_id", None)
    async with async_session_maker() as db:
        t = MarketplaceTemplateDB(
            user_id=current_user.user_id,
            compagnie_id=cid,
            type_template=demande.type,
            label=demande.label[:200],
            description=demande.description,
            tags=demande.tags,
            pays=demande.pays,
            langue=demande.langue,
            payload=demande.payload,
            preview_url=demande.preview_url,
            statut="pending",
            is_public=False,
        )
        db.add(t)
        await db.commit()
        await db.refresh(t)
        return {"ok": True, "template_id": t.id, "statut": "pending"}


# ─── Browse (recherche + filtres) ─────────────────────────────────────────────


@router.get("/browse", tags=["Marketplace"])
async def browse_templates(
    type: Optional[str] = Query(default=None,
                                  pattern="^(designerpro_projet|slides|rapport|redaction)$"),
    pays: Optional[str] = Query(default=None, max_length=3),
    langue: Optional[str] = Query(default=None, max_length=8),
    tag: Optional[str] = Query(default=None, max_length=50),
    tri: str = Query(default="recents",
                      pattern="^(recents|populaires|featured|note)$"),
    limite: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: TokenData = Depends(get_current_user),
):
    """Liste les templates publics (statut=published). Filtres + tri."""
    async with async_session_maker() as db:
        q = select(MarketplaceTemplateDB).where(
            and_(
                MarketplaceTemplateDB.statut == "published",
                MarketplaceTemplateDB.is_public == True,  # noqa: E712
            )
        )
        if type:
            q = q.where(MarketplaceTemplateDB.type_template == type)
        if pays:
            q = q.where(MarketplaceTemplateDB.pays == pays.upper())
        if langue:
            q = q.where(MarketplaceTemplateDB.langue == langue.lower())
        if tag:
            # JSON contains : compatible Postgres (jsonb) et SQLite (json_each)
            q = q.where(MarketplaceTemplateDB.tags.contains([tag]))
        if tri == "recents":
            q = q.order_by(desc(MarketplaceTemplateDB.publie_le))
        elif tri == "populaires":
            q = q.order_by(desc(MarketplaceTemplateDB.downloads_count))
        elif tri == "featured":
            q = q.order_by(
                desc(MarketplaceTemplateDB.is_featured),
                desc(MarketplaceTemplateDB.downloads_count),
            )
        elif tri == "note":
            # Approximation : trier par rating_sum/rating_count descendant
            q = q.order_by(
                desc(MarketplaceTemplateDB.rating_count),
                desc(MarketplaceTemplateDB.rating_sum),
            )
        q = q.limit(limite).offset(offset)
        rows = (await db.execute(q)).scalars().all()
        return {
            "ok": True,
            "limite": limite, "offset": offset,
            "items": [_serialiser(t) for t in rows],
        }


# ─── Détail d'un template ────────────────────────────────────────────────────


@router.get("/{template_id}", tags=["Marketplace"])
async def get_template(
    template_id: int,
    current_user: TokenData = Depends(get_current_user),
):
    async with async_session_maker() as db:
        t = (await db.execute(
            select(MarketplaceTemplateDB).where(MarketplaceTemplateDB.id == template_id)
        )).scalars().first()
        if not t:
            raise HTTPException(404, "Template introuvable")
        # Visibilité : public OU owner OU admin
        is_admin = current_user.role in ("admin", "super_admin", "yukpo_owner")
        if t.statut != "published" or not t.is_public:
            if t.user_id != current_user.user_id and not is_admin:
                raise HTTPException(403, "Template non public")
        return {"ok": True, "template": _serialiser(t, with_payload=True)}


# ─── Cloner un template (incrémente downloads_count) ─────────────────────────


@router.post("/{template_id}/cloner", tags=["Marketplace"])
async def cloner_template(
    template_id: int,
    current_user: TokenData = Depends(get_current_user),
):
    """Retourne le payload pour ré-utilisation. Incrémente downloads_count."""
    async with async_session_maker() as db:
        t = (await db.execute(
            select(MarketplaceTemplateDB).where(MarketplaceTemplateDB.id == template_id)
        )).scalars().first()
        if not t:
            raise HTTPException(404, "Template introuvable")
        if t.statut != "published" or not t.is_public:
            raise HTTPException(403, "Template non public")
        t.downloads_count = (t.downloads_count or 0) + 1
        await db.commit()
        return {
            "ok": True,
            "type": t.type_template,
            "label": t.label,
            "payload": t.payload,
        }


# ─── Noter un template (1-5) ─────────────────────────────────────────────────


class DemandeNote(BaseModel):
    note: int = Field(..., ge=1, le=5)
    commentaire: Optional[str] = Field(default=None, max_length=1000)


@router.post("/{template_id}/noter", tags=["Marketplace"])
async def noter_template(
    template_id: int,
    demande: DemandeNote,
    current_user: TokenData = Depends(get_current_user),
):
    """Vote 1-5 étoiles. Un utilisateur ne peut voter qu'une fois par template
    (UPSERT comportement : update si déjà voté)."""
    async with async_session_maker() as db:
        t = (await db.execute(
            select(MarketplaceTemplateDB).where(MarketplaceTemplateDB.id == template_id)
        )).scalars().first()
        if not t or t.statut != "published":
            raise HTTPException(404, "Template introuvable ou non publié")
        existing = (await db.execute(
            select(MarketplaceRatingDB).where(and_(
                MarketplaceRatingDB.template_id == template_id,
                MarketplaceRatingDB.user_id == current_user.user_id,
            ))
        )).scalars().first()
        if existing:
            # Update : retirer ancienne contribution puis ajouter nouvelle
            t.rating_sum = max(0, (t.rating_sum or 0) - (existing.note or 0)) + demande.note
            existing.note = demande.note
            existing.commentaire = demande.commentaire
        else:
            r = MarketplaceRatingDB(
                template_id=template_id,
                user_id=current_user.user_id,
                note=demande.note,
                commentaire=demande.commentaire,
            )
            db.add(r)
            t.rating_sum = (t.rating_sum or 0) + demande.note
            t.rating_count = (t.rating_count or 0) + 1
        await db.commit()
        avg = t.rating_sum / t.rating_count if t.rating_count else None
        return {"ok": True, "rating_avg": round(avg, 2) if avg else None,
                "rating_count": t.rating_count}


# ─── Modération admin ────────────────────────────────────────────────────────


class DemandeModeration(BaseModel):
    statut: str = Field(..., pattern="^(published|rejected|archived)$")
    is_featured: Optional[bool] = None
    moderation_note: Optional[str] = Field(default=None, max_length=2000)


@router.post("/admin/{template_id}/moderer", tags=["Marketplace"])
async def moderer_template(
    template_id: int,
    demande: DemandeModeration,
    current_user: TokenData = Depends(get_current_user),
):
    _require_admin(current_user)
    async with async_session_maker() as db:
        t = (await db.execute(
            select(MarketplaceTemplateDB).where(MarketplaceTemplateDB.id == template_id)
        )).scalars().first()
        if not t:
            raise HTTPException(404, "Template introuvable")
        ancien = t.statut
        t.statut = demande.statut
        if demande.is_featured is not None:
            t.is_featured = bool(demande.is_featured)
        if demande.moderation_note is not None:
            t.moderation_note = demande.moderation_note
        if demande.statut == "published":
            t.is_public = True
            if not t.publie_le:
                t.publie_le = datetime.utcnow()
        elif demande.statut in ("rejected", "archived"):
            t.is_public = False
        await db.commit()
        logger.info(
            f"[Marketplace] Modération template {template_id} : {ancien} → {demande.statut}"
        )
        return {"ok": True, "template": _serialiser(t)}


@router.get("/admin/pending", tags=["Marketplace"])
async def lister_pending(
    current_user: TokenData = Depends(get_current_user),
    limite: int = Query(default=50, ge=1, le=200),
):
    """Liste les templates en attente de modération."""
    _require_admin(current_user)
    async with async_session_maker() as db:
        q = select(MarketplaceTemplateDB).where(
            MarketplaceTemplateDB.statut == "pending"
        ).order_by(desc(MarketplaceTemplateDB.cree_le)).limit(limite)
        rows = (await db.execute(q)).scalars().all()
        return {"ok": True, "items": [_serialiser(t) for t in rows]}
