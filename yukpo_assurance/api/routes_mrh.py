"""Routes MRH (Multi-Risques Habitation) — Branche IRD CIMA"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from modules.souscription.mrh import DossierMRH, service_mrh
from modules.souscription.portail import registre
from core.auth import TokenData, get_current_user, require_permission

router = APIRouter(dependencies=[Depends(get_current_user)])


class DevisMRHRequest(BaseModel):
    type_bien: str = "appartement"
    statut_occupant: str = "locataire"
    adresse: str = ""
    ville: str = ""
    pays: str = "CM"
    surface_m2: float = 0
    nb_pieces: int = 3
    type_construction: str = "construction_dur"
    annee_construction: int = 2010
    nb_baies_vitrees: int = 4
    valeur_batiment_fcfa: float = 0
    valeur_mobilier_fcfa: float = 0
    valeur_objets_valeur_fcfa: float = 0
    valeur_appareils_fcfa: float = 0
    loyer_mensuel_fcfa: float = 0
    garanties: list[str] = ["incendie", "vol", "degats_eaux", "rc_locataire", "bris_glace"]
    mesures_securite: list[str] = []
    situation_geographique: str = "zone_urbaine_standard"
    sinistralite_3ans: str = "sans_sinistre_3ans"
    nom_assure: str = ""
    telephone: str = ""
    email: str = ""
    agent_code: Optional[str] = None
    courtier_code: Optional[str] = None
    date_effet: Optional[str] = None
    enrichir_ia: bool = False


class DeclarationSinistreMRHRequest(BaseModel):
    type_sinistre: str
    description: str
    valeur_dommages_fcfa: float
    date_sinistre: str


@router.post("/devis", summary="Calculer un devis MRH")
async def calculer_devis_mrh(
    req: DevisMRHRequest,
    current_user: TokenData = Depends(require_permission("souscription")),
):
    """
    Calcule un devis MRH complet par garantie.
    Conforme CIMA Branche IRD Art. 199-211. Recommandations IA incluses.
    """
    dossier_data = req.model_dump()
    enrichir_ia = dossier_data.pop("enrichir_ia", False)
    dossier = DossierMRH(**{k: v for k, v in dossier_data.items() if k in DossierMRH.__dataclass_fields__})
    devis = await service_mrh.calculer_devis(dossier, enrichir_ia=enrichir_ia)

    return {
        "prime_nette_totale_fcfa": devis.prime_nette_totale,
        "taxes_cima_fcfa": devis.taxes_cima,
        "taxes_locales_fcfa": devis.taxes_locales,
        "prime_ttc_fcfa": devis.prime_ttc,
        "detail_par_garantie": devis.detail_par_garantie,
        "garanties_incluses": devis.garanties_incluses,
        "garanties_optionnelles": devis.garanties_optionnelles_disponibles,
        "franchises": devis.franchises,
        "exclusions": devis.exclusions,
        "zone_catnat": devis.zone_catnat,
        "score_risque": devis.score_risque,
        "coefficients_appliques": devis.coefficients_appliques,
        "recommandations": devis.recommandations,
        "base_reglementaire": "Art. 199-211 Code CIMA — Branche IRD",
    }


@router.post("/emettre", summary="Émettre une police MRH")
async def emettre_police_mrh(
    req: DevisMRHRequest,
    current_user: TokenData = Depends(require_permission("souscription")),
):
    """
    Émet une police MRH et l'intègre dans ORASS.
    Génère un numéro de police YK-MR-{YYYY}-{SEQ}.
    """
    dossier_data = req.model_dump()
    dossier_data.pop("enrichir_ia", None)
    dossier = DossierMRH(**{k: v for k, v in dossier_data.items() if k in DossierMRH.__dataclass_fields__})
    devis = await service_mrh.calculer_devis(dossier, enrichir_ia=False)

    numero_police = registre.generer_numero_police("mrh")
    resultat = await service_mrh.emettre_police(dossier, devis, numero_police)

    # Enregistrement registre global
    from datetime import date, timedelta
    registre.sauvegarder(numero_police, {
        "branche": "mrh",
        "nom": dossier.nom_assure,
        "telephone": dossier.telephone,
        "adresse": dossier.adresse,
        "ville": dossier.ville,
        "prime_nette": devis.prime_nette_totale,
        "prime_ttc": devis.prime_ttc,
        "date_effet": dossier.date_effet or date.today().isoformat(),
        "date_echeance": resultat["police"]["date_echeance"],
        "agent_code": dossier.agent_code,
        "courtier_code": dossier.courtier_code,
        "garanties": devis.garanties_incluses,
        "statut": "actif",
    })

    return resultat


@router.post("/{numero_police}/sinistre", summary="Déclarer un sinistre MRH")
async def declarer_sinistre_mrh(
    numero_police: str,
    req: DeclarationSinistreMRHRequest,
    current_user: TokenData = Depends(require_permission("sinistres")),
):
    """
    Déclare un sinistre MRH. Évalue la couverture, applique la franchise.
    Délai de règlement max 30 jours (Art. 12 CIMA).
    """
    return await service_mrh.declarer_sinistre(
        numero_police=numero_police,
        type_sinistre=req.type_sinistre,
        description=req.description,
        valeur_dommages_fcfa=req.valeur_dommages_fcfa,
        date_sinistre=req.date_sinistre,
    )


@router.get("/microassurance", summary="Pack microassurance MRH")
async def calculer_microassurance_mrh(
    surface_m2: float = Query(..., description="Surface en m²"),
    ville: str = Query("Yaoundé", description="Ville"),
    pays: str = Query("CM", description="Code pays CIMA"),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Calcule un pack microassurance MRH (Circulaire CRCA 2024-001).
    Cible les ménages à faibles revenus. Prime < 50 000 FCFA/an.
    """
    return service_mrh.calculer_microassurance_mrh(surface_m2, ville, pays)


@router.get("/{numero_police}/revision", summary="Révision annuelle MRH")
async def revision_annuelle_mrh(
    numero_police: str,
    taux_inflation_pct: float = Query(3.0, description="Taux d'inflation en %"),
    current_user: TokenData = Depends(require_permission("souscription")),
):
    """Calcule la révision annuelle de la prime MRH selon l'inflation."""
    return service_mrh.calculer_revision_annuelle(numero_police, taux_inflation_pct)


@router.get("/statistiques", summary="Statistiques portefeuille MRH")
async def statistiques_mrh(
    current_user: TokenData = Depends(require_permission("analytics")),
):
    """Analyse du portefeuille MRH : types de biens, villes, zones catnat."""
    return service_mrh.statistiques_portefeuille()
