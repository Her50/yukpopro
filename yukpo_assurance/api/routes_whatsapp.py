"""
Routes FastAPI — WhatsApp Business (Meta Cloud API).
- GET  /webhook  : vérification webhook Meta
- POST /webhook  : réception messages entrants
- GET  /sessions : liste des sessions actives (admin)
- GET  /logs     : historique messages (admin)
- POST /envoyer  : envoi manuel d'un message (admin)
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db, CompagnieDB, SessionWhatsAppDB
from core.auth import get_current_user, TokenData
from core.multitenancy import require_module
from modules.whatsapp.gestionnaire_whatsapp import (
    MoteurConversationWhatsApp,
    ClientWhatsAppMeta,
    verifier_signature_meta,
)

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

async def _get_compagnie(compagnie_id: int, db: AsyncSession) -> Optional[CompagnieDB]:
    result = await db.execute(select(CompagnieDB).where(CompagnieDB.id == compagnie_id))
    return result.scalar_one_or_none()


async def _get_ou_creer_session(
    numero: str, compagnie_id: int, db: AsyncSession
) -> SessionWhatsAppDB:
    result = await db.execute(
        select(SessionWhatsAppDB).where(
            SessionWhatsAppDB.numero_client == numero,
            SessionWhatsAppDB.compagnie_id == compagnie_id,
            SessionWhatsAppDB.active == True,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        session = SessionWhatsAppDB(
            numero_client=numero,
            compagnie_id=compagnie_id,
            etat="accueil",
            sous_etat=None,
            contexte={},
            langue="fr",
            active=True,
        )
        db.add(session)
        await db.flush()
    return session


# ─────────────────────────────────────────────────────────────
# Webhook Meta — vérification (GET)
# ─────────────────────────────────────────────────────────────

@router.get("/webhook/{compagnie_id}", response_class=PlainTextResponse)
async def verifier_webhook(
    compagnie_id: int,
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify.token"),
    db: AsyncSession = Depends(get_db),
):
    """
    Meta envoie un GET pour vérifier le webhook.
    On compare hub.verify_token avec celui stocké dans CompagnieDB.
    """
    if hub_mode != "subscribe":
        raise HTTPException(400, "Mode invalide")

    compagnie = await _get_compagnie(compagnie_id, db)
    if not compagnie:
        raise HTTPException(404, "Compagnie introuvable")

    verify_token = compagnie.whatsapp_verify_token or ""
    if hub_verify_token != verify_token:
        raise HTTPException(403, "Verify token incorrect")

    return hub_challenge or ""


# ─────────────────────────────────────────────────────────────
# Webhook Meta — messages entrants (POST)
# ─────────────────────────────────────────────────────────────

@router.post("/webhook/{compagnie_id}")
async def recevoir_message(
    compagnie_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    x_hub_signature_256: Optional[str] = Header(None),
):
    """
    Réception des messages WhatsApp envoyés par les clients.
    Vérifie la signature HMAC-SHA256, puis traite en arrière-plan.
    """
    payload_bytes = await request.body()

    compagnie = await _get_compagnie(compagnie_id, db)
    if not compagnie:
        # Toujours retourner 200 pour éviter les re-tentatives Meta
        return {"status": "ignored"}

    # Vérification signature
    app_secret = compagnie.whatsapp_app_secret or ""
    if app_secret and x_hub_signature_256:
        if not verifier_signature_meta(payload_bytes, x_hub_signature_256, app_secret):
            raise HTTPException(403, "Signature invalide")

    try:
        data = json.loads(payload_bytes)
    except json.JSONDecodeError:
        return {"status": "ok"}

    # Extraction du message
    try:
        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        if "messages" not in value:
            return {"status": "ok"}  # statut de livraison, pas un message

        message = value["messages"][0]
        numero = message["from"]

        # Texte ou bouton interactif
        msg_type = message.get("type", "text")
        if msg_type == "text":
            texte = message["text"]["body"]
        elif msg_type == "interactive":
            inter = message["interactive"]
            if inter.get("type") == "button_reply":
                texte = inter["button_reply"]["id"]
            elif inter.get("type") == "list_reply":
                texte = inter["list_reply"]["id"]
            else:
                texte = ""
        else:
            texte = ""

    except (KeyError, IndexError):
        return {"status": "ok"}

    # Traitement en arrière-plan pour répondre vite (< 5 s requis par Meta)
    background_tasks.add_task(
        _traiter_message_bg,
        numero=numero,
        texte=texte,
        compagnie_id=compagnie_id,
        compagnie=compagnie,
    )

    return {"status": "ok"}


async def _traiter_message_bg(
    numero: str,
    texte: str,
    compagnie_id: int,
    compagnie: CompagnieDB,
):
    """Traitement asynchrone du message reçu."""
    from core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            session = await _get_ou_creer_session(numero, compagnie_id, db)

            moteur = MoteurConversationWhatsApp()
            reponse, nouvel_etat = await moteur.traiter_message(
                numero=numero,
                texte=texte,
                session=session,
                db_session=db,
                compagnie_id=compagnie_id,
            )

            session.etat = nouvel_etat
            session.derniere_activite = datetime.now(timezone.utc)
            await db.commit()

            # Envoi de la réponse
            client = ClientWhatsAppMeta(
                phone_number_id=compagnie.whatsapp_phone_id or "",
                access_token=compagnie.whatsapp_token or "",
            )
            await client.envoyer_texte(numero, reponse)

        except Exception as exc:
            print(f"[WhatsApp BG] Erreur : {exc}")
            await db.rollback()


# ─────────────────────────────────────────────────────────────
# Routes administration (requièrent authentification)
# ─────────────────────────────────────────────────────────────

@router.get(
    "/sessions",
    dependencies=[Depends(require_module("whatsapp"))],
)
async def lister_sessions(
    actives_seulement: bool = True,
    limit: int = Query(50, le=200),
    offset: int = 0,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Liste des sessions WhatsApp de la compagnie."""
    query = select(SessionWhatsAppDB).where(
        SessionWhatsAppDB.compagnie_id == current_user.compagnie_id
    )
    if actives_seulement:
        query = query.where(SessionWhatsAppDB.active == True)
    query = query.order_by(desc(SessionWhatsAppDB.derniere_activite)).offset(offset).limit(limit)
    result = await db.execute(query)
    sessions = result.scalars().all()

    return [
        {
            "id": s.id,
            "numero_client": s.numero_client,
            "etat": s.etat,
            "sous_etat": s.sous_etat,
            "langue": s.langue,
            "active": s.active,
            "derniere_activite": s.derniere_activite,
            "contexte": s.contexte,
        }
        for s in sessions
    ]


@router.delete(
    "/sessions/{session_id}",
    dependencies=[Depends(require_module("whatsapp"))],
)
async def fermer_session(
    session_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ferme / réinitialise une session WhatsApp."""
    result = await db.execute(
        select(SessionWhatsAppDB).where(
            SessionWhatsAppDB.id == session_id,
            SessionWhatsAppDB.compagnie_id == current_user.compagnie_id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session introuvable")
    session.active = False
    session.etat = "ferme"
    await db.commit()
    return {"message": "Session fermée"}


class EnvoiManuelSchema(BaseModel):
    numero: str
    message: str


@router.post(
    "/envoyer",
    dependencies=[Depends(require_module("whatsapp"))],
)
async def envoyer_message_manuel(
    payload: EnvoiManuelSchema,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Envoi manuel d'un message WhatsApp par un agent."""
    compagnie = await _get_compagnie(current_user.compagnie_id, db)
    if not compagnie:
        raise HTTPException(404, "Compagnie introuvable")

    client = ClientWhatsAppMeta(
        phone_number_id=compagnie.whatsapp_phone_id or "",
        access_token=compagnie.whatsapp_token or "",
    )
    ok = await client.envoyer_texte(payload.numero, payload.message)
    if not ok:
        raise HTTPException(502, "Échec envoi WhatsApp")
    return {"message": "Envoyé"}


class ConfigWhatsAppSchema(BaseModel):
    phone_id: str
    token: str
    verify_token: str
    app_secret: str = ""


@router.put(
    "/config",
    dependencies=[Depends(require_module("whatsapp"))],
)
async def configurer_whatsapp(
    config: ConfigWhatsAppSchema,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Configure les paramètres WhatsApp Business de la compagnie."""
    if "admin" not in current_user.permissions and "dg" not in current_user.role:
        raise HTTPException(403, "Droits insuffisants")

    compagnie = await _get_compagnie(current_user.compagnie_id, db)
    if not compagnie:
        raise HTTPException(404, "Compagnie introuvable")

    compagnie.whatsapp_phone_id = config.phone_id
    compagnie.whatsapp_token = config.token
    compagnie.whatsapp_verify_token = config.verify_token
    compagnie.whatsapp_app_secret = config.app_secret
    await db.commit()
    return {"message": "Configuration WhatsApp mise à jour"}
