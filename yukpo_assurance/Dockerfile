# ─── Stage 1 : Builder ────────────────────────────────────────────────────────
# Installe les dépendances dans un environnement isolé pour minimiser l'image finale
FROM python:3.11-slim AS builder

# Dépendances de compilation uniquement
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copier uniquement les requirements pour profiter du cache Docker
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ─── Stage 2 : Production ─────────────────────────────────────────────────────
FROM python:3.11-slim AS production

# Variables d'environnement Python (meilleures pratiques prod)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PORT=8000 \
    WORKERS=2

# Dépendances système runtime (Tesseract OCR + poppler)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-fra \
    tesseract-ocr-eng \
    poppler-utils \
    libpq-dev \
    curl \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
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
    --timeout 120 \
    --graceful-timeout 30 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --access-logfile - \
    --error-logfile - \
    --log-level info
