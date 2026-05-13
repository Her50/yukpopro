"""Génération QR code PNG pour landing pages publiées (Phase A1).

Utilise la lib `qrcode[pil]` (déjà installée — initialement pour 2FA).
Petite couche autour pour produire bytes PNG + base64 data URI.
"""
from __future__ import annotations

import base64
import io
import logging
from typing import Literal

logger = logging.getLogger("yukpo_assurance.pro.qr")


def generer_qr_png(
    url: str,
    *,
    taille: int = 8,
    border: int = 2,
    error_correction: Literal["L", "M", "Q", "H"] = "M",
) -> bytes:
    """Génère un QR code PNG bytes pointant vers `url`.

    `taille` = box_size pixels par module (8 → ~320px de côté pour URL courte).
    `error_correction` H = 30% redondance (logo overlay possible),
    M = 15% (défaut, bon équilibre densité).
    """
    import qrcode
    from qrcode.constants import (
        ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q, ERROR_CORRECT_H,
    )
    ec_map = {
        "L": ERROR_CORRECT_L, "M": ERROR_CORRECT_M,
        "Q": ERROR_CORRECT_Q, "H": ERROR_CORRECT_H,
    }
    qr = qrcode.QRCode(
        version=None,
        error_correction=ec_map[error_correction],
        box_size=taille,
        border=border,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0F172A", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def png_data_uri(png_bytes: bytes) -> str:
    """Convertit bytes PNG en data URI base64 prêt pour <img src>."""
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode()
