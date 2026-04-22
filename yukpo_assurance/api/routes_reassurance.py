"""Routes Réassurance — Art. 308-310 CIMA + Livre VI"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from modules.reassurance.gestionnaire_reassurance import (
    GestionnaireReassurance, TraiteReassurance,
    LigneCessionReassurance, REASSUREURS_AGREES_CIMA,
    gestionnaire_reassurance,
)
from core.auth import TokenData, get_current_user, require_permission

router = APIRouter(dependencies=[Depends(get_current_user)])


class TraiteRequest(BaseModel):
    id_traite: str
    nom_traite: str
    type_traite: str
    reassureur: str
    branche: str = "all"
    date_debut: str
    date_fin: str
    taux_cession_pct: float = 0
    commission_reassureur_pct: float = 0
    plein_conservation_fcfa: float = 0
    nb_pleins_traite: int = 0
    priorite_cedante_fcfa: float = 0
    portee_xl_fcfa: float = 0
    ratio_stop_loss_priorite_pct: float = 0
    ratio_stop_loss_limite_pct: float = 0
    prime_xl_pct: float = 0
    notation_reassureur: str = ""
    commentaires: str = ""


class CessionQuotePartRequest(BaseModel):
    id_traite: str
    prime_brute_fcfa: float
    capital_assure_fcfa: float
    sinistre_fcfa: float = 0


class CessionExcedentPleinRequest(BaseModel):
    id_traite: str
    prime_brute_fcfa: float
    capital_assure_fcfa: float
    sinistre_fcfa: float = 0


class XLRisqueRequest(BaseModel):
    id_traite: str
    sinistre_fcfa: float
    prime_assiette_fcfa: float


class StopLossRequest(BaseModel):
    id_traite: str
    sinistres_payes_fcfa: float
    primes_nettes_exercice_fcfa: float


class PMLRequest(BaseModel):
    portefeuille: list[dict]
    scenario: str = "standard"


class EtatC12Request(BaseModel):
    exercice: str
    primes_brutes_par_branche: dict[str, float]
    sinistres_par_branche: dict[str, float]


# ─── Traités ──────────────────────────────────────────────────────────────────

@router.post("/traites", summary="Créer un traité de réassurance")
async def creer_traite(
    req: TraiteRequest,
    current_user: TokenData = Depends(require_permission("daf")),
):
    """
    Crée un traité de réassurance.
    Vérifie la conformité Art. 308 CIMA (max 50% cession).
    Rôle requis : DAF ou DG.
    """
    traite = TraiteReassurance(**req.model_dump())
    return gestionnaire_reassurance.creer_traite(traite)


@router.get("/traites", summary="Lister les traités actifs")
async def lister_traites(
    branche: Optional[str] = Query(None, description="Filtrer par branche"),
    actifs_seulement: bool = Query(True),
    current_user: TokenData = Depends(require_permission("manager")),
):
    """Liste les traités de réassurance, filtrables par branche."""
    return gestionnaire_reassurance.lister_traites(branche=branche, actifs_seulement=actifs_seulement)


@router.get("/reassureurs-agrees", summary="Réassureurs agréés CIMA")
async def lister_reassureurs_agrees(
    current_user: TokenData = Depends(get_current_user),
):
    """Liste les réassureurs agréés CIMA (priorité Art. 308 al.2)."""
    return {
        "reassureurs": REASSUREURS_AGREES_CIMA,
        "note": "Art. 308 al.2 Code CIMA : priorité aux réassureurs agréés par la CRCA.",
        "priorites": ["Africa Re", "CICA-Re", "ZEP-Re"],
    }


# ─── Calcul des cessions ──────────────────────────────────────────────────────

@router.post("/cession/quote-part", summary="Calculer cession quote-part")
async def calculer_cession_quote_part(
    req: CessionQuotePartRequest,
    current_user: TokenData = Depends(require_permission("actuaire")),
):
    """
    Calcule la cession pour un traité quote-part.
    Retourne prime cédée, commission reçue, part sinistre réassureur.
    """
    return gestionnaire_reassurance.calculer_cession_quote_part(
        req.id_traite, req.prime_brute_fcfa, req.capital_assure_fcfa, req.sinistre_fcfa
    )


@router.post("/cession/excedent-plein", summary="Calculer cession excédent de plein")
async def calculer_cession_excedent_plein(
    req: CessionExcedentPleinRequest,
    current_user: TokenData = Depends(require_permission("actuaire")),
):
    """
    Calcule la cession pour un traité excédent de plein.
    Signale les risques dépassant la capacité du traité.
    """
    return gestionnaire_reassurance.calculer_cession_excedent_plein(
        req.id_traite, req.prime_brute_fcfa, req.capital_assure_fcfa, req.sinistre_fcfa
    )


@router.post("/cession/xl-risque", summary="Calculer récupération XL par risque")
async def calculer_xl_risque(
    req: XLRisqueRequest,
    current_user: TokenData = Depends(require_permission("actuaire")),
):
    """Calcule la récupération XL par risque selon priorité et portée."""
    return gestionnaire_reassurance.calculer_cession_xl_risque(
        req.id_traite, req.sinistre_fcfa, req.prime_assiette_fcfa
    )


@router.post("/cession/stop-loss", summary="Calculer récupération stop-loss")
async def calculer_stop_loss(
    req: StopLossRequest,
    current_user: TokenData = Depends(require_permission("actuaire")),
):
    """
    Calcule le déclenchement et la récupération stop-loss.
    Basé sur le ratio S/P réel vs la priorité contractuelle.
    """
    return gestionnaire_reassurance.calculer_cession_stop_loss(
        req.id_traite, req.sinistres_payes_fcfa, req.primes_nettes_exercice_fcfa
    )


# ─── PML et analyse ───────────────────────────────────────────────────────────

@router.post("/pml", summary="Analyse PML du portefeuille")
async def analyser_pml(
    req: PMLRequest,
    current_user: TokenData = Depends(require_permission("actuaire")),
):
    """
    Calcule le PML (Probable Maximum Loss) du portefeuille.
    Scénarios : standard (1/100 ans), modéré (1/25 ans), extreme (1/250 ans).
    Recommande la couverture XL catastrophe nécessaire.
    """
    return gestionnaire_reassurance.analyser_pml(req.portefeuille, req.scenario)


@router.get("/conformite-art308", summary="Vérifier conformité Art. 308 CIMA")
async def verifier_conformite_art308(
    current_user: TokenData = Depends(require_permission("daf")),
):
    """
    Vérifie le respect du plafond de cession Art. 308 CIMA (max 50%).
    Alerte si le taux global dépasse la limite légale.
    """
    return gestionnaire_reassurance.verifier_conformite_art308()


@router.get("/sinistres-recuperables", summary="Créances sur réassureurs")
async def sinistres_recuperables(
    current_user: TokenData = Depends(require_permission("daf")),
):
    """
    Total des sinistres récupérables sur réassureurs.
    À inscrire à l'actif du bilan (poste 25 PCSA).
    """
    return gestionnaire_reassurance.calculer_sinistres_recuperables_total()


# ─── Bordereau et états réglementaires ───────────────────────────────────────

@router.get("/bordereau", summary="Bordereau de cession")
async def generer_bordereau(
    periode_debut: str = Query(..., description="Date début YYYY-MM-DD"),
    periode_fin: str = Query(..., description="Date fin YYYY-MM-DD"),
    branche: Optional[str] = Query(None),
    current_user: TokenData = Depends(require_permission("daf")),
):
    """
    Génère le bordereau de cession réassurance pour une période.
    Utilisé pour la réconciliation comptable avec les réassureurs.
    """
    return gestionnaire_reassurance.generer_bordereau_cession(periode_debut, periode_fin, branche)


@router.post("/etat-c12", summary="Générer l'État C12 (CRCA)")
async def generer_etat_c12(
    req: EtatC12Request,
    current_user: TokenData = Depends(require_permission("daf")),
):
    """
    Génère l'État C12 — Réassurance Acceptée et Cédée (reporting CRCA annuel).
    Conforme Art. 308-310 Code CIMA.
    """
    return gestionnaire_reassurance.generer_etat_c12(
        req.exercice, req.primes_brutes_par_branche, req.sinistres_par_branche
    )


@router.get("/analyse-ia", summary="Analyse IA du programme de réassurance")
async def analyser_programme_ia(
    current_user: TokenData = Depends(require_permission("dg")),
):
    """
    Analyse IA du programme de réassurance.
    Recommandations de structuration, lacunes, réassureurs à privilégier.
    Rôle requis : DG ou DAF.
    """
    return await gestionnaire_reassurance.analyser_programme_ia()
