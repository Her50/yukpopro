"""Routes Landing Leads (Phase A Sprint 1).

Endpoints :

  POST /api/v1/landing-leads/{slug}        (public, sans auth)
      → Capture un lead depuis le formulaire de contact d'une landing
        publiée. Honeypot + rate-limit IP avant débit.

  GET  /api/v1/pro/landing-leads            (auth)
      → Liste paginée des leads du user connecté (filtres slug/statut/période).

  GET  /api/v1/pro/landing-leads/export.csv (auth)
      → Export CSV téléchargeable.

  PATCH /api/v1/pro/landing-leads/{lead_id} (auth)
      → Met à jour statut et notes (marquer contacté, converti, etc.).

Facturation (sur le MARCHAND propriétaire du slug, JAMAIS le visiteur).
Mapping vers forfaits EXISTANTS uniquement (pas de nouveau type) :
  • lead capturé en DB              → `client_action` (10 crédits)
  • notif WhatsApp marchand          → `whatsapp_message` (10 crédits)
  • notif email marchand SendGrid    → `whatsapp_message` (équiv. "envoi message")
"""
from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Path, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import TokenData, get_current_user
from core.database import (
    LandingLeadDB, LandingPublicationDB, UtilisateurDB,
    async_session_maker,
)

logger = logging.getLogger("yukpo_assurance.api.landing_leads")

router_public = APIRouter()  # exposé sans auth pour le form public
router_pro = APIRouter()     # exposé avec auth derrière /pro


async def _get_db():
    async with async_session_maker() as session:
        yield session


# ─── Rate limit in-memory (5 leads / IP / heure / slug) ──────────────────────
# Pas de Redis pour rester simple Sprint 1. Mémoire process — accept pour
# YukpoPro single-machine. Migration Redis triviale si scale-out.

_RATE_LIMIT_PAR_IP_SLUG: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_RATE_LIMIT_WINDOW_S = 3600
_RATE_LIMIT_MAX = 5


def _rate_limit_allow(ip: str, slug: str) -> bool:
    """True si l'IP peut encore poster sur ce slug dans la fenêtre."""
    key = (ip, slug)
    now = time.time()
    dq = _RATE_LIMIT_PAR_IP_SLUG[key]
    while dq and dq[0] < now - _RATE_LIMIT_WINDOW_S:
        dq.popleft()
    if len(dq) >= _RATE_LIMIT_MAX:
        return False
    dq.append(now)
    return True


def _hash_ip(ip: str) -> str:
    """sha256 IP — RGPD-friendly, pas d'IP en clair stockée."""
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:64]


# ─── Schemas ──────────────────────────────────────────────────────────────────

class LeadInput(BaseModel):
    """Payload accepté en form-data OU JSON.

    Note Pydantic v2 : les noms de fields avec leading underscore sont
    réservés/interdits. On utilise `hp_bot` (sans `_`) avec un alias
    `_hp_bot` pour matcher le nom du champ HTML hidden honeypot.
    """
    model_config = {"populate_by_name": True}

    nom: Optional[str] = Field(None, max_length=120)
    email: Optional[str] = Field(None, max_length=255)
    telephone: Optional[str] = Field(None, max_length=40)
    message: Optional[str] = Field(None, max_length=4000)
    source: str = Field("form", max_length=40)
    hp_bot: Optional[str] = Field(None, max_length=200, alias="_hp_bot")

    @field_validator("email")
    @classmethod
    def _email_format(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("email invalide")
        return v.lower().strip()


class LeadOut(BaseModel):
    id: int
    slug: str
    nom: Optional[str]
    email: Optional[str]
    telephone: Optional[str]
    message: Optional[str]
    source: str
    statut: str
    notes: Optional[str]
    created_at: datetime


class LeadPatch(BaseModel):
    statut: Optional[str] = Field(None, pattern=r"^(non_lu|lu|contacte|converti|perdu)$")
    notes: Optional[str] = Field(None, max_length=2000)


# ─── Endpoint PUBLIC ──────────────────────────────────────────────────────────

@router_public.post(
    "/{slug}",
    summary="Capture un lead depuis le form public d'une landing publiée",
)
async def capturer_lead_public(
    request: Request,
    slug: str = Path(..., min_length=3, max_length=60,
                     pattern=r"^[a-z0-9][a-z0-9-]{1,58}[a-z0-9]$"),
    nom: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    telephone: Optional[str] = Form(None),
    message: Optional[str] = Form(None),
    source: str = Form("form"),
    hp_bot: Optional[str] = Form(None, alias="_hp_bot"),
    db: AsyncSession = Depends(_get_db),
):
    """Endpoint PUBLIC sans auth. Anti-spam : honeypot + rate-limit IP+slug.

    Le marchand propriétaire du slug est débité (landing_lead_capture)
    puis notifié WhatsApp + email selon les coordonnées disponibles.
    """
    # 0. Honeypot : un bot rempli ça, un humain non → on ack silencieusement
    if hp_bot:
        logger.info(f"[Leads] honeypot trigger slug={slug}")
        return {"ok": True, "id": None}  # 200 silencieux

    # 1. Rate-limit IP
    ip = (request.client.host if request.client else "0.0.0.0")
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        ip = fwd.split(",")[0].strip() or ip
    if not _rate_limit_allow(ip, slug):
        logger.warning(f"[Leads] rate-limit IP={ip} slug={slug}")
        raise HTTPException(429, "Trop de soumissions — réessayez dans 1h.")

    # 2. Validation soft champs (au moins email OU téléphone)
    nom = (nom or "").strip()[:120] or None
    email_ok = (email or "").strip().lower() or None
    telephone_ok = (telephone or "").strip()[:40] or None
    message_ok = (message or "").strip()[:4000] or None
    if not (email_ok or telephone_ok):
        raise HTTPException(400, "email ou téléphone requis")

    # 3. Existence du slug + récup propriétaire
    res = await db.execute(
        select(LandingPublicationDB).where(LandingPublicationDB.slug == slug)
    )
    pub = res.scalar_one_or_none()
    if not pub:
        raise HTTPException(404, "Landing introuvable")

    # 4. Insertion lead
    user_agent = request.headers.get("user-agent", "")[:255]
    lead = LandingLeadDB(
        slug=slug, nom=nom, email=email_ok, telephone=telephone_ok,
        message=message_ok, source=source[:40],
        ip_hash=_hash_ip(ip), user_agent=user_agent,
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    logger.info(f"[Leads] capturé id={lead.id} slug={slug} (owner user={pub.user_id})")

    # 5. Débit forfait sur le MARCHAND propriétaire du slug (pas le visiteur)
    #    Mapping → `client_action` existant (lead = nouvelle fiche contact).
    try:
        from modules.bureau.service_credits_bureau import debiter_forfait_unifie
        await debiter_forfait_unifie(
            pub.user_id, "client_action", module="landing_leads",
        )
    except Exception as _e:
        logger.warning(f"[Leads] débit capture non bloquant : {_e}")

    # 6. Notifications WhatsApp + email au marchand (non bloquant)
    try:
        await _notifier_marchand(pub.user_id, slug, lead, db)
    except Exception as e:
        logger.warning(f"[Leads] notif marchand échec : {e}")

    # 7. Auto-reply J+0 au visiteur (Phase B4) — non bloquant
    if lead.email:
        try:
            from core.database import LandingFollowupSettingsDB
            from tasks.landing_followup_tasks import envoyer_auto_reply_j0
            fu = (await db.execute(
                select(LandingFollowupSettingsDB).where(
                    LandingFollowupSettingsDB.user_id == pub.user_id
                )
            )).scalar_one_or_none()
            envoye = await envoyer_auto_reply_j0(lead, fu)
            if envoye:
                from modules.bureau.service_credits_bureau import debiter_forfait_unifie
                await debiter_forfait_unifie(
                    pub.user_id, "whatsapp_message", module="landing_followup_j0",
                )
        except Exception as e:
            logger.debug(f"[Leads/auto-reply] échec : {e}")

    return {"ok": True, "id": lead.id}


async def _notifier_marchand(
    marchand_user_id: int, slug: str, lead: LandingLeadDB, db: AsyncSession,
) -> None:
    """Envoie notif WhatsApp + email au marchand. Débit forfait par canal."""
    res = await db.execute(
        select(UtilisateurDB).where(UtilisateurDB.id == marchand_user_id)
    )
    marchand = res.scalar_one_or_none()
    if not marchand:
        return

    from modules.bureau.service_credits_bureau import debiter_forfait_unifie

    apercu = (lead.message or "")[:160]
    contenu_wa = (
        f"🔔 Nouveau lead sur {slug}.yukpomnang.com\n\n"
        f"Nom : {lead.nom or '—'}\n"
        f"Email : {lead.email or '—'}\n"
        f"Téléphone : {lead.telephone or '—'}\n"
        + (f"\nMessage : {apercu}" if apercu else "")
        + f"\n\nGérer : https://yukpopro.yukpomnang.com/mes-leads"
    )

    # WhatsApp si tél marchand (forfait `whatsapp_message` existant débité)
    tel = getattr(marchand, "telephone", None)
    if tel:
        try:
            from core.notifications import envoyer_whatsapp
            from modules.bureau.service_credits_bureau import debiter_forfait_unifie
            await envoyer_whatsapp(tel, contenu_wa,
                                   metadata={"type": "landing_lead", "slug": slug})
            await debiter_forfait_unifie(
                marchand_user_id, "whatsapp_message", module="landing_leads",
            )
        except Exception as e:
            logger.warning(f"[Leads/notif] WA échec user={marchand_user_id}: {e}")

    # Email si email marchand — mapping vers `whatsapp_message` (sémantique
    # "envoi message", évite création d'un nouveau type "email").
    mail = getattr(marchand, "email", None)
    if mail:
        try:
            from core.notifications import _envoyer_email  # type: ignore
            from modules.bureau.service_credits_bureau import debiter_forfait_unifie
            sujet = f"Nouveau lead — {slug}"
            corps = (
                f"<h2>Nouveau lead</h2>"
                f"<p>Landing : <strong>{slug}.yukpomnang.com</strong></p>"
                f"<ul>"
                f"<li>Nom : {lead.nom or '—'}</li>"
                f"<li>Email : {lead.email or '—'}</li>"
                f"<li>Téléphone : {lead.telephone or '—'}</li>"
                f"</ul>"
                + (f"<p>{apercu}</p>" if apercu else "")
                + f'<p><a href="https://yukpopro.yukpomnang.com/mes-leads">'
                  f"Gérer dans YukpoPro</a></p>"
            )
            await _envoyer_email(mail, corps, sujet=sujet)  # type: ignore[call-arg]
            await debiter_forfait_unifie(
                marchand_user_id, "whatsapp_message", module="landing_leads",
            )
        except Exception as e:
            logger.warning(f"[Leads/notif] email échec user={marchand_user_id}: {e}")


# ─── Endpoints PRO (auth) ─────────────────────────────────────────────────────

@router_pro.get(
    "/landing-leads",
    summary="Liste paginée des leads du user connecté",
)
async def lister_leads_pro(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
    slug: Optional[str] = Query(None),
    statut: Optional[str] = Query(None,
        pattern=r"^(non_lu|lu|contacte|converti|perdu)$"),
    jours: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Retourne leads owned-by-user dans les N derniers jours."""
    debut = datetime.utcnow() - timedelta(days=jours)
    q = (
        select(LandingLeadDB, LandingPublicationDB.slug)
        .join(LandingPublicationDB,
              LandingPublicationDB.slug == LandingLeadDB.slug)
        .where(LandingPublicationDB.user_id == current_user.user_id)
        .where(LandingLeadDB.created_at >= debut)
        .order_by(desc(LandingLeadDB.created_at))
        .limit(limit).offset(offset)
    )
    if slug:
        q = q.where(LandingLeadDB.slug == slug)
    if statut:
        q = q.where(LandingLeadDB.statut == statut)

    res = await db.execute(q)
    rows = res.all()

    # Total + stats
    q_total = (
        select(func.count(LandingLeadDB.id))
        .join(LandingPublicationDB,
              LandingPublicationDB.slug == LandingLeadDB.slug)
        .where(LandingPublicationDB.user_id == current_user.user_id)
        .where(LandingLeadDB.created_at >= debut)
    )
    if slug:
        q_total = q_total.where(LandingLeadDB.slug == slug)
    total = (await db.execute(q_total)).scalar() or 0

    q_stats = (
        select(LandingLeadDB.statut, func.count(LandingLeadDB.id))
        .join(LandingPublicationDB,
              LandingPublicationDB.slug == LandingLeadDB.slug)
        .where(LandingPublicationDB.user_id == current_user.user_id)
        .where(LandingLeadDB.created_at >= debut)
        .group_by(LandingLeadDB.statut)
    )
    stats_rows = (await db.execute(q_stats)).all()
    par_statut = {s: int(n) for s, n in stats_rows}
    converti = par_statut.get("converti", 0)
    taux_conv = round(100.0 * converti / total, 1) if total else 0.0

    return {
        "leads": [
            {
                "id": r[0].id, "slug": r[0].slug,
                "nom": r[0].nom, "email": r[0].email,
                "telephone": r[0].telephone, "message": r[0].message,
                "source": r[0].source, "statut": r[0].statut,
                "notes": r[0].notes,
                "created_at": r[0].created_at.isoformat(),
            } for r in rows
        ],
        "total": int(total),
        "par_statut": par_statut,
        "taux_conversion_pct": taux_conv,
        "limit": limit, "offset": offset,
    }


@router_pro.get(
    "/landing-leads/export.csv",
    summary="Export CSV des leads du user connecté",
)
async def exporter_leads_csv(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
    slug: Optional[str] = Query(None),
    jours: int = Query(90, ge=1, le=365),
):
    debut = datetime.utcnow() - timedelta(days=jours)
    q = (
        select(LandingLeadDB)
        .join(LandingPublicationDB,
              LandingPublicationDB.slug == LandingLeadDB.slug)
        .where(LandingPublicationDB.user_id == current_user.user_id)
        .where(LandingLeadDB.created_at >= debut)
        .order_by(desc(LandingLeadDB.created_at))
    )
    if slug:
        q = q.where(LandingLeadDB.slug == slug)
    rows = (await db.execute(q)).scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "id", "slug", "date", "nom", "email", "telephone",
        "message", "source", "statut", "notes",
    ])
    for r in rows:
        writer.writerow([
            r.id, r.slug, r.created_at.isoformat(),
            r.nom or "", r.email or "", r.telephone or "",
            (r.message or "").replace("\n", " "), r.source,
            r.statut, (r.notes or "").replace("\n", " "),
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="leads-{int(time.time())}.csv"'},
    )


@router_pro.patch(
    "/landing-leads/{lead_id}",
    summary="Met à jour statut/notes d'un lead (ownership vérifié)",
)
async def patch_lead(
    lead_id: int,
    patch: LeadPatch,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    res = await db.execute(
        select(LandingLeadDB, LandingPublicationDB)
        .join(LandingPublicationDB,
              LandingPublicationDB.slug == LandingLeadDB.slug)
        .where(LandingLeadDB.id == lead_id)
    )
    row = res.one_or_none()
    if not row:
        raise HTTPException(404, "Lead introuvable")
    lead, pub = row
    if pub.user_id != current_user.user_id:
        raise HTTPException(403, "Lead non possédé")

    if patch.statut is not None:
        lead.statut = patch.statut
    if patch.notes is not None:
        lead.notes = patch.notes
    await db.commit()
    return {"ok": True, "id": lead.id, "statut": lead.statut, "notes": lead.notes}


@router_public.post(
    "/{slug}/newsletter",
    summary="Inscription newsletter depuis form public d'une landing (Phase B3)",
)
async def capturer_newsletter_public(
    request: Request,
    slug: str = Path(..., min_length=3, max_length=60,
                     pattern=r"^[a-z0-9][a-z0-9-]{1,58}[a-z0-9]$"),
    email: str = Form(...),
    hp_bot: Optional[str] = Form(None, alias="_hp_bot"),
    db: AsyncSession = Depends(_get_db),
):
    """Inscrit le visiteur à la newsletter Brevo/Mailchimp du marchand.

    Public sans auth. Honeypot + rate-limit IP (réutilise le mécanisme
    landing leads). En cas de succès, enregistre AUSSI un lead avec
    source='newsletter' pour le marchand.
    """
    if hp_bot:
        return {"ok": True}

    ip = (request.client.host if request.client else "0.0.0.0")
    if not _rate_limit_allow(ip, slug):
        raise HTTPException(429, "Trop de soumissions — réessayez dans 1h.")

    email_norm = (email or "").strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email_norm):
        raise HTTPException(400, "Email invalide")

    from core.database import LandingPublicationDB, TrackingSettingsDB
    pub = (await db.execute(
        select(LandingPublicationDB).where(LandingPublicationDB.slug == slug)
    )).scalar_one_or_none()
    if not pub:
        raise HTTPException(404, "Landing introuvable")

    settings_row = (await db.execute(
        select(TrackingSettingsDB).where(
            TrackingSettingsDB.user_id == pub.user_id
        )
    )).scalar_one_or_none()
    provider = (settings_row.newsletter_provider if settings_row else None) or "none"
    api_key = settings_row.newsletter_api_key if settings_row else None
    list_id = settings_row.newsletter_list_id if settings_row else None

    pushed_provider = False
    if provider == "brevo" and api_key:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15.0) as client:
                rep = await client.post(
                    "https://api.brevo.com/v3/contacts",
                    headers={"api-key": api_key, "accept": "application/json",
                             "content-type": "application/json"},
                    json={
                        "email": email_norm,
                        "listIds": [int(list_id)] if list_id and list_id.isdigit() else [],
                        "updateEnabled": True,
                    },
                )
                pushed_provider = rep.status_code in (201, 204, 400)  # 400 = déjà existant
        except Exception as e:
            logger.warning(f"[Newsletter/brevo] échec : {e}")
    elif provider == "mailchimp" and api_key and list_id:
        try:
            import httpx
            dc = api_key.split("-", 1)[-1] if "-" in api_key else "us1"
            async with httpx.AsyncClient(timeout=15.0) as client:
                rep = await client.post(
                    f"https://{dc}.api.mailchimp.com/3.0/lists/{list_id}/members",
                    auth=("yukpo", api_key),
                    json={"email_address": email_norm, "status": "subscribed"},
                )
                pushed_provider = rep.status_code in (200, 201, 400)
        except Exception as e:
            logger.warning(f"[Newsletter/mailchimp] échec : {e}")

    # Enregistrer aussi comme lead local (source=newsletter) pour suivi
    lead = LandingLeadDB(
        slug=slug, email=email_norm, source="newsletter",
        ip_hash=_hash_ip(ip),
        user_agent=request.headers.get("user-agent", "")[:255],
    )
    db.add(lead)
    await db.commit()

    # Débit forfait existant côté marchand
    try:
        from modules.bureau.service_credits_bureau import debiter_forfait_unifie
        await debiter_forfait_unifie(
            pub.user_id, "client_action", module="landing_newsletter",
        )
    except Exception as _e:
        logger.debug(f"[Newsletter] débit non bloquant : {_e}")

    return {"ok": True, "pushed_provider": pushed_provider,
            "provider": provider}


@router_pro.get(
    "/landing-publications",
    summary="Liste les landings publiées du user connecté",
)
async def lister_publications(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(_get_db),
):
    res = await db.execute(
        select(LandingPublicationDB)
        .where(LandingPublicationDB.user_id == current_user.user_id)
        .order_by(desc(LandingPublicationDB.derniere_modif))
    )
    pubs = res.scalars().all()
    return {
        "publications": [
            {
                "slug": p.slug,
                "url_public": p.url_public,
                "plan": p.plan,
                "html_fichier_id": p.html_fichier_id,
                "cree_le": p.cree_le.isoformat(),
                "derniere_modif": p.derniere_modif.isoformat(),
            } for p in pubs
        ]
    }
