"""Site Builder multi-pages (Phase C) — orchestrateur LLM + render HTML.

Génère un mini-site 3-7 pages (home + services + équipe + blog + contact)
depuis un brief utilisateur. Pipeline :

  1. Sonnet compose un SiteSpec : structure de nav + spec de chaque page
     (réutilise le format spec de `landing_page_builder` enrichi).
  2. Pour chaque page : images IA générées via image_gen (hero + OG).
  3. Sauvegarde en DB (SiteDB + SitePageDB par page).
  4. Au moment du publish : `construire_html_site_complet()` rend
     N fichiers HTML avec nav commune + footer commun + sitemap.xml +
     robots.txt, le tout en ZIP → Netlify.

Réutilise au MAXIMUM :
  • `landing_page_builder` (sections hero/features/stats/pricing/etc.
    + helpers `_section_*`)
  • `landing_publisher` (deploy ZIP Netlify)
  • `qr_generator` (QR de la home URL au publish)
"""
from __future__ import annotations

import base64
import json
import logging
import re
from html import escape
from typing import Optional

logger = logging.getLogger("yukpo_assurance.pro.site_builder")


# Types de pages supportées (alignées avec migration 0011)
TYPES_PAGES_VALIDES = (
    "home", "services", "equipe", "blog_index", "contact",
    "mentions_legales", "cgv", "confidentialite", "tarifs",
    "a_propos", "portfolio", "faq",
)

# Mapping type → slug par défaut dans l'URL
_SLUGS_DEFAUT = {
    "home":             "",
    "services":         "services",
    "equipe":           "equipe",
    "blog_index":       "blog",
    "contact":          "contact",
    "mentions_legales": "mentions-legales",
    "cgv":              "cgv",
    "confidentialite":  "confidentialite",
    "tarifs":           "tarifs",
    "a_propos":         "a-propos",
    "portfolio":        "portfolio",
    "faq":              "faq",
}

# Libellés humains des pages (pour nav + breadcrumbs)
_LABELS_PAGE = {
    "home":             "Accueil",
    "services":         "Services",
    "equipe":           "Équipe",
    "blog_index":       "Blog",
    "contact":          "Contact",
    "mentions_legales": "Mentions légales",
    "cgv":              "CGV",
    "confidentialite":  "Confidentialité",
    "tarifs":           "Tarifs",
    "a_propos":         "À propos",
    "portfolio":        "Portfolio",
    "faq":              "FAQ",
}


# ─── Prompt LLM pour la composition d'un site multi-pages ────────────────────

_PROMPT_SYSTEME_SITE = """Tu es un copywriter SENIOR & directeur artistique web \
expert qui crée des mini-sites professionnels DENSES, PERSUASIFS, MODERNES, \
alignés avec la marque. Tu ne fais JAMAIS de versions light/superficielles : \
chaque page doit avoir 5-9 sections riches, des paragraphes narratifs longs \
(120-250 mots/section), des exemples concrets, et un copywriting CTA-driven.

OBJECTIF DE DENSITÉ par page :
  • Home               : 7-9 sections (hero + features + comment_ca_marche + \
                         stats + temoignages + pricing/avantages + cta_final + FAQ)
  • Services           : 6-8 sections (hero + liste détaillée 4-8 services \
                         avec paragraphes 100-150 mots/service + process + cta)
  • Équipe             : 4-6 sections (hero + intro narrative + 3-8 membres \
                         avec bio 80-120 mots/membre + valeurs + cta)
  • Blog index         : 3-4 sections (hero + intro + manifeste éditorial + cta)
  • Contact            : 4-5 sections (hero + coordonnées + carte/horaires + \
                         form + FAQ rapide 3-4 questions)
  • Mentions/Conf/CGV  : contenu_md complet 800-1500 mots conformes OHADA/RGPD

Tu reçois un brief utilisateur + (optionnellement) BrandKit + types de pages
à composer. Tu RENVOIES UN JSON strict (pas de texte avant/après) :

{
  "nom_marque": "Nom commercial",
  "tagline": "Phrase d'accroche brand (max 100 chars)",
  "meta_globale": {
    "favicon_prompt": "Description EN 5-15 mots pour favicon",
    "og_image_prompt": "Description EN 30-60 mots pour OG image globale du site"
  },
  "nav": {
    "ordre_pages": ["home", "services", "equipe", "blog_index", "contact"]
  },
  "footer": {
    "copyright": "© 2026 NomMarque",
    "reseaux_sociaux": [{"plateforme": "linkedin", "url": "..."}, ...],
    "liens_legaux": [
      {"label": "Mentions légales", "url": "/mentions-legales"},
      {"label": "Confidentialité",  "url": "/confidentialite"}
    ]
  },
  "pages": {
    "home": {
      "titre_seo": "Titre SEO 60 chars max",
      "description_seo": "Description SEO 160 chars max",
      "hero": {
        "h1": "Promesse PUISSANTE et SPÉCIFIQUE (max 70 chars) — pas générique",
        "subtitle": "Bénéfice clé qui clarifie le h1 + différenciateur (max 200 chars)",
        "cta_primaire_label": "...", "cta_primaire_url": "/contact",
        "cta_secondaire_label": "...", "cta_secondaire_url": "/services",
        "image_prompt": "Description EN 40-80 mots"
      },
      "features": {
        "titre_section": "Pourquoi nous choisir / Nos forces",
        "intro_narrative": "Paragraphe 80-120 mots qui contextualise les 4-6 bénéfices",
        "items": [
          {
            "icone": "🚀",
            "titre": "Bénéfice CLIENT (pas feature technique)",
            "description": "Paragraphe 80-130 mots — pas une phrase. Détaille COMMENT et POURQUOI ce bénéfice est réel pour le client, avec un exemple ou métrique."
          }, ... 4-6 items
        ]
      },
      "comment_ca_marche": {
        "titre_section": "Comment ça marche",
        "intro": "1-2 phrases courtes",
        "etapes": [
          {"numero": "1", "titre": "Étape 1", "description": "60-100 mots décrivant l'étape, ce que fait le client, ce que tu fais"},
          ... 3-5 étapes
        ]
      },
      "stats": {
        "titre_section": "Notre impact en chiffres",
        "intro": "Paragraphe 50-80 mots qui contextualise (depuis quand, dans quelle zone)",
        "items": [{"valeur": "+ 240%", "label": "ROI moyen client", "icone": "📈"}, ... 4 stats]
      },
      "temoignages": {
        "titre_section": "Ils nous font confiance",
        "intro": "Paragraphe 50 mots qui contextualise",
        "items": [
          {"nom": "Marie K.", "fonction": "Directrice marketing, NomEntreprise Douala",
           "avatar_initiales": "MK",
           "citation": "Citation 60-120 mots, spécifique et crédible — pas générique"}
          , ... 3 témoignages
        ]
      },
      "cta_final": {
        "titre": "Prêt à transformer X ?",
        "sous_titre": "Argument-bénéfice 80-150 mots qui clôture",
        "cta_label": "...", "cta_url": "/contact"
      },
      "faq": {
        "titre_section": "Questions fréquentes",
        "items": [
          {"question": "Question concrète", "reponse": "Réponse 100-180 mots, précise et utile"},
          ... 4-6 FAQ
        ]
      }
    },
    "services": {
      "titre_seo": "...", "description_seo": "...",
      "hero": {...},
      "intro_narrative": "Paragraphe 120-180 mots qui pose le contexte global des services",
      "liste_services": [
        {
          "icone": "...", "titre": "Nom du service précis",
          "description": "Paragraphe DENSE 120-180 mots détaillant le service, public cible, méthode, durée, livrables, prix indicatif si possible",
          "bullets_inclus": ["3-5 livrables ou points clés"],
          "image_prompt": "EN 40-80 mots"
        }, ... 4-8 items
      ],
      "process": {
        "titre_section": "Notre méthode",
        "etapes": [{"numero":"1","titre":"...","description":"60-100 mots"}, ... 3-5 étapes]
      },
      "cta_final": {...}
    },
    "equipe": {
      "titre_seo": "...", "description_seo": "...",
      "hero": {...},
      "intro_narrative": "Paragraphe 100-180 mots qui présente l'équipe, ses valeurs, son ADN",
      "membres": [
        {
          "nom": "Prénom Nom", "fonction": "Poste précis",
          "bio": "Paragraphe 80-150 mots : parcours, expertise, ce qu'il apporte au client, anecdote crédible",
          "avatar_initiales": "PN"
        }, ... 3-8 membres simulés ANCRÉS LOCALEMENT
      ],
      "valeurs": {
        "titre_section": "Nos valeurs",
        "items": [{"icone": "...", "titre": "...", "description": "60-100 mots"}, ... 3-5 valeurs]
      }
    },
    "blog_index": {
      "titre_seo": "...", "description_seo": "...",
      "intro_narrative": "Paragraphe 150-250 mots — manifeste éditorial : ligne éditoriale, à qui s'adresse le blog, fréquence, types d'articles, valeur pour le lecteur"
    },
    "contact": {
      "titre_seo": "...", "description_seo": "...",
      "hero": {"h1": "...", "subtitle": "Sous-titre rassurant 120-180 chars"},
      "email": "contact@...", "telephone": "+237 ...",
      "adresse": "Adresse physique précise",
      "horaires": "Détaillés ex: 'Lun-Ven 8h-18h, Sam 9h-13h, fermé dimanche'",
      "carte_zone": "Description géographique 50 mots si pas de carte",
      "faq_rapide": {
        "items": [{"question":"...","reponse":"60-100 mots"}, ... 3-4 FAQ ciblées contact]
      }
    },
    "mentions_legales": {
      "titre_seo": "Mentions légales",
      "contenu_md": "Markdown 800-1500 mots complet : éditeur, hébergeur, directeur publication, propriété intellectuelle, conditions d'usage, lien CGV, etc. Cohérent avec le pays/cadre légal du brief (OHADA, RGPD si EU, etc.)"
    },
    "confidentialite": {
      "titre_seo": "Politique de confidentialité",
      "contenu_md": "Markdown 1000-1800 mots RGPD/OHADA : qui collecte, quelles données, finalités, base légale, durée, droits utilisateur, cookies, sous-traitants, transferts internationaux, contact DPO. NE PAS générique — adapté au secteur du brief."
    }
  }
}

Règles ABSOLUES (densité + crédibilité) :
1. CHAQUE page demandée dans `types_pages` doit être présente dans `pages`.
2. NE PAS inventer de pages non demandées.
3. PAS de version light ou superficielle. Chaque section riche, paragraphes longs.
4. INTERDIT : phrases creuses type "nous offrons des services de qualité",
   "leader sur le marché", "100% satisfait". Sois CONCRET avec exemples,
   métriques crédibles, méthodes nommées, livrables précis.
5. Hero image_prompt EN, 40-80 mots, photoréaliste sauf si BrandKit demande illustration.
6. Crédibilité géographique selon le brief : si Cameroun/CI/Sénégal mentionnés,
   adapte noms, villes, téléphones, monnaies, vocabulaire commercial.
7. Mentions légales + Confidentialité : 800-1800 mots de markdown structuré
   adapté au pays/cadre légal du brief.
8. CTAs internes : URLs commencent par / et matchent les slugs (/contact, /services, /tarifs).
9. Langue : utilise la langue du brief (FR par défaut).
10. UTILISE PARAGRAPHES NARRATIFS (80-180 mots) plus que des bullets seuls.
11. Chaque témoignage = citation 60-120 mots, nom complet crédible, entreprise précisée.
12. Chaque membre équipe = bio 80-150 mots avec parcours pro, expertise, anecdote.
"""


async def generer_specification_site(
    brief: str,
    *,
    types_pages: Optional[list[str]] = None,
    langue: str = "fr",
    brand_kit: Optional[dict] = None,
    cible: Optional[str] = None,
    ton: Optional[str] = None,
) -> tuple[dict, list[dict]]:
    """LLM Sonnet → SiteSpec multi-pages. Retourne (spec, usages_llm).

    `types_pages` : si None, défaut = ["home", "services", "equipe",
    "blog_index", "contact", "mentions_legales", "confidentialite"].
    """
    from core.ia_client import ia_client, ModeIA

    if not types_pages:
        types_pages = [
            "home", "services", "equipe", "blog_index", "contact",
            "mentions_legales", "confidentialite",
        ]
    # Nettoie + filtre seulement les types supportés
    types_pages = [t for t in types_pages if t in TYPES_PAGES_VALIDES]
    if "home" not in types_pages:
        types_pages.insert(0, "home")

    user_prompt = (
        f"BRIEF UTILISATEUR : {brief}\n"
        f"LANGUE : {langue}\n"
        f"TYPES DE PAGES À COMPOSER : {', '.join(types_pages)}\n"
    )
    if cible:
        user_prompt += f"CIBLE : {cible}\n"
    if ton:
        user_prompt += f"TON : {ton}\n"
    if brand_kit:
        user_prompt += f"BRAND_KIT : {json.dumps(brand_kit, ensure_ascii=False)[:1500]}\n"
    user_prompt += "\nProduis le JSON spec strict."

    # Composition site multi-pages 5-7 pages × N sections = volumineux.
    # Tier élevé Opus / GPT-5 + 24k tokens pour produire du contenu dense
    # et crédible en un seul appel.
    from core.ia_client import ModelePrioritaire
    rep = await ia_client.appeler(
        prompt=user_prompt,
        systeme=_PROMPT_SYSTEME_SITE,
        mode=ModeIA.REDACTION,
        max_tokens_override=24000,
        json_attendu=True,
        utiliser_cache=False,
        forcer_modele=ModelePrioritaire.CLAUDE_OPUS,
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
        "etape":      "spec_site_multipage",
    }
    return spec, [usage]


# ─── Génération des hero images IA (par page) ────────────────────────────────

async def _resolve_brand_lora(compagnie_id: Optional[int]) -> tuple[Optional[str], Optional[str]]:
    """Phase C.5 — Retourne (lora_url, trigger_word) du LoRA actif de la compagnie.

    Si plusieurs LoRA sont actifs `statut=ready` pour la même compagnie,
    on prend le plus récent. Retourne (None, None) si aucun ou erreur.
    """
    if not compagnie_id:
        return None, None
    try:
        from sqlalchemy import desc as _desc, select as _select
        from core.database import BrandLoraDB, async_session_maker
        async with async_session_maker() as db:
            row = (await db.execute(
                _select(BrandLoraDB)
                .where(BrandLoraDB.compagnie_id == int(compagnie_id))
                .where(BrandLoraDB.statut == "ready")
                .where(BrandLoraDB.actif.is_(True))
                .order_by(_desc(BrandLoraDB.training_fini))
            )).scalars().first()
            if row and row.lora_url:
                return row.lora_url, row.trigger_word
    except Exception as e:
        logger.debug(f"[Site/brand-lora] resolve échec : {e}")
    return None, None


async def enrichir_images_site(
    spec: dict, *, compagnie_id: Optional[int] = None,
) -> dict:
    """Pour chaque page avec un `image_prompt`, génère une hero image
    photoréaliste via fal.ai et stocke l'URL data-uri dans `_image_url`.

    Phase C.5 — auto-pickup du Brand LoRA actif de la compagnie : si la
    compagnie a un `BrandLoraDB.statut=ready`, son LoRA est injecté
    automatiquement dans toutes les générations d'images du site →
    cohérence brand parfaite sur tout le mini-site.

    Modifie `spec` in-place et retourne le même dict. Non bloquant.
    """
    from modules.bureau import image_gen as _ig

    # Phase C.5 — résolution Brand LoRA org
    brand_lora_url, trigger_word = await _resolve_brand_lora(compagnie_id)
    if brand_lora_url:
        logger.info(
            f"[Site/brand-lora] LoRA actif pour compagnie={compagnie_id}, "
            f"trigger='{trigger_word}' — injecté dans toutes les hero images"
        )

    pages = spec.get("pages") or {}
    for type_page, page_spec in pages.items():
        if not isinstance(page_spec, dict):
            continue
        hero = page_spec.get("hero") or {}
        prompt = hero.get("image_prompt")
        if prompt and not hero.get("_image_url"):
            # Préfixe trigger_word au prompt pour activer le LoRA brand
            prompt_final = (
                f"{trigger_word} {prompt}" if trigger_word else prompt
            )
            try:
                png = await _ig.generer_image(
                    prompt=prompt_final, mode="premium",
                    format_="landscape_16_9", timeout_s=120.0,
                    brand_lora_url=brand_lora_url,
                    brand_lora_scale=0.85 if brand_lora_url else 0.0,
                )
                if png:
                    hero["_image_url"] = (
                        "data:image/png;base64," + base64.b64encode(png).decode()
                    )
            except Exception as e:
                logger.warning(f"[Site/img] hero {type_page} échec : {e}")

    # Favicon global
    favicon_prompt = (spec.get("meta_globale") or {}).get("favicon_prompt")
    if favicon_prompt:
        try:
            svg = await _ig.generer_svg_natif(
                prompt=favicon_prompt, format_="square_hd",
                style="vector_illustration", timeout_s=60.0,
            )
            if svg:
                spec["_favicon_url"] = (
                    "data:image/svg+xml;base64," + base64.b64encode(svg).decode()
                )
        except Exception as e:
            logger.warning(f"[Site/img] favicon échec : {e}")
    return spec


# ─── Rendu HTML (par page + arborescence) ────────────────────────────────────

def _path_relatif_vers(page_courante: str, page_cible: str) -> str:
    """Calcule l'URL relative entre 2 types de pages."""
    slug = _SLUGS_DEFAUT.get(page_cible, page_cible)
    if page_cible == "home":
        return "/" if page_courante != "home" else "#"
    return f"/{slug}"


def _construire_nav(spec: dict, page_courante: str) -> str:
    """Nav top sticky commune à toutes les pages."""
    nav_pages = (spec.get("nav") or {}).get("ordre_pages") or list(
        (spec.get("pages") or {}).keys()
    )
    # Exclusion pages légales du menu top
    visible = [p for p in nav_pages if p not in (
        "mentions_legales", "cgv", "confidentialite",
    )]
    nom_marque = escape(spec.get("nom_marque") or "Yukpo")

    liens = "".join(
        f'<a href="{_path_relatif_vers(page_courante, p)}" '
        f'class="hover:opacity-70 {"font-semibold" if p == page_courante else ""}" '
        f'{"style=color:var(--accent)" if p == "contact" else ""}>'
        f"{escape(_LABELS_PAGE.get(p, p))}</a>"
        for p in visible
    )
    return (
        f'<nav class="sticky top-0 z-50 backdrop-blur-md bg-white/80 shadow-sm">'
        f'<div class="max-w-6xl mx-auto px-6 py-4 flex justify-between items-center">'
        f'<a href="/" class="text-xl font-bold" style="color:var(--primary)">'
        f"{nom_marque}</a>"
        f'<div class="hidden md:flex gap-6 text-sm">{liens}</div></div></nav>'
    )


def _construire_footer(spec: dict) -> str:
    """Footer commun à toutes les pages."""
    f = spec.get("footer") or {}
    liens = "".join(
        f'<a href="{escape(l.get("url", "#"))}" class="hover:underline" '
        f'style="color:var(--muted)">{escape(l.get("label", ""))}</a>'
        for l in (f.get("liens_legaux") or [])
    )
    socials_map = {
        "linkedin": "💼", "twitter": "🐦", "x": "🐦", "facebook": "📘",
        "instagram": "📸", "youtube": "▶", "tiktok": "🎵", "github": "🐱",
        "whatsapp": "💬", "telegram": "✈",
    }
    socials = "".join(
        f'<a href="{escape(s.get("url", "#"))}" target="_blank" rel="noopener" '
        f'class="text-2xl hover:opacity-70">'
        f'{socials_map.get(s.get("plateforme", "").lower(), "🔗")}</a>'
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


def _css_globale(brand_kit: Optional[dict]) -> str:
    """Variables CSS communes à toutes les pages."""
    from modules.pro.landing_page_builder import _tw_color_vars
    colors = _tw_color_vars(brand_kit)
    css_vars = ";".join(f"--{k.replace('_', '-')}:{v}" for k, v in colors.items())
    return css_vars


def _section_hero_simple(hero: dict) -> str:
    """Hero générique (texte + CTA + image). Réutilise le rendu landing."""
    if not hero:
        return ""
    img = hero.get("_image_url", "")
    h1 = escape(hero.get("h1", ""))
    subtitle = escape(hero.get("subtitle", ""))
    cta1 = hero.get("cta_primaire_label")
    cta_html = ""
    if cta1:
        cta_html = (
            f'<a href="{escape(hero.get("cta_primaire_url", "#"))}" '
            f'class="inline-block px-6 py-3 rounded-lg font-semibold text-white shadow-lg '
            f'hover:shadow-xl transition-all" style="background:var(--accent)">'
            f"{escape(cta1)}</a>"
        )
    cta2 = hero.get("cta_secondaire_label")
    if cta2:
        cta_html += (
            f'<a href="{escape(hero.get("cta_secondaire_url", "#"))}" '
            f'class="inline-block px-6 py-3 rounded-lg font-semibold border-2 ml-3" '
            f'style="border-color:var(--primary);color:var(--primary)">'
            f"{escape(cta2)}</a>"
        )
    img_html = (
        f'<div class="flex-1"><img src="{img}" alt="" class="rounded-2xl shadow-2xl w-full"></div>'
        if img else ""
    )
    return (
        f'<section class="py-20 md:py-28" style="background:var(--bg)">'
        f'<div class="max-w-6xl mx-auto px-6 flex flex-col md:flex-row items-center gap-12">'
        f'<div class="flex-1">'
        f'<h1 class="text-4xl md:text-5xl lg:text-6xl font-extrabold mb-6 leading-tight" '
        f'style="color:var(--primary)">{h1}</h1>'
        f'<p class="text-lg md:text-xl mb-8 opacity-80" style="color:var(--muted)">{subtitle}</p>'
        f'<div class="flex flex-wrap gap-3">{cta_html}</div></div>'
        f'{img_html}</div></section>'
    )


def _section_features_page(spec_page: dict) -> str:
    """Section features avec intro narrative + descriptions longues."""
    f = spec_page.get("features") or {}
    items = f.get("items") or []
    if not items:
        return ""
    intro = escape(f.get("intro_narrative", ""))
    intro_html = (
        f'<p class="text-base md:text-lg text-center max-w-3xl mx-auto mb-10 leading-relaxed" '
        f'style="color:var(--muted)">{intro}</p>'
    ) if intro else ""
    cards = "".join(
        f'<div class="p-6 rounded-xl bg-white shadow-md hover:shadow-xl transition-all">'
        f'<div class="text-4xl mb-4">{escape(it.get("icone", "✨"))}</div>'
        f'<h3 class="text-xl font-bold mb-3" style="color:var(--primary)">{escape(it.get("titre", ""))}</h3>'
        f'<p class="leading-relaxed text-sm md:text-base opacity-90" style="color:var(--text)">{escape(it.get("description", ""))}</p>'
        f'</div>' for it in items
    )
    return (
        f'<section class="py-20" style="background:var(--bg-alt)">'
        f'<div class="max-w-6xl mx-auto px-6">'
        f'<h2 class="text-3xl md:text-4xl font-bold text-center mb-6" style="color:var(--primary)">'
        f'{escape(f.get("titre_section", "Caractéristiques"))}</h2>'
        f'{intro_html}'
        f'<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">{cards}</div>'
        f'</div></section>'
    )


def _section_comment_ca_marche(spec_page: dict) -> str:
    """Section comment ça marche (numérotée 1-2-3-4-5)."""
    c = spec_page.get("comment_ca_marche") or {}
    etapes = c.get("etapes") or []
    if not etapes:
        return ""
    intro = escape(c.get("intro", ""))
    cards = "".join(
        f'<div class="relative">'
        f'<div class="w-14 h-14 rounded-full flex items-center justify-center text-xl font-bold text-white mb-4" '
        f'style="background:var(--accent)">{escape(e.get("numero", str(i+1)))}</div>'
        f'<h3 class="text-lg font-bold mb-2" style="color:var(--primary)">{escape(e.get("titre", ""))}</h3>'
        f'<p class="text-sm leading-relaxed opacity-90" style="color:var(--text)">{escape(e.get("description", ""))}</p>'
        f'</div>'
        for i, e in enumerate(etapes)
    )
    n = max(1, min(4, len(etapes)))
    return (
        f'<section class="py-20" style="background:var(--bg)">'
        f'<div class="max-w-6xl mx-auto px-6">'
        f'<h2 class="text-3xl md:text-4xl font-bold text-center mb-4" style="color:var(--primary)">'
        f'{escape(c.get("titre_section", "Comment ça marche"))}</h2>'
        + (f'<p class="text-center max-w-3xl mx-auto mb-12 opacity-80" style="color:var(--muted)">{intro}</p>' if intro else '<div class="mb-8"></div>')
        + f'<div class="grid grid-cols-1 md:grid-cols-{n} gap-8">{cards}</div>'
        f'</div></section>'
    )


def _section_faq(spec_page: dict, key: str = "faq") -> str:
    """Section FAQ accordéon."""
    f = spec_page.get(key) or {}
    items = f.get("items") or []
    if not items:
        return ""
    cards = "".join(
        f'<details class="bg-white rounded-lg shadow-sm p-5 cursor-pointer">'
        f'<summary class="font-semibold text-lg" style="color:var(--primary)">{escape(it.get("question", ""))}</summary>'
        f'<p class="mt-4 leading-relaxed opacity-90" style="color:var(--text)">{escape(it.get("reponse", ""))}</p>'
        f'</details>'
        for it in items
    )
    return (
        f'<section class="py-20" style="background:var(--bg-alt)">'
        f'<div class="max-w-3xl mx-auto px-6">'
        f'<h2 class="text-3xl md:text-4xl font-bold text-center mb-12" style="color:var(--primary)">'
        f'{escape(f.get("titre_section", "Questions fréquentes"))}</h2>'
        f'<div class="space-y-3">{cards}</div>'
        f'</div></section>'
    )


def _section_valeurs(spec_page: dict) -> str:
    """Section valeurs (page équipe)."""
    v = spec_page.get("valeurs") or {}
    items = v.get("items") or []
    if not items:
        return ""
    cards = "".join(
        f'<div class="p-5 rounded-xl bg-white shadow-md">'
        f'<div class="text-3xl mb-3">{escape(it.get("icone", "💎"))}</div>'
        f'<h3 class="text-lg font-bold mb-2" style="color:var(--primary)">{escape(it.get("titre", ""))}</h3>'
        f'<p class="text-sm opacity-90 leading-relaxed" style="color:var(--text)">{escape(it.get("description", ""))}</p>'
        f'</div>' for it in items
    )
    return (
        f'<section class="py-20" style="background:var(--bg)">'
        f'<div class="max-w-6xl mx-auto px-6">'
        f'<h2 class="text-3xl md:text-4xl font-bold text-center mb-12" style="color:var(--primary)">'
        f'{escape(v.get("titre_section", "Nos valeurs"))}</h2>'
        f'<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">{cards}</div>'
        f'</div></section>'
    )


def _section_intro_narrative(spec_page: dict) -> str:
    """Intro narrative longue (placée juste après le hero)."""
    intro = spec_page.get("intro_narrative")
    if not intro:
        return ""
    return (
        f'<section class="py-12" style="background:var(--bg)">'
        f'<div class="max-w-3xl mx-auto px-6">'
        f'<p class="text-lg md:text-xl leading-relaxed text-center" style="color:var(--text)">'
        f'{escape(intro)}</p>'
        f'</div></section>'
    )


def _section_services_liste(spec_page: dict) -> str:
    """Liste de services détaillés (page Services) — paragraphes longs + bullets."""
    items = spec_page.get("liste_services") or []
    if not items:
        return ""
    cards = []
    for it in items:
        bullets = it.get("bullets_inclus") or []
        bullets_html = ""
        if bullets:
            bullets_html = (
                '<ul class="mt-4 space-y-1.5">' +
                "".join(
                    f'<li class="text-sm flex items-start gap-2" style="color:var(--text)">'
                    f'<span style="color:var(--accent)">✓</span><span>{escape(b)}</span></li>'
                    for b in bullets
                ) + '</ul>'
            )
        cards.append(
            f'<div class="p-6 rounded-xl bg-white shadow-md">'
            f'<div class="text-4xl mb-4">{escape(it.get("icone", "🔧"))}</div>'
            f'<h3 class="text-2xl font-bold mb-3" style="color:var(--primary)">{escape(it.get("titre", ""))}</h3>'
            f'<p class="text-base leading-relaxed opacity-90" style="color:var(--text)">'
            f'{escape(it.get("description", ""))}</p>'
            f'{bullets_html}'
            f'</div>'
        )
    return (
        f'<section class="py-20" style="background:var(--bg)">'
        f'<div class="max-w-6xl mx-auto px-6">'
        f'<div class="grid grid-cols-1 md:grid-cols-2 gap-6">{"".join(cards)}</div>'
        f'</div></section>'
    )


def _section_equipe(spec_page: dict) -> str:
    """Grille membres équipe (page Équipe)."""
    membres = spec_page.get("membres") or []
    if not membres:
        return ""
    cards = "".join(
        f'<div class="p-6 rounded-xl bg-white shadow-md text-center">'
        f'<div class="w-20 h-20 rounded-full mx-auto mb-4 flex items-center justify-center '
        f'text-2xl font-bold text-white" style="background:var(--accent)">'
        f'{escape(m.get("avatar_initiales", "?"))}</div>'
        f'<h3 class="text-xl font-bold mb-1" style="color:var(--primary)">{escape(m.get("nom", ""))}</h3>'
        f'<div class="text-sm mb-2" style="color:var(--accent)">{escape(m.get("fonction", ""))}</div>'
        f'<p class="text-sm opacity-80" style="color:var(--text)">{escape(m.get("bio", ""))}</p>'
        f'</div>' for m in membres
    )
    return (
        f'<section class="py-20" style="background:var(--bg-alt)">'
        f'<div class="max-w-6xl mx-auto px-6">'
        f'<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">{cards}</div>'
        f'</div></section>'
    )


def _section_contact_page(spec_page: dict, slug_site: str) -> str:
    """Page Contact avec coordonnées + form POST landing-leads."""
    h = spec_page.get("hero") or {}
    info = []
    if spec_page.get("email"):
        info.append(f'<div>✉ {escape(spec_page["email"])}</div>')
    if spec_page.get("telephone"):
        info.append(f'<div>📞 {escape(spec_page["telephone"])}</div>')
    if spec_page.get("adresse"):
        info.append(f'<div>📍 {escape(spec_page["adresse"])}</div>')
    if spec_page.get("horaires"):
        info.append(f'<div>🕐 {escape(spec_page["horaires"])}</div>')

    return (
        _section_hero_simple(h)
        + f'<section class="py-20" style="background:var(--bg)">'
        + f'<div class="max-w-4xl mx-auto px-6 grid grid-cols-1 md:grid-cols-2 gap-12">'
        + f'<div class="space-y-4">{"".join(info)}</div>'
        + f'<form action="/api/v1/landing-leads/{escape(slug_site)}" method="POST" class="space-y-4">'
        + f'<input type="text" name="nom" placeholder="Nom" required class="w-full px-4 py-3 rounded-lg border border-gray-300">'
        + f'<input type="email" name="email" placeholder="Email" required class="w-full px-4 py-3 rounded-lg border border-gray-300">'
        + f'<input type="tel" name="telephone" placeholder="Téléphone" class="w-full px-4 py-3 rounded-lg border border-gray-300">'
        + f'<textarea name="message" rows="5" placeholder="Message" required class="w-full px-4 py-3 rounded-lg border border-gray-300"></textarea>'
        + f'<input type="text" name="_hp_bot" value="" tabindex="-1" autocomplete="off" style="position:absolute;left:-9999px">'
        + f'<button type="submit" class="w-full px-6 py-3 rounded-lg font-semibold text-white shadow-lg" style="background:var(--accent)">Envoyer</button>'
        + f'</form></div></section>'
    )


def _section_markdown(contenu_md: str) -> str:
    """Rend du markdown simple en HTML (titres + paragraphes)."""
    if not contenu_md:
        return ""
    # Render minimal — pour des pages légales, pas besoin d'un parser MD complet
    lignes = contenu_md.strip().split("\n")
    html = []
    for ligne in lignes:
        if ligne.startswith("# "):
            html.append(f'<h1 class="text-3xl font-bold mb-4 mt-6" style="color:var(--primary)">{escape(ligne[2:])}</h1>')
        elif ligne.startswith("## "):
            html.append(f'<h2 class="text-2xl font-bold mb-3 mt-5" style="color:var(--primary)">{escape(ligne[3:])}</h2>')
        elif ligne.startswith("### "):
            html.append(f'<h3 class="text-xl font-bold mb-2 mt-4" style="color:var(--primary)">{escape(ligne[4:])}</h3>')
        elif ligne.strip():
            html.append(f'<p class="mb-3 leading-relaxed" style="color:var(--text)">{escape(ligne)}</p>')
    return (
        f'<section class="py-12" style="background:var(--bg)">'
        f'<div class="max-w-3xl mx-auto px-6">{"".join(html)}</div></section>'
    )


def _section_blog_index(spec_page: dict, articles: list[dict]) -> str:
    """Liste des articles de blog (publié_le DESC)."""
    intro = escape(spec_page.get("intro", ""))
    cards = ""
    if articles:
        cards = "".join(
            f'<a href="/blog/{escape(a.get("slug", "#"))}" '
            f'class="block bg-white rounded-xl shadow-md hover:shadow-xl transition-all overflow-hidden">'
            + (f'<img src="{escape(a.get("hero_image_url", ""))}" alt="" class="w-full h-48 object-cover">'
               if a.get("hero_image_url") else "")
            + f'<div class="p-6">'
            f'<h3 class="text-xl font-bold mb-2" style="color:var(--primary)">{escape(a.get("titre", ""))}</h3>'
            f'<p class="text-sm opacity-80" style="color:var(--text)">{escape(a.get("resume", ""))}</p>'
            f'</div></a>'
            for a in articles
        )
    else:
        cards = (
            f'<p class="text-center col-span-full opacity-70" style="color:var(--muted)">'
            f"Aucun article publié pour le moment.</p>"
        )
    return (
        f'<section class="py-20" style="background:var(--bg)">'
        f'<div class="max-w-6xl mx-auto px-6">'
        + (f'<p class="text-lg text-center mb-12" style="color:var(--muted)">{intro}</p>' if intro else "")
        + f'<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">{cards}</div>'
        f'</div></section>'
    )


def construire_html_page(
    spec: dict,
    type_page: str,
    *,
    brand_kit: Optional[dict] = None,
    slug_site: str = "",
    articles: Optional[list[dict]] = None,
) -> str:
    """Rend le HTML d'UNE page du site (avec nav + footer communs).

    Args:
        spec       : SiteSpec global (issu de Sonnet)
        type_page  : "home" | "services" | "equipe" | "contact" | ...
        brand_kit  : pour les couleurs/fonts
        slug_site  : utilisé dans l'action du form contact
        articles   : liste des articles pour blog_index
    """
    page_spec = (spec.get("pages") or {}).get(type_page, {})
    if not page_spec:
        return ""

    css_vars = _css_globale(brand_kit)
    nom_marque = spec.get("nom_marque") or "Yukpo"
    titre = escape(page_spec.get("titre_seo") or f"{_LABELS_PAGE.get(type_page, type_page)} — {nom_marque}")
    desc = escape(page_spec.get("description_seo") or "")
    favicon = spec.get("_favicon_url") or ""

    # Composition des sections selon type de page
    sections = []
    sections.append(_construire_nav(spec, type_page))

    if type_page == "home":
        sections.append(_section_hero_simple(page_spec.get("hero") or {}))
        sections.append(_section_features_page(page_spec))
        sections.append(_section_comment_ca_marche(page_spec))
        # Stats + témoignages réutilisent les helpers landing existants
        from modules.pro.landing_page_builder import (
            _section_stats, _section_temoignages, _section_cta_final,
        )
        sections.append(_section_stats({"stats": page_spec.get("stats", {})}))
        sections.append(_section_temoignages({"temoignages": page_spec.get("temoignages", {})}))
        sections.append(_section_cta_final({"cta_final": page_spec.get("cta_final", {})}))
        sections.append(_section_faq(page_spec, "faq"))
    elif type_page == "services":
        sections.append(_section_hero_simple(page_spec.get("hero") or {}))
        sections.append(_section_intro_narrative(page_spec))
        sections.append(_section_services_liste(page_spec))
        sections.append(_section_comment_ca_marche({"comment_ca_marche": page_spec.get("process") or {}}))
        from modules.pro.landing_page_builder import _section_cta_final
        sections.append(_section_cta_final({"cta_final": page_spec.get("cta_final", {})}))
    elif type_page == "equipe":
        sections.append(_section_hero_simple(page_spec.get("hero") or {}))
        sections.append(_section_intro_narrative(page_spec))
        sections.append(_section_equipe(page_spec))
        sections.append(_section_valeurs(page_spec))
    elif type_page == "blog_index":
        sections.append(_section_blog_index(page_spec, articles or []))
    elif type_page == "contact":
        sections.append(_section_contact_page(page_spec, slug_site))
        sections.append(_section_faq(page_spec, "faq_rapide"))
    elif type_page in ("mentions_legales", "confidentialite", "cgv"):
        sections.append(_section_markdown(page_spec.get("contenu_md", "")))
    else:
        # Page custom : on render hero + features si dispo
        sections.append(_section_hero_simple(page_spec.get("hero") or {}))
        sections.append(_section_features_page(page_spec))

    sections.append(_construire_footer(spec))

    body = "\n".join(s for s in sections if s)

    return f"""<!DOCTYPE html>
<html lang="{escape(page_spec.get("langue") or spec.get("langue_principale") or "fr")}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{titre}</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="{titre}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="website">
{f'<link rel="icon" href="{favicon}">' if favicon else ""}
<meta name="generator" content="Yukpo Site Builder">
<meta name="yukpo-site" content="{escape(slug_site)}">
<meta name="yukpo-page-type" content="{escape(type_page)}">
<script src="https://cdn.tailwindcss.com"></script>
<style>
:root {{ {css_vars} }}
html {{ scroll-behavior: smooth; }}
body {{ font-family: var(--font-corps); color: var(--text); background: var(--bg); margin: 0; }}
h1, h2, h3, h4 {{ font-family: var(--font-titre); }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def construire_sitemap(spec: dict, url_base: str, articles: list[dict]) -> str:
    """Génère le sitemap.xml du site (toutes les pages + tous les articles publiés)."""
    urls = []
    pages = (spec.get("pages") or {})
    for type_page in pages.keys():
        path = _SLUGS_DEFAUT.get(type_page, type_page)
        url = url_base.rstrip("/") + ("/" if not path else f"/{path}")
        urls.append(f"<url><loc>{escape(url)}</loc></url>")
    for a in articles:
        if a.get("publie"):
            url = f"{url_base.rstrip('/')}/blog/{escape(a.get('slug', ''))}"
            urls.append(f"<url><loc>{url}</loc></url>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )


def construire_robots_txt(url_base: str) -> str:
    return (
        "User-agent: *\nAllow: /\n"
        f"Sitemap: {url_base.rstrip('/')}/sitemap.xml\n"
    )


def construire_arborescence_zip(
    spec: dict,
    *,
    slug_site: str,
    brand_kit: Optional[dict],
    url_public: str,
    articles: Optional[list[dict]] = None,
    pages_par_langue: Optional[dict[str, dict]] = None,
) -> dict[str, bytes]:
    """Retourne {path_dans_zip: bytes} pour TOUTES les pages du site +
    sitemap.xml + robots.txt. Pivot pour publish multi-fichiers Netlify.

    Args:
        spec              : SiteSpec en langue principale (legacy compat)
        pages_par_langue  : {langue_code: {type_page: contenu_json}} —
                            Phase C4 multi-langue. Si fourni, les pages
                            traduites sont déployées sous /<langue>/...
                            ex. /en/services/index.html
    """
    files: dict[str, bytes] = {}
    pages = (spec.get("pages") or {})
    articles = articles or []

    # 1. Pages en langue principale (racine /, /services, /equipe…)
    for type_page in pages.keys():
        html = construire_html_page(
            spec, type_page,
            brand_kit=brand_kit, slug_site=slug_site, articles=articles,
        )
        if not html:
            continue
        path_url = _SLUGS_DEFAUT.get(type_page, type_page)
        if type_page == "home":
            files["index.html"] = html.encode("utf-8")
        else:
            files[f"{path_url}/index.html"] = html.encode("utf-8")

    # 2. Pages traduites (Phase C4) — sous /<langue>/<slug>
    if pages_par_langue:
        for langue, pages_lang in pages_par_langue.items():
            if not pages_lang or langue == spec.get("langue_principale"):
                continue
            spec_lang = {**spec, "pages": pages_lang}
            for type_page in pages_lang.keys():
                html = construire_html_page(
                    spec_lang, type_page,
                    brand_kit=brand_kit, slug_site=slug_site, articles=articles,
                )
                if not html:
                    continue
                path_url = _SLUGS_DEFAUT.get(type_page, type_page)
                if type_page == "home":
                    files[f"{langue}/index.html"] = html.encode("utf-8")
                else:
                    files[f"{langue}/{path_url}/index.html"] = html.encode("utf-8")

    # 3. Articles de blog publiés
    for a in articles:
        if a.get("publie"):
            article_html = construire_html_article(spec, a,
                                                    brand_kit=brand_kit,
                                                    slug_site=slug_site)
            files[f"blog/{a.get('slug', 'article')}/index.html"] = article_html.encode("utf-8")

    files["sitemap.xml"] = construire_sitemap(spec, url_public, articles).encode("utf-8")
    files["robots.txt"] = construire_robots_txt(url_public).encode("utf-8")
    return files


def construire_html_article(
    spec: dict, article: dict,
    *, brand_kit: Optional[dict] = None, slug_site: str = "",
) -> str:
    """Rend une page article de blog (hero image + contenu markdown)."""
    css_vars = _css_globale(brand_kit)
    titre = escape(article.get("titre", "Article"))
    seo_titre = escape(article.get("seo_titre") or titre)
    seo_desc = escape(article.get("seo_desc") or article.get("resume") or "")
    hero_img = article.get("hero_image_url", "")
    favicon = spec.get("_favicon_url") or ""

    contenu = _section_markdown(article.get("contenu_md") or "")
    hero_html = ""
    if hero_img:
        hero_html = (
            f'<section class="py-12" style="background:var(--bg-alt)">'
            f'<div class="max-w-3xl mx-auto px-6">'
            f'<img src="{escape(hero_img)}" alt="" class="w-full rounded-2xl shadow-2xl mb-8">'
            f'<h1 class="text-4xl font-extrabold mb-4" style="color:var(--primary)">{titre}</h1>'
            f'<p class="text-sm opacity-70" style="color:var(--muted)">'
            f'Par {escape(article.get("auteur") or "Yukpo")}</p>'
            f'</div></section>'
        )
    return f"""<!DOCTYPE html>
<html lang="{escape(article.get("langue") or "fr")}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{seo_titre}</title>
<meta name="description" content="{seo_desc}">
<meta property="og:title" content="{seo_titre}">
<meta property="og:description" content="{seo_desc}">
<meta property="og:type" content="article">
{f'<meta property="og:image" content="{escape(hero_img)}">' if hero_img else ""}
{f'<link rel="icon" href="{favicon}">' if favicon else ""}
<script src="https://cdn.tailwindcss.com"></script>
<style>
:root {{ {css_vars} }}
body {{ font-family: var(--font-corps); color: var(--text); background: var(--bg); margin: 0; }}
</style>
</head>
<body>
{_construire_nav(spec, "blog_index")}
{hero_html}
{contenu}
{_construire_footer(spec)}
</body>
</html>
"""


# ─── Génération d'article de blog AI-powered (Phase C5) ──────────────────────

_PROMPT_ARTICLE = """Tu es un rédacteur SEO expert capable de produire des \
articles de blog percutants dans N'IMPORTE QUELLE LANGUE :

  • FR (français) — registre adapté Afrique francophone ou France selon contexte
  • EN (anglais international ou anglais africain)
  • AR (arabe — RTL, registre formel)
  • PT (portugais — Portugal ou Brésil ou Mozambique selon contexte)
  • ES, DE, IT, ZH, JA, RU, HI, SW (swahili), HA (haoussa), WO (wolof),
    LN (lingala), AM (amharique), TR (turc)
  • Et TOUTE autre langue demandée par l'utilisateur

Tu reçois un sujet + nom de la marque + langue cible + (optionnellement)
angle/audience/ton. Tu RENVOIES UN JSON strict (pas de texte avant/après) :

{
  "titre": "Titre accrocheur (max 80 chars, dans la langue cible)",
  "slug": "slug-kebab-case-seo-en-ascii-toujours",
  "resume": "Résumé teasing 2-3 phrases (max 280 chars, langue cible)",
  "contenu_md": "Article complet en markdown (1500-3000 mots) DANS LA LANGUE CIBLE — H2/H3, paragraphes courts, listes, exemples concrets ancrés dans le contexte géographique pertinent",
  "hero_image_prompt": "Description EN 40-80 mots pour hero image photoréaliste (TOUJOURS en anglais, c'est le prompt fal.ai)",
  "seo_titre": "Titre SEO 60 chars (langue cible)",
  "seo_desc": "Description SEO 155 chars (langue cible)",
  "seo_keywords": ["mot-clé 1", "mot-clé 2", ...8-12 keywords ciblés DANS LA LANGUE CIBLE]
}

Règles :
1. Markdown VALIDE (## H2, ### H3, paragraphes, listes -)
2. CONTENU 100% dans la langue cible (sauf hero_image_prompt qui reste EN)
3. Slug toujours en ASCII kebab-case (pour URL valide)
4. Exemples ancrés dans le contexte géographique adapté à la langue/marque
5. Pas d'invention de chiffres faux — utilise des termes qualitatifs si pas de source
6. CTA implicite vers les services de la marque en fin d'article
7. Si AR/HE : contenu en RTL respecté côté texte (markdown se rend correctement)
"""


async def generer_article_blog(
    sujet: str, *, nom_marque: str, langue: str = "fr",
    cible: Optional[str] = None, ton: Optional[str] = None,
) -> tuple[dict, list[dict]]:
    """LLM tier élevé → article complet + image hero prompt dans N'IMPORTE
    QUELLE langue (FR/EN/AR/PT/ES/DE/IT/ZH/JA/RU/HI/SW/HA/WO/LN/AM/TR/…).
    """
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire

    user_prompt = (
        f"SUJET : {sujet}\n"
        f"MARQUE : {nom_marque}\n"
        f"LANGUE CIBLE : {langue}\n"
    )
    if cible:
        user_prompt += f"CIBLE LECTEUR : {cible}\n"
    if ton:
        user_prompt += f"TON : {ton}\n"
    user_prompt += "\nProduis le JSON article strict."

    # Article 1500-3000 mots → tier élevé (CLAUDE_OPUS → GPT-5 si LLM=gpt)
    rep = await ia_client.appeler(
        prompt=user_prompt, systeme=_PROMPT_ARTICLE,
        mode=ModeIA.REDACTION, max_tokens_override=14000,
        json_attendu=True, utiliser_cache=False,
        forcer_modele=ModelePrioritaire.CLAUDE_OPUS,
    )
    texte = rep.contenu if hasattr(rep, "contenu") else str(rep)
    m = re.search(r"\{[\s\S]*\}", texte)
    if not m:
        raise ValueError("LLM n'a pas produit de JSON parseable")
    article = json.loads(m.group(0))

    # Hero image générée à côté (data URI)
    if article.get("hero_image_prompt"):
        try:
            from modules.bureau import image_gen as _ig
            png = await _ig.generer_image(
                prompt=article["hero_image_prompt"], mode="premium",
                format_="landscape_16_9", timeout_s=120.0,
            )
            if png:
                article["hero_image_url"] = (
                    "data:image/png;base64," + base64.b64encode(png).decode()
                )
        except Exception as e:
            logger.warning(f"[Article/img] hero échec : {e}")

    usage = {
        "tokens_in":  getattr(rep, "tokens_input", 0),
        "tokens_out": getattr(rep, "tokens_output", 0),
        "modele":     getattr(rep, "modele_utilise", "sonnet"),
        "etape":      "article_blog",
    }
    return article, [usage]
