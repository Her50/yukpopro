"""Chargement unifié des secrets paiement.

Ordre de résolution :
    1. Variable d'environnement (priorité absolue — prod conteneurisée)
    2. GCP Secret Manager (project = settings.GCP_PROJECT_ID, par défaut yukpo-project)
    3. settings.* du fichier .env (fallback dev)

Cache en mémoire pour éviter les appels répétés à GCP.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("yukpo_assurance.paiement.v2.secrets")

_GCP_CLIENT = None
_CACHE: dict[str, str] = {}

_DEFAULT_GCP_PROJECT = os.environ.get("GCP_PAYMENT_PROJECT", "yukpo-project")

# Mapping nom logique interne → secret GCP officiel
GCP_SECRET_MAP = {
    "CINETPAY_API_KEY": "cinetpay-api-key",
    "CINETPAY_API_PASSWORD": "cinetpay-api-password",
    "CINETPAY_SECRET_KEY": "cinetpay-secret-key",
    "CINETPAY_SITE_ID": "cinetpay-site-id",
    "FLUTTERWAVE_PUBLIC_KEY": "flutterwave-public-key",
    "FLUTTERWAVE_SECRET_KEY": "flutterwave-secret-key",
    "MTN_MOMO_WEBHOOK_SECRET": "mtn-money-webhook-secret",
    "NOTCHPAY_PUBLIC_KEY": "notchpay-public-key",
    "NOTCHPAY_SECRET_KEY": "notchpay-secret-key",
    "ORANGE_MONEY_WEBHOOK_SECRET": "orange-money-webhook-secret",
    "PAYPAL_CLIENT_ID": "paypal-client-id",
    "PAYPAL_CLIENT_SECRET": "paypal-client-secret",
    "PAYPAL_WEBHOOK_ID": "paypal-webhook-id",
    "STRIPE_PUBLISHABLE_KEY": "stripe-publishable-key",
    "STRIPE_SECRET_KEY": "stripe-secret-key",
    "STRIPE_WEBHOOK_SECRET": "stripe-webhook-secret",
}


def _get_gcp_client():
    global _GCP_CLIENT
    if _GCP_CLIENT is not None:
        return _GCP_CLIENT
    try:
        from google.cloud import secretmanager  # type: ignore
        _GCP_CLIENT = secretmanager.SecretManagerServiceClient()
        return _GCP_CLIENT
    except Exception as exc:
        logger.debug("GCP Secret Manager indisponible (%s) — fallback .env", exc)
        return None


def _load_from_gcp(secret_name: str, project_id: str) -> Optional[str]:
    client = _get_gcp_client()
    if client is None:
        return None
    try:
        path = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": path})
        return response.payload.data.decode("utf-8").strip()
    except Exception as exc:
        logger.debug("GCP secret %s introuvable: %s", secret_name, exc)
        return None


def get_secret(
    logical_name: str,
    *,
    fallback_settings_attr: Optional[str] = None,
    project_id: str = _DEFAULT_GCP_PROJECT,
) -> str:
    """
    Résout un secret de paiement.

    `logical_name` doit être en MAJUSCULES (ex: STRIPE_SECRET_KEY).
    `fallback_settings_attr` : nom d'attribut sur `settings` à utiliser si
    la variable d'env et GCP sont vides.
    """
    if logical_name in _CACHE:
        return _CACHE[logical_name]

    # 1. Variable d'environnement
    value = os.environ.get(logical_name, "").strip()
    if value:
        _CACHE[logical_name] = value
        return value

    # 2. GCP Secret Manager
    gcp_name = GCP_SECRET_MAP.get(logical_name)
    if gcp_name:
        gcp_value = _load_from_gcp(gcp_name, project_id)
        if gcp_value:
            _CACHE[logical_name] = gcp_value
            logger.info("Secret %s chargé depuis GCP Secret Manager", logical_name)
            return gcp_value

    # 3. settings.* fallback
    if fallback_settings_attr:
        try:
            from config.settings import settings  # local import (cycle-safe)
            attr_value = getattr(settings, fallback_settings_attr, "") or ""
            if attr_value:
                _CACHE[logical_name] = attr_value
                return attr_value
        except Exception:
            pass

    _CACHE[logical_name] = ""
    return ""


def clear_cache() -> None:
    """Vide le cache (utile pour les tests ou rotation de secrets)."""
    _CACHE.clear()


def list_available_secrets(project_id: str = _DEFAULT_GCP_PROJECT) -> dict[str, bool]:
    """Diagnostic : retourne un dict {nom_logique: True/False} indiquant
    si chaque secret est résolvable (sans révéler les valeurs)."""
    result = {}
    for logical_name in GCP_SECRET_MAP:
        result[logical_name] = bool(get_secret(logical_name))
    return result
