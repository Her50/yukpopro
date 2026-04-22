"""Ajout 2FA TOTP et indexes de performance

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-09
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Colonnes 2FA ──────────────────────────────────────────────────────────
    with op.batch_alter_table("utilisateurs") as batch_op:
        batch_op.add_column(sa.Column("totp_secret", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("totp_active", sa.Boolean(), nullable=False, server_default="false"))

    # ── Index de performance ──────────────────────────────────────────────────
    # Utilisateurs
    op.create_index("ix_utilisateurs_compagnie_role", "utilisateurs", ["compagnie_id", "role"])
    op.create_index("ix_utilisateurs_actif", "utilisateurs", ["actif"])

    # Sinistres (si table existe)
    try:
        op.create_index("ix_sinistres_compagnie_statut", "sinistres", ["compagnie_id", "statut"])
        op.create_index("ix_sinistres_date_survenance", "sinistres", ["date_survenance"])
        op.create_index("ix_sinistres_numero_police", "sinistres", ["numero_police"])
    except Exception:
        pass

    # Contrats (si table existe)
    try:
        op.create_index("ix_contrats_compagnie", "contrats", ["compagnie_id"])
        op.create_index("ix_contrats_date_echeance", "contrats", ["date_echeance"])
        op.create_index("ix_contrats_statut", "contrats", ["statut"])
    except Exception:
        pass

    # Chat sessions (si table existe)
    try:
        op.create_index("ix_sessions_chat_compagnie", "sessions_chat", ["compagnie_id"])
        op.create_index("ix_sessions_chat_user_cree", "sessions_chat", ["user_id", "cree_le"])
    except Exception:
        pass

    # Audit (si table existe)
    try:
        op.create_index("ix_audit_logs_compagnie_ts", "audit_logs", ["compagnie_id", "timestamp"])
        op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    except Exception:
        pass


def downgrade() -> None:
    # Supprimer les index
    for idx_name in [
        "ix_utilisateurs_compagnie_role", "ix_utilisateurs_actif",
        "ix_sinistres_compagnie_statut", "ix_sinistres_date_survenance",
        "ix_sinistres_numero_police", "ix_contrats_compagnie",
        "ix_contrats_date_echeance", "ix_contrats_statut",
        "ix_sessions_chat_compagnie", "ix_sessions_chat_user_cree",
        "ix_audit_logs_compagnie_ts", "ix_audit_logs_user_id",
    ]:
        try:
            op.drop_index(idx_name)
        except Exception:
            pass

    # Supprimer colonnes 2FA
    with op.batch_alter_table("utilisateurs") as batch_op:
        batch_op.drop_column("totp_active")
        batch_op.drop_column("totp_secret")
