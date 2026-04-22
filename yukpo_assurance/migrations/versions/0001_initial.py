"""Schema initial YukpoAssurance — toutes les tables

Revision ID: 0001
Revises:
Create Date: 2026-04-09

Strategie : utilise Base.metadata.create_all() sur la connexion sync
fournie par Alembic. Toutes les tables definies dans core/database.py
sont creees d'un coup. Les migrations suivantes peuvent utiliser
op.add_column() / op.create_table() / etc.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Cree toutes les tables du schema initial."""
    bind = op.get_bind()

    # Importer les metadonnees apres que le moteur est pret
    import sys
    import os
    # S'assurer que la racine du projet est dans le path
    root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)

    from core.database import Base
    # create_all est idempotent (checkfirst=True par defaut)
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    """Supprime toutes les tables du schema."""
    bind = op.get_bind()

    import sys
    import os
    root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)

    from core.database import Base
    # Attention : supprime TOUTES les donnees. Irreversible en production.
    Base.metadata.drop_all(bind=bind)
