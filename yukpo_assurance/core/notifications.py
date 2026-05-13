"""
YukpoAssurance — Service de notifications (WhatsApp / SMS / Email)
Gère l'envoi avec retry automatique et file d'attente en mémoire.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config.settings import settings

logger = logging.getLogger("yukpo_assurance.notifications")

# File d'attente des messages en attente
_queue: list[dict] = []
_failed: list[dict] = []


@dataclass
class Message:
    destinataire: str           # numéro WhatsApp : "whatsapp:+2250701010101"
    contenu: str
    type: str = "whatsapp"     # "whatsapp" | "sms" | "email"
    tentatives: int = 0
    max_tentatives: int = 3
    creee_le: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(Exception),
)
async def _envoyer_whatsapp_avec_retry(destinataire: str, contenu: str) -> bool:
    """Envoi WhatsApp via Twilio avec retry exponentiel."""
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        logger.warning("[Notif] Twilio non configuré — message simulé")
        logger.info(f"[Notif/SIM] WhatsApp → {destinataire}: {contenu[:80]}...")
        return True

    from twilio.rest import Client
    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    from_number = settings.TWILIO_WHATSAPP_NUMBER or "whatsapp:+14155238886"

    # Normaliser le numéro
    if not destinataire.startswith("whatsapp:"):
        destinataire = f"whatsapp:{destinataire}"

    message = client.messages.create(
        body=contenu,
        from_=from_number,
        to=destinataire,
    )
    logger.info(f"[Notif] WhatsApp envoyé SID={message.sid} → {destinataire}")
    return True


async def envoyer_whatsapp(
    destinataire: str,
    contenu: str,
    metadata: Optional[dict] = None,
) -> bool:
    """
    Envoie un message WhatsApp avec retry automatique.
    En cas d'échec définitif, stocke dans _failed pour retraitement manuel.
    """
    msg = Message(
        destinataire=destinataire,
        contenu=contenu,
        metadata=metadata or {},
    )
    try:
        ok = await _envoyer_whatsapp_avec_retry(destinataire, contenu)
        if ok:
            logger.info(f"[Notif] Message envoyé à {destinataire}")
        return ok
    except Exception as e:
        logger.error(f"[Notif] Échec définitif WhatsApp → {destinataire}: {e}")
        msg.tentatives = msg.max_tentatives
        _failed.append({
            "destinataire": destinataire,
            "contenu": contenu,
            "erreur": str(e),
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        })
        return False


async def envoyer_alerte_churn(
    telephone: str,
    nom_assure: str,
    message_commercial: str,
    numero_police: str,
) -> bool:
    """
    Envoie un message de rétention personnalisé à un assuré à risque de résiliation.
    """
    contenu = (
        f"Bonjour {nom_assure},\n\n"
        f"{message_commercial}\n\n"
        f"Contrat : {numero_police}\n"
        f"Pour toute question : contactez votre gestionnaire.\n\n"
        f"— Votre compagnie d'assurance"
    )
    return await envoyer_whatsapp(
        destinataire=telephone,
        contenu=contenu,
        metadata={"type": "churn_retention", "police": numero_police},
    )


async def envoyer_confirmation_sinistre(
    telephone: str,
    nom_assure: str,
    numero_sinistre: str,
    delai_jours: int,
) -> bool:
    """
    Envoie l'accusé de réception d'un sinistre au déclarant.
    """
    contenu = (
        f"Bonjour {nom_assure},\n\n"
        f"Votre sinistre N° {numero_sinistre} a bien été enregistré.\n"
        f"Délai de traitement réglementaire : {delai_jours} jours ouvrables.\n"
        f"Votre gestionnaire vous contactera sous 48h.\n\n"
        f"— Votre compagnie d'assurance"
    )
    return await envoyer_whatsapp(
        destinataire=telephone,
        contenu=contenu,
        metadata={"type": "confirmation_sinistre", "sinistre": numero_sinistre},
    )


async def envoyer_rappel_echeance(
    telephone: str,
    nom_assure: str,
    numero_police: str,
    date_echeance: str,
    prime_ttc: float,
) -> bool:
    """
    Rappel d'échéance de prime envoyé automatiquement.
    """
    contenu = (
        f"Bonjour {nom_assure},\n\n"
        f"Rappel : votre contrat {numero_police} arrive à échéance le {date_echeance}.\n"
        f"Prime à renouveler : {prime_ttc:,.0f} FCFA.\n"
        f"Contactez votre courtier ou réglez en ligne pour maintenir vos garanties.\n\n"
        f"— Votre compagnie d'assurance"
    )
    return await envoyer_whatsapp(
        destinataire=telephone,
        contenu=contenu,
        metadata={"type": "rappel_echeance", "police": numero_police},
    )


class _NotificationService:
    """
    Service de notifications unifié pour les agents.
    Centralise l'envoi multi-canal : WhatsApp, SMS, email.
    """

    async def envoyer(self, canal: str, destinataire: str, message: str) -> bool:
        """Envoie une notification sur le canal spécifié."""
        if not destinataire:
            logger.warning(f"[Notif] Destinataire vide — notification ignorée")
            return False
        if canal == "whatsapp":
            return await envoyer_whatsapp(destinataire, message)
        elif canal == "sms":
            return await _envoyer_sms(destinataire, message)
        elif canal == "email":
            return await _envoyer_email(destinataire, message)
        else:
            logger.warning(f"[Notif] Canal inconnu : {canal}")
            return False

    async def envoyer_alerte_direction(
        self,
        niveau: str,      # "info" | "avertissement" | "critique"
        message: str,
        article: str = "",
    ) -> bool:
        """
        Envoie une alerte à la direction générale.
        Utilisé par les agents pour les non-conformités CIMA et risques critiques.
        """
        from config.settings import settings
        # Numéro DG depuis settings (fallback simulation)
        tel_dg = getattr(settings, "TELEPHONE_DG", None) or getattr(settings, "DG_PHONE", None)
        email_dg = getattr(settings, "EMAIL_DG", None) or getattr(settings, "DG_EMAIL", None)

        icone = {"info": "ℹ️", "avertissement": "⚠️", "critique": "🚨"}.get(niveau, "📢")
        contenu = (
            f"{icone} ALERTE {niveau.upper()} — YukpoAssurance\n\n"
            f"{message}"
        )
        if article:
            contenu += f"\n\nRéférence : {article}"

        envoye = False
        if tel_dg:
            envoye = await envoyer_whatsapp(tel_dg, contenu)
        elif email_dg:
            envoye = await _envoyer_email(email_dg, contenu)
        else:
            # Simulation si pas de config
            logger.warning(f"[Notif/DG] Alerte direction simulée ({niveau}) : {message[:80]}")
            envoye = True

        logger.info(f"[Notif] Alerte direction {niveau} envoyée : {message[:80]}")
        return envoye


async def _envoyer_sms(destinataire: str, contenu: str) -> bool:
    """Envoi SMS via Twilio.

    Préfère `TWILIO_MESSAGING_SERVICE_SID` si défini (gère plusieurs
    senders + auto-failover + sender ID alphanumérique sur Afrique
    francophone). Sinon utilise `TWILIO_SMS_NUMBER` (numéro unique).
    Si aucun n'est défini → simulation log.
    """
    from config.settings import settings
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        logger.info(f"[Notif/SIM] SMS → {destinataire}: {contenu[:60]}...")
        return True

    messaging_sid = getattr(settings, "TWILIO_MESSAGING_SERVICE_SID", None) or ""
    sms_from = getattr(settings, "TWILIO_SMS_NUMBER", None) or ""

    if not messaging_sid and not sms_from:
        logger.info(f"[Notif/SIM] SMS (no sender configuré) → {destinataire}: {contenu[:60]}...")
        return True

    try:
        from twilio.rest import Client
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        if messaging_sid:
            msg = client.messages.create(
                body=contenu,
                messaging_service_sid=messaging_sid,
                to=destinataire,
            )
        else:
            msg = client.messages.create(
                body=contenu, from_=sms_from, to=destinataire,
            )
        logger.info(f"[Notif] SMS envoyé SID={msg.sid} → {destinataire}")
        return True
    except Exception as e:
        logger.error(f"[Notif] Échec SMS → {destinataire}: {e}")
        return False


async def notifier_telephone(
    destinataire: str,
    contenu: str,
    *,
    metadata: Optional[dict] = None,
    prefer: str = "whatsapp",
) -> dict:
    """Envoi téléphone intelligent : WhatsApp d'abord, fallback SMS auto.

    Stratégie contexte africain : WA est gratuit/data-light pour le
    destinataire, mais peut échouer si le numéro n'a pas WhatsApp ou si
    on est hors fenêtre 24h Business sans template approved. Le SMS
    fallback couvre tous les feature phones et numéros sans WA.

    Args:
        destinataire : numéro E.164 (ex. "+237 6 12 34 56 78") ou
                       déjà préfixé "whatsapp:".
        contenu      : texte (max 1600 chars utile, sera split SMS si plus
                       long). Pas de HTML.
        prefer       : "whatsapp" (défaut) | "sms" | "both".

    Returns:
        dict {wa_ok, sms_ok, canal_final} — canal_final = "whatsapp" si
        WA OK, sinon "sms" si SMS OK, sinon "none".
    """
    metadata = metadata or {}
    # Normalisation : strip espaces, accepter format avec/sans "whatsapp:"
    num_brut = destinataire.replace("whatsapp:", "").strip()
    if not num_brut:
        return {"wa_ok": False, "sms_ok": False, "canal_final": "none"}

    wa_ok = False
    sms_ok = False

    if prefer in ("whatsapp", "both"):
        try:
            wa_ok = await envoyer_whatsapp(num_brut, contenu, metadata=metadata)
        except Exception as e:
            logger.warning(f"[Notif] WA exception → {num_brut}: {e}")
            wa_ok = False

    # SMS si WA a échoué OU si on veut both/sms-only
    if not wa_ok and prefer != "whatsapp" or prefer == "both":
        try:
            sms_ok = await _envoyer_sms(num_brut, contenu)
        except Exception as e:
            logger.warning(f"[Notif] SMS exception → {num_brut}: {e}")
            sms_ok = False
    elif not wa_ok and prefer == "whatsapp":
        # Fallback auto SMS si WA a échoué (pas de message livré au user)
        try:
            sms_ok = await _envoyer_sms(num_brut, contenu)
        except Exception as e:
            logger.warning(f"[Notif] SMS fallback exception → {num_brut}: {e}")
            sms_ok = False

    canal_final = (
        "whatsapp" if wa_ok
        else ("sms" if sms_ok else "none")
    )
    return {"wa_ok": wa_ok, "sms_ok": sms_ok, "canal_final": canal_final}


async def _envoyer_email(
    destinataire: str,
    contenu: str,
    sujet: str = "Notification YukpoPro",
    contenu_html: Optional[str] = None,
) -> bool:
    """Envoi email via SendGrid si configuré, sinon log simulé.

    `contenu` est utilisé comme plain-text. Si `contenu_html` est fourni
    OU si `contenu` ressemble à du HTML (<...>), envoi en text/html.
    """
    if not settings.SENDGRID_API_KEY:
        logger.info(f"[Notif/SIM] Email → {destinataire} | {sujet} | {contenu[:60]}...")
        return True

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail, From

        looks_html = bool(contenu_html) or contenu.lstrip().startswith("<")
        from_email = From(
            settings.SENDGRID_FROM_EMAIL or "no-reply@yukpomnang.com",
            settings.SENDGRID_FROM_NAME or "YukpoPro",
        )
        mail = Mail(
            from_email=from_email,
            to_emails=destinataire,
            subject=sujet,
            html_content=(contenu_html or contenu) if looks_html else None,
            plain_text_content=contenu if not looks_html else None,
        )
        client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        rep = client.send(mail)
        if rep.status_code >= 300:
            logger.warning(f"[Notif] SendGrid {rep.status_code} → {destinataire}")
            return False
        logger.info(f"[Notif] Email SendGrid envoyé → {destinataire} | {sujet}")
        return True
    except Exception as e:
        logger.error(f"[Notif] SendGrid échec → {destinataire}: {e}")
        return False


# Singleton service notifications
notifications = _NotificationService()


def messages_en_echec() -> list[dict]:
    """Retourne les messages qui n'ont pas pu être envoyés."""
    return list(_failed)


async def retraiter_echecs() -> dict:
    """Tente de renvoyer tous les messages en échec."""
    if not _failed:
        return {"retraites": 0, "succes": 0, "echecs": 0}

    a_retraiter = list(_failed)
    _failed.clear()
    succes = 0
    echecs = 0

    for msg in a_retraiter:
        ok = await envoyer_whatsapp(msg["destinataire"], msg["contenu"], msg.get("metadata"))
        if ok:
            succes += 1
        else:
            echecs += 1

    return {"retraites": len(a_retraiter), "succes": succes, "echecs": echecs}
