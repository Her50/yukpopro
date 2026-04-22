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
