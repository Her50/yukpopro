"""Routes courtiers — portail mobile, commissions, suivi"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from modules.courtiers.portal import SoumissionCourtier, portail_courtier
from core.auth import TokenData, get_current_user, require_permission

router = APIRouter(dependencies=[Depends(get_current_user)])


class SoumissionRequest(BaseModel):
    courtier_code: str
    branche: str
    photos_documents: list[str] = []
    donnees_client: dict = {}
    canal: str = "app_mobile"


@router.post("/soumettre")
async def soumettre_dossier(
    req: SoumissionRequest,
    current_user: TokenData = Depends(require_permission("souscription:submit")),
):
    """Soumission d'un nouveau dossier depuis l'app mobile courtier"""
    # Courtier ne peut soumettre que pour son propre code
    if current_user.role == "courtier" and req.courtier_code != current_user.user_nom:
        req.courtier_code = current_user.user_nom  # forcer le code courtier du token
    soumission = SoumissionCourtier(**req.model_dump())
    return await portail_courtier.soumettre_dossier(soumission)


@router.get("/{courtier_code}/tableau-de-bord")
async def tableau_de_bord(
    courtier_code: str,
    current_user: TokenData = Depends(get_current_user),
    mois: Optional[int] = None,
    annee: Optional[int] = None,
):
    """Tableau de bord temps réel — production, commissions, sinistres"""
    # Un courtier ne peut voir que son propre tableau de bord
    if current_user.role == "courtier" and courtier_code != current_user.user_nom:
        raise HTTPException(403, "Accès limité à votre propre portail")
    tb = await portail_courtier.tableau_de_bord(courtier_code, mois, annee)
    return {
        "courtier_code": tb.courtier_code,
        "periode": tb.periode,
        "polices_actives": tb.polices_actives,
        "nouvelles_polices_mois": tb.nouvelles_polices_mois,
        "commissions_dues_fcfa": tb.commissions_dues,
        "commissions_a_payer_fcfa": tb.commissions_a_payer,
        "sinistres_en_cours": tb.sinistres_en_cours,
        "taux_retention": f"{tb.taux_retention:.1%}",
        "alertes": tb.alertes,
    }


@router.get("/{courtier_code}/dossier/{numero_police}")
async def suivi_dossier(
    courtier_code: str,
    numero_police: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Suivi en temps réel d'un dossier soumis"""
    if current_user.role == "courtier" and courtier_code != current_user.user_nom:
        raise HTTPException(403, "Accès limité à votre propre portefeuille")
    return await portail_courtier.suivi_dossier(numero_police, courtier_code)


@router.get("/{courtier_code}/tableau-de-bord-detaille")
async def tableau_de_bord_detaille(
    courtier_code: str,
    current_user: TokenData = Depends(get_current_user),
    mois: Optional[int] = None,
    annee: Optional[int] = None,
):
    """
    Tableau de bord enrichi : top productions, sinistres ouverts,
    taux conversion, pipeline en cours, objectif vs réalisé.
    """
    if current_user.role == "courtier" and courtier_code != current_user.user_nom:
        raise HTTPException(403, "Accès limité à votre propre portail")
    return await portail_courtier.get_tableau_bord_courtier(courtier_code, mois, annee)


@router.get("/{courtier_code}/portefeuille")
async def portefeuille_complet(
    courtier_code: str,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Portefeuille complet : liste tous les contrats avec statut, prime,
    date d'échéance, commission estimée et alertes par contrat.
    """
    if current_user.role == "courtier" and courtier_code != current_user.user_nom:
        raise HTTPException(403, "Accès limité à votre propre portefeuille")
    return await portail_courtier.suivi_portefeuille_complet(courtier_code)


@router.get("/{courtier_code}/commissions")
async def commissions_detaillees(
    courtier_code: str,
    current_user: TokenData = Depends(get_current_user),
    annee: Optional[int] = None,
):
    """
    Commissions détaillées : par branche, par mois, avec projection annuelle.
    Retourne : réalisé, versé, solde et projection fin d'année.
    """
    if current_user.role == "courtier" and courtier_code != current_user.user_nom:
        raise HTTPException(403, "Accès limité à vos propres commissions")
    return await portail_courtier.calculer_commissions_detaillees(courtier_code, annee)


@router.get("/{courtier_code}/alertes")
async def alertes_courtier(
    courtier_code: str,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Alertes intelligentes : renouvellements à 60j, impayés,
    sinistres en attente, commissions en retard de versement.
    """
    if current_user.role == "courtier" and courtier_code != current_user.user_nom:
        raise HTTPException(403, "Accès limité à vos propres alertes")
    return await portail_courtier.alertes_courtier(courtier_code)


@router.get("/classement/top-performers")
async def classement_courtiers(
    current_user: TokenData = Depends(require_permission("analytics:read")),
    mois: Optional[int] = None,
    annee: Optional[int] = None,
):
    """
    Classement des courtiers — top performers du mois/année.
    Score composite : primes émises, nb polices, taux de rétention.
    Réservé aux rôles avec permission analytics:read.
    """
    return await portail_courtier.classement_courtiers(mois, annee)
