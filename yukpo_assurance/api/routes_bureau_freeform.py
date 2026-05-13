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


def _detecter_type_visuel(brief: str) -> str:
    """Détecte le type de visuel depuis le brief pour nommer le fichier
    de manière lisible et courte. Retourne un slug court (≤20 chars) :
    carte_visite, faire_part, flyer, brochure, affiche, livret, menu, etc.
    Si aucun match, retourne 'visuel'. Évite les noms de fichier à rallonge
    type 'fais_moi_une_simulation_d_un_faire_part_pour_les_o'.
    """
    import re as _re_t
    b = (brief or "").lower()
    # Ordre = priorité de détection (plus spécifique d'abord)
    patterns = [
        (r"\bcarte[s]?\s+(?:de\s+)?visite|business\s+card", "carte_visite"),
        (r"\bfaire[- ]?part", "faire_part"),
        (r"\bcarton\s+(?:d['])?invitation|carte\s+invitation", "invitation"),
        (r"\bmarque[- ]?place|porte[- ]?nom", "marque_place"),
        (r"\bbadge", "badge"),
        (r"\bflyer", "flyer"),
        (r"\bd[ée]pliant|brochure|plaquette", "brochure"),
        (r"\baffiche|poster|banderole|oriflamme|kakemono", "affiche"),
        (r"\bmenu\b", "menu"),
        (r"\blivret\b", "livret"),
        (r"\bprogramme\b", "programme"),
        (r"\bcv\s+graphique|cv\s+visuel", "cv_graphique"),
        (r"\bpackaging|[ée]tiquette\s+produit", "packaging"),
        (r"\bsticker|autocollant", "sticker"),
        (r"\bcertificat|dipl[oô]me", "certificat"),
        (r"\bpost\s+(?:instagram|linkedin|facebook|social)|story|réseau", "post_social"),
        (r"\bticket|billet", "ticket"),
        (r"\bcv\b", "cv"),
        (r"\bcarte\b", "carte"),
    ]
    for pat, slug in patterns:
        if _re_t.search(pat, b):
            return slug
    return "visuel"


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

    # ── Mode async COMPLET (composer + render en background) ──
    # On retourne job_id IMMÉDIATEMENT (<1s) sans attendre le composer LLM
    # (60-75s) car Netlify free-tier timeout = 26s sur les proxies.
    # Le client poll /status/{job_id} via GET (rapides, pas de timeout).
    job_id = str(uuid.uuid4())
    titre_layout_provisoire = (demande.brief or "document")[:80]
    # Filename court et lisible : on utilise le TYPE de visuel détecté
    # (carte_visite, faire_part, flyer, …) au lieu du brief tronqué.
    # Optionnellement on suffixe avec le nom d'organisation si dispo.
    type_visuel = _detecter_type_visuel(demande.brief or "")
    org_nom = (demande.profil or {}).get("nom_organisation", "") if isinstance(demande.profil, dict) else ""
    org_slug = _slugifier(org_nom, max_len=20) if org_nom else ""
    slug = f"{type_visuel}_{org_slug}" if org_slug else type_visuel
    fichier_id_prevu = (
        f"bureau_freeform_{current_user.user_id}_{slug}_{int(time.time())}.pdf"
    )
    await _job_set(job_id, {
        "statut": "pending",
        "user_id": current_user.user_id,
        "fichier_id": fichier_id_prevu,
        "titre": titre_layout_provisoire,
        "nb_pages": 0,  # rempli après composition
        "duree_compose_ms": 0,
    })
    asyncio.create_task(_compose_et_render_background(
        job_id=job_id, fichier_id=fichier_id_prevu,
        demande=demande, medias=medias,
        descripteurs_medias=descripteurs_medias,
        descripteur_vert=descripteur_vert, brand_kit=brand_kit,
        export_cmyk=demande.export_cmyk,
        user_id=current_user.user_id,
    ))
    return {
        "ok": True,
        "async": True,
        "job_id": job_id,
        "statut": "pending",
        "titre": titre_layout_provisoire,
        "nb_pages": 0,
        "duree_compose_ms": 0,
        "message": (
            "Génération en cours (composer LLM + rendu PDF). "
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
            current_user.user_id, type_forfait="designerpro_creation",
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


async def _compose_et_render_background(
    *, job_id: str, fichier_id: str, demande: "DemandeFreeform", medias: dict,
    descripteurs_medias: list, descripteur_vert, brand_kit,
    export_cmyk: bool, user_id: int,
) -> None:
    """Tâche background COMPLÈTE : composer LLM (60-75s) + render PDF (45-95s).

    Retourne tôt côté handler HTTP (<1s) pour éviter le timeout Netlify
    (26s sur free-tier). Le frontend poll /status/{job_id} jusqu'à done.
    """
    from modules.bureau import freeform_composer
    jid8 = job_id[:8]
    try:
        await _job_set(job_id, {
            "statut": "composing", "user_id": user_id,
            "fichier_id": fichier_id,
            "titre": (demande.brief or "document")[:80], "nb_pages": 0,
        })
        logger.info(
            f"[Freeform/async] Job {jid8} composer START user={user_id} "
            f"nb_medias={len(descripteurs_medias or [])} brand_kit={'oui' if brand_kit else 'non'}"
        )
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
        titre_final = (layout_json.get("titre") or demande.brief or "document")[:80]
        nb_pages_final = len(layout_json.get("pages") or [])
        nb_elems_final = sum(len(p.get("elements") or []) for p in (layout_json.get("pages") or []))
        logger.info(
            f"[Freeform/async] Job {jid8} composer DONE in {duree_compose_ms}ms — "
            f"{nb_pages_final} pages, {nb_elems_final} elements, fmt={layout_json.get('format_mm')}"
        )
        await _job_set(job_id, {
            "statut": "running", "user_id": user_id,
            "fichier_id": fichier_id, "titre": titre_final,
            "nb_pages": nb_pages_final, "duree_compose_ms": duree_compose_ms,
        })
        await _render_background(
            job_id=job_id, fichier_id=fichier_id,
            layout_json=layout_json, medias=medias,
            export_cmyk=export_cmyk, user_id=user_id,
            brief=demande.brief, pays=demande.pays, langue=demande.langue,
        )
    except Exception as e:
        logger.error(
            f"[Freeform/async] Job {jid8} ECHEC compose : {e}",
            exc_info=True,
        )
        await _job_set(job_id, {
            "statut": "failed", "user_id": user_id,
            "erreur": str(e)[:300], "fichier_id": fichier_id,
        })


async def _render_background(
    *, job_id: str, fichier_id: str, layout_json: dict, medias: dict,
    export_cmyk: bool, user_id: int, brief: str, pays: str, langue: str,
) -> None:
    """Tâche background : Flux Pro Ultra + render + save + statut done."""
    from modules.bureau import freeform_layout
    from modules.bureau.service_credits_bureau import debiter_forfait
    nb_pages = len(layout_json.get("pages") or [])
    titre = layout_json.get("titre") or "document"
    jid8 = job_id[:8]

    try:
        await _job_set(job_id, {
            "statut": "running", "user_id": user_id,
            "fichier_id": fichier_id, "titre": titre, "nb_pages": nb_pages,
        })
        logger.info(
            f"[Freeform/async] Job {jid8} render START — {nb_pages} pages, "
            f"export_cmyk={export_cmyk}, fmt={layout_json.get('format_mm')}, "
            f"imposition={layout_json.get('_imposition_appliquee') or 'aucune'}"
        )
        t0 = time.time()
        pdf_bytes = await freeform_layout.rendre_pdf_depuis_json(layout_json, medias=medias)
        duree_render_ms = int((time.time() - t0) * 1000)
        logger.info(
            f"[Freeform/async] Job {jid8} render DONE in {duree_render_ms}ms — "
            f"{len(pdf_bytes)} bytes"
        )

        if export_cmyk:
            try:
                from modules.bureau.pdf_print_ready import convertir_rgb_to_cmyk
                cmyk_bytes = convertir_rgb_to_cmyk(pdf_bytes, icc_name="fogra39")
                if cmyk_bytes:
                    pdf_bytes = cmyk_bytes
                    logger.info(f"[Freeform/async] Job {jid8} CMYK OK — {len(pdf_bytes)} bytes")
            except Exception as e_cmyk:
                logger.warning(f"[Freeform/async] Job {jid8} CMYK skip : {e_cmyk}")

        # ── PDF/X-1a:2001 (TrimBox + BleedBox + ICC FOGRA39 + XMP) ────────
        # Convertit le PDF en PDF/X-1a strict pour conformité imprimerie
        # (Heidelberg Prinect, EFI Fiery, Caldera RIPs). Sans cette étape,
        # un imprimeur PRO refuse souvent le fichier (manque MediaBox/TrimBox
        # déclarés explicitement + ICC OutputIntent obligatoire en PDF/X).
        try:
            from modules.bureau.pdf_print_ready import convertir_en_pdf_x1a
            # Format trim = dimensions de la page sans bleed. Pour cartes
            # de visite imposées sur planche A4, le trim de la PLANCHE est A4
            # (210×297mm). C'est le bon TrimBox pour l'imposition livrée
            # à l'imprimeur (qui rognera ensuite au massicot selon les
            # crop marks dessinées dans le PDF).
            fmt = layout_json.get("format_mm") or [210, 297]
            bleed_mm_val = float(layout_json.get("bleed_mm", 3.0))
            x1a_bytes = convertir_en_pdf_x1a(
                pdf_bytes,
                titre=titre,
                format_trim_mm=(float(fmt[0]), float(fmt[1])),
                bleed_mm=bleed_mm_val,
                creator="Yukpo Designer Pro (freeform)",
                profil_icc="fogra39",
                surimpression_noir=True,
            )
            if x1a_bytes:
                pdf_bytes = x1a_bytes
                logger.info(f"[Freeform/async] Job {jid8} PDF/X-1a OK — {len(pdf_bytes)} bytes")
        except Exception as e_x1a:
            logger.warning(f"[Freeform/async] Job {jid8} PDF/X-1a skip : {e_x1a}")

        # ── Audit Vision LLM (qualité couleurs + dispositions + chevauchements) ─
        # Convertit la 1ère page PDF en PNG via pdf2image puis envoie à
        # Sonnet Vision via auditer_visuel_generique. Pas de re-render auto
        # (freeform = pipeline catalog, non-réversible depuis le JSON layout),
        # mais l'audit est retourné en INFO à l'utilisateur pour décider.
        audit_qualite_freeform = None
        try:
            from pdf2image import convert_from_bytes
            from modules.bureau.llm_placement import auditer_visuel_generique
            pages_pil = convert_from_bytes(pdf_bytes, dpi=150, first_page=1, last_page=1)
            if pages_pil:
                import io as _io
                buf = _io.BytesIO()
                pages_pil[0].save(buf, format="PNG", optimize=True)
                png_audit = buf.getvalue()
                audit_qualite_freeform, usage_audit = await auditer_visuel_generique(
                    png_bytes=png_audit,
                    brief=brief or "",
                    langue=langue or "fr",
                    contexte=f"Pipeline freeform — {nb_pages} pages, format {layout_json.get('format_mm')}",
                )
                if usage_audit.get("tokens_in") or usage_audit.get("tokens_out"):
                    try:
                        from modules.bureau.service_credits_bureau import debiter_llm
                        await debiter_llm(
                            user_id,
                            modele=usage_audit.get("modele", "claude"),
                            tokens_input=int(usage_audit.get("tokens_in", 0)),
                            tokens_output=int(usage_audit.get("tokens_out", 0)),
                            module="infographie",
                        )
                    except Exception as _e_dl:
                        logger.warning(f"[Freeform/audit] débit LLM skip : {_e_dl}")
                if audit_qualite_freeform:
                    score = audit_qualite_freeform.get("score_qualite_sur_10", 0)
                    verdict = audit_qualite_freeform.get("verdict", "?")
                    nb_faibles = len(audit_qualite_freeform.get("points_faibles", []))
                    logger.info(
                        f"[Freeform/audit] Job {jid8} qualité : score={score}/10 "
                        f"verdict={verdict} faibles={nb_faibles}"
                    )
        except Exception as e_audit:
            logger.warning(f"[Freeform/audit] Job {jid8} audit skip : {e_audit}")

        chemin_pdf = _DATA_DIR / fichier_id
        chemin_pdf.write_bytes(pdf_bytes)
        logger.info(
            f"[Freeform/async] Job {jid8} disk write OK — {chemin_pdf} "
            f"({len(pdf_bytes)} bytes)"
        )

        try:
            await debiter_forfait(
                user_id, type_forfait="designerpro_creation",
                multiplicateur=max(1, nb_pages * 5), module="infographie",
            )
            logger.info(
                f"[Freeform/async] Job {jid8} forfait débité — "
                f"designerpro_creation × {max(1, nb_pages * 5)}"
            )
        except Exception as e_forfait:
            logger.warning(f"[Freeform/async] Job {jid8} forfait KO : {e_forfait}")

        # Persistance DB : sans ça le PDF n'apparaît pas dans 'Mes Documents'
        # (historique = lecture DB, pas le store Zustand frontend qui est local).
        # En cas d'échec ici on logge ERROR + stacktrace pour diagnostic.
        try:
            from core.database import DocumentGenereDB, async_session_maker
            from datetime import datetime as _dt
            logger.info(f"[Freeform/async] Job {jid8} DB save START user={user_id}")
            async with async_session_maker() as _db:
                doc = DocumentGenereDB(
                    user_id=user_id,
                    titre=(titre or brief or "Visuel")[:200],
                    type_doc="designerpro_freeform",
                    fichier=fichier_id,
                    contenu_source="",
                    contenu_genere="",
                    session_id=f"chat_{user_id}",
                    meta={
                        "source": "freeform_async",
                        "format": "pdf",
                        "nb_pages": nb_pages,
                        "brief": (brief or "")[:300],
                        "pays": pays, "langue": langue,
                    },
                    cree_le=_dt.utcnow(), modifie_le=_dt.utcnow(),
                )
                _db.add(doc)
                await _db.commit()
                await _db.refresh(doc)
                logger.info(
                    f"[Freeform/async] Job {jid8} DB save DONE — doc_id={doc.id} "
                    f"fichier={fichier_id}"
                )
        except Exception as e_db:
            logger.error(
                f"[Freeform/async] Job {jid8} DB save FAILED (PDF disque OK, "
                f"mais invisible dans Mes Documents) : {e_db}",
                exc_info=True,
            )

        # Suggestions (re-créer demande factice pour helper)
        class _D: pass
        d = _D(); d.brief = brief; d.pays = pays; d.langue = langue; d.export_cmyk = export_cmyk  # type: ignore
        try:
            suggestions = await _generer_suggestions(layout_json, d, nb_pages)
        except Exception:
            suggestions = []

        # R3 — Persiste le layout_json dans BureauSessionDB pour permettre
        # modifications incrémentales ("change la couleur en bleu",
        # "ajoute mon logo en bas") sans regénérer depuis le brief.
        try:
            from modules.bureau import bureau_session as _bs
            await _bs.update_session_apres_generation(
                user_id=user_id,
                pipeline="freeform",
                fichier_id=fichier_id,
                brief=brief or "",
                layout_json=layout_json,  # Le LAYOUT entier (peut être gros)
            )
        except Exception as _e_sess:
            logger.warning(f"[Freeform/async] Job {jid8} session update : {_e_sess}")

        # Raccourci top-level pour le frontend : questions ciblées que le chat
        # doit poser à l'utilisateur après réception du PDF, pour itérer.
        questions_amelioration = []
        if isinstance(audit_qualite_freeform, dict):
            questions_amelioration = (
                audit_qualite_freeform.get("questions_amelioration") or []
            )
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
            "audit_qualite": audit_qualite_freeform,
            "questions_amelioration": questions_amelioration,
            "print_ready": "PDF/X-1a:2001",
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


# ─── R3 — Modification incrémentale d'un visuel freeform existant ───────────

class DemandeFreeformModifier(BaseModel):
    fichier_id: str = Field(..., min_length=5,
        description="ID du fichier précédent à modifier (de BureauSessionDB)")
    instructions: str = Field(..., min_length=3, max_length=4000,
        description="Instructions de modification en langage naturel")


@router.post("/modifier", tags=["Bureau — Freeform Layout"])
async def modifier_freeform(
    demande: DemandeFreeformModifier,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Modifie un visuel freeform existant via instructions ciblées ("change la
    couleur du titre en bleu", "ajoute le logo en haut", "supprime la 3e carte").

    Récupère le layout_json précédent depuis BureauSessionDB, demande à Sonnet
    Opus de produire le layout modifié, re-render via pipeline standard
    (PDF/X-1a + CMYK + bleed).

    SANS cet endpoint : l'user devait recommencer son brief from scratch pour
    chaque retouche → perte cohérence + coût LLM ×2 + pas de "suite logique".
    """
    from modules.bureau import bureau_session as _bs, freeform_layout
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde, debiter_llm, debiter_forfait,
    )
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire
    import json as _json
    import re as _re
    import time as _time

    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "infographie")
    if not autorise:
        raise HTTPException(403, msg)
    ok_solde, restants, _ = await verifier_solde(current_user.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")

    sess = await _bs.get_or_create_session(current_user.user_id)
    layout_precedent = sess.dernier_layout_json
    if not layout_precedent:
        raise HTTPException(404,
            "Layout précédent introuvable en session (TTL 30 min expiré). "
            "Régénère le visuel depuis le brief.")

    # Si layout très volumineux (100 cartes = JSON 50k+ chars), résume les
    # pages répétitives (template recto/verso suffit à comprendre la structure).
    layout_str = _json.dumps(layout_precedent, ensure_ascii=False)
    if len(layout_str) > 60000:
        pages = layout_precedent.get("pages", [])
        layout_resume = dict(layout_precedent)
        if len(pages) > 2:
            layout_resume["pages"] = pages[:2] + [
                {"_truncated": f"{len(pages) - 2} pages additionnelles (mêmes templates répétés)"}
            ]
        layout_str = _json.dumps(layout_resume, ensure_ascii=False)

    prompt_modif = (
        "Tu reçois un LAYOUT JSON existant + instructions de modification de "
        "l'utilisateur. Renvoie le layout COMPLET avec uniquement les "
        "modifications appliquées (conserve tout le reste).\n\n"
        f"LAYOUT JSON ACTUEL :\n{layout_str}\n\n"
        f"INSTRUCTIONS DE MODIFICATION :\n" + chr(34) * 3 + demande.instructions + chr(34) * 3 + "\n\n"
        "RÈGLES :\n"
        "1. Modifie UNIQUEMENT les éléments concernés.\n"
        "2. Conserve structure générale (format_mm, bleed, palette globale).\n"
        "3. Si modification couleur → mets à jour sur TOUS les éléments concernés.\n"
        "4. Si ajout → place sans chevaucher l'existant (zones séparées).\n"
        "5. Si suppression → retire l'élément du tableau elements.\n"
        "6. Conserve z_index cohérent (fond=0, décor=1, texte=2-4, QR=3, etc.).\n\n"
        "Renvoie UNIQUEMENT le JSON layout modifié complet, sans markdown."
    )

    try:
        rep = await ia_client.appeler(
            prompt=prompt_modif, mode=ModeIA.ANALYSE,
            forcer_modele=ModelePrioritaire.CLAUDE_OPUS,
            json_attendu=True, max_tokens_override=32000, utiliser_cache=False,
        )
    except Exception as e:
        logger.error(f"[Freeform/Modifier] LLM échec : {e}")
        raise HTTPException(502, f"Modification LLM échouée : {str(e)[:200]}")

    try:
        await debiter_llm(
            current_user.user_id,
            modele=getattr(rep, "modele_utilise", "claude"),
            tokens_input=int(getattr(rep, "tokens_input", 0) or 0),
            tokens_output=int(getattr(rep, "tokens_output", 0) or 0),
            module="infographie",
        )
    except Exception:
        pass

    raw = (rep.contenu or "").strip()
    try:
        layout_modifie = _json.loads(raw)
    except _json.JSONDecodeError:
        m = _re.search(r"\{[\s\S]*\}", raw)
        if not m:
            raise HTTPException(502, "LLM n'a pas produit de JSON layout parseable")
        try:
            layout_modifie = _json.loads(m.group())
        except Exception as e:
            raise HTTPException(502, f"Layout modifié invalide : {str(e)[:200]}")

    try:
        pdf_bytes = await freeform_layout.rendre_pdf_depuis_json(layout_modifie, medias={})
    except Exception as e:
        logger.error(f"[Freeform/Modifier] Render échec : {e}")
        raise HTTPException(500, f"Rendu PDF échoué : {str(e)[:200]}")

    # CMYK + PDF/X-1a (mêmes utils que /generer)
    try:
        from modules.bureau.pdf_print_ready import convertir_rgb_to_cmyk, convertir_en_pdf_x1a
        cmyk_bytes = convertir_rgb_to_cmyk(pdf_bytes, icc_name="fogra39")
        if cmyk_bytes:
            pdf_bytes = cmyk_bytes
        fmt = layout_modifie.get("format_mm") or [210, 297]
        x1a = convertir_en_pdf_x1a(
            pdf_bytes, titre=layout_modifie.get("titre", "Visuel modifié"),
            format_trim_mm=(float(fmt[0]), float(fmt[1])),
            bleed_mm=float(layout_modifie.get("bleed_mm", 3.0)),
            creator="Yukpo Freeform (modif)",
            profil_icc="fogra39", surimpression_noir=True,
        )
        if x1a:
            pdf_bytes = x1a
    except Exception as _e_x1a:
        logger.warning(f"[Freeform/Modifier] post-process échoué : {_e_x1a}")

    fichier_id_nouveau = f"bureau_freeform_{current_user.user_id}_modif_{int(_time.time())}.pdf"
    (_DATA_DIR / fichier_id_nouveau).write_bytes(pdf_bytes)

    try:
        await debiter_forfait(
            current_user.user_id, type_forfait="designerpro_modification",
            multiplicateur=1.5, module="infographie",
        )
    except Exception:
        pass

    # Maj session avec le NOUVEAU layout (l'user pourra modifier à nouveau)
    try:
        await _bs.update_session_apres_generation(
            user_id=current_user.user_id, pipeline="freeform",
            fichier_id=fichier_id_nouveau,
            brief=f"[modif] {demande.instructions[:300]}",
            layout_json=layout_modifie,
        )
    except Exception as _e_sess:
        logger.debug(f"[Freeform/Modifier/Session] : {_e_sess}")

    return {
        "ok": True,
        "fichier_id": fichier_id_nouveau,
        "modifie_depuis": demande.fichier_id,
        "nb_pages": len(layout_modifie.get("pages") or []),
        "taille_octets": len(pdf_bytes),
        "download_url": f"/api/v1/bureau/documents/{fichier_id_nouveau}",
        "print_ready": "PDF/X-1a:2001",
    }
