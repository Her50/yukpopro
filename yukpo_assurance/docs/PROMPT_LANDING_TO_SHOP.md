# 🚀 Prompt de démarrage — Landing Pages production-ready → YukpoShop e-commerce

> **Comment utiliser ce document** : copie l'intégralité de la section "PROMPT À COLLER" ci-dessous dans une nouvelle session Claude Code (ou Claude.ai). L'IA aura tout le contexte pour démarrer immédiatement sans poser de questions de cadrage.

---

## ⚡ PROMPT À COLLER

```
═══════════════════════════════════════════════════════════════════════════════
PROJET : Landing Pages production-ready (Phases A→C) + YukpoShop e-commerce (Phase D)
PRODUIT PARENT : Yukpo (YukpoPro + YukpoSecrétariat)
RÉPERTOIRE : c:\Users\23767\digitalisation_assurance
═══════════════════════════════════════════════════════════════════════════════

CONTEXTE PRODUIT (à lire AVANT de coder)
────────────────────────────────────────

Yukpo est une plateforme B2B SaaS pour les pros africains francophones :
  • YukpoPro       → outils marketing/comptable/RH (yukpopro_web/)
  • YukpoSecrétariat → secrétariat IA (yukposecretariat_web/)
  • Backend partagé  → yukpo_assurance/ (Fly.io, FastAPI Python, Postgres,
                       Redis, Celery, Anthropic Claude + OpenAI GPT,
                       fal.ai + Replicate pour images/vidéos)

Cible géographique : Cameroun, Côte d'Ivoire, Sénégal, Burkina, Mali +
                     diaspora Afrique francophone.
Devises principales : XAF (FCFA Afrique centrale), XOF (FCFA Ouest), MAD, NGN.
Paiements opérationnels : Stripe, Flutterwave, Orange Money, MTN MoMo,
                         Wave (Sénégal), Campay.
SMS/WhatsApp : Twilio (déjà branché).
i18n : 17 langues (FR/EN/AR/PT/ES/DE/IT/ZH/JA/RU/HI/SW/HA/WO/LN/AM/TR)
       — système react-i18next déjà en place dans les 2 frontends.

LECTURE OBLIGATOIRE AVANT DE COMMENCER
──────────────────────────────────────

1. yukpo_assurance/docs/INFRA_SCALING.md
   → infra Fly + R2 + multi-région + Celery routing (déjà en place)

2. yukpo_assurance/modules/pro/landing_page_builder.py
   → état actuel du module Landing (génération HTML+Tailwind statique)

3. yukpo_assurance/api/routes_pro_generateurs.py
   → endpoints /pro/landing-page/generer, /pro/slides-web/generer

4. yukpo_assurance/core/storage.py
   → abstraction R2/local prête (à utiliser pour les nouveaux artefacts)

5. yukpopro_web/src/pages/ChatPage.tsx (lignes 195-260)
   → intent detection actuel pour landing/slides-web/video

6. yukposecretariat_web/src/components/ChatUnifieSec.tsx (lignes 290-360)
   → idem côté Sec

7. yukpo_assurance/modules/paiement/v2/providers/
   → Stripe, Flutterwave, Orange Money, MTN MoMo opérationnels

8. yukpo_assurance/core/notifications.py
   → WhatsApp Twilio fonctionnel (envoyer_whatsapp)

9. yukpopro_web/src/i18n/ et yukposecretariat_web/src/i18n/
   → fichiers de traduction 17 langues, react-i18next configuré

10. packages/admin-dashboard/src/AdminDashboard.tsx
    → dashboard admin cross-app partagé (pattern composant partagé)

CONTRAINTES TECHNIQUES NON-NÉGOCIABLES
──────────────────────────────────────

A. Responsive Progressive Web App (PWA)
   • TOUTES les nouvelles UIs (admin marchand, storefront client) doivent
     être responsive mobile-first (Tailwind breakpoints sm/md/lg/xl).
   • PWA manifest + service worker → installable iOS/Android.
   • Capacité offline minimum : voir produits, brouillon panier, factures
     téléchargées récemment.
   • Touch-friendly (boutons 44px min, swipe gestures sur produits/photos).
   • Configuration PWA déjà active sur YukpoPro + Sec (vite-plugin-pwa).
     Étendre la précache list aux nouvelles routes.

B. Internationalisation i18n
   • Système react-i18next DÉJÀ opérationnel sur YukpoPro + Sec.
   • Fichiers : yukpopro_web/src/i18n/*.json (et idem Sec).
   • CHAQUE nouveau texte UI passe par t('clé.sous_clé', 'fallback FR').
   • Ajouter les traductions au minimum FR + EN + AR (RTL) + WO (Wolof
     Sénégal) + DOUALA (sabir camerounais commercial).
   • Storefront public client → détection langue navigateur + override
     manuel + persistance localStorage.

C. Backend stack
   • Python 3.11 + FastAPI async + SQLAlchemy async (Postgres).
   • Migrations Alembic (yukpo_assurance/migrations/).
   • Celery + Redis pour les tâches longues (génération sites,
     scrapping market, batch import produits).
   • Logging structuré avec logger.info/warning/error.
   • Tests pytest dans tests/ (pas obligatoires sprint 1, mais bienvenus).

D. Frontend stack
   • React 18 + TypeScript + Vite.
   • Tailwind CSS (config existante).
   • TanStack Query pour data fetching.
   • Zustand pour state global (déjà utilisé pour 10 modules).
   • Routes via react-router-dom v6.
   • Composants partagés réutilisables → packages/ si pertinent
     (pattern admin-dashboard à suivre).

E. Pas de breaking changes
   • Tout endpoint existant continue de marcher comme avant.
   • Toute modification de table existante = migration Alembic ascendante
     uniquement, pas de drop column.

F. Facturation systématique sur crédits user — marge Yukpo intégrée
   Modèle EXISTANT à réutiliser (PAS recoder) :
   `modules/bureau/service_credits_bureau.py` :
     • `debiter_llm(user_id, modele, tokens_in, tokens_out, module)`
       → tarif TARIFS_MODELES[modele] × tokens × MULTIPLICATEUR_YUKPO (20×)
     • `debiter_forfait(user_id, type_forfait, module, multiplicateur)`
       → COUTS_FORFAIT_FCFA[type] × multiplicateur × MULTIPLICATEUR_YUKPO
     • `debiter_llm_unifie` / `debiter_forfait_unifie` : délégation auto
       vers `modules/pro/service_credits.py` si user a plan Pro actif,
       sinon retombe sur solde Bureau.
   • CHAQUE nouvel endpoint qui consomme une ressource (LLM, image IA,
     vidéo, OCR, traduction, scraping, Netlify deploy, Plausible event,
     SendGrid email, WhatsApp Twilio, R2 storage, fal/Replicate inference,
     SMS, OAuth refresh, scraping Jumia, Meta Graph push…) DOIT débiter
     les crédits user via une de ces fonctions AVANT (pré-check) ET APRÈS
     (débit réel basé sur usage observé). Aucune feature "gratuite".
   • Si type_forfait n'existe pas encore dans `COUTS_FORFAIT_FCFA`, on
     l'AJOUTE dans le dict avec son tarif FCFA = coût provider réel
     (Netlify deploy ≈ 5, Twilio WA ≈ 30, SendGrid email ≈ 1, Replicate
     LoRA train ≈ 3000, Recraft SVG ≈ 20, etc.). MULTIPLICATEUR_YUKPO=20
     applique la marge automatiquement.
   • Pré-check via `await _pre_check_credits(user_id, role=current_user.role)`
     (pattern actuel dans `routes_pro_generateurs.py`). Retourner 402
     `CREDITS_EPUISES` avec usage actuel/quota si insuffisant.
   • Logs auto via `ConsommationBureauDB` (déjà branchés au dashboard
     admin cross-app — pas de code supplémentaire à écrire).
   • Endpoints PUBLICS sans auth (ex : POST landing-leads/{slug} en A3,
     storefront client en D3) : débit sur le compte du MARCHAND propriétaire
     du slug, pas sur le visiteur. Anti-abuse : rate-limit IP avant débit.
   • Une feature livrée sans facturation = bug bloquant à corriger AVANT
     merge.

G. CostAdvisor — alerte préventive avant opérations coûteuses
   Module : `core/cost_advisor.py` (livré 2026-05-13).
   Principe : si une opération va consommer ≥ X % du solde restant
   (seuil dépendant du PLAN), retourner 402 type='cost_confirm_required'
   avec breakdown user-friendly. Le frontend affiche une modale + lien
   "Recharger". L'user confirme → re-soumet la requête avec
   `confirmer_cout=true` → exécution. Si solde insuffisant → 402
   type='credits_insuffisants' (action=BLOCK) → redirection /abonnement.

   Seuils par plan (% solde) :
     gratuit=20, secretariat/infographie=25, complet=35,
     pro_starter=25, pro_business=40, pro_enterprise=60.
   Plancher absolu : pas de modale sous 50 crédits.

   À appliquer sur CHAQUE endpoint dont l'estimation max dépasse 150
   crédits. Pattern court :

       if not req.confirmer_cout:
           from core.cost_advisor import advisor, estimer_cout_module, AdvisorAction
           cout = estimer_cout_module("<key>", multiplicateur=<n>)
           v = await advisor.evaluer(user_id, cout, module="<key>")
           if v.action in (AdvisorAction.BLOCK, AdvisorAction.CONFIRM):
               raise HTTPException(402, v.detail_pour_402())

   Aucun travail UI supplémentaire requis — l'intercepteur axios global
   et `<CostConfirmModalRoot/>` (montés dans App.tsx YPro + Sec) gèrent
   automatiquement la modale et le retry.

ROADMAP — 4 PHASES SÉQUENTIELLES
═════════════════════════════════

═══════════════════════════════════════════════════════════════════════════════
PHASE A — Landing pages production-ready et partageables
═══════════════════════════════════════════════════════════════════════════════

OBJECTIF : Transformer la landing actuelle (HTML privé téléchargeable) en
vrai site web publiable, partageable par URL, avec formulaire de contact
fonctionnel et footer personnalisé.

LIVRABLES
─────────

A1. Bouton "Publier" dans le chat YukpoPro + Sec après génération landing
    • Apparaît automatiquement à la fin du message de succès.
    • Click → POST /api/v1/pro/landing-page/publier {fichier_id, slug_souhaite}
    • Backend déploie vers Netlify via API officielle Netlify (créer un
      site avec sous-domaine custom) :
        → Le slug devient mashop-douala.yukpomnang.com OU netlify.app
        → Domaine yukpomnang.com déjà géré, ajouter wildcard *.yukpomnang.com
          en DNS pointant vers Netlify
    • Retourne l'URL publique partageable + QR code généré côté backend.
    • Stocker en DB : table landing_publications
      (user_id, slug, netlify_site_id, url_public, html_fichier_id,
       cree_le, derniere_modif).

A2. Footer personnalisé "Powered by Yukpo" (optionnel selon plan)
    • Plan Pro : footer modifiable (mentions légales du cabinet user).
    • Plan Free : "Site généré par YukpoPro · yukpomnang.com" obligatoire.
    • Plan Business : footer 100% custom, branding masqué.

A3. Formulaire de contact qui POST → backend Yukpo (non plus mailto)
    • Côté HTML généré : <form action="/api/v1/landing-leads/{slug}">
    • Backend : table landing_leads (slug, nom, email, telephone, message,
       source, created_at, statut={non_lu, lu, contacté, converti, perdu}).
    • Notif WhatsApp/email au marchand à chaque nouveau lead (Twilio +
       SendGrid déjà branchés).
    • Anti-spam : rate limit 5 leads/IP/heure + honeypot field.

A4. Page "Mes Leads" dans YukpoPro
    • Liste tous les leads par landing publiée.
    • Filtres : statut, période, slug.
    • Actions : marquer contacté, exporter CSV, envoyer WhatsApp/email
       direct depuis l'UI (templates de réponse).
    • Stats minimales : taux de conversion, valeur estimée.

CRITÈRES DE SUCCÈS PHASE A
──────────────────────────
✓ Une landing générée peut être publiée en 1 clic
✓ URL publique partageable par WhatsApp/LinkedIn fonctionne (200 OK)
✓ Un visiteur peut soumettre le formulaire de contact
✓ Le marchand reçoit notification WhatsApp + voit le lead dans son YukpoPro
✓ Mobile responsive PWA (test sur iPhone Safari + Android Chrome)
✓ i18n FR/EN minimum, autres langues actives via toggle

ESTIMATION : 3-5 jours dev.

═══════════════════════════════════════════════════════════════════════════════
PHASE B — Sites vitrines intelligents : analytics + tracking pub
═══════════════════════════════════════════════════════════════════════════════

OBJECTIF : Transformer les landings publiées en outils marketing pro avec
analytics intégrés (Plausible/Umami self-hosted ou cloud) + slots pour
Facebook Pixel, Google Analytics 4, TikTok Pixel, Snap Pixel.

LIVRABLES
─────────

B1. Plausible Analytics self-hosted OU intégration Plausible cloud
    • Recommandé self-hosted (Fly app séparée, ~$10/mois) → 0 abonnement,
       respect RGPD, données sur ton infra.
    • Script Plausible injecté dans <head> du HTML généré.
    • Dashboard analytics dans YukpoPro → "Stats" sous chaque landing.
    • Métriques : visites, source trafic, pays, device, taux rebond,
       parcours utilisateur, conversions formulaire.

B2. Slots Pixel/Tracking custom par utilisateur
    • Dans Settings YukpoPro → "Tracking & Analytics" :
       - Champ Facebook Pixel ID (ex 1234567890123)
       - Champ Google Analytics 4 Measurement ID (G-XXXXXXX)
       - Champ TikTok Pixel ID
       - Champ Snap Pixel ID
       - Champ Microsoft Clarity ID (heatmaps)
    • Backend injecte les scripts dans <head> lors de publication landing.
    • Évents auto-tracked :
       - PageView (toutes pages)
       - Lead (soumission formulaire contact)
       - InitiateCheckout (futur Phase D)
       - Purchase (futur Phase D)

B3. Intégration newsletter (Brevo / Mailchimp)
    • Champ API key dans Settings.
    • Bouton "S'inscrire à la newsletter" sur les landings → ajoute
       contact dans liste Brevo/Mailchimp via API.

B4. Email automation simple
    • Templates email : confirmation lead, follow-up J+3, follow-up J+7.
    • Configurable par marchand dans YukpoPro.
    • Envoyé via SendGrid (déjà branché).

CRITÈRES DE SUCCÈS PHASE B
──────────────────────────
✓ Plausible Analytics tracke les visites de toutes les landings
✓ Un marchand colle son FB Pixel ID dans Settings → tracking actif
✓ Une campagne Facebook Ads pointant sur la landing remonte les conversions
✓ Heatmaps Clarity visibles si configuré

ESTIMATION : 4-6 jours dev.

═══════════════════════════════════════════════════════════════════════════════
PHASE C — Mini-sites multi-pages (vitrine pro 5 pages)
═══════════════════════════════════════════════════════════════════════════════

OBJECTIF : Passer du single landing-page au mini-site multi-pages
(Accueil, Services, Équipe, Blog, Contact). Navigation interne, SEO multi-
pages, sitemap.xml auto.

LIVRABLES
─────────

C1. Schema "Site" (multi-page) en plus de "Landing" (single page)
    • Table sites (user_id, slug, theme, langue_principale, langues_actives,
       cree_le, publie_le)
    • Table pages (site_id, slug, type, titre, contenu_json, ordre)
    • Types de pages : home, services, equipe, blog_index, blog_article,
       contact, mentions_legales, cgv, confidentialite

C2. Génération multi-page via chat
    • "génère un site 5 pages pour mon cabinet d'expertise comptable Douala"
    • LLM compose la structure : Accueil + Services + Équipe + Blog + Contact
    • Chaque page a son hero image IA + sections + CTA
    • Nav top fixe + footer commun + sitemap.xml + robots.txt auto

C3. Modification incrémentale par page
    • "ajoute une page Équipe avec 4 collaborateurs simulés crédibles"
    • "remplace le hero de la page Services par une photo bureau Douala"
    • Backend récupère le site depuis BureauSessionDB + modifie la page
       concernée seulement (économie LLM + cohérence).

C4. Multi-langue par page
    • Chaque page peut être traduite en N langues actives.
    • URL : /fr/services, /en/services, /ar/الخدمات.
    • Détection navigateur + override toggle visible.
    • Trad auto via Sonnet (déjà configuré dans modules/translate/).

C5. Blog AI-powered
    • "écris un article de blog sur la fiscalité OHADA 2026 pour mon site"
    • LLM rédige, génère hero image, publie sur le site automatiquement
    • SEO meta tags optimisés
    • Schedule publication (article publié dans 3 jours)

CRITÈRES DE SUCCÈS PHASE C
──────────────────────────
✓ Un site 5 pages est généré et publié en < 10 min
✓ Sitemap.xml indexable par Google
✓ Navigation interne fonctionnelle (mobile + desktop)
✓ Au moins 2 langues actives sur le même site
✓ Article de blog généré + publié via chat

ESTIMATION : 2-3 semaines dev.

═══════════════════════════════════════════════════════════════════════════════
PHASE C.5 — Brand AI Training (LoRA Flux dev fine-tuned)
═══════════════════════════════════════════════════════════════════════════════

3 jours dev. Insérée entre Phase C et Phase D.

OBJECTIF : Chaque org peut entraîner son LoRA brand custom une fois pour
toutes (5$ Replicate, 15-30 min), puis TOUS ses visuels futurs (Yukpo
image_gen, freeform, slides web, landing, vidéos) injectent ce LoRA
automatiquement → cohérence brand parfaite sans redécrire le style à chaque
prompt.

LIVRABLES :
  • Endpoint /api/v1/brand-ai/entrainer (upload 10-30 photos ZIP → Replicate)
  • Table brand_loras (org_id, trigger_word, replicate_url, statut, cree_le)
  • UI YukpoPro "Mon Brand IA" : upload + preview + bouton train + statut
  • Auto-pickup : image_gen.generer_image() détecte LoRA actif pour user.org_id
  • Système preview A/B (même prompt avec vs sans LoRA)
  • Multi-LoRA par org (saison/gamme/B2B vs B2C)

DIFFÉRENCIATEUR :
  Adobe Firefly Custom Models = Enterprise ~$2000/mois (Yukpo = 4000 XAF/training)
  Canva = pas dispo
  MidJourney = pas de fine-tune brand
  → Aucun concurrent grand public Afrique francophone

PRICING :
  Plan Business    : 1 LoRA inclus + génération illimitée
  Plan Enterprise  : multi-LoRA

ESTIMATION : 3 jours dev.

═══════════════════════════════════════════════════════════════════════════════
PHASE D — YukpoShop : e-commerce avec connexion sociale + import IA
═══════════════════════════════════════════════════════════════════════════════

⚠ PRÉ-REQUIS : Phases A, B, C, C.5 OPÉRATIONNELLES en prod et TESTÉES par de
   vrais marchands. Ne PAS attaquer la Phase D avant d'avoir validé que les
   phases précédentes apportent une vraie valeur à au moins 20-50 marchands
   payants.

OBJECTIF : Boutique e-commerce complète, mais avec 4 DIFFÉRENCIATEURS MAJEURS
qui n'existent NULLE PART ailleurs en 2026 sur le marché africain francophone :

  1. CONNEXION SOCIALE INTELLIGENTE (Facebook, Instagram, WhatsApp Business,
     TikTok Shop) : publication automatique des produits, gestion des
     commandes reçues via DM/comments WhatsApp/Insta directement depuis
     YukpoPro, virality engineering (templates de partage, reels auto).

  2. IMPORT IA MAGIQUE : marchand upload 1-N photos d'un produit → l'app
     génère AUTOMATIQUEMENT le produit complet (titre vendeur SEO, description
     marketing, prix suggéré via scraping concurrence locale, catégorie,
     tags, photos retouchées, variantes détectées).

  3. ANALYTICS PUB INTÉGRÉES : tableau de bord unifié des performances
     pub Facebook + Insta + TikTok + Google Ads + Snap → ROI par produit,
     cible client lookalike, recommandations campagnes auto.

  4. CRM CLIENT AVEC SCORING IA : profil 360° de chaque client (acheté,
     visité, abandonné panier, vu produit, commenté), prédiction churn,
     suggestion produit personnalisée, automation marketing (relance panier
     abandonné WhatsApp, anniversaire avec code promo).

LIVRABLES PHASE D — SOUS-PHASES
────────────────────────────────

D1. Catalogue produits + admin (2 semaines)

   • Schema DB :
       table shop_products (user_id, sku, titre, slug, description_courte,
        description_longue, prix_unit_xaf, prix_unit_devise, devise, tva_pct,
        stock, stock_alerte, photos_urls[], categorie, tags[], variantes_json,
        seo_titre, seo_desc, seo_keywords[], statut, cree_le, modif_le)
       table shop_categories (user_id, nom, slug, parent_id, ordre)
       table shop_variantes (product_id, nom, valeur, prix_diff_xaf, stock)

   • Onglet "Ma Boutique" dans YukpoPro + Sec (composant partagé dans
     packages/shop-dashboard/ comme admin-dashboard).
     Sous-onglets : Vue d'ensemble, Produits, Commandes, Clients,
     Promotions, Paiements, Logistique, Stats, Réglages.

   • CRUD produits via UI graphique ET via chat IA.

D2. Import IA MAGIQUE (2 semaines) — LE GROS DIFFÉRENCIATEUR

   • Endpoint POST /api/v1/shop/produits/import-ia (multipart)
     Body : N photos (jusqu'à 10) + brief libre optionnel + catégorie hint.

   • Pipeline :
       a. Réception 1-10 photos produit
       b. LLM Vision (Claude Sonnet ou GPT-4o) analyse chaque photo :
          - Détecte objet principal, couleur dominante, matière
          - Identifie variantes (tailles, couleurs visibles)
          - Suggère catégorie (vêtements / maroquinerie / cosmétique /
            électronique / artisanat / alimentaire)
       c. LLM Sonnet rédige :
          - Titre vendeur SEO 60 chars
          - Description marketing 200-400 mots
          - 10-15 tags SEO + hashtags réseaux sociaux
          - Suggestion prix via scraping (Jumia CM/CI, Amazon, Alibaba)
            adapté au pouvoir d'achat local
          - Variantes structurées (tailles 36-46, couleurs disponibles)
       d. Retouche photos auto (fond uni blanc/transparent via Flux Fill,
          recadrage, color correction)
       e. Création produit complet en base + photos uploadées vers R2

   • UX cible : "upload + 1 clic → produit prêt à vendre". Aucune saisie
     manuelle obligatoire. Le marchand peut ÉDITER après si besoin.

   • Bulk : import de 20 photos = 20 produits créés en 5-10 min.

D3. Storefront public client (2 semaines)

   • Nouveau frontend React PWA : packages/shop-storefront/ OU app dédiée
     yukposhop_web/.
   • URL : <slug>.yukpomnang.com (ex: maroquinerie-douala.yukpomnang.com)
   • Pages :
       - Accueil (hero brand + featured products + categories)
       - Catalogue avec filtres dynamiques
       - Page produit (gallery, variantes, ajout panier, avis, partage)
       - Panier (persistance localStorage + DB pour users connectés)
       - Checkout (adresse, livraison, paiement multi-provider)
       - Compte client (commandes, suivi, retours, favoris)
       - Recherche full-text
       - Wishlist
       - Programme fidélité (points, badges)
   • PWA installable (manifest + service worker offline cart)
   • Multi-langue automatique (FR/EN/AR/WO/DOUALA min)
   • Mobile-first responsive
   • SEO : sitemap produits dynamique, schema.org Product/Offer/Review

D4. Paiement multi-provider (1 semaine)

   • Briques EXISTANTES à réutiliser :
       - modules/paiement/v2/providers/stripe_provider.py
       - modules/paiement/v2/providers/flutterwave.py
       - modules/paiement/v2/providers/orange_money.py
       - modules/paiement/v2/providers/mtn_momo.py
   • Sélection provider par client final (en fonction du pays détecté).
   • Webhooks de confirmation → maj statut commande automatique.
   • Calcul TVA OHADA / CIMA automatique (RAG fiscal CI/CM déjà branché).
   • Facture PDF générée auto post-paiement (briques infographe_pro
     existantes).

D5. Notifications WhatsApp + Email automatisées (3 jours)

   • Marchand reçoit notif WhatsApp à chaque nouvelle commande.
   • Client reçoit confirmation email + tracking WhatsApp (Twilio existe).
   • Templates par étape : commande créée, payée, expédiée, livrée.
   • Templates personnalisables par marchand dans Settings.

D6. Connexion sociale INTELLIGENTE (3 semaines) — DIFFÉRENCIATEUR

   • Facebook/Instagram Catalog Sync
     - Marchand connecte son compte Meta Business via OAuth
     - YukpoShop synchronise les produits vers Facebook Shops + Instagram
       Shopping automatiquement (Meta Graph API)
     - Posts auto-générés sur la page Facebook à chaque nouveau produit
     - Stories Insta auto (Recraft v3 SVG visuels promo)
     - Tags produits dans les photos
   • WhatsApp Business
     - Webhook réception messages WhatsApp → arrivent dans chat YukpoPro
       du marchand
     - Le marchand répond depuis YukpoPro, message envoyé via WhatsApp
       Business API
     - Détection commande dans le message ("je veux le sac à 35000")
       → suggestion de créer commande automatiquement
     - Liens produits cliquables WhatsApp (preview riche)
   • TikTok Shop integration (si disponible API marché Cameroun/CI)
   • Snap Shopping Lens (futur)
   • Pinterest Business Pins shoppables

D7. Analytics pub unifiées (2 semaines) — DIFFÉRENCIATEUR

   • Onglet "Pubs & ROI" dans Ma Boutique :
       - Connexion OAuth Facebook Ads API, Google Ads API, TikTok Ads,
         Snapchat Ads
       - Récupération automatique des dépenses pub + impressions + clics
       - Croisement avec les commandes YukpoShop (UTM, fbclid, gclid)
       - Calcul ROAS (Return On Ad Spend) par campagne, par produit
       - Recommandations IA : "augmenter budget campagne X (ROAS 4.2)",
         "couper campagne Y (ROAS 0.3)"
       - Audience lookalike : suggestion de cibles à partir des meilleurs
         clients
   • Dashboard cross-canal (vue agrégée toutes les sources pub)

D8. CRM client avec scoring IA (2 semaines) — DIFFÉRENCIATEUR

   • Profil 360° par client final :
       - Historique commandes
       - Pages visitées (via Plausible)
       - Produits vus, ajoutés panier, abandonnés
       - Comments / DM reçus
       - Source d'acquisition (campagne, organic, referral)
   • Scoring IA :
       - Probabilité de churn (% chance de ne plus acheter)
       - Lifetime value prédit (LTV)
       - Segment : VIP, récurrent, dormant, en risque, new
   • Automation marketing :
       - Relance panier abandonné WhatsApp J+1 + J+3 + J+7
       - Email anniversaire avec code promo
       - SMS rupture-stock-bientôt sur produit favorisé
       - Cross-sell automatique (suggestions LLM basées sur historique)

D9. Logistique & livraison (1 semaine)

   • Zones de livraison configurables par marchand (par ville/quartier)
   • Tarifs livraison par zone + délai estimé
   • Transporteurs partenaires (interfaces) :
       - DHL Cameroun / Côte d'Ivoire
       - Speedaf
       - Bolloré Africa
       - Transporteurs locaux (intégration WhatsApp manuelle minimum)
   • Génération étiquette PDF + QR de suivi

D10. Mobile companion app (optionnel, 3-4 semaines)
   • App native marchand iOS + Android (React Native expo)
   • Gérer produits, commandes, scan code-barres pour réapprovisionnement
   • Notifications push à chaque commande
   • Mode caisse physique (POS mobile)

CRITÈRES DE SUCCÈS PHASE D
──────────────────────────
✓ Un marchand peut uploader 10 photos → 10 produits prêts à vendre en 5 min
✓ Une commande WhatsApp ("je veux le sac à 35000") crée auto un panier
✓ Un client paye via Orange Money → commande validée → marchand notifié
   WhatsApp → facture PDF générée → tracking expédition
✓ Catalogue produit Facebook Shops + Instagram Shopping synchronisé auto
✓ Dashboard ROAS pub unifié remonte les conversions cross-canal
✓ CRM client avec scoring churn + suggestion lookalike Facebook
✓ PWA installable mobile, fonctionne offline (panier brouillon)
✓ Multi-langue FR/EN/AR/WO/DOUALA opérationnel

ESTIMATION : 12-16 semaines dev focus (3-4 mois).

═══════════════════════════════════════════════════════════════════════════════
PHASE E — Collecte de données XLSForm + Analytics IA conversationnel
═══════════════════════════════════════════════════════════════════════════════

OBJECTIF : Transformer YukpoPro en plateforme de collecte de données
KoboCollect-class — formulaires XLSForm complexes (logique conditionnelle,
contraintes, calculs, médias) générés depuis un simple prompt chat,
collecte web/mobile/offline-first, et analyses IA puissantes "à la demande"
sans data scientist : "analyse la satisfaction par tranche d'âge et trace
un graphique" → rapport généré en 30s.

PRINCIPE : Réutiliser au MAXIMUM l'existant déjà en place dans
`modules/enquetes/` (gestionnaire_enquetes.py, persistence.py,
helpers_dictionnaire_plan.py, facturation.py) et `routes_enquetes.py`.
Modèles déjà présents : Etude, Formulaire, QuestionFormulaire,
ThemeQualitatif, TranscriptionAudio. Endpoints déjà exposés : créer
étude, créer/modifier formulaire, soumettre réponse, XLSForm export,
analyse qualitative+quantitative, rapport DOCX/PDF.

CE QUI MANQUE (à livrer en Phase E) :

E1. Génération de formulaire par chat IA (3-4 jours)

   • Côté backend, nouvel endpoint :
       POST /api/v1/enquetes/generer-par-prompt
       Body : {brief, langue, canal_diffusion, nb_questions_cible?, profil_cible?}
   • Pipeline :
       a. Sonnet compose un Formulaire XLSForm complet à partir du brief :
          - 10-40 questions structurées (select_one, select_multiple, integer,
            decimal, text, date, time, geopoint, image, audio, barcode)
          - Logique conditionnelle (relevant=, constraint=, calculation=)
          - Choices listes multi-langues
          - Groupes + répétitions (begin_group / begin_repeat)
          - Validation contraintes (regex, ranges, required)
          - Hints, default values
       b. Le formulaire est sauvegardé via gestionnaire_enquetes.creer_formulaire()
       c. Retourne {formulaire_id, lien_public, lien_qr, lien_xlsform_download}

   • Côté chat YukpoPro / YukpoSec, détection intent dans ChatPage.tsx +
     ChatUnifieSec.tsx (regex FR+EN +  prompt LLM si ambigu) :
       "génère un questionnaire de satisfaction client garage Douala"
       "crée un formulaire d'enquête santé maternelle Yaoundé en français + douala"
       "fais-moi un audit conformité OHADA pour mes franchisés"

E2. Lien public + collecte web/mobile responsive (2-3 jours)

   • Frontend public PWA `enquetes.yukpomnang.com/{formulaire_id}`
     OU sous-domaine custom du marchand `<slug>.yukpomnang.com/q`
   • Composant React qui :
       - Charge le Formulaire JSON depuis /enquetes/public/{id}
       - Render UI mobile-first responsive (boutons radio gros, swipe,
         géoloc auto, capture photo via appareil natif)
       - Gère branching XLSForm côté client (eval calculations + relevant)
       - PWA installable + offline-first (IndexedDB queue de réponses)
       - Resync auto quand re-connecté
       - Multi-langue selon Formulaire.langues_actives (FR/EN/AR/WO/DOUALA/SW)
   • Lien QR généré automatiquement (réutilise modules/pro/qr_generator.py)
   • Endpoint public d'ingestion : POST /enquetes/public/{id}/reponses
     (déjà existant : ge.soumettre_reponse — à étendre avec rate-limit
     IP + honeypot + débit forfait sur owner)

E3. Suivi temps réel de la collecte (1-2 jours)

   • Onglet "Mes enquêtes" dans YukpoPro :
       - Liste des études actives avec : nb_réponses, taux de complétion,
         temps moyen, dernier répondant, sparkline 7 derniers jours
       - Carte géographique (Leaflet + tuiles OSM) si geopoint dans formulaire
       - Sondages sur réponses par question en quasi-temps-réel (polling 30s)
   • Notifications push/WA/email au marchand sur seuils :
       - "Tu as dépassé 100 réponses → lance l'analyse maintenant ?"
       - "Aucune réponse depuis 7 jours → relance ton public ?"
   • Export CSV + XLSX en un clic (réutilise le pattern leads-dashboard)

E4. Analytics IA conversationnel "à la demande" (5-7 jours) — DIFFÉRENCIATEUR

   • Endpoint POST /api/v1/enquetes/{id}/analyser-prompt
     Body : {prompt_analyse}
     Ex prompts user :
       "compare la satisfaction par tranche d'âge et par genre"
       "calcule le NPS, segmente par ville, et identifie les 3 raisons
        principales d'insatisfaction"
       "fais une analyse de sentiment des verbatims libres"
       "trace l'évolution des réponses jour par jour"

   • Pipeline :
       a. Sonnet (avec accès au DataFrame pandas en lecture seule via
          un sandbox restreint) compose un PLAN d'analyse en JSON :
             {operations: [
               {type: "filter", colonne, predicat},
               {type: "groupby", colonnes},
               {type: "agg", agg: "mean|sum|count|nps|...", colonne},
               {type: "chart", chart_type: "bar|line|pie|heatmap|map",
                config: {...}},
               {type: "llm_synthese", instruction: "..."},
             ]}
       b. Backend exécute le plan via pandas (déjà branché modules/bureau/
          data_analyzer ou modules/pro/data_analyse — à vérifier/réutiliser)
       c. Génère graphiques Vega-Lite spec OU PNG matplotlib (existant
          déjà : `_graphique_barres`, `_graphique_camembert`,
          `_graphique_histogramme`, `_fig_to_b64` dans gestionnaire_enquetes)
       d. Sonnet rédige la synthèse en FR : insights clés, recommandations
          actionnables, alertes, segments à fort/faible niveau
       e. Retourne {plan_executed, charts: [...], synthese_md, donnees_brutes}

   • Cache : analyses identiques sur même dataset → réponse instantanée
     (clé = hash(prompt + dataset_version)).
   • Garde-fous sandbox : pas d'exec Python arbitraire, uniquement les
     opérations validées du PLAN JSON (dataframe.groupby/agg/filter/merge),
     limite de RAM/CPU.

E5. Rapport complet exportable (2-3 jours)

   • Réutilise `ge.generer_rapport(etude_id, format='docx'|'pdf')` existant
   • Étend avec sections :
       - Méthodologie (auto-décrite par Sonnet à partir du Formulaire)
       - Résultats clés (3-5 insights majeurs choisis par Sonnet)
       - Visualisations (les charts générés en E4, embarqués)
       - Verbatims représentatifs (qual + auto-classification thématique
         déjà présent dans ThemeQualitatif)
       - Recommandations actionnables segmentées par profil
       - Annexes : tableau croisé complet, données brutes
   • Branding : applique le BrandKit du user (déjà disponible côté Pro)
   • Multi-format : DOCX, PDF, HTML interactif (Plotly + Reveal.js), PPTX

E6. Templates pré-faits + onboarding (1-2 jours)

   • Catalogue de templates métier (clone-en-1-clic) :
       - Satisfaction client (CSAT, NPS, CES)
       - Audit conformité OHADA / CIMA
       - Enquête santé maternelle (UN OMS adapté Afrique)
       - Audit fournisseurs (RSE, qualité, délais)
       - Étude de marché (qual + quanti combinée)
       - Recensement bénéficiaires ONG
       - Sondage politique / opinion publique
       - 360° collaborateur (RH)
   • Chaque template : Formulaire XLSForm complet + analyse_prompts
     suggérés pour orienter l'analyse aval.

FACTURATION (modèle existant `modules/enquetes/facturation.py` à étendre,
appliquer MULTIPLICATEUR_YUKPO=20 via debiter_forfait) :

  • enquete_generation_prompt        : LLM Sonnet + render → 8 FCFA / form
  • enquete_xlsform_export           : 1 FCFA / export
  • enquete_reponse_capturee         : 0.3 FCFA / réponse (débit MARCHAND)
  • enquete_analyse_prompt_simple    : 5 FCFA / analyse (≤3 ops)
  • enquete_analyse_prompt_complexe  : 25 FCFA / analyse (≥4 ops ou +LLM)
  • enquete_rapport_complet_docx     : 15 FCFA / rapport
  • enquete_rapport_complet_pdf      : 20 FCFA / rapport
  • enquete_carte_geopoint           : 3 FCFA / rendu carte
  • enquete_offline_sync             : 0.1 FCFA / batch synchronisation

INFRA :

  • Réponses stockées en Postgres (existant) ; vidéos/photos→R2 (existant)
  • Cache analyses dans Redis (clé hash, TTL 24h)
  • Worker Celery `enquete_heavy` pour analyses prompt-complexes
    (réutilise le routing infra existant `core/celery_app.py`)

DIFFÉRENCIATEURS vs concurrents :

  • KoboCollect / ODK Central        : XLSForm pro mais NUL analytics
  • SurveyMonkey / Typeform          : UI ok mais pas XLSForm avancé,
                                       analytics basiques, pas africain
  • Google Forms                     : très basique, pas multi-canal
  • Yukpo                            : XLSForm + offline + analyses IA
                                       conversationnelles + branding +
                                       distribution WA/SMS + multi-langue
                                       africaine, tout via PROMPT chat.

CRITÈRES DE SUCCÈS PHASE E
──────────────────────────
✓ Un marchand tape "génère un questionnaire de satisfaction garage Douala
   en français et douala" → reçoit un lien public en 30s
✓ Un client mobile (Android low-end, 3G capricieux) remplit le formulaire
   offline puis se reconnecte → réponse syncée auto
✓ Le marchand demande "analyse par tranche d'âge et fais-moi un graphique
   du NPS par ville" → reçoit graphiques + synthèse en 30-60s
✓ Rapport DOCX/PDF complet, brandé, exportable en 1 clic
✓ Au moins 5 templates pré-faits utilisables tels quels
✓ PWA collecte installable, fonctionne offline (file d'attente IndexedDB)
✓ Multi-langue FR/EN/AR/WO/DOUALA/SW opérationnel sur formulaire ET rapport
✓ Toutes les opérations débitent via debiter_forfait_unifie (contrainte F)

ESTIMATION : 3-4 semaines dev focus.

═══════════════════════════════════════════════════════════════════════════════
PRIORISATION SÉQUENTIELLE STRICTE
═══════════════════════════════════════════════════════════════════════════════

NE PAS commencer la Phase D avant que A, B, C, C.5, E (ou un sous-ensemble
validé en marché) soient :
  • Déployées en production
  • Validées par au moins 20 utilisateurs réels payants
  • Sans bug bloquant remonté pendant 2 semaines consécutives

Ordre :

  Sprint 1-2   : Phase A   (publication + leads + footer)        [3-5 jours]
  Sprint 3-4   : Phase B   (analytics + pixel + newsletter)      [4-6 jours]
  Sprint 5-7   : Phase C   (multi-pages + multi-langue + blog)   [2-3 semaines]
  Sprint 8     : Phase C.5 (Brand AI Training — LoRA Flux dev)   [3 jours]
  PAUSE        : Validation marché 4-8 semaines avec early adopters
  Sprint 9-12  : Phase E   (XLSForm + Analytics IA prompt)       [3-4 semaines]
                 ↳ Greffée sur module enquetes/ existant (Etude/Formulaire/
                   XLSForm/analyses qualitatives+quantitatives déjà présents).
                   Valeur immédiate ONG/marketing/ESN — peut commencer
                   AVANT Phase D si le marché Phase A-C valide bien.
  Sprint 13+   : Phase D   (YukpoShop complet)                   [3-4 mois]

QUALITÉ — BARÈME NON-NÉGOCIABLE
─────────────────────────────────

À chaque sprint, livrer :
  ✓ Code commité avec commits sémantiques (feat:/fix:/refactor:/chore:)
  ✓ Migrations Alembic ascendantes uniquement
  ✓ Endpoint backend documenté dans le docstring de la route
  ✓ Composant frontend i18n-ready (toutes les chaînes via t('key'))
  ✓ Responsive testé mobile + desktop (Chrome DevTools 375px et 1440px min)
  ✓ Au moins 1 traduction FR + EN par défaut, autres langues activables
  ✓ Migration auto si breaking change DB (pas de drop column, juste add/rename)
  ✓ Logs structurés (logger.info pour succès, .warning pour anomalies)
  ✓ Erreurs HTTP propres (4xx pour client, 5xx pour serveur, jamais 500 silencieux)
  ✓ Coût LLM/IA débité via debiter_llm() (existant) — pas d'appel "gratuit"
  ✓ Coût NON-LLM débité via debiter_forfait() avec entrée correspondante
    dans COUTS_FORFAIT_FCFA — marge MULTIPLICATEUR_YUKPO=20 appliquée
    automatiquement, jamais bypassée (cf. contrainte F)
  ✓ Pré-check `_pre_check_credits(user_id, role)` AVANT chaque appel coûteux
    pour retourner 402 propre si solde insuffisant (pas de 500 mid-pipeline)
  ✓ Endpoints publics (leads form, storefront client) débitent le marchand
    propriétaire du slug — pas le visiteur anonyme

DÉMARRAGE — Premier commit attendu
─────────────────────────────────

Avant de coder, l'agent doit :
  1. Lire les 10 fichiers de contexte listés ci-dessus
  2. Confirmer la compréhension en 5-8 bullets dans sa première réponse
  3. Proposer un plan détaillé du sprint 1 (Phase A1-A4) avec :
     - Liste exacte des fichiers à créer/modifier
     - Schema migration Alembic (DDL)
     - Estimations heure par tâche
  4. Attendre validation user AVANT premier commit
  5. Une fois validé : commencer Phase A1 (bouton Publier + Netlify deploy)

═══════════════════════════════════════════════════════════════════════════════
FIN DU PROMPT — colle ce bloc dans ta nouvelle session
═══════════════════════════════════════════════════════════════════════════════
```

---

## 📋 Comment l'utiliser

1. **Ouvre une nouvelle session Claude Code** dans le même répertoire
   `c:\Users\23767\digitalisation_assurance`
2. **Copie tout le bloc "PROMPT À COLLER"** ci-dessus (entre les lignes
   `═══════════`)
3. **Colle dans le chat** comme premier message
4. **Réponds aux confirmations** (étapes 1-5 du démarrage)
5. **Laisse l'agent travailler par sprints validés**

## ✅ Checklist contexte récupéré automatiquement par le prompt

Le prompt fait référence à 10 fichiers de contexte que l'agent va lire :

- [x] `yukpo_assurance/docs/INFRA_SCALING.md` (infra Fly + R2 prête)
- [x] `yukpo_assurance/modules/pro/landing_page_builder.py`
- [x] `yukpo_assurance/api/routes_pro_generateurs.py`
- [x] `yukpo_assurance/core/storage.py` (R2/local prêt)
- [x] `yukpopro_web/src/pages/ChatPage.tsx` (intent detection actuel)
- [x] `yukposecretariat_web/src/components/ChatUnifieSec.tsx`
- [x] `yukpo_assurance/modules/paiement/v2/providers/` (4 providers prod)
- [x] `yukpo_assurance/core/notifications.py` (WhatsApp Twilio)
- [x] `yukpopro_web/src/i18n/` (17 langues react-i18next)
- [x] `packages/admin-dashboard/src/AdminDashboard.tsx` (pattern composant
       partagé)

L'agent aura tout pour démarrer sans poser de questions de cadrage. Il pourra
poser des questions techniques précises pendant l'implémentation, mais le
**quoi/pourquoi** est déjà cadré.
