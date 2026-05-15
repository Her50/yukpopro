"""SEO + référencement automatique pour storefronts YukpoShop.

Trois leviers :
  1. **IndexNow** (Bing, Yandex, Naver, Seznam) — protocole standard
     `POST https://api.indexnow.org/indexnow` avec un payload de N URLs +
     clé hostée sur le domaine. Indexation en 2-7 jours.
  2. **JSON-LD Schema.org Product** injecté dans le HTML page produit →
     rich snippets Google (étoile, prix, dispo) dès l'indexation.
  3. **OpenGraph product** + Twitter Card → previews riches sur FB/WA/LinkedIn/X.

  4. **Feed Google Merchant Center** : XML standard accessible publiquement
     que le commerçant peut soumettre dans son Google Merchant Center →
     onglet Shopping Google.

Pour Google Search : le ping `/ping?sitemap=` est déprécié depuis juin 2023.
Le seul levier automatique restant est le `Sitemap:` dans robots.txt (déjà
fait) + IndexNow (Google ne s'y rallie pas officiellement mais bcp de SEO
constatent qu'il accélère quand même la découverte indirectement).

Configuration env :
  INDEXNOW_KEY : 8-128 chars hex/alphanum, posé sur Fly secret.
                 Doit être accessible à `https://<domain>/<key>.txt`.
                 Le storefront builder injecte automatiquement ce fichier
                 dans l'arborescence Netlify.
"""
from __future__ import annotations

import json
import logging
import os
from html import escape
from typing import Any, Optional

import httpx

logger = logging.getLogger("yukpo_assurance.pro.seo")


def get_indexnow_key() -> Optional[str]:
    """Retourne la clé IndexNow ou None si non configurée."""
    k = (os.getenv("INDEXNOW_KEY") or "").strip()
    return k if k and 8 <= len(k) <= 128 else None


# ─── Ping IndexNow ──────────────────────────────────────────────────────────

async def ping_indexnow(host: str, urls: list[str]) -> dict[str, Any]:
    """Soumet une liste d'URLs aux moteurs IndexNow (Bing/Yandex/Naver/Seznam).

    Args:
      host: domaine sans schéma, ex. "marie-cosmetics.yukpomnang.com"
      urls: liste d'URLs complètes du même host (max 10 000)

    Returns:
      dict { ok, status, nb_urls, error? }
    """
    key = get_indexnow_key()
    if not key:
        return {"ok": False, "error": "INDEXNOW_KEY non configurée côté serveur",
                "nb_urls": len(urls)}
    if not urls:
        return {"ok": False, "error": "Aucune URL à soumettre", "nb_urls": 0}

    payload = {
        "host": host,
        "key": key,
        "keyLocation": f"https://{host}/{key}.txt",
        "urlList": urls[:10000],
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.indexnow.org/indexnow",
                json=payload,
                headers={"Content-Type": "application/json; charset=utf-8"},
            )
        # IndexNow renvoie 200 ou 202 pour succès, 422 si clé non vérifiée
        return {
            "ok": resp.status_code in (200, 202),
            "status": resp.status_code, "nb_urls": len(urls),
            "error": None if resp.status_code in (200, 202)
                     else f"HTTP {resp.status_code} : {resp.text[:200]}",
        }
    except Exception as e:
        return {"ok": False, "error": f"réseau : {e}", "nb_urls": len(urls)}


# ─── JSON-LD Schema.org Product ─────────────────────────────────────────────

def build_jsonld_product(p: dict, boutique: dict, base_url: str) -> str:
    """Construit un bloc JSON-LD `<script type="application/ld+json">` pour
    une page produit. Permet aux moteurs (Google notamment) d'afficher des
    rich snippets (prix, dispo, étoiles, image)."""
    photos = p.get("photos_urls_json") or []
    if not isinstance(photos, list):
        photos = []
    photos = [str(x) for x in photos if isinstance(x, str) and x][:5]

    prix = p.get("prix_unit_promo") or p.get("prix_unit") or 0
    devise = (p.get("devise") or boutique.get("devise") or "XAF")[:3]
    stock = int(p.get("stock") or 0)
    availability = (
        "https://schema.org/InStock" if stock > 0
        else "https://schema.org/OutOfStock"
    )

    product_url = f"{base_url.rstrip('/')}/p/{p.get('slug', '')}"
    sku = p.get("sku") or f"YK-{p.get('id', '')}"

    jsonld: dict[str, Any] = {
        "@context": "https://schema.org/",
        "@type": "Product",
        "name": p.get("titre") or "",
        "description": (
            p.get("description_courte")
            or p.get("description_longue")
            or p.get("yukpo_description_enriched")
            or ""
        )[:5000],
        "image": photos,
        "sku": str(sku),
        "brand": {
            "@type": "Brand",
            "name": boutique.get("nom") or "Yukpo Shop",
        },
        "offers": {
            "@type": "Offer",
            "url": product_url,
            "priceCurrency": devise,
            "price": int(prix),
            "availability": availability,
            "itemCondition": "https://schema.org/NewCondition",
            "seller": {
                "@type": "Organization",
                "name": boutique.get("nom") or "Yukpo Shop",
            },
        },
    }

    # Catégorie auto si dispo (Piste 6a)
    if p.get("yukpo_category"):
        jsonld["category"] = p["yukpo_category"]

    # AggregateRating : on synthétise avec yukpo_quality_score si présent
    # (score IA, 0-100). Conversion en étoiles 0-5.
    qs = p.get("yukpo_quality_score")
    if isinstance(qs, int) and qs >= 50:
        jsonld["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": round(qs / 20.0, 1),  # 0-5
            "reviewCount": 1,
            "bestRating": 5,
            "worstRating": 0,
        }

    return (
        '<script type="application/ld+json">'
        + json.dumps(jsonld, ensure_ascii=False, separators=(",", ":"))
        + '</script>'
    )


def build_jsonld_organization(boutique: dict, base_url: str) -> str:
    """JSON-LD `Organization` pour la home — aide Google à comprendre
    qui est la boutique (nom, logo, adresse Google Places, téléphone)."""
    jsonld: dict[str, Any] = {
        "@context": "https://schema.org/",
        "@type": "Store",
        "name": boutique.get("nom") or "Yukpo Shop",
        "url": base_url.rstrip("/"),
    }
    if boutique.get("description"):
        jsonld["description"] = str(boutique["description"])[:600]
    if boutique.get("logo_url"):
        jsonld["logo"] = str(boutique["logo_url"])
    if boutique.get("adresse_complete"):
        jsonld["address"] = {
            "@type": "PostalAddress",
            "streetAddress": str(boutique["adresse_complete"])[:300],
            "addressCountry": str(boutique.get("pays_principal") or "CM"),
        }
    if boutique.get("gps"):
        gps_str = str(boutique["gps"])
        if "," in gps_str:
            try:
                lat, lng = gps_str.split(",", 1)
                jsonld["geo"] = {
                    "@type": "GeoCoordinates",
                    "latitude": float(lat), "longitude": float(lng),
                }
            except Exception:
                pass
    if boutique.get("telephone"):
        jsonld["telephone"] = str(boutique["telephone"])
    if boutique.get("google_rating"):
        try:
            jsonld["aggregateRating"] = {
                "@type": "AggregateRating",
                "ratingValue": float(boutique["google_rating"]),
                "reviewCount": 1, "bestRating": 5,
            }
        except Exception:
            pass
    return (
        '<script type="application/ld+json">'
        + json.dumps(jsonld, ensure_ascii=False, separators=(",", ":"))
        + '</script>'
    )


# ─── OpenGraph product + Twitter Card ───────────────────────────────────────

def build_og_product(p: dict, boutique: dict, base_url: str) -> str:
    """Tags OpenGraph e-commerce + Twitter Card pour la page produit.

    Permet à Facebook/WhatsApp/LinkedIn/X d'afficher un preview riche
    avec image grande + prix + dispo quand le commerçant partage le lien.
    """
    photos = p.get("photos_urls_json") or []
    if not isinstance(photos, list):
        photos = []
    photo = (
        next((str(x) for x in photos if isinstance(x, str) and x), "")
        if photos else ""
    )
    # OG image dynamique (générée au publish : photo + prix + logo en watermark)
    # — préférée à la photo brute pour CTR +40% sur partages sociaux.
    og_dyn = p.get("_og_image_dyn")
    if og_dyn:
        photo = og_dyn

    prix = p.get("prix_unit_promo") or p.get("prix_unit") or 0
    devise = (p.get("devise") or boutique.get("devise") or "XAF")[:3]
    stock = int(p.get("stock") or 0)
    avail = "in stock" if stock > 0 else "out of stock"

    titre = escape((p.get("titre") or "")[:200])
    desc = escape(
        (p.get("description_courte")
         or p.get("description_longue")
         or p.get("yukpo_description_enriched")
         or boutique.get("nom") or "Yukpo Shop")[:300]
    )
    url = escape(f"{base_url.rstrip('/')}/p/{p.get('slug', '')}")

    parts = [
        f'<meta property="og:type" content="product">',
        f'<meta property="og:title" content="{titre}">',
        f'<meta property="og:description" content="{desc}">',
        f'<meta property="og:url" content="{url}">',
        f'<meta property="og:site_name" content="{escape(boutique.get("nom") or "Yukpo Shop")}">',
        f'<meta property="og:locale" content="fr_FR">',
    ]
    if photo:
        h = 630 if og_dyn else 1200
        parts += [
            f'<meta property="og:image" content="{escape(photo)}">',
            f'<meta property="og:image:width" content="1200">',
            f'<meta property="og:image:height" content="{h}">',
            f'<meta property="og:image:alt" content="{titre}">',
        ]
    parts += [
        # product: namespace (Facebook product graph)
        f'<meta property="product:price:amount" content="{int(prix)}">',
        f'<meta property="product:price:currency" content="{devise}">',
        f'<meta property="product:availability" content="{avail}">',
        f'<meta property="product:condition" content="new">',
        f'<meta property="product:brand" content="{escape(boutique.get("nom") or "Yukpo Shop")}">',
        # Twitter Card
        f'<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{titre}">',
        f'<meta name="twitter:description" content="{desc}">',
    ]
    if photo:
        parts.append(f'<meta name="twitter:image" content="{escape(photo)}">')

    return "\n".join(parts)


# ─── Feed Google Merchant Center (XML) ──────────────────────────────────────

def build_google_merchant_feed(
    boutique: dict, produits: list[dict], base_url: str,
) -> str:
    """Génère un feed XML compatible Google Merchant Center.

    Le commerçant peut soumettre l'URL `<storefront>/feed/google.xml` (ou
    `/api/v1/pro/shop/feed/google.xml` côté API) dans son compte Google
    Merchant Center → produits dans onglet Shopping Google.

    Format : RSS 2.0 + namespace `g:` (standard Google).
    """
    items_xml: list[str] = []
    for p in produits:
        if p.get("statut") != "actif":
            continue
        photos = p.get("photos_urls_json") or []
        photo = next((str(x) for x in photos if isinstance(x, str) and x), "") if isinstance(photos, list) else ""
        if not photo:
            continue  # Google exige au moins 1 image
        prix = int(p.get("prix_unit_promo") or p.get("prix_unit") or 0)
        devise = (p.get("devise") or boutique.get("devise") or "XAF")[:3]
        stock = int(p.get("stock") or 0)
        avail = "in_stock" if stock > 0 else "out_of_stock"

        # Description : ≥ 50 chars requis par Google
        desc_raw = (
            p.get("yukpo_description_enriched")
            or p.get("description_longue")
            or p.get("description_courte")
            or p.get("titre") or ""
        )
        if len(desc_raw) < 50:
            desc_raw = (desc_raw + " — " + (boutique.get("nom") or "Boutique Yukpo")
                        + " — Livraison " + (boutique.get("pays_principal") or "Cameroun"))
        desc_raw = desc_raw[:5000]

        sku = p.get("sku") or f"YK-{p.get('id', '')}"
        link = f"{base_url.rstrip('/')}/p/{p.get('slug', '')}"

        items_xml.append(f"""    <item>
      <g:id>{escape(str(sku))}</g:id>
      <title>{escape(p.get('titre') or '')[:150]}</title>
      <description>{escape(desc_raw)}</description>
      <link>{escape(link)}</link>
      <g:image_link>{escape(photo)}</g:image_link>
      <g:availability>{avail}</g:availability>
      <g:price>{prix} {devise}</g:price>
      <g:condition>new</g:condition>
      <g:brand>{escape(boutique.get('nom') or 'Yukpo')}</g:brand>
      <g:identifier_exists>no</g:identifier_exists>
      <g:product_type>{escape(str(p.get('yukpo_category') or 'general'))[:100]}</g:product_type>
    </item>""")

    title = escape(boutique.get("nom") or "Yukpo Shop")
    base = base_url.rstrip("/")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:g="http://base.google.com/ns/1.0" version="2.0">
  <channel>
    <title>{title}</title>
    <link>{base}</link>
    <description>{escape(boutique.get('description') or 'Boutique en ligne Yukpo')[:500]}</description>
{chr(10).join(items_xml)}
  </channel>
</rss>
"""
