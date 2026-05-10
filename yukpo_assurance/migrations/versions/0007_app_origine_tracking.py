"""Add app_origine column to consommations_tokens and consommations_bureau.

Revision ID: 0007_app_origine_tracking
Revises: 0006_payments_v2
Create Date: 2026-05-10

Permet de filtrer la consommation IA par application source (yukpopro vs
yukposecretariat) dans le dashboard admin unifié /admin-cross/*. Backfill
des lignes existantes : 'pro' pour consommations_tokens, 'sec' pour
consommations_bureau (la table d'origine est l'indicateur historique).

Index composite (app_origine, cree_le) pour les agrégations temporelles
filtrées par scope, qui sont la requête dominante du dashboard.
"""
from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # consommations_tokens (origine YukpoPro)
    op.add_column(
        "consommations_tokens",
        sa.Column("app_origine", sa.String(10), nullable=False, server_default="pro"),
    )
    op.create_index(
        "ix_consommations_tokens_app_cree",
        "consommations_tokens",
        ["app_origine", "cree_le"],
    )

    # consommations_bureau (origine YukpoSecrétariat)
    op.add_column(
        "consommations_bureau",
        sa.Column("app_origine", sa.String(10), nullable=False, server_default="sec"),
    )
    op.create_index(
        "ix_consommations_bureau_app_cree",
        "consommations_bureau",
        ["app_origine", "cree_le"],
    )

    # Backfill explicite (au cas où le server_default n'aurait pas suffi
    # sur des lignes pré-existantes selon la version Postgres).
    op.execute("UPDATE consommations_tokens SET app_origine = 'pro' WHERE app_origine IS NULL OR app_origine = ''")
    op.execute("UPDATE consommations_bureau SET app_origine = 'sec' WHERE app_origine IS NULL OR app_origine = ''")


def downgrade() -> None:
    op.drop_index("ix_consommations_bureau_app_cree", table_name="consommations_bureau")
    op.drop_column("consommations_bureau", "app_origine")
    op.drop_index("ix_consommations_tokens_app_cree", table_name="consommations_tokens")
    op.drop_column("consommations_tokens", "app_origine")
