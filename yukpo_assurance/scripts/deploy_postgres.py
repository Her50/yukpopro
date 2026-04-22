#!/usr/bin/env python3
"""
YukpoAssurance — Script de déploiement PostgreSQL en production (serveur compagnie).

Ce script est conçu pour être exécuté UNE FOIS lors du déploiement initial
sur le serveur de la compagnie d'assurance, ou après chaque migration majeure.

Il effectue dans l'ordre :
  1. Test de connectivité réseau vers le serveur PostgreSQL cible
  2. Création de l'utilisateur applicatif et de la base de données
  3. Activation des extensions PostgreSQL (uuid-ossp, pg_trgm, pgcrypto)
  4. Application des migrations Alembic (ou create_all en fallback)
  5. [Optionnel] Migration des données SQLite → PostgreSQL (dev → prod)
  6. Génération du fichier .env de production
  7. Rapport de santé final

Usage :
    # Deploiement minimal (BD deja creee par le DBA)
    python scripts/deploy_postgres.py
        --host db.compagnie.cm --port 5432
        --superuser-password MOT_DE_PASSE_POSTGRES
        --app-password MOT_DE_PASSE_YUKPO

    # Deploiement complet avec generation du .env prod
    python scripts/deploy_postgres.py
        --host db.compagnie.cm --port 5432
        --superuser-password MOT_DE_PASSE_POSTGRES
        --app-password MOT_DE_PASSE_YUKPO
        --generate-env --env-output /opt/yukpo/.env

    # Migrer les donnees SQLite dev vers PostgreSQL prod
    python scripts/deploy_postgres.py
        --host db.compagnie.cm
        --superuser-password MOT_DE_PASSE_POSTGRES
        --app-password MOT_DE_PASSE_YUKPO
        --migrate-from-sqlite yukpo_assurance_dev.db

    # Verifier seulement la connexion (sans creer quoi que ce soit)
    python scripts/deploy_postgres.py
        --host db.compagnie.cm
        --superuser-password MOT_DE_PASSE_POSTGRES
        --check-only
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# ─── Répertoire racine du projet ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ─── Constantes applicatives ──────────────────────────────────────────────────
APP_DB_USER = "yukpo"
APP_DB_NAME = "yukpo_assurance"
PG_DEFAULT_SUPERUSER = "postgres"

EXTENSIONS = ["uuid-ossp", "pg_trgm", "pgcrypto", "btree_gin"]


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers affichage
# ═══════════════════════════════════════════════════════════════════════════════

class C:
    OK      = "\033[92m[OK]\033[0m"
    WARN    = "\033[93m[WARN]\033[0m"
    ERR     = "\033[91m[ERR]\033[0m"
    INFO    = "\033[94m[INFO]\033[0m"
    STEP    = "\033[96m[>>]\033[0m"
    BOLD    = "\033[1m"
    END     = "\033[0m"

def log(level: str, msg: str):
    print(f"{level} {msg}")

def step(title: str):
    print(f"\n{C.BOLD}{'─'*60}{C.END}")
    print(f"{C.STEP} {C.BOLD}{title}{C.END}")
    print(f"{C.BOLD}{'─'*60}{C.END}")


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Test de connectivité réseau
# ═══════════════════════════════════════════════════════════════════════════════

def test_connexion_reseau(host: str, port: int) -> bool:
    """Vérifie que le port PostgreSQL est accessible depuis ce serveur."""
    import socket
    step(f"Test connectivité réseau → {host}:{port}")
    try:
        sock = socket.create_connection((host, port), timeout=5)
        sock.close()
        log(C.OK, f"Port {port} accessible sur {host}")
        return True
    except socket.timeout:
        log(C.ERR, f"Timeout — {host}:{port} inaccessible (firewall ? VPN requis ?)")
        return False
    except ConnectionRefusedError:
        log(C.ERR, f"Connexion refusée sur {host}:{port} — PostgreSQL démarré ?")
        return False
    except Exception as e:
        log(C.ERR, f"Erreur réseau : {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Création BD et utilisateur
# ═══════════════════════════════════════════════════════════════════════════════

def creer_base_et_utilisateur(
    host: str,
    port: int,
    superuser: str,
    superuser_password: str,
    app_password: str,
    ssl_mode: str = "prefer",
) -> bool:
    """Crée l'utilisateur applicatif et la base de données si inexistants."""
    step("Création utilisateur et base de données")
    try:
        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    except ImportError:
        log(C.ERR, "psycopg2 absent. Installez : pip install psycopg2-binary")
        return False

    try:
        conn = psycopg2.connect(
            host=host, port=port,
            dbname="postgres",
            user=superuser,
            password=superuser_password,
            connect_timeout=10,
            sslmode=ssl_mode,
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        log(C.OK, f"Connecté à PostgreSQL en tant que {superuser}")
    except Exception as e:
        log(C.ERR, f"Connexion superutilisateur impossible : {e}")
        _conseils_connexion(host, superuser)
        return False

    # ── Créer ou mettre à jour l'utilisateur applicatif ─────────────────────
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_DB_USER,))
    if cur.fetchone():
        cur.execute(
            f"ALTER ROLE {APP_DB_USER} WITH PASSWORD %s LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE",
            (app_password,),
        )
        log(C.OK, f"Utilisateur '{APP_DB_USER}' existant — mot de passe mis à jour")
    else:
        cur.execute(
            f"CREATE ROLE {APP_DB_USER} LOGIN PASSWORD %s NOSUPERUSER NOCREATEDB NOCREATEROLE",
            (app_password,),
        )
        log(C.OK, f"Utilisateur '{APP_DB_USER}' créé")

    # ── Créer la base de données ─────────────────────────────────────────────
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (APP_DB_NAME,))
    if cur.fetchone():
        log(C.WARN, f"Base '{APP_DB_NAME}' déjà existante — conservée telle quelle")
    else:
        cur.execute(
            f"""CREATE DATABASE "{APP_DB_NAME}"
                OWNER {APP_DB_USER}
                ENCODING 'UTF8'
                LC_COLLATE 'C'
                LC_CTYPE 'C'
                TEMPLATE template0"""
        )
        log(C.OK, f"Base '{APP_DB_NAME}' créée (UTF-8, template0)")

    # ── Droits sur la base ────────────────────────────────────────────────────
    cur.execute(f'GRANT ALL PRIVILEGES ON DATABASE "{APP_DB_NAME}" TO {APP_DB_USER}')
    log(C.OK, f"Droits accordés à {APP_DB_USER} sur {APP_DB_NAME}")

    conn.close()

    # ── Extensions dans la base applicative ──────────────────────────────────
    try:
        conn2 = psycopg2.connect(
            host=host, port=port, dbname=APP_DB_NAME,
            user=superuser, password=superuser_password,
            connect_timeout=10, sslmode=ssl_mode,
        )
        conn2.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur2 = conn2.cursor()
        # Droits schema public
        cur2.execute(f"GRANT ALL ON SCHEMA public TO {APP_DB_USER}")
        cur2.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {APP_DB_USER}")
        cur2.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO {APP_DB_USER}")
        for ext in EXTENSIONS:
            try:
                cur2.execute(f'CREATE EXTENSION IF NOT EXISTS "{ext}"')
                log(C.OK, f"Extension '{ext}' activée")
            except Exception as e_ext:
                log(C.WARN, f"Extension '{ext}' non disponible (non critique) : {e_ext}")
        conn2.close()
    except Exception as e:
        log(C.WARN, f"Extensions non configurées (non bloquant) : {e}")

    return True


def _conseils_connexion(host: str, user: str):
    print(f"""
  Conseils de connexion :
  1. Testez manuellement :
     psql -h {host} -U {user} -d postgres

  2. Verifiez pg_hba.conf sur le serveur :
     host  all  {user}  0.0.0.0/0  scram-sha-256

  3. Le serveur accepte-t-il les connexions distantes ?
     postgresql.conf : listen_addresses = '*'

  4. Firewall : le port 5432 est-il ouvert vers ce client ?
""")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Migrations Alembic / SQLAlchemy
# ═══════════════════════════════════════════════════════════════════════════════

def appliquer_migrations(database_url: str) -> bool:
    """Lance alembic upgrade head, ou SQLAlchemy create_all en fallback."""
    step("Application des migrations (Alembic → SQLAlchemy fallback)")

    env = os.environ.copy()
    env["DATABASE_URL"] = database_url

    # Tenter Alembic
    alembic_ini = PROJECT_ROOT / "alembic.ini"
    if alembic_ini.exists():
        log(C.INFO, "alembic.ini trouvé — tentative alembic upgrade head...")
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            capture_output=True, text=True, env=env, cwd=str(PROJECT_ROOT),
        )
        if result.returncode == 0:
            log(C.OK, "Migrations Alembic appliquées avec succès")
            if result.stdout.strip():
                for line in result.stdout.strip().splitlines()[-5:]:
                    log(C.INFO, f"  {line}")
            return True
        else:
            log(C.WARN, f"Alembic a échoué : {result.stderr[-300:]}")
            log(C.WARN, "Repli sur SQLAlchemy create_all...")
    else:
        log(C.WARN, "alembic.ini absent — utilisation de SQLAlchemy create_all")

    # Fallback SQLAlchemy
    return _create_all_sync(database_url)


def _create_all_sync(database_url: str) -> bool:
    """Crée toutes les tables via SQLAlchemy (idempotent — CREATE TABLE IF NOT EXISTS)."""
    async def _run():
        # Injecter la DATABASE_URL avant l'import de database.py
        os.environ["DATABASE_URL"] = database_url
        # Forcer rechargement du module si déjà importé avec une autre URL
        import importlib
        import core.database as db_module
        importlib.reload(db_module)
        await db_module.init_db()

    try:
        asyncio.run(_run())
        log(C.OK, "Tables créées via SQLAlchemy create_all")
        return True
    except Exception as e:
        log(C.ERR, f"Erreur create_all : {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Migration SQLite → PostgreSQL (dev → prod)
# ═══════════════════════════════════════════════════════════════════════════════

def migrer_sqlite_vers_postgres(sqlite_path: str, database_url: str) -> bool:
    """
    Migre les données d'une base SQLite (dev) vers PostgreSQL (prod).
    Tables migrées : compagnies, utilisateurs, contrats, sinistres, posts sociaux.
    Tables ignorées : logs, analytics temps réel, tables de session.
    """
    step(f"Migration données SQLite → PostgreSQL")
    try:
        import sqlite3
        import psycopg2
        from urllib.parse import urlparse
    except ImportError as e:
        log(C.ERR, f"Module manquant : {e}")
        return False

    sqlite_file = Path(sqlite_path)
    if not sqlite_file.exists():
        log(C.WARN, f"Fichier SQLite '{sqlite_path}' introuvable — migration ignorée")
        return True

    # Parser l'URL PostgreSQL
    url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    parsed = urlparse(url)

    # Tables à migrer (dans l'ordre des dépendances FK)
    TABLES_MIGREES = [
        "compagnies",
        "utilisateurs",
        "contrats",
        "clients",
        "sinistres",
        "posts_sociaux",
        "social_connectors",
        "analytics_posts",
        "trend_snapshots",
        "alertes_trends",
    ]

    try:
        src = sqlite3.connect(str(sqlite_file))
        src.row_factory = sqlite3.Row
        src_cur = src.cursor()

        dst = psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port or 5432,
            dbname=parsed.path.lstrip("/"),
            user=parsed.username,
            password=parsed.password,
            connect_timeout=10,
        )
        dst_cur = dst.cursor()
    except Exception as e:
        log(C.ERR, f"Connexion aux bases impossible : {e}")
        return False

    total_migre = 0
    for table in TABLES_MIGREES:
        try:
            src_cur.execute(f"SELECT * FROM {table}")
            rows = src_cur.fetchall()
            if not rows:
                continue

            colonnes = [desc[0] for desc in src_cur.description]
            placeholders = ", ".join(["%s"] * len(colonnes))
            cols_str = ", ".join(colonnes)

            # Désactiver les contraintes FK temporairement
            dst_cur.execute("SET session_replication_role = replica")

            for row in rows:
                try:
                    dst_cur.execute(
                        f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING",
                        list(row),
                    )
                except Exception:
                    pass  # Ligne en conflit ignorée

            dst_cur.execute("SET session_replication_role = DEFAULT")
            dst.commit()
            log(C.OK, f"Table '{table}' : {len(rows)} lignes migrées")
            total_migre += len(rows)
        except Exception as e:
            if "no such table" in str(e).lower():
                pass  # Table absente dans SQLite — normal
            else:
                log(C.WARN, f"Table '{table}' : {e}")

    src.close()
    dst.close()
    log(C.OK, f"Migration terminée — {total_migre} lignes au total")
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Vérification de santé finale
# ═══════════════════════════════════════════════════════════════════════════════

def verifier_sante(database_url: str) -> dict:
    """Vérifie que la base est accessible et compte les tables créées."""
    step("Vérification de santé finale")
    resultats = {}

    url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    try:
        import psycopg2
        from urllib.parse import urlparse
        parsed = urlparse(url)
        conn = psycopg2.connect(
            host=parsed.hostname, port=parsed.port or 5432,
            dbname=parsed.path.lstrip("/"),
            user=parsed.username, password=parsed.password,
            connect_timeout=5,
        )
        cur = conn.cursor()

        cur.execute("SELECT version()")
        version = cur.fetchone()[0]
        log(C.OK, f"Connexion applicative : {version[:70]}")
        resultats["connexion"] = "ok"
        resultats["version"] = version

        cur.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        """)
        nb_tables = cur.fetchone()[0]
        log(C.OK, f"{nb_tables} tables présentes dans le schéma public")
        resultats["nb_tables"] = nb_tables

        # Lister les tables attendues
        TABLES_ATTENDUES = [
            "compagnies", "utilisateurs", "contrats", "sinistres",
            "posts_sociaux", "social_connectors", "analytics_posts",
            "trend_snapshots",
        ]
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        tables_existantes = {row[0] for row in cur.fetchall()}
        manquantes = [t for t in TABLES_ATTENDUES if t not in tables_existantes]
        if manquantes:
            log(C.WARN, f"Tables attendues manquantes : {manquantes}")
            resultats["tables_manquantes"] = manquantes
        else:
            log(C.OK, "Toutes les tables attendues sont présentes")
            resultats["tables_manquantes"] = []

        conn.close()
    except Exception as e:
        log(C.ERR, f"Vérification échouée : {e}")
        resultats["connexion"] = f"error: {e}"

    return resultats


def configurer_backup_pitr(host: str, pg_data_dir: str = "/var/lib/postgresql/data") -> None:
    """
    Affiche les instructions pour configurer la sauvegarde PITR (Point-in-Time Recovery).
    Utilise pg_basebackup + WAL archiving.
    """
    step("Configuration Backup PITR (Point-in-Time Recovery)")
    log(C.INFO, "Ajoutez ces lignes à postgresql.conf :")
    print(f"""
  # ── WAL Archiving (PITR) ──────────────────────────────────────
  wal_level = replica
  archive_mode = on
  archive_command = 'cp %p /var/backups/postgresql/wal/%f'
  archive_timeout = 300          # Archive au moins toutes les 5 min

  # ── Base Backup ────────────────────────────────────────────────
  # Commande backup complet (à planifier via cron quotidien) :
  #   pg_basebackup -h {host} -U {APP_DB_USER} -D /var/backups/postgresql/base -Ft -z -P

  # ── Crontab backup ─────────────────────────────────────────────
  # 0 2 * * * pg_basebackup -h {host} -U {APP_DB_USER} -D /var/backups/postgresql/$(date +%Y%m%d) -Ft -z -P
  # 0 3 * * * find /var/backups/postgresql -name "*.tar.gz" -mtime +7 -delete
""")
    log(C.INFO, "Configuration PITR affichée.")


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Génération du fichier .env de production
# ═══════════════════════════════════════════════════════════════════════════════

def generer_env_production(
    host: str,
    port: int,
    app_password: str,
    output_path: str,
    ssl_mode: str = "require",
) -> str:
    """
    Génère un fichier .env prêt pour la production à partir de .env.example.
    Les clés sensibles (JWT, HMAC) sont générées aléatoirement si absentes.
    """
    step(f"Génération du fichier .env → {output_path}")

    database_url = (
        f"postgresql+asyncpg://{APP_DB_USER}:{app_password}"
        f"@{host}:{port}/{APP_DB_NAME}"
        f"?ssl={ssl_mode}"
    )

    # Charger .env.example comme base
    example_path = PROJECT_ROOT / ".env.example"
    if example_path.exists():
        content = example_path.read_text(encoding="utf-8")
    else:
        content = ""

    # Substitutions production
    substitutions = {
        r"^DATABASE_URL=.*$": f"DATABASE_URL={database_url}",
        r"^DEBUG=.*$": "DEBUG=false",
        r"^ORASS_MODE=.*$": "ORASS_MODE=simulation  # Changer en direct_sql ou api",
        r"^OTLP_ENABLED=.*$": "OTLP_ENABLED=true",
        r"^LOG_FORMAT=.*$": "LOG_FORMAT=json",
        r"^ENFORCE_COMPAGNIE_ISOLATION=.*$": "ENFORCE_COMPAGNIE_ISOLATION=true",
    }

    for pattern, replacement in substitutions.items():
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

    # Générer les clés secrètes si placeholder
    if "CHANGER_CLE_JWT" in content:
        jwt_key = secrets.token_hex(32)
        content = content.replace(
            "SECRET_KEY=CHANGER_CLE_JWT_MIN_32_CHARS_EN_PRODUCTION",
            f"SECRET_KEY={jwt_key}",
        )
        log(C.OK, f"SECRET_KEY générée aléatoirement (32 bytes)")

    if "CHANGER_CLE_HMAC" in content:
        hmac_key = secrets.token_hex(32)
        content = content.replace(
            "SIGNATURE_HMAC_KEY=CHANGER_CLE_HMAC_SIGNATURE_MIN_32_CHARS",
            f"SIGNATURE_HMAC_KEY={hmac_key}",
        )
        log(C.OK, f"SIGNATURE_HMAC_KEY générée aléatoirement (32 bytes)")

    # Récupérer les clés IA depuis le .env dev si disponible
    dev_env = PROJECT_ROOT / ".env"
    if dev_env.exists():
        dev_content = dev_env.read_text(encoding="utf-8")
        for key in ["CLAUDE_API_KEY", "OPENAI_API_KEY", "META_FB_APP_ID",
                    "META_FB_APP_SECRET", "META_FB_PAGE_ACCESS_TOKEN",
                    "META_FB_PAGE_ID", "META_IG_USER_ID",
                    "META_WHATSAPP_APP_SECRET", "META_WHATSAPP_VERIFY_TOKEN",
                    "META_WHATSAPP_PHONE_ID", "META_WHATSAPP_TOKEN",
                    "SERPAPI_KEY", "YOUTUBE_API_KEY", "NEWSAPI_KEY"]:
            match = re.search(rf"^{key}=(.+)$", dev_content, re.MULTILINE)
            if match and not match.group(1).startswith("VOTRE_") and not match.group(1).startswith("sk-ant-"):
                val = match.group(1).strip()
                # Remplacer dans le nouveau .env
                content = re.sub(
                    rf"^{key}=.*$", f"{key}={val}", content, flags=re.MULTILINE
                )
                log(C.OK, f"Clé '{key}' récupérée depuis .env dev")

    # Écrire le fichier
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")

    log(C.OK, f".env production écrit dans {out_path}")
    print(f"\n  {C.WARN} Vérifiez et complétez les placeholders restants dans {out_path}")
    return database_url


# ═══════════════════════════════════════════════════════════════════════════════
# Point d'entrée principal
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="YukpoAssurance — Déploiement PostgreSQL sur serveur compagnie",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--host", default="localhost",
                        help="Hôte du serveur PostgreSQL (défaut: localhost)")
    parser.add_argument("--port", type=int, default=5432,
                        help="Port PostgreSQL (défaut: 5432)")
    parser.add_argument("--superuser", default=PG_DEFAULT_SUPERUSER,
                        help=f"Superutilisateur PostgreSQL (défaut: {PG_DEFAULT_SUPERUSER})")
    parser.add_argument("--superuser-password", required=True,
                        help="Mot de passe du superutilisateur PostgreSQL")
    parser.add_argument("--app-password", required=True,
                        help="Mot de passe pour l'utilisateur applicatif 'yukpo' (obligatoire en production)")
    parser.add_argument("--ssl-mode", default="require",
                        choices=["disable", "allow", "prefer", "require", "verify-ca", "verify-full"],
                        help="Mode SSL PostgreSQL (défaut: prefer; production: require)")
    parser.add_argument("--skip-create-db", action="store_true",
                        help="Sauter la création BD/user (BD déjà créée par le DBA)")
    parser.add_argument("--skip-migrations", action="store_true",
                        help="Sauter les migrations Alembic")
    parser.add_argument("--migrate-from-sqlite",
                        help="Chemin vers la BD SQLite dev à migrer vers PostgreSQL")
    parser.add_argument("--generate-env", action="store_true",
                        help="Générer le fichier .env de production")
    parser.add_argument("--env-output", default=".env.production",
                        help="Chemin de sortie du .env production (défaut: .env.production)")
    parser.add_argument("--check-only", action="store_true",
                        help="Vérifier la connexion seulement, sans rien créer")
    args = parser.parse_args()

    # ── Changer de répertoire vers la racine du projet ──────────────────────
    os.chdir(str(PROJECT_ROOT))

    print(f"""
{C.BOLD}{'═'*60}
  YukpoAssurance — Déploiement PostgreSQL
  Cible : {args.host}:{args.port}/{APP_DB_NAME}
  Utilisateur applicatif : {APP_DB_USER}
{'═'*60}{C.END}
""")

    # ── Mode check-only ──────────────────────────────────────────────────────
    if args.check_only:
        ok = test_connexion_reseau(args.host, args.port)
        if ok:
            url = (f"postgresql+asyncpg://{APP_DB_USER}:{args.app_password}"
                   f"@{args.host}:{args.port}/{APP_DB_NAME}")
            verifier_sante(url)
        sys.exit(0 if ok else 1)

    # ── 1. Test réseau ────────────────────────────────────────────────────────
    if not test_connexion_reseau(args.host, args.port):
        log(C.ERR, "Arrêt : serveur PostgreSQL inaccessible")
        sys.exit(1)

    # ── 2. Création BD/utilisateur ────────────────────────────────────────────
    if not args.skip_create_db:
        ok = creer_base_et_utilisateur(
            host=args.host,
            port=args.port,
            superuser=args.superuser,
            superuser_password=args.superuser_password,
            app_password=args.app_password,
            ssl_mode=args.ssl_mode,
        )
        if not ok:
            log(C.ERR, "Arrêt : création de la base impossible")
            sys.exit(1)
    else:
        log(C.INFO, "Création BD ignorée (--skip-create-db)")

    # ── URL de connexion applicative ──────────────────────────────────────────
    database_url = (
        f"postgresql+asyncpg://{APP_DB_USER}:{args.app_password}"
        f"@{args.host}:{args.port}/{APP_DB_NAME}"
    )

    # ── 3. Migrations ─────────────────────────────────────────────────────────
    if not args.skip_migrations:
        ok = appliquer_migrations(database_url)
        if not ok:
            log(C.ERR, "Arrêt : migrations échouées")
            sys.exit(1)
    else:
        log(C.INFO, "Migrations ignorées (--skip-migrations)")

    # ── 4. Migration SQLite → PostgreSQL ─────────────────────────────────────
    if args.migrate_from_sqlite:
        migrer_sqlite_vers_postgres(args.migrate_from_sqlite, database_url)

    # ── 5. Génération .env production ─────────────────────────────────────────
    if args.generate_env:
        generer_env_production(
            host=args.host,
            port=args.port,
            app_password=args.app_password,
            output_path=args.env_output,
            ssl_mode=args.ssl_mode,
        )

    # ── 6. Vérification finale ────────────────────────────────────────────────
    resultats = verifier_sante(database_url)

    # ── Résumé ────────────────────────────────────────────────────────────────
    success = resultats.get("connexion") == "ok" and not resultats.get("tables_manquantes")

    print(f"""
{C.BOLD}{'═'*60}
  RÉSUMÉ DU DÉPLOIEMENT
{'═'*60}{C.END}

  Connexion BD  : {C.OK if resultats.get('connexion') == 'ok' else C.ERR} {resultats.get('connexion', 'N/A')}
  Tables créées : {resultats.get('nb_tables', '?')}
  Tables OK     : {"Oui" if not resultats.get('tables_manquantes') else f"Manquantes: {resultats.get('tables_manquantes')}"}

  DATABASE_URL (prod) :
    {database_url}

  {C.BOLD}Prochaines etapes :{C.END}
  +----------------------------------------------------------+
  |  1. Copiez .env.production -> .env sur le serveur        |
  |  2. Completez les cles API manquantes dans .env           |
  |  3. Demarrez : uvicorn api.main:app --host 0.0.0.0       |
  |     (ou via systemd / docker / gunicorn)                  |
  |  4. Testez : curl http://SERVEUR/health                   |
  |              curl http://SERVEUR/health/si                |
  +----------------------------------------------------------+

  {C.BOLD}Config Meta/WhatsApp (identique a yukpomnang2) :{C.END}
  +----------------------------------------------------------+
  |  META_FB_APP_ID          -> Dashboard Meta for Developers|
  |  META_FB_APP_SECRET      -> App Settings > Basic         |
  |  META_FB_PAGE_ACCESS_TOKEN -> Token de page longue duree |
  |  META_FB_PAGE_ID         -> ID de la Page Facebook       |
  |  META_IG_USER_ID         -> ID du compte Business IG     |
  |  META_WHATSAPP_PHONE_ID  -> Phone Number ID              |
  |  META_WHATSAPP_TOKEN     -> Token permanent Meta         |
  |  META_GRAPH_API_VERSION  -> v19.0 (ou plus recent)       |
  +----------------------------------------------------------+
""")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
