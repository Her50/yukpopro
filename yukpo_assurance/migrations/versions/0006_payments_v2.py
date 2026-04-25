"""Payment system v2 — wallet, transactions multi-provider, attempts, commissions.

Revision ID: 0006_payments_v2
Revises: 0005_profil_pays_extension
Create Date: 2026-04-25

Tables ajoutées :
  - wallet_yukpopro            : portefeuille interne (crédits + cash optionnel)
  - payment_transactions_v2    : transactions multi-provider unifiées
  - payment_attempts           : tentatives successives (cascade providers)
  - payment_webhook_events     : audit log webhooks reçus

L'ancien `commande_paiement` (legacy) est conservé pour compat — il sert
maintenant uniquement au flux fallback "validation manuelle admin".
"""
from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wallet_yukpopro",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("compagnie_id", sa.BigInteger, nullable=False, index=True),
        sa.Column("user_id", sa.BigInteger, nullable=True, index=True),
        sa.Column("solde_credits_yukpo", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("solde_cash_fcfa", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("devise", sa.String(8), nullable=False, server_default="XAF"),
        sa.Column("kyc_verifie", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("statut", sa.String(16), nullable=False, server_default="actif"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("compagnie_id", "user_id", name="uq_wallet_compagnie_user"),
    )

    op.create_table(
        "payment_transactions_v2",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("reference", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("compagnie_id", sa.BigInteger, nullable=False, index=True),
        sa.Column("user_id", sa.BigInteger, nullable=True, index=True),
        sa.Column("type", sa.String(24), nullable=False),  # abonnement | recharge | service
        sa.Column("plan_ou_pack", sa.String(32), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="XAF"),
        sa.Column("country_code", sa.String(2), nullable=True),
        sa.Column("customer_phone", sa.String(24), nullable=True, index=True),
        sa.Column("customer_email", sa.String(120), nullable=True),
        sa.Column("provider", sa.String(24), nullable=True, index=True),
        sa.Column("provider_reference", sa.String(120), nullable=True, index=True),
        sa.Column("payment_method", sa.String(24), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending", index=True),
        sa.Column("payment_url", sa.Text, nullable=True),
        sa.Column("ussd_instructions", sa.Text, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("metadata_json", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now(), index=True),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "payment_attempts",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("transaction_id", sa.BigInteger, sa.ForeignKey("payment_transactions_v2.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("provider", sa.String(24), nullable=False),
        sa.Column("provider_reference", sa.String(120), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("response_payload", sa.JSON, nullable=True),
        sa.Column("attempted_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "payment_webhook_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(24), nullable=False, index=True),
        sa.Column("provider_reference", sa.String(120), nullable=True, index=True),
        sa.Column("transaction_id", sa.BigInteger, sa.ForeignKey("payment_transactions_v2.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("status_received", sa.String(16), nullable=True),
        sa.Column("signature_valid", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("raw_payload", sa.JSON, nullable=True),
        sa.Column("received_at", sa.DateTime, nullable=False, server_default=sa.func.now(), index=True),
    )

    op.create_index("ix_pay_tx_v2_compagnie_status", "payment_transactions_v2", ["compagnie_id", "status"])
    op.create_index("ix_pay_tx_v2_provider_status", "payment_transactions_v2", ["provider", "status"])


def downgrade() -> None:
    op.drop_index("ix_pay_tx_v2_provider_status", "payment_transactions_v2")
    op.drop_index("ix_pay_tx_v2_compagnie_status", "payment_transactions_v2")
    op.drop_table("payment_webhook_events")
    op.drop_table("payment_attempts")
    op.drop_table("payment_transactions_v2")
    op.drop_table("wallet_yukpopro")
