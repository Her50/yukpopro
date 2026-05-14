"""Piste 2 — Cross-sell storefront via search Yukpo Rust marketplace.

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-14

Une seule colonne ajoutée :
  shop_boutiques.cross_sell_enabled BOOLEAN DEFAULT TRUE
    Toggle d'opt-out par boutique pour le bloc "Autres marchands près de
    chez vous" injecté dans le storefront. Activé par défaut (le commerçant
    a tout intérêt à recevoir du trafic croisé tant que ses concurrents
    directs ne squattent pas sa fiche).
"""
from alembic import op
import sqlalchemy as sa


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "shop_boutiques",
        sa.Column(
            "cross_sell_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
            comment="Si True, le storefront affiche un bloc 'Autres "
                    "marchands près de chez vous' (search Rust marketplace).",
        ),
    )


def downgrade() -> None:
    op.drop_column("shop_boutiques", "cross_sell_enabled")
