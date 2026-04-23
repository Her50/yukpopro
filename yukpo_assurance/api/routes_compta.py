"""Routes comptabilité — OCR pièces, rapprochement, reporting"""
import base64
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional

from modules.comptabilite.pieces_processor import PieceComptable, pieces_processor
from modules.comptabilite.rapprochement import rapprochement
from core.auth import TokenData, get_current_user, require_permission

router = APIRouter(dependencies=[Depends(require_permission("comptabilite"))])

_MIMES_PIECE = {
    "image/jpeg", "image/jpg", "image/png", "image/webp", "image/heic", "image/tiff",
    "application/pdf",
}


async def _pre_check_credits_piece(user_id: int) -> None:
    from modules.pro.service_credits import verifier_solde_suffisant
    try:
        ok, _r, _p, msg = await verifier_solde_suffisant(user_id)
        if not ok:
            raise HTTPException(402, msg)
    except HTTPException:
        raise
    except Exception:
        pass


async def _debit_llm_piece(user_id: int, module: str, fallback_tokens=(2000, 800)) -> None:
    try:
        from modules.pro.service_credits import verifier_et_debiter
        await verifier_et_debiter(
            user_id=user_id,
            modele="claude-sonnet-4-6",
            tokens_input=fallback_tokens[0],
            tokens_output=fallback_tokens[1],
            module=module,
        )
    except Exception:
        pass


class PieceRequest(BaseModel):
    type_piece: str
    image_b64: Optional[str] = None
    pdf_b64: Optional[str] = None
    id_reference: Optional[str] = None


class ValidationRequest(BaseModel):
    resultat: dict
    valide_par: str


class RapprochementCSVRequest(BaseModel):
    contenu_csv: str


@router.post("/piece/traiter")
async def traiter_piece(req: PieceRequest):
    """Traitement OCR + imputation automatique d'une pièce comptable"""
    piece = PieceComptable(
        type_piece=req.type_piece,
        image_b64=req.image_b64,
        pdf_b64=req.pdf_b64,
        id_reference=req.id_reference,
    )
    resultat = await pieces_processor.traiter_piece(piece)
    return {
        "type_piece": resultat.type_piece,
        "donnees_extraites": resultat.donnees_extraites,
        "imputation_proposee": resultat.imputation_proposee,
        "anomalies": resultat.anomalies,
        "confiance": resultat.confiance,
        "validation_requise": resultat.validation_requise,
        "ecriture_orass": resultat.ecriture_orass,
    }


@router.post("/piece/traiter-upload")
async def traiter_piece_upload(
    type_piece: str,
    fichier: UploadFile = File(...),
    id_reference: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Traitement d'une pièce comptable uploadée (image ou PDF)"""
    from config.settings import settings
    contenu = await fichier.read()
    taille_mb = len(contenu) / (1024 * 1024)
    limite_mb = settings.MAX_PDF_SIZE_MB if (fichier.content_type or "") == "application/pdf" else settings.MAX_IMAGE_SIZE_MB
    if taille_mb > limite_mb:
        raise HTTPException(413, f"Fichier trop volumineux : {taille_mb:.1f}MB (max {limite_mb}MB)")
    contenu_b64 = base64.standard_b64encode(contenu).decode()

    est_pdf = fichier.content_type == "application/pdf"
    piece = PieceComptable(
        type_piece=type_piece,
        image_b64=None if est_pdf else contenu_b64,
        pdf_b64=contenu_b64 if est_pdf else None,
        id_reference=id_reference,
    )
    resultat = await pieces_processor.traiter_piece(piece)
    return {
        "type_piece": resultat.type_piece,
        "donnees_extraites": resultat.donnees_extraites,
        "imputation_proposee": resultat.imputation_proposee,
        "anomalies": resultat.anomalies,
        "confiance": resultat.confiance,
        "validation_requise": resultat.validation_requise,
    }


@router.post("/analyser-piece", summary="OCR pièce comptable (mobile)")
async def analyser_piece_mobile(
    fichier: UploadFile = File(..., description="Image ou PDF de la pièce"),
    type_document: str = Form(..., description="facture|recu|releve_bancaire|bordereau|autre"),
    id_reference: Optional[str] = Form(None),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Analyse OCR + imputation automatique d'une pièce comptable (upload mobile).
    Pré-check crédits → validation MIME/taille → pieces_processor → débit LLM.
    """
    await _pre_check_credits_piece(current_user.user_id)

    from config.settings import settings
    mime = fichier.content_type or "application/octet-stream"
    if mime not in _MIMES_PIECE:
        raise HTTPException(415, f"Type non supporté : {mime}. Formats : JPEG, PNG, WebP, HEIC, PDF, TIFF")

    contenu = await fichier.read()
    taille_mb = len(contenu) / (1024 * 1024)
    est_pdf = mime == "application/pdf"
    limite_mb = settings.MAX_PDF_SIZE_MB if est_pdf else settings.MAX_IMAGE_SIZE_MB
    if taille_mb > limite_mb:
        raise HTTPException(413, f"Fichier trop volumineux : {taille_mb:.1f} Mo (max {limite_mb} Mo)")

    contenu_b64 = base64.standard_b64encode(contenu).decode()
    piece = PieceComptable(
        type_piece=type_document,
        image_b64=None if est_pdf else contenu_b64,
        pdf_b64=contenu_b64 if est_pdf else None,
        id_reference=id_reference,
    )
    try:
        resultat = await pieces_processor.traiter_piece(piece)
    except Exception as e:
        raise HTTPException(500, f"OCR pièce échoué : {str(e)[:200]}")

    await _debit_llm_piece(current_user.user_id, "compta_analyser_piece_mobile")
    return {
        "type_document": resultat.type_piece,
        "donnees_extraites": resultat.donnees_extraites,
        "imputation_proposee": resultat.imputation_proposee,
        "anomalies": resultat.anomalies,
        "confiance": resultat.confiance,
        "validation_requise": resultat.validation_requise,
        "ecriture_orass": resultat.ecriture_orass,
    }


@router.post("/rapprochement/csv")
async def rapprocher_csv(req: RapprochementCSVRequest):
    """Rapprochement bancaire depuis export CSV"""
    resultat = await rapprochement.rapprocher_depuis_csv(req.contenu_csv)
    return rapprochement.to_dict(resultat)


@router.post("/rapprochement/image")
async def rapprocher_image(body: dict):
    """Rapprochement bancaire depuis relevé scanné"""
    image_b64 = body.get("image_b64")
    if not image_b64:
        raise HTTPException(400, "image_b64 manquant")
    resultat = await rapprochement.rapprocher_depuis_image(image_b64)
    return rapprochement.to_dict(resultat)


@router.post("/rapprochement/demo")
async def rapprocher_demo(mois: int = 3, annee: int = 2025):
    """
    Rapprochement de démonstration — génère un relevé simulé complet.
    Idéal pour tester la fonctionnalité sans fichier réel.
    """
    resultat = await rapprochement.rapprocher_periode_demo(mois=mois, annee=annee)
    return rapprochement.to_dict(resultat)


@router.post("/rapprochement/json")
async def rapprocher_json(body: dict):
    """Rapprochement depuis une liste d'opérations JSON"""
    operations = body.get("operations", [])
    if not operations:
        raise HTTPException(400, "Champ 'operations' requis (liste d'opérations)")
    resultat = await rapprochement.rapprocher_depuis_json(operations)
    return rapprochement.to_dict(resultat)


@router.get("/rapprochement/plan-comptable")
async def plan_comptable():
    """Retourne le plan comptable PCSA CIMA utilisé pour les imputations automatiques"""
    from modules.comptabilite.rapprochement import ECRITURES_REFERENCE
    return {
        "plan_comptable": [
            {"compte": "60100", "libelle": "Prestations — Indemnités sinistres auto"},
            {"compte": "60200", "libelle": "Prestations — Indemnités sinistres corps"},
            {"compte": "61200", "libelle": "Commissions des intermédiaires"},
            {"compte": "64100", "libelle": "Primes de réassurance cédées"},
            {"compte": "67000", "libelle": "Frais généraux"},
            {"compte": "70100", "libelle": "Primes acquises — Non-vie"},
            {"compte": "70200", "libelle": "Primes acquises — Vie"},
            {"compte": "40100", "libelle": "Fournisseurs — Garages"},
            {"compte": "40200", "libelle": "Fournisseurs — Établissements de santé"},
            {"compte": "40300", "libelle": "Fournisseurs divers"},
            {"compte": "41100", "libelle": "Créances — Primes à recouvrer"},
            {"compte": "47000", "libelle": "Comptes d'attente"},
        ],
        "ecritures_reference_count": len(ECRITURES_REFERENCE),
        "note": "Plan comptable spécifique assurance PCSA (Plan Comptable Spécifique Assurance) — Zone CIMA",
    }
