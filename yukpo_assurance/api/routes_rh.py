"""
YukpoAssurance — Routes API Ressources Humaines
Employés, congés, paie, évaluations, recrutement, organigramme.
"""
from datetime import date, datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, TokenData, require_permission
from core.database import get_db, EmployeDB, CongeDB, EvaluationDB, RecrutementDB
from modules.rh.gestionnaire_rh import (
    calculer_bulletin_paie, calculer_solde_conges,
    calculer_score_evaluation, DEPARTEMENTS_ASSURANCE,
    POSTES_PAR_DEPARTEMENT, CRITERES_EVALUATION,
)

router = APIRouter()


# ─── Modèles Pydantic ─────────────────────────────────────────────────────────

class EmployeCreate(BaseModel):
    matricule: str
    nom: str
    prenom: str
    poste: str
    departement: str
    date_embauche: date
    date_naissance: Optional[date] = None
    telephone: Optional[str] = None
    email: Optional[str] = None
    salaire_base: float = 0
    grade: Optional[str] = None
    responsable_id: Optional[int] = None

class CongeCreate(BaseModel):
    employe_id: int
    type_conge: str   # annuel | maladie | maternite | paternite | sans_solde | deuil
    date_debut: date
    date_fin: date
    motif: Optional[str] = None

class EvaluationCreate(BaseModel):
    employe_id: int
    annee: int
    trimestre: Optional[int] = None
    notes: dict   # {critere: note_sur_5}
    commentaire: Optional[str] = None
    objectifs_prochain: Optional[str] = None

class RecrutementCreate(BaseModel):
    poste: str
    departement: str
    description: Optional[str] = None
    salaire_min: Optional[float] = None
    salaire_max: Optional[float] = None
    date_limite: Optional[date] = None

class BulletinPaieRequest(BaseModel):
    employe_id: int
    mois: int
    annee: int
    primes: float = 0
    avances: float = 0
    absences_jours: int = 0


# ─── EMPLOYÉS ─────────────────────────────────────────────────────────────────

@router.post("/employes", summary="Créer un employé")
async def creer_employe(
    data: EmployeCreate,
    current_user: TokenData = Depends(require_permission("rh:write")),
    db: AsyncSession = Depends(get_db),
):
    employe = EmployeDB(
        compagnie_id=current_user.compagnie_id,
        cree_par_id=current_user.user_id,
        **data.model_dump(),
    )
    db.add(employe)
    await db.commit()
    await db.refresh(employe)
    return {"employe_id": employe.id, "matricule": employe.matricule, "message": "Employé créé"}


@router.get("/employes", summary="Lister les employés")
async def lister_employes(
    departement: Optional[str] = None,
    statut: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: TokenData = Depends(require_permission("rh:read")),
    db: AsyncSession = Depends(get_db),
):
    q = select(EmployeDB).where(EmployeDB.compagnie_id == current_user.compagnie_id)
    if departement:
        q = q.where(EmployeDB.departement == departement)
    if statut:
        q = q.where(EmployeDB.statut == statut)
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    employes = result.scalars().all()
    total_q = select(func.count(EmployeDB.id)).where(EmployeDB.compagnie_id == current_user.compagnie_id)
    total = (await db.execute(total_q)).scalar()
    return {
        "employes": [_employe_to_dict(e) for e in employes],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/employes/{employe_id}", summary="Détail d'un employé")
async def get_employe(
    employe_id: int,
    current_user: TokenData = Depends(require_permission("rh:read")),
    db: AsyncSession = Depends(get_db),
):
    e = await _get_employe_or_404(employe_id, current_user.compagnie_id, db)
    solde = calculer_solde_conges(e.date_embauche, e.conges_pris_total or 0)
    return {**_employe_to_dict(e), "solde_conges": solde}


@router.patch("/employes/{employe_id}", summary="Modifier un employé")
async def modifier_employe(
    employe_id: int,
    data: dict,
    current_user: TokenData = Depends(require_permission("rh:write")),
    db: AsyncSession = Depends(get_db),
):
    e = await _get_employe_or_404(employe_id, current_user.compagnie_id, db)
    champs_modifiables = {"poste", "salaire_base", "grade", "statut", "telephone", "email", "responsable_id"}
    for k, v in data.items():
        if k in champs_modifiables:
            setattr(e, k, v)
    e.mise_a_jour = datetime.utcnow()
    await db.commit()
    return {"message": "Employé mis à jour", "employe_id": employe_id}


# ─── CONGÉS ───────────────────────────────────────────────────────────────────

@router.post("/conges", summary="Demande de congé")
async def demander_conge(
    data: CongeCreate,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    nb_jours = (data.date_fin - data.date_debut).days + 1
    if nb_jours <= 0:
        raise HTTPException(400, "Date de fin doit être après la date de début")

    conge = CongeDB(
        compagnie_id=current_user.compagnie_id,
        employe_id=data.employe_id,
        type_conge=data.type_conge,
        date_debut=data.date_debut,
        date_fin=data.date_fin,
        nb_jours=nb_jours,
        motif=data.motif,
        statut="en_attente",
        demande_par_id=current_user.user_id,
    )
    db.add(conge)
    await db.commit()
    await db.refresh(conge)
    return {"conge_id": conge.id, "nb_jours": nb_jours, "statut": "en_attente"}


@router.get("/conges", summary="Lister les congés")
async def lister_conges(
    employe_id: Optional[int] = None,
    statut: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: TokenData = Depends(require_permission("rh:read")),
    db: AsyncSession = Depends(get_db),
):
    q = select(CongeDB).where(CongeDB.compagnie_id == current_user.compagnie_id)
    if employe_id:
        q = q.where(CongeDB.employe_id == employe_id)
    if statut:
        q = q.where(CongeDB.statut == statut)
    q = q.order_by(CongeDB.date_debut.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    return {"conges": [_conge_to_dict(c) for c in result.scalars().all()]}


@router.patch("/conges/{conge_id}/statut", summary="Approuver/rejeter un congé")
async def statuer_conge(
    conge_id: int,
    statut: str,   # "approuve" | "rejete"
    commentaire: Optional[str] = None,
    current_user: TokenData = Depends(require_permission("rh:approve")),
    db: AsyncSession = Depends(get_db),
):
    if statut not in ("approuve", "rejete"):
        raise HTTPException(400, "Statut invalide : 'approuve' ou 'rejete'")
    q = select(CongeDB).where(
        and_(CongeDB.id == conge_id, CongeDB.compagnie_id == current_user.compagnie_id)
    )
    conge = (await db.execute(q)).scalar_one_or_none()
    if not conge:
        raise HTTPException(404, "Congé introuvable")
    conge.statut = statut
    conge.approuve_par_id = current_user.user_id
    conge.approuve_par_nom = current_user.user_nom
    conge.commentaire_approbateur = commentaire
    conge.date_decision = datetime.utcnow()
    await db.commit()
    return {"message": f"Congé {statut}", "conge_id": conge_id}


# ─── PAIE ─────────────────────────────────────────────────────────────────────

@router.post("/paie/bulletin", summary="Générer un bulletin de paie")
async def generer_bulletin(
    data: BulletinPaieRequest,
    current_user: TokenData = Depends(require_permission("rh:paie")),
    db: AsyncSession = Depends(get_db),
):
    e = await _get_employe_or_404(data.employe_id, current_user.compagnie_id, db)
    bulletin = calculer_bulletin_paie(
        salaire_brut=e.salaire_base,
        primes=data.primes,
        avances=data.avances,
        absences_jours=data.absences_jours,
    )
    return {
        "employe": {"id": e.id, "nom": e.nom, "prenom": e.prenom, "matricule": e.matricule, "poste": e.poste},
        "periode": f"{data.mois:02d}/{data.annee}",
        "bulletin": bulletin,
    }


@router.get("/paie/masse-salariale", summary="Masse salariale par département")
async def masse_salariale(
    current_user: TokenData = Depends(require_permission("rh:paie")),
    db: AsyncSession = Depends(get_db),
):
    q = select(EmployeDB).where(
        and_(EmployeDB.compagnie_id == current_user.compagnie_id, EmployeDB.statut == "actif")
    )
    employes = (await db.execute(q)).scalars().all()
    par_dept: dict = {}
    for e in employes:
        dept = e.departement or "Non défini"
        if dept not in par_dept:
            par_dept[dept] = {"nb_employes": 0, "masse_salariale": 0}
        par_dept[dept]["nb_employes"] += 1
        par_dept[dept]["masse_salariale"] += e.salaire_base or 0
    total = sum(v["masse_salariale"] for v in par_dept.values())
    return {
        "par_departement": par_dept,
        "total_employes": len(employes),
        "masse_salariale_totale_fcfa": total,
    }


# ─── ÉVALUATIONS ─────────────────────────────────────────────────────────────

@router.post("/evaluations", summary="Créer une évaluation")
async def creer_evaluation(
    data: EvaluationCreate,
    current_user: TokenData = Depends(require_permission("rh:write")),
    db: AsyncSession = Depends(get_db),
):
    resultat = calculer_score_evaluation(data.notes)
    eval_db = EvaluationDB(
        compagnie_id=current_user.compagnie_id,
        employe_id=data.employe_id,
        annee=data.annee,
        trimestre=data.trimestre,
        notes=data.notes,
        score=resultat["score"],
        mention=resultat["mention"],
        commentaire=data.commentaire,
        objectifs_prochain=data.objectifs_prochain,
        evaluateur_id=current_user.user_id,
        evaluateur_nom=current_user.user_nom,
    )
    db.add(eval_db)
    await db.commit()
    await db.refresh(eval_db)
    return {"evaluation_id": eval_db.id, "resultat": resultat}


@router.get("/evaluations/{employe_id}", summary="Historique évaluations d'un employé")
async def get_evaluations(
    employe_id: int,
    current_user: TokenData = Depends(require_permission("rh:read")),
    db: AsyncSession = Depends(get_db),
):
    q = select(EvaluationDB).where(
        and_(EvaluationDB.employe_id == employe_id, EvaluationDB.compagnie_id == current_user.compagnie_id)
    ).order_by(EvaluationDB.annee.desc())
    result = await db.execute(q)
    evals = result.scalars().all()
    return {"evaluations": [_eval_to_dict(ev) for ev in evals]}


# ─── RECRUTEMENT ─────────────────────────────────────────────────────────────

@router.post("/recrutement", summary="Créer une offre de recrutement")
async def creer_offre(
    data: RecrutementCreate,
    current_user: TokenData = Depends(require_permission("rh:write")),
    db: AsyncSession = Depends(get_db),
):
    offre = RecrutementDB(
        compagnie_id=current_user.compagnie_id,
        poste=data.poste,
        departement=data.departement,
        description=data.description,
        salaire_min=data.salaire_min,
        salaire_max=data.salaire_max,
        date_limite=data.date_limite,
        statut="ouvert",
        cree_par_id=current_user.user_id,
    )
    db.add(offre)
    await db.commit()
    await db.refresh(offre)
    return {"offre_id": offre.id, "message": "Offre de recrutement créée"}


@router.get("/recrutement", summary="Lister les offres de recrutement")
async def lister_offres(
    statut: Optional[str] = None,
    current_user: TokenData = Depends(require_permission("rh:read")),
    db: AsyncSession = Depends(get_db),
):
    q = select(RecrutementDB).where(RecrutementDB.compagnie_id == current_user.compagnie_id)
    if statut:
        q = q.where(RecrutementDB.statut == statut)
    q = q.order_by(RecrutementDB.cree_le.desc())
    result = await db.execute(q)
    return {"offres": [_offre_to_dict(o) for o in result.scalars().all()]}


# ─── RÉFÉRENTIEL ─────────────────────────────────────────────────────────────

@router.get("/referentiel/departements")
async def get_departements(current_user: TokenData = Depends(get_current_user)):
    return {"departements": DEPARTEMENTS_ASSURANCE, "postes_par_dept": POSTES_PAR_DEPARTEMENT}


@router.get("/referentiel/criteres-evaluation")
async def get_criteres(current_user: TokenData = Depends(get_current_user)):
    return {"criteres": CRITERES_EVALUATION}


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _get_employe_or_404(employe_id: int, compagnie_id: int, db: AsyncSession) -> EmployeDB:
    q = select(EmployeDB).where(
        and_(EmployeDB.id == employe_id, EmployeDB.compagnie_id == compagnie_id)
    )
    e = (await db.execute(q)).scalar_one_or_none()
    if not e:
        raise HTTPException(404, f"Employé {employe_id} introuvable")
    return e


def _employe_to_dict(e: EmployeDB) -> dict:
    return {
        "id": e.id, "matricule": e.matricule, "nom": e.nom, "prenom": e.prenom,
        "poste": e.poste, "departement": e.departement, "grade": e.grade,
        "date_embauche": str(e.date_embauche) if e.date_embauche else None,
        "telephone": e.telephone, "email": e.email,
        "salaire_base": e.salaire_base, "statut": e.statut,
        "responsable_id": e.responsable_id,
    }

def _conge_to_dict(c: CongeDB) -> dict:
    return {
        "id": c.id, "employe_id": c.employe_id, "type_conge": c.type_conge,
        "date_debut": str(c.date_debut), "date_fin": str(c.date_fin),
        "nb_jours": c.nb_jours, "statut": c.statut, "motif": c.motif,
        "approuve_par_nom": c.approuve_par_nom,
    }

def _eval_to_dict(ev: EvaluationDB) -> dict:
    return {
        "id": ev.id, "employe_id": ev.employe_id, "annee": ev.annee,
        "trimestre": ev.trimestre, "score": ev.score, "mention": ev.mention,
        "commentaire": ev.commentaire, "evaluateur_nom": ev.evaluateur_nom,
        "notes": ev.notes,
    }

def _offre_to_dict(o: RecrutementDB) -> dict:
    return {
        "id": o.id, "poste": o.poste, "departement": o.departement,
        "statut": o.statut, "date_limite": str(o.date_limite) if o.date_limite else None,
        "salaire_min": o.salaire_min, "salaire_max": o.salaire_max,
        "description": o.description, "cree_le": str(o.cree_le),
        "nb_candidatures": len(o.candidatures or []),
    }
