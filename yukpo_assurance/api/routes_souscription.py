"""Routes souscription — portail digital, KYC, calcul de prime, gestion contrats"""
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from typing import Optional
import base64

from modules.souscription.portail import DossierSouscription, portail_souscription
from core.orass_connector import orass
from core.auth import TokenData, get_current_user, require_permission

router = APIRouter(dependencies=[Depends(get_current_user)])


class SouscriptionRequest(BaseModel):
    branche: str
    cni_b64: Optional[str] = None
    carte_grise_b64: Optional[str] = None
    donnees_client: dict = {}
    courtier_code: Optional[str] = None
    agent_code: Optional[str] = None


class AnnulationRequest(BaseModel):
    motif: str


@router.post("/soumettre")
async def soumettre_souscription(
    req: SouscriptionRequest,
    current_user: TokenData = Depends(require_permission("souscription")),
):
    """
    Soumission d'un dossier de souscription.
    KYC + calcul prime + création contrat local (YK-{BR}-{YYYY}-{SEQ}) + attestation PDF.
    """
    dossier = DossierSouscription(**req.model_dump())
    resultat = await portail_souscription.traiter_dossier(dossier)
    return {
        "statut": resultat.statut,
        "numero_police": resultat.numero_police,
        "donnees_extraites": resultat.donnees_extraites,
        "pieces_manquantes": resultat.pieces_manquantes,
        "calcul_prime": resultat.calcul_prime,
        "message": resultat.message,
        "actions": resultat.actions,
        "attestation_pdf_b64": resultat.attestation_pdf_b64,
    }


@router.get("/contrats")
async def lister_contrats(
    agent_code: Optional[str] = Query(None, description="Filtrer par agent"),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Liste les contrats enregistrés localement.
    Filtrable par agent. Retourne les contrats triés par date de création décroissante.
    """
    return portail_souscription.lister_contrats(agent_code=agent_code)


@router.post("/contrats/{numero_police}/renouveler")
async def renouveler_contrat(
    numero_police: str,
    current_user: TokenData = Depends(require_permission("souscription")),
):
    """
    Renouvellement d'un contrat existant avec ajustement de prime par IA.
    Génère un nouveau numéro de police et une nouvelle attestation PDF.
    """
    resultat = await portail_souscription.renouveler_contrat(numero_police)
    if not resultat.get("succes"):
        raise HTTPException(404, resultat.get("erreur", "Erreur renouvellement"))
    return resultat


@router.post("/contrats/{numero_police}/annuler")
async def annuler_contrat(
    numero_police: str,
    req: AnnulationRequest,
    current_user: TokenData = Depends(require_permission("souscription")),
):
    """
    Résiliation d'un contrat avec calcul de la ristourne prorata temporis.
    La ristourne correspond à 75% de la prime restante non consommée.
    """
    resultat = await portail_souscription.annuler_contrat(numero_police, req.motif)
    if not resultat.get("succes"):
        raise HTTPException(400, resultat.get("erreur", "Erreur résiliation"))
    return resultat


@router.get("/statistiques")
async def statistiques_souscription(
    current_user: TokenData = Depends(require_permission("souscription")),
):
    """
    Statistiques de souscription : total polices, primes, répartition branches, top agents.
    """
    return portail_souscription.statistiques_souscription()


@router.get("/contrat/{numero_police}")
async def consulter_contrat(
    numero_police: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Consultation d'un contrat (registre local en priorité, ORASS en fallback)"""
    from modules.souscription.portail import registre
    contrat_local = registre.get(numero_police)
    if contrat_local:
        return contrat_local
    # Fallback ORASS
    contrat = await orass.rechercher_contrat(numero_police=numero_police)
    if not contrat:
        raise HTTPException(404, "Contrat introuvable")
    return contrat


@router.get("/impayes")
async def lister_impayes(
    seuil_jours: int = 30,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=500),
    current_user: TokenData = Depends(require_permission("comptabilite")),
):
    """Liste des contrats avec primes impayées (paginée)"""
    tous = await orass.lister_impayes(seuil_jours)
    return {"total": len(tous), "skip": skip, "limit": limit, "impayes": tous[skip:skip + limit]}


# ═══════════════════════════════════════════════════════════════════════════
# KYC — OCR pièce d'identité et carte grise (appelé depuis le mobile)
# ═══════════════════════════════════════════════════════════════════════════

_MIMES_KYC = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/heic", "image/tiff"}


async def _pre_check_credits_kyc(user_id: int) -> None:
    from modules.pro.service_credits import verifier_solde_suffisant
    try:
        ok, _r, _p, msg = await verifier_solde_suffisant(user_id)
        if not ok:
            raise HTTPException(402, msg)
    except HTTPException:
        raise
    except Exception:
        pass


async def _debit_llm_kyc(user_id: int, reponse, module: str, fallback_tokens=(1200, 400)) -> None:
    try:
        from modules.pro.service_credits import verifier_et_debiter
        await verifier_et_debiter(
            user_id=user_id,
            modele=getattr(reponse, "modele_utilise", None) or "claude-sonnet-4-6",
            tokens_input=getattr(reponse, "tokens_input", None) or fallback_tokens[0],
            tokens_output=getattr(reponse, "tokens_output", None) or fallback_tokens[1],
            module=module,
        )
    except Exception:
        pass


async def _lire_image_upload(fichier: UploadFile) -> str:
    mime = fichier.content_type or "application/octet-stream"
    if mime not in _MIMES_KYC:
        raise HTTPException(415, f"Type non supporté : {mime}. Formats : JPEG, PNG, WebP, HEIC, TIFF")
    contenu = await fichier.read()
    taille_mb = len(contenu) / (1024 * 1024)
    if taille_mb > 10.0:
        raise HTTPException(413, f"Image trop volumineuse : {taille_mb:.1f} Mo (max 10 Mo)")
    return base64.standard_b64encode(contenu).decode()


@router.post("/kyc/analyser-cni", summary="OCR carte nationale d'identité (KYC mobile)")
async def analyser_cni(
    fichier: UploadFile = File(..., description="Photo de la CNI (JPEG/PNG/WebP)"),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Extrait les données d'une CNI/passeport/permis via Claude Vision.
    Utilisé par le flux KYC du mobile (Expo). Débit crédits au tarif réel.
    """
    await _pre_check_credits_kyc(current_user.user_id)
    image_b64 = await _lire_image_upload(fichier)

    from core.ia_client import ia_client, ModeIA
    prompt = """Lis cette pièce d'identité et retourne UNIQUEMENT ce JSON :
{
  "type_piece": "CNI|passeport|permis",
  "numero": "",
  "nom": "",
  "prenoms": "",
  "date_naissance": "JJ/MM/AAAA",
  "lieu_naissance": "",
  "date_expiration": "JJ/MM/AAAA",
  "valide": true,
  "nationalite": "",
  "confiance": "haute|moyenne|faible"
}"""
    try:
        reponse = await ia_client.analyser_image_vision(
            image_b64=image_b64, prompt=prompt, mode=ModeIA.PRECISION,
        )
        data = reponse.as_json()
    except Exception as e:
        raise HTTPException(500, f"OCR CNI échoué : {str(e)[:200]}")

    await _debit_llm_kyc(current_user.user_id, reponse, "kyc_cni_mobile")
    return {
        "donnees_extraites": data,
        "confiance": data.get("confiance"),
        "valide": data.get("valide", False),
        "modele": getattr(reponse, "modele_utilise", None),
    }


@router.post("/kyc/analyser-carte-grise", summary="OCR carte grise (KYC mobile)")
async def analyser_carte_grise(
    fichier: UploadFile = File(..., description="Photo de la carte grise (JPEG/PNG/WebP)"),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Extrait les données d'une carte grise (certificat d'immatriculation) via Claude Vision.
    Utilisé par le flux souscription auto mobile. Débit crédits au tarif réel.
    """
    await _pre_check_credits_kyc(current_user.user_id)
    image_b64 = await _lire_image_upload(fichier)

    from core.ia_client import ia_client, ModeIA
    prompt = """Lis cette carte grise (certificat d'immatriculation) et retourne UNIQUEMENT ce JSON :
{
  "immatriculation": "",
  "marque": "",
  "modele": "",
  "annee": 0,
  "cylindree": 0,
  "puissance_fiscale": 0,
  "nombre_places": 5,
  "usage": "particulier|taxi|transport_commun|utilitaire",
  "proprietaire_nom": "",
  "chassis": "",
  "date_mise_en_circulation": "JJ/MM/AAAA",
  "confiance": "haute|moyenne|faible"
}"""
    try:
        reponse = await ia_client.analyser_image_vision(
            image_b64=image_b64, prompt=prompt, mode=ModeIA.PRECISION,
        )
        data = reponse.as_json()
    except Exception as e:
        raise HTTPException(500, f"OCR carte grise échoué : {str(e)[:200]}")

    await _debit_llm_kyc(current_user.user_id, reponse, "kyc_carte_grise_mobile")
    return {
        "donnees_extraites": data,
        "confiance": data.get("confiance"),
        "modele": getattr(reponse, "modele_utilise", None),
    }
