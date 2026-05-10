"""
Bureau Infographie Pro — Endpoints pour projets multi-page + médiathèque utilisateur.

Endpoints :
  GET    /api/v1/bureau/infographie-pro/projets               — Catalogue projets multi-page
  GET    /api/v1/bureau/infographie-pro/template/{template_id} — Description d'un template page

  POST   /api/v1/bureau/infographie-pro/medias                — Upload média (session ou compte)
  GET    /api/v1/bureau/infographie-pro/medias                — Liste médias d'un user/session
  DELETE /api/v1/bureau/infographie-pro/medias/{media_id}     — Supprime un média

  POST   /api/v1/bureau/infographie-pro/generer               — Brief → projet IA → PDF + PNG
  POST   /api/v1/bureau/infographie-pro/generer-auto          — IA détecte type projet (brief libre)
  POST   /api/v1/bureau/infographie-pro/modifier              — Modif projet existant via instructions
  GET    /api/v1/bureau/infographie-pro/projet/{projet_id}    — Récupère JSON projet (pour édition)
"""
import base64
import json
import logging
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.auth import TokenData, get_current_user

logger = logging.getLogger("yukpo_assurance.api.bureau_infographie_pro")
router = APIRouter()

_DATA_DIR = Path(__file__).parent.parent / "data" / "generated" / "bureau"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_PROJETS_JSON_DIR = Path(__file__).parent.parent / "data" / "generated" / "designerpro_projets"
_PROJETS_JSON_DIR.mkdir(parents=True, exist_ok=True)


# ─── Modèles Pydantic ─────────────────────────────────────────────────────────

class ProfilDesigner(BaseModel):
    metier: Optional[str] = None
    secteur: Optional[str] = None
    nom_organisation: Optional[str] = None
    audience: Optional[str] = None
    ton: Optional[str] = None
    couleur_primaire_hex: Optional[str] = None
    couleurs_accents_hex: Optional[list[str]] = None


class DemandeProjetPro(BaseModel):
    cle_projet: str = Field(..., description="Clé du projet (livret_deces_8p, brochure_corporate_4p, ...)")
    brief: str = Field(..., min_length=10)
    pays: str = Field(default="CM")
    langue: str = Field(default="fr", description="fr|en|ar|es|pt — langue de rédaction")
    profil: Optional[ProfilDesigner] = None
    medias_refs: Optional[list[str]] = Field(default=None,
        description="Références médias session/compte ('session:abc123' ou 'compte:def456')")
    export_cmyk: bool = Field(default=True)
    directives_visuelles: Optional[dict] = Field(default=None,
        description="Curseurs UI : creativite, densite_texte, importance_images, elegance (0–100)")
    mode_visuel: str = Field(default="sans",
        description="'sans' | 'standard' (Flux schnell) | 'premium' (Flux dev) | 'ultra' (Flux Pro Ultra) | 'ultra_plus' (ensemble Flux+Recraft+Ideogram, vision pick)")
    # Sprint 1.6 — IP-Adapter + Brand LoRA
    reference_style_ref: Optional[str] = Field(default=None,
        description="Réf. médiathèque ('session:abc' ou 'compte:def') vers une image de style → injectée via Flux IP-Adapter (modes ultra/premium/ultra_plus)")
    reference_strength: float = Field(default=0.65, ge=0.0, le=1.0,
        description="Force de l'IP-Adapter (0=ignore, 1=copie fidèle)")
    brand_lora_id: Optional[str] = Field(default=None,
        description="ID d'un Brand LoRA entraîné de l'organisation (mode premium uniquement)")
    brand_lora_scale: float = Field(default=0.85, ge=0.0, le=1.5,
        description="Force d'application du LoRA (0.6=subtil, 1.2=marqué)")


class DemandeAutoPro(BaseModel):
    """Génération auto : l'IA choisit elle-même le projet/format selon le brief."""
    brief: str = Field(..., min_length=10)
    pays: str = Field(default="CM")
    langue: str = Field(default="fr")
    profil: Optional[ProfilDesigner] = None
    medias_refs: Optional[list[str]] = None
    cle_projet_hint: Optional[str] = Field(default=None,
        description="Hint optionnel (l'IA peut le suivre ou s'en écarter selon le brief)")
    export_cmyk: bool = Field(default=True)
    directives_visuelles: Optional[dict] = None
    mode_visuel: str = Field(default="sans")


class DemandeModifierProjet(BaseModel):
    projet_id: str = Field(..., description="ID JSON du projet existant à modifier")
    instructions: str = Field(..., min_length=5)
    medias_refs_supplementaires: Optional[list[str]] = None
    pays: str = Field(default="CM")
    directives_visuelles: Optional[dict] = None
    mode_visuel: str = Field(default="sans")


# ─── Sprint 1.4 — WeasyPrint render (HTML/CSS3 → PDF) ────────────────────────


class DemandeRenderHTML(BaseModel):
    """Rend du HTML+CSS via WeasyPrint (Sprint 1.4)."""
    html: str = Field(..., min_length=20,
        description="Document HTML complet (peut contenir <style> embedded)")
    css: Optional[str] = Field(default=None,
        description="Feuille de styles additionnelle (optionnel)")
    base_url: Optional[str] = Field(default=None,
        description="URL de base pour résoudre images/fonts externes")


@router.post("/render-html", tags=["Bureau — Designer Pro"])
async def render_html_weasyprint(
    demande: DemandeRenderHTML,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Sprint 1.4 — Rendu HTML/CSS3 → PDF via WeasyPrint.
    Permet au LLM (ou à l'user expert) de générer des compositions modernes
    (CSS Grid bento, gradients, blend modes) impossibles en ReportLab pur.

    Coût : forfait `designerpro_html_render` ~3 FCFA/page (compute uniquement).
    """
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde, debiter_forfait,
    )
    try:
        from modules.bureau import infographe_weasyprint as wp
    except Exception as e:
        raise HTTPException(503, f"WeasyPrint non disponible : {e}")
    if not wp.is_available():
        raise HTTPException(503,
            "WeasyPrint non installé sur ce déploiement (deps Cairo/Pango). "
            "Passer en mode ReportLab via /generer.")

    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "infographie")
    if not autorise:
        raise HTTPException(403, msg)
    ok_solde, restants, _ = await verifier_solde(current_user.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")

    try:
        pdf_bytes = wp.rendre_html_to_pdf(
            html=demande.html, css=demande.css, base_url=demande.base_url,
        )
    except Exception as e:
        logger.error(f"[WeasyPrint render] {e}", exc_info=True)
        raise HTTPException(500, f"Échec rendu WeasyPrint : {e}")

    try:
        await debiter_forfait(
            current_user.user_id, "designerpro_html_render",
            module="infographie", multiplicateur=1.0,
        )
    except Exception:
        pass

    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
    return {
        "ok": True,
        "engine": "weasyprint",
        "pdf_base64": pdf_b64,
        "size_kb": round(len(pdf_bytes) / 1024, 1),
    }


@router.get("/render-html/demo", tags=["Bureau — Designer Pro"])
async def render_html_demo(
    current_user: TokenData = Depends(get_current_user),
):
    """Demo WeasyPrint : composition bento A4 (sans LLM)."""
    try:
        from modules.bureau import infographe_weasyprint as wp
    except Exception as e:
        raise HTTPException(503, f"WeasyPrint non disponible : {e}")
    if not wp.is_available():
        raise HTTPException(503, "WeasyPrint non installé")
    pdf_bytes = wp.render_bento_demo()
    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
    return {
        "ok": True, "engine": "weasyprint", "demo": "bento",
        "pdf_base64": pdf_b64, "size_kb": round(len(pdf_bytes) / 1024, 1),
    }


# ─── Sprint 1.6 — Brand LoRA ─────────────────────────────────────────────────


class DemandeEntrainerLora(BaseModel):
    """Lance l'entraînement d'un Brand LoRA pour l'organisation."""
    label: str = Field(..., min_length=2, max_length=120,
        description="Nom du LoRA (ex: 'ACME hiver 2026')")
    trigger_word: str = Field(..., min_length=2, max_length=80,
        description="Mot déclencheur unique injecté dans les prompts (ex: 'ACMESTYLE')")
    description: Optional[str] = Field(default=None, max_length=500)
    images_refs: list[str] = Field(..., min_length=10,
        description="≥10 références médiathèque ('session:abc'/'compte:def') vers les images d'entraînement")
    accepter_cout: bool = Field(default=False,
        description="Confirmation explicite du coût")
    # Sprint R3 — Choix du provider de training. 'replicate' (défaut) = 50× moins
    # cher que 'fal' grâce à l'écosystème ostris/flux-dev-lora-trainer.
    provider: str = Field(default="replicate", pattern="^(replicate|fal)$",
        description="'replicate' (4 000 FCFA, recommandé) ou 'fal' (200 000 FCFA, legacy)")


class ReponseLora(BaseModel):
    lora_id: str
    statut: str
    label: str
    trigger_word: str
    lora_url: Optional[str] = None
    nb_images_train: int
    cout_paye_fcfa: int
    cree_le: str
    erreur: Optional[str] = None


# Coûts training selon provider (Sprint R3)
#   - fal.ai      : ~$200 réel = ~120 000 FCFA → user paie 200 000 FCFA (marge 1.7×)
#   - Replicate   : ~$5 réel = ~3 000 FCFA → user paie 4 000 FCFA (marge 1.3× loss-leader B2B)
_COUT_LORA_TRAINING_FCFA_FAL = 200_000
_COUT_LORA_TRAINING_FCFA_REPLICATE = 4_000


def _cout_training_par_provider(provider: str) -> int:
    return _COUT_LORA_TRAINING_FCFA_REPLICATE if provider == "replicate" else _COUT_LORA_TRAINING_FCFA_FAL


@router.get("/brand-lora", response_model=list[ReponseLora], tags=["Bureau — Designer Pro"])
async def lister_brand_loras(current_user: TokenData = Depends(get_current_user)):
    """Liste les Brand LoRA actifs de l'organisation de l'utilisateur."""
    from core.database import async_session_maker, BrandLoraDB
    from sqlalchemy import select
    cid = getattr(current_user, "compagnie_id", None) or 1
    async with async_session_maker() as db:
        rows = (await db.execute(
            select(BrandLoraDB).where(
                BrandLoraDB.compagnie_id == cid, BrandLoraDB.actif == True  # noqa
            ).order_by(BrandLoraDB.cree_le.desc())
        )).scalars().all()
    return [
        ReponseLora(
            lora_id=r.lora_id, statut=r.statut, label=r.label,
            trigger_word=r.trigger_word, lora_url=r.lora_url,
            nb_images_train=r.nb_images_train, cout_paye_fcfa=r.cout_paye_fcfa,
            cree_le=r.cree_le.isoformat(), erreur=r.erreur,
        )
        for r in rows
    ]


@router.post("/brand-lora/entrainer", response_model=ReponseLora, tags=["Bureau — Designer Pro"])
async def entrainer_brand_lora(
    demande: DemandeEntrainerLora,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Lance l'entraînement d'un Brand LoRA via fal-ai/flux-lora-fast-training.
    Coût ~200 000 FCFA débité immédiatement (training non-remboursable).
    Le LoRA est ensuite réutilisable à l'infini par toute l'organisation.
    """
    import uuid
    from datetime import datetime
    from core.database import async_session_maker, BrandLoraDB
    from modules.bureau import mediatheque_session as msm
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde, debiter_forfait,
    )

    cout_fcfa = _cout_training_par_provider(demande.provider)
    if not demande.accepter_cout:
        raise HTTPException(
            400,
            f"Tu dois cocher 'accepter_cout' pour confirmer le débit de "
            f"{cout_fcfa} FCFA (training non-remboursable, provider={demande.provider})."
        )

    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "infographie")
    if not autorise:
        raise HTTPException(403, msg)
    ok_solde, restants, _ = await verifier_solde(current_user.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")

    # Résolution + lecture des images training
    session_id = f"chat_{current_user.user_id}"
    try:
        medias = msm.resoudre_refs(demande.images_refs, str(current_user.user_id), session_id)
    except Exception as e:
        raise HTTPException(400, f"Médias inaccessibles : {e}")
    if len(medias) < 10:
        raise HTTPException(400, f"Au moins 10 images valides requises (reçu {len(medias)})")

    cid = getattr(current_user, "compagnie_id", None) or 1
    lora_id = str(uuid.uuid4())

    # Création row "pending" + débit immédiat
    async with async_session_maker() as db:
        row = BrandLoraDB(
            lora_id=lora_id, compagnie_id=cid,
            user_id_createur=current_user.user_id,
            label=demande.label, trigger_word=demande.trigger_word,
            description=demande.description, statut="pending",
            nb_images_train=len(medias), cout_paye_fcfa=cout_fcfa,
            actif=True,
        )
        db.add(row)
        await db.commit()

    # Débit du forfait training (Sprint R3 — montants spécifiques par provider)
    try:
        forfait_key = ("designerpro_brand_lora_training_replicate"
                       if demande.provider == "replicate"
                       else "designerpro_brand_lora_training")
        await debiter_forfait(
            current_user.user_id, forfait_key,
            module="infographie",
            multiplicateur=float(cout_fcfa) if demande.provider == "fal" else 1.0,
            # Replicate : forfait = 4000 FCFA direct (multiplicateur=1)
            # fal.ai   : forfait = 1 FCFA × 200_000 = 200_000 FCFA
        )
    except Exception as e:
        logger.warning(f"[Brand LoRA] débit forfait : {e}")

    # Sprint R3 — Lancement training selon provider choisi
    import asyncio as _asyncio
    if demande.provider == "replicate":
        _asyncio.create_task(_lancer_training_lora_replicate_background(
            lora_id, list(medias.values()), demande.trigger_word,
        ))
    else:
        _asyncio.create_task(_lancer_training_lora_background(
            lora_id, list(medias.values()), demande.trigger_word,
        ))

    return ReponseLora(
        lora_id=lora_id, statut="pending", label=demande.label,
        trigger_word=demande.trigger_word, lora_url=None,
        nb_images_train=len(medias), cout_paye_fcfa=cout_fcfa,
        cree_le=datetime.utcnow().isoformat(), erreur=None,
    )


async def _lancer_training_lora_replicate_background(
    lora_id: str, medias: list, trigger_word: str,
):
    """Sprint R3 — Training Brand LoRA via Replicate (ostris/flux-dev-lora-trainer).
    50× moins cher que fal.ai. Upload zip → poll → stocke lora_url quand prêt."""
    import io
    import zipfile
    from datetime import datetime
    from core.database import async_session_maker, BrandLoraDB
    from sqlalchemy import select
    from modules.bureau import mediatheque_session as msm
    from modules.bureau import replicate_client as rc

    async def _set(statut: str, **kwargs):
        async with async_session_maker() as db:
            row = (await db.execute(
                select(BrandLoraDB).where(BrandLoraDB.lora_id == lora_id)
            )).scalar_one_or_none()
            if not row:
                return
            row.statut = statut
            for k, v in kwargs.items():
                setattr(row, k, v)
            await db.commit()

    if not rc.is_available():
        await _set("failed", erreur="REPLICATE_API_TOKEN non configuré",
                   training_fini=datetime.utcnow())
        return

    try:
        await _set("training", training_demarre=datetime.utcnow())
        # Replicate exige un ZIP d'images uploadé sur une URL publique.
        # Stratégie : on construit le ZIP, on l'upload sur Replicate via leur
        # files API (POST /v1/files), on récupère l'URL du fichier, puis on
        # lance le training avec cette URL.
        zip_buf = io.BytesIO()
        nb_ok = 0
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, m in enumerate(medias[:30]):
                try:
                    b = msm.lire_bytes(m)
                    ext = "png" if (m.mime or "").endswith("png") else "jpg"
                    zf.writestr(f"img_{i:03d}.{ext}", b)
                    nb_ok += 1
                except Exception as e:
                    logger.warning(f"[Brand LoRA Replicate {lora_id}] img {m.media_id} ignorée : {e}")
        if nb_ok < 10:
            await _set("failed", erreur=f"Seulement {nb_ok} images valides (min 10)",
                       training_fini=datetime.utcnow())
            return
        zip_bytes = zip_buf.getvalue()

        # Upload sur Replicate Files API
        import httpx
        from config.settings import settings
        files_url = "https://api.replicate.com/v1/files"
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                files_url,
                files={"content": ("training_set.zip", zip_bytes, "application/zip")},
                headers={"Authorization": f"Bearer {settings.REPLICATE_API_TOKEN}"},
            )
        if r.status_code not in (200, 201):
            await _set("failed", erreur=f"Replicate upload zip HTTP {r.status_code}: {r.text[:200]}",
                       training_fini=datetime.utcnow())
            return
        zip_url = r.json().get("urls", {}).get("get") or r.json().get("url")
        if not zip_url:
            await _set("failed", erreur="Replicate upload : pas d'URL retournée",
                       training_fini=datetime.utcnow())
            return

        result = await rc.entrainer_lora(
            images_zip_url=zip_url, trigger_word=trigger_word,
            steps=1000, lora_rank=16,
        )
        if result["status"] == "succeeded" and result.get("lora_url"):
            await _set("ready", lora_url=result["lora_url"],
                       training_fini=datetime.utcnow())
            logger.info(f"[Brand LoRA Replicate {lora_id}] OK → {result['lora_url']}")
        else:
            await _set("failed", erreur=(result.get("error") or "training échoué")[:500],
                       training_fini=datetime.utcnow())
    except Exception as e:
        logger.error(f"[Brand LoRA Replicate {lora_id}] exception : {e}", exc_info=True)
        await _set("failed", erreur=str(e)[:500], training_fini=datetime.utcnow())


async def _lancer_training_lora_background(lora_id: str, medias: list, trigger_word: str):
    """Tâche async : appelle fal-ai/flux-lora-fast-training, attend la fin,
    met à jour la row Brand LoRA avec l'URL résultante (ou erreur)."""
    import httpx
    from datetime import datetime
    from core.database import async_session_maker, BrandLoraDB
    from sqlalchemy import select
    from config.settings import settings
    from modules.bureau import mediatheque_session as msm
    import base64 as _b64

    async def _set(statut: str, **kwargs):
        async with async_session_maker() as db:
            row = (await db.execute(
                select(BrandLoraDB).where(BrandLoraDB.lora_id == lora_id)
            )).scalar_one_or_none()
            if not row:
                return
            row.statut = statut
            for k, v in kwargs.items():
                setattr(row, k, v)
            await db.commit()

    if not settings.FAL_KEY:
        await _set("failed", erreur="FAL_KEY non configuré", training_fini=datetime.utcnow())
        return

    try:
        await _set("training", training_demarre=datetime.utcnow())
        # Préparer les images en data URLs (fal-ai accepte un ZIP URL OU une liste de data URLs)
        images_data: list[str] = []
        for m in medias[:30]:  # cap à 30 images max (training plus long au-delà)
            try:
                b = msm.lire_bytes(m)
                images_data.append(
                    f"data:{m.mime or 'image/png'};base64,{_b64.b64encode(b).decode('ascii')}"
                )
            except Exception as e:
                logger.warning(f"[Brand LoRA {lora_id}] image {m.media_id} ignorée : {e}")
        if len(images_data) < 10:
            await _set("failed", erreur=f"Lecture images : {len(images_data)} valides (min 10)",
                       training_fini=datetime.utcnow())
            return

        url = "https://fal.run/fal-ai/flux-lora-fast-training"
        payload = {
            "images_data_url": images_data[0],   # fallback : 1ère image si pas de zip
            "images_urls": images_data,           # liste complète
            "trigger_word": trigger_word,
            "create_masks": True,
            "steps": 1000,
            "is_style": True,
        }
        headers = {"Authorization": f"Key {settings.FAL_KEY}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=1800.0) as client:
            r = await client.post(url, json=payload, headers=headers)
        if r.status_code != 200:
            await _set("failed", erreur=f"fal.ai HTTP {r.status_code}: {r.text[:200]}",
                       training_fini=datetime.utcnow())
            return
        data = r.json()
        # fal.ai renvoie typiquement {"diffusers_lora_file": {"url": "..."}}
        lora_url = (
            (data.get("diffusers_lora_file") or {}).get("url")
            or data.get("lora_url")
            or (data.get("config_file") or {}).get("url")
        )
        if not lora_url:
            await _set("failed", erreur="fal.ai : pas d'URL LoRA dans réponse",
                       training_fini=datetime.utcnow())
            return
        await _set("ready", lora_url=lora_url, training_fini=datetime.utcnow())
        logger.info(f"[Brand LoRA {lora_id}] training OK → {lora_url}")
    except Exception as e:
        logger.error(f"[Brand LoRA {lora_id}] training exception : {e}", exc_info=True)
        await _set("failed", erreur=str(e)[:500], training_fini=datetime.utcnow())


@router.delete("/brand-lora/{lora_id}", tags=["Bureau — Designer Pro"])
async def supprimer_brand_lora(
    lora_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Désactive un Brand LoRA (soft-delete : actif=False)."""
    from core.database import async_session_maker, BrandLoraDB
    from sqlalchemy import select
    cid = getattr(current_user, "compagnie_id", None) or 1
    async with async_session_maker() as db:
        row = (await db.execute(
            select(BrandLoraDB).where(
                BrandLoraDB.lora_id == lora_id, BrandLoraDB.compagnie_id == cid
            )
        )).scalar_one_or_none()
        if not row:
            raise HTTPException(404, "LoRA introuvable")
        row.actif = False
        await db.commit()
    return {"ok": True, "lora_id": lora_id}


# ─── Médiathèque ──────────────────────────────────────────────────────────────

@router.post("/medias", tags=["Bureau — Designer Pro"])
async def uploader_media(
    fichier: UploadFile = File(...),
    portee: str = Form("session", description="'session' (volatile 24h) | 'compte' (persistant)"),
    categorie: str = Form(..., description="photo|illustration|scan|qr|icone (session) ou logo|banniere|signature|cachet|filigrane|tampon (compte)"),
    label: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None, description="ID de session — requis si portee='session'"),
    current_user: TokenData = Depends(get_current_user),
):
    """Upload un média dans la médiathèque utilisateur."""
    from modules.bureau import mediatheque_session as msm
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde, debiter_forfait,
    )

    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "infographie")
    if not autorise:
        raise HTTPException(403, msg)
    ok_solde, restants, _ = await verifier_solde(current_user.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")

    if portee == "session":
        if not session_id:
            raise HTTPException(400, "session_id requis pour portee='session'")
        owner_id = session_id
    elif portee == "compte":
        owner_id = str(current_user.user_id)
    else:
        raise HTTPException(400, "portee doit être 'session' ou 'compte'")

    contenu = await fichier.read()
    mime = fichier.content_type or "application/octet-stream"

    try:
        media = msm.ajouter_media(
            portee=portee,
            owner_id=owner_id,
            contenu=contenu,
            nom_fichier=fichier.filename or "upload",
            mime=mime,
            categorie=categorie,
            label=label,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"[Designer Pro/Médias] Upload échoué : {e}")
        raise HTTPException(500, "Upload échoué")

    try:
        await debiter_forfait(current_user.user_id, "designerpro_media_upload",
                              module="infographie")
    except Exception as _e_debit:
        logger.warning(f"[Designer Pro/Media] D\u00e9bit upload non bloquant : {_e_debit}")

    return {
        "ref": f"{media.portee}:{media.media_id}",
        "media_id": media.media_id,
        "portee": media.portee,
        "categorie": media.categorie,
        "label": media.label,
        "mime": media.mime,
        "dimensions_px": [media.largeur_px, media.hauteur_px],
        "couleur_dominante": media.couleur_dominante_hex,
        "taille_bytes": media.taille_bytes,
        "expire_le": media.expire_le,
    }


@router.get("/medias", tags=["Bureau — Designer Pro"])
async def lister_medias(
    portee: str = "session",
    session_id: Optional[str] = None,
    categorie: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
):
    from modules.bureau import mediatheque_session as msm
    if portee == "session":
        if not session_id:
            raise HTTPException(400, "session_id requis pour portee='session'")
        owner_id = session_id
    else:
        owner_id = str(current_user.user_id)
    medias = msm.lister_medias(portee, owner_id, categorie)
    return {
        "medias": [
            {
                "ref": f"{m.portee}:{m.media_id}",
                "media_id": m.media_id,
                "portee": m.portee,
                "categorie": m.categorie,
                "label": m.label,
                "nom_fichier_origine": m.nom_fichier_origine,
                "mime": m.mime,
                "dimensions_px": [m.largeur_px, m.hauteur_px],
                "couleur_dominante": m.couleur_dominante_hex,
                "taille_bytes": m.taille_bytes,
                "cree_le": m.cree_le,
                "expire_le": m.expire_le,
            }
            for m in medias
        ],
        "total": len(medias),
    }


@router.get("/medias/{media_id}/contenu", tags=["Bureau — Designer Pro"])
async def telecharger_media(
    media_id: str,
    portee: str = "session",
    session_id: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Sert le contenu binaire d'un média (preview thumbnail dans le frontend)."""
    from modules.bureau import mediatheque_session as msm
    owner_id = session_id if portee == "session" else str(current_user.user_id)
    if portee == "session" and not session_id:
        raise HTTPException(400, "session_id requis")
    media = msm.recuperer_media(portee, owner_id, media_id)
    if not media:
        raise HTTPException(404, "Média introuvable ou expiré")
    try:
        contenu = msm.lire_bytes(media)
    except Exception:
        raise HTTPException(404, "Fichier média introuvable sur disque")
    return Response(content=contenu, media_type=media.mime)


@router.delete("/medias/{media_id}", tags=["Bureau — Designer Pro"])
async def supprimer_media(
    media_id: str,
    portee: str = "session",
    session_id: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
):
    from modules.bureau import mediatheque_session as msm
    owner_id = session_id if portee == "session" else str(current_user.user_id)
    if portee == "session" and not session_id:
        raise HTTPException(400, "session_id requis")
    ok = msm.supprimer_media(portee, owner_id, media_id)
    if not ok:
        raise HTTPException(404, "Média introuvable")
    return {"supprime": True}


# ─── Catalogue projets ────────────────────────────────────────────────────────

@router.get("/projets", tags=["Bureau — Designer Pro"])
async def lister_projets():
    """Catalogue des projets multi-page disponibles."""
    from modules.bureau import gabarits_livret as catalog
    return {"projets": catalog.lister_projets()}


@router.get("/template/{template_id}", tags=["Bureau — Designer Pro"])
async def detail_template(template_id: str):
    """Détail d'un template de page (slots, ambiance)."""
    from modules.bureau.gabarits_livret import PAGE_TEMPLATES
    if template_id not in PAGE_TEMPLATES:
        raise HTTPException(404, "Template inconnu")
    return PAGE_TEMPLATES[template_id]


# ─── Génération projet ────────────────────────────────────────────────────────

def _persister_projet_pro(user_id, cle_projet: str, ts: int, resultat) -> dict:
    """Sauvegarde tous les artefacts du projet (PDF, CMJN, PNG par page) sur disque
    avec le pattern de nommage compatible 'Mes Documents' (`bureau_designerpro_{uid}_...`)."""
    base = f"bureau_designerpro_{user_id}_{cle_projet}_{ts}"
    out = {
        "pdf_id": None, "pdf_base64": None,
        "pdf_cmyk_id": None, "pdf_cmyk_base64": None,
        "pages_png_ids": [], "pages_png_base64": [],
        "pages_png_hd_ids": [],
        "projet_json_id": None,
    }
    if resultat.pdf_bytes:
        fid = f"{base}.pdf"
        (_DATA_DIR / fid).write_bytes(resultat.pdf_bytes)
        out["pdf_id"] = fid
        out["pdf_base64"] = base64.b64encode(resultat.pdf_bytes).decode()
    if resultat.pdf_cmyk_bytes:
        fid = f"{base}_cmyk.pdf"
        (_DATA_DIR / fid).write_bytes(resultat.pdf_cmyk_bytes)
        out["pdf_cmyk_id"] = fid
        out["pdf_cmyk_base64"] = base64.b64encode(resultat.pdf_cmyk_bytes).decode()
    for idx, png in enumerate(resultat.pages_png or []):
        if not png:
            continue
        fid = f"{base}_p{idx+1}.png"
        (_DATA_DIR / fid).write_bytes(png)
        out["pages_png_ids"].append(fid)
        out["pages_png_base64"].append(base64.b64encode(png).decode())
    for idx, png in enumerate(resultat.pages_png_hd or []):
        if not png or png == (resultat.pages_png[idx] if idx < len(resultat.pages_png) else None):
            continue
        fid = f"{base}_p{idx+1}_hd.png"
        (_DATA_DIR / fid).write_bytes(png)
        out["pages_png_hd_ids"].append(fid)
    # JSON projet (pour modif ultérieure via chat)
    if resultat.projet:
        proj_dict = _projet_en_dict(resultat.projet)
        proj_id = f"{base}.json"
        (_PROJETS_JSON_DIR / proj_id).write_text(
            json.dumps(proj_dict, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        out["projet_json_id"] = proj_id
    return out


def _projet_en_dict(projet) -> dict:
    return {
        "cle_projet": projet.cle_projet,
        "titre": projet.titre,
        "palette": projet.palette,
        "palette_custom": projet.palette_custom,
        "polices": projet.polices,
        "langue": projet.langue,
        "medias_refs": projet.medias_refs,
        "pages": [
            {
                "numero": p.numero,
                "template_id": p.template_id,
                "palette_override": p.palette_override,
                "notes_ia": p.notes_ia,
                "zones": [
                    {"slot_id": z.slot_id, "type": z.type,
                     "contenu": z.contenu, "style": z.style}
                    for z in p.zones
                ],
            } for p in projet.pages
        ],
        "meta": projet.meta,
    }


def _projet_depuis_dict(d: dict):
    from modules.bureau.infographe_pro import ProjetInfographie, Page, Zone
    pages = []
    for p in d.get("pages", []):
        zones = [Zone(slot_id=z["slot_id"], type=z["type"],
                      contenu=z.get("contenu", {}) or {}, style=z.get("style", {}) or {})
                 for z in p.get("zones", [])]
        pages.append(Page(
            numero=int(p["numero"]),
            template_id=p["template_id"],
            zones=zones,
            palette_override=p.get("palette_override"),
            notes_ia=p.get("notes_ia"),
        ))
    return ProjetInfographie(
        cle_projet=d["cle_projet"],
        titre=d["titre"],
        palette=d.get("palette", "classique"),
        palette_custom=d.get("palette_custom"),
        pages=pages,
        medias_refs=d.get("medias_refs", []) or [],
        polices=d.get("polices", {}) or {},
        langue=d.get("langue", "fr"),
        meta=d.get("meta", {}) or {},
    )


def _serialiser_projet_pour_reponse(projet) -> dict:
    return {
        "cle_projet": projet.cle_projet,
        "titre": projet.titre,
        "palette": projet.palette,
        "langue": projet.langue,
        "nombre_pages": len(projet.pages),
        "pages_resume": [
            {"numero": p.numero, "template": p.template_id,
             "nb_zones": len(p.zones)}
            for p in projet.pages
        ],
    }


@router.post("/generer", tags=["Bureau — Designer Pro"])
async def generer_projet(
    demande: DemandeProjetPro,
    current_user: TokenData = Depends(get_current_user),
):
    from modules.bureau import gabarits_livret as catalog
    from modules.bureau.infographe_pro import generer_projet as _gen
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde, debiter_llm, debiter_forfait,
    )

    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "infographie")
    if not autorise:
        raise HTTPException(403, msg)
    ok_solde, restants, _ = await verifier_solde(current_user.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")
    if demande.cle_projet not in catalog.PROJETS_INFOGRAPHIE:
        raise HTTPException(400, f"Projet inconnu : {demande.cle_projet}")

    profil_dict = demande.profil.model_dump(exclude_none=True) if demande.profil else None
    session_id = f"chat_{current_user.user_id}"  # session par défaut = par user

    # Sprint 1.6 — résolution Brand LoRA si demandé
    lora_url: Optional[str] = None
    if demande.brand_lora_id:
        try:
            from core.database import async_session_maker, BrandLoraDB
            from sqlalchemy import select
            async with async_session_maker() as _db:
                row = (await _db.execute(
                    select(BrandLoraDB).where(BrandLoraDB.lora_id == demande.brand_lora_id)
                )).scalar_one_or_none()
                if row and row.statut == "ready" and row.actif:
                    cid = getattr(current_user, "compagnie_id", None)
                    if cid is None or row.compagnie_id == cid:
                        lora_url = row.lora_url
                    else:
                        logger.warning(f"[Designer Pro] Brand LoRA {demande.brand_lora_id} : compagnie mismatch")
                else:
                    logger.warning(f"[Designer Pro] Brand LoRA {demande.brand_lora_id} indisponible (statut={getattr(row,'statut','?')})")
        except Exception as e:
            logger.warning(f"[Designer Pro] Brand LoRA résolution échouée : {e}")

    try:
        resultat = await _gen(
            brief=demande.brief,
            cle_projet=demande.cle_projet,
            user_id=str(current_user.user_id),
            session_id=session_id,
            medias_refs=demande.medias_refs,
            pays=demande.pays,
            profil=profil_dict,
            langue=demande.langue,
            export_cmyk=demande.export_cmyk,
            directives_visuelles=demande.directives_visuelles,
            mode_visuel=demande.mode_visuel,
            reference_style_ref=demande.reference_style_ref,
            reference_strength=demande.reference_strength,
            brand_lora_url=lora_url,
            brand_lora_scale=demande.brand_lora_scale,
        )
    except Exception as e:
        logger.error(f"[Designer Pro] Génération échouée : {e}")
        raise HTTPException(500, f"Génération échouée : {e}")

    # Crédits
    try:
        meta = resultat.meta or {}
        if meta.get("tokens_input") or meta.get("tokens_output"):
            await debiter_llm(
                current_user.user_id, modele=meta.get("modele", "default"),
                tokens_input=int(meta.get("tokens_input") or 0),
                tokens_output=int(meta.get("tokens_output") or 0),
                module="infographie",
            )
        # Sprint 1.1 — Débit séparé du Layout AI (Opus 4.7) si actif
        if meta.get("layout_ai_modele") and (
            meta.get("layout_ai_tokens_input") or meta.get("layout_ai_tokens_output")
        ):
            await debiter_llm(
                current_user.user_id, modele=meta.get("layout_ai_modele", "claude-opus-4-7"),
                tokens_input=int(meta.get("layout_ai_tokens_input") or 0),
                tokens_output=int(meta.get("layout_ai_tokens_output") or 0),
                module="infographie",
            )
        # Sprint 1.2 — Débit séparé du Vision Picker Sonnet (5 archétypes)
        if meta.get("picker_modele") and (
            meta.get("picker_tokens_input") or meta.get("picker_tokens_output")
        ):
            await debiter_llm(
                current_user.user_id, modele=meta.get("picker_modele", "claude-sonnet-4-6"),
                tokens_input=int(meta.get("picker_tokens_input") or 0),
                tokens_output=int(meta.get("picker_tokens_output") or 0),
                module="infographie",
            )
        if resultat.pdf_bytes:
            # Forfait scalé sur le nombre de pages réellement produites
            # (1 FCFA × nb_pages × 20 = 20 crédits/page). Le LLM est débité
            # séparément via debiter_llm — le total reste cohérent avec la
            # complexité réelle, pas avec un prix marché arbitraire.
            nb_pages = int(resultat.meta.get("nb_pages") or 1) if resultat.meta else 1
            await debiter_forfait(
                current_user.user_id, "designerpro_creation",
                module="infographie", multiplicateur=max(1.0, float(nb_pages)),
            )
            # Forfait images IA (Flux via fal.ai) — débité par image effectivement
            # générée, selon le mode choisi par l'utilisateur. 0 image générée
            # (mode "sans" ou aucun slot image_ia produit par le LLM) → pas de
            # débit supplémentaire.
            nb_imgs = int(resultat.meta.get("nb_images_ia") or 0)
            if nb_imgs > 0:
                if demande.mode_visuel == "ultra_plus":
                    forfait_image = "designerpro_image_ultra_plus"
                elif demande.mode_visuel == "ultra":
                    forfait_image = "designerpro_image_ultra"
                elif demande.mode_visuel == "premium":
                    forfait_image = "designerpro_image_premium"
                else:
                    forfait_image = "designerpro_image_standard"
                await debiter_forfait(
                    current_user.user_id, forfait_image,
                    module="infographie", multiplicateur=float(nb_imgs),
                )
    except Exception as e:
        logger.warning(f"[Designer Pro/Crédits] {e}")

    ts = int(time.time())
    artefacts = _persister_projet_pro(current_user.user_id, demande.cle_projet, ts, resultat)

    # Enregistrement dans l'historique YukpoPro (`/pro/documents/historique`)
    # pour que l'utilisateur retrouve le visuel dans Mes Documents.
    try:
        from core.database import async_session_maker, DocumentGenereDB
        async with async_session_maker() as _db:
            _db.add(DocumentGenereDB(
                user_id=current_user.user_id,
                compagnie_id=getattr(current_user, "compagnie_id", None),
                titre=(resultat.projet.titre or demande.cle_projet)[:300] if resultat.projet else demande.cle_projet,
                type_doc="designerpro",
                fichier=artefacts.get("pdf_id"),
                contenu_source=demande.brief[:2000],
                session_id=f"designerpro_{ts}",
                meta={
                    "cle_projet": demande.cle_projet,
                    "nombre_pages": (resultat.meta or {}).get("nombre_pages"),
                    "mode_visuel": demande.mode_visuel,
                    "nb_images_ia": (resultat.meta or {}).get("nb_images_ia", 0),
                    "format_mm": (resultat.meta or {}).get("format_mm"),
                    "pdf_cmyk_id": artefacts.get("pdf_cmyk_id"),
                    "pages_png_ids": artefacts.get("pages_png_ids", []),
                    "projet_json_id": artefacts.get("projet_json_id"),
                },
            ))
            await _db.commit()
    except Exception as _e_hist:
        logger.warning(f"[Designer Pro/Historique] Sauvegarde historique non bloquante : {_e_hist}")

    # URL directe de téléchargement (utilisable depuis le frontend)
    download_url = (
        f"/api/v1/bureau/documents/{artefacts['pdf_id']}"
        if artefacts.get("pdf_id") else None
    )

    return {
        "projet": _serialiser_projet_pour_reponse(resultat.projet),
        **artefacts,
        "meta": resultat.meta,
        "download_url": download_url,
    }


# ── Génération auto (IA choisit le projet) ────────────────────────────────────

DESCRIPTIONS_PROJETS_IA = """\
- livret_deces_8p : Faire-part décès en livret 8 pages (familles, programme obsèques, plan, souvenirs, hommages)
- livret_deces_4p : Faire-part décès condensé 4 pages
- livret_mariage_4p : Faire-part mariage en livret 4 pages plié (invitation, plan, RSVP)
- carte_mariage_pliee : Carte mariage 4 faces format carte plié 105×148
- brochure_corporate_4p : Brochure entreprise 4 pages (couverture, services, témoignages, contact)
- menu_resto_4p : Menu de restaurant 4 pages (couverture, entrées, plats, dos)
- programme_culte_4p : Programme cérémonie/culte 4 pages (déroulement, chants, lectures)
- livre_photo_a4_8p : Album photo 8 pages format carré 21×21
"""


async def _detecter_projet_auto(brief: str, hint: Optional[str] = None,
                                 user_id: Optional[int] = None) -> str:
    """LLM rapide qui choisit la clé de projet la plus pertinente selon le brief.
    Si user_id fourni, débite le coût LLM (faible — ~40 tokens) pour rester équitable."""
    from core.ia_client import ia_client, ModeIA
    prompt = f"""Tu es un assistant de routing. Choisis la clé de projet la plus appropriée
parmi la liste, selon le brief utilisateur.

PROJETS DISPONIBLES :
{DESCRIPTIONS_PROJETS_IA}

BRIEF UTILISATEUR :
\"\"\"{brief[:1500]}\"\"\"

{f'HINT UTILISATEUR : {hint} (utilise-le si cohérent avec le brief, sinon ignore-le).' if hint else ''}

Retourne UNIQUEMENT la clé exacte (ex: "livret_deces_8p"), rien d'autre."""
    try:
        rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION,
                                       max_tokens_override=40, utiliser_cache=True)
        if user_id and (rep.tokens_input or rep.tokens_output):
            try:
                from modules.bureau.service_credits_bureau import debiter_llm as _dl
                await _dl(user_id, modele=rep.modele_utilise,
                          tokens_input=int(rep.tokens_input or 0),
                          tokens_output=int(rep.tokens_output or 0),
                          module="infographie")
            except Exception:
                pass
        cle = rep.contenu.strip().strip('"').strip("'").splitlines()[0].strip()
        from modules.bureau import gabarits_livret as catalog
        if cle in catalog.PROJETS_INFOGRAPHIE:
            return cle
    except Exception as e:
        logger.warning(f"[Designer Pro/Auto] Détection LLM : {e}")
    # Fallback heuristique
    msg = brief.lower()
    if "deuil" in msg or "déc" in msg or "obsèques" in msg or "memoriam" in msg:
        return "livret_deces_8p"
    if "mariage" in msg or "noces" in msg:
        return "livret_mariage_4p"
    if "menu" in msg or "restau" in msg or "carte des plats" in msg:
        return "menu_resto_4p"
    if "brochure" in msg or "plaquette" in msg or "présentation entreprise" in msg:
        return "brochure_corporate_4p"
    if "culte" in msg or "messe" in msg or "cérémonie religieuse" in msg:
        return "programme_culte_4p"
    if "album" in msg or "souvenir" in msg or "livre photo" in msg:
        return "livre_photo_a4_8p"
    return hint if hint else "brochure_corporate_4p"


# ─── Sprint 1.7 — Auto-orchestrateur LLM (analyse pré-génération) ────────────


class DemandeOrchestrer(BaseModel):
    """Sprint 1.7 — L'utilisateur saisit un prompt libre. Le LLM détecte tout."""
    prompt: str = Field(..., min_length=10,
        description="Description du besoin en langage naturel (ex: 'Je veux un flyer A5 pour la rentrée scolaire de mon école avec photos des classes')")
    pays: str = Field(default="CM")
    langue: str = Field(default="fr")
    profil: Optional[ProfilDesigner] = None
    # Sprint 1.8a — médias déjà uploadés à analyser (l'IA décide quoi en faire)
    medias_refs: Optional[list[str]] = Field(default=None,
        description="Réfs médiathèque déjà uploadées ('session:abc'/'compte:def') — l'IA analyse leur catégorie/dimensions/couleur dominante et recommande où les insérer")


class ReponseOrchestrer(BaseModel):
    """Analyse complète du besoin utilisateur — utilisée pour pré-remplir le formulaire."""
    type_projet: str = Field(..., description="'mono' (1 page : flyer/banniere/carte_visite) ou 'multi' (livret/brochure)")
    cle_projet: str = Field(..., description="Clé exacte du gabarit/projet détecté")
    label_projet: str
    description_projet: str
    confiance: float = Field(..., ge=0.0, le=1.0)
    alternatives: list[dict] = Field(default_factory=list,
        description="Top 3 alternatives crédibles : [{cle, label, score, raison}]")
    faisabilite: str = Field(..., description="'ok' | 'partielle' | 'impossible'")
    manques: list[str] = Field(default_factory=list,
        description="Éléments manquants pour une génération optimale (ex: 'photo du défunt', 'logo entreprise')")
    questions_clarification: list[str] = Field(default_factory=list,
        description="0-3 questions à poser à l'utilisateur si confiance < 0.85")
    brief_enrichi: str = Field(..., description="Brief reformulé/enrichi prêt à passer au générateur")
    mode_visuel_suggere: str = Field(default="standard",
        description="Mode IA visuelle suggéré selon ambition perçue : sans|standard|premium|ultra|ultra_plus")
    directives_visuelles_pre: dict = Field(default_factory=dict,
        description="Pré-remplissage des curseurs (creativite, densite_texte, importance_images, elegance)")
    archetype_dominant: Optional[str] = Field(default=None,
        description="Archétype de composition principal suggéré (grille_classique|asymetric|bento|fullbleed_cover|timeline_horiz)")
    cout_estime_credits: int = Field(default=0,
        description="Estimation des crédits qui seront consommés (LLM + génération + image IA)")
    # Sprint 1.8a — recommandations d'usage des médias uploadés
    recommandation_medias: list[dict] = Field(default_factory=list,
        description="Pour chaque média analysé : [{ref, role_suggere, page_cible, raison}] — l'IA dit où insérer chaque image")
    medias_manquants: list[str] = Field(default_factory=list,
        description="Types de médias attendus mais non fournis (ex: 'photo du défunt', 'logo entreprise')")
    medias_refs_actifs: list[str] = Field(default_factory=list,
        description="Sous-ensemble de medias_refs jugés pertinents par l'IA (à pré-cocher dans le formulaire)")


@router.post("/orchestrer", response_model=ReponseOrchestrer, tags=["Bureau — Designer Pro"])
async def orchestrer(
    demande: DemandeOrchestrer,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Sprint 1.7 — Auto-orchestrateur LLM : un seul prompt utilisateur en
    langage naturel. Le LLM analyse, détecte le type de projet, propose des
    alternatives, identifie les manques, suggère un mode visuel et des curseurs.

    L'utilisateur n'a pas à parcourir 30+ gabarits. Il décrit son besoin →
    l'IA fait la classification + faisabilité + pré-remplissage en 1 appel.

    Coût : ~6 cr (1 appel Haiku ~800/400 tokens).
    """
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire
    from modules.bureau import gabarits_livret as catalog_multi
    from modules.bureau.infographe import GABARITS as catalog_mono
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde, debiter_llm,
    )

    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "infographie")
    if not autorise:
        raise HTTPException(403, msg)
    ok_solde, restants, _ = await verifier_solde(current_user.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")

    # Compact catalog payload pour le LLM
    mono_compact = [
        {
            "cle": c, "label": v.get("label"),
            "categorie": v.get("categorie"),
            "format_mm": [v.get("width_mm"), v.get("height_mm")],
            "description": v.get("description", ""),
        }
        for c, v in catalog_mono.items()
    ]
    multi_compact = [
        {
            "cle": c, "label": v.get("label"),
            "categorie": v.get("categorie"),
            "format_mm": list(v.get("format_mm") or []),
            "nombre_pages": len(v.get("pages") or []),
            "description": v.get("description", ""),
        }
        for c, v in catalog_multi.PROJETS_INFOGRAPHIE.items()
    ]

    profil = demande.profil.model_dump(exclude_none=True) if demande.profil else {}

    # Sprint 1.8a — Analyse des médias déjà uploadés
    desc_medias_input: list[dict] = []
    if demande.medias_refs:
        try:
            from modules.bureau import mediatheque_session as msm
            session_id_local = f"chat_{current_user.user_id}"
            medias_resolus = msm.resoudre_refs(
                demande.medias_refs, str(current_user.user_id), session_id_local
            )
            for ref, m in medias_resolus.items():
                desc_medias_input.append({
                    "ref": ref,
                    "categorie": m.categorie,
                    "label": m.label or "",
                    "dimensions_px": [m.largeur_px, m.hauteur_px] if hasattr(m, "largeur_px") else None,
                    "couleur_dominante": getattr(m, "couleur_dominante_hex", None),
                    "portee": m.portee,
                })
        except Exception as e:
            logger.warning(f"[Orchestrer] résolution médias : {e}")

    prompt = f"""Tu es ASSISTANT D'ORCHESTRATION pour la suite Yukpo Designer Pro.
Mission : analyser le besoin de l'utilisateur en langage naturel et déterminer
EXACTEMENT le bon gabarit + paramètres optimaux à pré-remplir dans le formulaire.

L'utilisateur n'a pas envie de parcourir 30+ templates. Tu dois :
  1. Détecter le type de visuel (mono-page ou multi-page) et la clé exacte
  2. Évaluer ta confiance + proposer 2 alternatives crédibles
  3. Identifier les manques (médias/infos qui amélioreraient le résultat)
  4. Poser 0-3 questions de clarification SEULEMENT si confiance < 85%
  5. Reformuler le brief en version enrichie prête pour le générateur
  6. Suggérer mode visuel IA (sans/standard/premium/ultra/ultra_plus) selon ambition
  7. Pré-remplir les curseurs créativité/densité/images/élégance (0-100)
  8. Choisir l'archétype de composition dominant
  9. (Sprint 1.8a) ANALYSER les médias déjà uploadés : pour chaque média
     pertinent, indique son rôle attendu (couverture, portrait personne, photo
     événement, page intérieure, illustration de fond, logo, signature, etc.)
     et sur quelle page le placer. Dis aussi quels médias sont SUPERFLUS pour
     ce projet (ne pas les pré-cocher).

═══════════════════════════════════════════════════
  PROMPT UTILISATEUR
═══════════════════════════════════════════════════
\"\"\"{demande.prompt[:2000]}\"\"\"

Pays : {demande.pays}   Langue : {demande.langue}
Métier : {profil.get("metier", "(non précisé)")}
Organisation : {profil.get("nom_organisation", "(non précisée)")}

═══════════════════════════════════════════════════
  CATALOGUE MONO-PAGE (GABARITS — visuels en 1 seule page)
═══════════════════════════════════════════════════
{json.dumps(mono_compact, ensure_ascii=False)[:6000]}

═══════════════════════════════════════════════════
  CATALOGUE MULTI-PAGE (PROJETS — livrets, brochures, livres photo)
═══════════════════════════════════════════════════
{json.dumps(multi_compact, ensure_ascii=False)[:6000]}

═══════════════════════════════════════════════════
  MÉDIAS DÉJÀ UPLOADÉS PAR L'UTILISATEUR
═══════════════════════════════════════════════════
{json.dumps(desc_medias_input, ensure_ascii=False)[:4000] if desc_medias_input else "(aucun média)"}

═══════════════════════════════════════════════════
  ARCHÉTYPES DE COMPOSITION (5)
═══════════════════════════════════════════════════
- grille_classique : grille régulière, lecture linéaire (rapports, éditorial sobre)
- asymetric        : ancrage dominant + texte décalé (modernité, impact)
- bento            : grille modulaire dense (data viz, dashboard, portfolio)
- fullbleed_cover  : visuel pleine page + texte minimal (impact maximum, hero)
- timeline_horiz   : progression horizontale (parcours, étapes, story-telling)

═══════════════════════════════════════════════════
  MODES VISUELS IA
═══════════════════════════════════════════════════
- sans       : pas d'image IA (templates seuls)             — gratuit, ~10s
- standard   : Flux schnell                                 — 9 FCFA/img, ~1s
- premium    : Flux dev + variants + vision                 — 144 FCFA/img, ~10s
- ultra      : Flux Pro Ultra (cinéma)                      — 336 FCFA/img, ~15s
- ultra_plus : ensemble Flux+Recraft+Ideogram + pick auto   — 720 FCFA/img, ~25s

═══════════════════════════════════════════════════
  RÈGLES
═══════════════════════════════════════════════════
1. Choisis EXACTEMENT 1 gabarit du bon catalogue (mono OU multi).
2. Si le brief est ambigu (ex: "un visuel pour mon entreprise") → confiance basse
   + 1-3 questions ciblées + alternative la plus probable en main.
3. faisabilite = 'impossible' SEULEMENT si le brief n'a aucun lien avec un visuel
   imprimable/digital (ex: "écris-moi un poème"). Sinon 'ok' ou 'partielle'.
4. brief_enrichi = version reformulée plus structurée que celle de l'user, avec
   suggestions de champs manquants intégrées comme placeholders à compléter.
5. Curseurs : déduis du ton du brief (formel/audacieux, dense/aéré, etc.).
6. mode_visuel_suggere = "ultra_plus" si brief mentionne marque/luxe/identité forte ;
   "ultra" si visuel type photo cinématique ; "premium" si standard pro ; "standard"
   si rapide/économique ; "sans" si l'user ne veut pas d'IA visuelle (templates).

═══════════════════════════════════════════════════
  FORMAT DE SORTIE — JSON STRICT
═══════════════════════════════════════════════════
{{
  "type_projet": "mono | multi",
  "cle_projet": "cle_exacte_du_catalogue",
  "label_projet": "label affiché",
  "description_projet": "description courte",
  "confiance": 0.92,
  "alternatives": [
    {{"cle": "...", "label": "...", "score": 0.78, "raison": "..."}},
    {{"cle": "...", "label": "...", "score": 0.65, "raison": "..."}}
  ],
  "faisabilite": "ok | partielle | impossible",
  "manques": ["photo du défunt", "logo organisation", ...],
  "questions_clarification": ["Format A4 ou A5 ?", "..."],
  "brief_enrichi": "Version reformulée enrichie...",
  "mode_visuel_suggere": "premium",
  "directives_visuelles_pre": {{"creativite": 60, "densite_texte": 40,
                                 "importance_images": 75, "elegance": 80}},
  "archetype_dominant": "fullbleed_cover",
  "cout_estime_credits": 850,
  "recommandation_medias": [
    {{"ref": "session:abc", "role_suggere": "portrait principal couverture",
      "page_cible": 1, "raison": "photo verticale haute résolution adaptée"}},
    {{"ref": "compte:def", "role_suggere": "logo dos", "page_cible": 8,
      "raison": "logo entreprise pour signature finale"}}
  ],
  "medias_manquants": ["photo de groupe famille", "..."],
  "medias_refs_actifs": ["session:abc", "compte:def"]
}}

Retourne UNIQUEMENT le JSON, sans markdown ni préambule."""

    try:
        rep = await ia_client.appeler(
            prompt=prompt, mode=ModeIA.ANALYSE,
            json_attendu=True,
            forcer_modele=ModelePrioritaire.CLAUDE_HAIKU,
        )
    except Exception as e:
        logger.error(f"[Designer Pro/Orchestrer] LLM échoué : {e}")
        raise HTTPException(500, f"Orchestrateur LLM indisponible : {e}")

    try:
        data = json.loads(rep.contenu)
    except json.JSONDecodeError:
        import re
        m = re.search(r'\{.*\}', rep.contenu, re.DOTALL)
        data = json.loads(m.group()) if m else {}

    if not isinstance(data, dict) or not data.get("cle_projet"):
        raise HTTPException(500, "Orchestrateur : réponse LLM invalide")

    # Validation : la clé proposée doit exister dans le bon catalogue
    cle = data.get("cle_projet", "")
    type_proj = data.get("type_projet", "")
    if type_proj == "mono" and cle not in catalog_mono:
        # Fallback : on cherche dans multi
        if cle in catalog_multi.PROJETS_INFOGRAPHIE:
            data["type_projet"] = "multi"
        else:
            data["cle_projet"] = "flyer_a5"
            data["type_projet"] = "mono"
            data["confiance"] = min(float(data.get("confiance", 0.5)), 0.5)
    elif type_proj == "multi" and cle not in catalog_multi.PROJETS_INFOGRAPHIE:
        if cle in catalog_mono:
            data["type_projet"] = "mono"
        else:
            data["cle_projet"] = "brochure_corporate_4p"
            data["type_projet"] = "multi"
            data["confiance"] = min(float(data.get("confiance", 0.5)), 0.5)

    # Débit LLM
    try:
        await debiter_llm(
            current_user.user_id, modele=rep.modele_utilise,
            tokens_input=int(rep.tokens_input or 0),
            tokens_output=int(rep.tokens_output or 0),
            module="infographie",
        )
    except Exception:
        pass

    # Normalisation des champs requis
    return ReponseOrchestrer(
        type_projet=data.get("type_projet", "multi"),
        cle_projet=data.get("cle_projet", ""),
        label_projet=data.get("label_projet", ""),
        description_projet=data.get("description_projet", ""),
        confiance=float(data.get("confiance", 0.5)),
        alternatives=(data.get("alternatives") or [])[:3],
        faisabilite=data.get("faisabilite", "ok"),
        manques=(data.get("manques") or [])[:8],
        questions_clarification=(data.get("questions_clarification") or [])[:3],
        brief_enrichi=data.get("brief_enrichi", demande.prompt),
        mode_visuel_suggere=data.get("mode_visuel_suggere", "standard"),
        directives_visuelles_pre=data.get("directives_visuelles_pre") or {},
        archetype_dominant=data.get("archetype_dominant"),
        cout_estime_credits=int(data.get("cout_estime_credits", 500)),
        # Sprint 1.8a — médias
        recommandation_medias=(data.get("recommandation_medias") or [])[:30],
        medias_manquants=(data.get("medias_manquants") or [])[:10],
        medias_refs_actifs=(data.get("medias_refs_actifs") or [])[:30],
    )


@router.post("/generer-auto", tags=["Bureau — Designer Pro"])
async def generer_auto(
    demande: DemandeAutoPro,
    current_user: TokenData = Depends(get_current_user),
):
    """L'IA détecte automatiquement le type de projet selon le brief, puis génère."""
    cle = await _detecter_projet_auto(demande.brief, demande.cle_projet_hint,
                                       user_id=current_user.user_id)
    sub = DemandeProjetPro(
        cle_projet=cle,
        brief=demande.brief,
        pays=demande.pays,
        langue=demande.langue,
        profil=demande.profil,
        medias_refs=demande.medias_refs,
        export_cmyk=demande.export_cmyk,
        directives_visuelles=demande.directives_visuelles,
        mode_visuel=demande.mode_visuel,
    )
    res = await generer_projet(sub, current_user)
    if isinstance(res, dict):
        res["cle_projet_detectee"] = cle
    return res


# ── Modification de projet existant ───────────────────────────────────────────

@router.post("/modifier", tags=["Bureau — Designer Pro"])
async def modifier_projet(
    demande: DemandeModifierProjet,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Modifie un projet existant via instructions en langage naturel.
    L'IA reçoit le projet courant + instructions + médias supplémentaires éventuels
    et produit la nouvelle version.
    """
    from modules.bureau.infographe_pro import (
        rendre_projet_pdf, _png_par_page,
    )
    from modules.bureau import mediatheque_session as msm
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde, debiter_llm,
    )

    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "infographie")
    if not autorise:
        raise HTTPException(403, msg)
    ok_solde, restants, _ = await verifier_solde(current_user.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")

    if "/" in demande.projet_id or "\\" in demande.projet_id or ".." in demande.projet_id:
        raise HTTPException(400, "ID invalide")
    chemin = _PROJETS_JSON_DIR / demande.projet_id
    if not chemin.exists():
        raise HTTPException(404, "Projet introuvable (peut-être expiré)")
    if f"_{current_user.user_id}_" not in demande.projet_id and current_user.role != "admin":
        raise HTTPException(403, "Accès refusé")

    try:
        ancien_dict = json.loads(chemin.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(500, f"Lecture projet : {e}")

    # Charger médias référencés (anciens + supplémentaires)
    refs = list(ancien_dict.get("medias_refs", []) or [])
    refs += demande.medias_refs_supplementaires or []
    session_id = f"chat_{current_user.user_id}"
    medias = msm.resoudre_refs(refs, str(current_user.user_id), session_id)

    # Demander à l'IA d'appliquer les modifications au JSON projet
    from core.ia_client import ia_client, ModeIA
    prompt = f"""Tu es directeur artistique. Voici un projet d'infographie multi-page existant
au format JSON. L'utilisateur demande des modifications. Produis le JSON modifié EN ENTIER,
en conservant tout ce qui n'est pas concerné par les instructions et en appliquant les changements.

INSTRUCTIONS DE MODIFICATION :
\"\"\"{demande.instructions}\"\"\"

DIRECTIVES VISUELLES (curseurs 0–100) : {json.dumps(demande.directives_visuelles or {}, ensure_ascii=False)}

MÉDIATHÈQUE DISPONIBLE (refs réutilisables) :
{json.dumps([msm.descripteur_pour_ia(m) for m in medias.values()], ensure_ascii=False, indent=2)}

PROJET EXISTANT :
{json.dumps(ancien_dict, ensure_ascii=False, indent=2)}

Retourne UNIQUEMENT le nouveau JSON projet complet, sans markdown, sans commentaire."""

    try:
        rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.REDACTION,
                                       json_attendu=True)
        try:
            nouveau_dict = json.loads(rep.contenu)
        except json.JSONDecodeError:
            import re as _re
            m = _re.search(r"\{.*\}", rep.contenu, _re.DOTALL)
            nouveau_dict = json.loads(m.group()) if m else ancien_dict
    except Exception as e:
        logger.error(f"[Designer Pro/Modifier] LLM : {e}")
        raise HTTPException(500, f"Modification IA échouée : {e}")

    projet = _projet_depuis_dict(nouveau_dict)
    try:
        pdf = rendre_projet_pdf(projet, medias, "rgb")
        pdf_cmyk = rendre_projet_pdf(projet, medias, "cmyk")
    except Exception as e:
        logger.error(f"[Designer Pro/Modifier] Rendu : {e}")
        raise HTTPException(500, f"Rendu modifié : {e}")
    pages_png = _png_par_page(pdf, dpi=150)
    pages_png_hd = _png_par_page(pdf, dpi=300)

    try:
        meta = nouveau_dict.get("meta", {}) or {}
        if rep.tokens_input or rep.tokens_output:
            await debiter_llm(
                current_user.user_id, modele=rep.modele_utilise,
                tokens_input=int(rep.tokens_input or 0),
                tokens_output=int(rep.tokens_output or 0),
                module="infographie",
            )
        # Forfait modification : moitié du forfait création par page (¼ via le
        # multiplicateur 0.25). LLM débité séparément pour la modif elle-même.
        from modules.bureau.service_credits_bureau import debiter_forfait as _df
        nb_pages = 1
        try:
            nb_pages = max(1, int((projet.specification or {}).get("nb_pages") or 1))
        except Exception:
            pass
        await _df(current_user.user_id, "designerpro_modification",
                  module="infographie", multiplicateur=max(0.25 * float(nb_pages), 0.25))
    except Exception as _e_debit:
        logger.warning(f"[Designer Pro/Modifier] D\u00e9bit cr\u00e9dits non bloquant : {_e_debit}")

    # Faux ResultatProjet pour réutiliser _persister
    from modules.bureau.infographe_pro import ResultatProjet
    res = ResultatProjet(
        pdf_bytes=pdf, pdf_cmyk_bytes=pdf_cmyk,
        pages_png=pages_png, pages_png_hd=pages_png_hd,
        projet=projet,
        meta={"modifie_depuis": demande.projet_id, "instructions": demande.instructions[:200]},
    )
    ts = int(time.time())
    artefacts = _persister_projet_pro(current_user.user_id, projet.cle_projet, ts, res)

    return {
        "projet": _serialiser_projet_pour_reponse(projet),
        "modifie_depuis": demande.projet_id,
        **artefacts,
        "meta": res.meta,
    }


@router.get("/projet/{projet_id}", tags=["Bureau — Designer Pro"])
async def lire_projet_json(
    projet_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    if "/" in projet_id or "\\" in projet_id or ".." in projet_id:
        raise HTTPException(400, "ID invalide")
    chemin = _PROJETS_JSON_DIR / projet_id
    if not chemin.exists():
        raise HTTPException(404, "Projet introuvable")
    if f"_{current_user.user_id}_" not in projet_id and current_user.role != "admin":
        raise HTTPException(403, "Accès refusé")
    return json.loads(chemin.read_text(encoding="utf-8"))
