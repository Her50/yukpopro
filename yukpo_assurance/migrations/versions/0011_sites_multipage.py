"""Phase C — Mini-sites multi-pages (Site = collection de pages liées).

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-13

Trois tables :
  • sites           : 1 site = N pages, déployé en bloc sur Netlify
  • pages           : pages structurelles (home, services, equipe, contact, …)
  • pages_articles  : articles de blog (séparés des pages structurelles
                      car volume potentiellement élevé + scheduling)

Un site est créé par génération LLM (chat) puis publié sur Netlify avec
arborescence multi-fichiers HTML + sitemap.xml + robots.txt.
"""
from alembic import op
import sqlalchemy as sa


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


_TYPES_PAGE = (
    "home", "services", "equipe", "blog_index", "contact",
    "mentions_legales", "cgv", "confidentialite", "tarifs",
    "a_propos", "portfolio", "faq",
)


def upgrade() -> None:
    op.create_table(
        "sites",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False, index=True),
        sa.Column("slug", sa.String(60), nullable=False, unique=True),
        sa.Column("nom", sa.String(120), nullable=False,
                  comment="Nom commercial du site"),
        sa.Column("brief", sa.Text(), nullable=True,
                  comment="Brief original utilisateur ayant généré le site"),
        sa.Column("theme_json", sa.JSON(), nullable=True,
                  comment="Couleurs primary/secondary/accent + fonts (BrandKit override)"),
        sa.Column("brand_kit_json", sa.JSON(), nullable=True),
        sa.Column("langue_principale", sa.String(8),
                  nullable=False, server_default="fr"),
        sa.Column("langues_actives_json", sa.JSON(), nullable=True,
                  comment="Liste des codes ISO 639-1 des langues traduites disponibles"),
        sa.Column("netlify_site_id", sa.String(64), nullable=True),
        sa.Column("url_public", sa.String(255), nullable=True),
        sa.Column("plan", sa.String(16), nullable=False, server_default="free"),
        sa.Column("statut", sa.String(20), nullable=False, server_default="brouillon",
                  comment="brouillon | publie | suspendu"),
        sa.Column("cree_le", sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("publie_le", sa.DateTime(), nullable=True),
        sa.Column("derniere_modif", sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_sites_user", "sites", ["user_id"])

    op.create_table(
        "site_pages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("site_id", sa.BigInteger(),
                  sa.ForeignKey("sites.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("type", sa.String(32), nullable=False,
                  comment="home | services | equipe | contact | mentions_legales | ..."),
        sa.Column("slug_page", sa.String(80), nullable=False,
                  comment="Slug dans l'URL : / pour home, /services, /equipe, etc."),
        sa.Column("titre_seo", sa.String(120), nullable=True),
        sa.Column("description_seo", sa.String(200), nullable=True),
        sa.Column("contenu_json", sa.JSON(), nullable=False,
                  comment="Spec JSON LLM (sections, images, etc.) — rendue en HTML au publish"),
        sa.Column("ordre", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("langue", sa.String(8), nullable=False, server_default="fr"),
        sa.Column("publiee", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("cree_le", sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("modifie_le", sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
        # Unicité : 1 seule version d'un (site, type, langue)
        sa.UniqueConstraint("site_id", "type", "langue",
                             name="uq_site_pages_type_lang"),
    )
    op.create_index("ix_site_pages_site", "site_pages", ["site_id"])
    op.create_index("ix_site_pages_type", "site_pages", ["type"])

    op.create_table(
        "site_articles",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("site_id", sa.BigInteger(),
                  sa.ForeignKey("sites.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("slug", sa.String(120), nullable=False,
                  comment="Slug d'article — unique par site"),
        sa.Column("titre", sa.String(200), nullable=False),
        sa.Column("resume", sa.String(400), nullable=True),
        sa.Column("contenu_md", sa.Text(), nullable=True,
                  comment="Contenu Markdown rédigé par Sonnet"),
        sa.Column("hero_image_url", sa.String(500), nullable=True),
        sa.Column("auteur", sa.String(120), nullable=True),
        sa.Column("langue", sa.String(8), nullable=False, server_default="fr"),
        sa.Column("seo_titre", sa.String(120), nullable=True),
        sa.Column("seo_desc", sa.String(200), nullable=True),
        sa.Column("seo_keywords_json", sa.JSON(), nullable=True),
        sa.Column("publie", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("publie_le", sa.DateTime(), nullable=True,
                  comment="Si dans le futur → publication programmée"),
        sa.Column("cree_le", sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("site_id", "slug", name="uq_site_articles_slug"),
    )
    op.create_index("ix_site_articles_site_pub", "site_articles",
                    ["site_id", "publie", "publie_le"])


def downgrade() -> None:
    op.drop_index("ix_site_articles_site_pub", "site_articles")
    op.drop_table("site_articles")
    op.drop_index("ix_site_pages_type", "site_pages")
    op.drop_index("ix_site_pages_site", "site_pages")
    op.drop_table("site_pages")
    op.drop_index("ix_sites_user", "sites")
    op.drop_table("sites")
