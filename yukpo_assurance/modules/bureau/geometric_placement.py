"""
Geometric Placement — Designer Pro NEXT-GEN.

Pipeline "vision LLM + math Python" pour placement parfait de textes et
images sur un visuel, comme le ferait un graphiste expérimenté à l'œil.

Architecture :

  ┌────────────────────────────────────────────────────────────┐
  │  Phase 1 : LLM (vision sémantique + géométrique)           │
  │                                                            │
  │  Input :  brief, page (W×H mm + bleed), médias uploadés    │
  │           (dim, ratio, contenu sémantique tagué)           │
  │  Output : PlacementPlan JSON                               │
  │   - Pour chaque texte : bbox exacte (x,y,w,h mm), police,  │
  │     taille pt, couleur, alignement, rotation, ombre        │
  │   - Pour chaque image : zone cible (forme géométrique +    │
  │     dimensions), media_ref, fit_mode, crop_box, masque,    │
  │     filtres (recolor, blend, opacity, blur, contraste)     │
  │   - Pour chaque forme décorative : path/cercle/polygon     │
  │     avec couleur, stroke, fill                             │
  └────────────────────────────────────────────────────────────┘
                              ↓
  ┌────────────────────────────────────────────────────────────┐
  │  Phase 2 : Python (math précise + rendu)                   │
  │                                                            │
  │  - Calcul object-fit cover/contain exact                   │
  │  - Masques arbitraires (cercle, ellipse, polygon N côtés,  │
  │    rounded_rect, étoile, hexagone, path custom)            │
  │  - Transforms matriciels (rotation, scale, skew)           │
  │  - Filtres (recolor, blend modes, opacity, blur)           │
  │  - Composite ordonné z-index                               │
  │  - Sortie : PIL Image pleine page OU drawing ReportLab     │
  └────────────────────────────────────────────────────────────┘

Le LLM N'A PAS à calculer la math précise (pixels/pt exacts post-fit) —
il décrit l'INTENTION géométrique ("le portrait du défunt dans un cercle
de 60mm de diamètre centré en haut, focus visage si recadrage nécessaire")
et Python implémente. Le LLM raisonne en COMPRÉHENSION VISUELLE ; Python
exécute en PRÉCISION MÉCANIQUE.

Compatible avec ReportLab (PDF print-ready CMJN + bleed) ET PIL (PNG
preview rapide + masques complexes). Coexiste avec freeform_composer.py
(qui reste le générateur de mise en page rapide non-vision).
"""
from __future__ import annotations

import io
import logging
import math
from typing import Literal, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("yukpo_assurance.bureau.geometric_placement")


# ═══════════════════════════════════════════════════════════════════════
# 1. Énumérations
# ═══════════════════════════════════════════════════════════════════════

MaskShape = Literal[
    "rect",          # rectangle simple
    "rounded_rect",  # rectangle arrondi (radius_mm dans extra)
    "circle",        # cercle inscrit dans la bbox
    "ellipse",       # ellipse inscrite dans la bbox
    "polygon",       # polygon arbitraire (points[] dans extra)
    "hexagon",       # hexagone régulier
    "star",          # étoile N branches (n_points dans extra)
    "diamond",       # losange
    "blob",          # forme organique fluide (n_lobes dans extra)
]

FitMode = Literal[
    "cover",    # remplit la zone, recadre l'image (object-fit:cover CSS)
    "contain",  # affiche entière, marges si ratio diffère (object-fit:contain)
    "fill",     # étire pour remplir (déformation, à éviter sauf demande)
    "crop_box", # recadrage manuel : crop_box=(x,y,w,h) en % de l'image source
    "smart_focus",  # cover + focal_point pour garder le sujet centré
]

BlendMode = Literal[
    "normal", "multiply", "screen", "overlay", "soft_light", "hard_light",
    "darken", "lighten", "color_dodge", "color_burn", "difference",
]

TextAlign = Literal["left", "center", "right", "justify"]
VerticalAlign = Literal["top", "middle", "bottom"]


# ═══════════════════════════════════════════════════════════════════════
# 2. Schémas Pydantic — PlacementPlan
# ═══════════════════════════════════════════════════════════════════════

class Color(BaseModel):
    """Couleur RGB + alpha optionnel. CMJN dérivé automatiquement à l'export."""
    r: int = Field(..., ge=0, le=255)
    g: int = Field(..., ge=0, le=255)
    b: int = Field(..., ge=0, le=255)
    a: float = Field(default=1.0, ge=0.0, le=1.0)

    @classmethod
    def from_hex(cls, hex_str: str, alpha: float = 1.0) -> "Color":
        h = hex_str.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return cls(r=int(h[0:2], 16), g=int(h[2:4], 16), b=int(h[4:6], 16), a=alpha)

    def to_rgba(self) -> tuple[int, int, int, int]:
        return (self.r, self.g, self.b, int(round(self.a * 255)))


class BBox(BaseModel):
    """Bounding box en MILLIMÈTRES (origine top-left de la page, bleed inclus)."""
    x: float = Field(..., description="Distance gauche en mm")
    y: float = Field(..., description="Distance haut en mm")
    w: float = Field(..., gt=0, description="Largeur en mm")
    h: float = Field(..., gt=0, description="Hauteur en mm")


class Transform(BaseModel):
    """Transformations matricielles appliquées après positionnement."""
    rotation_deg: float = Field(default=0.0, ge=-360.0, le=360.0,
        description="Rotation horaire en degrés autour du centre de la bbox")
    scale: float = Field(default=1.0, ge=0.1, le=10.0,
        description="Mise à l'échelle uniforme (1.0 = taille bbox)")
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    blend_mode: BlendMode = "normal"


class Shadow(BaseModel):
    """Ombre portée (texte ou image)."""
    offset_x_mm: float = 0.5
    offset_y_mm: float = 0.5
    blur_mm: float = 0.8
    color: Color = Color(r=0, g=0, b=0, a=0.35)


class TextPlacement(BaseModel):
    """
    Bloc texte positionné géométriquement.

    Le LLM décide : bbox (où), font/size/weight/color (comment), align (interne),
    transform (rotation). Python implémente : line-break automatique, wrap dans
    la bbox, sub-pixel positioning, anti-aliasing.
    """
    kind: Literal["text"] = "text"
    text: str = Field(..., min_length=1, max_length=5000)
    bbox: BBox
    font_family: str = Field(default="Inter",
        description="Inter, Calibri, Playfair Display, Lato, Cormorant, Bebas Neue, etc.")
    font_size_pt: float = Field(..., gt=0, le=300)
    font_weight: Literal[300, 400, 500, 600, 700, 800, 900] = 400
    italic: bool = False
    color: Color
    align: TextAlign = "left"
    vertical_align: VerticalAlign = "top"
    line_height: float = Field(default=1.25, ge=0.8, le=3.0)
    letter_spacing_em: float = Field(default=0.0, ge=-0.1, le=0.5)
    uppercase: bool = False
    underline: bool = False
    transform: Transform = Transform()
    shadow: Optional[Shadow] = None
    # Couleur de fond du bloc (callout, badge, etc.)
    background: Optional[Color] = None
    background_radius_mm: float = Field(default=0.0, ge=0.0, le=20.0)
    background_padding_mm: float = Field(default=0.0, ge=0.0, le=20.0)
    z_index: int = Field(default=10)


class ImagePlacement(BaseModel):
    """
    Image positionnée et adaptée géométriquement à sa zone cible.

    L'image peut être :
      • UPLOADÉE par l'user (media_ref pointe sur la médiathèque session/compte)
      • GÉNÉRÉE AUTO IA (prompt_ia → Flux Pro Ultra / Recraft v3 / Ideogram 2
        à la volée si aucun media_ref fourni). Permet au LLM de placer des
        photos produits, scènes terrain, illustrations métier sans que l'user
        ait à les uploader. Essentiel pour visuels marketing où une photo
        cinématique pertinente est nécessaire.

    Le LLM décide :
      - target_zone (où, forme, dimensions)
      - fit_mode (comment l'image s'adapte au container)
      - focal_point (point d'ancrage si smart_focus)
      - mask_shape (silhouette finale)
      - filters (recolor, opacity, blur, contraste)
      - prompt_ia (si pas de media_ref) : description anglaise 30-60 mots
        ("Smartphone displaying mobile banking app, hand holding device,
        modern office background, professional lighting, photorealistic")
    """
    kind: Literal["image"] = "image"
    media_ref: Optional[str] = Field(default=None,
        description="Référence média uploadé. Si None, utilise prompt_ia pour génération auto.")
    prompt_ia: Optional[str] = Field(default=None, max_length=1000,
        description="Prompt EN 30-60 mots pour Flux/Recraft/Ideogram si media_ref absent")
    mode_ia: Literal["standard", "premium", "ultra", "ultra_plus"] = Field(
        default="premium",
        description="Qualité génération IA : standard=Flux schnell rapide, "
                    "premium=Flux dev (défaut), ultra=Flux Pro Ultra cinéma, "
                    "ultra_plus=ensemble Flux+Recraft+Ideogram avec vision picker")
    target_zone: BBox
    fit_mode: FitMode = "cover"
    # Pour smart_focus : point d'ancrage en % de l'image source (0..1, 0=top-left)
    focal_point_x: float = Field(default=0.5, ge=0.0, le=1.0)
    focal_point_y: float = Field(default=0.5, ge=0.0, le=1.0)
    # Pour crop_box : zone à recadrer en % de l'image source
    crop_box_x: float = Field(default=0.0, ge=0.0, le=1.0)
    crop_box_y: float = Field(default=0.0, ge=0.0, le=1.0)
    crop_box_w: float = Field(default=1.0, ge=0.01, le=1.0)
    crop_box_h: float = Field(default=1.0, ge=0.01, le=1.0)
    # Forme finale du clip (silhouette)
    mask_shape: MaskShape = "rect"
    mask_extra: dict = Field(default_factory=dict,
        description="Params dépendant du masque : radius_mm (rounded_rect), "
                    "points=[(x%,y%),...] (polygon), n_points (star), "
                    "n_lobes (blob), inner_radius_ratio (star)")
    border_mm: float = Field(default=0.0, ge=0.0, le=10.0)
    border_color: Optional[Color] = None
    # Filtres image
    recolor_to: Optional[Color] = Field(default=None,
        description="Monochrome teinté (préserve la luminance, applique la teinte)")
    grayscale: bool = False
    blur_radius_mm: float = Field(default=0.0, ge=0.0, le=20.0)
    brightness: float = Field(default=1.0, ge=0.1, le=3.0)
    contrast: float = Field(default=1.0, ge=0.1, le=3.0)
    transform: Transform = Transform()
    shadow: Optional[Shadow] = None
    z_index: int = Field(default=5)


class ShapePlacement(BaseModel):
    """
    Forme décorative géométrique (lignes, cercles, rectangles, polygons).
    Utile pour : filets, séparateurs, badges, accents corporate, motifs.
    """
    kind: Literal["shape"] = "shape"
    shape: MaskShape
    bbox: BBox
    fill: Optional[Color] = None
    stroke: Optional[Color] = None
    stroke_width_mm: float = Field(default=0.3, ge=0.0, le=10.0)
    shape_extra: dict = Field(default_factory=dict)
    transform: Transform = Transform()
    z_index: int = Field(default=1)


# ─── Primitives MARKETING NATIVES (visuels haute qualité direction marketing) ─

ChartType = Literal["bar", "column", "pie", "donut", "line", "area"]


class ChartPlacement(BaseModel):
    """
    Chart NATIF (bar / column / pie / donut / line / area) rendu vectoriel
    via PIL — pas une image plate générée par IA. Essentiel pour visuels
    marketing data-driven (rapport ROI, KPI campagne, comparaison perf,
    funnel conversion, étude marché).

    Le LLM fournit les données (labels + values + colors) ; Python rend en
    pur géométrique pour qualité parfaite à toute échelle.
    """
    kind: Literal["chart"] = "chart"
    chart_type: ChartType = "bar"
    bbox: BBox
    title: Optional[str] = Field(default=None, max_length=120)
    labels: list[str] = Field(..., min_length=1, max_length=20)
    values: list[float] = Field(..., min_length=1, max_length=20)
    colors: Optional[list[Color]] = Field(default=None,
        description="1 couleur par série, sinon palette brand auto")
    show_values: bool = Field(default=True,
        description="Affiche les valeurs sur les barres / parts de pie")
    show_legend: bool = Field(default=True)
    unit: str = Field(default="", max_length=10,
        description="Suffixe affiché après les valeurs (%, FCFA, M, K, x, …)")
    grid: bool = Field(default=False,
        description="Grille horizontale pour bar/column/line")
    transform: Transform = Transform()
    z_index: int = Field(default=4)


class MockupPlacement(BaseModel):
    """
    Mockup container marketing : smartphone / laptop / tablet / billboard
    / poster_frame / business_card_holder. Le rendu dessine le device
    en vectoriel et y embed l'image cible (capture d'app, photo produit,
    visuel ad). Essentiel pour présentations campagne, landing page mockups,
    catalogues produits.
    """
    kind: Literal["mockup"] = "mockup"
    device: Literal[
        "smartphone", "smartphone_landscape", "tablet", "laptop", "monitor",
        "billboard", "poster_frame", "instagram_post_phone",
        "business_card_holder", "tshirt", "tote_bag", "mug", "tv_screen",
    ] = "smartphone"
    bbox: BBox
    inner_image_media_ref: Optional[str] = Field(default=None,
        description="Image à embed dans le device (ex: 'session:capture_app')")
    inner_image_b64: Optional[str] = Field(default=None,
        description="Alternative : data URI base64 PNG/JPG")
    device_color: Color = Color(r=20, g=20, b=20, a=1.0)
    transform: Transform = Transform()
    shadow: Optional[Shadow] = None
    z_index: int = Field(default=5)


class GradientMeshPlacement(BaseModel):
    """
    Gradient mesh cinématique (style background marketing premium :
    Linear Cards, Stripe, Apple keynote). Effet bokeh/auroral via N blobs
    de couleur soft-blurés. Idéal full-bleed backgrounds, hero sections,
    posters tendance 2025-2026.
    """
    kind: Literal["gradient_mesh"] = "gradient_mesh"
    bbox: BBox
    blobs: list[dict] = Field(..., min_length=2, max_length=8,
        description="[{x:0..1, y:0..1, radius:0..1, color:Color}, ...] positions en %")
    blur_mm: float = Field(default=15.0, ge=0.0, le=50.0)
    base_color: Color = Color(r=240, g=240, b=245, a=1.0)
    transform: Transform = Transform()
    z_index: int = Field(default=0)


class PageBackground(BaseModel):
    """Fond de page (couleur unie, gradient, ou image full-bleed)."""
    color: Optional[Color] = None
    gradient: Optional[dict] = Field(default=None,
        description="{type:'linear|radial', angle_deg, stops:[{pos:0..1,color:Color},...]}")
    image_media_ref: Optional[str] = None
    image_fit: FitMode = "cover"
    image_opacity: float = Field(default=1.0, ge=0.0, le=1.0)


class TypographyToken(BaseModel):
    """Définition d'un niveau typographique (Display, H1, H2, …)."""
    nom: str = Field(..., description="display | h1 | h2 | h3 | body | caption | overline")
    font_size_pt: float = Field(..., gt=0)
    font_weight: int = Field(..., ge=100, le=900)
    line_height: float = Field(default=1.3, ge=0.8, le=3.0)
    letter_spacing_em: float = Field(default=0.0, ge=-0.15, le=0.5)
    uppercase: bool = Field(default=False)


class DesignTokens(BaseModel):
    """
    Système de design pré-calculé pour UN visuel.

    Produit par une phase LLM PRÉLIMINAIRE qui analyse le brief, la page,
    les médias et la marque AVANT le placement des éléments. Ces tokens
    sont ensuite injectés en INPUT du LLM de placement → cohérence garantie
    + pas de recomputation à chaque texte.

    Architecture : Phase 0 (tokens) → Phase 1 (placement) → Phase 2 (render).
    """
    # Palette
    palette: list[Color] = Field(..., min_length=2, max_length=6,
        description="2-6 couleurs cohérentes pour le visuel (ordre : "
                    "primaire, accent, fond, texte_principal, texte_secondaire…)")
    couleur_fond: Color
    couleur_texte_principal: Color
    couleur_accent: Color
    # Typographie
    font_family_titre: str = Field(..., description="Famille pour titres/sous-titres")
    font_family_corps: str = Field(..., description="Famille pour corps de texte")
    typo_scale: list[TypographyToken] = Field(..., min_length=3,
        description="Échelle typo calculée selon la diagonale de la page (display, h1, h2, h3, body, caption, overline). Tu décides quels niveaux sont utiles selon le format de page : carte de visite n'a pas de display, affiche A0 a un display géant.")
    # Style global
    registre: str = Field(...,
        description="sobre_corporate | luxe_elegant | deuil_classique | festif_jeune | artistique | tech_startup | institutionnel | minimaliste | dense_informatif")
    densite_visuelle: str = Field(...,
        description="minimaliste | aere | equilibre | dense | sature")
    formes_decoratives_autorisees: list[str] = Field(default_factory=list,
        description="Liste des MaskShape adaptées au registre : ex sobre_corporate→['rect','rounded_rect'], festif→['blob','star','polygon']")
    raisonnement: str = Field(default="", max_length=600,
        description="1-3 phrases expliquant les choix (palette, polices, registre)")


class PlacementPlan(BaseModel):
    """
    Plan de placement complet pour UNE page de visuel.

    C'est la sortie du LLM (phase 1) et l'input du renderer Python (phase 2).
    Tout est en MILLIMÈTRES (compatibles ReportLab + impression).
    """
    page_w_mm: float = Field(..., gt=0, description="Largeur trim de la page")
    page_h_mm: float = Field(..., gt=0, description="Hauteur trim de la page")
    bleed_mm: float = Field(default=3.0, ge=0.0, le=20.0,
        description="Bleed pour impression (le rendu fait page_w + 2×bleed)")
    background: Optional[PageBackground] = None
    items: list = Field(default_factory=list,
        description="Liste mixte de TextPlacement | ImagePlacement | ShapePlacement, ordonnée par z_index")
    debug_grid: bool = Field(default=False,
        description="Si True, dessine une grille fine pour debug visuel des positions")


# ═══════════════════════════════════════════════════════════════════════
# 3. Math helpers (object-fit, transforms, conversions)
# ═══════════════════════════════════════════════════════════════════════

MM_TO_PX_300DPI = 11.811023622  # 300dpi : 1mm = 11.811px


def mm_to_px(mm: float, dpi: int = 300) -> int:
    """Conversion mm → pixels selon DPI cible."""
    return int(round(mm * dpi / 25.4))


def compute_fit_box(
    src_w: int, src_h: int,
    target_w: int, target_h: int,
    mode: FitMode,
    focal_x: float = 0.5, focal_y: float = 0.5,
    crop: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
) -> tuple[tuple[int, int, int, int], tuple[int, int]]:
    """
    Calcule la boîte de recadrage source ET la taille de redimensionnement.

    Returns:
        (src_crop_box, render_size) où :
        - src_crop_box = (left, top, right, bottom) en pixels source
        - render_size  = (w, h) en pixels cible (peut différer du target si contain)
    """
    if mode == "fill":
        # Déforme : prend toute la source, redimensionne au target exact
        return (0, 0, src_w, src_h), (target_w, target_h)

    if mode == "contain":
        # Pas de crop, ajuste pour rentrer entier
        ratio = min(target_w / src_w, target_h / src_h)
        new_w = int(src_w * ratio)
        new_h = int(src_h * ratio)
        return (0, 0, src_w, src_h), (new_w, new_h)

    if mode == "crop_box":
        # Crop explicite défini par l'appelant
        cx, cy, cw, ch = crop
        left = int(cx * src_w)
        top = int(cy * src_h)
        right = int((cx + cw) * src_w)
        bottom = int((cy + ch) * src_h)
        return (left, top, right, bottom), (target_w, target_h)

    # mode == "cover" ou "smart_focus" : recadre pour remplir le target en
    # gardant le ratio source. focal_point ancrage du sujet.
    src_ratio = src_w / src_h
    tgt_ratio = target_w / target_h
    if src_ratio > tgt_ratio:
        # Source plus large que target → on coupe les côtés horizontaux
        new_w = int(src_h * tgt_ratio)
        new_h = src_h
        # Ancrage horizontal : focal_x ∈ [0..1] détermine le centre du crop
        max_left = src_w - new_w
        left = max(0, min(max_left, int(focal_x * src_w - new_w / 2)))
        return (left, 0, left + new_w, new_h), (target_w, target_h)
    else:
        # Source plus haute que target → on coupe le haut/bas
        new_w = src_w
        new_h = int(src_w / tgt_ratio)
        max_top = src_h - new_h
        top = max(0, min(max_top, int(focal_y * src_h - new_h / 2)))
        return (0, top, new_w, top + new_h), (target_w, target_h)


def make_mask(
    w: int, h: int,
    shape: MaskShape,
    extra: dict | None = None,
) -> "Image.Image":
    """
    Génère un masque alpha (PIL "L" mode) de la forme demandée.
    Blanc = visible, noir = transparent.
    """
    from PIL import Image, ImageDraw
    extra = extra or {}
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)

    if shape == "rect":
        d.rectangle([(0, 0), (w, h)], fill=255)
    elif shape == "rounded_rect":
        r = mm_to_px(float(extra.get("radius_mm", 3.0)))
        r = max(1, min(r, min(w, h) // 2))
        d.rounded_rectangle([(0, 0), (w, h)], radius=r, fill=255)
    elif shape == "circle":
        diameter = min(w, h)
        cx, cy = w / 2, h / 2
        d.ellipse([(cx - diameter / 2, cy - diameter / 2),
                   (cx + diameter / 2, cy + diameter / 2)], fill=255)
    elif shape == "ellipse":
        d.ellipse([(0, 0), (w, h)], fill=255)
    elif shape == "polygon":
        pts_pct = extra.get("points", [])
        if not pts_pct or len(pts_pct) < 3:
            d.rectangle([(0, 0), (w, h)], fill=255)
        else:
            pts = [(p[0] * w, p[1] * h) for p in pts_pct]
            d.polygon(pts, fill=255)
    elif shape == "hexagon":
        # Hexagone régulier inscrit dans la bbox
        cx, cy = w / 2, h / 2
        r = min(w, h) / 2
        pts = [
            (cx + r * math.cos(math.radians(60 * i - 30)),
             cy + r * math.sin(math.radians(60 * i - 30)))
            for i in range(6)
        ]
        d.polygon(pts, fill=255)
    elif shape == "star":
        n = int(extra.get("n_points", 5))
        inner = float(extra.get("inner_radius_ratio", 0.4))
        cx, cy = w / 2, h / 2
        r_out = min(w, h) / 2
        r_in = r_out * inner
        pts = []
        for i in range(n * 2):
            r = r_out if i % 2 == 0 else r_in
            angle = math.radians(90 + i * 180 / n)
            pts.append((cx + r * math.cos(angle), cy - r * math.sin(angle)))
        d.polygon(pts, fill=255)
    elif shape == "diamond":
        cx, cy = w / 2, h / 2
        d.polygon([(cx, 0), (w, cy), (cx, h), (0, cy)], fill=255)
    elif shape == "blob":
        # Forme organique : super-ellipse modulée par n_lobes sinusoïdales
        n = int(extra.get("n_lobes", 5))
        amp = float(extra.get("amplitude", 0.15))
        cx, cy = w / 2, h / 2
        r_base = min(w, h) / 2 * 0.95
        pts = []
        for deg in range(0, 360, 4):
            rad = math.radians(deg)
            r = r_base * (1 + amp * math.sin(n * rad))
            pts.append((cx + r * math.cos(rad), cy + r * math.sin(rad)))
        d.polygon(pts, fill=255)
    else:
        d.rectangle([(0, 0), (w, h)], fill=255)
    return mask


def apply_recolor(img: "Image.Image", target: Color) -> "Image.Image":
    """Applique une teinte monochrome préservant la luminance (effet duotone)."""
    from PIL import Image, ImageOps
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    # Extrait luminance
    luma = ImageOps.grayscale(img.convert("RGB"))
    # Mappe luminance → couleur cible (lin interpolation luminance black→target)
    r, g, b = target.r, target.g, target.b
    palette = []
    for i in range(256):
        f = i / 255
        palette.extend([int(r * f), int(g * f), int(b * f)])
    luma.putpalette(palette + [0] * (768 - len(palette)))
    colored = luma.convert("RGB")
    # Réapplique l'alpha original
    result = colored.convert("RGBA")
    alpha = img.split()[3]
    result.putalpha(alpha)
    return result


# ═══════════════════════════════════════════════════════════════════════
# 4. Renderer principal (PIL composite haute fidélité)
# ═══════════════════════════════════════════════════════════════════════

def render_placement_plan(
    plan: PlacementPlan,
    medias: dict[str, bytes],
    dpi: int = 300,
    include_bleed: bool = True,
) -> bytes:
    """
    Rend un PlacementPlan en PNG haute résolution.

    `plan`    : sortie LLM (Phase 1) validée
    `medias`  : dict {media_ref → bytes PNG/JPEG} pour les images uploadées
    `dpi`     : densité (300 = print, 150 = web, 72 = preview rapide)
    `include_bleed` : True pour PDF print, False pour PNG web

    Retourne les bytes PNG du rendu composite.
    """
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

    bleed = plan.bleed_mm if include_bleed else 0.0
    total_w_mm = plan.page_w_mm + 2 * bleed
    total_h_mm = plan.page_h_mm + 2 * bleed
    W = mm_to_px(total_w_mm, dpi)
    H = mm_to_px(total_h_mm, dpi)
    bleed_px = mm_to_px(bleed, dpi)

    # ── Fond de page ───────────────────────────────────────────────────
    bg = plan.background
    if bg and bg.color:
        canvas = Image.new("RGBA", (W, H), bg.color.to_rgba())
    else:
        canvas = Image.new("RGBA", (W, H), (255, 255, 255, 255))

    if bg and bg.gradient:
        canvas = _apply_gradient(canvas, bg.gradient, dpi)
    if bg and bg.image_media_ref and bg.image_media_ref in medias:
        bg_img = _load_image(medias[bg.image_media_ref])
        bg_crop, bg_size = compute_fit_box(
            bg_img.width, bg_img.height, W, H, bg.image_fit,
        )
        bg_cropped = bg_img.crop(bg_crop).resize(bg_size, Image.LANCZOS)
        # Centre si contain
        ox = (W - bg_size[0]) // 2
        oy = (H - bg_size[1]) // 2
        if bg.image_opacity < 1.0:
            alpha = bg_cropped.split()[3] if bg_cropped.mode == "RGBA" else None
            if alpha:
                alpha = alpha.point(lambda v: int(v * bg.image_opacity))
                bg_cropped.putalpha(alpha)
        canvas.paste(bg_cropped, (ox, oy), bg_cropped if bg_cropped.mode == "RGBA" else None)

    # ── Items triés par z_index ────────────────────────────────────────
    items_sorted = sorted(
        plan.items,
        key=lambda it: it.get("z_index", 5) if isinstance(it, dict) else getattr(it, "z_index", 5),
    )

    for raw in items_sorted:
        item = _coerce_item(raw)
        if item is None:
            continue
        try:
            if isinstance(item, ImagePlacement):
                _render_image(canvas, item, medias, bleed_px, dpi)
            elif isinstance(item, TextPlacement):
                _render_text(canvas, item, bleed_px, dpi)
            elif isinstance(item, ShapePlacement):
                _render_shape(canvas, item, bleed_px, dpi)
            elif isinstance(item, ChartPlacement):
                _render_chart(canvas, item, bleed_px, dpi)
            elif isinstance(item, MockupPlacement):
                _render_mockup(canvas, item, medias, bleed_px, dpi)
            elif isinstance(item, GradientMeshPlacement):
                _render_gradient_mesh(canvas, item, bleed_px, dpi)
        except Exception as e:
            logger.warning(f"[GeomPlacement] Item {item.kind} échoué : {e}")

    # ── Debug grid optionnelle ────────────────────────────────────────
    if plan.debug_grid:
        _draw_debug_grid(canvas, plan, bleed_px, dpi)

    out = io.BytesIO()
    canvas.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()


def _coerce_item(raw):
    """Coerce un item dict ou Pydantic vers le bon type."""
    if isinstance(raw, (TextPlacement, ImagePlacement, ShapePlacement,
                         ChartPlacement, MockupPlacement, GradientMeshPlacement)):
        return raw
    if isinstance(raw, dict):
        kind = raw.get("kind", "")
        try:
            if kind == "text":           return TextPlacement(**raw)
            if kind == "image":          return ImagePlacement(**raw)
            if kind == "shape":          return ShapePlacement(**raw)
            if kind == "chart":          return ChartPlacement(**raw)
            if kind == "mockup":         return MockupPlacement(**raw)
            if kind == "gradient_mesh":  return GradientMeshPlacement(**raw)
        except Exception as e:
            logger.warning(f"[GeomPlacement] Item invalide ({kind}) : {e}")
    return None


def _svg_to_png(svg_bytes: bytes, target_w_px: int, target_h_px: int) -> Optional[bytes]:
    """Rasterise un SVG en PNG aux dimensions cibles via cairosvg (préféré)
    avec fallback svglib + reportlab. Retourne None si aucun convertisseur
    disponible (rare en prod, dépendances installées)."""
    try:
        import cairosvg
        return cairosvg.svg2png(
            bytestring=svg_bytes,
            output_width=int(max(64, target_w_px)),
            output_height=int(max(64, target_h_px)),
        )
    except Exception as e1:
        logger.debug(f"[SVG→PNG] cairosvg indispo ({e1}), tentative svglib")
        try:
            from io import BytesIO
            from svglib.svglib import svg2rlg
            from reportlab.graphics import renderPM
            drawing = svg2rlg(BytesIO(svg_bytes))
            if drawing is None:
                return None
            scale_x = target_w_px / max(1, drawing.width)
            scale_y = target_h_px / max(1, drawing.height)
            drawing.scale(scale_x, scale_y)
            drawing.width = target_w_px
            drawing.height = target_h_px
            buf = BytesIO()
            renderPM.drawToFile(drawing, buf, fmt="PNG")
            return buf.getvalue()
        except Exception as e2:
            logger.warning(f"[SVG→PNG] svglib échec aussi : {e2}")
            return None


def _load_image(data: bytes) -> "Image.Image":
    from PIL import Image
    img = Image.open(io.BytesIO(data))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    return img


def _render_image(canvas, item: ImagePlacement, medias: dict, bleed_px: int, dpi: int):
    """Render une image avec fit, masque, transforms, filtres.
    Si media_ref absent mais prompt_ia présent → génération auto IA via Flux."""
    from PIL import Image, ImageFilter, ImageEnhance
    src = None
    if item.media_ref and item.media_ref in medias:
        src = _load_image(medias[item.media_ref])
    elif item.prompt_ia:
        # GÉNÉRATION AUTO IA — Flux/Recraft/Ideogram à la volée.
        # Synchrone via asyncio.run dans un thread séparé pour rester
        # dans la signature render_placement_plan() qui est sync.
        # AUTO-ROUTAGE : si le prompt décrit un visuel vectoriel
        # (logo/icône/illustration plate/wordmark), on appelle Recraft v3
        # SVG pour obtenir un SVG natif qu'on rasterise à la résolution
        # cible (qualité parfaite sans pixelisation). Sinon Flux/Ideogram
        # raster classique. Le bytes SVG est conservé en parallèle pour
        # export ultérieur (placement_to_svg.py) — c'est le différenciateur
        # vectoriel end-to-end.
        try:
            import asyncio as _aio
            from . import image_gen as _ig
            ratio = item.target_zone.w / max(0.01, item.target_zone.h)
            fmt = "square_hd" if 0.9 < ratio < 1.1 else (
                "portrait_4_3" if ratio < 0.9 else "landscape_4_3"
            )
            cache_key = f"ia_gen:{hash(item.prompt_ia) & 0xFFFFFFFF:08x}"
            png_ia = None
            if _ig.is_vector_brief(item.prompt_ia):
                # Routage Recraft v3 SVG (Replicate) → SVG natif → rasterise PNG
                try:
                    svg_bytes = _aio.run(_ig.generer_svg_natif(
                        prompt=item.prompt_ia, format_=fmt, timeout_s=120.0,
                    ))
                    if svg_bytes:
                        medias[cache_key + "_svg"] = svg_bytes
                        png_ia = _svg_to_png(svg_bytes,
                                             mm_to_px(item.target_zone.w, dpi),
                                             mm_to_px(item.target_zone.h, dpi))
                        logger.info(f"[GeomPlacement] SVG natif Recraft v3 généré ({len(svg_bytes)} bytes) + rasterisé PNG")
                except Exception as _e_svg:
                    logger.warning(f"[GeomPlacement] SVG natif échec ({_e_svg}), fallback Flux raster")
            if png_ia is None:
                png_ia = _aio.run(_ig.generer_image(
                    prompt=item.prompt_ia,
                    mode=item.mode_ia or "premium",
                    format_=fmt,
                    timeout_s=120.0,
                ))
            if png_ia:
                src = _load_image(png_ia)
                medias[cache_key] = png_ia
                logger.info(f"[GeomPlacement] Image IA générée ({item.mode_ia}) : {len(png_ia)} bytes")
        except Exception as e:
            logger.warning(f"[GeomPlacement] Génération IA échouée : {e}")
    if src is None:
        logger.debug(f"[GeomPlacement] Image absente : media_ref={item.media_ref} prompt_ia={bool(item.prompt_ia)}")
        return

    # 1. Bbox cible en pixels (avec offset bleed)
    tx = mm_to_px(item.target_zone.x, dpi) + bleed_px
    ty = mm_to_px(item.target_zone.y, dpi) + bleed_px
    tw = mm_to_px(item.target_zone.w, dpi)
    th = mm_to_px(item.target_zone.h, dpi)

    # 2. Filtres pré-fit (recolor/grayscale appliqués sur source)
    if item.grayscale:
        from PIL import ImageOps
        gray = ImageOps.grayscale(src.convert("RGB")).convert("RGBA")
        if src.mode == "RGBA":
            gray.putalpha(src.split()[3])
        src = gray
    if item.recolor_to:
        src = apply_recolor(src, item.recolor_to)
    if item.brightness != 1.0:
        src = ImageEnhance.Brightness(src).enhance(item.brightness)
    if item.contrast != 1.0:
        src = ImageEnhance.Contrast(src).enhance(item.contrast)
    if item.blur_radius_mm > 0:
        src = src.filter(ImageFilter.GaussianBlur(radius=mm_to_px(item.blur_radius_mm, dpi)))

    # 3. Fit (cover/contain/etc.) → crop source + resize au target
    crop_tuple = (item.crop_box_x, item.crop_box_y, item.crop_box_w, item.crop_box_h)
    crop_box, render_size = compute_fit_box(
        src.width, src.height, tw, th, item.fit_mode,
        focal_x=item.focal_point_x, focal_y=item.focal_point_y,
        crop=crop_tuple,
    )
    src_cropped = src.crop(crop_box).resize(render_size, Image.LANCZOS)

    # Center si contain (peut être < target)
    paste_x = tx + (tw - render_size[0]) // 2
    paste_y = ty + (th - render_size[1]) // 2

    # 4. Masque alpha selon mask_shape
    if item.mask_shape != "rect":
        mask = make_mask(render_size[0], render_size[1], item.mask_shape, item.mask_extra)
        if src_cropped.mode != "RGBA":
            src_cropped = src_cropped.convert("RGBA")
        src_cropped.putalpha(mask)
    elif src_cropped.mode != "RGBA":
        src_cropped = src_cropped.convert("RGBA")

    # 5. Opacité globale via transform
    if item.transform.opacity < 1.0:
        alpha = src_cropped.split()[3]
        alpha = alpha.point(lambda v: int(v * item.transform.opacity))
        src_cropped.putalpha(alpha)

    # 6. Rotation/scale
    if item.transform.rotation_deg != 0 or item.transform.scale != 1.0:
        if item.transform.scale != 1.0:
            new_w = int(src_cropped.width * item.transform.scale)
            new_h = int(src_cropped.height * item.transform.scale)
            src_cropped = src_cropped.resize((new_w, new_h), Image.LANCZOS)
        if item.transform.rotation_deg != 0:
            src_cropped = src_cropped.rotate(
                -item.transform.rotation_deg,  # PIL rotation = anti-horaire
                resample=Image.BICUBIC,
                expand=True,
            )
        # Recentrer après rotation
        paste_x = tx + (tw - src_cropped.width) // 2
        paste_y = ty + (th - src_cropped.height) // 2

    # 7. Ombre portée (avant l'image, derrière)
    if item.shadow:
        _render_shadow(canvas, src_cropped, (paste_x, paste_y), item.shadow, dpi)

    # 8. Bordure (after, sur le masque final)
    canvas.paste(src_cropped, (paste_x, paste_y), src_cropped)

    if item.border_color and item.border_mm > 0:
        from PIL import ImageDraw
        bw = max(1, mm_to_px(item.border_mm, dpi))
        d = ImageDraw.Draw(canvas)
        # Bordure suit la forme du masque
        if item.mask_shape in ("rect",):
            d.rectangle(
                [(paste_x, paste_y), (paste_x + src_cropped.width, paste_y + src_cropped.height)],
                outline=item.border_color.to_rgba(), width=bw,
            )
        elif item.mask_shape == "circle":
            diameter = min(src_cropped.width, src_cropped.height)
            cx = paste_x + src_cropped.width / 2
            cy = paste_y + src_cropped.height / 2
            d.ellipse(
                [(cx - diameter / 2, cy - diameter / 2),
                 (cx + diameter / 2, cy + diameter / 2)],
                outline=item.border_color.to_rgba(), width=bw,
            )
        # Polygon/etc. : à étendre si besoin


def _render_shadow(canvas, sprite, pos, shadow: Shadow, dpi: int):
    """Dessine une ombre portée derrière un sprite avec masque alpha."""
    from PIL import Image, ImageFilter
    ox = mm_to_px(shadow.offset_x_mm, dpi)
    oy = mm_to_px(shadow.offset_y_mm, dpi)
    blur = max(0, mm_to_px(shadow.blur_mm, dpi))

    if sprite.mode != "RGBA":
        sprite = sprite.convert("RGBA")
    alpha = sprite.split()[3]
    shadow_layer = Image.new("RGBA", sprite.size, shadow.color.to_rgba())
    shadow_layer.putalpha(alpha)
    if blur > 0:
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=blur))
    canvas.paste(shadow_layer, (pos[0] + ox, pos[1] + oy), shadow_layer)


def _render_text(canvas, item: TextPlacement, bleed_px: int, dpi: int):
    """Render un bloc texte avec wrap, alignement, transforms."""
    from PIL import Image, ImageDraw, ImageFont, ImageFilter

    tx = mm_to_px(item.bbox.x, dpi) + bleed_px
    ty = mm_to_px(item.bbox.y, dpi) + bleed_px
    tw = mm_to_px(item.bbox.w, dpi)
    th = mm_to_px(item.bbox.h, dpi)

    text = item.text.upper() if item.uppercase else item.text

    # ── Background du bloc (badge/callout) ──────────────────────────
    if item.background:
        from PIL import ImageDraw
        pad = mm_to_px(item.background_padding_mm, dpi)
        r = mm_to_px(item.background_radius_mm, dpi)
        bg_box = [(tx - pad, ty - pad), (tx + tw + pad, ty + th + pad)]
        bg_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        bg_draw = ImageDraw.Draw(bg_layer)
        if r > 0:
            bg_draw.rounded_rectangle(bg_box, radius=r, fill=item.background.to_rgba())
        else:
            bg_draw.rectangle(bg_box, fill=item.background.to_rgba())
        canvas.alpha_composite(bg_layer)

    # ── Charge la police ────────────────────────────────────────────
    font_px = int(round(item.font_size_pt * dpi / 72))
    font = _load_font(item.font_family, font_px, item.font_weight, item.italic)

    # ── Word-wrap dans la bbox ─────────────────────────────────────
    lines = _wrap_text(text, font, tw, letter_spacing_em=item.letter_spacing_em)
    line_h_px = int(font_px * item.line_height)
    total_text_h = len(lines) * line_h_px

    # Vertical align
    if item.vertical_align == "middle":
        cur_y = ty + max(0, (th - total_text_h) // 2)
    elif item.vertical_align == "bottom":
        cur_y = ty + max(0, th - total_text_h)
    else:
        cur_y = ty

    # ── Render texte (potentiellement sur layer rotated) ────────────
    color = item.color.to_rgba()
    if item.transform.rotation_deg != 0:
        # Render texte sur layer transparente, puis rotate, puis paste
        layer = Image.new("RGBA", (tw, max(line_h_px, total_text_h)), (0, 0, 0, 0))
        layer_d = ImageDraw.Draw(layer)
        cur = 0
        for line in lines:
            _draw_line(layer_d, line, 0, cur, tw, font, color, item.align,
                       item.letter_spacing_em, font_px)
            if item.underline:
                _draw_underline(layer_d, line, 0, cur, tw, font, color, item.align)
            cur += line_h_px
        if item.shadow:
            _render_text_shadow(canvas, layer, (tx, cur_y), item.shadow, dpi)
        rotated = layer.rotate(-item.transform.rotation_deg, resample=Image.BICUBIC, expand=True)
        canvas.alpha_composite(rotated, dest=(tx, cur_y))
    else:
        # Direct
        if item.shadow:
            # Build sprite for shadow render
            layer = Image.new("RGBA", (tw, max(line_h_px, total_text_h)), (0, 0, 0, 0))
            layer_d = ImageDraw.Draw(layer)
            cur = 0
            for line in lines:
                _draw_line(layer_d, line, 0, cur, tw, font, color, item.align,
                           item.letter_spacing_em, font_px)
                cur += line_h_px
            _render_text_shadow(canvas, layer, (tx, cur_y), item.shadow, dpi)
        d = ImageDraw.Draw(canvas)
        cur = cur_y
        for line in lines:
            _draw_line(d, line, tx, cur, tw, font, color, item.align,
                       item.letter_spacing_em, font_px)
            if item.underline:
                _draw_underline(d, line, tx, cur, tw, font, color, item.align)
            cur += line_h_px


def _render_text_shadow(canvas, text_layer, pos, shadow: Shadow, dpi: int):
    """Ombre portée d'un layer texte (alpha mask + blur + offset)."""
    from PIL import Image, ImageFilter
    alpha = text_layer.split()[3]
    shadow_layer = Image.new("RGBA", text_layer.size, shadow.color.to_rgba())
    shadow_layer.putalpha(alpha)
    blur = max(0, mm_to_px(shadow.blur_mm, dpi))
    if blur > 0:
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=blur))
    ox = mm_to_px(shadow.offset_x_mm, dpi)
    oy = mm_to_px(shadow.offset_y_mm, dpi)
    canvas.alpha_composite(shadow_layer, dest=(pos[0] + ox, pos[1] + oy))


def _draw_line(d, text, x, y, w, font, color, align, letter_spacing_em, font_px):
    """Dessine une ligne avec alignement horizontal."""
    if letter_spacing_em != 0:
        _draw_with_letter_spacing(d, text, x, y, w, font, color, align,
                                   letter_spacing_em, font_px)
        return
    # Calcul largeur texte pour alignement
    try:
        bbox = d.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
    except Exception:
        text_w = font.getsize(text)[0] if hasattr(font, "getsize") else len(text) * font_px // 2
    if align == "center":
        x = x + (w - text_w) // 2
    elif align == "right":
        x = x + (w - text_w)
    d.text((x, y), text, font=font, fill=color)


def _draw_with_letter_spacing(d, text, x, y, w, font, color, align,
                                spacing_em: float, font_px: int):
    """Dessine en ajoutant letter-spacing (em-based)."""
    spacing_px = int(font_px * spacing_em)
    # Mesure largeur totale
    try:
        char_widths = []
        for c in text:
            bbox = d.textbbox((0, 0), c, font=font)
            char_widths.append(bbox[2] - bbox[0])
        total_w = sum(char_widths) + spacing_px * max(0, len(text) - 1)
    except Exception:
        total_w = len(text) * font_px // 2 + spacing_px * len(text)
    if align == "center":
        x = x + (w - total_w) // 2
    elif align == "right":
        x = x + (w - total_w)
    cur_x = x
    for c, cw in zip(text, char_widths):
        d.text((cur_x, y), c, font=font, fill=color)
        cur_x += cw + spacing_px


def _draw_underline(d, text, x, y, w, font, color, align):
    """Trait souligné sous la ligne."""
    try:
        bbox = d.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        ascent = bbox[3]
    except Exception:
        text_w = len(text) * 6
        ascent = 12
    if align == "center":
        x = x + (w - text_w) // 2
    elif align == "right":
        x = x + (w - text_w)
    line_y = y + ascent + 2
    d.line([(x, line_y), (x + text_w, line_y)], fill=color, width=max(1, ascent // 15))


def _wrap_text(text: str, font, max_width: int, letter_spacing_em: float = 0.0) -> list[str]:
    """Word-wrap basé sur la largeur réelle de la police."""
    from PIL import ImageDraw, Image
    # Drawing context jetable pour mesurer
    tmp = Image.new("RGB", (10, 10))
    d = ImageDraw.Draw(tmp)

    def width(s: str) -> int:
        try:
            bbox = d.textbbox((0, 0), s, font=font)
            return bbox[2] - bbox[0]
        except Exception:
            return len(s) * 6

    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        words = paragraph.split()
        current = ""
        for word in words:
            test = (current + " " + word).strip() if current else word
            if width(test) <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                # Si le mot seul dépasse, on le coupe brutalement
                if width(word) > max_width:
                    chunk = ""
                    for c in word:
                        if width(chunk + c) <= max_width:
                            chunk += c
                        else:
                            if chunk:
                                lines.append(chunk)
                            chunk = c
                    current = chunk
                else:
                    current = word
        if current:
            lines.append(current)
    return lines


def _render_shape(canvas, item: ShapePlacement, bleed_px: int, dpi: int):
    """Render une forme géométrique décorative."""
    from PIL import Image, ImageDraw
    tx = mm_to_px(item.bbox.x, dpi) + bleed_px
    ty = mm_to_px(item.bbox.y, dpi) + bleed_px
    tw = mm_to_px(item.bbox.w, dpi)
    th = mm_to_px(item.bbox.h, dpi)

    layer = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    mask = make_mask(tw, th, item.shape, item.shape_extra)
    if item.fill:
        fill_layer = Image.new("RGBA", (tw, th), item.fill.to_rgba())
        fill_layer.putalpha(mask)
        layer = Image.alpha_composite(layer, fill_layer)

    if item.stroke and item.stroke_width_mm > 0:
        # Bordure : différence entre 2 masques de taille différente
        sw = max(1, mm_to_px(item.stroke_width_mm, dpi))
        inner_mask = Image.new("L", (tw, th), 0)
        d_inner = ImageDraw.Draw(inner_mask)
        d_inner.rectangle([(sw, sw), (tw - sw, th - sw)], fill=255)
        # Limite aux pixels où mask=blanc et inner_mask=noir
        ring_mask = Image.eval(mask, lambda v: v) if mask else None
        if ring_mask:
            # ring = mask - (mask ∩ shrunk(mask))
            shrunk = mask.filter(__import__("PIL").ImageFilter.MinFilter(size=2 * sw + 1))
            from PIL import ImageChops
            ring = ImageChops.subtract(mask, shrunk)
            stroke_layer = Image.new("RGBA", (tw, th), item.stroke.to_rgba())
            stroke_layer.putalpha(ring)
            layer = Image.alpha_composite(layer, stroke_layer)

    # Rotation
    if item.transform.rotation_deg != 0:
        layer = layer.rotate(-item.transform.rotation_deg, resample=Image.BICUBIC, expand=True)
        tx = tx + (tw - layer.width) // 2
        ty = ty + (th - layer.height) // 2

    if item.transform.opacity < 1.0:
        alpha = layer.split()[3]
        alpha = alpha.point(lambda v: int(v * item.transform.opacity))
        layer.putalpha(alpha)

    canvas.alpha_composite(layer, dest=(tx, ty))


def _apply_gradient(canvas, gradient: dict, dpi: int) -> "Image.Image":
    """Applique un gradient linéaire ou radial."""
    from PIL import Image, ImageDraw
    W, H = canvas.size
    g_type = gradient.get("type", "linear")
    stops = gradient.get("stops", [])
    if len(stops) < 2:
        return canvas
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if g_type == "linear":
        angle = float(gradient.get("angle_deg", 0))
        # Vecteur direction
        rad = math.radians(angle)
        dx, dy = math.cos(rad), math.sin(rad)
        # Projection de chaque pixel sur l'axe du gradient
        # Pour perf, on génère une rampe 1D puis on rotate-affine
        ramp_len = int(math.sqrt(W * W + H * H))
        ramp = Image.new("RGBA", (ramp_len, 1), (0, 0, 0, 0))
        for x in range(ramp_len):
            t = x / max(1, ramp_len - 1)
            ramp.putpixel((x, 0), _lerp_stops(stops, t))
        # Resize verticalement + rotate
        ramp = ramp.resize((ramp_len, ramp_len // 4))
        ramp = ramp.rotate(-angle, resample=Image.BICUBIC, expand=True)
        ox = (ramp.width - W) // 2
        oy = (ramp.height - H) // 2
        layer = ramp.crop((ox, oy, ox + W, oy + H)).convert("RGBA")
    elif g_type == "radial":
        cx, cy = W // 2, H // 2
        max_r = int(math.sqrt(cx * cx + cy * cy))
        ramp_data = layer.load()
        for y in range(H):
            for x in range(W):
                dx = x - cx; dy = y - cy
                r = math.sqrt(dx * dx + dy * dy)
                t = min(1.0, r / max_r)
                ramp_data[x, y] = _lerp_stops(stops, t)
    return Image.alpha_composite(canvas, layer)


def _lerp_stops(stops: list, t: float) -> tuple[int, int, int, int]:
    """Interpole couleur entre les color stops du gradient."""
    if t <= stops[0]["pos"]:
        c = stops[0]["color"]
        return _color_to_tuple(c)
    if t >= stops[-1]["pos"]:
        return _color_to_tuple(stops[-1]["color"])
    for i in range(len(stops) - 1):
        a, b = stops[i], stops[i + 1]
        if a["pos"] <= t <= b["pos"]:
            f = (t - a["pos"]) / max(1e-6, b["pos"] - a["pos"])
            ca = _color_to_tuple(a["color"])
            cb = _color_to_tuple(b["color"])
            return tuple(int(ca[k] + (cb[k] - ca[k]) * f) for k in range(4))
    return _color_to_tuple(stops[-1]["color"])


def _color_to_tuple(c) -> tuple[int, int, int, int]:
    """Color (dict ou Pydantic) → tuple RGBA."""
    if isinstance(c, dict):
        return (int(c.get("r", 0)), int(c.get("g", 0)), int(c.get("b", 0)),
                int(round(float(c.get("a", 1.0)) * 255)))
    if isinstance(c, Color):
        return c.to_rgba()
    return (0, 0, 0, 255)


def _draw_debug_grid(canvas, plan: PlacementPlan, bleed_px: int, dpi: int):
    """Trame fine (5mm/10mm) pour visualiser positions LLM en debug."""
    from PIL import ImageDraw
    d = ImageDraw.Draw(canvas)
    W, H = canvas.size
    step_5 = mm_to_px(5, dpi)
    step_10 = mm_to_px(10, dpi)
    light = (200, 200, 200, 120)
    bold = (150, 150, 150, 200)
    for x in range(0, W, step_5):
        d.line([(x, 0), (x, H)], fill=light, width=1)
    for y in range(0, H, step_5):
        d.line([(0, y), (W, y)], fill=light, width=1)
    for x in range(0, W, step_10):
        d.line([(x, 0), (x, H)], fill=bold, width=1)
    for y in range(0, H, step_10):
        d.line([(0, y), (W, y)], fill=bold, width=1)


def _load_font(family: str, size_px: int, weight: int = 400, italic: bool = False):
    """Charge la police via font_loader si dispo, sinon fallback PIL default."""
    from PIL import ImageFont
    try:
        from modules.bureau.font_loader import charger_police
        path = charger_police(family, weight=weight, italic=italic)
        if path:
            return ImageFont.truetype(path, size_px)
    except Exception:
        pass
    # Fallback ordonné
    for candidate in ("calibri.ttf", "arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(candidate, size_px)
        except Exception:
            continue
    return ImageFont.load_default()


# ═══════════════════════════════════════════════════════════════════════
# Render — Primitives marketing (chart, mockup, gradient_mesh)
# ═══════════════════════════════════════════════════════════════════════

def _render_chart(canvas, item: "ChartPlacement", bleed_px: int, dpi: int):
    """
    Render chart natif vectoriel via PIL (bar/column/pie/donut/line/area).
    Pas d'image plate IA — qualité parfaite à toute échelle.
    Idéal visuels marketing data (ROI, KPI campagne, comparaison perf).
    """
    from PIL import Image, ImageDraw
    tx = mm_to_px(item.bbox.x, dpi) + bleed_px
    ty = mm_to_px(item.bbox.y, dpi) + bleed_px
    tw = mm_to_px(item.bbox.w, dpi)
    th = mm_to_px(item.bbox.h, dpi)

    layer = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    # Couleurs : utilise palette fournie sinon palette défaut (Inter brand)
    default_palette = [
        Color(r=0x4F, g=0x46, b=0xE5, a=1.0),  # indigo
        Color(r=0x10, g=0xB9, b=0x81, a=1.0),  # emerald
        Color(r=0xF5, g=0x9E, b=0x0B, a=1.0),  # amber
        Color(r=0xEF, g=0x44, b=0x44, a=1.0),  # red
        Color(r=0x8B, g=0x5C, b=0xF6, a=1.0),  # violet
        Color(r=0x06, g=0xB6, b=0xD4, a=1.0),  # cyan
    ]
    colors = item.colors or default_palette
    n = min(len(item.labels), len(item.values))
    if n == 0:
        return

    # Title (top, 12% de la hauteur réservé)
    title_h = int(th * 0.12) if item.title else 0
    legend_h = int(th * 0.08) if item.show_legend and item.chart_type in ("bar", "column", "line", "area") else 0
    chart_top = ty + title_h
    chart_h = th - title_h - legend_h
    chart_w = tw

    if item.title:
        font_title = _load_font("Calibri Light", max(11, int(title_h * 0.55)),
                                 weight=600)
        d_canvas = ImageDraw.Draw(canvas)
        try:
            bbox = d_canvas.textbbox((0, 0), item.title, font=font_title)
            tw_title = bbox[2] - bbox[0]
        except Exception:
            tw_title = len(item.title) * 6
        d_canvas.text(
            (tx + (tw - tw_title) // 2, ty),
            item.title, font=font_title, fill=(40, 40, 50, 255),
        )

    if item.chart_type in ("bar", "column"):
        # Bar = horizontal, column = vertical
        is_vertical = (item.chart_type == "column")
        max_v = max(item.values[:n]) if item.values else 1.0
        if max_v <= 0:
            max_v = 1.0
        pad = max(6, int(chart_w * 0.04))
        if is_vertical:
            avail_w = chart_w - 2 * pad
            bar_w = avail_w / n * 0.7
            gap = avail_w / n * 0.3
            label_font = _load_font("Calibri", max(8, int(chart_h * 0.05)))
            value_font = _load_font("Calibri", max(8, int(chart_h * 0.06)), weight=600)
            value_h = max(12, int(chart_h * 0.08))
            for i in range(n):
                v = item.values[i]
                ratio = v / max_v
                bh = int((chart_h - value_h - 16) * ratio)
                bx = int(tx + pad + i * (bar_w + gap))
                by = chart_top + chart_h - bh - 16
                c = (colors[i % len(colors)]).to_rgba()
                d_canvas = ImageDraw.Draw(canvas)
                d_canvas.rectangle(
                    [(bx, by), (bx + int(bar_w), by + bh)],
                    fill=c,
                )
                if item.show_values:
                    label_v = f"{v:g}{item.unit}"
                    try:
                        bbv = d_canvas.textbbox((0, 0), label_v, font=value_font)
                        wv = bbv[2] - bbv[0]
                    except Exception:
                        wv = len(label_v) * 5
                    d_canvas.text(
                        (bx + int(bar_w) // 2 - wv // 2, by - value_h),
                        label_v, font=value_font, fill=(40, 40, 50, 255),
                    )
                # Label dessous
                lbl = item.labels[i][:14]
                try:
                    bbl = d_canvas.textbbox((0, 0), lbl, font=label_font)
                    wl = bbl[2] - bbl[0]
                except Exception:
                    wl = len(lbl) * 5
                d_canvas.text(
                    (bx + int(bar_w) // 2 - wl // 2, chart_top + chart_h - 14),
                    lbl, font=label_font, fill=(80, 80, 90, 255),
                )
        else:
            # Bar horizontal
            label_w = int(chart_w * 0.25)
            chart_x = tx + label_w
            avail_w_h = chart_w - label_w - pad
            bar_h_each = chart_h / n * 0.7
            gap_v = chart_h / n * 0.3
            label_font = _load_font("Calibri", max(8, int(bar_h_each * 0.45)))
            value_font = _load_font("Calibri", max(8, int(bar_h_each * 0.5)), weight=600)
            d_canvas = ImageDraw.Draw(canvas)
            for i in range(n):
                v = item.values[i]
                bw = int(avail_w_h * (v / max_v))
                by = int(chart_top + i * (bar_h_each + gap_v))
                c = (colors[i % len(colors)]).to_rgba()
                d_canvas.rectangle(
                    [(chart_x, by), (chart_x + bw, by + int(bar_h_each))],
                    fill=c,
                )
                # Label gauche
                lbl = item.labels[i][:18]
                d_canvas.text(
                    (tx + 4, by + int(bar_h_each * 0.2)),
                    lbl, font=label_font, fill=(60, 60, 70, 255),
                )
                if item.show_values:
                    label_v = f"{v:g}{item.unit}"
                    d_canvas.text(
                        (chart_x + bw + 4, by + int(bar_h_each * 0.2)),
                        label_v, font=value_font, fill=(40, 40, 50, 255),
                    )

    elif item.chart_type in ("pie", "donut"):
        # Pie / donut centré dans le bbox
        total = sum(item.values[:n]) or 1.0
        cx = tx + tw // 2
        cy = chart_top + chart_h // 2
        radius = min(tw, chart_h) // 2 - 6
        inner_r = int(radius * 0.55) if item.chart_type == "donut" else 0
        d_canvas = ImageDraw.Draw(canvas)
        start = -90  # 12h
        for i in range(n):
            angle = item.values[i] / total * 360
            end = start + angle
            color_rgba = (colors[i % len(colors)]).to_rgba()
            d_canvas.pieslice(
                [(cx - radius, cy - radius), (cx + radius, cy + radius)],
                start=start, end=end, fill=color_rgba,
            )
            start = end
        if inner_r > 0:
            d_canvas.ellipse(
                [(cx - inner_r, cy - inner_r), (cx + inner_r, cy + inner_r)],
                fill=(255, 255, 255, 255),
            )

    elif item.chart_type in ("line", "area"):
        max_v = max(item.values[:n]) if item.values else 1.0
        if max_v <= 0:
            max_v = 1.0
        pad = max(8, int(chart_w * 0.04))
        avail_w = chart_w - 2 * pad
        avail_h = chart_h - 20
        step = avail_w / max(1, n - 1) if n > 1 else 0
        points = []
        for i in range(n):
            px = int(tx + pad + i * step)
            py = int(chart_top + 10 + (avail_h - avail_h * (item.values[i] / max_v)))
            points.append((px, py))
        d_canvas = ImageDraw.Draw(canvas)
        line_color = (colors[0]).to_rgba()
        if item.chart_type == "area":
            poly = points + [(points[-1][0], chart_top + chart_h),
                              (points[0][0], chart_top + chart_h)]
            r, g, b, _ = line_color
            d_canvas.polygon(poly, fill=(r, g, b, 80))
        # Ligne
        for i in range(len(points) - 1):
            d_canvas.line([points[i], points[i + 1]], fill=line_color, width=3)
        # Points
        for p in points:
            d_canvas.ellipse(
                [(p[0] - 4, p[1] - 4), (p[0] + 4, p[1] + 4)],
                fill=line_color,
            )

    # Légende (bar/column/line/area uniquement, sous le chart)
    if item.show_legend and legend_h > 0:
        d_canvas = ImageDraw.Draw(canvas)
        legend_font = _load_font("Calibri", max(7, int(legend_h * 0.5)))
        gx = tx + 6
        gy = chart_top + chart_h + 4
        for i, lbl in enumerate(item.labels[:n]):
            c = (colors[i % len(colors)]).to_rgba()
            d_canvas.rectangle([(gx, gy + 2), (gx + 10, gy + 10)], fill=c)
            d_canvas.text((gx + 14, gy), lbl[:18], font=legend_font, fill=(60, 60, 70, 255))
            try:
                bb = d_canvas.textbbox((0, 0), lbl[:18], font=legend_font)
                gx += 14 + (bb[2] - bb[0]) + 12
            except Exception:
                gx += 14 + len(lbl) * 5 + 12


def _render_mockup(canvas, item: "MockupPlacement", medias: dict, bleed_px: int, dpi: int):
    """
    Render mockup container vectoriel + image embarquée.
    9 devices supportés : smartphone, smartphone_landscape, tablet, laptop,
    monitor, billboard, poster_frame, instagram_post_phone,
    business_card_holder, tshirt, tote_bag, mug, tv_screen.
    """
    from PIL import Image, ImageDraw
    tx = mm_to_px(item.bbox.x, dpi) + bleed_px
    ty = mm_to_px(item.bbox.y, dpi) + bleed_px
    tw = mm_to_px(item.bbox.w, dpi)
    th = mm_to_px(item.bbox.h, dpi)
    dev_color = item.device_color.to_rgba()
    d = ImageDraw.Draw(canvas)

    # Charge inner image si fourni
    inner_img = None
    if item.inner_image_b64:
        try:
            import base64 as _b64
            payload = item.inner_image_b64.split(",", 1)[-1] if "," in item.inner_image_b64 else item.inner_image_b64
            inner_img = _load_image(_b64.b64decode(payload + "=="))
        except Exception:
            pass
    elif item.inner_image_media_ref and item.inner_image_media_ref in medias:
        inner_img = _load_image(medias[item.inner_image_media_ref])

    if item.device in ("smartphone", "instagram_post_phone"):
        # Smartphone portrait : ratio 9:19.5 (iPhone-like)
        ratio = 19.5 / 9
        if th / tw < ratio:
            phone_h = th
            phone_w = int(phone_h / ratio)
        else:
            phone_w = tw
            phone_h = int(phone_w * ratio)
        px = tx + (tw - phone_w) // 2
        py = ty + (th - phone_h) // 2
        radius = int(phone_w * 0.12)
        d.rounded_rectangle([(px, py), (px + phone_w, py + phone_h)],
                             radius=radius, fill=dev_color)
        # Écran (intérieur, marge ~5%)
        screen_pad = int(phone_w * 0.05)
        sx, sy = px + screen_pad, py + screen_pad
        sw, sh = phone_w - 2 * screen_pad, phone_h - 2 * screen_pad
        if inner_img:
            inner_resized = inner_img.resize((sw, sh), Image.LANCZOS)
            screen_radius = max(1, radius - screen_pad)
            mask = make_mask(sw, sh, "rounded_rect", {"radius_mm": screen_radius / dpi * 25.4})
            if inner_resized.mode != "RGBA":
                inner_resized = inner_resized.convert("RGBA")
            inner_resized.putalpha(mask)
            canvas.paste(inner_resized, (sx, sy), inner_resized)
        else:
            d.rounded_rectangle([(sx, sy), (sx + sw, sy + sh)],
                                 radius=max(1, radius - screen_pad),
                                 fill=(245, 245, 250, 255))
        # Encoche (notch) en haut centre
        notch_w = int(phone_w * 0.3)
        notch_h = int(phone_w * 0.045)
        nx = px + (phone_w - notch_w) // 2
        d.rounded_rectangle([(nx, py + screen_pad + 2),
                              (nx + notch_w, py + screen_pad + 2 + notch_h)],
                             radius=notch_h // 2, fill=dev_color)
    elif item.device in ("laptop", "monitor", "tv_screen"):
        # Écran 16:9 + base (laptop) / pied (monitor)
        screen_ratio = 16 / 9
        if item.device == "laptop":
            screen_h = int(th * 0.85)
            base_h = th - screen_h
        else:
            screen_h = int(th * 0.92)
            base_h = th - screen_h
        screen_w = int(screen_h * screen_ratio)
        if screen_w > tw:
            screen_w = tw - 8
            screen_h = int(screen_w / screen_ratio)
            base_h = th - screen_h
        sx_o = tx + (tw - screen_w) // 2
        sy_o = ty
        bezel = max(4, int(screen_w * 0.025))
        d.rounded_rectangle([(sx_o, sy_o), (sx_o + screen_w, sy_o + screen_h)],
                             radius=8, fill=dev_color)
        inner_x = sx_o + bezel
        inner_y = sy_o + bezel
        inner_w = screen_w - 2 * bezel
        inner_h = screen_h - 2 * bezel
        if inner_img:
            inner_resized = inner_img.resize((inner_w, inner_h), Image.LANCZOS)
            canvas.paste(inner_resized, (inner_x, inner_y))
        else:
            d.rectangle([(inner_x, inner_y),
                          (inner_x + inner_w, inner_y + inner_h)],
                         fill=(245, 245, 250, 255))
        if item.device == "laptop":
            # Base trapézoïdale
            base_y = sy_o + screen_h
            base_w_top = int(screen_w * 0.6)
            base_w_bot = int(screen_w * 1.05)
            base_cx = sx_o + screen_w // 2
            d.polygon([
                (base_cx - base_w_top // 2, base_y),
                (base_cx + base_w_top // 2, base_y),
                (base_cx + base_w_bot // 2, base_y + base_h),
                (base_cx - base_w_bot // 2, base_y + base_h),
            ], fill=dev_color)
        elif item.device == "monitor":
            # Pied vertical + socle
            stand_w = int(screen_w * 0.1)
            stand_h = int(base_h * 0.6)
            stand_x = sx_o + (screen_w - stand_w) // 2
            d.rectangle([(stand_x, sy_o + screen_h),
                          (stand_x + stand_w, sy_o + screen_h + stand_h)], fill=dev_color)
            socle_w = int(screen_w * 0.5)
            socle_x = sx_o + (screen_w - socle_w) // 2
            d.rounded_rectangle(
                [(socle_x, sy_o + screen_h + stand_h),
                 (socle_x + socle_w, ty + th - 2)],
                radius=4, fill=dev_color,
            )
    elif item.device == "billboard":
        # Panneau 4×3 + 2 poteaux
        billboard_h = int(th * 0.75)
        billboard_w = tw - 8
        frame = max(4, int(billboard_w * 0.02))
        bx = tx + 4
        by = ty
        d.rectangle([(bx, by), (bx + billboard_w, by + billboard_h)],
                     fill=dev_color)
        if inner_img:
            inner_resized = inner_img.resize(
                (billboard_w - 2 * frame, billboard_h - 2 * frame), Image.LANCZOS)
            canvas.paste(inner_resized, (bx + frame, by + frame))
        else:
            d.rectangle([(bx + frame, by + frame),
                          (bx + billboard_w - frame, by + billboard_h - frame)],
                         fill=(240, 240, 245, 255))
        # 2 poteaux
        post_w = max(6, int(billboard_w * 0.025))
        post1_x = bx + int(billboard_w * 0.2)
        post2_x = bx + int(billboard_w * 0.75)
        for px2 in (post1_x, post2_x):
            d.rectangle([(px2, by + billboard_h), (px2 + post_w, ty + th)],
                         fill=dev_color)
    else:
        # Devices simples : rectangle + image dedans
        d.rounded_rectangle([(tx, ty), (tx + tw, ty + th)],
                             radius=int(min(tw, th) * 0.05), fill=dev_color)
        pad = int(min(tw, th) * 0.05)
        if inner_img:
            inner_resized = inner_img.resize((tw - 2 * pad, th - 2 * pad), Image.LANCZOS)
            canvas.paste(inner_resized, (tx + pad, ty + pad))


def _render_gradient_mesh(canvas, item: "GradientMeshPlacement", bleed_px: int, dpi: int):
    """
    Render gradient mesh cinématique (Linear Cards / Stripe / Apple keynote
    style). N blobs de couleur soft-blurés sur un fond de base.
    Idéal full-bleed backgrounds, hero sections, posters tendance 2025-2026.
    """
    from PIL import Image, ImageDraw, ImageFilter
    tx = mm_to_px(item.bbox.x, dpi) + bleed_px
    ty = mm_to_px(item.bbox.y, dpi) + bleed_px
    tw = mm_to_px(item.bbox.w, dpi)
    th = mm_to_px(item.bbox.h, dpi)

    base = Image.new("RGBA", (tw, th), item.base_color.to_rgba())
    blur_radius_px = max(1, mm_to_px(item.blur_mm, dpi))

    for blob in item.blobs:
        try:
            bx_pct = float(blob.get("x", 0.5))
            by_pct = float(blob.get("y", 0.5))
            radius_pct = float(blob.get("radius", 0.4))
            color_raw = blob.get("color", {"r": 100, "g": 100, "b": 200, "a": 0.8})
            if isinstance(color_raw, dict):
                color_rgba = (
                    int(color_raw.get("r", 0)), int(color_raw.get("g", 0)),
                    int(color_raw.get("b", 0)),
                    int(round(float(color_raw.get("a", 0.8)) * 255)),
                )
            else:
                color_rgba = color_raw.to_rgba()
        except Exception:
            continue
        cx = int(bx_pct * tw)
        cy = int(by_pct * th)
        r = int(min(tw, th) * radius_pct)
        blob_layer = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        dr = ImageDraw.Draw(blob_layer)
        dr.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=color_rgba)
        # Blur lourd → effet auroral fondu
        blob_blurred = blob_layer.filter(ImageFilter.GaussianBlur(radius=blur_radius_px))
        base = Image.alpha_composite(base, blob_blurred)

    canvas.alpha_composite(base, dest=(tx, ty))
