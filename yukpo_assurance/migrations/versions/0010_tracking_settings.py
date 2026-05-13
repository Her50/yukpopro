"""Phase B — Tracking analytics & follow-up automation par user.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-13

Deux tables :
  • tracking_settings        : config Plausible + pixels (FB/GA4/TikTok/
                               Snap/Clarity) + newsletter (Brevo/Mailchimp)
  • landing_followup_settings: config emails auto post-lead (J+0/J+3/J+7)

Une ligne par user (user_id en clé primaire). Réutilisé par les landings
A (single-page) ET les sites multi-pages Phase C.
"""
from alembic import op
import sqlalchemy as sa


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tracking_settings",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        # Plausible : self-hosted ou cloud — on stocke juste l'activation
        # par user. La config globale du provider Plausible reste env-only
        # (PLAUSIBLE_SCRIPT_URL, PLAUSIBLE_API_KEY).
        sa.Column("plausible_actif", sa.Boolean(),
                  nullable=False, server_default=sa.true()),
        # Pixels publicitaires — un ID texte par plateforme.
        sa.Column("fb_pixel_id", sa.String(40), nullable=True),
        sa.Column("ga4_measurement_id", sa.String(40), nullable=True),
        sa.Column("tiktok_pixel_id", sa.String(40), nullable=True),
        sa.Column("snap_pixel_id", sa.String(40), nullable=True),
        sa.Column("clarity_project_id", sa.String(40), nullable=True),
        # Newsletter — provider + API key + list_id
        sa.Column("newsletter_provider", sa.String(20), nullable=True,
                  comment="brevo | mailchimp | none"),
        sa.Column("newsletter_api_key", sa.String(120), nullable=True),
        sa.Column("newsletter_list_id", sa.String(80), nullable=True),
        sa.Column("modif_le", sa.DateTime(),
                  nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "landing_followup_settings",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        # J+0 : auto-reply au visiteur dès la capture du lead
        sa.Column("j0_actif", sa.Boolean(),
                  nullable=False, server_default=sa.false()),
        sa.Column("j0_sujet", sa.String(160), nullable=True),
        sa.Column("j0_corps", sa.Text(), nullable=True),
        # J+3 follow-up si lead encore non_lu côté marchand
        sa.Column("j3_actif", sa.Boolean(),
                  nullable=False, server_default=sa.false()),
        sa.Column("j3_sujet", sa.String(160), nullable=True),
        sa.Column("j3_corps", sa.Text(), nullable=True),
        # J+7 dernière relance
        sa.Column("j7_actif", sa.Boolean(),
                  nullable=False, server_default=sa.false()),
        sa.Column("j7_sujet", sa.String(160), nullable=True),
        sa.Column("j7_corps", sa.Text(), nullable=True),
        sa.Column("modif_le", sa.DateTime(),
                  nullable=False, server_default=sa.func.now()),
    )

    # Indices sur landing_leads pour les jobs de relance (scan rapide)
    op.create_index(
        "ix_landing_leads_followup",
        "landing_leads", ["created_at", "statut"],
    )


def downgrade() -> None:
    op.drop_index("ix_landing_leads_followup", "landing_leads")
    op.drop_table("landing_followup_settings")
    op.drop_table("tracking_settings")
