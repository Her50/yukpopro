"""
YukpoAssurance — Chat IA Intelligent (inspiré de YukpoIA de yukpomnang2)
Chat conversationnel avancé pour les employés d'assurance :
- Sessions persistantes avec mémoire long-terme
- Multimodal : texte, images, audio (transcription Whisper), PDF, Excel
- Résumé automatique des conversations longues
- Mémoire utilisateur : rôle, habitudes, contexte récurrent
- Génération de documents directement depuis le chat
- Détection d'intention : CIMA, sinistres, compta, réunion, document...
"""
import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from core.ia_client import ModeIA, ReponseIA, ia_client
from core.orchestrateur import DomaineMétier
from core.audit import audit_service
from config.settings import settings

logger = logging.getLogger("yukpo_assurance.chat")

# ─── Constantes (inspirées de yukpo_ia_session_store.rs) ──────────────────────
RECENT_TURNS_FOR_PROMPT = 8        # Nb de tours récents injectés dans le contexte
SUMMARY_EVERY_N_MESSAGES = 12      # Résumé auto tous les N messages
MEMORY_EVERY_N_MESSAGES = 20       # Mise à jour mémoire long terme tous les N messages
MAX_USER_MEMORY_ITEMS = 15         # Nb max d'éléments en mémoire utilisateur

# Cache crédits en mémoire : évite un appel DB bloquant avant chaque message
# True = crédits ok, False = épuisés, None = pas encore vérifié
# Entrées expirées après 60s via call_later
_credits_cache: dict[int, bool] = {}


class TypeAttachment(str, Enum):
    IMAGE = "image"
    AUDIO = "audio"
    PDF = "pdf"
    EXCEL = "excel"
    WORD = "word"


@dataclass
class Attachment:
    """Pièce jointe multimodale dans un message chat"""
    type: TypeAttachment
    data_b64: str
    filename: str
    mime_type: str
    transcript: Optional[str] = None        # Rempli après transcription Whisper
    extracted_text: Optional[str] = None    # Rempli après extraction PDF/Excel


@dataclass
class MessageChat:
    role: str       # "user" | "assistant" | "system"
    contenu: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    attachments: list[Attachment] = field(default_factory=list)
    generated_files: list[dict] = field(default_factory=list)  # fichiers générés
    metadata: dict = field(default_factory=dict)


@dataclass
class SessionChat:
    """
    Session de chat persistante (inspirée de IaSessionRow de yukpo_ia_session_store.rs)
    Stocke l'historique, les résumés et la mémoire utilisateur.
    """
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: int = 0
    role_utilisateur: str = "agent"
    titre: Optional[str] = None
    ecran_contexte: Optional[str] = None    # ex: "sinistre_detail", "reporting_cima"
    messages: list[MessageChat] = field(default_factory=list)
    resume: Optional[str] = None            # Résumé IA des tours anciens
    memoire_utilisateur: dict = field(default_factory=dict)  # préférences, habitudes
    nb_messages: int = 0
    tokens_total: int = 0
    creee_le: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    mise_a_jour: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ── Stockage : cache RAM LRU + persistance PostgreSQL/SQLite ──────────────────
# LRU: OrderedDict permet d'évincer les sessions les plus anciennes facilement
from collections import OrderedDict
_sessions: OrderedDict[str, SessionChat] = OrderedDict()

# Capacité maximale du cache RAM (au-delà on évince les + anciennes)
_MAX_SESSIONS_RAM = 500


def _evict_sessions_si_necessaire() -> None:
    """Évince les sessions les plus anciennes si le cache est plein."""
    while len(_sessions) >= _MAX_SESSIONS_RAM:
        oldest_id, _ = next(iter(_sessions.items()))
        del _sessions[oldest_id]
        logger.debug(f"[Chat/LRU] Session évincée du cache RAM: {oldest_id[:8]}")


def creer_session(user_id: int, role: str = "agent", titre: Optional[str] = None) -> SessionChat:
    _evict_sessions_si_necessaire()
    s = SessionChat(user_id=user_id, role_utilisateur=role, titre=titre)
    _sessions[s.session_id] = s
    _sessions.move_to_end(s.session_id)  # La plus récente à la fin
    # Persister immédiatement en DB (fire-and-forget)
    asyncio.ensure_future(_sauvegarder_session_en_db(s))
    return s


async def _sauvegarder_session_en_db(session: SessionChat) -> None:
    """Sauvegarde / met à jour une session en DB."""
    try:
        from core.database import async_session_maker, SessionChatDB
        from sqlalchemy import select
        async with async_session_maker() as db:
            result = await db.execute(
                select(SessionChatDB).where(SessionChatDB.id == session.session_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = SessionChatDB(
                    id=session.session_id,
                    user_id=session.user_id,
                    role_utilisateur=session.role_utilisateur,
                )
                db.add(row)
            row.titre = session.titre
            row.resume = session.resume
            row.memoire_utilisateur = session.memoire_utilisateur
            row.nb_messages = session.nb_messages
            row.tokens_total = session.tokens_total
            row.mise_a_jour = session.mise_a_jour.replace(tzinfo=None)
            await db.commit()
    except Exception as e:
        logger.warning(f"[Chat/DB] Sauvegarde session échouée: {e}")


def get_session(session_id: str) -> Optional[SessionChat]:
    s = _sessions.get(session_id)
    if s:
        _sessions.move_to_end(session_id)  # LRU touch
    return s


async def get_session_async(session_id: str) -> Optional[SessionChat]:
    """Recherche en cache RAM, puis en DB si absente (après redémarrage)."""
    if session_id in _sessions:
        return _sessions[session_id]
    try:
        from core.database import async_session_maker, SessionChatDB, MessageChatDB
        from sqlalchemy import select
        async with async_session_maker() as db:
            result = await db.execute(
                select(SessionChatDB).where(SessionChatDB.id == session_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            # Reconstruire la session en mémoire
            s = SessionChat(
                session_id=row.id,
                user_id=row.user_id,
                role_utilisateur=row.role_utilisateur or "agent",
                titre=row.titre,
                resume=row.resume,
                memoire_utilisateur=row.memoire_utilisateur or {},
                nb_messages=row.nb_messages,
                tokens_total=row.tokens_total,
            )
            # Charger les N derniers messages
            msgs_result = await db.execute(
                select(MessageChatDB)
                .where(MessageChatDB.session_id == session_id)
                .order_by(MessageChatDB.timestamp.desc())
                .limit(RECENT_TURNS_FOR_PROMPT * 2)
            )
            rows_msgs = list(reversed(msgs_result.scalars().all()))
            for m in rows_msgs:
                s.messages.append(MessageChat(
                    role=m.role,
                    contenu=m.contenu,
                    timestamp=m.timestamp.replace(tzinfo=timezone.utc) if m.timestamp else datetime.now(timezone.utc),
                    generated_files=m.generated_files or [],
                    metadata={"modele": m.modele_utilise, "tokens": m.tokens, "domaine": m.domaine},
                ))
            _evict_sessions_si_necessaire()
            _sessions[session_id] = s
            return s
    except Exception as e:
        logger.warning(f"[Chat/DB] Chargement session {session_id} échoué: {e}")
        return None


async def charger_sessions_depuis_db(limite: int = 200) -> None:
    """Chargement au démarrage des sessions récentes depuis la DB vers le cache RAM."""
    try:
        from core.database import async_session_maker, SessionChatDB
        from sqlalchemy import select
        async with async_session_maker() as db:
            result = await db.execute(
                select(SessionChatDB)
                .order_by(SessionChatDB.mise_a_jour.desc())
                .limit(limite)
            )
            rows = result.scalars().all()
            for row in rows:
                if row.id not in _sessions:
                    s = SessionChat(
                        session_id=row.id,
                        user_id=row.user_id,
                        role_utilisateur=row.role_utilisateur or "agent",
                        titre=row.titre,
                        resume=row.resume,
                        memoire_utilisateur=row.memoire_utilisateur or {},
                        nb_messages=row.nb_messages,
                        tokens_total=row.tokens_total,
                    )
                    _sessions[row.id] = s
        logger.info(f"[Chat/DB] {len(rows)} sessions rechargées depuis la DB")
    except Exception as e:
        logger.warning(f"[Chat/DB] Chargement sessions au démarrage échoué: {e}")


def lister_sessions(user_id: int) -> list[dict]:
    return [
        {
            "session_id": s.session_id,
            "titre": s.titre or f"Conversation du {s.creee_le.strftime('%d/%m/%Y %H:%M')}",
            "nb_messages": s.nb_messages,
            "mise_a_jour": s.mise_a_jour.isoformat(),
        }
        for s in _sessions.values()
        if s.user_id == user_id
    ]


class ChatAssurance:
    """
    Chat IA intelligent YukpoAssurance.

    Inspiré des patterns de YukpoIA (yukpomnang2) :
    - Prétraitement des attachments (transcription audio Whisper, extraction PDF/Excel)
    - Sessions persistantes avec résumé automatique
    - Mémoire long-terme par utilisateur
    - Enrichissement de réponse avec fichiers générés (inline_base64 → URL)
    - Détection d'intention pour router vers le bon module métier

    Plus : spécialisation 100% assurance CIMA.
    """

    # ──────────────────────────────────────────────────────────────
    # OUTILS DU CHAT (tool-use)
    # ──────────────────────────────────────────────────────────────

    _OUTILS_CHAT = [
        {
            "name": "recherche_cima",
            "description": (
                "Recherche le texte OFFICIEL d'articles du Code CIMA "
                "(Code des Assurances des États membres de la CIMA — 412 articles indexés). "
                "UTILISE cet outil pour TOUTE question sur : un article précis (Art. 13, Art. 200…), "
                "un délai réglementaire, un plafond d'indemnisation, une obligation d'assurance, "
                "RC auto, sinistres, primes, garanties, provisions techniques, solvabilité, "
                "agréments, réassurance, intermédiaires, microassurance. "
                "L'outil comprend le langage naturel et les fautes de frappe — "
                "formule simplement ta question en français."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": (
                            "Question sur le Code CIMA. "
                            "Exemple : 'Art. 13 nouveau paiement primes' ou "
                            "'délai déclaration sinistre RC auto Art. 12'."
                        ),
                    },
                },
                "required": ["question"],
            },
        },
        {
            "name": "recherche_reglementaire",
            "description": (
                "Recherche dans le corpus réglementaire africain : OHADA, codes du travail, "
                "fiscalité (CGI, TVA), conventions collectives, marchés publics, droit commercial. "
                "UTILISE cet outil pour toute question juridique hors Code CIMA."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Question juridique, fiscale ou réglementaire",
                    },
                    "pays": {
                        "type": "string",
                        "description": "Code pays ISO-2 (CM, CI, SN, BF, GA…). Vide = multi-pays.",
                    },
                    "domaine": {
                        "type": "string",
                        "description": (
                            "Optionnel. fiscal | travail | commercial | comptabilite | "
                            "civil | penal | conventions_collectives | banque | marches_publics."
                        ),
                    },
                },
                "required": ["question"],
            },
        },
    ]

    async def _executer_outil_chat(self, nom: str, params: dict) -> str:
        """Exécute un outil du chat et retourne le résultat."""
        if nom == "recherche_cima":
            try:
                from modules.chat.cima_retriever import rechercher_articles
                question = params.get("question", "").strip()
                if not question:
                    return "Erreur : question vide."
                resultat = await asyncio.to_thread(rechercher_articles, question)
                if not resultat or not resultat.strip():
                    return (
                        "ARTICLE_NON_TROUVE: Cet article n'est pas dans la base CIMA locale. "
                        "Informez l'utilisateur et recommandez de consulter le texte officiel "
                        "auprès de la CRCA. N'inventez pas le texte d'un article."
                    )
                return resultat
            except Exception as e:
                logger.warning(f"[Chat/Outil] recherche_cima échoué : {e}")
                return f"CORPUS_INDISPONIBLE: Base CIMA temporairement inaccessible ({type(e).__name__})."

        if nom == "recherche_reglementaire":
            try:
                from modules.rag.rag_retriever import rechercher_corpus_reglementaire
                question = params.get("question", "").strip()
                if not question:
                    return "Erreur : question vide."
                contexte = rechercher_corpus_reglementaire(
                    question=question,
                    pays=params.get("pays"),
                    domaine=params.get("domaine"),
                    top_k=6,
                    seuil_score=0.35,
                )
                if not contexte or not contexte.strip():
                    return (
                        "DOCUMENT_NON_INDEXE: Aucun passage trouvé dans le corpus réglementaire. "
                        "Orientez vers les sources officielles. N'inventez pas de contenu juridique."
                    )
                return contexte
            except Exception as e:
                logger.warning(f"[Chat/Outil] recherche_reglementaire échoué : {e}")
                return f"CORPUS_INDISPONIBLE: Corpus réglementaire temporairement inaccessible ({type(e).__name__})."

        return f"[Outil '{nom}' non reconnu]"

    # ──────────────────────────────────────────────────────────────
    # POINT D'ENTRÉE PRINCIPAL
    # ──────────────────────────────────────────────────────────────

    async def chat(
        self,
        session: SessionChat,
        message: str,
        attachments: Optional[list[Attachment]] = None,
    ) -> dict:
        """
        Traite un message utilisateur et retourne la réponse IA.
        Gère : tool-use, multimodal, sessions, mémoire, génération de documents, crédits.
        """
        debut = time.monotonic()

        # 1. Prétraitement des pièces jointes (audio → transcript, PDF → texte)
        attachments = attachments or []
        if attachments:
            await self._pretraiter_attachments(attachments)

        # 2. Enrichissement du message avec le contenu extrait
        message_enrichi = self._enrichir_message(message, attachments)

        # 3. Détection automatique d'un dossier référencé (SIN-2025-001, police, etc.)
        from modules.dossiers.contexte import dossier_contexte_service
        contexte_dossier = await dossier_contexte_service.extraire_contexte(message_enrichi)

        # 4. Construction du prompt avec mémoire + historique récent + résumé + dossier
        systeme = self._construire_systeme_prompt(session)
        if contexte_dossier:
            systeme += dossier_contexte_service.formater_pour_prompt(contexte_dossier)
            logger.info(
                f"[Chat] Dossier auto-chargé: {contexte_dossier.type_dossier} "
                f"{contexte_dossier.reference}"
            )
        prompt_complet = self._construire_prompt_avec_contexte(session, message_enrichi)

        # 5. Images pour le multimodal
        images_b64 = [a.data_b64 for a in attachments if a.type == TypeAttachment.IMAGE]

        # 6. Détection d'intention et domaine
        domaine = self._detecter_domaine_avance(message, attachments)
        mode_ia = self._mode_selon_domaine(domaine)

        # 7. Pré-vérification des crédits — cache 60s pour éviter un appel DB bloquant
        if session.user_id and session.user_id > 0:
            _cache_ok = _credits_cache.get(session.user_id)
            if _cache_ok is False:
                # Crédits marqués épuisés en cache → bloquer sans appel DB
                return {
                    "session_id": session.session_id,
                    "reponse": "⚠️ Crédits Yukpo épuisés ce mois. Passez au plan supérieur pour continuer.",
                    "domaine_detecte": "credits_epuises",
                    "modele": "—",
                    "tokens_session": session.tokens_total,
                    "nb_messages": session.nb_messages,
                    "generated_files": [],
                    "titre_session": session.titre,
                    "duree_ms": 0,
                }
            elif _cache_ok is None:
                # Pas encore en cache : vérifier en DB, puis mettre en cache
                try:
                    from modules.pro.service_credits import solde_utilisateur
                    from core.database import async_session_maker
                    async with async_session_maker() as _db:
                        _solde = await solde_utilisateur(session.user_id, _db)
                    _epuise = _solde.get("credits_restants", 1) <= 0 and _solde.get("plan") != "business"
                    _credits_cache[session.user_id] = not _epuise
                    asyncio.get_event_loop().call_later(60, _credits_cache.pop, session.user_id, None)
                    if _epuise:
                        return {
                            "session_id": session.session_id,
                            "reponse": (
                                f"⚠️ Crédits Yukpo épuisés "
                                f"({int(_solde['credits_utilises'])}/{int(_solde['credits_alloues'])} ce mois). "
                                "Passez au plan supérieur pour continuer à utiliser YukpoAssurance IA."
                            ),
                            "domaine_detecte": "credits_epuises",
                            "modele": "—",
                            "tokens_session": session.tokens_total,
                            "nb_messages": session.nb_messages,
                            "generated_files": [],
                            "titre_session": session.titre,
                            "duree_ms": 0,
                        }
                except Exception as _e:
                    logger.warning(f"[Chat/Credits] Pré-vérification échouée (non bloquant) : {_e}")
                    _credits_cache[session.user_id] = True
                    asyncio.get_event_loop().call_later(60, _credits_cache.pop, session.user_id, None)

        # 8. Appel IA avec boucle tool-use (le LLM décide lui-même quand chercher)
        if images_b64:
            # Multimodal → appel direct sans tools (GPT-4o Vision)
            reponse: ReponseIA = await ia_client.appeler(
                prompt=prompt_complet,
                mode=mode_ia,
                systeme=systeme,
                images_b64=images_b64,
            )
        else:
            reponse: ReponseIA = await ia_client.appeler_avec_outils(
                prompt=prompt_complet,
                outils=self._OUTILS_CHAT,
                executeur_outil=self._executer_outil_chat,
                mode=mode_ia,
                systeme=systeme,
                module="chat",
                user_id=session.user_id or None,
            )

        # 9. Débit des crédits réels consommés (tokens accumulés sur tous les tours)
        if session.user_id and session.user_id > 0:
            asyncio.create_task(self._debiter_credits(
                user_id=session.user_id,
                modele=reponse.modele_utilise,
                tokens_input=reponse.tokens_input,
                tokens_output=reponse.tokens_output,
                session_id=session.session_id,
            ))

        # 10. Détection de génération de documents dans la réponse
        generated_files = await self._traiter_generation_documents(
            reponse.contenu, session
        )

        # 11. Mise à jour de la session (in-memory)
        dossier_ref = contexte_dossier.reference if contexte_dossier else None
        msg_user = MessageChat(
            role="user", contenu=message, attachments=attachments,
            metadata={"dossier_reference": dossier_ref} if dossier_ref else {},
        )
        msg_assistant = MessageChat(
            role="assistant",
            contenu=reponse.contenu,
            generated_files=generated_files,
            metadata={
                "modele": reponse.modele_utilise,
                "tokens": reponse.tokens_output,
                "domaine": domaine.value if domaine else "copilote",
                "dossier_reference": dossier_ref,
            },
        )
        session.messages.extend([msg_user, msg_assistant])
        session.nb_messages += 2
        session.tokens_total += reponse.tokens_input + reponse.tokens_output
        session.mise_a_jour = datetime.now(timezone.utc)

        # Titre automatique si c'est la 1ère question — fire-and-forget pour ne pas bloquer
        if not session.titre and session.nb_messages == 2:
            asyncio.create_task(self._generer_titre_et_sauvegarder(session, message))

        # 10. Persistance DB + Audit + Redis (fire-and-forget, ne bloque pas la réponse)
        asyncio.create_task(self._persister_messages(
            session, msg_user, msg_assistant, dossier_ref,
            domaine.value if domaine else "copilote",
        ))
        # Synchronisation Redis pour persistance distribuée (multi-instance)
        asyncio.create_task(self._sauvegarder_session_redis(session.session_id, {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "role_utilisateur": session.role_utilisateur,
            "titre": session.titre,
            "resume": session.resume,
            "nb_messages": session.nb_messages,
            "tokens_total": session.tokens_total,
            "mise_a_jour": session.mise_a_jour.isoformat(),
        }))
        asyncio.create_task(audit_service.log(
            action="chat_message",
            module="chat",
            user_id=session.user_id,
            resource_type="session",
            resource_id=session.session_id,
            details={
                "domaine": domaine.value if domaine else "copilote",
                "modele": reponse.modele_utilise,
                "tokens": reponse.tokens_input + reponse.tokens_output,
                "dossier": dossier_ref,
                "nb_fichiers_generes": len(generated_files),
            },
        ))

        # 11. Résumé auto si seuil atteint
        if session.nb_messages % SUMMARY_EVERY_N_MESSAGES == 0:
            asyncio.create_task(self._resumer_session(session))

        # 12. Mise à jour mémoire utilisateur
        if session.nb_messages % MEMORY_EVERY_N_MESSAGES == 0:
            asyncio.create_task(self._mettre_a_jour_memoire(session))

        duree_ms = (time.monotonic() - debut) * 1000
        logger.info(
            f"[Chat] session={session.session_id[:8]} "
            f"domaine={domaine.value if domaine else '?'} "
            f"duree={duree_ms:.0f}ms modele={reponse.modele_utilise}"
        )

        return {
            "session_id": session.session_id,
            "reponse": reponse.contenu,
            "domaine_detecte": domaine.value if domaine else "copilote",
            "modele": reponse.modele_utilise,
            "tokens_session": session.tokens_total,
            "nb_messages": session.nb_messages,
            "generated_files": generated_files,
            "titre_session": session.titre,
            "duree_ms": round(duree_ms),
        }

    # ──────────────────────────────────────────────────────────────
    # CRÉDITS
    # ──────────────────────────────────────────────────────────────

    async def _debiter_credits(
        self,
        user_id: int,
        modele: str,
        tokens_input: int,
        tokens_output: int,
        session_id: str,
    ) -> None:
        """Débite les crédits réels après un appel IA (fire-and-forget)."""
        try:
            from modules.pro.service_credits import verifier_et_debiter
            ok, _, msg = await verifier_et_debiter(
                user_id=user_id,
                modele=modele,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                module="chat",
                session_id=session_id,
            )
            if not ok:
                logger.warning(f"[Chat/Credits] Crédits insuffisants user={user_id} : {msg}")
        except Exception as e:
            logger.warning(f"[Chat/Credits] Débit échoué user={user_id} : {e}")

    # ──────────────────────────────────────────────────────────────
    # PERSISTANCE REDIS DES SESSIONS
    # ──────────────────────────────────────────────────────────────

    async def _sauvegarder_session_redis(self, session_id: str, session_data: dict) -> None:
        """Sauvegarde une session chat dans Redis pour persistance distribuée."""
        try:
            import redis.asyncio as aioredis
            import json as _json
            from config.settings import settings as _s
            r = aioredis.from_url(_s.REDIS_URL, socket_connect_timeout=1)
            # TTL 24h pour les sessions chat
            await r.setex(
                f"chat:session:{session_id}",
                86400,
                _json.dumps(session_data, ensure_ascii=False, default=str)
            )
            await r.aclose()
        except Exception:
            pass  # Redis non disponible — données en mémoire uniquement

    async def _charger_session_redis(self, session_id: str) -> dict | None:
        """Charge une session chat depuis Redis."""
        try:
            import redis.asyncio as aioredis
            import json as _json
            from config.settings import settings as _s
            r = aioredis.from_url(_s.REDIS_URL, socket_connect_timeout=1)
            data = await r.get(f"chat:session:{session_id}")
            await r.aclose()
            if data:
                return _json.loads(data)
        except Exception:
            pass
        return None

    async def _supprimer_session_redis(self, session_id: str) -> None:
        """Supprime une session depuis Redis."""
        try:
            import redis.asyncio as aioredis
            from config.settings import settings as _s
            r = aioredis.from_url(_s.REDIS_URL, socket_connect_timeout=1)
            await r.delete(f"chat:session:{session_id}")
            await r.aclose()
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────
    # PRÉTRAITEMENT MULTIMODAL
    # ──────────────────────────────────────────────────────────────

    async def _pretraiter_attachments(self, attachments: list[Attachment]) -> None:
        """
        Prétraite les pièces jointes avant l'appel IA.
        Audio → transcription Whisper | PDF/Excel → texte extrait.
        Inspiré de preprocess_yukpo_ia_attachments dans yukpomnang2.
        """
        tasks = []
        for att in attachments:
            if att.type == TypeAttachment.AUDIO and not att.transcript:
                tasks.append(self._transcrire_audio(att))
            elif att.type in (TypeAttachment.PDF, TypeAttachment.EXCEL, TypeAttachment.WORD):
                if not att.extracted_text:
                    tasks.append(self._extraire_texte_document(att))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _transcrire_audio(self, att: Attachment) -> None:
        """Transcription audio via OpenAI Whisper"""
        try:
            import base64
            import openai
            client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            audio_bytes = base64.b64decode(att.data_b64)

            # Whisper via l'API OpenAI
            import io
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = att.filename

            transcription = await client.audio.transcriptions.create(
                model="whisper-1",
                file=(att.filename, audio_bytes, att.mime_type),
                language="fr",
            )
            att.transcript = transcription.text
            logger.info(f"[Chat/Whisper] Transcription OK: {len(att.transcript)} chars")
        except Exception as e:
            logger.warning(f"[Chat/Whisper] Transcription échouée: {e}")
            att.transcript = "[Transcription audio non disponible]"

    async def _extraire_texte_document(self, att: Attachment) -> None:
        """Extraction du texte d'un PDF, Excel ou Word"""
        try:
            import base64
            contenu = base64.b64decode(att.data_b64)

            if att.type == TypeAttachment.PDF:
                import PyPDF2
                import io
                reader = PyPDF2.PdfReader(io.BytesIO(contenu))
                pages = [reader.pages[i].extract_text() for i in range(min(10, len(reader.pages)))]
                att.extracted_text = "\n\n".join(filter(None, pages))

            elif att.type == TypeAttachment.EXCEL:
                import pandas as pd
                import io
                df = pd.read_excel(io.BytesIO(contenu), sheet_name=None)
                textes = []
                for sheet_name, sheet_df in df.items():
                    textes.append(f"=== Feuille : {sheet_name} ===\n{sheet_df.to_string()}")
                att.extracted_text = "\n\n".join(textes)

        except Exception as e:
            logger.warning(f"[Chat/Extract] Extraction {att.type} échouée: {e}")

    # ──────────────────────────────────────────────────────────────
    # CONSTRUCTION DU CONTEXTE
    # ──────────────────────────────────────────────────────────────

    def _construire_systeme_prompt(self, session: SessionChat) -> str:
        memoire_str = ""
        if session.memoire_utilisateur:
            memoire_str = f"\n\nMÉMOIRE UTILISATEUR:\n{json.dumps(session.memoire_utilisateur, ensure_ascii=False, indent=2)}"

        return f"""Tu es YukpoAssurance, l'IA experte et bienveillante spécialisée pour les professionnels de l'assurance en zone CIMA.
15 États membres : Bénin, Burkina Faso, Cameroun, Centrafrique, Comores, Congo, Côte d'Ivoire, Gabon, Guinée-Bissau, Guinée Équatoriale, Mali, Niger, Sénégal, Tchad, Togo.
Régulateur : CRCA (Libreville, Gabon). Monnaie : FCFA (XAF/XOF).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ DONNÉES CIMA OFFICIELLES — À UTILISER OBLIGATOIREMENT
   (Ces valeurs sont extraites du Code CIMA consolidé 2024)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STRUCTURE DU CODE CIMA : 6 LIVRES uniquement (Livres I à VI) — il n'existe PAS de Livre VII.
- Livre I   : Contrat d'assurance (Art. 1–98)
- Livre II  : Assurances obligatoires / RC Auto (Art. 200–251)
- Livre III : Entreprises d'assurance (Art. 300–430)
- Livre IV  : Intermédiaires (Art. 500–545)
- Livre V   : Dispositions diverses / LBC-FT (Art. 600–640)
- Livre VI  : Réassurance (Art. 700–730)

RC AUTOMOBILE OBLIGATOIRE (Livre II) :
- Fondement légal : Art. 200 (obligation) + Art. 201 (plafonds minimaux)
- Capitaux minimaux garantis (Art. 201) :
  * Dommages CORPORELS par victime    : 50 000 000 FCFA
  * Dommages CORPORELS par accident   : 300 000 000 FCFA
  * Dommages MATÉRIELS par accident   : 50 000 000 FCFA
- Offre indemnisation corporelle      : 3 mois (Art. 210)
- Règlement après expertise           : 30 jours (Art. 231)
- Contre-expertise                    : 15 jours (Art. 232)
- Fonds de Garantie Automobile (FGA)  : Art. 207 (véhicules non assurés)
- Barèmes d'invalidité                : Art. 220 (Commission Médicale Consultative)
- RC décennale construction           : Art. 225 (obligatoire)

DÉLAIS RÉGLEMENTAIRES (Livre I) :
- Déclaration sinistre par l'assuré   : 5 jours ouvrés (Art. 12) — 24h incendie, 2j vol
- Accusé réception assureur           : 10 jours calendaires (Art. 12-bis)
- Instruction et offre d'indemnisation: 3 mois (Art. 12-bis)
- Paiement après accord               : 45 jours calendaires (Art. 12-ter)
- Pénalité retard                     : taux légal + 50%/mois (Art. 12-ter)
- Art. 13 (paiement primes)           : consulte l'outil recherche_cima pour le texte exact
- Résiliation préavis                 : 2 mois (Art. 9)
- Résiliation non-paiement            : 30 jours après mise en demeure (Art. 10)
- Aggravation de risque               : 8 jours pour déclarer (Art. 17)
- Règlement sinistre vie              : 30 jours après dossier complet (Art. 73)
- Prescription non-vie                : 2 ans (Art. 26)
- Prescription vie                    : 10 ans (Art. 27)
- Valeur de rachat vie                : délai min. 6 mois (Art. 52)
- Taux technique max vie              : 3,5%/an (Art. 54)

ENTREPRISES D'ASSURANCE (Livre III) :
- Capital minimum (Circulaire CIMA 2016-001, Art. 329-1) : 3 000 000 000 FCFA (Vie et Non-Vie)
- Marge solvabilité Non-Vie (Art. 337-1) : max(23% × primes nettes ; 26% × sinistres moy 3 ans ; 300 000 000 FCFA)
- Marge solvabilité Vie (Art. 338-1)     : 4% × PM brutes + 0,3% × capital sous risque net ; min 500 000 000 FCFA
- Couverture provisions (Art. 335)       : actifs représentatifs ≥ 100% provisions techniques
- Taux réassurance max (Art. 308)        : 50% des primes brutes par branche
- Investissements locaux (Art. 320)      : min 50% en valeurs émises ou garanties dans la zone CIMA
- Notification CRCA (Art. 303)           : 30 jours pour tout changement statutaire

PROVISIONS TECHNIQUES (Art. 334-1 à 334-7) :
- Art. 334-1 : PPNA — Provision pour Primes Non Acquises (prorata temporis)
- Art. 334-2 : PSAP — Provision pour Sinistres À Payer (dossier/dossier + IBNR)
- Art. 334-3 : PRC  — Provision pour Risques Croissants (maladie/accident prime fixe)
- Art. 334-4 : PM   — Provisions Mathématiques Vie (méthode prospective obligatoire)
- Art. 334-5 : PMR  — Provision Mathématique de Rentes
- Art. 334-7 : PE   — Provision d'Égalisation (catastrophes)

ÉTATS RÉGLEMENTAIRES C1-C20 (Art. 400) — Échéances CRCA :
- C1  : Résultat technique Non-Vie       | Annuel | 31 mars
- C2  : Résultat technique Vie           | Annuel | 31 mars (Art. 423 : 75% produits financiers aux assurés)
- C3  : Bilan                            | Annuel | 31 mars
- C4  : État des placements              | Annuel | 31 mars (Art. 335)
- C5  : Provisions techniques Non-Vie   | Annuel | 31 mars (PSAP Art.334-2, PPNA Art.334-1, PRC Art.334-3)
- C6  : Provisions mathématiques Vie     | Annuel | 31 mars (PM Art. 334-4)
- C7  : Marge de solvabilité             | Annuel | 31 mars (Art. 337-1 / 338-1)
- C8  : Cessions en réassurance          | Annuel | 31 mars
- C9  : Statistiques sinistres auto      | Annuel | 31 mars
- C10 : Statistiques sinistres Vie       | Annuel | 31 mars
- C11 : État de concordance              | Annuel | 31 mars
- C12 : Production par branche           | Annuel | 31 mars
- C13 : Intermédiaires                   | Annuel | 31 mars
- C14 : Rapport commissaire aux comptes  | Annuel | 30 avril
- C15 : Rapport Conseil d'Administration | Annuel | 30 avril
- C16 : Engagements hors bilan           | Annuel | 31 mars
- C17 : Stats trimestrielles production  | Trim.  | T+30 jours
- C18 : Stats trimestrielles sinistres   | Trim.  | T+30 jours
- C19 : Rapport d'audit interne          | Annuel | 31 mars
- C20 : Plan de réassurance              | Annuel | 31 janvier (Art. 312)

INTERMÉDIAIRES (Livre IV) :
- Courtier : 3 devis comparatifs minimum (Art. 502)
- Reversement primes max : 30 jours (Art. 520)
- Commissions indicatives : Auto/IRD 15-20% ; Vie 5-15% ; Transport 10-15% ; RC 12-18%

BRANCHES & TAXES :
- Auto (code 1) : taxe 15% | Vie (code 2) : exonéré | IRD/MRH (code 3) : 15%
- RC (code 4) : 15% | Transport (code 5) : 10% | Maladie/Accidents (code 6) : 10%
- Agricole (code 7) : exonéré | Crédit (code 8) : 12%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Profil de l'utilisateur : {session.role_utilisateur}
Session : {session.ecran_contexte or 'chat général'}

RÈGLES DE RÉPONSE :
1. Réponds toujours en **français professionnel** avec une touche chaleureuse et engageante
2. **OBLIGATOIRE — OUTIL `recherche_cima`** :
   - Pour TOUTE question mentionnant un article du Code CIMA, un délai réglementaire, un plafond, une obligation d'assurance → appelle l'outil `recherche_cima` AVANT de répondre.
   - Reproduis le texte retourné par l'outil TEL QUEL, sans modifier ni compléter avec tes connaissances générales.
   - Si l'outil retourne ARTICLE_NON_TROUVE → dis-le explicitement et recommande la CRCA. Ne jamais inventer.
   - Le Code CIMA comporte **6 Livres uniquement** (I à VI). Il n'existe pas de Livre VII.
3. Pour les questions hors Code CIMA (fiscalité, droit du travail, OHADA) → utilise l'outil `recherche_reglementaire`.
4. Utilise les données du tableau de référence ci-dessus pour les valeurs numériques courantes (RC Auto, solvabilité, provisions).
4. Pour les calculs, montre la formule et le résultat chiffré en FCFA
5. Utilise des **emojis pertinents** (📋 règles, 💡 conseils, ⚠️ alertes, 📊 chiffres, ✅ conformité, 🏥 médical, 🚗 auto, ⚖️ juridique, 📄 documents)
6. Structure avec titres markdown (###), listes (-) et **gras** pour les points clés
7. Empathie si sinistre grave ou situation difficile pour l'assuré
8. Maximum 400 mots sauf génération de documents
9. Si tu génères un document, inclus la balise [GÉNÉRER_DOCUMENT] avec la structure JSON
10. Termine TOUJOURS par une action concrète ou une question de suivi pertinente{memoire_str}"""

    def _construire_prompt_avec_contexte(self, session: SessionChat, message: str) -> str:
        """
        Construit le prompt utilisateur.
        Avec l'architecture tool-use, les articles CIMA ne sont plus pré-injectés ici :
        le LLM appelle lui-même recherche_cima() quand il en a besoin.
        """
        parties = []

        # ── 1. Résumé des tours anciens ───────────────────────────────────────
        if session.resume:
            parties.append(f"[RÉSUMÉ DES ÉCHANGES PRÉCÉDENTS]\n{session.resume}")

        # ── 2. Historique récent ──────────────────────────────────────────────
        messages_recents = session.messages[-(RECENT_TURNS_FOR_PROMPT * 2):]
        if messages_recents:
            hist = []
            for m in messages_recents:
                role = "ASSISTANT" if m.role == "assistant" else "UTILISATEUR"
                hist.append(f"[{role}]: {m.contenu[:500]}")
            parties.append("[HISTORIQUE RÉCENT]\n" + "\n".join(hist))

        # ── 3. Message actuel ─────────────────────────────────────────────────
        parties.append(f"[QUESTION DE L'UTILISATEUR]\n{message}")
        return "\n\n".join(parties)

    def _enrichir_message(self, message: str, attachments: list[Attachment]) -> str:
        extras = []
        for att in attachments:
            if att.transcript:
                extras.append(f"[TRANSCRIPTION AUDIO — {att.filename}]\n{att.transcript}")
            if att.extracted_text:
                texte = att.extracted_text[:3000]  # tronqué
                extras.append(f"[CONTENU DOCUMENT — {att.filename}]\n{texte}")
        if extras:
            return message + "\n\n" + "\n\n".join(extras)
        return message

    # ──────────────────────────────────────────────────────────────
    # GÉNÉRATION DE DOCUMENTS DEPUIS LE CHAT
    # ──────────────────────────────────────────────────────────────

    async def _traiter_generation_documents(
        self, reponse: str, session: SessionChat
    ) -> list[dict]:
        """
        Détecte si l'IA a inclus une instruction de génération de document
        et génère le fichier correspondant.
        Inspiré du document_generation_service.rs de yukpomnang2.
        """
        generated = []

        # Détection du marqueur [GÉNÉRER_DOCUMENT] avec JSON inline
        import re
        pattern = r'\[GÉNÉRER_DOCUMENT\]\s*```json\s*([\s\S]*?)```'
        matches = re.findall(pattern, reponse, re.IGNORECASE)

        for match in matches:
            try:
                outline = json.loads(match)
                fichier = await self._generer_document_depuis_outline(outline, session.user_id)
                if fichier:
                    generated.append(fichier)
                    logger.info(f"[Chat/DocGen] Document généré: {fichier.get('filename')}")
            except json.JSONDecodeError:
                logger.warning("[Chat/DocGen] JSON outline invalide")

        return generated

    async def _generer_document_depuis_outline(
        self, outline: dict, user_id: int
    ) -> Optional[dict]:
        """Génère un document via le script document_generator.py"""
        from modules.documents.generateur import DocumentGenerateur
        gen = DocumentGenerateur()
        return await gen.generer(outline, user_id)

    # ──────────────────────────────────────────────────────────────
    # MÉMOIRE & RÉSUMÉ
    # ──────────────────────────────────────────────────────────────

    # ──────────────────────────────────────────────────────────────
    # PERSISTANCE DB
    # ──────────────────────────────────────────────────────────────

    async def _persister_messages(
        self,
        session: SessionChat,
        msg_user: "MessageChat",
        msg_assistant: "MessageChat",
        dossier_ref: Optional[str],
        domaine: str,
    ) -> None:
        """Sauvegarde les messages en DB (fire-and-forget)."""
        try:
            from core.database import async_session_maker, SessionChatDB, MessageChatDB
            from sqlalchemy import select

            async with async_session_maker() as db:
                # Upsert session
                result = await db.execute(
                    select(SessionChatDB).where(SessionChatDB.id == session.session_id)
                )
                row = result.scalar_one_or_none()
                if row is None:
                    row = SessionChatDB(
                        id=session.session_id,
                        user_id=session.user_id,
                        role_utilisateur=session.role_utilisateur,
                    )
                    db.add(row)

                row.titre = session.titre
                row.resume = session.resume
                row.memoire_utilisateur = session.memoire_utilisateur
                row.nb_messages = session.nb_messages
                row.tokens_total = session.tokens_total
                row.mise_a_jour = session.mise_a_jour.replace(tzinfo=None)

                # Messages
                for msg, role in ((msg_user, "user"), (msg_assistant, "assistant")):
                    db.add(MessageChatDB(
                        session_id=session.session_id,
                        role=role,
                        contenu=msg.contenu,
                        attachments_meta=[
                            {"filename": a.filename, "type": a.type.value}
                            for a in (msg.attachments or [])
                        ],
                        generated_files=msg.generated_files,
                        modele_utilise=msg.metadata.get("modele") if role == "assistant" else None,
                        tokens=msg.metadata.get("tokens", 0) if role == "assistant" else 0,
                        domaine=domaine if role == "assistant" else None,
                        dossier_reference=dossier_ref,
                        timestamp=msg.timestamp.replace(tzinfo=None),
                    ))

                await db.commit()
        except Exception as e:
            logger.warning(f"[Chat/DB] Persistance échouée: {e}")

    async def _resumer_session(self, session: SessionChat) -> None:
        """Génère un résumé IA des échanges anciens pour libérer le contexte"""
        if len(session.messages) < 10:
            return
        anciens = session.messages[:-RECENT_TURNS_FOR_PROMPT * 2]
        hist_str = "\n".join(
            f"[{m.role.upper()}]: {m.contenu[:300]}"
            for m in anciens
        )
        prompt = f"""Résume en 3-5 points clés les échanges suivants entre un employé d'assurance et l'IA YukpoAssurance.
Retiens : les problèmes soulevés, les décisions prises, les numéros de polices/sinistres mentionnés.

{hist_str}

Résumé concis :"""
        try:
            reponse = await ia_client.appeler(prompt=prompt, mode=ModeIA.COPILOTE)
            session.resume = reponse.contenu
        except Exception as e:
            logger.warning(f"[Chat/Résumé] Erreur: {e}")

    async def _mettre_a_jour_memoire(self, session: SessionChat) -> None:
        """Extrait et met à jour la mémoire long terme de l'utilisateur"""
        messages_str = "\n".join(
            f"[{m.role.upper()}]: {m.contenu[:200]}"
            for m in session.messages[-20:]
        )
        prompt = f"""Analyse ces échanges et extrait 3-5 informations clés sur l'utilisateur
(son département, ses problèmes récurrents, ses préférences de réponse, son niveau d'expertise).

{messages_str}

Retourne UNIQUEMENT ce JSON :
{{
  "departement": "",
  "expertise_cima": "debutant|intermediaire|expert",
  "problematiques_recurrentes": [],
  "preferences_reponse": "",
  "contexte_notable": ""
}}"""
        try:
            reponse = await ia_client.appeler(
                prompt=prompt, mode=ModeIA.COPILOTE, json_attendu=True
            )
            data = reponse.as_json()
            session.memoire_utilisateur.update({k: v for k, v in data.items() if v})
            # Limiter la taille
            if len(session.memoire_utilisateur) > MAX_USER_MEMORY_ITEMS:
                keys = list(session.memoire_utilisateur.keys())
                for k in keys[:-MAX_USER_MEMORY_ITEMS]:
                    del session.memoire_utilisateur[k]
        except Exception as e:
            logger.warning(f"[Chat/Mémoire] Erreur: {e}")

    async def _generer_titre(self, premier_message: str) -> str:
        """Génère un titre court pour la session"""
        try:
            reponse = await ia_client.appeler(
                prompt=f"Génère un titre court (max 8 mots) pour cette conversation d'assurance : {premier_message[:200]}",
                mode=ModeIA.COPILOTE,
            )
            return reponse.contenu.strip().strip('"').strip("'")[:80]
        except Exception:
            return f"Session du {datetime.now().strftime('%d/%m %H:%M')}"

    async def _generer_titre_et_sauvegarder(self, session: "SessionChat", premier_message: str) -> None:
        """Génère le titre en arrière-plan et met à jour la session sans bloquer la réponse."""
        try:
            # Titre rapide local si message court — évite l'appel API
            mots = premier_message.strip().split()
            if len(mots) <= 6:
                session.titre = " ".join(mots).capitalize()[:60]
            else:
                session.titre = await self._generer_titre(premier_message)
            asyncio.ensure_future(_sauvegarder_session_en_db(session))
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────
    # DÉTECTION D'INTENTION
    # ──────────────────────────────────────────────────────────────

    def _detecter_domaine_avance(
        self, message: str, attachments: list[Attachment]
    ) -> DomaineMétier:
        msg = message.lower()

        # Audio → souvent réunion ou dicté de rapport
        if any(a.type == TypeAttachment.AUDIO for a in attachments):
            if any(m in msg for m in ["réunion", "pv", "compte-rendu", "séance"]):
                return DomaineMétier.COPILOTE
            return DomaineMétier.COPILOTE

        # Excel/PDF → souvent comptabilité ou CIMA
        if any(a.type in (TypeAttachment.EXCEL, TypeAttachment.PDF) for a in attachments):
            if any(m in msg for m in ["bilan", "état", "cima", "rapport", "provision"]):
                return DomaineMétier.CIMA
            return DomaineMétier.COMPTABILITE

        # Mots clés sinistres
        if any(m in msg for m in ["sinistre", "accident", "déclaration", "expertise", "règlement", "indemnité"]):
            return DomaineMétier.SINISTRES

        # Mots clés CIMA
        if any(m in msg for m in ["cima", "crca", "article", "réglementaire", "provision", "marge", "solvabilité", "ratio", "état c"]):
            return DomaineMétier.CIMA

        # Mots clés comptabilité
        if any(m in msg for m in ["comptab", "facture", "écriture", "rapprochement", "bilan", "ohada"]):
            return DomaineMétier.COMPTABILITE

        # Mots clés souscription
        if any(m in msg for m in ["souscription", "contrat", "police", "prime", "garantie", "devis"]):
            return DomaineMétier.SOUSCRIPTION

        # Mots clés courtiers
        if any(m in msg for m in ["courtier", "commission", "intermédiaire"]):
            return DomaineMétier.COURTIERS

        return DomaineMétier.COPILOTE

    def _mode_selon_domaine(self, domaine: DomaineMétier) -> ModeIA:
        mapping = {
            DomaineMétier.CIMA: ModeIA.PRECISION,
            DomaineMétier.FRAUDE: ModeIA.ANALYSE,
            DomaineMétier.SINISTRES: ModeIA.ANALYSE,
            DomaineMétier.COMPTABILITE: ModeIA.ANALYSE,
            DomaineMétier.OCR: ModeIA.PRECISION,
        }
        return mapping.get(domaine, ModeIA.COPILOTE)

    # ──────────────────────────────────────────────────────────────
    # EXPORT DE SESSION
    # ──────────────────────────────────────────────────────────────

    async def exporter_session(self, session: SessionChat, format: str = "docx") -> dict:
        """Exporte la session de chat en document Word/PDF"""
        from modules.documents.generateur import DocumentGenerateur

        sections = []
        for i, msg in enumerate(session.messages):
            if msg.role == "user":
                sections.append({
                    "heading": f"Question {(i // 2) + 1}",
                    "level": 2,
                    "paragraphs": [msg.contenu],
                })
            else:
                sections.append({
                    "heading": "Réponse YukpoAssurance",
                    "level": 3,
                    "paragraphs": [msg.contenu],
                })

        outline = {
            "document_type": format,
            "title": session.titre or "Export Chat YukpoAssurance",
            "subtitle": f"Session du {session.creee_le.strftime('%d/%m/%Y')} — {session.role_utilisateur}",
            "author": "YukpoAssurance IA",
            "theme": "blue",
            "sections": sections,
        }

        gen = DocumentGenerateur()
        return await gen.generer(outline, session.user_id)


# Instance singleton
chat_assurance = ChatAssurance()
