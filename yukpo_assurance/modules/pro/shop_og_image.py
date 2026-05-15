"""Génération d'OG image dynamique pour produits YukpoShop.

Composition 1200×630 (ratio standard Facebook/WhatsApp/X/LinkedIn) :
  • Photo produit en arrière-plan (couvre toute la zone, blur léger derrière)
  • Bandeau bas gradient → prix + titre + logo + URL boutique
  • Watermark logo en haut à droite

Output : bytes PNG. Sauvegardé dans storage shop_branding et URL injectée
dans <meta property="og:image">.
"""
from __future__ import annotations

import io
import logging
from typing import Optional

logger = logging.getLogger("yukpo_assurance.pro.shop_og_image")

_WIDTH = 1200
_HEIGHT = 630
_PADDING = 40


def _fetch_image_bytes(url: str, timeout: float = 5.0) -> Optional[bytes]:
    try:
        import httpx
        with httpx.Client(timeout=timeout, follow_redirects=True) as c:
            r = c.get(url)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
                return r.content
    except Exception as e:
        logger.debug(f"[OG] fetch fail {url} : {e}")
    return None


def generer_og_image_produit(
    produit: dict, boutique: dict, base_url: str,
) -> Optional[bytes]:
    """Génère une OG image 1200×630 PNG. Retourne None si Pillow indisponible
    ou aucune photo produit exploitable (le caller utilise alors la photo
    produit brute en fallback)."""
    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageFont
    except ImportError:
        return None

    photos = produit.get("photos_urls_json") or []
    photo_url = photos[0] if isinstance(photos, list) and photos else None
    photo_bytes = _fetch_image_bytes(photo_url) if photo_url else None
    logo_url = boutique.get("logo_url")
    logo_bytes = _fetch_image_bytes(logo_url) if logo_url else None

    if not photo_bytes:
        return None

    try:
        canvas = Image.new("RGB", (_WIDTH, _HEIGHT), color=(15, 23, 42))
        # Background : photo cover-fit avec blur léger
        bg = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
        # cover-fit
        bg_ratio = bg.width / bg.height
        target_ratio = _WIDTH / _HEIGHT
        if bg_ratio > target_ratio:
            new_h = _HEIGHT
            new_w = int(new_h * bg_ratio)
        else:
            new_w = _WIDTH
            new_h = int(new_w / bg_ratio)
        bg = bg.resize((new_w, new_h), Image.LANCZOS)
        off_x = (new_w - _WIDTH) // 2
        off_y = (new_h - _HEIGHT) // 2
        bg = bg.crop((off_x, off_y, off_x + _WIDTH, off_y + _HEIGHT))
        bg_blur = bg.filter(ImageFilter.GaussianBlur(radius=8))
        canvas.paste(bg_blur, (0, 0))

        # Photo produit "nette" centrée-gauche
        photo = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
        photo_h = _HEIGHT - 2 * _PADDING
        ratio = photo.width / photo.height
        photo_w = int(photo_h * ratio)
        photo = photo.resize((photo_w, photo_h), Image.LANCZOS)
        canvas.paste(photo, (_PADDING, _PADDING))

        # Overlay sombre côté droit pour lisibilité texte
        overlay = Image.new("RGBA", (_WIDTH, _HEIGHT), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        odraw.rectangle(
            [(_PADDING + photo_w + 20, 0), (_WIDTH, _HEIGHT)],
            fill=(15, 23, 42, 200),
        )
        canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")

        draw = ImageDraw.Draw(canvas)

        # Font fallback (PIL default font si pas de TTF dispo)
        try:
            font_title = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48,
            )
            font_price = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64,
            )
            font_small = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24,
            )
        except (OSError, IOError):
            font_title = ImageFont.load_default()
            font_price = ImageFont.load_default()
            font_small = ImageFont.load_default()

        text_x = _PADDING + photo_w + 50
        text_w = _WIDTH - text_x - _PADDING

        # Titre produit (wrap à text_w)
        titre = (produit.get("titre") or "")[:80]
        wrapped = _wrap_text(titre, font_title, draw, text_w)
        y = _PADDING + 30
        for line in wrapped[:3]:
            draw.text((text_x, y), line, fill=(255, 255, 255), font=font_title)
            y += 58

        # Prix
        prix_promo = produit.get("prix_unit_promo")
        prix = produit.get("prix_unit") or 0
        devise = produit.get("devise") or boutique.get("devise") or "XAF"
        prix_affichage = f"{int(prix_promo or prix)} {devise}"
        draw.text((text_x, y + 20), prix_affichage, fill=(167, 139, 250), font=font_price)

        # Nom boutique + URL en bas droite
        nom_boutique = (boutique.get("nom") or "")[:40]
        url_clean = base_url.replace("https://", "").replace("http://", "").rstrip("/")
        draw.text(
            (text_x, _HEIGHT - _PADDING - 60),
            nom_boutique, fill=(226, 232, 240), font=font_small,
        )
        draw.text(
            (text_x, _HEIGHT - _PADDING - 30),
            url_clean, fill=(148, 163, 184), font=font_small,
        )

        # Logo watermark haut-droite
        if logo_bytes:
            try:
                logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
                lh = 80
                lw = int(logo.width * (lh / logo.height))
                logo = logo.resize((lw, lh), Image.LANCZOS)
                canvas_rgba = canvas.convert("RGBA")
                canvas_rgba.paste(logo, (_WIDTH - lw - _PADDING, _PADDING), logo)
                canvas = canvas_rgba.convert("RGB")
            except Exception:
                pass

        out = io.BytesIO()
        canvas.save(out, format="PNG", optimize=True)
        return out.getvalue()
    except Exception as e:
        logger.warning(f"[OG] génération échec : {e}")
        return None


def _wrap_text(text: str, font, draw, max_width: int) -> list[str]:
    """Wrap simple par mots."""
    words = text.split()
    if not words:
        return []
    lines, current = [], words[0]
    for w in words[1:]:
        test = f"{current} {w}"
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            lines.append(current)
            current = w
    lines.append(current)
    return lines
