"""
Bureau Infographie — Routes FastAPI pour génération d'infographies print-ready.

Endpoints :
  GET  /api/v1/bureau/infographie/gabarits        — Liste des gabarits disponibles
  POST /api/v1/bureau/infographie/generer         — Brief → PDF print-ready + PNG preview
  POST /api/v1/bureau/infographie/generer-manuel  — Spec directe (sans IA) → PDF
  GET  /api/v1/bureau/infographie/fichier/{id}    — Télécharge PDF ou PNG
"""
import base64
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.auth import TokenData, get_current_user

logger = logging.getLogger("yukpo_assurance.api.bureau_infographie")
router = APIRouter()

_DATA_DIR = Path(__file__).parent.parent / "data" / "generated" / "bureau"
_DATA_DIR.mkdir(parents=True, exist_ok=True)


class DemandeBrief(BaseModel):
    brief: str = Field(..., min_length=10, description="Description libre du besoin en langage naturel")
    type_gabarit: str = Field(..., description="Type de gabarit (ex: flyer_a5, carte_visite, diplome)")
    pays: str = Field(default="CM")


class DemandeManuelle(BaseModel):
    type_gabarit: str
    titre: str
    sous_titre: Optional[str] = None
    corps: Optional[str] = None
    details: list[str] = Field(default_factory=list)
    palette: str = Field(default="classique", description="classique | cameroun | senegal | elegance | moderne")
    nom_organisation: Optional[str] = None
    contact: Optional[str] = None
    slogan: Optional[str] = None
    date_evenement: Optional[str] = None
    lieu: Optional[str] = None


class DemandeCustom(BaseModel):
    width_mm: float = Field(..., gt=0, le=3000, description="Largeur en mm")
    height_mm: float = Field(..., gt=0, le=3000, description="Hauteur en mm")
    bleed_mm: float = Field(default=3, ge=0, le=20, description="Fond perdu en mm")
    brief: str = Field(..., min_length=10)
    pays: str = Field(default="CM")


@router.get("/gabarits", tags=["Bureau — Infographie"])
async def lister_gabarits():
    """Retourne tous les gabarits disponibles avec leurs prix et dimensions."""
    from modules.bureau.infographe import GABARITS, PALETTES
    return {
        "gabarits": [
            {
                "cle": cle,
                "label": info["label"],
                "width_mm": info["width_mm"],
                "height_mm": info["height_mm"],
                "bleed_mm": info["bleed_mm"],
                "categorie": info["categorie"],
                "description": info["description"],
                "prix_fcfa": info["prix_fcfa"],
            }
            for cle, info in GABARITS.items()
        ],
        "palettes": list(PALETTES.keys()),
    }


@router.post("/generer", tags=["Bureau — Infographie"])
async def generer_depuis_brief(
    demande: DemandeBrief,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Analyse un brief client et génère l'infographie complète (PDF print-ready + PNG preview).
    L'IA extrait automatiquement : titre, palette, textes, layout selon le gabarit.
    """
    from modules.bureau.infographe import generer_infographie, GABARITS
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde, debiter_llm, debiter_forfait,
    )

    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "infographie")
    if not autorise:
        raise HTTPException(403, msg)
    ok_solde, restants, _ = await verifier_solde(current_user.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")

    if demande.type_gabarit not in GABARITS:
        raise HTTPException(
            status_code=400,
            detail=f"Gabarit inconnu. Disponibles : {list(GABARITS.keys())}",
        )

    try:
        resultat = await generer_infographie(
            brief=demande.brief,
            type_gabarit=demande.type_gabarit,
            pays=demande.pays,
        )
    except Exception as e:
        logger.error(f"[Bureau Infographie] Génération échouée : {e}")
        raise HTTPException(status_code=500, detail=f"Génération échouée : {e}")

    # Débit crédits : LLM spec + forfait PDF
    try:
        meta = resultat.meta or {}
        if meta.get("tokens_input") or meta.get("tokens_output"):
            await debiter_llm(
                current_user.user_id,
                modele=meta.get("modele", "default"),
                tokens_input=int(meta.get("tokens_input", 0) or 0),
                tokens_output=int(meta.get("tokens_output", 0) or 0),
                module="infographie",
            )
        if resultat.pdf_bytes:
            await debiter_forfait(current_user.user_id, "infographie_pdf", module="infographie")
        if resultat.png_bytes:
            await debiter_forfait(current_user.user_id, "infographie_png", module="infographie")
    except Exception as _e:
        logger.warning(f"[Bureau/Crédits] Debit infographie échoué : {_e}")

    ts = int(__import__("time").time())
    pdf_id = None
    png_id = None
    pdf_b64 = None
    png_b64 = None

    if resultat.pdf_bytes:
        pdf_id = f"bureau_infog_{current_user.user_id}_{demande.type_gabarit}_{ts}.pdf"
        (_DATA_DIR / pdf_id).write_bytes(resultat.pdf_bytes)
        pdf_b64 = base64.b64encode(resultat.pdf_bytes).decode()

    if resultat.png_bytes:
        png_id = f"bureau_infog_{current_user.user_id}_{demande.type_gabarit}_{ts}.png"
        (_DATA_DIR / png_id).write_bytes(resultat.png_bytes)
        png_b64 = base64.b64encode(resultat.png_bytes).decode()

    spec = resultat.specification
    return {
        "gabarit": demande.type_gabarit,
        "titre": spec.titre if spec else "",
        "palette": spec.palette if spec else "classique",
        "specification": {
            "titre": spec.titre,
            "sous_titre": spec.sous_titre,
            "corps": spec.corps,
            "details": spec.details,
            "palette": spec.palette,
            "nom_organisation": spec.nom_organisation,
            "contact": spec.contact,
            "slogan": spec.slogan,
            "date_evenement": spec.date_evenement,
            "lieu": spec.lieu,
        } if spec else None,
        "pdf_id": pdf_id,
        "png_id": png_id,
        "pdf_base64": pdf_b64,
        "png_base64": png_b64,
        "prix_fcfa": resultat.meta.get("prix_fcfa", 0),
        "meta": resultat.meta,
    }


@router.post("/generer-manuel", tags=["Bureau — Infographie"])
async def generer_manuel(
    demande: DemandeManuelle,
    current_user: TokenData = Depends(get_current_user),
):
    """Génère un PDF directement depuis une spécification manuelle (sans passer par l'IA)."""
    from modules.bureau.infographe import (
        SpecificationInfographie, generer_pdf, GABARITS, PALETTES,
    )
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde, debiter_forfait,
    )

    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "infographie")
    if not autorise:
        raise HTTPException(403, msg)
    ok_solde, restants, _ = await verifier_solde(current_user.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")

    if demande.type_gabarit not in GABARITS:
        raise HTTPException(status_code=400, detail=f"Gabarit inconnu : {demande.type_gabarit}")
    if demande.palette not in PALETTES:
        raise HTTPException(status_code=400, detail=f"Palette inconnue : {demande.palette}")

    spec = SpecificationInfographie(
        type_gabarit=demande.type_gabarit,
        titre=demande.titre,
        sous_titre=demande.sous_titre,
        corps=demande.corps,
        details=demande.details,
        palette=demande.palette,
        nom_organisation=demande.nom_organisation,
        contact=demande.contact,
        slogan=demande.slogan,
        date_evenement=demande.date_evenement,
        lieu=demande.lieu,
    )

    try:
        pdf_bytes = generer_pdf(spec)
    except Exception as e:
        logger.error(f"[Bureau Infographie Manuel] Erreur : {e}")
        raise HTTPException(status_code=500, detail=str(e))

    ts = int(__import__("time").time())
    pdf_id = f"bureau_infog_{current_user.user_id}_{demande.type_gabarit}_{ts}.pdf"
    (_DATA_DIR / pdf_id).write_bytes(pdf_bytes)

    try:
        await debiter_forfait(current_user.user_id, "infographie_pdf", module="infographie")
    except Exception as _e:
        logger.warning(f"[Bureau/Crédits] Debit infographie manuel échoué : {_e}")

    return {
        "gabarit": demande.type_gabarit,
        "pdf_id": pdf_id,
        "pdf_base64": base64.b64encode(pdf_bytes).decode(),
        "prix_fcfa": GABARITS[demande.type_gabarit]["prix_fcfa"],
    }


@router.post("/generer-depuis-modele", tags=["Bureau — Infographie"])
async def generer_depuis_modele_image(
    modele: UploadFile = File(...),
    brief: str = Form(...),
    type_gabarit: str = Form(...),
    pays: str = Form(default="CM"),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Upload ou scan d'une image modèle → analyse de style via IA → génération d'infographie inspirée.
    Formats acceptés : PNG, JPG, JPEG, WEBP (max 10 MB).
    """
    from modules.bureau.infographe import generer_infographie, analyser_modele_image, GABARITS
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde, debiter_llm, debiter_forfait,
    )

    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "infographie")
    if not autorise:
        raise HTTPException(403, msg)
    ok_solde, restants, _ = await verifier_solde(current_user.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")

    if type_gabarit not in GABARITS:
        raise HTTPException(status_code=400, detail=f"Gabarit inconnu : {type_gabarit}")

    if modele.size and modele.size > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image trop volumineuse (max 10 MB)")

    ext = (modele.filename or "").lower().rsplit(".", 1)[-1]
    if ext not in ("png", "jpg", "jpeg", "webp"):
        raise HTTPException(status_code=400, detail="Format image non supporté (PNG/JPG/JPEG/WEBP)")

    image_bytes = await modele.read()
    mime_type = "image/png" if ext == "png" else "image/jpeg"

    try:
        analyse_style = await analyser_modele_image(image_bytes, mime_type)
    except Exception as e:
        logger.warning(f"[Infographie] Analyse modèle échouée : {e} — génération sans analyse")
        analyse_style = ""

    brief_enrichi = brief
    if analyse_style:
        brief_enrichi = (
            f"{brief}\n\n"
            f"[STYLE DÉTECTÉ SUR L'IMAGE MODÈLE]\n{analyse_style}\n"
            "Inspire-toi de ce style pour la mise en page, les couleurs et la typographie."
        )

    try:
        resultat = await generer_infographie(
            brief=brief_enrichi,
            type_gabarit=type_gabarit,
            pays=pays,
        )
    except Exception as e:
        logger.error(f"[Bureau Infographie Modèle] Génération échouée : {e}")
        raise HTTPException(status_code=500, detail=f"Génération échouée : {e}")

    ts = int(__import__("time").time())
    import base64 as _b64
    pdf_id = png_id = pdf_b64 = png_b64 = None

    if resultat.pdf_bytes:
        pdf_id = f"bureau_infog_{current_user.user_id}_{type_gabarit}_{ts}.pdf"
        (_DATA_DIR / pdf_id).write_bytes(resultat.pdf_bytes)
        pdf_b64 = _b64.b64encode(resultat.pdf_bytes).decode()

    if resultat.png_bytes:
        png_id = f"bureau_infog_{current_user.user_id}_{type_gabarit}_{ts}.png"
        (_DATA_DIR / png_id).write_bytes(resultat.png_bytes)
        png_b64 = _b64.b64encode(resultat.png_bytes).decode()

    # Débit : vision modèle + LLM spec + forfaits PDF/PNG
    try:
        if analyse_style:
            await debiter_forfait(current_user.user_id, "infographie_vision", module="infographie")
        meta = resultat.meta or {}
        if meta.get("tokens_input") or meta.get("tokens_output"):
            await debiter_llm(
                current_user.user_id,
                modele=meta.get("modele", "default"),
                tokens_input=int(meta.get("tokens_input", 0) or 0),
                tokens_output=int(meta.get("tokens_output", 0) or 0),
                module="infographie",
            )
        if resultat.pdf_bytes:
            await debiter_forfait(current_user.user_id, "infographie_pdf", module="infographie")
        if resultat.png_bytes:
            await debiter_forfait(current_user.user_id, "infographie_png", module="infographie")
    except Exception as _e:
        logger.warning(f"[Bureau/Crédits] Debit infographie modèle échoué : {_e}")

    spec = resultat.specification
    return {
        "gabarit": type_gabarit,
        "analyse_modele": analyse_style,
        "specification": {
            "titre": spec.titre,
            "sous_titre": spec.sous_titre,
            "corps": spec.corps,
            "details": spec.details,
            "palette": spec.palette,
            "nom_organisation": spec.nom_organisation,
            "contact": spec.contact,
            "slogan": spec.slogan,
            "date_evenement": spec.date_evenement,
            "lieu": spec.lieu,
        } if spec else None,
        "pdf_id": pdf_id,
        "png_id": png_id,
        "pdf_base64": pdf_b64,
        "png_base64": png_b64,
        "prix_fcfa": resultat.meta.get("prix_fcfa", 0),
        "meta": resultat.meta,
    }


@router.post("/generer-custom", tags=["Bureau — Infographie"])
async def generer_format_custom(
    demande: DemandeCustom,
    current_user: TokenData = Depends(get_current_user),
):
    """Génère une infographie avec un format entièrement personnalisé (dimensions libres en mm)."""
    from modules.bureau.infographe import generer_infographie, creer_gabarit_custom, GABARITS as _GABARITS
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde, debiter_llm, debiter_forfait,
    )
    import copy

    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "infographie")
    if not autorise:
        raise HTTPException(403, msg)
    ok_solde, restants, _ = await verifier_solde(current_user.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")

    gabarit_custom = creer_gabarit_custom(
        width_mm=demande.width_mm,
        height_mm=demande.height_mm,
        bleed_mm=demande.bleed_mm,
    )
    gabarit_key = f"custom_{int(demande.width_mm)}x{int(demande.height_mm)}"

    _GABARITS_PATCHED = {**_GABARITS, gabarit_key: gabarit_custom}

    try:
        resultat = await generer_infographie(
            brief=demande.brief,
            type_gabarit=gabarit_key,
            pays=demande.pays,
            gabarits_override=_GABARITS_PATCHED,
        )
    except Exception as e:
        logger.error(f"[Bureau Infographie Custom] Génération échouée : {e}")
        raise HTTPException(status_code=500, detail=f"Génération échouée : {e}")

    ts = int(__import__("time").time())
    import base64 as _b64
    pdf_id = png_id = pdf_b64 = png_b64 = None

    if resultat.pdf_bytes:
        pdf_id = f"bureau_infog_{current_user.user_id}_custom_{ts}.pdf"
        (_DATA_DIR / pdf_id).write_bytes(resultat.pdf_bytes)
        pdf_b64 = _b64.b64encode(resultat.pdf_bytes).decode()

    if resultat.png_bytes:
        png_id = f"bureau_infog_{current_user.user_id}_custom_{ts}.png"
        (_DATA_DIR / png_id).write_bytes(resultat.png_bytes)
        png_b64 = _b64.b64encode(resultat.png_bytes).decode()

    try:
        meta = resultat.meta or {}
        if meta.get("tokens_input") or meta.get("tokens_output"):
            await debiter_llm(
                current_user.user_id,
                modele=meta.get("modele", "default"),
                tokens_input=int(meta.get("tokens_input", 0) or 0),
                tokens_output=int(meta.get("tokens_output", 0) or 0),
                module="infographie",
            )
        if resultat.pdf_bytes:
            await debiter_forfait(current_user.user_id, "infographie_pdf", module="infographie")
        if resultat.png_bytes:
            await debiter_forfait(current_user.user_id, "infographie_png", module="infographie")
    except Exception as _e:
        logger.warning(f"[Bureau/Crédits] Debit infographie custom échoué : {_e}")

    spec = resultat.specification
    return {
        "gabarit": gabarit_key,
        "dimensions_mm": {"width": demande.width_mm, "height": demande.height_mm, "bleed": demande.bleed_mm},
        "specification": {
            "titre": spec.titre,
            "sous_titre": spec.sous_titre,
            "corps": spec.corps,
            "details": spec.details,
            "palette": spec.palette,
        } if spec else None,
        "pdf_id": pdf_id,
        "png_id": png_id,
        "pdf_base64": pdf_b64,
        "png_base64": png_b64,
        "meta": resultat.meta,
    }


@router.get("/fichier/{fichier_id}", tags=["Bureau — Infographie"])
async def telecharger_infographie(
    fichier_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Télécharge un PDF ou PNG d'infographie généré."""
    if "/" in fichier_id or "\\" in fichier_id or ".." in fichier_id:
        raise HTTPException(status_code=400, detail="Nom de fichier invalide")

    chemin = _DATA_DIR / fichier_id
    if not chemin.exists():
        raise HTTPException(status_code=404, detail="Fichier introuvable")

    if f"_{current_user.user_id}_" not in fichier_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Accès refusé")

    suffix = chemin.suffix.lower()
    media_types = {
        ".pdf": "application/pdf",
        ".png": "image/png",
    }
    media_type = media_types.get(suffix, "application/octet-stream")

    return Response(
        content=chemin.read_bytes(),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{fichier_id}"'},
    )
