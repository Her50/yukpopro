"""Étendre profils_pro.pays de String(5) à String(64) pour supporter les noms de pays complets

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-24
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "profils_pro",
        "pays",
        existing_type=sa.String(5),
        type_=sa.String(64),
        existing_nullable=False,
        existing_server_default=None,
    )


def downgrade() -> None:
    op.alter_column(
        "profils_pro",
        "pays",
        existing_type=sa.String(64),
        type_=sa.String(5),
        existing_nullable=False,
    )
