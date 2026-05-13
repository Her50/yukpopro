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
    # Audit visuel Sonnet — pdf2image a besoin de poppler-utils pour la
    # commande `pdftoppm`. Sans ça, l'audit du pipeline freeform skippe
    # silencieusement et aucun feedback qualité n'est généré.
    poppler-utils \
    # FFmpeg — stitching vidéos longues (15-60s) : N clips Kling 10s
    # générés en parallèle puis concaténés avec crossfade xfade.
    # Sans ffmpeg, video_gen.generer_video_long() échoue au stitching.
    # Inclut libx264/aac codecs pour ré-encodage si filtres complexes.
    ffmpeg \
    # pikepdf : la lib libqpdf est bundled statiquement dans le wheel
    # x86_64-linux du package pip ; aucun paquet apt requis.
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

# Rendre l'entrypoint exécutable AVANT le switch d'utilisateur
RUN chmod +x /app/entrypoint.sh

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

# Sol B — entrypoint.sh orchestre web (gunicorn) + worker Celery dans le
# même container (partage filesystem pour le volume PDF). Si CELERY_ENABLED
# != "true", lance uniquement le web (compat legacy asyncio path).
CMD ["/app/entrypoint.sh"]
