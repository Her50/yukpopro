"""Phase D — YukpoShop : magic import IA + storefront builder.

D2 Différenciateur clé : 1-10 photos d'un produit → LLM Vision Opus génère
AUTOMATIQUEMENT le produit complet (titre vendeur SEO, description marketing
200-400 mots, prix suggéré, catégorie, tags, variantes détectées). Aucune
saisie manuelle obligatoire — UX "upload + 1 clic → produit prêt à vendre".

Réutilise :
  • image_gen (vision Claude Opus / GPT-5 unified API)
  • storage R2 pour persister les photos uploadées
  • site_builder.construire_arborescence_zip pattern pour le storefront
  • Brand LoRA auto-pickup pour la régen d'images promotionnelles

Pas de scraping prix externe v1 — le LLM estime via sa connaissance du marché
africain francophone (qualité acceptable pour MVP, scraping Jumia/Alibaba
peut être ajouté plus tard via modules/pro/recherche_web_pro).
"""
from __future__ import annotations

import base64
import json
import logging
import re
from html import escape
from typing import Any, Optional

logger = logging.getLogger("yukpo_assurance.pro.shop_builder")


# ─── D2 — Magic import IA depuis photos ──────────────────────────────────────

_PROMPT_SYSTEME_MAGIC_IMPORT = """Tu es un expert e-commerce + copywriter \
SEO qui crée des fiches produit complètes et persuasives à partir de photos.

Tu reçois 1 à 10 photos d'un MÊME produit (différents angles/details).
Tu RENVOIES UN JSON strict (pas de texte avant/après) :

{
  "titre": "Titre vendeur SEO (max 70 chars) — accrocheur + mot-clé principal",
  "slug": "slug-kebab-case-ascii-pour-url",
  "description_courte": "Hook 2 lignes (max 280 chars) — bénéfice client clé",
  "description_longue": "Markdown 200-400 mots : présentation, bénéfices clients (## H2), caractéristiques détaillées (liste -), conseils d'utilisation, garantie/qualité, CTA implicite",
  "categorie_suggeree": "vêtements | maroquinerie | cosmétique | électronique | artisanat | alimentaire | mobilier | bijouterie | déco | sport | beauté | enfants | high-tech | autre",
  "sous_categorie": "Plus précis ex: 'sacs à main cuir', 'parfums femme', 'écouteurs bluetooth'",
  "couleur_dominante": "Mot simple ex: 'noir', 'rouge', 'multicolore'",
  "matiere": "Mot/courte description ex: 'cuir véritable', 'coton bio', 'plastique ABS'",
  "tags": ["mot-clé 1", "mot-clé 2", ...8-12 keywords SEO + hashtags réseaux sociaux mélangés],
  "prix_suggere": 25000,
  "prix_suggere_devise": "XAF",
  "prix_explication": "Justification rapide du prix : positionnement marché, qualité perçue, comparables locaux",
  "variantes_detectees": [
    {"nom": "Couleur", "valeurs": ["noir", "rouge", "bleu"]},
    {"nom": "Taille",  "valeurs": ["S", "M", "L"]}
  ],
  "stock_initial_suggere": 10,
  "seo_titre": "Titre meta SEO 60 chars",
  "seo_desc":  "Meta description 155 chars",
  "seo_keywords": ["8-12 keywords ciblés long-tail"]
}

Règles :
1. TON COMMERCIAL chaleureux, pas robotique. Adapte au public africain francophone
   (Cameroun/CI/Sénégal/Burkina/Mali — vocabulaire familier, fierté locale).
2. PRIX : estimation réaliste pour le marché LOCAL en XAF (Cameroun/CI = 1 EUR ≈ 656 XAF).
   Si produit clairement haut de gamme/import → prix premium ; si bas de gamme local →
   prix accessible. Ne mens pas, donne une fourchette crédible.
3. VARIANTES : ne détecte que les variantes VISIBLES dans les photos (taille mentionnée,
   couleurs différentes). Ne jamais inventer.
4. SLUG : ASCII kebab-case, ≤80 chars, sans accents, basé sur le titre.
5. DESCRIPTION LONGUE : structurée Markdown, parle au CLIENT, pas au marchand.
6. SEO_KEYWORDS : mix mots-clés courts + long-tail locaux ("sac main femme Douala",
   "parfum oriental Yaoundé", etc.).
7. SOUS_CATEGORIE : précise pour faciliter le filtre catalogue.
8. Si les photos montrent plusieurs PRODUITS différents (pas variantes) → renvoie
   un message d'erreur dans le champ "erreur_detection" et n'envoie rien d'autre.
"""


async def magic_import_depuis_photos(
    photos_b64: list[str],
    *,
    brief_optionnel: str = "",
    categorie_hint: Optional[str] = None,
    pays: str = "CM",
    devise: str = "XAF",
) -> tuple[dict, list[dict]]:
    """LLM Vision Opus → fiche produit complète à partir de N photos.

    Args:
        photos_b64 : list de data URIs "data:image/...;base64,..." (1-10 max)
        brief_optionnel : texte libre du marchand ("c'est un sac à main cuir
            premium Italie") — utile si les photos seules ne suffisent pas
        categorie_hint : si l'utilisateur connaît déjà la catégorie

    Returns:
        (produit_data, usages_llm) — produit_data prêt à insérer en DB
    """
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire

    if not photos_b64:
        raise ValueError("Au moins 1 photo requise")
    if len(photos_b64) > 10:
        photos_b64 = photos_b64[:10]

    user_prompt = (
        f"PAYS DU MARCHAND : {pays}\n"
        f"DEVISE LOCALE : {devise}\n"
    )
    if brief_optionnel:
        user_prompt += f"BRIEF MARCHAND : {brief_optionnel[:600]}\n"
    if categorie_hint:
        user_prompt += f"CATÉGORIE HINT : {categorie_hint}\n"
    user_prompt += (
        f"\nNombre de photos fournies : {len(photos_b64)}\n"
        f"Produis le JSON produit strict en analysant TOUTES les photos."
    )

    # Vision + universalité + qualité top : CLAUDE_OPUS → GPT-5 si LLM_PRIMAIRE=gpt
    rep = await ia_client.appeler(
        prompt=user_prompt,
        systeme=_PROMPT_SYSTEME_MAGIC_IMPORT,
        mode=ModeIA.RAISONNEMENT,
        images_b64=photos_b64,
        max_tokens_override=16000,
        json_attendu=True,
        utiliser_cache=False,
        forcer_modele=ModelePrioritaire.CLAUDE_OPUS,
    )
    texte = rep.contenu if hasattr(rep, "contenu") else str(rep)
    m = re.search(r"\{[\s\S]*\}", texte)
    if not m:
        raise ValueError("LLM n'a pas produit de JSON parseable")
    produit = json.loads(m.group(0))

    if produit.get("erreur_detection"):
        raise ValueError(f"Détection : {produit['erreur_detection']}")

    usage = {
        "tokens_in":  getattr(rep, "tokens_input", 0),
        "tokens_out": getattr(rep, "tokens_output", 0),
        "modele":     getattr(rep, "modele_utilise", "opus-vision"),
        "etape":      "shop_magic_import",
    }
    return produit, [usage]


# ─── Storefront public — HTML PWA mobile-first ───────────────────────────────


def _css_globale_storefront(brand_kit: Optional[dict]) -> str:
    """CSS variables réutilisées par toutes les pages du storefront."""
    from modules.pro.landing_page_builder import _tw_color_vars
    colors = _tw_color_vars(brand_kit)
    return ";".join(f"--{k.replace('_', '-')}:{v}" for k, v in colors.items())


def _construire_nav_storefront(boutique: dict, panier_url: str = "/panier") -> str:
    """Nav top sticky commune (logo + cherche + panier)."""
    nom = escape(boutique.get("nom") or "Boutique")
    logo = boutique.get("logo_url", "")
    logo_html = (
        f'<img src="{escape(logo)}" alt="" class="h-10 w-auto rounded-lg">'
        if logo else f'<span class="text-xl font-bold" style="color:var(--primary)">{nom}</span>'
    )
    return (
        f'<nav class="sticky top-0 z-50 backdrop-blur-md bg-white/95 shadow-sm">'
        f'<div class="max-w-6xl mx-auto px-4 py-3 flex justify-between items-center gap-4">'
        f'<a href="/" class="flex items-center gap-2">{logo_html}</a>'
        f'<a href="{panier_url}" id="cart-link" class="relative p-2 rounded-lg hover:bg-slate-100">'
        f'<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
        f'<circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/>'
        f'<path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg>'
        f'<span id="cart-count" class="absolute -top-1 -right-1 bg-rose-500 text-white text-xs '
        f'rounded-full w-5 h-5 flex items-center justify-center hidden">0</span>'
        f'</a></div></nav>'
    )


def _construire_footer_storefront(boutique: dict) -> str:
    annee = 2026
    return (
        f'<footer class="py-10 mt-12" style="background:var(--primary);color:white">'
        f'<div class="max-w-6xl mx-auto px-4 text-center">'
        f'<p class="text-sm opacity-80">© {annee} {escape(boutique.get("nom", "Boutique"))}</p>'
        f'<p class="text-xs opacity-60 mt-2">'
        f'Boutique propulsée par <a href="https://yukpomnang.com" target="_blank" '
        f'rel="noopener" style="color:inherit;text-decoration:underline">YukpoPro</a>'
        f'</p></div></footer>'
    )


def _card_marketplace_item(item: dict) -> str:
    """Piste 2 — Card pour un item externe (marketplace Yukpo Rust).

    Diffère de `_card_produit` :
    - Link en target=_blank vers la boutique externe (ou marketplace yukpo)
    - Badge discret « via Yukpo marketplace »
    - Affiche distance si dispo
    """
    titre = escape(item.get("titre") or "Service")
    prix = item.get("prix") or 0
    devise = escape(item.get("devise") or "XAF")
    photo = item.get("photo_url")
    vendeur = escape(item.get("vendeur_nom") or "")
    boutique_url = item.get("boutique_url")
    # Fallback URL : page marketplace publique si dispo
    href = boutique_url or (
        f"https://yukpomnang.com/services/{item.get('service_id')}"
        if item.get("service_id") else "#"
    )
    distance = item.get("distance_km")
    dist_html = (
        f'<div class="text-xs opacity-60 mt-0.5">{int(distance)} km</div>'
        if isinstance(distance, (int, float)) and distance > 0 else ""
    )
    prix_html = (
        f'<span class="font-bold" style="color:var(--accent)">{int(prix)} {devise}</span>'
        if prix else ""
    )
    return (
        f'<a href="{escape(href)}" target="_blank" rel="noopener" '
        f'class="block bg-white rounded-xl shadow-md hover:shadow-xl transition overflow-hidden relative">'
        f'<div class="absolute top-2 right-2 z-10 bg-violet-600/90 text-white text-[10px] '
        f'font-semibold px-2 py-0.5 rounded-full">Yukpo</div>'
        + (f'<img src="{escape(photo)}" alt="" class="w-full aspect-square object-cover">'
           if photo else
           f'<div class="w-full aspect-square bg-slate-100 flex items-center justify-center text-slate-400 text-4xl">🌍</div>')
        + f'<div class="p-3">'
        f'<h3 class="font-semibold text-sm truncate" style="color:var(--primary)">{titre}</h3>'
        + (f'<div class="text-xs opacity-70 truncate">{vendeur}</div>' if vendeur else "")
        + f'<div class="mt-1 text-sm">{prix_html}</div>'
        + dist_html
        + f'</div></a>'
    )


def _section_cross_sell_html(items: list[dict], titre: str = "Autres marchands près de chez vous") -> str:
    """Piste 2 — Section conditionnelle injectée dans home + pages produit.
    Retourne chaîne vide si items=[] (pas de rendu visible)."""
    if not items:
        return ""
    cards_html = "".join(_card_marketplace_item(it) for it in items[:6])
    return (
        f'<section class="py-8 bg-violet-50/40"><div class="max-w-6xl mx-auto px-4">'
        f'<div class="flex items-center justify-between mb-4">'
        f'<h2 class="text-xl font-bold" style="color:var(--primary)">{escape(titre)}</h2>'
        f'<div class="text-xs opacity-60">via Yukpo marketplace</div>'
        f'</div>'
        f'<div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">{cards_html}</div>'
        f'</div></section>'
    )


def _page_accueil_html(
    boutique: dict, produits_featured: list[dict], categories: list[dict],
    cross_sell_items: Optional[list[dict]] = None,
) -> str:
    """Page d'accueil : hero + grid produits featured + categories + cross-sell."""
    desc = escape(boutique.get("description") or "")
    cats_html = "".join(
        f'<a href="/c/{escape(c["slug"])}" class="block bg-white rounded-xl p-4 shadow-md hover:shadow-xl text-center">'
        + (f'<img src="{escape(c.get("image_url", ""))}" alt="" class="w-full h-32 object-cover rounded mb-2">' if c.get("image_url") else "")
        + f'<div class="font-semibold" style="color:var(--primary)">{escape(c["nom"])}</div></a>'
        for c in categories
    )
    prods_html = "".join(_card_produit(p, boutique) for p in produits_featured)

    return (
        f'<section class="py-12 md:py-20" style="background:linear-gradient(135deg,var(--bg),var(--bg-alt))">'
        f'<div class="max-w-6xl mx-auto px-4 text-center">'
        f'<h1 class="text-3xl md:text-5xl font-extrabold mb-4" style="color:var(--primary)">'
        f'{escape(boutique.get("nom", "Bienvenue"))}</h1>'
        f'<p class="text-lg md:text-xl opacity-80 max-w-2xl mx-auto">{desc}</p>'
        f'</div></section>'
        + (f'<section class="py-8"><div class="max-w-6xl mx-auto px-4">'
           f'<h2 class="text-2xl font-bold mb-6" style="color:var(--primary)">Nos catégories</h2>'
           f'<div class="grid grid-cols-2 md:grid-cols-4 gap-4">{cats_html}</div></div></section>'
           if categories else "")
        + (f'<section class="py-8"><div class="max-w-6xl mx-auto px-4">'
           f'<h2 class="text-2xl font-bold mb-6" style="color:var(--primary)">À la une</h2>'
           f'<div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">{prods_html}</div></div></section>'
           if produits_featured else "")
        + _section_cross_sell_html(cross_sell_items or [])
    )


def _card_produit(p: dict, boutique: dict) -> str:
    """Card produit réutilisée sur home + catalogue + recherche."""
    photo = ""
    if p.get("photos_urls_json"):
        photos = p["photos_urls_json"]
        if isinstance(photos, list) and photos:
            photo = photos[0]
    devise = escape(p.get("devise") or boutique.get("devise") or "XAF")
    prix_aff = (
        f'<span class="line-through opacity-60 text-sm">{int(p["prix_unit"])} {devise}</span> '
        f'<span class="font-bold text-rose-600">{int(p["prix_unit_promo"])} {devise}</span>'
        if p.get("prix_unit_promo") else
        f'<span class="font-bold" style="color:var(--accent)">{int(p["prix_unit"])} {devise}</span>'
    )
    return (
        f'<a href="/p/{escape(p["slug"])}" class="block bg-white rounded-xl shadow-md hover:shadow-xl transition overflow-hidden">'
        + (f'<img src="{escape(photo)}" alt="" class="w-full aspect-square object-cover">' if photo
           else f'<div class="w-full aspect-square bg-slate-100 flex items-center justify-center text-slate-400">📦</div>')
        + f'<div class="p-3">'
        f'<h3 class="font-semibold text-sm md:text-base truncate" style="color:var(--primary)">{escape(p.get("titre", ""))}</h3>'
        f'<div class="mt-1 text-sm">{prix_aff}</div>'
        f'</div></a>'
    )


def _page_produit_html(
    p: dict, boutique: dict, autres_produits: list[dict],
    cross_sell_items: Optional[list[dict]] = None,
) -> str:
    """Page produit : galerie + variantes + add-to-cart + autres produits."""
    photos = p.get("photos_urls_json") or []
    photos_html = "".join(
        f'<img src="{escape(ph)}" alt="" class="rounded-xl shadow-md w-full">'
        for ph in (photos if isinstance(photos, list) else [])
    )
    if not photos_html:
        photos_html = (
            '<div class="rounded-xl bg-slate-100 aspect-square flex items-center '
            'justify-center text-slate-400 text-6xl">📦</div>'
        )

    devise = escape(p.get("devise") or boutique.get("devise") or "XAF")
    prix_aff = (
        f'<span class="text-2xl line-through opacity-60">{int(p["prix_unit"])} {devise}</span> '
        f'<span class="text-3xl font-extrabold text-rose-600">{int(p["prix_unit_promo"])} {devise}</span>'
        if p.get("prix_unit_promo") else
        f'<span class="text-3xl font-extrabold" style="color:var(--accent)">{int(p["prix_unit"])} {devise}</span>'
    )

    variantes_html = ""
    variantes = p.get("variantes_json") or []
    if isinstance(variantes, list) and variantes:
        for vgroup in variantes:
            if isinstance(vgroup, dict):
                vals = vgroup.get("valeurs") or []
                if vals:
                    variantes_html += (
                        f'<div class="mb-3"><div class="text-sm font-semibold mb-2">{escape(vgroup.get("nom", "Variante"))}</div>'
                        f'<div class="flex flex-wrap gap-2">'
                        + "".join(
                            f'<button class="variante-btn px-3 py-1.5 border-2 border-slate-300 rounded-lg text-sm hover:border-violet-500" '
                            f'data-var-group="{escape(vgroup.get("nom", ""))}" data-var-val="{escape(v)}">{escape(v)}</button>'
                            for v in vals
                        ) + '</div></div>'
                    )

    desc_md = p.get("description_longue") or ""
    desc_html_lines = []
    for ligne in desc_md.split("\n"):
        l = ligne.strip()
        if l.startswith("## "):
            desc_html_lines.append(f'<h2 class="text-xl font-bold mt-4 mb-2" style="color:var(--primary)">{escape(l[3:])}</h2>')
        elif l.startswith("- "):
            desc_html_lines.append(f'<li>{escape(l[2:])}</li>')
        elif l:
            desc_html_lines.append(f'<p class="mb-2">{escape(l)}</p>')
    desc_html = "".join(desc_html_lines)

    autres_html = "".join(_card_produit(a, boutique) for a in autres_produits[:4])

    return (
        f'<section class="py-8"><div class="max-w-6xl mx-auto px-4 grid grid-cols-1 md:grid-cols-2 gap-8">'
        f'<div class="space-y-3">{photos_html}</div>'
        f'<div>'
        f'<h1 class="text-2xl md:text-3xl font-bold mb-3" style="color:var(--primary)">{escape(p.get("titre", ""))}</h1>'
        f'<p class="text-slate-600 mb-4">{escape(p.get("description_courte") or "")}</p>'
        f'<div class="mb-4">{prix_aff}</div>'
        f'{variantes_html}'
        f'<div class="flex gap-2 mb-6">'
        f'<input type="number" id="qte" value="1" min="1" max="{p.get("stock", 99)}" '
        f'class="w-20 px-3 py-2 border border-slate-300 rounded-lg">'
        f'<button onclick="ajouterAuPanier({p["id"]}, {json.dumps(p.get("titre"))}, {p.get("prix_unit_promo") or p.get("prix_unit", 0)}, {json.dumps((p.get("photos_urls_json") or [None])[0] or "")})" '
        f'class="flex-grow px-6 py-3 rounded-lg text-white font-semibold shadow-lg" style="background:var(--accent)">'
        f'🛒 Ajouter au panier</button></div>'
        f'<div class="prose max-w-none">{desc_html}</div>'
        f'</div></div></section>'
        + (f'<section class="py-8 bg-slate-50"><div class="max-w-6xl mx-auto px-4">'
           f'<h2 class="text-xl font-bold mb-4" style="color:var(--primary)">Vous aimerez aussi</h2>'
           f'<div class="grid grid-cols-2 md:grid-cols-4 gap-4">{autres_html}</div></div></section>'
           if autres_html else "")
        + _section_cross_sell_html(
            cross_sell_items or [],
            titre="D'autres marchands à découvrir",
          )
    )


def _page_panier_checkout_html(boutique: dict, api_base: str = "") -> str:
    """Page panier + checkout. Logique JS côté client (localStorage cart)."""
    devise = escape(boutique.get("devise") or "XAF")
    api_post = (
        f"{api_base.rstrip('/')}/api/v1/shop/public/{escape(boutique['slug'])}/orders"
        if api_base else f"/api/v1/shop/public/{escape(boutique['slug'])}/orders"
    )
    return (
        f'<section class="py-8"><div class="max-w-3xl mx-auto px-4">'
        f'<h1 class="text-2xl font-bold mb-6" style="color:var(--primary)">Mon panier</h1>'
        f'<div id="cart-items" class="space-y-3 mb-6"></div>'
        f'<div id="cart-total" class="text-right text-xl font-bold mb-6">Total : 0 {devise}</div>'
        f'<h2 class="text-xl font-bold mb-3" style="color:var(--primary)">Vos coordonnées</h2>'
        f'<form id="checkout-form" class="space-y-3 mb-6">'
        f'<input type="text" name="client_nom" placeholder="Nom complet" required '
        f'class="w-full px-4 py-3 rounded-lg border border-slate-300">'
        f'<input type="tel" name="client_telephone" placeholder="Téléphone (WhatsApp idéalement)" required '
        f'class="w-full px-4 py-3 rounded-lg border border-slate-300">'
        f'<input type="email" name="client_email" placeholder="Email (optionnel)" '
        f'class="w-full px-4 py-3 rounded-lg border border-slate-300">'
        f'<input type="text" name="ville" placeholder="Ville de livraison" required '
        f'class="w-full px-4 py-3 rounded-lg border border-slate-300">'
        f'<textarea name="adresse" rows="2" placeholder="Adresse précise / instructions" '
        f'class="w-full px-4 py-3 rounded-lg border border-slate-300"></textarea>'
        f'<select name="provider" required class="w-full px-4 py-3 rounded-lg border border-slate-300">'
        f'<option value="orange_money">Orange Money</option>'
        f'<option value="mtn_momo">MTN Mobile Money</option>'
        f'<option value="stripe">Carte bancaire (Stripe)</option>'
        f'<option value="cash">Paiement à la livraison</option>'
        f'</select>'
        f'<input type="text" name="_hp_bot" tabindex="-1" autocomplete="off" '
        f'style="position:absolute;left:-9999px">'
        f'<button type="submit" class="w-full px-6 py-3 rounded-lg text-white font-semibold shadow-lg" style="background:var(--accent)">'
        f'Valider la commande</button>'
        f'</form>'
        f'<div id="checkout-result"></div>'
        f'</div></section>'
        f'<script>'
        f'const API_POST = "{api_post}";'
        f'function getCart() {{ try {{ return JSON.parse(localStorage.getItem("yk_cart_{boutique["slug"]}") || "[]"); }} catch {{ return []; }} }}'
        f'function setCart(c) {{ localStorage.setItem("yk_cart_{boutique["slug"]}", JSON.stringify(c)); refresh(); }}'
        f'function refresh() {{'
        f'  const c = getCart();'
        f'  document.getElementById("cart-items").innerHTML = c.length ? c.map((it,i) => '
        f'    `<div class="flex items-center gap-3 p-3 bg-white rounded-lg shadow">'
        f'    ${{it.photo ? `<img src="${{it.photo}}" class="w-16 h-16 rounded object-cover">` : ""}}'
        f'    <div class="flex-grow"><div class="font-semibold">${{it.titre}}</div>'
        f'    <div class="text-sm text-slate-600">${{it.prix}} {devise} × ${{it.qte}}</div></div>'
        f'    <button onclick="retirer(${{i}})" class="text-rose-500">✕</button></div>`).join("")'
        f'    : "<p class=\\"text-center text-slate-500 py-8\\">Panier vide</p>";'
        f'  const total = c.reduce((s,it) => s + it.prix * it.qte, 0);'
        f'  document.getElementById("cart-total").textContent = "Total : " + total + " {devise}";'
        f'  const count = document.getElementById("cart-count");'
        f'  if (count) {{ count.textContent = c.length; count.classList.toggle("hidden", !c.length); }}'
        f'}}'
        f'function retirer(i) {{ const c = getCart(); c.splice(i,1); setCart(c); }}'
        f'function ajouterAuPanier(id, titre, prix, photo) {{'
        f'  const qte = parseInt(document.getElementById("qte")?.value || 1);'
        f'  const c = getCart(); c.push({{ id, titre, prix, qte, photo }}); setCart(c);'
        f'  alert("Ajouté au panier"); }}'
        f'window.ajouterAuPanier = ajouterAuPanier;'
        f'document.getElementById("checkout-form")?.addEventListener("submit", async e => {{'
        f'  e.preventDefault();'
        f'  const fd = new FormData(e.target);'
        f'  if (fd.get("_hp_bot")) return;'
        f'  const items = getCart();'
        f'  if (!items.length) return alert("Panier vide");'
        f'  const payload = {{ items, client: Object.fromEntries(fd), source: "storefront" }};'
        f'  const res = await fetch(API_POST, {{ method: "POST", headers: {{"Content-Type": "application/json"}}, body: JSON.stringify(payload) }});'
        f'  const data = await res.json();'
        f'  if (data.ok) {{'
        f'    document.getElementById("checkout-result").innerHTML = '
        f'      `<div class="bg-emerald-50 border border-emerald-200 rounded-lg p-4 text-emerald-900">'
        f'      <h3 class="font-bold mb-2">✓ Commande ${{data.numero}} reçue</h3>'
        f'      <p>Le marchand vous contacte bientôt par WhatsApp / téléphone pour finaliser le paiement.</p>'
        f'      ${{data.paiement_url ? `<a href="${{data.paiement_url}}" class="mt-3 inline-block px-4 py-2 bg-emerald-600 text-white rounded-lg">Payer maintenant</a>` : ""}}</div>`;'
        f'    setCart([]);'
        f'  }} else {{ alert("Erreur : " + (data.detail || "inconnue")); }}'
        f'}});'
        f'refresh();'
        f'</script>'
    )


def construire_html_page_storefront(
    boutique: dict, type_page: str,
    *, produit: Optional[dict] = None,
    produits: Optional[list[dict]] = None,
    categories: Optional[list[dict]] = None,
    autres_produits: Optional[list[dict]] = None,
    cross_sell_items: Optional[list[dict]] = None,
    api_base: str = "",
) -> str:
    """Rend une page du storefront (home/produit/panier).

    `cross_sell_items` : Piste 2 — liste des services marketplace Yukpo Rust
    à afficher dans la section « Autres marchands près de chez vous ».
    Si vide/None, la section n'est pas rendue.
    """
    css_vars = _css_globale_storefront(boutique.get("brand_kit_json"))
    titre_seo = escape(
        boutique.get("nom", "Boutique") +
        ({"home": "", "panier": " — Panier",
          "produit": f" — {produit.get('titre', '')}" if produit else ""}.get(type_page, ""))
    )
    favicon = boutique.get("logo_url", "")

    if type_page == "home":
        body = _page_accueil_html(
            boutique, produits or [], categories or [],
            cross_sell_items=cross_sell_items,
        )
    elif type_page == "produit" and produit:
        body = _page_produit_html(
            produit, boutique, autres_produits or [],
            cross_sell_items=cross_sell_items,
        )
    elif type_page == "panier":
        body = _page_panier_checkout_html(boutique, api_base=api_base)
    else:
        body = "<section class='p-8 text-center'>Page introuvable</section>"

    return f"""<!DOCTYPE html>
<html lang="{escape(boutique.get('langue_principale') or 'fr')}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{titre_seo}</title>
<meta name="description" content="{escape(boutique.get('description') or '')}">
{f'<link rel="icon" href="{escape(favicon)}">' if favicon else ""}
<meta name="theme-color" content="#7B3FE4">
<script src="https://cdn.tailwindcss.com"></script>
<style>:root {{ {css_vars} }}
body {{ font-family: var(--font-corps); color: var(--text); background: var(--bg); margin: 0; }}
.prose h2 {{ font-size: 1.25rem; font-weight: 700; margin-top: 1.5rem; }}
.prose li {{ list-style: disc; margin-left: 1.5rem; }}
</style>
</head>
<body>
{_construire_nav_storefront(boutique)}
<main>{body}</main>
{_construire_footer_storefront(boutique)}
</body>
</html>
"""


def construire_arborescence_storefront(
    boutique: dict, *, produits: list[dict],
    categories: list[dict], api_base: str = "",
    cross_sell_items: Optional[list[dict]] = None,
) -> dict[str, bytes]:
    """Génère TOUTE l'arborescence ZIP du storefront pour Netlify multi-files.

    Routes :
      /              → home (hero + featured + categories + cross-sell)
      /panier        → checkout client-side (localStorage cart)
      /p/<slug>      → page produit + cross-sell
      /c/<slug>      → catalogue par catégorie
      /sitemap.xml + robots.txt

    `cross_sell_items` : Piste 2 — items marketplace Yukpo Rust à afficher
    dans home + pages produit. Caller doit fetcher via
    `yukposhop_rust_search.chercher_services_marketplace()` AVANT d'appeler
    (sync ici pour rester rétrocompat avec les anciens callers). Si None
    ou [], aucun bloc cross-sell rendu (rétrocompat 100%).
    """
    files: dict[str, bytes] = {}
    cs = cross_sell_items or []

    # Home (top 8 produits featured = les 8 plus récents actifs)
    featured = [p for p in produits if p.get("statut") == "actif"][:8]
    files["index.html"] = construire_html_page_storefront(
        boutique, "home", produits=featured, categories=categories,
        api_base=api_base, cross_sell_items=cs,
    ).encode("utf-8")

    # Panier (pas de cross-sell — l'user est dans le tunnel checkout)
    files["panier/index.html"] = construire_html_page_storefront(
        boutique, "panier", api_base=api_base,
    ).encode("utf-8")

    # Pages produits + catalogues
    for p in produits:
        if p.get("statut") != "actif":
            continue
        autres = [pp for pp in produits if pp.get("id") != p.get("id")
                   and pp.get("statut") == "actif"][:4]
        files[f"p/{p['slug']}/index.html"] = construire_html_page_storefront(
            boutique, "produit", produit=p, autres_produits=autres,
            api_base=api_base, cross_sell_items=cs,
        ).encode("utf-8")

    for c in categories:
        cat_prods = [p for p in produits
                     if p.get("categorie_id") == c.get("id") and p.get("statut") == "actif"]
        files[f"c/{c['slug']}/index.html"] = construire_html_page_storefront(
            boutique, "home", produits=cat_prods, categories=[],
            api_base=api_base, cross_sell_items=cs,
        ).encode("utf-8")

    # Sitemap + robots
    base_url = (boutique.get("url_public") or f"https://{boutique['slug']}.yukpomnang.com").rstrip("/")
    urls = [f"<url><loc>{base_url}/</loc></url>",
            f"<url><loc>{base_url}/panier</loc></url>"]
    for p in produits:
        if p.get("statut") == "actif":
            urls.append(f"<url><loc>{base_url}/p/{escape(p['slug'])}</loc></url>")
    for c in categories:
        urls.append(f"<url><loc>{base_url}/c/{escape(c['slug'])}</loc></url>")
    files["sitemap.xml"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls) + "\n</urlset>\n"
    ).encode("utf-8")
    files["robots.txt"] = (
        f"User-agent: *\nAllow: /\nSitemap: {base_url}/sitemap.xml\n"
    ).encode("utf-8")

    return files
