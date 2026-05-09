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
    # Nom
    z_nom = _zone_par_id(page, "nom")
    nom = (z_nom.contenu.get("texte") if z_nom else None) or projet.titre or ""
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

async def generer_projet_depuis_brief(
    brief: str,
    cle_projet: str,
    medias: dict[str, msm.Media],
    pays: str = "CM",
    profil: Optional[dict] = None,
    langue: str = "fr",
    directives_visuelles: Optional[dict] = None,
) -> ProjetInfographie:
    """
    L'IA reçoit le catalogue de pages + descripteurs des médias disponibles,
    et produit la structure complète du projet (textes par slot + assignations médias).
    """
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire

    proj_def = catalog.PROJETS_INFOGRAPHIE.get(cle_projet)
    if not proj_def:
        raise ValueError(f"Projet inconnu : {cle_projet}")

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
{bloc_directives}
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
    mode_visuel: str = "sans",   # "sans" | "standard" | "premium"
) -> ResultatProjet:
    """
    Pipeline complet : brief + médias → projet IA → (génération images IA si
    `mode_visuel != "sans"`) → PDF + PNG par page.

    `mode_visuel` :
    - "sans"     : aucune image IA générée — placeholder pour les slots image_ia
    - "standard" : Flux schnell via fal.ai (rapide, ~1s/image)
    - "premium"  : Flux dev via fal.ai (qualité supérieure, ~5-10s/image)
    """
    medias = msm.resoudre_refs(medias_refs or [], user_id, session_id) if medias_refs else {}

    t0 = time.time()
    projet = await generer_projet_depuis_brief(
        brief=brief, cle_projet=cle_projet, medias=medias,
        pays=pays, profil=profil, langue=langue,
        directives_visuelles=directives_visuelles,
    )
    t_ia = time.time() - t0

    # ── Pipeline images IA (Niveau 3 : Flux + vision check Premium) ────────
    nb_images_generees = 0
    duree_images_ms = 0
    if mode_visuel in ("standard", "premium", "ultra"):
        t_img = time.time()
        nb_images_generees = await _generer_images_ia_pour_projet(
            projet=projet,
            medias=medias,
            mode=mode_visuel,
            user_id=user_id,
            session_id=session_id,
            brief=brief,
            pays=pays,
        )
        duree_images_ms = int((time.time() - t_img) * 1000)

    pdf = rendre_projet_pdf(projet, medias, mode_couleur="rgb")
    pdf_cmyk = None
    if export_cmyk:
        try:
            pdf_cmyk = rendre_projet_pdf(projet, medias, mode_couleur="cmyk")
        except Exception as e:
            logger.warning(f"[InfographePro] CMJN échoué : {e}")

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

    # 3. Enrichir chaque prompt en parallèle (Sonnet, modes premium/ultra)
    enrichis: list[str] = []
    if mode in ("premium", "ultra"):
        import asyncio as _asyncio
        contextes = [f"page {p}, slot {z.slot_id or '?'}" for (z, _p, _f, p) in zones_a_generer]
        enrichis = list(await _asyncio.gather(*(
            _enrichir_prompt_image(prompt_brut=p, directive=directive,
                                    contexte_zone=ctx, mode=mode)
            for ((_z, p, _f, _pg), ctx) in zip(zones_a_generer, contextes)
        )))
    else:
        enrichis = [p for (_z, p, _f, _pg) in zones_a_generer]

    # 4. Génération images (1 variante en standard, 2 variantes en premium/ultra)
    mode_typed: ImageMode
    if mode == "ultra":
        mode_typed = "ultra"
    elif mode == "premium":
        mode_typed = "premium"
    else:
        mode_typed = "standard"
    nb_variantes = 2 if mode in ("premium", "ultra") else 1
    prompts_batch = [(enrichis[i], zones_a_generer[i][2]) for i in range(len(zones_a_generer))]
    images_bytes = await generer_images_batch(
        prompts_batch, mode=mode_typed, nb_variantes=nb_variantes,
    )

    # 5. Validation finale (vision check + 1 retry, modes premium/ultra)
    if mode in ("premium", "ultra"):
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
