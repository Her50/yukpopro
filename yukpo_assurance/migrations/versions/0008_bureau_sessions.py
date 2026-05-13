"""Bureau Sessions unifiées (modification incrémentale tous pipelines).

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-13

Mémorise le dernier fichier produit par n'importe quel pipeline bureau
(infographe mono, freeform, designer_pro, rapport, slides, geometric)
pour permettre des modifications ciblées via /modifier sans régénération
from scratch.

TTL 30 minutes après dernière interaction. Une session active à la fois
par utilisateur (la plus récente).
"""
from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bureau_sessions",
        sa.Column("session_id", sa.String(36), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), nullable=False, index=True),
        sa.Column("pipeline", sa.String(40), nullable=True),
        sa.Column("dernier_fichier_id", sa.String(200), nullable=True),
        sa.Column("dernier_brief", sa.String(2000), nullable=True),
        sa.Column("dernier_layout_json", sa.JSON(), nullable=True),
        sa.Column("historique", sa.JSON(), server_default="[]"),
        sa.Column("derniere_interaction", sa.DateTime(),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("cree_le", sa.DateTime(),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_bureau_sessions_user_interaction",
        "bureau_sessions",
        ["user_id", "derniere_interaction"],
    )


def downgrade() -> None:
    op.drop_index("ix_bureau_sessions_user_interaction", "bureau_sessions")
    op.drop_table("bureau_sessions")
