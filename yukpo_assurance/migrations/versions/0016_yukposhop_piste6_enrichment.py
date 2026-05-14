"""Piste 6a — Enrichissement IA produit YukpoShop via Rust marketplace.

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-14

Au moment du sync Piste 1, Rust appelle GPT-4o-mini pour enrichir le
produit (catégorie auto, tags, specialized_type, description enrichie
si vide, language detection, quality_score). YukpoShop store le résultat
pour l'afficher dans son UI sans regénérer.
"""
from alembic import op
import sqlalchemy as sa


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = [
        ("yukpo_category", sa.String(60)),
        ("yukpo_specialized_type", sa.String(80)),
        ("yukpo_tags_json", sa.JSON()),
        ("yukpo_description_enriched", sa.Text()),
        ("yukpo_language_detected", sa.String(8)),
        ("yukpo_quality_score", sa.Integer()),
        ("yukpo_enriched_at", sa.DateTime()),
        ("yukpo_enrichment_cost_tokens", sa.Integer()),
    ]
    for name, type_ in cols:
        op.add_column("shop_products", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    for name in [
        "yukpo_enrichment_cost_tokens", "yukpo_enriched_at",
        "yukpo_quality_score", "yukpo_language_detected",
        "yukpo_description_enriched", "yukpo_tags_json",
        "yukpo_specialized_type", "yukpo_category",
    ]:
        op.drop_column("shop_products", name)
