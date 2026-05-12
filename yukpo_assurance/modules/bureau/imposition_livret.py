"""
Imposition livret saddle-stitched (piqûre métal au pli central).

Standard d'impression commercial pour livrets agrafés au pli :
- L'utilisateur a un livret de N pages logiques (1, 2, 3, ... N) générées
  dans l'ordre de lecture.
- Pour l'impression duplex agrafée, on imprime N/2 feuilles PHYSIQUES,
  chaque feuille porte 2 pages logiques côte-à-côte (paysage), recto et
  verso.
- Après impression duplex, pli au centre, agrafage du pli → livret lisible
  dans l'ordre logique.

## Algorithme d'imposition saddle-stitched

Pour N pages logiques (N multiple de 4 — sinon on pad avec pages vides) :

  Feuille i (i = 0, 1, ..., N/4-1) :
    Recto extérieur (vu plié à plat dehors) :
      gauche  = page logique N - 2i
      droite  = page logique 1  + 2i
    Verso intérieur (vu plié à plat dedans) :
      gauche  = page logique 2  + 2i
      droite  = page logique N-1 - 2i

Exemple N=8 :
  Feuille 1 recto : [page 8] [page 1]
  Feuille 1 verso : [page 2] [page 7]
  Feuille 2 recto : [page 6] [page 3]
  Feuille 2 verso : [page 4] [page 5]

Exemple N=12 :
  Feuille 1 recto : [12] [1]
  Feuille 1 verso : [2]  [11]
  Feuille 2 recto : [10] [3]
  Feuille 2 verso : [4]  [9]
  Feuille 3 recto : [8]  [5]
  Feuille 3 verso : [6]  [7]

## Détails techniques

- Chaque feuille physique : largeur = 2 × page_w_mm, hauteur = page_h_mm
  (orientation paysage typiquement).
- Page logique « gauche » placée à offset x=0 sur la feuille.
- Page logique « droite » placée à offset x=page_w_mm.
- Tous les éléments des pages logiques sont décalés en conséquence.
- Bleed externe étendu à 3mm autour de la feuille physique entière (4
  bords) ; au pli central, pas de bleed nécessaire (pages partagent le
  pli).
- Crop marks aux 4 coins externes de la feuille + repère de pli au
  centre (ligne pointillée fine ou pair de marques).

Note : la page COUVERTURE (page logique 1) et le DOS (page logique N)
sont toujours sur la même feuille (feuille 1, côté extérieur recto). C'est
ce qui justifie que la couverture soit conçue en isolé visuel et le dos
sobre.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace as _dc_replace
from typing import Any


def calculer_paires_imposition(nb_pages: int) -> list[tuple[int, int]]:
    """Retourne la liste ordonnée des paires (index_gauche, index_droite)
    pour l'imposition saddle-stitched. Index 1-based.

    Pour N=8 :
        [(8,1), (2,7), (6,3), (4,5)]

    Chaque paire correspond à UNE face physique imprimée. Faces ordonnées :
    feuille_1_recto, feuille_1_verso, feuille_2_recto, feuille_2_verso, ...
    """
    if nb_pages <= 0 or nb_pages % 4 != 0:
        raise ValueError(
            f"nb_pages={nb_pages} doit être multiple de 4 pour saddle-stitched. "
            f"Padder avec pages vides en amont."
        )
    paires: list[tuple[int, int]] = []
    nb_feuilles = nb_pages // 4
    for i in range(nb_feuilles):
        # Recto extérieur (les pages les plus éloignées dans l'ordre logique)
        recto_g = nb_pages - 2 * i
        recto_d = 1 + 2 * i
        paires.append((recto_g, recto_d))
        # Verso intérieur
        verso_g = 2 + 2 * i
        verso_d = nb_pages - 1 - 2 * i
        paires.append((verso_g, verso_d))
    return paires


def imposer_layout_saddle_stitched(layout_json: dict) -> dict:
    """Transforme un layout logique (N pages dans l'ordre lecture) en
    layout physique imposé (N/2 faces, 2 pages logiques par face, format
    paysage).

    Précondition : toutes les pages ont le MÊME format (sinon imposition
    impossible — retourne layout inchangé avec warning).

    Comportement :
    1. Padding pages vides si nb_pages pas multiple de 4
    2. Calcul des paires
    3. Pour chaque paire : crée une page « feuille » format = (2W, H) avec
       éléments page-gauche à x=0 et éléments page-droite à x=W
    4. Reconstruit layout_json avec les nouvelles pages + format ajusté

    Le pipeline freeform_layout.rendre_layout_pdf est compatible : il rend
    chaque page (= feuille imposée) au format indiqué dans page.format_mm.

    Retourne le nouveau dict layout. Pages originales en `_pages_logiques`
    pour audit/debug.
    """
    pages = layout_json.get("pages") or []
    if not pages:
        return layout_json

    # 1) Vérification cohérence format
    fmt_global = layout_json.get("format_mm") or [148, 210]
    page_w, page_h = float(fmt_global[0]), float(fmt_global[1])
    for p in pages:
        pf = p.get("format_mm")
        if pf and (float(pf[0]) != page_w or float(pf[1]) != page_h):
            # Format mixte → imposition impossible, on ne touche pas
            return {**layout_json, "_imposition_skipped": "formats_mixtes"}

    # 2) Padding à multiple de 4
    pages_padded = list(pages)
    while len(pages_padded) % 4 != 0:
        pages_padded.append({
            "numero": len(pages_padded) + 1,
            "fond_couleur": pages_padded[0].get("fond_couleur") or "#FFFFFF",
            "format_mm": [page_w, page_h],
            "elements": [],
            "libelle_piece": "page_vide_padding",
        })

    nb_total = len(pages_padded)
    paires = calculer_paires_imposition(nb_total)

    # 3) Construction des feuilles imposées
    feuilles: list[dict] = []
    for idx_face, (g_idx, d_idx) in enumerate(paires):
        page_gauche = pages_padded[g_idx - 1]  # 1-based → 0-based
        page_droite = pages_padded[d_idx - 1]

        # Déplace chaque élément de la page droite : x += page_w
        elements_g = [deepcopy(el) for el in (page_gauche.get("elements") or [])]
        elements_d = []
        for el in (page_droite.get("elements") or []):
            new_el = deepcopy(el)
            for k in ("x_mm", "x1_mm", "x2_mm"):
                if k in new_el and new_el[k] is not None:
                    try:
                        new_el[k] = float(new_el[k]) + page_w
                    except (TypeError, ValueError):
                        pass
            elements_d.append(new_el)

        # Fond : si les 2 pages ont le même fond, on l'applique à la feuille.
        # Sinon, on crée 2 rectangles fond (gauche + droite).
        fond_g = page_gauche.get("fond_couleur") or "#FFFFFF"
        fond_d = page_droite.get("fond_couleur") or "#FFFFFF"
        fond_feuille = fond_g if fond_g == fond_d else "#FFFFFF"
        fonds_split: list[dict] = []
        if fond_g != fond_d:
            # Rectangle fond gauche
            fonds_split.append({
                "type": "rectangle",
                "x_mm": 0, "y_mm": 0,
                "w_mm": page_w, "h_mm": page_h,
                "fond": fond_g, "z_index": -10,
            })
            fonds_split.append({
                "type": "rectangle",
                "x_mm": page_w, "y_mm": 0,
                "w_mm": page_w, "h_mm": page_h,
                "fond": fond_d, "z_index": -10,
            })

        # Repère de pli au centre (pointillé fin gris)
        repere_pli = {
            "type": "ligne",
            "x1_mm": page_w, "y1_mm": -3,
            "x2_mm": page_w, "y2_mm": page_h + 3,
            "epaisseur_pt": 0.25,
            "couleur": "#CCCCCC",
            "style": "dashed",
            "z_index": -5,
        }

        # Crop marks externes
        crop_marks = []
        # Sur les 4 coins de la feuille (largeur 2W, hauteur H)
        for cx in (0, 2 * page_w):
            for cy in (0, page_h):
                crop_marks.append({
                    "type": "crop_marks",
                    "x_mm": cx - 0.5, "y_mm": cy - 0.5,
                    "w_mm": 1, "h_mm": 1,
                    "longueur_mm": 3, "epaisseur_pt": 0.25,
                    "couleur": "#000000",
                })

        # Identifier le numéro physique (feuille N, face recto/verso)
        nb_feuille = idx_face // 2 + 1
        face = "recto" if idx_face % 2 == 0 else "verso"
        libelle = f"feuille_{nb_feuille}_{face}_logiques_{g_idx}+{d_idx}"

        feuilles.append({
            "numero": idx_face + 1,
            "fond_couleur": fond_feuille,
            "format_mm": [page_w * 2, page_h],
            "elements": fonds_split + elements_g + elements_d + [repere_pli] + crop_marks,
            "libelle_piece": libelle,
        })

    # 4) Layout imposé
    layout_impose = {
        **layout_json,
        "format_mm": [page_w * 2, page_h],  # feuille paysage = 2W × H
        "pages": feuilles,
        "_pages_logiques_origine": pages_padded,
        "_imposition_appliquee": "saddle_stitched",
        "_nb_pages_logiques": nb_total,
        "_nb_feuilles_physiques": nb_total // 2,
    }
    return layout_impose


def doit_imposer(layout_json: dict) -> bool:
    """Heuristique : imposer si le document est un livret (>=4 pages,
    format cohérent type A5/A6/carré). Skip pour visuels single-page
    (poster, affiche, carte) ou cartes 8-up (gérées séparément).
    """
    pages = layout_json.get("pages") or []
    if len(pages) < 4:
        return False
    # Si déjà imposé, ne pas re-imposer
    if layout_json.get("_imposition_appliquee"):
        return False
    # Si pages au format planche A4 (210×297) avec libelle_piece commençant
    # par 'planche_' → ce sont des planches 8-up déjà imposées (cartes
    # visite recto-verso). Skip.
    if any(
        (p.get("libelle_piece") or "").startswith(("planche_recto", "planche_verso"))
        for p in pages
    ):
        return False
    # Format physique : préférer A5, A6, carré 14, carré 21 (livrets)
    fmt = layout_json.get("format_mm") or [210, 297]
    w, h = float(fmt[0]), float(fmt[1])
    formats_livret = [
        (105, 148),   # A6
        (148, 105),   # A6 paysage
        (148, 210),   # A5 portrait
        (210, 148),   # A5 paysage
        (140, 140),   # carré 14
        (148, 148),   # carré 15
        (210, 210),   # carré 21
        (210, 297),   # A4 portrait (livret programme)
    ]
    for (fw, fh) in formats_livret:
        if abs(w - fw) < 5 and abs(h - fh) < 5:
            return True
    return False
