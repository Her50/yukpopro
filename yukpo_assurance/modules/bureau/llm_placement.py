"""
LLM Placement Planner — Phase 1 du pipeline Designer Pro NEXT-GEN.

Demande à un LLM (Sonnet pour la vision géométrique, Opus si demandes très
complexes) de produire un PlacementPlan JSON à partir de :
  - brief utilisateur (intention sémantique)
  - dimensions de page (W×H mm, bleed, orientation)
  - manifest des médias uploadés (dim source, ratio, contenu sémantique)
  - palette de marque optionnelle (BrandKit org)

Le LLM raisonne EN VISION HUMAINE :
  "Le portrait du défunt est en pied, photo 800×1200 portrait. Je le mets
   dans un cercle de 60mm centré en haut de la couverture, recadrage focal
   sur le visage (focal_y=0.2 pour garder la tête). Sous le portrait, le
   nom du défunt en gros (Cormorant 42pt, bleu marine), centré, italique
   léger. En bas, dates 1948–2026 en Lato 18pt gris."

Python implémente CETTE intention en pixels exacts via geometric_placement.

Modèle par défaut : Sonnet (équilibre vision + math). Fallback GPT-4 turbo
si Claude indispo. Cap tokens out : ~3000 pour un layout riche.
"""
from __future__ import annotations

import io
import json
import logging
import re
from typing import Optional

from .geometric_placement import (
    PlacementPlan, TextPlacement, ImagePlacement, ShapePlacement,
    BBox, Color, Transform, Shadow, PageBackground,
)

logger = logging.getLogger("yukpo_assurance.bureau.llm_placement")


# ═══════════════════════════════════════════════════════════════════════
# Manifest d'image uploadée — métadonnées exploitables par le LLM
# ═══════════════════════════════════════════════════════════════════════

def manifest_image(
    media_ref: str,
    image_bytes: bytes,
    tags: Optional[list[str]] = None,
    role_hint: Optional[str] = None,
) -> dict:
    """
    Construit le manifest d'une image pour le LLM.

    `media_ref` : identifiant stable (ex: 'session:abc123')
    `tags`      : sémantique humaine (['portrait', 'visage', 'défunt']) ; si
                  None, on tente une auto-détection légère (orientation,
                  couleur dominante). Vision Sonnet idéal pour générer tags
                  riches mais c'est un appel séparé hors scope ici.
    `role_hint` : suggestion sémantique ('portrait_principal', 'logo',
                  'fond_decoratif', 'illustration_section')
    """
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        ratio = round(w / max(1, h), 3)
        orientation = "portrait" if h > w * 1.1 else ("paysage" if w > h * 1.1 else "carre")
        # Couleur dominante moyenne sur thumbnail
        thumb = img.convert("RGB").resize((40, 40))
        pixels = list(thumb.getdata())
        avg = tuple(sum(c[i] for c in pixels) // len(pixels) for i in range(3))
    except Exception as e:
        logger.warning(f"[Manifest] échec lecture image {media_ref} : {e}")
        w = h = 0; ratio = 1.0; orientation = "inconnu"; avg = (128, 128, 128)

    return {
        "media_ref": media_ref,
        "width_px": w, "height_px": h,
        "ratio": ratio, "orientation": orientation,
        "couleur_dominante_hex": f"#{avg[0]:02x}{avg[1]:02x}{avg[2]:02x}",
        "tags": tags or [],
        "role_hint": role_hint or "auto",
    }


# ═══════════════════════════════════════════════════════════════════════
# Prompt LLM — placement géométrique
# ═══════════════════════════════════════════════════════════════════════

PROMPT_SYSTEM = """Tu es DIRECTEUR ARTISTIQUE et GRAPHISTE EXPERT.

Mission : pour un visuel imprimable (flyer, carte, livret, affiche, faire-part,
diplôme…), tu décides EN VISION HUMAINE le placement parfait de chaque élément
(texte, image, forme décorative) sur la page.

Tu reçois :
  - Brief utilisateur (intention, contenu)
  - Page : largeur, hauteur, marges bleed (en mm, origine top-left)
  - Médias uploadés : dimensions, orientation, contenu sémantique
  - Palette/typographie de marque (si fournie)

Tu produis un PLAN JSON où CHAQUE élément a sa bounding box EXACTE en mm,
ses propriétés visuelles complètes, et les ajustements géométriques nécessaires
(recadrage focal des images, masque silhouette, rotation, ombre, etc.).

PRINCIPES DE DESIGN :
1. RESPIRATION — laisse 8-15mm de marge intérieure depuis le trim.
2. HIÉRARCHIE — 1 élément dominant (≥40% de la surface visuelle), 2-3 secondaires,
   reste accessoire. Jamais 10 éléments tous au même niveau.
3. ALIGNEMENT — grille visuelle implicite, axes alignés. Centres optiques
   coïncident souvent.
4. CONTRASTE — couleur, taille, poids. Pas de mou.
5. AÉRATION TYPOGRAPHIQUE — line-height 1.2-1.5, letter-spacing élargi
   (0.05-0.15em) pour les TITRES MAJUSCULES, normal sinon.
6. ROLE DES IMAGES — un portrait = cercle ou masque doux (pas un rectangle dur).
   Un logo = rectangle aligné en coin. Un fond = full-bleed + opacité réduite
   si du texte se superpose.
7. CADRAGE FOCAL — si une photo doit être recadrée pour s'adapter à la zone,
   précise focal_point_x/y pour ancrer le sujet (visage, produit, mention clé).

Pour CHAQUE image dans target_zone :
  - Si le ratio source ≠ ratio cible, fit_mode='smart_focus' avec focal_point
    explicite (ex: portrait debout dans cercle → focal_y=0.2 pour visage en haut).
  - mask_shape adapté : portrait = circle ou rounded_rect, paysage = rect,
    logo = rect, illustration = blob ou polygon si organique.
  - filters (recolor/grayscale/blur) si l'image distrait du message principal
    (ex: fond de carte = grayscale + blur léger + opacity 0.3).

Pour CHAQUE texte :
  - bbox AVEC marge de respiration (pas collé au bord).
  - vertical_align logique (titre = center vertical dans son bloc, paragraphe = top).
  - Hiérarchie pt : titre principal 32-72pt, sous-titre 18-28pt, corps 10-14pt,
    légende 7-9pt.
  - Couleur contrastée par rapport au fond (ratio WCAG > 4.5 pour corps).
  - shadow OPTIONNEL seulement si texte sur image (visibilité).

SORTIE : JSON STRICT conforme au schéma indiqué. Pas de markdown, pas de prose.
"""


_LANGUE_INFOS = {
    "fr": {"nom": "français",  "direction": "ltr", "polices_priorisees": ["Inter", "Calibri", "Lato"]},
    "en": {"nom": "anglais",   "direction": "ltr", "polices_priorisees": ["Inter", "Helvetica", "Arial"]},
    "es": {"nom": "espagnol",  "direction": "ltr", "polices_priorisees": ["Inter", "Lato"]},
    "pt": {"nom": "portugais", "direction": "ltr", "polices_priorisees": ["Inter", "Lato"]},
    "de": {"nom": "allemand",  "direction": "ltr", "polices_priorisees": ["Inter", "Calibri"]},
    "it": {"nom": "italien",   "direction": "ltr", "polices_priorisees": ["Inter", "Lato"]},
    "ar": {"nom": "arabe",     "direction": "rtl", "polices_priorisees": ["Noto Sans Arabic", "Amiri", "Cairo"]},
    "zh": {"nom": "chinois",   "direction": "ltr", "polices_priorisees": ["Noto Sans SC", "PingFang SC"]},
    "ja": {"nom": "japonais",  "direction": "ltr", "polices_priorisees": ["Noto Sans JP", "Hiragino"]},
    "ru": {"nom": "russe",     "direction": "ltr", "polices_priorisees": ["Inter", "Liberation Sans"]},
    "hi": {"nom": "hindi",     "direction": "ltr", "polices_priorisees": ["Noto Sans Devanagari"]},
    "sw": {"nom": "swahili",   "direction": "ltr", "polices_priorisees": ["Inter", "Lato"]},
    "ha": {"nom": "haoussa",   "direction": "ltr", "polices_priorisees": ["Inter", "Noto Sans"]},
    "wo": {"nom": "wolof",     "direction": "ltr", "polices_priorisees": ["Inter", "Lato"]},
    "ln": {"nom": "lingala",   "direction": "ltr", "polices_priorisees": ["Inter", "Lato"]},
    "am": {"nom": "amharique", "direction": "ltr", "polices_priorisees": ["Noto Sans Ethiopic"]},
    "tr": {"nom": "turc",      "direction": "ltr", "polices_priorisees": ["Inter", "Lato"]},
}


def construire_prompt_user(
    brief: str,
    page_w_mm: float,
    page_h_mm: float,
    bleed_mm: float = 3.0,
    medias: Optional[list[dict]] = None,
    brand_kit: Optional[dict] = None,
    inspiration: Optional[str] = None,
    langue: str = "fr",
) -> str:
    """
    Compose le prompt user complet.

    `medias`     : liste de manifests produits par manifest_image().
    `brand_kit`  : {couleur_primaire_hex, couleur_accent_hex, polices: {titre, corps}, ...}
    `inspiration`: brief de style libre ("style minimaliste japonais", "deuil classique européen").
    `langue`     : code ISO de la langue cible pour TOUS les textes du visuel
                   (fr/en/es/pt/de/ar/zh/ja/ru/hi/sw/ha/wo/ln/am/tr).
    """
    medias_str = ""
    if medias:
        medias_str = "\n\nMÉDIAS UPLOADÉS DISPONIBLES :\n" + json.dumps(medias, ensure_ascii=False, indent=2)
    brand_str = ""
    if brand_kit:
        brand_str = "\n\nCHARTE DE MARQUE (à respecter strictement) :\n" + json.dumps(brand_kit, ensure_ascii=False, indent=2)
    inspi_str = ""
    if inspiration:
        inspi_str = f"\n\nINSPIRATION STYLISTIQUE : {inspiration}"

    # Langue cible : injection explicite des contraintes typographiques
    info_l = _LANGUE_INFOS.get(langue, _LANGUE_INFOS["fr"])
    polices_pref = ", ".join(info_l["polices_priorisees"])
    rtl_note = ""
    if info_l["direction"] == "rtl":
        rtl_note = (
            "\n  • Direction RTL (droite→gauche) : align='right' pour les blocs "
            "de paragraphe, mais align='center' pour titres centrés sur la page. "
            "Le texte arabe lui-même est rendu correctement par PIL/HarfBuzz."
        )
    langue_str = (
        f"\n\nLANGUE DES TEXTES SUR LE VISUEL : {info_l['nom']} (code ISO : {langue})\n"
        f"  • TOUS les textes (titres, sous-titres, corps, légendes, mentions) "
        f"DOIVENT être en {info_l['nom']}. Pas de mélange.\n"
        f"  • Polices priorisées (par ordre de préférence selon la couverture "
        f"glyphes) : {polices_pref}. Choisis font_family parmi cette liste.{rtl_note}"
    )

    return f"""BRIEF UTILISATEUR :
\"\"\"{brief}\"\"\"

PAGE :
  - Largeur  : {page_w_mm} mm (trim, sans bleed)
  - Hauteur  : {page_h_mm} mm
  - Bleed    : {bleed_mm} mm (zone de fond perdu pour découpe imprimeur)
  - Origine  : top-left, axe Y descendant (comme CSS){langue_str}
{medias_str}{brand_str}{inspi_str}

SCHÉMA JSON ATTENDU :
{{
  "page_w_mm": {page_w_mm},
  "page_h_mm": {page_h_mm},
  "bleed_mm": {bleed_mm},
  "background": {{
    "color": {{"r": 255, "g": 255, "b": 255, "a": 1.0}},
    "gradient": null,
    "image_media_ref": null
  }},
  "items": [
    {{
      "kind": "image",
      "media_ref": "session:abc",
      "target_zone": {{"x": 30, "y": 25, "w": 60, "h": 60}},
      "fit_mode": "smart_focus",
      "focal_point_x": 0.5, "focal_point_y": 0.25,
      "mask_shape": "circle",
      "mask_extra": {{}},
      "border_mm": 0.8,
      "border_color": {{"r": 200, "g": 200, "b": 200, "a": 1.0}},
      "shadow": {{"offset_x_mm": 0.5, "offset_y_mm": 0.8, "blur_mm": 2.0,
                 "color": {{"r": 0, "g": 0, "b": 0, "a": 0.25}}}},
      "z_index": 5
    }},
    {{
      "kind": "text",
      "text": "Marie NGONO",
      "bbox": {{"x": 15, "y": 95, "w": 120, "h": 18}},
      "font_family": "Cormorant",
      "font_size_pt": 32,
      "font_weight": 600,
      "italic": false,
      "color": {{"r": 30, "g": 40, "b": 60, "a": 1.0}},
      "align": "center",
      "vertical_align": "middle",
      "line_height": 1.15,
      "letter_spacing_em": 0.02,
      "uppercase": false,
      "z_index": 10
    }},
    {{
      "kind": "shape",
      "shape": "rect",
      "bbox": {{"x": 50, "y": 120, "w": 50, "h": 0.4}},
      "fill": {{"r": 180, "g": 150, "b": 90, "a": 1.0}},
      "stroke": null,
      "z_index": 1
    }}
  ]
}}

RÈGLES STRICTES :
- Tu DOIS placer TOUS les médias uploadés (ne pas en ignorer).
- Tu DOIS respecter la palette de marque si fournie (couleurs, polices).
- bbox.x + bbox.w ≤ page_w_mm + bleed_mm (pas de débordement).
- bbox.y + bbox.h ≤ page_h_mm + bleed_mm.
- z_index : background=0, formes décoratives=1-3, images=5-8, textes=10-15.
- target_zone.x doit être ≥ 5mm de marge intérieure SAUF si fond full-bleed
  intentionnel (auquel cas la zone déborde jusqu'à -bleed_mm).

Réponds UNIQUEMENT en JSON valide, sans markdown, sans préambule.
"""


# ═══════════════════════════════════════════════════════════════════════
# Appel LLM
# ═══════════════════════════════════════════════════════════════════════

async def generer_placement_plan(
    brief: str,
    page_w_mm: float,
    page_h_mm: float,
    bleed_mm: float = 3.0,
    medias: Optional[list[dict]] = None,
    brand_kit: Optional[dict] = None,
    inspiration: Optional[str] = None,
    modele: str = "sonnet",
    langue: str = "fr",
) -> Optional[PlacementPlan]:
    """
    Appelle le LLM et retourne un PlacementPlan validé.

    `modele` : 'sonnet' (défaut, équilibre vision/coût), 'opus' (placements
               complexes mémoire/livret), 'haiku' (placements simples
               carte/flyer rapide).
    `langue` : code ISO de la langue cible des textes sur le visuel
               (fr/en/es/pt/de/ar/zh/ja/ru/hi/sw/ha/wo/ln/am/tr).
    """
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire

    forcer_modele = {
        "sonnet": ModelePrioritaire.CLAUDE_SONNET,
        "opus":   ModelePrioritaire.CLAUDE_OPUS,
        "haiku":  ModelePrioritaire.CLAUDE_HAIKU,
    }.get(modele, ModelePrioritaire.CLAUDE_SONNET)

    user_prompt = construire_prompt_user(
        brief, page_w_mm, page_h_mm, bleed_mm,
        medias=medias, brand_kit=brand_kit, inspiration=inspiration,
        langue=langue,
    )

    try:
        rep = await ia_client.appeler(
            prompt=user_prompt,
            systeme=PROMPT_SYSTEM,
            mode=ModeIA.PRECISION,
            forcer_modele=forcer_modele,
            json_attendu=True,
            max_tokens_override=4000,
        )
    except Exception as e:
        logger.error(f"[LLMPlacement] Appel LLM échoué : {e}")
        return None

    raw = (rep.contenu or "").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Extraction tolérante : premier JSON object trouvé
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            logger.warning("[LLMPlacement] Pas de JSON parseable dans la réponse")
            return None
        try:
            data = json.loads(m.group())
        except Exception as e:
            logger.warning(f"[LLMPlacement] JSON malformé : {e}")
            return None

    try:
        plan = PlacementPlan(**data)
    except Exception as e:
        logger.warning(f"[LLMPlacement] Validation Pydantic échouée : {e}")
        # Tentative auto-fix : injecter dimensions page si manquantes
        data.setdefault("page_w_mm", page_w_mm)
        data.setdefault("page_h_mm", page_h_mm)
        data.setdefault("bleed_mm", bleed_mm)
        data.setdefault("items", [])
        try:
            plan = PlacementPlan(**data)
        except Exception as e2:
            logger.error(f"[LLMPlacement] Auto-fix échoué : {e2}")
            return None
    return plan


# ═══════════════════════════════════════════════════════════════════════
# Boucle auto-critique LLM Vision (audit + révision avant rendu final)
# ═══════════════════════════════════════════════════════════════════════

PROMPT_REVISION_SYSTEM = """Tu es DIRECTEUR ARTISTIQUE SENIOR. Tu reçois UN VISUEL
DÉJÀ RENDU à auditer en VISION (image PNG attachée) AVEC le PlacementPlan JSON
qui l'a produit. Ton job : repérer les défauts qu'un humain remarquerait au
premier coup d'œil et proposer un plan corrigé.

DÉFAUTS À TRAQUER :
1. Texte tronqué (ne rentre pas dans sa bbox), débordement, chevauchement avec
   d'autres éléments.
2. Image mal cadrée (sujet coupé, visage tronqué, focal_point décalé).
3. Hiérarchie cassée (titre trop petit, sous-titre trop gros, parité visuelle).
4. Espacement irrégulier (alignements ratés, marges incohérentes).
5. Couleurs : contraste insuffisant texte/fond (ratio WCAG < 4.5 pour corps),
   conflit palette charte.
6. Zones vides disgracieuses ou densité visuelle déséquilibrée.
7. Forme du masque inadaptée (cercle pour paysage, rect pour portrait carré, etc.).
8. Police inadaptée au registre (formel/festif/sobre).
9. Rotation/ombre/effet excessif ou absent là où il manque.

SORTIE JSON STRICT :
{
  "verdict": "ok" | "ameliorations_mineures" | "refonte_necessaire",
  "score_qualite_sur_10": 7.5,
  "issues": [
    {"severite": "critique|majeur|mineur", "type": "texte_tronque|...",
     "item_index": 2, "description": "Le titre déborde de 8mm à droite",
     "correctif": "Réduire font_size_pt de 32 à 26 OU élargir bbox.w de 60 à 90"}
  ],
  "plan_revise": null OU {PlacementPlan complet avec corrections appliquées}
}

Si verdict='ok' → plan_revise=null (pas de re-render nécessaire).
Si verdict='ameliorations_mineures' OU 'refonte_necessaire' → fournis le
PlacementPlan complet revisé conforme au schéma initial.
"""


async def auditer_et_reviser_placement(
    plan: PlacementPlan,
    png_bytes: bytes,
    brief: str,
    medias_manifest: Optional[list[dict]] = None,
    modele: str = "sonnet",
) -> Optional["RevisionResult"]:
    """
    Phase 3 (optionnelle) : audit visuel du rendu par Sonnet Vision puis
    proposition de plan révisé si défauts détectés.

    Retourne un RevisionResult avec verdict + issues + plan_revise (ou None).
    """
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire
    import base64

    forcer_modele = {
        "sonnet": ModelePrioritaire.CLAUDE_SONNET,
        "opus":   ModelePrioritaire.CLAUDE_OPUS,
    }.get(modele, ModelePrioritaire.CLAUDE_SONNET)

    user_prompt = (
        f"BRIEF UTILISATEUR INITIAL :\n\"\"\"{brief}\"\"\"\n\n"
        f"PLACEMENT_PLAN qui a produit le visuel ci-joint :\n"
        f"{json.dumps(plan.model_dump(), ensure_ascii=False)[:6000]}\n\n"
        f"MÉDIAS UPLOADÉS :\n"
        f"{json.dumps(medias_manifest or [], ensure_ascii=False)[:2000]}\n\n"
        f"Audite le visuel attaché et retourne le JSON de révision."
    )

    # Sonnet supporte les images en input via 'images' param du ia_client.
    # Si l'implémentation locale ne supporte pas, fallback texte-only avec
    # description sommaire (mais qualité dégradée).
    image_b64 = base64.b64encode(png_bytes).decode()
    try:
        rep = await ia_client.appeler(
            prompt=user_prompt,
            systeme=PROMPT_REVISION_SYSTEM,
            mode=ModeIA.PRECISION,
            forcer_modele=forcer_modele,
            json_attendu=True,
            max_tokens_override=4500,
            images=[{"data": image_b64, "mime": "image/png"}],
        )
    except TypeError:
        # ia_client ne supporte pas images= → fallback sans vision
        logger.info("[Revision] ia_client.appeler ne supporte pas images, audit texte-only")
        try:
            rep = await ia_client.appeler(
                prompt=user_prompt + "\n\n[NOTE: rendu visuel non transmis, audit basé "
                                       "uniquement sur le PlacementPlan JSON]",
                systeme=PROMPT_REVISION_SYSTEM,
                mode=ModeIA.PRECISION,
                forcer_modele=forcer_modele,
                json_attendu=True,
                max_tokens_override=4500,
            )
        except Exception as e:
            logger.warning(f"[Revision] LLM fallback texte échoué : {e}")
            return None
    except Exception as e:
        logger.warning(f"[Revision] LLM échoué : {e}")
        return None

    raw = (rep.contenu or "").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return None
        try:
            data = json.loads(m.group())
        except Exception:
            return None

    verdict = data.get("verdict", "ok")
    issues = data.get("issues", [])
    score = float(data.get("score_qualite_sur_10", 5.0))
    plan_revise = None
    raw_revise = data.get("plan_revise")
    if isinstance(raw_revise, dict):
        try:
            plan_revise = PlacementPlan(**raw_revise)
        except Exception as e:
            logger.warning(f"[Revision] plan_revise invalide : {e}")
            plan_revise = None

    return RevisionResult(
        verdict=verdict, score=score, issues=issues, plan_revise=plan_revise,
    )


class RevisionResult(BaseModel):
    """Résultat d'un audit Vision LLM."""
    verdict: str = Field(...,
        description="ok | ameliorations_mineures | refonte_necessaire")
    score: float = Field(..., ge=0.0, le=10.0)
    issues: list[dict] = Field(default_factory=list)
    plan_revise: Optional[PlacementPlan] = None


async def generer_visuel_avec_revision(
    brief: str,
    page_w_mm: float, page_h_mm: float, bleed_mm: float,
    medias_bytes: dict[str, bytes],
    medias_manifest: list[dict],
    brand_kit: Optional[dict] = None,
    inspiration: Optional[str] = None,
    modele: str = "sonnet",
    langue: str = "fr",
    dpi: int = 300,
    max_iterations: int = 2,
    score_seuil_ok: float = 7.5,
) -> tuple[Optional[PlacementPlan], bytes, list[dict]]:
    """
    Pipeline complet : placement → rendu → audit → révision → re-rendu.

    Retourne (plan_final, png_final, journal_revisions).
    `max_iterations` borné à 2 pour limiter coût (chaque iter = 1 appel
    LLM placement + 1 appel LLM audit + 1 render).
    `score_seuil_ok` : si score ≥ ce seuil, on arrête même si plan_revise
    existe (évite révisions infinies pour gains marginaux).
    """
    from .geometric_placement import render_placement_plan

    journal: list[dict] = []
    plan = await generer_placement_plan(
        brief, page_w_mm, page_h_mm, bleed_mm,
        medias=medias_manifest, brand_kit=brand_kit,
        inspiration=inspiration, modele=modele, langue=langue,
    )
    if plan is None:
        return None, b"", [{"iteration": 0, "erreur": "LLM placement initial KO"}]

    png = render_placement_plan(plan, medias_bytes, dpi=dpi, include_bleed=True)
    journal.append({"iteration": 0, "etape": "render_initial", "size_kb": len(png) // 1024})

    for it in range(1, max_iterations + 1):
        revision = await auditer_et_reviser_placement(
            plan, png, brief, medias_manifest=medias_manifest, modele=modele,
        )
        if revision is None:
            journal.append({"iteration": it, "etape": "audit_skip", "raison": "LLM KO"})
            break

        journal.append({
            "iteration": it, "etape": "audit",
            "verdict": revision.verdict,
            "score": revision.score,
            "nb_issues": len(revision.issues),
            "issues_critiques": sum(1 for i in revision.issues
                                     if i.get("severite") == "critique"),
        })

        if revision.verdict == "ok" or revision.score >= score_seuil_ok:
            break
        if revision.plan_revise is None:
            journal.append({"iteration": it, "etape": "audit_sans_revise"})
            break

        plan = revision.plan_revise
        png = render_placement_plan(plan, medias_bytes, dpi=dpi, include_bleed=True)
        journal.append({"iteration": it, "etape": "re_render",
                        "size_kb": len(png) // 1024})

    return plan, png, journal
