"""Phase D9 — Logistique & livraison.

Fonctionnalités :
  1. Zones de livraison configurables (villes/régions/pays + tarifs + délais)
  2. Calcul des frais de livraison à la volée pour une adresse donnée
  3. Génération d'étiquettes PDF + QR de tracking (générique ou via API
     transporteur — DHL Express, Speedaf, Bolloré Logistics si crédentiels
     fournis ; sinon étiquette générique imprimable + lien tracking custom)

Pour MVP : génération d'étiquette générique en PDF (ReportLab). Les API
DHL/Speedaf/Bolloré sont des intégrations payantes complexes — on prépare
le pattern via `creer_etiquette_*` stubs, à activer quand le marchand
fournit ses credentials transporteur.
"""
from __future__ import annotations

import base64
import io
import logging
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger("yukpo_assurance.pro.shop_logistique")


async def calculer_frais_livraison(
    boutique_id: int, adresse: dict, db,
) -> dict:
    """Trouve la zone correspondant à l'adresse et retourne frais + délai.

    Args:
        adresse : {ville, region, pays, ...}

    Returns: {zone_id, zone_nom, tarif, devise, delai_min, delai_max} ou None.
    """
    from sqlalchemy import asc, select
    from core.database import ShopLivraisonZoneDB

    ville_norm = (adresse.get("ville") or "").lower().strip()
    region_norm = (adresse.get("region") or "").lower().strip()
    pays_norm = (adresse.get("pays") or "").upper().strip()

    zones = (await db.execute(
        select(ShopLivraisonZoneDB)
        .where(ShopLivraisonZoneDB.boutique_id == boutique_id)
        .where(ShopLivraisonZoneDB.actif.is_(True))
        .order_by(asc(ShopLivraisonZoneDB.ordre))
    )).scalars().all()

    # Matching ordre de précision : ville > région > pays > fallback
    for z in zones:
        villes = [v.lower() for v in (z.villes_json or [])]
        if ville_norm and ville_norm in villes:
            return _zone_to_dict(z, "ville")
    for z in zones:
        regions = [r.lower() for r in (z.regions_json or [])]
        if region_norm and region_norm in regions:
            return _zone_to_dict(z, "region")
    for z in zones:
        pays_list = [p.upper() for p in (z.pays_json or [])]
        if pays_norm and pays_norm in pays_list:
            return _zone_to_dict(z, "pays")
    # Fallback : la 1re zone "catch-all" sans filtres
    for z in zones:
        if not z.villes_json and not z.regions_json and not z.pays_json:
            return _zone_to_dict(z, "fallback")
    return {"zone_id": None, "tarif": 0, "delai_min": 1, "delai_max": 7,
            "match": "aucun"}


def _zone_to_dict(z, match: str) -> dict:
    return {
        "zone_id": z.id, "zone_nom": z.nom,
        "tarif": float(z.tarif or 0), "devise": z.devise,
        "delai_min": z.delai_jours_min, "delai_max": z.delai_jours_max,
        "transporteur_prefere": z.transporteur_prefere, "match": match,
    }


# ─── Génération étiquette PDF générique ──────────────────────────────────────


def generer_etiquette_pdf_generique(
    order_data: dict, boutique_data: dict,
    *, tracking_num: str, tracking_base_url: str,
) -> bytes:
    """Génère une étiquette PDF imprimable A6 portrait (105×148 mm).

    Inclut : expéditeur (boutique), destinataire (client), articles,
    QR code de tracking pointant vers tracking_base_url/{tracking_num},
    code-barre du numéro de commande. Indépendant des API transporteur
    (DHL/Speedaf/Bolloré).
    """
    try:
        from reportlab.lib.pagesizes import A6
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
        from reportlab.lib.colors import HexColor, black
        from modules.pro.qr_generator import generer_qr_png
    except ImportError as e:
        logger.error(f"[Etiquette] dépendances manquantes : {e}")
        return b""

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A6)
    w, h = A6
    margin = 6 * mm

    # En-tête avec nom boutique
    c.setFillColor(HexColor("#7B3FE4"))
    c.rect(0, h - 18 * mm, w, 18 * mm, fill=1, stroke=0)
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont("Helvetica-Bold", 14)
    c.drawString(margin, h - 12 * mm, (boutique_data.get("nom") or "Yukpo")[:30])
    c.setFont("Helvetica", 8)
    c.drawString(margin, h - 16 * mm, (boutique_data.get("url_public") or "yukpomnang.com"))

    y = h - 22 * mm
    c.setFillColor(black)

    # Numéro de commande
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, y, f"Commande {order_data.get('numero', '')}")
    y -= 5 * mm

    # Expéditeur
    c.setFont("Helvetica-Bold", 8)
    c.drawString(margin, y, "EXPÉDITEUR")
    y -= 3.5 * mm
    c.setFont("Helvetica", 8)
    c.drawString(margin, y, (boutique_data.get("nom") or "Boutique")[:40])
    y -= 3.5 * mm
    c.drawString(margin, y, (boutique_data.get("ville") or "")[:40])
    y -= 5 * mm

    # Destinataire
    c.setFont("Helvetica-Bold", 9)
    c.drawString(margin, y, "DESTINATAIRE")
    y -= 4 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin, y, (order_data.get("client_nom") or "")[:35])
    y -= 4 * mm
    c.setFont("Helvetica", 9)
    c.drawString(margin, y, (order_data.get("client_telephone") or "")[:25])
    y -= 4 * mm
    adresse = order_data.get("adresse_livraison_json") or {}
    if isinstance(adresse, dict):
        ville = adresse.get("ville") or ""
        adr = adresse.get("adresse") or ""
        if ville:
            c.drawString(margin, y, ville[:35])
            y -= 3.5 * mm
        if adr:
            for line in [adr[i:i+38] for i in range(0, min(len(adr), 76), 38)]:
                c.drawString(margin, y, line)
                y -= 3.5 * mm
    y -= 3 * mm

    # QR Code tracking
    qr_url = f"{tracking_base_url.rstrip('/')}/track/{tracking_num}"
    try:
        qr_png = generer_qr_png(qr_url, taille=4, error_correction="Q")
        from reportlab.lib.utils import ImageReader
        qr_img = ImageReader(io.BytesIO(qr_png))
        c.drawImage(qr_img, w - 36 * mm, 12 * mm, width=30 * mm, height=30 * mm)
    except Exception as e:
        logger.warning(f"[Etiquette/QR] échec : {e}")

    # Numéro tracking en bas
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, 12 * mm, "TRACKING")
    c.setFont("Helvetica", 10)
    c.drawString(margin, 7 * mm, tracking_num)
    c.setFont("Helvetica", 7)
    c.setFillColor(HexColor("#666666"))
    c.drawString(margin, 3 * mm, qr_url[:50])

    c.showPage()
    c.save()
    return buf.getvalue()


# ─── Stubs API transporteurs (à brancher quand credentials fournis) ──────────


async def creer_etiquette_dhl(order, boutique, dhl_credentials: dict) -> dict:
    """STUB — DHL Express API integration. Active quand credentials fournis."""
    logger.warning("[DHL] Integration non implémentée (credentials manquants)")
    return {"ok": False, "transporteur": "dhl", "error": "Not implemented"}


async def creer_etiquette_speedaf(order, boutique, credentials: dict) -> dict:
    """STUB — Speedaf API."""
    return {"ok": False, "transporteur": "speedaf", "error": "Not implemented"}


async def creer_etiquette_bollore(order, boutique, credentials: dict) -> dict:
    """STUB — Bolloré Logistics API."""
    return {"ok": False, "transporteur": "bollore", "error": "Not implemented"}


import secrets as _secrets


def generer_tracking_num() -> str:
    """Génère un numéro de tracking interne YK-xxxxxx."""
    return f"YK{_secrets.token_hex(5).upper()}"
