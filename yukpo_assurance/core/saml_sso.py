"""
Sprint 2.2 — SAML SSO via python3-saml (OneLogin's SAML toolkit pour Python).

Supporte tous les Identity Providers SAML 2.0 standards :
  - Okta
  - Azure Active Directory (Microsoft Entra ID)
  - Google Workspace
  - OneLogin
  - PingIdentity
  - Auth0
  - Keycloak

Flow utilisateur :
  1. User clique "Se connecter avec SSO" sur YukpoPro frontend
  2. Frontend redirige vers /api/v1/saml/login?compagnie_id=X
  3. Backend redirige vers IdP SSO URL avec SAMLRequest
  4. User s'authentifie chez IdP (Okta/Azure/Google)
  5. IdP POST l'assertion signée vers /api/v1/saml/acs?compagnie_id=X
  6. Backend valide signature, mappe attributs → user, mint JWT, set cookie
  7. Frontend reçoit le user authentifié

Sur Windows local : python3-saml échoue à l'import (libxmlsec1 manquant).
L'app fonctionne, les endpoints SAML retournent 503.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("yukpo_assurance.saml_sso")

# Import gracieux — on tolère l'absence sur Windows local
try:
    from onelogin.saml2.auth import OneLogin_Saml2_Auth
    from onelogin.saml2.settings import OneLogin_Saml2_Settings
    from onelogin.saml2.utils import OneLogin_Saml2_Utils
    _SAML_AVAILABLE = True
except Exception as e:
    OneLogin_Saml2_Auth = None  # type: ignore
    OneLogin_Saml2_Settings = None  # type: ignore
    OneLogin_Saml2_Utils = None  # type: ignore
    _SAML_AVAILABLE = False
    logger.info(f"[SAML] python3-saml indispo (mode dégradé) : {e}")


def is_available() -> bool:
    return _SAML_AVAILABLE


def _build_settings_dict(saml_config_row) -> dict:
    """Construit le dict de settings python3-saml depuis une row SamlConfigDB."""
    return {
        "strict": True,
        "debug": False,
        "sp": {
            "entityId": saml_config_row.sp_entity_id,
            "assertionConsumerService": {
                "url": saml_config_row.sp_acs_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
        },
        "idp": {
            "entityId": saml_config_row.idp_entity_id,
            "singleSignOnService": {
                "url": saml_config_row.idp_sso_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "x509cert": saml_config_row.idp_x509_cert,
        },
        "security": {
            "wantAssertionsSigned": True,
            "wantMessagesSigned": False,
            "wantNameId": True,
            "wantNameIdEncrypted": False,
            "signMetadata": False,
            "authnRequestsSigned": False,
            "logoutRequestSigned": False,
            "logoutResponseSigned": False,
            "signatureAlgorithm": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
            "digestAlgorithm": "http://www.w3.org/2001/04/xmlenc#sha256",
        },
    }


async def _request_to_saml_data(request) -> dict:
    """Adapte un Request FastAPI vers le format attendu par python3-saml."""
    body = await request.body() if request.method == "POST" else b""
    try:
        from urllib.parse import parse_qs
        post_data = parse_qs(body.decode("utf-8")) if body else {}
        post_data = {k: v[0] for k, v in post_data.items()}
    except Exception:
        post_data = {}
    return {
        "https": "on" if request.url.scheme == "https" else "off",
        "http_host": request.url.hostname or "",
        "server_port": str(request.url.port or (443 if request.url.scheme == "https" else 80)),
        "script_name": request.url.path,
        "get_data": dict(request.query_params),
        "post_data": post_data,
    }


async def init_auth(request, saml_config_row) -> "OneLogin_Saml2_Auth":
    """Construit un objet OneLogin_Saml2_Auth pour cette requête + config IdP."""
    if not _SAML_AVAILABLE:
        raise RuntimeError("python3-saml non disponible (libxmlsec1 manquant)")
    saml_data = await _request_to_saml_data(request)
    settings_dict = _build_settings_dict(saml_config_row)
    return OneLogin_Saml2_Auth(saml_data, settings_dict)


def parse_idp_metadata(metadata_xml: str) -> dict:
    """
    Parse un metadata XML d'IdP (collé par l'admin) et extrait :
      - entity_id, sso_url, x509_cert
    Pour pré-remplir SamlConfigDB lors de la configuration.
    """
    if not _SAML_AVAILABLE:
        raise RuntimeError("python3-saml non disponible")
    try:
        from onelogin.saml2.idp_metadata_parser import OneLogin_Saml2_IdPMetadataParser
        parsed = OneLogin_Saml2_IdPMetadataParser.parse(metadata_xml)
        idp = parsed.get("idp", {})
        return {
            "entity_id": idp.get("entityId", ""),
            "sso_url": (idp.get("singleSignOnService") or {}).get("url", ""),
            "x509_cert": idp.get("x509cert", ""),
        }
    except Exception as e:
        logger.error(f"[SAML] parse IdP metadata échoué : {e}")
        raise ValueError(f"Metadata XML invalide : {e}")
