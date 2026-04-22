-- ═══════════════════════════════════════════════════════════════════════════
-- YukpoAssurance — Initialisation Supabase PostgreSQL
-- Exécuter dans Supabase Dashboard → SQL Editor
-- ═══════════════════════════════════════════════════════════════════════════

-- Extensions nécessaires
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";   -- recherche texte floue
CREATE EXTENSION IF NOT EXISTS "unaccent";  -- recherche sans accents

-- Schéma dédié (optionnel mais recommandé)
-- CREATE SCHEMA IF NOT EXISTS yukpo;

-- Optimisations connexion (Supabase gère déjà le pooling via pgBouncer)
-- La DATABASE_URL doit utiliser le port 6543 (pooler) et non 5432 (direct)

-- Vérification
SELECT version();
SELECT current_database();
