#!/bin/bash
# YukpoAssurance — Création sécurisée du compte read-only PostgreSQL
# Exécuté automatiquement par docker-entrypoint au premier démarrage du container.
# Lit le mot de passe depuis la variable d'environnement POSTGRES_READONLY_PASSWORD.

set -e

READONLY_USER="yukpo_readonly"
READONLY_DB="yukpo_assurance"

# Vérifier que la variable est définie
if [ -z "${POSTGRES_READONLY_PASSWORD}" ]; then
    echo "[WARN] POSTGRES_READONLY_PASSWORD non défini — génération d'un mot de passe aléatoire (mode dev)"
    POSTGRES_READONLY_PASSWORD=$(head -c 32 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 24)
    echo "[INFO] Mot de passe read-only généré (utiliser uniquement en développement)"
fi

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Créer ou mettre à jour l'utilisateur read-only
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${READONLY_USER}') THEN
            CREATE ROLE ${READONLY_USER} LOGIN PASSWORD '${POSTGRES_READONLY_PASSWORD}';
            RAISE NOTICE 'Utilisateur ${READONLY_USER} créé avec succès';
        ELSE
            ALTER ROLE ${READONLY_USER} WITH PASSWORD '${POSTGRES_READONLY_PASSWORD}';
            RAISE NOTICE 'Mot de passe ${READONLY_USER} mis à jour';
        END IF;
    END
    \$\$;

    -- Droits d'accès
    GRANT CONNECT ON DATABASE ${READONLY_DB} TO ${READONLY_USER};
    GRANT USAGE ON SCHEMA public TO ${READONLY_USER};
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO ${READONLY_USER};
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO ${READONLY_USER};

    SELECT 'Compte ${READONLY_USER} configuré avec succès' AS statut;
EOSQL
