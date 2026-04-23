"""Routes Chat IA — YukpoIA Assurance (sessions, multimodal, mémoire)"""
import asyncio
import base64
import json
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, AsyncGenerator

import anthropic

from modules.chat.yukpo_ia_assurance import (
    Attachment, TypeAttachment,
    chat_assurance, creer_session, get_session, lister_sessions,
)
from core.auth import TokenData, get_current_user, require_permission, _decoder_token
from config.settings import settings

logger = logging.getLogger("yukpo_assurance.chat")

router = APIRouter(dependencies=[Depends(get_current_user)])


class MessageRequest(BaseModel):
    session_id: Optional[str] = None
    user_id: int = 1
    role: str = "agent"
    message: str
    ecran_contexte: Optional[str] = None


class NouvelleSessionRequest(BaseModel):
    user_id: int = 1
    role: str = "agent"
    titre: Optional[str] = None
    ecran_contexte: Optional[str] = None


class AttachmentRequest(BaseModel):
    type: str         # "image" | "audio" | "pdf" | "excel" | "word"
    data_b64: str
    filename: str
    mime_type: str


class MessageAvecAttachmentRequest(BaseModel):
    session_id: Optional[str] = None
    user_id: int = 1
    role: str = "agent"
    message: str
    attachments: list[AttachmentRequest] = []


@router.post("/sessions")
async def creer_nouvelle_session(
    req: NouvelleSessionRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Crée une nouvelle session de chat (user_id vient du token JWT)"""
    session = creer_session(
        user_id=current_user.user_id,
        role=current_user.role,
        titre=req.titre,
    )
    if req.ecran_contexte:
        session.ecran_contexte = req.ecran_contexte
    return {
        "session_id": session.session_id,
        "titre": session.titre,
        "creee_le": session.creee_le.isoformat(),
    }


@router.get("/sessions/mes-sessions")
async def mes_sessions(current_user: TokenData = Depends(get_current_user)):
    """Liste les sessions de chat de l'utilisateur connecté"""
    return {"sessions": lister_sessions(current_user.user_id)}


@router.post("/message")
async def envoyer_message(
    req: MessageRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Envoie un message au chat IA YukpoAssurance.
    Crée automatiquement une session si session_id absent.
    L'identité utilisateur vient du token JWT.
    """
    if req.session_id:
        session = get_session(req.session_id)
        if not session:
            raise HTTPException(404, f"Session {req.session_id} introuvable")
        # Vérifier que la session appartient bien à l'utilisateur (sauf admin)
        if session.user_id != current_user.user_id and current_user.role != "admin":
            raise HTTPException(403, "Session appartenant à un autre utilisateur")
    else:
        session = creer_session(user_id=current_user.user_id, role=current_user.role)
        if req.ecran_contexte:
            session.ecran_contexte = req.ecran_contexte

    try:
        return await chat_assurance.chat(session=session, message=req.message)
    except Exception as e:
        logger.warning(f"[Chat/POST] IA échouée ({e}) → mode démo")
        reponse_demo = _reponse_demo_cima(req.message)
        return {
            "reponse": reponse_demo,
            "session_id": session.session_id,
            "modele": "demo-cima",
            "message": {"role": "assistant", "content": reponse_demo},
        }


@router.get("/message-stream", dependencies=[])
async def envoyer_message_stream_get(
    session_id: Optional[str] = None,
    content: str = "",
    token: Optional[str] = None,
):
    """
    GET endpoint SSE pour EventSource (navigateurs).
    Le token JWT est passé en query param car EventSource ne supporte pas les headers.
    """
    # Authentification via query param
    if not token:
        raise HTTPException(401, "Token requis")
    try:
        current_user = _decoder_token(token)
    except Exception:
        raise HTTPException(401, "Token invalide")

    # Résolution / création de session
    if session_id:
        session = get_session(session_id)
        if not session:
            raise HTTPException(404, f"Session {session_id} introuvable")
        if session.user_id != current_user.user_id and current_user.role != "admin":
            raise HTTPException(403, "Session appartenant à un autre utilisateur")
    else:
        session = creer_session(user_id=current_user.user_id, role=current_user.role)

    return await _stream_response(session, content, current_user)


@router.post("/message-stream")
async def envoyer_message_stream(
    req: MessageRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Envoie un message au chat IA en streaming SSE (Server-Sent Events).
    Retourne les chunks de réponse au fur et à mesure de la génération.
    Format SSE : data: {"chunk": "...", "done": false}
    Événement final : data: {"chunk": "", "done": true, "session_id": "..."}
    """
    # Résolution / création de session (identique à /message)
    if req.session_id:
        session = get_session(req.session_id)
        if not session:
            raise HTTPException(404, f"Session {req.session_id} introuvable")
        if session.user_id != current_user.user_id and current_user.role != "admin":
            raise HTTPException(403, "Session appartenant à un autre utilisateur")
    else:
        session = creer_session(user_id=current_user.user_id, role=current_user.role)
        if req.ecran_contexte:
            session.ecran_contexte = req.ecran_contexte

    return await _stream_response(session, req.message, current_user)


def _claude_key_valide() -> bool:
    """Vérifie que la clé Claude est configurée et a le bon format."""
    k = settings.CLAUDE_API_KEY
    return bool(k) and k.startswith("sk-ant-") and len(k) > 40 and "votre-cle" not in k


def _openai_key_valide() -> bool:
    """Vérifie que la clé OpenAI est configurée et a le bon format."""
    k = settings.OPENAI_API_KEY
    return bool(k) and k.startswith("sk-") and len(k) > 40


async def _stream_response(session, message: str, current_user: TokenData) -> StreamingResponse:
    """
    Streaming SSE multi-moteur :
    1. Claude (Anthropic) — si clé valide
    2. OpenAI GPT-4o — si clé valide
    3. Mode démo CIMA — réponse locale si aucune clé disponible
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        from modules.chat.yukpo_ia_assurance import MessageChat

        systeme = chat_assurance._construire_systeme_prompt(session)
        prompt_complet = chat_assurance._construire_prompt_avec_contexte(session, message)
        domaine = chat_assurance._detecter_domaine_avance(message, [])
        texte_complet: list[str] = []
        modele_utilise = "demo"

        # ── 1. Essai Claude ──────────────────────────────────────────────────
        if _claude_key_valide():
            try:
                claude_client = anthropic.AsyncAnthropic(api_key=settings.CLAUDE_API_KEY)
                # Prompt caching : le system prompt (~2000 tokens) est mis en cache
                # côté Anthropic pendant 5 min → réduit TTFT de ~60% sur les appels suivants
                system_avec_cache = [
                    {
                        "type": "text",
                        "text": systeme,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
                async with claude_client.messages.stream(
                    model=settings.CLAUDE_MODEL_PRIMAIRE,
                    max_tokens=settings.IA_MAX_TOKENS,
                    system=system_avec_cache,
                    messages=[{"role": "user", "content": prompt_complet}],
                ) as stream:
                    async for chunk_text in stream.text_stream:
                        texte_complet.append(chunk_text)
                        yield f"data: {json.dumps({'chunk': chunk_text, 'done': False}, ensure_ascii=False)}\n\n"
                modele_utilise = settings.CLAUDE_MODEL_PRIMAIRE
                logger.info(f"[Chat/Stream] Claude OK — session {session.session_id}")
            except Exception as e_claude:
                logger.warning(f"[Chat/Stream] Claude échoué ({e_claude}) → fallback OpenAI")
                texte_complet.clear()

        # ── 2. Fallback OpenAI ───────────────────────────────────────────────
        if not texte_complet and _openai_key_valide():
            try:
                import openai as _openai
                oai = _openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
                messages_oai = []
                if systeme:
                    messages_oai.append({"role": "system", "content": systeme})
                messages_oai.append({"role": "user", "content": prompt_complet})
                async with await oai.chat.completions.create(
                    model=settings.GPT_MODEL_FALLBACK,
                    max_tokens=min(settings.IA_MAX_TOKENS, 4096),
                    messages=messages_oai,
                    stream=True,
                ) as stream:
                    async for chunk in stream:
                        delta = chunk.choices[0].delta.content if chunk.choices else None
                        if delta:
                            texte_complet.append(delta)
                            yield f"data: {json.dumps({'chunk': delta, 'done': False}, ensure_ascii=False)}\n\n"
                modele_utilise = settings.GPT_MODEL_FALLBACK
                logger.info(f"[Chat/Stream] OpenAI OK — session {session.session_id}")
            except Exception as e_oai:
                logger.warning(f"[Chat/Stream] OpenAI échoué ({e_oai}) → mode démo")
                texte_complet.clear()

        # ── 3. Mode démo CIMA ────────────────────────────────────────────────
        if not texte_complet:
            demo = _reponse_demo_cima(message)
            # Simuler un streaming lettre par lettre (chunks de mots)
            mots = demo.split(" ")
            for i, mot in enumerate(mots):
                chunk = (mot + " ") if i < len(mots) - 1 else mot
                texte_complet.append(chunk)
                yield f"data: {json.dumps({'chunk': chunk, 'done': False}, ensure_ascii=False)}\n\n"
                if len(chunk) > 20:
                    await asyncio.sleep(0.02)
            modele_utilise = "demo-cima"

        # ── Finalisation ─────────────────────────────────────────────────────
        reponse_finale = "".join(texte_complet)
        msg_user = MessageChat(role="user", contenu=message)
        msg_assistant = MessageChat(
            role="assistant",
            contenu=reponse_finale,
            metadata={
                "modele": modele_utilise,
                "domaine": domaine.value if domaine else "copilote",
                "streaming": True,
            },
        )
        session.messages.extend([msg_user, msg_assistant])
        session.nb_messages += 2
        session.mise_a_jour = datetime.utcnow()

        if not session.titre and session.nb_messages == 2:
            asyncio.ensure_future(_set_session_titre(session, message))

        asyncio.ensure_future(
            chat_assurance._persister_messages(
                session, msg_user, msg_assistant, None,
                domaine.value if domaine else "copilote",
            )
        )

        payload_fin = json.dumps(
            {
                "chunk": "",
                "done": True,
                "full_content": reponse_finale,
                "session_id": session.session_id,
                "titre_session": session.titre,
                "nb_messages": session.nb_messages,
                "domaine_detecte": domaine.value if domaine else "copilote",
                "modele": modele_utilise,
            },
            ensure_ascii=False,
        )
        yield f"data: {payload_fin}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _reponse_demo_cima(question: str) -> str:
    """Réponses démo CIMA quand aucune clé IA n'est disponible."""
    q = question.lower()
    if any(k in q for k in ["délai", "délais", "reglement", "règlement"]):
        return (
            "📋 **Délais réglementaires CIMA — synthèse**\n\n"
            "### Délais côté assureur\n"
            "- **10 jours** calendaires pour accuser réception de tout sinistre *(Art. 12-bis CIMA)*\n"
            "- **3 mois** pour instruire le dossier et formuler l'offre d'indemnisation *(Art. 12-bis CIMA)*\n"
            "- **45 jours** calendaires pour payer après accord sur l'indemnité *(Art. 12-ter CIMA)*\n"
            "- **30 jours** pour répondre à toute réclamation écrite *(Art. 13 CIMA)*\n\n"
            "### Délais côté assuré\n"
            "- **5 jours ouvrés** pour déclarer un sinistre *(Art. 12 CIMA)*\n"
            "  *(exception : 24h pour incendie, 2 jours ouvrés pour vol)*\n\n"
            "### Cas spécifiques RC Auto\n"
            "- **30 jours** pour régler après expertise contradictoire *(Art. 231 CIMA)*\n"
            "- **3 mois** pour offre d'indemnisation corporelle *(Art. 210 CIMA)*\n"
            "- **15 jours** pour organiser la contre-expertise *(Art. 232 CIMA)*\n\n"
            "### Pénalités de retard\n"
            "- Dépassement du délai de paiement : **taux légal + 50% par mois** *(Art. 12-ter CIMA)*\n\n"
            "_💡 Pour une analyse personnalisée de vos dossiers, configurez votre clé API Claude dans le fichier .env_"
        )
    if any(k in q for k in ["solvabilité", "solvabilite", "marge", "ratio"]):
        return (
            "📊 **Marge de solvabilité CIMA**\n\n"
            "### Non-Vie — Art. 337-1 CIMA\n"
            "Exigence = **maximum** de :\n"
            "- **23%** des primes nettes acquises de l'exercice\n"
            "- **26%** de la charge sinistres moyenne des 3 derniers exercices\n"
            "- Minimum absolu : **300 millions FCFA**\n\n"
            "### Vie — Art. 338-1 CIMA\n"
            "- **4%** des provisions mathématiques brutes de réassurance\n"
            "- **+ 0,3%** du capital sous risque net (contrats temporaires décès)\n"
            "- Minimum absolu : **500 millions FCFA**\n\n"
            "### Couverture provisions — Art. 335 CIMA\n"
            "- Actifs représentatifs ≥ **100%** des provisions techniques\n\n"
            "Votre ratio affiché de **142%** est conforme aux exigences CIMA.\n\n"
            "_💡 Pour une analyse détaillée de vos ratios, configurez votre clé API Claude dans le fichier .env_"
        )
    if any(k in q for k in ["indemnité", "indemnite", "fracture", "ippe", "ipp", "corporel"]):
        return (
            "🏥 **Calcul indemnité corporelle (Art. 258 CIMA)**\n\n"
            "Pour une fracture du tibia :\n"
            "• **IPP estimée** : 8–12% selon consolidation\n"
            "• **Préjudice fonctionnel temporaire** : 150 000 XAF/mois\n"
            "• **Pretium doloris** 3/7 : 450 000 XAF\n"
            "• **Soins médicaux** : sur justificatifs réels\n\n"
            "**Estimation totale** : 1 200 000 à 1 800 000 XAF\n\n"
            "_💡 Pour un calcul précis avec l'âge et le salaire, configurez votre clé API dans .env_"
        )
    if any(k in q for k in ["c5", "c12", "état", "etat", "cima", "réglementation", "reglementation"]):
        return (
            "⚖️ **États réglementaires CIMA**\n\n"
            "Le Code CIMA prévoit **20 états réglementaires** (C1-C20) :\n"
            "• **C1-C5** : Provisions techniques et PSAP\n"
            "• **C6-C10** : Primes, sinistres, commissions par branche\n"
            "• **C11-C15** : Placements et actifs représentatifs\n"
            "• **C16-C20** : Solvabilité, réassurance (C12), charges\n\n"
            "Transmission obligatoire à la **CRCA** avant le 30 juin de chaque année.\n\n"
            "_💡 Pour générer vos états automatiquement, configurez votre clé API dans .env_"
        )
    if any(k in q for k in ["rapport", "générer", "generer", "document", "excel", "pdf", "powerpoint"]):
        return (
            "📄 **Génération de documents IA**\n\n"
            "YukpoAssurance peut générer automatiquement :\n"
            "• **Rapports PDF** : conformité CIMA, sinistres, provisions\n"
            "• **Excel** : états C1-C20, tableaux de bord, balance OHADA\n"
            "• **PowerPoint** : présentations CA, analyses fraude\n\n"
            "👉 Utilisez l'onglet **Rapports & Documents** pour accéder aux templates.\n\n"
            "_💡 Pour la génération IA avancée, configurez votre clé Claude API dans .env_"
        )
    return (
        f"🤖 **Yukpo IA — Mode démo CIMA**\n\n"
        f"Votre question : *\"{question[:80]}{'...' if len(question) > 80 else ''}\"*\n\n"
        f"Je suis Yukpo IA, votre copilote assurance spécialisé Code CIMA (509 articles, Livres I-VI, 15 États membres).\n\n"
        f"**Je peux vous aider sur :**\n"
        f"• Réglementation CIMA et états prudentiels\n"
        f"• Calcul d'indemnités et provisions techniques\n"
        f"• Rédaction de courriers et rapports\n"
        f"• Analyse de sinistres et détection de fraude\n\n"
        f"_⚙️ Mode démo actif — Configurez `CLAUDE_API_KEY` dans `.env` pour la réponse complète._"
    )


async def _set_session_titre(session, premier_message: str) -> None:
    """Tâche de fond : génère le titre de session après le 1er tour streaming."""
    # Ne tenter la génération de titre que si une clé IA valide est disponible
    if not _claude_key_valide() and not _openai_key_valide():
        # Générer un titre simple à partir du message sans appel IA
        mots = premier_message.strip().split()[:6]
        session.titre = " ".join(mots).capitalize()[:60]
        return
    try:
        session.titre = await chat_assurance._generer_titre(premier_message)
    except Exception:
        pass


@router.post("/message-avec-fichiers")
async def message_avec_fichiers(
    req: MessageAvecAttachmentRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Envoie un message avec pièces jointes (multimodal).
    Supports : images, audio (transcription Whisper), PDF, Excel, Word.
    """
    if req.session_id:
        session = get_session(req.session_id)
        if not session:
            raise HTTPException(404, "Session introuvable")
        if session.user_id != current_user.user_id and current_user.role != "admin":
            raise HTTPException(403, "Session appartenant à un autre utilisateur")
    else:
        session = creer_session(user_id=current_user.user_id, role=current_user.role)

    attachments = [
        Attachment(
            type=TypeAttachment(a.type),
            data_b64=a.data_b64,
            filename=a.filename,
            mime_type=a.mime_type,
        )
        for a in req.attachments
    ]

    return await chat_assurance.chat(
        session=session,
        message=req.message,
        attachments=attachments,
    )


@router.post("/upload-et-chat")
async def upload_et_chat(
    message: str,
    fichier: UploadFile = File(...),
    session_id: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Upload d'un fichier + question en une seule requête"""
    if session_id:
        session = get_session(session_id)
        if not session:
            raise HTTPException(404, "Session introuvable")
        if session.user_id != current_user.user_id and current_user.role != "admin":
            raise HTTPException(403, "Session appartenant à un autre utilisateur")
    else:
        session = creer_session(user_id=current_user.user_id, role=current_user.role)

    # Vérification taille fichier
    from config.settings import settings
    contenu = await fichier.read()
    taille_mb = len(contenu) / (1024 * 1024)
    limite_mb = settings.MAX_PDF_SIZE_MB if (fichier.content_type or "").startswith("application/pdf") else settings.MAX_IMAGE_SIZE_MB
    if taille_mb > limite_mb:
        raise HTTPException(413, f"Fichier trop volumineux : {taille_mb:.1f}MB (max {limite_mb}MB)")
    data_b64 = base64.standard_b64encode(contenu).decode()
    mime = fichier.content_type or "application/octet-stream"

    # Détection du type
    if mime.startswith("image/"):
        att_type = TypeAttachment.IMAGE
    elif mime.startswith("audio/"):
        att_type = TypeAttachment.AUDIO
    elif mime == "application/pdf":
        att_type = TypeAttachment.PDF
    elif "spreadsheet" in mime or "excel" in mime:
        att_type = TypeAttachment.EXCEL
    elif "wordprocessing" in mime or "word" in mime:
        att_type = TypeAttachment.WORD
    else:
        att_type = TypeAttachment.PDF

    attachment = Attachment(
        type=att_type,
        data_b64=data_b64,
        filename=fichier.filename or "fichier",
        mime_type=mime,
    )

    return await chat_assurance.chat(
        session=session,
        message=message,
        attachments=[attachment],
    )


class RenommerSessionRequest(BaseModel):
    titre: str


@router.patch("/sessions/{session_id}")
async def renommer_session(
    session_id: str,
    req: RenommerSessionRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Renomme une session de chat"""
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} introuvable")
    if session.user_id != current_user.user_id and current_user.role != "admin":
        raise HTTPException(403, "Session appartenant à un autre utilisateur")
    session.titre = req.titre.strip()[:100]
    return {"session_id": session_id, "titre": session.titre}


@router.get("/sessions/{session_id}/historique")
async def historique_session(session_id: str):
    """Retourne l'historique d'une session de chat"""
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session introuvable")
    return {
        "session_id": session_id,
        "titre": session.titre,
        "nb_messages": session.nb_messages,
        "resume": session.resume,
        "messages": [
            {
                "role": m.role,
                "contenu": m.contenu,
                "timestamp": m.timestamp.isoformat(),
                "generated_files": m.generated_files,
            }
            for m in session.messages
        ],
    }


@router.post("/sessions/{session_id}/exporter")
async def exporter_session(session_id: str, format: str = "docx"):
    """Exporte la session de chat en document Word ou PDF"""
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session introuvable")
    if not session.messages:
        raise HTTPException(400, "Session vide — rien à exporter")
    return await chat_assurance.exporter_session(session, format)


@router.get("/stream/{session_id}")
async def stream_chat_sse(
    session_id: str,
    question: str,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Stream de réponse chat en SSE (Server-Sent Events).
    Permet une expérience temps réel — la réponse s'affiche mot par mot.
    """
    from sse_starlette.sse import EventSourceResponse
    import json as _json

    async def event_generator():
        try:
            from modules.chat.yukpo_ia_assurance import gestionnaire_chat
            from core.ia_client import ia_client, ModeIA
            from core.security import security_service

            # Valider le prompt
            valide, raison = security_service.valider_prompt(question, current_user.user_id)
            if not valide:
                yield {"event": "error", "data": _json.dumps({"detail": raison})}
                return

            # Stream via Claude
            prompt_complet = f"Question: {question}"
            try:
                client = ia_client._client_anthropic
                if not client:
                    raise ValueError("Client Anthropic non initialisé")
                with client.messages.stream(
                    model=getattr(ia_client, "_modele_actuel", "claude-sonnet-4-6"),
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt_complet}],
                ) as stream:
                    for text in stream.text_stream:
                        yield {"event": "token", "data": _json.dumps({"token": text})}
                yield {"event": "done", "data": _json.dumps({"session_id": session_id})}
            except Exception as e:
                yield {"event": "error", "data": _json.dumps({"detail": str(e)})}
        except Exception as e:
            yield {"event": "error", "data": _json.dumps({"detail": str(e)})}

    return EventSourceResponse(event_generator())
