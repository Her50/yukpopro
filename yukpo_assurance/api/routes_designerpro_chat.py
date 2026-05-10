"""
Sprint C1 — Chat conversationnel Designer Pro (multi-tours).

L'utilisateur peut continuer son projet en chat continu :
  - "Faire-part décès 4 pages pour M. NGONO"          → nouveau projet
  - "Ajoute une page hommages"                          → modification projet actif
  - "Change la palette en bleu marine"                  → modification
  - "Translate to English"                              → traduction
  - "Génère une autre version"                          → regenerate (mêmes specs, nouveau seed)
  - "Génère maintenant un livret de mariage"            → nouveau projet (intent change)

Backend détecte l'intention (Haiku ~50 tokens) et route automatiquement vers
le bon endpoint interne. Le frontend ne fait qu'envoyer le brief + récupérer
le résultat — pas besoin de bouton dédié "Modifier".

Endpoints :
  POST /chat/message         → envoie un message dans la session active
  GET  /chat/session         → récupère la session active (historique)
  POST /chat/reset           → reset session (nouveau projet from scratch)
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from core.auth import TokenData, get_current_user

logger = logging.getLogger("yukpo_assurance.api.designerpro_chat")
router = APIRouter()

_SESSION_TTL_MINUTES = 30


class ChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=2, max_length=5000)
    medias_refs: Optional[list[str]] = None
    pays: str = Field(default="CM")
    langue: str = Field(default="fr")


class ChatMessageResponse(BaseModel):
    intent: str   # nouveau_projet | modification | traduction | regenerate_seed | inconnu
    confiance: float
    session_id: str
    projet_actif_id: Optional[str] = None
    raison: Optional[str] = None
    routage: dict = Field(default_factory=dict)
    # Présence d'une 'action' = le frontend doit suivre cette indication
    # (ex: {endpoint: "/generer-auto", payload: {...}})


async def _get_or_create_session(user_id: int, compagnie_id: int) -> "DesignerProSessionDB":
    """Récupère la session active de l'user (TTL 30min) ou en crée une nouvelle."""
    from core.database import async_session_maker, DesignerProSessionDB
    cutoff = datetime.utcnow() - timedelta(minutes=_SESSION_TTL_MINUTES)
    async with async_session_maker() as db:
        # Cherche session active récente
        sess = (await db.execute(
            select(DesignerProSessionDB).where(
                DesignerProSessionDB.user_id == user_id,
                DesignerProSessionDB.derniere_interaction >= cutoff,
            ).order_by(DesignerProSessionDB.derniere_interaction.desc()).limit(1)
        )).scalar_one_or_none()
        if sess:
            return sess
        # Sinon nouvelle
        sess = DesignerProSessionDB(
            session_id=str(uuid.uuid4()), user_id=user_id, compagnie_id=compagnie_id,
            historique=[], derniere_interaction=datetime.utcnow(),
        )
        db.add(sess)
        await db.commit()
        await db.refresh(sess)
        return sess


async def _classifier_intent(
    message: str, projet_actif_id: Optional[str], historique_recent: list,
) -> dict:
    """
    Sprint C1.2 — Classifie l'intention de l'user via Haiku (~50 tokens).

    Retourne {intent, confiance, raison}.
    intent ∈ {nouveau_projet, modification, traduction, regenerate_seed, inconnu}
    """
    try:
        from core.ia_client import ia_client, ModeIA, ModelePrioritaire
        ctx_actif = (
            f"PROJET ACTIF : {projet_actif_id} (l'user a déjà généré quelque chose)"
            if projet_actif_id else
            "AUCUN projet actif (l'user démarre)"
        )
        # Echantillon historique : 3 derniers tours
        hist_recent = historique_recent[-3:] if historique_recent else []
        ctx_hist = "\n".join(
            f"{m.get('role')} : {(m.get('content') or '')[:150]}" for m in hist_recent
        )
        prompt = (
            f"Classifie l'INTENTION de l'utilisateur dans un chat Yukpo Designer Pro.\n\n"
            f"{ctx_actif}\n\n"
            f"HISTORIQUE RÉCENT :\n{ctx_hist or '(vide)'}\n\n"
            f"NOUVEAU MESSAGE : «{message[:1500]}»\n\n"
            f"Catégories :\n"
            f"  - nouveau_projet : créer un nouveau visuel from scratch (mots-clés : génère, "
            f"crée, nouveau, autre projet, switch sujet/format)\n"
            f"  - modification : modifier le projet actif (ajoute, change, remplace, supprime, "
            f"déplace, références à des pages, couleurs, palette, mediums)\n"
            f"  - traduction : passe le projet actif dans une autre langue (translate, traduis, "
            f"version anglaise, en wolof, etc.)\n"
            f"  - regenerate_seed : générer une autre variante des mêmes specs (autre version, "
            f"essaie autre chose, varie, remix)\n"
            f"  - inconnu : si vraiment ambigu\n\n"
            f"Si AUCUN projet actif, l'intention est forcément 'nouveau_projet'.\n\n"
            f"FORMAT JSON STRICT :\n"
            f'{{"intent": "...", "confiance": 0.92, "raison": "..."}}\n\n'
            f"Retourne UNIQUEMENT le JSON."
        )
        rep = await ia_client.appeler(
            prompt=prompt, mode=ModeIA.PRECISION, json_attendu=True,
            forcer_modele=ModelePrioritaire.CLAUDE_HAIKU,
            max_tokens_override=200, utiliser_cache=True,
        )
        import json
        try:
            data = json.loads(rep.contenu)
        except Exception:
            import re
            m = re.search(r'\{.*\}', rep.contenu, re.DOTALL)
            data = json.loads(m.group()) if m else {}
        intent = data.get("intent", "inconnu")
        if intent not in ("nouveau_projet", "modification", "traduction",
                          "regenerate_seed", "inconnu"):
            intent = "inconnu"
        if not projet_actif_id and intent in ("modification", "traduction", "regenerate_seed"):
            intent = "nouveau_projet"
        return {
            "intent": intent,
            "confiance": float(data.get("confiance", 0.5)),
            "raison": data.get("raison", "")[:200],
        }
    except Exception as e:
        logger.warning(f"[Chat/intent] échec : {e}")
        return {
            "intent": "modification" if projet_actif_id else "nouveau_projet",
            "confiance": 0.4, "raison": f"fallback (LLM error): {e}",
        }


@router.get("/session", tags=["Designer Pro Chat"])
async def get_session(current_user: TokenData = Depends(get_current_user)):
    """Récupère la session active (historique) de l'utilisateur."""
    cid = getattr(current_user, "compagnie_id", None) or 1
    sess = await _get_or_create_session(current_user.user_id, cid)
    return {
        "session_id": sess.session_id,
        "projet_actif_id": sess.projet_actif_id,
        "historique": sess.historique or [],
        "derniere_interaction": sess.derniere_interaction.isoformat(),
        "ttl_minutes": _SESSION_TTL_MINUTES,
    }


@router.post("/message", response_model=ChatMessageResponse, tags=["Designer Pro Chat"])
async def envoyer_message(
    demande: ChatMessageRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Sprint C1 — Envoie un message dans la session active.

    Étapes :
      1. Récupère ou crée la session de l'user (TTL 30min)
      2. Classifie l'intention (Haiku) selon projet_actif_id + historique
      3. Retourne intent + routage suggéré pour le frontend
         (le frontend appelle ensuite /generer-auto, /modifier, /multilingual,
          ou /regenerer en fonction)
      4. Met à jour l'historique + derniere_interaction

    Le frontend N'A PAS BESOIN d'appeler explicitement /generer ou /modifier :
    il regarde `intent` de la réponse et appelle l'endpoint correspondant
    automatiquement.
    """
    from core.database import async_session_maker, DesignerProSessionDB

    cid = getattr(current_user, "compagnie_id", None) or 1
    sess = await _get_or_create_session(current_user.user_id, cid)

    # Classification intent
    intent_data = await _classifier_intent(
        demande.message, sess.projet_actif_id, sess.historique or [],
    )
    intent = intent_data["intent"]

    # Routage suggéré pour le frontend
    routage: dict = {}
    if intent == "nouveau_projet":
        routage = {
            "endpoint": "/api/v1/bureau/infographie-pro/generer-auto",
            "method": "POST",
            "payload_template": {
                "brief": demande.message, "pays": demande.pays, "langue": demande.langue,
                "medias_refs": demande.medias_refs, "mode_visuel": "auto",
            },
        }
    elif intent == "modification":
        routage = {
            "endpoint": "/api/v1/bureau/infographie-pro/modifier",
            "method": "POST",
            "payload_template": {
                "projet_id": sess.projet_actif_id, "instructions": demande.message,
                "medias_refs_supplementaires": demande.medias_refs, "pays": demande.pays,
            },
        }
    elif intent == "traduction":
        # On laisse aussi /modifier gérer (Sonnet comprend), OU on peut router vers
        # /multilingual si on extrait les codes langues. Simplification : /modifier.
        routage = {
            "endpoint": "/api/v1/bureau/infographie-pro/modifier",
            "method": "POST",
            "payload_template": {
                "projet_id": sess.projet_actif_id, "instructions": demande.message,
                "pays": demande.pays,
            },
            "hint": "Le LLM Sonnet va traduire tous les textuels en gardant la structure.",
        }
    elif intent == "regenerate_seed":
        routage = {
            "endpoint": "/api/v1/bureau/infographie-pro/modifier",
            "method": "POST",
            "payload_template": {
                "projet_id": sess.projet_actif_id,
                "instructions": (
                    f"{demande.message}\n\n"
                    "[INSTRUCTION SYSTÈME : génère une nouvelle variante des mêmes "
                    "sujets/contenus avec un autre angle visuel — varie compositions, "
                    "tons, accents, mais garde la même structure de pages.]"
                ),
                "pays": demande.pays,
            },
        }

    # Append à l'historique
    async with async_session_maker() as db:
        sess_db = (await db.execute(
            select(DesignerProSessionDB).where(
                DesignerProSessionDB.session_id == sess.session_id
            )
        )).scalar_one_or_none()
        if sess_db:
            hist = list(sess_db.historique or [])
            hist.append({
                "role": "user", "ts": datetime.utcnow().isoformat(),
                "content": demande.message[:2000],
                "intent": intent, "confiance": intent_data["confiance"],
            })
            # Cap last 50
            sess_db.historique = hist[-50:]
            sess_db.derniere_interaction = datetime.utcnow()
            await db.commit()

    return ChatMessageResponse(
        intent=intent, confiance=float(intent_data["confiance"]),
        session_id=sess.session_id, projet_actif_id=sess.projet_actif_id,
        raison=intent_data.get("raison"), routage=routage,
    )


class UpdateProjetActifRequest(BaseModel):
    projet_id: str = Field(..., max_length=120)


@router.post("/session/projet-actif", tags=["Designer Pro Chat"])
async def update_projet_actif(
    demande: UpdateProjetActifRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Met à jour le projet_actif_id de la session courante.
    Appelé par le frontend après une génération réussie.
    """
    from core.database import async_session_maker, DesignerProSessionDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    sess = await _get_or_create_session(current_user.user_id, cid)
    async with async_session_maker() as db:
        sess_db = (await db.execute(
            select(DesignerProSessionDB).where(
                DesignerProSessionDB.session_id == sess.session_id
            )
        )).scalar_one_or_none()
        if sess_db:
            sess_db.projet_actif_id = demande.projet_id
            sess_db.derniere_interaction = datetime.utcnow()
            # Append yukpo response to history
            hist = list(sess_db.historique or [])
            hist.append({
                "role": "yukpo", "ts": datetime.utcnow().isoformat(),
                "content": f"Projet généré : {demande.projet_id}",
                "projet_id": demande.projet_id,
            })
            sess_db.historique = hist[-50:]
            await db.commit()
    return {"ok": True, "session_id": sess.session_id, "projet_actif_id": demande.projet_id}


@router.post("/reset", tags=["Designer Pro Chat"])
async def reset_session(current_user: TokenData = Depends(get_current_user)):
    """
    Reset la session active (force un nouveau projet from scratch).
    L'historique précédent est conservé en archive (séparée par derniere_interaction).
    """
    from core.database import async_session_maker, DesignerProSessionDB
    cid = getattr(current_user, "compagnie_id", None) or 1
    new_id = str(uuid.uuid4())
    async with async_session_maker() as db:
        new_sess = DesignerProSessionDB(
            session_id=new_id, user_id=current_user.user_id, compagnie_id=cid,
            historique=[], derniere_interaction=datetime.utcnow(),
        )
        db.add(new_sess)
        await db.commit()
    return {"ok": True, "session_id": new_id, "message": "Nouvelle session"}
