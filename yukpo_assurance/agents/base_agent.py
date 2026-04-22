"""
BaseAgent — Classe de base pour tous les agents spécialisés.

ARCHITECTURE PAUSE/REPRISE :
  Quand un agent atteint une action nécessitant validation humaine :
  1. Il SAUVEGARDE l'état complet (messages Claude + tool_use_id) dans approval_queue
  2. Il retourne un statut EN_ATTENTE_VALIDATION
  3. Quand le validateur approuve/rejette → approval_queue appelle executer_depuis_contexte()
  4. L'agent reprend EXACTEMENT où il s'était arrêté, avec la décision humaine injectée
  5. La boucle continue jusqu'à end_turn

Chaque agent hérite de cette classe et implémente :
  - _definir_outils() → liste des outils disponibles
  - _executer_outil(nom, params) → exécution réelle
  - _system_prompt() → instructions spécifiques à l'agent
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import AsyncGenerator, Optional

from core.agent_orchestrateur import EtapeAgent, ResultatAgent, StatutExecution, TypeAgent
from core.approval_queue import approval_queue

logger = logging.getLogger("yukpo_assurance.agents")

# Seuil financier : toute décision au-dessus nécessite validation humaine
SEUIL_VALIDATION_FCFA = 500_000

# ─── Répertoire des checkpoints (résilience coupures) ────────────────────────
_CHECKPOINT_DIR = Path(__file__).parent.parent / "data" / "checkpoints"
_CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


def _chemin_checkpoint(execution_id: str) -> Path:
    return _CHECKPOINT_DIR / f"{execution_id}.json"


def _sauvegarder_checkpoint(
    execution_id: str,
    agent_type: str,
    messages: list,
    instruction: str,
    user_id: int,
    contexte: dict,
    tour: int,
) -> None:
    """
    Sauvegarde l'état de l'agent après chaque cycle d'outils.
    En cas de coupure (serveur, réseau, courant), ce fichier permet
    de reprendre l'exécution depuis le dernier point stable.
    """
    try:
        data = {
            "execution_id":  execution_id,
            "agent_type":    agent_type,
            "messages":      messages,
            "instruction":   instruction,
            "user_id":       user_id,
            "contexte":      contexte,
            "tour":          tour,
            "saved_at":      time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "statut":        "en_cours",
        }
        path = _chemin_checkpoint(execution_id)
        path.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[checkpoint] Impossible de sauvegarder {execution_id}: {e}")


def _supprimer_checkpoint(execution_id: str) -> None:
    """Supprime le checkpoint après fin d'exécution (succès ou erreur définitive)."""
    try:
        path = _chemin_checkpoint(execution_id)
        if path.exists():
            path.unlink()
    except Exception:
        pass


def charger_checkpoint(execution_id: str) -> Optional[dict]:
    """
    Charge un checkpoint existant. Utilisé par l'endpoint /agent/reprendre/{id}.
    Retourne None si aucun checkpoint n'existe pour cet execution_id.
    """
    try:
        path = _chemin_checkpoint(execution_id)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def lister_checkpoints_utilisateur(user_id: int) -> list[dict]:
    """
    Liste tous les checkpoints d'un utilisateur (exécutions interrompues).
    Utilisé par le frontend pour proposer la reprise au reconnect.
    """
    result = []
    try:
        for path in _CHECKPOINT_DIR.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("user_id") == user_id and data.get("statut") == "en_cours":
                    result.append({
                        "execution_id": data["execution_id"],
                        "agent_type":   data["agent_type"],
                        "instruction":  data["instruction"][:100],
                        "tour":         data["tour"],
                        "saved_at":     data["saved_at"],
                    })
            except Exception:
                continue
    except Exception:
        pass
    return result


class BaseAgent(ABC):
    """Classe de base — boucle outil + pause/reprise validation humaine + streaming."""

    type_agent: TypeAgent = TypeAgent.AUTO

    def __init__(self):
        # Compteur par instance — pas de partage de classe entre types d'agents
        self._executions_actives: int = 0

    @property
    def executions_actives(self) -> int:
        return self._executions_actives

    # ── Méthodes à implémenter par chaque agent ───────────────────────────────

    @abstractmethod
    def _definir_outils(self) -> list[dict]:
        """Retourne la liste des outils Claude (format Anthropic tool_use)."""
        ...

    @abstractmethod
    async def _executer_outil(
        self, nom: str, params: dict, user_id: int, execution_id: str
    ) -> str:
        """Exécute un outil et retourne le résultat sous forme de string."""
        ...

    @abstractmethod
    def _system_prompt(self) -> str:
        """Retourne le system prompt spécifique à l'agent."""
        ...

    # ── Exécution principale ──────────────────────────────────────────────────

    async def executer(
        self,
        instruction: str,
        user_id: int,
        contexte: dict,
        execution_id: str,
    ) -> ResultatAgent:
        """Exécute l'instruction via la boucle outil autonome."""
        prompt = self._construire_prompt(instruction, contexte)
        messages = [{"role": "user", "content": prompt}]
        return await self._boucle_agent(
            messages=messages,
            user_id=user_id,
            contexte=contexte,
            execution_id=execution_id,
            instruction=instruction,
        )

    async def executer_depuis_contexte(
        self,
        messages: list,
        user_id: int,
        contexte: dict,
        execution_id: str,
        instruction: str,
    ) -> ResultatAgent:
        """
        Reprend l'exécution depuis un état de conversation sauvegardé.
        Appelé par approval_queue après validation humaine.
        """
        logger.info(f"[{self.type_agent}] Reprise depuis contexte — exec={execution_id}")
        return await self._boucle_agent(
            messages=messages,
            user_id=user_id,
            contexte=contexte,
            execution_id=execution_id,
            instruction=instruction,
        )

    async def _boucle_agent(
        self,
        messages: list,
        user_id: int,
        contexte: dict,
        execution_id: str,
        instruction: str,
    ) -> ResultatAgent:
        """
        Boucle outil centrale.

        FLOW PAUSE/REPRISE :
        - Si _necessite_validation() → True pour un outil :
          1. L'outil a déjà été exécuté (résultat pré-pause calculé)
          2. On sauvegarde les messages + tool_use_id dans approval_queue
          3. On injecte "[EN ATTENTE]" dans le résultat de l'outil
          4. Claude voit ce message et produit un texte "en attente de validation"
          5. On retourne EN_ATTENTE — la boucle ne continue PAS
          6. Quand le validateur agit → approval_queue.approuver() appelle executer_depuis_contexte()
          7. Cette méthode reprend la boucle avec la décision injectée
        """
        self._executions_actives += 1
        debut = time.time()
        etapes: list[EtapeAgent] = []
        actions_requises: list[dict] = []
        ia_appelee = False
        cout_ia = 0.0

        try:
            from core.ia_client import ModeIA, ia_client

            # Injecter l'outil de demande d'information dans tous les agents
            outils = self._definir_outils()
            if not any(o.get("name") == "demander_information_utilisateur" for o in outils):
                outils = outils + [self._OUTIL_DEMANDER_INFO]

            tour = 0
            MAX_TOURS = 15  # sécurité anti-boucle

            while tour < MAX_TOURS:
                tour += 1
                t0 = time.time()
                ia_appelee = True

                reponse = await asyncio.to_thread(
                    self._appeler_claude_sync,
                    messages, outils,
                )
                cout_ia += getattr(reponse, "_cout_usd", 0)

                # ─ L'agent a terminé naturellement ──────────────────────────
                if reponse.stop_reason == "end_turn":
                    texte_final = ""
                    for bloc in reponse.content:
                        if hasattr(bloc, "text"):
                            texte_final = bloc.text
                    etapes.append(EtapeAgent(
                        type="resultat",
                        libelle="Processus terminé",
                        detail=texte_final[:500],
                        statut="ok",
                        duree_ms=int((time.time() - t0) * 1000),
                    ))

                    # ── Traiter les questions en file d'attente ───────────────
                    # Si l'utilisateur a envoyé des questions pendant le traitement,
                    # les injecter maintenant que l'agent est libre
                    questions_en_file = approval_queue.recuperer_questions_en_file(execution_id)
                    if questions_en_file:
                        questions_texte = "\n".join(
                            f"  [{i+1}] {q['user_nom']} ({q['reçue_le'][:16]}): {q['question']}"
                            for i, q in enumerate(questions_en_file)
                        )
                        etapes.append(EtapeAgent(
                            type="action",
                            libelle=f"📬 {len(questions_en_file)} question(s) en file traitée(s)",
                            detail=questions_texte[:300],
                            statut="ok",
                        ))
                        # Injecter les questions dans la suite du traitement
                        texte_final += (
                            f"\n\n📬 **Questions reçues pendant le traitement :**\n"
                            f"{questions_texte}\n"
                            f"Ces questions ont été enregistrées et seront traitées dans la prochaine interaction."
                        )

                    return ResultatAgent(
                        execution_id=execution_id,
                        agent=self.type_agent,
                        instruction=instruction,
                        statut=StatutExecution.TERMINE,
                        etapes=etapes,
                        resume=texte_final,
                        actions_requises=actions_requises,
                        duree_totale_ms=int((time.time() - debut) * 1000),
                        ia_appelee=ia_appelee,
                        cout_ia_usd=cout_ia,
                    )

                # ── Vérifier les messages d'interruption entre chaque tour ──
                # Modifications → injectées immédiatement dans la conversation
                # Questions → traitées après la fin du traitement
                messages_interruption = approval_queue.consommer_messages_interruption(execution_id)
                for msg_inter in messages_interruption:
                    if msg_inter.get("type") == "modification":
                        # Injecter comme message utilisateur pour rediriger le traitement
                        injection = (
                            f"[MESSAGE UTILISATEUR en cours de traitement — "
                            f"{msg_inter['user_nom']}] : {msg_inter['message']}\n"
                            f"Tiens compte de cette instruction et adapte le traitement en cours."
                        )
                        messages.append({"role": "user", "content": injection})
                        etapes.append(EtapeAgent(
                            type="action",
                            libelle=f"⚡ Modification reçue : {msg_inter['message'][:80]}",
                            detail=f"Injectée par {msg_inter['user_nom']}",
                            statut="ok",
                        ))
                        logger.info(
                            f"[{self.type_agent}] Modification injectée exec={execution_id}: "
                            f"{msg_inter['message'][:100]}"
                        )
                    else:
                        # Question → mettre en file pour traitement post-exécution
                        approval_queue.mettre_en_file_question(
                            execution_id=execution_id,
                            question_utilisateur=msg_inter["message"],
                            user_id=msg_inter["user_id"],
                            user_nom=msg_inter["user_nom"],
                        )

                # ─ L'agent veut utiliser des outils ─────────────────────────
                if reponse.stop_reason == "tool_use":
                    messages.append({"role": "assistant", "content": reponse.content})
                    resultats_outils = []
                    pause_validation = False
                    item_validation_id = None

                    for bloc in reponse.content:
                        if not hasattr(bloc, "name"):
                            continue

                        nom_outil    = bloc.name
                        params_outil = getattr(bloc, "input", {})
                        tool_use_id  = bloc.id

                        etape = EtapeAgent(
                            type="action",
                            libelle=f"→ {nom_outil}",
                            detail=str(params_outil)[:200],
                            statut="en_cours",
                        )

                        t_outil = time.time()
                        resultat_str = ""

                        # ─── DEMANDE D'INFORMATION COMPLÉMENTAIRE ────────────
                        if nom_outil == "demander_information_utilisateur":
                            question          = params_outil.get("question", "")
                            contexte_q        = params_outil.get("contexte", "")
                            choix             = params_outil.get("choix_possibles", [])
                            type_rep          = params_outil.get("type_reponse", "texte_libre")
                            nombre_imgs_max   = params_outil.get("nombre_images_max",
                                                    5 if type_rep == "images" else 1)
                            formats_acceptes  = params_outil.get("formats_acceptes", ["jpg", "png", "pdf"])

                            item = await approval_queue.ajouter({
                                "type":                  "question_utilisateur",
                                "question":              question,
                                "contexte_question":     contexte_q,
                                "choix_possibles":       choix,
                                "type_reponse":          type_rep,
                                "nombre_images_max":     nombre_imgs_max,
                                "formats_acceptes":      formats_acceptes,
                                "_messages_contexte":    list(messages),
                                "_tool_use_id":          tool_use_id,
                                "_resultat_pre_pause":   "",
                                "_agent_type":           self.type_agent.value,
                                "_instruction_originale": instruction,
                                "_contexte_execution":   contexte,
                                "user_id":               user_id,
                                "execution_id":          execution_id,
                            })

                            etape.type    = "question"
                            etape.libelle = f"❓ {question}"
                            etape.detail  = contexte_q
                            etape.statut  = "en_cours"
                            etape.donnees = {
                                "question_id":     item.id,
                                "choix":           choix,
                                "type_reponse":    type_rep,
                                "nombre_imgs_max": nombre_imgs_max,
                                "formats":         formats_acceptes,
                            }
                            etape.duree_ms = 0
                            etapes.append(etape)

                            actions_requises.append({
                                "id":                item.id,
                                "outil":             nom_outil,
                                "question":          question,
                                "choix":             choix,
                                "type_reponse":      type_rep,
                                "nombre_images_max": nombre_imgs_max,
                                "formats_acceptes":  formats_acceptes,
                                "user_id":           user_id,
                            })

                            # Un seul dernier appel IA pour que Claude génère le message
                            # "j'attends votre réponse" visible dans l'interface
                            resultat_attente = (
                                f"[EN ATTENTE DE RÉPONSE UTILISATEUR — ID: {item.id}]\n"
                                f"Question posée : {question}\n"
                                f"L'agent reprendra automatiquement dès réception de la réponse."
                            )
                            resultats_outils.append({
                                "type":        "tool_result",
                                "tool_use_id": tool_use_id,
                                "content":     resultat_attente,
                            })

                            messages.append({"role": "user", "content": resultats_outils})
                            try:
                                reponse_q = await asyncio.to_thread(
                                    self._appeler_claude_sync, messages, outils,
                                )
                                texte_q = ""
                                for bloc in reponse_q.content:
                                    if hasattr(bloc, "text"):
                                        texte_q = bloc.text
                                etapes.append(EtapeAgent(
                                    type="question",
                                    libelle="En attente de votre réponse",
                                    detail=texte_q[:300] or question,
                                    statut="en_cours",
                                    donnees={"question_id": item.id, "choix": choix, "type_reponse": type_rep},
                                ))
                            except Exception:
                                pass

                            return ResultatAgent(
                                execution_id=execution_id,
                                agent=self.type_agent,
                                instruction=instruction,
                                statut=StatutExecution.EN_ATTENTE,
                                etapes=etapes,
                                resume=f"❓ {question}",
                                actions_requises=actions_requises,
                                duree_totale_ms=int((time.time() - debut) * 1000),
                                ia_appelee=ia_appelee,
                                cout_ia_usd=cout_ia,
                            )
                        # ─────────────────────────────────────────────────────

                        try:
                            # Exécuter l'outil (calcul déterministe ou appel IA)
                            resultat_str = await self._executer_outil(
                                nom_outil, params_outil, user_id, execution_id
                            )
                            etape.statut = "ok"
                            etape.detail = resultat_str[:300]

                        except Exception as e:
                            etape.statut = "erreur"
                            etape.detail = f"Erreur : {e}"
                            resultat_str = f"ERREUR : {e}"

                        etape.duree_ms = int((time.time() - t_outil) * 1000)
                        etapes.append(etape)

                        # ─── LOGIQUE PAUSE/REPRISE ───────────────────────────
                        if self._necessite_validation(nom_outil, params_outil, resultat_str):
                            # Sauvegarder l'état COMPLET de la conversation
                            # pour que l'agent puisse reprendre après décision
                            # On sauvegarde les messages AVANT d'ajouter ce tool_result
                            # (ce tool_result sera reconstruit lors de la reprise)
                            item = await approval_queue.ajouter({
                                "type": params_outil.get("type", nom_outil),
                                **params_outil,
                                "_messages_contexte":    list(messages),  # état conversation complet
                                "_tool_use_id":          tool_use_id,
                                "_resultat_pre_pause":   resultat_str,
                                "_agent_type":           self.type_agent.value,
                                "_instruction_originale": instruction,
                                "_contexte_execution":   contexte,
                                "user_id":               user_id,
                                "execution_id":          execution_id,
                            })

                            # Injecter un message informatif dans le résultat de l'outil
                            resultat_str = (
                                f"{resultat_str}\n\n"
                                f"[EN ATTENTE DE VALIDATION HUMAINE — ID: {item.id}]\n"
                                f"Ce processus reprendra automatiquement après décision du validateur."
                            )

                            action_requise = {
                                "id":           item.id,
                                "outil":        nom_outil,
                                "params":       params_outil,
                                "resultat":     resultat_str,
                                "user_id":      user_id,
                                "execution_id": execution_id,
                            }
                            actions_requises.append(action_requise)
                            pause_validation = True
                            item_validation_id = item.id

                        # Accumuler le résultat de l'outil
                        resultats_outils.append({
                            "type":        "tool_result",
                            "tool_use_id": tool_use_id,
                            "content":     resultat_str,
                        })

                    # Ajouter tous les résultats d'outils aux messages
                    messages.append({"role": "user", "content": resultats_outils})

                    # Checkpoint après chaque cycle d'outils
                    # → si le serveur tombe ici, on peut reprendre depuis cet état
                    _sauvegarder_checkpoint(
                        execution_id=execution_id,
                        agent_type=self.type_agent.value,
                        messages=messages,
                        instruction=instruction,
                        user_id=user_id,
                        contexte=contexte,
                        tour=tour,
                    )

                    # Si une pause de validation est nécessaire :
                    # on fait UN dernier appel IA pour que Claude génère un message
                    # "en attente de validation" à montrer à l'utilisateur, puis on arrête
                    if pause_validation:
                        try:
                            reponse_pause = await asyncio.to_thread(
                                self._appeler_claude_sync, messages, outils,
                            )
                            texte_pause = ""
                            for bloc in reponse_pause.content:
                                if hasattr(bloc, "text"):
                                    texte_pause = bloc.text
                            etapes.append(EtapeAgent(
                                type="validation",
                                libelle="En attente de validation humaine",
                                detail=texte_pause[:300] or "Validation requise pour continuer",
                                statut="en_cours",
                                donnees={"validation_id": item_validation_id},
                            ))
                        except Exception:
                            pass

                        return ResultatAgent(
                            execution_id=execution_id,
                            agent=self.type_agent,
                            instruction=instruction,
                            statut=StatutExecution.EN_ATTENTE,
                            etapes=etapes,
                            resume=f"En attente de validation — ID: {item_validation_id}",
                            actions_requises=actions_requises,
                            duree_totale_ms=int((time.time() - debut) * 1000),
                            ia_appelee=ia_appelee,
                            cout_ia_usd=cout_ia,
                        )

            # MAX_TOURS atteint
            return ResultatAgent(
                execution_id=execution_id,
                agent=self.type_agent,
                instruction=instruction,
                statut=StatutExecution.ERREUR,
                etapes=etapes,
                erreur=f"Nombre maximum de tours atteint ({MAX_TOURS})",
                duree_totale_ms=int((time.time() - debut) * 1000),
                ia_appelee=ia_appelee,
            )

        except Exception as e:
            logger.error(f"[{self.type_agent}] Erreur exécution : {e}", exc_info=True)
            # Ajouter une étape d'erreur visible dans la timeline frontend
            etapes.append(EtapeAgent(
                type="erreur",
                libelle=f"Erreur : {str(e)[:120]}",
                detail=str(e),
                statut="erreur",
            ))
            return ResultatAgent(
                execution_id=execution_id,
                agent=self.type_agent,
                instruction=instruction,
                statut=StatutExecution.ERREUR,
                etapes=etapes,
                resume=f"❌ Erreur : {str(e)[:300]}",
                erreur=str(e),
                duree_totale_ms=int((time.time() - debut) * 1000),
                ia_appelee=ia_appelee,
                cout_ia_usd=cout_ia,
            )
        finally:
            self._executions_actives = max(0, self._executions_actives - 1)
            # Supprimer le checkpoint si l'exécution est terminée (succès ou erreur non-récupérable)
            # Les checkpoints de validation humaine (EN_ATTENTE) sont conservés
            _supprimer_checkpoint(execution_id)

    def _appeler_claude_sync(self, messages: list, outils: list):
        """
        Appel synchrone : GPT-4o en priorité (cohérent avec ia_client.py), Claude en fallback.
        Exécuté dans un thread via asyncio.to_thread.
        """
        from config.settings import settings

        openai_key = settings.OPENAI_API_KEY or ""
        claude_key = settings.CLAUDE_API_KEY or ""

        # GPT-4o primaire — cohérent avec ia_client._choisir_modele()
        openai_ok = (
            bool(openai_key)
            and len(openai_key) >= 20
            and "VOTRE" not in openai_key.upper()
            and "YOUR" not in openai_key.upper()
        )
        if openai_ok:
            return self._appeler_gpt_sync(messages, outils)

        # Claude en fallback si OpenAI indisponible
        claude_ok = bool(claude_key) and not claude_key.startswith("sk-ant-votre") and len(claude_key) >= 40
        if claude_ok:
            logger.info(f"[{self.type_agent}] OPENAI_API_KEY absente/invalide → fallback Claude")
            return self._appeler_claude_sync_anthropic(messages, outils)

        raise RuntimeError(
            "❌ Aucune clé API IA valide.\n"
            "Configurez OPENAI_API_KEY (prioritaire) ou CLAUDE_API_KEY dans yukpo_assurance/.env"
        )

    def _appeler_claude_sync_anthropic(self, messages: list, outils: list):
        """Appel direct à l'API Anthropic."""
        import anthropic
        from config.settings import settings
        try:
            client = anthropic.Anthropic(api_key=settings.CLAUDE_API_KEY)
            return client.messages.create(
                model=settings.CLAUDE_MODEL_PRIMAIRE,
                max_tokens=settings.IA_MAX_TOKENS,
                system=self._system_prompt(),
                tools=outils,
                messages=messages,
            )
        except anthropic.AuthenticationError:
            raise RuntimeError(
                "❌ CLAUDE_API_KEY refusée (401). Vérifiez votre clé sur https://console.anthropic.com/"
            )
        except anthropic.RateLimitError:
            raise RuntimeError("❌ Limite de débit Claude atteinte. Réessayez dans quelques secondes.")

    def _appeler_gpt_sync(self, messages: list, outils: list):
        """
        Fallback : exécute la boucle outil via GPT-4o (OpenAI function-calling).
        Convertit les formats Anthropic ↔ OpenAI et retourne un objet compatible.
        """
        import json
        import openai
        from dataclasses import dataclass, field as dc_field
        from config.settings import settings

        # ── Conversion outils Anthropic → OpenAI ────────────────────────────
        def _fixer_schema(schema: dict) -> dict:
            """Ajoute items manquants sur les array params — requis par OpenAI."""
            if not isinstance(schema, dict):
                return schema
            if schema.get("type") == "array" and "items" not in schema:
                schema = {**schema, "items": {"type": "string"}}
            if "properties" in schema:
                schema = {**schema, "properties": {
                    k: _fixer_schema(v) for k, v in schema["properties"].items()
                }}
            return schema

        def _outil_to_openai(o: dict) -> dict:
            return {
                "type": "function",
                "function": {
                    "name": o["name"],
                    "description": o.get("description", ""),
                    "parameters": _fixer_schema(o.get("input_schema", {"type": "object", "properties": {}})),
                },
            }

        outils_gpt = [_outil_to_openai(o) for o in outils]

        # ── Conversion messages Anthropic → OpenAI ───────────────────────────
        def _msg_to_openai(m: dict) -> list[dict]:
            role = m["role"]
            content = m["content"]

            if isinstance(content, str):
                return [{"role": role, "content": content}]

            if not isinstance(content, list):
                return [{"role": role, "content": str(content)}]

            # Message assistant avec tool_use blocks
            if role == "assistant":
                text_parts = []
                tool_calls = []
                for bloc in content:
                    if isinstance(bloc, dict):
                        t = bloc.get("type", "")
                        if t == "text":
                            text_parts.append(bloc.get("text", ""))
                        elif t == "tool_use":
                            tool_calls.append({
                                "id": bloc["id"],
                                "type": "function",
                                "function": {
                                    "name": bloc["name"],
                                    "arguments": json.dumps(bloc.get("input", {}), ensure_ascii=False),
                                },
                            })
                    elif hasattr(bloc, "type"):
                        if bloc.type == "text":
                            text_parts.append(bloc.text)
                        elif bloc.type == "tool_use":
                            tool_calls.append({
                                "id": bloc.id,
                                "type": "function",
                                "function": {
                                    "name": bloc.name,
                                    "arguments": json.dumps(bloc.input or {}, ensure_ascii=False),
                                },
                            })
                msg: dict = {"role": "assistant", "content": " ".join(text_parts) or None}
                if tool_calls:
                    msg["tool_calls"] = tool_calls
                return [msg]

            # Message user avec tool_result ou images
            if role == "user":
                out = []
                oai_content: list[dict] = []
                for bloc in content:
                    if not isinstance(bloc, dict):
                        continue
                    t = bloc.get("type", "")
                    if t == "tool_result":
                        # Chaque tool_result → message séparé de rôle "tool"
                        out.append({
                            "role": "tool",
                            "tool_call_id": bloc["tool_use_id"],
                            "content": str(bloc.get("content", "")),
                        })
                    elif t == "text":
                        oai_content.append({"type": "text", "text": bloc.get("text", "")})
                    elif t == "image":
                        src = bloc.get("source", {})
                        if src.get("type") == "base64":
                            oai_content.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{src['media_type']};base64,{src['data']}",
                                    "detail": "high",
                                },
                            })
                if oai_content:
                    out.append({"role": "user", "content": oai_content})
                return out if out else [{"role": "user", "content": ""}]

            return [{"role": role, "content": str(content)}]

        # Construire la liste des messages OpenAI
        oai_messages: list[dict] = [{"role": "system", "content": self._system_prompt()}]
        for m in messages:
            oai_messages.extend(_msg_to_openai(m))

        # ── Appel GPT-4o ─────────────────────────────────────────────────────
        client_gpt = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        kwargs: dict = {
            "model": settings.GPT_MODEL_FALLBACK,
            "max_tokens": settings.IA_MAX_TOKENS,
            "messages": oai_messages,
        }
        if outils_gpt:
            kwargs["tools"] = outils_gpt
            kwargs["tool_choice"] = "auto"

        resp = client_gpt.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        msg = choice.message

        # ── Conversion réponse OpenAI → objet compatible Anthropic ───────────
        @dataclass
        class _TextBlock:
            type: str = "text"
            text: str = ""

        @dataclass
        class _ToolUseBlock:
            type: str = "tool_use"
            id: str = ""
            name: str = ""
            input: dict = dc_field(default_factory=dict)

        @dataclass
        class _MockResponse:
            stop_reason: str
            content: list

        blocks: list = []
        if msg.content:
            blocks.append(_TextBlock(type="text", text=msg.content))

        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    params = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    params = {}
                blocks.append(_ToolUseBlock(
                    type="tool_use",
                    id=tc.id,
                    name=tc.function.name,
                    input=params,
                ))

        finish = choice.finish_reason  # "stop" | "tool_calls" | "length"
        stop_reason = "tool_use" if finish == "tool_calls" else "end_turn"

        return _MockResponse(stop_reason=stop_reason, content=blocks)

    def _prompt_questions_specifiques(self) -> str:
        """
        Override dans chaque agent pour définir PRÉCISÉMENT quand et quoi demander.
        Retourne un bloc texte injecté dans le prompt de chaque appel.
        """
        return ""

    def _construire_prompt(self, instruction: str, contexte: dict) -> str:
        import json
        parties = [f"INSTRUCTION : {instruction}"]
        if contexte:
            parties.append(f"CONTEXTE :\n{json.dumps(contexte, ensure_ascii=False, indent=2)}")

        # Injecter le guide de demande d'informations complémentaires
        guide_questions = self._prompt_questions_specifiques()
        if guide_questions:
            parties.append(
                "━━━ GUIDE : DEMANDE D'INFORMATIONS COMPLÉMENTAIRES ━━━\n"
                "Quand une information essentielle manque, utilise l'outil "
                "`demander_information_utilisateur` de façon PROGRESSIVE :\n"
                "• Pose UNE question à la fois (ne pas regrouper toutes les questions en une)\n"
                "• Dès que tu reçois la réponse, continue ton travail ou pose la question suivante si nécessaire\n"
                "• Formule chaque question de manière PRÉCISE et CONTEXTUALISÉE\n"
                "• Indique toujours dans `contexte` POURQUOI tu as besoin de cette info\n\n"
                f"SCÉNARIOS SPÉCIFIQUES À CET AGENT :\n{guide_questions}"
            )

        return "\n\n".join(parties)

    # ── Outil de demande d'information — injecté automatiquement dans tous les agents ──

    _OUTIL_DEMANDER_INFO = {
        "name": "demander_information_utilisateur",
        "description": (
            "Pose une question à l'utilisateur humain quand une information essentielle "
            "manque pour continuer le processus. L'agent se met en pause jusqu'à réception "
            "de la réponse. À utiliser UNIQUEMENT si l'information ne peut pas être trouvée "
            "dans ORASS, les documents, ou le contexte disponible. "
            "Les médias (images, PDF) fournis par l'utilisateur sont automatiquement "
            "archivés dans le système d'archive numérique Yukpo et transmis en base64 "
            "pour analyse directe via Claude Vision. Pour les pièces justificatives "
            "(photos sinistre, pièces comptables, documents d'identité, contrats scannés, "
            "relevés bancaires), utiliser type_reponse='image' ou type_reponse='images'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "La question précise à poser à l'utilisateur"
                },
                "contexte": {
                    "type": "string",
                    "description": "Explication brève du pourquoi cette information est nécessaire"
                },
                "choix_possibles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Si la réponse est un choix parmi plusieurs options (optionnel)"
                },
                "type_reponse": {
                    "type": "string",
                    "enum": [
                        "texte_libre", "choix_multiple", "oui_non", "nombre", "date",
                        "image",   # une seule image/document attendu
                        "images",  # plusieurs images/documents attendus (photos sinistre, pièces comptables, etc.)
                    ],
                    "description": "Type de réponse attendue. Utiliser 'image' pour un document/photo unique, 'images' pour plusieurs pièces justificatives."
                },
                "nombre_images_max": {
                    "type": "integer",
                    "description": "Nombre maximum d'images/documents attendus (uniquement pour type image/images, défaut: 1 pour 'image', 5 pour 'images')"
                },
                "formats_acceptes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Formats acceptés (ex: ['jpg','png','pdf']). Par défaut: jpg, png, pdf"
                },
            },
            "required": ["question", "type_reponse"],
        },
    }

    def _necessite_validation(self, outil: str, params: dict, resultat: str) -> bool:
        """
        Détermine si une action outil nécessite une validation humaine.

        OUTILS FINANCIERS : validation si montant > 0 ou si résultat contient un montant FCFA.
        OUTILS DE DÉCISION : validation systématique (embauche, transaction, clôture, etc.)
        """
        # Outils financiers directs
        outils_financiers = {
            "valider_sinistre", "emettre_police", "payer_indemnite",
            "collecter_prime", "passer_ecriture_comptable",
        }
        # Outils de décision RH/juridique/compta
        outils_decision = {
            "approuver_conge", "emettre_contrat", "lancer_cloture",
            "valider_transaction", "embaucher",
        }
        # Outils de communication externalisée massive
        outils_diffusion = {
            "envoyer_campagne", "generer_rapport_direction",
        }

        if outil in outils_financiers:
            montant = params.get("montant", params.get("prime_ttc", params.get("montant_offert", 0)))
            if isinstance(montant, (int, float)) and montant > 0:
                return True
            if "FCFA" in resultat and "EN ATTENTE" not in resultat:
                return True

        if outil in outils_decision:
            return True

        # NE PAS RE-VALIDER si déjà en attente (éviter boucle infinie)
        if "EN ATTENTE DE VALIDATION" in resultat:
            return False

        return False

    async def stream_executer(
        self,
        instruction: str,
        user_id: int,
        contexte: dict,
    ) -> AsyncGenerator[EtapeAgent, None]:
        """Stream les étapes en temps réel."""
        execution_id = str(uuid.uuid4())

        yield EtapeAgent(
            type="action",
            libelle=f"Démarrage {self.type_agent.value}",
            detail=instruction[:100],
            statut="en_cours",
        )

        resultat = await self.executer(instruction, user_id, contexte, execution_id)
        for etape in resultat.etapes:
            yield etape

        # Étape finale
        if resultat.statut == StatutExecution.EN_ATTENTE:
            statut_final = "en_cours"
            libelle_final = "En attente de validation humaine"
        elif resultat.statut == StatutExecution.TERMINE:
            statut_final = "ok"
            libelle_final = "Terminé"
        else:
            statut_final = "erreur"
            libelle_final = "Erreur"

        yield EtapeAgent(
            type="resultat",
            libelle=libelle_final,
            detail=resultat.resume or resultat.erreur or "",
            statut=statut_final,
            donnees={
                "actions_requises":    len(resultat.actions_requises),
                "validation_en_cours": resultat.statut == StatutExecution.EN_ATTENTE,
                "ia_appelee":          resultat.ia_appelee,
                "duree_ms":            resultat.duree_totale_ms,
            },
        )
