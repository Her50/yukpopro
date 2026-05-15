"""Web Push notifications (VAPID) pour marchands YukpoShop.

Déclenché sur :
  • new_order  : nouvelle commande sur storefront
  • new_message: visiteur envoie un message
  • new_comment: nouvel avis à modérer

Dépend de la lib `pywebpush` (best-effort : si non installée, no-op silencieux).
Clés VAPID via env :
  VAPID_PUBLIC_KEY  : exposée au navigateur pour subscribe
  VAPID_PRIVATE_KEY : utilisée pour signer les envois
  VAPID_CONTACT     : mailto: ou URL (recommandation IETF)

Facturation : chaque notif push réussie débite `whatsapp_message` (mapping
sémantique sur le forfait existant, marge ×20 incluse — équivalent
notification temps réel).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import ShopPushSubscriptionDB

logger = logging.getLogger("yukpo_assurance.pro.shop_webpush")


def get_vapid_public_key() -> Optional[str]:
    return os.getenv("VAPID_PUBLIC_KEY") or None


def _get_vapid_private_key() -> Optional[str]:
    return os.getenv("VAPID_PRIVATE_KEY") or None


def _get_vapid_contact() -> str:
    return os.getenv("VAPID_CONTACT", "mailto:contact@yukpomnang.com")


async def envoyer_push_user(
    db: AsyncSession,
    user_id: int,
    title: str,
    body: str,
    url: Optional[str] = None,
    icon: Optional[str] = None,
    tag: Optional[str] = None,
) -> int:
    """Envoie un push à toutes les subscriptions d'un user. Retourne le nombre
    de notifs envoyées avec succès. Best-effort : silencieux sur échec."""
    private = _get_vapid_private_key()
    if not private:
        return 0
    try:
        from pywebpush import webpush, WebPushException  # type: ignore
    except ImportError:
        logger.info("[WebPush] pywebpush non installé — push désactivé")
        return 0

    subs = (await db.execute(
        select(ShopPushSubscriptionDB).where(ShopPushSubscriptionDB.user_id == user_id)
    )).scalars().all()
    if not subs:
        return 0

    payload = json.dumps({
        "title": title, "body": body, "url": url or "/",
        "icon": icon, "tag": tag or "yukposhop",
        "timestamp": datetime.utcnow().isoformat(),
    })
    sent = 0
    stale: list[int] = []
    for s in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": s.endpoint,
                    "keys": {"p256dh": s.p256dh, "auth": s.auth},
                },
                data=payload,
                vapid_private_key=private,
                vapid_claims={"sub": _get_vapid_contact()},
                ttl=86400,
            )
            s.derniere_utilisation = datetime.utcnow()
            sent += 1
        except WebPushException as e:
            code = getattr(e.response, "status_code", None)
            if code in (404, 410):  # subscription expirée
                stale.append(s.id)
            else:
                logger.warning(f"[WebPush] erreur envoi sub={s.id} code={code} : {e}")
        except Exception as e:
            logger.warning(f"[WebPush] erreur inattendue sub={s.id} : {e}")

    # Cleanup subs expirées
    if stale:
        for sid in stale:
            sub = (await db.execute(
                select(ShopPushSubscriptionDB).where(ShopPushSubscriptionDB.id == sid)
            )).scalar_one_or_none()
            if sub:
                await db.delete(sub)

    if sent or stale:
        await db.commit()

    # Facturation : 1 débit par utilisateur destinataire (pas par sub)
    if sent:
        try:
            from modules.bureau.service_credits_bureau import debiter_forfait_unifie
            await debiter_forfait_unifie(
                user_id, "whatsapp_message", module="shop_webpush",
            )
        except Exception:
            pass

    return sent
