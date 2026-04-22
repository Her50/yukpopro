"""
YukpoAssurance — Client IA multi-modèle  (v3 — Production-grade)
Orchestration Claude (primaire) + GPT-4o (fallback)
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

# ── Tarifs API mis à jour (USD / token) ──────────────────────────────────────
TARIFS_INPUT = {
    "claude-opus-4-6":             15.0  / 1_000_000,
    "claude-sonnet-4-6":            3.0  / 1_000_000,  # Sonnet 4.6 — rapport qualité/prix optimal
    "claude-haiku-4-5-20251001":    0.25 / 1_000_000,
    "gpt-4o":                       2.5  / 1_000_000,
    "gpt-4o-mini":                  0.15 / 1_000_000,
}
TARIFS_OUTPUT = {
    "claude-opus-4-6":             75.0  / 1_000_000,
    "claude-sonnet-4-6":           15.0  / 1_000_000,
    "claude-haiku-4-5-20251001":    1.25 / 1_000_000,
    "gpt-4o":                      10.0  / 1_000_000,
    "gpt-4o-mini":                  0.60 / 1_000_000,
}


class ModeIA(str, Enum):
    PRECISION  = "precision"    # États CIMA, calculs réglementaires — temp 0.1
    ANALYSE    = "analyse"      # Fraude, souscription, sinistres — temp 0.3
    REDACTION  = "redaction"    # Rapports, courriers — temp 0.4
    COPILOTE   = "copilote"     # Assistant quotidien — temp 0.5
    COMMERCIAL = "commercial"   # Offres, communication client — temp 0.7


class ModelePrioritaire(str, Enum):
    CLAUDE_OPUS    = "claude-opus-4-6"
    CLAUDE_SONNET  = "claude-sonnet-4-6"       # Optimal pour CIMA/sinistres/rédaction
    CLAUDE_HAIKU   = "claude-haiku-4-5-20251001"
    GPT4O          = "gpt-4o"                  # Primaire pour Vision/OCR et commercial


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
    1. GPT-4o en priorité — modèle primaire pour tous les modes
    2. Claude Opus — fallback automatique si GPT indisponible
    3. Claude Haiku — tâches légères si forcé explicitement

    Améliorations v2 :
    - Circuit breaker par modèle
    - Cache Redis transparent (hash(prompt+systeme) → réponse)
    - Batch API corrigée (asyncio.to_thread)
    - Alertes coût dépassement budget
    """

    def __init__(self):
        # GPT-4o est le modèle primaire — clé OpenAI obligatoire
        # timeout=15s + max_retries=1 = 30s max → confortable dans la fenêtre copilote de 45s
        self._gpt = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=15.0, max_retries=1)
        # Claude = fallback uniquement — initialisé seulement si clé présente ET non-placeholder
        _claude_key = settings.CLAUDE_API_KEY or ""
        _claude_valide = (
            _claude_key.startswith("sk-ant-")
            and len(_claude_key) > 40
            and "CONFIGURER" not in _claude_key.upper()
            and "YOUR" not in _claude_key.upper()
            and "CLE" not in _claude_key.upper()
        )
        self._claude = (
            anthropic.AsyncAnthropic(api_key=_claude_key, timeout=20.0)
            if _claude_valide
            else None
        )
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
            if modele in (ModelePrioritaire.CLAUDE_OPUS, ModelePrioritaire.CLAUDE_HAIKU):
                reponse = await self._appel_claude(
                    prompt=prompt, modele=modele.value, temperature=temperature,
                    systeme=systeme, images_b64=images_b64, json_attendu=json_attendu,
                    max_tokens=max_tokens,
                )
            else:
                reponse = await self._appel_gpt(
                    prompt=prompt, temperature=temperature,
                    systeme=systeme, images_b64=images_b64, json_attendu=json_attendu,
                    max_tokens=max_tokens,
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

        # GPT-4o supporte au maximum 16 384 tokens en sortie
        _GPT4O_MAX_TOKENS = 16000
        _tokens_demandes = min(max_tokens or settings.IA_MAX_TOKENS, _GPT4O_MAX_TOKENS)
        _modele = (
            settings.GPT_MODEL_FALLBACK
            if _tokens_demandes <= 20
            else getattr(settings, "GPT_MODEL_PRIMAIRE", settings.GPT_MODEL_FALLBACK)
        )

        kwargs: dict[str, Any] = {
            "model": _modele,
            "max_tokens": _tokens_demandes,
            "temperature": temperature,
            "messages": messages,
        }
        if json_attendu:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self._gpt.chat.completions.create(**kwargs)

        if not response.choices or len(response.choices) == 0:
            raise ValueError("GPT-4o a retourné une réponse sans choix")
        texte = response.choices[0].message.content or ""
        if not texte.strip():
            raise ValueError("GPT-4o a retourné un texte vide")

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
        OCR/analyse d'image : GPT-4o en premier, Claude Opus en fallback.
        Un seul appel — pas de parallèle, pas de double coût.
        Suit la même stratégie que appeler() mais forcé sur Vision.
        """
        temperature = self._temperature_par_mode(mode)
        cb_gpt = self._circuit_breakers[ModelePrioritaire.GPT4O.value]

        # 1. GPT-4o (primaire Vision)
        if not cb_gpt.est_ouvert:
            debut = time.monotonic()
            try:
                reponse = await self._appel_gpt(
                    prompt=prompt, temperature=temperature, systeme=None,
                    images_b64=[image_b64], json_attendu=True,
                )
                self._enregistrer_succes(ModelePrioritaire.GPT4O.value, time.monotonic() - debut, reponse)
                cb_gpt.enregistrer_succes()
                return reponse
            except Exception as e:
                logger.warning(f"[IAClient/Vision] GPT-4o échoué: {e} → fallback Claude")
                self._enregistrer_echec(ModelePrioritaire.GPT4O.value)
                cb_gpt.enregistrer_echec()

        # 2. Claude Opus (fallback Vision)
        cb_claude = self._circuit_breakers[ModelePrioritaire.CLAUDE_OPUS.value]
        if cb_claude.est_ouvert:
            raise RuntimeError("Vision IA indisponible — GPT-4o et Claude en circuit ouvert")

        debut = time.monotonic()
        reponse = await self._appel_claude(
            prompt=prompt, modele=settings.CLAUDE_MODEL_PRIMAIRE,
            temperature=temperature, systeme=None,
            images_b64=[image_b64], json_attendu=True,
        )
        reponse.fallback_utilise = True
        self._enregistrer_succes(ModelePrioritaire.CLAUDE_OPUS.value, time.monotonic() - debut, reponse)
        cb_claude.enregistrer_succes()
        return reponse

    # ─── Utilitaires internes ─────────────────────────────────────────────────

    def _choisir_modele(self, mode: ModeIA) -> ModelePrioritaire:
        """
        Sélection du modèle — GPT-4o primaire sur tous les modes.
        Claude Sonnet/Opus = fallback automatique si GPT-4o indisponible.
        Claude Opus reste disponible via forcer_modele=ModelePrioritaire.CLAUDE_OPUS.
        """
        # GPT-4o primaire sur tous les modes — Claude en fallback si clé valide
        return ModelePrioritaire.GPT4O

    def _temperature_par_mode(self, mode: ModeIA) -> float:
        mapping = {
            ModeIA.PRECISION:  settings.IA_TEMPERATURE_PRECISION,
            ModeIA.ANALYSE:    0.3,
            ModeIA.REDACTION:  settings.IA_TEMPERATURE_REDACTION,
            ModeIA.COPILOTE:   0.5,
            ModeIA.COMMERCIAL: settings.IA_TEMPERATURE_CREATIVE,
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
    ) -> ReponseIA:
        """Fallback : Claude si GPT-4o indisponible (clé CLAUDE_API_KEY requise)."""
        if self._claude is None:
            raise RuntimeError("Service IA indisponible — configurez CLAUDE_API_KEY comme fallback")
        cb = self._circuit_breakers.get(settings.CLAUDE_MODEL_PRIMAIRE)
        if cb and cb.est_ouvert:
            raise RuntimeError("Tous les modèles IA sont indisponibles (circuit breakers ouverts)")
        try:
            reponse = await self._appel_claude(
                prompt=prompt,
                modele=settings.CLAUDE_MODEL_PRIMAIRE,
                temperature=self._temperature_par_mode(mode),
                systeme=systeme,
                images_b64=images_b64,
                json_attendu=json_attendu,
                max_tokens=max_tokens or settings.IA_MAX_TOKENS,
            )
            self._enregistrer_succes(settings.CLAUDE_MODEL_PRIMAIRE, time.monotonic() - debut, reponse)
            return reponse
        except Exception as e:
            logger.error(f"[IAClient] Fallback Claude aussi échoué: {e}")
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
        Boucle tool-use async (GPT-4o primaire).

        Le LLM peut appeler plusieurs outils avant de produire sa réponse finale.
        Tous les tokens de tous les tours sont accumulés et persistés ensemble.
        Fallback transparent vers appeler() sans outils si GPT-4o indisponible.
        """
        temperature = self._temperature_par_mode(mode)
        debut = time.monotonic()
        tokens_input_total = 0
        tokens_output_total = 0
        modele_utilise = getattr(settings, "GPT_MODEL_PRIMAIRE", settings.GPT_MODEL_FALLBACK)
        outils_gpt = [self._outil_anthropic_vers_openai(o) for o in outils] if outils else []

        messages: list[dict[str, Any]] = []
        if systeme:
            messages.append({"role": "system", "content": systeme})
        messages.append({"role": "user", "content": prompt})

        texte_final = ""

        try:
            for _ in range(max_tours):
                kwargs: dict[str, Any] = {
                    "model": modele_utilise,
                    "max_tokens": min(settings.IA_MAX_TOKENS, 16000),
                    "temperature": temperature,
                    "messages": messages,
                }
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
            logger.warning(f"[IAClient] appeler_avec_outils échoué ({exc}) → fallback sans outils")
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
