"""
Publisher Meta — Facebook & Instagram Graph API
Portage de facebook_publisher_service.rs + instagram_publisher_service.rs de yukpomnang2.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger("yukpo.cm.publisher")

GRAPH_BASE = "https://graph.facebook.com"


# ─────────────────────────────────────────────────────────────
# Facebook Publisher
# ─────────────────────────────────────────────────────────────

async def publier_facebook(
    page_token: str,
    page_id: str,
    caption: str,
    image_url: Optional[str] = None,
    lien_url: Optional[str] = None,
    api_version: str = "v19.0",
) -> str:
    """
    Publie un post sur une Page Facebook.
    Retourne l'ID du post créé (ex: '12345678_98765432').
    Portage de post_product_to_page() de yukpomnang2.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        if image_url:
            # Publier avec image (photo post)
            url = f"{GRAPH_BASE}/{api_version}/{page_id}/photos"
            payload = {
                "url": image_url,
                "caption": caption,
                "access_token": page_token,
            }
            resp = await client.post(url, json=payload)
        elif lien_url:
            # Publier avec lien
            url = f"{GRAPH_BASE}/{api_version}/{page_id}/feed"
            payload = {
                "message": caption,
                "link": lien_url,
                "access_token": page_token,
            }
            resp = await client.post(url, json=payload)
        else:
            # Post texte simple
            url = f"{GRAPH_BASE}/{api_version}/{page_id}/feed"
            payload = {
                "message": caption,
                "access_token": page_token,
            }
            resp = await client.post(url, json=payload)

        if resp.status_code != 200:
            error = resp.json().get("error", {})
            raise ValueError(
                f"Facebook API erreur {resp.status_code}: "
                f"{error.get('message', resp.text)}"
            )
        data = resp.json()
        return data.get("id") or data.get("post_id", "")


async def recuperer_insights_facebook(
    page_token: str,
    post_id: str,
    api_version: str = "v19.0",
) -> dict:
    """Récupère les insights d'un post Facebook (impressions, reach, engagement)."""
    metrics = "post_impressions,post_reach,post_engaged_users,post_clicks"
    url = f"{GRAPH_BASE}/{api_version}/{post_id}/insights?metric={metrics}&access_token={page_token}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        result = {}
        for item in data.get("data", []):
            name = item.get("name", "")
            value = item.get("values", [{}])[-1].get("value", 0)
            result[name] = value
        return result


# ─────────────────────────────────────────────────────────────
# Instagram Publisher
# ─────────────────────────────────────────────────────────────

async def get_ig_business_account_id(
    page_token: str,
    page_id: str,
    api_version: str = "v19.0",
) -> Optional[str]:
    """
    Récupère l'ID du compte Instagram Business lié à une Page Facebook.
    Portage de get_ig_business_account_id() de yukpomnang2.
    """
    url = (
        f"{GRAPH_BASE}/{api_version}/{page_id}"
        f"?fields=instagram_business_account&access_token={page_token}"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            return None
        data = resp.json()
        ig = data.get("instagram_business_account")
        return ig.get("id") if ig else None


async def publier_instagram(
    ig_user_id: str,
    page_token: str,
    image_url: str,
    caption: str,
    api_version: str = "v19.0",
) -> str:
    """
    Publie une image sur Instagram Business via l'API Graph (2 étapes).
    Portage de publish_product_image() de yukpomnang2.
    Étape 1 : Créer le container de média
    Étape 2 : Publier le container
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Étape 1 : création du container média
        url_container = f"{GRAPH_BASE}/{api_version}/{ig_user_id}/media"
        payload_container = {
            "image_url": image_url,
            "caption": caption,
            "access_token": page_token,
        }
        resp1 = await client.post(url_container, json=payload_container)
        if resp1.status_code != 200:
            error = resp1.json().get("error", {})
            raise ValueError(
                f"Instagram container erreur {resp1.status_code}: "
                f"{error.get('message', resp1.text)}"
            )
        container_id = resp1.json().get("id")
        if not container_id:
            raise ValueError("Instagram: container_id manquant dans la réponse")

        # Étape 2 : publier le container
        url_publish = f"{GRAPH_BASE}/{api_version}/{ig_user_id}/media_publish"
        payload_publish = {
            "creation_id": container_id,
            "access_token": page_token,
        }
        resp2 = await client.post(url_publish, json=payload_publish)
        if resp2.status_code != 200:
            error = resp2.json().get("error", {})
            raise ValueError(
                f"Instagram publish erreur {resp2.status_code}: "
                f"{error.get('message', resp2.text)}"
            )
        return resp2.json().get("id", "")


async def recuperer_insights_instagram(
    ig_user_id: str,
    media_id: str,
    page_token: str,
    api_version: str = "v19.0",
) -> dict:
    """Récupère les insights d'un post Instagram."""
    metrics = "impressions,reach,likes,comments,shares,saved,profile_visits"
    url = (
        f"{GRAPH_BASE}/{api_version}/{media_id}/insights"
        f"?metric={metrics}&access_token={page_token}"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        return {item["name"]: item.get("values", [{}])[-1].get("value", item.get("value", 0))
                for item in data.get("data", [])}


# ─────────────────────────────────────────────────────────────
# Helper : récupérer les tokens depuis la DB compagnie
# ─────────────────────────────────────────────────────────────

async def charger_config_meta(
    db,
    compagnie_id: int,
    plateforme: str = "facebook",
) -> dict:
    """
    Charge la configuration Meta (tokens, page_id) depuis la table SocialConnectorDB.
    Retourne un dict avec : page_token, page_id, ig_user_id.
    """
    from sqlalchemy import select
    from core.database import SocialConnectorDB

    result = await db.execute(
        select(SocialConnectorDB).where(
            SocialConnectorDB.compagnie_id == compagnie_id,
            SocialConnectorDB.plateforme == plateforme,
            SocialConnectorDB.est_actif == True,
        )
    )
    connector = result.scalar_one_or_none()
    if not connector:
        raise ValueError(f"Aucun compte {plateforme} connecté pour cette compagnie")

    metadata = connector.metadata_json or {}
    return {
        "page_token": metadata.get("page_access_token", ""),
        "page_id": metadata.get("page_id", connector.account_id or ""),
        "ig_user_id": metadata.get("ig_user_id", ""),
        "api_version": "v19.0",
    }
