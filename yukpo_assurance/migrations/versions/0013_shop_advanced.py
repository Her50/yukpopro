"""Phase D suite (D6 + D7 + D8 + D9) — social sync + ads ROAS + CRM + logistique.

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-13

7 nouvelles tables :
  D6 :  shop_social_integrations   — credentials OAuth Meta/TikTok par boutique
  D6 :  shop_social_publications   — historique posts FB/IG auto-générés
  D7 :  shop_ads_integrations      — credentials OAuth FB Ads / Google Ads
  D7 :  shop_ads_metrics           — métriques par campagne et jour
  D8 :  shop_clients               — profil 360° client final
  D8 :  shop_client_events         — événements visit/cart/order/dm/comment
  D9 :  shop_livraison_zones       — zones livraison + tarifs
  D9 :  shop_livraison_etiquettes  — étiquettes générées (DHL/Speedaf/local)
"""
from alembic import op
import sqlalchemy as sa


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── D6 — Social integrations ────────────────────────────────────────
    op.create_table(
        "shop_social_integrations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("boutique_id", sa.BigInteger(),
                  sa.ForeignKey("shop_boutiques.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("platform", sa.String(20), nullable=False,
                  comment="meta_fb | meta_ig | meta_wa_business | tiktok_shop | pinterest"),
        sa.Column("page_id", sa.String(64), nullable=True,
                  comment="ID Facebook Page / IG Business / TikTok Shop / etc."),
        sa.Column("catalog_id", sa.String(64), nullable=True,
                  comment="Meta Commerce Catalog ID si Catalog Sync activé"),
        sa.Column("access_token_chiffre", sa.Text(), nullable=True,
                  comment="Access token chiffré côté app (jamais en clair en DB)"),
        sa.Column("refresh_token_chiffre", sa.Text(), nullable=True),
        sa.Column("expire_le", sa.DateTime(), nullable=True),
        sa.Column("scope_json", sa.JSON(), nullable=True),
        sa.Column("compte_username", sa.String(120), nullable=True),
        sa.Column("statut", sa.String(20), nullable=False, server_default="actif",
                  comment="actif | suspendu | expire | erreur"),
        sa.Column("derniere_sync", sa.DateTime(), nullable=True),
        sa.Column("derniere_erreur", sa.Text(), nullable=True),
        sa.Column("cree_le", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("modif_le", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("boutique_id", "platform", name="uq_shop_social_platform"),
    )

    op.create_table(
        "shop_social_publications",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("boutique_id", sa.BigInteger(),
                  sa.ForeignKey("shop_boutiques.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("product_id", sa.BigInteger(),
                  sa.ForeignKey("shop_products.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("type_post", sa.String(20), nullable=False,
                  comment="post_feed | story | reel | catalog_item"),
        sa.Column("post_external_id", sa.String(120), nullable=True),
        sa.Column("post_url", sa.String(500), nullable=True),
        sa.Column("contenu_md", sa.Text(), nullable=True),
        sa.Column("statut", sa.String(20), nullable=False, server_default="publie",
                  comment="programmé | publie | erreur | supprime"),
        sa.Column("statistiques_json", sa.JSON(), nullable=True,
                  comment="{vues, likes, partages, commentaires, clics, conversions}"),
        sa.Column("publie_le", sa.DateTime(), nullable=True),
        sa.Column("cree_le", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_shop_social_pub_boutique", "shop_social_publications",
                    ["boutique_id", "publie_le"])

    # ─── D7 — Ads integrations + métriques ROAS ─────────────────────────
    op.create_table(
        "shop_ads_integrations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("boutique_id", sa.BigInteger(),
                  sa.ForeignKey("shop_boutiques.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("platform", sa.String(20), nullable=False,
                  comment="fb_ads | google_ads | tiktok_ads | snapchat_ads"),
        sa.Column("ad_account_id", sa.String(80), nullable=False),
        sa.Column("access_token_chiffre", sa.Text(), nullable=True),
        sa.Column("refresh_token_chiffre", sa.Text(), nullable=True),
        sa.Column("expire_le", sa.DateTime(), nullable=True),
        sa.Column("derniere_sync", sa.DateTime(), nullable=True),
        sa.Column("derniere_erreur", sa.Text(), nullable=True),
        sa.Column("statut", sa.String(20), nullable=False, server_default="actif"),
        sa.Column("cree_le", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("boutique_id", "platform", "ad_account_id",
                             name="uq_shop_ads_account"),
    )

    op.create_table(
        "shop_ads_metrics",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("boutique_id", sa.BigInteger(),
                  sa.ForeignKey("shop_boutiques.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("campagne_id", sa.String(80), nullable=False),
        sa.Column("campagne_nom", sa.String(200), nullable=True),
        sa.Column("ad_set_id", sa.String(80), nullable=True),
        sa.Column("ad_id", sa.String(80), nullable=True),
        sa.Column("jour", sa.Date(), nullable=False, index=True),
        sa.Column("depenses", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("impressions", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("clics", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("conversions_externes", sa.BigInteger(), nullable=False, server_default="0",
                  comment="Conversions remontées par la plateforme pub"),
        sa.Column("conversions_locales", sa.BigInteger(), nullable=False, server_default="0",
                  comment="Commandes Yukpo matchées (UTM/fbclid/gclid)"),
        sa.Column("revenu_local", sa.Numeric(12, 2), nullable=False, server_default="0",
                  comment="Revenu généré par les commandes matchées"),
        sa.Column("devise", sa.String(8), nullable=False, server_default="XAF"),
        sa.Column("derniere_maj", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("boutique_id", "platform", "campagne_id", "jour",
                             name="uq_shop_ads_metric_day"),
    )
    op.create_index("ix_shop_ads_metrics_boutique_jour", "shop_ads_metrics",
                    ["boutique_id", "jour"])

    # ─── D8 — CRM clients + scoring churn ───────────────────────────────
    op.create_table(
        "shop_clients",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("boutique_id", sa.BigInteger(),
                  sa.ForeignKey("shop_boutiques.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("telephone", sa.String(40), nullable=True, index=True),
        sa.Column("email", sa.String(255), nullable=True, index=True),
        sa.Column("nom", sa.String(120), nullable=True),
        sa.Column("ville", sa.String(120), nullable=True),
        sa.Column("source_acquisition", sa.String(40), nullable=True,
                  comment="organic | facebook | instagram | tiktok | google_ads | bouche | referral | …"),
        sa.Column("premiere_commande_le", sa.DateTime(), nullable=True),
        sa.Column("derniere_commande_le", sa.DateTime(), nullable=True),
        sa.Column("nb_commandes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revenu_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("ltv_predite", sa.Numeric(12, 2), nullable=True,
                  comment="Lifetime Value prédite par scoring IA"),
        sa.Column("score_churn_pct", sa.Integer(), nullable=True,
                  comment="0-100, % chance de ne plus acheter dans les 90j"),
        sa.Column("segment", sa.String(20), nullable=True,
                  comment="vip | recurrent | dormant | risque | new"),
        sa.Column("recos_ia_json", sa.JSON(), nullable=True,
                  comment="Recommandations cross-sell / relance suggérées par IA"),
        sa.Column("derniere_analyse_le", sa.DateTime(), nullable=True),
        sa.Column("notes_marchand", sa.Text(), nullable=True),
        sa.Column("cree_le", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("modif_le", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("boutique_id", "telephone", name="uq_shop_client_tel"),
    )
    op.create_index("ix_shop_clients_segment", "shop_clients",
                    ["boutique_id", "segment"])

    op.create_table(
        "shop_client_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("client_id", sa.BigInteger(),
                  sa.ForeignKey("shop_clients.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("type_event", sa.String(40), nullable=False,
                  comment="visit_produit | ajout_panier | commande | dm_recu | "
                          "comment_post | story_view | reach_page"),
        sa.Column("product_id", sa.BigInteger(),
                  sa.ForeignKey("shop_products.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("source", sa.String(40), nullable=True,
                  comment="storefront | whatsapp | facebook | instagram | tiktok | api"),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now(),
                  index=True),
    )

    # ─── D9 — Logistique zones + étiquettes ─────────────────────────────
    op.create_table(
        "shop_livraison_zones",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("boutique_id", sa.BigInteger(),
                  sa.ForeignKey("shop_boutiques.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("nom", sa.String(120), nullable=False,
                  comment="Ex: 'Douala intra-muros', 'Yaoundé', 'Reste du Cameroun', 'International'"),
        sa.Column("villes_json", sa.JSON(), nullable=True,
                  comment="Liste de villes/quartiers couverts (filtrage adresse)"),
        sa.Column("regions_json", sa.JSON(), nullable=True),
        sa.Column("pays_json", sa.JSON(), nullable=True),
        sa.Column("tarif", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("devise", sa.String(8), nullable=False, server_default="XAF"),
        sa.Column("delai_jours_min", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("delai_jours_max", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("transporteur_prefere", sa.String(40), nullable=True,
                  comment="dhl | speedaf | bollore | local_whatsapp | … (humain ou API)"),
        sa.Column("ordre", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actif", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("cree_le", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "shop_livraison_etiquettes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.BigInteger(),
                  sa.ForeignKey("shop_orders.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("transporteur", sa.String(40), nullable=False),
        sa.Column("tracking_num", sa.String(80), nullable=True, index=True),
        sa.Column("etiquette_pdf_url", sa.String(500), nullable=True),
        sa.Column("etiquette_qr_url", sa.String(500), nullable=True),
        sa.Column("statut", sa.String(20), nullable=False, server_default="creee",
                  comment="creee | imprimee | enlevee | livree | retournee"),
        sa.Column("cout_transport", sa.Numeric(10, 2), nullable=True),
        sa.Column("date_enlevement", sa.DateTime(), nullable=True),
        sa.Column("date_livraison", sa.DateTime(), nullable=True),
        sa.Column("response_api_json", sa.JSON(), nullable=True,
                  comment="Réponse brute de l'API transporteur (debug)"),
        sa.Column("cree_le", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("shop_livraison_etiquettes")
    op.drop_table("shop_livraison_zones")
    op.drop_table("shop_client_events")
    op.drop_index("ix_shop_clients_segment", "shop_clients")
    op.drop_table("shop_clients")
    op.drop_index("ix_shop_ads_metrics_boutique_jour", "shop_ads_metrics")
    op.drop_table("shop_ads_metrics")
    op.drop_table("shop_ads_integrations")
    op.drop_index("ix_shop_social_pub_boutique", "shop_social_publications")
    op.drop_table("shop_social_publications")
    op.drop_table("shop_social_integrations")
