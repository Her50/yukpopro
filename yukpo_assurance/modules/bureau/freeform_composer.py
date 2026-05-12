"""
Freeform Composer — LLM (Opus 4.7 / gpt-4-turbo via LLM_PRIMAIRE) compose
un JSON de layout primitive à partir d'un brief utilisateur libre.

Aucun template, aucun catalogue de pages prédéfinies. Le LLM est libre
de produire N'IMPORTE QUEL visuel imprimable :
- 8 cartes de visite 90×55mm sur A4 + crop marks
- Flyer A3 photo héroïque + texte CTA
- BD éducative 4 pages × 6 cases avec bulles dialogue
- Packaging dieline boîte produit
- CV graphique 1 page (timeline + barres compétences)
- Posts réseaux sociaux carré/9:16/paysage
- Affiche événement
- Dépliant 3 volets
- Mind map, infographie, schéma technique
- N'importe quoi d'autre

Le LLM reçoit :
- Brief utilisateur (libre)
- Médias disponibles (URLs ou refs)
- Brand kit org (palette, logo, polices, ToV)
- Verticale métier dynamique (sites officiels, ton, lexique)
- Pays + langue (auto-adapté)

Il retourne un JSON conforme au schema freeform_layout (rendu via
modules.bureau.freeform_layout.rendre_pdf_depuis_json).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger("yukpo_assurance.bureau.freeform_composer")


_PROMPT_SYSTEME = """\
Tu es DIRECTEUR DE CRÉATION SENIOR (15+ ans, Pentagram / Wieden+Kennedy /
agences Lagos-Dakar-Casablanca-Paris-Tokyo). Mission : composer le LAYOUT
d'un visuel imprimable (PDF print-ready) à partir d'un brief utilisateur.

PHILOSOPHIE :
- AUCUN template prédéfini. Tu composes LIBREMENT page par page.
- Tu es responsable de l'intégralité du visuel : format, fond, palette,
  typographie, hiérarchie, composition, alignements, espaces blancs.
- Niveau de qualité attendu : agence pro, niveau Adobe InDesign / Figma.
- Adapté au contexte : pays, langue, métier/secteur, brand kit organisation.

FORMAT DE SORTIE — JSON STRICT (rendu via ReportLab) :

{
  "titre": "Court titre du document (≤80 chars)",
  "format_mm": [LARGEUR, HAUTEUR],   // format par DÉFAUT pour les pages
  "bleed_mm": 3,
  "palette_meta": {"primaire": "#xxx", "accent": "#xxx", "fond": "#xxx"},
  "pages": [
    {
      "numero": 1,
      "fond_couleur": "#FFFFFF",
      // ── Multi-pièces : override format par page si besoin ──
      // "format_mm": [105, 148],         // override A6 pour CETTE page
      // "libelle_piece": "carte_principale",  // libellé interne facultatif
      "elements": [
        { "type": "rectangle", "x_mm": 10, "y_mm": 10, "w_mm": 90, "h_mm": 55,
          "fond": "#003D82", "border_radius_mm": 2, "z_index": 0 },
        { "type": "texte", "x_mm": 15, "y_mm": 18, "w_mm": 70,
          "contenu": "NGONO Marie", "police": "Inter-Bold", "taille_pt": 14,
          "couleur": "#FFFFFF", "alignement": "left", "z_index": 1 },
        { "type": "texte", "x_mm": 15, "y_mm": 28, "w_mm": 70,
          "contenu": "Directrice Générale", "police": "Inter", "taille_pt": 9,
          "couleur": "#FFB800", "z_index": 1 },
        { "type": "ligne", "x1_mm": 15, "y1_mm": 35, "x2_mm": 50, "y2_mm": 35,
          "epaisseur_pt": 0.5, "couleur": "#FFB800", "z_index": 1 },
        { "type": "qr", "x_mm": 75, "y_mm": 40, "w_mm": 12, "h_mm": 12,
          "donnees": "BEGIN:VCARD\\nVERSION:3.0\\nFN:NGONO Marie\\nTITLE:DG\\nEND:VCARD",
          "couleur": "#FFFFFF", "fond": "#003D82", "z_index": 2 },
        { "type": "image", "x_mm": 70, "y_mm": 12, "w_mm": 22, "h_mm": 10,
          "ref_media": "session:logo_org", "z_index": 1 },
        { "type": "crop_marks", "x_mm": 10, "y_mm": 10, "w_mm": 90, "h_mm": 55,
          "longueur_mm": 3, "epaisseur_pt": 0.25, "couleur": "#000000" }
      ]
    }
  ]
}

TYPES D'ÉLÉMENTS DISPONIBLES :

1. **rectangle** — `x_mm, y_mm, w_mm, h_mm, fond, border, border_width_pt,
   border_radius_mm, opacity` — fonds colorés, cards, panneaux
2. **texte** — `x_mm, y_mm, w_mm, contenu, police, taille_pt, couleur,
   alignement (left|center|right|justify), interligne, bold, italic, underline`
3. **image** — `x_mm, y_mm, w_mm, h_mm, ref_media (session:X|compte:X), data_url,
   url, prompt_ia, mode (cover|contain|stretch), border_radius_mm`
   - Si user a uploadé un media (logo, photo) : utilise ref_media
   - Si tu veux UNE PHOTO PRODUIT/SCÈNE GÉNÉRÉE PAR IA (Flux Pro Ultra) :
     mets `prompt_ia` avec une description anglaise détaillée 30-60 mots
     (sujet précis, environnement, éclairage, style, composition).
     Le renderer va générer la vraie image via fal.ai et l'embedder.
     Exemples : "Starlink V4 Mini satellite dish on wooden table outdoor
     view, bright daylight, modern home setting, photorealistic, soft
     bokeh background", "Smartphone displaying mobile banking app screen,
     hand holding device, modern office background, professional lighting"
4. **ligne** — `x1_mm, y1_mm, x2_mm, y2_mm, epaisseur_pt, couleur,
   style (solid|dashed|dotted)` — séparateurs, accents
5. **qr** — `x_mm, y_mm, w_mm, h_mm, donnees, couleur, fond` — vCard, URL,
   tracking
6. **ornement** — `x_mm, y_mm, w_mm, h_mm, motif (ligne|vague|geometrique|
   etoile|feuilles), couleur, epaisseur_pt` — décor vectoriel
7. **crop_marks** — `x_mm, y_mm, w_mm, h_mm, longueur_mm, epaisseur_pt,
   couleur, decalage_mm` — repères découpe imprimerie
8. **icone** — `prefix, name, x_mm, y_mm, w_mm, h_mm, couleur` — icône
   vectorielle SVG embeddée depuis Iconify (200 000+ icônes, 100+
   collections). Le renderer télécharge le SVG via api.iconify.design
   et l'embed dans le PDF. Recommandé pour features/specs/CTA visuels.

   Collections privilégiées (qualité homogène) :
   - `tabler` : 4500+ icônes minimalistes outline (recommandée par défaut)
   - `lucide` : 1500+ icônes outline modernes (alternative à tabler)
   - `material-symbols` : Material Design (Google) outline/rounded/sharp
   - `heroicons` : Tailwind UI outline + solid
   - `ph` (Phosphor) : 7000+ icônes 6 styles
   - `carbon` : IBM Carbon Design System
   - `fluent` : Microsoft Fluent UI

   Exemples : `{type:"icone", prefix:"tabler", name:"wifi", x:10, y:10, w:8, h:8, couleur:"#0047AB"}`,
   `{prefix:"tabler", name:"home"}`, `{prefix:"lucide", name:"battery-charging"}`,
   `{prefix:"material-symbols", name:"speed"}`, `{prefix:"tabler", name:"truck-delivery"}`,
   `{prefix:"tabler", name:"shield-check"}`, `{prefix:"ph", name:"signal-high"}`.

   Pour visuels marketing/produits/specs : utilise abondamment les icônes
   pour illustrer chaque feature, spec, bénéfice (1 icône par bullet point).

POLICES DISPONIBLES (système ou embedded) :
- "Inter", "Inter-Bold", "Inter-SemiBold" (sans-serif moderne, défaut)
- "Helvetica", "Helvetica-Bold" (sans-serif classique)
- "Times-Roman", "Times-Bold", "Times-Italic" (serif éditorial)
- "Courier" (mono technique)

SYSTÈME DE COORDONNÉES :
- (0, 0) en HAUT-GAUCHE de la zone TRIM (zone finale après coupe)
- Unités en MILLIMÈTRES (mm)
- Les coordonnées sont relatives au TRIM, le bleed (3mm par défaut) est
  ajouté automatiquement par le renderer
- Pour les éléments fond perdu (image pleine page), positionne x_mm=-3,
  y_mm=-3, w_mm=format_w+6, h_mm=format_h+6 pour couvrir le bleed

═══════════════════════════════════════════════════════════════════
NIVEAU EXIGÉ : AGENCE PRO PENTAGRAM / WIEDEN+KENNEDY
═══════════════════════════════════════════════════════════════════

Le rendu doit susciter un EFFET WHAOU. Pas du texte plat sur fond
coloré — c'est le minimum syndical d'un stagiaire. Tu produis du
DESIGN avec :
- Composition visuelle réfléchie (rythmes, contrastes, focal points)
- Éléments décoratifs (formes géométriques, lignes d'accent, ornements)
- Profondeur (gradients subtils, overlays opacity, ombres)
- Iconographie Iconify systématique (phone, mail, web, location, briefcase)
- Hiérarchie typo CONTRASTÉE (taille × poids × couleur — 3-4 niveaux)
- Détails graphiques (filets séparateurs, bordures arrondies, badges,
  cartouches, encadrés colorés)

Pour CHAQUE visuel : pose-toi la question "est-ce qu'un client paierait
pour ça ?" — si non, ajoute des éléments graphiques jusqu'à ce que oui.

═══════════════════════════════════════════════════════════════════
EXIGENCES DE QUALITÉ — APPLIQUE-LES À TOUT VISUEL DEMANDÉ
═══════════════════════════════════════════════════════════════════

Tu es responsable du résultat final. Voici les standards à respecter,
quel que soit le type de visuel (carte, flyer, livret, BD, packaging,
CV, post social, affiche, dépliant, magazine, étiquette, badge, ticket,
diplôme, infographie, mind map, ou tout autre format imprimable).

1. TYPOGRAPHIE
   - 3 niveaux maximum : titre principal (16-72pt selon format),
     sous-titre (10-14pt), corps (8-10pt). Légendes/captions 6-7pt.
   - Une seule famille de police par visuel (sauf raison forte). Si
     deux : une serif éditoriale + une sans-serif moderne. Jamais 3+.
   - Police défaut "Inter" ou "Inter-Bold" (sans-serif moderne lisible).
     Alternatives : "Helvetica", "Helvetica-Bold", "Times-Roman",
     "Times-Bold", "Times-Italic", "Courier".
   - Bold = poids 700, jamais bold cosmétique sur du corps de texte.
   - Italic = pour citations, légendes, mentions légales — jamais titre.
   - Letter-spacing négatif léger (-0.5) sur les très grands titres
     (>40pt) pour resserrer la lecture.
   - Interligne : 1.2 pour titres, 1.4-1.5 pour corps de texte long.

2. PALETTE COULEURS
   - 2-3 couleurs maximum : 1 primaire (corporate/registre), 1 accent
     (highlights), 1 fond (souvent blanc ou sombre profond).
   - Si BrandKit utilisateur fourni : utilise EXCLUSIVEMENT ces couleurs.
   - Sinon adapte au registre : sobre/cérémonial = navy + or + ivoire ;
     festif = palette tropicale ; corporate = bleu + gris ; santé = vert
     menthe + blanc ; tech = sombre + neon ; mariage = pastel + or ;
     deuil = noir + gris + blanc cassé ; restaurant = terre + bordeaux.
   - Jamais de couleurs criardes pour textes longs (saturation max 70%).
   - Ratio contraste WCAG AA minimum (texte sur fond) : 4.5:1.

3. HIÉRARCHIE VISUELLE
   - Le regard doit suivre un parcours évident : élément le plus gros /
     contrasté en haut → secondaires → tertiaires → CTA / signature.
   - Un seul "héros" par page (image dominante, titre impact, OU couleur
     pleine — jamais les trois en même temps).
   - Espace blanc autour des éléments importants (au moins 1× leur
     hauteur de marge).

4. COMPOSITION & GRILLE
   - Marges symétriques (en général 10-15mm sur A4, 5-10mm sur A6/carte).
   - Aligne tous les éléments sur une grille invisible. Pas de
     positionnement aléatoire — chaque coordonnée doit avoir une raison.
   - Pour LES VISUELS REGROUPANT N ÉLÉMENTS À DÉCOUPER (cartes, badges,
     étiquettes, cases BD, vignettes) : produis UNE seule page A4
     contenant tous les N éléments en grille mathématique (lignes ×
     colonnes calculées), PAS N pages séparées avec 1 élément chacune.
     Calcule : marges + gutter + (taille_element × N) ≤ format_page.
     Ajoute des crop_marks autour de chaque trim de découpe.

5. ESPACE / RESPIRATION
   - Ne charge jamais une page à plus de 70% en éléments. Le vide est
     un élément actif du design, pas un manque.
   - Marges intérieures généreuses dans les rectangles fond (au moins
     5mm de padding texte).

6. PHOTO / IMAGE
   - Pour photos pleine page (héros, cover) : étends de -3mm à
     format_w+3mm pour couvrir le bleed (fond perdu impression).
   - Mode "cover" pour remplir un cadre sans déformer (recadrage centre).
   - Mode "contain" pour respecter ratio sans recadrage (logos, icônes).
   - Si l'utilisateur fournit un media via ref_media : utilise-le.
   - Si aucun media et image nécessaire : utilise type "image" avec
     prompt_ia décrivant en anglais détaillé la scène attendue
     (généré par fal.ai/Replicate downstream).
   - Jamais d'image gratuite sans intention narrative.

7. BLEED & PRINT-READY
   - bleed_mm = 3 par défaut (5mm si format > A3).
   - Tout fond plein-page (couleur, image héroïque, motif) doit déborder
     de bleed_mm au-delà du trim sur les 4 côtés. Les éléments texte
     restent strictement à l'intérieur des marges (jamais < 5mm du trim).
   - Pour visuels destinés impression imprimerie (cartes, flyers,
     affiches, livrets), ajoute systématiquement des crop_marks aux
     coins des zones à découper.

8. ÉLÉMENTS DÉCORATIFS
   - Ornements (vague, géométrique, étoile, feuilles, ligne) : avec
     parcimonie, accent visuel ponctuel, jamais saturation décorative.
   - Lignes séparatrices : 0.3-0.8pt, couleur accent ou neutre.
   - Bordures rectangle : 0.5-1pt max, sauf intention forte.

9. ADAPTATION CONTEXTE
   - Pays utilisateur : adapte conventions visuelles (FR/EU = sobre +
     éditorial ; US = direct + impact ; JP = minimaliste + symboles ;
     Afrique francophone = chaleureux + couleurs vives selon registre).
   - Verticale métier : si fournie, applique le ton recommandé, le
     lexique, les couleurs typiques, les polices typiques.
   - Brand kit : prime sur tout le reste.

10. NOMBRE DE PAGES
    - 1 page par défaut pour visuels uniques (carte, flyer, affiche,
      post social, CV, étiquette, badge).
    - N pages pour livrets/brochures/magazines/BD/packagings dépliables
      uniquement si le brief le demande explicitement.
    - JAMAIS 1 page par "élément" (anti-pattern : 5 cartes ≠ 5 pages,
      c'est 1 page A4 avec 5 cartes en grille).

11. RÉPONSE STRICTE
    - Toujours en JSON valide, sans markdown, sans commentaire avant ou
      après.
    - Tous les textes du document final en FRANÇAIS sauf si l'utilisateur
      demande explicitement une autre langue dans son brief.
    - Coordonnées en mm cohérentes avec format_mm.
    - Aucune coordonnée négative (sauf bleed -3 explicite pour fond
      plein-page).
    - Aucun élément hors page (x+w doit toujours rester ≤ format_w+bleed).

═══════════════════════════════════════════════════════════════════
ANALYSE INTELLIGENTE DE L'INTENTION — UNIVERSEL
═══════════════════════════════════════════════════════════════════

AUCUNE recette figée par mot-clé. Tu LIS le brief, tu COMPRENDS la
vraie intention (qui consomme, dans quel contexte, pour quoi faire),
puis tu décides librement :
- Format (A6, A5, A4, A3, A2, A1, A0, carte, US Letter, Tabloid, ratio
  social, packaging dieline, livret multi-pages, etc.).
- Orientation (portrait / paysage).
- Densité (visuel marketing dense vs rapport éditorial aéré).
- Nombre de pages (1 seule pour une affiche, multi-pages pour un livret).
- Style (photoréaliste héroïque, éditorial sobre, infographique data,
  illustratif BD, technique schéma, célébratif événementiel, etc.).

QUELQUES INTENTIONS POSSIBLES (liste NON exhaustive — sois capable de
gérer N'IMPORTE QUOI) :
- Visuels marketing (flyers, affiches, publicités produit, packaging,
  posts réseaux sociaux, bannières web).
- Identité (cartes de visite, badges, en-têtes, signatures email,
  papier à lettre, étiquettes, autocollants).
- Événementiel (faire-parts, invitations, programmes, billets, menus,
  diplômes, certificats, save-the-date, cartes de vœux, hommage).
- Éditorial (rapports d'analyse avec tableaux + graphiques natifs,
  notes de synthèse, fiches techniques, magazines, brochures, livrets,
  whitepapers, études).
- Data (infographies, dashboards print, tableaux comparatifs,
  organigrammes, mind maps, timelines, schémas process).
- Narratif (BD éducative, manuels illustrés, livrets formation,
  storyboards).
- Personnel (CV graphiques, portfolios, lettres motivation visuelles).
- Tout autre format imprimable ou numérique pertinent.

QUESTIONNE-TOI AVANT DE COMPOSER :
1. Quel est le LIVRABLE final ? (un PDF à imprimer ? un post Instagram ?
   un livret 8 pages ? un dashboard ?)
2. Quel FORMAT physique / numérique sert le mieux cette intention ?
   (cf. référentiel ci-dessous).
3. Quel REGISTRE émotionnel ? (sobre/cérémonial, festif/joyeux, urgent/
   impactant, technique/data, narratif/pédagogique, intime/personnel).
4. Quelle DENSITÉ ? Un faire-part = épuré + ornements. Un rapport
   d'analyse = tableaux + graphiques + légendes denses. Une pub produit
   = image héroïque + USP + CTA + specs visuels.
5. Quels ÉLÉMENTS spécifiques sont nécessaires ? (image IA héroïque,
   tableaux de données, graphiques natifs en rectangles+textes+lignes,
   timelines, photos, QR codes, icônes Iconify illustratives).

═══════════════════════════════════════════════════════════════════
FORMATS IMPRIMABLES & NUMÉRIQUES — RÉFÉRENTIEL UNIVERSEL
═══════════════════════════════════════════════════════════════════

Tu DOIS toujours choisir le BON format physique/numérique adapté à
l'intention. Voici le référentiel standard mondial à appliquer pour
TOUS les visuels (pas uniquement les cartes de visite) :

SÉRIE ISO 216 (papier standard mondial — défaut Europe/Afrique) :
- A0 : 841×1189mm (très grand poster, plan technique, signalétique salon)
- A1 : 594×841mm (poster expo, plan architecture)
- A2 : 420×594mm (poster, infographie murale, calendrier)
- A3 : 297×420mm (affiche, set de table, brochure pliée, dessin technique)
- A4 : 210×297mm (rapport, flyer 1 page, page de magazine, lettre)
- A5 : 148×210mm (livret, dépliant, programme, menu, faire-part)
- A6 : 105×148mm (carte postale, ticket, save-the-date, étiquette grand)
- A7 : 74×105mm (mini-flyer, étiquette, ticket événement)

FORMATS US (si pays = US/CA ou brief le demande) :
- US Letter : 215.9×279.4mm (rapport US, flyer US)
- US Legal : 215.9×355.6mm (contrat US long)
- Tabloid/Ledger : 279.4×431.8mm (poster US, magazine US double-page)
- Half Letter : 139.7×215.9mm (livret US)

CARTES & IDENTITÉ :
- Carte de visite EU/Afrique : 85×55mm (parfois 90×55mm)
- Carte de visite US : 88.9×50.8mm (3.5×2 in)
- Carte de visite JP : 91×55mm
- Badge nominatif : 85×54mm ou 100×70mm
- Carte de fidélité : 85×55mm (format CB)

ÉVÉNEMENTIEL :
- Faire-part standard : 105×148mm (A6) ou 148×210mm (A5) plié
- Carton invitation : 100×150mm ou 127×178mm
- Save-the-date : 105×148mm (A6) ou format carré 130×130mm
- Billet d'entrée : 75×210mm (long) ou A7
- Menu restaurant : A4 plié ou A5 simple
- Programme événement : A5 plié ou A4 plié 3 volets

LIVRETS & BROCHURES :
- Brochure A4 pliée 2 volets (gate-fold) : A4 ouvert → A5 fermé
- Brochure A4 pliée 3 volets (tri-fold) : A4 ouvert → 99×210mm fermé
- Livret A5 broché : multiples de 4 pages (A5, 8 pages, 12 pages...)
- Magazine A4 : 210×297mm, dos carré ou agrafé

PACKAGING :
- Étiquette bouteille : 90×110mm (vin), 60×80mm (cosmétique)
- Boîte cubique : à composer en dieline développée
- Sachet plat : 100×150mm
- Sticker rond / carré : 50×50mm, 80×80mm, 100×100mm

RÉSEAUX SOCIAUX (export numérique, pas d'impression) :
- Instagram carré : 1080×1080px → 100×100mm @300dpi
- Instagram portrait : 1080×1350px → 91.4×114.3mm @300dpi
- Story / Reel 9:16 : 1080×1920px → 91.4×162.6mm @300dpi
- Facebook post : 1200×630px (paysage)
- LinkedIn post : 1200×627px (paysage) / 1080×1080 (carré)
- LinkedIn bannière profil : 1584×396px
- YouTube thumbnail : 1280×720px
- Twitter/X header : 1500×500px
Pour réseaux : convertis pixels→mm @ 300dpi (1mm = 11.81px à 300dpi).

CV / DOCUMENTS PERSONNELS :
- CV EU/Afrique : A4 portrait
- CV US : US Letter portrait
- Portfolio : A4 paysage ou carré 210×210mm

AFFICHAGE PUBLICITAIRE (campagnes outdoor) :
- Affiche 40×60cm (urbain, vitrine)
- Affiche 60×80cm (abribus)
- 4×3m (panneau outdoor — composé en A2 mis à l'échelle, mêmes ratios)
- Roll-up : 850×2000mm (salon, événement)
- Kakemono : 600×1600mm ou 800×2000mm

RÈGLE DE SÉLECTION :
- Si brief précise format (« A3 », « format Instagram », « carte 90mm ») :
  applique-le strictement.
- Sinon : déduis le BON format depuis l'intention. Affiche événement →
  A3/A2. Faire-part mariage → A6 plié. Rapport interne → A4. Carte de
  visite → grille N cartes 85×55mm sur A4 imprimerie. Story Instagram →
  91.4×162.6mm. Flyer promo magasin → A5 ou A6.

═══════════════════════════════════════════════════════════════════
ENSEMBLES MULTI-PIÈCES — UN SEUL PDF, PLUSIEURS FORMATS
═══════════════════════════════════════════════════════════════════

Énormément de livrables réels ne sont PAS une seule pièce mais un
ENSEMBLE COHÉRENT de plusieurs pièces de formats différents partageant
la même identité visuelle (mêmes couleurs, polices, ornements, ton).
Tu DOIS savoir composer ces ensembles en UN SEUL PDF où CHAQUE page
peut avoir un `format_mm` propre via override.

Le schema autorise `pages[i].format_mm: [W, H]` qui surcharge le
`format_mm` document. Si absent, la page hérite. Tu peux donc mixer
librement A6 + A5 + A4 + carte 85×55 dans le même PDF.

EXEMPLES D'ENSEMBLES MULTI-PIÈCES (liste NON exhaustive — sois capable
d'inventer la composition adaptée à toute intention) :

- Faire-part de deuil COMPLET :
  * Page 1 — Carte principale (annonce décès) — 105×148mm (A6)
  * Page 2 — Livret de messe / programme funérailles — 148×210mm (A5)
    [peut être plusieurs pages A5 si le programme est long]
  * Page 3 — Carte de remerciement — 85×55mm (format CB)
  * Page 4 — Carte mémorial / souvenir avec portrait du défunt —
    74×105mm (A7) ou 85×55mm
  * Page 5 — Carton invitation à la veillée — 100×150mm

- Faire-part de mariage COMPLET :
  * Carte d'invitation principale — A6 ou format carré 130×130mm
  * Carton réponse RSVP — 100×150mm
  * Carton plan / itinéraire — 100×150mm
  * Carton menu — 100×210mm (DL)
  * Marque-place — 50×85mm
  * Carte de remerciement — 105×148mm

- Kit identité visuelle entreprise :
  * Page 1 — Carte de visite (8 cartes 85×55 sur A4 imprimerie)
  * Page 2 — En-tête papier à lettre — A4
  * Page 3 — Enveloppe DL — 220×110mm
  * Page 4 — Carte de compliments — 148×105mm (A6 paysage)

- Kit événement (salon / conférence) :
  * Page 1 — Affiche A3 — 297×420mm
  * Page 2 — Flyer A5 — 148×210mm
  * Page 3 — Billet d'entrée — 75×210mm
  * Page 4 — Badge nominatif — 100×70mm
  * Page 5 — Programme A5 plié

- Faire-part naissance / baptême :
  * Annonce naissance — A6
  * Carton remerciement — format CB
  * Marque-place baptême — 50×85mm

- Pack restaurant :
  * Menu A4
  * Menu enfant A5
  * Marque-table 75×210mm
  * Carte fidélité format CB

- Pack hommage / commémoration / anniversaire de décès :
  * Affiche A3
  * Carte souvenir A6
  * Programme cérémonie A5

RÈGLES MULTI-PIÈCES :
1. CHAQUE pièce est UNE page du PDF avec son propre `format_mm`.
2. Toutes les pièces partagent la MÊME identité : palette commune,
   typographie commune, ornements/icônes cohérents, ton homogène.
3. Mets `libelle_piece` (snake_case court) sur chaque page pour
   l'identifier : "carte_principale", "livret_messe", "remerciement",
   "rsvp", "menu", "badge", "marque_place", "billet", "souvenir"…
4. Ajoute des `crop_marks` sur les pièces destinées à découpe imprimerie.
5. Si le brief décrit clairement UNE seule pièce (« une carte de visite »,
   « un faire-part », « un flyer »), reste sur UN SEUL format — n'invente
   pas un ensemble si l'utilisateur ne le demande pas. À l'inverse, si
   le brief évoque un ensemble (« faire-part deuil complet », « kit
   mariage », « pack identité », « ensemble cérémonie »), génère
   véritablement l'ensemble multi-pièces.
6. Si l'utilisateur n'est PAS explicite mais que le livrable nécessite
   intrinsèquement plusieurs pièces (ex: « faire-part de deuil » sans
   précision = annonce + remerciement minimum), juge intelligemment et
   propose l'ensemble minimum cohérent (2-3 pièces) plutôt qu'une seule
   carte qui paraîtrait incomplète.

═══════════════════════════════════════════════════════════════════
EXIGENCES TRANSVERSALES — APPLICABLES À TOUT VISUEL
═══════════════════════════════════════════════════════════════════

Quel que soit le livrable, tu produis du DESIGN PRO, pas du texte plat :
- COMPOSITION réfléchie : focal point, parcours œil, contrastes,
  rythmes. Aucune coordonnée arbitraire.
- HIÉRARCHIE typographique CONTRASTÉE (3-4 niveaux taille × poids ×
  couleur). Lis le brief : si rapport éditorial, 1 titre + 1 sous-titre
  + corps. Si pub marketing, méga-titre + sous-titre choc + features.
  Si faire-part, titre ornemental + date/lieu + RSVP discret.
- ICÔNES ICONIFY systématiques quand pertinent (1 par feature, 1 par
  contact, 1 par section). Collection `tabler` ou `lucide` par défaut.
- ORNEMENTS / FORMES géométriques d'accent (lignes filets, badges
  arrondis, bandeaux latéraux, cartouches, fonds colorés border-radius).
- IMAGES IA via prompt_ia (anglais détaillé 30-60 mots) pour héros,
  scènes produit, ambiance, photos d'illustration. Mode "cover" pour
  remplir un cadre, "contain" pour respecter le ratio.
- TABLEAUX & GRAPHIQUES NATIFS pour analyses Excel / rapports data :
  un tableau = grille de rectangles fond + textes alignés (en-têtes
  fond accent, lignes alternées gris très clair, séparateurs 0.3pt).
  Un graphique = composition rectangles (barres) + lignes (axes) +
  textes (légendes) + cercles via ornement. Pas d'image bitmap pour
  data — composition vectorielle directe.
- ÉLÉMENTS DE PRINT-READY : crop_marks autour des trims à découper,
  bleed -3mm sur fonds plein-page, marges techniques 5mm minimum
  côté trim.
- DENSITÉ MINIMALE par page significative : au moins 6 éléments. Texte
  plat + fond uni = ÉCHEC. Toujours ajouter ornement, icône, gradient,
  bordure, badge, accent pour donner du caractère.
- GRILLES MATHÉMATIQUES pour N éléments répétés (cartes, vignettes,
  cases BD, étiquettes) : UNE page A4/A3 avec N éléments en grille
  calculée (lignes × colonnes), JAMAIS N pages d'un seul élément.

  ALGORITHME OBLIGATOIRE quand brief = « N <items> » (N>=2) :
  1. Calcule cartes_par_page = floor((H_page - 2*marge) / (h_item + gutter_v))
     × floor((W_page - 2*marge) / (w_item + gutter_h)).
     Exemple A4 portrait (210×297) + cartes 85×55 + marge 10 + gutter 5 :
     colonnes = floor((210-20)/(85+5))=2, lignes=floor((297-20)/(55+5))=4
     → 8 cartes/A4.
  2. nb_pages = ceil(N / cartes_par_page). Ex: 20 cartes → 3 pages A4.
  3. Sur CHAQUE page, dessine TOUTES les positions cartes_par_page de la
     grille (sauf la dernière page : juste les restants N mod nb_pages).
  4. Pour CHAQUE carte : compose un BLOC dense complet — fond couleur
     primaire, accent latéral, nom Bold, fonction italique accent, filet
     fin, 3 icônes contact (phone/mail/web) avec textes, QR vCard valide,
     logo top-right si fourni. PAS de carte plate texte-seul.
  5. crop_marks pour CHAQUE trim de découpe + marges techniques 3mm bleed.
  6. SIMULATION DE DONNÉES — si le brief dit « simule les infos »,
     « simule N employés », « génère N personnes » sans liste précise :
     INVENTE N (nom + prénom + fonction + téléphone + email pro)
     RÉALISTES adaptés au pays/secteur du profil. Varie titres et
     fonctions (DG, RH, Compta, Commercial, Tech, Marketing…). Évite
     « John Doe » génériques.

  CONSÉQUENCE TECHNIQUE : pour 20 cartes, le JSON contiendra environ
  20 × ~8 éléments primitives = ~160 éléments + ornements + crop_marks.
  Sois DENSE mais COMPACT (clés JSON courtes, pas de répétition inutile,
  pas de commentaires). Tu DOIS faire tenir l'ensemble dans la limite
  de tokens — réduis verbosité plutôt que de tronquer des cartes.

DÉFAUTS À ÉVITER ABSOLUMENT :
- Texte centré sur fond uni sans aucun élément graphique.
- Une seule famille de couleur sans accent.
- Photos décoratives sans intention.
- Plus de 3 polices différentes.
- Marges incohérentes.
- N pages séparées pour N cartes/vignettes (anti-pattern grille).
- Inventer des données (chiffres, dates, noms) absentes du brief.
- Faire le même design pour toutes les intentions — chaque livrable
  doit visuellement REFLÉTER son intention (un faire-part ne ressemble
  pas à une pub Starlink ne ressemble pas à un rapport audit).

DONNÉES & FAITS :
- N'invente PAS de noms / dates / chiffres absents du brief.
- Si le brief mentionne N personnes nommées : utilise EXACTEMENT ces
  noms et fonctions. S'il dit « N personnes » sans préciser, génère
  N noms réalistes adaptés au pays (Cameroun = noms FR + bantous, etc.).
- Pour les QR vCard : contenu vCard valide complet (BEGIN:VCARD …
  END:VCARD avec FN, TITLE, ORG, TEL, EMAIL au minimum).
- Pour graphiques data : utilise UNIQUEMENT les chiffres fournis par
  le brief. Aucune extrapolation, aucune projection inventée.
- Toujours produire un JSON STRICT, sans commentaire ni markdown.

Tu reçois maintenant le contexte (brief + médias + brand kit + verticale).
Compose le layout PARFAIT pour ce visuel.
"""


async def _pre_generer_donnees_simulees(
    brief: str,
    nb_items: int,
    profil: Optional[dict] = None,
    pays: str = "CM",
    langue: str = "fr",
) -> list[dict]:
    """Pré-génère N entrées simulées GÉNÉRIQUES via Haiku, peu importe le
    type d'item (cartes de visite, badges visiteurs, étiquettes produits,
    marque-places mariage, tickets concert, fiches trombinoscope, menus,
    médailles compétition, fiches élèves, dossards course, sigles,
    diplômes, certificats…).

    Le LLM INFÈRE le schéma de données depuis le brief lui-même, puis
    génère N entrées avec ce schéma. Aucun cas hardcodé.

    Étape 1 (Haiku, ~50ms) : « Quel schéma de données pour ce visuel ? »
                            → liste de champs adaptés au contexte
    Étape 2 (Haiku, ~200ms) : génère N entrées avec ce schéma

    En réalité on combine les 2 en un seul appel pour économiser.

    Le composer freeform recevra ces N entrées et fera la mise en page.

    Retourne [] en cas d'échec (le composer continue avec son travail
    normal, avec risque de placeholders comme avant).
    """
    try:
        from core.ia_client import ia_client, ModeIA, ModelePrioritaire
        import json as _j

        nom_org = (profil or {}).get("nom_organisation") or ""
        metier  = (profil or {}).get("metier") or ""

        prompt = (
            f"Tu produis des données SIMULÉES réalistes pour un visuel "
            f"comportant {nb_items} éléments répétés (cartes, badges, "
            f"étiquettes, fiches, tickets, marque-places, dossards, "
            f"médailles, certificats, ou tout autre item répété).\n\n"
            f"BRIEF UTILISATEUR :\n« {brief[:800]} »\n\n"
            f"CONTEXTE :\n"
            f"- Pays : {pays}\n"
            f"- Langue : {langue}\n"
            f"- Organisation : {nom_org or '(non précisée)'}\n"
            f"- Secteur/métier : {metier or '(non précisé)'}\n\n"
            f"ÉTAPE 1 — INFÉRER LE SCHÉMA. Lis le brief, déduis les CHAMPS "
            f"pertinents pour CE type d'item :\n"
            f"  - Cartes de visite → nom, prenom, fonction, tel, email\n"
            f"  - Badges visiteurs salon → nom, prenom, entreprise, role\n"
            f"  - Étiquettes produits → nom_produit, volume_poids, "
            f"description_courte, code_ean\n"
            f"  - Marque-places mariage → nom_invite, table\n"
            f"  - Tickets concert → numero, categorie, prix\n"
            f"  - Trombinoscope employés → nom, prenom, fonction, departement\n"
            f"  - Médailles compétition → numero_dossard, nom, equipe, "
            f"discipline\n"
            f"  - Menus restaurant → plat, description, prix, allergenes\n"
            f"  - Diplômes → nom_recipiendaire, intitule_diplome, mention, "
            f"date\n"
            f"  - … ou tout autre schéma adapté au brief.\n\n"
            f"ÉTAPE 2 — GÉNÉRER. Produis EXACTEMENT {nb_items} entrées "
            f"avec ce schéma. Données RÉELLES adaptées au pays {pays} et "
            f"au secteur :\n"
            f"  - Noms : prénoms+noms RÉALISTES (locaux + internationaux), "
            f"jamais « Nom Prénom » / « John Doe ».\n"
            f"  - Téléphones (si présents) : format pays correct, chiffres "
            f"variés (pas « 6XX XXX XXX »).\n"
            f"  - Emails : prenom.nom@<slug-org>.<tld>.\n"
            f"  - Prix/montants (si présents) : en devise locale, chiffres "
            f"plausibles.\n"
            f"  - Tout autre champ : valeurs concrètes, jamais de placeholder.\n\n"
            f"FORMAT DE RÉPONSE — JSON STRICT, AUCUN markdown, AUCUN "
            f"commentaire. Structure obligatoire :\n"
            f"{{\n"
            f'  "schema": ["champ1", "champ2", "champ3", ...],\n'
            f'  "items": [\n'
            f'    {{"champ1": "valeur1", "champ2": "valeur2", ...}},\n'
            f'    ... ({nb_items} entrées au total) ...\n'
            f"  ]\n"
            f"}}"
        )
        rep = await ia_client.appeler(
            prompt=prompt,
            mode=ModeIA.REDACTION,
            forcer_modele=ModelePrioritaire.CLAUDE_HAIKU,    # → gpt-4o-mini si LLM_PRIMAIRE=gpt
            json_attendu=True,
            # 20 items × ~120 tokens (schémas larges types étiquettes) = 2400,
            # marge pour 50+ items courts → 4000.
            max_tokens_override=4000,
            utiliser_cache=False,
        )
        contenu = (rep.contenu or "").strip()
        try:
            data = _j.loads(contenu)
        except _j.JSONDecodeError:
            import re as _re
            m = _re.search(r"\{[\s\S]*\}", contenu)
            data = _j.loads(m.group()) if m else {}

        if not isinstance(data, dict):
            return []
        items = data.get("items") or []
        if not isinstance(items, list):
            return []
        # Sanitization — chaque entrée est un dict de strings/numbers, on
        # accepte n'importe quel schéma renvoyé par Haiku.
        out: list[dict] = []
        for item in items[:nb_items]:
            if not isinstance(item, dict):
                continue
            entry = {}
            for k, v in item.items():
                if v is None:
                    continue
                key = str(k).strip()[:40]
                if isinstance(v, (int, float)):
                    entry[key] = v
                else:
                    entry[key] = str(v).strip()[:200]
            if entry:
                out.append(entry)
        return out
    except Exception as e:
        logger.warning(f"[FreeformComposer] Pré-génération données simulées KO : {e}")
        return []


async def _composer_carte_template(
    brief: str,
    profil: Optional[dict] = None,
    brand_kit: Optional[dict] = None,
    descripteur_vertical: Optional[dict] = None,
    medias_descripteurs: Optional[list[dict]] = None,
    pays: str = "CM",
    langue: str = "fr",
    card_w_mm: float = 85.0,
    card_h_mm: float = 55.0,
) -> dict:
    """Demande au LLM de composer UNE SEULE carte de visite template
    (page unique 85×55mm avec design pro). On utilise ce template comme
    motif à dupliquer N fois en grille A4 côté Python.

    Le LLM est libre sur le style (palette, layout, typo) en fonction
    du brief / verticale métier / brand kit / médias uploadés. Pas de
    design hard-codé pour permettre la variété entre organisations.

    Retourne un dict { format_mm, pages: [{elements: [...]}] } ou {} si
    échec.
    """
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire

    couleur_prim = (profil or {}).get("couleur_primaire_hex") or ""
    accents = (profil or {}).get("couleurs_accents_hex") or []
    nom_org = (profil or {}).get("nom_organisation") or ""
    metier = (profil or {}).get("metier") or ""

    # Palette : priorité brand_kit > profil > déduction via verticale métier.
    bk_palette_hint = ""
    if brand_kit and (brand_kit.get("couleur_primaire_hex") or brand_kit.get("couleurs_accents_hex")):
        bk_palette_hint = (
            f"\n## PALETTE BRAND KIT (à respecter STRICTEMENT) :\n"
            f"- Primaire : {brand_kit.get('couleur_primaire_hex') or couleur_prim or '(libre)'}\n"
            f"- Accents : {brand_kit.get('couleurs_accents_hex') or accents or '(libre)'}\n"
            f"Tu n'as PAS le droit d'utiliser d'autres couleurs principales.\n"
        )
    elif couleur_prim or accents:
        bk_palette_hint = (
            f"\n## PALETTE PROFIL (à utiliser comme couleur dominante) :\n"
            f"- Primaire : {couleur_prim or '(à déduire du métier)'}\n"
            f"- Accents : {accents or '(à déduire du métier)'}\n"
        )

    # Verticale métier : couleurs/polices/ton typiques pour adapter le style.
    vertical_hint = ""
    if descripteur_vertical:
        couleurs_typ = descripteur_vertical.get("couleurs_typiques") or ""
        polices_typ = descripteur_vertical.get("polices_typiques") or ""
        ton = descripteur_vertical.get("ton_recommande") or ""
        label_vert = descripteur_vertical.get("label") or metier or ""
        vertical_hint = (
            f"\n## STYLE MÉTIER ({label_vert}) — à appliquer si pas de brand kit :\n"
            f"- Couleurs typiques : {couleurs_typ or 'libre selon ton du brief'}\n"
            f"- Polices recommandées : {polices_typ or 'sans-serif moderne'}\n"
            f"- Ton visuel : {ton or 'professionnel'}\n"
            f"Ne te limite PAS à navy/jaune. Le visuel doit évoquer le métier.\n"
        )

    # Médias uploadés (logo, bannière). Si présents, le LLM les référence
    # via ref_media dans un élément Image dans la carte.
    media_hint = ""
    logos_refs = []
    bannieres_refs = []
    if medias_descripteurs:
        for m in medias_descripteurs:
            cat = (m.get("categorie") or "").lower()
            ref = m.get("ref")
            if not ref:
                continue
            if "logo" in cat or m.get("est_logo"):
                logos_refs.append(ref)
            elif "banniere" in cat or "banner" in cat or "header" in cat:
                bannieres_refs.append(ref)
        if logos_refs or bannieres_refs:
            media_hint = (
                f"\n## MÉDIAS UPLOADÉS PAR L'USER (à utiliser via ref_media) :\n"
            )
            if logos_refs:
                media_hint += (
                    f"- LOGO disponible (ref_media={logos_refs[0]!r}) — "
                    f"OBLIGATOIRE de l'inclure en Image 12×12mm coin haut-gauche\n"
                    f"  ou centré sur le verso. Format : {{\"type\":\"image\",\"ref_media\":\"{logos_refs[0]}\",\"x_mm\":...,\"y_mm\":...,\"w_mm\":12,\"h_mm\":12}}\n"
                )
            if bannieres_refs:
                media_hint += (
                    f"- BANNIÈRE/HEADER disponible (ref_media={bannieres_refs[0]!r}) — "
                    f"à placer en haut de la carte ou pleine largeur verso.\n"
                )

    nom_org_hint = (
        f"Organisation : « {nom_org} »\n" if nom_org else
        "Organisation : à déduire intelligemment du brief\n"
    )
    metier_hint = (
        f"Métier : {metier}\n" if metier else ""
    )

    prompt = f"""\
Compose UNE SEULE carte de visite professionnelle au format {card_w_mm}×{card_h_mm}mm.
Tu produis DEUX pages : page 1 = RECTO, page 2 = VERSO de cette même carte
(impression recto-verso standard duplex).

Brief utilisateur : « {brief[:400] if brief else ''} »
{nom_org_hint}{metier_hint}Pays : {pays} / Langue : {langue}
{bk_palette_hint}{vertical_hint}{media_hint}
═══ LIBERTÉ CRÉATIVE TOTALE SUR LE STYLE ═══

Tu CHOISIS le design en fonction du métier/secteur/brief, sans rester
prisonnier d'un template "navy + jaune". Inspire-toi de l'identité du
métier :
  - Finance/banque : navy/charcoal + or, sobre et institutionnel
  - Santé/médical : blanc + vert sapin ou bleu cyan, propre et rassurant
  - Tech/IT : noir/blanc + cyan/turquoise/violet, géométrique et moderne
  - Restauration/food : terracotta/crème ou noir + or, chaleureux
  - Juridique : noir + bordeaux ou navy, classique sérigraphié
  - Mode/créatif : couleurs vives ou pastels, audacieux et asymétrique
  - Industriel/BTP : gris/anthracite + orange sécurité, robuste
  - Éducation : vert sapin + crème, lisible et accessible
  - Conseil/coaching : violet/aubergine + or, premium élégant
  - Cosmétique/beauté : rose poudré + or rosé, féminin doux
Pour les autres métiers, déduis intelligemment d'après le contexte.

═══ PAGE 1 (RECTO) — éléments OBLIGATOIRES ═══

Tu places dans l'ordre que tu juges esthétique :
1. Rectangle fond couleur primaire pleine carte avec border_radius
2. Élément visuel d'accent au choix : bandeau vertical/horizontal, demi-cercle,
   diagonale, encart, grille géométrique — varie selon le style métier
3. Texte « NOM Prénom » Bold 11-13pt en couleur lisible — placeholder
4. Texte « Fonction » italic ou regular 8pt couleur accent — placeholder
5. Filet/séparateur subtil (0.4pt, 25-50mm) selon style
6. Icone tabler phone 4×4mm + IMMÉDIATEMENT À DROITE Texte « +237 6XX XXX XXX »
   7pt couleur lisible — placeholder remplacé auto
7. Icone tabler mail 4×4mm + IMMÉDIATEMENT À DROITE Texte « email@org.cm »
   7pt — placeholder remplacé auto
8. Icone tabler world 4×4mm + IMMÉDIATEMENT À DROITE Texte « www.org.cm »
   7pt — placeholder remplacé auto
9. QR 11-14mm coin choisi (avec contraste correct)
10. Si LOGO uploadé : Image ref_media en coin 10-14mm
11. Crop marks aux 4 coins

⚠️ IMPÉRATIF : chaque icône (phone/mail/world) DOIT avoir SON TEXTE adjacent.
   Pas d'icône seule sans texte à côté.

═══ PAGE 2 (VERSO) — branding organisation ═══

Design plus aéré, met en valeur l'identité de l'organisation :
1. Rectangle fond couleur primaire (ou inverse : fond blanc + accent vif)
2. Si LOGO uploadé : Image ref_media 25-35mm centrée verticalement
3. Sinon : Texte nom organisation Bold 14-18pt centré
4. Sous-titre : slogan/baseline en italic 8-9pt couleur accent
5. Élément graphique décoratif : forme géométrique ou pattern subtil
6. Si bannière uploadée : Image ref_media en haut, pleine largeur (avec
   crop si nécessaire pour respecter format carte)
7. Crop marks aux 4 coins

Format JSON :
{{
  "format_mm": [{card_w_mm}, {card_h_mm}],
  "bleed_mm": 3,
  "palette_meta": {{"primaire": "...", "accent": "...", "fond": "#FFFFFF"}},
  "pages": [
    {{"numero": 1, "libelle_piece": "recto", "fond_couleur": "#FFFFFF", "elements": [ ... ]}},
    {{"numero": 2, "libelle_piece": "verso", "fond_couleur": "#FFFFFF", "elements": [ ... ]}}
  ]
}}

Renseigne palette_meta avec les couleurs que TU as choisies (sera utilisé
pour cohérence du brand kit ultérieur). Retourne UNIQUEMENT le JSON, sans markdown.
"""

    try:
        rep = await ia_client.appeler(
            prompt=prompt,
            systeme=_PROMPT_SYSTEME,
            mode=ModeIA.ANALYSE,
            forcer_modele=ModelePrioritaire.CLAUDE_OPUS,  # → gpt-4-turbo (4096 OK pour 1 carte)
            json_attendu=True,
            max_tokens_override=2500,
            utiliser_cache=False,
        )
        contenu = (rep.contenu or "").strip()
        logger.warning(
            f"[FreeformComposer/Template] LLM répondu {len(contenu)} chars, "
            f"aperçu fin : ...{contenu[-150:]!r}"
        )
        try:
            data = json.loads(contenu)
        except json.JSONDecodeError as _jde:
            logger.warning(
                f"[FreeformComposer/Template] JSON invalide ({_jde}) → regex extraction"
            )
            import re as _re
            m = _re.search(r"\{[\s\S]*\}", contenu)
            data = json.loads(m.group()) if m else {}

        if not isinstance(data, dict) or not data.get("pages"):
            return {}
        return data
    except Exception as e:
        logger.warning(f"[FreeformComposer/Template] Echec LLM : {e}")
        return {}


def _layout_carte_template_fallback(
    card_w_mm: float = 85.0, card_h_mm: float = 55.0,
    couleur_primaire: str = "#003D82",
    couleur_accent: str = "#FFB800",
) -> dict:
    """Layout template de carte de visite hard-coded en cas d'échec LLM.
    Design sobre mais propre : fond primaire, bandeau accent, nom+fonction
    + 3 lignes contact + QR placeholder + crop marks."""
    return {
        "format_mm": [card_w_mm, card_h_mm],
        "bleed_mm": 3,
        "palette_meta": {
            "primaire": couleur_primaire,
            "accent": couleur_accent,
            "fond": "#FFFFFF",
        },
        "pages": [{
            "numero": 1,
            "fond_couleur": "#FFFFFF",
            "elements": [
                # Fond carte
                {"type": "rectangle", "x_mm": 0, "y_mm": 0,
                 "w_mm": card_w_mm, "h_mm": card_h_mm,
                 "fond": couleur_primaire, "border_radius_mm": 2, "z_index": 0},
                # Bandeau accent à gauche
                {"type": "rectangle", "x_mm": 0, "y_mm": 0,
                 "w_mm": 6, "h_mm": card_h_mm,
                 "fond": couleur_accent, "z_index": 1},
                # Nom Prénom
                {"type": "texte", "x_mm": 10, "y_mm": 9,
                 "w_mm": card_w_mm - 18,
                 "contenu": "NOM Prénom",
                 "police": "Inter-Bold", "taille_pt": 11,
                 "couleur": "#FFFFFF", "z_index": 2},
                # Fonction
                {"type": "texte", "x_mm": 10, "y_mm": 16,
                 "w_mm": card_w_mm - 18,
                 "contenu": "Fonction",
                 "police": "Inter", "italic": True, "taille_pt": 8,
                 "couleur": couleur_accent, "z_index": 2},
                # Filet
                {"type": "ligne", "x1_mm": 10, "y1_mm": 22,
                 "x2_mm": 45, "y2_mm": 22,
                 "epaisseur_pt": 0.4, "couleur": couleur_accent, "z_index": 2},
                # Tel
                {"type": "icone", "prefix": "tabler", "name": "phone",
                 "x_mm": 10, "y_mm": 28, "w_mm": 4, "h_mm": 4,
                 "couleur": couleur_accent, "z_index": 2},
                {"type": "texte", "x_mm": 16, "y_mm": 28.5,
                 "w_mm": card_w_mm - 24,
                 "contenu": "+237 6XX XXX XXX",
                 "police": "Inter", "taille_pt": 7,
                 "couleur": "#FFFFFF", "z_index": 2},
                # Mail
                {"type": "icone", "prefix": "tabler", "name": "mail",
                 "x_mm": 10, "y_mm": 34, "w_mm": 4, "h_mm": 4,
                 "couleur": couleur_accent, "z_index": 2},
                {"type": "texte", "x_mm": 16, "y_mm": 34.5,
                 "w_mm": card_w_mm - 24,
                 "contenu": "email@example.com",
                 "police": "Inter", "taille_pt": 7,
                 "couleur": "#FFFFFF", "z_index": 2},
                # World/site
                {"type": "icone", "prefix": "tabler", "name": "world",
                 "x_mm": 10, "y_mm": 40, "w_mm": 4, "h_mm": 4,
                 "couleur": couleur_accent, "z_index": 2},
                {"type": "texte", "x_mm": 16, "y_mm": 40.5,
                 "w_mm": card_w_mm - 24,
                 "contenu": "www.org.cm",
                 "police": "Inter", "taille_pt": 7,
                 "couleur": "#FFFFFF", "z_index": 2},
                # QR
                {"type": "qr", "x_mm": card_w_mm - 16, "y_mm": card_h_mm - 16,
                 "w_mm": 12, "h_mm": 12,
                 "donnees": "BEGIN:VCARD\nVERSION:3.0\nEND:VCARD",
                 "couleur": couleur_primaire, "fond": "#FFFFFF", "z_index": 3},
            ],
        }],
    }


def _reorganiser_grille_a4(
    data: dict,
    donnees: list[dict],
    card_w_mm: float = 85.0,
    card_h_mm: float = 55.0,
) -> dict:
    """Post-validation déterministe : si le LLM a produit l'anti-pattern
    « N pages au format CARTE avec 1 carte par page », on RECONSTRUIT un
    layout en planches A4 avec 8 cartes/page en grille 2×4.

    Robuste : si le LLM a déjà produit une grille A4 correcte, on ne
    touche pas. Si l'anti-pattern est détecté, on extrait la 1re carte
    comme template visuel et on la duplique N fois avec injection des
    données simulées (remplacement du texte par les valeurs réelles).
    """
    pages = data.get("pages") or []
    if not pages or not donnees:
        return data
    # NOTE : on N'EXIGE PLUS len(pages)>=2 — le pipeline 2-phases appelle
    # cette fonction avec un template à UNE seule page (la carte template)
    # qu'on doit dupliquer N fois en grille. Le check précédent
    # `len(pages) < 2 → return` empêchait totalement la duplication.

    # Détection du format de chaque page
    def _page_is_card_format(p):
        fmt = p.get("format_mm")
        if isinstance(fmt, list) and len(fmt) >= 2:
            w, h = float(fmt[0]), float(fmt[1])
        else:
            # Hérite du format doc
            fmt_doc = data.get("format_mm") or [210, 297]
            w, h = float(fmt_doc[0]), float(fmt_doc[1])
        # Carte de visite ≈ 50-100 × 30-70 mm
        return 50 <= w <= 110 and 30 <= h <= 75

    is_per_card_pattern = all(_page_is_card_format(p) for p in pages)
    if not is_per_card_pattern:
        return data  # déjà en grille A4 ou autre

    logger.warning(
        f"[FreeformComposer] Anti-pattern détecté ({len(pages)} pages au "
        f"format carte) → reconstruction grille A4 × 8 cartes"
    )

    # Support recto-verso : page[0] = template recto, page[1] (si présente)
    # = template verso. On génère 2× planches : recto pour toutes les cartes,
    # puis verso. Permet impression duplex standard.
    template_recto = pages[0].get("elements") or []
    template_verso = pages[1].get("elements") if len(pages) >= 2 else None
    a_verso = bool(template_verso)
    template_fond = pages[0].get("fond_couleur") or "#FFFFFF"

    # Post-injection : s'assurer que le template recto contient bien des
    # Texte placeholders pour téléphone, email, website. Le LLM les omet
    # parfois (icône seule sans texte adjacent) → on injecte par défaut.
    def _enrichir_template_recto(elems: list) -> list:
        a_tel = a_email = a_web = False
        for el in elems:
            if not isinstance(el, dict):
                continue
            if (el.get("type") or "").lower() not in ("texte", "text"):
                continue
            c = str(el.get("contenu", "") or "").lower()
            if "+" in c or "tel" in c or "phone" in c or "📞" in c:
                a_tel = True
            if "@" in c:
                a_email = True
            if "www" in c or "http" in c or ".com" in c or ".cm" in c or ".sn" in c:
                a_web = True
        # Si déjà tout présent, on ne touche pas
        if a_tel and a_email and a_web:
            return elems
        # Sinon, on cherche les icônes phone/mail/world pour placer les
        # textes IMMÉDIATEMENT à leur droite (4mm offset).
        enriched = list(elems)
        for el in elems:
            if not isinstance(el, dict):
                continue
            if (el.get("type") or "").lower() != "icone":
                continue
            name = (el.get("name") or "").lower()
            x = float(el.get("x_mm", 0) or 0)
            y = float(el.get("y_mm", 0) or 0)
            w = float(el.get("w_mm", 4) or 4)
            h = float(el.get("h_mm", 4) or 4)
            text_x = x + w + 1.0  # 1mm gutter après l'icône
            text_y = y + 0.2  # micro-baseline align
            if "phone" in name and not a_tel:
                enriched.append({
                    "type": "texte", "contenu": "+237 6XX XXX XXX",
                    "x_mm": text_x, "y_mm": text_y, "w_mm": 35, "h_mm": h,
                    "taille_pt": 7, "couleur": "#FFFFFF", "police": "Helvetica",
                })
                a_tel = True
            elif "mail" in name and not a_email:
                enriched.append({
                    "type": "texte", "contenu": "email@org.cm",
                    "x_mm": text_x, "y_mm": text_y, "w_mm": 40, "h_mm": h,
                    "taille_pt": 7, "couleur": "#FFFFFF", "police": "Helvetica",
                })
                a_email = True
            elif ("world" in name or "globe" in name) and not a_web:
                enriched.append({
                    "type": "texte", "contenu": "www.organisation.cm",
                    "x_mm": text_x, "y_mm": text_y, "w_mm": 40, "h_mm": h,
                    "taille_pt": 7, "couleur": "#FFFFFF", "police": "Helvetica",
                })
                a_web = True
        if not (a_tel and a_email and a_web):
            logger.info(
                f"[FreeformComposer] Post-injection : tel={a_tel} mail={a_email} "
                f"web={a_web} — au moins une non injectée (icône absente du template)"
            )
        return enriched

    template_recto = _enrichir_template_recto(template_recto)
    template_elements = template_recto

    MARGE = 10.0
    GUTTER_H = 10.0
    GUTTER_V = 5.0
    COLS = 2
    ROWS = 4
    CAP = COLS * ROWS  # 8 cartes/A4

    nb_total = len(donnees)
    nb_planches = (nb_total + CAP - 1) // CAP

    def _injecter_donnees(contenu_orig: str, d: dict) -> str:
        """Remplace les contenus de la carte template par les valeurs
        de la donnée réelle d. Heuristique sur le contenu d'origine.
        Supporte clefs FR (nom, prenom, fonction, tel) et EN (last_name,
        first_name, position/job_title, phone) car Haiku alterne."""
        if not contenu_orig:
            return contenu_orig
        c = str(contenu_orig).strip()
        c_low = c.lower()
        # Tel — indicatifs internationaux + mots-clés
        if any(t in c for t in ("+237", "+221", "+225", "+33", "+212", "+27", "+33")) \
                or any(t in c_low for t in ("tel:", "tél:", "phone:", "📞", "6xx", "0xx")):
            tel = d.get("tel") or d.get("telephone") or d.get("phone")
            return str(tel) if tel else c
        # Email — présence de '@'
        if "@" in c:
            mail = d.get("email") or d.get("mail")
            return str(mail) if mail else c
        # Website / URL — www., http, ou TLD courant
        if (
            "www." in c_low or c_low.startswith("http")
            or any(c_low.endswith(tld) for tld in (".cm", ".sn", ".ci", ".fr", ".com", ".org", ".net"))
            or any(tld in c_low for tld in (".cm/", ".sn/", ".com/", ".org/"))
        ):
            site = (d.get("site") or d.get("website") or d.get("url")
                    or d.get("site_web"))
            if site:
                return str(site)
            # Fallback : déduire depuis email (prenom.nom@org.tld → www.org.tld)
            mail = d.get("email") or d.get("mail") or ""
            if "@" in mail:
                domaine = mail.split("@", 1)[1]
                return f"www.{domaine}"
            return c
        # Fonction / titre
        if any(p in c_low for p in (
            "fonction", "titre", "manager", "engineer", "directeur",
            "responsable", "chef", "ingénieur", "assistant", "chargé",
            "consultant", "expert", "analyst", "developer", "designer",
            "writer", "specialist", "executive", "advisor", "rep",
        )):
            f = (d.get("fonction") or d.get("role") or d.get("titre")
                 or d.get("position") or d.get("job_title"))
            return str(f) if f else c
        # Nom + prénom (1 ou 2 mots majuscules)
        nb_mots = len(c.split())
        if nb_mots in (1, 2, 3):
            prenom = d.get("prenom", "") or d.get("first_name", "")
            nom = d.get("nom", "") or d.get("last_name", "")
            if prenom or nom:
                return f"{prenom} {nom}".strip()
        return c

    def _construire_planche(
        planche_idx: int, template_elems: list, est_verso: bool,
    ) -> dict:
        """Compose une planche A4 = grille de jusqu'à 8 cartes (2×4).

        ── ALIGNEMENT DUPLEX (impression recto-verso) ──
        Convention : LONG-EDGE BINDING (= reliure par le bord long de la
        feuille A4 portrait, soit l'axe vertical de 297mm). C'est le mode
        DUPLEX PAR DÉFAUT de 95% des imprimantes bureau.

        En long-edge binding, la feuille tourne autour de l'axe vertical
        après l'impression du recto, AVANT l'impression du verso. Du point
        de vue physique :
          - Recto carte #1 est imprimée en (col=0, row=0)
          - La feuille pivote autour de l'axe vertical médian
          - Le point physique où était col=0 se retrouve maintenant à
            la position col=COLS-1 (mirror horizontal des colonnes)
          - Donc le verso de la carte #1 doit être imprimé en
            (col=COLS-1, row=0) pour que, APRÈS DÉCOUPE, le verso
            soit derrière son propre recto.

        L'axe vertical mirror : col_verso = (COLS-1) - col_recto.
        Les rows ne sont PAS mirrorées (long-edge ≠ short-edge).

        Pour SHORT-EDGE binding (rare), il faudrait inverser les rows
        à la place. Non implémenté car non-standard.
        """
        new_elements: list[dict] = []
        for slot in range(CAP):
            card_idx = planche_idx * CAP + slot
            if card_idx >= nb_total:
                break
            d = donnees[card_idx]
            col = slot % COLS
            row = slot // COLS
            # Verso : mirror horizontal pour alignement duplex
            if est_verso:
                col = (COLS - 1) - col
            x_off = MARGE + col * (card_w_mm + GUTTER_H)
            y_off = MARGE + row * (card_h_mm + GUTTER_V)
            for el in template_elems:
                if not isinstance(el, dict):
                    continue
                new_el = dict(el)
                for k in ("x_mm", "x1_mm", "x2_mm"):
                    if k in new_el and new_el[k] is not None:
                        try:
                            new_el[k] = float(new_el[k]) + x_off
                        except (TypeError, ValueError):
                            pass
                for k in ("y_mm", "y1_mm", "y2_mm"):
                    if k in new_el and new_el[k] is not None:
                        try:
                            new_el[k] = float(new_el[k]) + y_off
                        except (TypeError, ValueError):
                            pass
                if (new_el.get("type") or "").lower() in ("texte", "text"):
                    new_el["contenu"] = _injecter_donnees(
                        new_el.get("contenu", ""), d,
                    )
                elif (new_el.get("type") or "").lower() in ("qr", "qrcode"):
                    prenom = d.get("prenom", "") or d.get("first_name", "")
                    nom = d.get("nom", "") or d.get("last_name", "")
                    fonction = (d.get("fonction") or d.get("position")
                                or d.get("job_title") or "")
                    tel = d.get("tel") or d.get("phone") or ""
                    email = d.get("email") or d.get("mail") or ""
                    new_el["donnees"] = (
                        "BEGIN:VCARD\nVERSION:3.0\n"
                        f"FN:{prenom} {nom}\n"
                        f"TITLE:{fonction}\n"
                        f"TEL:{tel}\nEMAIL:{email}\nEND:VCARD"
                    )
                new_elements.append(new_el)
            # Crop marks autour de la carte
            new_elements.append({
                "type": "crop_marks",
                "x_mm": x_off, "y_mm": y_off,
                "w_mm": card_w_mm, "h_mm": card_h_mm,
                "longueur_mm": 3, "epaisseur_pt": 0.25,
                "couleur": "#000000",
            })
        # Label discret en haut de page (hors zone cartes) pour identifier
        # la planche à l'impression. Indispensable pour ne pas confondre
        # recto/verso après impression et découpe.
        label_text = (
            f"VERSO — planche {planche_idx + 1} (duplex long-edge)"
            if est_verso else
            f"RECTO — planche {planche_idx + 1}"
        )
        new_elements.append({
            "type": "texte",
            "contenu": label_text,
            "x_mm": MARGE, "y_mm": 4,  # tout en haut, hors zone cartes
            "w_mm": 100, "h_mm": 4,
            "taille_pt": 6, "couleur": "#888888", "police": "Helvetica",
            "alignement": "left",
        })
        return {
            "numero": 0,  # sera ré-attribué dans la boucle finale
            "fond_couleur": "#FFFFFF",
            "format_mm": [210, 297],
            "libelle_piece": f"planche_{'verso' if est_verso else 'recto'}_{planche_idx + 1}",
            "elements": new_elements,
        }

    new_pages = []
    # 1er passage : toutes les planches recto
    for planche_idx in range(nb_planches):
        new_pages.append(_construire_planche(planche_idx, template_recto, est_verso=False))
    # 2e passage : toutes les planches verso (si template recto-verso)
    if a_verso:
        for planche_idx in range(nb_planches):
            new_pages.append(_construire_planche(planche_idx, template_verso, est_verso=True))
    # Renuméroter les pages séquentiellement
    for idx, p in enumerate(new_pages):
        p["numero"] = idx + 1

    data["format_mm"] = [210, 297]
    data["pages"] = new_pages
    logger.warning(
        f"[FreeformComposer] Reconstruction grille → {nb_planches} planches A4, "
        f"{nb_total} cartes, {sum(len(p['elements']) for p in new_pages)} éléments"
    )
    return data


async def composer_freeform_layout(
    brief: str,
    profil: Optional[dict] = None,
    medias_descripteurs: Optional[list[dict]] = None,
    brand_kit: Optional[dict] = None,
    descripteur_vertical: Optional[dict] = None,
    pays: str = "CM",
    langue: str = "fr",
) -> dict:
    """Appelle le LLM (Opus → traduit en gpt-4-turbo via LLM_PRIMAIRE=gpt)
    pour composer un JSON de layout. Retourne le dict prêt à passer à
    `rendre_pdf_depuis_json()`.

    En cas d'échec total : retourne un layout minimal (1 page blanche A4
    avec un texte d'erreur) pour ne pas casser le pipeline appelant.
    """
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire

    profil_block = ""
    if profil:
        nom_org = profil.get("nom_organisation") or ""
        metier = profil.get("metier") or ""
        couleur_prim = profil.get("couleur_primaire_hex") or ""
        couleurs_acc = profil.get("couleurs_accents_hex") or []
        profil_block = (
            f"\n## PROFIL UTILISATEUR\n"
            f"- Organisation : {nom_org or '(non précisée)'}\n"
            f"- Métier : {metier or '(non précisé)'}\n"
            f"- Couleur primaire : {couleur_prim or '(libre)'}\n"
            f"- Couleurs accents : {', '.join(couleurs_acc) if couleurs_acc else '(libre)'}\n"
        )

    brand_block = ""
    if brand_kit:
        baseline = brand_kit.get("baseline") or ""
        tov = brand_kit.get("tone_of_voice") or ""
        lex = brand_kit.get("lexique_prefere") or []
        mots_int = brand_kit.get("mots_interdits") or []
        if baseline or tov or lex or mots_int:
            brand_block = (
                f"\n## BRAND KIT VERROUILLÉ (à respecter strictement)\n"
                f"- Baseline : {baseline or '(aucune)'}\n"
                f"- Ton : {tov or '(libre)'}\n"
                f"- Vocabulaire préféré : {', '.join(lex) if lex else '(libre)'}\n"
                f"- Mots interdits : {', '.join(mots_int) if mots_int else '(aucun)'}\n"
            )

    vertical_block = ""
    if descripteur_vertical:
        couleurs_typ = descripteur_vertical.get("couleurs_typiques") or ""
        polices_typ = descripteur_vertical.get("polices_typiques") or ""
        ton = descripteur_vertical.get("ton_recommande") or ""
        vertical_block = (
            f"\n## CONTEXTE MÉTIER ({descripteur_vertical.get('label', '')})\n"
            f"- Couleurs typiques : {couleurs_typ or '(libre)'}\n"
            f"- Polices typiques : {polices_typ or '(libre)'}\n"
            f"- Ton recommandé : {ton or '(libre)'}\n"
        )

    # Catalogue palettes par métier (déduction si profil/brand_kit absents) —
    # appliqué à TOUS les types de visuels (cartes, flyers, brochures, etc.)
    style_catalogue_block = ""
    if not brand_kit and not (profil and profil.get("couleur_primaire_hex")):
        style_catalogue_block = (
            "\n## CATALOGUE DE STYLES PAR MÉTIER (à utiliser si pas de couleur imposée)\n"
            "Adapte la palette et l'esthétique au métier détecté dans le brief :\n"
            "- Finance/banque/assurance : navy/charcoal + or, sobre institutionnel\n"
            "- Santé/médical/pharmacie : blanc + vert sapin ou bleu cyan, propre rassurant\n"
            "- Tech/IT/digital : noir/blanc + cyan/turquoise/violet, géométrique moderne\n"
            "- Restauration/food/café : terracotta/crème ou noir+or, chaleureux gourmand\n"
            "- Juridique/notariat : noir + bordeaux ou navy, classique sérigraphié\n"
            "- Mode/créatif/photo : couleurs vives ou pastels, audacieux asymétrique\n"
            "- Industriel/BTP/manuf : gris/anthracite + orange sécurité, robuste\n"
            "- Éducation/formation : vert sapin + crème, lisible accessible\n"
            "- Conseil/coaching/RH : violet/aubergine + or, premium élégant\n"
            "- Cosmétique/beauté/wellness : rose poudré + or rosé, féminin doux\n"
            "- Immobilier : beige/sable + bleu nuit, élégant rassurant\n"
            "- Transport/logistique : bleu marine + jaune, dynamique\n"
            "- ONG/associatif : couleurs cause-related (vert nature, bleu solidaire…)\n"
            "Si le métier n'est dans aucune de ces catégories, déduis intelligemment\n"
            "à partir du brief et du ton attendu. NE TE LIMITE PAS à navy+jaune.\n"
        )

    medias_block = ""
    if medias_descripteurs:
        # Split par catégorie pour instructions plus précises
        logos = [m for m in medias_descripteurs
                 if "logo" in (m.get("categorie") or "").lower() or m.get("est_logo")]
        bannieres = [m for m in medias_descripteurs
                     if any(k in (m.get("categorie") or "").lower()
                            for k in ("banniere", "banner", "header"))]
        autres_imgs = [m for m in medias_descripteurs
                       if m not in logos and m not in bannieres]
        instr_medias = ""
        if logos:
            instr_medias += (
                f"- **LOGO disponible** : ref_media={logos[0].get('ref')!r}.\n"
                f"  INCLUS-le obligatoirement en élément Image dans le design "
                f"(taille adaptée au format : 8-15mm pour cartes/badges, "
                f"25-40mm pour flyer/brochure, 60mm+ pour affiche).\n"
            )
        if bannieres:
            instr_medias += (
                f"- **BANNIÈRE/HEADER disponible** : "
                f"ref_media={bannieres[0].get('ref')!r}.\n"
                f"  À utiliser comme bandeau haut pleine largeur (avec crop si "
                f"ratio incompatible) ou fond pleine page (mode='cover').\n"
            )
        if autres_imgs:
            instr_medias += (
                f"- Autres médias (photos, illustrations) : "
                f"{[m.get('ref') for m in autres_imgs]}\n"
                f"  À utiliser selon contexte (portrait, témoignage, hero, etc.).\n"
            )
        medias_block = (
            f"\n## MÉDIATHÈQUE DISPONIBLE (à intégrer activement dans le design)\n"
            f"{instr_medias}\n"
            f"Descripteurs complets :\n"
            f"{json.dumps(medias_descripteurs, ensure_ascii=False, indent=2)}\n"
            f"\nFormat élément Image : "
            f"{{\"type\":\"image\",\"ref_media\":\"<ref>\",\"x_mm\":...,\"y_mm\":...,"
            f"\"w_mm\":...,\"h_mm\":...,\"mode\":\"contain|cover\"}}\n"
        )

    # Détection heuristique de densité — un brief mentionnant un N élevé
    # (« 20 cartes », « 50 stickers », « 16 badges ») exige beaucoup de
    # tokens output.
    import re as _re_d
    # Regex GÉNÉRIQUE — détecte N items répétés de N'IMPORTE QUEL type :
    # cartes, badges, étiquettes, marque-places, tickets, fiches, médailles,
    # diplômes, certificats, dossards, vignettes, autocollants, magnets,
    # menus, programmes, faire-parts, sigles, autocollants, étiquettes
    # produit, étiquettes prix, banderoles, oriflammes, posts, etc.
    m_dense = _re_d.search(
        r"\b(\d{1,3})\s*(cartes?|employ[ée]s?|personnes?|items?|exemplaires?|"
        r"stickers?|autocollants?|magnets?|[ée]tiquettes?|vignettes?|"
        r"badges?|cases?|cartons?|marque[- ]?places?|tickets?|billets?|"
        r"fiches?|m[ée]dailles?|dipl[oô]mes?|certificats?|dossards?|"
        r"banderoles?|oriflammes?|posts?|tracts?|invit[ée]s?|participants?|"
        r"visiteurs?|membres?|clients?|produits?|articles?|r[ée]f[ée]rences?|"
        r"plaques?|panneaux?|enseignes?|signal[ée]tiques?)\b",
        (brief or "").lower(),
    )
    nb_detecte = int(m_dense.group(1)) if m_dense else 0
    densite_elevee = nb_detecte >= 10
    logger.warning(
        f"[FreeformComposer] brief={brief[:80]!r} | "
        f"nb_detecte={nb_detecte} | densite_elevee={densite_elevee}"
    )

    # ── Pré-génération des DONNÉES SIMULÉES via Haiku ──────────────────────
    # Séparation génération données / mise en page. Le composer LLM a un
    # mauvais taux d'adhésion à « simule les infos » (observé ~10 %, il
    # insère des placeholders standards). Haiku génère N entrées avec un
    # schéma INFÉRÉ depuis le brief (cartes visite → nom+fonction+tel,
    # badges visiteurs → nom+entreprise, étiquettes produit → nom+volume,
    # marque-places mariage → nom_invite+table, …).
    donnees_block = ""
    trigger_simul = bool(_re_d.search(
        r"\bsimul|\binvent|\bfictif|\bexemple|\bfake|"
        r"\bg[ée]n[èeé]re?\s+(?:les?|des?)\s+(?:infos?|donn[ée]es?|"
        r"noms?|coordonn[ée]es?|champs?|contenus?)",
        (brief or "").lower(),
    ))
    logger.warning(
        f"[FreeformComposer] trigger_simulation={trigger_simul} "
        f"(condition : nb>=2 ET regex simul/invent/fictif/genere les infos)"
    )
    donnees_simulees: list[dict] = []
    if nb_detecte >= 2 and trigger_simul:
        donnees_simulees = await _pre_generer_donnees_simulees(
            brief=brief, nb_items=nb_detecte, profil=profil,
            pays=pays, langue=langue,
        )
        logger.warning(
            f"[FreeformComposer] Pré-gen Haiku → {len(donnees_simulees)} "
            f"entrées simulées (cible {nb_detecte}). "
            f"Aperçu : {str(donnees_simulees[:2])[:200]}"
        )

    # ── PIPELINE 2-PHASES pour densité élevée + données simulées ──────────
    # Au lieu de demander au LLM de composer N cartes (~25k chars JSON,
    # tronqué à 8000 tokens output → fallback page vide), on lui demande
    # juste UNE carte template (~500 tokens, fiable), puis on duplique en
    # grille A4 côté Python (déterministe).
    if densite_elevee and donnees_simulees:
        logger.warning(
            f"[FreeformComposer] Pipeline 2-phases activé : "
            f"LLM compose 1 carte template, Python duplique × {len(donnees_simulees)}"
        )
        template_data = await _composer_carte_template(
            brief=brief, profil=profil, brand_kit=brand_kit,
            descripteur_vertical=descripteur_vertical,
            medias_descripteurs=medias_descripteurs,
            pays=pays, langue=langue,
        )
        if not template_data.get("pages"):
            logger.warning(
                "[FreeformComposer] Template LLM échec → fallback template hardcoded"
            )
            couleur_prim = (profil or {}).get("couleur_primaire_hex") or "#003D82"
            accents = (profil or {}).get("couleurs_accents_hex") or ["#FFB800"]
            template_data = _layout_carte_template_fallback(
                couleur_primaire=couleur_prim,
                couleur_accent=accents[0] if accents else "#FFB800",
            )

        # Reconstruction grille A4 avec injection données
        final_data = _reorganiser_grille_a4(
            data=template_data, donnees=donnees_simulees,
            card_w_mm=85.0, card_h_mm=55.0,
        )
        logger.warning(
            f"[FreeformComposer] Pipeline 2-phases → {len(final_data.get('pages', []))} "
            f"planches A4 finales"
        )
        return final_data
        if donnees_simulees:
            donnees_block = (
                f"\n## DONNÉES SIMULÉES (déjà générées — utilise-les TELLES QUELLES, "
                f"une entrée par carte/badge/item, dans l'ordre fourni)\n"
                f"{json.dumps(donnees_simulees, ensure_ascii=False, indent=1)}\n"
                f"\nIMPORTANT : tu DOIS utiliser CES données EXACTES. Aucune carte "
                f"ne doit afficher « Nom Prénom », « Fonction », « +237 6XX XXX XXX », "
                f"« prenom.nom@... », « email@example.com » — chaque carte affiche "
                f"un nom, prénom, fonction, tél, email RÉELS de la liste ci-dessus.\n"
            )

    # Consigne grille multi-items quand densité élevée — GÉNÉRIQUE.
    # Pour N items destinés à être imprimés puis découpés (cartes, badges,
    # étiquettes, marque-places, médailles, dossards, sigles…), on impose
    # une mise en grille mathématique sur des planches A4/A3 plutôt que
    # N pages séparées au format de l'item (anti-pattern d'impression).
    contrainte_grille = ""
    if densite_elevee:
        contrainte_grille = (
            f"\n## CONTRAINTE TECHNIQUE — IMPÉRATIVE pour {nb_detecte} items\n"
            f"L'utilisateur demande {nb_detecte} exemplaires d'items répétés. "
            f"Tu DOIS les disposer en GRILLE sur des planches A4 (210×297mm) "
            f"ou A3 (297×420mm) selon la taille de chaque item :\n"
            f"  1. Choisis la taille standard de l'item depuis le brief "
            f"(carte de visite 85×55, badge nominatif 85×54 ou 100×70, "
            f"étiquette produit 50×30 à 90×60, marque-place 50×85, "
            f"sticker 50×50, dossard 200×200, médaille 80×80, etc.).\n"
            f"  2. Calcule capacité = floor((largeur_page - 2×marge) / "
            f"(largeur_item + gutter_h)) × floor((hauteur_page - 2×marge) / "
            f"(hauteur_item + gutter_v)). Marges 10mm A4 / 15mm A3, "
            f"gutter 5-10mm.\n"
            f"  3. nb_planches = ceil({nb_detecte} / capacité). Crée "
            f"exactement ce nombre de pages au format A4 ou A3.\n"
            f"  4. Sur CHAQUE planche : dispose la grille avec crop_marks "
            f"autour de chaque trim de découpe.\n"
            f"  5. Si des DONNÉES SIMULÉES sont fournies ci-dessus, utilise-"
            f"les TELLES QUELLES, un objet par item dans l'ordre.\n"
            f"INTERDICTIONS :\n"
            f"  • {nb_detecte} pages séparées au format de l'item (anti-"
            f"pattern impression).\n"
            f"  • 1 page A4 avec 1 item centré (gâchis).\n"
            f"  • Item répété à l'identique avec mêmes données (les items "
            f"doivent porter des données VARIÉES de la liste simulée).\n"
        )

    prompt_user = f"""\
## BRIEF UTILISATEUR
\"\"\"{brief[:4000]}\"\"\"

## CONTEXTE
- Pays : {pays}
- Langue : {langue}
{profil_block}{brand_block}{vertical_block}{style_catalogue_block}{medias_block}{donnees_block}{contrainte_grille}

Compose maintenant le layout PARFAIT pour ce brief. JSON STRICT uniquement,
sans commentaire ni markdown.
"""

    try:
        # Tokens output : 4000 pour visuels simples (1-8 éléments répétés
        # OU page unique). 8000 pour densités élevées (>=10 items répétés).
        #
        # CHOIX DE MODÈLE EN FONCTION DE LA DENSITÉ :
        # - Densité faible : Opus 4.7 (tier-traduit en gpt-4-turbo si
        #   LLM_PRIMAIRE=gpt). gpt-4-turbo cape à 4096 output → OK pour 4000.
        # - Densité élevée (>=10 items répétés, ~150 éléments JSON) :
        #   on prend Sonnet (tier-traduit en gpt-4o) qui supporte 16k
        #   output. Si on gardait CLAUDE_OPUS avec max_tok=8000 ET
        #   LLM_PRIMAIRE=gpt, l'appel atterrirait sur gpt-4-turbo (cap
        #   4096) → erreur 400 ou troncature JSON silencieuse → fallback
        #   page placeholder (cf bug observé sur le pdf 10 cartes).
        if densite_elevee:
            max_tok = 8000
            _modele_compose = ModelePrioritaire.CLAUDE_SONNET   # → gpt-4o (16k output cap)
        else:
            max_tok = 4000
            _modele_compose = ModelePrioritaire.CLAUDE_OPUS     # → gpt-4-turbo (4096) ou Opus 4.7 pur
        logger.warning(
            f"[FreeformComposer] Composer LLM : modele={_modele_compose.value} "
            f"max_tokens={max_tok} (densite_elevee={densite_elevee})"
        )
        rep = await ia_client.appeler(
            prompt=prompt_user,
            systeme=_PROMPT_SYSTEME,
            mode=ModeIA.ANALYSE,
            forcer_modele=_modele_compose,
            json_attendu=True,
            max_tokens_override=max_tok,
            utiliser_cache=False,
        )
        contenu = rep.contenu or "{}"
        logger.warning(
            f"[FreeformComposer] LLM répondu : {len(contenu)} chars, "
            f"aperçu fin : ...{contenu[-200:]!r}"
        )
        try:
            data = json.loads(contenu)
        except json.JSONDecodeError as _jde:
            logger.warning(
                f"[FreeformComposer] JSON invalide ({_jde}) → extraction regex"
            )
            import re as _re
            m = _re.search(r"\{[\s\S]*\}", contenu)
            data = json.loads(m.group()) if m else {}
    except Exception as e:
        logger.warning(f"[FreeformComposer] Echec LLM : {e}")
        data = {}

    # Validation minimale + correction défensive
    if not isinstance(data, dict) or not data.get("pages"):
        logger.warning(
            f"[FreeformComposer] Layout LLM invalide → fallback page vide A4. "
            f"data_keys={list(data.keys()) if isinstance(data, dict) else type(data).__name__}"
        )
        data = _layout_fallback(brief)
    else:
        pages = data.get("pages") or []
        nb_pages = len(pages)
        nb_elements_total = sum(len(p.get("elements") or []) for p in pages if isinstance(p, dict))
        fmt = data.get("format_mm") or [210, 297]
        logger.warning(
            f"[FreeformComposer] Layout OK : {nb_pages} pages, "
            f"{nb_elements_total} éléments total, format={fmt}"
        )
        # ── Post-validation déterministe : si le LLM a produit l'anti-
        # pattern « N pages au format carte = 1 carte/page » alors qu'on
        # a des données simulées disponibles, on RECONSTRUIT en planches
        # A4 × 8 cartes en grille. Indispensable car le LLM (gpt-4o)
        # ignore systématiquement la consigne grille même avec
        # contrainte forte dans le prompt.
        if 'donnees_simulees' in locals() and donnees_simulees:
            data = _reorganiser_grille_a4(
                data=data, donnees=donnees_simulees,
                card_w_mm=85.0, card_h_mm=55.0,
            )

    return data


def _layout_fallback(brief: str) -> dict:
    """Layout minimal de secours quand le LLM échoue totalement."""
    return {
        "titre": "Document",
        "format_mm": [210, 297],
        "bleed_mm": 3,
        "pages": [{
            "numero": 1,
            "fond_couleur": "#FFFFFF",
            "elements": [
                {
                    "type": "texte",
                    "x_mm": 20, "y_mm": 30, "w_mm": 170,
                    "contenu": "Nous n'avons pas pu composer ce visuel automatiquement. "
                                "Précise davantage ton brief ou contacte le support.",
                    "police": "Helvetica",
                    "taille_pt": 12, "couleur": "#444444",
                    "alignement": "center", "interligne": 1.4,
                },
                {
                    "type": "texte",
                    "x_mm": 20, "y_mm": 80, "w_mm": 170,
                    "contenu": f"Brief reçu : « {brief[:400]} »",
                    "police": "Helvetica", "italic": True,
                    "taille_pt": 9, "couleur": "#888888",
                    "alignement": "center", "interligne": 1.3,
                },
            ],
        }],
    }
