"""
YukpoAssurance — Client IA multi-modèle  (v3 — Production-grade)
Orchestration Claude Sonnet (primaire) + GPT-4o (fallback)
Inspiré de l'architecture app_ia.rs + orchestration_ia.rs de yukpomnang2

v3 — Nouvelles fonctionnalités :
- Circuit breaker Redis-persistant (survit aux redémarrages)
- Budget tokens par utilisateur et global avec enforcement
- Token-cost capping : refus auto si budget dépassé
- Alertes budget (Prometheus + log WARNING)
- Batch API Claude corrigée (asyncio.to_thread pour résultats sync)
- Cache Redis transparent (hash prompt → réponse, TTL configurable)
- Tarifs à jour (Anthropic + OpenAI 2025)
"""
from __future__ import annotations
import asyncio
import base64
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Callable

import anthropic
import openai
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config.settings import settings

logger = logging.getLogger("yukpo_assurance.ia_client")

# ── Disponibilité Redis (cache 30s) ───────────────────────────────────────────
# Évite de bloquer l'event loop async sur chaque appel IA quand Redis est down.
_redis_disponible: bool | None = None   # None = pas encore vérifié
_redis_last_check: float = 0.0          # timestamp du dernier check

def _redis_est_disponible() -> bool:
    """Vérifie Redis via socket non-bloquant, résultat mis en cache 30s."""
    global _redis_disponible, _redis_last_check
    now = time.monotonic()
    if _redis_disponible is not None and now - _redis_last_check < 30.0:
        return _redis_disponible
    try:
        import socket as _socket
        from urllib.parse import urlparse
        url = urlparse(settings.REDIS_URL)
        host = url.hostname or "localhost"
        port = url.port or 6379
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        s.settimeout(0.3)   # 300ms max — timeout rapide, non-bloquant
        result = s.connect_ex((host, port))
        s.close()
        _redis_disponible = (result == 0)
    except Exception:
        _redis_disponible = False
    _redis_last_check = now
    if not _redis_disponible:
        logger.debug("[IAClient] Redis indisponible — mode mémoire uniquement")
    return _redis_disponible

# ── Tarifs API (USD / token) — source : openai.com/api/pricing + anthropic.com/pricing ──
TARIFS_INPUT = {
    "claude-opus-4-7":             15.0 / 1_000_000,
    "claude-opus-4-6":             15.0 / 1_000_000,
    "claude-sonnet-4-6":            3.0 / 1_000_000,
    "claude-haiku-4-5-20251001":   0.25 / 1_000_000,
    # OpenAI flagship 2025
    "gpt-5":                       10.0 / 1_000_000,
    "gpt-5-mini":                   2.5 / 1_000_000,
    "gpt-5-nano":                   0.50 / 1_000_000,
    # OpenAI 4.1 family (avril 2025) — 1M ctx + 32k output
    "gpt-4.1":                      2.0 / 1_000_000,
    "gpt-4.1-mini":                 0.40 / 1_000_000,
    "gpt-4.1-nano":                 0.10 / 1_000_000,
    # OpenAI reasoning models (o-series)
    "o3":                           2.0 / 1_000_000,
    "o3-mini":                      1.10 / 1_000_000,
    "o4-mini":                      1.10 / 1_000_000,
    # OpenAI legacy (encore supportés pour rétrocompat)
    "gpt-4-turbo":                 10.0 / 1_000_000,   # cap 4096 output - obsolète
    "gpt-4o":                       2.5 / 1_000_000,
    "gpt-4o-mini":                 0.15 / 1_000_000,
}
TARIFS_OUTPUT = {
    "claude-opus-4-7":             75.0 / 1_000_000,
    "claude-opus-4-6":             75.0 / 1_000_000,
    "claude-sonnet-4-6":           15.0 / 1_000_000,
    "claude-haiku-4-5-20251001":   1.25 / 1_000_000,
    "gpt-5":                       30.0 / 1_000_000,
    "gpt-5-mini":                  10.0 / 1_000_000,
    "gpt-5-nano":                   2.0 / 1_000_000,
    "gpt-4.1":                      8.0 / 1_000_000,
    "gpt-4.1-mini":                 1.60 / 1_000_000,
    "gpt-4.1-nano":                 0.40 / 1_000_000,
    "o3":                           8.0 / 1_000_000,
    "o3-mini":                      4.40 / 1_000_000,
    "o4-mini":                      4.40 / 1_000_000,
    "gpt-4-turbo":                 30.0 / 1_000_000,
    "gpt-4o":                      10.0 / 1_000_000,
    "gpt-4o-mini":                  0.60 / 1_000_000,
}


class ModeIA(str, Enum):
    PRECISION    = "precision"      # États CIMA, calculs réglementaires — temp 0.1
    ANALYSE      = "analyse"        # Fraude, souscription, sinistres — temp 0.3
    REDACTION    = "redaction"      # Rapports, courriers — temp 0.4
    COPILOTE     = "copilote"       # Assistant quotidien — temp 0.5
    COMMERCIAL   = "commercial"     # Offres, communication client — temp 0.7
    RAISONNEMENT = "raisonnement"   # Compositions structurées Opus (questionnaires, Magic Import) — temp 0.2


class ModelePrioritaire(str, Enum):
    CLAUDE_OPUS    = "claude-opus-4-7"          # Niveau 5 : layout AI / décisions de composition pro
    CLAUDE_SONNET  = "claude-sonnet-4-6"        # Optimal pour CIMA/sinistres/rédaction
    CLAUDE_HAIKU   = "claude-haiku-4-5-20251001"
    # OpenAI flagship (août 2025) — équivalent ou supérieur à Opus
    GPT5           = "gpt-5"                    # Niveau 5+ : flagship général
    GPT5_MINI      = "gpt-5-mini"               # Niveau 4 : qualité élevée moins cher
    GPT5_NANO      = "gpt-5-nano"               # Niveau 3 : éco
    # OpenAI 4.1 (avril 2025) — 32k OUTPUT, 1M context, JSON structuré long
    GPT4_1         = "gpt-4.1"                  # Niveau 5 : composer freeform livret multi-pages
    GPT4_1_MINI    = "gpt-4.1-mini"             # Niveau 4 : structuré rapide pas cher
    GPT4_1_NANO    = "gpt-4.1-nano"             # Niveau 2 : pré-gen Haiku, simulations massives
    # OpenAI reasoning (chain-of-thought) — pour orchestrer/classification critique
    O3             = "o3"                       # Niveau 5 : raisonnement profond
    O3_MINI        = "o3-mini"                  # Niveau 4 : raisonnement rapide pas cher
    O4_MINI        = "o4-mini"                  # Niveau 4 : raisonnement updated
    # Legacy (rétrocompat, à éviter pour nouveaux usages)
    GPT4_TURBO     = "gpt-4-turbo"              # ❌ cap 4096 output, obsolète
    GPT4O          = "gpt-4o"                   # 16k output - usage légacy
    GPT4O_MINI     = "gpt-4o-mini"              # 16k output - usage légacy léger

# Mapping Claude → GPT équivalent (utilisé quand Claude est indisponible OU
# quand LLM_PRIMAIRE=gpt). Mise à jour mai 2026 :
#
#   Claude Opus 4.7   → GPT-5         (équivalent top-tier, ~3× moins cher
#                                      que Opus, comparable qualité creative
#                                      writing + reasoning + long-context)
#   Claude Sonnet 4.6 → GPT-5-mini    (mid-tier équilibre qualité/coût)
#   Claude Haiku 4.5  → GPT-4.1-nano  (économique, classification rapide)
#
# Pourquoi GPT-5 et pas GPT-4.1 pour Opus : GPT-4.1 (32k output, $2/$8) reste
# excellent pour les longs documents structurés (livret 16 pages, freeform
# 100 cartes) où le 32k OUT compte. Mais pour CREATIVE WRITING DENSE
# (marketing/promo, slogans, simulation contenu riche) → GPT-5 dépasse
# GPT-4.1 et talonne Opus.
#
# GPT-4-turbo (cap 4096) reste BANNI pour les générations structurées denses.
_CLAUDE_TO_GPT: dict[str, str] = {
    ModelePrioritaire.CLAUDE_HAIKU.value:  ModelePrioritaire.GPT4_1_NANO.value,
    ModelePrioritaire.CLAUDE_SONNET.value: ModelePrioritaire.GPT5_MINI.value,
    ModelePrioritaire.CLAUDE_OPUS.value:   ModelePrioritaire.GPT5.value,
}


# ── Circuit breaker par modèle ────────────────────────────────────────────────
@dataclass
class CircuitBreaker:
    """
    Circuit breaker Redis-persistant — survit aux redémarrages (v3).
    Fallback en mémoire si Redis indisponible.
    """
    modele: str = ""
    seuil_echecs: int = 5
    cooldown_secondes: int = 60
    # État en mémoire (fallback)
    _echecs_consecutifs: int = 0
    _ouvert_depuis: Optional[float] = None

    def _redis_key_echecs(self) -> str:
        return f"cb:echecs:{self.modele}"

    def _redis_key_ouvert(self) -> str:
        return f"cb:ouvert_depuis:{self.modele}"

    @property
    def est_ouvert(self) -> bool:
        # Vérifier Redis uniquement si disponible (évite blocage event loop si Redis down)
        if _redis_est_disponible():
            try:
                import redis
                r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=0.3, socket_timeout=0.3)
                ouvert_ts = r.get(self._redis_key_ouvert())
                if ouvert_ts:
                    ts = float(ouvert_ts)
                    if time.time() - ts > self.cooldown_secondes:
                        r.delete(self._redis_key_ouvert())
                        r.set(self._redis_key_echecs(), 0)
                        return False
                    return True
            except Exception:
                pass
        # Fallback mémoire (toujours)
        if self._ouvert_depuis is None:
            return False
        if time.monotonic() - self._ouvert_depuis > self.cooldown_secondes:
            self._ouvert_depuis = None
            self._echecs_consecutifs = 0
            return False
        return True

    def enregistrer_succes(self):
        self._echecs_consecutifs = 0
        self._ouvert_depuis = None
        if _redis_est_disponible():
            try:
                import redis
                r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=0.3, socket_timeout=0.3)
                r.set(self._redis_key_echecs(), 0)
                r.delete(self._redis_key_ouvert())
            except Exception:
                pass

    def enregistrer_echec(self):
        self._echecs_consecutifs += 1
        if _redis_est_disponible():
            try:
                import redis
                r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=0.3, socket_timeout=0.3)
                echecs = int(r.incr(self._redis_key_echecs()) or 0)
                r.expire(self._redis_key_echecs(), self.cooldown_secondes * 3)
                if echecs >= self.seuil_echecs:
                    r.set(self._redis_key_ouvert(), time.time(), ex=self.cooldown_secondes)
                    logger.warning(
                        f"[CircuitBreaker/Redis] {self.modele} ouvert après {echecs} échecs — "
                        f"cooldown {self.cooldown_secondes}s"
                    )
                    return
            except Exception:
                pass
        # Fallback mémoire
        if self._echecs_consecutifs >= self.seuil_echecs:
            self._ouvert_depuis = time.monotonic()
            logger.warning(
                f"[CircuitBreaker/Mem] {self.modele} ouvert après {self._echecs_consecutifs} échecs — "
                f"cooldown {self.cooldown_secondes}s"
            )


@dataclass
class MetriquesModele:
    """Suivi de performance par modèle — inspiré de ModelMetrics dans app_ia.rs"""
    total_requetes: int = 0
    requetes_succes: int = 0
    requetes_echec: int = 0
    temps_reponse_moyen: float = 0.0
    tokens_utilises: int = 0
    cout_total_usd: float = 0.0
    derniere_utilisation: Optional[float] = None

    @property
    def taux_succes(self) -> float:
        if self.total_requetes == 0:
            return 1.0
        return self.requetes_succes / self.total_requetes


@dataclass
class ReponseIA:
    """Réponse structurée du client IA"""
    contenu: str
    modele_utilise: str
    tokens_input: int = 0
    tokens_output: int = 0
    temps_ms: float = 0.0
    confiance: float = 1.0
    fallback_utilise: bool = False
    depuis_cache: bool = False
    metadata: dict = field(default_factory=dict)

    def as_json(self) -> dict:
        try:
            return json.loads(self.contenu)
        except json.JSONDecodeError:
            return {"texte": self.contenu}


class IAClient:
    """
    Client IA unifié pour YukpoAssurance.

    Stratégie d'orchestration :
    1. Claude (Sonnet 4.6) en priorité — modèle primaire pour tous les modes
    2. GPT-4o — fallback automatique si Claude indisponible
    3. Claude Haiku — tâches légères si forcé explicitement

    Améliorations v2 :
    - Circuit breaker par modèle
    - Cache Redis transparent (hash(prompt+systeme) → réponse)
    - Batch API corrigée (asyncio.to_thread)
    - Alertes coût dépassement budget
    """

    def __init__(self):
        # Claude est le modèle primaire — clé CLAUDE_API_KEY obligatoire
        _claude_key = settings.CLAUDE_API_KEY or ""
        _claude_valide = (
            _claude_key.startswith("sk-ant-")
            and len(_claude_key) > 40
            and "CONFIGURER" not in _claude_key.upper()
            and "YOUR" not in _claude_key.upper()
            and "CLE" not in _claude_key.upper()
        )
        # timeout=300s pour gros projets (infographie multi-page, brochures, livrets)
        self._claude = (
            anthropic.AsyncAnthropic(api_key=_claude_key, timeout=300.0)
            if _claude_valide
            else None
        )
        # timeout=240s pour génération de documents longs et projets multi-page
        self._gpt = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=240.0, max_retries=1)
        self._metriques: dict[str, MetriquesModele] = {
            m.value: MetriquesModele() for m in ModelePrioritaire
        }
        self._circuit_breakers: dict[str, CircuitBreaker] = {
            m.value: CircuitBreaker(modele=m.value, cooldown_secondes=300)  # 5 min cooldown
            for m in ModelePrioritaire
        }
        self._cache_redis = None  # Initialisé lazily
        self._cache_local: dict[str, ReponseIA] = {}  # Fallback si Redis down
        # Budget global cumulé (en USD) — alerte si > IA_BUDGET_ALERTE_USD
        self._cout_session_usd: float = 0.0

    # ─── Cache Redis ──────────────────────────────────────────────────────────

    # Sentinel pour "Redis testé et indisponible" — évite de retenter à chaque requête
    _REDIS_UNAVAILABLE = object()

    async def _get_cache(self) -> Any:
        """Retourne le client Redis (lazy init, None si indisponible)."""
        if self._cache_redis is self._REDIS_UNAVAILABLE:
            return None
        if self._cache_redis is not None:
            return self._cache_redis
        # Vérifier rapidement via socket avant de tenter la connexion async
        if not _redis_est_disponible():
            self._cache_redis = self._REDIS_UNAVAILABLE
            return None
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(
                settings.REDIS_URL,
                socket_connect_timeout=0.3,
                socket_timeout=0.3,
            )
            await asyncio.wait_for(r.ping(), timeout=0.5)
            self._cache_redis = r
            return r
        except Exception:
            self._cache_redis = self._REDIS_UNAVAILABLE
            return None

    def _cache_key(self, prompt: str, systeme: Optional[str], mode: ModeIA, max_tokens: int = 0) -> str:
        # Inclure max_tokens dans la clé : une réponse longue ≠ une réponse courte pour la même question
        h = hashlib.sha256(
            f"{mode.value}|{systeme or ''}|{max_tokens}|{prompt}".encode()
        ).hexdigest()[:32]
        return f"ia_cache:{h}"

    async def _lire_cache(self, key: str) -> Optional[ReponseIA]:
        # Mémoire locale d'abord
        if key in self._cache_local:
            r = self._cache_local[key]
            r.depuis_cache = True
            return r
        r = await self._get_cache()
        if r:
            try:
                data = await r.get(key)
                if data:
                    d = json.loads(data)
                    return ReponseIA(
                        contenu=d["contenu"],
                        modele_utilise=d.get("modele_utilise", "cache"),
                        depuis_cache=True,
                    )
            except Exception:
                pass
        return None

    async def _ecrire_cache(self, key: str, reponse: ReponseIA, ttl: int = 3600) -> None:
        data = json.dumps({"contenu": reponse.contenu, "modele_utilise": reponse.modele_utilise})
        # Redis
        r = await self._get_cache()
        if r:
            try:
                await r.setex(key, ttl, data)
            except Exception:
                pass
        # Mémoire locale (cap 200 entrées LRU simple)
        if len(self._cache_local) >= 200:
            oldest = next(iter(self._cache_local))
            del self._cache_local[oldest]
        self._cache_local[key] = reponse

    # ─── Méthode principale ───────────────────────────────────────────────────

    async def appeler(
        self,
        prompt: str,
        *,
        mode: ModeIA = ModeIA.ANALYSE,
        systeme: Optional[str] = None,
        images_b64: Optional[list[str]] = None,
        forcer_modele: Optional[ModelePrioritaire] = None,
        json_attendu: bool = False,
        utiliser_cache: bool = True,
        cache_ttl: int = 3600,
        max_tokens_override: Optional[int] = None,  # Pour documents très longs (IA_MAX_TOKENS_DOCUMENT)
    ) -> ReponseIA:
        """
        Point d'entrée unique pour tous les appels IA.
        Sélectionne le modèle, gère le cache, le circuit breaker et le fallback.
        """
        temperature = self._temperature_par_mode(mode)
        modele = forcer_modele or self._choisir_modele(mode)

        # ── Politique LLM_PRIMAIRE — respect global ──────────────────────
        # Quand le code appelle forcer_modele=CLAUDE_X, c'est une demande
        # de TIER de qualité (haute/moyenne/légère), pas une demande
        # d'utiliser Claude spécifiquement. Si LLM_PRIMAIRE="gpt", on
        # traduit automatiquement vers le GPT équivalent — c'est la
        # source de vérité de la politique. Anthropic devient fallback
        # naturel via le circuit breaker.
        # Mapping actuel (mai 2026) — cf. _CLAUDE_TO_GPT ligne 151 :
        #   CLAUDE_OPUS   → GPT-5         (flagship raisonnement haut de gamme,
        #                                  équivalent qualité Opus, ~3× moins cher)
        #   CLAUDE_SONNET → GPT-5-mini    (mid-tier équilibre qualité/coût)
        #   CLAUDE_HAIKU  → GPT-4.1-nano  (économique, classification rapide)
        # Note : gpt-4-turbo est LEGACY (cap 4096 output, obsolète) — NE PAS
        # utiliser pour les nouveaux usages. Pour rivaliser Opus en raisonnement,
        # GPT-5 est le bon choix (talonne Opus en creative writing dense +
        # long-context, et O3/O3-mini sont disponibles pour reasoning profond).
        if forcer_modele is not None and self._llm_primaire() == "gpt":
            if modele in (
                ModelePrioritaire.CLAUDE_OPUS,
                ModelePrioritaire.CLAUDE_SONNET,
                ModelePrioritaire.CLAUDE_HAIKU,
            ):
                gpt_equiv_value = _CLAUDE_TO_GPT.get(modele.value)
                if gpt_equiv_value:
                    try:
                        modele = ModelePrioritaire(gpt_equiv_value)
                        logger.debug(
                            f"[IAClient] LLM_PRIMAIRE=gpt → traduit "
                            f"{forcer_modele.value} → {modele.value}"
                        )
                    except ValueError:
                        pass

        # Résoudre max_tokens effectif avant le cache (la clé en dépend)
        max_tokens = max_tokens_override or settings.IA_MAX_TOKENS

        # Cache uniquement si pas d'images (résultats déterministes)
        cache_key = None
        if utiliser_cache and not images_b64:
            cache_key = self._cache_key(prompt, systeme, mode, max_tokens)
            cached = await self._lire_cache(cache_key)
            if cached:
                logger.debug(f"[IAClient] Cache hit — {cache_key[:16]}")
                return cached

        debut = time.monotonic()

        # Vérifier budget global
        await self._verifier_budget(utilisateur_id=None)

        # Vérifier circuit breaker
        cb = self._circuit_breakers[modele.value]
        if cb.est_ouvert:
            logger.warning(f"[IAClient] Circuit ouvert pour {modele.value} → fallback immédiat")
            return await self._fallback(
                prompt=prompt, mode=mode, systeme=systeme,
                images_b64=images_b64, json_attendu=json_attendu, debut=debut,
                max_tokens=max_tokens,
            )

        try:
            if modele in (
                ModelePrioritaire.CLAUDE_OPUS,
                ModelePrioritaire.CLAUDE_SONNET,
                ModelePrioritaire.CLAUDE_HAIKU,
            ):
                if self._claude is None:
                    # Claude indisponible — mapper vers GPT équivalent
                    gpt_nom = _CLAUDE_TO_GPT.get(modele.value, ModelePrioritaire.GPT4O.value)
                    reponse = await self._appel_gpt(
                        prompt=prompt, temperature=temperature,
                        systeme=systeme, images_b64=images_b64, json_attendu=json_attendu,
                        max_tokens=max_tokens, modele_force=gpt_nom,
                    )
                else:
                    # Pour CLAUDE_SONNET, utiliser le modèle concret défini dans settings
                    modele_concret = (
                        settings.CLAUDE_MODEL_PRIMAIRE
                        if modele == ModelePrioritaire.CLAUDE_SONNET
                        else modele.value
                    )
                    reponse = await self._appel_claude(
                        prompt=prompt, modele=modele_concret, temperature=temperature,
                        systeme=systeme, images_b64=images_b64, json_attendu=json_attendu,
                        max_tokens=max_tokens,
                    )
            else:
                # GPT4O ou GPT4O_MINI explicite
                reponse = await self._appel_gpt(
                    prompt=prompt, temperature=temperature,
                    systeme=systeme, images_b64=images_b64, json_attendu=json_attendu,
                    max_tokens=max_tokens, modele_force=modele.value,
                )

            self._enregistrer_succes(modele.value, time.monotonic() - debut, reponse)
            cb.enregistrer_succes()

            if cache_key and not images_b64:
                await self._ecrire_cache(cache_key, reponse, ttl=cache_ttl)

            asyncio.ensure_future(self._persister_cout(reponse, mode.value))
            return reponse

        except Exception as e:
            logger.warning(f"[IAClient] {modele.value} échoué: {e} → bascule fallback")
            self._enregistrer_echec(modele.value)
            cb.enregistrer_echec()
            return await self._fallback(
                prompt=prompt, mode=mode, systeme=systeme,
                images_b64=images_b64, json_attendu=json_attendu, debut=debut,
                max_tokens=max_tokens,
                modele_original=modele,    # tier preservation pour fallback
            )

    # ─── Appel Claude ─────────────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        retry=retry_if_exception_type((anthropic.APITimeoutError, anthropic.InternalServerError)),
    )
    async def _appel_claude(
        self,
        prompt: str,
        modele: str,
        temperature: float,
        systeme: Optional[str],
        images_b64: Optional[list[str]],
        json_attendu: bool,
        max_tokens: int = 0,
    ) -> ReponseIA:
        debut = time.monotonic()
        contenu_user: list[dict] = []

        if images_b64:
            for img in images_b64:
                # Détection type d'image (PNG ou JPEG)
                media_type = "image/png" if img.startswith("iVBOR") else "image/jpeg"
                contenu_user.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": img},
                })

        contenu_user.append({"type": "text", "text": prompt})

        kwargs: dict[str, Any] = {
            "model": modele,
            "max_tokens": max_tokens or settings.IA_MAX_TOKENS,
            "temperature": temperature,
            "messages": [{"role": "user", "content": contenu_user}],
        }
        # Prompt caching Anthropic : system prompt mis en cache → ~90% moins cher sur tokens cachés
        if systeme:
            try:
                from core.token_optimizer import preparer_system_avec_cache
                kwargs["system"] = preparer_system_avec_cache(systeme)
            except Exception:
                kwargs["system"] = systeme  # fallback sans cache

        if self._claude is None:
            raise RuntimeError("Clé CLAUDE_API_KEY non configurée — Claude indisponible comme fallback")
        response = await self._claude.messages.create(**kwargs)

        if not response.content or len(response.content) == 0:
            raise ValueError(f"Claude {modele} a retourné une réponse vide (stop_reason: {response.stop_reason})")
        texte = response.content[0].text
        if not texte or not texte.strip():
            raise ValueError(f"Claude {modele} a retourné un texte vide")

        if json_attendu:
            texte = self._extraire_json(texte)

        return ReponseIA(
            contenu=texte,
            modele_utilise=modele,
            tokens_input=response.usage.input_tokens,
            tokens_output=response.usage.output_tokens,
            temps_ms=(time.monotonic() - debut) * 1000,
        )

    # ─── Appel GPT-4o ─────────────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(1),
        wait=wait_exponential(min=1, max=5),
        retry=retry_if_exception_type((openai.APITimeoutError, openai.InternalServerError)),
    )
    async def _appel_gpt(
        self,
        prompt: str,
        temperature: float,
        systeme: Optional[str],
        images_b64: Optional[list[str]],
        json_attendu: bool,
        max_tokens: int = 0,
        modele_force: Optional[str] = None,
    ) -> ReponseIA:
        debut = time.monotonic()
        messages = []
        if systeme:
            messages.append({"role": "system", "content": systeme})

        contenu_user: list[dict] = []
        if images_b64:
            for img in images_b64:
                contenu_user.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img}", "detail": "high"},
                })
        contenu_user.append({"type": "text", "text": prompt})
        messages.append({"role": "user", "content": contenu_user})

        # Limites tokens par modèle GPT
        _MAX_BY_MODEL = {
            "gpt-4o":       16000,
            "gpt-4o-mini":  16000,
        }
        if modele_force:
            _modele = modele_force
        elif (max_tokens or settings.IA_MAX_TOKENS) <= 20:
            _modele = settings.GPT_MODEL_FALLBACK
        else:
            _modele = getattr(settings, "GPT_MODEL_PRIMAIRE", settings.GPT_MODEL_FALLBACK)
        _max_out = _MAX_BY_MODEL.get(_modele, 16000)
        _tokens_demandes = min(max_tokens or settings.IA_MAX_TOKENS, _max_out)

        # Modèles "reasoning" (gpt-5.x, o1/o3/o4) : exigent `max_completion_tokens`
        # et n'acceptent ni `temperature` ni `response_format=json_object`.
        _ml = _modele.lower()
        _est_reasoning = (
            _ml.startswith("gpt-5")
            or _ml.startswith("o1") or _ml.startswith("o3") or _ml.startswith("o4")
        )
        kwargs: dict[str, Any] = {
            "model": _modele,
            "messages": messages,
        }
        if _est_reasoning:
            kwargs["max_completion_tokens"] = _tokens_demandes
        else:
            kwargs["max_tokens"] = _tokens_demandes
            kwargs["temperature"] = temperature
            if json_attendu:
                kwargs["response_format"] = {"type": "json_object"}

        response = await self._gpt.chat.completions.create(**kwargs)

        if not response.choices or len(response.choices) == 0:
            raise ValueError(f"{_modele} a retourné une réponse sans choix")
        texte = response.choices[0].message.content or ""

        # Auto-fallback : si le modèle renvoie vide, on retente une fois avec gpt-4o.
        if not texte.strip() and not modele_force and _modele != "gpt-4o":
            logger.warning(f"[IAClient] {_modele} a retourné un texte vide → retry avec gpt-4o")
            kwargs_retry = {
                "model": "gpt-4o",
                "messages": messages,
                "max_tokens": min(max_tokens or settings.IA_MAX_TOKENS, 16000),
                "temperature": temperature,
            }
            if json_attendu:
                kwargs_retry["response_format"] = {"type": "json_object"}
            response = await self._gpt.chat.completions.create(**kwargs_retry)
            if not response.choices or len(response.choices) == 0:
                raise ValueError("gpt-4o a retourné une réponse sans choix")
            texte = response.choices[0].message.content or ""
            _modele = "gpt-4o"

        if not texte.strip():
            raise ValueError(f"{_modele} a retourné un texte vide")

        return ReponseIA(
            contenu=texte,
            modele_utilise=_modele,
            tokens_input=response.usage.prompt_tokens if response.usage else 0,
            tokens_output=response.usage.completion_tokens if response.usage else 0,
            temps_ms=(time.monotonic() - debut) * 1000,
            fallback_utilise=False,
        )

    # ─── Batch API Claude (CORRIGÉ) ───────────────────────────────────────────

    async def traiter_batch_documents(
        self,
        documents: list[dict],  # [{"id": str, "image_b64": str, "type_doc": str}]
        prompt_builder: Callable[[str], str],
    ) -> list[dict]:
        """
        Traite des centaines de documents en parallèle via Claude Batch API.
        Coût : -50% vs appels individuels. Jusqu'à 10 000 documents par batch.

        CORRECTION v2 : results() retourne un itérateur SYNC dans le SDK Anthropic.
        On utilise asyncio.to_thread pour l'itérer sans bloquer l'event loop.
        """
        if not documents:
            return []

        requests = []
        for doc in documents:
            prompt = prompt_builder(doc["type_doc"])
            req: dict[str, Any] = {
                "custom_id": doc["id"],
                "params": {
                    "model": settings.CLAUDE_MODEL_PRIMAIRE,
                    "max_tokens": 1024,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": doc["image_b64"],
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }],
                },
            }
            requests.append(req)

        logger.info(f"[Batch] Lancement batch {len(requests)} documents")
        batch = await self._claude.messages.batches.create(requests=requests)

        # Polling jusqu'à completion
        for _ in range(120):  # max 10 minutes
            batch = await self._claude.messages.batches.retrieve(batch.id)
            if batch.processing_status == "ended":
                break
            await asyncio.sleep(5)
        else:
            logger.error("[Batch] Timeout après 10 minutes")
            return [{"id": doc["id"], "data": None, "succes": False} for doc in documents]

        # ── CORRECTION : itérer les résultats avec un client SYNC dans un thread ──
        batch_id = batch.id
        api_key = settings.CLAUDE_API_KEY

        def _collecter_resultats() -> list:
            sync_client = anthropic.Anthropic(api_key=api_key)
            return list(sync_client.messages.batches.results(batch_id))

        raw_results = await asyncio.to_thread(_collecter_resultats)

        resultats = []
        for result in raw_results:
            if result.result.type == "succeeded":
                try:
                    texte = result.result.message.content[0].text
                    data = json.loads(texte)
                except (json.JSONDecodeError, IndexError, AttributeError):
                    data = {"texte": getattr(
                        getattr(result.result, "message", None),
                        "content", [{}]
                    )[0].get("text", "") if hasattr(result.result, "message") else ""}
                resultats.append({"id": result.custom_id, "data": data, "succes": True})
            else:
                logger.warning(f"[Batch] Échec document {result.custom_id}")
                resultats.append({"id": result.custom_id, "data": None, "succes": False})

        logger.info(
            f"[Batch] Terminé : {sum(1 for r in resultats if r['succes'])}/"
            f"{len(resultats)} succès"
        )
        return resultats

    # ─── Vision IA : GPT-4o primaire, Claude fallback ────────────────────────

    async def analyser_image_vision(
        self,
        image_b64: str,
        prompt: str,
        mode: ModeIA = ModeIA.PRECISION,
    ) -> ReponseIA:
        """
        OCR/analyse d'image — ordre primaire/fallback dicté par settings.LLM_PRIMAIRE.
        Un seul appel — pas de parallèle, pas de double coût.
        """
        temperature = self._temperature_par_mode(mode)
        primaire = self._llm_primaire()

        async def _try_claude() -> Optional[ReponseIA]:
            cb = self._circuit_breakers[ModelePrioritaire.CLAUDE_SONNET.value]
            if self._claude is None or cb.est_ouvert:
                return None
            debut = time.monotonic()
            try:
                rep = await self._appel_claude(
                    prompt=prompt, modele=settings.CLAUDE_MODEL_PRIMAIRE,
                    temperature=temperature, systeme=None,
                    images_b64=[image_b64], json_attendu=True,
                )
                self._enregistrer_succes(ModelePrioritaire.CLAUDE_SONNET.value, time.monotonic() - debut, rep)
                cb.enregistrer_succes()
                return rep
            except Exception as e:
                logger.warning(f"[IAClient/Vision] Claude échoué: {e}")
                self._enregistrer_echec(ModelePrioritaire.CLAUDE_SONNET.value)
                cb.enregistrer_echec()
                return None

        async def _try_gpt() -> Optional[ReponseIA]:
            cb = self._circuit_breakers[ModelePrioritaire.GPT4O.value]
            if cb.est_ouvert:
                return None
            debut = time.monotonic()
            try:
                rep = await self._appel_gpt(
                    prompt=prompt, temperature=temperature, systeme=None,
                    images_b64=[image_b64], json_attendu=True,
                )
                self._enregistrer_succes(ModelePrioritaire.GPT4O.value, time.monotonic() - debut, rep)
                cb.enregistrer_succes()
                return rep
            except Exception as e:
                logger.warning(f"[IAClient/Vision] GPT échoué: {e}")
                cb.enregistrer_echec()
                return None

        ordre = (_try_gpt, _try_claude) if primaire == "gpt" else (_try_claude, _try_gpt)
        for i, attempt in enumerate(ordre):
            rep = await attempt()
            if rep:
                if i > 0:
                    rep.fallback_utilise = True
                return rep
        raise RuntimeError("Vision IA indisponible — Claude et GPT en circuit ouvert")

    # ─── Utilitaires internes ─────────────────────────────────────────────────

    def _llm_primaire(self) -> str:
        """Retourne 'gpt' ou 'claude' selon settings.LLM_PRIMAIRE."""
        return getattr(settings, "LLM_PRIMAIRE", "gpt").lower()

    def _choisir_modele(self, mode: ModeIA) -> ModelePrioritaire:
        """
        Sélection du modèle primaire selon settings.LLM_PRIMAIRE.
          - LLM_PRIMAIRE=gpt    → GPT-5.5 (ou GPT-4o-mini pour COPILOTE/COMMERCIAL)
          - LLM_PRIMAIRE=claude → Claude Sonnet
        Si le primaire est indisponible (clé manquante), bascule auto sur l'autre.
        """
        primaire = self._llm_primaire()
        if primaire == "claude" and self._claude is not None:
            return ModelePrioritaire.CLAUDE_SONNET
        # GPT primaire (ou Claude indisponible)
        if mode in (ModeIA.COPILOTE, ModeIA.COMMERCIAL):
            return ModelePrioritaire.GPT4O_MINI
        return ModelePrioritaire.GPT4O

    def _temperature_par_mode(self, mode: ModeIA) -> float:
        mapping = {
            ModeIA.PRECISION:    settings.IA_TEMPERATURE_PRECISION,
            ModeIA.ANALYSE:      0.3,
            ModeIA.REDACTION:    settings.IA_TEMPERATURE_REDACTION,
            ModeIA.COPILOTE:     0.5,
            ModeIA.COMMERCIAL:   settings.IA_TEMPERATURE_CREATIVE,
            ModeIA.RAISONNEMENT: 0.2,
        }
        return mapping[mode]

    def _extraire_json(self, texte: str) -> str:
        """Extrait le premier objet JSON d'un texte libre."""
        import re
        if texte.strip().startswith(("{", "[")):
            try:
                json.loads(texte)
                return texte
            except json.JSONDecodeError:
                pass
        match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\}|\[[\s\S]*?\])\s*```', texte)
        if match:
            return match.group(1)
        match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', texte)
        if match:
            return match.group(1)
        logger.warning(f"[IAClient] JSON attendu mais non trouvé: {texte[:200]}")
        return texte

    async def _fallback(
        self, prompt, mode, systeme, images_b64, json_attendu, debut,
        max_tokens: int = 0,
        modele_original: Optional[ModelePrioritaire] = None,
    ) -> ReponseIA:
        """
        Fallback intelligent qui PRESERVE LE TIER QUALITE :
          - Si Opus fail → gpt-4-turbo (raisonnement haut de gamme equivalent)
          - Si Sonnet fail → gpt-4o (rédaction standard equivalent)
          - Si Haiku fail → gpt-4o-mini (rapide+cheap equivalent)
          - Si modele_original GPT et echec → bascule Claude tier equivalent

        Avant : tout tombait sur Sonnet/gpt-4o par defaut, ce qui DEGRADAIT
        Opus → gpt-4o (perte raisonnement). Maintenant la chaine preserve
        le tier via _CLAUDE_TO_GPT (et son inverse implicite).
        """
        # Mapping inverse pour preserve tier sur primaire GPT echec
        _GPT_TO_CLAUDE = {
            ModelePrioritaire.GPT4_TURBO.value: ModelePrioritaire.CLAUDE_OPUS,
            ModelePrioritaire.GPT4O.value:      ModelePrioritaire.CLAUDE_SONNET,
            ModelePrioritaire.GPT4O_MINI.value: ModelePrioritaire.CLAUDE_HAIKU,
        }

        primaire = self._llm_primaire()
        # Primaire GPT → fallback Claude TIER-EQUIVALENT
        if primaire == "gpt" and self._claude is not None:
            # Determiner le Claude tier-equivalent du modele original
            claude_tier = ModelePrioritaire.CLAUDE_SONNET  # defaut
            if modele_original:
                if modele_original.value in _GPT_TO_CLAUDE:
                    claude_tier = _GPT_TO_CLAUDE[modele_original.value]
                elif modele_original in (ModelePrioritaire.CLAUDE_OPUS,
                                          ModelePrioritaire.CLAUDE_SONNET,
                                          ModelePrioritaire.CLAUDE_HAIKU):
                    claude_tier = modele_original
            modele_concret = (
                settings.CLAUDE_MODEL_PRIMAIRE
                if claude_tier == ModelePrioritaire.CLAUDE_SONNET
                else claude_tier.value
            )
            cb = self._circuit_breakers.get(claude_tier.value)
            if not (cb and cb.est_ouvert):
                try:
                    reponse = await self._appel_claude(
                        prompt=prompt,
                        modele=modele_concret,
                        temperature=self._temperature_par_mode(mode),
                        systeme=systeme,
                        images_b64=images_b64,
                        json_attendu=json_attendu,
                        max_tokens=max_tokens or settings.IA_MAX_TOKENS,
                    )
                    reponse.fallback_utilise = True
                    self._enregistrer_succes(claude_tier.value, time.monotonic() - debut, reponse)
                    logger.info(
                        f"[IAClient] Fallback tier-preserve : "
                        f"{modele_original.value if modele_original else '?'} → {modele_concret}"
                    )
                    return reponse
                except Exception as e:
                    logger.error(f"[IAClient] Fallback Claude {claude_tier.value} échoué: {e}")
        # Sinon fallback GPT TIER-EQUIVALENT
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("Service IA indisponible — aucun fournisseur disponible")
        # Determiner le GPT tier-equivalent
        gpt_tier_value = ModelePrioritaire.GPT4O.value  # defaut
        if modele_original:
            if modele_original.value in _CLAUDE_TO_GPT:
                gpt_tier_value = _CLAUDE_TO_GPT[modele_original.value]
            elif modele_original in (ModelePrioritaire.GPT4_TURBO,
                                      ModelePrioritaire.GPT4O,
                                      ModelePrioritaire.GPT4O_MINI):
                gpt_tier_value = modele_original.value
        cb = self._circuit_breakers.get(gpt_tier_value)
        if cb and cb.est_ouvert:
            raise RuntimeError("Tous les modèles IA sont indisponibles (circuit breakers ouverts)")
        try:
            reponse = await self._appel_gpt(
                prompt=prompt,
                temperature=self._temperature_par_mode(mode),
                systeme=systeme,
                images_b64=images_b64,
                json_attendu=json_attendu,
                max_tokens=max_tokens or settings.IA_MAX_TOKENS,
                modele_force=gpt_tier_value,
            )
            reponse.fallback_utilise = True
            self._enregistrer_succes(gpt_tier_value, time.monotonic() - debut, reponse)
            logger.info(
                f"[IAClient] Fallback tier-preserve : "
                f"{modele_original.value if modele_original else '?'} → {gpt_tier_value}"
            )
            return reponse
        except Exception as e:
            logger.error(f"[IAClient] Fallback GPT {gpt_tier_value} aussi échoué: {e}")
            raise

    def _enregistrer_succes(self, modele: str, duree: float, reponse: ReponseIA):
        m = self._metriques.get(modele)
        if m:
            m.total_requetes += 1
            m.requetes_succes += 1
            m.derniere_utilisation = time.time()
            n = m.requetes_succes
            m.temps_reponse_moyen = ((n - 1) * m.temps_reponse_moyen + duree * 1000) / n
            cout = (
                reponse.tokens_input * TARIFS_INPUT.get(modele, 0.01 / 1_000_000)
                + reponse.tokens_output * TARIFS_OUTPUT.get(modele, 0.01 / 1_000_000)
            )
            m.cout_total_usd += cout

    def _enregistrer_echec(self, modele: str):
        m = self._metriques.get(modele)
        if m:
            m.total_requetes += 1
            m.requetes_echec += 1

    async def _verifier_budget(self, utilisateur_id: Optional[int] = None) -> None:
        """
        Vérifie le budget IA avant chaque appel — deux niveaux :
        1. Budget global journalier (tous utilisateurs confondus)
        2. Budget par utilisateur journalier
        Lève RuntimeError si un budget est dépassé.
        Silencieux si Redis indisponible (ne bloque pas le service).
        """
        budget_global = getattr(settings, "IA_BUDGET_GLOBAL_USD_JOUR", 50.0)
        budget_alerte = getattr(settings, "IA_BUDGET_ALERTE_USD", 40.0)
        budget_user = getattr(settings, "IA_BUDGET_PAR_USER_USD_JOUR", 5.0)
        today = __import__("datetime").date.today().isoformat()

        if not _redis_est_disponible():
            return   # Redis down → pas de contrôle budget (non bloquant)
        try:
            import redis
            r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=0.3, socket_timeout=0.3)

            # ── Vérification budget GLOBAL ────────────────────────────────────
            cle_global = f"ia_cout_jour:{today}"
            cout_global = float(r.get(cle_global) or 0)
            if cout_global >= budget_global:
                logger.error(
                    f"[IAClient] BUDGET GLOBAL DÉPASSÉ: {cout_global:.2f}$ / {budget_global}$ — appels bloqués"
                )
                raise RuntimeError(
                    f"Budget IA journalier global dépassé ({cout_global:.2f}$ / {budget_global}$). "
                    "Contacter l'administrateur."
                )
            if cout_global >= budget_alerte:
                logger.warning(
                    f"[IAClient] ALERTE BUDGET GLOBAL: {cout_global:.2f}$ / {budget_global}$ "
                    f"({cout_global / budget_global:.0%})"
                )

            # ── Vérification budget PAR UTILISATEUR ───────────────────────────
            if utilisateur_id is not None and budget_user > 0:
                cle_user = f"ia_cout_user:{utilisateur_id}:{today}"
                cout_user = float(r.get(cle_user) or 0)
                if cout_user >= budget_user:
                    logger.warning(
                        f"[IAClient] BUDGET USER {utilisateur_id} DÉPASSÉ: "
                        f"{cout_user:.2f}$ / {budget_user}$ — appel refusé"
                    )
                    raise RuntimeError(
                        f"Budget IA utilisateur dépassé ({cout_user:.2f}$ / {budget_user}$ aujourd'hui). "
                        "Réessayez demain ou contactez votre administrateur."
                    )
                seuil_alerte_user = budget_user * 0.8
                if cout_user >= seuil_alerte_user:
                    logger.warning(
                        f"[IAClient] ALERTE BUDGET USER {utilisateur_id}: "
                        f"{cout_user:.2f}$ / {budget_user}$ ({cout_user / budget_user:.0%})"
                    )

        except RuntimeError:
            raise
        except Exception:
            pass  # Ne pas bloquer si Redis down

    async def _persister_cout(
        self, reponse: "ReponseIA", module: str, utilisateur_id: Optional[int] = None
    ) -> None:
        """Enregistre le coût de l'appel IA en DB + Redis pour le suivi budgétaire (global + per-user)."""
        modele = reponse.modele_utilise
        cout = (
            reponse.tokens_input * TARIFS_INPUT.get(modele, 0.01 / 1_000_000)
            + reponse.tokens_output * TARIFS_OUTPUT.get(modele, 0.01 / 1_000_000)
        )
        self._cout_session_usd += cout
        today = __import__("datetime").date.today().isoformat()

        # Incrémenter les compteurs Redis (global + per-user) si Redis disponible
        if _redis_est_disponible():
            try:
                import redis
                r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=0.3, socket_timeout=0.3)
                cle_global = f"ia_cout_jour:{today}"
                r.incrbyfloat(cle_global, cout)
                r.expire(cle_global, 86400 * 2)
                if utilisateur_id is not None:
                    cle_user = f"ia_cout_user:{utilisateur_id}:{today}"
                    r.incrbyfloat(cle_user, cout)
                    r.expire(cle_user, 86400 * 2)
            except Exception:
                pass

        # Persister en DB
        try:
            from core.database import async_session_maker, CoutIADB
            async with async_session_maker() as db:
                db.add(CoutIADB(
                    modele=modele, module=module,
                    tokens_input=reponse.tokens_input,
                    tokens_output=reponse.tokens_output,
                    cout_estime_usd=round(cout, 6),
                ))
                await db.commit()
        except Exception as e:
            logger.warning(f"[IAClient] Persistance coût échouée — {type(e).__name__}: {e}")

    # ─── Tool-use (boucle outil async) ───────────────────────────────────────

    @staticmethod
    def _outil_anthropic_vers_openai(outil: dict) -> dict:
        """Convertit un outil format Anthropic → format OpenAI function calling."""
        def _fixer(schema: dict) -> dict:
            if not isinstance(schema, dict):
                return schema
            if schema.get("type") == "array" and "items" not in schema:
                schema = {**schema, "items": {"type": "string"}}
            if "properties" in schema:
                schema = {**schema, "properties": {k: _fixer(v) for k, v in schema["properties"].items()}}
            return schema
        return {
            "type": "function",
            "function": {
                "name": outil["name"],
                "description": outil.get("description", ""),
                "parameters": _fixer(outil.get("input_schema", {"type": "object", "properties": {}})),
            },
        }

    async def _appeler_avec_outils_claude(
        self,
        prompt: str,
        outils: list[dict],
        executeur_outil: Callable,
        *,
        mode: ModeIA,
        systeme: Optional[str],
        max_tours: int,
    ) -> tuple[str, int, int, str]:
        """Boucle tool-use native Claude (format anthropic tool_use/tool_result)."""
        temperature = self._temperature_par_mode(mode)
        tokens_in_total = 0
        tokens_out_total = 0
        modele_claude = settings.CLAUDE_MODEL_PRIMAIRE
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        texte_final = ""

        for _ in range(max_tours):
            kwargs: dict[str, Any] = {
                "model": modele_claude,
                "max_tokens": min(settings.IA_MAX_TOKENS, 8192),
                "temperature": temperature,
                "messages": messages,
            }
            if systeme:
                kwargs["system"] = systeme
            if outils:
                kwargs["tools"] = outils

            response = await self._claude.messages.create(**kwargs)
            tokens_in_total += response.usage.input_tokens
            tokens_out_total += response.usage.output_tokens

            # Collecter texte et tool_use blocs
            blocs_text: list[str] = []
            tool_uses: list[Any] = []
            for bloc in response.content:
                if getattr(bloc, "type", None) == "text":
                    blocs_text.append(bloc.text)
                elif getattr(bloc, "type", None) == "tool_use":
                    tool_uses.append(bloc)

            # Message assistant (conserver tel quel pour le tour suivant)
            messages.append({
                "role": "assistant",
                "content": [
                    {"type": "text", "text": b.text} if getattr(b, "type", None) == "text"
                    else {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
                    for b in response.content if getattr(b, "type", None) in ("text", "tool_use")
                ],
            })

            if response.stop_reason != "tool_use" or not tool_uses:
                texte_final = "\n".join(blocs_text).strip()
                break

            # Exécuter les outils en parallèle
            async def _exec_un(tu):
                try:
                    res = await executeur_outil(tu.name, tu.input or {})
                except Exception as exc:
                    res = f"ERREUR outil {tu.name}: {exc}"
                return tu.id, str(res)

            resultats = await asyncio.gather(*[_exec_un(tu) for tu in tool_uses])
            messages.append({
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": tid, "content": r}
                    for tid, r in resultats
                ],
            })

        return texte_final, tokens_in_total, tokens_out_total, modele_claude

    async def appeler_avec_outils(
        self,
        prompt: str,
        outils: list[dict],
        executeur_outil: Callable,  # async (nom: str, params: dict) -> str
        *,
        mode: ModeIA = ModeIA.ANALYSE,
        systeme: Optional[str] = None,
        max_tours: int = 6,
        module: str = "chat",
        user_id: Optional[int] = None,
    ) -> "ReponseIA":
        """
        Boucle tool-use async (Claude primaire, GPT-4o fallback).

        Le LLM peut appeler plusieurs outils avant de produire sa réponse finale.
        Tous les tokens de tous les tours sont accumulés et persistés ensemble.
        Fallback transparent vers appeler() sans outils si tout échoue.
        """
        temperature = self._temperature_par_mode(mode)
        debut = time.monotonic()
        tokens_input_total = 0
        tokens_output_total = 0

        primaire = self._llm_primaire()
        cb_claude = self._circuit_breakers[ModelePrioritaire.CLAUDE_SONNET.value]

        async def _try_claude_outils() -> Optional[ReponseIA]:
            if self._claude is None or cb_claude.est_ouvert:
                return None
            try:
                texte, tin, tout, modele_claude = await self._appeler_avec_outils_claude(
                    prompt=prompt, outils=outils, executeur_outil=executeur_outil,
                    mode=mode, systeme=systeme, max_tours=max_tours,
                )
                cb_claude.enregistrer_succes()
                return ReponseIA(
                    contenu=texte, modele_utilise=modele_claude,
                    tokens_input=tin, tokens_output=tout,
                    temps_ms=(time.monotonic() - debut) * 1000,
                )
            except Exception as exc:
                logger.warning(f"[IAClient] Claude tool-use échoué ({exc})")
                cb_claude.enregistrer_echec()
                return None

        # Primaire Claude → tente Claude d'abord
        if primaire == "claude":
            rep = await _try_claude_outils()
            if rep is not None:
                asyncio.ensure_future(self._persister_cout(rep, module, user_id))
                return rep

        # GPT (tool-use OpenAI function-calling) — primaire ou fallback
        modele_utilise = getattr(settings, "GPT_MODEL_PRIMAIRE", settings.GPT_MODEL_FALLBACK)
        outils_gpt = [self._outil_anthropic_vers_openai(o) for o in outils] if outils else []

        messages: list[dict[str, Any]] = []
        if systeme:
            messages.append({"role": "system", "content": systeme})
        messages.append({"role": "user", "content": prompt})

        texte_final = ""

        try:
            _ml = modele_utilise.lower()
            _est_reasoning = _ml.startswith("gpt-5") or _ml.startswith("o1") or _ml.startswith("o3") or _ml.startswith("o4")
            _max_out = min(settings.IA_MAX_TOKENS, 16000)
            for _ in range(max_tours):
                kwargs: dict[str, Any] = {
                    "model": modele_utilise,
                    "messages": messages,
                }
                if _est_reasoning:
                    kwargs["max_completion_tokens"] = _max_out
                else:
                    kwargs["max_tokens"] = _max_out
                    kwargs["temperature"] = temperature
                if outils_gpt:
                    kwargs["tools"] = outils_gpt
                    kwargs["tool_choice"] = "auto"

                response = await self._gpt.chat.completions.create(**kwargs)

                if response.usage:
                    tokens_input_total += response.usage.prompt_tokens
                    tokens_output_total += response.usage.completion_tokens

                choice = response.choices[0]
                msg = choice.message

                # Conserver le message assistant dans l'historique
                assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
                if msg.tool_calls:
                    assistant_msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in msg.tool_calls
                    ]
                messages.append(assistant_msg)

                # Terminé ?
                if choice.finish_reason == "stop" or not msg.tool_calls:
                    texte_final = msg.content or ""
                    break

                # Exécuter les outils (en parallèle si plusieurs)
                async def _exec_un(tc):
                    try:
                        params = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        params = {}
                    try:
                        result = await executeur_outil(tc.function.name, params)
                    except Exception as exc:
                        result = f"ERREUR outil {tc.function.name}: {exc}"
                    return tc.id, str(result)

                resultats = await asyncio.gather(*[_exec_un(tc) for tc in msg.tool_calls])
                for tool_id, resultat in resultats:
                    messages.append({"role": "tool", "tool_call_id": tool_id, "content": resultat})

        except Exception as exc:
            logger.warning(f"[IAClient] GPT tool-use échoué ({exc})")
            # Si primaire=gpt et GPT vient d'échouer, essayer Claude tool-use comme fallback
            if primaire == "gpt":
                rep_claude = await _try_claude_outils()
                if rep_claude is not None:
                    rep_claude.fallback_utilise = True
                    asyncio.ensure_future(self._persister_cout(rep_claude, module, user_id))
                    return rep_claude
            logger.warning("[IAClient] → fallback sans outils")
            reponse_fb = await self.appeler(prompt=prompt, mode=mode, systeme=systeme)
            reponse_fb.tokens_input += tokens_input_total
            reponse_fb.tokens_output += tokens_output_total
            asyncio.ensure_future(self._persister_cout(reponse_fb, module, user_id))
            return reponse_fb

        reponse = ReponseIA(
            contenu=texte_final,
            modele_utilise=modele_utilise,
            tokens_input=tokens_input_total,
            tokens_output=tokens_output_total,
            temps_ms=(time.monotonic() - debut) * 1000,
        )
        asyncio.ensure_future(self._persister_cout(reponse, module, user_id))
        return reponse

    @staticmethod
    def encoder_image(chemin: str) -> str:
        with open(chemin, "rb") as f:
            return base64.standard_b64encode(f.read()).decode()

    def rapport_metriques(self) -> dict:
        return {
            modele: {
                "total": m.total_requetes,
                "succes": m.requetes_succes,
                "echecs": m.requetes_echec,
                "taux_succes": f"{m.taux_succes:.1%}",
                "temps_moyen_ms": round(m.temps_reponse_moyen, 1),
                "cout_total_usd": round(m.cout_total_usd, 4),
                "circuit_ouvert": self._circuit_breakers[modele].est_ouvert,
            }
            for modele, m in self._metriques.items()
        }


# Instance singleton
ia_client = IAClient()
