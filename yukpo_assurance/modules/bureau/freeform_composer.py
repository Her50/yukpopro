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

═══════════════════════════════════════════════════════════════════════
RECONNAISSANCE DE MARQUE (CRITIQUE — applicable à TOUS visuels)
═══════════════════════════════════════════════════════════════════════
Si le brief mentionne UNE MARQUE (cliente, employeur, organisation,
événement sponsorisé), tu DOIS appliquer SA palette officielle au lieu
de couleurs génériques. Cette règle s'applique à TOUT visuel : carte
de visite, flyer, affiche, faire-part avec logo entreprise, badge,
brochure, banderole sponsor, etc.

DÉMARCHE EN 3 ÉTAPES (à appliquer dans cet ordre) :

  ÉTAPE A — Si marque dans LE CATALOGUE EXPLICITE ci-dessous → applique
            directement ses couleurs officielles.

  ÉTAPE B — Si marque CONNUE MONDIALEMENT mais hors catalogue (ex: Adidas,
            Nike, BMW, Mercedes, IBM, Oracle, Amazon, Netflix, Spotify,
            Tesla, Visa, Mastercard, FedEx, UPS, McDonald's, Starbucks,
            Burger King, IKEA, Zara, H&M, Sephora, L'Oréal, Chanel, LVMH,
            Hermès, Rolex, Boeing, Airbus, Ferrari, etc.) → utilise TA
            CONNAISSANCE pour appliquer les couleurs officielles que tu
            connais. Sonnet 4.6 a des milliers de marques en mémoire :
            mobilise-les.

  ÉTAPE C — Si marque LOCALE / PME / INCONNUE (ex: "Brasserie du Wouri",
            "Pharmacie Mbarga", "Cabinet Conseil Yaoundé", "Restaurant
            Chez Tantine") → déduis la palette par SECTEUR + CONTEXTE :
              • Telecom → bleu/violet vif + accent énergie
              • Banque/finance → bleu marine + or/argent
              • Assurance → bleu/vert/blanc, sérieux
              • Énergie/pétrole → vert + jaune OU rouge + jaune
              • Pharmaceutique → vert tendre + blanc
              • Médical/hôpital → blanc + bleu ciel + vert apaisant
              • Restauration → palette chaude (rouge/orange/jaune/brun)
              • Luxe → noir + or + blanc (haute densité)
              • Mode → palette saison (printemps/été pastels ; auto/hiver foncés)
              • Religieux/culte → violet + or OU bleu + argent OU blanc + brun
              • Funéraire/deuil → gris foncé + violet/bleu nuit + blanc
              • Mariage → palette douce (rose/champagne/or OU teal/blanc)
              • Festif/jeunesse → palette vive multi-couleurs
              • Tech/startup → bleu profond + accent vif (cyan/magenta)
              • ONG/humanitaire → couleurs primaires + blanc, optimiste
              • Sport → couleurs des fédérations / nationales si pertinent

QUELQUES EXEMPLES MAJEURS AFRIQUE + MONDE (non-exhaustif — utilise aussi
ta connaissance LATENTE pour d'autres marques) :

  TÉLÉCOM AFRIQUE :
  • Orange / Orange Cameroun / Orange CI / Orange SN → #FF7900 (orange vif)
    + noir #000000 + blanc. Identité : block orange dominant, typo Helvetica/Open Sans
  • MTN / MTN Cameroun / MTN Nigeria → #FFCC00 (jaune) + bleu #002A5C
  • Camtel → #0066CC (bleu) + jaune #FCB900
  • Moov Africa → #E94E1B (rouge orangé) + bleu #1E3A8A
  • Airtel → #ED1C24 (rouge) + blanc

  BANQUES AFRIQUE :
  • Afriland First Bank → #009639 (vert) + jaune #FCD116
  • Ecobank → #003876 (bleu) + bleu clair #00B5E2
  • UBA → #DA2128 (rouge) + noir
  • Société Générale → #E60028 (rouge) + noir
  • BICEC / BGFI → bleu marine + or
  • SGBC Cameroun → #E60028 + noir

  PÉTROLE / ÉNERGIE :
  • Total / TotalEnergies → #ED1C24 (rouge) + bleu #003D82 + jaune #FCB900
  • Shell → #FBCE07 (jaune) + rouge #DD1D21

  MONDIAL :
  • Coca-Cola → #F40009 (rouge) + blanc
  • Pepsi → #004B93 (bleu) + rouge #E32934
  • Apple → noir/blanc/gris
  • Google → #4285F4 / #EA4335 / #FBBC04 / #34A853
  • Microsoft → #00A4EF #7FBA00 #FFB900 #F25022
  • Samsung → #1428A0 (bleu)
  • Nestlé → #87B1E8 (bleu pâle) + blanc
  • Unilever → #1F36C7 (bleu)

Si la marque n'est pas dans cette liste et n'est pas reconnue, tu DÉDUIS
la palette du SECTEUR (telecom = bleu/violet vif, banque = bleu marine,
énergie = vert/jaune, luxe = noir/or, tech = bleu, médical = vert/blanc).
JAMAIS de palette aléatoire qui ignore l'identité de marque.

═══════════════════════════════════════════════════════════════════════
PRÉVENTION CHEVAUCHEMENTS (CRITIQUE — bug observé en prod)
═══════════════════════════════════════════════════════════════════════
RÈGLES STRICTES de placement pour éviter les chevauchements visuels :

1. ÉLÉMENT FONCTIONNEL (QR code, icône avec sens, contact, logo identité)
   NE DOIT PAS chevaucher un élément DÉCORATIF (ornement, motif de fond,
   cercles olympiques, vague, étoiles, watermark).
   → Réserve une zone CLEAN (rectangle sans décoration) où placer le QR.
   → Si tu veux un motif décoratif (ornement), place-le dans une zone
     DIFFÉRENTE de celle du QR/icône fonctionnelle.

2. Z-INDEX HIÉRARCHIQUE :
   • z_index 0 : fond couleur, dégradés full-page
   • z_index 1 : décorations grandes (filets, ornements, motifs)
   • z_index 2 : texte de fond / accents typographiques
   • z_index 3 : éléments fonctionnels (QR, icônes contact, logo)
   • z_index 4 : texte principal (nom, titre, fonction)
   • z_index 5 : éléments en surimpression intentionnelle (badges, callouts)
   Plus le z_index est HAUT, plus l'élément est AU-DESSUS.

3. AVANT de placer un QR/icône à coordonnées (X,Y,W,H), VÉRIFIE que la
   zone [X..X+W, Y..Y+H] n'intersecte AUCUN autre élément (sauf le fond
   z_index=0). Si conflit, déplace l'élément fonctionnel ou retire la
   décoration de cette zone.

4. PAS DE DUPLICATION : un même contenu (ex: nom de personne) ne doit
   pas apparaître 2 fois sur la même carte (ex: bold gauche + petit en
   haut à droite simultanément). Choisis UNE position et tiens-y.

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


async def _detecter_organisation_dans_brief(brief: str) -> Optional[str]:
    """Extrait le nom de l'organisation depuis le brief utilisateur via
    plusieurs patterns courants. Retourne None si aucun nom trouvé."""
    import re as _re_org
    if not brief:
        return None
    # Patterns explicites — l'utilisateur annonce le nom
    patterns = [
        r"mon\s+(?:organisation|entreprise|soci[ée]t[ée]|compagnie|structure|"
        r"association|ONG|cabinet|agence|boutique)\s+(?:s['']appelle\s+|"
        r"se\s+nomme\s+|est\s+|c['']est\s+)?[«\"']?([A-Z][A-Za-z0-9 &.\-]{1,50}?)[»\"']?"
        r"(?:[\.,;!\n]|$)",
        r"(?:c['']est|c'est|il\s+s['']agit\s+de|pour)\s+[«\"']?"
        r"([A-Z][A-Za-z0-9 &.\-]{1,50}?)[»\"']?\s+(?:cameroun|s[ée]n[ée]gal|"
        r"c[ôo]te\s+d['']ivoire|congo|togo|b[ée]nin|gabon|mali|"
        r"burkina|niger|tchad|maroc|tunisie|alg[ée]rie|france)",
    ]
    for pat in patterns:
        m = _re_org.search(pat, brief, _re_org.IGNORECASE)
        if m:
            nom = m.group(1).strip().strip(",.;:!\"'«»")
            if 2 <= len(nom) <= 60:
                return nom
    # Fallback : token ALL-CAPS isolé de 2-8 lettres (MTN, ORANGE, BIC, BNP, …)
    m = _re_org.search(r"\b([A-Z]{2,8})\b", brief)
    if m:
        token = m.group(1)
        # Filtre les sigles communs non-organisations
        if token not in {"PDF", "QR", "A3", "A4", "A5", "RGB", "CMYK", "URL", "API", "IT", "RH", "HR", "CV"}:
            return token
    return None


async def _enrichir_via_web_search(
    brief: str, nom_organisation: Optional[str], pays: str = "CM",
    user_id: Optional[int] = None,
) -> dict:
    """Recherche web Serper pour enrichir le contexte branding d'une
    organisation : couleurs officielles, URL du logo, slogan/baseline.

    Triggered seulement si user demande explicitement (mots-clés
    'cherche sur internet', 'branding', 'logo officiel', etc.) ET
    qu'un nom d'organisation a été détecté.

    Retourne : { couleurs_detectees, logo_url, slogan, snippets_brand }.
    """
    import re as _re_ws
    if not nom_organisation or not brief:
        return {}
    declenche_ws = bool(_re_ws.search(
        r"(cherche|recherche|trouve|va\s+chercher|search).*"
        r"(internet|web|en\s+ligne|google)"
        r"|branding|charte\s+graphique|couleurs?\s+officielle"
        r"|logo\s+(?:officiel|de\s+l)|identit[ée]\s+visuelle",
        brief.lower(),
    ))
    if not declenche_ws:
        return {}

    try:
        from modules.pro.recherche_web_pro import _serper_search
    except Exception:
        logger.info("[Freeform/WebSearch] Serper indisponible — skip")
        return {}

    requete = (
        f"{nom_organisation} {pays} brand colors logo identity slogan"
        if pays else
        f"{nom_organisation} brand colors logo identity slogan"
    )
    logger.warning(f"[Freeform/WebSearch] Requête : {requete!r}")
    try:
        import asyncio as _aio_ws
        resultats = await _aio_ws.wait_for(
            _serper_search(requete, sites=[], pays_gl=pays, num=8),
            timeout=10.0,
        )
    except _aio_ws.TimeoutError:
        logger.warning("[Freeform/WebSearch] Serper timeout 10s — skip")
        return {}
    except Exception as e_ws:
        logger.warning(f"[Freeform/WebSearch] Serper erreur : {e_ws} — skip")
        return {}

    if not resultats:
        logger.info("[Freeform/WebSearch] Aucun résultat — skip enrichissement")
        return {}

    # Facturation Serper : coût réel ~$0.005/recherche × 600 FCFA/USD × 20
    # marge = ~60 FCFA. Forfait fixe car Serper n'expose pas tokens.
    if user_id is not None:
        try:
            from modules.pro.service_credits import debiter_forfait_fcfa as _serp_bill
            await _serp_bill(
                user_id=int(user_id),
                cout_fcfa=60.0,
                module="recherche_web_branding",
            )
        except Exception as _e_sb:
            logger.warning(f"[Freeform/WebSearch] Facturation KO (non bloquant) : {_e_sb}")

    # Extraction couleurs depuis les snippets
    # Cherche : "yellow and black", "#FFCC00", "yellow & black", "rgb(255,...)"
    couleurs_mots_to_hex = {
        "yellow": "#FFCC00", "jaune": "#FFCC00",
        "black": "#000000", "noir": "#000000",
        "white": "#FFFFFF", "blanc": "#FFFFFF",
        "red": "#E30613", "rouge": "#E30613",
        "blue": "#0033A0", "bleu": "#0033A0",
        "green": "#008C44", "vert": "#008C44",
        "orange": "#FF7900",
        "purple": "#660099", "violet": "#660099",
        "pink": "#E6007E", "rose": "#E6007E",
        "gray": "#888888", "grey": "#888888", "gris": "#888888",
        "navy": "#0A1F44",
        "gold": "#D4AF37", "or": "#D4AF37",
        "silver": "#C0C0C0", "argent": "#C0C0C0",
    }
    couleurs_trouvees: list[str] = []
    snippets_text = ""
    for r in resultats:
        snip = str(r.get("snippet", "")) + " " + str(r.get("title", ""))
        snippets_text += " " + snip
        # Hex direct
        for hex_m in _re_ws.findall(r"#[0-9A-Fa-f]{6}\b", snip):
            if hex_m.upper() not in [c.upper() for c in couleurs_trouvees]:
                couleurs_trouvees.append(hex_m)
        # Mots couleur
        for mot, hex_v in couleurs_mots_to_hex.items():
            if _re_ws.search(rf"\b{mot}\b", snip.lower()) and hex_v not in couleurs_trouvees:
                couleurs_trouvees.append(hex_v)
    couleurs_trouvees = couleurs_trouvees[:4]

    # Slogan : phrase courte avec « tagline » / « slogan » / « baseline »
    slogan = ""
    for r in resultats:
        snip = str(r.get("snippet", ""))
        m_slo = _re_ws.search(
            r"(?:tagline|slogan|baseline|motto)\s*[:\"'«]\s*([^\"'»\.]{5,100})",
            snip, _re_ws.IGNORECASE,
        )
        if m_slo:
            slogan = m_slo.group(1).strip()
            break

    # Logo URL — Serper organic peut contenir un imageUrl. À défaut, on
    # construit une URL Wikipedia logo par défaut si disponible
    logo_url = ""
    for r in resultats:
        if r.get("imageUrl"):
            logo_url = r["imageUrl"]
            break
        if "wikipedia.org" in str(r.get("link", "")):
            # Wikipedia pages have logos. URL fetch left aside for simplicity.
            pass

    out = {
        "couleurs_detectees": couleurs_trouvees,
        "logo_url": logo_url,
        "slogan": slogan,
        "snippets_brand": snippets_text[:1500],
    }
    logger.warning(
        f"[Freeform/WebSearch] Enrichissement OK pour {nom_organisation!r} : "
        f"{len(couleurs_trouvees)} couleurs, logo={'oui' if logo_url else 'non'}, "
        f"slogan={'oui' if slogan else 'non'}"
    )
    return out


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
        # BUG FIX : max_tokens HARDCODÉ 4000 tronquait dès nb_items > 50.
        # Calcul réaliste : header ~200 tokens + chaque item ~80 tokens JSON
        # (5-7 champs nom/prenom/fonction/email/tel × valeurs camerounaises).
        # Pour 100 cartes : 200 + 100×80 = 8200. Pour 200 cartes : 16200.
        # Cap à 32000 (limite raisonnable Haiku/Sonnet pour ce type de JSON).
        max_tok = min(32000, 400 + nb_items * 90)

        # MODÈLE : Sonnet d'office. C'est PAS de l'extraction (où Haiku excelle)
        # mais de la CRÉATION CONTEXTUELLE CULTURELLE — noms régionaux
        # camerounais/sénégalais/maliens authentiques, fonctions structurées
        # par secteur (banque/telecom/admin), variété sans répétition, formats
        # locaux (emails domaine entreprise, téléphones +237/+221/+223…).
        # Haiku produit des listes plates et répétitives même sur 20 items.
        # Surcoût ~3× est négligeable absolu (~$0.01 pour 100 items) vs la
        # qualité critique des données (l'utilisateur imprime 100 cartes
        # avec ces noms → la médiocrité se voit immédiatement).
        modele_simu = ModelePrioritaire.CLAUDE_SONNET
        rep = await ia_client.appeler(
            prompt=prompt,
            mode=ModeIA.REDACTION,
            forcer_modele=modele_simu,
            json_attendu=True,
            max_tokens_override=max_tok,
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
    enrichissement_web: Optional[dict] = None,
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

    # Enrichissement web (Serper) — couleurs/slogan/snippets détectés
    web_hint = ""
    if enrichissement_web:
        slogan = enrichissement_web.get("slogan") or ""
        snippets = enrichissement_web.get("snippets_brand") or ""
        web_hint = (
            f"\n## RECHERCHE WEB BRANDING ({nom_org or 'organisation'})\n"
            f"Données collectées via Google sur l'identité visuelle de l'organisation :\n"
        )
        if slogan:
            web_hint += f"- Slogan/baseline officiel : « {slogan} »\n  Utilise-le tel-quel au verso.\n"
        if snippets:
            web_hint += (
                f"- Snippets web (extraits) :\n{snippets[:800]}\n"
                f"  Inspire-toi du ton et des éléments graphiques évoqués.\n"
            )
        web_hint += "Reste fidèle à l'identité de la marque évoquée.\n"

    prompt = f"""\
Compose UNE SEULE carte de visite professionnelle au format {card_w_mm}×{card_h_mm}mm.
Tu produis DEUX pages : page 1 = RECTO, page 2 = VERSO de cette même carte
(impression recto-verso standard duplex).

Brief utilisateur : « {brief[:400] if brief else ''} »
{nom_org_hint}{metier_hint}Pays : {pays} / Langue : {langue}
{bk_palette_hint}{vertical_hint}{web_hint}{media_hint}
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
            forcer_modele=ModelePrioritaire.CLAUDE_OPUS,  # → gpt-4.1 (32k output, JSON dense recto+verso)
            json_attendu=True,
            max_tokens_override=4000,  # bumpé 2500→4000 pour recto+verso enrichi
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

    # ── Calcul nb_pages_recommande selon densité contenu ─────────────────
    # Heuristique : analyse longueur brief + nb photos + nb sections
    # explicitement demandées → recommandation au LLM (qui peut ajuster).
    # Évite que le LLM produise 4 pages alors que le contenu mérite 12.
    nb_photos = len(medias_descripteurs or [])
    brief_long = len(brief or "")
    # Compte les sections enumerées dans le brief (mots reliés par 'et'/
    # virgules après un verbe générer)
    import re as _re_pg
    sections_demandees = []
    _m_sections = _re_pg.search(
        r"(?:tu\s+vas\s+(?:simuler|cr[ée]er)|inclu[se]?|"
        r"avec|contenant|comprenant|qui\s+contienne?)\s+([^.]{20,300})",
        (brief or "").lower(),
    )
    if _m_sections:
        # split par virgule/et/puis pour avoir une estim grossière du nb sections
        bloc = _m_sections.group(1)
        sections_demandees = [
            s.strip() for s in _re_pg.split(r",|\bet\b|\bpuis\b|\bavec\b", bloc)
            if 3 <= len(s.strip()) <= 60
        ]
    nb_sections = len(sections_demandees)
    # Formule empirique pages recommandées (livret cérémonie A5) :
    pages_brief = max(1, brief_long // 200)       # 1 page par 200 chars brief
    pages_photos = (nb_photos // 4) * 2 + (1 if nb_photos % 4 else 0)  # 4 photos/page Souvenirs
    pages_sections = max(0, nb_sections - 2)      # 2 sections fit page de garde + sommaire
    pages_estimees = 4 + pages_brief + pages_photos + pages_sections  # 4 = base couverture+intro+dos+remerciements
    # Arrondir au multiple de 4 le plus proche (livret saddle-stitched)
    pages_recommandees = ((pages_estimees + 3) // 4) * 4
    pages_recommandees = max(4, min(pages_recommandees, 24))  # garde-fous [4, 24]
    logger.warning(
        f"[FreeformComposer] Recommandation pages : brief={brief_long} chars, "
        f"photos={nb_photos}, sections_demandees={nb_sections} "
        f"→ {pages_recommandees} pages recommandées"
    )

    # ── Enrichissement web (Serper) AVANT les blocks ─────────────────────
    # Doit s'exécuter d'abord pour que les couleurs détectées soient
    # injectées dans `profil` avant la construction de profil_block.
    # IMPORTANT : init avant tout `if` pour éviter UnboundLocalError côté
    # web_search_block plus bas (Python scope analysis lit toute la fonction).
    nom_org_detecte = await _detecter_organisation_dans_brief(brief)
    enrichissement_web: dict = {}
    if nom_org_detecte:
        enrichissement_web = await _enrichir_via_web_search(
            brief=brief, nom_organisation=nom_org_detecte, pays=pays,
        )
    if enrichissement_web:
        couleurs_web = enrichissement_web.get("couleurs_detectees") or []
        if couleurs_web:
            profil = dict(profil or {})
            if not profil.get("couleur_primaire_hex"):
                profil["couleur_primaire_hex"] = couleurs_web[0]
            if not profil.get("couleurs_accents_hex") and len(couleurs_web) >= 2:
                profil["couleurs_accents_hex"] = couleurs_web[1:]
            if nom_org_detecte and not profil.get("nom_organisation"):
                profil["nom_organisation"] = nom_org_detecte
            logger.warning(
                f"[Freeform/WebSearch] Profil enrichi : "
                f"primaire={profil.get('couleur_primaire_hex')} "
                f"accents={profil.get('couleurs_accents_hex')}"
            )

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

    # Enrichissement web (Serper) — brand/slogan/snippets si web search activé
    web_search_block = ""
    if enrichissement_web:
        slo = enrichissement_web.get("slogan") or ""
        sni = enrichissement_web.get("snippets_brand") or ""
        cols = enrichissement_web.get("couleurs_detectees") or []
        web_search_block = (
            f"\n## RECHERCHE WEB BRANDING ({nom_org_detecte or 'organisation'})\n"
            f"Données identité visuelle officielle collectées sur Google :\n"
        )
        if cols:
            web_search_block += f"- Couleurs détectées (déjà injectées dans profil) : {cols}\n"
        if slo:
            web_search_block += f"- Slogan/baseline : « {slo} » (à utiliser tel-quel si pertinent)\n"
        if sni:
            web_search_block += (
                f"- Extraits snippets web (inspire-toi du ton) :\n{sni[:600]}\n"
            )
        web_search_block += (
            "Respecte l'identité de la marque détectée. Si un logo officiel\n"
            "n'a pas été uploadé en média, propose à l'utilisateur de le faire\n"
            "via un Texte discret au verso : « Logo officiel à insérer ».\n"
        )

    # ── Connaissance LIVRET / FAIRE-PART / CÉRÉMONIE (toujours fournie) ────
    # Pas de regex de détection. Le LLM lit le brief, identifie lui-même
    # le registre approprié dans le catalogue ci-dessous, et applique les
    # règles correspondantes. Si aucun registre ne correspond exactement,
    # le LLM compose intelligemment à partir des principes communs (densité,
    # iconographie pertinente, format livret).
    contexte_block = (
        "\n## ⚠️ DÉTECTION CONTEXTE PERSONNEL vs CORPORATE (CRITIQUE)\n"
        "Avant d'appliquer toute palette/branding, identifie si le document\n"
        "est :\n"
        "(A) **Personnel / Familial / Privé** : le brief contient « mon papa »,\n"
        "    « ma maman », « mon mari », « ma femme », « mon frère », « ma\n"
        "    sœur », « mon fils », « ma fille », « mon ami », « notre famille »,\n"
        "    « les familles X et Y », etc. Document à usage FAMILIAL/PRIVÉ.\n"
        "    → IGNORE complètement profil/brand_kit (couleurs corporate de\n"
        "    l'organisation NE S'APPLIQUENT PAS à un document familial).\n"
        "    Applique STRICTEMENT la palette appropriée au registre détecté\n"
        "    (deuil = navy+or+ivoire, mariage = crème+or rosé, naissance =\n"
        "    pastels…). Ne pas faire un faire-part de décès aux couleurs\n"
        "    vert+jaune de la société de l'utilisateur — c'est ABSURDE.\n"
        "\n"
        "(B) **Corporate / Institutionnel** : le brief mentionne explicitement\n"
        "    une organisation ou émet le document AU NOM d'une organisation\n"
        "    (« notre entreprise X organise », « la société X annonce le\n"
        "    décès de son fondateur Y », « invitation officielle de\n"
        "    l'association Z »). Là le brand_kit/profil prime — couleurs\n"
        "    organisation appropriées.\n"
        "\n"
        "Dans le doute (brief ambigu), va sur (A) personnel : moins risqué\n"
        "qu'un faire-part familial avec mauvaises couleurs corporate.\n"
        "\n"
        "## 📖 CONNAISSANCE LIVRET / FAIRE-PART / CÉRÉMONIE\n"
        "Si le brief décrit un FAIRE-PART, LIVRET, PROGRAMME, INVITATION ou\n"
        "tout document de cérémonie/événement, tu identifies toi-même le\n"
        "REGISTRE émotionnel approprié à partir du brief et tu appliques les\n"
        "principes ci-dessous. Tu n'es PAS limité à ces 6 registres — si le\n"
        "brief décrit une cérémonie différente (anniversaire entreprise,\n"
        "rentrée scolaire solennelle, intronisation chefferie, soirée gala…),\n"
        "compose par analogie en respectant les PRINCIPES COMMUNS.\n"
        "\n"
        "### Catalogue de registres connus (illustratif, pas exhaustif)\n"
        "\n"
        "**DEUIL / FUNÉRAILLE** (décès, obsèques, In Memoriam, hommage défunt,\n"
        "veillée funéraire, requiem, condoléances, cimetière)\n"
        "  - Ton : respectueux, digne, sobre, recueilli\n"
        "  - **CHOISIS UNE PALETTE PARMI 5 selon contexte/culture** (pas la\n"
        "    même pour TOUS les faire-parts — variété entre familles) :\n"
        "    a) Classique européen : navy #1A2742 + or #B8860B sur ivoire #FBF7F0\n"
        "    b) Africain traditionnel : noir #000000 + ocre #8B4513 sur blanc\n"
        "       cassé #F5F5DC (brief mentionne village/Cameroun/terroir)\n"
        "    c) Chrétien liturgique : violet #4B0082 + or #D4AF37 sur blanc\n"
        "       (forte connotation messe/religieuse)\n"
        "    d) Sombre épuré moderne : charcoal #2C2C2C + argent #9CA3AF sur\n"
        "       blanc #FFFFFF (style minimaliste contemporain)\n"
        "    e) Bordeaux digne : bordeaux #722F37 + or sombre #B8860B sur\n"
        "       ivoire #FBF7F0 (élégance classique)\n"
        "  - INTERDIT couleurs flashy (jaune vif, fuchsia, vert vif, cyan,\n"
        "    orange, rose flashy) — toujours inapproprié.\n"
        "  - **CONTRASTE LISIBILITÉ ABSOLU (CRITIQUE)** :\n"
        "    Tout texte courant (corps, citations italic, listes, légendes)\n"
        "    sur fond foncé (navy, noir, charcoal, violet, bordeaux) DOIT\n"
        "    être en BLANC #FFFFFF ou IVOIRE #FBF7F0. JAMAIS en or/argent.\n"
        "    Le or/argent ne sert QUE pour : grands titres (≥20pt), filets,\n"
        "    icônes, ornements. Une citation italic 11pt en or sombre sur\n"
        "    fond navy = ILLISIBLE — interdit.\n"
        "  - Icônes : croix (chrétien), colombe (paix), lys/rose blanche,\n"
        "    cierge, croissant (musulman). 2-4 par page.\n"
        "  - Citations : versets bibliques, coraniques, poèmes de deuil.\n"
        "    Couleur = blanc ou ivoire (contraste).\n"
        "\n"
        "**MARIAGE / FIANÇAILLES** (wedding, noces, union, dot, cérémonie\n"
        "nuptiale, mariage coutumier)\n"
        "  - Ton : élégant, raffiné, joyeux, célébration\n"
        "  - Palette : crème #F5E6D3 / rose poudré #E8B4B8 / marine #1A3A5C\n"
        "    + or rosé #B76E79 / champagne #F7E7CE / bordeaux. Style :\n"
        "    bohème chic, classique, moderne ou traditionnel africain selon brief\n"
        "  - Icônes : alliances, cœur (discret, pas spammé), fleur (rose/\n"
        "    pivoine/orchidée), branche feuille (bohème), étoiles\n"
        "  - Citations : poèmes d'amour, versets mariage, citations d'auteurs\n"
        "\n"
        "**RELIGIEUX ENFANT** (baptême, première communion, confirmation)\n"
        "  - Ton : doux, lumineux, spirituel, innocence\n"
        "  - Palette : bleu ciel #A4C8E1 / blanc / rose poudré #F5C6CB + or\n"
        "    sobre #D4AF37 / argent. Fond blanc/ivoire/pastel doux\n"
        "  - Icônes : croix sobre, colombe (Saint-Esprit), étoile/lumière,\n"
        "    eau/coquille baptismale\n"
        "  - Citations : versets bibliques baptême/communion\n"
        "\n"
        "**NAISSANCE / BABY SHOWER** (annonce bébé, gender reveal, fête prénatale)\n"
        "  - Ton : tendre, joyeux, lumineux, bienvenue\n"
        "  - Palette : pastels (bleu poudré #B6D6E8 / rose poudré #F5C6CB /\n"
        "    jaune doux #FFF4C2 / vert eau #C8E6C9) + doré doux ou argent\n"
        "  - Icônes : ourson, étoile, empreinte de pied, nuage doux\n"
        "  - Citations : poèmes/citations naissance, vœux\n"
        "\n"
        "**ANNIVERSAIRE / JUBILÉ** (X ans, noces d'or, noces de diamant)\n"
        "  - Ton : festif, célébration, joyeux. Adapté à l'âge (jeune=vif\n"
        "    coloré ; sage=or/marine sobre)\n"
        "  - Palette : libre selon contexte. Jubilé d'or = or+marine.\n"
        "    Noces de diamant = argent+blanc.\n"
        "  - Icônes : bougie, sparkle, ballon, cadeau\n"
        "  - Citations : vœux, anecdotes, hommages affectueux\n"
        "\n"
        "**CÉRÉMONIE GÉNÉRIQUE** (autres : intronisation, gala, remise prix,\n"
        "rentrée scolaire, fête associative, journée portes ouvertes)\n"
        "  - Adapte palette + iconographie au ton détecté dans le brief\n"
        "  - Si profil/brand_kit fourni, prioritaire sur les suggestions ci-dessus\n"
        "\n"
        "### PRINCIPES TRANSVERSES (s'appliquent à TOUS les registres)\n"
        "\n"
        "**1. Densité visuelle pro** — CRITIQUE\n"
        "Chaque page DOIT être RICHE — refuse les pages '3 lignes flottant\n"
        "dans le vide'. Cible : **10-18 éléments par page** (fond, titre,\n"
        "filets ornement, corps texte, citations, icônes décoratives,\n"
        "ornements de coins, cadres subtils). Remplir 75%+ de la page utile.\n"
        "Si contenu brief manque, INVENTE sections plausibles (mot du célébrant,\n"
        "plan d'accès, remerciements, citations spirituelles) plutôt que laisser\n"
        "page vide.\n"
        "\n"
        "**2. Typographie élégante**\n"
        "- Titre principal : Bold 22-32pt selon importance, peut être espacé\n"
        "- Sous-titres : Bold 12-16pt avec filet de séparation\n"
        "- Corps : Regular 10pt, interligne aéré 1.4-1.6\n"
        "- Citations : italic 10-12pt centré, encadré subtil\n"
        "\n"
        "**3. Précision factuelle (anti-hallucination)**\n"
        "Si le brief dit « décédé le X », « marié le X », X est la date de\n"
        "l'événement, PAS une date de naissance. NE PAS extrapoler une date\n"
        "de naissance depuis « retraite depuis 7 ans » ou autres indices —\n"
        "c'est de la falsification de données sensibles. Cherche « né le »\n"
        "EXPLICITEMENT. Si absent, placeholder « [Date de naissance] » entre\n"
        "crochets. Idem pour témoignages demandés mais non fournis : créer\n"
        "« [Témoignage à compléter par la famille] » plutôt qu'inventer des\n"
        "personnes ou paroles inexistantes.\n"
        "\n"
        "**4. Médias uploadés — intégration impérative**\n"
        "Si des photos sont fournies (medias_descripteurs ci-dessous), tu DOIS\n"
        "les utiliser :\n"
        "- Portrait principal : couverture page 1, portrait 45×60mm ou rond\n"
        "  50×50mm, cadre subtil or/argent\n"
        "- Photos secondaires : galerie page « Souvenirs » 3-6 photos grille\n"
        "  avec légendes italic\n"
        "- Si aucune photo : Rectangle placeholder #EFEFEF, contour fin,\n"
        "  légende « Portrait » centrée\n"
        "\n"
        "**5. Standards d'impression livret**\n"
        "- Format physique : A5 (148×210mm) par défaut pour livret cérémonie.\n"
        "  Alternatives selon brief : A6 (105×148) format poche, A4\n"
        "  (210×297) programme étendu, carré 14×14 ou 21×21 haut de gamme,\n"
        "  DL 99×210 faire-part long.\n"
        "- Nombre de pages MULTIPLE DE 4 (livret agrafé) : 4, 8, 12, 16, 24.\n"
        "  Si brief demande 5 ou 6 feuillets, arrondir à 8 pages (couverture\n"
        "  + 6 contenu + dos) — un feuillet = 2 pages recto-verso.\n"
        "- Bleed 3mm obligatoire sur fonds plein bord.\n"
        "- Marges intérieures larges 15-18mm (reliure agrafée), extérieures\n"
        "  10-12mm. Pagination discrète bas de page (sauf couverture/dos).\n"
        "\n"
        "**6. Structures-types par taille de livret** (adapter au brief)\n"
        "- 4 pages : Couverture + Programme + Texte principal + Remerciements/Dos\n"
        "- 8 pages : Couverture + Intro/citation + Parcours/Biographie +\n"
        "  Programme double + Familles/Proches + Témoignages/Souvenirs +\n"
        "  Remerciements/Dos\n"
        "- 12+ pages : ajoute Souvenirs photos étendus, Cantiques/Chants,\n"
        "  Plan d'accès, Hommages étendus, Citations spirituelles, Album photo\n"
        "Dévier de ces suggestions est OK si le brief justifie une autre\n"
        "structure — reste cohérent et pro.\n"
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
    # (l'enrichissement web Serper est désormais exécuté tout en haut
    # de la fonction, avant la construction des blocks — voir code)

    import re as _re_d
    # Regex GÉNÉRIQUE — détecte N items répétés.
    # Items "personnes" (employés, membres, visiteurs, invités) → on infère
    # automatiquement la nécessité de données simulées. Items "objets"
    # (cartes, badges, étiquettes) → on peut avoir besoin de mots-clés.
    REGEX_ITEMS_PERSONNES = (
        r"employ[ée]s?|personnes?|membres?|visiteurs?|invit[ée]s?|"
        r"participants?|clients?|salari[ée]s?|collaborateurs?|"
        r"[ée]quipiers?|joueurs?|agents?|prestataires?|enseignants?|"
        r"[ée]l[èe]ves?|[ée]tudiants?"
    )
    REGEX_ITEMS_OBJETS = (
        r"cartes?|items?|exemplaires?|stickers?|autocollants?|magnets?|"
        r"[ée]tiquettes?|vignettes?|badges?|cases?|cartons?|"
        r"marque[- ]?places?|tickets?|billets?|fiches?|m[ée]dailles?|"
        r"dipl[oô]mes?|certificats?|dossards?|banderoles?|oriflammes?|"
        r"posts?|tracts?|produits?|articles?|r[ée]f[ée]rences?|"
        r"plaques?|panneaux?|enseignes?|signal[ée]tiques?"
    )
    REGEX_ITEMS = f"({REGEX_ITEMS_PERSONNES}|{REGEX_ITEMS_OBJETS})"
    # findall TOUTES les occurrences pour disambiguer "8 cartes pour 20
    # employés" : on prend le MAX entre objets (cartes) et personnes
    # (employés). Si personnes > objets, c'est le compte réel de cartes
    # à produire (8 cartes par page = layout, 20 personnes = quantité).
    all_matches = _re_d.findall(
        r"\b(\d{1,3})\s*(" + REGEX_ITEMS + r")\b",
        (brief or "").lower(),
    )
    nb_personnes_max = 0
    nb_objets_max = 0
    a_items_personnes = False
    for nb_str, kind, _ in all_matches:
        try:
            nb = int(nb_str)
        except ValueError:
            continue
        if _re_d.fullmatch(REGEX_ITEMS_PERSONNES, kind):
            nb_personnes_max = max(nb_personnes_max, nb)
            a_items_personnes = True
        else:
            nb_objets_max = max(nb_objets_max, nb)
    # La quantité à produire = max(personnes, objets). Pour "8 cartes pour
    # 20 employés" → 20 cartes. Pour "8 cartes" → 8 cartes.
    nb_detecte = max(nb_personnes_max, nb_objets_max)
    densite_elevee = nb_detecte >= 8  # 8 cartes = 1 planche A4 pleine
    logger.warning(
        f"[FreeformComposer] brief={brief[:80]!r} | "
        f"nb_personnes_max={nb_personnes_max} nb_objets_max={nb_objets_max} | "
        f"nb_detecte={nb_detecte} densite_elevee={densite_elevee} "
        f"a_items_personnes={a_items_personnes}"
    )

    # ── Pré-génération des DONNÉES SIMULÉES via Haiku ──────────────────────
    # Trigger AUTOMATIQUE si items sont des PERSONNES (employés, membres,
    # invités, etc.) : c'est impossible d'écrire 20 noms+tel+email dans
    # le chat, donc évidemment l'utilisateur attend que l'app simule.
    # Sinon, déclenchement explicite via mots-clés.
    donnees_block = ""
    trigger_simul_explicite = bool(_re_d.search(
        r"\bsimul|\binvent|\bfictif|\bexemple|\bfake|al[ée]a"
        r"|\bg[ée]n[èeé]re?\s+(?:les?|des?)?\s*(?:infos?|donn[ée]es?|"
        r"informations?|noms?|coordonn[ée]es?|champs?|contenus?|"
        r"valeurs?|exemples?)\b",
        (brief or "").lower(),
    ))
    # Auto-trigger : items personnes >= 2 → on sait qu'il faut simuler
    trigger_simul_auto = a_items_personnes and nb_personnes_max >= 2
    trigger_simul = trigger_simul_explicite or trigger_simul_auto
    logger.warning(
        f"[FreeformComposer] trigger_simul={trigger_simul} "
        f"(explicite={trigger_simul_explicite}, auto={trigger_simul_auto})"
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
            enrichissement_web=enrichissement_web,
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
{profil_block}{brand_block}{vertical_block}{web_search_block}{contexte_block}{style_catalogue_block}{medias_block}{donnees_block}{contrainte_grille}

## RÈGLES PLACEMENT ÉLÉMENTS (anti-collision)

CHAQUE élément a `x_mm, y_mm, w_mm, h_mm`. Les icônes (Icone) sont
positionnées à `(x, y)` avec taille `(w, h)`. Pour ÉVITER les collisions :

1. **Définis une grille mentale claire** : la page a une zone titre
   en haut (10-25mm depuis y=10), un corps central (y=25 à y=H-25),
   un pied (y=H-25 à H). NE PLACE PAS d'icône sur la zone titre/corps
   texte sauf intention.

2. **Marge minimale 5mm** entre un Texte et une Icone. Si une icône
   est à `(x=10, y=180, w=8, h=8)`, le bloc Texte le plus proche en
   x DOIT commencer à `x >= 23` (5mm gap) ou être à `y < 175` ou
   `y > 195`.

3. **Icônes décoratives** (croix, fleurs, ornements) :
   - Placer dans les COINS de page (top-left, top-right, bottom-left,
     bottom-right) entre `5mm` et `25mm` du bord
   - Taille modeste : 4-8mm
   - Couleur subtile (accent OU primaire 50% opacité)
   - JAMAIS au milieu de la zone texte
   - Si placement à côté d'un Texte, vérifie que le Texte commence
     APRÈS la fin de l'icône en x : `texte.x >= icone.x + icone.w + 4`

4. **Mauvais exemples (à NE PAS faire)** :
   - Icone à `(50, 50, 5, 5)` + Texte démarrant à `(48, 50, ...)`
     → icone se superpose au texte « am » de « Famille »
   - Croix au milieu d'une page de Programme (centre = espace texte)
   - 3 icônes en bas-gauche superposées les unes sur les autres

5. **Bons exemples** :
   - Croix `(95, 8, 6, 6)` en haut-centre, titre Texte `(20, 20, 170,
     12)` en dessous → pas de collision
   - 4 ornements aux 4 coins, chacun 5-10mm du bord
   - Filet horizontal `(20, 18, 170, 0.5)` séparant titre et corps

## CONTRAINTES IMPRESSION LIVRET RECTO-VERSO (CRITIQUE)

### Imposition saddle-stitched (gérée AUTOMATIQUEMENT par le backend)

Tu composes les pages dans l'ORDRE LOGIQUE de lecture (page 1 = couverture,
page 2 = 1ère intérieure, …, dernière = dos). Le backend applique
ensuite automatiquement l'imposition saddle-stitched : il réordonne et
groupe les pages par paires sur des feuilles physiques A4 paysage pour
permettre l'impression duplex puis pli au centre + agrafage.

Exemple pour 8 pages logiques :
  Feuille 1 recto imprimée : [page 8] | [page 1]
  Feuille 1 verso imprimée : [page 2] | [page 7]
  Feuille 2 recto imprimée : [page 6] | [page 3]
  Feuille 2 verso imprimée : [page 4] | [page 5]
Après impression duplex + pli + agrafage, le livret se lit dans
l'ordre logique 1, 2, 3, … 8.

**Tu ne dois PAS te soucier de l'imposition** — backend s'en occupe.
Compose simplement les pages dans l'ordre de lecture cohérent.

### Logique de lecture après pli/agrafage

- Page 1 = COUVERTURE recto (impactante, isolée, photo+titre)
- Page 2 = première page intérieure (à gauche quand on ouvre)
- Page 3 = page intérieure droite (face à face avec page 2)
- Page 4 = page intérieure gauche (suivante)
- Page 5 = page intérieure droite (face à face avec page 4)
- … et ainsi de suite
- Dernière page = DOS extérieur (citation isolée, sobre, court)

### Continuité face à face

Quand l'utilisateur ouvre le livret, il voit DEUX pages côte-à-côte :
(2,3), (4,5), (6,7). Pour une expérience pro, conçois ces paires
comme un TOUT visuel cohérent :
- Page 2 = liste des familles annonceuses
  Page 3 = parcours de vie (continue logique)
- Page 4 = programme obsèques (gauche)
  Page 5 = témoignages (droite, complément naturel)
- Page 6 = souvenirs photos
  Page 7 = remerciements
Évite de COUPER un contenu au milieu d'une paire (ex : programme
sur page 4 ET 5 = casse la cohérence si user ouvre à plat).

### Reliure asymétrique

Si le document est un livret (≥4 pages), respecte les conventions
imprimeur pour reliure agrafée :

1. **Format physique** : préfère **A5 (148×210mm)** par défaut pour
   livret cérémonie. Sinon : A4 (210×297) pour programme étendu,
   carré 21×21 haut de gamme.
2. **Pages multiples de 4** (livret agrafé). Si user demande X
   feuillets, génère 2X pages (un feuillet = recto+verso).
3. **Marges asymétriques pour reliure** :
   - Marge intérieure (côté reliure) : 15-18mm
   - Marge extérieure : 10-12mm
   - Marges page paire : intérieure à droite, extérieure à gauche
   - Marges page impaire : intérieure à gauche, extérieure à droite
   - Ceci évite que le texte disparaisse dans le pli central
4. **Bleed 3mm** sur les rectangles de fond plein-bord (`x=-3, y=-3,
   w=W+6, h=H+6` pour les fonds couleur primaire).
5. **Pagination discrète** bas de page (sauf couverture + dos), 8pt
   gris sobre.
6. **Page couverture (1)** : design impactant, titre + dates clés +
   ornement principal.
7. **Page dos (dernière)** : sobre, citation + ornement + RIEN d'autre.
   Pas de marge intérieure (c'est l'extérieur arrière du livret).

## DIMENSIONNEMENT DYNAMIQUE DU DOCUMENT (CRITIQUE)

Le backend a pré-calculé une **recommandation** : **{pages_recommandees} pages** selon
la densité de contenu (longueur brief, nombre de photos uploadées,
sections demandées). C'est un MINIMUM viable, pas un plafond.

Tu PEUX ajuster :
- Plus que recommandé : si le contenu RÉEL exige plus de respiration
  (chaque section mérite sa page, double-page panoramique, galerie
  photos étendue, etc.)
- Moins que recommandé : SI ET SEULEMENT SI le brief est court et
  bien servi par moins (rare — la plupart des briefs sous-évaluent
  leur besoin)
- TOUJOURS multiple de 4 pour livret saddle-stitched

Critères pour AJOUTER une page :
- Plus de 3 photos uploadées → page Souvenirs dédiée
- Plus de 4 témoignages → 2 pages Témoignages
- Brief explicite « parcours académique/pro/social/spirituel » =
  4 sous-sections → 2-4 pages dédiées
- Citations bibliques/poèmes substantiels → page Mot d'introduction

## NOUVEAU TYPE D'ÉLÉMENT : `texte_fluide` (text-wrap polygone)

En plus de `texte` (boîte rectangulaire fixe), tu disposes d'un type
`texte_fluide` qui FAIT S'ÉCOULER le texte AUTOUR d'obstacles (images,
formes). Le texte enveloppe l'obstacle comme dans un magazine pro.

Schéma JSON :
```json
{{
  "type": "texte_fluide",
  "contenu": "Texte long qui va s'écouler...",
  "x_mm": 10, "y_mm": 30, "w_mm": 190, "h_mm": 150,
  "taille_pt": 10, "couleur": "#000000", "police": "Helvetica",
  "interligne": 1.4, "alignement": "justify",
  "obstacles": [
    {{
      "type": "rectangle",
      "x_mm": 130, "y_mm": 40, "w_mm": 60, "h_mm": 80,
      "padding_mm": 3
    }},
    {{
      "type": "cercle",
      "cx_mm": 50, "cy_mm": 100, "r_mm": 25, "padding_mm": 3
    }},
    {{
      "type": "polygone",
      "points_mm": [[10,200], [50,180], [90,210], [30,230]],
      "padding_mm": 2
    }}
  ]
}}
```

Le moteur, ligne par ligne, calcule les intervalles X libres autour
des obstacles et fait couler le texte dans ces intervalles. Si une
ligne est entièrement obstruée (image grande au centre par ex), le
texte saute à la ligne suivante.

**Quand utiliser `texte_fluide` vs `texte` standard** :
- `texte_fluide` : article magazine avec image insérée, témoignage
  long enveloppant une photo portrait, biographie + photo de jeunesse,
  texte qui contourne un logo ou ornement décoratif
- `texte` standard : titres, sous-titres, citations courtes en
  encadré, listes, signatures, mentions légales

**Pattern A reconçu avec texte_fluide** :
Au lieu de Texte rectangle à droite + Texte sous, utilise :
```json
{{
  "type": "image", "ref_media": "compte:abc",
  "x_mm": 10, "y_mm": 30, "w_mm": 60, "h_mm": 80, "mode": "cover"
}},
{{
  "type": "texte_fluide",
  "contenu": "Long paragraphe de témoignage qui commence à droite\nde la photo, descend, puis continue en pleine largeur sous la photo automatiquement...",
  "x_mm": 10, "y_mm": 30, "w_mm": 190, "h_mm": 150,
  "taille_pt": 10, "alignement": "justify",
  "obstacles": [
    {{"type": "rectangle", "x_mm": 10, "y_mm": 30, "w_mm": 60, "h_mm": 80, "padding_mm": 4}}
  ]
}}
```
Résultat : texte naturellement enveloppant la photo, comme dans un
magazine. Plus jamais de blocs texte rectangulaires juxtaposés à des
photos — du vrai design éditorial.

## MISE EN PAGE PHOTO + TEXTE (text-around-image)

Quand une page contient PHOTO + TEXTE, ne place PAS simplement la
photo en haut et le texte en bas en blocs séparés (mise en page de
journal d'école). Compose en COLONNES qui simulent un text-wrap pro :

### Pattern A : Photo gauche, texte enrobant à droite (le plus courant)
```
┌─────────────┐
│             │  Titre section bold
│   PHOTO     │  ────────────────────
│  60×80mm    │  Bloc texte 1 :
│             │  paragraphe 1 ligne
│             │  collé à droite de
└─────────────┘  la photo, w=85mm
─────────────────────────────────
   Bloc texte 2 sous la photo, pleine
   largeur, w=170mm, paragraphe 2-3.
```
- Photo : x=10, y=20, w=60, h=80mm
- Texte 1 (à droite) : x=75, y=20, w=125, h=80mm (même hauteur)
- Texte 2 (sous) : x=10, y=110, w=190, h=...

### Pattern B : Photo droite, texte à gauche (symétrique)
- Texte titre + corps : x=10, y=20, w=125, h=80mm
- Photo : x=140, y=20, w=60, h=80mm

### Pattern C : Photo centrée, texte en colonnes
```
   Colonne G          PHOTO          Colonne D
   x=10               x=70           x=140
   w=55, h=200        w=60, h=80     w=55, h=200
                      (haut centré)
```
- 2 textes en colonnes verticales encadrant la photo

### Pattern D : Photo bandeau haut, texte dessous
- Photo : x=0, y=0, w=210, h=70mm (pleine largeur bord à bord)
- Texte titre + corps : x=10, y=80, w=190, h=... (texte aéré dessous)

**Choisis le pattern selon le contenu** :
- Témoignage individuel = Pattern A ou B (photo portrait + citation)
- Couverture = Pattern D (photo héroïque pleine largeur + titre)
- Page Souvenirs = grille 2×2 ou 3×3 sans texte enrobant
- Programme avec carte localisation = Pattern A (carte gauche, étapes droite)

## ASSOCIATION PHOTO ↔ TEXTE (sémantique)

Les photos uploadées (cf bloc MÉDIATHÈQUE) sont décrites par leur
catégorie + label + dimensions + couleur dominante. Si la description
mentionne explicitement un sujet (« photo couple », « portrait
défunt », « groupe famille »), associe-la à la section pertinente :

| Description photo | Section appropriée |
|---|---|
| « portrait du défunt » | Couverture page 1 OU page parcours |
| « photo de couple » | Page témoignage du conjoint |
| « groupe famille » | Page « Familles annonceuses » ou « Souvenirs » |
| « photo de jeunesse » | Page « Parcours de vie » sous-section débuts |
| « cérémonie / événement passé » | Page Souvenirs |
| « religieux / paroisse / église » | Page « Parcours spirituel » |

Pour les photos sans description claire, distribue-les équitablement
sur les pages Souvenirs en gardant cohérence chromatique
(couleur_dominante) avec le fond de page.

## EXIGENCES TRANSVERSES ABSOLUES (CRITIQUE)

**1. RESPECT SCRUPULEUX DES SECTIONS DEMANDÉES**
Si l'utilisateur énumère des sections (« tu vas simuler les témoignages,
le programme, les familles, le parcours… »), CHACUNE DOIT APPARAÎTRE
sous forme de page dédiée OU de section nettement séparée et titrée
dans le document. Compter le nombre exact de sections demandées et
les inclure TOUTES. Sinon le résultat est inacceptable.

**2. RICHESSE DU CONTENU (anti-paresse)**
Pour chaque section, PRODUIS un contenu DÉTAILLÉ :
- Programme des obsèques : minimum 5-8 étapes (levée du corps, veillée,
  cérémonie religieuse, panégyrique, eulogie, procession, inhumation,
  réception), chaque étape avec heure + lieu + détail
- Familles annonceuses : énumère 4-8 lignages/branches familiales avec
  liste des membres clés (épouse, enfants avec prénoms simulés, frères/
  sœurs, beaux-parents, alliés). Format hiérarchique avec encadrés.
- Témoignages : produis 4-6 témoignages SIMULÉS distincts (différents
  proches : conjoint, enfants, collègue, ami d'enfance, voisin,
  responsable spirituel). Chaque témoignage = citation italique 2-4
  lignes + nom du témoin (peut être placeholder « [Prénom Nom] » si
  user n'a pas fourni).
- Parcours de vie : segmente en 4 sous-sections (Académique /
  Professionnel / Social-Familial / Spirituel-Religieux), chacune
  avec 3-5 lignes de contenu détaillé simulé plausible
- Remerciements : message chaleureux 4-6 lignes + signature « Les
  familles X et Y », pas juste 1 phrase générique

**3. SIMULATION vs INVENTION FACTUELLE SENSIBLE**
- Le user demande EXPLICITEMENT « simuler » témoignages, familles,
  parcours → TU DOIS produire ce contenu inventé MAIS RÉALISTE.
- Pour les DATES (naissance, décès, mariage), NE PAS extrapoler :
  utilise placeholder « [Date de naissance] » si non fourni, mais
  conserve la date fournie pour l'événement clé.
- Pour les NOMS d'enfants, de frères, de témoins : invente des
  prénoms cohérents avec le pays (camerounais, sénégalais, etc.)
  PUIS le LLM doit indiquer qu'ils sont placeholders à valider.

**4. NOMBRE DE PAGES**
Si le user demande « N feuillets » → produis EXACTEMENT 2×N pages
(un feuillet = recto-verso = 2 pages). Brief « 4 feuillets minimum »
→ 8 pages MINIMUM. PAS 4 pages.

**5. DENSITÉ MINIMALE PAR PAGE**
Chaque page contient AU MOINS 10 éléments JSON (rectangle fond, titres,
filets ornements, blocs texte multiples, icônes décoratives 2-4 par
page, cadres subtils, signatures, ornements de coins). Un page avec
seulement « titre + 3 lignes + 1 icône » est INACCEPTABLE.

Compose maintenant le layout PARFAIT pour ce brief en respectant
TOUTES les exigences ci-dessus. JSON STRICT uniquement, sans
commentaire ni markdown.
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
        # ── Sélection modèle + tokens budget — règles 2026 ─────────────────
        # Famille GPT-4.1 (avril 2025) : 32k output cap, 1M context — IDÉALE
        # pour JSON structuré dense multi-pages. Le composer freeform a besoin
        # de 8-16k tokens de sortie pour un livret riche, ce qui était impossible
        # avec gpt-4-turbo (cap 4096) et limite avec gpt-4o (16k).
        # Mapping interne (cf core/ia_client.py:_CLAUDE_TO_GPT) :
        #   CLAUDE_OPUS   → gpt-4.1       (32k out)
        #   CLAUDE_SONNET → gpt-4.1-mini  (32k out, économique)
        #   CLAUDE_HAIKU  → gpt-4.1-nano  (32k out, très économique)
        livret_ou_dense = densite_elevee or bool(contexte_block) or bool(
            _re_d.search(
                r"\blivret|brochure|d[ée]pliant|plaquette|programme|"
                r"faire[- ]?part|album|magazine|portfolio|"
                r"\d+\s*(?:feuillets?|pages?|volets?)",
                (brief or "").lower(),
            )
        )
        # 3 tiers de budget output selon complexité :
        if densite_elevee and contexte_block:
            # livret cérémonie multi-page (faire-part 8p, programme 12p) +
            # densité élevée (20 cartes etc.). Très exigeant.
            max_tok = 16000
            _modele_compose = ModelePrioritaire.CLAUDE_OPUS   # → gpt-4.1 (32k out)
        elif livret_ou_dense:
            # livret 4-8 pages OU N items répétés. Besoin large.
            max_tok = 12000
            _modele_compose = ModelePrioritaire.CLAUDE_OPUS   # → gpt-4.1 (32k out)
        else:
            # Visuel simple 1 page (poster, carte standalone, post social).
            max_tok = 5000
            _modele_compose = ModelePrioritaire.CLAUDE_SONNET  # → gpt-4.1-mini (économique)
        logger.warning(
            f"[FreeformComposer] Composer LLM : modele={_modele_compose.value} "
            f"max_tokens={max_tok} (livret_ou_dense={livret_ou_dense}, "
            f"densite_elevee={densite_elevee}, ceremonie={bool(contexte_block)})"
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

        # ── Post-validation déterministe v356 ──────────────────────────
        # Filets de sécurité indépendants du LLM : même si le modèle
        # ignore les règles de placement / pagination du prompt, on
        # corrige côté code. Cf bugs PDF SIAKA Jean (mai 2026) :
        # icônes superposées au texte + livret A4 plat 8p (OK déjà ×4
        # ici mais le filet protège pour 5, 6, 7, 9 p…).
        data = _corriger_collisions_icones(data)
        data = _forcer_pagination_livret(data, brief)

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


def _bbox_overlap(a: tuple, b: tuple) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _estimer_bbox_texte(el: dict) -> tuple[float, float, float, float]:
    """Estime la bbox d'un élément texte. ReportLab fait du word-wrap, donc
    h_mm n'est pas dans le JSON — on l'approxime depuis taille_pt + len(contenu)
    + w_mm. Conservateur (surestime un peu) pour éviter les faux négatifs."""
    x = float(el.get("x_mm") or 0)
    y = float(el.get("y_mm") or 0)
    w = float(el.get("w_mm") or 50)
    taille = float(el.get("taille_pt") or 10)
    contenu = str(el.get("contenu") or "")
    interligne = float(el.get("interligne") or 1.4)
    # 1pt = 0.3528mm. char_width ≈ 0.55 × taille_pt pour Helvetica/Inter.
    char_w_mm = max(0.5, taille * 0.55 * 0.3528)
    line_h_mm = taille * interligne * 0.3528
    chars_per_line = max(1, int(w / char_w_mm))
    nb_lignes = max(1, (len(contenu) + chars_per_line - 1) // chars_per_line)
    # Compte les \n explicites du contenu
    nb_lignes += contenu.count("\n")
    h_mm = line_h_mm * nb_lignes + 0.5
    return (x, y, x + w, y + h_mm)


def _corriger_collisions_icones(data: dict) -> dict:
    """Détecte les icônes qui se superposent à un Texte et les repositionne
    vers un coin de page libre. Bug observé PDF SIAKA Jean : icône 'famille'
    devant le 'F' de « Famille SIAKA » → texte tronqué visuellement en
    « amille SIAKA ». Le LLM ignore parfois la consigne placement même avec
    règles explicites dans le prompt — donc filet déterministe."""
    pages = data.get("pages") or []
    fmt_doc = data.get("format_mm") or [210, 297]
    nb_corrections = 0
    for page in pages:
        if not isinstance(page, dict):
            continue
        fmt_page = page.get("format_mm") or fmt_doc
        W, H = float(fmt_page[0]), float(fmt_page[1])
        elements = page.get("elements") or []
        text_bboxes = [
            _estimer_bbox_texte(el)
            for el in elements
            if isinstance(el, dict) and el.get("type") == "texte"
        ]
        if not text_bboxes:
            continue
        for el in elements:
            if not isinstance(el, dict) or el.get("type") != "icone":
                continue
            try:
                ix = float(el.get("x_mm") or 0)
                iy = float(el.get("y_mm") or 0)
                iw = float(el.get("w_mm") or 8)
                ih = float(el.get("h_mm") or 8)
            except (TypeError, ValueError):
                continue
            ibox = (ix, iy, ix + iw, iy + ih)
            if not any(_bbox_overlap(ibox, tb) for tb in text_bboxes):
                continue
            # Reposition vers un coin libre (marge 6mm)
            m = 6.0
            candidats = [
                (m, m),                          # haut-gauche
                (W - iw - m, m),                 # haut-droite
                (m, H - ih - m),                 # bas-gauche
                (W - iw - m, H - ih - m),        # bas-droite
                ((W - iw) / 2, m),               # haut-centre
                ((W - iw) / 2, H - ih - m),      # bas-centre
            ]
            choisi = None
            for cx, cy in candidats:
                cbox = (cx, cy, cx + iw, cy + ih)
                if not any(_bbox_overlap(cbox, tb) for tb in text_bboxes):
                    choisi = (cx, cy)
                    break
            if choisi is None:
                choisi = (W - iw - m, m)  # fallback haut-droite
            el["x_mm"] = round(choisi[0], 1)
            el["y_mm"] = round(choisi[1], 1)
            nb_corrections += 1
    if nb_corrections:
        logger.warning(
            f"[FreeformComposer] Post-validation : {nb_corrections} icône(s) "
            f"repositionnée(s) (anti-collision texte)."
        )
    return data


def _forcer_pagination_livret(data: dict, brief: str) -> dict:
    """Pour les livrets/faire-part (≥4 pages), force le total à un multiple
    de 4 (contrainte agrafage imprimeur). Pad avec une page sobre type 'dos'
    si nécessaire. Bug observé : livret 5p ou 6p → impossible à agrafer."""
    pages = data.get("pages") or []
    n = len(pages)
    if n < 4 or n % 4 == 0:
        return data
    import re as _re
    if not _re.search(
        r"\blivret|brochure|d[ée]pliant|plaquette|programme|faire[- ]?part|"
        r"funeraille|obs[èe]ques|c[ée]r[ée]monie|hommage|magazine|portfolio",
        (brief or "").lower(),
    ):
        return data
    cible = ((n + 3) // 4) * 4
    diff = cible - n
    fmt = data.get("format_mm") or [148, 210]
    primaire = (data.get("palette_meta") or {}).get("primaire") or "#1A2742"
    for i in range(diff):
        pages.append({
            "numero": n + i + 1,
            "fond_couleur": "#FFFFFF",
            "elements": [
                {
                    "type": "ornement",
                    "x_mm": float(fmt[0]) / 2 - 6.0,
                    "y_mm": float(fmt[1]) / 2 - 6.0,
                    "w_mm": 12.0, "h_mm": 12.0,
                    "motif": "geometrique",
                    "couleur": primaire,
                    "epaisseur_pt": 0.6,
                },
            ],
        })
    data["pages"] = pages
    logger.warning(
        f"[FreeformComposer] Post-validation : pagination {n} → {cible} pages "
        f"(multiple de 4 pour agrafage livret)."
    )
    return data
