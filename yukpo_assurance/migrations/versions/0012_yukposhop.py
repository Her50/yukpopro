"""Phase D — YukpoShop e-commerce (catalogue produits + commandes).

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-13

5 tables :
  • shop_boutiques  : configuration boutique par marchand (lié 1-1 à user_id)
  • shop_products   : produits du marchand (avec photos R2 URLs, variantes JSON)
  • shop_categories : catégories arborescentes par boutique
  • shop_orders     : commandes clients (avec adresse livraison + paiement)
  • shop_order_items: lignes de commande (produit × quantité × variante)

Le storefront public sera servi via Netlify multi-fichiers (réutilise
la même infra que Phase C sites) sous <slug>.yukpomnang.com.
"""
from alembic import op
import sqlalchemy as sa


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Boutique du marchand (1 par user, sous-domaine custom)
    op.create_table(
        "shop_boutiques",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False, unique=True, index=True),
        sa.Column("slug", sa.String(60), nullable=False, unique=True),
        sa.Column("nom", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("logo_url", sa.String(500), nullable=True),
        sa.Column("brand_kit_json", sa.JSON(), nullable=True),
        sa.Column("devise", sa.String(8), nullable=False, server_default="XAF",
                  comment="Devise principale de la boutique (XAF/XOF/MAD/NGN/EUR/USD)"),
        sa.Column("pays_principal", sa.String(8), nullable=False, server_default="CM"),
        sa.Column("langues_actives_json", sa.JSON(), nullable=True),
        sa.Column("netlify_site_id", sa.String(64), nullable=True),
        sa.Column("url_public", sa.String(255), nullable=True),
        sa.Column("plan", sa.String(16), nullable=False, server_default="free"),
        sa.Column("statut", sa.String(20), nullable=False, server_default="brouillon"),
        sa.Column("settings_json", sa.JSON(), nullable=True,
                  comment="Paramètres : zones livraison, providers paiement actifs, ..."),
        sa.Column("cree_le", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("publie_le", sa.DateTime(), nullable=True),
        sa.Column("derniere_modif", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # 2. Catégories arborescentes
    op.create_table(
        "shop_categories",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("boutique_id", sa.BigInteger(),
                  sa.ForeignKey("shop_boutiques.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("nom", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("parent_id", sa.BigInteger(),
                  sa.ForeignKey("shop_categories.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("ordre", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(500), nullable=True),
        sa.Column("cree_le", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("boutique_id", "slug", name="uq_shop_cat_slug"),
    )

    # 3. Produits
    op.create_table(
        "shop_products",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("boutique_id", sa.BigInteger(),
                  sa.ForeignKey("shop_boutiques.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("sku", sa.String(64), nullable=True, index=True),
        sa.Column("titre", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("description_courte", sa.String(400), nullable=True),
        sa.Column("description_longue", sa.Text(), nullable=True),
        sa.Column("prix_unit", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("prix_unit_promo", sa.Numeric(12, 2), nullable=True,
                  comment="Si non-null et < prix_unit → produit en promo"),
        sa.Column("devise", sa.String(8), nullable=False, server_default="XAF"),
        sa.Column("tva_pct", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("stock", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stock_alerte", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("photos_urls_json", sa.JSON(), nullable=True,
                  comment="Array URLs R2 ou data-uri (max 10 photos)"),
        sa.Column("categorie_id", sa.BigInteger(),
                  sa.ForeignKey("shop_categories.id", ondelete="SET NULL"),
                  nullable=True, index=True),
        sa.Column("tags_json", sa.JSON(), nullable=True),
        sa.Column("variantes_json", sa.JSON(), nullable=True,
                  comment="[{nom: 'Taille', valeur: 'M', prix_diff: 0, stock: 5}, …]"),
        sa.Column("seo_titre", sa.String(120), nullable=True),
        sa.Column("seo_desc", sa.String(200), nullable=True),
        sa.Column("seo_keywords_json", sa.JSON(), nullable=True),
        sa.Column("statut", sa.String(20), nullable=False, server_default="actif",
                  comment="actif | brouillon | archive | rupture"),
        sa.Column("source", sa.String(20), nullable=False, server_default="manuel",
                  comment="manuel | import_ia | api | csv"),
        sa.Column("cree_le", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("modif_le", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("boutique_id", "slug", name="uq_shop_prod_slug"),
    )
    op.create_index("ix_shop_products_boutique_statut", "shop_products",
                    ["boutique_id", "statut"])

    # 4. Commandes
    op.create_table(
        "shop_orders",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("boutique_id", sa.BigInteger(),
                  sa.ForeignKey("shop_boutiques.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("numero", sa.String(40), nullable=False, unique=True,
                  comment="Numéro commande lisible humain (YK-2026-00001)"),
        # Client final (peut être anonyme/invité)
        sa.Column("client_user_id", sa.Integer(), nullable=True, index=True),
        sa.Column("client_nom", sa.String(120), nullable=True),
        sa.Column("client_email", sa.String(255), nullable=True),
        sa.Column("client_telephone", sa.String(40), nullable=True),
        sa.Column("adresse_livraison_json", sa.JSON(), nullable=True,
                  comment="{rue, ville, region, code_postal, pays, instructions}"),
        sa.Column("zone_livraison", sa.String(80), nullable=True),
        sa.Column("montant_produits", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("montant_livraison", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("montant_tva", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("montant_remise", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("montant_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("devise", sa.String(8), nullable=False, server_default="XAF"),
        sa.Column("code_promo", sa.String(40), nullable=True),
        sa.Column("statut", sa.String(20), nullable=False, server_default="en_attente_paiement",
                  comment="en_attente_paiement | payee | en_preparation | expediee | livree | annulee | remboursee"),
        sa.Column("paiement_provider", sa.String(40), nullable=True,
                  comment="stripe | flutterwave | orange_money | mtn_momo | wave | campay | cinetpay"),
        sa.Column("paiement_ref", sa.String(120), nullable=True),
        sa.Column("paiement_statut", sa.String(20), nullable=False, server_default="en_attente"),
        sa.Column("paye_le", sa.DateTime(), nullable=True),
        sa.Column("expedie_le", sa.DateTime(), nullable=True),
        sa.Column("livre_le", sa.DateTime(), nullable=True),
        sa.Column("tracking_url", sa.String(500), nullable=True),
        sa.Column("source", sa.String(40), nullable=False, server_default="storefront",
                  comment="storefront | whatsapp | instagram | tiktok | facebook | api"),
        sa.Column("utm_source", sa.String(80), nullable=True),
        sa.Column("utm_campaign", sa.String(120), nullable=True),
        sa.Column("notes_marchand", sa.Text(), nullable=True),
        sa.Column("notes_client", sa.Text(), nullable=True),
        sa.Column("cree_le", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("modif_le", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_shop_orders_boutique_statut", "shop_orders",
                    ["boutique_id", "statut", "cree_le"])
    op.create_index("ix_shop_orders_client", "shop_orders",
                    ["client_telephone", "client_email"])

    # 5. Lignes de commande
    op.create_table(
        "shop_order_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.BigInteger(),
                  sa.ForeignKey("shop_orders.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("product_id", sa.BigInteger(),
                  sa.ForeignKey("shop_products.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("titre", sa.String(200), nullable=False,
                  comment="Snapshot titre au moment de la commande"),
        sa.Column("variante_label", sa.String(120), nullable=True,
                  comment="Ex: 'Taille M / Couleur Rouge'"),
        sa.Column("variante_json", sa.JSON(), nullable=True),
        sa.Column("quantite", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("prix_unit", sa.Numeric(12, 2), nullable=False),
        sa.Column("photo_url", sa.String(500), nullable=True),
        sa.Column("cree_le", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("shop_order_items")
    op.drop_index("ix_shop_orders_client", "shop_orders")
    op.drop_index("ix_shop_orders_boutique_statut", "shop_orders")
    op.drop_table("shop_orders")
    op.drop_index("ix_shop_products_boutique_statut", "shop_products")
    op.drop_table("shop_products")
    op.drop_table("shop_categories")
    op.drop_table("shop_boutiques")
