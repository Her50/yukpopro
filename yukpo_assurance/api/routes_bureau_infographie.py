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


class ProfilInfographie(BaseModel):
    """Contexte utilisateur transmis au LLM pour contextualiser le visuel."""
    metier: Optional[str] = None
    secteur: Optional[str] = None
    nom_organisation: Optional[str] = None
    audience: Optional[str] = None
    ton: Optional[str] = Field(default=None, description="formel | chaleureux | jeune | premium | sobre")
    couleur_primaire_hex: Optional[str] = Field(default=None, description="Couleur de marque principale #RRGGBB")
    couleurs_accents_hex: Optional[list[str]] = Field(default=None, description="Couleurs d'accent de marque")


class DemandeBrief(BaseModel):
    brief: str = Field(..., min_length=10, description="Description libre du besoin en langage naturel")
    type_gabarit: str = Field(..., description="Type de gabarit (ex: flyer_a5, carte_visite, diplome)")
    pays: str = Field(default="CM")
    profil: Optional[ProfilInfographie] = None
    export_cmyk: bool = Field(default=True, description="Générer aussi une version PDF CMJN (print offset)")
    export_svg: bool = Field(default=True, description="Générer aussi un export SVG vectoriel")
    dpi_preview: int = Field(default=300, ge=72, le=600, description="DPI du rendu PNG principal")


class DemandeManuelle(BaseModel):
    type_gabarit: str
    titre: str
    sous_titre: Optional[str] = None
    corps: Optional[str] = None
    details: list[str] = Field(default_factory=list)
    palette: str = Field(default="classique", description="classique | cameroun | senegal | elegance | moderne | ...")
    nom_organisation: Optional[str] = None
    contact: Optional[str] = None
    slogan: Optional[str] = None
    date_evenement: Optional[str] = None
    lieu: Optional[str] = None
    couleur_primaire_hex: Optional[str] = None
    couleurs_accents_hex: Optional[list[str]] = None
    export_cmyk: bool = Field(default=True)
    export_svg: bool = Field(default=True)


class DemandeCustom(BaseModel):
    width_mm: float = Field(..., gt=0, le=3000, description="Largeur en mm")
    height_mm: float = Field(..., gt=0, le=3000, description="Hauteur en mm")
    bleed_mm: float = Field(default=3, ge=0, le=20, description="Fond perdu en mm")
    brief: str = Field(..., min_length=10)
    pays: str = Field(default="CM")
    profil: Optional[ProfilInfographie] = None
    export_cmyk: bool = Field(default=True)
    export_svg: bool = Field(default=True)


class DemandeVariantes(BaseModel):
    brief: str = Field(..., min_length=10)
    type_gabarit: str
    pays: str = Field(default="CM")
    profil: Optional[ProfilInfographie] = None
    nombre: int = Field(default=4, ge=2, le=4)


def _persister_artefacts(user_id, type_gabarit: str, ts: int, resultat) -> dict:
    """
    Sauve sur disque tous les artefacts disponibles (PDF RGB, PDF CMJN, PNG 300dpi,
    PNG web 150dpi, SVG) et retourne le dict {ids, base64} pour la réponse API.
    """
    base = f"bureau_pdf_{user_id}_infographie_{type_gabarit}_{ts}"
    out = {
        "pdf_id": None, "pdf_base64": None,
        "pdf_cmyk_id": None, "pdf_cmyk_base64": None,
        "png_id": None, "png_base64": None,
        "png_preview_id": None, "png_preview_base64": None,
        "svg_id": None, "svg_base64": None,
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
    if resultat.png_bytes:
        fid = f"{base}.png"
        (_DATA_DIR / fid).write_bytes(resultat.png_bytes)
        out["png_id"] = fid
        out["png_base64"] = base64.b64encode(resultat.png_bytes).decode()
    if resultat.png_preview_bytes and resultat.png_preview_bytes != resultat.png_bytes:
        fid = f"{base}_web.png"
        (_DATA_DIR / fid).write_bytes(resultat.png_preview_bytes)
        out["png_preview_id"] = fid
        out["png_preview_base64"] = base64.b64encode(resultat.png_preview_bytes).decode()
    if resultat.svg_bytes:
        fid = f"{base}.svg"
        (_DATA_DIR / fid).write_bytes(resultat.svg_bytes)
        out["svg_id"] = fid
        out["svg_base64"] = base64.b64encode(resultat.svg_bytes).decode()
    return out


def _serialiser_spec(spec) -> Optional[dict]:
    if not spec:
        return None
    return {
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
        "justification": (spec.meta or {}).get("justification"),
        "variante": (spec.meta or {}).get("variante_hint"),
    }


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

    profil_dict = demande.profil.model_dump(exclude_none=True) if demande.profil else None
    try:
        resultat = await generer_infographie(
            brief=demande.brief,
            type_gabarit=demande.type_gabarit,
            pays=demande.pays,
            profil=profil_dict,
            export_cmyk=demande.export_cmyk,
            export_svg=demande.export_svg,
            dpi_preview=demande.dpi_preview,
        )
    except Exception as e:
        logger.error(f"[Bureau Infographie] Génération échouée : {e}")
        raise HTTPException(status_code=500, detail=f"Génération échouée : {e}")

    # Débit crédits : LLM (tokens) + création (montant FCFA = prix_fcfa du gabarit)
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
        prix_gabarit = float(GABARITS[demande.type_gabarit].get("prix_fcfa", 0) or 0)
        if prix_gabarit > 0 and resultat.pdf_bytes:
            await debiter_forfait(
                current_user.user_id,
                "infographie_creation",
                module="infographie",
                multiplicateur=prix_gabarit / 20.0,
            )
    except Exception as _e:
        logger.warning(f"[Bureau/Crédits] Debit infographie échoué : {_e}")

    ts = int(__import__("time").time())
    artefacts = _persister_artefacts(current_user.user_id, demande.type_gabarit, ts, resultat)

    spec = resultat.specification
    return {
        "gabarit": demande.type_gabarit,
        "titre": spec.titre if spec else "",
        "palette": spec.palette if spec else "classique",
        "specification": _serialiser_spec(spec),
        **artefacts,
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

    from modules.bureau.infographe import _palette_personnalisee_depuis_hex, generer_infographie
    meta_spec: dict = {}
    if demande.couleur_primaire_hex:
        meta_spec["palette_custom"] = _palette_personnalisee_depuis_hex(
            demande.couleur_primaire_hex,
            demande.couleurs_accents_hex or [],
        )

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
        meta=meta_spec,
    )

    try:
        # On passe par generer_infographie avec spec_override pour bénéficier
        # automatiquement du PDF CMJN + PNG 300 DPI + SVG.
        resultat = await generer_infographie(
            brief="(spécification manuelle — aucun brief IA)",
            type_gabarit=demande.type_gabarit,
            spec_override=spec,
            export_cmyk=demande.export_cmyk,
            export_svg=demande.export_svg,
        )
    except Exception as e:
        logger.error(f"[Bureau Infographie Manuel] Erreur : {e}")
        logger.error(f"[routes_bureau_infographie.py] {e}")
        raise HTTPException(status_code=500, detail="Erreur serveur interne")

    ts = int(__import__("time").time())
    artefacts = _persister_artefacts(current_user.user_id, demande.type_gabarit, ts, resultat)

    try:
        prix_gabarit = float(GABARITS[demande.type_gabarit].get("prix_fcfa", 0) or 0)
        if prix_gabarit > 0:
            await debiter_forfait(
                current_user.user_id,
                "infographie_creation",
                module="infographie",
                multiplicateur=prix_gabarit / 20.0,
            )
    except Exception as _e:
        logger.warning(f"[Bureau/Crédits] Debit infographie manuel échoué : {_e}")

    return {
        "gabarit": demande.type_gabarit,
        "specification": _serialiser_spec(resultat.specification),
        **artefacts,
        "prix_fcfa": GABARITS[demande.type_gabarit]["prix_fcfa"],
        "meta": resultat.meta,
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
    artefacts = _persister_artefacts(current_user.user_id, type_gabarit, ts, resultat)

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
        prix_gabarit = float(GABARITS[type_gabarit].get("prix_fcfa", 0) or 0)
        if prix_gabarit > 0 and resultat.pdf_bytes:
            await debiter_forfait(
                current_user.user_id,
                "infographie_creation",
                module="infographie",
                multiplicateur=prix_gabarit / 20.0,
            )
    except Exception as _e:
        logger.warning(f"[Bureau/Crédits] Debit infographie modèle échoué : {_e}")

    return {
        "gabarit": type_gabarit,
        "analyse_modele": analyse_style,
        "specification": _serialiser_spec(resultat.specification),
        **artefacts,
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

    profil_dict = demande.profil.model_dump(exclude_none=True) if demande.profil else None
    try:
        resultat = await generer_infographie(
            brief=demande.brief,
            type_gabarit=gabarit_key,
            pays=demande.pays,
            gabarits_override=_GABARITS_PATCHED,
            profil=profil_dict,
            export_cmyk=demande.export_cmyk,
            export_svg=demande.export_svg,
        )
    except Exception as e:
        logger.error(f"[Bureau Infographie Custom] Génération échouée : {e}")
        raise HTTPException(status_code=500, detail=f"Génération échouée : {e}")

    ts = int(__import__("time").time())
    artefacts = _persister_artefacts(current_user.user_id, "custom", ts, resultat)

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
        prix_gabarit = float(gabarit_custom.get("prix_fcfa", 5000) or 5000)
        if prix_gabarit > 0 and resultat.pdf_bytes:
            await debiter_forfait(
                current_user.user_id,
                "infographie_creation",
                module="infographie",
                multiplicateur=prix_gabarit / 20.0,
            )
    except Exception as _e:
        logger.warning(f"[Bureau/Crédits] Debit infographie custom échoué : {_e}")

    return {
        "gabarit": gabarit_key,
        "dimensions_mm": {"width": demande.width_mm, "height": demande.height_mm, "bleed": demande.bleed_mm},
        "specification": _serialiser_spec(resultat.specification),
        **artefacts,
        "meta": resultat.meta,
    }


@router.post("/generer-variantes", tags=["Bureau — Infographie"])
async def generer_variantes(
    demande: DemandeVariantes,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Génère N (2-4) variantes créatives distinctes en parallèle.
    Utilisé pour proposer plusieurs directions artistiques à l'utilisateur
    avant qu'il ne choisisse celle à finaliser.
    """
    from modules.bureau.infographe import generer_variantes_parallele, GABARITS
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde, debiter_llm,
    )

    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "infographie")
    if not autorise:
        raise HTTPException(403, msg)
    ok_solde, restants, _ = await verifier_solde(current_user.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")

    if demande.type_gabarit not in GABARITS:
        raise HTTPException(400, f"Gabarit inconnu : {demande.type_gabarit}")

    profil_dict = demande.profil.model_dump(exclude_none=True) if demande.profil else None

    try:
        resultats = await generer_variantes_parallele(
            brief=demande.brief,
            type_gabarit=demande.type_gabarit,
            pays=demande.pays,
            profil=profil_dict,
            nombre=demande.nombre,
        )
    except Exception as e:
        logger.error(f"[Bureau Infographie Variantes] Génération échouée : {e}")
        raise HTTPException(500, f"Génération variantes échouée : {e}")

    ts = int(__import__("time").time())
    variantes_payload = []
    for idx, resultat in enumerate(resultats):
        artefacts = _persister_artefacts(
            current_user.user_id, f"{demande.type_gabarit}_v{idx+1}", ts, resultat,
        )
        # Débit LLM par variante (4 × tokens)
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
        except Exception as _e:
            logger.warning(f"[Bureau/Crédits] Débit variante {idx} : {_e}")

        variantes_payload.append({
            "index": idx,
            "variante": (resultat.meta or {}).get("variante") or (resultat.meta or {}).get("variante_hint"),
            "specification": _serialiser_spec(resultat.specification),
            **artefacts,
            "meta": resultat.meta,
        })

    return {
        "gabarit": demande.type_gabarit,
        "nombre_variantes": len(variantes_payload),
        "variantes": variantes_payload,
        "note": "Seule la variante sélectionnée sera débitée en forfait gabarit lors de la validation finale.",
    }


class ModifierInfographieRequest(BaseModel):
    fichier_id: str = Field(..., description="ID du fichier infographie à modifier")
    instructions: str = Field(..., min_length=5, description="Instructions de modification en langage naturel")
    pays: str = Field(default="CM")


@router.post("/modifier", tags=["Bureau — Infographie"])
async def modifier_infographie(
    demande: ModifierInfographieRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Modifie un visuel existant via instructions en langage naturel.
    L'IA analyse le PNG du visuel actuel et applique les modifications demandées.
    """
    import re
    from modules.bureau.infographe import generer_infographie, analyser_modele_image, GABARITS
    from modules.bureau.service_credits_bureau import (
        verifier_acces_module, verifier_solde, debiter_llm, debiter_forfait,
    )

    if f"_{current_user.user_id}_" not in demande.fichier_id and current_user.role != "admin":
        raise HTTPException(403, "Accès refusé")

    autorise, plan, msg = await verifier_acces_module(current_user.user_id, "infographie")
    if not autorise:
        raise HTTPException(403, msg)
    ok_solde, restants, _ = await verifier_solde(current_user.user_id)
    if not ok_solde:
        raise HTTPException(402, f"CREDITS_EPUISES|restants={int(restants)}|plan={plan}")

    # Extraire le gabarit depuis le nom de fichier : bureau_pdf_{uid}_infographie_{gabarit}_{ts}.ext
    gabarit = "flyer_a5"
    m = re.search(r"_infographie_(.+?)_\d+\.", demande.fichier_id)
    if m:
        gabarit = m.group(1)
    if gabarit not in GABARITS:
        gabarit = next(iter(GABARITS), "flyer_a5")

    # Préférer le PNG pour l'analyse visuelle
    base_no_ext = demande.fichier_id.rsplit(".", 1)[0]
    png_path = _DATA_DIR / (base_no_ext + ".png")
    pdf_path = _DATA_DIR / demande.fichier_id
    source_path = png_path if png_path.exists() else (pdf_path if pdf_path.exists() else None)

    if source_path is None:
        raise HTTPException(404, "Fichier source introuvable — le visuel a peut-être expiré")

    # Analyser le visuel existant si c'est un PNG
    analyse_style = ""
    if source_path.suffix == ".png":
        try:
            analyse_style = await analyser_modele_image(source_path.read_bytes(), "image/png")
        except Exception as e:
            logger.warning(f"[Infographie/Modifier] Analyse PNG échouée : {e}")

    brief_modification = (
        f"MODIFICATION DU VISUEL EXISTANT.\n\n"
        f"Instructions de modification : {demande.instructions}\n\n"
    )
    if analyse_style:
        brief_modification += (
            f"[VISUEL ACTUEL DÉTECTÉ]\n{analyse_style}\n\n"
            "Conserve tous les éléments non concernés par les instructions "
            "et applique uniquement les changements demandés."
        )

    try:
        resultat = await generer_infographie(
            brief=brief_modification,
            type_gabarit=gabarit,
            pays=demande.pays,
        )
    except Exception as e:
        logger.error(f"[Infographie/Modifier] Génération échouée : {e}")
        raise HTTPException(500, f"Modification échouée : {e}")

    ts = int(__import__("time").time())
    artefacts = _persister_artefacts(current_user.user_id, gabarit, ts, resultat)

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
    except Exception as _e:
        logger.warning(f"[Infographie/Modifier/Credits] {_e}")

    return {
        **artefacts,
        "gabarit": gabarit,
        "titre": (resultat.specification.titre if resultat.specification else ""),
        "specification": _serialiser_spec(resultat.specification),
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
        ".svg": "image/svg+xml",
    }
    media_type = media_types.get(suffix, "application/octet-stream")

    return Response(
        content=chemin.read_bytes(),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{fichier_id}"'},
    )
