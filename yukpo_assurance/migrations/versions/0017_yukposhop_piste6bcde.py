"""Piste 6 b/c/d/e — VideoFeed + Recommendations + Modération IA + Google Places.

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-14

shop_products :
  - video_url, video_thumbnail_url (6b VideoFeed mobile Yukpo)
  - yukpo_ai_moderation_status, yukpo_ai_moderation_reason (6d via LLM)

shop_boutiques :
  - gps, adresse_complete, google_place_id, google_rating,
    google_horaires_json, telephone, google_enriched_at (6e Google Places)
"""
from alembic import op
import sqlalchemy as sa


revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 6b VideoFeed
    op.add_column("shop_products", sa.Column("video_url", sa.String(500), nullable=True))
    op.add_column("shop_products", sa.Column("video_thumbnail_url", sa.String(500), nullable=True))
    # 6d Moderation IA
    op.add_column("shop_products", sa.Column("yukpo_ai_moderation_status", sa.String(20), nullable=True))
    op.add_column("shop_products", sa.Column("yukpo_ai_moderation_reason", sa.Text(), nullable=True))
    # 6e Google Places
    op.add_column("shop_boutiques", sa.Column("gps", sa.String(60), nullable=True))
    op.add_column("shop_boutiques", sa.Column("adresse_complete", sa.String(400), nullable=True))
    op.add_column("shop_boutiques", sa.Column("google_place_id", sa.String(120), nullable=True))
    op.add_column("shop_boutiques", sa.Column("google_rating", sa.Float(), nullable=True))
    op.add_column("shop_boutiques", sa.Column("google_horaires_json", sa.JSON(), nullable=True))
    op.add_column("shop_boutiques", sa.Column("telephone", sa.String(40), nullable=True))
    op.add_column("shop_boutiques", sa.Column("google_enriched_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    for col in [
        "google_enriched_at", "telephone", "google_horaires_json",
        "google_rating", "google_place_id", "adresse_complete", "gps",
    ]:
        op.drop_column("shop_boutiques", col)
    for col in [
        "yukpo_ai_moderation_reason", "yukpo_ai_moderation_status",
        "video_thumbnail_url", "video_url",
    ]:
        op.drop_column("shop_products", col)
