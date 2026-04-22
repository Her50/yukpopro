-- YukpoAssurance — Script d'initialisation PostgreSQL
-- Ce script s'exécute automatiquement au premier démarrage du container PostgreSQL

-- Extension pour les UUIDs
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Extension pour les performances de recherche full-text
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Extension pour le chiffrement (données sensibles)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- NOTE : La création du compte read-only yukpo_readonly est gérée par
-- scripts/init_readonly_user.sh (02_readonly_user.sh) qui lit POSTGRES_READONLY_PASSWORD
-- depuis l'environnement Docker — plus sécurisé qu'un mot de passe hardcodé ici.

-- Index de performance pour les requêtes fréquentes (créés après init_db via Alembic)
-- Les index sont définis dans les modèles SQLAlchemy, mais on peut en ajouter ici
-- pour les colonnes JSON si nécessaire.
