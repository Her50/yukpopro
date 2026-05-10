"""
Endpoint Freeform Layout — composition LLM directe (sans templates rigides).

POST /api/v1/bureau/freeform/generer
  Body : { brief, pays, langue, medias_refs, ... }

Pipeline 2-phases :
1. Synchrone (~5-10s) : compose layout JSON via LLM, valide, détermine si
   le layout contient des images IA à générer.
2a. Si pas d'image IA : rasterise immédiatement, retourne fichier (~5s).
2b. Si image IA présente : retourne `job_id` immédiatement, lance le
    rendering en background (Flux Pro Ultra ~15-30s/img + render).
    Le client poll /status/{job_id} pour récupérer le fichier final.

Ce 2-phases permet de :
- Garder la latence courte pour briefs simples (carte visite sans IA)
- Permettre Flux Pro Ultra qualité max sans contrainte timeout Cloudflare 100s
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.auth import get_current_user, TokenData

router = APIRouter()
logger = logging.getLogger("yukpo_assurance.routes_bureau_freeform")

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "generated" / "bureau"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Stockage statut jobs : Redis si dispo, sinon mémoire process (TTL 1h).
_JOBS_LOCAL: dict[str, dict] = {}
_JOB_TTL_S = 3600


def _slugifier(texte: str, max_len: int = 50) -> str:
    """Convertit un texte libre en slug ASCII-safe pour filename."""
    import re
    import unicodedata
    if not texte or not texte.strip():
        return "document"
    norm = unicodedata.normalize("NFKD", texte)
    ascii_only = norm.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_only.lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return (slug[:max_len].rstrip("_")) or "document"


# ─── Stockage statut jobs (Redis avec fallback mémoire) ──────────────────


async def _job_set(job_id: str, data: dict) -> None:
    data = {**data, "_ts": time.time()}
    _JOBS_LOCAL[job_id] = data
    # Redis best-effort
    try:
        import redis.asyncio as aioredis
        from config.settings import settings
        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=0.5)
        await r.set(f"freeform:job:{job_id}", json.dumps(data), ex=_JOB_TTL_S)
        await r.aclose()
    except Exception:
        pass


async def _job_get(job_id: str) -> Optional[dict]:
    # Redis prioritaire (multi-worker safe)
    try:
        import redis.asyncio as aioredis
        from config.settings import settings
        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=0.5)
        raw = await r.get(f"freeform:job:{job_id}")
        await r.aclose()
        if raw:
            return json.loads(raw if isinstance(raw, str) else raw.decode())
    except Exception:
        pass
    # Fallback mémoire local
    return _JOBS_LOCAL.get(job_id)


def _layout_a_images_ia(layout_json: dict) -> bool:
    """Détecte si le layout contient au moins un élément image avec
    `prompt_ia` non vide (et sans ref/data_url) qui nécessitera Flux."""
    for page in (layout_json.get("pages") or []):
        for el in (page.get("elements") or []):
            if (el.get("type") in ("image", "image_ia")
                and el.get("prompt_ia")
                and not (el.get("ref_media") or el.get("data_url") or el.get("url"))):
                return True
    return False


# ─── Schema requête ──────────────────────────────────────────────────────


class DemandeFreeform(BaseModel):
    brief: str = Field(..., min_length=10, max_length=5000)
    pays: str = Field(default="CM")
    langue: str = Field(default="fr")
    medias_refs: Optional[list[str]] = Field(default=None)
    profil: Optional[dict] = Field(default=None)
    export_cmyk: bool = Field(default=True)


# ─── Endpoint /generer (2-phases sync/async) ─────────────────────────────


@router.post("/generer", tags=["Bureau — Freeform Layout"])
async def generer_freeform(
    demande: DemandeFreeform,
    current_user: TokenData = Depends(get_current_user),
):
    """Génère un visuel libre (PDF print-ready) via composition LLM.
    Mode 2-phases : sync si pas d'IA, async (job_id + polling) si IA inline."""
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde,
    )
    from modules.bureau import (
        freeform_composer, mediatheque_session as _msm,
        verticales_metier as _vm,
    )

    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "infographie")
    if not autorise:
        raise HTTPException(403, msg)
    ok_solde, restants, _ = await verifier_solde(current_user.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")

    # Résolution médias session
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

    # Verticalité dynamique
    descripteur_vert = None
    try:
        profil = demande.profil or {}
        descripteur_vert = await _vm.detecter_vertical_dynamique_llm(
            metier=profil.get("metier"), secteur=profil.get("secteur"),
            pays=demande.pays, brief=demande.brief,
        )
    except Exception:
        pass

    # Brand kit auto-héritage
    brand_kit = None
    try:
        cid = getattr(current_user, "compagnie_id", None) or 1
        from api.routes_brand_kit import charger_overrides_brand_kit
        bk_overrides = await charger_overrides_brand_kit(int(cid))
        if isinstance(bk_overrides, dict) and bk_overrides:
            brand_kit = bk_overrides
    except Exception:
        pass

    # PHASE 1 (synchrone) — Compose JSON layout via LLM
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

    # Détecter si génération IA inline nécessaire (Flux Pro Ultra ~15-30s/img)
    a_images_ia = _layout_a_images_ia(layout_json)

    titre_layout = (layout_json.get("titre") or demande.brief or "document")[:80]
    slug = _slugifier(titre_layout, max_len=50)

    if not a_images_ia:
        # PHASE 2a (synchrone) — pas d'IA inline → render direct, retour fichier
        return await _generer_sync(
            current_user, demande, layout_json, medias, slug, duree_compose_ms,
        )

    # PHASE 2b (asynchrone) — IA inline → job_id + background task
    job_id = str(uuid.uuid4())
    fichier_id_prevu = (
        f"bureau_freeform_{current_user.user_id}_{slug}_{int(time.time())}.pdf"
    )
    await _job_set(job_id, {
        "statut": "pending",
        "user_id": current_user.user_id,
        "fichier_id": fichier_id_prevu,
        "titre": titre_layout,
        "nb_pages": len(layout_json.get("pages") or []),
        "duree_compose_ms": duree_compose_ms,
    })
    asyncio.create_task(_render_background(
        job_id=job_id, fichier_id=fichier_id_prevu,
        layout_json=layout_json, medias=medias,
        export_cmyk=demande.export_cmyk,
        user_id=current_user.user_id,
        brief=demande.brief, pays=demande.pays, langue=demande.langue,
    ))
    return {
        "ok": True,
        "async": True,
        "job_id": job_id,
        "statut": "pending",
        "titre": titre_layout,
        "nb_pages": len(layout_json.get("pages") or []),
        "duree_compose_ms": duree_compose_ms,
        "message": (
            "Génération en cours (Flux Pro Ultra qualité photoréaliste). "
            "Suivre via GET /api/v1/bureau/freeform/status/{job_id}. "
            "Durée typique : 30-90s selon nombre d'images."
        ),
        "status_url": f"/api/v1/bureau/freeform/status/{job_id}",
    }


# ─── Phase 2a : render synchrone (sans IA inline) ───────────────────────


async def _generer_sync(
    current_user: TokenData,
    demande: DemandeFreeform,
    layout_json: dict,
    medias: dict,
    slug: str,
    duree_compose_ms: int,
) -> dict:
    from modules.bureau import freeform_layout
    from modules.bureau.service_credits_bureau import debiter_forfait

    t0 = time.time()
    try:
        pdf_bytes = await freeform_layout.rendre_pdf_depuis_json(layout_json, medias=medias)
    except Exception as e:
        logger.error(f"[Freeform/sync] Render échoué : {e}")
        raise HTTPException(500, f"Rendu PDF échoué : {str(e)[:200]}")
    duree_render_ms = int((time.time() - t0) * 1000)

    if demande.export_cmyk:
        try:
            from modules.bureau.pdf_print_ready import convertir_rgb_to_cmyk
            cmyk_bytes = convertir_rgb_to_cmyk(pdf_bytes, icc_name="fogra39")
            if cmyk_bytes:
                pdf_bytes = cmyk_bytes
        except Exception as e:
            logger.debug(f"[Freeform/sync] CMYK skip : {e}")

    fichier_id = f"bureau_freeform_{current_user.user_id}_{slug}_{int(time.time())}.pdf"
    (_DATA_DIR / fichier_id).write_bytes(pdf_bytes)

    nb_pages = len(layout_json.get("pages") or [])
    try:
        await debiter_forfait(
            current_user.user_id, cle_forfait="designerpro_creation",
            multiplicateur=max(1, nb_pages * 5), module="infographie",
        )
    except Exception:
        pass

    suggestions = await _generer_suggestions(layout_json, demande, nb_pages)
    download_url = f"/api/v1/bureau/documents/{fichier_id}"
    return {
        "ok": True, "async": False,
        "fichier": fichier_id, "fichier_genere": fichier_id, "pdf_id": fichier_id,
        "download_url": download_url, "url_telechargement": download_url,
        "nb_pages": nb_pages,
        "format_mm": layout_json.get("format_mm"),
        "titre": layout_json.get("titre"),
        "duree_compose_ms": duree_compose_ms,
        "duree_render_ms": duree_render_ms,
        "taille_octets": len(pdf_bytes),
        "suggestions": suggestions,
    }


# ─── Phase 2b : render background (avec IA inline Flux Pro Ultra) ───────


async def _render_background(
    *, job_id: str, fichier_id: str, layout_json: dict, medias: dict,
    export_cmyk: bool, user_id: int, brief: str, pays: str, langue: str,
) -> None:
    """Tâche background : Flux Pro Ultra + render + save + statut done."""
    from modules.bureau import freeform_layout
    from modules.bureau.service_credits_bureau import debiter_forfait
    nb_pages = len(layout_json.get("pages") or [])
    titre = layout_json.get("titre") or "document"

    try:
        await _job_set(job_id, {
            "statut": "running", "user_id": user_id,
            "fichier_id": fichier_id, "titre": titre, "nb_pages": nb_pages,
        })
        t0 = time.time()
        pdf_bytes = await freeform_layout.rendre_pdf_depuis_json(layout_json, medias=medias)
        duree_render_ms = int((time.time() - t0) * 1000)

        if export_cmyk:
            try:
                from modules.bureau.pdf_print_ready import convertir_rgb_to_cmyk
                cmyk_bytes = convertir_rgb_to_cmyk(pdf_bytes, icc_name="fogra39")
                if cmyk_bytes:
                    pdf_bytes = cmyk_bytes
            except Exception:
                pass

        (_DATA_DIR / fichier_id).write_bytes(pdf_bytes)

        try:
            await debiter_forfait(
                user_id, cle_forfait="designerpro_creation",
                multiplicateur=max(1, nb_pages * 5), module="infographie",
            )
        except Exception:
            pass

        # Suggestions (re-créer demande factice pour helper)
        class _D: pass
        d = _D(); d.brief = brief; d.pays = pays; d.langue = langue; d.export_cmyk = export_cmyk  # type: ignore
        try:
            suggestions = await _generer_suggestions(layout_json, d, nb_pages)
        except Exception:
            suggestions = []

        await _job_set(job_id, {
            "statut": "done", "user_id": user_id,
            "fichier_id": fichier_id, "titre": titre, "nb_pages": nb_pages,
            "download_url": f"/api/v1/bureau/documents/{fichier_id}",
            "url_telechargement": f"/api/v1/bureau/documents/{fichier_id}",
            "fichier": fichier_id, "fichier_genere": fichier_id,
            "pdf_id": fichier_id,
            "duree_render_ms": duree_render_ms,
            "taille_octets": len(pdf_bytes),
            "suggestions": suggestions,
        })
        logger.info(f"[Freeform/async] Job {job_id[:8]} done : {fichier_id} ({len(pdf_bytes)} bytes, {duree_render_ms}ms)")
    except Exception as e:
        logger.error(f"[Freeform/async] Job {job_id[:8]} ECHEC : {e}")
        await _job_set(job_id, {
            "statut": "failed", "user_id": user_id,
            "erreur": str(e)[:300], "fichier_id": fichier_id,
        })


async def _generer_suggestions(layout_json: dict, demande, nb_pages: int) -> list[dict]:
    try:
        from modules.pro.suggestions_intelligente import (
            generer_suggestions_suite, detecter_manques_visuel,
        )
        meta = {
            "format_mm": layout_json.get("format_mm"),
            "nb_pages": nb_pages,
            "langue": getattr(demande, "langue", "fr"),
            "pays": getattr(demande, "pays", "CM"),
            "export_cmyk": getattr(demande, "export_cmyk", True),
            "titre_layout": layout_json.get("titre"),
        }
        manques = detecter_manques_visuel(meta, demande.brief)
        return await generer_suggestions_suite(
            type_doc="freeform_visuel", brief_original=demande.brief,
            meta_resultat=meta, manques_detectes=manques,
        )
    except Exception:
        return []


# ─── Endpoint /status/{job_id} ───────────────────────────────────────────


@router.get("/status/{job_id}", tags=["Bureau — Freeform Layout"])
async def freeform_status(
    job_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Polling : retourne le statut + (si statut=done) URL de téléchargement.
    Le client polle toutes les 3-5 secondes jusqu'à statut ∈ {done, failed}."""
    if "/" in job_id or len(job_id) > 64:
        raise HTTPException(400, "job_id invalide")
    data = await _job_get(job_id)
    if not data:
        raise HTTPException(404, "Job introuvable ou expiré (TTL 1h)")
    # Sécurité : un user ne voit que ses jobs
    if data.get("user_id") != current_user.user_id and current_user.role != "admin":
        raise HTTPException(403, "Accès refusé à ce job")
    return data
