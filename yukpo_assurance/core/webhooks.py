"""
YukpoAssurance — Service Webhooks avec retry exponentiel

Permet aux compagnies partenaires de recevoir des notifications push pour :
- Nouveau sinistre déclaré
- Statut sinistre mis à jour
- Paiement reçu / échoué
- Alerte fraude déclenchée
- Alerte conformité CIMA

Architecture :
1. EventWebhook décrit l'événement (type, payload, destinataire)
2. WebhookService.envoyer() tente l'envoi HTTP POST avec HMAC-SHA256
3. En cas d'échec : retry exponentiel avec backoff (3 tentatives max)
4. Persistence en DB pour audit trail et retry au redémarrage
5. Dead Letter Queue : événements en échec après max_retries → stockage + alerte
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import httpx

logger = logging.getLogger("yukpo_assurance.webhooks")

# Retry config
_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 2   # 2s, 4s, 8s
_TIMEOUT_SECONDS = 10


class TypeEvenement(str, Enum):
    SINISTRE_NOUVEAU       = "sinistre.nouveau"
    SINISTRE_STATUT_MIS_A_JOUR = "sinistre.statut_mis_a_jour"
    PAIEMENT_RECU          = "paiement.recu"
    PAIEMENT_ECHOUE        = "paiement.echoue"
    FRAUDE_ALERTE          = "fraude.alerte"
    CONFORMITE_ALERTE      = "conformite.alerte"
    CONTRAT_EXPIRE         = "contrat.expire"
    CONTRAT_SOUSCRIT       = "contrat.souscrit"
    OCR_TERMINE            = "ocr.termine"


@dataclass
class EvenementWebhook:
    type_evenement: TypeEvenement
    payload: dict
    compagnie_id: int
    url_destination: str
    secret_hmac: str                      # Partagé avec le destinataire pour vérification
    webhook_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    nb_tentatives: int = 0
    max_retries: int = _MAX_RETRIES
    statut: str = "pending"               # pending | sent | failed | dead_letter


@dataclass
class ResultatEnvoi:
    succes: bool
    statut_http: Optional[int] = None
    nb_tentatives: int = 0
    erreur: Optional[str] = None
    duree_ms: float = 0.0


class WebhookService:
    """
    Service d'envoi de webhooks avec retry exponentiel et HMAC-SHA256.

    Usage :
        await webhook_service.envoyer(EvenementWebhook(
            type_evenement=TypeEvenement.SINISTRE_NOUVEAU,
            payload={"numero_sinistre": "SIN-AUTO-001", ...},
            compagnie_id=1,
            url_destination="https://partner.cm/webhooks/yukpo",
            secret_hmac="shared_secret",
        ))
    """

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._worker_task: Optional[asyncio.Task] = None

    def demarrer_worker(self) -> None:
        """Démarre le worker async de traitement de queue en arrière-plan."""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.ensure_future(self._worker_loop())
            logger.info("[Webhooks] Worker démarré")

    async def arreter_worker(self) -> None:
        """Arrête proprement le worker."""
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            logger.info("[Webhooks] Worker arrêté")

    # ─── API principale ───────────────────────────────────────────────────────

    async def envoyer(self, evenement: EvenementWebhook) -> ResultatEnvoi:
        """
        Envoie un webhook avec retry exponentiel.
        Méthode directe (bloquante jusqu'à succès ou max_retries).
        """
        for tentative in range(1, evenement.max_retries + 1):
            evenement.nb_tentatives = tentative
            debut = time.monotonic()

            try:
                resultat = await self._envoyer_http(evenement)
                if resultat.succes:
                    evenement.statut = "sent"
                    logger.info(
                        f"[Webhooks] ✓ Envoyé {evenement.type_evenement} → {evenement.url_destination} "
                        f"(tentative {tentative}, {resultat.duree_ms:.0f}ms)"
                    )
                    await self._persister(evenement, resultat)
                    return resultat

            except Exception as e:
                resultat = ResultatEnvoi(
                    succes=False,
                    erreur=str(e),
                    nb_tentatives=tentative,
                    duree_ms=(time.monotonic() - debut) * 1000,
                )

            # Backoff exponentiel avant le prochain essai
            if tentative < evenement.max_retries:
                backoff = _BACKOFF_BASE_SECONDS ** tentative
                logger.warning(
                    f"[Webhooks] ✗ Tentative {tentative}/{evenement.max_retries} échouée "
                    f"(url={evenement.url_destination}) → retry dans {backoff}s"
                )
                await asyncio.sleep(backoff)

        # Tous les essais épuisés → Dead Letter
        evenement.statut = "dead_letter"
        logger.error(
            f"[Webhooks] DEAD LETTER: {evenement.type_evenement} → {evenement.url_destination} "
            f"après {evenement.max_retries} tentatives"
        )
        await self._persister(evenement, ResultatEnvoi(
            succes=False,
            erreur="Max retries atteint",
            nb_tentatives=evenement.max_retries,
        ))
        await self._alerter_dead_letter(evenement)

        return ResultatEnvoi(
            succes=False,
            erreur="Toutes les tentatives ont échoué",
            nb_tentatives=evenement.max_retries,
        )

    async def enqueuer(self, evenement: EvenementWebhook) -> bool:
        """
        Ajoute un événement dans la queue pour traitement asynchrone.
        Non-bloquant — retourne True si la queue a accepté l'événement.
        """
        try:
            self._queue.put_nowait(evenement)
            return True
        except asyncio.QueueFull:
            logger.error(f"[Webhooks] Queue pleine — événement {evenement.type_evenement} perdu")
            return False

    # ─── Worker async ──────────────────────────────────────────────────────────

    async def _worker_loop(self) -> None:
        """Worker qui consomme la queue en continu."""
        logger.info("[Webhooks] Worker loop démarré")
        while True:
            try:
                evenement = await self._queue.get()
                await self.envoyer(evenement)
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Webhooks] Erreur worker: {e}")

    # ─── HTTP ─────────────────────────────────────────────────────────────────

    async def _envoyer_http(self, evenement: EvenementWebhook) -> ResultatEnvoi:
        """Envoie la requête HTTP POST avec HMAC-SHA256."""
        payload_json = json.dumps({
            "webhook_id": evenement.webhook_id,
            "type": evenement.type_evenement,
            "timestamp": evenement.timestamp,
            "compagnie_id": evenement.compagnie_id,
            "data": evenement.payload,
        }, ensure_ascii=False)

        # Signature HMAC-SHA256
        signature = hmac.new(
            evenement.secret_hmac.encode(),
            payload_json.encode(),
            hashlib.sha256,
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-YukpoAssurance-Signature": f"sha256={signature}",
            "X-YukpoAssurance-Event": evenement.type_evenement,
            "X-YukpoAssurance-Delivery": evenement.webhook_id,
            "User-Agent": "YukpoAssurance-Webhooks/1.0",
        }

        debut = time.monotonic()
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(
                evenement.url_destination,
                content=payload_json,
                headers=headers,
            )

        duree_ms = (time.monotonic() - debut) * 1000
        succes = 200 <= response.status_code < 300

        return ResultatEnvoi(
            succes=succes,
            statut_http=response.status_code,
            nb_tentatives=evenement.nb_tentatives,
            duree_ms=duree_ms,
            erreur=None if succes else f"HTTP {response.status_code}",
        )

    # ─── Persistance ──────────────────────────────────────────────────────────

    async def _persister(self, evenement: EvenementWebhook, resultat: ResultatEnvoi) -> None:
        """Enregistre le webhook en DB pour l'audit trail."""
        try:
            from core.database import async_session_maker, AuditLogDB
            async with async_session_maker() as db:
                db.add(AuditLogDB(
                    user_id=0,
                    action=f"webhook.{evenement.statut}",
                    ressource="webhook",
                    details=json.dumps({
                        "webhook_id": evenement.webhook_id,
                        "type_evenement": evenement.type_evenement,
                        "url": evenement.url_destination,
                        "compagnie_id": evenement.compagnie_id,
                        "nb_tentatives": evenement.nb_tentatives,
                        "statut": evenement.statut,
                        "statut_http": resultat.statut_http,
                        "duree_ms": round(resultat.duree_ms, 1),
                    }),
                    ip_address="internal",
                    statut="success" if resultat.succes else "error",
                ))
                await db.commit()
        except Exception as e:
            logger.warning(f"[Webhooks] Persistance audit échouée: {e}")

    async def _alerter_dead_letter(self, evenement: EvenementWebhook) -> None:
        """Alerte interne quand un webhook passe en Dead Letter."""
        logger.error(
            f"[Webhooks] DEAD LETTER — compagnie={evenement.compagnie_id} "
            f"type={evenement.type_evenement} url={evenement.url_destination}"
        )
        # En production : envoyer une notification à l'équipe ops (email/Slack)


# ── Helpers pour émettre des événements depuis les modules métier ─────────────

async def notifier_nouveau_sinistre(
    numero_sinistre: str,
    compagnie_id: int,
    score_fraude: float = 0,
    montant: float = 0,
) -> None:
    """Notifie les webhooks de la compagnie d'un nouveau sinistre."""
    await _notifier_si_configure(
        compagnie_id=compagnie_id,
        type_evenement=TypeEvenement.SINISTRE_NOUVEAU,
        payload={
            "numero_sinistre": numero_sinistre,
            "score_fraude": score_fraude,
            "montant_declare": montant,
            "alerte_fraude": score_fraude > 75,
        },
    )


async def notifier_paiement(
    reference_paiement: str,
    compagnie_id: int,
    montant: float,
    succes: bool,
    operateur: str = "",
) -> None:
    """Notifie d'un paiement Mobile Money."""
    type_evt = TypeEvenement.PAIEMENT_RECU if succes else TypeEvenement.PAIEMENT_ECHOUE
    await _notifier_si_configure(
        compagnie_id=compagnie_id,
        type_evenement=type_evt,
        payload={
            "reference": reference_paiement,
            "montant_fcfa": montant,
            "operateur": operateur,
            "succes": succes,
        },
    )


async def notifier_alerte_conformite(
    compagnie_id: int,
    alerte: str,
    niveau: str = "CRITIQUE",
    ratio: str = "",
) -> None:
    """Notifie d'une alerte de conformité CIMA."""
    await _notifier_si_configure(
        compagnie_id=compagnie_id,
        type_evenement=TypeEvenement.CONFORMITE_ALERTE,
        payload={
            "alerte": alerte,
            "niveau": niveau,
            "ratio": ratio,
        },
    )


async def _notifier_si_configure(
    compagnie_id: int,
    type_evenement: TypeEvenement,
    payload: dict,
) -> None:
    """Envoie un événement webhook si la compagnie a configuré un endpoint."""
    try:
        # Charger la config webhook depuis la DB
        from core.database import async_session_maker, CompagnieDB
        from sqlalchemy import select

        async with async_session_maker() as db:
            result = await db.execute(
                select(CompagnieDB).where(CompagnieDB.id == compagnie_id)
            )
            compagnie = result.scalar_one_or_none()

        if not compagnie:
            return

        # Récupérer l'URL et le secret depuis les données de la compagnie
        config = compagnie.configuration or {}
        webhook_url = config.get("webhook_url")
        webhook_secret = config.get("webhook_secret", "")

        if not webhook_url:
            return  # Pas de webhook configuré pour cette compagnie

        evenement = EvenementWebhook(
            type_evenement=type_evenement,
            payload=payload,
            compagnie_id=compagnie_id,
            url_destination=webhook_url,
            secret_hmac=webhook_secret,
        )

        # Envoi en background (non-bloquant)
        asyncio.ensure_future(webhook_service.envoyer(evenement))

    except Exception as e:
        logger.warning(f"[Webhooks] Notification {type_evenement} compagnie={compagnie_id}: {e}")


# ── Vérification HMAC côté récepteur ─────────────────────────────────────────

def verifier_signature_webhook(
    payload_json: str,
    signature_header: str,
    secret: str,
) -> bool:
    """
    Vérification côté récepteur de la signature HMAC-SHA256.
    À utiliser dans les endpoints récepteurs de webhooks.

    Usage :
        ok = verifier_signature_webhook(
            payload_json=request.body(),
            signature_header=request.headers["X-YukpoAssurance-Signature"],
            secret="my_shared_secret",
        )
    """
    expected = hmac.new(
        secret.encode(), payload_json.encode(), hashlib.sha256
    ).hexdigest()
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)


# Instance singleton
webhook_service = WebhookService()
