"""
PlacementPlan → SVG natif (vectoriel scalable infini).

Sortie complémentaire au rendu PIL raster de geometric_placement.py.
Le SVG produit est conforme SVG 1.1 + autonome (toutes définitions
inline : pas de référence externe). Utilisable pour :

  • Impression grand format (4×3m abribus, panneau autoroute) sans pixelisation
  • Édition fine post-génération (Inkscape, Illustrator, Figma)
  • Web embedding (logo, hero, icône) — fluide tous écrans + retina
  • Animations CSS/JS ultérieures

Couvre TextPlacement, ImagePlacement, ShapePlacement, PageBackground,
ChartPlacement, GradientMeshPlacement. MockupPlacement = pas vectorisé
ici (containers complexes — fallback raster).

Pour images bitmap (uploadées ou prompt_ia non-vectoriel) → embed
base64 dans <image href="data:image/png;base64,..."/>.
Pour Recraft v3 SVG (logos/icônes), si le bytes SVG est fourni
directement, on inline le contenu <svg>...</svg> dans un <g>.
"""
from __future__ import annotations

import base64
import logging
import math
from io import BytesIO
from typing import Optional
from xml.sax.saxutils import escape

logger = logging.getLogger("yukpo_assurance.bureau.placement_to_svg")


# ─── Helpers conversion ─────────────────────────────────────────────────

def _mm(v: float) -> str:
    """Convertit un mm en chaîne SVG (en mm directement, supporté par tous les
    viewers SVG 1.1+ et préservé à l'impression)."""
    return f"{v:.3f}"


def _color_rgba(color) -> str:
    """Convertit un Color Pydantic en string SVG (rgb ou rgba)."""
    if color is None:
        return "none"
    a = float(getattr(color, "a", 1.0))
    if a >= 0.999:
        return f"rgb({color.r},{color.g},{color.b})"
    return f"rgba({color.r},{color.g},{color.b},{a:.3f})"


def _opacity(color) -> str:
    if color is None:
        return "0"
    return f"{float(getattr(color, 'a', 1.0)):.3f}"


def _transform_str(item, cx: float, cy: float) -> str:
    """Génère le transform SVG (rotation + scale autour du centre bbox)."""
    t = getattr(item, "transform", None)
    if not t:
        return ""
    parts = []
    if t.rotation_deg:
        parts.append(f"rotate({t.rotation_deg:.2f} {_mm(cx)} {_mm(cy)})")
    if t.scale and abs(t.scale - 1.0) > 0.001:
        parts.append(f"translate({_mm(cx)} {_mm(cy)}) scale({t.scale:.3f}) translate({_mm(-cx)} {_mm(-cy)})")
    return f' transform="{" ".join(parts)}"' if parts else ""


def _opacity_attr(item) -> str:
    t = getattr(item, "transform", None)
    if t and t.opacity < 0.999:
        return f' opacity="{t.opacity:.3f}"'
    return ""


# ─── Masques (clip-path) ────────────────────────────────────────────────

def _polygon_points(shape: str, x: float, y: float, w: float, h: float,
                    extra: dict) -> str:
    """Retourne les points 'x1,y1 x2,y2 …' pour un polygon SVG."""
    if shape == "hexagon":
        cx, cy = x + w / 2, y + h / 2
        r = min(w, h) / 2
        return " ".join(
            f"{cx + r * math.cos(math.radians(60 * i - 30)):.3f},"
            f"{cy + r * math.sin(math.radians(60 * i - 30)):.3f}"
            for i in range(6)
        )
    if shape == "diamond":
        cx, cy = x + w / 2, y + h / 2
        return f"{cx},{y} {x + w},{cy} {cx},{y + h} {x},{cy}"
    if shape == "star":
        n = int(extra.get("n_points", 5))
        inner = float(extra.get("inner_radius_ratio", 0.42))
        cx, cy = x + w / 2, y + h / 2
        r_out = min(w, h) / 2
        r_in = r_out * inner
        pts = []
        for i in range(2 * n):
            ang = math.radians(-90 + 180 * i / n)
            r = r_out if i % 2 == 0 else r_in
            pts.append(f"{cx + r * math.cos(ang):.3f},{cy + r * math.sin(ang):.3f}")
        return " ".join(pts)
    if shape == "polygon":
        pts = extra.get("points") or []
        return " ".join(f"{x + p[0] * w:.3f},{y + p[1] * h:.3f}" for p in pts)
    return ""


def _shape_to_path(shape: str, x: float, y: float, w: float, h: float,
                   extra: dict) -> str:
    """Retourne un <path d="..."> ou <rect/circle/...> selon la forme."""
    if shape == "rect":
        return f'<rect x="{_mm(x)}" y="{_mm(y)}" width="{_mm(w)}" height="{_mm(h)}"'
    if shape == "rounded_rect":
        r = float(extra.get("radius_mm", min(w, h) * 0.08))
        return (f'<rect x="{_mm(x)}" y="{_mm(y)}" width="{_mm(w)}" height="{_mm(h)}" '
                f'rx="{_mm(r)}" ry="{_mm(r)}"')
    if shape == "circle":
        return (f'<circle cx="{_mm(x + w / 2)}" cy="{_mm(y + h / 2)}" '
                f'r="{_mm(min(w, h) / 2)}"')
    if shape == "ellipse":
        return (f'<ellipse cx="{_mm(x + w / 2)}" cy="{_mm(y + h / 2)}" '
                f'rx="{_mm(w / 2)}" ry="{_mm(h / 2)}"')
    if shape in ("hexagon", "diamond", "star", "polygon"):
        return f'<polygon points="{_polygon_points(shape, x, y, w, h, extra)}"'
    if shape == "blob":
        # Approximation par 4 courbes Bézier pour effet organique
        n = int(extra.get("n_lobes", 5))
        cx, cy = x + w / 2, y + h / 2
        r = min(w, h) / 2
        path_d = []
        for i in range(n):
            ang1 = 2 * math.pi * i / n
            ang2 = 2 * math.pi * (i + 1) / n
            r_var = r * (0.85 + 0.15 * math.sin(i * 1.7))
            x1 = cx + r_var * math.cos(ang1)
            y1 = cy + r_var * math.sin(ang1)
            x2 = cx + r_var * math.cos(ang2)
            y2 = cy + r_var * math.sin(ang2)
            cx_ctrl = cx + r * 1.3 * math.cos((ang1 + ang2) / 2)
            cy_ctrl = cy + r * 1.3 * math.sin((ang1 + ang2) / 2)
            if i == 0:
                path_d.append(f"M{x1:.3f},{y1:.3f}")
            path_d.append(f"Q{cx_ctrl:.3f},{cy_ctrl:.3f} {x2:.3f},{y2:.3f}")
        path_d.append("Z")
        return f'<path d="{" ".join(path_d)}"'
    return f'<rect x="{_mm(x)}" y="{_mm(y)}" width="{_mm(w)}" height="{_mm(h)}"'


# ─── Background ─────────────────────────────────────────────────────────

def _render_background(bg, page_w: float, page_h: float, bleed: float,
                       defs: list, body: list) -> None:
    """Ajoute le fond de page au SVG."""
    if bg is None:
        return
    total_w = page_w + 2 * bleed
    total_h = page_h + 2 * bleed
    if bg.color:
        body.append(f'<rect x="0" y="0" width="{_mm(total_w)}" height="{_mm(total_h)}" '
                    f'fill="{_color_rgba(bg.color)}"/>')
        return
    if bg.gradient:
        g = bg.gradient
        gid = f"bg_grad_{id(bg) & 0xFFFF:04x}"
        stops_xml = "".join(
            f'<stop offset="{s["pos"]:.3f}" stop-color="{_color_rgba(_obj_to_color(s["color"]))}" '
            f'stop-opacity="{_opacity(_obj_to_color(s["color"]))}"/>'
            for s in g.get("stops", [])
        )
        if g.get("type") == "radial":
            defs.append(f'<radialGradient id="{gid}" cx="0.5" cy="0.5" r="0.7">{stops_xml}</radialGradient>')
        else:
            ang = float(g.get("angle_deg", 90))
            x1 = 50 - 50 * math.cos(math.radians(ang))
            y1 = 50 - 50 * math.sin(math.radians(ang))
            x2 = 50 + 50 * math.cos(math.radians(ang))
            y2 = 50 + 50 * math.sin(math.radians(ang))
            defs.append(
                f'<linearGradient id="{gid}" x1="{x1}%" y1="{y1}%" x2="{x2}%" y2="{y2}%">'
                f'{stops_xml}</linearGradient>'
            )
        body.append(f'<rect x="0" y="0" width="{_mm(total_w)}" height="{_mm(total_h)}" '
                    f'fill="url(#{gid})"/>')


def _obj_to_color(c):
    """Accepte dict ou objet Color."""
    if hasattr(c, "r"):
        return c
    if isinstance(c, dict):
        from types import SimpleNamespace
        return SimpleNamespace(r=c.get("r", 0), g=c.get("g", 0), b=c.get("b", 0),
                               a=c.get("a", 1.0))
    from types import SimpleNamespace
    return SimpleNamespace(r=0, g=0, b=0, a=1.0)


# ─── Items ──────────────────────────────────────────────────────────────

def _render_shape_item(item, bleed: float, defs: list, body: list) -> None:
    """ShapePlacement → primitive SVG vectorielle."""
    x = item.bbox.x + bleed
    y = item.bbox.y + bleed
    w, h = item.bbox.w, item.bbox.h
    extra = item.shape_extra or {}
    head = _shape_to_path(item.shape, x, y, w, h, extra)
    fill = _color_rgba(item.fill) if item.fill else "none"
    stroke = _color_rgba(item.stroke) if item.stroke else "none"
    sw = item.stroke_width_mm if item.stroke else 0
    cx, cy = x + w / 2, y + h / 2
    body.append(
        f'{head} fill="{fill}" stroke="{stroke}" stroke-width="{_mm(sw)}"'
        f'{_transform_str(item, cx, cy)}{_opacity_attr(item)}/>'
    )


def _render_text_item(item, bleed: float, defs: list, body: list) -> None:
    """TextPlacement → <text> SVG avec wrap multi-ligne (tspan)."""
    x = item.bbox.x + bleed
    y = item.bbox.y + bleed
    w, h = item.bbox.w, item.bbox.h
    cx, cy = x + w / 2, y + h / 2

    # Fond optionnel
    if item.background:
        pad = item.background_padding_mm
        radius = item.background_radius_mm
        body.append(
            f'<rect x="{_mm(x - pad)}" y="{_mm(y - pad)}" '
            f'width="{_mm(w + 2 * pad)}" height="{_mm(h + 2 * pad)}" '
            f'rx="{_mm(radius)}" ry="{_mm(radius)}" '
            f'fill="{_color_rgba(item.background)}"'
            f'{_transform_str(item, cx, cy)}/>'
        )

    # Texte : conversion pt → mm (1pt = 0.3528 mm)
    font_size_mm = item.font_size_pt * 0.3528
    text_anchor = {"left": "start", "center": "middle",
                   "right": "end", "justify": "start"}.get(item.align, "start")
    anchor_x = {"left": x, "center": cx, "right": x + w}.get(item.align, x)

    text_content = item.text.upper() if item.uppercase else item.text
    style = (
        f'font-family:"{item.font_family}",sans-serif;'
        f'font-size:{_mm(font_size_mm)}mm;'
        f'font-weight:{item.font_weight};'
        f'fill:{_color_rgba(item.color)};'
    )
    if item.italic:
        style += "font-style:italic;"
    if item.letter_spacing_em:
        style += f"letter-spacing:{item.letter_spacing_em:.3f}em;"
    if item.underline:
        style += "text-decoration:underline;"

    # Wrap multi-ligne par char-count heuristique (approx ; le rendu PIL fait
    # le wrap exact, ici on coupe sur ' ' selon largeur estimée 0.5em/char)
    char_w_mm = font_size_mm * 0.55
    max_chars = max(1, int(w / char_w_mm))
    lines = _wrap_lines(text_content, max_chars)
    line_height_mm = font_size_mm * item.line_height

    # Vertical align
    n = len(lines)
    block_h = n * line_height_mm
    if item.vertical_align == "middle":
        first_y = y + (h - block_h) / 2 + font_size_mm * 0.85
    elif item.vertical_align == "bottom":
        first_y = y + h - block_h + font_size_mm * 0.85
    else:
        first_y = y + font_size_mm * 0.85

    tspans = "".join(
        f'<tspan x="{_mm(anchor_x)}" '
        f'y="{_mm(first_y + i * line_height_mm)}">{escape(line)}</tspan>'
        for i, line in enumerate(lines)
    )
    shadow_filter = ""
    if item.shadow:
        sid = _add_shadow_filter(item.shadow, defs)
        shadow_filter = f' filter="url(#{sid})"'

    body.append(
        f'<text text-anchor="{text_anchor}" style="{style}"'
        f'{_transform_str(item, cx, cy)}{_opacity_attr(item)}{shadow_filter}>'
        f'{tspans}</text>'
    )


def _wrap_lines(text: str, max_chars: int) -> list[str]:
    """Wrap simple sur espaces."""
    out: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split(" ")
        line = ""
        for w in words:
            if not line:
                line = w
            elif len(line) + 1 + len(w) <= max_chars:
                line += " " + w
            else:
                out.append(line)
                line = w
        if line:
            out.append(line)
    return out or [text]


def _add_shadow_filter(shadow, defs: list) -> str:
    """Définit un <filter> SVG pour ombre portée + retourne son id."""
    sid = f"sh_{len(defs)}"
    ox = shadow.offset_x_mm
    oy = shadow.offset_y_mm
    blur = shadow.blur_mm
    col = _color_rgba(shadow.color)
    defs.append(
        f'<filter id="{sid}" x="-50%" y="-50%" width="200%" height="200%">'
        f'<feGaussianBlur in="SourceAlpha" stdDeviation="{blur:.2f}"/>'
        f'<feOffset dx="{ox:.2f}" dy="{oy:.2f}" result="offsetblur"/>'
        f'<feFlood flood-color="{col}"/>'
        f'<feComposite in2="offsetblur" operator="in"/>'
        f'<feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge>'
        f'</filter>'
    )
    return sid


def _render_image_item(item, bleed: float, medias: dict,
                       defs: list, body: list,
                       svg_inline_assets: Optional[dict] = None) -> None:
    """ImagePlacement → <image> bitmap base64 OU <g> SVG inline (Recraft v3)."""
    x = item.bbox.x + bleed
    y = item.bbox.y + bleed
    w, h = item.target_zone.w, item.target_zone.h
    cx, cy = x + w / 2, y + h / 2

    # Récup bytes : priorité media_ref → puis svg_inline_assets[cache_key]
    media_data = None
    is_svg = False
    if item.media_ref and item.media_ref in medias:
        media_data = medias[item.media_ref]
        is_svg = media_data[:5] == b"<?xml" or b"<svg" in media_data[:200]
    elif svg_inline_assets:
        # Recraft v3 SVG depuis IA gen : pré-stocké par routes_bureau_infographie_pro
        # sous clé f"ia_gen:{hash(prompt_ia)}"
        if item.prompt_ia:
            key = f"ia_gen:{hash(item.prompt_ia) & 0xFFFFFFFF:08x}"
            if key in svg_inline_assets:
                media_data = svg_inline_assets[key]
                is_svg = True
            elif key in medias:
                media_data = medias[key]
                is_svg = media_data[:5] == b"<?xml" or b"<svg" in media_data[:200]

    # Clip-path selon mask_shape
    clip_id = None
    if item.mask_shape != "rect":
        clip_id = f"clip_{id(item) & 0xFFFF:04x}"
        clip_path = _shape_to_path(item.mask_shape, x, y, w, h, item.mask_extra)
        defs.append(f'<clipPath id="{clip_id}">{clip_path}/></clipPath>')

    clip_attr = f' clip-path="url(#{clip_id})"' if clip_id else ""
    transform = _transform_str(item, cx, cy)
    opacity = _opacity_attr(item)

    if media_data is None:
        # Placeholder : carré gris vide
        body.append(
            f'<rect x="{_mm(x)}" y="{_mm(y)}" width="{_mm(w)}" height="{_mm(h)}" '
            f'fill="rgb(230,230,235)" stroke="rgb(180,180,185)" stroke-width="0.3"'
            f'{transform}{opacity}/>'
        )
        return

    if is_svg:
        # Inline le <svg> reçu dans un <g> avec viewBox approprié
        svg_str = media_data.decode("utf-8", errors="replace")
        inner = _extract_svg_inner(svg_str)
        vb = _extract_svg_viewbox(svg_str) or "0 0 100 100"
        vb_parts = vb.split()
        vb_w = float(vb_parts[2]) if len(vb_parts) >= 4 else 100
        vb_h = float(vb_parts[3]) if len(vb_parts) >= 4 else 100
        sx = w / vb_w
        sy = h / vb_h
        s = min(sx, sy)  # contain par défaut pour vectoriel
        body.append(
            f'<g transform="translate({_mm(x)} {_mm(y)}) scale({s:.4f})"{clip_attr}{opacity}>'
            f'{inner}</g>'
        )
    else:
        # Bitmap : embed en base64
        b64 = base64.b64encode(media_data).decode("ascii")
        body.append(
            f'<image x="{_mm(x)}" y="{_mm(y)}" width="{_mm(w)}" height="{_mm(h)}" '
            f'href="data:image/png;base64,{b64}" preserveAspectRatio="xMidYMid slice"'
            f'{clip_attr}{transform}{opacity}/>'
        )


def _extract_svg_inner(svg_str: str) -> str:
    """Extrait le contenu entre <svg ...> et </svg> (sans la balise root)."""
    s = svg_str.strip()
    if s.startswith("<?xml"):
        s = s.split("?>", 1)[-1].lstrip()
    start = s.find(">")
    end = s.rfind("</svg>")
    if start < 0 or end < 0:
        return svg_str
    return s[start + 1:end]


def _extract_svg_viewbox(svg_str: str) -> Optional[str]:
    """Extrait l'attribut viewBox du <svg> root."""
    import re
    m = re.search(r'viewBox\s*=\s*"([^"]+)"', svg_str)
    if m:
        return m.group(1)
    return None


def _render_chart_item(item, bleed: float, defs: list, body: list) -> None:
    """ChartPlacement → primitives SVG natives (rect/circle/path/text)."""
    x = item.bbox.x + bleed
    y = item.bbox.y + bleed
    w, h = item.bbox.w, item.bbox.h
    colors = item.colors or _default_palette(len(item.values))

    if item.title:
        body.append(
            f'<text x="{_mm(x)}" y="{_mm(y + 4)}" font-size="3.5mm" '
            f'font-weight="600" fill="rgb(40,40,50)">{escape(item.title)}</text>'
        )
        chart_y = y + 8
        chart_h = h - 8
    else:
        chart_y = y
        chart_h = h

    n = len(item.values)
    max_v = max(item.values) if item.values else 1
    if max_v <= 0:
        max_v = 1

    if item.chart_type in ("bar", "column"):
        bar_w = w / (n * 1.4)
        gap = bar_w * 0.4
        for i, v in enumerate(item.values):
            bar_h = (v / max_v) * chart_h * 0.85
            bx = x + i * (bar_w + gap) + gap / 2
            by = chart_y + chart_h - bar_h
            col = _color_rgba(_obj_to_color(colors[i % len(colors)]))
            body.append(
                f'<rect x="{_mm(bx)}" y="{_mm(by)}" width="{_mm(bar_w)}" '
                f'height="{_mm(bar_h)}" fill="{col}" rx="0.5"/>'
            )
            if item.show_values:
                body.append(
                    f'<text x="{_mm(bx + bar_w / 2)}" y="{_mm(by - 1)}" '
                    f'font-size="2mm" text-anchor="middle" fill="rgb(60,60,70)">'
                    f'{v:g}{escape(item.unit)}</text>'
                )
            if i < len(item.labels):
                body.append(
                    f'<text x="{_mm(bx + bar_w / 2)}" y="{_mm(chart_y + chart_h + 3)}" '
                    f'font-size="2mm" text-anchor="middle" fill="rgb(80,80,90)">'
                    f'{escape(item.labels[i])}</text>'
                )

    elif item.chart_type in ("pie", "donut"):
        total = sum(item.values)
        if total <= 0:
            return
        cx, cy = x + w / 2, chart_y + chart_h / 2
        r = min(w, chart_h) / 2.4
        inner_r = r * 0.55 if item.chart_type == "donut" else 0
        angle_start = -math.pi / 2
        for i, v in enumerate(item.values):
            angle_end = angle_start + 2 * math.pi * (v / total)
            x1 = cx + r * math.cos(angle_start)
            y1 = cy + r * math.sin(angle_start)
            x2 = cx + r * math.cos(angle_end)
            y2 = cy + r * math.sin(angle_end)
            large_arc = 1 if (angle_end - angle_start) > math.pi else 0
            col = _color_rgba(_obj_to_color(colors[i % len(colors)]))
            if inner_r > 0:
                ix1 = cx + inner_r * math.cos(angle_end)
                iy1 = cy + inner_r * math.sin(angle_end)
                ix2 = cx + inner_r * math.cos(angle_start)
                iy2 = cy + inner_r * math.sin(angle_start)
                d = (f"M{x1:.3f},{y1:.3f} A{r:.3f},{r:.3f} 0 {large_arc},1 "
                     f"{x2:.3f},{y2:.3f} L{ix1:.3f},{iy1:.3f} "
                     f"A{inner_r:.3f},{inner_r:.3f} 0 {large_arc},0 "
                     f"{ix2:.3f},{iy2:.3f} Z")
            else:
                d = (f"M{cx:.3f},{cy:.3f} L{x1:.3f},{y1:.3f} "
                     f"A{r:.3f},{r:.3f} 0 {large_arc},1 {x2:.3f},{y2:.3f} Z")
            body.append(f'<path d="{d}" fill="{col}" stroke="white" stroke-width="0.3"/>')
            angle_start = angle_end

    elif item.chart_type in ("line", "area"):
        if n < 2:
            return
        step = w / (n - 1)
        pts = [(x + i * step, chart_y + chart_h - (v / max_v) * chart_h * 0.85)
               for i, v in enumerate(item.values)]
        col = _color_rgba(_obj_to_color(colors[0]))
        d = "M" + " L".join(f"{px:.3f},{py:.3f}" for px, py in pts)
        if item.chart_type == "area":
            d_area = (d + f" L{pts[-1][0]:.3f},{chart_y + chart_h:.3f} "
                      f"L{pts[0][0]:.3f},{chart_y + chart_h:.3f} Z")
            body.append(f'<path d="{d_area}" fill="{col}" fill-opacity="0.25"/>')
        body.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="0.6"/>')


def _default_palette(n: int) -> list:
    from types import SimpleNamespace
    base = [
        (66, 133, 244), (52, 168, 83), (251, 188, 4), (234, 67, 53),
        (156, 39, 176), (0, 188, 212), (255, 152, 0), (96, 125, 139),
    ]
    return [SimpleNamespace(r=r, g=g, b=b, a=1.0) for (r, g, b) in base[:max(1, n)]]


def _render_gradient_mesh_item(item, bleed: float, defs: list, body: list) -> None:
    """GradientMeshPlacement → SVG <filter feGaussianBlur> sur cercles colorés."""
    x = item.bbox.x + bleed
    y = item.bbox.y + bleed
    w, h = item.bbox.w, item.bbox.h

    fid = f"mesh_blur_{id(item) & 0xFFFF:04x}"
    defs.append(
        f'<filter id="{fid}" x="-20%" y="-20%" width="140%" height="140%">'
        f'<feGaussianBlur stdDeviation="{item.blur_mm:.2f}"/></filter>'
    )

    body.append(f'<g filter="url(#{fid})">')
    body.append(
        f'<rect x="{_mm(x)}" y="{_mm(y)}" width="{_mm(w)}" height="{_mm(h)}" '
        f'fill="{_color_rgba(item.base_color)}"/>'
    )
    for blob in item.blobs:
        bx = x + float(blob.get("x", 0.5)) * w
        by = y + float(blob.get("y", 0.5)) * h
        br = float(blob.get("radius", 0.3)) * min(w, h)
        col = _color_rgba(_obj_to_color(blob.get("color", {})))
        body.append(f'<circle cx="{_mm(bx)}" cy="{_mm(by)}" r="{_mm(br)}" fill="{col}"/>')
    body.append('</g>')


# ─── Entrée publique ───────────────────────────────────────────────────

def placement_plan_to_svg(plan, medias: dict | None = None,
                          svg_inline_assets: dict | None = None) -> bytes:
    """
    Convertit un PlacementPlan en SVG natif autonome.

    plan : PlacementPlan
    medias : dict[ref → bytes] (PNG/JPG bitmap OU SVG string)
    svg_inline_assets : dict[cache_key → svg bytes] (Recraft v3 SVG IA)

    Returns: bytes UTF-8 du document SVG complet.
    """
    medias = medias or {}
    bleed = plan.bleed_mm
    total_w = plan.page_w_mm + 2 * bleed
    total_h = plan.page_h_mm + 2 * bleed

    defs: list[str] = []
    body: list[str] = []

    # Background
    _render_background(plan.background, plan.page_w_mm, plan.page_h_mm,
                       bleed, defs, body)

    # Items triés par z_index
    items = sorted(plan.items, key=lambda it: getattr(it, "z_index", 0))
    for item in items:
        kind = getattr(item, "kind", None) or (
            item.get("kind") if isinstance(item, dict) else None
        )
        try:
            if kind == "shape":
                _render_shape_item(item, bleed, defs, body)
            elif kind == "text":
                _render_text_item(item, bleed, defs, body)
            elif kind == "image":
                _render_image_item(item, bleed, medias, defs, body,
                                   svg_inline_assets=svg_inline_assets)
            elif kind == "chart":
                _render_chart_item(item, bleed, defs, body)
            elif kind == "gradient_mesh":
                _render_gradient_mesh_item(item, bleed, defs, body)
            elif kind == "mockup":
                logger.debug("Mockup non vectorisé en SVG — fallback raster requis")
            else:
                logger.debug(f"Type item inconnu en SVG : {kind}")
        except Exception as e:
            logger.warning(f"[SVG] Erreur rendu item {kind} : {e}")

    defs_xml = "\n".join(defs)
    body_xml = "\n".join(body)

    svg = (
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" version="1.1" '
        f'width="{_mm(total_w)}mm" height="{_mm(total_h)}mm" '
        f'viewBox="0 0 {_mm(total_w)} {_mm(total_h)}">\n'
        f'<defs>{defs_xml}</defs>\n'
        f'{body_xml}\n'
        '</svg>\n'
    )
    return svg.encode("utf-8")
