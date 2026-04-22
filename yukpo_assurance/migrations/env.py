"""Alembic env.py — configuré pour YukpoAssurance avec SQLAlchemy async."""
import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Ajouter le répertoire racine au path pour les imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Alembic Config
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import des modèles pour autogenerate
from core.database import Base  # noqa: E402
target_metadata = Base.metadata

# URL depuis la variable d'environnement ou alembic.ini
def get_url() -> str:
    from config.settings import settings
    url = settings.DATABASE_URL
    # Alembic ne supporte pas asyncpg directement — utiliser psycopg2 pour les migrations
    if "asyncpg" in url:
        url = url.replace("postgresql+asyncpg", "postgresql+psycopg2")
    elif url.startswith("sqlite+aiosqlite"):
        url = url.replace("sqlite+aiosqlite", "sqlite")
    return url


def run_migrations_offline() -> None:
    """Mode offline : génère le SQL sans connexion."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Mode online avec moteur async."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from config.settings import settings

    # Pour les migrations, on utilise une URL synchrone si possible
    url = get_url()
    if "psycopg2" in url or url.startswith("sqlite"):
        from sqlalchemy import create_engine
        connectable = create_engine(url, poolclass=pool.NullPool)
        with connectable.connect() as conn:
            do_run_migrations(conn)
    else:
        connectable = create_async_engine(settings.DATABASE_URL, poolclass=pool.NullPool)
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
        await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
