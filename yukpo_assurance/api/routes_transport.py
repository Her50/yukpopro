"""Routes Transport Assurance — Branche 50 CIMA"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from modules.souscription.transport import (
    DossierTransport, service_transport
)
from modules.souscription.portail import registre, _CODE_BRANCHE
from core.auth import TokenData, get_current_user, require_permission

router = APIRouter(dependencies=[Depends(get_current_user)])


class DevisTransportRequest(BaseModel):
    type_couverture: str = "marchandises"
    type_transport: str = "terrestre_national"
    nom_assure: str = ""
    telephone: str = ""
    description_marchandises: str = ""
    valeur_marchandises_fcfa: float = 0
    poids_total_kg: float = 0
    nb_colis: int = 0
    lieu_chargement: str = ""
    lieu_livraison: str = ""
    pays_transit: list[str] = []
    date_chargement: Optional[str] = None
    date_livraison_prevue: Optional[str] = None
    chiffre_affaires_transport_fcfa: float = 0
    type_vehicule: str = "porteur"
    nb_vehicules: int = 1
    valeur_vehicule_neuf_fcfa: float = 0
    valeur_venale_vehicule_fcfa: float = 0
    annee_vehicule: int = 2020
    garanties_supplementaires: list[str] = []
    risques_speciaux: list[str] = []
    mode_tarification: str = "voyage_unique"
    nb_voyages_annuels: int = 1
    valeur_annuelle_fcfa: float = 0
    agent_code: Optional[str] = None
    courtier_code: Optional[str] = None
    date_effet: Optional[str] = None
    pays: str = "CM"
    enrichir_ia: bool = False


class DeclarationSinistreTransportRequest(BaseModel):
    description_sinistre: str
    valeur_dommages_fcfa: float
    lieu_sinistre: str
    date_sinistre: str


@router.post("/devis", summary="Calculer un devis transport")
async def calculer_devis_transport(
    req: DevisTransportRequest,
    current_user: TokenData = Depends(require_permission("souscription")),
):
    """
    Calcule un devis d'assurance transport (marchandises, RC transporteur, corps, CMR, flotte).
    Conforme barèmes CIMA Branche 50 — Art. 212-229.
    """
    pays = req.pays
    req_dict = req.model_dump()
    req_dict.pop("pays", None)
    req_dict.pop("enrichir_ia", None)

    dossier = DossierTransport(**{k: v for k, v in req_dict.items() if k in DossierTransport.__dataclass_fields__})
    devis = await service_transport.calculer_devis(dossier, pays=pays, enrichir_ia=req.enrichir_ia)

    return {
        "prime_nette_fcfa": devis.prime_nette,
        "taxes_cima_fcfa": devis.taxes_cima,
        "taxes_locales_fcfa": devis.taxes_locales,
        "prime_ttc_fcfa": devis.prime_ttc,
        "type_couverture": devis.type_couverture,
        "garanties_incluses": devis.garanties_incluses,
        "franchises": devis.franchises,
        "exclusions": devis.exclusions,
        "plafond_indemnisation_fcfa": devis.plafond_indemnisation_fcfa,
        "plafond_cmr_fcfa": devis.plafond_cmr_fcfa,
        "score_risque": devis.score_risque,
        "detail_calcul": devis.detail_calcul,
        "recommandations_ia": devis.recommandations_ia,
        "base_reglementaire": "Art. 212-229 Code CIMA — Branche Transport",
    }


@router.post("/emettre", summary="Émettre une police transport")
async def emettre_police_transport(
    req: DevisTransportRequest,
    current_user: TokenData = Depends(require_permission("souscription")),
):
    """
    Calcule le devis et émet une police transport. Intègre dans ORASS.
    Génère un numéro de police YK-TR-{YYYY}-{SEQ}.
    """
    pays = req.pays
    req_dict = req.model_dump()
    req_dict.pop("pays", None)
    req_dict.pop("enrichir_ia", None)

    dossier = DossierTransport(**{k: v for k, v in req_dict.items() if k in DossierTransport.__dataclass_fields__})
    devis = await service_transport.calculer_devis(dossier, pays=pays, enrichir_ia=False)

    numero_police = registre.generer_numero_police("transport")
    police = await service_transport.emettre_police(dossier, devis, numero_police)

    # Enregistrement dans le registre global
    from datetime import date, timedelta
    date_effet = dossier.date_effet or date.today().isoformat()
    registre.sauvegarder(numero_police, {
        "branche": "transport",
        "nom": dossier.nom_assure,
        "telephone": dossier.telephone,
        "prime_nette": devis.prime_nette,
        "prime_ttc": devis.prime_ttc,
        "date_effet": date_effet,
        "date_echeance": police.date_echeance,
        "agent_code": dossier.agent_code,
        "courtier_code": dossier.courtier_code,
        "type_couverture": dossier.type_couverture,
        "garanties": devis.garanties_incluses,
        "statut": "actif",
    })

    return {
        "succes": True,
        "numero_police": numero_police,
        "type_couverture": police.type_couverture,
        "date_effet": police.date_effet,
        "date_echeance": police.date_echeance,
        "prime_nette_fcfa": devis.prime_nette,
        "prime_ttc_fcfa": devis.prime_ttc,
        "garanties": devis.garanties_incluses,
        "plafond_indemnisation_fcfa": devis.plafond_indemnisation_fcfa,
        "plafond_cmr_fcfa": devis.plafond_cmr_fcfa,
        "message": (
            f"Police transport {numero_police} émise. "
            f"Prime TTC : {devis.prime_ttc:,.0f} FCFA."
        ),
    }


@router.post("/{numero_police}/sinistre", summary="Déclarer un sinistre transport")
async def declarer_sinistre_transport(
    numero_police: str,
    req: DeclarationSinistreTransportRequest,
    current_user: TokenData = Depends(require_permission("sinistres")),
):
    """Déclare un sinistre transport — calcule la récupération selon le traité."""
    return await service_transport.declarer_sinistre_transport(
        numero_police=numero_police,
        description_sinistre=req.description_sinistre,
        valeur_dommages_fcfa=req.valeur_dommages_fcfa,
        lieu_sinistre=req.lieu_sinistre,
        date_sinistre=req.date_sinistre,
    )


@router.get("/cmr/plafond", summary="Calculer plafond CMR")
async def calculer_plafond_cmr(
    poids_kg: float = Query(..., description="Poids total de la marchandise en kg"),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Calcule le plafond d'indemnisation CMR.
    Convention CMR 1956 Art. 23 §3 : 8,33 DTS/kg.
    """
    return service_transport.calculer_plafond_cmr(poids_kg=poids_kg)


@router.get("/statistiques", summary="Statistiques portefeuille transport")
async def statistiques_transport(
    current_user: TokenData = Depends(require_permission("analytics")),
):
    """Analyse du portefeuille transport (actif, primes, répartition)."""
    return service_transport.statistiques_portefeuille()
