"""Routes Tracking Settings (Phase B).

Endpoints :

  GET    /api/v1/pro/tracking-settings              (auth)
       → Lecture des settings tracking du user (pixels, newsletter).
  PUT    /api/v1/pro/tracking-settings              (auth)
       → Mise à jour. Crée la ligne si absente.
  GET    /api/v1/pro/landing-publications/{slug}/stats   (auth)
       → Récupère stats Plausible (visites/sources/pays) sur la landing.

  GET    /api/v1/pro/landing-followup-settings      (auth)
       → Lecture des templates email J+0/J+3/J+7.
  PUT    /api/v1/pro/landing-followup-settings      (auth)
       → Mise à jour des templates.

Facturation : pas de coût IA, juste des read/write DB → mapping vers
`kanban_action` (5 crédits) pour les écritures, lectures gratuites.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import TokenData, get_current_user
from core.database import (
    LandingFollowupSettingsDB, LandingPublicationDB,
    TrackingSettingsDB, async_session_maker,
)

logger = logging.getLogger("yukpo_assurance.api.tracking_settings")

router = APIRouter()


async def _get_db():
    async with async_session_maker() as session:
        yield session


# ─── Schemas ──────────────────────────────────────────────────────────────────

class TrackingSettingsOut(BaseModel):
    plausible_actif: bool
    fb_pixel_id: Optional[str] = None
    ga4_measurement_id: Optional[str] = None
    tiktok_pixel_id: Optional[str] = None
    snap_pixel_id: Optional[str] = None
    clarity_project_id: Optional[str] = None
    newsletter_provider: Optional[str] = None
    newsletter_list_id: Optional[str] = None
    # API key jamais retournée en clair → masquée
    newsletter_api_key_set: bool = False


class TrackingSettingsIn(BaseModel):
    plausible_actif: Optional[bool] = None
    fb_pixel_id: Optional[str] = Field(None, max_length=40)
    ga4_measurement_id: Optional[str] = Field(None, max_length=40)
    tiktok_pixel_id: Optional[str] = Field(None, max_length=40)
    snap_pixel_id: Optional[str] = Field(None, max_length=40)
    clarity_project_id: Optional[str] = Field(None, max_length=40)
    newsletter_provider: Optional[str] = Field(
        None, pattern=r"^(brevo|mailchimp|none)?$"
    )
    newsletter_api_key: Optional[str] = Field(None, max_length=120)
    newsletter_list_id: Optional[str] = Field(None, max_length=80)


class FollowupTemplate(BaseModel):
    actif: bool
    sujet: Optional[str] = Field(None, max_length=160)
    corps: Optional[str] = Field(None, max_length=8000)


class FollowupSettingsIn(BaseModel):
    j0: Optional[FollowupTemplate] = None
    j3: Optional[FollowupTemplate] = None
    j7: Optional[FollowupTemplate] = None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/tracking-settings", summary="Lecture tracking settings du user")
async def get_tracking_settings(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
) -> TrackingSettingsOut:
    res = await db.execute(
        select(TrackingSettingsDB).where(
            TrackingSettingsDB.user_id == current_user.user_id
        )
    )
    row = res.scalar_one_or_none()
    if not row:
        return TrackingSettingsOut(plausible_actif=True)
    return TrackingSettingsOut(
        plausible_actif=row.plausible_actif,
        fb_pixel_id=row.fb_pixel_id,
        ga4_measurement_id=row.ga4_measurement_id,
        tiktok_pixel_id=row.tiktok_pixel_id,
        snap_pixel_id=row.snap_pixel_id,
        clarity_project_id=row.clarity_project_id,
        newsletter_provider=row.newsletter_provider,
        newsletter_list_id=row.newsletter_list_id,
        newsletter_api_key_set=bool(row.newsletter_api_key),
    )


@router.put("/tracking-settings", summary="Maj tracking settings du user")
async def put_tracking_settings(
    payload: TrackingSettingsIn,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    res = await db.execute(
        select(TrackingSettingsDB).where(
            TrackingSettingsDB.user_id == current_user.user_id
        )
    )
    row = res.scalar_one_or_none()
    if not row:
        row = TrackingSettingsDB(user_id=current_user.user_id)
        db.add(row)

    # Patch champ par champ — seuls les fields fournis sont écrits
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(row, k, v if v != "" else None)
    row.modif_le = datetime.utcnow()
    await db.commit()

    # Débit forfait existant (mapping → kanban_action = "écriture config")
    try:
        from modules.bureau.service_credits_bureau import debiter_forfait_unifie
        await debiter_forfait_unifie(
            current_user.user_id, "kanban_action", module="tracking_settings",
        )
    except Exception as _e:
        logger.debug(f"[Tracking] débit non bloquant : {_e}")
    return {"ok": True}


@router.get(
    "/landing-publications/{slug}/stats",
    summary="Stats Plausible (visites/sources) d'une landing publiée",
)
async def get_landing_stats(
    slug: str = Path(..., min_length=3, max_length=60,
                     pattern=r"^[a-z0-9][a-z0-9-]{1,58}[a-z0-9]$"),
    periode: str = "30d",
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    """Proxy vers l'API Plausible Stats. Vérifie ownership du slug.

    Périodes acceptées Plausible : day, 7d, 30d, month, 6mo, 12mo, custom
    """
    # Ownership
    pub = (await db.execute(
        select(LandingPublicationDB).where(LandingPublicationDB.slug == slug)
    )).scalar_one_or_none()
    if not pub:
        raise HTTPException(404, "Landing introuvable")
    if pub.user_id != current_user.user_id:
        raise HTTPException(403, "Landing non possédée")

    api_key = os.getenv("PLAUSIBLE_API_KEY", "").strip()
    api_base = os.getenv("PLAUSIBLE_API_BASE", "https://plausible.io/api/v1").strip()
    if not api_key:
        raise HTTPException(503, "PLAUSIBLE_API_KEY non configuré")

    # Le `site_id` Plausible = le domaine de la landing (sans https://)
    site_id = pub.url_public.replace("https://", "").replace("http://", "").rstrip("/")

    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            agg = await client.get(
                f"{api_base}/stats/aggregate",
                headers=headers,
                params={
                    "site_id": site_id, "period": periode,
                    "metrics": "visitors,pageviews,bounce_rate,visit_duration",
                },
            )
            srcs = await client.get(
                f"{api_base}/stats/breakdown",
                headers=headers,
                params={
                    "site_id": site_id, "period": periode,
                    "property": "visit:source", "limit": 10,
                },
            )
            pays = await client.get(
                f"{api_base}/stats/breakdown",
                headers=headers,
                params={
                    "site_id": site_id, "period": periode,
                    "property": "visit:country", "limit": 10,
                },
            )
            timeseries = await client.get(
                f"{api_base}/stats/timeseries",
                headers=headers,
                params={
                    "site_id": site_id, "period": periode,
                    "metrics": "visitors,pageviews",
                },
            )
        except httpx.HTTPError as e:
            raise HTTPException(502, f"Erreur Plausible : {e}")

    def _ok(r): return r.json() if r.status_code < 300 else {}

    return {
        "site_id": site_id, "periode": periode,
        "aggregate": _ok(agg).get("results", {}),
        "sources": _ok(srcs).get("results", []),
        "pays": _ok(pays).get("results", []),
        "timeseries": _ok(timeseries).get("results", []),
    }


@router.get(
    "/landing-followup-settings", summary="Templates email follow-up J+0/J+3/J+7",
)
async def get_followup_settings(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    row = (await db.execute(
        select(LandingFollowupSettingsDB).where(
            LandingFollowupSettingsDB.user_id == current_user.user_id
        )
    )).scalar_one_or_none()
    if not row:
        return {
            "j0": {"actif": False, "sujet": None, "corps": None},
            "j3": {"actif": False, "sujet": None, "corps": None},
            "j7": {"actif": False, "sujet": None, "corps": None},
        }
    return {
        "j0": {"actif": row.j0_actif, "sujet": row.j0_sujet, "corps": row.j0_corps},
        "j3": {"actif": row.j3_actif, "sujet": row.j3_sujet, "corps": row.j3_corps},
        "j7": {"actif": row.j7_actif, "sujet": row.j7_sujet, "corps": row.j7_corps},
    }


@router.put("/landing-followup-settings", summary="Maj templates email follow-up")
async def put_followup_settings(
    payload: FollowupSettingsIn,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    row = (await db.execute(
        select(LandingFollowupSettingsDB).where(
            LandingFollowupSettingsDB.user_id == current_user.user_id
        )
    )).scalar_one_or_none()
    if not row:
        row = LandingFollowupSettingsDB(user_id=current_user.user_id)
        db.add(row)

    if payload.j0:
        row.j0_actif = payload.j0.actif
        row.j0_sujet = payload.j0.sujet
        row.j0_corps = payload.j0.corps
    if payload.j3:
        row.j3_actif = payload.j3.actif
        row.j3_sujet = payload.j3.sujet
        row.j3_corps = payload.j3.corps
    if payload.j7:
        row.j7_actif = payload.j7.actif
        row.j7_sujet = payload.j7.sujet
        row.j7_corps = payload.j7.corps
    row.modif_le = datetime.utcnow()
    await db.commit()

    try:
        from modules.bureau.service_credits_bureau import debiter_forfait_unifie
        await debiter_forfait_unifie(
            current_user.user_id, "kanban_action", module="followup_settings",
        )
    except Exception as _e:
        logger.debug(f"[Followup] débit non bloquant : {_e}")
    return {"ok": True}
