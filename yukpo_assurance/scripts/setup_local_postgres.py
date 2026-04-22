#!/usr/bin/env python3
"""
YukpoAssurance — Script de configuration PostgreSQL local pour développement/tests.

Usage :
    python scripts/setup_local_postgres.py
    python scripts/setup_local_postgres.py --pg-password VOTRE_MOT_DE_PASSE
    python scripts/setup_local_postgres.py --pg-password VOTRE_MOT_DE_PASSE --create-tables

Ce script :
  1. Se connecte à PostgreSQL en tant que superutilisateur
  2. Crée l'utilisateur yukpo et la base yukpo_assurance
  3. Applique les migrations Alembic (si --create-tables)
  4. Vérifie la connexion finale

Si vous ne connaissez pas le mot de passe postgres :
  Windows : ouvrir pgAdmin > Server > Properties > Connection
         ou : psql -U postgres    (depuis le CMD en tant qu'admin)
         ou : pg_dump ... -W      (vérification manuelle)
"""
import argparse
import sys
import os
import subprocess

# Ajout du parent au path pour imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

YUKPO_DB_USER = "yukpo"
YUKPO_DB_PASSWORD = "yukpo_secret_2025"
YUKPO_DB_NAME = "yukpo_assurance"
PG_HOST = "localhost"
PG_PORT = "5432"


def setup_postgres(pg_password: str, create_tables: bool = False):
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

    print(f"[Setup] Connexion à PostgreSQL en tant que superutilisateur...")
    try:
        conn = psycopg2.connect(
            host=PG_HOST,
            port=int(PG_PORT),
            dbname="postgres",
            user="postgres",
            password=pg_password,
            connect_timeout=5,
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
    except Exception as e:
        print(f"[ERREUR] Connexion superutilisateur impossible : {e}")
        print("\nConseils :")
        print("  1. Ouvrez pgAdmin et notez le mot de passe postgres")
        print("  2. Ou : psql -U postgres (dans CMD en tant qu'administrateur)")
        print("  3. Ou passez --pg-password VOTRE_MDP en argument")
        sys.exit(1)

    # Créer l'utilisateur yukpo
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (YUKPO_DB_USER,))
    if not cur.fetchone():
        cur.execute(
            f"CREATE ROLE {YUKPO_DB_USER} LOGIN PASSWORD %s",
            (YUKPO_DB_PASSWORD,),
        )
        print(f"[OK] Utilisateur '{YUKPO_DB_USER}' créé")
    else:
        cur.execute(
            f"ALTER ROLE {YUKPO_DB_USER} WITH PASSWORD %s LOGIN",
            (YUKPO_DB_PASSWORD,),
        )
        print(f"[OK] Utilisateur '{YUKPO_DB_USER}' déjà existant (mot de passe mis à jour)")

    # Créer la base de données
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (YUKPO_DB_NAME,))
    if not cur.fetchone():
        cur.execute(f'CREATE DATABASE "{YUKPO_DB_NAME}" OWNER {YUKPO_DB_USER} ENCODING \'UTF8\'')
        print(f"[OK] Base de données '{YUKPO_DB_NAME}' créée")
    else:
        cur.execute(f'ALTER DATABASE "{YUKPO_DB_NAME}" OWNER TO {YUKPO_DB_USER}')
        print(f"[OK] Base de données '{YUKPO_DB_NAME}' déjà existante")

    # Extensions utiles
    try:
        # Se connecter à la nouvelle base pour créer les extensions
        conn2 = psycopg2.connect(
            host=PG_HOST, port=int(PG_PORT), dbname=YUKPO_DB_NAME,
            user="postgres", password=pg_password, connect_timeout=5,
        )
        conn2.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur2 = conn2.cursor()
        for ext in ["uuid-ossp", "pg_trgm", "pgcrypto"]:
            try:
                cur2.execute(f'CREATE EXTENSION IF NOT EXISTS "{ext}"')
            except Exception:
                pass
        conn2.close()
        print("[OK] Extensions PostgreSQL activées (uuid-ossp, pg_trgm, pgcrypto)")
    except Exception as e:
        print(f"[Warning] Extensions non créées (non critique) : {e}")

    conn.close()

    # Vérifier la connexion yukpo
    print(f"\n[Setup] Vérification de la connexion yukpo...")
    try:
        conn_test = psycopg2.connect(
            host=PG_HOST, port=int(PG_PORT), dbname=YUKPO_DB_NAME,
            user=YUKPO_DB_USER, password=YUKPO_DB_PASSWORD, connect_timeout=5,
        )
        cur_test = conn_test.cursor()
        cur_test.execute("SELECT version()")
        ver = cur_test.fetchone()[0]
        conn_test.close()
        print(f"[OK] Connexion yukpo vérifiée : {ver[:60]}")
    except Exception as e:
        print(f"[ERREUR] Connexion yukpo impossible : {e}")
        sys.exit(1)

    # Migrations Alembic
    if create_tables:
        print("\n[Setup] Application des migrations Alembic...")
        env = os.environ.copy()
        env["DATABASE_URL"] = (
            f"postgresql+asyncpg://{YUKPO_DB_USER}:{YUKPO_DB_PASSWORD}"
            f"@{PG_HOST}:{PG_PORT}/{YUKPO_DB_NAME}"
        )
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            capture_output=True, text=True, env=env,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        if result.returncode == 0:
            print("[OK] Tables créées via Alembic")
        else:
            print("[Warning] Alembic indisponible, utilisation de SQLAlchemy create_all()...")
            _create_tables_sync()
    else:
        print("\n[Setup] Tables non créées (passez --create-tables pour les créer)")

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  YukpoAssurance — PostgreSQL local configuré avec succès !  ║
╠══════════════════════════════════════════════════════════════╣
║  Host     : {PG_HOST}:{PG_PORT}
║  Base     : {YUKPO_DB_NAME}
║  User     : {YUKPO_DB_USER}
║  Password : {YUKPO_DB_PASSWORD}
║
║  DATABASE_URL = postgresql+asyncpg://{YUKPO_DB_USER}:{YUKPO_DB_PASSWORD}
║                 @{PG_HOST}:{PG_PORT}/{YUKPO_DB_NAME}
║
║  Prochaine étape :
║    uvicorn api.main:app --reload
╚══════════════════════════════════════════════════════════════╝
""")


def _create_tables_sync():
    """Crée les tables directement via SQLAlchemy (fallback si Alembic absent)."""
    import asyncio

    async def _run():
        from core.database import init_db
        await init_db()
        print("[OK] Tables créées via SQLAlchemy (create_all)")

    asyncio.run(_run())


def setup_sqlite():
    """Configure SQLite pour les tests sans PostgreSQL."""
    import asyncio

    print("[Setup] Configuration SQLite pour les tests locaux...")
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")

    # Lire .env actuel
    with open(env_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Commenter PostgreSQL, décommenter SQLite
    if "DATABASE_URL=postgresql" in content and "# DATABASE_URL=sqlite" not in content:
        content = content.replace(
            "DATABASE_URL=postgresql+asyncpg://yukpo:yukpo_secret_2025@localhost:5432/yukpo_assurance",
            "# DATABASE_URL=postgresql+asyncpg://yukpo:yukpo_secret_2025@localhost:5432/yukpo_assurance  # PostgreSQL prod\n"
            "DATABASE_URL=sqlite+aiosqlite:///./yukpo_assurance_dev.db  # SQLite local dev",
        )
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(content)
        print("[OK] .env mis à jour : SQLite activé pour dev local")

    async def _run():
        from core.database import init_db
        await init_db()
        print("[OK] Base SQLite créée : yukpo_assurance_dev.db")

    asyncio.run(_run())
    print("\n[OK] Prêt. Lancez : uvicorn api.main:app --reload")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Configure PostgreSQL local pour YukpoAssurance")
    parser.add_argument("--pg-password", default="", help="Mot de passe du superutilisateur postgres")
    parser.add_argument("--create-tables", action="store_true", help="Créer les tables après setup")
    parser.add_argument("--sqlite", action="store_true", help="Utiliser SQLite (sans PostgreSQL)")
    args = parser.parse_args()

    # Changer le répertoire de travail vers la racine du projet
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)

    if args.sqlite:
        setup_sqlite()
    elif args.pg_password:
        setup_postgres(args.pg_password, create_tables=args.create_tables)
    else:
        print(__doc__)
        print("\nOptions rapides :")
        print("  --sqlite              → SQLite local immédiat (aucun PostgreSQL requis)")
        print("  --pg-password MOT_DE_PASSE --create-tables  → PostgreSQL complet")
        print("\nExemple :")
        print("  python scripts/setup_local_postgres.py --pg-password mon_mdp --create-tables")
        sys.exit(0)
