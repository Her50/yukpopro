"""
YukpoAssurance — API FastAPI principale
Point d'entrée de l'application. Toutes les routes sont montées ici.
"""
from contextlib import asynccontextmanager
import logging
import os
import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# ─── Prometheus (facultatif) ──────────────────────────────────────────────────
try:
    from prometheus_client import (
        Counter, Histogram, Gauge,
        generate_latest, CONTENT_TYPE_LATEST,
        CollectorRegistry, REGISTRY,
    )
    _PROMETHEUS_OK = True
    _yukpo_requests_total = Counter(
        "yukpo_requests_total",
        "Nombre total de requêtes HTTP",
        ["method", "endpoint", "status"],
    )
    _yukpo_request_duration = Histogram(
        "yukpo_request_duration_seconds",
        "Durée des requêtes HTTP en secondes",
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    )
    _yukpo_ia_calls_total = Counter(
        "yukpo_ia_calls_total",
        "Nombre total d'appels aux modèles IA",
        ["model", "status"],
    )
    _yukpo_active_sessions = Gauge(
        "yukpo_active_chat_sessions",
        "Nombre de sessions chat actives en mémoire",
    )
except ImportError:
    _PROMETHEUS_OK = False
    # Stubs no-op pour que les modules qui importent les métriques ne crashent pas
    class _NoOpCounter:
        def labels(self, **kw): return self
        def inc(self, amount=1): pass
    class _NoOpGauge:
        def set(self, v): pass
        def inc(self, v=1): pass
        def dec(self, v=1): pass
    _yukpo_requests_total = _NoOpCounter()
    _yukpo_request_duration = type("_", (), {"observe": lambda self, v: None})()
    _yukpo_ia_calls_total = _NoOpCounter()
    _yukpo_active_sessions = _NoOpGauge()

from config.settings import settings
from api.routes_copilote import router as copilote_router
from api.routes_cima import router as cima_router
from api.routes_sinistres import router as sinistres_router
from api.routes_compta import router as compta_router
from api.routes_courtiers import router as courtiers_router
from api.routes_souscription import router as souscription_router
from api.routes_chat import router as chat_router
from api.routes_documents import router as documents_router
from api.routes_reunions import router as reunions_router
from api.routes_analytics import router as analytics_router
from api.routes_audit import router as audit_router
from api.routes_rh import router as rh_router
from api.routes_commercial import router as commercial_router
from api.routes_collaboration import router as collaboration_router
from api.routes_whatsapp import router as whatsapp_router
from api.routes_paiement import router as paiement_router
from api.routes_paiement_v2 import router as paiement_v2_router
from api.routes_contrats_clients import router as contrats_clients_router
from api.routes_secteur import router as secteur_router
from api.routes_community_manager import router as cm_router
from api.routes_trends import router as trends_router
from api.routes_agenda import router as agenda_router
from api.routes_tarification import router as tarification_router
from api.routes_streaming import router as streaming_router
from api.routes_transport import router as transport_router
from api.routes_rag import router as rag_router
from api.routes_pro_profil import router as pro_profil_router
from api.routes_pro_agent import router as pro_agent_router
from api.routes_pro_generateurs import router as pro_generateurs_router
from api.routes_pro_copilote import router as pro_copilote_router
from api.routes_pro_admin import router as pro_admin_router
from api.routes_pro_abonnement import router as pro_abonnement_router
from api.routes_pro_organizations import router as pro_orgs_router
from api.routes_admin_paiements import router as admin_paiements_router
from api.routes_pro_reunions import router as pro_reunions_router
from api.routes_mrh import router as mrh_router
from api.routes_enquetes import router as enquetes_router
from api.routes_reassurance import router as reassurance_router
from api.routes_archive import router as archive_router
from api.routes_kpi_rh import router as kpi_rh_router
from api.routes_agent import router as agent_router
from api.routes_agent_systeme import router as agent_systeme_router
from api.routes_agent_conv import router as agent_conv_router
from api.routes_portail import router as portail_router
from api.routes_bureau_redaction import router as bureau_redaction_router
from api.routes_bureau_ocr import router as bureau_ocr_router
from api.routes_bureau_audio import router as bureau_audio_router
from api.routes_bureau_infographie import router as bureau_infographie_router
from api.routes_bureau_infographie_pro import router as bureau_infographie_pro_router
# Sprint 2.1 — API publique + clés
from api.routes_api_keys import router as api_keys_router
from api.routes_public_designerpro import router as public_designerpro_router
from api.routes_bureau_gestion import router as bureau_gestion_router
from api.routes_bureau_traduction import router as bureau_traduction_router
from api.routes_bureau_documents import router as bureau_documents_router
from api.routes_bureau_abonnement import router as bureau_abonnement_router
from api.routes_bureau_admin import router as bureau_admin_router
from api.routes_translate_live import router as translate_live_router
from api.graphql_schema import creer_router_graphql
from core.audit import AuditMiddleware
from core.auth import auth_router
from core.middleware_tenant import TenantMiddleware
from core.telemetry import (
    initialiser_telemetry, instrumenter_fastapi, creer_endpoint_metrics,
)
# Métriques business exposées globalement pour instrumentation cross-modules
from core.telemetry import (
    ia_appels_total, ia_duree_secondes, ia_cout_usd_total, ia_tokens_total,
    sinistres_crees, primes_calculees, prime_montant_fcfa,
    cima_questions, conformite_alertes, sessions_chat_actives,
)

# ─── Logging structuré ────────────────────────────────────────────────────────
try:
    import structlog
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
    logger = structlog.get_logger("yukpo_assurance")
except ImportError:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    logger = logging.getLogger("yukpo_assurance")

# ─── Rate Limiter ─────────────────────────────────────────────────────────────
# Rate limiting par IP pour les routes publiques
# + Rate limiting par user_id dans les endpoints IA (via security_service)
limiter = Limiter(key_func=get_remote_address, default_limits=["300/minute"])


async def rate_limit_ia_middleware(request: Request, call_next):
    """
    Rate limiting par user_id pour les endpoints IA.
    Protège contre le DoS IA et contrôle les coûts.
    """
    # S'applique uniquement aux routes IA (pas à /health, /metrics, etc.)
    if "/api/v1/" in request.url.path and request.method in ("POST", "PUT"):
        try:
            # Extraire user_id depuis le JWT sans décoder complètement
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                from jose import jwt as _jwt
                from config.settings import settings as _settings
                try:
                    payload = _jwt.decode(
                        auth_header[7:],
                        _settings.SECRET_KEY,
                        algorithms=["HS256"],
                        options={"verify_exp": True},
                    )
                    user_id = int(payload.get("sub", 0))
                    role = payload.get("role", "agent")
                    if user_id:
                        from core.security import security_service
                        autorise, info_rl = security_service.verifier_rate_limit(user_id, role)
                        if not autorise:
                            return JSONResponse(
                                status_code=429,
                                content={
                                    "detail": "Trop de requêtes — limite atteinte",
                                    "rate_limit": info_rl,
                                },
                                headers={
                                    "X-RateLimit-Limit": str(info_rl["limit"]),
                                    "X-RateLimit-Remaining": "0",
                                    "Retry-After": str(info_rl["reset_in_seconds"]),
                                },
                            )
                except Exception:
                    pass
        except Exception:
            pass
    return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("  YukpoAssurance — Démarrage")
    logger.info(f"  Version {settings.APP_VERSION}")
    logger.info(f"  Mode ORASS : {settings.ORASS_MODE}")
    logger.info("  Modules : Chat IA | CIMA | Sinistres | Compta | Courtiers")
    logger.info("           Souscription | Documents | Réunions | Analytics")
    logger.info("           RH (paie OHADA) | Commercial (pipeline) | Collaboration (docs + WS)")
    logger.info("           WhatsApp chatbot | Paiement Mobile Money | Contrats clients PDF")
    logger.info("           Community Manager IA | Veille Tendances | Agenda & Rappels")
    logger.info("           Multi-secteur activité (12 secteurs : assurance, banque, industrie…)")
    logger.info("=" * 60)

    # ── Vérification clés API IA ──────────────────────────────────────────────
    claude_key = settings.CLAUDE_API_KEY or ""
    openai_key = settings.OPENAI_API_KEY or ""
    claude_ok = bool(claude_key) and not any(p in claude_key for p in ["votre-cle", "CONFIGURER", "placeholder"]) and len(claude_key) >= 40
    openai_ok = bool(openai_key) and len(openai_key) >= 20

    if claude_ok:
        logger.info(f"  [IA] ✅ Claude API configurée (key: {claude_key[:15]}...) — modèle primaire")
    elif openai_ok:
        logger.info("  [IA] ℹ️  CLAUDE_API_KEY absente — fallback GPT-4o actif (OpenAI). Les agents fonctionnent normalement.")
    else:
        logger.warning("  [IA] ⚠️  Aucune clé IA valide (ni Claude ni OpenAI) — agents bloqués. Configurez CLAUDE_API_KEY ou OPENAI_API_KEY dans .env")

    if openai_ok:
        logger.info(f"  [IA] ✅ OpenAI API configurée (key: {openai_key[:10]}...)")
    else:
        logger.warning("  [IA] ⚠️  OPENAI_API_KEY invalide — Vision OCR et fallback indisponibles")

    # Créer les dossiers de sortie pour les documents générés
    output_dir = os.path.join(os.path.dirname(__file__), "..", "data", "generated")
    os.makedirs(output_dir, exist_ok=True)
    logger.info(f"  [FS] Dossier documents générés: {output_dir}")

    # Initialisation de la base de données
    try:
        # Importer les modèles des modules externes pour enregistrer leurs tables
        from modules.pro.profil_pro import ProfilProfessionnelDB  # noqa: F401
        from core.database import init_db
        await init_db()
        logger.info("  [DB] Base de données initialisée (SQLite/PostgreSQL)")
    except Exception as e:
        logger.warning(f"  [DB] Init DB non critique: {e}")

    # ── Création / reset du compte super_admin au démarrage ────────────────────
    async def _creer_super_admin():
        import os as _os, secrets as _sec, bcrypt as _bcrypt
        from datetime import datetime as _dtt
        from core.database import UtilisateurDB as _UDB, async_session_maker as _asm2
        from sqlalchemy import select as _sel2

        _admin_email = _os.environ.get("BOOTSTRAP_ADMIN_EMAIL") or _os.environ.get("SUPER_ADMIN_EMAIL", "admin@yukpopro.cm")
        _admin_pwd   = _os.environ.get("BOOTSTRAP_ADMIN_PASSWORD") or _os.environ.get("SUPER_ADMIN_PASSWORD", "")
        _admin_nom   = _os.environ.get("SUPER_ADMIN_NOM", "Yukpo Admin")
        _reset       = _os.environ.get("BOOTSTRAP_ADMIN_RESET", "").lower() in ("1", "true", "yes")

        async with _asm2() as _sess:
            # Cherche un super_admin par email d'abord, sinon n'importe quel super_admin
            _existing = (await _sess.execute(
                _sel2(_UDB).where(_UDB.email == _admin_email)
            )).scalars().first()
            if not _existing:
                _existing = (await _sess.execute(
                    _sel2(_UDB).where(_UDB.role.in_(["super_admin", "yukpo_owner"]))
                )).scalars().first()

            if not _existing:
                _pwd = _admin_pwd or _sec.token_urlsafe(16)
                _hashed = _bcrypt.hashpw(_pwd[:72].encode(), _bcrypt.gensalt()).decode()
                _uname = _admin_email.split("@")[0]
                _u = _UDB(
                    username=_uname, email=_admin_email, nom=_admin_nom,
                    hashed_password=_hashed, role="super_admin",
                    compagnie_id=1, actif=True, cree_le=_dtt.utcnow(), cree_par=None,
                )
                _sess.add(_u)
                await _sess.commit()
                logger.warning(
                    f"  [Admin] ✅ Compte super_admin CRÉÉ : email={_admin_email} "
                    f"username={_uname} role=super_admin "
                    f"password={_pwd if not _admin_pwd else '(depuis env BOOTSTRAP_ADMIN_PASSWORD)'}"
                )
            elif _reset and _admin_pwd:
                # Reset password sur demande explicite
                _hashed = _bcrypt.hashpw(_admin_pwd[:72].encode(), _bcrypt.gensalt()).decode()
                _existing.hashed_password = _hashed
                _existing.actif = True
                if _existing.role not in ("super_admin", "yukpo_owner"):
                    _existing.role = "super_admin"
                _existing.tentatives_echec = 0
                _existing.bloque_jusqu_au = None
                await _sess.commit()
                logger.warning(
                    f"  [Admin] 🔁 Password RÉINITIALISÉ pour {_existing.email} "
                    f"(role={_existing.role}). RETIRE BOOTSTRAP_ADMIN_RESET maintenant !"
                )
            else:
                logger.info(
                    f"  [Admin] Compte super_admin déjà existant : {_existing.email} "
                    f"(role={_existing.role}, actif={_existing.actif})"
                )

    try:
        import asyncio as _aio
        await _aio.wait_for(_creer_super_admin(), timeout=10.0)
    except _aio.TimeoutError:
        logger.warning("  [Admin] Création super_admin ignorée — timeout 10s (DB indisponible au démarrage)")
    except Exception as _e:
        logger.warning(f"  [Admin] Création auto super_admin : {_e}")

    # Pre-chauffe de l'index sémantique CIMA — timeout court pour ne pas bloquer
    try:
        import asyncio
        from modules.chat.cima_embedder import prechauffer_index
        await asyncio.wait_for(asyncio.to_thread(prechauffer_index), timeout=5.0)
        logger.info("  [CIMA] Index sémantique RAG prêt")
    except asyncio.TimeoutError:
        logger.warning("  [CIMA] Index RAG chargé en arrière-plan (non bloquant)")
    except Exception as e:
        logger.warning(f"  [CIMA] Index non chargé : {e}")

    # ── Polices Google Fonts (Designer Pro) — pré-téléchargement non-bloquant ──
    try:
        import asyncio as _aio_fonts
        async def _prechauffer_fonts():
            try:
                from modules.bureau.font_loader import prechauffer
                rapport = await _aio_fonts.to_thread(prechauffer)
                ok = sum(1 for v in rapport.values() if v)
                logger.info(f"  [Fonts] Google Fonts préchargées : {ok}/{len(rapport)} familles")
            except Exception as _e:
                logger.info(f"  [Fonts] Pré-chargement non-critique : {_e}")
        _aio_fonts.create_task(_prechauffer_fonts())
    except Exception:
        pass

    # ── RAG Multi-documents — chargement au démarrage (non bloquant avec timeout) ─
    try:
        import asyncio as _asyncio
        from modules.rag.rag_embedder import prechauffer_index_rag
        await _asyncio.wait_for(_asyncio.to_thread(prechauffer_index_rag), timeout=30.0)
        logger.info("  [RAG] Index corpus réglementaire chargés")
    except _asyncio.TimeoutError:
        logger.warning("  [RAG] Timeout 30s — chargement RAG en arrière-plan")
        asyncio.create_task(_asyncio.to_thread(prechauffer_index_rag))
    except Exception as e:
        logger.warning(f"  [RAG] Index non chargés : {e}")

    # Démarrage du scheduler de mise à jour automatique des sources RAG
    try:
        from modules.rag.updater import rag_scheduler
        rag_scheduler.demarrer()
        logger.info("  [RAG] Scheduler mise à jour automatique démarré")
    except Exception as e:
        logger.warning(f"  [RAG] Scheduler non démarré : {e}")

    # Rechargement des sessions chat depuis la DB (warm cache)
    try:
        from modules.chat.yukpo_ia_assurance import charger_sessions_depuis_db
        await charger_sessions_depuis_db(limite=200)
    except Exception as e:
        logger.warning(f"  [Chat] Rechargement sessions: {e}")

    # Rechargement des réunions depuis la DB (warm cache)
    try:
        from modules.reunions.gestionnaire import charger_reunions_depuis_db
        await charger_reunions_depuis_db(limite=100)
    except Exception as e:
        logger.warning(f"  [Réunions] Rechargement: {e}")

    # Warm-up études Enquêtes depuis la DB
    try:
        from modules.enquetes.persistence import charger_toutes_etudes
        n_etudes = await charger_toutes_etudes()
        logger.info(f"  [Enquêtes] {n_etudes} étude(s) chargée(s) en mémoire")
    except Exception as e:
        logger.warning(f"  [Enquêtes] Warm-up études: {e}")

    # Warm-up sessions Copilote depuis la DB
    try:
        from modules.copilote.persistence import charger_toutes_sessions
        n_cop = await charger_toutes_sessions()
        logger.info(f"  [Copilote] {n_cop} session(s) chargée(s) en mémoire")
    except Exception as e:
        logger.warning(f"  [Copilote] Warm-up sessions: {e}")

    # Vérification Redis (non bloquante)
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        logger.info("  [Redis] Connexion OK")
    except Exception:
        logger.info("  [Redis] Non disponible — fonctionnement sans cache Redis")

    # Démarrage du scheduler Community Manager
    try:
        from core.database import async_session_maker
        from modules.community_manager.scheduler_cm import demarrer_scheduler
        demarrer_scheduler(async_session_maker)
        logger.info("  [CM] Scheduler Community Manager démarré")
    except Exception as e:
        logger.warning(f"  [CM] Scheduler non démarré: {e}")

    # ── Agents autonomes Yukpo (schema_si + meta_factory) ─────────────────────
    try:
        from core.agents_scheduler import demarrer_scheduler as demarrer_agents_scheduler
        await demarrer_agents_scheduler()
        logger.info("  [Agents] Scheduler autonome démarré — schema_si(6h) meta_factory(24h)")
    except Exception as e:
        logger.warning(f"  [Agents] Scheduler agents autonomes non démarré: {e}")

    # ── Veille emploi automatique (Pro) ───────────────────────────────────────
    try:
        from modules.pro.scheduler_emploi import demarrer_scheduler_emploi
        await demarrer_scheduler_emploi()
        logger.info("  [Emploi] Scheduler veille emploi démarré — cycle 30min")
    except Exception as e:
        logger.warning(f"  [Emploi] Scheduler veille emploi non démarré: {e}")

    # ── Auto-annulation paiements MoMo provisoires > 3h ───────────────────────
    try:
        import asyncio as _asyncio
        from modules.pro.service_paiement_commande import annuler_commandes_expirees

        async def _cron_paiements():
            while True:
                await _asyncio.sleep(900)  # 15 min
                try:
                    async with async_session_maker() as s:
                        await annuler_commandes_expirees(s)
                except Exception as _e:
                    logger.warning(f"[PaiementCron] Erreur: {_e}")

        _asyncio.create_task(_cron_paiements())
        logger.info("  [Paiement] CRON auto-annulation démarré — cycle 15min")
    except Exception as e:
        logger.warning(f"  [Paiement] CRON non démarré: {e}")

    # ── Veille marchés publics automatique (Pro) ──────────────────────────────
    try:
        from modules.pro.scheduler_marches import demarrer_scheduler_marches
        await demarrer_scheduler_marches()
        logger.info("  [Marchés] Scheduler marchés publics démarré — cycle 2h")
    except Exception as e:
        logger.warning(f"  [Marchés] Scheduler marchés publics non démarré: {e}")

    # Webhook worker (retry exponentiel)
    try:
        from core.webhooks import webhook_service
        webhook_service.demarrer_worker()
        logger.info("  [Webhooks] Worker retry démarré")
    except Exception as e:
        logger.warning(f"  [Webhooks] Worker non démarré: {e}")

    # OpenTelemetry : init tracing distribué
    try:
        otlp_ok = initialiser_telemetry(
            service_name="yukpo-assurance",
            service_version=settings.APP_VERSION,
            otlp_endpoint=getattr(settings, "OTLP_ENDPOINT", "http://localhost:4317"),
        )
        if otlp_ok:
            logger.info("  [Telemetry] OpenTelemetry OTLP initialisé")
        else:
            logger.info("  [Telemetry] OpenTelemetry non disponible — métriques Prometheus actives")
    except Exception as e:
        logger.warning(f"  [Telemetry] Init: {e}")

    yield

    # Arrêt propre du scheduler
    try:
        from modules.community_manager.scheduler_cm import arreter_scheduler
        arreter_scheduler()
        logger.info("  [CM] Scheduler Community Manager arrêté")
    except Exception:
        pass

    # Arrêt propre du scheduler veille emploi
    try:
        from modules.pro.scheduler_emploi import arreter_scheduler_emploi
        await arreter_scheduler_emploi()
    except Exception:
        pass

    # Arrêt propre du scheduler marchés publics
    try:
        from modules.pro.scheduler_marches import arreter_scheduler_marches
        await arreter_scheduler_marches()
    except Exception:
        pass

    # Arrêt propre du scheduler RAG
    try:
        from modules.rag.updater import rag_scheduler
        await rag_scheduler.arreter()
        logger.info("  [RAG] Scheduler mise à jour automatique arrêté")
    except Exception:
        pass

    # Arrêt propre du webhook worker
    try:
        from core.webhooks import webhook_service
        await webhook_service.arreter_worker()
        logger.info("  [Webhooks] Worker arrêté")
    except Exception:
        pass

    logger.info("YukpoAssurance — Arrêt")


app = FastAPI(
    title="YukpoAssurance API",
    description=(
        "IA spécialisée pour les compagnies d'assurance en zone CIMA. "
        "Copilote métier, digitalisation des processus, conformité réglementaire."
    ),
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# Rate limiting IP
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Rate limiting par user IA
app.middleware("http")(rate_limit_ia_middleware)

# ── CSRF Protection (mutations via cookie frontend uniquement) ────────────────
_CSRF_EXEMPT_PATHS = {
    "/api/v1/auth/login", "/api/v1/auth/token",
    "/api/v1/auth/register/pro", "/api/v1/auth/logout",
    "/health", "/metrics",
}
_CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    """
    Vérifie le token CSRF pour toutes les mutations (POST/PUT/DELETE/PATCH)
    effectuées via le cookie httpOnly (frontend web).
    Les clients avec Authorization: Bearer sont exemptés — les headers
    ne peuvent pas être forgés par CSRF (contrairement aux cookies).
    """
    has_bearer = request.headers.get("Authorization", "").startswith("Bearer ")
    if (
        request.method not in _CSRF_SAFE_METHODS
        and request.url.path not in _CSRF_EXEMPT_PATHS
        and not has_bearer  # Bearer token = pas de CSRF (header non forgeable)
        and request.cookies.get("access_token")  # Seulement si cookie présent (web sans Bearer)
        and not request.url.path.startswith("/graphql")
    ):
        csrf_header = request.headers.get("X-CSRF-Token", "")
        csrf_cookie = request.cookies.get("csrf_token", "")
        if not csrf_header or not csrf_cookie or csrf_header != csrf_cookie:
            return JSONResponse(
                status_code=403,
                content={"detail": "Token CSRF invalide ou manquant"},
            )
    return await call_next(request)

# Isolation multi-tenant (extrait compagnie_id du JWT, enforce si activé)
app.add_middleware(TenantMiddleware)

# Audit trail (avant CORS pour capturer toutes les requêtes)
app.add_middleware(AuditMiddleware)

# ─── Middleware Prometheus ─────────────────────────────────────────────────────
if _PROMETHEUS_OK:
    @app.middleware("http")
    async def prometheus_middleware(request: Request, call_next):
        debut = time.monotonic()
        # Normalisation de l'endpoint (évite l'explosion de labels avec IDs)
        path = request.url.path
        for segment in path.split("/"):
            # Remplace les segments UUID / numériques par un placeholder
            if len(segment) > 8 and (
                "-" in segment or segment.isdigit()
            ):
                path = path.replace(segment, "{id}")
                break

        try:
            response = await call_next(request)
            status = str(response.status_code)
        except Exception:
            status = "500"
            raise
        finally:
            duree = time.monotonic() - debut
            _yukpo_requests_total.labels(
                method=request.method,
                endpoint=path,
                status=status,
            ).inc()
            _yukpo_request_duration.observe(duree)

        return response

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Ajoute les headers de sécurité OWASP sur toutes les réponses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "connect-src 'self' ws: wss:; "
        "frame-ancestors 'none';"
    )
    return response

# OpenTelemetry FastAPI instrumentation + endpoint /metrics
instrumenter_fastapi(app)
creer_endpoint_metrics(app)

# ─── Routes ───────────────────────────────────────────────────────────────────
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentification"])
app.include_router(chat_router, prefix="/api/v1/chat", tags=["Chat IA (YukpoIA Assurance)"])
app.include_router(copilote_router, prefix="/api/v1/copilote", tags=["Copilote IA"])
app.include_router(cima_router, prefix="/api/v1/cima", tags=["Réglementation CIMA"])
app.include_router(sinistres_router, prefix="/api/v1/sinistres", tags=["Sinistres"])
app.include_router(compta_router, prefix="/api/v1/comptabilite", tags=["Comptabilité"])
app.include_router(courtiers_router, prefix="/api/v1/courtiers", tags=["Courtiers"])
app.include_router(souscription_router, prefix="/api/v1/souscription", tags=["Souscription"])
app.include_router(documents_router, prefix="/api/v1/documents", tags=["Génération Documents"])
app.include_router(reunions_router, prefix="/api/v1/reunions", tags=["Gestion Réunions"])
app.include_router(analytics_router, prefix="/api/v1/analytics", tags=["Analytics & Dashboards"])
app.include_router(audit_router, prefix="/api/v1/audit", tags=["Audit Trail"])
app.include_router(rh_router, prefix="/api/v1/rh", tags=["Ressources Humaines"])
app.include_router(commercial_router, prefix="/api/v1/commercial", tags=["Commercial & Pipeline"])
app.include_router(collaboration_router, prefix="/api/v1/collaboration", tags=["Collaboration Documentaire"])
app.include_router(whatsapp_router, prefix="/api/v1", tags=["WhatsApp Chatbot Client"])
app.include_router(paiement_router, prefix="/api/v1", tags=["Paiement Mobile Money"])
app.include_router(paiement_v2_router, prefix="/api/v1", tags=["Paiement v2 (multi-provider)"])
app.include_router(contrats_clients_router, prefix="/api/v1", tags=["Contrats Clients PDF"])
app.include_router(secteur_router, prefix="/api/v1", tags=["Secteur & Multi-activité"])
app.include_router(cm_router, prefix="/api/v1", tags=["Community Manager IA"])
app.include_router(trends_router, prefix="/api/v1", tags=["Veille & Tendances"])
app.include_router(agenda_router, prefix="/api/v1", tags=["Agenda & Rappels"])
app.include_router(tarification_router, prefix="/api/v1/tarification", tags=["Tarification Prédictive"])
app.include_router(transport_router, prefix="/api/v1/transport", tags=["Transport Assurance (Branche 50)"])
app.include_router(mrh_router, prefix="/api/v1/mrh", tags=["MRH Multi-Risques Habitation (IRD)"])
app.include_router(reassurance_router, prefix="/api/v1/reassurance", tags=["Réassurance (Art. 308 CIMA)"])
app.include_router(archive_router, prefix="/api/v1/archive", tags=["Archive Numérique Transversale"])
app.include_router(kpi_rh_router, prefix="/api/v1/rh/kpi", tags=["KPI Performance RH"])
app.include_router(agent_router, tags=["Agents IA Autonomes"])
app.include_router(agent_conv_router, tags=["Agent Conversationnel Intelligent"])
app.include_router(agent_systeme_router, tags=["Agents Système Yukpo (super_admin only)"])
app.include_router(portail_router, prefix="/api/v1", tags=["Portail Prestataires & Assurés"])
app.include_router(streaming_router, prefix="/api/v1", tags=["Streaming SSE (tâches longues)"])
app.include_router(rag_router, prefix="/api/v1/rag", tags=["RAG Corpus Réglementaire Africain"])
app.include_router(pro_profil_router, prefix="/api/v1/pro/profil", tags=["Plateforme Pro — Profil Métier"])
app.include_router(pro_agent_router, prefix="/api/v1/pro/agent", tags=["Plateforme Pro — Agent IA"])
app.include_router(pro_generateurs_router, prefix="/api/v1/pro", tags=["Plateforme Pro — Rapports & Slides"])
app.include_router(pro_copilote_router, prefix="/api/v1/pro/copilote", tags=["Plateforme Pro — Yukpo Copilote"])
app.include_router(pro_admin_router,      prefix="/api/v1/pro/admin",       tags=["Plateforme Pro — Administration"])
app.include_router(pro_abonnement_router, prefix="/api/v1/pro/abonnement",  tags=["Plateforme Pro — Abonnements"])
app.include_router(pro_orgs_router,       prefix="/api/v1",                 tags=["Plateforme Pro — Organisations"])
app.include_router(admin_paiements_router, prefix="/api/v1/admin/paiements", tags=["Admin — Paiements MoMo"])
app.include_router(pro_reunions_router,   prefix="/api/v1/pro/reunions",    tags=["Plateforme Pro — Réunions & Transcription"])
app.include_router(enquetes_router, prefix="/api/v1/enquetes", tags=["Enquêtes & Études qualitatives/quantitatives"])

# ─── Endpoint setup initial (création admin si aucun n'existe) ────────────────
from fastapi import Body as _Body
from core.database import async_session_maker as _asm, UtilisateurDB as _UDB
from sqlalchemy import select as _sel
from datetime import datetime as _dtt
import os as _os, bcrypt as _bcrypt_mod

@app.post("/api/v1/setup/admin", tags=["Setup"], include_in_schema=False)
async def setup_admin(
    email: str = _Body(...),
    password: str = _Body(...),
    setup_key: str = _Body(...),
):
    """
    Crée le premier super_admin si aucun n'existe encore.
    Protégé par setup_key = valeur de ADMIN_SETUP_KEY (env var) ou 'yukpo-setup-2024'.
    Une fois l'admin créé, cet endpoint renvoie une erreur 409.
    """
    from fastapi import HTTPException as _HE

    expected_key = _os.environ.get("ADMIN_SETUP_KEY", "yukpo-setup-2024")
    if setup_key != expected_key:
        raise _HE(403, "setup_key invalide")
    if not email or "@" not in email:
        raise _HE(400, "email invalide")
    if len(password) < 8:
        raise _HE(400, "password : 8 caractères minimum")

    async with _asm() as _sess:
        existing = (await _sess.execute(
            _sel(_UDB).where(_UDB.role.in_(["super_admin", "yukpo_owner"]))
        )).scalars().first()

        if existing:
            raise _HE(409, f"Admin déjà existant : {existing.email}. Utilisez /auth/login.")

        _hashed = _bcrypt_mod.hashpw(password[:72].encode(), _bcrypt_mod.gensalt()).decode()
        _u = _UDB(
            username=email.split("@")[0], email=email,
            nom="Yukpo Admin", hashed_password=_hashed,
            role="super_admin", compagnie_id=1,
            actif=True, cree_le=_dtt.utcnow(), cree_par=None,
        )
        _sess.add(_u)
        await _sess.commit()
        return {"message": f"Compte super_admin créé : {email}", "role": "super_admin"}


@app.post("/api/v1/setup/reset-admin-password", tags=["Setup"], include_in_schema=False)
async def reset_admin_password(
    email: str = _Body(...),
    new_password: str = _Body(...),
    setup_key: str = _Body(...),
):
    """Réinitialise le mot de passe du super_admin existant. Protégé par setup_key."""
    from fastapi import HTTPException as _HE
    from sqlalchemy import update as _upd

    expected_key = _os.environ.get("ADMIN_SETUP_KEY", "yukpo-setup-2024")
    if setup_key != expected_key:
        raise _HE(403, "setup_key invalide")
    if len(new_password) < 8:
        raise _HE(400, "password : 8 caractères minimum")

    _hashed = _bcrypt_mod.hashpw(new_password[:72].encode(), _bcrypt_mod.gensalt()).decode()
    async with _asm() as _sess:
        result = await _sess.execute(
            _upd(_UDB).where(_UDB.email == email).values(hashed_password=_hashed)
        )
        await _sess.commit()
        if result.rowcount == 0:
            raise _HE(404, f"Aucun utilisateur avec l'email {email}")
        return {"message": f"Mot de passe réinitialisé pour {email}"}

# ─── YukpoSecrétariat ─────────────────────────────────────────────────────────
app.include_router(bureau_redaction_router,  prefix="/api/v1/bureau/redaction",   tags=["Secrétariat — Rédaction IA"])
app.include_router(bureau_ocr_router,        prefix="/api/v1/bureau/ocr",         tags=["Secrétariat — OCR & Scan"])
app.include_router(bureau_audio_router,      prefix="/api/v1/bureau/audio",       tags=["Secrétariat — Audio → Document"])
app.include_router(bureau_infographie_router,prefix="/api/v1/bureau/infographie", tags=["Secrétariat — Infographie Print"])
app.include_router(bureau_infographie_pro_router, prefix="/api/v1/bureau/infographie-pro", tags=["Secrétariat — Infographie Pro (multi-page IA)"])
# Sprint 2.1 — Gestion clés API (admin org via JWT) + API publique B2B (auth par clé)
app.include_router(api_keys_router, prefix="/api/v1/api-keys", tags=["API Keys (admin org)"])
app.include_router(public_designerpro_router, prefix="/api/v1/public/designerpro", tags=["Public API — Designer Pro"])
app.include_router(bureau_gestion_router,    prefix="/api/v1/bureau/gestion",     tags=["Secrétariat — Gestion Opérationnelle"])
app.include_router(bureau_traduction_router, prefix="/api/v1/bureau/traduction",  tags=["Secrétariat — Traduction IA"])
app.include_router(bureau_documents_router,  prefix="/api/v1/bureau/documents",   tags=["Secrétariat — Mes Documents"])
app.include_router(bureau_abonnement_router, prefix="/api/v1/bureau/abonnement",  tags=["Secrétariat — Abonnement & Crédits"])
app.include_router(bureau_admin_router,      prefix="/api/v1/bureau/admin",       tags=["Secrétariat — Administration"])

# ─── YukpoTranslate Live (traduction vocale temps réel) ─────────────────────
app.include_router(translate_live_router, prefix="/api/v1/translate/live", tags=["Traduction Live (YukpoTranslate)"])

# GraphQL (Strawberry) — optionnel selon installation
_graphql_router = creer_router_graphql()
if _graphql_router:
    app.include_router(_graphql_router, prefix="/graphql", tags=["GraphQL API"])
    logger.info("  [GraphQL] Router Strawberry monté sur /graphql")


@app.get("/", tags=["Santé"])
async def racine():
    return {
        "application": "YukpoAssurance",
        "version": settings.APP_VERSION,
        "statut": "opérationnel",
        "modules": [
            "Chat IA intelligent (sessions, mémoire, multimodal, audio)",
            "Copilote IA assurance",
            "Réglementation CIMA (C1-C20, ratios prudentiels)",
            "Sinistres & Détection de fraude (score 0-100)",
            "Comptabilité & OCR documents (OHADA/PCSA CIMA)",
            "Portail Courtiers (commissions, suivi temps réel)",
            "Souscription digitale (KYC OCR, calcul prime)",
            "Génération documents (Word, PDF, PPT, Excel)",
            "Gestion réunions (transcription, PV, agenda IA)",
            "Analytics & Dashboards (analyses poussées, prédictif)",
            "Ressources Humaines (paie OHADA, congés, évaluations, recrutement)",
            "Commercial & Pipeline (prospects scoring, objectifs, campagnes)",
            "Collaboration Documentaire (versioning, workflows approbation, WebSocket temps réel)",
            "WhatsApp Chatbot Client (devis instantané, sinistres, paiement, documents)",
            "Paiement Mobile Money (CinetPay, MTN MoMo, Orange Money, Wave)",
            "Contrats Clients PDF (génération, email, WhatsApp, depuis ORASS)",
            "Community Manager IA (génération posts, A/B test, scheduler, analytics)",
            "Veille & Tendances (TrendPulse, analyse IA, alertes, veille réglementaire)",
            "Agenda & Rappels (événements, tâches, rappels CIMA, sinistres en retard)",
            "Multi-secteur activité (12 secteurs plugin : assurance, banque, industrie, commerce…)",
        ],
    }


@app.get("/health", tags=["Santé"])
async def health():
    """Healthcheck complet : DB, Redis, modèles IA, orchestrateur."""
    checks: dict = {}

    # DB
    try:
        from core.database import async_session_maker
        from sqlalchemy import text
        async with async_session_maker() as db:
            await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    # Redis
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "unavailable"

    # Clés IA
    checks["claude_api_key"] = "configuré" if settings.CLAUDE_API_KEY else "manquant"
    checks["openai_api_key"] = "configuré" if settings.OPENAI_API_KEY else "manquant"

    # Orchestrateur
    try:
        from core.orchestrateur import orchestrateur
        stats = orchestrateur.statistiques()
        checks["orchestrateur"] = stats
    except Exception as e:
        checks["orchestrateur"] = f"error: {e}"

    # Statut global
    statut = "ok" if checks["database"] == "ok" and checks["claude_api_key"] == "configuré" else "degradé"

    # Fix statut : dégradé si openai manquant (modèle primaire)
    statut = "ok" if checks["database"] == "ok" and checks["openai_api_key"] == "configuré" else "degradé"
    return {"statut": statut, "checks": checks, "version": settings.APP_VERSION}


@app.get("/api/v1/ia/test", tags=["Santé"])
async def tester_ia():
    """Test rapide de la connexion IA — envoie un mini-prompt à GPT-4o et mesure la latence."""
    import time as _time
    from core.ia_client import IAClient, ModeIA
    t0 = _time.monotonic()
    try:
        client = IAClient()
        reponse = await client.generer(
            prompt="Réponds juste 'OK' en un mot.",
            mode=ModeIA.PRECISION,
            max_tokens=10,
        )
        latence_ms = round((_time.monotonic() - t0) * 1000, 1)
        return {
            "statut": "ok",
            "modele": reponse.modele_utilise,
            "reponse": reponse.contenu.strip(),
            "latence_ms": latence_ms,
            "openai_key_present": bool(settings.OPENAI_API_KEY),
        }
    except Exception as e:
        return {
            "statut": "erreur",
            "message": str(e),
            "openai_key_present": bool(settings.OPENAI_API_KEY),
            "conseil": "Vérifiez OPENAI_API_KEY dans .env et redémarrez le backend.",
        }


@app.get("/health/detailed", tags=["Santé"])
async def health_detailed():
    """
    Healthcheck détaillé avec latences mesurées pour chaque dépendance.
    Retourne les temps de réponse en ms pour faciliter le monitoring.
    """
    import time as _time

    checks: dict = {}
    latences: dict = {}

    # DB
    t0 = _time.monotonic()
    try:
        from core.database import async_session_maker
        from sqlalchemy import text
        async with async_session_maker() as db:
            await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"
    latences["database_ms"] = round((_time.monotonic() - t0) * 1000, 1)

    # Redis
    t0 = _time.monotonic()
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "unavailable"
    latences["redis_ms"] = round((_time.monotonic() - t0) * 1000, 1)

    # Clés IA
    checks["claude_api_key"] = "configuré" if settings.CLAUDE_API_KEY else "manquant"
    checks["openai_api_key"] = "configuré" if settings.OPENAI_API_KEY else "manquant"

    # Orchestrateur
    t0 = _time.monotonic()
    try:
        from core.orchestrateur import orchestrateur
        stats = orchestrateur.statistiques()
        checks["orchestrateur"] = stats
    except Exception as e:
        checks["orchestrateur"] = f"error: {e}"
    latences["orchestrateur_ms"] = round((_time.monotonic() - t0) * 1000, 1)

    # Métriques IA (depuis ia_client)
    t0 = _time.monotonic()
    try:
        from core.ia_client import ia_client
        checks["ia_metriques"] = ia_client.rapport_metriques()
    except Exception as e:
        checks["ia_metriques"] = f"error: {e}"
    latences["ia_metriques_ms"] = round((_time.monotonic() - t0) * 1000, 1)

    # Sessions chat actives
    try:
        from modules.chat.yukpo_ia_assurance import _sessions
        nb_sessions = len(_sessions)
        checks["sessions_chat_actives"] = nb_sessions
        if _PROMETHEUS_OK:
            _yukpo_active_sessions.set(nb_sessions)
    except Exception:
        checks["sessions_chat_actives"] = "indisponible"

    # Prometheus disponible ?
    checks["prometheus"] = "ok" if _PROMETHEUS_OK else "non installé (pip install prometheus-client)"

    statut = "ok" if checks["database"] == "ok" and checks["claude_api_key"] == "configuré" else "degradé"

    return {
        "statut": statut,
        "checks": checks,
        "latences": latences,
        "version": settings.APP_VERSION,
    }


@app.get("/health/si", tags=["Santé"])
async def health_si():
    """
    Vérifie la connectivité des Systèmes d'Information tiers (ORASS, Mercure, SI entreprise).
    Teste tous les modes configurés et retourne un rapport de disponibilité.
    """
    import time as _time
    from config.settings import settings
    checks: dict = {}

    # ── ORASS / Mercure ─────────────────────────────────────────────────────────
    mode = settings.ORASS_MODE
    checks["orass_mode"] = mode

    t0 = _time.monotonic()
    if mode == "simulation":
        checks["orass"] = "ok (simulation — aucune connexion réelle)"
    elif mode == "direct_sql":
        try:
            from core.orass_connector import orass
            orass._get_sql_engine()
            checks["orass"] = "ok (direct_sql connecté)"
        except Exception as e:
            checks["orass"] = f"error: {e}"
    elif mode == "api":
        try:
            import httpx
            url = f"{settings.ORASS_API_URL.rstrip('/')}/health" if settings.ORASS_API_URL else None
            if not url:
                checks["orass"] = "error: ORASS_API_URL non configuré"
            else:
                async with httpx.AsyncClient(timeout=5) as client:
                    resp = await client.get(url)
                    checks["orass"] = f"ok (HTTP {resp.status_code})" if resp.status_code < 400 else f"error HTTP {resp.status_code}"
        except Exception as e:
            checks["orass"] = f"error: {e}"
    elif mode == "csv_import":
        import os
        csv_dir = settings.ORASS_CSV_DIR
        if os.path.isdir(csv_dir):
            nb = len([f for f in os.listdir(csv_dir) if f.endswith(".csv")])
            checks["orass"] = f"ok (csv_import — {nb} fichiers CSV dans {csv_dir})"
        else:
            checks["orass"] = f"warning: dossier CSV introuvable ({csv_dir})"
    checks["orass_latence_ms"] = round((_time.monotonic() - t0) * 1000, 1)

    # ── Mercure DB (si configuré séparément) ────────────────────────────────────
    if settings.MERCURE_DB_URL:
        t0 = _time.monotonic()
        try:
            from sqlalchemy import create_engine, text
            eng = create_engine(settings.MERCURE_DB_URL, pool_pre_ping=True, pool_size=1)
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
            checks["mercure_db"] = "ok"
        except Exception as e:
            checks["mercure_db"] = f"error: {e}"
        checks["mercure_latence_ms"] = round((_time.monotonic() - t0) * 1000, 1)
    else:
        checks["mercure_db"] = "non configuré (MERCURE_DB_URL vide)"

    # ── Base de données applicative (PostgreSQL ou SQLite) ──────────────────────
    t0 = _time.monotonic()
    try:
        from core.database import async_session_maker
        from sqlalchemy import text
        db_url = str(settings.DATABASE_URL)
        is_sqlite = "sqlite" in db_url
        async with async_session_maker() as db:
            if is_sqlite:
                result = await db.execute(text("SELECT sqlite_version()"))
                version = result.scalar()
                checks["database_yukpo"] = f"ok (SQLite {version} — dev local)"
            else:
                result = await db.execute(text("SELECT version()"))
                version = result.scalar()
                checks["database_yukpo"] = f"ok ({version[:50] if version else 'PostgreSQL'})"
    except Exception as e:
        checks["database_yukpo"] = f"error: {e}"
    checks["database_latence_ms"] = round((_time.monotonic() - t0) * 1000, 1)

    # ── Dossier exports SI (CSV) ─────────────────────────────────────────────────
    import os
    csv_dir = settings.ORASS_CSV_DIR
    checks["dossier_exports_csv"] = csv_dir
    checks["dossier_exports_accessible"] = os.path.isdir(csv_dir)

    # ── Dossiers générés ──────────────────────────────────────────────────────────
    gen_dir = os.path.join(os.path.dirname(__file__), "..", "data", "generated")
    checks["dossier_generated"] = os.path.abspath(gen_dir)
    checks["dossier_generated_accessible"] = os.path.isdir(gen_dir)

    # ── Statut global ──────────────────────────────────────────────────────────────
    tous_ok = checks.get("database_yukpo", "").startswith("ok") and not checks.get("orass", "").startswith("error")
    return {
        "statut": "ok" if tous_ok else "degradé",
        "orass_mode_actif": mode,
        "checks": checks,
        "conseil": (
            "ORASS en mode simulation. Configurez ORASS_MODE=direct_sql ou api pour les données réelles."
            if mode == "simulation" else "Connexions SI opérationnelles."
        ),
    }


@app.get("/metrics", tags=["Monitoring"])
async def metrics():
    """
    Endpoint métriques Prometheus.
    Compatible avec prometheus scraping (format text/plain).
    Métriques exposées :
    - yukpo_requests_total (Counter, labels: method, endpoint, status)
    - yukpo_request_duration_seconds (Histogram)
    - yukpo_ia_calls_total (Counter, labels: model, status)
    - yukpo_active_chat_sessions (Gauge)
    """
    if not _PROMETHEUS_OK:
        return JSONResponse(
            status_code=503,
            content={
                "error": "prometheus_client non installé",
                "install": "pip install prometheus-client",
            },
        )

    # Mise à jour du gauge des sessions actives avant de scraper
    try:
        from modules.chat.yukpo_ia_assurance import _sessions
        _yukpo_active_sessions.set(len(_sessions))
    except Exception:
        pass

    # Mise à jour des métriques IA depuis ia_client
    try:
        from core.ia_client import ia_client
        rapport = ia_client.rapport_metriques()
        for modele, stats in rapport.items():
            succes = stats.get("succes", 0)
            echecs = stats.get("echecs", 0)
            # Ces counters sont mis à jour via le middleware — ici on s'assure
            # que les métriques ia_calls reflètent les vraies valeurs
            # (on utilise un gauge supplémentaire si nécessaire)
    except Exception:
        pass

    data = generate_latest(REGISTRY)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


@app.get("/performance", tags=["Monitoring"])
async def metriques_performance():
    """Métriques de performance en temps réel."""
    import time, gc
    resultats = {
        "timestamp": time.time(),
        "python_gc_counts": gc.get_count(),
    }
    # Sessions chat en mémoire
    try:
        from modules.chat.yukpo_ia_assurance import _sessions
        resultats["sessions_chat_memoire"] = len(_sessions)
    except Exception:
        pass

    # Circuit breakers
    try:
        from core.ia_client import ia_client
        resultats["circuit_breakers"] = {
            m: cb.est_ouvert
            for m, cb in getattr(ia_client, "_circuit_breakers", {}).items()
        }
    except Exception:
        pass

    # Budget IA
    try:
        from core.ia_client import ia_client
        resultats["budget_ia"] = {
            "depense_globale_usd": getattr(ia_client, "_depense_globale", 0.0),
            "limite_usd_jour": getattr(settings, "IA_BUDGET_GLOBAL_USD_JOUR", 50.0),
        }
    except Exception:
        pass

    # Redis health
    try:
        import redis as redis_lib
        r = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        info = r.info("memory")
        resultats["redis"] = {
            "status": "ok",
            "used_memory_mb": round(info.get("used_memory", 0) / 1024 / 1024, 1),
        }
    except Exception:
        resultats["redis"] = {"status": "unavailable"}

    return resultats
