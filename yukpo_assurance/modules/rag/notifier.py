"""
Notifier RAG — Notifications de mise à jour des documents réglementaires.

Canaux supportés :
  - Webhook HTTP (Slack, Teams, n8n, Make, …)
  - Email via SMTP (configuré dans .env)
  - Log structuré (toujours actif en fallback)
"""
import logging
import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from typing import Optional

import httpx

logger = logging.getLogger("yukpo_assurance.rag.notifier")


class RAGNotifier:
    """Envoie des notifications lors des mises à jour RAG."""

    def __init__(self):
        self.webhook_url: Optional[str] = os.getenv("RAG_WEBHOOK_URL")
        self.email_dest:  Optional[str] = os.getenv("RAG_ALERT_EMAIL")

    # ── Notification standard ────────────────────────────────────────────

    async def notifier_mise_a_jour(
        self,
        doc_id:    str,
        nom_doc:   str,
        pays:      str,
        domaine:   str,
        nb_chunks: int,
        url:       str,
        hash_nouveau: str,
    ) -> None:
        """Notifie une mise à jour réussie d'un document RAG."""
        message = (
            f"✅ *Mise à jour RAG* — `{doc_id}`\n"
            f"• Document : {nom_doc}\n"
            f"• Pays : {pays} | Domaine : {domaine}\n"
            f"• Chunks indexés : {nb_chunks}\n"
            f"• Source : {url[:80]}{'…' if len(url) > 80 else ''}\n"
            f"• Hash : `{hash_nouveau[:16]}…`\n"
            f"• Date : {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        )
        logger.info(f"[RAGNotifier] MAJ réussie : {doc_id} ({nb_chunks} chunks)")
        await self._envoyer(f"RAG mis à jour : {doc_id}", message)

    async def notifier_echec(
        self,
        doc_id:  str,
        nom_doc: str,
        erreur:  str,
    ) -> None:
        """Notifie un échec de mise à jour — intervention manuelle requise."""
        message = (
            f"⚠️ *Échec mise à jour RAG* — `{doc_id}`\n"
            f"• Document : {nom_doc}\n"
            f"• Erreur : {erreur}\n"
            f"• Date : {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"• Action requise : vérifier l'URL source ou ingérer manuellement"
        )
        logger.warning(f"[RAGNotifier] Échec MAJ : {doc_id} — {erreur}")
        await self._envoyer(f"⚠️ ÉCHEC RAG : {doc_id}", message, alerte=True)

    async def notifier_rapport_hebdo(self, rapport: dict) -> None:
        """Envoie un rapport hebdomadaire de l'état du corpus."""
        nb_ok     = rapport.get("mis_a_jour", 0)
        nb_echecs = rapport.get("echecs", 0)
        nb_inchanges = rapport.get("inchanges", 0)

        message = (
            f"📊 *Rapport hebdomadaire RAG*\n"
            f"• ✅ Mis à jour : {nb_ok}\n"
            f"• ⏭️  Inchangés : {nb_inchanges}\n"
            f"• ❌ Échecs : {nb_echecs}\n"
            f"• Chunks total : {rapport.get('nb_chunks_total', '?')}\n"
            f"• Docs indexés : {rapport.get('nb_docs', '?')}\n"
            f"• Semaine : {datetime.utcnow().strftime('%Y-W%W')}"
        )
        logger.info(f"[RAGNotifier] Rapport hebdo : {nb_ok} MAJ, {nb_echecs} échecs")
        await self._envoyer("Rapport RAG hebdomadaire", message)

    # ── Transport ────────────────────────────────────────────────────────

    async def _envoyer(self, titre: str, message: str, alerte: bool = False) -> None:
        """Envoie via tous les canaux configurés."""
        # 1. Webhook HTTP (Slack, Teams, n8n…)
        if self.webhook_url:
            await self._envoyer_webhook(titre, message)

        # 2. Email si alerte critique
        if alerte and self.email_dest:
            await self._envoyer_email(titre, message)

    async def _envoyer_webhook(self, titre: str, message: str) -> None:
        """Envoie vers un webhook HTTP (format Slack compatible)."""
        try:
            payload = {
                "text": f"*{titre}*\n{message}",
                "blocks": [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*{titre}*\n{message}"},
                    }
                ],
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(self.webhook_url, json=payload)
                if resp.status_code not in (200, 201, 204):
                    logger.warning(
                        f"[RAGNotifier] Webhook retourné {resp.status_code}"
                    )
        except Exception as e:
            logger.warning(f"[RAGNotifier] Webhook échoué : {e}")

    async def _envoyer_email(self, titre: str, message: str) -> None:
        """Envoie un email via SMTP (configuré dans .env)."""
        try:
            smtp_host = os.getenv("SMTP_HOST", "smtp.sendgrid.net")
            smtp_port = int(os.getenv("SMTP_PORT", 587))
            smtp_user = os.getenv("SMTP_USER", "apikey")
            smtp_pass = os.getenv("SMTP_PASSWORD", "")
            from_addr = os.getenv("SMTP_FROM", "noreply@yukpo.cm")

            if not smtp_pass:
                return

            msg = MIMEText(message.replace("*", "").replace("`", ""), "plain", "utf-8")
            msg["Subject"] = f"[YukpoAssurance RAG] {titre}"
            msg["From"]    = from_addr
            msg["To"]      = self.email_dest

            # SMTP dans un thread pour ne pas bloquer la boucle asyncio
            import asyncio
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: _envoyer_smtp(smtp_host, smtp_port, smtp_user, smtp_pass, msg),
            )
        except Exception as e:
            logger.warning(f"[RAGNotifier] Email échoué : {e}")


def _envoyer_smtp(host, port, user, password, msg) -> None:
    with smtplib.SMTP(host, port) as srv:
        srv.starttls()
        srv.login(user, password)
        srv.send_message(msg)


# ─── Singleton ────────────────────────────────────────────────────────────────
rag_notifier = RAGNotifier()
