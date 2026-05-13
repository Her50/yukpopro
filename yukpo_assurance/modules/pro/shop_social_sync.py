"""Phase D6 — Connexion sociale (Meta Catalog Sync, FB/IG posts, WA Business).

Synchronise les produits YukpoShop vers :
  • Facebook Shops + Instagram Shopping (via Meta Commerce Catalog API)
  • Posts Facebook auto-générés à chaque nouveau produit
  • Stories Insta auto (SVG Recraft)
  • WhatsApp Business : webhook réception messages → arrive dans le chat
    YukpoPro du marchand (intégration future)

OAuth flow simplifié — le user fait le consentement Meta Business → callback
backend récupère l'access_token longue durée → stocké chiffré côté DB.

NOTE : Meta Graph API exige une App Review pour la production (catalogue,
catalog_management permission). Pour MVP : mode DEV testable avec tes
propres Pages Meta uniquement.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger("yukpo_assurance.pro.shop_social_sync")


# Meta Graph API v18+ — versions à mettre à jour annuellement
_META_GRAPH_BASE = "https://graph.facebook.com/v19.0"


# ─── Catalog Sync (FB Shops + IG Shopping) ───────────────────────────────────

async def sync_produits_vers_meta_catalog(
    catalog_id: str, access_token: str, produits: list[dict],
    *, store_url_base: str,
) -> dict:
    """Synchronise N produits Yukpo vers un Meta Commerce Catalog.

    Batch API : 50 produits par appel pour limiter le throttling Meta.
    Le format `requests` Meta accepte create/update/delete sur le même payload.

    Args:
        catalog_id   : ID du catalogue Meta Commerce (créé par le marchand)
        access_token : System User Token avec catalog_management permission
        produits     : list de dicts ShopProductDB-like (id, titre, prix, photos, slug…)
        store_url_base : URL publique du storefront ex. https://maboutique.yukpomnang.com

    Returns: {nb_sync_ok, nb_sync_erreur, response_meta}
    """
    if not produits:
        return {"nb_sync_ok": 0, "nb_sync_erreur": 0, "response_meta": None}

    requests_list = []
    for p in produits[:50]:
        photos = p.get("photos_urls_json") or []
        photo_url = photos[0] if isinstance(photos, list) and photos else ""
        requests_list.append({
            "method": "CREATE" if p.get("source") != "_synced_meta" else "UPDATE",
            "retailer_id": f"yukpo-{p.get('id')}",  # ID stable côté Meta
            "data": {
                "availability": "in stock" if (p.get("stock") or 0) > 0 else "out of stock",
                "brand": p.get("nom_marque") or "Yukpo",
                "category": p.get("categorie_meta") or "Apparel & Accessories",
                "description": (p.get("description_courte") or "")[:5000],
                "image_link": photo_url,
                "additional_image_link": photos[1:10] if len(photos) > 1 else None,
                "name": p.get("titre", "Produit")[:200],
                "price": f"{int((p.get('prix_unit_promo') or p.get('prix_unit') or 0) * 100)} {p.get('devise', 'XAF')}",
                "condition": "new",
                "url": f"{store_url_base.rstrip('/')}/p/{p.get('slug')}",
                "retailer_id": f"yukpo-{p.get('id')}",
            },
        })

    url = f"{_META_GRAPH_BASE}/{catalog_id}/items_batch"
    payload = {
        "access_token": access_token,
        "item_type": "PRODUCT_ITEM",
        "requests": requests_list,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            rep = await client.post(url, json=payload)
            data = rep.json()
            if rep.status_code >= 300:
                logger.warning(f"[Meta/catalog] erreur {rep.status_code}: {data}")
                return {
                    "nb_sync_ok": 0,
                    "nb_sync_erreur": len(requests_list),
                    "response_meta": data,
                }
            return {
                "nb_sync_ok": len(requests_list),
                "nb_sync_erreur": 0,
                "response_meta": data,
            }
        except Exception as e:
            logger.error(f"[Meta/catalog] exception : {e}")
            return {
                "nb_sync_ok": 0, "nb_sync_erreur": len(requests_list),
                "response_meta": {"error": str(e)},
            }


# ─── Posts Facebook auto-générés ─────────────────────────────────────────────

async def publier_post_facebook(
    page_id: str, page_access_token: str,
    *, message: str, lien_produit: Optional[str] = None,
    image_url: Optional[str] = None,
) -> dict:
    """Publie un post sur la page Facebook du marchand."""
    url = f"{_META_GRAPH_BASE}/{page_id}/feed"
    if image_url:
        url = f"{_META_GRAPH_BASE}/{page_id}/photos"
    payload: dict = {
        "access_token": page_access_token,
        "message": message[:5000],
    }
    if image_url:
        payload["url"] = image_url
    if lien_produit:
        payload["link"] = lien_produit
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            rep = await client.post(url, data=payload)
            data = rep.json()
            if rep.status_code >= 300:
                return {"ok": False, "error": data}
            return {"ok": True, "post_id": data.get("id") or data.get("post_id"),
                    "data": data}
        except Exception as e:
            return {"ok": False, "error": str(e)}


async def composer_message_post_produit(produit: dict, boutique: dict) -> str:
    """LLM Sonnet/GPT-5-mini compose un post FB engageant pour un produit."""
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire

    prompt = (
        f"Compose un post Facebook engageant (200-400 chars, max 3 émojis, "
        f"1-2 hashtags) pour annoncer ce produit :\n"
        f"Boutique : {boutique.get('nom')}\n"
        f"Produit : {produit.get('titre')}\n"
        f"Description : {(produit.get('description_courte') or '')[:300]}\n"
        f"Prix : {int(produit.get('prix_unit') or 0)} {produit.get('devise', 'XAF')}\n"
        f"Ville cible : {boutique.get('pays_principal', 'CM')}\n\n"
        f"Ton : commercial chaleureux Afrique francophone. "
        f"Pas d'enrobage IA, pas de markdown. Juste le texte du post."
    )
    rep = await ia_client.appeler(
        prompt=prompt,
        mode=ModeIA.COMMERCIAL,
        max_tokens_override=600,
        forcer_modele=ModelePrioritaire.CLAUDE_SONNET,
    )
    return (rep.contenu or "").strip()


# ─── OAuth flow simplifié Meta ───────────────────────────────────────────────

def url_oauth_meta(redirect_uri: str, app_id: str, state: str) -> str:
    """Construit l'URL d'autorisation Meta pour démarrer le flow OAuth."""
    scopes = ",".join([
        "pages_show_list", "pages_read_engagement", "pages_manage_posts",
        "catalog_management", "instagram_basic", "instagram_content_publish",
        "business_management",
    ])
    return (
        f"https://www.facebook.com/v19.0/dialog/oauth?"
        f"client_id={app_id}&redirect_uri={redirect_uri}&"
        f"state={state}&scope={scopes}&response_type=code"
    )


async def echanger_code_pour_token(
    code: str, redirect_uri: str, app_id: str, app_secret: str,
) -> dict:
    """OAuth code → short-lived token → long-lived token (60j)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Code → short-lived token
        r1 = await client.get(
            f"{_META_GRAPH_BASE}/oauth/access_token",
            params={
                "client_id": app_id, "client_secret": app_secret,
                "redirect_uri": redirect_uri, "code": code,
            },
        )
        if r1.status_code >= 300:
            raise Exception(f"Meta OAuth code échec : {r1.text}")
        short_token = r1.json().get("access_token")
        # 2. Short → Long-lived (60 jours)
        r2 = await client.get(
            f"{_META_GRAPH_BASE}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": app_id, "client_secret": app_secret,
                "fb_exchange_token": short_token,
            },
        )
        if r2.status_code >= 300:
            raise Exception(f"Meta long-lived échec : {r2.text}")
        data = r2.json()
        return {
            "access_token": data.get("access_token"),
            "expires_in_seconds": data.get("expires_in", 60 * 86400),
        }


async def lister_pages_user(access_token: str) -> list[dict]:
    """Liste les pages FB que le user gère (pour choisir laquelle connecter)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(
            f"{_META_GRAPH_BASE}/me/accounts",
            params={"access_token": access_token,
                     "fields": "id,name,access_token,instagram_business_account,category"},
        )
        if r.status_code >= 300:
            return []
        return r.json().get("data", [])
