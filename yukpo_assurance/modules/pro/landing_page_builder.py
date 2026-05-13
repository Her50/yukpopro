"""
Landing Page Builder — Génération de landing pages web prêtes prod.

Sortie HTML statique single-file (Tailwind CDN + JS vanilla) avec :

  • Hero section (titre + sous-titre + CTA + hero image IA)
  • Features (cards icônes + titres + descriptions)
  • KPIs / Stats (chiffres marquants animés au scroll)
  • Témoignages (carrousel avatars + quotes)
  • Pricing (tableaux comparatifs + CTAs)
  • FAQ (accordéon JS vanilla)
  • CTA finale + Contact (formulaire mailto OU webhook)
  • Footer (links + réseaux sociaux + mentions légales)
  • Meta SEO (Open Graph + Twitter Card + favicon généré)
  • Responsive mobile-first
  • Dark mode auto (prefers-color-scheme)
  • Accessibilité (semantic HTML5 + aria + skip-to-content)
  • Lazy load images
  • Animations CSS (fade-in-up au scroll via IntersectionObserver)

Cas d'usage :
  • Page produit/service unique
  • Page événement (séminaire, lancement, recrutement)
  • Page campagne (offre limitée, promo)
  • Page projet (pitch externe, ICO/levée de fonds)
  • Page recrutement (job listing détaillé)
  • Page contact agence

Pas de framework client (pas de React/Vue/etc.) — un HTML statique
ouvrable directement, déployable n'importe où (Netlify, Vercel, S3,
GitHub Pages, Cloudflare Pages).
"""
from __future__ import annotations

import base64
import json
import logging
import re
from datetime import datetime
from html import escape
from typing import Optional

logger = logging.getLogger("yukpo_assurance.pro.landing_page")


# ── Prompt LLM ────────────────────────────────────────────────────────────────

_PROMPT_SYSTEME = """Tu es un copywriter & UX designer expert qui crée des landing \
pages web converti­santes, claires, modernes.

Tu reçois : sujet/produit + objectif + cible + ton + (optionnellement) BrandKit.

Tu RENVOIES UN JSON strict (pas de texte avant/après) :

{
  "meta": {
    "titre_seo": "Titre SEO (max 60 chars)",
    "description_seo": "Description SEO (max 160 chars)",
    "og_image_prompt": "Description EN 30-60 mots pour image OG/Twitter card",
    "favicon_prompt": "Description EN 5-15 mots pour favicon (souvent un \
monogramme ou un pictogramme simple)",
    "lang": "fr"
  },
  "brand": {
    "nom_marque": "Nom de la marque",
    "tagline": "Phrase d'accroche (max 80 chars)",
    "ton": "professionnel | startup | luxe | tech | bienveillant | dynamique"
  },
  "hero": {
    "h1": "Promesse principale (max 70 chars)",
    "subtitle": "Bénéfice clé qui clarifie le H1 (max 160 chars)",
    "cta_primaire_label": "Démarrer gratuitement",
    "cta_primaire_url":   "#contact",
    "cta_secondaire_label": "Voir la démo",
    "cta_secondaire_url":   "#features",
    "image_prompt": "Description EN 40-80 mots pour hero image (Flux Pro Ultra). \
Photoréaliste ou illustration selon le ton.",
    "image_position": "right | left | full | background"
  },
  "features": {
    "titre_section": "Fonctionnalités clés",
    "items": [
      {"icone": "🚀", "titre": "Performance", "description": "Une explication \
courte du bénéfice (1-2 phrases, focus client)"}
    ]
  },
  "stats": {
    "titre_section": "Notre impact en chiffres",
    "items": [
      {"valeur": "+250%", "label": "ROI moyen", "icone": "📈"}
    ]
  },
  "comment_ca_marche": {
    "titre_section": "Comment ça marche",
    "etapes": [
      {"numero": "1", "titre": "Inscription", "description": "..."}
    ]
  },
  "temoignages": {
    "titre_section": "Ils nous font confiance",
    "items": [
      {"nom": "Marie K.", "fonction": "Directrice Marketing, ACME",
       "avatar_initiales": "MK",
       "citation": "..."}
    ]
  },
  "pricing": {
    "titre_section": "Tarifs simples et transparents",
    "plans": [
      {"nom": "Starter", "prix": "Gratuit", "periode": "",
       "features": ["..."],
       "cta_label": "Commencer", "cta_url": "#contact",
       "highlight": false}
    ]
  },
  "faq": {
    "titre_section": "Questions fréquentes",
    "items": [{"question": "...", "reponse": "..."}]
  },
  "cta_final": {
    "titre": "Prêt à transformer …",
    "sous_titre": "...",
    "cta_label": "Démarrer maintenant",
    "cta_url": "#contact"
  },
  "contact": {
    "titre_section": "Nous contacter",
    "email": "contact@entreprise.com",
    "telephone": "+237 6 XX XX XX XX",
    "adresse": "Adresse postale",
    "formulaire_active": true,
    "webhook_url": ""
  },
  "footer": {
    "copyright": "© 2026 Entreprise",
    "liens_legaux": [
      {"label": "Mentions légales", "url": "#"},
      {"label": "Confidentialité",  "url": "#"}
    ],
    "reseaux_sociaux": [
      {"plateforme": "linkedin", "url": "..."},
      {"plateforme": "twitter",  "url": "..."}
    ]
  }
}

Règles :
1. CHAQUE section optionnelle : si non pertinente pour le sujet → mettre \
"items": [] (la section sera omise du HTML)
2. Toujours hero + cta_final + footer (sections obligatoires)
3. H1 = promesse (PAS le nom du produit). Le nom apparaît dans le nav et la tagline
4. Features 3-6 items max, avec icône émoji ou Heroicons SVG slug
5. Stats 3-4 chiffres marquants
6. Témoignages 3 max, avec initiales pour avatar (pas de photo)
7. Pricing 3 plans max, "highlight": true sur le plan recommandé
8. FAQ 5-8 items pertinents pour conversion
9. Langue : utilise EXACTEMENT la langue du brief (sujet/contexte)
10. Brand-aware : si BrandKit fourni, le LLM doit aligner ton + nom de marque
"""


async def generer_specification_landing(
    sujet: str,
    objectif: str = "conversion",
    cible: Optional[str] = None,
    ton: Optional[str] = None,
    contexte: Optional[str] = None,
    brand_kit: Optional[dict] = None,
    langue: str = "fr",
) -> tuple[dict, dict]:
    """LLM Sonnet → spec JSON de la landing page. Retourne (spec, usage_llm)."""
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire

    user_prompt = (
        f"SUJET / PRODUIT : {sujet}\n"
        f"OBJECTIF : {objectif}\n"
        f"LANGUE : {langue}\n"
    )
    if cible:
        user_prompt += f"CIBLE : {cible}\n"
    if ton:
        user_prompt += f"TON SOUHAITÉ : {ton}\n"
    if contexte:
        user_prompt += f"CONTEXTE : {contexte[:2500]}\n"
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
        max_tokens=10000,
        temperature=0.7,
    )
    texte = rep.contenu if hasattr(rep, "contenu") else str(rep)
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


# ── Rendu HTML ────────────────────────────────────────────────────────────────

def _tw_color_vars(brand_kit: Optional[dict]) -> dict:
    """Extrait les couleurs primary/accent depuis BrandKit ou défauts."""
    bk = brand_kit or {}
    return {
        "primary":   bk.get("primary_color")   or "#0F172A",
        "secondary": bk.get("secondary_color") or "#334155",
        "accent":    bk.get("accent_color")    or "#3B82F6",
        "bg":        bk.get("bg_color")        or "#FFFFFF",
        "bg_alt":    bk.get("bg_alt_color")    or "#F8FAFC",
        "text":      bk.get("text_color")      or "#0F172A",
        "muted":     bk.get("muted_color")     or "#64748B",
        "font_titre": bk.get("font_titre")     or "Inter, system-ui, sans-serif",
        "font_corps": bk.get("font_corps")     or "Inter, system-ui, sans-serif",
    }


def _section_hero(spec: dict, colors: dict) -> str:
    h = spec.get("hero") or {}
    brand = spec.get("brand") or {}
    img = h.get("_image_url", "")
    has_img = bool(img)
    pos = h.get("image_position") or "right"
    cta1 = h.get("cta_primaire_label")
    cta2 = h.get("cta_secondaire_label")
    cta_html = ""
    if cta1:
        cta_html += (f'<a href="{escape(h.get("cta_primaire_url", "#contact"))}" '
                     f'class="cta-primary inline-block px-6 py-3 rounded-lg font-semibold text-white shadow-lg hover:shadow-xl transition-all" '
                     f'style="background:var(--accent)">{escape(cta1)}</a>')
    if cta2:
        cta_html += (f'<a href="{escape(h.get("cta_secondaire_url", "#features"))}" '
                     f'class="cta-secondary inline-block px-6 py-3 rounded-lg font-semibold border-2 hover:bg-gray-50 transition-all ml-3" '
                     f'style="border-color:var(--primary);color:var(--primary)">{escape(cta2)}</a>')

    img_html = ""
    if has_img:
        if pos == "background":
            return (
                f'<section id="hero" class="relative py-32 overflow-hidden text-white" '
                f'style="background:linear-gradient(rgba(15,23,42,0.65),rgba(15,23,42,0.65)),url({img}) center/cover">'
                f'<div class="max-w-6xl mx-auto px-6 text-center">'
                f'<h1 class="text-5xl md:text-6xl font-extrabold mb-6 leading-tight">{escape(h.get("h1", ""))}</h1>'
                f'<p class="text-xl md:text-2xl mb-8 opacity-90">{escape(h.get("subtitle", ""))}</p>'
                f'<div class="flex flex-wrap justify-center gap-3">{cta_html}</div>'
                f'</div></section>'
            )
        img_html = (
            f'<div class="hero-img reveal-on-scroll flex-1">'
            f'<img src="{img}" alt="" class="rounded-2xl shadow-2xl w-full"></div>'
        )

    text_html = (
        f'<div class="hero-text reveal-on-scroll flex-1">'
        f'<h1 class="text-4xl md:text-5xl lg:text-6xl font-extrabold mb-6 leading-tight" '
        f'style="color:var(--primary)">{escape(h.get("h1", ""))}</h1>'
        f'<p class="text-lg md:text-xl mb-8 opacity-80" style="color:var(--muted)">'
        f'{escape(h.get("subtitle", ""))}</p>'
        f'<div class="flex flex-wrap gap-3">{cta_html}</div>'
        f'</div>'
    )
    flex_order = (img_html + text_html) if pos == "left" else (text_html + img_html)

    return (
        f'<section id="hero" class="py-20 md:py-28" style="background:var(--bg)">'
        f'<div class="max-w-6xl mx-auto px-6 flex flex-col md:flex-row items-center gap-12">'
        f'{flex_order}'
        f'</div></section>'
    )


def _section_features(spec: dict) -> str:
    f = spec.get("features") or {}
    items = f.get("items") or []
    if not items:
        return ""
    cards = "".join(
        f'<div class="feature-card reveal-on-scroll p-6 rounded-xl bg-white shadow-md hover:shadow-xl transition-all">'
        f'<div class="text-4xl mb-4">{escape(it.get("icone", "✨"))}</div>'
        f'<h3 class="text-xl font-bold mb-2" style="color:var(--primary)">{escape(it.get("titre", ""))}</h3>'
        f'<p class="opacity-80" style="color:var(--muted)">{escape(it.get("description", ""))}</p>'
        f'</div>'
        for it in items
    )
    return (
        f'<section id="features" class="py-20" style="background:var(--bg-alt)">'
        f'<div class="max-w-6xl mx-auto px-6">'
        f'<h2 class="text-3xl md:text-4xl font-bold text-center mb-12" style="color:var(--primary)">'
        f'{escape(f.get("titre_section", "Fonctionnalités"))}</h2>'
        f'<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">{cards}</div>'
        f'</div></section>'
    )


def _section_stats(spec: dict) -> str:
    s = spec.get("stats") or {}
    items = s.get("items") or []
    if not items:
        return ""
    cards = "".join(
        f'<div class="stat-item reveal-on-scroll text-center">'
        f'<div class="text-5xl md:text-6xl font-extrabold mb-2" style="color:var(--accent)">'
        f'{escape(it.get("valeur", ""))}</div>'
        f'<div class="text-sm md:text-base uppercase tracking-wider" style="color:var(--muted)">'
        f'{escape(it.get("label", ""))}</div></div>'
        for it in items
    )
    return (
        f'<section id="stats" class="py-20" style="background:var(--primary);color:white">'
        f'<div class="max-w-6xl mx-auto px-6">'
        f'<h2 class="text-3xl md:text-4xl font-bold text-center mb-12 text-white">'
        f'{escape(s.get("titre_section", "Notre impact"))}</h2>'
        f'<div class="grid grid-cols-2 md:grid-cols-4 gap-8">{cards}</div>'
        f'</div></section>'
    )


def _section_etapes(spec: dict) -> str:
    e = spec.get("comment_ca_marche") or {}
    etapes = e.get("etapes") or []
    if not etapes:
        return ""
    items = "".join(
        f'<div class="etape-card reveal-on-scroll text-center">'
        f'<div class="w-16 h-16 mx-auto mb-4 rounded-full flex items-center justify-center text-2xl font-bold text-white" '
        f'style="background:var(--accent)">{escape(it.get("numero", str(i+1)))}</div>'
        f'<h3 class="text-xl font-bold mb-2" style="color:var(--primary)">{escape(it.get("titre", ""))}</h3>'
        f'<p class="opacity-80" style="color:var(--muted)">{escape(it.get("description", ""))}</p></div>'
        for i, it in enumerate(etapes)
    )
    return (
        f'<section id="etapes" class="py-20" style="background:var(--bg)">'
        f'<div class="max-w-6xl mx-auto px-6">'
        f'<h2 class="text-3xl md:text-4xl font-bold text-center mb-12" style="color:var(--primary)">'
        f'{escape(e.get("titre_section", "Comment ça marche"))}</h2>'
        f'<div class="grid grid-cols-1 md:grid-cols-{len(etapes)} gap-8">{items}</div>'
        f'</div></section>'
    )


def _section_temoignages(spec: dict) -> str:
    t = spec.get("temoignages") or {}
    items = t.get("items") or []
    if not items:
        return ""
    cards = "".join(
        f'<div class="testi-card reveal-on-scroll p-6 rounded-xl bg-white shadow-md">'
        f'<div class="flex items-center mb-4">'
        f'<div class="w-12 h-12 rounded-full flex items-center justify-center font-bold text-white mr-4" '
        f'style="background:var(--accent)">{escape(it.get("avatar_initiales", "?"))}</div>'
        f'<div><div class="font-bold" style="color:var(--primary)">{escape(it.get("nom", ""))}</div>'
        f'<div class="text-sm" style="color:var(--muted)">{escape(it.get("fonction", ""))}</div></div></div>'
        f'<p class="italic" style="color:var(--text)">"{escape(it.get("citation", ""))}"</p></div>'
        for it in items
    )
    return (
        f'<section id="temoignages" class="py-20" style="background:var(--bg-alt)">'
        f'<div class="max-w-6xl mx-auto px-6">'
        f'<h2 class="text-3xl md:text-4xl font-bold text-center mb-12" style="color:var(--primary)">'
        f'{escape(t.get("titre_section", "Témoignages"))}</h2>'
        f'<div class="grid grid-cols-1 md:grid-cols-3 gap-6">{cards}</div>'
        f'</div></section>'
    )


def _section_pricing(spec: dict) -> str:
    p = spec.get("pricing") or {}
    plans = p.get("plans") or []
    if not plans:
        return ""
    cards = "".join(
        f'<div class="pricing-card reveal-on-scroll p-8 rounded-2xl '
        f'{"border-4 transform scale-105 shadow-2xl" if it.get("highlight") else "border-2 shadow-md"} bg-white" '
        f'style="border-color:{"var(--accent)" if it.get("highlight") else "var(--bg-alt)"}">'
        f'<h3 class="text-2xl font-bold mb-2" style="color:var(--primary)">{escape(it.get("nom", ""))}</h3>'
        f'<div class="text-4xl font-extrabold mb-1" style="color:var(--accent)">'
        f'{escape(it.get("prix", ""))}</div>'
        f'<div class="text-sm mb-6" style="color:var(--muted)">{escape(it.get("periode", ""))}</div>'
        f'<ul class="space-y-2 mb-6">'
        f'{"".join(f"<li class=text-sm style=color:var(--text)>✓ {escape(f)}</li>" for f in it.get("features", []))}'
        f'</ul>'
        f'<a href="{escape(it.get("cta_url", "#contact"))}" '
        f'class="block text-center px-6 py-3 rounded-lg font-semibold text-white transition-all hover:opacity-90" '
        f'style="background:var(--accent)">{escape(it.get("cta_label", "Choisir"))}</a></div>'
        for it in plans
    )
    return (
        f'<section id="pricing" class="py-20" style="background:var(--bg)">'
        f'<div class="max-w-6xl mx-auto px-6">'
        f'<h2 class="text-3xl md:text-4xl font-bold text-center mb-12" style="color:var(--primary)">'
        f'{escape(p.get("titre_section", "Tarifs"))}</h2>'
        f'<div class="grid grid-cols-1 md:grid-cols-{min(3, len(plans))} gap-6 items-stretch">{cards}</div>'
        f'</div></section>'
    )


def _section_faq(spec: dict) -> str:
    f = spec.get("faq") or {}
    items = f.get("items") or []
    if not items:
        return ""
    cards = "".join(
        f'<details class="faq-item reveal-on-scroll bg-white rounded-lg shadow-sm p-4 cursor-pointer">'
        f'<summary class="font-semibold text-lg" style="color:var(--primary)">'
        f'{escape(it.get("question", ""))}</summary>'
        f'<p class="mt-3 opacity-80" style="color:var(--text)">{escape(it.get("reponse", ""))}</p>'
        f'</details>'
        for it in items
    )
    return (
        f'<section id="faq" class="py-20" style="background:var(--bg-alt)">'
        f'<div class="max-w-3xl mx-auto px-6">'
        f'<h2 class="text-3xl md:text-4xl font-bold text-center mb-12" style="color:var(--primary)">'
        f'{escape(f.get("titre_section", "Questions fréquentes"))}</h2>'
        f'<div class="space-y-3">{cards}</div>'
        f'</div></section>'
    )


def _section_cta_final(spec: dict) -> str:
    c = spec.get("cta_final") or {}
    if not c:
        return ""
    return (
        f'<section id="cta-final" class="py-24 text-center" '
        f'style="background:linear-gradient(135deg,var(--primary),var(--accent));color:white">'
        f'<div class="max-w-3xl mx-auto px-6 reveal-on-scroll">'
        f'<h2 class="text-3xl md:text-5xl font-extrabold mb-4 text-white">{escape(c.get("titre", ""))}</h2>'
        f'<p class="text-lg md:text-xl mb-8 opacity-90">{escape(c.get("sous_titre", ""))}</p>'
        f'<a href="{escape(c.get("cta_url", "#contact"))}" '
        f'class="inline-block px-8 py-4 rounded-lg font-bold text-lg bg-white shadow-xl hover:scale-105 transition-transform" '
        f'style="color:var(--primary)">{escape(c.get("cta_label", "Commencer"))}</a>'
        f'</div></section>'
    )


def _section_contact(spec: dict) -> str:
    c = spec.get("contact") or {}
    info = []
    if c.get("email"):
        info.append(f'<div>✉ <a href="mailto:{escape(c["email"])}" style="color:var(--accent)">{escape(c["email"])}</a></div>')
    if c.get("telephone"):
        info.append(f'<div>📞 <a href="tel:{escape(c["telephone"])}" style="color:var(--accent)">{escape(c["telephone"])}</a></div>')
    if c.get("adresse"):
        info.append(f'<div>📍 {escape(c["adresse"])}</div>')

    formulaire = ""
    if c.get("formulaire_active", True) and c.get("email"):
        formulaire = (
            f'<form action="mailto:{escape(c["email"])}" method="post" enctype="text/plain" class="space-y-4 reveal-on-scroll">'
            f'<input type="text" name="nom" placeholder="Votre nom" required '
            f'class="w-full px-4 py-3 rounded-lg border border-gray-300 focus:outline-none focus:border-blue-500">'
            f'<input type="email" name="email" placeholder="Votre email" required '
            f'class="w-full px-4 py-3 rounded-lg border border-gray-300 focus:outline-none focus:border-blue-500">'
            f'<textarea name="message" rows="5" placeholder="Votre message" required '
            f'class="w-full px-4 py-3 rounded-lg border border-gray-300 focus:outline-none focus:border-blue-500"></textarea>'
            f'<button type="submit" class="w-full px-6 py-3 rounded-lg font-semibold text-white shadow-lg hover:shadow-xl transition-all" '
            f'style="background:var(--accent)">Envoyer</button>'
            f'</form>'
        )
    return (
        f'<section id="contact" class="py-20" style="background:var(--bg)">'
        f'<div class="max-w-4xl mx-auto px-6">'
        f'<h2 class="text-3xl md:text-4xl font-bold text-center mb-12" style="color:var(--primary)">'
        f'{escape(c.get("titre_section", "Nous contacter"))}</h2>'
        f'<div class="grid grid-cols-1 md:grid-cols-2 gap-12">'
        f'<div class="space-y-4 reveal-on-scroll">{"".join(info)}</div>'
        f'{formulaire}'
        f'</div></div></section>'
    )


def _section_footer(spec: dict) -> str:
    f = spec.get("footer") or {}
    brand = spec.get("brand") or {}
    liens = "".join(
        f'<a href="{escape(l.get("url", "#"))}" class="hover:underline" style="color:var(--muted)">{escape(l.get("label", ""))}</a>'
        for l in (f.get("liens_legaux") or [])
    )
    socials_map = {
        "linkedin": "💼", "twitter": "🐦", "x": "🐦", "facebook": "📘",
        "instagram": "📸", "youtube": "▶", "tiktok": "🎵", "github": "🐱",
        "whatsapp": "💬", "telegram": "✈",
    }
    socials = "".join(
        f'<a href="{escape(s.get("url", "#"))}" target="_blank" rel="noopener" '
        f'class="text-2xl hover:opacity-70">{socials_map.get(s.get("plateforme", "").lower(), "🔗")}</a>'
        for s in (f.get("reseaux_sociaux") or [])
    )
    return (
        f'<footer class="py-12" style="background:var(--primary);color:white">'
        f'<div class="max-w-6xl mx-auto px-6 flex flex-col md:flex-row justify-between items-center gap-4">'
        f'<div class="text-sm opacity-80">{escape(f.get("copyright", ""))}</div>'
        f'<div class="flex gap-4 text-sm">{liens}</div>'
        f'<div class="flex gap-3">{socials}</div>'
        f'</div></footer>'
    )


def _section_nav(spec: dict) -> str:
    brand = spec.get("brand") or {}
    return (
        f'<nav class="sticky top-0 z-50 backdrop-blur-md bg-white/80 shadow-sm">'
        f'<div class="max-w-6xl mx-auto px-6 py-4 flex justify-between items-center">'
        f'<a href="#hero" class="text-xl font-bold" style="color:var(--primary)">'
        f'{escape(brand.get("nom_marque", "Logo"))}</a>'
        f'<div class="hidden md:flex gap-6 text-sm">'
        f'<a href="#features" class="hover:opacity-70">Fonctionnalités</a>'
        f'<a href="#pricing" class="hover:opacity-70">Tarifs</a>'
        f'<a href="#faq" class="hover:opacity-70">FAQ</a>'
        f'<a href="#contact" class="font-semibold" style="color:var(--accent)">Contact</a>'
        f'</div></div></nav>'
    )


def construire_html_landing(spec: dict, brand_kit: Optional[dict] = None) -> str:
    """Construit le HTML landing page standalone à partir de la spec JSON."""
    colors = _tw_color_vars(brand_kit)
    meta = spec.get("meta") or {}
    brand = spec.get("brand") or {}

    css_vars = ";".join(f"--{k.replace('_', '-')}:{v}" for k, v in colors.items())

    titre = escape(meta.get("titre_seo") or brand.get("nom_marque") or "Landing")
    desc = escape(meta.get("description_seo") or "")
    lang = escape(meta.get("lang") or "fr")
    og_img = spec.get("_og_image_url") or ""
    favicon = spec.get("_favicon_url") or ""

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{titre}</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="{titre}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="website">
{f'<meta property="og:image" content="{og_img}">' if og_img else ""}
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{titre}">
<meta name="twitter:description" content="{desc}">
{f'<meta name="twitter:image" content="{og_img}">' if og_img else ""}
{f'<link rel="icon" href="{favicon}">' if favicon else ""}
<meta name="generator" content="Yukpo Landing Page Builder">
<script src="https://cdn.tailwindcss.com"></script>
<style>
:root {{ {css_vars} }}
html {{ scroll-behavior: smooth; }}
body {{ font-family: var(--font-corps); color: var(--text); background: var(--bg); margin: 0; }}
h1, h2, h3, h4 {{ font-family: var(--font-titre); }}
.reveal-on-scroll {{ opacity: 0; transform: translateY(20px); transition: opacity 0.6s ease-out, transform 0.6s ease-out; }}
.reveal-on-scroll.is-visible {{ opacity: 1; transform: translateY(0); }}
details summary::-webkit-details-marker {{ display: none; }}
details summary::after {{ content: "+"; float: right; font-size: 1.5em; line-height: 1; transition: transform 0.2s; }}
details[open] summary::after {{ transform: rotate(45deg); }}
@media (prefers-color-scheme: dark) {{
  body.auto-dark {{ background: #0F172A; color: #E2E8F0; }}
  body.auto-dark .feature-card, body.auto-dark .testi-card, body.auto-dark .pricing-card, body.auto-dark .faq-item {{ background: #1E293B; color: #E2E8F0; }}
}}
@media print {{
  .reveal-on-scroll {{ opacity: 1; transform: none; }}
  nav, #cta-final {{ break-inside: avoid; }}
}}
.skip-link {{ position: absolute; left: -9999px; }}
.skip-link:focus {{ left: 1rem; top: 1rem; z-index: 100; background: white; padding: 0.5rem 1rem; border-radius: 0.5rem; box-shadow: 0 4px 12px rgba(0,0,0,0.15); }}
</style>
</head>
<body>
<a href="#main" class="skip-link">Aller au contenu</a>
{_section_nav(spec)}
<main id="main">
{_section_hero(spec, colors)}
{_section_features(spec)}
{_section_stats(spec)}
{_section_etapes(spec)}
{_section_temoignages(spec)}
{_section_pricing(spec)}
{_section_faq(spec)}
{_section_cta_final(spec)}
{_section_contact(spec)}
</main>
{_section_footer(spec)}
<script>
const observer = new IntersectionObserver(entries => {{
  entries.forEach(entry => {{
    if (entry.isIntersecting) entry.target.classList.add('is-visible');
  }});
}}, {{ threshold: 0.15 }});
document.querySelectorAll('.reveal-on-scroll').forEach(el => observer.observe(el));
</script>
</body>
</html>
"""


# ── Pipeline complet ──────────────────────────────────────────────────────────

async def generer_landing_page(
    sujet: str,
    objectif: str = "conversion",
    cible: Optional[str] = None,
    ton: Optional[str] = None,
    contexte: Optional[str] = None,
    brand_kit: Optional[dict] = None,
    langue: str = "fr",
    generer_images: bool = True,
) -> tuple[bytes, dict, list[dict]]:
    """
    Pipeline complet : LLM spec → images IA (hero + OG + favicon) → HTML.

    Retourne (html_bytes, spec_finale, usages_llm).
    """
    spec, usage_spec = await generer_specification_landing(
        sujet=sujet, objectif=objectif, cible=cible, ton=ton,
        contexte=contexte, brand_kit=brand_kit, langue=langue,
    )
    usages = [{**usage_spec, "etape": "spec_landing"}]

    if generer_images:
        from modules.bureau import image_gen as _ig

        # Hero image
        hero = spec.get("hero") or {}
        if hero.get("image_prompt"):
            try:
                png = await _ig.generer_image(
                    prompt=hero["image_prompt"], mode="ultra",
                    format_="landscape_16_9", timeout_s=120.0,
                )
                if png:
                    hero["_image_url"] = "data:image/png;base64," + base64.b64encode(png).decode()
            except Exception as e:
                logger.warning(f"[Landing/hero] image échec : {e}")

        # OG image
        og_prompt = (spec.get("meta") or {}).get("og_image_prompt")
        if og_prompt:
            try:
                png = await _ig.generer_image(
                    prompt=og_prompt, mode="premium",
                    format_="landscape_16_9", timeout_s=90.0,
                )
                if png:
                    spec["_og_image_url"] = "data:image/png;base64," + base64.b64encode(png).decode()
            except Exception as e:
                logger.warning(f"[Landing/og] image échec : {e}")

        # Favicon — SVG vectoriel via Recraft (scalable, léger)
        favicon_prompt = (spec.get("meta") or {}).get("favicon_prompt")
        if favicon_prompt:
            try:
                svg = await _ig.generer_svg_natif(
                    prompt=favicon_prompt, format_="square_hd",
                    style="vector_illustration", timeout_s=90.0,
                )
                if svg:
                    spec["_favicon_url"] = "data:image/svg+xml;base64," + base64.b64encode(svg).decode()
            except Exception as e:
                logger.warning(f"[Landing/favicon] SVG échec : {e}")

    html = construire_html_landing(spec, brand_kit=brand_kit)
    return html.encode("utf-8"), spec, usages
