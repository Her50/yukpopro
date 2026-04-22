"""Ajout table utilisateurs — authentification production

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-09

Ajoute la table 'utilisateurs' pour remplacer le login simulation
par une vraie authentification bcrypt + RBAC.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "utilisateurs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("nom", sa.String(100), nullable=False),
        sa.Column("prenoms", sa.String(150), nullable=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="agent"),
        sa.Column("compagnie_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("actif", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("telephone", sa.String(30), nullable=True),
        sa.Column("code_agent", sa.String(30), nullable=True),
        sa.Column("nb_connexions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("derniere_connexion", sa.DateTime(), nullable=True),
        sa.Column("tentatives_echec", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bloque_jusqu_au", sa.DateTime(), nullable=True),
        sa.Column("cree_le", sa.DateTime(), nullable=False),
        sa.Column("modifie_le", sa.DateTime(), nullable=True),
        sa.Column("cree_par", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_utilisateurs_username", "utilisateurs", ["username"], unique=True)
    op.create_index("ix_utilisateurs_email", "utilisateurs", ["email"], unique=True)
    op.create_index("ix_utilisateurs_code_agent", "utilisateurs", ["code_agent"], unique=False)

    # Créer un compte admin par défaut (mot de passe à changer IMMÉDIATEMENT)
    # Hash bcrypt de "yukpo_admin_2026_CHANGER" — à modifier avant la mise en production
    op.execute(
        """
        INSERT INTO utilisateurs
            (username, email, nom, hashed_password, role, compagnie_id, actif, nb_connexions, tentatives_echec, cree_le)
        VALUES
            ('admin', 'admin@yukpo.local', 'Administrateur',
             '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBp2JLVVibqBNS',
             'admin', 1, true, 0, 0, CURRENT_TIMESTAMP)
        ON CONFLICT (username) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_utilisateurs_code_agent", table_name="utilisateurs")
    op.drop_index("ix_utilisateurs_email", table_name="utilisateurs")
    op.drop_index("ix_utilisateurs_username", table_name="utilisateurs")
    op.drop_table("utilisateurs")
