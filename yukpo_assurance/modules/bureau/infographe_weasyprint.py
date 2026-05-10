"""
Sprint 1.4 — Moteur de rendu alternatif WeasyPrint (HTML/CSS3 → PDF).

Pourquoi WeasyPrint en complément de ReportLab :
  - CSS3 print-ready : grid, flexbox, transforms, gradients radiaux/coniques,
    blend-modes, border-radius arbitraires, mix-blend-mode, etc.
  - Compositions modernes natives (bento, asymétrique, fullbleed cinema)
  - Animations CSS print sur les overlays
  - LLM peut générer directement du HTML+CSS dynamique → flexibilité maximale
  - Print CMJN possible via Ghostscript (post-traitement)

Limites :
  - Plus lent que ReportLab (≈3-5×, ~2s/page A4 vs 0.5s)
  - Deps système Cairo/Pango (pas dispo Windows local sans MSYS2)
  - Pas de fallback Windows : import gracieux (try/except), endpoint 503 sinon

Usage :
  pdf_bytes = rendre_html_to_pdf(html, css="...", base_url="...")
  ou via endpoint POST /bureau/infographie-pro/render-html

Coexiste avec infographe.py (mono-page ReportLab) et infographe_pro.py
(multi-page ReportLab). N'écrase rien.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("yukpo_assurance.bureau.infographe_weasyprint")

# Import gracieux : sur Windows local sans Cairo/Pango, weasyprint échoue à
# l'import. On laisse l'app démarrer normalement et l'endpoint retourne 503.
try:
    from weasyprint import HTML, CSS
    _WEASYPRINT_AVAILABLE = True
except Exception as e:
    HTML = None  # type: ignore
    CSS = None  # type: ignore
    _WEASYPRINT_AVAILABLE = False
    logger.info(f"[WeasyPrint] indisponible (mode dégradé) : {e}")


def is_available() -> bool:
    """True si WeasyPrint est utilisable (libs Cairo/Pango présentes)."""
    return _WEASYPRINT_AVAILABLE


# ─── Sprint TOP 5 — Typographie LaTeX-quality (preset CSS global) ────────────
#
# CSS injecté en complément des stylesheets utilisateur. Active :
#   - Polices Inter (Google Fonts CDN, fallback Liberation Sans / Calibri)
#   - OpenType features : kern (crénage), liga (ligatures), pnum (chiffres
#     proportionnels), onum (chiffres bas-de-casse), tnum optionnel.
#   - Césure auto (hyphens: auto) — réduit drastiquement les rivières blanches
#     en justification.
#   - Veuves / orphelines (widows: 3, orphans: 3) — évite les paragraphes
#     coupés à 1 ligne en bas/haut de page.
#   - text-rendering: geometricPrecision pour le print pro.
#
# Critère McKinsey/BCG : pas de césure forcée, pas de veuves/orphelines, pas
# de chiffres tabulaires en plein corps de texte. Niveau Adobe InDesign.
TYPO_PRESET_CSS = """
@font-face {
  font-family: 'Inter';
  font-weight: 400;
  font-style: normal;
  src: url('https://rsms.me/inter/font-files/Inter-Regular.woff2') format('woff2');
  font-display: swap;
}
@font-face {
  font-family: 'Inter';
  font-weight: 600;
  font-style: normal;
  src: url('https://rsms.me/inter/font-files/Inter-SemiBold.woff2') format('woff2');
  font-display: swap;
}
@font-face {
  font-family: 'Inter';
  font-weight: 700;
  font-style: normal;
  src: url('https://rsms.me/inter/font-files/Inter-Bold.woff2') format('woff2');
  font-display: swap;
}
@font-face {
  font-family: 'Inter';
  font-weight: 900;
  font-style: normal;
  src: url('https://rsms.me/inter/font-files/Inter-Black.woff2') format('woff2');
  font-display: swap;
}

html, body {
  font-family: 'Inter', 'Liberation Sans', 'Calibri', 'DejaVu Sans', sans-serif;
  font-feature-settings: 'kern' 1, 'liga' 1, 'pnum' 1, 'ss01' 1;
  text-rendering: geometricPrecision;
  -webkit-font-smoothing: antialiased;
}
p, li, td {
  hyphens: auto;
  -webkit-hyphens: auto;
  hyphenate-limit-chars: 6 3 2;  /* min 6 chars / 3 avant / 2 après césure */
  text-align: justify;
  text-justify: inter-word;
  widows: 3;
  orphans: 3;
}
h1, h2, h3, h4, h5, h6 {
  page-break-after: avoid;
  page-break-inside: avoid;
  hyphens: none;
  letter-spacing: -0.01em;
  font-feature-settings: 'kern' 1, 'liga' 1;
}
table, figure, img {
  page-break-inside: avoid;
}
.numbers, .kpi, .tabular {
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum' 1;
}
"""


def rendre_html_to_pdf(
    html: str,
    css: Optional[str] = None,
    base_url: Optional[str] = None,
    presentational_hints: bool = True,
    cmyk: bool = False,
    icc_name: str = "fogra39",
) -> bytes:
    """
    Rasterise du HTML+CSS en PDF via WeasyPrint.

    `html`  : document HTML complet (avec <html>, <head>, <body>) ou fragment.
    `css`   : feuille de styles additionnelle (concat à <style> embedded).
    `base_url` : pour résoudre les URLs relatives (images, fonts, etc.).
                 Mettre une URL https:// pour télécharger des assets externes.
    `presentational_hints` : True pour respecter <font color>, <table border>...
    `cmyk`  : Gap #9 — si True, post-traite via Ghostscript pour conversion
              RGB → CMYK avec profil ICC (FOGRA39 par défaut). PDF
              imprimerie-ready (offset/numérique grand volume). Si gs absent
              (env Windows local), retourne le PDF RGB original.
    `icc_name` : 'fogra39' | 'psocoated_v3' | 'gracol_us' (cf. pdf_print_ready)

    Lève ImportError si WeasyPrint n'est pas dispo (Windows local).
    """
    if not _WEASYPRINT_AVAILABLE:
        raise ImportError(
            "WeasyPrint n'est pas installé sur cet environnement. "
            "Installer Cairo + Pango + GDK-PixBuf, ou déployer sur Linux."
        )
    # Sprint TOP 5 — typo preset injecté EN PREMIER (le HTML utilisateur le
    # surcharge ensuite si besoin). Inter font-face, kern+liga+pnum, hyphens,
    # widows/orphans → niveau Adobe InDesign sur tous les rendus.
    stylesheets = [CSS(string=TYPO_PRESET_CSS)]
    if css:
        stylesheets.append(CSS(string=css))
    pdf_bytes = HTML(string=html, base_url=base_url).write_pdf(
        stylesheets=stylesheets,
        presentational_hints=presentational_hints,
    )

    if cmyk:
        try:
            from .pdf_print_ready import convertir_rgb_to_cmyk
            cmyk_bytes = convertir_rgb_to_cmyk(pdf_bytes, icc_name=icc_name)
            if cmyk_bytes:
                return cmyk_bytes
            logger.info("[WeasyPrint] CMYK indispo (gs ou ICC absent) — RGB conservé")
        except Exception as e:
            logger.warning(f"[WeasyPrint] CMYK post-traitement KO : {e}")
    return pdf_bytes


# ─── Templates HTML/CSS3 démos (Sprint 1.4) ───────────────────────────────────
#
# Ces templates servent de référence pour le LLM (Opus art director) qui
# pourra générer du HTML/CSS custom inspiré de ces structures, et au moteur
# de rendu d'avoir des layouts SOTA prêts à l'emploi.
#
# Composition disponibles : bento, asymetric, fullbleed_cover, timeline_horiz.

BENTO_DEMO_HTML = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<title>{titre}</title>
<style>
  @page {{
    size: {format_w}mm {format_h}mm;
    margin: 0;
    bleed: 3mm;
    marks: crop;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Liberation Sans', 'DejaVu Sans', 'Inter', sans-serif;
    color: {color_text};
    background: {color_bg};
    font-feature-settings: 'kern', 'liga', 'pnum';
    width: {format_w}mm; height: {format_h}mm;
  }}
  .grid {{
    display: grid;
    width: 100%; height: 100%;
    grid-template-columns: 1fr 1fr 1fr;
    grid-template-rows: 1.5fr 1fr 1fr;
    gap: 4mm;
    padding: 8mm;
  }}
  .card {{
    background: {color_card};
    border-radius: 4mm;
    padding: 6mm;
    overflow: hidden;
    position: relative;
  }}
  .card.hero {{
    grid-column: 1 / span 2;
    grid-row: 1 / span 2;
    background: linear-gradient(135deg, {color_primary} 0%, {color_accent} 100%);
    color: white;
  }}
  .card.tag {{ background: {color_primary}; color: white; }}
  .card h1 {{ font-size: 32pt; font-weight: 800; line-height: 1.05; letter-spacing: -0.02em; }}
  .card h2 {{ font-size: 16pt; font-weight: 700; margin-bottom: 2mm; }}
  .card p {{ font-size: 9pt; line-height: 1.5; opacity: 0.9; }}
  .card .num {{ font-size: 48pt; font-weight: 900; opacity: 0.15; position: absolute; bottom: -4mm; right: 2mm; }}
  .card.cta {{
    grid-column: 3; grid-row: 3;
    background: {color_accent};
    color: white;
    display: flex; align-items: center; justify-content: center;
    text-align: center; font-weight: 700; font-size: 11pt;
  }}
</style>
</head>
<body>
<div class="grid">
  <div class="card hero">
    <h1>{titre}</h1>
    <p style="margin-top: 6mm; font-size: 11pt;">{accroche}</p>
  </div>
  <div class="card tag">
    <h2>{kpi1_label}</h2>
    <div style="font-size: 36pt; font-weight: 900; line-height: 1;">{kpi1_value}</div>
    <span class="num">01</span>
  </div>
  <div class="card">
    <h2>{kpi2_label}</h2>
    <div style="font-size: 36pt; font-weight: 900; color: {color_primary}; line-height: 1;">{kpi2_value}</div>
    <span class="num">02</span>
  </div>
  <div class="card">
    <h2>{section3_titre}</h2>
    <p>{section3_texte}</p>
  </div>
  <div class="card cta">{cta}</div>
</div>
</body>
</html>"""


def render_bento_demo(
    titre: str = "Yukpo Designer Pro",
    accroche: str = "Visuels brand-compliant en 2 minutes, niveau Adobe/Canva.",
    kpi1_label: str = "Crédits",
    kpi1_value: str = "10K",
    kpi2_label: str = "Pages/min",
    kpi2_value: str = "120",
    section3_titre: str = "Multi-format",
    section3_texte: str = "Flyer, brochure, livret, faire-part, banderole — un moteur, tous les formats CIMA-ready.",
    cta: str = "Démarrer →",
    color_bg: str = "#0f172a",
    color_text: str = "#e2e8f0",
    color_card: str = "#1e293b",
    color_primary: str = "#7c3aed",
    color_accent: str = "#ec4899",
    format_w: int = 210, format_h: int = 297, lang: str = "fr",
) -> bytes:
    """Rend la composition demo bento (A4 portrait par défaut)."""
    html = BENTO_DEMO_HTML.format(
        titre=titre, accroche=accroche,
        kpi1_label=kpi1_label, kpi1_value=kpi1_value,
        kpi2_label=kpi2_label, kpi2_value=kpi2_value,
        section3_titre=section3_titre, section3_texte=section3_texte,
        cta=cta,
        color_bg=color_bg, color_text=color_text, color_card=color_card,
        color_primary=color_primary, color_accent=color_accent,
        format_w=format_w, format_h=format_h, lang=lang,
    )
    return rendre_html_to_pdf(html)
