"""Piste 1 — YukpoShop -> Yukpo Rust bridge (publication produit dans marketplace).

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-14

Colonnes ajoutées :

shop_boutiques :
  - rust_sync_enabled BOOLEAN DEFAULT TRUE
    Permet à un commerçant de désactiver la publication marketplace par
    boutique (privacy / brand control).

shop_products :
  - rust_service_id          : Service.id côté Rust si publié, NULL sinon
  - rust_sync_status         : pending | synced | failed | disabled | skipped
  - rust_sync_error          : message d'erreur du dernier échec (debug)
  - rust_synced_at           : timestamp du dernier sync OK
  - rust_sync_attempts       : compteur (cap retry à 5)
"""
from alembic import op
import sqlalchemy as sa


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "shop_boutiques",
        sa.Column(
            "rust_sync_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
            comment="Si True, les produits publiés sont aussi indexés "
                    "dans le marketplace Yukpo Rust pour trafic gratuit.",
        ),
    )

    op.add_column(
        "shop_products",
        sa.Column("rust_service_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "shop_products",
        sa.Column(
            "rust_sync_status",
            sa.String(20),
            nullable=False,
            server_default="pending",
            comment="pending | synced | failed | disabled | skipped",
        ),
    )
    op.add_column(
        "shop_products",
        sa.Column("rust_sync_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "shop_products",
        sa.Column("rust_synced_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "shop_products",
        sa.Column(
            "rust_sync_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # Index pour requêter rapidement les produits en attente de sync
    op.create_index(
        "ix_shop_products_rust_sync_status",
        "shop_products",
        ["rust_sync_status"],
        postgresql_where=sa.text("rust_sync_status IN ('pending','failed')"),
    )


def downgrade() -> None:
    op.drop_index("ix_shop_products_rust_sync_status", table_name="shop_products")
    op.drop_column("shop_products", "rust_sync_attempts")
    op.drop_column("shop_products", "rust_synced_at")
    op.drop_column("shop_products", "rust_sync_error")
    op.drop_column("shop_products", "rust_sync_status")
    op.drop_column("shop_products", "rust_service_id")
    op.drop_column("shop_boutiques", "rust_sync_enabled")
