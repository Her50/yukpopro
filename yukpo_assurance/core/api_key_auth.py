"""
Sprint 2.1 — Authentification par clé API + rate-limiting.

Format clé : `ypro_live_<32 hex>` (prod) ou `ypro_test_<32 hex>` (sandbox).
Header attendu : `X-API-Key: ypro_live_...` OU `Authorization: Bearer ypro_live_...`

Stockage : seulement le SHA-256 de la clé en DB (irreversible). La clé en
clair n'est montrée qu'UNE FOIS à la création, puis perdue.

Rate limiting : Redis sliding window (per_hour + per_day par clé). Fallback
in-memory si Redis indispo. Headers de réponse :
  - X-RateLimit-Limit-Hour, X-RateLimit-Remaining-Hour
  - X-RateLimit-Limit-Day,  X-RateLimit-Remaining-Day
  - Retry-After (si 429)
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select

logger = logging.getLogger("yukpo_assurance.api_key_auth")


# ─── Génération + hash ────────────────────────────────────────────────────────


def generer_cle_api(env: str = "live") -> tuple[str, str, str]:
    """
    Génère une nouvelle clé API.
    Retourne (cle_complete, prefix, sha256_hash).
    `env` ∈ {"live", "test"}.
    """
    if env not in ("live", "test"):
        env = "live"
    prefix = f"ypro_{env}_"
    secret_part = secrets.token_hex(16)   # 32 chars hex
    cle_complete = f"{prefix}{secret_part}"
    sha = hashlib.sha256(cle_complete.encode("utf-8")).hexdigest()
    return cle_complete, prefix, sha


def hasher_cle(cle: str) -> str:
    """SHA-256 hex (64 chars)."""
    return hashlib.sha256(cle.encode("utf-8")).hexdigest()


# ─── Modèle d'identité ────────────────────────────────────────────────────────


class ApiKeyIdentity:
    """Identité résolue d'une clé API (équivalent de TokenData mais pour B2B API)."""

    def __init__(self, key_id: str, compagnie_id: int, user_id: int,
                 scopes: list[str], rate_hour: int, rate_day: int, label: str):
        self.key_id = key_id
        self.compagnie_id = compagnie_id
        self.user_id = user_id            # créateur de la clé (audit)
        self.scopes = scopes
        self.rate_limit_per_hour = rate_hour
        self.rate_limit_per_day = rate_day
        self.label = label

    def has_scope(self, scope: str) -> bool:
        if "*" in self.scopes:
            return True
        return scope in self.scopes


# ─── Rate limiting (Redis sliding window) ─────────────────────────────────────

# Fallback in-memory : dict[key_id] → list[timestamp]
_RATE_LIMIT_MEMORY: dict[str, list[float]] = {}


async def _check_rate_limit(
    key_id: str, limit_hour: int, limit_day: int,
) -> tuple[bool, dict]:
    """
    Vérifie + incrémente le compteur de la clé.
    Retourne (allowed: bool, headers: dict).
    """
    now = time.time()
    headers = {}
    try:
        from config.settings import settings
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
        # Sliding window via sorted set : score = timestamp, value = unique req id
        key_h = f"apikey_rl:hour:{key_id}"
        key_d = f"apikey_rl:day:{key_id}"
        cutoff_h = now - 3600
        cutoff_d = now - 86400
        async with r.pipeline(transaction=True) as p:
            p.zremrangebyscore(key_h, 0, cutoff_h)
            p.zremrangebyscore(key_d, 0, cutoff_d)
            p.zcard(key_h)
            p.zcard(key_d)
            res = await p.execute()
        count_h = int(res[2] or 0)
        count_d = int(res[3] or 0)
        if count_h >= limit_hour:
            await r.aclose()
            headers.update({
                "X-RateLimit-Limit-Hour": str(limit_hour),
                "X-RateLimit-Remaining-Hour": "0",
                "Retry-After": "3600",
            })
            return False, headers
        if count_d >= limit_day:
            await r.aclose()
            headers.update({
                "X-RateLimit-Limit-Day": str(limit_day),
                "X-RateLimit-Remaining-Day": "0",
                "Retry-After": "86400",
            })
            return False, headers
        # Incrément
        unique = secrets.token_hex(8)
        async with r.pipeline(transaction=True) as p:
            p.zadd(key_h, {unique: now})
            p.zadd(key_d, {unique: now})
            p.expire(key_h, 3600)
            p.expire(key_d, 86400)
            await p.execute()
        await r.aclose()
        headers.update({
            "X-RateLimit-Limit-Hour": str(limit_hour),
            "X-RateLimit-Remaining-Hour": str(max(0, limit_hour - count_h - 1)),
            "X-RateLimit-Limit-Day": str(limit_day),
            "X-RateLimit-Remaining-Day": str(max(0, limit_day - count_d - 1)),
        })
        return True, headers
    except Exception as e:
        logger.debug(f"[ApiKey RL] Redis indispo, fallback memory : {e}")

    # Fallback in-memory (non-cluster-safe — best effort)
    cutoff_h = now - 3600
    cutoff_d = now - 86400
    timestamps = _RATE_LIMIT_MEMORY.setdefault(key_id, [])
    # Clean
    timestamps[:] = [t for t in timestamps if t > cutoff_d]
    count_h = sum(1 for t in timestamps if t > cutoff_h)
    count_d = len(timestamps)
    if count_h >= limit_hour:
        return False, {"X-RateLimit-Limit-Hour": str(limit_hour),
                       "X-RateLimit-Remaining-Hour": "0", "Retry-After": "3600"}
    if count_d >= limit_day:
        return False, {"X-RateLimit-Limit-Day": str(limit_day),
                       "X-RateLimit-Remaining-Day": "0", "Retry-After": "86400"}
    timestamps.append(now)
    return True, {
        "X-RateLimit-Limit-Hour": str(limit_hour),
        "X-RateLimit-Remaining-Hour": str(max(0, limit_hour - count_h - 1)),
        "X-RateLimit-Limit-Day": str(limit_day),
        "X-RateLimit-Remaining-Day": str(max(0, limit_day - count_d - 1)),
    }


# ─── Dépendance FastAPI ───────────────────────────────────────────────────────


async def get_api_key_identity(
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> ApiKeyIdentity:
    """
    Dépendance FastAPI : valide la clé API + applique le rate limiting +
    retourne l'identité de l'organisation.

    Lève 401 si la clé est absente/invalide/révoquée.
    Lève 429 si le rate-limit est dépassé.
    Ajoute les headers X-RateLimit-* à la réponse.
    """
    cle: Optional[str] = None
    if x_api_key and x_api_key.startswith(("ypro_live_", "ypro_test_")):
        cle = x_api_key.strip()
    elif authorization and authorization.startswith("Bearer "):
        candidate = authorization[7:].strip()
        if candidate.startswith(("ypro_live_", "ypro_test_")):
            cle = candidate
    if not cle:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clé API manquante. Header X-API-Key: ypro_live_xxx requis.",
            headers={"WWW-Authenticate": 'ApiKey realm="yukpopro"'},
        )

    sha = hasher_cle(cle)
    from core.database import async_session_maker, ApiKeyDB
    async with async_session_maker() as db:
        row = (await db.execute(
            select(ApiKeyDB).where(ApiKeyDB.key_hash == sha)
        )).scalar_one_or_none()
        if not row or not row.actif or row.revoquee_le is not None:
            raise HTTPException(401, "Clé API invalide ou révoquée.")
        # MAJ derniere_utilisation (best effort)
        try:
            row.derniere_utilisation = datetime.utcnow()
            await db.commit()
        except Exception:
            pass
        identity = ApiKeyIdentity(
            key_id=row.key_id, compagnie_id=row.compagnie_id,
            user_id=row.user_id_createur,
            scopes=row.scopes or [], rate_hour=row.rate_limit_per_hour,
            rate_day=row.rate_limit_per_day, label=row.label,
        )

    # Rate limit
    allowed, rl_headers = await _check_rate_limit(
        identity.key_id, identity.rate_limit_per_hour, identity.rate_limit_per_day,
    )
    # Stocke les headers dans request.state pour middleware d'enrichissement
    request.state.rate_limit_headers = rl_headers
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit dépassé pour la clé '{identity.label}'.",
            headers=rl_headers,
        )
    return identity


def require_scope(scope: str):
    """Dépendance composable : vérifie qu'une clé a un scope donné."""
    async def _dep(identity: ApiKeyIdentity = Depends(get_api_key_identity)) -> ApiKeyIdentity:
        if not identity.has_scope(scope):
            raise HTTPException(403, f"Scope '{scope}' requis. Scopes actifs: {identity.scopes}")
        return identity
    return _dep
