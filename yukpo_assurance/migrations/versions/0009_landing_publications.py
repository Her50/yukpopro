"""Landing pages publication + leads capture (Phase A Sprint 1).

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-13

Deux nouvelles tables :
  • landing_publications : trace les landings déployées sur Netlify
    (slug, site_id, url publique, plan, footer custom). Unicité du slug
    garantie globalement (sous-domaine *.yukpomnang.com).
  • landing_leads       : leads capturés par le formulaire de contact
    public des landings publiées. Lié au slug (ON DELETE CASCADE).
"""
from alembic import op
import sqlalchemy as sa


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "landing_publications",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False, index=True),
        sa.Column("slug", sa.String(60), nullable=False, unique=True),
        sa.Column("netlify_site_id", sa.String(64), nullable=False),
        sa.Column("url_public", sa.String(255), nullable=False),
        sa.Column("html_fichier_id", sa.String(200), nullable=False),
        sa.Column("plan", sa.String(16), nullable=False, server_default="free"),
        sa.Column("footer_custom", sa.Text(), nullable=True),
        sa.Column("cree_le", sa.DateTime(),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("derniere_modif", sa.DateTime(),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_landing_pub_user", "landing_publications", ["user_id"]
    )

    op.create_table(
        "landing_leads",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(60),
                  sa.ForeignKey("landing_publications.slug",
                                ondelete="CASCADE"),
                  nullable=False),
        sa.Column("nom", sa.String(120), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("telephone", sa.String(40), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("source", sa.String(40), nullable=False,
                  server_default="form"),
        sa.Column("ip_hash", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("statut", sa.String(20), nullable=False,
                  server_default="non_lu"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_landing_leads_slug", "landing_leads", ["slug"]
    )
    op.create_index(
        "ix_landing_leads_slug_statut",
        "landing_leads", ["slug", "statut"],
    )
    op.create_index(
        "ix_landing_leads_created", "landing_leads", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_landing_leads_created", "landing_leads")
    op.drop_index("ix_landing_leads_slug_statut", "landing_leads")
    op.drop_index("ix_landing_leads_slug", "landing_leads")
    op.drop_table("landing_leads")
    op.drop_index("ix_landing_pub_user", "landing_publications")
    op.drop_table("landing_publications")
