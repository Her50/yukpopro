"""
Freeform Layout — Renderer générique JSON → PDF.

Architecture LLM-FIRST sans templates rigides : le LLM compose un JSON
de primitives géométriques (rectangles, textes positionnés, images,
QR, lignes, courbes, ornements) et ce module les rasterise en PDF
ReportLab. Adapté à TOUS les visuels imprimables :

- Cartes de visite (8-up A4 90×55mm + crop marks)
- Flyers A3/A4/A5 avec photo héroïque + texte hiérarchisé
- BD éducative N pages avec cases + bulles dialogue
- Packaging dieline (boîte produit, étiquette, dosette)
- CV graphique 1 page (timeline, barres compétences)
- Posts réseaux sociaux (Instagram carré, story 9:16, LinkedIn paysage)
- Affiches événement
- Dépliants 2/3 volets
- Livrets/Programmes/Menus (alternative aux PAGE_TEMPLATES rigides)
- Livre photo, magazine, rapport visuel
- Mind map, infographie ludique, schéma technique

Format unité = mm pour cohérence print. Bleed/Trim/Safe zone gérés.
"""
from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional, Union

logger = logging.getLogger("yukpo_assurance.bureau.freeform_layout")

# 1mm ≈ 2.834645 points ReportLab
_MM_TO_PT = 72.0 / 25.4


def mm_to_pt(mm: float) -> float:
    return mm * _MM_TO_PT


def parse_color(hex_str: Optional[str], default: tuple = (1, 1, 1)):
    """Parse '#RRGGBB' ou '#RGB' ou nom CSS basique → ReportLab Color."""
    from reportlab.lib.colors import Color, HexColor, white, black
    if not hex_str:
        return Color(*default)
    s = hex_str.strip()
    if s.startswith("#"):
        try:
            return HexColor(s)
        except Exception:
            return Color(*default)
    name = s.lower()
    css = {
        "white": white, "black": black,
        "transparent": Color(1, 1, 1, alpha=0),
        "none": Color(1, 1, 1, alpha=0),
    }
    return css.get(name, Color(*default))


# ─── Schema des primitives ──────────────────────────────────────────────────


@dataclass
class ElementBase:
    """Élément géométrique positionné en mm depuis le coin haut-gauche de la page."""
    type: str
    x_mm: float = 0
    y_mm: float = 0
    w_mm: float = 0
    h_mm: float = 0
    rotation_deg: float = 0
    opacity: float = 1.0
    z_index: int = 0


@dataclass
class Rectangle(ElementBase):
    fond: Optional[str] = None         # hex ou None (pas de fill)
    border: Optional[str] = None       # hex
    border_width_pt: float = 0
    border_radius_mm: float = 0


@dataclass
class Texte(ElementBase):
    contenu: str = ""
    police: str = "Helvetica"          # Helvetica, Helvetica-Bold, Inter, Inter-Bold, Times, Courier...
    taille_pt: float = 10
    couleur: str = "#000000"
    alignement: str = "left"           # left | center | right | justify
    interligne: float = 1.2
    bold: bool = False
    italic: bool = False
    underline: bool = False
    letter_spacing_pt: float = 0


@dataclass
class TexteFluide(ElementBase):
    """Texte qui s'écoule AUTOUR d'obstacles (text-wrap polygone).

    Pour chaque ligne, le moteur calcule les intervalles libres de x
    en évitant les obstacles, puis remplit ces intervalles avec les
    mots. C'est le mode 'magazine' où le texte enveloppe une image
    non-rectangulaire ou plusieurs images.

    Obstacles supportés :
    - 'rectangle' : {type, x_mm, y_mm, w_mm, h_mm, padding_mm}
    - 'cercle'    : {type, cx_mm, cy_mm, r_mm, padding_mm}
    - 'polygone'  : {type, points_mm: [[x1,y1], [x2,y2], ...], padding_mm}

    Si obstacles est vide, se comporte comme un Texte rectangulaire
    classique.
    """
    contenu: str = ""
    police: str = "Helvetica"
    taille_pt: float = 10
    couleur: str = "#000000"
    alignement: str = "left"           # left | right | justify
    interligne: float = 1.4
    bold: bool = False
    italic: bool = False
    obstacles: list[dict] = field(default_factory=list)


@dataclass
class Image(ElementBase):
    """Image embedded — soit ref_media (résolu depuis mediathèque session),
    soit data_url (data:image/png;base64,...), soit url (https://...).
    Pour un visuel généré IA : type='image_ia' avec un champ prompt."""
    ref_media: Optional[str] = None      # 'session:abc' ou 'compte:def'
    data_url: Optional[str] = None
    url: Optional[str] = None
    prompt_ia: Optional[str] = None      # Si fourni, sera généré par fal.ai/Replicate avant rendu
    mode: str = "cover"                  # cover | contain | stretch
    border_radius_mm: float = 0


@dataclass
class Ligne(ElementBase):
    """Trait droit ou courbe simple (par x1/y1/x2/y2)."""
    x1_mm: float = 0
    y1_mm: float = 0
    x2_mm: float = 0
    y2_mm: float = 0
    epaisseur_pt: float = 0.5
    couleur: str = "#000000"
    style: str = "solid"             # solid | dashed | dotted


@dataclass
class QR(ElementBase):
    """QR code (vCard, URL, texte arbitraire)."""
    donnees: str = ""
    couleur: str = "#000000"
    fond: str = "#FFFFFF"


@dataclass
class Ornement(ElementBase):
    """Motif décoratif vectoriel (vague, géométrique, feuilles, ligne accent)."""
    motif: str = "ligne"             # ligne | vague | geometrique | feuilles | etoile | coeur
    couleur: str = "#000000"
    epaisseur_pt: float = 1.0


@dataclass
class CropMarks(ElementBase):
    """Crop marks pour découpe imprimerie (autour d'une zone)."""
    longueur_mm: float = 3
    epaisseur_pt: float = 0.25
    couleur: str = "#000000"
    decalage_mm: float = 1            # distance entre le trim et le début de la marque


@dataclass
class Icone(ElementBase):
    """Icône vectorielle SVG depuis bibliothèque Iconify (200 000+ icônes,
    100+ collections : Lucide, Tabler, Heroicons, Phosphor, Material Symbols,
    Carbon, Fluent, etc.). Le renderer télécharge le SVG via API Iconify et
    l'embed dans le PDF (qualité vectorielle, zoom infini).
    Exemples :
      {"type": "icone", "prefix": "tabler", "name": "wifi", "x_mm": 10, "y_mm": 10, "w_mm": 8, "h_mm": 8, "couleur": "#0047AB"}
      {"type": "icone", "prefix": "lucide", "name": "battery-charging", ...}
      {"type": "icone", "prefix": "material-symbols", "name": "home-outline", ...}
    """
    prefix: str = "tabler"
    name: str = "circle"
    couleur: str = "currentColor"     # hex ou "currentColor" (=noir par défaut)


Element = Union[Rectangle, Texte, Image, Ligne, QR, Ornement, CropMarks, Icone]


@dataclass
class LayoutPage:
    numero: int = 1
    fond_couleur: Optional[str] = "#FFFFFF"
    fond_image_ref: Optional[str] = None
    elements: list[Element] = field(default_factory=list)
    # Override format / bleed par page — None = hérite du document.
    # Permet les ensembles multi-pièces (faire-part deuil/mariage avec
    # carte principale A6 + livret A5 + carte CB, kit événement
    # affiche A3 + flyer A5 + ticket A7, etc.) dans un seul PDF.
    format_mm: Optional[tuple[float, float]] = None
    bleed_mm: Optional[float] = None
    libelle_piece: Optional[str] = None  # « carte_principale », « livret_messe », « remerciement »…


@dataclass
class LayoutDocument:
    """Document libre composé de N pages avec primitives positionnées."""
    titre: str = "Document"
    format_mm: tuple[float, float] = (210, 297)  # A4 portrait par défaut
    bleed_mm: float = 3
    pages: list[LayoutPage] = field(default_factory=list)
    palette_meta: dict = field(default_factory=dict)
    polices_embeddees: list[str] = field(default_factory=list)


# ─── Désérialisation JSON → LayoutDocument ─────────────────────────────────


_TYPE_TO_CLASS = {
    "rectangle":     Rectangle,
    "rect":          Rectangle,
    "texte":         Texte,
    "text":          Texte,
    "texte_fluide":  TexteFluide,
    "text_wrap":     TexteFluide,
    "image":         Image,
    "image_ia":      Image,
    "ligne":         Ligne,
    "line":          Ligne,
    "qr":            QR,
    "qrcode":        QR,
    "ornement":      Ornement,
    "ornament":      Ornement,
    "crop_marks":    CropMarks,
    "cropmarks":     CropMarks,
    "icone":         Icone,
    "icon":          Icone,
}


def parse_layout_json(data: dict) -> LayoutDocument:
    """Construit un LayoutDocument à partir d'un JSON conforme.
    Tolérant aux clés manquantes : valeurs par défaut + log warning."""
    if not isinstance(data, dict):
        raise ValueError("Layout JSON doit être un dict")
    fmt = data.get("format_mm") or [210, 297]
    if isinstance(fmt, list) and len(fmt) >= 2:
        format_mm = (float(fmt[0]), float(fmt[1]))
    else:
        format_mm = (210, 297)
    bleed = float(data.get("bleed_mm") or 3)

    pages = []
    pages_data = data.get("pages") or []
    if not isinstance(pages_data, list):
        pages_data = []
    for idx, p_data in enumerate(pages_data):
        if not isinstance(p_data, dict):
            continue
        elements = []
        for e_data in (p_data.get("elements") or []):
            if not isinstance(e_data, dict):
                continue
            etype = (e_data.get("type") or "").lower().strip()
            cls = _TYPE_TO_CLASS.get(etype)
            if not cls:
                logger.debug(f"[freeform] Type inconnu : {etype}")
                continue
            try:
                # Filtrer les clés que dataclass connaît
                kwargs = {
                    k: v for k, v in e_data.items()
                    if k in cls.__dataclass_fields__
                }
                elements.append(cls(**kwargs))
            except Exception as e:
                logger.debug(f"[freeform] Element {etype} skip : {e}")
                continue
        # Format par-page optionnel (multi-pièces)
        p_fmt = p_data.get("format_mm")
        page_format_mm: Optional[tuple[float, float]] = None
        if isinstance(p_fmt, list) and len(p_fmt) >= 2:
            try:
                page_format_mm = (float(p_fmt[0]), float(p_fmt[1]))
            except (TypeError, ValueError):
                page_format_mm = None
        p_bleed = p_data.get("bleed_mm")
        try:
            page_bleed_mm = float(p_bleed) if p_bleed is not None else None
        except (TypeError, ValueError):
            page_bleed_mm = None

        pages.append(LayoutPage(
            numero=int(p_data.get("numero", idx + 1)),
            fond_couleur=p_data.get("fond_couleur", "#FFFFFF"),
            fond_image_ref=p_data.get("fond_image_ref"),
            elements=elements,
            format_mm=page_format_mm,
            bleed_mm=page_bleed_mm,
            libelle_piece=p_data.get("libelle_piece"),
        ))

    if not pages:
        # Garde-fou : au moins une page vide pour pouvoir rendre quelque chose
        pages = [LayoutPage(numero=1, fond_couleur="#FFFFFF", elements=[])]

    return LayoutDocument(
        titre=data.get("titre") or "Document",
        format_mm=format_mm,
        bleed_mm=bleed,
        pages=pages,
        palette_meta=data.get("palette_meta") or {},
        polices_embeddees=data.get("polices_embeddees") or [],
    )


# ─── Renderer ReportLab ──────────────────────────────────────────────────────


async def pre_generer_images_ia(doc: LayoutDocument) -> None:
    """Pré-génère les images IA (éléments Image avec prompt_ia non vide et
    sans ref_media/data_url/url) via fal.ai Flux Pro Ultra et stocke les
    bytes en data_url base64 sur l'élément. À appeler AVANT rendre_layout_pdf
    (qui est synchrone).

    Permet au LLM de produire {type:"image", prompt_ia:"Starlink V4 Mini
    satellite dish on wooden table outdoor view", x_mm, y_mm, w_mm, h_mm}
    et que le rendu final embarque une vraie image générée Flux.

    Concurrence : génère en parallèle (sémaphore=3) pour limiter les appels
    fal.ai simultanés. Échec d'une image -> placeholder (pas blocage rendu).
    """
    import asyncio
    import base64 as _b64

    a_generer: list[Image] = []
    for page in doc.pages:
        for el in page.elements:
            if isinstance(el, Image) and el.prompt_ia and not (el.ref_media or el.data_url or el.url):
                a_generer.append(el)
    if not a_generer:
        return

    try:
        from .image_gen import generer_image, ImageMode, ImageGenError
    except Exception:
        logger.info("[freeform/IA] image_gen non disponible — images IA skipées")
        return

    # Dédup par (prompt, format) : pipeline 2-phases duplique le template
    # × N cartes, donc 20 cartes avec le même logo IA = 1 seule génération
    # partagée. Évite 20× appels Flux Ultra (~25s chacun = 8+ min).
    def _fmt_for(el: Image) -> str:
        if not (el.w_mm and el.h_mm):
            return "landscape_4_3"
        ratio = el.w_mm / el.h_mm
        if ratio > 1.5: return "landscape_16_9"
        if ratio > 1.1: return "landscape_4_3"
        if ratio < 0.7: return "portrait_16_9"
        if ratio < 0.9: return "portrait_4_3"
        return "square"

    groupes: dict[tuple[str, str], list[Image]] = {}
    for el in a_generer:
        cle = (el.prompt_ia[:500], _fmt_for(el))
        groupes.setdefault(cle, []).append(el)

    logger.info(
        f"[freeform/IA] {len(a_generer)} éléments image_ia → "
        f"{len(groupes)} générations uniques (dédup pipeline 2-phases)"
    )

    sem = asyncio.Semaphore(3)

    # ── Détection automatique du registre visuel ────────────────────────
    # Pour un visuel MARKETING (promo/affiche/campagne/landing/teaser),
    # on bascule en mode "premium" (Flux dev 28 steps, ~10-15s, qualité ×3
    # vs fast). Pour un document texte simple (carte visite, facture, mémo),
    # "fast" suffit. Détection par mots-clés dans le titre + nb d'images
    # demandées. Configurable via env FREEFORM_IMAGE_MODE_DEFAULT.
    import os as _os
    titre_lower = (getattr(doc, "titre", "") or "").lower()
    keywords_marketing = (
        "promo", "promotion", "concours", "tirage", "tombola", "campagne",
        "campaign", "marketing", "publicité", "publicite", "ad ", "affiche",
        "poster", "flyer", "annonce", "teaser", "lancement", "launch",
        "événement", "evenement", "event", "soldes", "cashback", "deal",
        "offre", "gagne", "gagnez", "win", "concour", "loterie",
    )
    marketing_detecte = any(kw in titre_lower for kw in keywords_marketing)
    mode_image = _os.getenv("FREEFORM_IMAGE_MODE_DEFAULT") or (
        "premium" if marketing_detecte or len(groupes) <= 3 else "fast"
    )
    # Budget timeout adapté au mode :
    #   fast (Flux schnell)  : 5-8s/image  → 60s budget global suffisant
    #   premium (Flux dev)   : 10-15s/img  → 180s budget pour ne pas perdre
    #   ultra (Flux Pro)     : 25-30s/img  → 300s budget
    _BUDGET_PAR_MODE = {"fast": 60.0, "premium": 180.0, "ultra": 300.0}
    budget_total_s = _BUDGET_PAR_MODE.get(mode_image, 60.0)
    logger.info(
        f"[freeform/IA] {len(groupes)} groupes IA — mode={mode_image} "
        f"(marketing={marketing_detecte}, budget={budget_total_s}s)"
    )

    async def _one_groupe(prompt: str, fmt: str, els: list[Image]):
        async with sem:
            try:
                bts = await generer_image(
                    prompt=prompt, mode=mode_image, format_=fmt,
                )
                if bts:
                    data_url = (
                        f"data:image/png;base64,"
                        f"{_b64.b64encode(bts).decode('ascii')}"
                    )
                    for el in els:
                        el.data_url = data_url
                else:
                    logger.warning(
                        f"[freeform/IA] image '{prompt[:40]}' bytes vides "
                        f"({mode_image}) → placeholder gris"
                    )
            except Exception as e:
                logger.warning(
                    f"[freeform/IA] image '{prompt[:40]}' KO ({mode_image}) : {e}"
                )

    # Budget total dur : timeout adapté au mode (60/180/300s). Au-delà, on
    # coupe net et on laisse les placeholders — mieux qu'un timeout client.
    try:
        await asyncio.wait_for(
            asyncio.gather(*(_one_groupe(p, f, els) for (p, f), els in groupes.items())),
            timeout=budget_total_s,
        )
        logger.info(
            f"[freeform/IA] {len(groupes)} génération(s) IA terminée(s) "
            f"en mode {mode_image}"
        )
    except asyncio.TimeoutError:
        logger.warning(
            f"[freeform/IA] Timeout {budget_total_s}s mode={mode_image} — "
            f"{len(groupes)} groupes lancés, images manquantes = placeholders"
        )


def rendre_layout_pdf(doc: LayoutDocument, medias: Optional[dict] = None) -> bytes:
    """Rasterise un LayoutDocument en PDF via ReportLab canvas.

    `medias` : dict optionnel {ref → Media} pour résoudre les éléments
    Image avec ref_media. Si absent, ces images sont skippées (placeholder).
    Compatible bleed/crop : si bleed_mm > 0, le canvas total = format + 2*bleed
    et les TrimBox/BleedBox sont posés via pdf_print_ready downstream.
    """
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import landscape
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    doc_fmt_w_mm, doc_fmt_h_mm = doc.format_mm
    doc_bleed = doc.bleed_mm

    # ── Polices : tenter de charger Inter via font_loader ──────────────────
    try:
        from . import font_loader as _fl
        for famille in ("Inter", "Inter-Bold", "Inter-SemiBold"):
            chemin = _fl.chemin_police(famille) if hasattr(_fl, "chemin_police") else None
            if chemin:
                try:
                    pdfmetrics.registerFont(TTFont(famille, str(chemin)))
                except Exception:
                    pass
    except Exception:
        pass

    buf = io.BytesIO()
    # Canvas initial dimensionné sur la 1re page (override page si présent).
    first_page = doc.pages[0] if doc.pages else None
    p0_w_mm = (first_page.format_mm[0] if first_page and first_page.format_mm else doc_fmt_w_mm)
    p0_h_mm = (first_page.format_mm[1] if first_page and first_page.format_mm else doc_fmt_h_mm)
    p0_bleed = (first_page.bleed_mm if first_page and first_page.bleed_mm is not None else doc_bleed)
    init_w = mm_to_pt(p0_w_mm + 2 * p0_bleed)
    init_h = mm_to_pt(p0_h_mm + 2 * p0_bleed)
    c = canvas.Canvas(buf, pagesize=(init_w, init_h))
    c.setTitle(doc.titre)
    c.setAuthor("Yukpo")

    import time as _t
    for idx_page, page in enumerate(doc.pages):
        t0_page = _t.time()
        # Format/bleed effectif de la page (override > document)
        page_fmt_w_mm = page.format_mm[0] if page.format_mm else doc_fmt_w_mm
        page_fmt_h_mm = page.format_mm[1] if page.format_mm else doc_fmt_h_mm
        page_bleed = page.bleed_mm if page.bleed_mm is not None else doc_bleed
        total_w = mm_to_pt(page_fmt_w_mm + 2 * page_bleed)
        total_h = mm_to_pt(page_fmt_h_mm + 2 * page_bleed)
        offset_x = mm_to_pt(page_bleed)
        offset_y = mm_to_pt(page_bleed)
        # Redimensionne la page courante (chaque showPage utilise pagesize courant)
        c.setPageSize((total_w, total_h))

        # Fond
        if page.fond_couleur and page.fond_couleur not in ("none", "transparent"):
            col = parse_color(page.fond_couleur, default=(1, 1, 1))
            c.setFillColor(col)
            c.rect(0, 0, total_w, total_h, stroke=0, fill=1)

        # Fond image (image pleine page bord-à-bord avec bleed)
        if page.fond_image_ref and medias and page.fond_image_ref in medias:
            try:
                _draw_image_filling_page(c, medias[page.fond_image_ref], total_w, total_h)
            except Exception as e:
                logger.debug(f"[freeform] Fond image skip : {e}")

        # Trier par z_index pour ordre de rendu
        ordered = sorted(page.elements, key=lambda el: getattr(el, "z_index", 0) or 0)

        nb_ok = 0
        nb_skip = 0
        types_count: dict[str, int] = {}
        for el in ordered:
            types_count[type(el).__name__] = types_count.get(type(el).__name__, 0) + 1
            try:
                _render_element(c, el, offset_x, offset_y, page_fmt_w_mm, page_fmt_h_mm, medias)
                nb_ok += 1
            except Exception as e:
                nb_skip += 1
                logger.debug(f"[freeform] Element skip ({type(el).__name__}) : {e}")
                continue

        elapsed = _t.time() - t0_page
        logger.warning(
            f"[freeform/render] page {idx_page+1}/{len(doc.pages)} OK en {elapsed:.1f}s — "
            f"{nb_ok} ok / {nb_skip} skip — types={types_count}"
        )
        c.showPage()

    c.save()
    return buf.getvalue()


def _render_element(
    c, el: Element, off_x: float, off_y: float,
    fmt_w_mm: float, fmt_h_mm: float, medias: Optional[dict],
) -> None:
    """Rendre un élément. Le système de coordonnées du LLM a (0,0) en HAUT
    gauche de la zone trim ; ReportLab a (0,0) en BAS gauche. On flippe Y.
    `off_x/off_y` = bleed offset depuis le bord physique."""
    # Y-flip : page_pt - el.y_mm - el.h_mm
    fmt_h_pt = mm_to_pt(fmt_h_mm)

    if isinstance(el, Rectangle):
        x = off_x + mm_to_pt(el.x_mm)
        y = off_y + fmt_h_pt - mm_to_pt(el.y_mm + el.h_mm)
        w = mm_to_pt(el.w_mm)
        h = mm_to_pt(el.h_mm)
        if el.fond:
            c.setFillColor(parse_color(el.fond))
        if el.border:
            c.setStrokeColor(parse_color(el.border))
            c.setLineWidth(el.border_width_pt or 0.5)
        radius = mm_to_pt(el.border_radius_mm or 0)
        if radius > 0:
            c.roundRect(x, y, w, h, radius,
                         stroke=1 if el.border else 0,
                         fill=1 if el.fond else 0)
        else:
            c.rect(x, y, w, h,
                    stroke=1 if el.border else 0,
                    fill=1 if el.fond else 0)
        return

    if isinstance(el, Texte):
        x = off_x + mm_to_pt(el.x_mm)
        y_top = off_y + fmt_h_pt - mm_to_pt(el.y_mm)
        # Police + style
        font_name = el.police or "Helvetica"
        if el.bold and "Bold" not in font_name:
            font_name = f"{font_name}-Bold" if font_name in ("Helvetica", "Times", "Courier", "Inter") else font_name
        base_size = el.taille_pt or 10
        # ── Auto-scale anti-overflow ─────────────────────────────────────
        # Bug observé : titre "GAGNEZ GROS AVEC MTN MEGA" en 36pt dans une
        # boîte w=80mm h=20mm → word-wrap génère 3 lignes × 43pt leading =
        # 129pt mais h dispo = 56pt → les 2 dernières lignes débordent et
        # écrasent le sous-titre "À GAGNER :" placé juste en dessous.
        # Stratégie : si débordement détecté, réduit progressivement taille_pt
        # jusqu'à ce que l'ensemble tienne dans h_mm (min 7pt pour mentions
        # légales).
        max_w_pt = mm_to_pt(el.w_mm) if el.w_mm else None
        max_h_pt = mm_to_pt(el.h_mm) if el.h_mm else None
        effective_size = float(base_size)
        if max_w_pt and max_h_pt:
            for _attempt in range(8):
                try:
                    c.setFont(font_name, effective_size)
                except Exception:
                    c.setFont("Helvetica", effective_size)
                lignes_test = _wrap_text(
                    c, el.contenu or "", font_name, effective_size, max_w_pt
                )
                interligne = el.interligne or 1.2
                hauteur_totale = (
                    effective_size + (len(lignes_test) - 1) * effective_size * interligne
                )
                # Tolérance 5% pour absorber le baseline shift
                if hauteur_totale <= max_h_pt * 1.05:
                    break
                if effective_size <= 7:
                    break
                # Réduire 15% → converge en 3-4 itérations sur cas extrêmes
                effective_size *= 0.85
        try:
            c.setFont(font_name, effective_size)
        except Exception:
            c.setFont("Helvetica", effective_size)
        c.setFillColor(parse_color(el.couleur, default=(0, 0, 0)))

        # Word-wrap final avec la taille calculée
        leading = effective_size * (el.interligne or 1.2)
        lignes = _wrap_text(c, el.contenu or "", font_name, effective_size, max_w_pt)
        cur_y = y_top - effective_size   # baseline première ligne
        for ligne in lignes:
            tw = c.stringWidth(ligne, font_name, effective_size)
            if el.alignement == "center":
                draw_x = x + ((max_w_pt or tw) - tw) / 2
            elif el.alignement == "right":
                draw_x = x + ((max_w_pt or tw) - tw)
            else:
                draw_x = x
            c.drawString(draw_x, cur_y, ligne)
            if el.underline:
                c.setLineWidth(0.5)
                c.setStrokeColor(parse_color(el.couleur, default=(0, 0, 0)))
                c.line(draw_x, cur_y - 1.5, draw_x + tw, cur_y - 1.5)
            cur_y -= leading
        return

    if isinstance(el, Image):
        x = off_x + mm_to_pt(el.x_mm)
        y = off_y + fmt_h_pt - mm_to_pt(el.y_mm + el.h_mm)
        w = mm_to_pt(el.w_mm)
        h = mm_to_pt(el.h_mm)
        # ── Cache ImageReader scope render ─────────────────────────────────
        # Sur impression bulk (100 cartes × 8 cartes/planche = 100+ usages du
        # même logo Orange/identité), l'ancien code refaisait `_resoudre_image`
        # + `ImageReader(BytesIO(bytes))` à chaque occurrence : 100× base64
        # decode + 100× PIL JPEG/PNG decode = ~5-15s perdues par planche dense.
        # Le cache est attaché au canvas (GC quand le render finit, pas de
        # leak cross-render). Clé : data_url|ref_media|url (cheap hash si
        # data_url > 200 chars).
        cache: dict = getattr(c, "_yukpo_img_cache", None)
        if cache is None:
            cache = {}
            c._yukpo_img_cache = cache
        # Construit la clé sans dupliquer les payloads volumineux
        if el.data_url:
            key = f"d:{hash(el.data_url) & 0xFFFFFFFF:08x}"
        elif el.ref_media:
            key = f"r:{el.ref_media}"
        elif el.url:
            key = f"u:{el.url}"
        else:
            key = None
        ir = cache.get(key) if key else None
        if ir is None:
            img_data = _resoudre_image(el, medias)
            if not img_data:
                c.setFillColorRGB(0.92, 0.92, 0.92)
                c.rect(x, y, w, h, stroke=0, fill=1)
                return
            from reportlab.lib.utils import ImageReader
            try:
                ir = ImageReader(io.BytesIO(img_data))
                if key:
                    cache[key] = ir
            except Exception as e:
                logger.debug(f"[freeform] Image decode skip : {e}")
                return
        try:
            c.drawImage(ir, x, y, w, h, mask="auto",
                        preserveAspectRatio=(el.mode == "contain"))
        except Exception as e:
            logger.debug(f"[freeform] Image render skip : {e}")
        return

    if isinstance(el, Ligne):
        x1 = off_x + mm_to_pt(el.x1_mm)
        y1 = off_y + fmt_h_pt - mm_to_pt(el.y1_mm)
        x2 = off_x + mm_to_pt(el.x2_mm)
        y2 = off_y + fmt_h_pt - mm_to_pt(el.y2_mm)
        c.setStrokeColor(parse_color(el.couleur, default=(0, 0, 0)))
        c.setLineWidth(el.epaisseur_pt or 0.5)
        if el.style == "dashed":
            c.setDash(4, 3)
        elif el.style == "dotted":
            c.setDash(1, 2)
        c.line(x1, y1, x2, y2)
        c.setDash()  # reset
        return

    if isinstance(el, QR):
        x = off_x + mm_to_pt(el.x_mm)
        y = off_y + fmt_h_pt - mm_to_pt(el.y_mm + el.h_mm)
        w = mm_to_pt(el.w_mm)
        h = mm_to_pt(el.h_mm)
        try:
            from reportlab.graphics.barcode.qr import QrCodeWidget
            from reportlab.graphics.shapes import Drawing
            from reportlab.graphics import renderPDF
            qrw = QrCodeWidget(el.donnees or "")
            bb = qrw.getBounds()
            qw, qh = bb[2] - bb[0], bb[3] - bb[1]
            d = Drawing(w, h, transform=[w / qw, 0, 0, h / qh, 0, 0])
            d.add(qrw)
            renderPDF.draw(d, c, x, y)
        except Exception as e:
            logger.debug(f"[freeform] QR skip : {e}")
            c.setFillColorRGB(0.85, 0.85, 0.85)
            c.rect(x, y, w, h, stroke=0, fill=1)
        return

    if isinstance(el, Ornement):
        _draw_ornement(c, el, off_x, off_y, fmt_h_pt)
        return

    if isinstance(el, CropMarks):
        _draw_crop_marks(c, el, off_x, off_y, fmt_h_pt)
        return

    if isinstance(el, TexteFluide):
        _draw_texte_fluide(c, el, off_x, off_y, fmt_h_pt)
        return

    if isinstance(el, Icone):
        _draw_icone(c, el, off_x, off_y, fmt_h_pt)
        return


def _intervalles_libres_sur_ligne(
    box_x_pt: float, box_w_pt: float,
    ligne_y_pt: float, ligne_h_pt: float,
    obstacles_pt: list[dict],
) -> list[tuple[float, float]]:
    """Calcule les intervalles libres [x1,x2] de x où le texte peut s'écouler
    sur la bande horizontale [ligne_y, ligne_y+ligne_h].

    Stratégie : commence avec un intervalle complet [box_x, box_x+box_w],
    puis pour chaque obstacle qui INTERSECTE la bande, on retire l'intervalle
    occupé par l'obstacle (avec padding). Si l'obstacle scinde un intervalle
    en deux, on génère deux intervalles.

    Retourne la liste des intervalles libres triés par x croissant. Liste
    vide = ligne entièrement occupée → sauter cette bande.
    """
    free = [(box_x_pt, box_x_pt + box_w_pt)]
    ligne_y2 = ligne_y_pt + ligne_h_pt

    for obs in obstacles_pt:
        kind = (obs.get("type") or "rectangle").lower()
        pad = float(obs.get("padding_mm", 2)) * 2.835

        if kind in ("rectangle", "rect", "image"):
            ox = float(obs.get("x_pt", 0)) - pad
            oy = float(obs.get("y_pt", 0)) - pad
            ow = float(obs.get("w_pt", 0)) + 2 * pad
            oh = float(obs.get("h_pt", 0)) + 2 * pad
            # L'obstacle intersecte-t-il la bande de ligne en Y ?
            if oy >= ligne_y2 or oy + oh <= ligne_y_pt:
                continue
            ox1, ox2 = ox, ox + ow
        elif kind in ("cercle", "circle"):
            cx = float(obs.get("cx_pt", 0))
            cy = float(obs.get("cy_pt", 0))
            r = float(obs.get("r_pt", 0)) + pad
            # Demi-largeur du cercle au niveau de la bande ligne
            # Au milieu de la ligne pour simplifier
            mid_y = (ligne_y_pt + ligne_y2) / 2
            dy = abs(mid_y - cy)
            if dy >= r:
                continue
            import math as _m
            half_w = _m.sqrt(r * r - dy * dy)
            ox1, ox2 = cx - half_w, cx + half_w
        elif kind in ("polygone", "polygon"):
            # Bounding box du polygone à la hauteur de la ligne
            pts = obs.get("points_pt") or []
            if not pts:
                continue
            # Pour chaque arête, trouver intersections avec la ligne médiane
            mid_y = (ligne_y_pt + ligne_y2) / 2
            xs_intersect = []
            for i in range(len(pts)):
                p1 = pts[i]
                p2 = pts[(i + 1) % len(pts)]
                y1, y2 = float(p1[1]), float(p2[1])
                if (y1 <= mid_y < y2) or (y2 <= mid_y < y1):
                    x1, x2 = float(p1[0]), float(p2[0])
                    if y2 != y1:
                        t = (mid_y - y1) / (y2 - y1)
                        xs_intersect.append(x1 + t * (x2 - x1))
            if len(xs_intersect) < 2:
                continue
            xs_intersect.sort()
            ox1 = min(xs_intersect) - pad
            ox2 = max(xs_intersect) + pad
        else:
            continue

        # Soustrait l'intervalle [ox1, ox2] des intervalles libres
        new_free = []
        for (fa, fb) in free:
            if ox2 <= fa or ox1 >= fb:
                # pas de chevauchement
                new_free.append((fa, fb))
                continue
            if ox1 > fa:
                new_free.append((fa, ox1))
            if ox2 < fb:
                new_free.append((ox2, fb))
        free = new_free

    # Filtre intervalles trop étroits (< 12pt = inutilisable pour mots)
    return [(a, b) for (a, b) in free if (b - a) >= 12]


def _draw_texte_fluide(
    c, el: "TexteFluide", off_x: float, off_y: float, fmt_h_pt: float,
) -> None:
    """Rend un texte qui s'écoule autour d'obstacles polygonaux.

    Algorithme ligne par ligne :
      1. Pour chaque ligne y, calcule les intervalles libres de x via
         _intervalles_libres_sur_ligne (en évitant les obstacles avec padding).
      2. Pour chaque intervalle libre, remplit avec autant de mots que possible
         (word-wrap classique sur cet intervalle).
      3. Si la ligne est entièrement obstruée, saute à la ligne suivante.
      4. Arrête quand le texte est épuisé ou la bbox du conteneur dépassée.

    Coords mm → pt en interne. ReportLab origine bas-gauche, on flippe Y.
    """
    box_x = off_x + mm_to_pt(el.x_mm)
    box_w_pt = mm_to_pt(el.w_mm) if el.w_mm else 100 * 2.835
    box_h_pt = mm_to_pt(el.h_mm) if el.h_mm else 100 * 2.835
    # En coords ReportLab : box_y_bas en bas du conteneur, box_y_haut en haut
    box_y_haut = off_y + fmt_h_pt - mm_to_pt(el.y_mm)
    box_y_bas = box_y_haut - box_h_pt

    # Police + style
    font_name = el.police or "Helvetica"
    if el.bold and "Bold" not in font_name:
        font_name = f"{font_name}-Bold" if font_name in ("Helvetica", "Times", "Courier", "Inter") else font_name
    size = el.taille_pt or 10
    leading = size * (el.interligne or 1.4)
    try:
        c.setFont(font_name, size)
    except Exception:
        c.setFont("Helvetica", size)
        font_name = "Helvetica"
    c.setFillColor(parse_color(el.couleur, default=(0, 0, 0)))

    # Pré-conversion des obstacles en coords pt (origin bas-gauche)
    # Obstacles données en mm avec origine haut-gauche → conversion
    obstacles_pt: list[dict] = []
    for obs in (el.obstacles or []):
        if not isinstance(obs, dict):
            continue
        kind = (obs.get("type") or "rectangle").lower()
        if kind in ("rectangle", "rect", "image"):
            obstacles_pt.append({
                "type": "rectangle",
                "x_pt": off_x + mm_to_pt(float(obs.get("x_mm", 0))),
                # y_mm origine haut → y_pt = top_page - y_mm - h_mm
                "y_pt": off_y + fmt_h_pt - mm_to_pt(
                    float(obs.get("y_mm", 0)) + float(obs.get("h_mm", 0))
                ),
                "w_pt": mm_to_pt(float(obs.get("w_mm", 0))),
                "h_pt": mm_to_pt(float(obs.get("h_mm", 0))),
                "padding_mm": float(obs.get("padding_mm", 2)),
            })
        elif kind in ("cercle", "circle"):
            obstacles_pt.append({
                "type": "cercle",
                "cx_pt": off_x + mm_to_pt(float(obs.get("cx_mm", 0))),
                "cy_pt": off_y + fmt_h_pt - mm_to_pt(float(obs.get("cy_mm", 0))),
                "r_pt": mm_to_pt(float(obs.get("r_mm", 0))),
                "padding_mm": float(obs.get("padding_mm", 2)),
            })
        elif kind in ("polygone", "polygon"):
            pts_mm = obs.get("points_mm") or []
            pts_pt = [
                [
                    off_x + mm_to_pt(float(p[0])),
                    off_y + fmt_h_pt - mm_to_pt(float(p[1])),
                ]
                for p in pts_mm if isinstance(p, (list, tuple)) and len(p) >= 2
            ]
            obstacles_pt.append({
                "type": "polygone",
                "points_pt": pts_pt,
                "padding_mm": float(obs.get("padding_mm", 2)),
            })

    # Tokenisation du texte. Préserve les sauts de ligne explicites (\n)
    # comme « paragraphes ». À l'intérieur, mots séparés par espaces.
    paragraphes = (el.contenu or "").split("\n")

    cursor_y = box_y_haut - size  # baseline de la 1ère ligne
    max_iter = 500  # garde-fou
    iter_count = 0

    for paragraphe in paragraphes:
        if cursor_y < box_y_bas:
            break
        mots = paragraphe.split(" ") if paragraphe else [""]
        # Index du prochain mot à placer
        i_mot = 0
        while i_mot < len(mots) and cursor_y >= box_y_bas and iter_count < max_iter:
            iter_count += 1
            ligne_top = cursor_y + size * 0.2  # leeway au-dessus de la baseline
            ligne_bot = cursor_y - size * 0.1
            intervalles = _intervalles_libres_sur_ligne(
                box_x, box_w_pt, ligne_bot, ligne_top - ligne_bot, obstacles_pt,
            )
            if not intervalles:
                # Ligne entièrement obstruée, saute
                cursor_y -= leading
                continue

            # Remplit chaque intervalle avec autant de mots que possible
            placed_words_in_line = False
            for (xa, xb) in intervalles:
                avail_w = xb - xa
                line_mots: list[str] = []
                cur_w = 0.0
                # Pré-positionne le 1er mot quitte à déborder si trop long
                while i_mot < len(mots):
                    mot = mots[i_mot]
                    w_with_space = c.stringWidth(
                        mot + (" " if line_mots else ""), font_name, size,
                    )
                    if cur_w + w_with_space > avail_w:
                        if not line_mots:
                            # Mot seul plus large que l'intervalle : casse rude
                            line_mots.append(mot[:max(1, int(avail_w / (size * 0.55)))])
                            i_mot += 1
                        break
                    line_mots.append(mot)
                    cur_w += w_with_space
                    i_mot += 1
                if line_mots:
                    placed_words_in_line = True
                    ligne_text = " ".join(line_mots)
                    if el.alignement == "right":
                        x_draw = xb - c.stringWidth(ligne_text, font_name, size)
                    elif el.alignement == "justify" and len(line_mots) > 1 and i_mot < len(mots):
                        # Justification : étire les espaces pour remplir [xa, xb]
                        text_w = c.stringWidth(ligne_text, font_name, size)
                        extra = (avail_w - text_w) / (len(line_mots) - 1)
                        x_draw = xa
                        for j, m in enumerate(line_mots):
                            c.drawString(x_draw, cursor_y, m)
                            x_draw += c.stringWidth(m, font_name, size) + (
                                c.stringWidth(" ", font_name, size) + extra
                            )
                        continue  # déjà dessiné
                    else:
                        x_draw = xa
                    c.drawString(x_draw, cursor_y, ligne_text)

            if not placed_words_in_line:
                # Pas de mot placé sur cette ligne mais intervalles libres
                # (probablement mot trop long pour tous) → on saute pour éviter
                # boucle infinie
                break
            cursor_y -= leading

        # Saut de paragraphe : leading supplémentaire entre paragraphes
        cursor_y -= leading * 0.3


def _wrap_text(c, texte: str, font: str, size: float, max_width_pt: Optional[float]) -> list[str]:
    """Word wrap simple basé sur stringWidth."""
    if not texte:
        return []
    if not max_width_pt or max_width_pt <= 0:
        return texte.split("\n")
    out: list[str] = []
    for paragraphe in texte.split("\n"):
        mots = paragraphe.split(" ")
        cur = ""
        for mot in mots:
            essai = (cur + " " + mot).strip()
            try:
                w = c.stringWidth(essai, font, size)
            except Exception:
                w = len(essai) * size * 0.55
            if w > max_width_pt and cur:
                out.append(cur)
                cur = mot
            else:
                cur = essai
        if cur:
            out.append(cur)
    return out


def _resoudre_image(el: Image, medias: Optional[dict]) -> Optional[bytes]:
    """Récupère les bytes de l'image depuis ref_media, data_url ou url."""
    import base64 as _b64
    if el.data_url:
        try:
            head, b64 = el.data_url.split(",", 1)
            return _b64.b64decode(b64)
        except Exception:
            pass
    if el.ref_media and medias:
        med = medias.get(el.ref_media)
        if med:
            try:
                from . import mediatheque_session as _msm
                return _msm.lire_bytes(med)
            except Exception:
                if hasattr(med, "bytes"):
                    return med.bytes
    if el.url:
        try:
            import httpx
            # timeout court : si le LLM met une URL invalide/lente, on ne
            # bloque pas le rendu PDF de tout le doc (1 image manquée =
            # placeholder, mais 20 images × 15s = freeze 5 min).
            r = httpx.get(el.url, timeout=3.0)
            r.raise_for_status()
            return r.content
        except Exception as e:
            logger.debug(f"[freeform/Image] URL {el.url[:60]} KO : {e}")
    return None


def _draw_image_filling_page(c, media, total_w_pt: float, total_h_pt: float) -> None:
    from reportlab.lib.utils import ImageReader
    from . import mediatheque_session as _msm
    bts = _msm.lire_bytes(media)
    if not bts:
        return
    ir = ImageReader(io.BytesIO(bts))
    c.drawImage(ir, 0, 0, total_w_pt, total_h_pt, mask="auto",
                 preserveAspectRatio=False)


def _draw_ornement(c, el: Ornement, off_x: float, off_y: float, fmt_h_pt: float) -> None:
    """Motifs décoratifs vectoriels simples (extensible)."""
    from math import sin, pi
    x = off_x + mm_to_pt(el.x_mm)
    y_bottom = off_y + fmt_h_pt - mm_to_pt(el.y_mm + el.h_mm)
    w = mm_to_pt(el.w_mm)
    h = mm_to_pt(el.h_mm)
    c.setStrokeColor(parse_color(el.couleur, default=(0, 0, 0)))
    c.setLineWidth(el.epaisseur_pt or 1.0)

    motif = (el.motif or "ligne").lower()
    if motif == "ligne":
        # Trait horizontal au centre vertical
        c.line(x, y_bottom + h / 2, x + w, y_bottom + h / 2)
    elif motif == "vague":
        # Sinusoïde
        steps = max(20, int(w / 2))
        path = c.beginPath()
        for i in range(steps + 1):
            t = i / steps
            px = x + t * w
            py = y_bottom + h / 2 + (h / 4) * sin(t * 4 * pi)
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        c.drawPath(path, stroke=1, fill=0)
    elif motif == "geometrique":
        # 3 cercles alignés
        r = h / 4
        for i, t in enumerate([0.2, 0.5, 0.8]):
            c.circle(x + t * w, y_bottom + h / 2, r, stroke=1, fill=0)
    elif motif == "etoile":
        from math import cos
        cx, cy = x + w / 2, y_bottom + h / 2
        r = min(w, h) / 2
        path = c.beginPath()
        for i in range(11):
            ang = -pi / 2 + i * pi / 5
            rr = r if i % 2 == 0 else r / 2.4
            px = cx + rr * cos(ang)
            py = cy + rr * sin(ang)
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        path.close()
        c.drawPath(path, stroke=1, fill=0)
    elif motif == "feuilles":
        # Petits arcs en chaîne
        n = max(3, int(w / 8))
        seg = w / n
        for i in range(n):
            ax = x + i * seg
            c.bezier(ax, y_bottom + h / 2,
                     ax + seg / 3, y_bottom + h,
                     ax + 2 * seg / 3, y_bottom + h,
                     ax + seg, y_bottom + h / 2)
    else:
        # Défaut : ligne simple
        c.line(x, y_bottom + h / 2, x + w, y_bottom + h / 2)


def _draw_icone(c, el: Icone, off_x: float, off_y: float, fmt_h_pt: float) -> None:
    """Embed l'icône Iconify en VECTORIEL dans le PDF via svglib.

    Pipeline : SVG Iconify → svglib.Drawing → renderPDF.draw() — qualité
    infinie à toute résolution d'impression (300/600/1200 DPI). Pas de
    rasterization, le SVG est intégré comme path vectoriel dans le PDF.

    Fallback transparent en cercle gris si Iconify échoue ou si svglib
    n'arrive pas à parser le SVG (rare).
    """
    x = off_x + mm_to_pt(el.x_mm)
    y = off_y + fmt_h_pt - mm_to_pt(el.y_mm + el.h_mm)
    w = mm_to_pt(el.w_mm)
    h = mm_to_pt(el.h_mm)
    couleur = el.couleur if el.couleur and el.couleur != "currentColor" else "#000000"

    svg_bytes = _telecharger_icone_iconify(el.prefix, el.name, couleur)
    if not svg_bytes:
        c.setFillColorRGB(0.85, 0.85, 0.85)
        c.circle(x + w / 2, y + h / 2, min(w, h) / 2, stroke=0, fill=1)
        return

    try:
        from reportlab.graphics import renderPDF
        from svglib.svglib import svg2rlg  # type: ignore
        from io import BytesIO
        # Parse SVG -> Drawing à chaque appel (5-10ms, OK pour ~120 icônes).
        # On évite ainsi deepcopy(Drawing) qui peut récursivement boucler sur
        # des structures complexes (fonts, paths imbriqués), source du
        # hang prod observé en v327.
        d = svg2rlg(BytesIO(svg_bytes))
        if d is None:
            raise RuntimeError("svg2rlg returned None")
        src_w = d.width or 24.0
        src_h = d.height or 24.0
        d.scale(w / src_w, h / src_h)
        d.width = w
        d.height = h
        renderPDF.draw(d, c, x, y, showBoundary=0)
    except Exception as e:
        logger.debug(f"[freeform/icone] Render {el.prefix}:{el.name} : {e}")
        c.setFillColorRGB(0.85, 0.85, 0.85)
        c.circle(x + w / 2, y + h / 2, min(w, h) / 2, stroke=0, fill=1)


# Cache d'octets SVG (déjà couleur-substitués, prêts pour svg2rlg).
# Beaucoup plus simple/sûr que cacher des Drawing reportlab (qui ne se
# deepcopy pas fiablement). ~300 octets/SVG × N icônes ≈ négligeable.
_ICONIFY_CACHE: dict[str, bytes] = {}

_ICONIFY_DISABLED = os.environ.get("YUKPO_ICONIFY_DISABLED", "0") == "1"


def _telecharger_icone_iconify(prefix: str, name: str, couleur_hex: str) -> Optional[bytes]:
    """Télécharge l'icône SVG depuis api.iconify.design avec substitution
    couleur côté Python (currentColor -> #rrggbb). Cache mémoire par
    (prefix, name, couleur) — un seul HTTP par triplet, partagé entre
    toutes les cartes du même rendu.

    Iconify renvoie color sans # quand on passe ?color=xxx (invalide pour
    svglib strict), donc on télécharge avec currentColor et on substitue
    nous-mêmes — robuste.

    Retourne les bytes SVG prêts à parser, ou None si Iconify échoue
    (caller dessine alors un cercle gris).
    """
    if _ICONIFY_DISABLED:
        return None
    cle = f"{prefix}:{name}:{couleur_hex}"
    cached = _ICONIFY_CACHE.get(cle)
    if cached is not None:
        return cached or None  # b"" -> None
    try:
        import httpx
        url = f"https://api.iconify.design/{prefix}/{name}.svg"
        r = httpx.get(url, timeout=4.0)
        if r.status_code != 200 or not r.content:
            _ICONIFY_CACHE[cle] = b""
            return None
        couleur_css = couleur_hex if couleur_hex.startswith("#") else f"#{couleur_hex}"
        svg_str = r.text.replace("currentColor", couleur_css)
        svg_bytes = svg_str.encode("utf-8")
        _ICONIFY_CACHE[cle] = svg_bytes
        return svg_bytes
    except Exception as e:
        logger.debug(f"[Iconify] {prefix}:{name} : {e}")
        _ICONIFY_CACHE[cle] = b""
    return None


def _draw_crop_marks(c, el: CropMarks, off_x: float, off_y: float, fmt_h_pt: float) -> None:
    """Repères de coupe imprimerie autour de la zone (x, y, w, h)."""
    x = off_x + mm_to_pt(el.x_mm)
    y = off_y + fmt_h_pt - mm_to_pt(el.y_mm + el.h_mm)
    w = mm_to_pt(el.w_mm)
    h = mm_to_pt(el.h_mm)
    L = mm_to_pt(el.longueur_mm or 3)
    D = mm_to_pt(el.decalage_mm or 1)
    c.setStrokeColor(parse_color(el.couleur, default=(0, 0, 0)))
    c.setLineWidth(el.epaisseur_pt or 0.25)
    # 4 coins, traits horizontaux + verticaux
    # Coin haut-gauche
    c.line(x - D - L, y + h, x - D, y + h)
    c.line(x, y + h + D, x, y + h + D + L)
    # Coin haut-droit
    c.line(x + w + D, y + h, x + w + D + L, y + h)
    c.line(x + w, y + h + D, x + w, y + h + D + L)
    # Coin bas-gauche
    c.line(x - D - L, y, x - D, y)
    c.line(x, y - D, x, y - D - L)
    # Coin bas-droit
    c.line(x + w + D, y, x + w + D + L, y)
    c.line(x + w, y - D, x + w, y - D - L)


# ─── Helper public ──────────────────────────────────────────────────────────


async def rendre_pdf_depuis_json(
    layout_json: dict, medias: Optional[dict] = None,
    imposer_livret: bool = True,
) -> bytes:
    """API publique async : prend un JSON de layout (produit par LLM) et
    retourne un PDF bytes prêt à servir. Étapes :
    1. (NEW) Imposition saddle-stitched si livret (≥4p, format A5/A6/A4/carré)
    2. Parse JSON → LayoutDocument
    3. Pré-génère les images IA (Flux Pro Ultra) en parallèle pour les
       éléments avec prompt_ia non vide
    4. Rasterise via ReportLab (sync)
    5. Post-traite PDF/X-1a (pikepdf : TrimBox/BleedBox + ICC FOGRA39)

    Si imposer_livret=False, on ne réordonne pas les pages (utile pour
    aperçu pur logique, exports « pages séparées »).
    """
    import asyncio

    # ── Étape 1 : Imposition livret saddle-stitched ──────────────────────
    if imposer_livret:
        try:
            from . import imposition_livret as _imp
            if _imp.doit_imposer(layout_json):
                nb_pages_avant = len(layout_json.get("pages") or [])
                layout_json = _imp.imposer_layout_saddle_stitched(layout_json)
                nb_feuilles_apres = len(layout_json.get("pages") or [])
                logger.warning(
                    f"[freeform/imposition] Saddle-stitched appliquée : "
                    f"{nb_pages_avant} pages logiques → {nb_feuilles_apres} "
                    f"faces imposées (feuilles physiques duplex)"
                )
        except Exception as e_imp:
            logger.warning(f"[freeform/imposition] Skip (erreur non-fatale) : {e_imp}")

    doc = parse_layout_json(layout_json)
    logger.warning(f"[freeform/render] parse OK — {len(doc.pages)} pages, "
                   f"{sum(len(p.elements) for p in doc.pages)} elements totaux")
    await pre_generer_images_ia(doc)

    # ── Pipeline async chunked pour livrets très volumineux ────────────────
    # Au-delà du seuil (32 pages par défaut), le timeout 600s Fly devient un
    # risque réel. On découpe en sous-renders de N pages, rendues chacune en
    # PDF indépendant, puis on fusionne via pikepdf. Chaque sous-render passe
    # par le semaphore donc l'ordre serial reste garanti — la seule différence
    # est qu'entre 2 chunks, le canvas est réinitialisé (GC mémoire) ce qui
    # évite le pic OOM observé sur 64+ pages denses.
    _CHUNK_THRESHOLD = int(os.getenv("FREEFORM_CHUNK_THRESHOLD", "32"))
    _CHUNK_SIZE = int(os.getenv("FREEFORM_CHUNK_SIZE", "16"))
    if len(doc.pages) > _CHUNK_THRESHOLD:
        logger.warning(
            f"[freeform/render] {len(doc.pages)} pages > {_CHUNK_THRESHOLD} → "
            f"mode chunked ({_CHUNK_SIZE} pages/chunk)"
        )
        return await _rendre_layout_pdf_chunked(doc, medias, _CHUNK_SIZE)

    # ── Semaphore configurable au lieu de Lock fixe ────────────────────────
    # `FREEFORM_RENDER_CONCURRENCY` env (1 par défaut sur shared-cpu-1x, à
    # passer à 2-3 sur performance-2x/4x). Sur shared-cpu-1x → 1 = comportement
    # historique (sérialisation totale). Sur performance-4x → 3 = throughput
    # ×3 quand plusieurs users génèrent en parallèle, sans contention puisque
    # 4 vCPU dédiés absorbent.
    sem = _get_render_sem()
    waiting = sem._value <= 0 if hasattr(sem, "_value") else False
    if waiting:
        logger.warning("[freeform/render] en attente du semaphore (autres renders en cours)")
    async with sem:
        logger.warning("[freeform/render] début rasterization ReportLab")
        pdf_bytes = await asyncio.to_thread(rendre_layout_pdf, doc, medias=medias)
        logger.warning(f"[freeform/render] rasterization OK — {len(pdf_bytes)} bytes")
        try:
            from . import pdf_print_ready as _pp
            pdf_bytes = await asyncio.to_thread(
                _pp.convertir_en_pdf_x1a, pdf_bytes, doc.titre,
                (doc.format_mm[0], doc.format_mm[1]), doc.bleed_mm,
            )
            logger.warning("[freeform/render] PDF/X-1a OK")
        except Exception as e:
            logger.debug(f"[freeform] PDF/X-1a skip : {e}")
    return pdf_bytes


async def _rendre_layout_pdf_chunked(
    doc: "LayoutDocument", medias: Optional[dict], chunk_size: int,
) -> bytes:
    """Découpe un LayoutDocument en chunks de N pages, rend chacun
    indépendamment puis fusionne en un PDF unique via pikepdf.

    Avantages :
      - Chaque chunk a son propre Canvas ReportLab → mémoire bornée (pas de
        balloning à 64+ pages denses)
      - Si timeout pendant un chunk, on a déjà sauvegardé les précédents
        (extension future : reprise sur échec)
      - PDF/X-1a est appliqué SUR LE PDF FINAL fusionné, pas sur chaque chunk
        (économise N×pikepdf, gain ~5s × N)
    """
    import copy
    chunks: list[bytes] = []
    sem = _get_render_sem()
    pages_total = len(doc.pages)
    for i in range(0, pages_total, chunk_size):
        sub_doc = copy.copy(doc)
        sub_doc.pages = doc.pages[i:i + chunk_size]
        idx_end = min(i + chunk_size, pages_total)
        logger.warning(f"[freeform/chunked] chunk {i + 1}-{idx_end}/{pages_total}")
        async with sem:
            chunk_pdf = await asyncio.to_thread(
                rendre_layout_pdf, sub_doc, medias=medias,
            )
            chunks.append(chunk_pdf)

    # Fusion pikepdf
    try:
        import pikepdf
        from io import BytesIO as _BIO
        merged = pikepdf.Pdf.new()
        for c_pdf in chunks:
            with pikepdf.Pdf.open(_BIO(c_pdf)) as p:
                merged.pages.extend(p.pages)
        out_buf = _BIO()
        merged.save(out_buf)
        pdf_bytes = out_buf.getvalue()
        logger.warning(f"[freeform/chunked] fusion OK : {len(chunks)} chunks → {len(pdf_bytes)} bytes")
    except Exception as e:
        logger.error(f"[freeform/chunked] fusion KO ({e}) → renvoi 1er chunk seulement")
        pdf_bytes = chunks[0] if chunks else b""

    # PDF/X-1a sur le PDF final fusionné
    try:
        from . import pdf_print_ready as _pp
        pdf_bytes = await asyncio.to_thread(
            _pp.convertir_en_pdf_x1a, pdf_bytes, doc.titre,
            (doc.format_mm[0], doc.format_mm[1]), doc.bleed_mm,
        )
    except Exception as e:
        logger.debug(f"[freeform/chunked] PDF/X-1a skip : {e}")
    return pdf_bytes


# Sémaphore asyncio process-wide configurable via FREEFORM_RENDER_CONCURRENCY.
# Lazy-init car asyncio.Semaphore() exige une event loop courante.
_RENDER_SEM: Optional[Any] = None


def _get_render_sem():
    import asyncio
    global _RENDER_SEM
    if _RENDER_SEM is None:
        n = max(1, int(os.getenv("FREEFORM_RENDER_CONCURRENCY", "1")))
        _RENDER_SEM = asyncio.Semaphore(n)
        logger.info(f"[freeform] Render semaphore initialisé à N={n}")
    return _RENDER_SEM


# Backward-compat : si du code externe importe _get_render_lock, on lui rend
# le semaphore qui se comporte comme un Lock quand N=1.
def _get_render_lock():
    return _get_render_sem()
