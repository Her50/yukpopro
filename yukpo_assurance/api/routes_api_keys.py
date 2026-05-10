"""
Sprint 2.1 — Gestion des clés API (côté JWT, pour l'admin de l'org).

Endpoints (auth JWT requise) :
  - GET    /api-keys                         → liste des clés de l'org
  - POST   /api-keys                         → crée une clé (renvoie clé en clair UNE FOIS)
  - DELETE /api-keys/{key_id}                → révoque une clé
  - PATCH  /api-keys/{key_id}                → modifie label/scopes/rate-limit

Scopes disponibles (ajouter selon besoins) :
  - "designerpro:generate"  → lance générations Designer Pro
  - "designerpro:read"      → lecture catalogue + projets
  - "media:upload"          → upload médias session/compte
  - "*"                     → wildcard (full accès)
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from core.auth import TokenData, get_current_user

logger = logging.getLogger("yukpo_assurance.api.api_keys")
router = APIRouter()


SCOPES_DISPONIBLES = [
    "designerpro:generate",
    "designerpro:read",
    "designerpro:orchestrer",
    "media:upload",
    "media:read",
    "*",
]


class CreerCleRequest(BaseModel):
    label: str = Field(..., min_length=2, max_length=120,
        description="Nom interne de la clé (ex: 'Site marketing prod')")
    scopes: list[str] = Field(default_factory=lambda: ["designerpro:generate"],
        description="Scopes accordés. '*' = full accès.")
    rate_limit_per_hour: int = Field(default=100, ge=1, le=10000)
    rate_limit_per_day: int = Field(default=1000, ge=1, le=1_000_000)
    env: str = Field(default="live", pattern="^(live|test)$")
    note: Optional[str] = Field(default=None, max_length=500)


class CleResponse(BaseModel):
    key_id: str
    label: str
    key_prefix: str
    scopes: list[str]
    rate_limit_per_hour: int
    rate_limit_per_day: int
    actif: bool
    cree_le: str
    derniere_utilisation: Optional[str] = None
    revoquee_le: Optional[str] = None
    note: Optional[str] = None
    # cle_complete présent UNIQUEMENT à la création (révélation one-shot)
    cle_complete: Optional[str] = Field(default=None,
        description="Clé en clair (visible UNIQUEMENT à la création — copier maintenant)")


class PatchCleRequest(BaseModel):
    label: Optional[str] = None
    scopes: Optional[list[str]] = None
    rate_limit_per_hour: Optional[int] = Field(default=None, ge=1, le=10000)
    rate_limit_per_day: Optional[int] = Field(default=None, ge=1, le=1_000_000)
    actif: Optional[bool] = None
    note: Optional[str] = None


def _row_to_response(row, cle_complete: Optional[str] = None) -> CleResponse:
    return CleResponse(
        key_id=row.key_id, label=row.label, key_prefix=row.key_prefix,
        scopes=row.scopes or [], rate_limit_per_hour=row.rate_limit_per_hour,
        rate_limit_per_day=row.rate_limit_per_day, actif=row.actif,
        cree_le=row.cree_le.isoformat() if row.cree_le else None,
        derniere_utilisation=row.derniere_utilisation.isoformat() if row.derniere_utilisation else None,
        revoquee_le=row.revoquee_le.isoformat() if row.revoquee_le else None,
        note=row.note, cle_complete=cle_complete,
    )


@router.get("", response_model=list[CleResponse], tags=["API Keys (admin org)"])
async def lister_cles(current_user: TokenData = Depends(get_current_user)):
    """Liste les clés API de l'organisation de l'utilisateur."""
    from core.database import async_session_maker, ApiKeyDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    async with async_session_maker() as db:
        rows = (await db.execute(
            select(ApiKeyDB).where(ApiKeyDB.compagnie_id == cid)
            .order_by(ApiKeyDB.cree_le.desc())
        )).scalars().all()
    return [_row_to_response(r) for r in rows]


@router.post("", response_model=CleResponse, tags=["API Keys (admin org)"])
async def creer_cle(
    demande: CreerCleRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Crée une nouvelle clé API. ⚠️ La clé en clair n'est retournée QUE par
    cette réponse — impossible à récupérer ensuite (seul le hash est stocké).
    """
    from core.database import async_session_maker, ApiKeyDB
    from core.api_key_auth import generer_cle_api

    # Validation scopes
    invalid = [s for s in demande.scopes if s not in SCOPES_DISPONIBLES]
    if invalid:
        raise HTTPException(400, f"Scopes invalides : {invalid}. Disponibles : {SCOPES_DISPONIBLES}")

    cle, prefix, sha = generer_cle_api(env=demande.env)
    cid = getattr(current_user, "compagnie_id", None) or 1
    key_id = str(uuid.uuid4())

    async with async_session_maker() as db:
        row = ApiKeyDB(
            key_id=key_id, compagnie_id=cid,
            user_id_createur=current_user.user_id,
            label=demande.label, key_prefix=prefix, key_hash=sha,
            scopes=demande.scopes, rate_limit_per_hour=demande.rate_limit_per_hour,
            rate_limit_per_day=demande.rate_limit_per_day, actif=True,
            cree_le=datetime.utcnow(), note=demande.note,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)

    logger.info(f"[API Keys] Nouvelle clé créée : {key_id} (compagnie={cid}, label={demande.label})")
    return _row_to_response(row, cle_complete=cle)


@router.patch("/{key_id}", response_model=CleResponse, tags=["API Keys (admin org)"])
async def patch_cle(
    key_id: str, demande: PatchCleRequest,
    current_user: TokenData = Depends(get_current_user),
):
    from core.database import async_session_maker, ApiKeyDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    async with async_session_maker() as db:
        row = (await db.execute(
            select(ApiKeyDB).where(
                ApiKeyDB.key_id == key_id, ApiKeyDB.compagnie_id == cid
            )
        )).scalar_one_or_none()
        if not row:
            raise HTTPException(404, "Clé introuvable")
        if demande.label is not None:
            row.label = demande.label
        if demande.scopes is not None:
            invalid = [s for s in demande.scopes if s not in SCOPES_DISPONIBLES]
            if invalid:
                raise HTTPException(400, f"Scopes invalides : {invalid}")
            row.scopes = demande.scopes
        if demande.rate_limit_per_hour is not None:
            row.rate_limit_per_hour = demande.rate_limit_per_hour
        if demande.rate_limit_per_day is not None:
            row.rate_limit_per_day = demande.rate_limit_per_day
        if demande.actif is not None:
            row.actif = demande.actif
        if demande.note is not None:
            row.note = demande.note
        await db.commit()
        await db.refresh(row)
    return _row_to_response(row)


@router.delete("/{key_id}", tags=["API Keys (admin org)"])
async def revoquer_cle(
    key_id: str, current_user: TokenData = Depends(get_current_user),
):
    """Révoque définitivement une clé (soft-delete : actif=False + revoquee_le)."""
    from core.database import async_session_maker, ApiKeyDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    async with async_session_maker() as db:
        row = (await db.execute(
            select(ApiKeyDB).where(
                ApiKeyDB.key_id == key_id, ApiKeyDB.compagnie_id == cid
            )
        )).scalar_one_or_none()
        if not row:
            raise HTTPException(404, "Clé introuvable")
        row.actif = False
        row.revoquee_le = datetime.utcnow()
        await db.commit()
    logger.info(f"[API Keys] Clé révoquée : {key_id}")
    return {"ok": True, "key_id": key_id, "revoquee_le": row.revoquee_le.isoformat()}


@router.get("/scopes-disponibles", tags=["API Keys (admin org)"])
async def lister_scopes(current_user: TokenData = Depends(get_current_user)):
    """Catalogue des scopes pour l'UI."""
    return {"scopes": SCOPES_DISPONIBLES}
