"""
YukpoAssurance — Routes API Module Commercial
Prospects, pipeline, objectifs, campagnes, tableau de bord commercial.
"""
from datetime import datetime, date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, TokenData, require_permission
from core.database import get_db, ProspectDB, ObjectifCommercialDB, CampagneDB
from modules.commercial.gestionnaire_commercial import (
    score_prospect, calculer_avancement_objectif,
    prospects_a_relancer, generer_tableau_bord_commercial,
    SOURCES_LEAD, BRANCHES_PRODUIT, STATUTS_PIPELINE,
)

router = APIRouter()


# ─── Modèles Pydantic ─────────────────────────────────────────────────────────

class ProspectCreate(BaseModel):
    nom: str
    prenom: Optional[str] = None
    telephone: Optional[str] = None
    email: Optional[str] = None
    source: str = "appel_entrant"
    branche_interesse: Optional[str] = None
    deja_assure: bool = False
    budget_fcfa: float = 0
    delai_decision_jours: int = 30
    notes: Optional[str] = None

class ProspectUpdate(BaseModel):
    statut: Optional[str] = None
    notes: Optional[str] = None
    branche_interesse: Optional[str] = None
    agent_id: Optional[int] = None
    budget_fcfa: Optional[float] = None

class ObjectifCreate(BaseModel):
    agent_id: Optional[int] = None
    annee: int
    mois: int
    type_objectif: str   # "primes" | "contrats" | "prospects"
    valeur_cible: float
    description: Optional[str] = None

class CampagneCreate(BaseModel):
    nom: str
    type_campagne: str   # "renouvellement" | "fidelisation" | "acquisition" | "cross_selling"
    description: Optional[str] = None
    date_debut: date
    date_fin: date
    cibles: list = []   # liste de critères de ciblage
    budget_fcfa: float = 0


# ─── PROSPECTS ────────────────────────────────────────────────────────────────

@router.post("/prospects", summary="Créer un prospect")
async def creer_prospect(
    data: ProspectCreate,
    current_user: TokenData = Depends(require_permission("commercial:write")),
    db: AsyncSession = Depends(get_db),
):
    donnees_score = data.model_dump()
    resultat_score = score_prospect(donnees_score)
    prospect = ProspectDB(
        compagnie_id=current_user.compagnie_id,
        agent_id=current_user.user_id,
        agent_nom=current_user.user_nom,
        score=resultat_score["score"],
        niveau_qualification=resultat_score["niveau"],
        statut="nouveau",
        dernier_contact=datetime.utcnow(),
        **{k: v for k, v in data.model_dump().items() if k not in ("notes",)},
        notes=data.notes,
    )
    db.add(prospect)
    await db.commit()
    await db.refresh(prospect)
    return {
        "prospect_id": prospect.id,
        "score": resultat_score["score"],
        "niveau": resultat_score["niveau"],
        "raisons": resultat_score["raisons"],
    }


@router.get("/prospects", summary="Lister les prospects")
async def lister_prospects(
    statut: Optional[str] = None,
    agent_id: Optional[int] = None,
    branche: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: TokenData = Depends(require_permission("commercial:read")),
    db: AsyncSession = Depends(get_db),
):
    q = select(ProspectDB).where(ProspectDB.compagnie_id == current_user.compagnie_id)
    if statut:
        q = q.where(ProspectDB.statut == statut)
    if agent_id:
        q = q.where(ProspectDB.agent_id == agent_id)
    if branche:
        q = q.where(ProspectDB.branche_interesse == branche)
    q = q.order_by(ProspectDB.score.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    prospects = result.scalars().all()
    total_q = select(func.count(ProspectDB.id)).where(ProspectDB.compagnie_id == current_user.compagnie_id)
    total = (await db.execute(total_q)).scalar()
    return {"prospects": [_prospect_to_dict(p) for p in prospects], "total": total}


@router.patch("/prospects/{prospect_id}", summary="Mettre à jour un prospect")
async def update_prospect(
    prospect_id: int,
    data: ProspectUpdate,
    current_user: TokenData = Depends(require_permission("commercial:write")),
    db: AsyncSession = Depends(get_db),
):
    p = await _get_prospect_or_404(prospect_id, current_user.compagnie_id, db)
    if data.statut:
        if data.statut not in STATUTS_PIPELINE:
            raise HTTPException(400, f"Statut invalide. Valeurs : {STATUTS_PIPELINE}")
        p.statut = data.statut
    if data.notes:
        p.notes = data.notes
    if data.branche_interesse:
        p.branche_interesse = data.branche_interesse
    if data.budget_fcfa is not None:
        p.budget_fcfa = data.budget_fcfa
    p.dernier_contact = datetime.utcnow()
    p.mise_a_jour = datetime.utcnow()
    await db.commit()
    return {"message": "Prospect mis à jour", "prospect_id": prospect_id, "statut": p.statut}


@router.get("/prospects/a-relancer", summary="Prospects à relancer")
async def prospects_relance(
    jours: int = Query(7, ge=1, le=90),
    current_user: TokenData = Depends(require_permission("commercial:read")),
    db: AsyncSession = Depends(get_db),
):
    q = select(ProspectDB).where(
        and_(
            ProspectDB.compagnie_id == current_user.compagnie_id,
            ProspectDB.statut.notin_(["souscrit", "perdu"]),
        )
    )
    result = await db.execute(q)
    tous = [_prospect_to_dict(p) for p in result.scalars().all()]
    a_relancer = prospects_a_relancer(tous, jours_sans_contact=jours)
    return {"a_relancer": a_relancer, "total": len(a_relancer)}


# ─── OBJECTIFS ───────────────────────────────────────────────────────────────

@router.post("/objectifs", summary="Créer un objectif commercial")
async def creer_objectif(
    data: ObjectifCreate,
    current_user: TokenData = Depends(require_permission("commercial:write")),
    db: AsyncSession = Depends(get_db),
):
    obj = ObjectifCommercialDB(
        compagnie_id=current_user.compagnie_id,
        agent_id=data.agent_id or current_user.user_id,
        annee=data.annee,
        mois=data.mois,
        type_objectif=data.type_objectif,
        valeur_cible=data.valeur_cible,
        valeur_atteinte=0,
        description=data.description,
        cree_par_id=current_user.user_id,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"objectif_id": obj.id, "message": "Objectif créé"}


@router.patch("/objectifs/{objectif_id}/progression", summary="Mettre à jour la progression")
async def update_objectif(
    objectif_id: int,
    valeur_atteinte: float,
    current_user: TokenData = Depends(require_permission("commercial:write")),
    db: AsyncSession = Depends(get_db),
):
    q = select(ObjectifCommercialDB).where(
        and_(ObjectifCommercialDB.id == objectif_id, ObjectifCommercialDB.compagnie_id == current_user.compagnie_id)
    )
    obj = (await db.execute(q)).scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Objectif introuvable")
    obj.valeur_atteinte = valeur_atteinte
    obj.mise_a_jour = datetime.utcnow()
    avancement = calculer_avancement_objectif(obj.valeur_cible, valeur_atteinte)
    await db.commit()
    return {"message": "Progression mise à jour", "avancement": avancement}


@router.get("/objectifs", summary="Lister les objectifs")
async def lister_objectifs(
    annee: int = date.today().year,
    mois: Optional[int] = None,
    agent_id: Optional[int] = None,
    current_user: TokenData = Depends(require_permission("commercial:read")),
    db: AsyncSession = Depends(get_db),
):
    q = select(ObjectifCommercialDB).where(
        and_(ObjectifCommercialDB.compagnie_id == current_user.compagnie_id, ObjectifCommercialDB.annee == annee)
    )
    if mois:
        q = q.where(ObjectifCommercialDB.mois == mois)
    if agent_id:
        q = q.where(ObjectifCommercialDB.agent_id == agent_id)
    result = await db.execute(q)
    objectifs = result.scalars().all()
    return {
        "objectifs": [
            {
                "id": o.id, "agent_id": o.agent_id, "type_objectif": o.type_objectif,
                "valeur_cible": o.valeur_cible, "valeur_atteinte": o.valeur_atteinte,
                "mois": o.mois, "annee": o.annee, "description": o.description,
                **calculer_avancement_objectif(o.valeur_cible, o.valeur_atteinte),
            }
            for o in objectifs
        ]
    }


# ─── CAMPAGNES ────────────────────────────────────────────────────────────────

@router.post("/campagnes", summary="Créer une campagne commerciale")
async def creer_campagne(
    data: CampagneCreate,
    current_user: TokenData = Depends(require_permission("commercial:write")),
    db: AsyncSession = Depends(get_db),
):
    camp = CampagneDB(
        compagnie_id=current_user.compagnie_id,
        nom=data.nom,
        type_campagne=data.type_campagne,
        description=data.description,
        date_debut=data.date_debut,
        date_fin=data.date_fin,
        cibles=data.cibles,
        budget_fcfa=data.budget_fcfa,
        statut="planifiee",
        cree_par_id=current_user.user_id,
    )
    db.add(camp)
    await db.commit()
    await db.refresh(camp)
    return {"campagne_id": camp.id, "message": "Campagne créée"}


@router.get("/campagnes", summary="Lister les campagnes")
async def lister_campagnes(
    statut: Optional[str] = None,
    current_user: TokenData = Depends(require_permission("commercial:read")),
    db: AsyncSession = Depends(get_db),
):
    q = select(CampagneDB).where(CampagneDB.compagnie_id == current_user.compagnie_id)
    if statut:
        q = q.where(CampagneDB.statut == statut)
    q = q.order_by(CampagneDB.date_debut.desc())
    result = await db.execute(q)
    return {"campagnes": [_campagne_to_dict(c) for c in result.scalars().all()]}


# ─── TABLEAU DE BORD COMMERCIAL ──────────────────────────────────────────────

@router.get("/tableau-de-bord", summary="Tableau de bord commercial")
async def tableau_de_bord(
    annee: int = date.today().year,
    mois: int = date.today().month,
    current_user: TokenData = Depends(require_permission("commercial:read")),
    db: AsyncSession = Depends(get_db),
):
    # Prospects
    q_p = select(ProspectDB).where(ProspectDB.compagnie_id == current_user.compagnie_id)
    prospects_raw = (await db.execute(q_p)).scalars().all()
    prospects = [_prospect_to_dict(p) for p in prospects_raw]

    # Objectifs du mois
    q_o = select(ObjectifCommercialDB).where(
        and_(
            ObjectifCommercialDB.compagnie_id == current_user.compagnie_id,
            ObjectifCommercialDB.annee == annee,
            ObjectifCommercialDB.mois == mois,
        )
    )
    objectifs = [
        {"valeur_cible": o.valeur_cible, "valeur_atteinte": o.valeur_atteinte, "type_objectif": o.type_objectif}
        for o in (await db.execute(q_o)).scalars().all()
    ]

    # Convertis ce mois
    souscrit_mois = sum(1 for p in prospects if p.get("statut") == "souscrit")

    tdb = generer_tableau_bord_commercial(prospects, objectifs, souscrit_mois, 0)
    return tdb


# ─── RÉFÉRENTIEL ─────────────────────────────────────────────────────────────

@router.get("/referentiel")
async def get_referentiel(current_user: TokenData = Depends(get_current_user)):
    return {"sources_lead": SOURCES_LEAD, "branches": BRANCHES_PRODUIT, "statuts_pipeline": STATUTS_PIPELINE}


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _get_prospect_or_404(prospect_id: int, compagnie_id: int, db: AsyncSession) -> ProspectDB:
    q = select(ProspectDB).where(and_(ProspectDB.id == prospect_id, ProspectDB.compagnie_id == compagnie_id))
    p = (await db.execute(q)).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Prospect introuvable")
    return p

def _prospect_to_dict(p) -> dict:
    if hasattr(p, "id"):
        return {
            "id": p.id, "nom": p.nom, "prenom": p.prenom, "telephone": p.telephone,
            "email": p.email, "source": p.source, "branche_interesse": p.branche_interesse,
            "statut": p.statut, "score": p.score, "niveau_qualification": p.niveau_qualification,
            "agent_nom": p.agent_nom, "notes": p.notes, "budget_fcfa": p.budget_fcfa,
            "dernier_contact": str(p.dernier_contact) if p.dernier_contact else None,
        }
    return p

def _campagne_to_dict(c: CampagneDB) -> dict:
    return {
        "id": c.id, "nom": c.nom, "type_campagne": c.type_campagne,
        "statut": c.statut, "date_debut": str(c.date_debut), "date_fin": str(c.date_fin),
        "budget_fcfa": c.budget_fcfa, "description": c.description,
    }
