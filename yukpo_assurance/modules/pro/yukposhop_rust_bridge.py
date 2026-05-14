"""Piste 1 — Bridge YukpoShop -> Yukpo Rust marketplace.

Quand un commerçant crée/met à jour un produit publié dans YukpoShop, on
publie aussi le produit dans le marketplace Yukpo Rust pour bénéficier de
sa recherche full-text + matching IA + GPS-géolocalisation. Le consommateur
voit le produit dans l'app Yukpo + clique pour atterrir sur la boutique
YukpoShop du commerçant.

Architecture :
  - HMAC-SHA256 signature header X-Yukpo-Signature (anti-tampering)
  - Timestamp header X-Yukpo-Timestamp (anti-replay, fenêtre 5min)
  - Idempotency : la clé est (source="yukposhop", external_id=produit.id)
    Rust upsert le Service via external_product_links.
  - Retry : 3 tentatives exponentielles 2/4/8s en cas d'erreur transitoire,
    abandon après 5 attempts cumulés (le produit reste avec rust_sync_status
    = "failed" et est ré-essayable manuellement via /republier-rust).
  - Schéma : on envoie un payload neutre que Rust mappe ensuite vers son
    Service.data JSONB. Pas de couplage fort.

Configuration via env vars (cf. fly secrets) :
  - RUST_BRIDGE_URL : URL complète du bridge endpoint Rust
                     (défaut : https://yukpomnang.fly.dev/api/v1/integrations/yukposhop/sync)
  - RUST_BRIDGE_HMAC_KEY : secret partagé base64 (32 bytes idéalement)
  - RUST_BRIDGE_ENABLED : "true" pour activer (défaut false en dev)
  - RUST_BRIDGE_TIMEOUT_S : timeout HTTP (défaut 12s — Rust peut être lent
                            sur le 1er call si scale-to-zero)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import ShopBoutiqueDB, ShopProductDB

logger = logging.getLogger("yukpo_assurance.pro.rust_bridge")


# ─── Config ──────────────────────────────────────────────────────────────────

def _config():
    return {
        "enabled": (os.getenv("RUST_BRIDGE_ENABLED") or "false").lower() == "true",
        "url": os.getenv("RUST_BRIDGE_URL")
               or "https://yukpomnang.fly.dev/api/v1/integrations/yukposhop/sync",
        "hmac_key": os.getenv("RUST_BRIDGE_HMAC_KEY") or "",
        "timeout_s": float(os.getenv("RUST_BRIDGE_TIMEOUT_S") or "12"),
    }


MAX_ATTEMPTS = 5            # Plafond cumulé sur la durée de vie du produit
RETRY_BACKOFFS_S = (2, 4, 8)  # Backoff exponentiel par tentative dans CE call


# ─── Mapping produit -> payload neutre ──────────────────────────────────────

def _mapper_produit_pour_rust(
    p: ShopProductDB,
    b: ShopBoutiqueDB,
    vendeur_email: str,
    vendeur_nom: Optional[str] = None,
) -> dict[str, Any]:
    """Compose le payload envoyé à Rust. Format STABLE — versionné via 'schema_version'.

    Rust upsert ensuite via (source, external_id). Aucun secret n'est inclus.
    """
    # Devise — YukpoShop peut avoir XAF/XOF/EUR/USD, Rust est XAF. Pour la v1,
    # on envoie devise + prix tel quel ; Rust se charge de convertir si besoin.
    photos = []
    if isinstance(p.photos_urls_json, list):
        photos = [str(u) for u in p.photos_urls_json if isinstance(u, str) and u][:8]

    tags = []
    if isinstance(p.tags_json, list):
        tags = [str(t) for t in p.tags_json if isinstance(t, str)][:20]

    return {
        "schema_version": 2,  # 6b/d : video_url + boutique gps
        "source": "yukposhop",
        "external_id": str(p.id),                # idempotency key
        "external_updated_at": (p.modif_le or p.cree_le).isoformat() + "Z",
        "vendeur": {
            "email": vendeur_email,
            "nom_affiche": vendeur_nom or b.nom,
            "boutique_slug": b.slug,
            "boutique_url": b.url_public,
            "gps": getattr(b, "gps", None),   # Piste 6e — propage GPS boutique
            "pays": b.pays_principal or "CM",
            "telephone": getattr(b, "telephone", None),
        },
        "produit": {
            "titre": p.titre,
            "description": (p.description_longue or p.description_courte or "")[:5000],
            "prix": float(p.prix_unit_promo or p.prix_unit or 0),
            "devise": p.devise or b.devise or "XAF",
            "stock": int(p.stock or 0),
            "photos_urls": photos,
            "video_url": getattr(p, "video_url", None),     # Piste 6b
            "video_thumbnail_url": getattr(p, "video_thumbnail_url", None),
            "tags": tags,
            "slug": p.slug,
            "categorie": None,  # Rust auto-classifie via IA
            "pays": b.pays_principal or "CM",
        },
        "retour_au_marchand": {
            # URL où Rust renvoie le consommateur quand il clique sur le produit.
            "url_storefront": (
                f"{b.url_public}/produits/{p.slug}"
                if b.url_public else None
            ),
            "whatsapp_contact": None,  # à enrichir plus tard si dispo
        },
    }


# ─── HMAC signature ──────────────────────────────────────────────────────────

def _signer(body_bytes: bytes, hmac_key: str, timestamp: str) -> str:
    """HMAC-SHA256(timestamp + "." + body) en base64 — anti-tampering+replay."""
    if not hmac_key:
        return ""
    try:
        key = base64.b64decode(hmac_key)
    except Exception:
        # Si pas valid base64, on utilise la clé brute (compat dev)
        key = hmac_key.encode("utf-8")
    msg = timestamp.encode("ascii") + b"." + body_bytes
    sig = hmac.new(key, msg, hashlib.sha256).digest()
    return base64.b64encode(sig).decode("ascii")


# ─── Result type ─────────────────────────────────────────────────────────────

@dataclass
class SyncResult:
    success: bool
    rust_service_id: Optional[int]
    error: Optional[str]
    http_status: Optional[int]
    duration_ms: int


# ─── Publication (push) ─────────────────────────────────────────────────────

async def publier_produit_vers_rust(
    produit_id: int,
    db: AsyncSession,
    vendeur_email: str,
    vendeur_nom: Optional[str] = None,
) -> SyncResult:
    """Publie un produit YukpoShop dans le marketplace Yukpo Rust.

    Idempotent : si rust_service_id existe déjà, Rust fera UPDATE plutôt
    qu'INSERT. Met à jour `rust_sync_status` + `rust_synced_at` en base.

    Best-effort : ne lève PAS d'exception en cas d'échec — retourne SyncResult
    avec error rempli. Le caller décide quoi faire (typiquement : logger
    seulement, ne pas bloquer la réponse user-facing).
    """
    t0 = time.monotonic()
    cfg = _config()
    if not cfg["enabled"]:
        return SyncResult(False, None, "RUST_BRIDGE_ENABLED=false (skip)",
                          None, 0)
    if not cfg["hmac_key"]:
        return SyncResult(False, None, "RUST_BRIDGE_HMAC_KEY manquant",
                          None, 0)

    # Récupère produit + boutique + check ownership/sync_enabled
    p = (await db.execute(
        select(ShopProductDB).where(ShopProductDB.id == produit_id)
    )).scalar_one_or_none()
    if not p:
        return SyncResult(False, None, "Produit introuvable", None, 0)
    b = (await db.execute(
        select(ShopBoutiqueDB).where(ShopBoutiqueDB.id == p.boutique_id)
    )).scalar_one_or_none()
    if not b:
        return SyncResult(False, None, "Boutique introuvable", None, 0)
    if not getattr(b, "rust_sync_enabled", True):
        p.rust_sync_status = "disabled"
        await db.commit()
        return SyncResult(False, None, "Sync désactivée pour cette boutique",
                          None, 0)
    if p.statut != "actif":
        p.rust_sync_status = "skipped"
        await db.commit()
        return SyncResult(False, None, f"Produit statut={p.statut} (non actif)",
                          None, 0)
    if (p.rust_sync_attempts or 0) >= MAX_ATTEMPTS:
        return SyncResult(False, None,
                          f"Max attempts {MAX_ATTEMPTS} atteint — sync manuelle requise",
                          None, 0)

    payload = _mapper_produit_pour_rust(p, b, vendeur_email, vendeur_nom)
    body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    timestamp = str(int(time.time()))
    sig = _signer(body_bytes, cfg["hmac_key"], timestamp)

    headers = {
        "Content-Type": "application/json",
        "X-Yukpo-Signature": sig,
        "X-Yukpo-Timestamp": timestamp,
        "X-Yukpo-Source": "yukposhop",
        "X-Yukpo-Schema-Version": "1",
    }

    last_error = None
    last_status = None
    rust_service_id: Optional[int] = None
    enrichment: Optional[dict] = None  # Piste 6a

    async with httpx.AsyncClient(timeout=cfg["timeout_s"]) as client:
        for attempt_idx in range(len(RETRY_BACKOFFS_S) + 1):
            try:
                resp = await client.post(cfg["url"], content=body_bytes, headers=headers)
                last_status = resp.status_code
                if resp.status_code == 200 or resp.status_code == 201:
                    data = resp.json()
                    rust_service_id = data.get("rust_service_id") or data.get("service_id")
                    if not isinstance(rust_service_id, int):
                        last_error = f"Réponse Rust sans service_id valide : {data}"
                        break
                    # Piste 6a — récupération enrichissement IA (best-effort)
                    enrich_payload = data.get("enrichment")
                    if isinstance(enrich_payload, dict):
                        enrichment = enrich_payload
                    last_error = None
                    break
                elif 400 <= resp.status_code < 500 and resp.status_code != 429:
                    # 4xx (sauf 429) : pas la peine de retry, problème côté nous
                    last_error = f"HTTP {resp.status_code} : {resp.text[:300]}"
                    break
                else:
                    # 5xx ou 429 : transitoire, retry
                    last_error = f"HTTP {resp.status_code} : {resp.text[:200]}"
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = f"Réseau : {e}"
            except Exception as e:
                last_error = f"Inattendu : {e}"
                break

            # Backoff entre attempts (sauf après la dernière)
            if attempt_idx < len(RETRY_BACKOFFS_S):
                import asyncio
                await asyncio.sleep(RETRY_BACKOFFS_S[attempt_idx])

    duration_ms = int((time.monotonic() - t0) * 1000)

    # Persiste le résultat
    p.rust_sync_attempts = (p.rust_sync_attempts or 0) + 1
    if rust_service_id:
        p.rust_service_id = rust_service_id
        p.rust_sync_status = "synced"
        p.rust_synced_at = datetime.utcnow()
        p.rust_sync_error = None
        # Piste 6a — store enrichment fields si dispo
        if enrichment:
            cat = enrichment.get("category")
            if isinstance(cat, str) and cat:
                p.yukpo_category = cat[:60]
            st = enrichment.get("specialized_type")
            if isinstance(st, str) and st and st != "null":
                p.yukpo_specialized_type = st[:80]
            tags = enrichment.get("tags_fr")
            if isinstance(tags, list) and tags:
                p.yukpo_tags_json = [str(t)[:60] for t in tags if isinstance(t, str)][:8]
            desc = enrichment.get("description_enriched_fr")
            if isinstance(desc, str) and desc and desc != "null":
                p.yukpo_description_enriched = desc[:4000]
            lang = enrichment.get("language_detected")
            if isinstance(lang, str) and lang:
                p.yukpo_language_detected = lang[:8]
            qs = enrichment.get("quality_score")
            if isinstance(qs, int):
                p.yukpo_quality_score = max(0, min(100, qs))
            ct = enrichment.get("cost_tokens")
            if isinstance(ct, int):
                p.yukpo_enrichment_cost_tokens = ct
            # Piste 6d — modération IA
            mod_status = enrichment.get("moderation_status")
            if isinstance(mod_status, str) and mod_status in ("approved", "flagged", "rejected"):
                p.yukpo_ai_moderation_status = mod_status
                # Si rejected, auto-désactive le produit en local (sécurité)
                if mod_status == "rejected" and p.statut == "actif":
                    p.statut = "brouillon"
                    logger.warning(
                        f"[RustBridge] produit_id={produit_id} REJECTED par modération IA "
                        f"-> statut basculé en 'brouillon'"
                    )
            mod_reason = enrichment.get("moderation_reason")
            if isinstance(mod_reason, str) and mod_reason and mod_reason != "null":
                p.yukpo_ai_moderation_reason = mod_reason[:1000]
            p.yukpo_enriched_at = datetime.utcnow()
    else:
        p.rust_sync_status = "failed"
        p.rust_sync_error = (last_error or "Inconnu")[:1000]
    await db.commit()

    if rust_service_id:
        logger.info(
            f"[RustBridge] produit_id={produit_id} -> rust_service_id={rust_service_id} "
            f"({duration_ms}ms, attempt {p.rust_sync_attempts})"
        )
    else:
        logger.warning(
            f"[RustBridge] produit_id={produit_id} ECHEC ({duration_ms}ms) : {last_error}"
        )

    return SyncResult(
        success=bool(rust_service_id),
        rust_service_id=rust_service_id,
        error=last_error,
        http_status=last_status,
        duration_ms=duration_ms,
    )


# ─── Helper pour BackgroundTasks FastAPI ────────────────────────────────────

async def publier_async_safe(produit_id: int, vendeur_email: str,
                              vendeur_nom: Optional[str] = None) -> None:
    """Wrapper safe pour FastAPI BackgroundTasks — gère sa propre session DB
    et avale les exceptions (le caller ne doit jamais voir d'erreur)."""
    from core.database import async_session_maker
    try:
        async with async_session_maker() as session:
            await publier_produit_vers_rust(
                produit_id=produit_id, db=session,
                vendeur_email=vendeur_email, vendeur_nom=vendeur_nom,
            )
    except Exception as e:
        logger.warning(f"[RustBridge] background task échec produit_id={produit_id}: {e}")
