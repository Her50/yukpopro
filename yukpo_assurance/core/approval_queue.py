"""
ApprovalQueue — File de validation humaine avec reprise de processus.

PRINCIPE FONDAMENTAL :
  1. Agent pause son exécution → stocke TOUT l'état (messages, outil en attente)
  2. Humain approuve ou rejette via API
  3. L'agent REPREND exactement où il s'est arrêté avec la décision humaine
  4. Le processus complet continue jusqu'à la fin

Architecture état-complet :
  - Chaque item stocke les messages Claude + tool_use_id en attente
  - La reprise reconstruit le contexte et relance la boucle agent
  - En cas de rejet, l'agent reçoit la raison et adapte la suite

GARANTIES :
  - Aucune action financière sans validation humaine
  - Audit trail complet (qui a approuvé, quand, avec quel commentaire)
  - Timeout configurable → escalade automatique si non traité
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger("yukpo_assurance.approval_queue")

# Timeout avant escalade (en heures)
_TIMEOUT_ESCALADE_HEURES = 4


class StatutValidation(str, Enum):
    EN_ATTENTE  = "en_attente"
    APPROUVE    = "approuve"
    REJETE      = "rejete"
    EXPIRE      = "expire"
    ESCALADE    = "escalade"


@dataclass
class ItemValidation:
    """Un item en attente de validation humaine, avec état complet pour reprise."""

    id:           str = field(default_factory=lambda: str(uuid.uuid4()))
    type:         str = ""                          # sinistre | emission_police | conge_rh | ...
    description:  str = ""                          # résumé lisible pour le validateur
    donnees:      dict = field(default_factory=dict) # paramètres métier de l'action
    montant:      float = 0.0
    statut:       StatutValidation = StatutValidation.EN_ATTENTE

    # ── État de reprise ────────────────────────────────────────────────────────
    # Stockage de TOUT le contexte de conversation pour reprendre exactement
    # où l'agent s'est arrêté après décision humaine
    messages_contexte:      list = field(default_factory=list)   # historique Claude complet
    tool_use_id:            str  = ""   # ID du bloc tool_use en attente
    resultat_pre_pause:     str  = ""   # ce que l'outil avait retourné avant pause
    agent_type:             str  = ""   # TypeAgent.value pour reprendre avec le bon agent
    instruction_originale:  str  = ""   # instruction initiale de l'utilisateur
    contexte_execution:     dict = field(default_factory=dict)   # contexte métier original

    # ── Médias attachés (images, documents) ───────────────────────────────────
    medias_urls:      list = field(default_factory=list)   # chemins/URLs des fichiers uploadés
    medias_base64:    list = field(default_factory=list)   # data base64 pour injection dans Claude

    # ── Traçabilité ────────────────────────────────────────────────────────────
    user_id:          int  = 0
    execution_id:     str  = ""
    validateur_id:    Optional[int]  = None
    validateur_nom:   Optional[str]  = None
    commentaire:      str  = ""
    cree_le:          str  = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    traite_le:        Optional[str]  = None
    expires_le:       str  = field(default_factory=lambda: (
        datetime.now(timezone.utc) + timedelta(hours=_TIMEOUT_ESCALADE_HEURES)
    ).isoformat())


# Stockage en mémoire (en production → Redis ou table DB)
_file: dict[str, ItemValidation] = {}
_callbacks_approbation: list = []  # callbacks appelés après décision

# File d'attente des questions posées par l'utilisateur pendant qu'un agent est occupé
# { execution_id: [{ id, question, user_id, user_nom, reçue_le, traitee }] }
_questions_en_file: dict[str, list] = {}

# Messages d'interruption (modifications du traitement en cours)
# { execution_id: [{ id, message, user_id, user_nom, type: 'modification'|'question', reçu_le }] }
_messages_interruption: dict[str, list] = {}


class ApprovalQueue:
    """
    File de validation humaine.
    Chaque item stocke l'état complet de l'agent pour permettre la reprise.
    """

    async def ajouter(self, donnees: dict, **kwargs) -> ItemValidation:
        """
        Ajoute un item en attente de validation.

        Paramètres spéciaux (préfixés _) :
          - _messages_contexte: historique Claude complet (pour reprise)
          - _tool_use_id: ID du tool_use en attente
          - _resultat_pre_pause: résultat de l'outil avant mise en pause
          - _agent_type: type d'agent à reprendre
          - _instruction_originale: instruction initiale
        """
        # Extraire les données de reprise depuis kwargs ou donnees
        messages_contexte    = donnees.pop("_messages_contexte", [])
        tool_use_id          = donnees.pop("_tool_use_id", "")
        resultat_pre_pause   = donnees.pop("_resultat_pre_pause", "")
        agent_type           = donnees.pop("_agent_type", "")
        instruction_orig     = donnees.pop("_instruction_originale", "")
        contexte_exec        = donnees.pop("_contexte_execution", {})

        # Description lisible pour le validateur
        description = _generer_description(donnees)
        montant     = float(donnees.get("montant", donnees.get("montant_offert", donnees.get("prime_ttc", 0))))

        item = ItemValidation(
            type=donnees.get("type", "action"),
            description=description,
            donnees=donnees,
            montant=montant,
            messages_contexte=messages_contexte,
            tool_use_id=tool_use_id,
            resultat_pre_pause=resultat_pre_pause,
            agent_type=agent_type,
            instruction_originale=instruction_orig,
            contexte_execution=contexte_exec,
            user_id=donnees.pop("user_id", 0),
            execution_id=donnees.pop("execution_id", ""),
        )
        _file[item.id] = item
        logger.info(f"[ApprovalQueue] Nouvel item {item.id} — type={item.type} montant={item.montant:,.0f} FCFA")

        # Notification direction si montant critique
        if item.montant >= 5_000_000:
            await self._escalader(item, "montant_critique")

        return item

    async def approuver(
        self,
        item_id:        str,
        validateur_id:  int,
        validateur_nom: str,
        commentaire:    str = "",
    ) -> Optional[Any]:
        """
        Approuve un item et REPREND l'exécution de l'agent.
        Retourne le ResultatAgent de la reprise (ou None si pas de contexte).
        """
        item = _file.get(item_id)
        if not item:
            raise ValueError(f"Item {item_id} introuvable")
        if item.statut != StatutValidation.EN_ATTENTE:
            raise ValueError(f"Item {item_id} déjà traité (statut: {item.statut})")

        item.statut = StatutValidation.APPROUVE
        item.validateur_id = validateur_id
        item.validateur_nom = validateur_nom
        item.commentaire = commentaire
        item.traite_le = datetime.now(timezone.utc).isoformat()

        logger.info(f"[ApprovalQueue] APPROUVÉ {item_id} par {validateur_nom}")

        # Reprendre l'exécution de l'agent si contexte stocké
        if item.messages_contexte and item.agent_type and item.tool_use_id:
            return await self._reprendre_execution(
                item=item,
                decision="APPROUVÉ",
                commentaire=commentaire,
                validateur_nom=validateur_nom,
            )
        return None

    async def rejeter(
        self,
        item_id:        str,
        validateur_id:  int,
        validateur_nom: str,
        motif:          str,
    ) -> Optional[Any]:
        """
        Rejette un item et reprend l'agent avec la décision de rejet.
        L'agent adapte la suite du processus (notification assuré, etc.)
        """
        item = _file.get(item_id)
        if not item:
            raise ValueError(f"Item {item_id} introuvable")
        if item.statut != StatutValidation.EN_ATTENTE:
            raise ValueError(f"Item {item_id} déjà traité")

        item.statut = StatutValidation.REJETE
        item.validateur_id = validateur_id
        item.validateur_nom = validateur_nom
        item.commentaire = motif
        item.traite_le = datetime.now(timezone.utc).isoformat()

        logger.info(f"[ApprovalQueue] REJETÉ {item_id} par {validateur_nom} — motif: {motif}")

        if item.messages_contexte and item.agent_type and item.tool_use_id:
            return await self._reprendre_execution(
                item=item,
                decision="REJETÉ",
                commentaire=motif,
                validateur_nom=validateur_nom,
            )
        return None

    async def repondre_question(
        self,
        item_id:       str,
        reponse:       str,
        user_id:       int,
        user_nom:      str,
        medias_urls:   list | None = None,
        medias_base64: list | None = None,
    ) -> Optional[Any]:
        """
        Soumet la réponse d'un utilisateur à une question posée par l'agent.
        Supporte les médias (images, documents PDF) pour les types image/images.
        Injecte la réponse + médias dans le contexte et reprend l'exécution.
        """
        item = _file.get(item_id)
        if not item:
            raise ValueError(f"Question {item_id} introuvable")
        if item.statut != StatutValidation.EN_ATTENTE:
            raise ValueError(f"Question {item_id} déjà traitée (statut: {item.statut})")
        if item.type != "question_utilisateur":
            raise ValueError(f"Item {item_id} n'est pas une question utilisateur")

        item.statut = StatutValidation.APPROUVE
        item.validateur_id  = user_id
        item.validateur_nom = user_nom
        item.commentaire    = reponse
        item.traite_le      = datetime.now(timezone.utc).isoformat()
        if medias_urls:
            item.medias_urls    = medias_urls
        if medias_base64:
            item.medias_base64  = medias_base64

        nb_medias = len(medias_urls or [])
        logger.info(
            f"[ApprovalQueue] Réponse reçue pour question {item_id} par {user_nom}: "
            f"{reponse[:100]} + {nb_medias} média(s)"
        )

        if item.messages_contexte and item.agent_type and item.tool_use_id:
            return await self._reprendre_execution(
                item=item,
                decision=f"RÉPONSE UTILISATEUR : {reponse}",
                commentaire=reponse,
                validateur_nom=user_nom,
            )
        return None

    async def _reprendre_execution(
        self,
        item:           ItemValidation,
        decision:       str,
        commentaire:    str,
        validateur_nom: str,
    ):
        """
        Reprend l'exécution de l'agent depuis l'état sauvegardé.
        Injecte la décision humaine dans les messages et relance la boucle.
        """
        from core.agent_orchestrateur import TypeAgent, agent_orchestrateur
        agent_orchestrateur._charger_agents()

        try:
            agent_type_enum = TypeAgent(item.agent_type)
        except ValueError:
            logger.error(f"[ApprovalQueue] TypeAgent inconnu : {item.agent_type}")
            return None

        agent = agent_orchestrateur._agents.get(agent_type_enum)
        if not agent:
            logger.error(f"[ApprovalQueue] Agent {agent_type_enum} non disponible pour reprise")
            return None

        # Construire le message à injecter selon la nature de la décision
        if decision.startswith("RÉPONSE UTILISATEUR :"):
            # Réponse à une question de clarification posée par l'agent
            message_decision = (
                f"Réponse de l'utilisateur ({validateur_nom}) : {commentaire}\n"
                f"Reprends le processus en tenant compte de cette information."
            )
        elif decision == "APPROUVÉ":
            message_decision = f"✅ APPROUVÉ par {validateur_nom}"
            if commentaire:
                message_decision += f" — Commentaire : {commentaire}"
            message_decision += "\nContinuer le processus selon cette décision."
        else:
            message_decision = f"❌ REJETÉ par {validateur_nom}"
            if commentaire:
                message_decision += f" — Motif : {commentaire}"
            message_decision += "\nAdapter la suite du processus en tenant compte de ce rejet."

        # Ajouter le résultat de l'outil + la décision humaine aux messages
        messages_reprise = list(item.messages_contexte)

        # Construire le contenu du tool_result
        texte_base = item.resultat_pre_pause
        if texte_base:
            texte_base += f"\n\n{message_decision}"
        else:
            texte_base = message_decision

        # Si des médias (images/documents) ont été fournis → injecter en vision Claude
        if item.medias_base64:
            # Contenu multi-modal : texte + images
            content_blocs: list = [{"type": "text", "text": texte_base}]
            for i, b64_data in enumerate(item.medias_base64):
                # Détecter le type MIME depuis l'en-tête base64 ou forcer JPEG
                media_type = "image/jpeg"
                if b64_data.startswith("data:"):
                    # "data:image/png;base64,AAA..." → extraire le type
                    try:
                        header, b64_data = b64_data.split(",", 1)
                        media_type = header.split(":")[1].split(";")[0]
                    except Exception:
                        pass
                content_blocs.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": b64_data,
                    },
                })
                logger.info(f"[ApprovalQueue] Image {i+1}/{len(item.medias_base64)} injectée dans Claude ({media_type})")
            tool_result_content = content_blocs
        elif item.medias_urls:
            # Médias stockés sur disque — joindre les descriptions
            descriptions = "\n".join(f"  • Média {i+1}: {url}" for i, url in enumerate(item.medias_urls))
            tool_result_content = f"{texte_base}\n\nMédias fournis par l'utilisateur :\n{descriptions}"
        else:
            tool_result_content = texte_base

        # Injecter le tool_result avec décision dans les messages
        messages_reprise.append({
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": item.tool_use_id,
                "content": tool_result_content,
            }]
        })

        logger.info(f"[ApprovalQueue] Reprise {item.agent_type} exec={item.execution_id} décision={decision}")

        # Reprendre la boucle agent depuis ce point
        return await agent.executer_depuis_contexte(
            messages=messages_reprise,
            user_id=item.user_id,
            contexte=item.contexte_execution,
            execution_id=item.execution_id + "_reprise",
            instruction=item.instruction_originale,
        )

    def lister(
        self,
        statut:     Optional[str] = None,
        type_item:  Optional[str] = None,
        user_id:    Optional[int] = None,
        limit:      int = 50,
    ) -> list[dict]:
        """Liste les items avec filtres optionnels."""
        items = list(_file.values())
        if statut:
            items = [i for i in items if i.statut.value == statut]
        if type_item:
            items = [i for i in items if i.type == type_item]
        if user_id:
            items = [i for i in items if i.user_id == user_id]
        items.sort(key=lambda i: i.cree_le, reverse=True)
        return [_serialiser_item(i) for i in items[:limit]]

    def get(self, item_id: str) -> Optional[dict]:
        item = _file.get(item_id)
        return _serialiser_item(item) if item else None

    def stats(self) -> dict:
        total = len(_file)
        en_attente = sum(1 for i in _file.values() if i.statut == StatutValidation.EN_ATTENTE)
        approuves  = sum(1 for i in _file.values() if i.statut == StatutValidation.APPROUVE)
        rejetes    = sum(1 for i in _file.values() if i.statut == StatutValidation.REJETE)
        montant_en_attente = sum(i.montant for i in _file.values() if i.statut == StatutValidation.EN_ATTENTE)
        return {
            "total": total,
            "en_attente": en_attente,
            "approuves": approuves,
            "rejetes": rejetes,
            "montant_en_attente_fcfa": montant_en_attente,
        }

    async def _escalader(self, item: ItemValidation, raison: str):
        """Escalade un item critique à la direction."""
        try:
            from core.notifications import notifications
            await notifications.envoyer_alerte_direction(
                niveau="avertissement",
                message=f"Validation requise ({raison}) — {item.description} — {item.montant:,.0f} FCFA",
                article=f"Item ID: {item.id}",
            )
        except Exception as e:
            logger.error(f"[ApprovalQueue] Erreur escalade : {e}")

    # ── File d'attente questions utilisateur (en cours de traitement) ─────────

    def envoyer_message_en_cours(
        self,
        execution_id: str,
        message: str,
        user_id: int,
        user_nom: str,
    ) -> dict:
        """
        Envoie un message à un agent pendant son exécution.

        Détecte automatiquement si c'est :
        - Une MODIFICATION du traitement → injectée dans la boucle agent
        - Une QUESTION à traiter après → mise en file d'attente

        Retourne un dict avec le type détecté et l'ID du message.
        """
        # Mots-clés signalant une modification de traitement
        mots_modification = [
            "annule", "annuler", "stop", "arrête", "arreter",
            "modifie", "modifier", "change", "changer", "plutôt",
            "non finalement", "en fait", "plutot",
            "corrige", "corriger", "revise", "révise",
            "ne pas", "ne plus", "abandon", "interromps",
        ]
        msg_lower = message.lower()
        est_modification = any(mot in msg_lower for mot in mots_modification)
        type_msg = "modification" if est_modification else "question"

        mid = str(uuid.uuid4())
        if execution_id not in _messages_interruption:
            _messages_interruption[execution_id] = []
        _messages_interruption[execution_id].append({
            "id":       mid,
            "message":  message,
            "user_id":  user_id,
            "user_nom": user_nom,
            "type":     type_msg,
            "reçu_le":  datetime.now(timezone.utc).isoformat(),
            "traite":   False,
        })
        logger.info(
            f"[ApprovalQueue] Message {type_msg} reçu pour exec={execution_id} "
            f"par {user_nom}: {message[:80]}"
        )
        return {"id": mid, "type": type_msg, "execution_id": execution_id}

    def consommer_messages_interruption(self, execution_id: str) -> list[dict]:
        """
        Récupère et marque comme traités tous les messages d'interruption en attente
        pour une exécution. Appelé par la boucle agent entre deux tours.
        """
        messages = _messages_interruption.get(execution_id, [])
        non_traites = [m for m in messages if not m.get("traite")]
        for m in non_traites:
            m["traite"] = True
        return non_traites

    def mettre_en_file_question(
        self,
        execution_id: str,
        question_utilisateur: str,
        user_id: int,
        user_nom: str,
    ) -> str:
        """
        Enregistre une question posée par l'utilisateur pendant qu'un agent est occupé.
        L'agent la traitera dès qu'il aura terminé le traitement en cours.
        Retourne l'ID de la question mise en file.
        """
        fid = str(uuid.uuid4())
        if execution_id not in _questions_en_file:
            _questions_en_file[execution_id] = []
        _questions_en_file[execution_id].append({
            "id":               fid,
            "question":         question_utilisateur,
            "user_id":          user_id,
            "user_nom":         user_nom,
            "reçue_le":         datetime.now(timezone.utc).isoformat(),
            "traitee":          False,
        })
        logger.info(
            f"[ApprovalQueue] Question mise en file pour exec={execution_id} "
            f"par {user_nom}: {question_utilisateur[:80]}"
        )
        return fid

    def recuperer_questions_en_file(self, execution_id: str) -> list[dict]:
        """Récupère et vide la file des questions en attente pour une exécution."""
        questions = _questions_en_file.pop(execution_id, [])
        return [q for q in questions if not q.get("traitee")]

    def questions_en_attente_pour_exec(self, execution_id: str) -> int:
        """Nombre de questions en file pour une exécution donnée."""
        return len([q for q in _questions_en_file.get(execution_id, []) if not q.get("traitee")])

    async def verifier_expirations(self):
        """Tâche périodique : escalade les items expirés sans traitement."""
        now = datetime.now(timezone.utc)
        for item in _file.values():
            if item.statut != StatutValidation.EN_ATTENTE:
                continue
            expires = datetime.fromisoformat(item.expires_le)
            if now > expires:
                item.statut = StatutValidation.ESCALADE
                logger.warning(f"[ApprovalQueue] Item {item.id} expiré → escalade")
                await self._escalader(item, "timeout_validation")


def _generer_description(donnees: dict) -> str:
    """Génère une description lisible pour le validateur."""
    type_item = donnees.get("type", "")
    descriptions = {
        "question_utilisateur":    f"❓ Question agent : {donnees.get('question', '')[:120]}",
        "sinistre":                f"Sinistre {donnees.get('reference', '')} — {donnees.get('decision', '')} — {donnees.get('montant', 0):,.0f} FCFA",
        "emission_police":         f"Émission police — {donnees.get('assure', '')} — {donnees.get('prime_ttc', 0):,.0f} FCFA",
        "conge_rh":                f"Congé {donnees.get('type_conge', '')} — {donnees.get('employe_id', '')} — {donnees.get('date_debut', '')} → {donnees.get('date_fin', '')}",
        "recrutement_offre":       f"Publication offre : {donnees.get('poste', '')}",
        "embauche":                f"Embauche : {donnees.get('candidat_id', '')} — {donnees.get('poste', '')}",
        "transaction_juridique":   f"Transaction {donnees.get('reference', '')} — {donnees.get('montant_offert', 0):,.0f} FCFA",
        "ecriture_comptable_grande": f"Écriture comptable — {donnees.get('montant', 0):,.0f} FCFA",
        "cloture_comptable":       f"Clôture {donnees.get('type_cloture', '')} {donnees.get('periode', '')}",
        "rapport_direction":       f"Rapport {donnees.get('type_rapport', '')} {donnees.get('periode', '')} → {', '.join(donnees.get('destinataires', []))}",
    }
    return descriptions.get(type_item, f"{type_item} — {str(donnees)[:100]}")


def _serialiser_item(item: ItemValidation) -> dict:
    """Sérialise un item pour l'API (sans les messages contexte — trop volumineux)."""
    d: dict = {
        "id":             item.id,
        "type":           item.type,
        "description":    item.description,
        "donnees":        item.donnees,
        "montant":        item.montant,
        "statut":         item.statut.value,
        "user_id":        item.user_id,
        "execution_id":   item.execution_id,
        "validateur_id":  item.validateur_id,
        "validateur_nom": item.validateur_nom,
        "commentaire":    item.commentaire,
        "cree_le":        item.cree_le,
        "traite_le":      item.traite_le,
        "expires_le":     item.expires_le,
        "peut_reprendre": bool(item.messages_contexte and item.tool_use_id),
    }
    # Champs supplémentaires pour les questions utilisateur
    if item.type == "question_utilisateur":
        d["question"]            = item.donnees.get("question", "")
        d["contexte_question"]   = item.donnees.get("contexte_question", "")
        d["choix_possibles"]     = item.donnees.get("choix_possibles", [])
        d["type_reponse"]        = item.donnees.get("type_reponse", "texte_libre")
        d["nombre_images_max"]   = item.donnees.get("nombre_images_max", 1)
        d["formats_acceptes"]    = item.donnees.get("formats_acceptes", ["jpg", "png", "pdf"])
        d["medias_urls"]         = item.medias_urls
    return d


# Singleton
approval_queue = ApprovalQueue()
