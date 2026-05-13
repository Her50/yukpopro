"""
Slides Web Builder — Présentations Reveal.js interactives autonomes.

Sortie HTML single-file (Reveal.js 4.6 via CDN jsdelivr) avec :

  • Navigation clavier (← → flèches, espace, esc pour overview)
  • Transitions fade/slide/zoom/convex/concave/none
  • Speaker notes (touche S)
  • Plein écran (touche F)
  • Mode présentateur (touche S)
  • Export PDF auto (?print-pdf à la fin de l'URL)
  • Animations CSS fragments (apparitions séquentielles d'éléments)
  • Code highlight (Prism via Reveal plugin)
  • Math LaTeX (KaTeX)
  • Iframe embeds (vidéos, sites)

Complémentaire à slide_builder_pro.py (PPTX statique). Cas d'usage :
  • Pitch investisseur partageable URL (vs envoi PPTX 50MB)
  • Formation publique web (cours en ligne, atelier)
  • Conférence avec partage live
  • Catalogue interactif client (parcours guidé)
  • Lecteur preview dans le chat avant download PPTX
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from html import escape
from typing import Optional

logger = logging.getLogger("yukpo_assurance.pro.slides_web")


# ── Thèmes (cohérents avec slide_builder_pro.py PPTX) ─────────────────────────

THEMES = {
    "corporate": {
        "primary": "#0A2A4A", "secondary": "#1C4E80", "accent": "#D4AF37",
        "bg": "#FFFFFF", "text": "#0A2A4A", "muted": "#445A70",
        "font_titre": "Playfair Display, Georgia, serif",
        "font_corps": "Inter, system-ui, sans-serif",
        "transition": "slide",
    },
    "pitch": {
        "primary": "#1A1A2E", "secondary": "#16213E", "accent": "#E94F37",
        "bg": "#0D0D17", "text": "#FFFFFF", "muted": "#9CA3AF",
        "font_titre": "Bebas Neue, Impact, sans-serif",
        "font_corps": "Inter, system-ui, sans-serif",
        "transition": "zoom",
    },
    "finance": {
        "primary": "#004D40", "secondary": "#006957", "accent": "#00BF6F",
        "bg": "#F4FBF7", "text": "#004D40", "muted": "#3D5A47",
        "font_titre": "Inter, system-ui, sans-serif",
        "font_corps": "Inter, system-ui, sans-serif",
        "transition": "convex",
    },
    "formation": {
        "primary": "#006EB6", "secondary": "#0085D9", "accent": "#FFB400",
        "bg": "#FFFFFF", "text": "#0F2742", "muted": "#5A6C84",
        "font_titre": "Inter, system-ui, sans-serif",
        "font_corps": "Inter, system-ui, sans-serif",
        "transition": "slide",
    },
}


def _theme_pour_type(type_pres: str) -> str:
    mapping = {
        "bilan_activite": "corporate",
        "rapport_direction": "corporate",
        "proposition_client": "pitch",
        "pitch_projet": "pitch",
        "formation": "formation",
        "analyse_marche": "finance",
        "rapport_financier": "finance",
    }
    return mapping.get(type_pres, "corporate")


# ── Prompt LLM : structure JSON des slides ────────────────────────────────────

_PROMPT_SYSTEME = """Tu es un graphiste & speechwriter expert qui crée des présentations \
web interactives Reveal.js professionnelles, avec une narration ciselée.

Tu reçois : sujet + type + mode + contexte + (optionnellement) BrandKit.

Tu RENVOIES UN JSON strict (pas de texte avant/après) :

{
  "titre": "Titre principal (max 80 chars)",
  "sous_titre": "Sous-titre court (max 120 chars)",
  "auteur": "Auteur / société (optionnel)",
  "date": "Date d'usage (optionnel, format libre)",
  "theme_pref": "corporate | pitch | finance | formation",
  "slides": [
    {
      "type": "cover | section | content | image_full | quote | kpi | comparaison | timeline | citation | qa | merci",
      "titre": "Titre slide (max 100)",
      "sous_titre": "Optionnel",
      "contenu": "Markdown supporté (listes, **gras**, *italique*, [lien](url), `code`, > citation)",
      "image_prompt": "Si type=image_full ou besoin hero : description EN pour Flux/Recraft 30-60 mots",
      "image_position": "left | right | full | top | bottom",
      "kpis": [
        {"valeur": "+42%", "label": "Croissance YoY", "icone": "📈"}
      ],
      "comparaison": [
        {"titre": "Avant", "items": ["…"]},
        {"titre": "Après",  "items": ["…"]}
      ],
      "timeline": [
        {"date": "Q1 2026", "titre": "Lancement", "details": "…"}
      ],
      "citation": {"texte": "…", "auteur": "…"},
      "notes_orateur": "Notes pour l'orateur (touche S pendant la présentation)",
      "fragments": true
    }
  ]
}

Règles :
1. Mode "executive" = 5-8 slides ; "detaille" = 15-25 ; "pitch" = 10-15 ; "expert" = 25-40
2. Toujours 1 slide cover en premier et 1 slide merci/Q&A en dernier
3. Pour "pitch_projet" : intègre problème, solution, marché, business model, traction, équipe, demande
4. Pour "rapport_direction" : exec summary, contexte, indicateurs, faits marquants, décisions, plan
5. Pour "formation" : objectifs, prérequis, sections numérotées, exercices, récap
6. fragments=true sur slides avec listes → apparition séquentielle (impact)
7. notes_orateur substantielles (50-200 mots) pour aider la prés en live
8. Brand-aware : si BrandKit fourni, intègre la palette et les polices via theme_pref
9. Langue : utilise EXACTEMENT la langue de l'utilisateur (sujet/contexte)
"""


async def generer_specification_slides_web(
    sujet: str,
    type_pres: str = "rapport_direction",
    mode: str = "executive",
    contexte: Optional[str] = None,
    donnees: Optional[dict] = None,
    brand_kit: Optional[dict] = None,
    langue: str = "fr",
) -> tuple[dict, dict]:
    """LLM Sonnet → spec JSON des slides. Retourne (spec, usage_llm)."""
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire

    user_prompt = (
        f"SUJET : {sujet}\n"
        f"TYPE_PRES : {type_pres}\n"
        f"MODE : {mode}\n"
        f"LANGUE : {langue}\n"
    )
    if contexte:
        user_prompt += f"CONTEXTE : {contexte[:2000]}\n"
    if donnees:
        user_prompt += f"DONNÉES : {json.dumps(donnees, ensure_ascii=False)[:3000]}\n"
    if brand_kit:
        user_prompt += f"BRAND_KIT : {json.dumps(brand_kit, ensure_ascii=False)[:1500]}\n"
    user_prompt += "\nProduis le JSON spec strict."

    rep = await ia_client.appeler(
        messages=[
            {"role": "system", "content": _PROMPT_SYSTEME},
            {"role": "user",   "content": user_prompt},
        ],
        mode=ModeIA.QUALITE,
        modele_prioritaire=ModelePrioritaire.CLAUDE_SONNET,
        max_tokens=8000,
        temperature=0.6,
    )
    texte = rep.contenu if hasattr(rep, "contenu") else str(rep)
    # Extraction du premier objet JSON
    m = re.search(r"\{[\s\S]*\}", texte)
    if not m:
        raise ValueError("LLM n'a pas produit de JSON parseable")
    spec = json.loads(m.group(0))
    usage = {
        "tokens_in":  getattr(rep, "tokens_input", 0),
        "tokens_out": getattr(rep, "tokens_output", 0),
        "modele":     getattr(rep, "modele_utilise", "sonnet"),
    }
    return spec, usage


# ── Rendu HTML Reveal.js ──────────────────────────────────────────────────────

def _md_inline(text: str) -> str:
    """Markdown inline minimal (gras, italique, code, lien) en HTML."""
    if not text:
        return ""
    s = escape(text)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
               r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    return s


def _md_block(text: str) -> str:
    """Markdown block : listes, paragraphes, citations."""
    if not text:
        return ""
    lines = text.split("\n")
    out = []
    in_ul = False
    in_ol = False
    for line in lines:
        line = line.rstrip()
        if not line:
            if in_ul:
                out.append("</ul>"); in_ul = False
            if in_ol:
                out.append("</ol>"); in_ol = False
            continue
        if line.startswith("- ") or line.startswith("* "):
            if not in_ul:
                if in_ol:
                    out.append("</ol>"); in_ol = False
                out.append("<ul>"); in_ul = True
            out.append(f'<li class="fragment fade-up">{_md_inline(line[2:])}</li>')
        elif re.match(r"^\d+\.\s", line):
            if not in_ol:
                if in_ul:
                    out.append("</ul>"); in_ul = False
                out.append("<ol>"); in_ol = True
            out.append(f'<li class="fragment fade-up">{_md_inline(re.sub(r"^\d+\.\s", "", line))}</li>')
        elif line.startswith("> "):
            out.append(f'<blockquote>{_md_inline(line[2:])}</blockquote>')
        elif line.startswith("# "):
            out.append(f"<h2>{_md_inline(line[2:])}</h2>")
        elif line.startswith("## "):
            out.append(f"<h3>{_md_inline(line[3:])}</h3>")
        else:
            out.append(f"<p>{_md_inline(line)}</p>")
    if in_ul:
        out.append("</ul>")
    if in_ol:
        out.append("</ol>")
    return "\n".join(out)


def _render_slide_section(slide: dict, idx: int, theme: dict) -> str:
    """Une slide → une <section> Reveal.js."""
    t = slide.get("type", "content")
    titre = escape(slide.get("titre") or "")
    sous_titre = escape(slide.get("sous_titre") or "")
    contenu = slide.get("contenu") or ""
    notes = slide.get("notes_orateur") or ""

    notes_xml = (
        f'<aside class="notes">{_md_block(notes)}</aside>' if notes else ""
    )

    if t == "cover":
        return (
            f'<section class="cover" data-background-color="{theme["primary"]}">'
            f'<div class="cover-inner">'
            f'<h1 class="big-title">{titre}</h1>'
            f'{f"<p class=subtitle>{sous_titre}</p>" if sous_titre else ""}'
            f"{_md_block(contenu)}"
            f"</div>{notes_xml}</section>"
        )

    if t == "section":
        return (
            f'<section data-background-color="{theme["secondary"]}">'
            f'<h2 class="section-divider">{titre}</h2>'
            f'{f"<p class=subtitle>{sous_titre}</p>" if sous_titre else ""}'
            f"{notes_xml}</section>"
        )

    if t == "image_full":
        img_url = slide.get("_image_url", "")
        bg_img = f' data-background-image="{escape(img_url)}"' if img_url else ""
        return (
            f'<section class="image-full"{bg_img} data-background-size="cover">'
            f'<div class="overlay">'
            f"<h2>{titre}</h2>"
            f"{_md_block(contenu)}"
            f"</div>{notes_xml}</section>"
        )

    if t == "quote" or t == "citation":
        c = slide.get("citation") or {}
        return (
            f'<section class="quote-slide">'
            f'<blockquote class="big-quote">"{escape(c.get("texte") or contenu)}"</blockquote>'
            f'<p class="quote-author">— {escape(c.get("auteur") or "")}</p>'
            f"{notes_xml}</section>"
        )

    if t == "kpi":
        kpis = slide.get("kpis") or []
        kpi_html = "".join(
            f'<div class="kpi-card fragment fade-up">'
            f'<div class="kpi-icon">{escape(k.get("icone", "📊"))}</div>'
            f'<div class="kpi-value">{escape(k.get("valeur", ""))}</div>'
            f'<div class="kpi-label">{escape(k.get("label", ""))}</div>'
            f'</div>'
            for k in kpis
        )
        return (
            f'<section class="kpi-slide"><h2>{titre}</h2>'
            f'<div class="kpi-grid">{kpi_html}</div>{notes_xml}</section>'
        )

    if t == "comparaison":
        cols = slide.get("comparaison") or []
        cols_html = "".join(
            f'<div class="comp-col fragment fade-up">'
            f'<h3>{escape(c.get("titre", ""))}</h3>'
            f'<ul>{"".join(f"<li>{_md_inline(i)}</li>" for i in c.get("items", []))}</ul>'
            f'</div>'
            for c in cols
        )
        return (
            f'<section class="comparaison-slide"><h2>{titre}</h2>'
            f'<div class="comp-grid">{cols_html}</div>{notes_xml}</section>'
        )

    if t == "timeline":
        ev = slide.get("timeline") or []
        items_html = "".join(
            f'<div class="tl-item fragment fade-right">'
            f'<div class="tl-date">{escape(e.get("date", ""))}</div>'
            f'<div class="tl-body"><strong>{escape(e.get("titre", ""))}</strong>'
            f'<p>{_md_inline(e.get("details", ""))}</p></div></div>'
            for e in ev
        )
        return (
            f'<section class="timeline-slide"><h2>{titre}</h2>'
            f'<div class="timeline">{items_html}</div>{notes_xml}</section>'
        )

    if t == "qa" or t == "merci":
        return (
            f'<section data-background-color="{theme["primary"]}" class="merci">'
            f'<h1>{titre or "Merci"}</h1>'
            f'{f"<p class=subtitle>{sous_titre}</p>" if sous_titre else ""}'
            f"{_md_block(contenu)}"
            f"{notes_xml}</section>"
        )

    # Type "content" par défaut
    img_pos = slide.get("image_position") or "right"
    img_url = slide.get("_image_url") or ""
    if img_url and img_pos in ("left", "right"):
        img_html = f'<div class="img-side"><img src="{escape(img_url)}" alt=""></div>'
        body = f"<div class='txt-side'>{_md_block(contenu)}</div>"
        order = (img_html + body) if img_pos == "left" else (body + img_html)
        return (
            f'<section class="content-2col"><h2>{titre}</h2>'
            f'<div class="two-col">{order}</div>{notes_xml}</section>'
        )

    return (
        f'<section class="content-slide"><h2>{titre}</h2>'
        f'{f"<p class=subtitle>{sous_titre}</p>" if sous_titre else ""}'
        f"{_md_block(contenu)}{notes_xml}</section>"
    )


def construire_html_revealjs(spec: dict, brand_kit: Optional[dict] = None) -> str:
    """Construit le HTML Reveal.js standalone à partir de la spec JSON."""
    theme_name = spec.get("theme_pref") or "corporate"
    if theme_name not in THEMES:
        theme_name = "corporate"
    theme = dict(THEMES[theme_name])

    # Override BrandKit
    if brand_kit:
        if brand_kit.get("primary_color"):
            theme["primary"] = brand_kit["primary_color"]
        if brand_kit.get("accent_color"):
            theme["accent"] = brand_kit["accent_color"]
        if brand_kit.get("font_corps"):
            theme["font_corps"] = brand_kit["font_corps"]
        if brand_kit.get("font_titre"):
            theme["font_titre"] = brand_kit["font_titre"]

    sections = "\n".join(
        _render_slide_section(s, i, theme)
        for i, s in enumerate(spec.get("slides", []))
    )

    titre_doc = escape(spec.get("titre") or "Présentation")
    auteur = escape(spec.get("auteur") or "")
    date = escape(spec.get("date") or datetime.utcnow().strftime("%d/%m/%Y"))

    # CSS theme injecté inline (variables CSS)
    css_vars = (
        f"--primary:{theme['primary']};"
        f"--secondary:{theme['secondary']};"
        f"--accent:{theme['accent']};"
        f"--bg:{theme['bg']};"
        f"--text:{theme['text']};"
        f"--muted:{theme['muted']};"
        f"--font-titre:{theme['font_titre']};"
        f"--font-corps:{theme['font_corps']};"
    )

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{titre_doc}</title>
<meta name="author" content="{auteur}">
<meta name="generator" content="Yukpo Slides Web Builder">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@4.6.0/dist/reveal.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@4.6.0/dist/theme/white.css" id="theme">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@4.6.0/plugin/highlight/monokai.css">
<style>
:root {{ {css_vars} }}
.reveal {{ font-family: var(--font-corps); color: var(--text); }}
.reveal h1, .reveal h2, .reveal h3, .reveal h4 {{ font-family: var(--font-titre); color: var(--primary); text-transform: none; }}
.reveal h1 {{ font-size: 2.4em; font-weight: 800; }}
.reveal h2 {{ font-size: 1.8em; font-weight: 700; border-bottom: 3px solid var(--accent); padding-bottom: 0.2em; margin-bottom: 0.6em; }}
.reveal a {{ color: var(--accent); }}
.reveal ul li, .reveal ol li {{ margin: 0.4em 0; }}
.reveal blockquote {{ border-left: 4px solid var(--accent); padding-left: 1em; font-style: italic; color: var(--muted); }}
.cover {{ color: white; }}
.cover h1, .cover h2 {{ color: white; }}
.big-title {{ font-size: 3em; line-height: 1.1; margin-bottom: 0.3em; }}
.subtitle {{ font-size: 1.2em; color: var(--muted); margin-top: 0.5em; }}
.cover .subtitle {{ color: rgba(255,255,255,0.85); }}
.section-divider {{ color: white; font-size: 2.5em; border: none; }}
.merci h1 {{ color: white; font-size: 3.5em; }}
.merci .subtitle {{ color: rgba(255,255,255,0.9); }}
.image-full .overlay {{ background: rgba(0,0,0,0.55); padding: 2em; color: white; border-radius: 8px; }}
.image-full h2 {{ color: white; border-bottom-color: var(--accent); }}
.big-quote {{ font-size: 1.8em; font-style: italic; line-height: 1.35; color: var(--primary); border: none; }}
.quote-author {{ font-size: 1em; color: var(--muted); margin-top: 1em; }}
.kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1.5em; }}
.kpi-card {{ background: var(--bg); border: 2px solid var(--accent); border-radius: 12px; padding: 1.5em; text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
.kpi-icon {{ font-size: 2em; margin-bottom: 0.3em; }}
.kpi-value {{ font-size: 2.4em; font-weight: 800; color: var(--primary); line-height: 1; }}
.kpi-label {{ color: var(--muted); margin-top: 0.4em; font-size: 0.9em; }}
.comp-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2em; }}
.comp-col {{ background: rgba(0,0,0,0.04); border-radius: 10px; padding: 1.2em; }}
.comp-col h3 {{ color: var(--accent); border-bottom: 2px solid var(--primary); }}
.timeline {{ position: relative; padding-left: 30px; }}
.timeline::before {{ content: ""; position: absolute; left: 8px; top: 0; bottom: 0; width: 3px; background: var(--accent); }}
.tl-item {{ position: relative; margin-bottom: 1.5em; }}
.tl-item::before {{ content: ""; position: absolute; left: -28px; top: 6px; width: 14px; height: 14px; border-radius: 50%; background: var(--accent); border: 3px solid var(--bg); }}
.tl-date {{ font-weight: 700; color: var(--primary); }}
.tl-body {{ color: var(--text); }}
.two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2em; align-items: center; }}
.img-side img {{ max-width: 100%; border-radius: 10px; box-shadow: 0 6px 20px rgba(0,0,0,0.15); }}
.txt-side {{ font-size: 0.95em; line-height: 1.5; }}
.reveal pre code {{ border-radius: 8px; padding: 1em; }}
.reveal .footer {{ position: fixed; bottom: 10px; right: 20px; font-size: 0.75em; color: var(--muted); z-index: 100; }}
</style>
</head>
<body>
<div class="reveal">
  <div class="slides">
{sections}
  </div>
  <div class="footer">{auteur} · {date}</div>
</div>
<script src="https://cdn.jsdelivr.net/npm/reveal.js@4.6.0/dist/reveal.js"></script>
<script src="https://cdn.jsdelivr.net/npm/reveal.js@4.6.0/plugin/notes/notes.js"></script>
<script src="https://cdn.jsdelivr.net/npm/reveal.js@4.6.0/plugin/highlight/highlight.js"></script>
<script src="https://cdn.jsdelivr.net/npm/reveal.js@4.6.0/plugin/markdown/markdown.js"></script>
<script src="https://cdn.jsdelivr.net/npm/reveal.js@4.6.0/plugin/zoom/zoom.js"></script>
<script>
Reveal.initialize({{
  hash: true,
  controls: true,
  progress: true,
  history: false,
  center: true,
  transition: "{theme['transition']}",
  backgroundTransition: "fade",
  pdfMaxPagesPerSlide: 1,
  plugins: [RevealNotes, RevealHighlight, RevealMarkdown, RevealZoom]
}});
</script>
</body>
</html>
"""


# ── Pipeline complet ──────────────────────────────────────────────────────────

async def generer_slides_web(
    sujet: str,
    type_pres: str = "rapport_direction",
    mode: str = "executive",
    contexte: Optional[str] = None,
    donnees: Optional[dict] = None,
    brand_kit: Optional[dict] = None,
    langue: str = "fr",
    generer_images_hero: bool = True,
) -> tuple[bytes, dict, list[dict]]:
    """
    Pipeline complet : LLM spec → image gen (optionnel) → HTML Reveal.js.

    Retourne (html_bytes, spec_finale, usages_llm).
    """
    spec, usage_spec = await generer_specification_slides_web(
        sujet=sujet, type_pres=type_pres, mode=mode,
        contexte=contexte, donnees=donnees, brand_kit=brand_kit, langue=langue,
    )
    usages = [{**usage_spec, "etape": "spec_slides_web"}]

    # Génération images hero (uniquement slides avec image_prompt explicite)
    if generer_images_hero:
        from modules.bureau import image_gen as _ig
        import base64
        for slide in spec.get("slides", []):
            prompt_img = slide.get("image_prompt")
            if not prompt_img:
                continue
            try:
                fmt = "landscape_16_9" if slide.get("type") == "image_full" else "landscape_4_3"
                png = await _ig.generer_image(
                    prompt=prompt_img, mode="premium",
                    format_=fmt, timeout_s=90.0,
                )
                if png:
                    slide["_image_url"] = "data:image/png;base64," + base64.b64encode(png).decode()
            except Exception as e:
                logger.warning(f"[SlidesWeb/hero] image_prompt échec : {e}")

    # Force le theme depuis brand_kit si fourni (override LLM)
    if brand_kit and brand_kit.get("theme_force"):
        spec["theme_pref"] = brand_kit["theme_force"]
    elif not spec.get("theme_pref"):
        spec["theme_pref"] = _theme_pour_type(type_pres)

    html = construire_html_revealjs(spec, brand_kit=brand_kit)
    return html.encode("utf-8"), spec, usages
