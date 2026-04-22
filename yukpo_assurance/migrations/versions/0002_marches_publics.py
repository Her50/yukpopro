"""Ajout colonnes marchés publics sur profils_pro

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-17
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_columns("profils_pro")}

    if "marches_publics_recents" not in existing:
        op.add_column("profils_pro", sa.Column("marches_publics_recents", sa.JSON, nullable=True))
    if "derniere_recherche_marches" not in existing:
        op.add_column("profils_pro", sa.Column("derniere_recherche_marches", sa.DateTime, nullable=True))


def downgrade() -> None:
    op.drop_column("profils_pro", "derniere_recherche_marches")
    op.drop_column("profils_pro", "marches_publics_recents")
