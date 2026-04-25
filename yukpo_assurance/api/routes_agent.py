"""
Routes Agent — API pour les agents IA autonomes.

Endpoints :
  POST   /agent/instruire          — Lancer une instruction agent (bloquant)
  GET    /agent/stream/{exec_id}   — Stream SSE des étapes en temps réel
  GET    /agent/validations         — Lister les validations en attente
  GET    /agent/validations/{id}   — Détail d'une validation
  POST   /agent/approuver/{id}     — Approuver → reprend le processus
  POST   /agent/rejeter/{id}       — Rejeter → reprend avec motif
  GET    /agent/historique          — Historique des exécutions
  GET    /agent/agents              — État de tous les agents
  GET    /agent/stats               — Statistiques file d'approbation
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Optional

import base64
import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Répertoire d'archivage numérique (partagé avec routes_archive.py)
_ARCHIVE_DIR = Path(__file__).parent.parent / "data" / "archive" / "agents"
_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

from core.auth import get_current_user, TokenData
from core.agent_orchestrateur import TypeAgent, agent_orchestrateur
from core.approval_queue import approval_queue

logger = logging.getLogger("yukpo_assurance.api.routes_agent")

router = APIRouter(prefix="/api/v1/agent", tags=["agents"])

# ─── Historique en mémoire (en prod → DB) ────────────────────────────────────
_historique: list[dict] = []


# ─── Schémas Pydantic ────────────────────────────────────────────────────────

class InstruireRequest(BaseModel):
    instruction: str
    agent_type:  Optional[str] = "auto"   # auto | sinistres | souscription | ...
    contexte:    Optional[dict] = {}


class ApprouverRequest(BaseModel):
    commentaire: Optional[str] = ""


class RejeterRequest(BaseModel):
    motif: str


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/instruire")
async def instruire_agent(
    body: InstruireRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Lance une instruction auprès de l'agent spécialisé.

    Retourne le résultat complet (synchrone).
    Pour le streaming temps réel, utiliser GET /stream/{exec_id}.
    """
    user_id = int(current_user.user_id)
    execution_id = str(uuid.uuid4())

    # ── Vérification solde AVANT appel agent ──────────────────────────────────
    try:
        from modules.pro.service_credits import verifier_solde_suffisant
        from core.database import async_session_maker
        async with async_session_maker() as _db_solde:
            _ok_s, _s, _p, _msg_s = await verifier_solde_suffisant(
                user_id=user_id, cout_estime_usd=0.20, db=_db_solde,
            )
        if not _ok_s:
            parts = _msg_s.split("|")
            raise HTTPException(status_code=402, detail={
                "code":    "CREDITS_EPUISES",
                "message": f"Crédits Yukpo épuisés ({parts[1] if len(parts)>1 else '?'}/{parts[2] if len(parts)>2 else '?'} ce mois).",
                "action":  "Rechargez vos crédits ou changez de plan pour continuer.",
                "url":     "/abonnement",
            })
    except HTTPException:
        raise
    except Exception as _e_pre:
        logger.warning(f"[Credits] Pré-check agent non bloquant : {_e_pre}")

    # Déterminer le type d'agent
    try:
        agent_type = TypeAgent(body.agent_type) if body.agent_type != "auto" else TypeAgent.AUTO
    except ValueError:
        agent_type = TypeAgent.AUTO

    t0 = time.time()
    try:
        resultat = await agent_orchestrateur.executer(
            instruction=body.instruction,
            user_id=user_id,
            agent_type=agent_type,
            contexte=body.contexte or {},
        )

        # ── Débit crédits selon coût IA réel ─────────────────────────────────
        if resultat.cout_ia_usd and resultat.cout_ia_usd > 0:
            try:
                from modules.pro.service_credits import verifier_et_debiter
                from core.database import async_session_maker
                # Estimation tokens depuis le coût USD (Sonnet ~$3/$15 per 1M)
                _tokens_out = int(resultat.cout_ia_usd / 0.000015)
                _tokens_in  = int(resultat.cout_ia_usd / 0.000003)
                async with async_session_maker() as _db_debit:
                    await verifier_et_debiter(
                        user_id=user_id,
                        modele="claude-sonnet-4-5",
                        tokens_input=_tokens_in,
                        tokens_output=_tokens_out,
                        module="agent",
                        db=_db_debit,
                    )
            except Exception as _e_debit:
                logger.warning(f"[Credits] Débit agent non bloquant : {_e_debit}")

        # Archiver dans l'historique
        entree = {
            "execution_id": resultat.execution_id,
            "instruction":  body.instruction[:200],
            "agent":        resultat.agent.value,
            "statut":       resultat.statut.value,
            "duree_ms":     resultat.duree_totale_ms,
            "ia_appelee":   resultat.ia_appelee,
            "cout_ia_usd":  resultat.cout_ia_usd,
            "nb_validations": len(resultat.actions_requises),
            "user_id":      user_id,
            "timestamp":    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        _historique.insert(0, entree)
        if len(_historique) > 500:
            _historique.pop()

        return {
            "execution_id":     resultat.execution_id,
            "agent":            resultat.agent.value,
            "statut":           resultat.statut.value,
            "resume":           resultat.resume,
            "etapes":           [_etape_to_dict(e) for e in resultat.etapes],
            "actions_requises": resultat.actions_requises,
            "erreur":           resultat.erreur,
            "duree_ms":         resultat.duree_totale_ms,
            "ia_appelee":       resultat.ia_appelee,
            "cout_ia_usd":      resultat.cout_ia_usd,
        }
    except Exception as e:
        logger.error(f"[routes_agent] Erreur instruire : {e}")
        logger.error(f"[routes_agent.py] {e}")
        raise HTTPException(status_code=500, detail="Erreur serveur interne")


@router.get("/stream")
async def stream_agent(
    instruction: str = Query(..., description="Instruction en langage naturel"),
    agent_type:  str = Query("auto"),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Stream SSE des étapes de l'agent en temps réel.
    Chaque événement SSE = une étape (action, ia, validation, résultat).

    Format SSE :
      data: {"type": "action", "libelle": "→ calculer_prime", "statut": "ok", ...}
    """
    user_id = int(current_user.user_id)

    try:
        agent_type_enum = TypeAgent(agent_type) if agent_type != "auto" else TypeAgent.AUTO
    except ValueError:
        agent_type_enum = TypeAgent.AUTO

    async def event_generator():
        """
        Génère les événements SSE en temps réel.
        Un heartbeat (commentaire SSE) est envoyé toutes les 5s pour
        maintenir la connexion vivante pendant les appels Claude longs.
        """
        # File de sortie : l'agent y dépose ses étapes, le générateur les lit
        queue: asyncio.Queue = asyncio.Queue()
        fin_event = asyncio.Event()

        async def remplir_queue():
            """Tâche parallèle : exécute l'agent et dépose les étapes dans la queue."""
            try:
                async for etape in agent_orchestrateur.stream_executer(
                    instruction=instruction,
                    user_id=user_id,
                    agent_type=agent_type_enum,
                    contexte={},
                ):
                    await queue.put(("etape", etape))
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"[stream_agent] Erreur exécution : {e}")
                err_etape = {"type": "erreur", "libelle": "Erreur agent", "detail": str(e),
                             "statut": "erreur", "duree_ms": 0, "donnees": {}, "id": "err", "timestamp": ""}
                await queue.put(("data_raw", json.dumps(err_etape, ensure_ascii=False)))
            finally:
                fin_event.set()
                await queue.put(("fin", None))

        task = asyncio.create_task(remplir_queue())

        try:
            while True:
                try:
                    # Attendre le prochain item avec timeout heartbeat (5s)
                    item_type, payload = await asyncio.wait_for(queue.get(), timeout=5.0)
                except asyncio.TimeoutError:
                    # Pas de nouvelle étape → envoyer un commentaire SSE (heartbeat)
                    yield ": heartbeat\n\n"
                    continue

                if item_type == "fin":
                    break
                elif item_type == "etape":
                    data = json.dumps(_etape_to_dict(payload), ensure_ascii=False)
                    yield f"data: {data}\n\n"
                elif item_type == "data_raw":
                    yield f"data: {payload}\n\n"

        except asyncio.CancelledError:
            task.cancel()
        finally:
            if not task.done():
                task.cancel()
            yield "data: {\"type\": \"fin\"}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/executions_interrompues")
async def executions_interrompues(
    current_user: TokenData = Depends(get_current_user),
):
    """
    Liste les exécutions interrompues (coupure réseau / courant) pour l'utilisateur.
    Le frontend propose de reprendre ces exécutions au reconnect.
    """
    from agents.base_agent import lister_checkpoints_utilisateur
    return {"executions": lister_checkpoints_utilisateur(int(current_user.user_id))}


@router.get("/stream/reprendre/{execution_id}")
async def reprendre_execution(
    execution_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Reprend une exécution interrompue depuis le dernier checkpoint sauvegardé.
    Même format SSE que /stream — le frontend n'a pas besoin de logique spéciale.
    """
    from agents.base_agent import charger_checkpoint
    checkpoint = charger_checkpoint(execution_id)
    if not checkpoint:
        raise HTTPException(status_code=404, detail="Aucun checkpoint trouvé pour cette exécution")
    if checkpoint.get("user_id") != int(current_user.user_id):
        raise HTTPException(status_code=403, detail="Non autorisé")

    try:
        agent_type_enum = TypeAgent(checkpoint["agent_type"])
    except ValueError:
        agent_type_enum = TypeAgent.AUTO

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()
        fin_event = asyncio.Event()

        async def remplir_queue():
            try:
                from core.agent_orchestrateur import agent_orchestrateur
                # Reprendre depuis les messages sauvegardés
                async for etape in agent_orchestrateur.stream_executer_depuis_messages(
                    messages=checkpoint["messages"],
                    user_id=checkpoint["user_id"],
                    agent_type=agent_type_enum,
                    contexte=checkpoint.get("contexte", {}),
                    instruction=checkpoint["instruction"],
                    execution_id=execution_id,
                ):
                    await queue.put(("etape", etape))
            except Exception as e:
                err_etape = {"type": "erreur", "libelle": "Erreur reprise", "detail": str(e),
                             "statut": "erreur", "duree_ms": 0, "donnees": {}, "id": "err", "timestamp": ""}
                await queue.put(("data_raw", json.dumps(err_etape, ensure_ascii=False)))
            finally:
                fin_event.set()
                await queue.put(("fin", None))

        task = asyncio.create_task(remplir_queue())
        try:
            while True:
                try:
                    item_type, payload = await asyncio.wait_for(queue.get(), timeout=5.0)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if item_type == "fin":
                    break
                elif item_type == "etape":
                    yield f"data: {json.dumps(_etape_to_dict(payload), ensure_ascii=False)}\n\n"
                elif item_type == "data_raw":
                    yield f"data: {payload}\n\n"
        except asyncio.CancelledError:
            task.cancel()
        finally:
            if not task.done():
                task.cancel()
            yield "data: {\"type\": \"fin\"}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/validations")
async def lister_validations(
    statut:    str = Query("en_attente", description="en_attente | approuve | rejete | tous"),
    type_item: Optional[str] = Query(None),
    limit:     int = Query(50),
    current_user: TokenData = Depends(get_current_user),
):
    """Liste les validations en attente (ou filtrées par statut)."""
    statut_filtre = None if statut == "tous" else statut
    items = approval_queue.lister(
        statut=statut_filtre,
        type_item=type_item,
        limit=limit,
    )
    return {
        "validations": items,
        "total": len(items),
        "stats": approval_queue.stats(),
    }


@router.get("/validations/{item_id}")
async def detail_validation(
    item_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Détail d'une validation spécifique."""
    item = approval_queue.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Validation {item_id} introuvable")
    return item


@router.post("/approuver/{item_id}")
async def approuver_validation(
    item_id: str,
    body: ApprouverRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Approuve une validation en attente.

    → REPREND automatiquement l'exécution de l'agent depuis l'état sauvegardé.
    → L'agent continue le processus avec la décision d'approbation injectée.
    """
    user_id  = int(current_user.user_id)
    user_nom = current_user.user_nom

    try:
        resultat_reprise = await approval_queue.approuver(
            item_id=item_id,
            validateur_id=user_id,
            validateur_nom=user_nom,
            commentaire=body.commentaire or "",
        )

        response = {
            "statut": "approuve",
            "item_id": item_id,
            "validateur": user_nom,
            "reprise": None,
        }

        if resultat_reprise:
            # Archiver la reprise
            entree = {
                "execution_id": resultat_reprise.execution_id,
                "instruction":  f"[REPRISE après approbation {item_id}]",
                "agent":        resultat_reprise.agent.value,
                "statut":       resultat_reprise.statut.value,
                "duree_ms":     resultat_reprise.duree_totale_ms,
                "ia_appelee":   resultat_reprise.ia_appelee,
                "user_id":      user_id,
                "timestamp":    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            _historique.insert(0, entree)

            response["reprise"] = {
                "execution_id": resultat_reprise.execution_id,
                "statut":       resultat_reprise.statut.value,
                "resume":       resultat_reprise.resume,
                "etapes":       [_etape_to_dict(e) for e in resultat_reprise.etapes],
                "nouvelle_validation_requise": len(resultat_reprise.actions_requises) > 0,
            }
            logger.info(f"[routes_agent] Reprise après approbation {item_id} → {resultat_reprise.statut}")

        return response

    except ValueError as e:
        logger.warning(f"[routes_agent.py] {e}")
        raise HTTPException(status_code=400, detail="Données invalides")
    except Exception as e:
        logger.error(f"[routes_agent] Erreur approbation {item_id} : {e}")
        logger.error(f"[routes_agent.py] {e}")
        raise HTTPException(status_code=500, detail="Erreur serveur interne")


@router.post("/rejeter/{item_id}")
async def rejeter_validation(
    item_id: str,
    body: RejeterRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Rejette une validation en attente.

    → REPREND l'exécution de l'agent avec la décision de rejet.
    → L'agent adapte la suite (notification assuré, alternatives, etc.)
    """
    user_id  = int(current_user.user_id)
    user_nom = current_user.user_nom

    try:
        resultat_reprise = await approval_queue.rejeter(
            item_id=item_id,
            validateur_id=user_id,
            validateur_nom=user_nom,
            motif=body.motif,
        )

        response = {
            "statut": "rejete",
            "item_id": item_id,
            "validateur": user_nom,
            "motif": body.motif,
            "reprise": None,
        }

        if resultat_reprise:
            response["reprise"] = {
                "execution_id": resultat_reprise.execution_id,
                "statut":       resultat_reprise.statut.value,
                "resume":       resultat_reprise.resume,
                "etapes":       [_etape_to_dict(e) for e in resultat_reprise.etapes],
            }

        return response

    except ValueError as e:
        logger.warning(f"[routes_agent.py] {e}")
        raise HTTPException(status_code=400, detail="Données invalides")
    except Exception as e:
        logger.error(f"[routes_agent] Erreur rejet {item_id} : {e}")
        logger.error(f"[routes_agent.py] {e}")
        raise HTTPException(status_code=500, detail="Erreur serveur interne")


class RepondreRequest(BaseModel):
    reponse: str


async def _traiter_reponse_question(
    item_id: str,
    reponse: str,
    user_id: int,
    user_nom: str,
    medias: list[UploadFile] | None = None,
) -> dict:
    """
    Logique commune : valide l'item, traite les fichiers, reprend l'agent.
    Retourne le dict de réponse API.
    """
    item = approval_queue.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Question {item_id} introuvable")
    if item.get("statut") != "en_attente":
        raise HTTPException(status_code=400, detail="Cette question a déjà reçu une réponse")
    if item.get("type") != "question_utilisateur":
        raise HTTPException(status_code=400, detail="Cet item n'est pas une question utilisateur")

    # ── Traitement des médias uploadés ───────────────────────────────────────
    medias_urls:   list[str] = []
    medias_base64: list[str] = []

    if medias:
        # Stocker dans data/archive/agents/{item_id}/ (système d'archive numérique)
        item_archive_dir = _ARCHIVE_DIR / item_id
        item_archive_dir.mkdir(exist_ok=True)
        for upload in medias:
            if not upload or not upload.filename:
                continue
            contenu = await upload.read()
            if not contenu:
                continue
            # Générer un nom unique pour l'archive
            ext = Path(upload.filename).suffix or ".bin"
            nom_archive = f"{uuid.uuid4().hex}{ext}"
            chemin = item_archive_dir / nom_archive
            chemin.write_bytes(contenu)
            # URL relative pour l'accès via le module archive
            url_archive = f"/api/v1/archive/agents/{item_id}/{nom_archive}"
            medias_urls.append(url_archive)
            # Base64 pour Claude Vision (injection directe dans le contexte)
            b64 = base64.b64encode(contenu).decode("utf-8")
            ct = upload.content_type or "image/jpeg"
            medias_base64.append(f"data:{ct};base64,{b64}")
            logger.info(
                f"[routes_agent] Média archivé : {chemin} "
                f"({len(contenu)//1024} Ko) → {url_archive}"
            )

    try:
        resultat_reprise = await approval_queue.repondre_question(
            item_id=item_id,
            reponse=reponse,
            user_id=user_id,
            user_nom=user_nom,
            medias_urls=medias_urls or None,
            medias_base64=medias_base64 or None,
        )

        response: dict = {
            "statut":     "repondu",
            "item_id":    item_id,
            "reponse":    reponse,
            "nb_medias":  len(medias_urls),
            "reprise":    None,
        }

        if resultat_reprise:
            entree = {
                "execution_id": resultat_reprise.execution_id,
                "instruction":  f"[REPRISE après réponse à la question {item_id}]",
                "agent":        resultat_reprise.agent.value,
                "statut":       resultat_reprise.statut.value,
                "duree_ms":     resultat_reprise.duree_totale_ms,
                "ia_appelee":   resultat_reprise.ia_appelee,
                "user_id":      user_id,
                "timestamp":    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            _historique.insert(0, entree)

            response["reprise"] = {
                "execution_id":  resultat_reprise.execution_id,
                "statut":        resultat_reprise.statut.value,
                "resume":        resultat_reprise.resume,
                "etapes":        [_etape_to_dict(e) for e in resultat_reprise.etapes],
                "nouvelle_question": any(e.type == "question" for e in resultat_reprise.etapes),
            }

        return response

    except ValueError as e:
        logger.warning(f"[routes_agent.py] {e}")
        raise HTTPException(status_code=400, detail="Données invalides")
    except Exception as e:
        logger.error(f"[routes_agent] Erreur réponse question {item_id} : {e}")
        logger.error(f"[routes_agent.py] {e}")
        raise HTTPException(status_code=500, detail="Erreur serveur interne")


@router.post("/repondre/{item_id}")
async def repondre_question(
    item_id: str,
    body: RepondreRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Soumet la réponse JSON à une question posée par l'agent.
    Pour les réponses avec médias, utiliser POST /repondre/{item_id}/medias (multipart).
    """
    user_id  = int(current_user.user_id)
    user_nom = current_user.user_nom
    return await _traiter_reponse_question(item_id, body.reponse, user_id, user_nom)


@router.post("/repondre/{item_id}/medias")
async def repondre_question_avec_medias(
    item_id:     str,
    reponse:     str = Form(""),
    medias:      list[UploadFile] = File(default=[]),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Soumet la réponse + médias (images, PDF) à une question posée par l'agent.

    Multipart/form-data :
      - reponse   : texte de la réponse (peut être vide si les médias parlent d'eux-mêmes)
      - medias[]  : fichiers images (JPG, PNG) ou documents (PDF) — jusqu'à N fichiers

    Les médias sont sauvegardés sur disque et injectés en base64 dans Claude Vision
    pour que l'agent puisse lire les documents visuellement.
    """
    user_id  = int(current_user.user_id)
    user_nom = current_user.user_nom
    return await _traiter_reponse_question(item_id, reponse, user_id, user_nom, medias or [])


@router.post("/medias/upload")
async def uploader_medias(
    medias: list[UploadFile] = File(...),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Upload préalable de médias (avant de répondre).
    Retourne les URLs locales et les données base64 pour prévisualisation frontend.
    """
    user_id = int(current_user.user_id)
    resultats = []
    upload_dir = _ARCHIVE_DIR / f"tmp_{user_id}"
    upload_dir.mkdir(exist_ok=True)

    for upload in medias:
        if not upload or not upload.filename:
            continue
        contenu = await upload.read()
        if not contenu:
            continue
        nom = f"{uuid.uuid4().hex}_{upload.filename}"
        chemin = upload_dir / nom
        chemin.write_bytes(contenu)
        b64 = base64.b64encode(contenu).decode("utf-8")
        resultats.append({
            "nom":         upload.filename,
            "url":         str(chemin),
            "taille_ko":   len(contenu) // 1024,
            "type":        upload.content_type,
            "preview_b64": f"data:{upload.content_type};base64,{b64[:200]}...",  # aperçu tronqué
        })

    return {"uploads": resultats, "total": len(resultats)}


class MessageEnCoursRequest(BaseModel):
    message: str


@router.post("/en-cours/{execution_id}/message")
async def envoyer_message_en_cours(
    execution_id: str,
    body: MessageEnCoursRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Envoie un message à un agent pendant son exécution en cours.

    L'agent détecte automatiquement le type de message :
    - **Modification** (annule, modifie, change, plutôt...) → injectée dans la boucle dès le
      prochain tour, l'agent adapte le traitement en cours
    - **Question** → mise en file d'attente, traitée après la fin du traitement actuel

    Retourne le type détecté et l'ID du message pour suivi.
    """
    user_id  = int(current_user.user_id)
    user_nom = current_user.user_nom

    resultat = approval_queue.envoyer_message_en_cours(
        execution_id=execution_id,
        message=body.message,
        user_id=user_id,
        user_nom=user_nom,
    )
    return {
        **resultat,
        "message": body.message,
        "info": (
            "Message de modification injecté dans le traitement en cours — l'agent adaptera sa réponse"
            if resultat["type"] == "modification"
            else "Question enregistrée — l'agent la traitera après avoir terminé le traitement en cours"
        ),
    }


@router.get("/en-cours/{execution_id}/messages-en-attente")
async def messages_en_attente(
    execution_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Liste les messages en file d'attente pour une exécution."""
    messages = approval_queue._messages_interruption.get(execution_id, [])
    questions = approval_queue._questions_en_file.get(execution_id, [])
    return {
        "execution_id":    execution_id,
        "modifications":   [m for m in messages if m.get("type") == "modification"],
        "questions_file":  [q for q in questions if not q.get("traitee")],
        "total":           len(messages) + len(questions),
    }


@router.get("/historique")
async def historique_executions(
    limit: int = Query(50),
    agent: Optional[str] = Query(None),
    current_user: TokenData = Depends(get_current_user),
):
    """Historique des exécutions d'agents."""
    hist = _historique
    if agent:
        hist = [h for h in hist if h.get("agent") == agent]
    return {
        "historique": hist[:limit],
        "total": len(hist),
    }


@router.get("/agents")
async def liste_agents(
    current_user: TokenData = Depends(get_current_user),
):
    """État et disponibilité de tous les agents spécialisés."""
    return {
        "agents": agent_orchestrateur.agents_disponibles(),
        "executions_actives": sum(
            a.get("nb_actifs", 0)
            for a in agent_orchestrateur.agents_disponibles()
        ),
    }


@router.get("/stats")
async def stats_file(
    current_user: TokenData = Depends(get_current_user),
):
    """Statistiques de la file de validation."""
    return {
        "file_validation": approval_queue.stats(),
        "historique_total": len(_historique),
        "agents": agent_orchestrateur.agents_disponibles(),
    }


# ─── Utilitaires ─────────────────────────────────────────────────────────────

def _etape_to_dict(etape) -> dict:
    return {
        "id":        etape.id,
        "type":      etape.type,
        "libelle":   etape.libelle,
        "detail":    etape.detail,
        "statut":    etape.statut,
        "duree_ms":  etape.duree_ms,
        "donnees":   etape.donnees,
        "timestamp": etape.timestamp,
    }
