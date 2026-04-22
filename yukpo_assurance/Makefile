# ─── YukpoAssurance Makefile ──────────────────────────────────────────────────
.PHONY: help install dev test test-cima test-api test-fraude test-docs test-souscription \
        test-coverage lint format security \
        docker-build docker-up docker-down docker-dev docker-prod docker-logs docker-shell \
        migrate migrate-init migrate-create \
        clean check-prod \
        deploy deploy-check deploy-env

# ─── Couleurs terminal ────────────────────────────────────────────────────────
CYAN  := \033[36m
GREEN := \033[32m
RESET := \033[0m

help:
	@echo ""
	@echo "$(CYAN)YukpoAssurance — Commandes disponibles$(RESET)"
	@echo ""
	@echo "$(GREEN)Démarrage rapide$(RESET)"
	@echo "  make setup-sqlite     Configurer SQLite local (aucun serveur requis)"
	@echo "  make setup-pg PG_PASS=MOT_DE_PASSE   Configurer PostgreSQL local"
	@echo ""
	@echo "$(GREEN)Développement$(RESET)"
	@echo "  make install          Installer toutes les dépendances Python"
	@echo "  make dev              Serveur FastAPI avec hot-reload (port 8000)"
	@echo ""
	@echo "$(GREEN)Tests$(RESET)"
	@echo "  make test             Tous les tests avec coverage (min 70%)"
	@echo "  make test-cima        Tests réglementaires CIMA uniquement"
	@echo "  make test-api         Tests API endpoints uniquement"
	@echo "  make test-fraude      Tests détection fraude uniquement"
	@echo "  make test-docs        Tests génération documents"
	@echo "  make test-souscription Tests souscription"
	@echo "  make test-coverage    Coverage HTML + rapport détaillé"
	@echo ""
	@echo "$(GREEN)Qualité & Sécurité$(RESET)"
	@echo "  make lint             ruff + black --check"
	@echo "  make format           black + isort (applique les corrections)"
	@echo "  make security         bandit (SAST) + safety (deps)"
	@echo ""
	@echo "$(GREEN)Docker$(RESET)"
	@echo "  make docker-dev       Docker Compose mode développement"
	@echo "  make docker-prod      Docker Compose mode production"
	@echo "  make docker-build     Build l'image Docker"
	@echo "  make docker-up        Démarrer tous les services"
	@echo "  make docker-down      Arrêter tous les services"
	@echo "  make docker-logs      Suivre les logs en temps réel"
	@echo "  make docker-shell     Shell bash dans le container app"
	@echo ""
	@echo "$(GREEN)Base de données$(RESET)"
	@echo "  make migrate          Appliquer les migrations Alembic (upgrade head)"
	@echo "  make migrate-init     Initialiser Alembic"
	@echo "  make migrate-create   Créer une nouvelle migration"
	@echo ""
	@echo "$(GREEN)Maintenance$(RESET)"
	@echo "  make clean            Supprimer __pycache__, .pyc, caches pytest"
	@echo "  make check-prod       Vérifier la configuration production"
	@echo ""
	@echo "$(GREEN)Déploiement serveur compagnie$(RESET)"
	@echo "  make deploy PG_HOST=... PG_SUPER_PASS=...     Déploiement complet (BD + migrations + .env)"
	@echo "  make deploy-check PG_HOST=... PG_APP_PASS=... Tester la connexion seulement"
	@echo "  make deploy-env PG_HOST=... PG_SUPER_PASS=... Générer .env production seulement"
	@echo ""

# ─────────────────────────────────────────────────────────────────────────────
# INSTALLATION
# ─────────────────────────────────────────────────────────────────────────────
install:
	pip install --upgrade pip
	pip install -r requirements.txt
	pip install ruff black mypy isort pytest pytest-asyncio pytest-cov httpx bandit safety
	@echo "$(GREEN)Installation terminée$(RESET)"

# ── Setup bases de données locales ──────────────────────────────────────────
setup-sqlite:
	python scripts/setup_local_postgres.py --sqlite
	@echo "$(GREEN)SQLite configuré - lancez: make dev$(RESET)"

setup-pg:
	@if [ -z "$(PG_PASS)" ]; then echo "Usage: make setup-pg PG_PASS=votre_mot_de_passe"; exit 1; fi
	python scripts/setup_local_postgres.py --pg-password $(PG_PASS) --create-tables
	@echo "$(GREEN)PostgreSQL configuré$(RESET)"

# ─────────────────────────────────────────────────────────────────────────────
# DÉVELOPPEMENT
# ─────────────────────────────────────────────────────────────────────────────
dev:
	ORASS_MODE=simulation uvicorn api.main:app \
		--reload \
		--host 0.0.0.0 \
		--port 8000 \
		--log-level info \
		--reload-dir api \
		--reload-dir modules \
		--reload-dir core \
		--reload-dir config

# ─────────────────────────────────────────────────────────────────────────────
# TESTS
# ─────────────────────────────────────────────────────────────────────────────
test:
	pytest tests/ \
		-v \
		--tb=short \
		--cov=. \
		--cov-report=term-missing \
		--cov-report=html:htmlcov \
		--cov-fail-under=70 \
		--junitxml=test-results/junit.xml \
		-p no:warnings
	@echo "$(GREEN)Tests terminés — rapport HTML dans htmlcov/$(RESET)"

test-cima:
	pytest tests/test_cima.py -v --tb=short -p no:warnings
	@echo "$(GREEN)Tests CIMA terminés$(RESET)"

test-api:
	pytest tests/test_auth.py tests/test_api_auth.py tests/test_api_chat.py \
		tests/test_sinistres_api.py \
		-v --tb=short -p no:warnings
	@echo "$(GREEN)Tests API terminés$(RESET)"

test-fraude:
	pytest tests/test_fraude.py -v --tb=short -p no:warnings
	@echo "$(GREEN)Tests fraude terminés$(RESET)"

test-docs:
	pytest tests/test_documents.py -v --tb=short -p no:warnings
	@echo "$(GREEN)Tests documents terminés$(RESET)"

test-souscription:
	pytest tests/test_souscription.py -v --tb=short -p no:warnings
	@echo "$(GREEN)Tests souscription terminés$(RESET)"

test-coverage:
	pytest tests/ \
		-v \
		--cov=. \
		--cov-report=html:htmlcov \
		--cov-report=xml:coverage.xml \
		--cov-report=term-missing \
		--cov-branch \
		-p no:warnings
	@echo "$(GREEN)Coverage HTML généré dans htmlcov/index.html$(RESET)"

# ─────────────────────────────────────────────────────────────────────────────
# QUALITÉ DE CODE
# ─────────────────────────────────────────────────────────────────────────────
lint:
	ruff check . --fix
	black --check --diff .
	@echo "$(GREEN)Lint OK$(RESET)"

format:
	black .
	isort . --profile black
	@echo "$(GREEN)Formatage appliqué (black + isort)$(RESET)"

security:
	@echo "$(CYAN)--- Bandit SAST scan ---$(RESET)"
	bandit -r api/ modules/ core/ config/ \
		-x tests/ \
		--severity-level medium \
		--confidence-level medium \
		-f screen
	@echo ""
	@echo "$(CYAN)--- Safety dependency check ---$(RESET)"
	safety check --file requirements.txt
	@echo "$(GREEN)Security scan terminé$(RESET)"

# ─────────────────────────────────────────────────────────────────────────────
# DOCKER
# ─────────────────────────────────────────────────────────────────────────────
docker-build:
	docker compose build --no-cache
	@echo "$(GREEN)Image Docker construite$(RESET)"

docker-dev:
	COMPOSE_PROFILES=dev docker compose up --build
	@echo "$(GREEN)Mode développement démarré$(RESET)"

docker-prod:
	docker compose up -d
	@echo "$(GREEN)Mode production démarré$(RESET)"
	@echo "  API    : http://localhost:8000"
	@echo "  Docs   : http://localhost:8000/docs"
	@echo "  Nginx  : http://localhost:80"

docker-up:
	docker compose up -d
	@echo "$(GREEN)Services démarrés$(RESET)"
	@echo "  API disponible sur http://localhost:8000"
	@echo "  Docs Swagger : http://localhost:8000/docs"

docker-down:
	docker compose down
	@echo "$(GREEN)Services arrêtés$(RESET)"

docker-logs:
	docker compose logs -f app

docker-shell:
	docker compose exec app bash

# ─────────────────────────────────────────────────────────────────────────────
# BASE DE DONNÉES / MIGRATIONS
# ─────────────────────────────────────────────────────────────────────────────
migrate-init:
	alembic init migrations

migrate:
	alembic upgrade head
	@echo "$(GREEN)Migrations appliquées$(RESET)"

migrate-create:
	@read -p "Nom de la migration: " name; alembic revision --autogenerate -m "$$name"

# ─────────────────────────────────────────────────────────────────────────────
# MAINTENANCE
# ─────────────────────────────────────────────────────────────────────────────
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -f yukpo_assurance.db test_yukpo.db
	rm -rf htmlcov/ coverage.xml test-results/
	@echo "$(GREEN)Nettoyage terminé$(RESET)"

check-prod:
	python -c "from config.settings import settings; issues = settings.validate_production(); [print('WARNING:', i) for i in issues]; print('Checks production OK' if not issues else f'{len(issues)} problème(s) détecté(s)')"

# ─────────────────────────────────────────────────────────────────────────────
# DÉPLOIEMENT SERVEUR COMPAGNIE
# ─────────────────────────────────────────────────────────────────────────────
# Déploiement complet (crée BD, migrations, génère .env prod)
# Usage : make deploy PG_HOST=db.compagnie.cm PG_SUPER_PASS=motdepasse PG_APP_PASS=yukpo_prod
deploy:
	@if [ -z "$(PG_HOST)" ] || [ -z "$(PG_SUPER_PASS)" ]; then \
		echo "Usage: make deploy PG_HOST=db.compagnie.cm PG_SUPER_PASS=motdepasse [PG_APP_PASS=mon_mdp_app]"; exit 1; fi
	python scripts/deploy_postgres.py \
		--host $(PG_HOST) \
		--port $(or $(PG_PORT),5432) \
		--superuser-password $(PG_SUPER_PASS) \
		--app-password $(or $(PG_APP_PASS),yukpo_prod_2025) \
		--ssl-mode $(or $(PG_SSL),prefer) \
		--generate-env \
		--env-output .env.production
	@echo "$(GREEN)Déploiement terminé — copiez .env.production → .env sur le serveur$(RESET)"

# Vérifier la connexion seulement (sans créer quoi que ce soit)
# Usage : make deploy-check PG_HOST=db.compagnie.cm PG_APP_PASS=motdepasse
deploy-check:
	@if [ -z "$(PG_HOST)" ]; then echo "Usage: make deploy-check PG_HOST=db.compagnie.cm PG_APP_PASS=motdepasse"; exit 1; fi
	python scripts/deploy_postgres.py \
		--host $(PG_HOST) \
		--superuser-password "" \
		--app-password $(or $(PG_APP_PASS),yukpo_prod_2025) \
		--check-only

# Générer uniquement le .env prod (sans toucher à la BD)
# Usage : make deploy-env PG_HOST=db.compagnie.cm PG_SUPER_PASS=motdepasse PG_APP_PASS=mon_mdp_app
deploy-env:
	@if [ -z "$(PG_HOST)" ] || [ -z "$(PG_SUPER_PASS)" ]; then \
		echo "Usage: make deploy-env PG_HOST=db.compagnie.cm PG_SUPER_PASS=motdepasse PG_APP_PASS=mon_mdp"; exit 1; fi
	python scripts/deploy_postgres.py \
		--host $(PG_HOST) \
		--superuser-password $(PG_SUPER_PASS) \
		--app-password $(or $(PG_APP_PASS),yukpo_prod_2025) \
		--skip-create-db --skip-migrations \
		--generate-env --env-output .env.production
	@echo "$(GREEN).env.production généré$(RESET)"
