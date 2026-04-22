"""
YukpoAssurance — Configuration centrale
"""
import os
import secrets
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional


def _charger_ou_creer_secret_key() -> str:
    """
    Charge la SECRET_KEY depuis :
    1. Variable d'environnement SECRET_KEY (production — vault, k8s secret)
    2. Fichier .secret_key à la racine du projet (développement persistant)
    3. Génère une nouvelle clé et la sauvegarde dans le fichier (premier démarrage)

    IMPORTANT : En production, toujours utiliser la variable d'environnement.
    Ne jamais committer le fichier .secret_key.
    """
    # 1. Variable d'environnement (priorité absolue — production)
    env_key = os.environ.get("SECRET_KEY", "")
    if env_key and len(env_key) >= 32:
        return env_key

    # 2. Fichier .secret_key (dev persistant)
    secret_file = Path(__file__).parent.parent / ".secret_key"
    try:
        if secret_file.exists():
            key = secret_file.read_text().strip()
            if len(key) >= 32:
                return key
    except Exception:
        pass

    # 3. Génération + sauvegarde (premier démarrage dev)
    new_key = secrets.token_hex(32)
    try:
        secret_file.write_text(new_key)
        # chmod 600 — lecture seule par le propriétaire
        os.chmod(secret_file, 0o600)
    except Exception:
        pass
    return new_key


def _lire_cle_depuis_env_file(nom_var: str) -> str:
    """
    Lit une clé directement depuis le fichier .env en ignorant les variables système.
    Utilisé quand la variable système contient une valeur invalide (mauvais format, placeholder).
    """
    env_file = Path(__file__).parent.parent / ".env"
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{nom_var}=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


class Settings(BaseSettings):
    # ─── Application ──────────────────────────────────────────────
    APP_NAME: str = "YukpoAssurance"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    # SECRET_KEY : persistante entre redémarrages (voir _charger_ou_creer_secret_key)
    # En production : définir SECRET_KEY dans les variables d'environnement / vault
    SECRET_KEY: str = _charger_ou_creer_secret_key()

    # ─── IA — Modèles ─────────────────────────────────────────────
    CLAUDE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    def __init__(self, **data):
        super().__init__(**data)
        # Correction : si les clés IA chargées depuis les variables système sont invalides,
        # lire directement depuis .env (contourne une variable système corrompue/placeholder)
        if not (self.OPENAI_API_KEY.startswith("sk-") and len(self.OPENAI_API_KEY) > 40):
            cle_env = _lire_cle_depuis_env_file("OPENAI_API_KEY")
            if cle_env.startswith("sk-") and len(cle_env) > 40:
                object.__setattr__(self, "OPENAI_API_KEY", cle_env)
        if not (self.CLAUDE_API_KEY.startswith("sk-ant-") and len(self.CLAUDE_API_KEY) > 40
                and "votre-cle" not in self.CLAUDE_API_KEY):
            cle_env = _lire_cle_depuis_env_file("CLAUDE_API_KEY")
            if cle_env.startswith("sk-ant-") and len(cle_env) > 40 and "votre-cle" not in cle_env:
                object.__setattr__(self, "CLAUDE_API_KEY", cle_env)

    # Modèles par défaut
    CLAUDE_MODEL_PRIMAIRE: str = "claude-sonnet-4-6"    # Chat — bon équilibre vitesse/qualité
    CLAUDE_MODEL_RAPIDE: str = "claude-haiku-4-5-20251001"  # Tâches simples, classification
    GPT_MODEL_PRIMAIRE: str = "gpt-4o"                  # Modèle principal — qualité maximale
    GPT_MODEL_FALLBACK: str = "gpt-4o-mini"             # Fallback rapide pour classification/détection

    # Paramètres d'orchestration (inspiré de yukpomnang2/orchestration_ia.rs)
    IA_TEMPERATURE_PRECISION: float = 0.1   # États réglementaires, calculs CIMA
    IA_TEMPERATURE_REDACTION: float = 0.4   # Rapports, courriers
    IA_TEMPERATURE_CREATIVE: float = 0.7    # Offres commerciales
    IA_MAX_TOKENS: int = 4096             # Chat conversationnel — 4096 suffisant, réduit la latence
    IA_MAX_TOKENS_DOCUMENT: int = 16384   # Pour génération de documents longs (rapports CIMA)
    IA_CONFIDENCE_THRESHOLD: float = 0.85
    IA_MAX_RETRIES: int = 3
    IA_TIMEOUT_SECONDS: int = 120         # Augmenté pour documents longs (was 60s)

    # Tailles max fichiers (en MB)
    MAX_IMAGE_SIZE_MB: int = 10
    MAX_PDF_SIZE_MB: int = 20
    MAX_EXCEL_SIZE_MB: int = 5

    # ─── Base de données ──────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/yukpo_assurance"
    DATABASE_POOL_SIZE: int = 10

    # ─── Redis (cache & sessions) ─────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL_SECONDS: int = 3600

    # ─── ORASS / Mercure ──────────────────────────────────────────
    ORASS_DB_URL: Optional[str] = None          # connexion directe SQL si dispo
    ORASS_DSN: Optional[str] = None             # alias ORASS_DB_URL pour orass_connector
    ORASS_API_URL: Optional[str] = None         # API ORASS si exposée
    ORASS_CSV_DIR: str = "data/orass_csv"       # dossier exports CSV depuis ORASS/Mercure
    MERCURE_DB_URL: Optional[str] = None
    ORASS_MODE: str = "simulation"              # "simulation" | "direct_sql" | "csv_import" | "api"

    # ─── WhatsApp Business (Meta Cloud API) ───────────────────────
    # Paramètres globaux — peuvent être surchargés par CompagnieDB
    META_WHATSAPP_APP_SECRET: str = ""          # Pour vérification HMAC-SHA256 des webhooks
    META_WHATSAPP_VERIFY_TOKEN: str = ""        # Token de vérification webhook Meta
    META_WHATSAPP_PHONE_ID: str = ""            # Phone Number ID Meta Business
    META_WHATSAPP_TOKEN: str = ""               # Access Token permanent Meta

    # ─── Paiement Mobile Money ────────────────────────────────────
    # Paramètres globaux — peuvent être surchargés par CompagnieDB
    CINETPAY_API_KEY: str = ""
    CINETPAY_SITE_ID: str = ""
    MTN_MOMO_API_KEY: str = ""
    MTN_MOMO_SUBSCRIPTION_KEY: str = ""
    MTN_MOMO_ENVIRONMENT: str = "sandbox"       # "sandbox" | "production"
    ORANGE_MONEY_CLIENT_ID: str = ""
    ORANGE_MONEY_CLIENT_SECRET: str = ""
    ORANGE_MONEY_MERCHANT_KEY: str = ""
    WAVE_API_KEY: str = ""

    # ─── Community Manager / Social AI ───────────────────────────
    META_FB_APP_ID: str = ""              # Facebook App ID (pour OAuth)
    META_FB_APP_SECRET: str = ""          # Facebook App Secret
    # Clés globales — peuvent être surchargées par CompagnieDB.social_accounts
    META_FB_PAGE_ACCESS_TOKEN: str = ""   # Page Access Token Facebook
    META_FB_PAGE_ID: str = ""             # Page ID Facebook
    META_IG_USER_ID: str = ""             # Instagram Business Account ID
    META_GRAPH_API_VERSION: str = "v19.0"

    # ─── TrendPulse — Sources externes ────────────────────────────
    SERPAPI_KEY: str = ""                 # SerpAPI (Google Trends)
    YOUTUBE_API_KEY: str = ""             # YouTube Data API v3
    NEWSAPI_KEY: str = ""                 # NewsAPI.org
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""

    # ─── Email marketing (SendGrid) ───────────────────────────────
    SENDGRID_API_KEY: str = ""
    SENDGRID_FROM_EMAIL: str = ""
    SENDGRID_FROM_NAME: str = "YukpoAssurance"

    # ─── Yukpo Platform — Super Admin ────────────────────────────
    SUPER_ADMIN_EMAIL: str = ""    # Email propriétaires Yukpo (rapports agents autonomes)

    # ─── Contrats clients PDF ─────────────────────────────────────
    CONTRATS_DIR: str = "data/contrats_generes"  # Dossier de stockage des contrats générés

    # ─── SMTP (envoi email) ───────────────────────────────────────
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""

    # ─── WhatsApp / Notifications (legacy Twilio) ─────────────────
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_WHATSAPP_NUMBER: Optional[str] = None

    # ─── Sécurité ─────────────────────────────────────────────────
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000"]
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480      # 8 heures
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ─── Multitenancy ─────────────────────────────────────────────
    # compagnie_id est porté par le JWT — chaque compagnie a sa propre instance
    # ou partage l'infra avec isolation par compagnie_id
    ENFORCE_COMPAGNIE_ISOLATION: bool = True    # Isolation multi-tenant activée

    # ─── Documents générés ────────────────────────────────────────
    GENERATED_DOCS_DIR: str = "data/generated"   # Relatif à la racine du projet

    # ─── OpenTelemetry / Observabilité ────────────────────────────────────────
    OTLP_ENDPOINT: str = "http://localhost:4317"    # OTLP gRPC (Jaeger / Grafana Tempo)
    OTLP_ENABLED: bool = False                      # False par défaut — activer en prod
    SIGNATURE_HMAC_KEY: str = ""                    # Clé HMAC pour signatures électroniques
    SIGNATURE_BACKEND: str = "hmac"                 # "hmac" | "pki_local" | "yousign" | "docusign"
    YOUSIGN_API_KEY: str = ""                       # Clé Yousign (SIGNATURE_BACKEND=yousign)
    YOUSIGN_BASE_URL: str = "https://staging-api.yousign.app/v3"  # prod: yousign.app/v3
    DOCUSIGN_ACCOUNT_ID: str = ""                   # Compte Docusign
    DOCUSIGN_CLIENT_ID: str = ""
    DOCUSIGN_RSA_KEY_PATH: str = ""                 # Chemin clé RSA Docusign JWT
    DOCUSIGN_BASE_URL: str = "https://demo.docusign.net/restapi"  # prod: docusign.net/restapi
    PKI_CA_CERT_PATH: str = ""                      # CA auto-signée (SIGNATURE_BACKEND=pki_local)
    PKI_SIGNING_KEY_PATH: str = ""
    PKI_SIGNING_CERT_PATH: str = ""

    # ─── Budget IA ────────────────────────────────────────────────
    IA_BUDGET_GLOBAL_USD_JOUR: float = 50.0         # Budget global journalier (USD)
    IA_BUDGET_ALERTE_USD: float = 40.0              # Seuil d'alerte (80% du budget)
    IA_BUDGET_PAR_USER_USD_JOUR: float = 5.0        # Budget par utilisateur/jour
    IA_MAX_TOKENS_PAR_APPEL: int = 16384            # Max tokens par appel unique (augmenté pour rapports longs)

    # ─── Sécurité PII / Chiffrement ───────────────────────────────
    PII_ENCRYPTION_KEY: str = ""                    # Clé AES-256 pour chiffrement CNI/tél/email
    ORASS_API_KEY: str = ""                         # Clé API ORASS (mode api)
    ORASS_API_SECRET: str = ""                      # Secret HMAC pour signature requêtes ORASS

    # ─── Logging ──────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"   # "json" | "text"

    class Config:
        # Chemin absolu vers .env — fonctionne quel que soit le répertoire de lancement
        env_file = str(Path(__file__).parent.parent / ".env")
        case_sensitive = True
        extra = "ignore"   # Ignorer les variables non déclarées (POSTGRES_PASSWORD, etc.)

    def validate_production(self) -> list[str]:
        """Retourne la liste des problèmes bloquants pour la production."""
        issues = []
        # GPT-4o est le modèle primaire — clé OpenAI obligatoire
        if not self.OPENAI_API_KEY:
            issues.append("OPENAI_API_KEY manquant — modèle primaire GPT-4o inaccessible")
        # Claude = fallback optionnel
        if not self.CLAUDE_API_KEY:
            issues.append("CLAUDE_API_KEY manquant — fallback Claude désactivé (non bloquant)")
        if self.DATABASE_URL.startswith("postgresql") and "password" in self.DATABASE_URL:
            issues.append("DATABASE_URL contient le mot de passe en clair — utiliser un secret manager")
        if self.ORASS_MODE == "simulation":
            issues.append("ORASS_MODE=simulation — connecter le vrai ORASS avant la mise en production")
        if self.ORASS_MODE == "api" and not self.ORASS_API_KEY:
            issues.append("ORASS_API_KEY manquant (mode api)")
        if self.ORASS_MODE == "api" and not self.ORASS_API_SECRET:
            issues.append("ORASS_API_SECRET manquant (mode api) — signatures HMAC désactivées")
        if not self.META_WHATSAPP_APP_SECRET:
            issues.append("META_WHATSAPP_APP_SECRET manquant — sécurité webhook WhatsApp désactivée")
        if not any([self.CINETPAY_API_KEY, self.MTN_MOMO_API_KEY,
                    self.ORANGE_MONEY_CLIENT_ID, self.WAVE_API_KEY]):
            issues.append("Aucun opérateur de paiement configuré — mode simulation actif")
        if not self.PII_ENCRYPTION_KEY:
            issues.append("PII_ENCRYPTION_KEY manquant — données sensibles non chiffrées (CNI, tél)")
        if not self.SIGNATURE_HMAC_KEY:
            issues.append("SIGNATURE_HMAC_KEY manquant — signatures électroniques désactivées")
        if self.IA_BUDGET_GLOBAL_USD_JOUR <= 0:
            issues.append("IA_BUDGET_GLOBAL_USD_JOUR invalide — contrôle budget IA désactivé")
        return issues

    def validate_staging(self) -> list[str]:
        """Vérifications pour l'environnement de staging/UAT."""
        issues = []
        if not self.CLAUDE_API_KEY and not self.OPENAI_API_KEY:
            issues.append("Aucune clé IA configurée — impossible de tester les fonctionnalités IA")
        if self.ORASS_MODE not in ("simulation", "csv_import", "direct_sql", "api"):
            issues.append(f"ORASS_MODE invalide: {self.ORASS_MODE}")
        return issues


settings = Settings()
