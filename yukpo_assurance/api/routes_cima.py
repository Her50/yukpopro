"""Routes CIMA — réglementation et états financiers"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from modules.cima.code_cima_engine import cima_engine
from modules.cima.etats_reglementaires import generateur_etats
from modules.cima.verificateur_crca import verificateur_crca
from core.auth import TokenData, get_current_user, require_permission

router = APIRouter(dependencies=[Depends(require_permission("cima"))])


class QuestionCIMARequest(BaseModel):
    question: str
    role: str = "agent"
    contexte: Optional[str] = None


class MargeRequest(BaseModel):
    primes_nettes: float
    charge_sinistres_moyenne_3ans: float
    capitaux_propres: float


class CouvertureRequest(BaseModel):
    provisions_techniques: float
    actifs_admis: float


class RatioSPRequest(BaseModel):
    sinistres_payes: float
    variation_psap: float
    primes_nettes: float
    branche: str = "auto"


class EtatRequest(BaseModel):
    code_etat: str
    annee: int
    trimestre: Optional[int] = None
    donnees_manuelles: Optional[dict] = None


@router.post("/question")
async def question_cima(req: QuestionCIMARequest):
    """Q&R réglementaire CIMA avec citation d'articles"""
    return await cima_engine.repondre_question_cima(
        question=req.question,
        role_utilisateur=req.role,
        contexte_supplementaire=req.contexte,
    )


@router.post("/ratios/marge-solvabilite")
async def marge_solvabilite(req: MargeRequest):
    """Calcul de la marge de solvabilité non-vie (Art. 337-1 CIMA)"""
    return cima_engine.calculer_marge_solvabilite_non_vie(
        primes_nettes=req.primes_nettes,
        charge_sinistres_moyenne_3ans=req.charge_sinistres_moyenne_3ans,
        capitaux_propres=req.capitaux_propres,
    )


@router.post("/ratios/couverture-provisions")
async def couverture_provisions(req: CouvertureRequest):
    """Vérification de la couverture des provisions techniques (Art. 335 CIMA)"""
    return cima_engine.calculer_couverture_provisions(
        provisions_techniques=req.provisions_techniques,
        actifs_admis_en_couverture=req.actifs_admis,
    )


@router.post("/ratios/sinistres-primes")
async def ratio_sp(req: RatioSPRequest):
    """Calcul du ratio S/P par branche"""
    return cima_engine.calculer_ratio_sinistres_primes(
        sinistres_payes=req.sinistres_payes,
        variation_psap=req.variation_psap,
        primes_nettes=req.primes_nettes,
        branche=req.branche,
    )


@router.post("/conformite")
async def rapport_conformite(donnees: dict):
    """Rapport de conformité CIMA global"""
    return cima_engine.rapport_conformite_global(donnees)


@router.get("/delai/{type_sinistre}")
async def delai_reglementaire(type_sinistre: str):
    """Délai réglementaire CIMA pour un type de sinistre"""
    return cima_engine.get_delai_reglementaire(type_sinistre)


@router.post("/etats/generer")
async def generer_etat(req: EtatRequest):
    """Génère un état CIMA réglementaire (C1 à C20)"""
    return await generateur_etats.generer_etat(
        code_etat=req.code_etat,
        annee=req.annee,
        trimestre=req.trimestre,
        donnees_manuelles=req.donnees_manuelles,
    )


@router.post("/etats/pack-annuel/{annee}")
async def pack_annuel(annee: int):
    """Génère le pack complet des 20 états CIMA annuels"""
    return await generateur_etats.generer_pack_annuel_complet(annee)


@router.get("/inspection-crca/{annee}")
async def inspection_crca(annee: int = 2025):
    """Simulation d'inspection CRCA — grille de 7 points avec plan d'action IA"""
    rapport = await verificateur_crca.inspecter(annee)
    return verificateur_crca.rapport_to_dict(rapport)


# ─── Provisions techniques CIMA ───────────────────────────────────────────────

class PSAPRequest(BaseModel):
    sinistres_declares: list[dict]
    methode: str = "dossier_par_dossier"


class PPNARequest(BaseModel):
    primes_emises: float
    date_effet_exercice: str
    date_cloture_exercice: str
    methode: str = "prorata_temporis"


class PMVieRequest(BaseModel):
    capital_assure_fcfa: float
    prime_annuelle_fcfa: float
    age_entree: int
    duree_contrat_ans: int
    annee_courante_contrat: int
    taux_technique: float = 0.035
    table_mortalite: str = "TD_88_90"
    type_contrat: str = "mixte"


class ProvisionsPRCRequest(BaseModel):
    primes_nettes_exercice: float
    ratio_sp_moyen_historique: float = 0.65


@router.post("/provisions/psap", summary="Calculer la PSAP (Art. 334-2 CIMA)")
async def calculer_psap(req: PSAPRequest):
    """
    Provision pour Sinistres À Payer.
    Méthodes : dossier_par_dossier, chain_ladder, bornhuetter_ferguson.
    """
    return cima_engine.calculer_psap(req.sinistres_declares, req.methode)


@router.post("/provisions/ppna", summary="Calculer la PPNA (Art. 334-1 CIMA)")
async def calculer_ppna(req: PPNARequest):
    """
    Provision Pour Primes Non Acquises.
    Méthodes : prorata_temporis (CIMA), quart_inventaire, huitieme.
    """
    return cima_engine.calculer_ppna(
        req.primes_emises, req.date_effet_exercice,
        req.date_cloture_exercice, req.methode
    )


@router.post("/provisions/pm-vie", summary="Calculer les PM Vie (Art. 334-4 CIMA)")
async def calculer_pm_vie(req: PMVieRequest):
    """
    Provisions Mathématiques Vie — méthode prospective CIMA.
    Tables agréées : TD_88_90, TV_88_90, CIMA_2016.
    Types : mixte, deces_pur, vie_pure, rente_viagere.
    """
    return cima_engine.calculer_pm_vie(
        capital_assure_fcfa=req.capital_assure_fcfa,
        prime_annuelle_fcfa=req.prime_annuelle_fcfa,
        age_entree=req.age_entree,
        duree_contrat_ans=req.duree_contrat_ans,
        annee_courante_contrat=req.annee_courante_contrat,
        taux_technique=req.taux_technique,
        table_mortalite=req.table_mortalite,
        type_contrat=req.type_contrat,
    )


@router.post("/provisions/prc", summary="Calculer la PRC (Art. 334-3 CIMA)")
async def calculer_prc(req: ProvisionsPRCRequest):
    """
    Provision pour Risques en Cours.
    Requise si ratio S/P attendu > 100% sur les primes non acquises.
    """
    return cima_engine.calculer_provision_risques_en_cours(
        req.primes_nettes_exercice, req.ratio_sp_moyen_historique
    )


@router.post("/provisions/rapport-complet", summary="Rapport complet provisions (État C5)")
async def rapport_provisions_complet(donnees: dict):
    """
    Rapport complet de toutes les provisions techniques CIMA.
    Génère les données pour l'État C5 (reporting CRCA).
    Inclut : PSAP, PPNA, PM Vie, PRC.
    """
    return cima_engine.rapport_provisions_complet(donnees)
