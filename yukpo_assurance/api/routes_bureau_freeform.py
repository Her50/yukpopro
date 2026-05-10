"""
Endpoint Freeform Layout — composition LLM directe (sans templates rigides).

POST /api/v1/bureau/freeform/generer
  Body : { brief, pays, langue, medias_refs, ... }
  Compose JSON layout via gpt-4-turbo (LLM_PRIMAIRE=gpt) + rasterise PDF.

Usage : appelable depuis l'orchestrateur G1 quand intent=visuel ou
directement depuis le frontend pour les briefs visuels atypiques.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.auth import get_current_user, TokenData

router = APIRouter()
logger = logging.getLogger("yukpo_assurance.routes_bureau_freeform")

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "generated" / "bureau"
_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _slugifier(texte: str, max_len: int = 50) -> str:
    """Convertit un texte libre en slug ASCII-safe pour filename.

    Exemples :
      "Carte de visite Yukpo 5 personnes" -> "carte_de_visite_yukpo_5_personnes"
      "Flyer A3 anti-tabac MINSANTE Cameroun" -> "flyer_a3_anti_tabac_minsante_cameroun"
      "Rapport — Annuel 2026 (v2.1)" -> "rapport_annuel_2026_v2_1"
      "" -> "document"
    """
    import re
    import unicodedata
    if not texte or not texte.strip():
        return "document"
    # Normaliser accents
    norm = unicodedata.normalize("NFKD", texte)
    ascii_only = norm.encode("ascii", "ignore").decode("ascii")
    # Lowercase + remplace tout sauf alphanum par _
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_only.lower())
    # Trim _ multiples + bordure
    slug = re.sub(r"_+", "_", slug).strip("_")
    if not slug:
        return "document"
    return slug[:max_len].rstrip("_")


class DemandeFreeform(BaseModel):
    brief: str = Field(..., min_length=10, max_length=5000)
    pays: str = Field(default="CM")
    langue: str = Field(default="fr")
    medias_refs: Optional[list[str]] = Field(default=None)
    profil: Optional[dict] = Field(default=None)
    export_cmyk: bool = Field(default=True)


@router.post("/generer", tags=["Bureau — Freeform Layout"])
async def generer_freeform(
    demande: DemandeFreeform,
    current_user: TokenData = Depends(get_current_user),
):
    """Génère un visuel libre (PDF print-ready) via composition LLM
    directe sans template. Le LLM produit un JSON de primitives, le
    renderer ReportLab les rasterise."""
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde, debiter_llm, debiter_forfait,
    )
    from modules.bureau import (
        freeform_layout, freeform_composer, mediatheque_session as _msm,
        verticales_metier as _vm,
    )

    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "infographie")
    if not autorise:
        raise HTTPException(403, msg)
    ok_solde, restants, _ = await verifier_solde(current_user.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")

    # Résolution des médias session pour les éléments image avec ref_media
    medias = {}
    if demande.medias_refs:
        try:
            session_id = f"chat_{current_user.user_id}"
            medias = _msm.resoudre_refs(
                demande.medias_refs, str(current_user.user_id), session_id,
            )
        except Exception as e:
            logger.debug(f"[Freeform] Resolution medias : {e}")

    descripteurs_medias = []
    for ref, m in (medias or {}).items():
        try:
            d = _msm.descripteur_pour_ia(m)
            d["ref"] = ref
            descripteurs_medias.append(d)
        except Exception:
            pass

    # Verticalité dynamique (couvre TOUS les secteurs mondiaux)
    descripteur_vert = None
    try:
        profil = demande.profil or {}
        descripteur_vert = await _vm.detecter_vertical_dynamique_llm(
            metier=profil.get("metier"),
            secteur=profil.get("secteur"),
            pays=demande.pays,
            brief=demande.brief,
        )
    except Exception:
        pass

    # Brand kit éventuel (Sprint 2.4 — auto-héritage compagnie)
    brand_kit = None
    try:
        cid = getattr(current_user, "compagnie_id", None) or 1
        from api.routes_brand_kit import charger_overrides_brand_kit
        bk_overrides = await charger_overrides_brand_kit(int(cid))
        if isinstance(bk_overrides, dict) and bk_overrides:
            brand_kit = bk_overrides
    except Exception:
        pass

    # 1. LLM compose le layout JSON
    t0 = time.time()
    layout_json = await freeform_composer.composer_freeform_layout(
        brief=demande.brief,
        profil=demande.profil,
        medias_descripteurs=descripteurs_medias,
        brand_kit=brand_kit,
        descripteur_vertical=descripteur_vert,
        pays=demande.pays,
        langue=demande.langue,
    )
    duree_compose_ms = int((time.time() - t0) * 1000)

    # 2. Rendu PDF (async : pre-génération images IA via Flux Pro Ultra +
    # icônes Iconify embeddées + ReportLab rasterise)
    t0 = time.time()
    try:
        pdf_bytes = await freeform_layout.rendre_pdf_depuis_json(layout_json, medias=medias)
    except Exception as e:
        logger.error(f"[Freeform] Render échoué : {e}")
        raise HTTPException(500, f"Rendu PDF échoué : {str(e)[:200]}")
    duree_render_ms = int((time.time() - t0) * 1000)

    # 3. CMYK Ghostscript si demandé
    if demande.export_cmyk:
        try:
            from modules.bureau.pdf_print_ready import convertir_rgb_to_cmyk
            cmyk_bytes = convertir_rgb_to_cmyk(pdf_bytes, icc_name="fogra39")
            if cmyk_bytes:
                pdf_bytes = cmyk_bytes
        except Exception as e:
            logger.debug(f"[Freeform] CMYK skip : {e}")

    # 4. Sauvegarde — filename parlant : bureau_freeform_<user_id>_<slug_titre>_<ts>.pdf
    # Le slug est extrait du titre du layout produit par le LLM. Préfixe
    # `bureau_freeform_` conservé pour le routing /bureau/documents (cf.
    # ChatPage MessageBubble qui détecte ce préfixe).
    titre_layout = (layout_json.get("titre") or demande.brief or "document")[:80]
    slug = _slugifier(titre_layout, max_len=50)
    fichier_id = f"bureau_freeform_{current_user.user_id}_{slug}_{int(time.time())}.pdf"
    chemin = _DATA_DIR / fichier_id
    chemin.write_bytes(pdf_bytes)

    # 5. Débit forfait (1 FCFA / page, multiplicateur = nb pages)
    nb_pages = len(layout_json.get("pages") or [])
    try:
        await debiter_forfait(
            current_user.user_id,
            cle_forfait="designerpro_creation",
            multiplicateur=max(1, nb_pages * 5),  # ~5 FCFA / page freeform
            module="infographie",
        )
    except Exception as e:
        logger.debug(f"[Freeform] Forfait debit non bloquant : {e}")

    # Suggestions intelligentes post-génération (3-5 propositions de suite
    # contextuelles : variantes, déclinaisons, multilingues, formats print,
    # etc. — non bloquant, ~0.4 FCFA Haiku).
    suggestions: list[dict] = []
    try:
        from modules.pro.suggestions_intelligente import (
            generer_suggestions_suite, detecter_manques_visuel,
        )
        meta_sug = {
            "format_mm": layout_json.get("format_mm"),
            "nb_pages": nb_pages,
            "langue": demande.langue,
            "pays": demande.pays,
            "export_cmyk": demande.export_cmyk,
            "titre_layout": layout_json.get("titre"),
        }
        manques = detecter_manques_visuel(meta_sug, demande.brief)
        suggestions = await generer_suggestions_suite(
            type_doc="freeform_visuel",
            brief_original=demande.brief,
            meta_resultat=meta_sug,
            manques_detectes=manques,
        )
    except Exception as _e_sug:
        logger.debug(f"[Freeform/Suggestions] non bloquant : {_e_sug}")

    download_url = f"/api/v1/bureau/documents/{fichier_id}"
    return {
        "ok": True,
        "fichier": fichier_id,
        "fichier_genere": fichier_id,        # alias frontend ChatPage
        "pdf_id": fichier_id,
        "download_url": download_url,
        "url_telechargement": download_url,
        "nb_pages": nb_pages,
        "format_mm": layout_json.get("format_mm"),
        "titre": layout_json.get("titre"),
        "duree_compose_ms": duree_compose_ms,
        "duree_render_ms": duree_render_ms,
        "taille_octets": len(pdf_bytes),
        "suggestions": suggestions,
    }
