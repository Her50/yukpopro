# ─── Stage 1 : Builder ────────────────────────────────────────────────────────
# Installe les dépendances dans un environnement isolé pour minimiser l'image finale
FROM python:3.11-slim AS builder

# Dépendances de compilation uniquement
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    python3-dev \
    # Sprint 2.2 — build deps pour python3-saml (lxml + xmlsec)
    libxml2-dev \
    libxmlsec1-dev \
    libxmlsec1-openssl \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# requirements-cloud.txt exclut cx_Oracle et pyodbc (non compatibles cloud sans clients natifs)
COPY requirements-cloud.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements-cloud.txt


# ─── Stage 2 : Production ─────────────────────────────────────────────────────
FROM python:3.11-slim AS production

# Variables d'environnement Python (meilleures pratiques prod)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PORT=8000 \
    WORKERS=2

# Dépendances système runtime minimales (cloud/simulation mode)
# libreoffice-core/writer/impress : conversion DOCX/PPTX → PDF en mode --headless
# fonts-dejavu-core : rendu correct des caractères latins étendus dans les PDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    curl \
    libglib2.0-0 \
    libreoffice-core \
    libreoffice-writer \
    libreoffice-impress \
    fonts-dejavu-core \
    # Sprint 1.4 — WeasyPrint runtime deps (CSS3 print → PDF haute qualité)
    libcairo2 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi8 \
    shared-mime-info \
    fonts-liberation \
    # Sprint 2.2 — SAML SSO runtime deps (xmlsec1 pour signature/validation XML)
    libxml2 \
    libxslt1.1 \
    libxmlsec1 \
    libxmlsec1-openssl \
    # Gap #9 — Ghostscript pour conversion RGB → CMYK (print-ready imprimerie)
    ghostscript \
    && rm -rf /var/lib/apt/lists/*

# Copier les packages Python compilés depuis le builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Créer les dossiers nécessaires
RUN mkdir -p \
    data/generated \
    data/attestations \
    data/contrats_generes \
    data/ml_models \
    data/orass_csv \
    data/pki \
    logs \
    test-results

# Copier le code applicatif
COPY . .

# Utilisateur non-root (sécurité — principle of least privilege)
RUN useradd --system --uid 1001 --no-create-home appuser \
    && mkdir -p /home/appuser \
    && chown appuser:appuser /home/appuser \
    && chown -R appuser:appuser /app
USER appuser

# Health check — vérifie l'endpoint /health
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -fs http://localhost:${PORT}/health || exit 1

EXPOSE ${PORT}

# Commande de démarrage :
# - Gunicorn gère les workers (process manager robuste)
# - UvicornWorker = ASGI natif (asyncio complet)
# - Workers : 2*CPU+1 est la règle gunicorn, ici configurable via WORKERS
# - --graceful-timeout 30 : délai pour terminer les requêtes en cours
# - --max-requests 1000 : recycle les workers après 1000 requêtes (évite les memory leaks)
CMD gunicorn api.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers ${WORKERS} \
    --bind 0.0.0.0:${PORT} \
    --timeout 360 \
    --graceful-timeout 60 \
    --worker-tmp-dir /tmp \
    --max-requests 2000 \
    --max-requests-jitter 200 \
    --access-logfile - \
    --error-logfile - \
    --log-level info
