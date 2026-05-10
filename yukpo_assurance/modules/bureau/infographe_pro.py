"""
Infographie Pro — Moteur multi-page avec zones, médiathèque utilisateur, et IA.

Pipeline :
  1. Brief utilisateur + médias uploadés + cle_projet
  2. IA reçoit catalogue de pages + descripteurs des médias → produit ProjetInfographie
  3. Moteur rend chaque page (ReportLab + Pillow) selon son template_id
  4. Assemblage PDF multi-page + PNG par page + métadonnées print-ready

Ne remplace PAS le module `infographe.py` (visuels mono-page).
Coexiste pour les projets riches : livrets, brochures, livres photo, menus, programmes.
"""
from __future__ import annotations

import io
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from . import mediatheque_session as msm
from . import gabarits_livret as catalog

logger = logging.getLogger("yukpo_assurance.bureau.infographe_pro")

# ─── Modèles ──────────────────────────────────────────────────────────────────


@dataclass
class Zone:
    """Une zone de contenu sur une page. Position en mm relatifs au format final
    (hors bleed). Le moteur convertit en points en tenant compte du bleed."""
    slot_id: str
    type: str
    contenu: dict = field(default_factory=dict)  # texte/items/ref_media/coords...
    style: dict = field(default_factory=dict)


@dataclass
class Page:
    numero: int
    template_id: str
    zones: list[Zone] = field(default_factory=list)
    palette_override: Optional[dict] = None
    notes_ia: Optional[str] = None


@dataclass
class ProjetInfographie:
    cle_projet: str
    titre: str
    palette: str = "classique"
    palette_custom: Optional[dict] = None    # {primaire, secondaire, fond, texte, accent}
    pages: list[Page] = field(default_factory=list)
    medias_refs: list[str] = field(default_factory=list)  # ["session:abc", "compte:def"]
    polices: dict = field(default_factory=lambda: {"titre": "Helvetica-Bold", "corps": "Helvetica"})
    langue: str = "fr"
    meta: dict = field(default_factory=dict)


@dataclass
class ResultatProjet:
    pdf_bytes: Optional[bytes] = None
    pdf_cmyk_bytes: Optional[bytes] = None
    pages_png: list[bytes] = field(default_factory=list)   # PNG par page (web preview)
    pages_png_hd: list[bytes] = field(default_factory=list)  # 300 DPI print
    projet: Optional[ProjetInfographie] = None
    meta: dict = field(default_factory=dict)


# ─── Palettes ────────────────────────────────────────────────────────────────
# On réutilise les palettes du module simple (cohérence visuelle inter-modules)
from .infographe import PALETTES, _palette_personnalisee_depuis_hex   # noqa: E402

POLICES_FALLBACK = {
    "Cormorant": "Times-Italic",       # Fallback ReportLab core
    "Playfair Display": "Times-Bold",
    "Lato": "Helvetica",
    "Inter": "Helvetica",
    "Helvetica-Bold": "Helvetica-Bold",
    "Helvetica": "Helvetica",
    "Times-Bold": "Times-Bold",
    "Times-Italic": "Times-Italic",
}


def _resoudre_police(nom: str, italic: bool = False, bold: bool = True) -> str:
    """Phase 2 : tente Google Fonts (téléchargement + cache local) si la famille
    correspond à une famille connue, sinon retombe sur les 14 polices core
    PostScript via POLICES_FALLBACK."""
    try:
        from . import font_loader as _fl
        # Le nom peut être direct ("Playfair Display") ou un alias ReportLab
        famille_directe = nom if nom in _fl.FAMILLES else None
        if not famille_directe:
            # Mappings inverses : si on nous donne "Helvetica-Bold" mais que l'utilisateur
            # a configuré une famille Google équivalente dans le projet, on tente quand même.
            for fam in _fl.FAMILLES:
                if fam.lower() in nom.lower():
                    famille_directe = fam
                    break
        if famille_directe:
            rl = _fl.police_pour(famille_directe, italic=italic, bold=bold)
            if rl:
                return rl
    except Exception:
        pass

    base = POLICES_FALLBACK.get(nom, "Helvetica")
    # Garde la base mappée, ajuste italic/bold si pertinent
    if base.startswith("Helvetica"):
        return ("Helvetica-BoldOblique" if (bold and italic) else
                "Helvetica-Bold" if bold else
                "Helvetica-Oblique" if italic else
                "Helvetica")
    if base.startswith("Times"):
        return ("Times-BoldItalic" if (bold and italic) else
                "Times-Bold" if bold else
                "Times-Italic" if italic else
                "Times-Roman")
    return base


# ─── Helpers de rendu (couleurs, formes, texte, images) ───────────────────────


def _rgb(c, t):
    from reportlab.lib.colors import Color
    return Color(t[0]/255, t[1]/255, t[2]/255)


def _rgba(c, t, a):
    from reportlab.lib.colors import Color
    return Color(t[0]/255, t[1]/255, t[2]/255, alpha=a)


def _fill_bg(c, w, h, palette):
    c.setFillColor(_rgb(c, palette["fond"]))
    c.rect(0, 0, w, h, fill=True, stroke=False)


def _gradient_v(c, w, y0, h_band, col_bas, col_haut, steps=60):
    for i in range(steps):
        t = i / max(1, steps - 1)
        r = col_bas[0] + (col_haut[0] - col_bas[0]) * t
        g = col_bas[1] + (col_haut[1] - col_bas[1]) * t
        b = col_bas[2] + (col_haut[2] - col_bas[2]) * t
        c.setFillColor(_rgb(c, (r, g, b)))
        c.rect(0, y0 + h_band * t, w, h_band / steps + 0.5, fill=True, stroke=False)


def _texte_centre(c, txt, x, y, taille, couleur, font="Helvetica-Bold"):
    c.setFont(font, taille)
    c.setFillColor(_rgb(c, couleur))
    c.drawCentredString(x, y, txt)


def _texte_gauche(c, txt, x, y, taille, couleur, font="Helvetica"):
    c.setFont(font, taille)
    c.setFillColor(_rgb(c, couleur))
    c.drawString(x, y, txt)


def _wrap_lignes(texte: str, taille_pt: float, largeur_pt: float, max_lignes: int = 999) -> list[str]:
    """Wrap par mots, approximation 0.5×taille par caractère."""
    if not texte:
        return []
    char_w = taille_pt * 0.5
    max_chars = max(1, int(largeur_pt / char_w))
    lignes: list[str] = []
    for paragraphe in str(texte).split("\n"):
        mots = paragraphe.split()
        ligne = ""
        for m in mots:
            test = (ligne + " " + m).strip()
            if len(test) > max_chars and ligne:
                lignes.append(ligne)
                ligne = m
                if len(lignes) >= max_lignes:
                    return lignes
            else:
                ligne = test
        if ligne:
            lignes.append(ligne)
            if len(lignes) >= max_lignes:
                return lignes
    return lignes


def _texte_paragraphe(c, txt, x, y, w, taille, couleur, font="Helvetica",
                      interligne=1.35, max_lignes=20, align="left"):
    """Dessine un paragraphe wrappé. y = baseline première ligne. Retourne y final."""
    if not txt:
        return y
    lignes = _wrap_lignes(txt, taille, w, max_lignes)
    c.setFont(font, taille)
    c.setFillColor(_rgb(c, couleur))
    for ligne in lignes:
        if align == "center":
            c.drawCentredString(x + w / 2, y, ligne)
        elif align == "right":
            c.drawRightString(x + w, y, ligne)
        else:
            c.drawString(x, y, ligne)
        y -= taille * interligne
    return y


# ─── Sprint 1.3 — Effets typographiques avancés ──────────────────────────────
#
# 6 effets pour rivaliser avec Canva pro (~80% des usages typographiques) :
#   1. gradient_text (linéaire / radial)
#   2. drop_shadow (offset + flou + opacité)
#   3. text_mask (texte sur image avec masque coloré semi-transparent par-dessus)
#   4. outline (stroke autour des lettres)
#   5. courbe (texte sur arc — concave/convexe)
#   6. blend (transparence + blend modes via Pillow → embed)
#
# Les effets natifs ReportLab (shadow, outline) restent vectoriels.
# Les effets complexes (gradient, courbe, blend) rasterisent via Pillow puis
# embed comme image. Compromis qualité/complexité optimal pour print.


def _font_pillow(font_rl: str, taille_pt: float):
    """Mappe une police ReportLab vers une PIL.ImageFont (DejaVu en fallback)."""
    try:
        from PIL import ImageFont
        # ReportLab utilise des noms PostScript. Pillow attend un fichier TTF.
        # On tente d'abord le font_loader (Google Fonts cachées localement),
        # sinon on retombe sur DejaVu/Liberation système.
        try:
            from . import font_loader as _fl
            ttf = _fl.chemin_ttf_pour(font_rl)
            if ttf:
                return ImageFont.truetype(ttf, int(taille_pt * 4))  # ×4 pour rendu HD
        except Exception:
            pass
        for candidat in ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf",
                         "LiberationSans-Bold.ttf", "Arial.ttf"):
            try:
                return ImageFont.truetype(candidat, int(taille_pt * 4))
            except Exception:
                continue
        return ImageFont.load_default()
    except Exception:
        return None


def _texte_gradient_png(texte: str, taille_pt: float, font_rl: str,
                        col_debut, col_fin, direction: str = "vertical",
                        radial: bool = False) -> bytes:
    """Rasterise un texte avec gradient (linéaire ou radial) → PNG transparent.
    `col_debut`/`col_fin` = (r,g,b) 0-255."""
    try:
        from PIL import Image, ImageDraw
        font = _font_pillow(font_rl, taille_pt)
        if font is None:
            return b""
        # Mesure
        bbox = font.getbbox(texte)
        w = max(1, bbox[2] - bbox[0])
        h = max(1, bbox[3] - bbox[1])
        pad = 6
        canvas = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
        # 1. Construire un calque gradient
        grad = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
        gd = ImageDraw.Draw(grad)
        cx, cy = (w + 2 * pad) // 2, (h + 2 * pad) // 2
        max_r = max(cx, cy)
        for i in range(max(w, h) + 2 * pad):
            t = i / max(1, (max(w, h) + 2 * pad - 1))
            r = int(col_debut[0] + (col_fin[0] - col_debut[0]) * t)
            g = int(col_debut[1] + (col_fin[1] - col_debut[1]) * t)
            b = int(col_debut[2] + (col_fin[2] - col_debut[2]) * t)
            if radial:
                rr = int(max_r * (1 - t))
                gd.ellipse((cx - rr, cy - rr, cx + rr, cy + rr),
                           fill=(r, g, b, 255))
            elif direction == "vertical":
                gd.rectangle((0, i, w + 2 * pad, i + 1), fill=(r, g, b, 255))
            else:  # horizontal
                gd.rectangle((i, 0, i + 1, h + 2 * pad), fill=(r, g, b, 255))
        # 2. Masque texte
        mask = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
        md = ImageDraw.Draw(mask)
        md.text((pad - bbox[0], pad - bbox[1]), texte, fill=255, font=font)
        # 3. Composer
        canvas.paste(grad, (0, 0), mask)
        # Down-sample (rendu HD ×4 → taille finale)
        final_w = canvas.size[0] // 4 or 1
        final_h = canvas.size[1] // 4 or 1
        canvas = canvas.resize((final_w, final_h), Image.LANCZOS)
        buf = io.BytesIO()
        canvas.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        logger.debug(f"[InfographePro] gradient_text échoué : {e}")
        return b""


def _texte_courbe_png(texte: str, taille_pt: float, font_rl: str,
                      couleur, rayon_pt: float = 80.0,
                      arc_deg: float = 120.0, concave: bool = False) -> bytes:
    """Rasterise un texte courbé sur un arc → PNG transparent."""
    try:
        import math
        from PIL import Image, ImageDraw
        font = _font_pillow(font_rl, taille_pt)
        if font is None:
            return b""
        # Estimer largeur totale en pixels HD
        widths = [font.getbbox(ch)[2] - font.getbbox(ch)[0] for ch in texte]
        total_w = sum(widths)
        ascent = font.getbbox("Hg")[3]
        # Canvas carré assez grand
        size = int(rayon_pt * 4 * 2 + ascent + 20)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        cx, cy = size // 2, size // 2
        rayon_px = rayon_pt * 4
        # Angle de départ (centrer l'arc en haut)
        arc_rad = math.radians(arc_deg)
        angle_total = total_w / rayon_px  # angle parcouru
        angle = -math.pi / 2 - angle_total / 2 if not concave else math.pi / 2 + angle_total / 2
        for ch, ww in zip(texte, widths):
            ang_pas = ww / rayon_px
            x = cx + math.cos(angle + ang_pas / 2) * rayon_px
            y = cy + math.sin(angle + ang_pas / 2) * rayon_px
            # Lettre tournée tangentiellement
            ch_img = Image.new("RGBA", (ww + 4, ascent + 4), (0, 0, 0, 0))
            cd = ImageDraw.Draw(ch_img)
            cd.text((2, 2), ch, fill=tuple(couleur) + (255,), font=font)
            ang_deg = math.degrees(angle + ang_pas / 2 + math.pi / 2)
            if concave:
                ang_deg += 180
            ch_img = ch_img.rotate(-ang_deg, resample=Image.BICUBIC, expand=True)
            canvas.alpha_composite(ch_img, (int(x - ch_img.size[0] / 2), int(y - ch_img.size[1] / 2)))
            angle += ang_pas
        # Down-sample
        canvas = canvas.resize((size // 4, size // 4), Image.LANCZOS)
        buf = io.BytesIO()
        canvas.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        logger.debug(f"[InfographePro] texte_courbe échoué : {e}")
        return b""


def _texte_avec_effets(c, txt: str, x: float, y: float, taille: float,
                        couleur, font: str = "Helvetica-Bold",
                        effets: Optional[dict] = None,
                        align: str = "left", largeur: float = 0):
    """
    Trace un texte avec effets optionnels.

    `effets` (dict) :
      - "shadow": {"dx": 1.5, "dy": -1.5, "color": (0,0,0), "alpha": 0.4}
      - "outline": {"width": 0.6, "color": (0,0,0)}            # mode fill+stroke
      - "outline_only": {"width": 0.8, "color": (...)}         # mode stroke only
      - "gradient": {"col_debut": (r,g,b), "col_fin": (r,g,b),
                     "direction": "vertical|horizontal", "radial": False}
      - "courbe": {"rayon_pt": 80, "arc_deg": 120, "concave": False}
      - "blend": {"alpha": 0.7}                                # transparence simple

    Effets compatibles entre eux (ex: shadow + gradient). Les effets rasterisés
    (gradient, courbe) prennent priorité sur le rendu vectoriel natif.
    """
    effets = effets or {}
    # Effets rasterisés (gradient ou courbe) → embed PNG
    if effets.get("gradient") or effets.get("courbe"):
        from reportlab.lib.utils import ImageReader
        if effets.get("courbe"):
            cv = effets["courbe"]
            png = _texte_courbe_png(
                txt, taille, font, couleur,
                rayon_pt=float(cv.get("rayon_pt", 80)),
                arc_deg=float(cv.get("arc_deg", 120)),
                concave=bool(cv.get("concave", False)),
            )
        else:
            gr = effets["gradient"]
            png = _texte_gradient_png(
                txt, taille, font,
                col_debut=tuple(gr.get("col_debut", couleur)),
                col_fin=tuple(gr.get("col_fin", (255, 255, 255))),
                direction=gr.get("direction", "vertical"),
                radial=bool(gr.get("radial", False)),
            )
        if png:
            try:
                from PIL import Image
                im = Image.open(io.BytesIO(png))
                w_px, h_px = im.size
                # Conversion px → points (Pillow rend à 72 DPI ici, après le ÷4)
                pt_per_px = 1.0
                w_pt = w_px * pt_per_px
                h_pt = h_px * pt_per_px
                if align == "center":
                    x_draw = x - w_pt / 2
                elif align == "right":
                    x_draw = x - w_pt
                else:
                    x_draw = x
                # y est baseline du texte vectoriel : on adapte pour image (top-left)
                c.drawImage(ImageReader(io.BytesIO(png)),
                            x_draw, y - h_pt * 0.78,
                            width=w_pt, height=h_pt, mask='auto')
                return
            except Exception as e:
                logger.debug(f"[InfographePro] embed effet rasterisé échoué : {e}")
                # fallback rendu vectoriel basique
    # Drop shadow vectoriel (avant le glyph principal pour passer dessous)
    if effets.get("shadow"):
        sh = effets["shadow"]
        dx = float(sh.get("dx", 1.5))
        dy = float(sh.get("dy", -1.5))
        sh_col = tuple(sh.get("color", (0, 0, 0)))
        sh_alpha = float(sh.get("alpha", 0.4))
        c.saveState()
        c.setFont(font, taille)
        c.setFillColor(_rgba(c, sh_col, sh_alpha))
        if align == "center":
            c.drawCentredString(x + dx, y + dy, txt)
        elif align == "right":
            c.drawRightString(x + dx, y + dy, txt)
        else:
            c.drawString(x + dx, y + dy, txt)
        c.restoreState()
    # Texte principal (avec outline et/ou blend si demandés)
    c.saveState()
    c.setFont(font, taille)
    blend = effets.get("blend") or {}
    alpha = float(blend.get("alpha", 1.0))
    c.setFillColor(_rgba(c, couleur, alpha))
    out = effets.get("outline")
    out_only = effets.get("outline_only")
    if out_only:
        # Mode stroke uniquement
        c.setStrokeColor(_rgba(c, tuple(out_only.get("color", couleur)), 1.0))
        c.setLineWidth(float(out_only.get("width", 0.6)))
        c.setTextRenderMode(1)   # stroke
    elif out:
        # Mode fill+stroke
        c.setStrokeColor(_rgba(c, tuple(out.get("color", (0, 0, 0))), 1.0))
        c.setLineWidth(float(out.get("width", 0.5)))
        c.setTextRenderMode(2)   # fill+stroke
    if align == "center":
        c.drawCentredString(x, y, txt)
    elif align == "right":
        c.drawRightString(x, y, txt)
    else:
        c.drawString(x, y, txt)
    if out or out_only:
        c.setTextRenderMode(0)   # reset
    c.restoreState()


def _overlay_mask_couleur(c, x: float, y: float, w: float, h: float,
                           couleur, alpha: float = 0.45):
    """Pose un voile coloré semi-transparent sur une zone (typiquement
    sur une image cover pour faire ressortir un texte par-dessus).
    Effet typographique #3 : 'texte sur image avec masque coloré'."""
    c.saveState()
    c.setFillColor(_rgba(c, couleur, alpha))
    c.rect(x, y, w, h, fill=True, stroke=False)
    c.restoreState()


def _inserer_image(c, image_bytes, x, y, w, h, mode="cover", radius_pt=0):
    """Insère une image dans une zone rectangulaire avec mode `cover` ou `contain`.
    `radius_pt` arrondit les coins (clipping via mask Pillow)."""
    try:
        from PIL import Image, ImageDraw
        from reportlab.lib.utils import ImageReader
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if "transparency" in img.info else "RGB")

        # Calcul ratio pour cover/contain
        iw, ih = img.size
        ratio_zone = w / h if h else 1
        ratio_img = iw / ih if ih else 1
        if mode == "cover":
            if ratio_img > ratio_zone:
                new_h = ih
                new_w = int(ih * ratio_zone)
                left = (iw - new_w) // 2
                img = img.crop((left, 0, left + new_w, new_h))
            else:
                new_w = iw
                new_h = int(iw / ratio_zone)
                top = (ih - new_h) // 2
                img = img.crop((0, top, new_w, top + new_h))

        # Coins arrondis via mask Pillow (en pixels — convertir radius_pt → px)
        if radius_pt > 0:
            target_px = max(1, int(min(w, h) * 4))  # rendu haute déf
            target_w = target_px
            target_h = max(1, int(target_px * (h / w)))
            img = img.resize((target_w, target_h), Image.LANCZOS)
            radius_px = max(1, int(target_px * (radius_pt / w)))
            mask = Image.new("L", (target_w, target_h), 0)
            d = ImageDraw.Draw(mask)
            d.rounded_rectangle((0, 0, target_w, target_h), radius_px, fill=255)
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            img.putalpha(mask)

        buf = io.BytesIO()
        img.save(buf, format="PNG" if img.mode == "RGBA" else "JPEG", quality=92)
        buf.seek(0)
        c.drawImage(ImageReader(buf), x, y, width=w, height=h, mask='auto')
    except Exception as e:
        logger.warning(f"[InfographePro] Insertion image échouée : {e}")
        # Placeholder visuel
        c.setStrokeColor(_rgb(c, (200, 200, 200)))
        c.setLineWidth(0.5)
        c.rect(x, y, w, h, fill=False, stroke=True)


def _qr_png(donnees: str, taille_px: int = 600) -> bytes:
    """Génère un QR code PNG."""
    try:
        import qrcode
        qr = qrcode.QRCode(box_size=10, border=2)
        qr.add_data(donnees)
        qr.make()
        img = qr.make_image(fill_color="black", back_color="white")
        # Resize précis
        img = img.resize((taille_px, taille_px))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"[InfographePro] QR code échoué : {e}")
        return b""


def _carte_png(coords: list[tuple[float, float]], w_px: int = 800, h_px: int = 600) -> bytes:
    """Plan localisation via staticmap (tuiles OpenStreetMap). coords = [(lat, lon), ...]"""
    try:
        from staticmap import StaticMap, CircleMarker
        if not coords:
            return b""
        m = StaticMap(w_px, h_px, padding_x=20, padding_y=20)
        couleurs = ["#c00", "#06c", "#0a0", "#a06", "#a60"]
        for i, (lat, lon) in enumerate(coords):
            m.add_marker(CircleMarker((lon, lat), couleurs[i % len(couleurs)], 12))
        image = m.render()
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"[InfographePro] Carte staticmap échouée : {e} — fallback grille")
        return _carte_fallback_png(coords, w_px, h_px)


def _carte_fallback_png(coords: list[tuple[float, float]], w: int, h: int) -> bytes:
    """Fallback simple : grille schématique (si staticmap indisponible / pas internet)."""
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (w, h), "#f4f4f4")
        d = ImageDraw.Draw(img)
        # Grille
        for x in range(0, w, 40):
            d.line([(x, 0), (x, h)], fill="#ddd", width=1)
        for y in range(0, h, 40):
            d.line([(0, y), (w, y)], fill="#ddd", width=1)
        # Markers placés relativement
        if coords:
            lats = [c[0] for c in coords]; lons = [c[1] for c in coords]
            lat_min, lat_max = min(lats), max(lats)
            lon_min, lon_max = min(lons), max(lons)
            dl = max(lat_max - lat_min, 0.001)
            dn = max(lon_max - lon_min, 0.001)
            for i, (lat, lon) in enumerate(coords):
                px = int(((lon - lon_min) / dn) * (w - 80)) + 40
                py = h - (int(((lat - lat_min) / dl) * (h - 80)) + 40)
                d.ellipse((px - 12, py - 12, px + 12, py + 12), fill="#c00", outline="white", width=2)
                d.text((px + 16, py - 8), str(i + 1), fill="#222")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return b""


def _ornement_filigrane(c, w, h, palette, motif="floral"):
    """Ornement décoratif vectoriel (lignes courbes ou symbole religieux/floral)."""
    from reportlab.lib.pagesizes import mm
    c.saveState()
    c.setStrokeColor(_rgba(c, palette["secondaire"], 0.5))
    c.setLineWidth(0.8)
    cx = w / 2
    if motif == "floral":
        # Volutes symétriques
        for sgn in (-1, 1):
            p = c.beginPath()
            p.moveTo(cx + sgn * 6 * mm, h - 6 * mm)
            p.curveTo(cx + sgn * 14 * mm, h - 4 * mm,
                      cx + sgn * 18 * mm, h - 9 * mm,
                      cx + sgn * 22 * mm, h - 7 * mm)
            c.drawPath(p, fill=False, stroke=True)
        # Petite étoile centrale
        c.setFillColor(_rgb(c, palette["secondaire"]))
        c.circle(cx, h - 6 * mm, 0.8 * mm, fill=True, stroke=False)
    elif motif == "deuil":
        # Bande sobre + petite croix
        c.setStrokeColor(_rgb(c, palette["primaire"]))
        c.setLineWidth(0.6)
        c.line(cx - 18 * mm, h - 8 * mm, cx + 18 * mm, h - 8 * mm)
        c.line(cx, h - 12 * mm, cx, h - 4 * mm)
        c.line(cx - 2 * mm, h - 8 * mm, cx + 2 * mm, h - 8 * mm)
    else:  # générique
        c.line(cx - 25 * mm, h - 8 * mm, cx + 25 * mm, h - 8 * mm)
    c.restoreState()


def _coins_imprimerie(c, w, h, bleed):
    """Traits de coupe aux 4 coins (impression pro)."""
    from reportlab.lib.colors import black
    taille = 5
    offset = 2
    c.setStrokeColor(black)
    c.setLineWidth(0.25)
    for cx, cy in [(bleed, bleed), (w - bleed, bleed),
                   (bleed, h - bleed), (w - bleed, h - bleed)]:
        dx = 1 if cx < w / 2 else -1
        dy = 1 if cy < h / 2 else -1
        c.line(cx + dx * offset, cy, cx + dx * (offset + taille), cy)
        c.line(cx, cy + dy * offset, cx, cy + dy * (offset + taille))


# ─── Templates de rendu par template_id ───────────────────────────────────────

def _zone_par_id(page: Page, slot_id: str) -> Optional[Zone]:
    for z in page.zones:
        if z.slot_id == slot_id:
            return z
    return None


def _ctx_palette(projet: ProjetInfographie, page: Page) -> dict:
    if page.palette_override:
        return page.palette_override
    if projet.palette_custom:
        return projet.palette_custom
    return PALETTES.get(projet.palette, PALETTES["classique"])


def _font_titre(projet: ProjetInfographie, italic: bool = False) -> str:
    return _resoudre_police(projet.polices.get("titre", "Helvetica-Bold"),
                            italic=italic, bold=True)


def _font_corps(projet: ProjetInfographie, italic: bool = False, bold: bool = False) -> str:
    return _resoudre_police(projet.polices.get("corps", "Helvetica"),
                            italic=italic, bold=bold)


def _media_bytes(zone: Zone, medias: dict[str, msm.Media]) -> Optional[bytes]:
    ref = (zone.contenu or {}).get("ref_media")
    if not ref:
        return None
    media = medias.get(ref)
    if not media:
        return None
    try:
        return msm.lire_bytes(media)
    except Exception as e:
        logger.warning(f"[InfographePro] Lecture média {ref} : {e}")
        return None


# ─── DEUIL ────────────────────────────────────────────────────────────────────

def _render_deuil_couverture(c, projet, page, w, h, bleed, medias):
    from reportlab.lib.pagesizes import mm
    pal = _ctx_palette(projet, page)
    _fill_bg(c, w, h, pal)
    # Bande noire haute fine
    c.setFillColor(_rgb(c, pal["primaire"]))
    c.rect(0, h - 12 * mm, w, 12 * mm, fill=True, stroke=False)
    _texte_centre(c, "In Memoriam", w / 2, h - 8 * mm, 9, (255, 255, 255),
                  _font_titre(projet, italic=True))
    # Cadre central sobre
    c.setStrokeColor(_rgb(c, pal["secondaire"]))
    c.setLineWidth(0.5)
    c.rect(bleed + 8 * mm, bleed + 14 * mm, w - 2 * bleed - 16 * mm,
           h - 2 * bleed - 26 * mm, fill=False, stroke=True)
    # Portrait
    z_portrait = _zone_par_id(page, "portrait")
    img_b = _media_bytes(z_portrait, medias) if z_portrait else None
    if img_b:
        ph_w = 70 * mm; ph_h = 90 * mm
        _inserer_image(c, img_b, w / 2 - ph_w / 2, h / 2 - 6 * mm, ph_w, ph_h, "cover", radius_pt=2 * mm)
    else:
        # Cadre placeholder portrait
        ph_w = 70 * mm; ph_h = 90 * mm
        c.setFillColor(_rgba(c, pal["secondaire"], 0.15))
        c.rect(w / 2 - ph_w / 2, h / 2 - 6 * mm, ph_w, ph_h, fill=True, stroke=False)
    # Nom — Sprint 1.3 : honore style.effets si défini par l'IA
    z_nom = _zone_par_id(page, "nom")
    nom = (z_nom.contenu.get("texte") if z_nom else None) or projet.titre or ""
    effets_nom = (z_nom.style or {}).get("effets") if z_nom else None
    if effets_nom:
        _texte_avec_effets(c, nom[:60], w / 2, h / 2 - 18 * mm, 22, pal["primaire"],
                            font=_font_titre(projet), effets=effets_nom, align="center")
    else:
        _texte_centre(c, nom[:60], w / 2, h / 2 - 18 * mm, 22, pal["primaire"], _font_titre(projet))
    # Dates
    z_dates = _zone_par_id(page, "dates")
    if z_dates:
        dates = z_dates.contenu.get("texte") or ""
        _texte_centre(c, dates[:60], w / 2, h / 2 - 28 * mm, 11, pal["texte"], _font_corps(projet))
    # Citation
    z_cit = _zone_par_id(page, "citation")
    if z_cit and z_cit.contenu.get("texte"):
        _texte_paragraphe(c, z_cit.contenu["texte"], bleed + 15 * mm, bleed + 30 * mm,
                          w - 2 * bleed - 30 * mm, 9, pal["texte"],
                          _font_corps(projet, italic=True), align="center", max_lignes=4)


def _render_deuil_familles(c, projet, page, w, h, bleed, medias):
    from reportlab.lib.pagesizes import mm
    pal = _ctx_palette(projet, page)
    _fill_bg(c, w, h, pal)
    _ornement_filigrane(c, w, h, pal, "deuil")
    z_intro = _zone_par_id(page, "intro")
    y = h - bleed - 22 * mm
    if z_intro and z_intro.contenu.get("texte"):
        y = _texte_paragraphe(c, z_intro.contenu["texte"], bleed + 14 * mm, y,
                              w - 2 * bleed - 28 * mm, 10, pal["texte"],
                              _font_corps(projet, italic=True), align="center", max_lignes=4)
        y -= 4 * mm
    # Familles : grille 2 colonnes
    z_fam = _zone_par_id(page, "familles")
    familles = (z_fam.contenu.get("items") if z_fam else []) or []
    col_w = (w - 2 * bleed - 30 * mm) / 2
    col_x = [bleed + 14 * mm, bleed + 14 * mm + col_w + 6 * mm]
    y_col = [y, y]
    for i, fam in enumerate(familles[:8]):
        ci = i % 2
        x = col_x[ci]
        yy = y_col[ci]
        nom_fam = fam.get("nom", "")
        membres = fam.get("membres", []) or []
        # Titre famille
        c.setFont(_font_titre(projet), 11)
        c.setFillColor(_rgb(c, pal["primaire"]))
        c.drawString(x, yy, f"Famille {nom_fam[:40]}")
        yy -= 4 * mm
        # Ligne
        c.setStrokeColor(_rgba(c, pal["secondaire"], 0.6))
        c.setLineWidth(0.3)
        c.line(x, yy + 2 * mm, x + col_w, yy + 2 * mm)
        # Membres
        c.setFont(_font_corps(projet), 9)
        c.setFillColor(_rgb(c, pal["texte"]))
        for m in membres[:8]:
            if yy < bleed + 18 * mm:
                break
            c.drawString(x, yy, str(m)[:40])
            yy -= 3.5 * mm
        y_col[ci] = yy - 4 * mm
    # Annonce finale
    z_ann = _zone_par_id(page, "annonce")
    if z_ann and z_ann.contenu.get("texte"):
        _texte_paragraphe(c, z_ann.contenu["texte"], bleed + 14 * mm, bleed + 18 * mm,
                          w - 2 * bleed - 28 * mm, 10, pal["primaire"],
                          _font_corps(projet, bold=True), align="center", max_lignes=3)


def _render_programme_etapes(c, projet, page, w, h, bleed, medias):
    """Rendu commun pour pages avec des étapes/programme (deuil_programme, mariage_invitation, programme_deroulement)."""
    from reportlab.lib.pagesizes import mm
    pal = _ctx_palette(projet, page)
    _fill_bg(c, w, h, pal)
    _ornement_filigrane(c, w, h, pal, "floral" if "mariage" in page.template_id else "deuil")
    z_titre = _zone_par_id(page, "titre") or _zone_par_id(page, "intro")
    titre = (z_titre.contenu.get("texte") if z_titre else "") or "Programme"
    _texte_centre(c, titre[:60], w / 2, h - bleed - 24 * mm, 18, pal["primaire"], _font_titre(projet))
    # Ligne déco
    c.setStrokeColor(_rgb(c, pal["secondaire"]))
    c.setLineWidth(0.5)
    c.line(w / 2 - 25 * mm, h - bleed - 28 * mm, w / 2 + 25 * mm, h - bleed - 28 * mm)
    # Étapes
    z_et = (_zone_par_id(page, "etapes") or _zone_par_id(page, "programme")
            or _zone_par_id(page, "sequences"))
    etapes = (z_et.contenu.get("items") if z_et else []) or []
    y = h - bleed - 40 * mm
    x_l = bleed + 16 * mm
    x_r = w - bleed - 14 * mm
    for et in etapes[:10]:
        if y < bleed + 18 * mm:
            break
        heure = str(et.get("heure", "") or "")
        date_e = str(et.get("date", "") or "")
        lieu = str(et.get("lieu", "") or "")
        titre_e = str(et.get("titre", "") or et.get("description", "") or "")
        # Bloc heure à gauche
        c.setFillColor(_rgb(c, pal["primaire"]))
        c.setFont(_font_titre(projet), 11)
        gauche = " ".join(filter(None, [date_e, heure])).strip()
        c.drawString(x_l, y, gauche[:30])
        # Titre étape
        c.setFont(_font_titre(projet), 11)
        c.setFillColor(_rgb(c, pal["texte"]))
        c.drawString(x_l + 35 * mm, y, titre_e[:50])
        # Lieu en dessous
        if lieu:
            c.setFont(_font_corps(projet, italic=True), 8.5)
            c.setFillColor(_rgb(c, pal["accent"]))
            c.drawString(x_l + 35 * mm, y - 4 * mm, lieu[:60])
        # Séparateur
        c.setStrokeColor(_rgba(c, pal["secondaire"], 0.4))
        c.setLineWidth(0.2)
        c.line(x_l, y - 6.5 * mm, x_r, y - 6.5 * mm)
        y -= 11 * mm


def _render_plan(c, projet, page, w, h, bleed, medias):
    from reportlab.lib.pagesizes import mm
    pal = _ctx_palette(projet, page)
    _fill_bg(c, w, h, pal)
    z_titre = _zone_par_id(page, "titre")
    titre = (z_titre.contenu.get("texte") if z_titre else "") or "Plan d'accès"
    _texte_centre(c, titre[:60], w / 2, h - bleed - 22 * mm, 18, pal["primaire"], _font_titre(projet))
    # Carte
    z_carte = _zone_par_id(page, "carte")
    coords = (z_carte.contenu.get("coords") if z_carte else []) or []
    coords_t = [(float(p.get("lat", 0)), float(p.get("lon", 0))) for p in coords if p]
    carte_h = (h - 2 * bleed) * 0.55
    carte_w = w - 2 * bleed - 20 * mm
    if coords_t:
        png = _carte_png(coords_t,
                         w_px=int(carte_w * 4),
                         h_px=int(carte_h * 4))
        if png:
            _inserer_image(c, png, bleed + 10 * mm, h / 2 - 4 * mm,
                           carte_w, carte_h, "cover", radius_pt=2 * mm)
    # Adresses
    z_adr = _zone_par_id(page, "adresses")
    adresses = (z_adr.contenu.get("items") if z_adr else []) or []
    y = bleed + 30 * mm + len(adresses) * 5 * mm
    c.setFont(_font_corps(projet, bold=True), 10)
    c.setFillColor(_rgb(c, pal["primaire"]))
    c.drawString(bleed + 12 * mm, y, "Adresses")
    y -= 4.5 * mm
    c.setFont(_font_corps(projet), 9)
    c.setFillColor(_rgb(c, pal["texte"]))
    for i, a in enumerate(adresses[:6]):
        nom = a.get("nom", "") if isinstance(a, dict) else str(a)
        adr = a.get("adresse", "") if isinstance(a, dict) else ""
        c.drawString(bleed + 12 * mm, y, f"{i+1}. {nom[:40]} — {adr[:60]}")
        y -= 4 * mm


def _render_mediatheque(c, projet, page, w, h, bleed, medias):
    """Grille photos avec légendes — utilisé par deuil_mediatheque, livre_photo_grille."""
    from reportlab.lib.pagesizes import mm
    pal = _ctx_palette(projet, page)
    _fill_bg(c, w, h, pal)
    z_titre = _zone_par_id(page, "titre")
    if z_titre and z_titre.contenu.get("texte"):
        _texte_centre(c, z_titre.contenu["texte"][:50], w / 2, h - bleed - 18 * mm,
                      14, pal["primaire"], _font_titre(projet))
    z_photos = _zone_par_id(page, "photos") or _zone_par_id(page, "image_secondaire")
    items = (z_photos.contenu.get("items") if z_photos else []) or []
    n = len(items)
    if n == 0:
        return
    # Grille adaptative : 1 → 1×1, 2 → 2×1, 3-4 → 2×2, 5-6 → 3×2, 7-9 → 3×3
    if n <= 1:
        cols, rows = 1, 1
    elif n == 2:
        cols, rows = 2, 1
    elif n <= 4:
        cols, rows = 2, 2
    elif n <= 6:
        cols, rows = 3, 2
    else:
        cols, rows = 3, 3
    margin = 8 * mm
    gap = 3 * mm
    top = h - bleed - 28 * mm if z_titre else h - bleed - 10 * mm
    bottom = bleed + 12 * mm
    grid_w = w - 2 * bleed - 2 * margin
    grid_h = top - bottom
    cell_w = (grid_w - (cols - 1) * gap) / cols
    cell_h = (grid_h - (rows - 1) * gap) / rows
    for i, item in enumerate(items[:cols * rows]):
        ci = i % cols
        ri = i // cols
        x = bleed + margin + ci * (cell_w + gap)
        y = top - (ri + 1) * cell_h - ri * gap
        ref = item.get("ref_media") if isinstance(item, dict) else None
        legende = item.get("legende", "") if isinstance(item, dict) else ""
        media = medias.get(ref) if ref else None
        if media:
            try:
                img_b = msm.lire_bytes(media)
                _inserer_image(c, img_b, x, y, cell_w, cell_h, "cover", radius_pt=1.5 * mm)
            except Exception:
                pass
        else:
            c.setFillColor(_rgba(c, pal["secondaire"], 0.18))
            c.rect(x, y, cell_w, cell_h, fill=True, stroke=False)
        if legende:
            c.setFont(_font_corps(projet, italic=True), 7.5)
            c.setFillColor(_rgb(c, pal["texte"]))
            c.drawCentredString(x + cell_w / 2, y - 2.5 * mm, str(legende)[:60])


def _render_temoignages(c, projet, page, w, h, bleed, medias):
    from reportlab.lib.pagesizes import mm
    pal = _ctx_palette(projet, page)
    _fill_bg(c, w, h, pal)
    z_titre = _zone_par_id(page, "titre")
    if z_titre and z_titre.contenu.get("texte"):
        _texte_centre(c, z_titre.contenu["texte"][:50], w / 2, h - bleed - 18 * mm,
                      16, pal["primaire"], _font_titre(projet))
    z = _zone_par_id(page, "temoignages")
    items = (z.contenu.get("items") if z else []) or []
    y = h - bleed - 32 * mm
    for t in items[:6]:
        if y < bleed + 14 * mm:
            break
        citation = t.get("citation", "") if isinstance(t, dict) else str(t)
        auteur = t.get("auteur", "") if isinstance(t, dict) else ""
        # Guillemet déco
        c.setFont(_font_titre(projet), 18)
        c.setFillColor(_rgba(c, pal["secondaire"], 0.6))
        c.drawString(bleed + 12 * mm, y + 1 * mm, "“")
        # Citation
        y_after = _texte_paragraphe(c, citation, bleed + 18 * mm, y,
                                    w - 2 * bleed - 30 * mm, 9.5, pal["texte"],
                                    _font_corps(projet, italic=True), max_lignes=4)
        # Auteur
        if auteur:
            c.setFont(_font_corps(projet, bold=True), 9)
            c.setFillColor(_rgb(c, pal["primaire"]))
            c.drawString(bleed + 18 * mm, y_after - 1 * mm, f"— {auteur[:50]}")
            y_after -= 5 * mm
        y = y_after - 4 * mm


def _render_remerciements(c, projet, page, w, h, bleed, medias):
    from reportlab.lib.pagesizes import mm
    pal = _ctx_palette(projet, page)
    _fill_bg(c, w, h, pal)
    _ornement_filigrane(c, w, h, pal, "deuil")
    z_titre = _zone_par_id(page, "titre")
    titre = (z_titre.contenu.get("texte") if z_titre else "") or "Remerciements"
    _texte_centre(c, titre[:50], w / 2, h - bleed - 25 * mm, 18, pal["primaire"], _font_titre(projet))
    # Corps
    z_corps = _zone_par_id(page, "corps")
    if z_corps and z_corps.contenu.get("texte"):
        _texte_paragraphe(c, z_corps.contenu["texte"], bleed + 18 * mm,
                          h / 2 + 20 * mm, w - 2 * bleed - 36 * mm, 10.5,
                          pal["texte"], _font_corps(projet), align="center", max_lignes=12)
    # Signature
    z_sig = _zone_par_id(page, "signature")
    if z_sig and z_sig.contenu.get("texte"):
        _texte_centre(c, z_sig.contenu["texte"][:80], w / 2, bleed + 22 * mm,
                      11, pal["primaire"], _font_corps(projet, italic=True, bold=True))


def _render_dos_simple(c, projet, page, w, h, bleed, medias):
    from reportlab.lib.pagesizes import mm
    pal = _ctx_palette(projet, page)
    _fill_bg(c, w, h, pal)
    _ornement_filigrane(c, w, h, pal,
                        "deuil" if "deuil" in page.template_id else "floral")
    # Citation finale
    z_cit = (_zone_par_id(page, "citation_finale") or _zone_par_id(page, "citation"))
    if z_cit and z_cit.contenu.get("texte"):
        _texte_paragraphe(c, z_cit.contenu["texte"], bleed + 18 * mm, h * 0.6,
                          w - 2 * bleed - 36 * mm, 11, pal["texte"],
                          _font_corps(projet, italic=True), align="center", max_lignes=6)
    # QR si dispo
    z_qr = _zone_par_id(page, "rsvp_final") or _zone_par_id(page, "qr")
    if z_qr and z_qr.contenu.get("donnees"):
        png = _qr_png(z_qr.contenu["donnees"], 400)
        if png:
            qr_w = 30 * mm
            _inserer_image(c, png, w / 2 - qr_w / 2, bleed + 18 * mm, qr_w, qr_w, "contain")
            _texte_centre(c, z_qr.contenu.get("legende", "Scanner") [:30],
                          w / 2, bleed + 13 * mm, 8, pal["texte"], _font_corps(projet))
    # Contact
    z_ct = _zone_par_id(page, "contact") or _zone_par_id(page, "contact_familles")
    if z_ct and z_ct.contenu.get("texte"):
        _texte_centre(c, z_ct.contenu["texte"][:80], w / 2, bleed + 8 * mm,
                      8.5, pal["accent"], _font_corps(projet))


# ─── MARIAGE ──────────────────────────────────────────────────────────────────

def _render_mariage_couverture(c, projet, page, w, h, bleed, medias):
    from reportlab.lib.pagesizes import mm
    pal = _ctx_palette(projet, page)
    _fill_bg(c, w, h, pal)
    # Cadre double or
    c.setStrokeColor(_rgb(c, pal["primaire"]))
    c.setLineWidth(1.2)
    c.rect(bleed + 5 * mm, bleed + 5 * mm,
           w - 2 * bleed - 10 * mm, h - 2 * bleed - 10 * mm, fill=False, stroke=True)
    c.setStrokeColor(_rgb(c, pal["accent"]))
    c.setLineWidth(0.4)
    c.rect(bleed + 8 * mm, bleed + 8 * mm,
           w - 2 * bleed - 16 * mm, h - 2 * bleed - 16 * mm, fill=False, stroke=True)
    _ornement_filigrane(c, w, h - 8 * mm, pal, "floral")
    # Mention
    z_men = _zone_par_id(page, "mention")
    mention = (z_men.contenu.get("texte") if z_men else "") or "Invitation"
    _texte_centre(c, mention[:60], w / 2, h - bleed - 28 * mm,
                  11, pal["secondaire"], _font_corps(projet, italic=True))
    # Noms
    z_n = _zone_par_id(page, "noms")
    noms = (z_n.contenu.get("texte") if z_n else "") or projet.titre or ""
    _texte_centre(c, noms[:60], w / 2, h / 2 + 5 * mm, 30, pal["primaire"], _font_titre(projet))
    # Ligne déco
    c.setStrokeColor(_rgb(c, pal["secondaire"]))
    c.setLineWidth(0.6)
    c.line(w / 2 - 25 * mm, h / 2 - 4 * mm, w / 2 + 25 * mm, h / 2 - 4 * mm)
    # Date + lieu
    z_d = _zone_par_id(page, "date")
    if z_d and z_d.contenu.get("texte"):
        _texte_centre(c, z_d.contenu["texte"][:50], w / 2, h / 2 - 14 * mm,
                      14, pal["primaire"], _font_titre(projet))
    z_l = _zone_par_id(page, "lieu_court")
    if z_l and z_l.contenu.get("texte"):
        _texte_centre(c, z_l.contenu["texte"][:60], w / 2, h / 2 - 22 * mm,
                      11, pal["texte"], _font_corps(projet))


# ─── BROCHURE CORPORATE ───────────────────────────────────────────────────────

def _render_brochure_couverture(c, projet, page, w, h, bleed, medias):
    from reportlab.lib.pagesizes import mm
    pal = _ctx_palette(projet, page)
    _fill_bg(c, w, h, pal)
    # Image hero plein cadre haut 60%
    z_hero = _zone_par_id(page, "image_hero")
    img_hero = _media_bytes(z_hero, medias) if z_hero else None
    band_h = h * 0.62
    if img_hero:
        _inserer_image(c, img_hero, 0, h - band_h, w, band_h, "cover")
        # Voile dégradé bas pour lisibilité texte
        _gradient_v(c, w, h - band_h, band_h * 0.5,
                    pal["primaire"], pal["fond"])
    else:
        c.setFillColor(_rgb(c, pal["primaire"]))
        c.rect(0, h - band_h, w, band_h, fill=True, stroke=False)
    # Logo
    z_logo = _zone_par_id(page, "logo")
    img_logo = _media_bytes(z_logo, medias) if z_logo else None
    if img_logo:
        logo_w = 30 * mm
        _inserer_image(c, img_logo, bleed + 8 * mm, h - bleed - 16 * mm,
                       logo_w, 12 * mm, "contain")
    # Titre
    z_t = _zone_par_id(page, "titre")
    if z_t and z_t.contenu.get("texte"):
        _texte_paragraphe(c, z_t.contenu["texte"], bleed + 14 * mm,
                          h - band_h + 20 * mm, w - 2 * bleed - 28 * mm,
                          28, pal["primaire"], _font_titre(projet), max_lignes=3, align="left")
    # Accroche
    z_a = _zone_par_id(page, "accroche")
    if z_a and z_a.contenu.get("texte"):
        _texte_paragraphe(c, z_a.contenu["texte"], bleed + 14 * mm, bleed + 18 * mm,
                          w - 2 * bleed - 28 * mm, 11, pal["texte"],
                          _font_corps(projet, italic=True), max_lignes=3)


def _render_brochure_propositions(c, projet, page, w, h, bleed, medias):
    from reportlab.lib.pagesizes import mm
    pal = _ctx_palette(projet, page)
    _fill_bg(c, w, h, pal)
    # Bande haute
    c.setFillColor(_rgb(c, pal["primaire"]))
    c.rect(0, h - 18 * mm, w, 18 * mm, fill=True, stroke=False)
    z_t = _zone_par_id(page, "titre_section")
    titre = (z_t.contenu.get("texte") if z_t else "") or "Nos services"
    _texte_centre(c, titre[:60], w / 2, h - 11 * mm, 16, (255, 255, 255), _font_titre(projet))
    # Grille services 2 colonnes
    z_s = _zone_par_id(page, "services")
    services = (z_s.contenu.get("items") if z_s else []) or []
    cols = 2
    margin = 14 * mm
    gap = 8 * mm
    cell_w = (w - 2 * bleed - 2 * margin - (cols - 1) * gap) / cols
    cell_h = 38 * mm
    y_top = h - 28 * mm
    for i, srv in enumerate(services[:6]):
        ci = i % cols
        ri = i // cols
        x = bleed + margin + ci * (cell_w + gap)
        y = y_top - (ri + 1) * cell_h - ri * gap
        # Cadre service
        c.setFillColor(_rgba(c, pal["secondaire"], 0.10))
        c.roundRect(x, y, cell_w, cell_h, 2 * mm, fill=True, stroke=False)
        # Numéro
        c.setFillColor(_rgb(c, pal["primaire"]))
        c.circle(x + 8 * mm, y + cell_h - 8 * mm, 4 * mm, fill=True, stroke=False)
        c.setFillColor(_rgb(c, (255, 255, 255)))
        c.setFont(_font_titre(projet), 10)
        c.drawCentredString(x + 8 * mm, y + cell_h - 9.5 * mm, str(i + 1))
        # Titre service
        nom = srv.get("titre", "") if isinstance(srv, dict) else str(srv)
        desc = srv.get("description", "") if isinstance(srv, dict) else ""
        c.setFont(_font_titre(projet), 11)
        c.setFillColor(_rgb(c, pal["primaire"]))
        c.drawString(x + 16 * mm, y + cell_h - 8 * mm, nom[:40])
        # Description
        _texte_paragraphe(c, desc, x + 16 * mm, y + cell_h - 14 * mm,
                          cell_w - 20 * mm, 8.5, pal["texte"], _font_corps(projet),
                          max_lignes=3)


# ─── MENU RESTO ───────────────────────────────────────────────────────────────

def _render_menu_couverture(c, projet, page, w, h, bleed, medias):
    from reportlab.lib.pagesizes import mm
    pal = _ctx_palette(projet, page)
    _fill_bg(c, w, h, pal)
    z_signature = _zone_par_id(page, "image_signature")
    img_sig = _media_bytes(z_signature, medias) if z_signature else None
    if img_sig:
        _inserer_image(c, img_sig, 0, 0, w, h, "cover")
        # Voile sombre
        c.setFillColor(_rgba(c, (0, 0, 0), 0.45))
        c.rect(0, 0, w, h, fill=True, stroke=False)
    # Logo
    z_l = _zone_par_id(page, "logo")
    img_l = _media_bytes(z_l, medias) if z_l else None
    if img_l:
        logo_w = 35 * mm
        _inserer_image(c, img_l, w / 2 - logo_w / 2, h - bleed - 35 * mm,
                       logo_w, 25 * mm, "contain")
    # Nom
    z_n = _zone_par_id(page, "nom_resto")
    nom = (z_n.contenu.get("texte") if z_n else "") or projet.titre
    couleur_titre = (255, 255, 255) if img_sig else pal["primaire"]
    _texte_centre(c, nom[:60], w / 2, h / 2 + 8 * mm, 32, couleur_titre, _font_titre(projet))
    # Accroche
    z_a = _zone_par_id(page, "accroche")
    if z_a and z_a.contenu.get("texte"):
        _texte_centre(c, z_a.contenu["texte"][:80], w / 2, h / 2 - 6 * mm,
                      12, couleur_titre, _font_corps(projet, italic=True))
    # Mention "Carte"
    _texte_centre(c, "— Carte —", w / 2, bleed + 18 * mm,
                  10, couleur_titre, _font_corps(projet, italic=True))


def _render_menu_plats(c, projet, page, w, h, bleed, medias):
    from reportlab.lib.pagesizes import mm
    pal = _ctx_palette(projet, page)
    _fill_bg(c, w, h, pal)
    z_t = _zone_par_id(page, "titre_section")
    titre = (z_t.contenu.get("texte") if z_t else "") or "Notre carte"
    _texte_centre(c, titre[:50], w / 2, h - bleed - 18 * mm, 18, pal["primaire"], _font_titre(projet))
    c.setStrokeColor(_rgb(c, pal["secondaire"]))
    c.setLineWidth(0.4)
    c.line(w / 2 - 25 * mm, h - bleed - 22 * mm, w / 2 + 25 * mm, h - bleed - 22 * mm)
    # Plats
    z_p = _zone_par_id(page, "plats")
    plats = (z_p.contenu.get("items") if z_p else []) or []
    y = h - bleed - 32 * mm
    for plat in plats[:12]:
        if y < bleed + 12 * mm:
            break
        nom = plat.get("nom", "") if isinstance(plat, dict) else str(plat)
        desc = plat.get("description", "") if isinstance(plat, dict) else ""
        prix = plat.get("prix", "") if isinstance(plat, dict) else ""
        # Nom + prix sur la même ligne avec point-leaders simulés
        c.setFont(_font_titre(projet), 11)
        c.setFillColor(_rgb(c, pal["primaire"]))
        c.drawString(bleed + 12 * mm, y, nom[:40])
        if prix:
            c.setFont(_font_titre(projet), 11)
            c.setFillColor(_rgb(c, pal["accent"]))
            c.drawRightString(w - bleed - 12 * mm, y, str(prix)[:20])
        y -= 4.5 * mm
        if desc:
            c.setFont(_font_corps(projet, italic=True), 8.5)
            c.setFillColor(_rgb(c, pal["texte"]))
            c.drawString(bleed + 14 * mm, y, str(desc)[:80])
            y -= 3.8 * mm
        y -= 2 * mm


def _render_menu_dos(c, projet, page, w, h, bleed, medias):
    from reportlab.lib.pagesizes import mm
    pal = _ctx_palette(projet, page)
    _fill_bg(c, w, h, pal)
    # Block contact bas
    c.setFillColor(_rgb(c, pal["primaire"]))
    c.rect(0, 0, w, h * 0.45, fill=True, stroke=False)
    blanc = (255, 255, 255)
    _texte_centre(c, "Bienvenue", w / 2, h * 0.7, 22, pal["primaire"], _font_titre(projet))
    z_h = _zone_par_id(page, "horaires")
    if z_h and z_h.contenu.get("texte"):
        _texte_centre(c, z_h.contenu["texte"][:60], w / 2, h * 0.6,
                      11, pal["texte"], _font_corps(projet))
    z_a = _zone_par_id(page, "adresse")
    if z_a and z_a.contenu.get("texte"):
        _texte_paragraphe(c, z_a.contenu["texte"], bleed + 12 * mm, h * 0.38,
                          w - 2 * bleed - 24 * mm, 11, blanc,
                          _font_corps(projet), align="center", max_lignes=3)
    z_c = _zone_par_id(page, "contact")
    if z_c and z_c.contenu.get("texte"):
        _texte_centre(c, z_c.contenu["texte"][:80], w / 2, h * 0.22,
                      10, blanc, _font_corps(projet))
    z_qr = _zone_par_id(page, "qr")
    if z_qr and z_qr.contenu.get("donnees"):
        png = _qr_png(z_qr.contenu["donnees"], 400)
        if png:
            qr_w = 24 * mm
            _inserer_image(c, png, w / 2 - qr_w / 2, bleed + 8 * mm, qr_w, qr_w, "contain")


# ─── PROGRAMME / LIVRE PHOTO ──────────────────────────────────────────────────

def _render_programme_couverture(c, projet, page, w, h, bleed, medias):
    from reportlab.lib.pagesizes import mm
    pal = _ctx_palette(projet, page)
    _fill_bg(c, w, h, pal)
    _ornement_filigrane(c, w, h, pal, "floral")
    # Cadre
    c.setStrokeColor(_rgb(c, pal["primaire"]))
    c.setLineWidth(1.0)
    c.rect(bleed + 8 * mm, bleed + 8 * mm,
           w - 2 * bleed - 16 * mm, h - 2 * bleed - 16 * mm, fill=False, stroke=True)
    z_t = _zone_par_id(page, "titre")
    titre = (z_t.contenu.get("texte") if z_t else "") or projet.titre
    _texte_centre(c, titre[:60], w / 2, h / 2 + 10 * mm, 26,
                  pal["primaire"], _font_titre(projet))
    z_s = _zone_par_id(page, "sous_titre")
    if z_s and z_s.contenu.get("texte"):
        _texte_centre(c, z_s.contenu["texte"][:80], w / 2, h / 2,
                      12, pal["texte"], _font_corps(projet, italic=True))
    z_dl = _zone_par_id(page, "date_lieu")
    if z_dl and z_dl.contenu.get("texte"):
        _texte_centre(c, z_dl.contenu["texte"][:80], w / 2, h / 2 - 12 * mm,
                      11, pal["accent"], _font_corps(projet))


def _render_livre_photo_couverture(c, projet, page, w, h, bleed, medias):
    from reportlab.lib.pagesizes import mm
    pal = _ctx_palette(projet, page)
    z_h = _zone_par_id(page, "image_hero")
    img_h = _media_bytes(z_h, medias) if z_h else None
    if img_h:
        _inserer_image(c, img_h, 0, 0, w, h, "cover")
        c.setFillColor(_rgba(c, (0, 0, 0), 0.35))
        c.rect(0, 0, w, h * 0.4, fill=True, stroke=False)
    else:
        _gradient_v(c, w, 0, h, pal["primaire"], pal["accent"])
    z_t = _zone_par_id(page, "titre")
    if z_t and z_t.contenu.get("texte"):
        _texte_centre(c, z_t.contenu["texte"][:50], w / 2, h * 0.22,
                      28, (255, 255, 255), _font_titre(projet))
    z_s = _zone_par_id(page, "sous_titre")
    if z_s and z_s.contenu.get("texte"):
        _texte_centre(c, z_s.contenu["texte"][:80], w / 2, h * 0.14,
                      12, (255, 255, 255), _font_corps(projet, italic=True))


# ─── Routeur de templates ─────────────────────────────────────────────────────

TEMPLATE_RENDERERS = {
    "deuil_couverture": _render_deuil_couverture,
    "deuil_familles": _render_deuil_familles,
    "deuil_programme": _render_programme_etapes,
    "deuil_plan": _render_plan,
    "deuil_mediatheque": _render_mediatheque,
    "deuil_temoignages": _render_temoignages,
    "deuil_remerciements": _render_remerciements,
    "deuil_dos": _render_dos_simple,
    "mariage_couverture": _render_mariage_couverture,
    "mariage_invitation": _render_programme_etapes,
    "mariage_plan": _render_plan,
    "mariage_dos": _render_dos_simple,
    "brochure_couverture": _render_brochure_couverture,
    "brochure_propositions": _render_brochure_propositions,
    "brochure_temoignages": _render_temoignages,
    "brochure_contact": _render_plan,
    "menu_couverture": _render_menu_couverture,
    "menu_entrees": _render_menu_plats,
    "menu_dos": _render_menu_dos,
    "programme_couverture": _render_programme_couverture,
    "programme_deroulement": _render_programme_etapes,
    "programme_chants": _render_programme_etapes,
    "livre_photo_couverture": _render_livre_photo_couverture,
    "livre_photo_grille": _render_mediatheque,
}


# ─── Pipeline rendu PDF ───────────────────────────────────────────────────────

def rendre_projet_pdf(projet: ProjetInfographie,
                      medias: dict[str, msm.Media],
                      mode_couleur: str = "rgb") -> bytes:
    from reportlab.lib.pagesizes import mm
    from reportlab.pdfgen import canvas

    proj_def = catalog.PROJETS_INFOGRAPHIE.get(projet.cle_projet)
    if not proj_def:
        raise ValueError(f"Projet inconnu : {projet.cle_projet}")
    fw, fh = proj_def["format_mm"]
    bleed_mm = proj_def["bleed_mm"]
    w = (fw + 2 * bleed_mm) * mm
    h = (fh + 2 * bleed_mm) * mm
    bleed = bleed_mm * mm

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h), pageCompression=1)
    c.setTitle(projet.titre or proj_def["label"])
    c.setSubject(proj_def["label"])
    c.setCreator("Yukpo Designer Pro")
    c.setAuthor("YukpoSecrétariat")

    for page in projet.pages:
        renderer = TEMPLATE_RENDERERS.get(page.template_id)
        if not renderer:
            logger.warning(f"[InfographePro] Template inconnu : {page.template_id} — skip")
        else:
            try:
                renderer(c, projet, page, w, h, bleed, medias)
            except Exception as e:
                logger.error(f"[InfographePro] Rendu page {page.numero} ({page.template_id}) : {e}")
        _coins_imprimerie(c, w, h, bleed)
        c.showPage()

    c.save()
    return buf.getvalue()


def _png_par_page(pdf_bytes: bytes, dpi: int = 150) -> list[bytes]:
    """Rend chaque page en PNG."""
    try:
        from pdf2image import convert_from_bytes
        images = convert_from_bytes(pdf_bytes, dpi=dpi)
        out = []
        for img in images:
            b = io.BytesIO()
            img.save(b, format="PNG", optimize=True)
            out.append(b.getvalue())
        return out
    except Exception as e:
        logger.debug(f"[InfographePro] PNG par page : {e}")
        return []


# ─── Génération via IA ────────────────────────────────────────────────────────

async def _decider_layout_avec_opus(
    brief: str,
    cle_projet: str,
    desc_medias: list[dict],
    profil: Optional[dict],
    directives_visuelles: Optional[dict],
    langue: str,
    pays: str,
) -> tuple[Optional[dict], dict]:
    """
    Sprint 1.1 — Layout AI : Opus 4.7 décide de la composition page-par-page.

    Reçoit le catalogue COMPLET des PAGE_TEMPLATES disponibles + les médias
    user, et retourne pour chaque page :
      - score de pertinence par template candidat (0–100)
      - template_recommande (id du PAGE_TEMPLATE choisi)
      - raison concise
      - custom_layout (proposition de composition libre si aucun template ne convient)

    Retourne (decisions|None, meta_tokens). Échec silencieux → (None, {}).
    Le pipeline Haiku continue normalement avec le template par défaut du projet.
    """
    try:
        from core.ia_client import ia_client, ModeIA, ModelePrioritaire

        proj_def = catalog.PROJETS_INFOGRAPHIE.get(cle_projet)
        if not proj_def:
            return None, {}

        pages_default = proj_def.get("pages") or []
        if not pages_default:
            return None, {}

        catalogue_templates = []
        for tpl_id, tpl in catalog.PAGE_TEMPLATES.items():
            catalogue_templates.append({
                "template_id": tpl_id,
                "label": tpl.get("label"),
                "description": tpl.get("description"),
                "ambiance": tpl.get("ambiance"),
                "slots": [
                    {"slot_id": s.get("slot_id"), "type": s.get("type"),
                     "requis": bool(s.get("requis", False))}
                    for s in (tpl.get("slots") or [])
                ],
            })

        profil = profil or {}
        dv = directives_visuelles or {}
        # Phase 3 — Contexte vertical métier injecté pour Opus (mondial)
        bloc_vert_opus = ""
        try:
            from . import verticales_metier as _vm
            vk = _vm.detecter_vertical(profil.get("metier"), profil.get("secteur"))
            if vk:
                bloc_vert_opus = _vm.construire_bloc_prompt_vertical(vk, pays=pays)
        except Exception:
            pass

        prompt = f"""Tu es DIRECTEUR ARTISTIQUE PRINCIPAL d'une agence design senior
(15+ ans, références : Pentagram, Wieden+Kennedy, agences de Lagos/Dakar/Casablanca).

Mission : décider de la COMPOSITION VISUELLE page-par-page d'un projet print/digital
multi-page. Tu vas évaluer les templates disponibles et choisir le mieux adapté
PAR PAGE, ou proposer un layout custom si aucun template ne convient parfaitement.

═══════════════════════════════════════════════════
  BRIEF CLIENT
═══════════════════════════════════════════════════
\"\"\"{brief[:3000]}\"\"\"

Pays : {pays}   Langue : {langue}
Métier : {profil.get("metier", "(non précisé)")}
Organisation : {profil.get("nom_organisation", "(non précisée)")}
Couleur primaire : {profil.get("couleur_primaire_hex", "(libre)")}
{bloc_vert_opus}
Curseurs utilisateur (0–100) :
- Créativité : {dv.get("creativite", 50)}
- Densité texte : {dv.get("densite_texte", 50)}
- Importance images : {dv.get("importance_images", 50)}
- Élégance : {dv.get("elegance", 50)}

═══════════════════════════════════════════════════
  PROJET (séquence par défaut)
═══════════════════════════════════════════════════
Type : {proj_def.get("label")} ({cle_projet})
Format : {proj_def.get("format_mm")} mm
Pages par défaut : {pages_default}

═══════════════════════════════════════════════════
  CATALOGUE TEMPLATES DISPONIBLES (tous)
═══════════════════════════════════════════════════
{json.dumps(catalogue_templates, ensure_ascii=False)[:14000]}

═══════════════════════════════════════════════════
  MÉDIAS UTILISATEUR
═══════════════════════════════════════════════════
{json.dumps(desc_medias, ensure_ascii=False)[:3000] if desc_medias else "(aucun)"}

═══════════════════════════════════════════════════
  RÈGLES STRICTES
═══════════════════════════════════════════════════
1. Tu produis UNE décision par page de la séquence par défaut.
2. Pour chaque page : choisis le template_id parmi le CATALOGUE qui maximise
   l'impact visuel + cohérence narrative + adéquation au brief.
3. Tu peux conserver le template par défaut OU le remplacer par un autre du
   catalogue (recommandé si tu vois un meilleur fit).
4. Si aucun template ne convient PARFAITEMENT et que tu peux proposer une
   composition vraiment supérieure : remplis "custom_layout" avec
   `{{"composition": "bento|asymetric|fullbleed|grille|timeline|cover_oversized",
   "structure": "description courte 1-2 phrases", "raison": "..."}}`
   Sinon laisse "custom_layout": null.
5. Score de 0 à 100 = ta confiance dans ce choix vs alternatives.
6. "raison" = 15-30 mots max, justifie le choix sur la base composition / hiérarchie / densité.

═══════════════════════════════════════════════════
  SPRINT 1.2 — VARIANTS DE COMPOSITION (5 archétypes)
═══════════════════════════════════════════════════
Pour CHAQUE page, tu produis aussi une liste "variants" de 3 propositions
ALTERNATIVES choisies parmi ces 5 ARCHÉTYPES de composition :

  - "grille_classique"  → grille régulière 2 ou 3 colonnes, hiérarchie typo
                          claire, lecture linéaire (éditorial sobre, rapport)
  - "asymetric"          → composition asymétrique avec un point d'ancrage
                          dominant + texte décalé (impact, modernité)
  - "bento"              → grille modulaire bento (cards de tailles variées),
                          dense visuellement (data viz, portfolio, dashboard)
  - "fullbleed_cover"   → image/visuel pleine page (bord à bord) + texte
                          minimal sur overlay (impact maximum, cover, hero)
  - "timeline_horiz"    → progression horizontale type timeline ou parcours
                          (programme, étapes, story-telling chronologique)

Chaque variant : `{{"archetype": "...", "score": 0-100, "raison": "≤15 mots",
"justification_compo": "comment cet archétype sert l'objectif de cette page"}}`.

La 1ère variante DOIT être la meilleure (score le + élevé). Les 2 suivantes
sont des alternatives crédibles avec un angle différent.

═══════════════════════════════════════════════════
  STRATÉGIE GLOBALE
═══════════════════════════════════════════════════
"global_strategy" : 1-2 phrases (anglais ou français) décrivant l'arc visuel du
projet (ex: "Cover oversized impact, intérieur éditorial aéré, finale call-to-action
plein écran"). Utilisée par le pipeline Haiku/Sonnet pour rester cohérent.

═══════════════════════════════════════════════════
  FORMAT DE SORTIE — JSON STRICT
═══════════════════════════════════════════════════
{{
  "global_strategy": "...",
  "pages": [
    {{
      "numero": 1,
      "template_default": "{pages_default[0] if pages_default else ''}",
      "template_recommande": "id_du_catalogue",
      "score": 85,
      "raison": "...",
      "custom_layout": null,
      "variants": [
        {{"archetype": "fullbleed_cover", "score": 88, "raison": "...",
          "justification_compo": "..."}},
        {{"archetype": "asymetric", "score": 76, "raison": "...",
          "justification_compo": "..."}},
        {{"archetype": "grille_classique", "score": 64, "raison": "...",
          "justification_compo": "..."}}
      ]
    }}
  ]
}}

Retourne UNIQUEMENT le JSON, sans markdown ni préambule."""

        rep = await ia_client.appeler(
            prompt=prompt,
            mode=ModeIA.ANALYSE,
            json_attendu=True,
            forcer_modele=ModelePrioritaire.CLAUDE_OPUS,
        )
        try:
            data = json.loads(rep.contenu)
        except json.JSONDecodeError:
            import re
            m = re.search(r'\{.*\}', rep.contenu, re.DOTALL)
            data = json.loads(m.group()) if m else {}

        if not isinstance(data, dict) or "pages" not in data:
            return None, {}

        # Sprint 1.2 — Vision picker Sonnet : ré-évalue les variants page-par-page
        # selon des critères critiques (équilibre, hiérarchie, lisibilité, impact
        # éditorial). Sonnet a un œil critique différent d'Opus → 2nde opinion.
        # Si Sonnet est plus confiant qu'Opus pour une autre variant → on bascule.
        picker_meta = await _picker_variants_sonnet(
            decisions=data, brief=brief, pays=pays, langue=langue,
        )

        meta = {
            "layout_ai_modele": rep.modele_utilise,
            "layout_ai_tokens_input": rep.tokens_input,
            "layout_ai_tokens_output": rep.tokens_output,
            "layout_ai_decisions": data,
            **picker_meta,
        }
        return data, meta
    except Exception as e:
        logger.warning(f"[InfographePro] Layout AI Opus échoué : {e}")
        return None, {}


async def _picker_variants_sonnet(
    decisions: dict,
    brief: str,
    pays: str,
    langue: str,
) -> dict:
    """
    Sprint 1.2 — Vision Picker Sonnet (text-eval, pas de rendu).

    Reçoit les variants Opus et ré-évalue chaque page selon 4 critères :
      - équilibre visuel (occupation espace, respiration)
      - hiérarchie (point d'ancrage clair, parcours œil)
      - lisibilité (densité, contrastes implicites)
      - impact éditorial (cohérence avec brief + ambition créative)

    Pour chaque page : Sonnet pick une variant + score réajusté + critique courte.
    Si Sonnet pick != variants[0] (top Opus) → on log un override + on bascule
    `archetype_final` sur le pick Sonnet (le pipeline Haiku reçoit cet archétype).

    Échec silencieux → on garde les picks Opus (variants[0] par page).
    """
    try:
        from core.ia_client import ia_client, ModeIA, ModelePrioritaire

        pages_dec = decisions.get("pages") or []
        if not pages_dec:
            return {}

        # Compact payload : on n'envoie que ce dont Sonnet a besoin
        pages_input = [
            {
                "numero": p.get("numero"),
                "template_recommande": p.get("template_recommande"),
                "raison_opus": (p.get("raison") or "")[:200],
                "variants": [
                    {
                        "archetype": v.get("archetype"),
                        "score_opus": v.get("score"),
                        "justification": (v.get("justification_compo") or "")[:200],
                    }
                    for v in (p.get("variants") or [])[:5]
                ],
            }
            for p in pages_dec
        ]

        prompt = (
            f"Tu es CRITIQUE EDITORIAL & ART REVIEWER (15+ ans, ex-Pentagram, ex-Magnum).\n"
            f"Mission : ré-évaluer les variants de composition proposés par le directeur\n"
            f"artistique (Opus) selon 4 CRITÈRES STRICTS, page par page :\n"
            f"  1. Équilibre visuel (occupation espace, respiration, balance masse)\n"
            f"  2. Hiérarchie (point d'ancrage clair, parcours œil, lecture)\n"
            f"  3. Lisibilité (densité texte vs visuel, contrastes implicites)\n"
            f"  4. Impact éditorial (cohérence avec brief + ambition créative)\n\n"
            f"Tu ne vois PAS les images — tu raisonnes sur la SÉMANTIQUE des archétypes\n"
            f"de composition (grille_classique / asymetric / bento / fullbleed_cover /\n"
            f"timeline_horiz) et leur adéquation au contenu de chaque page.\n\n"
            f"Pour CHAQUE page, choisis UNE variant (ton pick) avec un score réajusté\n"
            f"(0-100) + critique courte (≤25 mots). Si tu changes du pick Opus, justifie.\n\n"
            f"BRIEF :\n«{brief[:1500]}»\n"
            f"Pays : {pays}   Langue : {langue}\n\n"
            f"VARIANTS À ÉVALUER :\n{json.dumps(pages_input, ensure_ascii=False, indent=1)}\n\n"
            f"FORMAT DE SORTIE — JSON STRICT :\n"
            f"{{\n"
            f"  \"picks\": [\n"
            f"    {{\"numero\": 1, \"archetype_final\": \"...\", \"score_sonnet\": 92,\n"
            f"     \"critique\": \"...\", \"override_opus\": false}}\n"
            f"  ]\n"
            f"}}\n\n"
            f"Retourne UNIQUEMENT le JSON."
        )
        rep = await ia_client.appeler(
            prompt=prompt,
            mode=ModeIA.ANALYSE,
            json_attendu=True,
            forcer_modele=ModelePrioritaire.CLAUDE_SONNET,
        )
        try:
            picker_data = json.loads(rep.contenu)
        except json.JSONDecodeError:
            import re
            m = re.search(r'\{.*\}', rep.contenu, re.DOTALL)
            picker_data = json.loads(m.group()) if m else {}

        if not isinstance(picker_data, dict) or "picks" not in picker_data:
            return {}

        # Application : on injecte archetype_final sur la décision Opus (mute)
        picks_by_page = {p.get("numero"): p for p in (picker_data.get("picks") or [])}
        nb_overrides = 0
        for page in pages_dec:
            pick = picks_by_page.get(page.get("numero"))
            if not pick:
                continue
            arche_final = pick.get("archetype_final")
            page["archetype_final"] = arche_final
            page["picker_score"] = pick.get("score_sonnet")
            page["picker_critique"] = (pick.get("critique") or "")[:300]
            # Détection override Opus
            top_opus = (page.get("variants") or [{}])[0].get("archetype")
            if arche_final and arche_final != top_opus:
                page["picker_override"] = True
                nb_overrides += 1
            else:
                page["picker_override"] = False

        logger.info(
            f"[InfographePro] Vision picker Sonnet : {nb_overrides}/{len(pages_dec)} "
            f"overrides Opus"
        )
        return {
            "picker_modele": rep.modele_utilise,
            "picker_tokens_input": rep.tokens_input,
            "picker_tokens_output": rep.tokens_output,
            "picker_overrides": nb_overrides,
            "picker_picks": picker_data.get("picks"),
        }
    except Exception as e:
        logger.warning(f"[InfographePro] Vision picker Sonnet échoué : {e}")
        return {}


async def detecter_langue_brief(brief: str, langue_defaut: str = "fr") -> str:
    """
    Sprint L1.1 — Détecte la langue principale du brief utilisateur (~50 tokens
    Haiku, ~0.1 FCFA réel). Override silencieusement la langue passée si elle
    diffère. Codes ISO 639-1 : fr/en/es/pt/ar/de/zh/sw/ha/ru/hi/tr/wo/ln/am.

    Échec silencieux → retourne `langue_defaut`. Pas de coût additionnel
    facturé (inclus dans le pipeline standard).
    """
    if not brief or len(brief.strip()) < 20:
        return langue_defaut
    try:
        from core.ia_client import ia_client, ModeIA, ModelePrioritaire
        prompt = (
            f"Détecte la langue PRINCIPALE de ce texte. Réponds UNIQUEMENT par "
            f"le code ISO 639-1 sur 2 lettres (parmi: fr, en, es, pt, ar, de, "
            f"zh, sw, ha, ru, hi, tr, wo, ln, am). Pas d'explication, juste 2 lettres.\n\n"
            f"Texte : «{brief[:1500]}»"
        )
        rep = await ia_client.appeler(
            prompt=prompt, mode=ModeIA.PRECISION,
            forcer_modele=ModelePrioritaire.CLAUDE_HAIKU,
            max_tokens_override=20, utiliser_cache=True,
        )
        code = (rep.contenu or "").strip().lower()[:2]
        valides = {"fr", "en", "es", "pt", "ar", "de", "zh", "sw", "ha",
                   "ru", "hi", "tr", "wo", "ln", "am"}
        if code in valides:
            if code != langue_defaut:
                logger.info(f"[L1] Langue override : {langue_defaut} → {code} (détecté)")
            return code
    except Exception as e:
        logger.debug(f"[L1] Détection langue échouée : {e}")
    return langue_defaut


async def generer_projet_depuis_brief(
    brief: str,
    cle_projet: str,
    medias: dict[str, msm.Media],
    pays: str = "CM",
    profil: Optional[dict] = None,
    langue: str = "fr",
    directives_visuelles: Optional[dict] = None,
    layout_ai: bool = False,
) -> ProjetInfographie:
    """
    L'IA reçoit le catalogue de pages + descripteurs des médias disponibles,
    et produit la structure complète du projet (textes par slot + assignations médias).
    """
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire

    proj_def = catalog.PROJETS_INFOGRAPHIE.get(cle_projet)
    if not proj_def:
        raise ValueError(f"Projet inconnu : {cle_projet}")

    # Sprint L1.1 — Auto-détection langue : override silencieux si différent
    langue = await detecter_langue_brief(brief, langue_defaut=langue)

    desc_projet = catalog.descripteur_pour_ia(cle_projet)
    desc_medias = [msm.descripteur_pour_ia(m) for m in medias.values()]

    profil = profil or {}
    metier = profil.get("metier", "")
    nom_org = profil.get("nom_organisation", "")
    couleur_prim = profil.get("couleur_primaire_hex", "")
    couleurs_acc = profil.get("couleurs_accents_hex", []) or []

    dv = directives_visuelles or {}
    def _pct(key: str, default: int) -> int:
        try:
            v = int(dv.get(key, default))
            return max(0, min(100, v))
        except Exception:
            return default
    creativite = _pct("creativite", 50)
    densite_texte = _pct("densite_texte", 50)
    importance_images = _pct("importance_images", 50)
    elegance = _pct("elegance", 50)
    # Phase 3 — Contexte vertical métier (mondial, pas de RAG figé)
    # 1. Profil.metier/secteur d'abord (rapide)
    # 2. Si profil vide → fallback Haiku depuis brief (refinement Phase 3+)
    bloc_vertical = ""
    try:
        from . import verticales_metier as _vm
        vert_key = _vm.detecter_vertical(metier, profil.get("secteur"))
        if not vert_key and brief:
            vert_key = await _vm.detecter_vertical_depuis_brief(brief)
        if vert_key:
            bloc_vertical = _vm.construire_bloc_prompt_vertical(vert_key, pays=pays)
    except Exception:
        pass

    bloc_directives = (
        f"\n═══════════════════════════════════════════════════\n"
        f"  DIRECTIVES VISUELLES (curseurs utilisateur, 0–100)\n"
        f"═══════════════════════════════════════════════════\n"
        f"- Créativité      : {creativite}/100  (0=sobre/classique, 100=audacieux/expérimental)\n"
        f"- Densité texte   : {densite_texte}/100  (0=aéré/minimaliste, 100=riche/dense)\n"
        f"- Importance images : {importance_images}/100  (0=texte dominant, 100=images pleine page)\n"
        f"- Élégance        : {elegance}/100  (0=fonctionnel, 100=cérémonial/luxe)\n"
        f"Adapte ton choix de palette, longueur des textes, ton, et hiérarchie visuelle\n"
        f"en respectant ces curseurs.\n"
    )

    # Sprint 2.4 — Brand Kit : injection ToV/lexique/mots interdits dans le prompt
    brand_kit = (dv.get("__brand_kit__") if isinstance(dv, dict) else None) or {}
    bloc_brand_kit = ""
    if brand_kit:
        tov = (brand_kit.get("tone_of_voice") or "").strip()
        lex_pref = brand_kit.get("lexique_prefere") or []
        mots_int = brand_kit.get("mots_interdits") or []
        baseline = brand_kit.get("baseline") or ""
        strict = int(brand_kit.get("strictness") or 70)
        if tov or lex_pref or mots_int or baseline:
            bloc_brand_kit = (
                f"\n═══════════════════════════════════════════════════\n"
                f"  BRAND KIT VERROUILLÉ (Sprint 2.4) — strictness={strict}/100\n"
                f"═══════════════════════════════════════════════════\n"
                f"- Tone of voice : {tov or '(aucun)'}\n"
                f"- Baseline officielle : {baseline or '(aucune)'}\n"
                f"- Vocabulaire préféré : {', '.join(lex_pref) if lex_pref else '(libre)'}\n"
                f"- Mots INTERDITS (à NE PAS utiliser) : {', '.join(mots_int) if mots_int else '(aucun)'}\n"
                f"RÈGLE STRICTE : tu DOIS respecter ces consignes brand sur l'ensemble des\n"
                f"textes générés. Si strictness ≥ 70, c'est un VERROU non-négociable —\n"
                f"chaque mot interdit présent dans la sortie est un échec.\n"
            )

    # Sprint 1.1 — Layout AI : Opus 4.7 décide composition pré-Haiku
    layout_decisions: Optional[dict] = None
    layout_meta: dict = {}
    bloc_layout_ai = ""
    if layout_ai:
        layout_decisions, layout_meta = await _decider_layout_avec_opus(
            brief=brief, cle_projet=cle_projet, desc_medias=desc_medias,
            profil=profil, directives_visuelles=directives_visuelles,
            langue=langue, pays=pays,
        )
        if layout_decisions:
            strat = (layout_decisions.get("global_strategy") or "")[:400]
            pages_dec = layout_decisions.get("pages") or []
            pages_dec_compact = [
                {
                    "numero": p.get("numero"),
                    "template_recommande": p.get("template_recommande"),
                    "score": p.get("score"),
                    "raison": (p.get("raison") or "")[:200],
                    "custom_layout": p.get("custom_layout"),
                    # Sprint 1.2 — archétype final retenu après vision picker Sonnet
                    "archetype_final": p.get("archetype_final"),
                    "picker_critique": p.get("picker_critique"),
                }
                for p in pages_dec
            ]
            bloc_layout_ai = (
                f"\n═══════════════════════════════════════════════════\n"
                f"  LAYOUT AI — DÉCISIONS DIRECTEUR ARTISTIQUE (Opus 4.7) +\n"
                f"  VISION PICKER (Sonnet 4.6 — 5 archétypes : grille_classique /\n"
                f"  asymetric / bento / fullbleed_cover / timeline_horiz)\n"
                f"═══════════════════════════════════════════════════\n"
                f"Stratégie globale : {strat}\n\n"
                f"Décisions page-par-page (à RESPECTER strictement) :\n"
                f"{json.dumps(pages_dec_compact, ensure_ascii=False, indent=2)}\n\n"
                f"RÈGLE : pour chaque page,\n"
                f"  • utilise EXACTEMENT le `template_recommande` comme valeur de `template`\n"
                f"  • si `archetype_final` est défini : ajoute un champ `notes` à la page\n"
                f"    reflétant cet archétype de composition (ex: 'Composition fullbleed_cover\n"
                f"    : visuel pleine page bord-à-bord, texte minimal en overlay bas-gauche')\n"
                f"  • si `custom_layout` est non-null, complète `notes` avec sa structure\n"
            )

    prompt = f"""Tu es directeur artistique senior et copywriter expert (15+ ans agence pro).

═══════════════════════════════════════════════════
  MISSION
═══════════════════════════════════════════════════
Conçois un PROJET MULTI-PAGE professionnel niveau agence (rivaliser avec studios de design),
adapté précisément au brief client. Tu décides des textes, médias, et structure complète.

═══════════════════════════════════════════════════
  CONTEXTE
═══════════════════════════════════════════════════
Pays de diffusion : {pays}
Langue de rédaction : {langue}
Métier client : {metier or "(non précisé)"}
Organisation : {nom_org or "(non précisée)"}
Couleur primaire de marque : {couleur_prim or "(libre)"}
Couleurs accents : {', '.join(couleurs_acc) if couleurs_acc else "(libres)"}

═══════════════════════════════════════════════════
  BRIEF UTILISATEUR
═══════════════════════════════════════════════════
\"\"\"{brief}\"\"\"

═══════════════════════════════════════════════════
  PROJET À PRODUIRE
═══════════════════════════════════════════════════
{json.dumps(desc_projet, ensure_ascii=False, indent=2)}

═══════════════════════════════════════════════════
  MÉDIATHÈQUE UTILISATEUR DISPONIBLE
═══════════════════════════════════════════════════
{json.dumps(desc_medias, ensure_ascii=False, indent=2) if desc_medias else "(aucun média uploadé)"}
{bloc_vertical}{bloc_directives}{bloc_brand_kit}{bloc_layout_ai}
═══════════════════════════════════════════════════
  RÈGLES STRICTES
═══════════════════════════════════════════════════
1. Pour chaque page du projet, remplis tous les slots `requis` au minimum. Tu peux remplir
   les slots optionnels si pertinent.
2. Pour les slots de type "image_user", choisis la `ref` parmi la médiathèque ci-dessus
   en associant catégorie/role (ex: portrait_defunt → photo type portrait).
   Si aucun média ne convient, omets la zone (le moteur affichera un placeholder).
3. Pour `liste`, `programme`, `temoignage`, `famille` : produis des `items` riches, complets,
   adaptés au contexte africain/francophone. **PAS de placeholder type "[à compléter]"**.
4. Pour `carte` : produis `coords: [{{"lat": X.XXX, "lon": Y.YYY}}]` plausibles selon
   le pays et les indices du brief, ainsi que `adresses` complètes.
5. Pour `qr` : produis un champ `donnees` (URL ou texte court) cohérent et un `legende`.
6. Tu peux varier l'ambiance par page si pertinent via `palette_override` (ex: page
   souvenirs plus chaleureuse).
7. Le ton et le vocabulaire doivent rivaliser avec un copywriter pro (pas de banalités,
   pas de redites, structure narrative cohérente sur l'ensemble du livret).
8. **Aucun champ inventé** qui contredirait le brief (pas de date imaginaire, etc.).
9. EFFETS TYPOGRAPHIQUES (Sprint 1.3) : tu peux ajouter à n'importe quelle zone
   `texte` un champ `style.effets` pour enrichir visuellement (utilise avec parcimonie
   sur les TITRES principaux, jamais sur du corps de texte courant). Effets dispo :
   - "shadow"  : `{{"dx":1.5,"dy":-1.5,"color":[0,0,0],"alpha":0.4}}`  ombre portée
   - "outline" : `{{"width":0.6,"color":[0,0,0]}}`                       contour fill+stroke
   - "outline_only" : `{{"width":0.8,"color":[200,40,80]}}`              contour seul (texte creux)
   - "gradient": `{{"col_debut":[r,g,b],"col_fin":[r,g,b],"direction":"vertical|horizontal","radial":false}}`
   - "courbe"  : `{{"rayon_pt":80,"arc_deg":120,"concave":false}}`       texte sur arc (titres impact)
   - "blend"   : `{{"alpha":0.7}}`                                        transparence simple
   Ils peuvent se combiner (shadow + gradient, etc.). Réservés aux compositions
   "fullbleed_cover", "asymetric" ou "bento" (jamais sur "grille_classique").

═══════════════════════════════════════════════════
  FORMAT DE SORTIE — JSON STRICT
═══════════════════════════════════════════════════
{{
  "titre": "Titre global du projet (ex: nom des mariés ou du défunt ou de la marque)",
  "palette": "{'|'.join(PALETTES.keys())}",
  "palette_hex_primaire": "#RRGGBB ou null",
  "palettes_hex_accents": ["#RRGGBB", ...],
  "langue": "{langue}",
  "pages": [
    {{
      "numero": 1,
      "template": "id_template_de_la_page",
      "zones": [
        {{"slot_id": "id_du_slot", "type": "texte", "contenu": {{"texte": "..."}}}},
        {{"slot_id": "...", "type": "image_user", "contenu": {{"ref_media": "session:abc"}}}},
        {{"slot_id": "...", "type": "liste", "contenu": {{"items": ["...", "..."]}}}},
        {{"slot_id": "...", "type": "famille", "contenu": {{"items": [
          {{"nom": "Nom famille", "membres": ["Membre 1", "Membre 2"]}}
        ]}}}},
        {{"slot_id": "...", "type": "programme", "contenu": {{"items": [
          {{"date": "...", "heure": "...", "lieu": "...", "titre": "..."}}
        ]}}}},
        {{"slot_id": "...", "type": "temoignage", "contenu": {{"items": [
          {{"citation": "...", "auteur": "..."}}
        ]}}}},
        {{"slot_id": "...", "type": "carte", "contenu": {{"coords": [{{"lat": 3.87, "lon": 11.52}}]}}}},
        {{"slot_id": "...", "type": "qr", "contenu": {{"donnees": "https://...", "legende": "..."}}}},
        {{"slot_id": "photos", "type": "image_user", "contenu": {{"items": [
          {{"ref_media": "session:abc", "legende": "..."}}
        ]}}}},
        {{"slot_id": "...", "type": "image_ia", "contenu": {{
          "prompt": "Description visuelle DÉTAILLÉE en anglais pour génération d'image (30-60 mots, style/sujet/ambiance/composition explicites — adapté au contexte africain quand pertinent : tenue, peau, environnement)",
          "format": "portrait_4_3 | portrait_16_9 | landscape_4_3 | landscape_16_9 | square"
        }}}}
      ]
    }}
  ]
}}

Note pour les slots image :
- Si tu trouves un média user pertinent → utilise "image_user" avec ref_media.
- SINON pour les slots qui demandent un visuel (couverture, illustration de fond,
  motif décoratif, page de garde, scène d'ambiance) → propose "image_ia" avec un
  prompt anglais détaillé. Le moteur générera l'image via Flux. Évite "image_ia"
  pour des portraits de personnes réelles (utilise une photo user) ou des
  signatures/cachets (toujours user).

Retourne UNIQUEMENT le JSON, sans commentaire, sans markdown."""

    # On force Haiku 4.5 pour cette étape : la sortie est du JSON structuré
    # avec contenus prédéfinis (titres, listes, prompts d'images), pas du
    # raisonnement complexe → Haiku suffit largement et est ~12× moins cher
    # que Sonnet/GPT-4o sans perte de qualité perceptible.
    reponse = await ia_client.appeler(
        prompt=prompt,
        mode=ModeIA.REDACTION,
        json_attendu=True,
        forcer_modele=ModelePrioritaire.CLAUDE_HAIKU,
    )
    try:
        data = json.loads(reponse.contenu)
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{.*\}', reponse.contenu, re.DOTALL)
        data = json.loads(match.group()) if match else {}

    # Construire le ProjetInfographie
    palette_custom = None
    if data.get("palette_hex_primaire"):
        palette_custom = _palette_personnalisee_depuis_hex(
            data["palette_hex_primaire"],
            data.get("palettes_hex_accents") or couleurs_acc,
        )
    elif couleur_prim:
        palette_custom = _palette_personnalisee_depuis_hex(couleur_prim, couleurs_acc)

    pages_obj: list[Page] = []
    for p_data in data.get("pages", []) or []:
        zones_obj = []
        for z in p_data.get("zones", []) or []:
            zones_obj.append(Zone(
                slot_id=z.get("slot_id", ""),
                type=z.get("type", "texte"),
                contenu=z.get("contenu", {}) or {},
                style=z.get("style", {}) or {},
            ))
        pages_obj.append(Page(
            numero=int(p_data.get("numero", len(pages_obj) + 1)),
            template_id=p_data.get("template", ""),
            zones=zones_obj,
            palette_override=p_data.get("palette_override"),
            notes_ia=p_data.get("notes"),
        ))

    projet = ProjetInfographie(
        cle_projet=cle_projet,
        titre=data.get("titre", proj_def["label"]),
        palette=data.get("palette") or proj_def.get("palette", "classique"),
        palette_custom=palette_custom,
        pages=pages_obj,
        medias_refs=[f"{m.portee}:{m.media_id}" for m in medias.values()],
        polices=proj_def.get("polices", {"titre": "Helvetica-Bold", "corps": "Helvetica"}),
        langue=data.get("langue", langue),
        meta={
            "modele": reponse.modele_utilise,
            "tokens_input": reponse.tokens_input,
            "tokens_output": reponse.tokens_output,
            "fallback_utilise": reponse.fallback_utilise,
            **layout_meta,
        },
    )
    return projet


async def generer_projet(
    brief: str,
    cle_projet: str,
    user_id: str,
    session_id: str,
    medias_refs: Optional[list[str]] = None,
    pays: str = "CM",
    profil: Optional[dict] = None,
    langue: str = "fr",
    export_cmyk: bool = True,
    dpi_pages: int = 150,
    dpi_pages_hd: int = 300,
    directives_visuelles: Optional[dict] = None,
    mode_visuel: str = "sans",   # "sans" | "standard" | "premium" | "ultra" | "ultra_plus"
    reference_style_ref: Optional[str] = None,   # Sprint 1.6 — "session:abc"|"compte:def"
    reference_strength: float = 0.65,
    brand_lora_url: Optional[str] = None,        # Sprint 1.6 — URL LoRA fal.ai
    brand_lora_scale: float = 0.85,
) -> ResultatProjet:
    """
    Pipeline complet : brief + médias → projet IA → (génération images IA si
    `mode_visuel != "sans"`) → PDF + PNG par page.

    `mode_visuel` :
    - "sans"       : aucune image IA générée — placeholder pour les slots image_ia
    - "standard"   : Flux schnell via fal.ai (rapide, ~1s/image)
    - "premium"    : Flux dev via fal.ai (qualité supérieure, ~5-10s/image)
    - "ultra"      : Flux 1.1 Pro Ultra (raw cinematic SOTA)
    - "ultra_plus" : Sprint 1.5 — ensemble Flux Pro Ultra + Recraft v3 + Ideogram 2
                     en parallèle ; Sonnet vision picker choisit la meilleure des 3
    """
    medias = msm.resoudre_refs(medias_refs or [], user_id, session_id) if medias_refs else {}

    # Sprint 1.1 — Layout AI (Opus 4.7) actif uniquement en premium/ultra/ultra_plus
    # (le coût Opus n'est pas justifié sur les modes économiques)
    layout_ai_active = mode_visuel in ("premium", "ultra", "ultra_plus")

    t0 = time.time()
    projet = await generer_projet_depuis_brief(
        brief=brief, cle_projet=cle_projet, medias=medias,
        pays=pays, profil=profil, langue=langue,
        directives_visuelles=directives_visuelles,
        layout_ai=layout_ai_active,
    )
    t_ia = time.time() - t0

    # ── Pipeline images IA (Niveau 3 : Flux + vision check Premium) ────────
    nb_images_generees = 0
    duree_images_ms = 0
    # Sprint 1.6 — résolution référence style (URL publique du média réf)
    ref_url_resolved: Optional[str] = None
    if reference_style_ref and reference_style_ref in medias:
        try:
            from . import mediatheque_session as _msm2
            ref_media = medias[reference_style_ref]
            # On a besoin d'une URL publique pour fal.ai. On utilise une dataURL
            # base64 (fal.ai accepte data:image/png;base64,...).
            ref_bytes = _msm2.lire_bytes(ref_media)
            import base64 as _b64
            ref_url_resolved = (
                f"data:{ref_media.mime or 'image/png'};base64,"
                f"{_b64.b64encode(ref_bytes).decode('ascii')}"
            )
        except Exception as e:
            logger.warning(f"[InfographePro] Référence style {reference_style_ref} non résolue : {e}")

    if mode_visuel in ("standard", "premium", "ultra", "ultra_plus"):
        t_img = time.time()
        nb_images_generees = await _generer_images_ia_pour_projet(
            projet=projet,
            medias=medias,
            mode=mode_visuel,
            user_id=user_id,
            session_id=session_id,
            brief=brief,
            pays=pays,
            reference_url=ref_url_resolved,
            reference_strength=reference_strength,
            brand_lora_url=brand_lora_url,
            brand_lora_scale=brand_lora_scale,
        )
        duree_images_ms = int((time.time() - t_img) * 1000)

    pdf = rendre_projet_pdf(projet, medias, mode_couleur="rgb")
    pdf_cmyk = None
    if export_cmyk:
        try:
            pdf_cmyk = rendre_projet_pdf(projet, medias, mode_couleur="cmyk")
        except Exception as e:
            logger.warning(f"[InfographePro] CMJN échoué : {e}")

    # Sprint 1.8c — Print-ready PDF/X-1a:2001 (post-traitement pikepdf)
    # Le CMYK est priorité (PDF/X-1a est CMYK par définition). Le RGB reste
    # disponible pour preview/web mais on l'enrichit aussi en TrimBox/BleedBox
    # pour cohérence (utile aux imprimeries qui font la conversion elles-mêmes).
    try:
        from . import pdf_print_ready as _pp
        format_trim = (proj_def["format_mm"][0], proj_def["format_mm"][1])
        bleed_mm = float(proj_def.get("bleed_mm", 3))
        titre = projet.titre or proj_def["label"]
        if pdf_cmyk:
            pdf_cmyk = _pp.convertir_en_pdf_x1a(pdf_cmyk, titre, format_trim, bleed_mm)
        # On enrichit aussi le RGB des trim/bleed boxes (pas un vrai PDF/X mais
        # pratique pour imprimeurs qui chargent dans Indesign/Illustrator)
        pdf = _pp.convertir_en_pdf_x1a(pdf, titre, format_trim, bleed_mm)
    except Exception as e:
        logger.warning(f"[InfographePro] PDF/X-1a post-traitement skip : {e}")

    pages_png = _png_par_page(pdf, dpi=dpi_pages)
    pages_png_hd = _png_par_page(pdf, dpi=dpi_pages_hd) if dpi_pages_hd != dpi_pages else pages_png

    proj_def = catalog.PROJETS_INFOGRAPHIE[cle_projet]

    return ResultatProjet(
        pdf_bytes=pdf,
        pdf_cmyk_bytes=pdf_cmyk,
        pages_png=pages_png,
        pages_png_hd=pages_png_hd,
        projet=projet,
        meta={
            "cle_projet": cle_projet,
            "label": proj_def["label"],
            "nombre_pages": len(projet.pages),
            "format_mm": list(proj_def["format_mm"]),
            "prix_fcfa": proj_def["prix_fcfa"],
            "duree_ia_ms": int(t_ia * 1000),
            "tokens_input": (projet.meta or {}).get("tokens_input"),
            "tokens_output": (projet.meta or {}).get("tokens_output"),
            "modele": (projet.meta or {}).get("modele"),
            "medias_utilises": len(medias),
            "mode_visuel": mode_visuel,
            "nb_images_ia": nb_images_generees,
            "duree_images_ms": duree_images_ms,
            "layout_ai_active": layout_ai_active,
            "layout_ai_modele": (projet.meta or {}).get("layout_ai_modele"),
            "layout_ai_tokens_input": (projet.meta or {}).get("layout_ai_tokens_input"),
            "layout_ai_tokens_output": (projet.meta or {}).get("layout_ai_tokens_output"),
            # Sprint 1.2 — Vision picker Sonnet
            "picker_modele": (projet.meta or {}).get("picker_modele"),
            "picker_tokens_input": (projet.meta or {}).get("picker_tokens_input"),
            "picker_tokens_output": (projet.meta or {}).get("picker_tokens_output"),
            "picker_overrides": (projet.meta or {}).get("picker_overrides"),
            # Sprint 1.6 — IP-Adapter / Brand LoRA
            "reference_style_active": bool(ref_url_resolved),
            "brand_lora_active": bool(brand_lora_url),
        },
    )


async def _construire_directive_artistique(
    brief: str,
    projet_titre: str,
    pays: str,
    mode: str,
) -> str:
    """
    Étape "art director" : Claude Sonnet définit une directive visuelle
    cohérente pour TOUTES les images du projet (palette photo, style,
    lighting, ambiance, contexte africain…). Le résultat est ensuite
    préfixé à chaque prompt d'image pour garantir la cohérence.

    Skip silencieusement (retourne "") en mode "standard" pour économiser
    le coût LLM sur ce tier d'entrée.
    """
    if mode == "standard" or mode == "sans":
        return ""
    try:
        from core.ia_client import ia_client, ModeIA, ModelePrioritaire
        prompt = (
            f"Tu es directeur artistique senior. Définis en 60-100 mots une "
            f"directive visuelle UNIFIÉE pour toutes les illustrations d'un projet "
            f"intitulé « {projet_titre[:200]} » (pays : {pays}). "
            f"Brief client :\n«{brief[:1000]}»\n\n"
            f"Réponds STRICTEMENT par une seule phrase anglaise dense (style, lighting, "
            f"color grading, photography reference, mood) à utiliser comme préfixe à "
            f"chaque prompt Flux. Exemple de format : "
            f"« Editorial corporate photography, golden hour soft lighting, warm cinematic "
            f"color grade, candid documentary style, 35mm shallow depth of field, "
            f"Afrocentric subjects, modern professional African setting ». "
            f"Pas de markdown, pas de préambule."
        )
        rep = await ia_client.appeler(
            prompt=prompt,
            mode=ModeIA.REDACTION,
            forcer_modele=ModelePrioritaire.CLAUDE_SONNET,
        )
        directive = (rep.contenu or "").strip().strip('"').strip("«").strip("»").strip()
        return directive[:600]
    except Exception as e:
        logger.debug(f"[InfographePro] directive artistique skipped : {e}")
        return ""


async def _enrichir_prompt_image(
    prompt_brut: str,
    directive: str,
    contexte_zone: str,
    mode: str,
) -> str:
    """
    Étape "art director" : Claude Sonnet enrichit le prompt brut du Haiku
    avec des détails cinématographiques (lighting, lens, composition, mood,
    references) pour matcher la qualité Midjourney/DALL-E.

    Skip en mode "standard" (économie). Si Sonnet échoue → on retourne le
    prompt brut combiné à la directive.
    """
    base = (directive + ". " + prompt_brut).strip(". ")
    if mode == "standard" or mode == "sans":
        return prompt_brut[:1500]
    try:
        from core.ia_client import ia_client, ModeIA, ModelePrioritaire
        meta_prompt = (
            f"Tu es prompt engineer expert en Flux 1.1. Enrichis le prompt suivant "
            f"avec : sujet précis, lighting cinématographique, lens 35mm/50mm + DOF, "
            f"color grading, composition (rule of thirds / leading lines), "
            f"references photographiques (editorial, lifestyle, documentary, fashion), "
            f"qualité (high detail, hyper realistic). Reste fidèle au sujet. Anglais, "
            f"40-80 mots, dense, sans markdown.\n\n"
            f"Directive globale du projet :\n«{directive[:300]}»\n\n"
            f"Contexte de la zone : {contexte_zone[:200]}\n\n"
            f"Prompt brut à enrichir :\n«{prompt_brut[:800]}»\n\n"
            f"Réponds par le PROMPT ENRICHI seulement, sans préambule."
        )
        rep = await ia_client.appeler(
            prompt=meta_prompt,
            mode=ModeIA.REDACTION,
            forcer_modele=ModelePrioritaire.CLAUDE_SONNET,
        )
        enrichi = (rep.contenu or "").strip().strip('"').strip("«").strip("»").strip()
        if enrichi and len(enrichi) > 30:
            return enrichi[:1500]
    except Exception as e:
        logger.debug(f"[InfographePro] enrichissement skipped : {e}")
    return base[:1500]


async def _generer_images_ia_pour_projet(
    projet: ProjetInfographie,
    medias: dict[str, msm.Media],
    mode: str,
    user_id: str,
    session_id: str,
    brief: str = "",
    pays: str = "CM",
    reference_url: Optional[str] = None,        # Sprint 1.6 — IP-Adapter
    reference_strength: float = 0.65,
    brand_lora_url: Optional[str] = None,        # Sprint 1.6 — Brand LoRA
    brand_lora_scale: float = 0.85,
) -> int:
    """
    Pour chaque zone `image_ia` du projet, génère une image via fal.ai
    (Niveau 3 hybride avec art director enrichment + variants pour les
    modes premium et ultra). Injecte les images générées dans le dict
    `medias` comme des Media de session synthétiques.

    Retourne le nombre d'images effectivement générées.
    """
    from .image_gen import (
        generer_images_batch, valider_image_vision,
        ImageMode, ImageGenError,
    )

    # 1. Collecter toutes les zones image_ia
    zones_a_generer: list[tuple[Zone, str, str, int]] = []
    for page in projet.pages:
        for zone in page.zones:
            if zone.type != "image_ia":
                continue
            prompt = (zone.contenu or {}).get("prompt") or ""
            fmt = (zone.contenu or {}).get("format") or "portrait_4_3"
            if not prompt.strip():
                continue
            zones_a_generer.append((zone, prompt, fmt, page.numero or 1))

    if not zones_a_generer:
        return 0

    logger.info(
        f"[InfographePro] Génération de {len(zones_a_generer)} image(s) IA "
        f"en mode {mode} (user={user_id})"
    )

    # 2. Étape art director (Sonnet) : style guide unifié pour le projet
    directive = await _construire_directive_artistique(
        brief=brief, projet_titre=projet.titre, pays=pays, mode=mode,
    )
    if directive:
        logger.info(f"[InfographePro] Directive artistique : {directive[:120]}…")

    # 3. Enrichir chaque prompt en parallèle (Sonnet, modes premium/ultra/ultra_plus)
    enrichis: list[str] = []
    if mode in ("premium", "ultra", "ultra_plus"):
        import asyncio as _asyncio
        contextes = [f"page {p}, slot {z.slot_id or '?'}" for (z, _p, _f, p) in zones_a_generer]
        enrichis = list(await _asyncio.gather(*(
            _enrichir_prompt_image(prompt_brut=p, directive=directive,
                                    contexte_zone=ctx, mode=mode)
            for ((_z, p, _f, _pg), ctx) in zip(zones_a_generer, contextes)
        )))
    else:
        enrichis = [p for (_z, p, _f, _pg) in zones_a_generer]

    # 4. Génération images (1 variante en standard/ultra_plus*, 2 variantes en
    #    premium/ultra). *ultra_plus génère déjà 3 modèles différents = 3 variantes
    #    de fait, donc pas besoin de multiplier par seed.
    mode_typed: ImageMode
    if mode == "ultra_plus":
        mode_typed = "ultra_plus"
    elif mode == "ultra":
        mode_typed = "ultra"
    elif mode == "premium":
        mode_typed = "premium"
    else:
        mode_typed = "standard"
    nb_variantes = 2 if mode in ("premium", "ultra") else 1
    prompts_batch = [(enrichis[i], zones_a_generer[i][2]) for i in range(len(zones_a_generer))]
    images_bytes = await generer_images_batch(
        prompts_batch, mode=mode_typed, nb_variantes=nb_variantes,
        reference_url=reference_url,
        reference_strength=reference_strength,
        brand_lora_url=brand_lora_url,
        brand_lora_scale=brand_lora_scale,
    )

    # 5. Validation finale (vision check + 1 retry, modes premium/ultra/ultra_plus)
    if mode in ("premium", "ultra", "ultra_plus"):
        nouvelles_images: list[Optional[bytes]] = []
        for ((zone, _p_raw, fmt, _pg), prompt_enrichi, img) in zip(
            zones_a_generer, enrichis, images_bytes,
        ):
            if img is None:
                nouvelles_images.append(None)
                continue
            ok, raison = await valider_image_vision(img, prompt_enrichi)
            if ok:
                nouvelles_images.append(img)
                continue
            logger.info(f"[InfographePro] Vision rejette image ({raison[:60]}) — retry")
            try:
                from .image_gen import generer_image
                retry_img = await generer_image(prompt_enrichi, mode=mode_typed, format_=fmt)
                nouvelles_images.append(retry_img)
            except ImageGenError:
                nouvelles_images.append(img)
        images_bytes = nouvelles_images

    # 6. Sauvegarder + injecter dans medias + remapper les zones
    nb_ok = 0
    for ((zone, prompt_brut, _fmt, _pg), img) in zip(zones_a_generer, images_bytes):
        if not img:
            continue
        try:
            media = msm.ajouter_media(
                portee="session",
                owner_id=session_id or user_id,
                contenu=img,
                nom_fichier=f"ia_{zone.slot_id or 'img'}.png",
                mime="image/png",
                categorie="illustration",
                label=prompt_brut[:80],
            )
            medias[media.media_id] = media
            zone.type = "image_user"
            zone.contenu = {**(zone.contenu or {}), "ref_media": f"session:{media.media_id}"}
            nb_ok += 1
        except Exception as e:
            logger.warning(f"[InfographePro] Sauvegarde image IA échouée : {e}")

    return nb_ok
