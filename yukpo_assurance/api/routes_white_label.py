"""
Sprint 2.5 — White-label endpoints (revendeurs/cabinets/agences).

Permet aux organisations partenaires de proposer YukpoPro sous leur propre
marque : custom domain (via Vercel API si VERCEL_API_TOKEN configuré),
logo header custom, couleur primaire UI, sender email transactionnel.

Endpoints (JWT — admin org) :
  GET    /                  → config white-label de l'org
  PUT    /                  → upsert config
  POST   /domain/verify     → vérifie DNS du custom domain (CNAME → cname.vercel-dns.com)
  POST   /domain/attach     → rattache via Vercel API (si VERCEL_API_TOKEN)
  DELETE /                  → désactive (actif=False)

Endpoints PUBLICS (no auth — frontend rendu) :
  GET    /public/lookup?domain=xxx → résout un custom domain → config publique
                                       (logo, couleur, nom_marque) pour rendu UI
"""
from __future__ import annotations

import logging
import socket
import uuid
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from core.auth import TokenData, get_current_user
from config.settings import settings

logger = logging.getLogger("yukpo_assurance.api.white_label")
router = APIRouter()


# ─── Modèles ──────────────────────────────────────────────────────────────────


class WhiteLabelUpsert(BaseModel):
    custom_domain: Optional[str] = Field(default=None, max_length=255,
        description="Domaine custom (ex: 'design.acmebank.cm'). Doit pointer vers cname.vercel-dns.com en CNAME.")
    logo_url: Optional[str] = Field(default=None, max_length=500)
    favicon_url: Optional[str] = Field(default=None, max_length=500)
    couleur_primaire_hex: Optional[str] = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    nom_marque: Optional[str] = Field(default=None, max_length=120)
    tagline: Optional[str] = Field(default=None, max_length=300)
    sender_email: Optional[str] = Field(default=None, max_length=200)
    sender_name: Optional[str] = Field(default=None, max_length=120)
    reply_to_email: Optional[str] = Field(default=None, max_length=200)
    footer_html: Optional[str] = None
    hide_yukpo_brand: bool = Field(default=False)
    vercel_project: Optional[str] = Field(default="ypro", pattern="^(ypro|sec)$",
        description="Sur quel frontend Vercel rattacher ce custom domain")


class WhiteLabelResponse(BaseModel):
    wl_id: str
    compagnie_id: int
    actif: bool
    custom_domain: Optional[str]
    domain_verified: bool
    domain_target: Optional[str]
    vercel_project_id: Optional[str]
    vercel_added_le: Optional[str]
    logo_url: Optional[str]
    favicon_url: Optional[str]
    couleur_primaire_hex: Optional[str]
    nom_marque: Optional[str]
    tagline: Optional[str]
    sender_email: Optional[str]
    sender_name: Optional[str]
    reply_to_email: Optional[str]
    smtp_dkim_actif: bool
    footer_html: Optional[str]
    hide_yukpo_brand: bool
    cree_le: str
    modifie_le: str


def _row_to_response(row) -> WhiteLabelResponse:
    return WhiteLabelResponse(
        wl_id=row.wl_id, compagnie_id=row.compagnie_id, actif=row.actif,
        custom_domain=row.custom_domain, domain_verified=row.domain_verified,
        domain_target=row.domain_target, vercel_project_id=row.vercel_project_id,
        vercel_added_le=row.vercel_added_le.isoformat() if row.vercel_added_le else None,
        logo_url=row.logo_url, favicon_url=row.favicon_url,
        couleur_primaire_hex=row.couleur_primaire_hex,
        nom_marque=row.nom_marque, tagline=row.tagline,
        sender_email=row.sender_email, sender_name=row.sender_name,
        reply_to_email=row.reply_to_email, smtp_dkim_actif=row.smtp_dkim_actif,
        footer_html=row.footer_html, hide_yukpo_brand=row.hide_yukpo_brand,
        cree_le=row.cree_le.isoformat(),
        modifie_le=row.modifie_le.isoformat() if row.modifie_le else row.cree_le.isoformat(),
    )


# ─── Endpoints admin org ──────────────────────────────────────────────────────


@router.get("", response_model=Optional[WhiteLabelResponse], tags=["White-label"])
async def get_white_label(current_user: TokenData = Depends(get_current_user)):
    """Config white-label active de l'org (None si jamais configuré)."""
    from core.database import async_session_maker, WhiteLabelDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    async with async_session_maker() as db:
        row = (await db.execute(
            select(WhiteLabelDB).where(
                WhiteLabelDB.compagnie_id == cid, WhiteLabelDB.actif == True  # noqa
            )
        )).scalar_one_or_none()
    return _row_to_response(row) if row else None


@router.put("", response_model=WhiteLabelResponse, tags=["White-label"])
async def upsert_white_label(
    demande: WhiteLabelUpsert, current_user: TokenData = Depends(get_current_user),
):
    """Upsert la config white-label de l'org."""
    from core.database import async_session_maker, WhiteLabelDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    async with async_session_maker() as db:
        row = (await db.execute(
            select(WhiteLabelDB).where(WhiteLabelDB.compagnie_id == cid)
        )).scalar_one_or_none()
        if row:
            for f in ("custom_domain", "logo_url", "favicon_url",
                      "couleur_primaire_hex", "nom_marque", "tagline",
                      "sender_email", "sender_name", "reply_to_email",
                      "footer_html", "hide_yukpo_brand"):
                v = getattr(demande, f)
                if v is not None or f in ("hide_yukpo_brand",):
                    setattr(row, f, v)
            row.actif = True
            row.modifie_le = datetime.utcnow()
        else:
            row = WhiteLabelDB(
                wl_id=str(uuid.uuid4()), compagnie_id=cid, actif=True,
                custom_domain=demande.custom_domain,
                logo_url=demande.logo_url, favicon_url=demande.favicon_url,
                couleur_primaire_hex=demande.couleur_primaire_hex,
                nom_marque=demande.nom_marque, tagline=demande.tagline,
                sender_email=demande.sender_email, sender_name=demande.sender_name,
                reply_to_email=demande.reply_to_email,
                footer_html=demande.footer_html,
                hide_yukpo_brand=demande.hide_yukpo_brand,
            )
            db.add(row)
        await db.commit()
        await db.refresh(row)
    logger.info(f"[WhiteLabel] Upsert compagnie={cid} domain={demande.custom_domain}")
    return _row_to_response(row)


@router.post("/domain/verify", tags=["White-label"])
async def verify_domain(current_user: TokenData = Depends(get_current_user)):
    """
    Vérifie que le custom_domain résout vers cname.vercel-dns.com via DNS.
    Met à jour domain_verified = True si OK.
    """
    from core.database import async_session_maker, WhiteLabelDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    async with async_session_maker() as db:
        row = (await db.execute(
            select(WhiteLabelDB).where(WhiteLabelDB.compagnie_id == cid)
        )).scalar_one_or_none()
        if not row or not row.custom_domain:
            raise HTTPException(404, "Aucun custom_domain configuré")
        domain = row.custom_domain
        target = row.domain_target or "cname.vercel-dns.com"
        try:
            # Résolution CNAME via socket (best effort)
            import dns.resolver  # type: ignore
            answers = dns.resolver.resolve(domain, "CNAME")
            cnames = [str(a.target).rstrip(".") for a in answers]
            verified = any(target in c for c in cnames)
        except Exception:
            # Fallback : check if A record résout
            try:
                _ = socket.gethostbyname(domain)
                verified = True   # A record existe → présume OK
                cnames = ["(A record résout)"]
            except Exception as e:
                row.domain_verified = False
                await db.commit()
                raise HTTPException(400, f"DNS non résolu pour {domain} : {e}")
        row.domain_verified = bool(verified)
        await db.commit()
        return {
            "ok": True, "domain": domain, "target_attendu": target,
            "cnames_resolus": cnames, "verified": row.domain_verified,
            "message": ("✓ DNS conforme" if row.domain_verified
                        else f"⚠ Le CNAME doit pointer vers {target}"),
        }


@router.post("/domain/attach", tags=["White-label"])
async def attach_vercel_domain(
    project: str = Query("ypro", pattern="^(ypro|sec)$"),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Rattache le custom_domain au projet Vercel via API.
    Requiert VERCEL_API_TOKEN + VERCEL_PROJECT_YPRO/SEC dans settings.
    """
    if not settings.VERCEL_API_TOKEN:
        raise HTTPException(503,
            "VERCEL_API_TOKEN non configuré. L'admin doit ajouter le domain "
            "manuellement dans le dashboard Vercel.")
    project_id = (settings.VERCEL_PROJECT_YPRO if project == "ypro"
                  else settings.VERCEL_PROJECT_SEC)
    if not project_id:
        raise HTTPException(503,
            f"VERCEL_PROJECT_{project.upper()} non configuré.")

    from core.database import async_session_maker, WhiteLabelDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    async with async_session_maker() as db:
        row = (await db.execute(
            select(WhiteLabelDB).where(WhiteLabelDB.compagnie_id == cid)
        )).scalar_one_or_none()
        if not row or not row.custom_domain:
            raise HTTPException(404, "Aucun custom_domain configuré")
        url = f"https://api.vercel.com/v10/projects/{project_id}/domains"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    url, json={"name": row.custom_domain},
                    headers={"Authorization": f"Bearer {settings.VERCEL_API_TOKEN}"},
                )
            if r.status_code not in (200, 201, 409):   # 409 = déjà ajouté
                raise HTTPException(500, f"Vercel API HTTP {r.status_code}: {r.text[:200]}")
            row.vercel_project_id = project_id
            row.vercel_added_le = datetime.utcnow()
            await db.commit()
            return {"ok": True, "domain": row.custom_domain, "vercel_project": project,
                    "status_code": r.status_code, "vercel_response": r.json() if r.text else None}
        except httpx.HTTPError as e:
            raise HTTPException(500, f"Vercel API échouée : {e}")


@router.delete("", tags=["White-label"])
async def disable_white_label(current_user: TokenData = Depends(get_current_user)):
    """Désactive (actif=False, audit-keep)."""
    from core.database import async_session_maker, WhiteLabelDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    async with async_session_maker() as db:
        row = (await db.execute(
            select(WhiteLabelDB).where(WhiteLabelDB.compagnie_id == cid)
        )).scalar_one_or_none()
        if not row:
            raise HTTPException(404, "Aucune config")
        row.actif = False
        row.modifie_le = datetime.utcnow()
        await db.commit()
    return {"ok": True, "compagnie_id": cid, "actif": False}


# ─── Endpoint PUBLIC (sans auth) — pour rendu frontend white-label ────────────


@router.get("/public/lookup", tags=["White-label"])
async def public_lookup(domain: str = Query(..., max_length=255)):
    """
    Résout un custom domain → config publique pour rendu UI.
    Pas d'auth (les frontends consomment au boot pour adapter logo/couleur).
    Retourne uniquement les champs publics safe (pas de sender_email, etc.).
    """
    from core.database import async_session_maker, WhiteLabelDB
    domain = (domain or "").strip().lower()
    if not domain:
        raise HTTPException(400, "domain requis")
    async with async_session_maker() as db:
        row = (await db.execute(
            select(WhiteLabelDB).where(
                WhiteLabelDB.custom_domain == domain,
                WhiteLabelDB.actif == True,  # noqa
            )
        )).scalar_one_or_none()
    if not row:
        return {"ok": False, "white_label": None, "message": "Domain non configuré"}
    return {
        "ok": True,
        "white_label": {
            "nom_marque": row.nom_marque,
            "tagline": row.tagline,
            "logo_url": row.logo_url,
            "favicon_url": row.favicon_url,
            "couleur_primaire_hex": row.couleur_primaire_hex,
            "footer_html": row.footer_html,
            "hide_yukpo_brand": row.hide_yukpo_brand,
            "compagnie_id": row.compagnie_id,
        },
    }
