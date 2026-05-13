"""Publication landing page → Netlify API (Phase A1).

Déploie une landing HTML statique (single-file) sur Netlify via leur API
officielle. Crée un site si nouveau slug, sinon redéploie sur le site
existant. L'URL publique est de forme :

    https://<slug>.yukpomnang.com           (si DNS wildcard configuré)
    https://<slug>-<random>.netlify.app     (fallback netlify)

Pré-requis env :
  • NETLIFY_API_TOKEN   — Personal Access Token (Netlify → User settings)
  • NETLIFY_TEAM_SLUG   — (optionnel) team slug pour facturation centralisée
  • LANDING_DOMAIN_BASE — défaut "yukpomnang.com" — domaine racine alias

Pricing impact : facturé via debiter_forfait("landing_publish_netlify").
"""
from __future__ import annotations

import io
import logging
import os
import zipfile
from typing import Optional

import httpx

logger = logging.getLogger("yukpo_assurance.pro.landing_publisher")


_NETLIFY_API = "https://api.netlify.com/api/v1"
_DEFAULT_DOMAIN = "yukpomnang.com"


class NetlifyError(Exception):
    """Erreur de communication ou réponse Netlify non 2xx."""


def _token() -> str:
    tok = os.getenv("NETLIFY_API_TOKEN", "").strip()
    if not tok:
        raise NetlifyError(
            "NETLIFY_API_TOKEN non configuré — impossible de publier. "
            "Cf. docs/INFRA_SCALING.md section 'Landing publication'."
        )
    return tok


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
    }


def _zip_html_unique_file(html_bytes: bytes) -> bytes:
    """Empaquette le HTML standalone dans un ZIP `index.html` à la racine.

    Netlify déploie un ZIP en attendant un `index.html` au root.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("index.html", html_bytes)
        # robots.txt minimal pour autoriser l'indexation par défaut
        zf.writestr(
            "robots.txt",
            "User-agent: *\nAllow: /\n",
        )
    return buf.getvalue()


def _zip_arborescence(files: dict) -> bytes:
    """Empaquette un dict {chemin_relatif: bytes} en ZIP Netlify.

    Phase C — utilisé pour les mini-sites multi-pages :
    files = {
      "index.html":           b"...",
      "services/index.html":  b"...",
      "equipe/index.html":    b"...",
      "blog/article-x/index.html": b"...",
      "sitemap.xml":          b"...",
      "robots.txt":           b"...",
    }
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            # Sécurité : on refuse les chemins absolus ou path traversal
            if path.startswith("/") or ".." in path or path.startswith("\\"):
                logger.warning(f"[Netlify/zip] chemin invalide ignoré : {path}")
                continue
            zf.writestr(path, content)
    return buf.getvalue()


async def creer_site(slug: str, *, ajouter_alias_custom: bool = True) -> dict:
    """Crée un nouveau site Netlify pour ce slug.

    Returns: {site_id, ssl_url, name, url_public_souhaitee}
    """
    base_domain = os.getenv("LANDING_DOMAIN_BASE", _DEFAULT_DOMAIN).strip()
    custom_alias = f"{slug}.{base_domain}" if ajouter_alias_custom else None

    payload: dict = {"name": slug}
    team_slug = os.getenv("NETLIFY_TEAM_SLUG", "").strip()
    endpoint = f"{_NETLIFY_API}/sites"
    if team_slug:
        endpoint = f"{_NETLIFY_API}/{team_slug}/sites"
    if custom_alias:
        payload["custom_domain"] = custom_alias

    async with httpx.AsyncClient(timeout=30.0) as client:
        rep = await client.post(endpoint, headers=_headers(), json=payload)
        if rep.status_code >= 300:
            raise NetlifyError(
                f"Netlify create_site échec {rep.status_code}: {rep.text[:300]}"
            )
        data = rep.json()
        return {
            "site_id": data["id"],
            "ssl_url": data.get("ssl_url") or data.get("url"),
            "name": data.get("name"),
            "url_public_souhaitee": (
                f"https://{custom_alias}" if custom_alias
                else (data.get("ssl_url") or data.get("url"))
            ),
        }


async def deployer_zip(site_id: str, zip_bytes: bytes) -> dict:
    """Déploie un ZIP sur un site existant. Returns {deploy_id, deploy_ssl_url}."""
    url = f"{_NETLIFY_API}/sites/{site_id}/deploys"
    headers = {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/zip",
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        rep = await client.post(url, headers=headers, content=zip_bytes)
        if rep.status_code >= 300:
            raise NetlifyError(
                f"Netlify deploy échec {rep.status_code}: {rep.text[:300]}"
            )
        data = rep.json()
        return {
            "deploy_id": data.get("id"),
            "deploy_ssl_url": data.get("ssl_url") or data.get("deploy_ssl_url"),
            "state": data.get("state"),
        }


async def publier_landing(html_bytes: bytes, slug: str) -> dict:
    """Crée le site + déploie en un seul appel.

    Returns: {
      site_id, url_public, deploy_id, custom_domain_alias_demande,
    }
    """
    if not slug or not slug.replace("-", "").isalnum():
        raise ValueError(f"Slug invalide : {slug!r}")
    site = await creer_site(slug)
    zip_bytes = _zip_html_unique_file(html_bytes)
    deploy = await deployer_zip(site["site_id"], zip_bytes)
    logger.info(
        f"[Netlify] publication slug={slug} site_id={site['site_id']} "
        f"deploy={deploy.get('deploy_id')} url={site['url_public_souhaitee']}"
    )
    return {
        "site_id": site["site_id"],
        "url_public": site["url_public_souhaitee"],
        "fallback_netlify_url": site["ssl_url"],
        "deploy_id": deploy.get("deploy_id"),
        "state": deploy.get("state"),
    }


async def republier_landing(site_id: str, html_bytes: bytes) -> dict:
    """Redéploie un nouveau HTML sur un site Netlify existant.

    Returns: {deploy_id, state}
    """
    zip_bytes = _zip_html_unique_file(html_bytes)
    deploy = await deployer_zip(site_id, zip_bytes)
    logger.info(
        f"[Netlify] re-publication site_id={site_id} "
        f"deploy={deploy.get('deploy_id')}"
    )
    return deploy


async def publier_site_multipage(
    files: dict, slug: str,
    *, site_id_existant: Optional[str] = None,
) -> dict:
    """Phase C — Publie un site multi-pages (arborescence de fichiers) sur Netlify.

    Args:
        files            : dict {chemin: bytes} (incluant index.html + sitemap)
        slug             : sous-domaine cible (<slug>.yukpomnang.com)
        site_id_existant : si fourni, re-déploiement sur ce site (sinon création)

    Returns: {site_id, url_public, deploy_id, is_new}
    """
    if not slug or not slug.replace("-", "").isalnum():
        raise ValueError(f"Slug invalide : {slug!r}")
    zip_bytes = _zip_arborescence(files)

    if site_id_existant:
        deploy = await deployer_zip(site_id_existant, zip_bytes)
        return {
            "site_id": site_id_existant,
            "url_public": None,  # déjà connu côté caller
            "deploy_id": deploy.get("deploy_id"),
            "state": deploy.get("state"),
            "is_new": False,
        }
    site = await creer_site(slug)
    deploy = await deployer_zip(site["site_id"], zip_bytes)
    return {
        "site_id": site["site_id"],
        "url_public": site["url_public_souhaitee"],
        "fallback_netlify_url": site["ssl_url"],
        "deploy_id": deploy.get("deploy_id"),
        "state": deploy.get("state"),
        "is_new": True,
    }


async def supprimer_site(site_id: str) -> bool:
    """Supprime un site Netlify (utile pour cleanup compte / suspension user)."""
    url = f"{_NETLIFY_API}/sites/{site_id}"
    headers = {"Authorization": f"Bearer {_token()}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        rep = await client.delete(url, headers=headers)
        return rep.status_code in (200, 204)


def is_active() -> bool:
    """True si le module est configuré et utilisable."""
    return bool(os.getenv("NETLIFY_API_TOKEN", "").strip())
