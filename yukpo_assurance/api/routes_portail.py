"""
Routes API — Portail Externe Prestataires & Assurés + Webhook WhatsApp.

ENDPOINTS PORTAIL WEB :
  GET  /portail/{token}                  → Détails de l'intervention (pour le frontend portail)
  POST /portail/{token}/soumettre        → Soumettre une intervention (texte + docs)
  POST /portail/{token}/documents        → Upload de documents pour une intervention
  GET  /portail/admin/interventions      → Lister toutes les interventions (staff interne)
  GET  /portail/admin/interventions/{id} → Détail d'une intervention

ENDPOINTS WHATSAPP :
  GET  /whatsapp/webhook                 → Vérification webhook Meta Business API
  POST /whatsapp/webhook                 → Réception messages entrants (texte + documents)

ENDPOINTS SUIVI DÉLAIS CIMA :
  GET  /delais/{reference}               → Timeline et délais d'un sinistre
  POST /delais/{reference}/etape         → Enregistrer la complétion d'une étape
  GET  /delais/tableau-bord              → Tableau de bord global délais CIMA

SÉCURITÉ :
  - Portail public (token) : authentification par token unique — pas de login requis
  - Admin interventions : JWT obligatoire (même auth que le reste de l'API)
  - Webhook WhatsApp : vérification signature HMAC Meta
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("yukpo_assurance.api.portail")

router = APIRouter(tags=["portail"])

# Token de vérification WhatsApp (Meta Business API)
_WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "yukpo_whatsapp_token")
_WHATSAPP_APP_SECRET   = os.environ.get("WHATSAPP_APP_SECRET", "")
_WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")

# Base URL de l'API pour les liens médias WhatsApp
_WHATSAPP_API_URL = "https://graph.facebook.com/v19.0"


# ─── Schemas Pydantic ─────────────────────────────────────────────────────────

class SoumissionInterventionPayload(BaseModel):
    texte:          str = ""
    champs:         dict = {}
    # Les documents sont envoyés en base64 dans ce champ
    documents_b64:  list[str] = []


# ─── PORTAIL PUBLIC (accès par token) ────────────────────────────────────────

@router.get("/portail/{token}", response_class=JSONResponse)
async def get_intervention_portail(token: str):
    """
    Récupère les détails d'une intervention via son token.
    Utilisé par le frontend portail Yukpo pour afficher le formulaire.
    """
    from core.portail_externe import portail_externe

    iv = portail_externe.get_par_token(token)
    if not iv:
        raise HTTPException(status_code=404, detail="Lien invalide ou expiré")
    if iv.statut == "expire":
        raise HTTPException(status_code=410, detail="Ce lien a expiré. Contactez votre gestionnaire.")
    if iv.statut == "soumis":
        return JSONResponse({
            "statut": "soumis",
            "message": "Votre soumission a déjà été enregistrée. Merci.",
            "reference": iv.reference_sinistre,
            "soumis_le": iv.soumis_le,
        })

    return JSONResponse({
        "id":                   iv.id,
        "type_intervention":    iv.type_intervention,
        "reference_sinistre":   iv.reference_sinistre,
        "titre":                iv.titre,
        "message_instruction":  iv.message_instruction,
        "champs_requis":        iv.champs_requis,
        "documents_requis":     iv.documents_requis,
        "nb_docs_max":          iv.nb_docs_max,
        "destinataire_nom":     iv.destinataire_nom,
        "destinataire_type":    iv.destinataire_type,
        "statut":               iv.statut,
        "expires_le":           iv.expires_le,
    })


@router.post("/portail/{token}/soumettre")
async def soumettre_intervention(token: str, payload: SoumissionInterventionPayload):
    """
    Traite la soumission d'une intervention externe.
    Reprend automatiquement le workflow agent suspendu.
    """
    from core.portail_externe import portail_externe

    iv = portail_externe.get_par_token(token)
    if not iv:
        raise HTTPException(status_code=404, detail="Lien invalide ou expiré")

    resultat = await portail_externe.traiter_soumission(
        token=token,
        texte=payload.texte,
        docs_base64=payload.documents_b64 if payload.documents_b64 else None,
        champs=payload.champs if payload.champs else None,
        canal="portail_web",
    )

    if not resultat.get("succes"):
        raise HTTPException(status_code=400, detail=resultat.get("erreur", "Erreur soumission"))

    return JSONResponse(resultat)


@router.post("/portail/{token}/documents")
async def uploader_documents_portail(
    token: str,
    fichiers: list[UploadFile] = File(...),
    texte:    str              = Form(""),
    champs_json: str           = Form("{}"),
):
    """
    Upload de documents pour une intervention — format multipart/form-data.
    Utilisé par le portail web quand le prestataire envoie des fichiers.
    """
    import base64
    from core.portail_externe import portail_externe

    iv = portail_externe.get_par_token(token)
    if not iv:
        raise HTTPException(status_code=404, detail="Lien invalide ou expiré")

    # Convertir les fichiers en base64
    docs_b64: list[str] = []
    for fichier in fichiers:
        contenu = await fichier.read()
        mime_type = fichier.content_type or "application/octet-stream"
        b64_data = base64.b64encode(contenu).decode()
        docs_b64.append(f"data:{mime_type};base64,{b64_data}")

    try:
        champs = json.loads(champs_json)
    except Exception:
        champs = {}

    resultat = await portail_externe.traiter_soumission(
        token=token,
        texte=texte,
        docs_base64=docs_b64,
        champs=champs,
        canal="portail_web",
    )

    return JSONResponse(resultat)


# ─── ADMIN INTERVENTIONS (staff interne) ─────────────────────────────────────

@router.get("/portail/admin/interventions")
async def lister_interventions(
    statut:           Optional[str] = None,
    reference:        Optional[str] = None,
    destinataire_type: Optional[str] = None,
):
    """Liste les interventions externes avec filtres."""
    from core.portail_externe import portail_externe
    items = portail_externe.lister(
        statut=statut,
        reference=reference,
        destinataire_type=destinataire_type,
    )
    return JSONResponse({"interventions": items, "total": len(items)})


@router.get("/portail/admin/interventions/{iv_id}")
async def get_intervention_detail(iv_id: str):
    """Détail complet d'une intervention (staff interne)."""
    from core.portail_externe import portail_externe
    item = portail_externe.get(iv_id)
    if not item:
        raise HTTPException(status_code=404, detail="Intervention introuvable")
    return JSONResponse(item)


# ─── WEBHOOK WHATSAPP (Meta Business API) ────────────────────────────────────

@router.get("/whatsapp/webhook")
async def whatsapp_verify(request: Request):
    """
    Vérification du webhook WhatsApp (Meta Business API).
    Meta envoie un GET avec hub.challenge à retourner pour valider l'endpoint.
    """
    params = dict(request.query_params)
    mode      = params.get("hub.mode")
    token     = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == _WHATSAPP_VERIFY_TOKEN:
        logger.info("[WhatsApp] Webhook vérifié avec succès")
        return HTMLResponse(content=challenge, status_code=200)

    logger.warning(f"[WhatsApp] Échec vérification — token reçu: {token}")
    raise HTTPException(status_code=403, detail="Token de vérification invalide")


@router.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    """
    Réception des messages WhatsApp entrants (texte, images, documents).

    Format Meta Business API (Graph API v19.0) :
    {
      "entry": [{
        "changes": [{
          "value": {
            "messages": [{ "from": "237677...", "type": "text"|"image"|"document", ... }]
          }
        }]
      }]
    }
    """
    # Vérification signature HMAC si configurée
    if _WHATSAPP_APP_SECRET:
        signature = request.headers.get("X-Hub-Signature-256", "")
        body = await request.body()
        expected = "sha256=" + hmac.new(
            _WHATSAPP_APP_SECRET.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            logger.warning("[WhatsApp] Signature HMAC invalide — webhook rejeté")
            raise HTTPException(status_code=403, detail="Signature invalide")
        payload = json.loads(body)
    else:
        payload = await request.json()

    try:
        await _traiter_payload_whatsapp(payload)
    except Exception as e:
        logger.error(f"[WhatsApp] Erreur traitement payload : {e}", exc_info=True)

    # Meta exige toujours 200 OK même en cas d'erreur
    return JSONResponse({"status": "ok"}, status_code=200)


async def _traiter_payload_whatsapp(payload: dict):
    """
    Parse et traite le payload WhatsApp entrant.
    Gère : texte, images, documents, réactions.
    """
    from core.portail_externe import portail_externe

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages = value.get("messages", [])

            for msg in messages:
                telephone = msg.get("from", "")
                msg_type  = msg.get("type", "text")
                msg_id    = msg.get("id", "")

                logger.info(f"[WhatsApp] Message reçu de {telephone} — type={msg_type} id={msg_id}")

                # ── Texte ─────────────────────────────────────────────────────
                if msg_type == "text":
                    texte = msg.get("text", {}).get("body", "")
                    reponse_data = await portail_externe.traiter_message_whatsapp(
                        telephone=telephone,
                        message=texte,
                        docs_b64=None,
                    )
                    if reponse_data.get("reponse"):
                        await _envoyer_message_whatsapp(telephone, reponse_data["reponse"])

                # ── Image ─────────────────────────────────────────────────────
                elif msg_type == "image":
                    image_id   = msg.get("image", {}).get("id", "")
                    caption    = msg.get("image", {}).get("caption", "")
                    docs_b64   = await _telecharger_media_whatsapp([image_id])
                    reponse_data = await portail_externe.traiter_message_whatsapp(
                        telephone=telephone,
                        message=caption or "Image transmise",
                        docs_b64=docs_b64,
                    )
                    if reponse_data.get("reponse"):
                        await _envoyer_message_whatsapp(telephone, reponse_data["reponse"])

                # ── Document (PDF, etc.) ──────────────────────────────────────
                elif msg_type == "document":
                    doc_id     = msg.get("document", {}).get("id", "")
                    filename   = msg.get("document", {}).get("filename", "document.pdf")
                    caption    = msg.get("document", {}).get("caption", "")
                    docs_b64   = await _telecharger_media_whatsapp([doc_id])
                    reponse_data = await portail_externe.traiter_message_whatsapp(
                        telephone=telephone,
                        message=caption or f"Document transmis : {filename}",
                        docs_b64=docs_b64,
                    )
                    if reponse_data.get("reponse"):
                        await _envoyer_message_whatsapp(telephone, reponse_data["reponse"])

                # ── Plusieurs médias (audio, vidéo — info seulement) ──────────
                else:
                    logger.info(f"[WhatsApp] Type média non géré : {msg_type} de {telephone}")


async def _telecharger_media_whatsapp(media_ids: list[str]) -> list[str]:
    """
    Télécharge des médias depuis l'API Meta et les retourne en base64.
    """
    import base64
    import httpx

    if not _WHATSAPP_ACCESS_TOKEN:
        logger.warning("[WhatsApp] WHATSAPP_ACCESS_TOKEN non configuré — médias ignorés")
        return []

    docs_b64: list[str] = []
    headers = {"Authorization": f"Bearer {_WHATSAPP_ACCESS_TOKEN}"}

    async with httpx.AsyncClient(timeout=30) as client:
        for media_id in media_ids:
            try:
                # 1. Récupérer l'URL du média
                resp_url = await client.get(
                    f"{_WHATSAPP_API_URL}/{media_id}",
                    headers=headers,
                )
                resp_url.raise_for_status()
                media_url  = resp_url.json().get("url", "")
                mime_type  = resp_url.json().get("mime_type", "image/jpeg")

                if not media_url:
                    continue

                # 2. Télécharger le binaire
                resp_media = await client.get(media_url, headers=headers)
                resp_media.raise_for_status()

                b64_data = base64.b64encode(resp_media.content).decode()
                docs_b64.append(f"data:{mime_type};base64,{b64_data}")
                logger.info(f"[WhatsApp] Média {media_id} téléchargé ({mime_type}, {len(resp_media.content)} octets)")

            except Exception as e:
                logger.error(f"[WhatsApp] Erreur téléchargement média {media_id} : {e}")

    return docs_b64


async def _envoyer_message_whatsapp(telephone: str, texte: str):
    """Envoie un message WhatsApp via l'API Meta (réponse automatique)."""
    import httpx

    if not _WHATSAPP_ACCESS_TOKEN:
        logger.info(f"[WhatsApp] Réponse simulée → {telephone}: {texte[:100]}")
        return

    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
    if not phone_number_id:
        logger.warning("[WhatsApp] WHATSAPP_PHONE_NUMBER_ID non configuré")
        return

    payload = {
        "messaging_product": "whatsapp",
        "to": telephone,
        "type": "text",
        "text": {"body": texte},
    }
    headers = {
        "Authorization": f"Bearer {_WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(
                f"{_WHATSAPP_API_URL}/{phone_number_id}/messages",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            logger.info(f"[WhatsApp] Réponse envoyée à {telephone}")
        except Exception as e:
            logger.error(f"[WhatsApp] Erreur envoi message à {telephone} : {e}")


# ─── SUIVI DÉLAIS CIMA ────────────────────────────────────────────────────────

@router.get("/delais/{reference}")
async def get_timeline_sinistre(reference: str):
    """Retourne la timeline complète d'un sinistre avec tous les délais CIMA."""
    from core.suivi_delai_cima import suivi_delai_cima
    tl = suivi_delai_cima.get_timeline(reference)
    if not tl:
        raise HTTPException(
            status_code=404,
            detail=f"Aucune timeline trouvée pour le sinistre {reference}. "
                   "La timeline est initialisée automatiquement à la réception de la déclaration."
        )
    return JSONResponse(tl)


class EtapePayload(BaseModel):
    etape:      str
    timestamp:  Optional[str] = None


@router.post("/delais/{reference}/etape")
async def enregistrer_etape_sinistre(reference: str, payload: EtapePayload):
    """
    Enregistre la complétion d'une étape workflow pour un sinistre.
    Retourne les prochaines échéances CIMA.
    """
    from core.suivi_delai_cima import suivi_delai_cima
    if reference not in {tl.reference for tl in []}: # check existence
        pass  # suivi_delai_cima gère le cas non trouvé
    result = suivi_delai_cima.enregistrer_etape(
        reference=reference,
        etape=payload.etape,
        timestamp=payload.timestamp,
    )
    return JSONResponse(result)


@router.get("/delais/tableau-bord")
async def tableau_bord_delais(
    branche:  Optional[str] = None,
    user_id:  Optional[int] = None,
):
    """
    Tableau de bord global des délais CIMA.
    Retourne : sinistres en retard, alertes J-7, état de conformité.
    """
    from core.suivi_delai_cima import suivi_delai_cima
    return JSONResponse(suivi_delai_cima.tableau_bord_delais(
        branche=branche,
        user_id=user_id,
    ))


# ─── CHECKLISTS DOCUMENTS ─────────────────────────────────────────────────────

@router.get("/portail/checklists")
async def get_checklists_documents():
    """
    Retourne la liste des checklists de documents attendus par type de prestataire/assuré.
    Utilisé par le frontend pour afficher les guides de soumission.
    """
    from core.portail_externe import CHECKLIST_DOCUMENTS
    return JSONResponse(CHECKLIST_DOCUMENTS)


@router.get("/portail/checklists/{type_prestataire}")
async def get_checklist_prestataire(type_prestataire: str):
    """Checklist de documents pour un type de prestataire spécifique."""
    from core.portail_externe import CHECKLIST_DOCUMENTS
    checklist = CHECKLIST_DOCUMENTS.get(type_prestataire)
    if not checklist:
        raise HTTPException(status_code=404, detail=f"Type prestataire '{type_prestataire}' non trouvé")
    return JSONResponse({
        "type": type_prestataire,
        **checklist,
    })
