"""
Agent Conversationnel Intelligent — v2 optimisée pour la vitesse.

Optimisations :
  1. Fast-path : détection d'intent en < 1 ms avant tout appel LLM
     → si l'intent est clair, on lance directement l'agent sans passer par le Copilote
  2. Appel LLM direct (GPT-4o / Claude) sans pipeline orchestrateur pour le chat pur
  3. max_tokens limité à 600 pour le chat conversationnel
  4. Suppression du sleep artificiel de 400 ms
  5. Logs de timing pour diagnostiquer les lenteurs

Endpoint :
  POST /api/v1/agent/converser  — SSE
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.auth import get_current_user, TokenData

logger = logging.getLogger("yukpo_assurance.api.agent_conv")

router = APIRouter(prefix="/api/v1/agent", tags=["agents"])


# ─── Schémas ─────────────────────────────────────────────────────────────────

class MessageConv(BaseModel):
    role: str        # "user" | "agent"
    content: str

class ConverserRequest(BaseModel):
    messages: List[MessageConv]


# ─── Fast-path : intent → agent (mots-clés, < 1 ms) ─────────────────────────

# Verbes d'action qui indiquent clairement une tâche à exécuter
_VERBES_ACTION = {
    "declarer", "déclarer", "instruire", "traiter", "ouvrir", "creer", "créer",
    "souscrire", "emettre", "émettre", "generer", "générer", "calculer",
    "etablir", "établir", "produire", "lancer", "exporter", "cloturer",
    "clôturer", "établir", "rédiger", "enregistrer", "passer", "soumettre",
}

# Phrases entières signalant clairement une action
_PHRASES_ACTION = [
    "je veux", "je voudrais", "je souhaite", "j'ai besoin",
    "aide-moi à", "aide moi à", "fais", "génère", "génere",
    "lance", "ouvre", "créer", "créé", "nouveau", "nouvelle",
    "déclarer", "declarer",
]

# Mots-clés domaines → type d'agent
_MOTS_AGENTS: dict[str, str] = {
    # sinistres généraux
    "sinistre":        "sinistres",
    "sinistres":       "sinistres",
    "indemnisation":   "sinistres",
    "expertise":       "sinistres",
    "dommage":         "sinistres",
    "dommages":        "sinistres",
    # sinistres auto
    "accident":        "sinistres_auto",
    "collision":       "sinistres_auto",
    "constat":         "sinistres_auto",
    "vehicule":        "sinistres_auto",
    "véhicule":        "sinistres_auto",
    "auto":            "sinistres_auto",
    # maladie
    "maladie":         "maladie",
    "hospitalisation": "maladie",
    "soin":            "maladie",
    "soins":           "maladie",
    "medical":         "maladie",
    "médical":         "maladie",
    "santé":           "maladie",
    "sante":           "maladie",
    "ordonnance":      "maladie",
    "bpc":             "maladie",
    # souscription
    "police":          "souscription",
    "contrat":         "souscription",
    "souscription":    "souscription",
    "souscrire":       "souscription",
    "tarif":           "souscription",
    "prime":           "souscription",
    "avenant":         "souscription",
    # vie
    "vie":             "vie",
    "épargne":         "vie",
    "epargne":         "vie",
    "décès":           "vie",
    "deces":           "vie",
    "rente":           "vie",
    "prevoyance":      "vie",
    "prévoyance":      "vie",
    # conformité / états CIMA
    "conformite":      "conformite",
    "conformité":      "conformite",
    "ratio":           "conformite",
    "prudentiel":      "conformite",
    "provision":       "provisions",
    "provisions":      "provisions",
    "psap":            "provisions",
    "état":            "etats_cima",
    "etats":           "etats_cima",
    "liasse":          "etats_cima",
    "c1":              "etats_cima",
    "c20":             "etats_cima",
    # comptabilité
    "comptabilite":    "comptabilite",
    "comptabilité":    "comptabilite",
    "journal":         "comptabilite",
    "ecriture":        "comptabilite",
    "écriture":        "comptabilite",
    "balance":         "comptabilite",
    "bilan":           "comptabilite",
    # réassurance
    "reassurance":     "reassurance",
    "réassurance":     "reassurance",
    "traite":          "reassurance",
    "traité":          "reassurance",
    "cession":         "reassurance",
    "bordereau":       "reassurance",
    # RH
    "recrutement":     "rh",
    "conge":           "rh",
    "congé":           "rh",
    "paie":            "rh",
    "salaire":         "rh",
    # commercial
    "courtier":        "commercial",
    "production":      "commercial",
    "commission":      "commercial",
    "portefeuille":    "commercial",
    # juridique
    "contentieux":     "juridique",
    "litige":          "juridique",
    "juridique":       "juridique",
    "recours":         "juridique",
    # risques divers
    "rc pro":          "risques_divers",
    "rc-pro":          "risques_divers",
    "dommage ouvrage": "risques_divers",
    "mrh":             "risques_divers",
    "caution":         "risques_divers",
    # intelligence / rapports
    "rapport":         "intelligence",
    "analyse":         "intelligence",
    "kpi":             "intelligence",
    "tableau de bord": "intelligence",
}

# Questions pures (pas d'agent) — même si elles contiennent des mots domaine
_MOTS_QUESTION_PURE = {
    "qu'est-ce", "qu'est ce", "comment", "pourquoi", "quand", "quelle",
    "quel", "expliquer", "explique", "définir", "définition", "c'est quoi",
    "kesako", "renseigner", "informer", "différence entre", "signifie",
    "signification", "définissez", "formuler", "décrire",
}


def _detecter_agent_fastpath(message: str) -> Optional[str]:
    """
    Détection d'intent ultra-rapide (< 1 ms) sans LLM.
    Retourne le type d'agent si l'intent est une ACTION claire, None sinon.
    """
    texte = message.lower().strip()
    mots = set(texte.replace(",", " ").replace(".", " ").replace("?", " ").split())

    # Si c'est une question pure → pas d'agent
    if any(q in texte for q in _MOTS_QUESTION_PURE):
        return None

    # Chercher un verbe d'action
    a_verbe = bool(mots & _VERBES_ACTION)
    a_phrase_action = any(p in texte for p in _PHRASES_ACTION)

    if not (a_verbe or a_phrase_action):
        return None

    # Chercher le domaine
    for mot, agent in _MOTS_AGENTS.items():
        if mot in texte:
            return agent

    return None


def _detecter_agent_depuis_actions(actions: list) -> Optional[str]:
    """Extrait un type d'agent depuis les actions suggérées par le Copilote."""
    if not actions:
        return None
    texte_actions = " ".join(str(a).lower() for a in actions)
    for mot, agent in _MOTS_AGENTS.items():
        if mot in texte_actions:
            return agent
    return None


_MOTS_DECLARATION = {
    "nouveau sinistre", "déclarer un sinistre", "declarer un sinistre",
    "nouvelle déclaration", "sinistre vient", "je déclare", "déclaration",
    "declaration", "j'ai un sinistre", "signaler un sinistre",
}
_MOTS_SOUSCRIPTION_NOUVEAU = {
    "nouveau contrat", "nouvelle police", "souscrire un", "créer un contrat",
}


def _construire_instruction(messages: list, user_message: str) -> str:
    """Construit l'instruction complète avec MODE hint pour l'agent."""
    texte = user_message.lower()
    # Vérifier aussi le contexte récent (messages précédents)
    texte_contexte = " ".join(
        m.content.lower() for m in messages[-4:] if m.role == "user"
    )

    mode_hint = ""
    if any(k in texte or k in texte_contexte for k in _MOTS_DECLARATION):
        mode_hint = (
            "⚡ MODE DÉCLARATION ACTIVÉ — L'utilisateur déclare un NOUVEAU sinistre.\n"
            "→ NE PAS demander si c'est nouveau ou existant (c'est NOUVEAU).\n"
            "→ Ne pas demander la date/police/branche séparément.\n"
            "→ Commencer DIRECTEMENT par : demander_information_utilisateur avec type_reponse='images' "
            "pour la déclaration de l'assuré. Extraire les données ensuite avec analyser_documents_sinistre, "
            "puis creer_sinistre.\n\n"
        )
    elif any(k in texte or k in texte_contexte for k in _MOTS_SOUSCRIPTION_NOUVEAU):
        mode_hint = "⚡ MODE SOUSCRIPTION — NOUVEAU CONTRAT À CRÉER.\n\n"

    contexte_parts = []
    for m in messages[-6:]:
        role = "Utilisateur" if m.role == "user" else "Yukpo"
        if m.content != user_message:
            contexte_parts.append(f"{role}: {m.content[:200]}")
    if contexte_parts:
        contexte_str = "\n".join(contexte_parts)
        return f"{mode_hint}[Contexte]\n{contexte_str}\n\nInstruction : {user_message}"
    return f"{mode_hint}{user_message}"


# ─── Système prompt conversationnel léger ────────────────────────────────────

_SYSTEM_CHAT = (
    "Tu es Yukpo, l'assistant IA d'une compagnie d'assurance en zone CIMA. "
    "Tu réponds en français, de façon concise (3-5 phrases max). "
    "Tu maîtrises le Code CIMA, les sinistres, la souscription, la comptabilité PCSA, "
    "la réassurance et la conformité. "
    "Si l'utilisateur te demande d'effectuer une ACTION (déclarer, souscrire, générer, calculer), "
    "réponds brièvement que tu lances le traitement. "
    "Sinon, réponds directement à la question de façon claire et professionnelle."
)


async def _appeler_llm_chat(messages: list, dernier_msg: str) -> str:
    """
    Appel LLM léger pour le chat conversationnel pur.
    - Pas d'orchestrateur, pas de pipeline lourd
    - max_tokens = 600 (suffisant pour le chat)
    - Utilise directement ia_client
    """
    from core.ia_client import ModeIA, ia_client

    # Construire le contexte conversationnel (3 derniers échanges)
    hist_parts = []
    for m in messages[-6:]:
        role = "Utilisateur" if m.role == "user" else "Yukpo"
        if m.content != dernier_msg:
            hist_parts.append(f"{role}: {m.content[:300]}")

    prompt = "\n".join(hist_parts) + f"\nUtilisateur: {dernier_msg}" if hist_parts else dernier_msg

    try:
        reponse = await asyncio.wait_for(
            ia_client.appeler(
                prompt=prompt,
                mode=ModeIA.COPILOTE,
                systeme=_SYSTEM_CHAT,
                max_tokens_override=600,
                utiliser_cache=True,
                cache_ttl=300,
            ),
            timeout=20.0,
        )
        return reponse.contenu
    except asyncio.TimeoutError:
        return "Je prends un peu plus de temps que prévu. Pouvez-vous reformuler votre question ?"
    except Exception as e:
        logger.warning(f"[agent_conv] LLM chat échoué: {e}")
        return _reponse_fallback(dernier_msg)


# ─── Endpoint principal ───────────────────────────────────────────────────────

@router.post("/converser")
async def converser(
    body: ConverserRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Interface conversationnelle — optimisée vitesse.
    SSE — retourne soit :
      - {"type": "chat", "content": "..."}
      - {"type": "lancer_agent", "agent_type": "...", "instruction": "..."}
    """

    async def event_generator():
        t0 = time.monotonic()
        try:
            user_msgs = [m for m in body.messages if m.role == "user"]
            if not user_msgs:
                yield _evt({"type": "chat", "content": "Bonjour ! Comment puis-je vous aider ?"})
                yield _evt({"type": "fin"})
                return

            dernier_msg = user_msgs[-1].content

            # ── FAST-PATH : intent clair → lancer agent SANS appel LLM ──────
            agent_type = _detecter_agent_fastpath(dernier_msg)
            if agent_type:
                t_fast = (time.monotonic() - t0) * 1000
                logger.info(f"[agent_conv] Fast-path {agent_type} en {t_fast:.1f}ms")
                instruction = _construire_instruction(body.messages, dernier_msg)
                yield _evt({"type": "lancer_agent", "agent_type": agent_type, "instruction": instruction})
                yield _evt({"type": "fin"})
                return

            # ── SLOW-PATH : message conversationnel → appel LLM léger ────────
            t_llm_start = time.monotonic()
            reponse_texte = await _appeler_llm_chat(body.messages, dernier_msg)
            t_llm = (time.monotonic() - t_llm_start) * 1000
            logger.info(f"[agent_conv] LLM chat en {t_llm:.0f}ms")

            # Vérifier si le LLM a détecté un besoin d'agent dans le contexte
            # (ex: message ambigu mais le LLM comprend que c'est une action)
            agent_type_post = _detecter_agent_depuis_contexte(reponse_texte, dernier_msg)
            if agent_type_post:
                yield _evt({"type": "chat", "content": reponse_texte})
                instruction = _construire_instruction(body.messages, dernier_msg)
                yield _evt({"type": "lancer_agent", "agent_type": agent_type_post, "instruction": instruction})
            else:
                yield _evt({"type": "chat", "content": reponse_texte})

            t_total = (time.monotonic() - t0) * 1000
            logger.info(f"[agent_conv] Total {t_total:.0f}ms")

        except Exception as e:
            logger.error(f"[agent_conv] Erreur : {e}", exc_info=True)
            yield _evt({"type": "chat", "content": _reponse_fallback(
                body.messages[-1].content if body.messages else ""
            )})
        finally:
            yield _evt({"type": "fin"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _evt(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _detecter_agent_depuis_contexte(reponse_llm: str, message_user: str) -> Optional[str]:
    """
    Détecte si le LLM a répondu en mode 'je lance le traitement' indiquant un besoin d'agent.
    """
    texte_combined = (reponse_llm + " " + message_user).lower()
    mots_lancement = ["je lance", "je vais lancer", "je démarre", "je traite", "je crée", "je génère"]
    if not any(m in texte_combined for m in mots_lancement):
        return None
    for mot, agent in _MOTS_AGENTS.items():
        if mot in texte_combined:
            return agent
    return None


def _reponse_fallback(user_msg: str) -> str:
    """Réponse de secours sans LLM."""
    texte = user_msg.lower()
    if any(g in texte for g in ["bonjour", "salut", "bonsoir", "hello", "bonne nuit"]):
        return (
            "Bonjour ! Je suis Yukpo, votre assistant assurance CIMA. "
            "Je peux vous aider à déclarer un sinistre, souscrire un contrat, "
            "calculer des provisions, générer des états CIMA, ou répondre à vos questions réglementaires."
        )
    return (
        "Je suis là pour vous aider. Décrivez votre demande et "
        "je vous orienterai vers le bon agent ou vous répondrai directement."
    )
