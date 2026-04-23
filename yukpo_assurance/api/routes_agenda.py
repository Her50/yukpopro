"""
Routes FastAPI — Agenda & Rappels Employés
- GET  /evenements              : liste des événements
- POST /evenements              : créer un événement
- PUT  /evenements/{id}         : modifier
- DELETE /evenements/{id}       : supprimer
- GET  /evenements/semaine      : vue semaine
- GET  /taches                  : liste des tâches
- POST /taches                  : créer une tâche
- PUT  /taches/{id}             : modifier
- PUT  /taches/{id}/statut      : changer le statut
- GET  /taches/urgentes         : tâches urgentes / en retard
- GET  /resume-journalier       : résumé de la journée
- POST /rappels/sinistres       : déclenche rappels sinistres CIMA
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db, EvenementAgendaDB, TacheDB, RappelDB
from core.auth import get_current_user, TokenData
from core.multitenancy import require_module
from modules.agenda.gestionnaire_agenda import (
    GestionnaireAgenda,
    GenerateurRappels,
)

router = APIRouter(prefix="/agenda", tags=["Agenda & Rappels"])
gestionnaire = GestionnaireAgenda()
gen_rappels = GenerateurRappels()


# ─────────────────────────────────────────────────────────────
# Schémas
# ─────────────────────────────────────────────────────────────

class EvenementSchema(BaseModel):
    titre: str
    description: Optional[str] = None
    type_evenement: str = "rendez_vous"
    date_debut: datetime
    date_fin: Optional[datetime] = None
    toute_la_journee: bool = False
    lieu: Optional[str] = None
    lien_visio: Optional[str] = None
    recurrence: Optional[str] = None
    couleur: str = "#003366"
    participants: List[int] = []
    rappels: List[int] = [30]      # minutes avant
    lien_sinistre: Optional[int] = None
    lien_contrat: Optional[int] = None
    lien_reunion: Optional[str] = None


class TacheSchema(BaseModel):
    titre: str
    description: Optional[str] = None
    assigne_a: int
    priorite: str = "normale"
    date_echeance: Optional[datetime] = None
    date_debut_prevue: Optional[datetime] = None
    rappel_j_moins: int = 1
    tags: List[str] = []
    lien_sinistre: Optional[int] = None
    lien_contrat: Optional[int] = None
    lien_police: Optional[str] = None


class ChangerStatutTacheSchema(BaseModel):
    statut: str
    avancement_pct: Optional[int] = None


class CommentaireTacheSchema(BaseModel):
    texte: str


class RappelsSinistresSchema(BaseModel):
    sinistres: List[Dict[str, Any]]   # [{"id": 1, "numero": "S-001", "date_ouverture": "...", "gestionnaire_id": 5}]
    canal: str = "push"


# ─────────────────────────────────────────────────────────────
# Événements
# ─────────────────────────────────────────────────────────────

@router.post(
    "/evenements",
    dependencies=[Depends(require_module("agenda"))],
)
async def creer_evenement(
    payload: EvenementSchema,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    evt = EvenementAgendaDB(
        compagnie_id=current_user.compagnie_id,
        employe_id=current_user.user_id,
        titre=payload.titre,
        description=payload.description,
        type_evenement=payload.type_evenement,
        date_debut=payload.date_debut,
        date_fin=payload.date_fin,
        toute_la_journee=payload.toute_la_journee,
        lieu=payload.lieu,
        lien_visio=payload.lien_visio,
        recurrence=payload.recurrence,
        couleur=payload.couleur,
        participants=payload.participants,
        rappels=payload.rappels,
        lien_sinistre=payload.lien_sinistre,
        lien_contrat=payload.lien_contrat,
        lien_reunion=payload.lien_reunion,
        statut="planifie",
        cree_par=current_user.username,
    )
    db.add(evt)
    await db.commit()
    await db.refresh(evt)
    return {"id": evt.id, "titre": evt.titre, "date_debut": evt.date_debut}


@router.get(
    "/evenements",
    dependencies=[Depends(require_module("agenda"))],
)
async def lister_evenements(
    employe_id: Optional[int] = None,
    date_debut: Optional[date] = None,
    date_fin: Optional[date] = None,
    type_evenement: Optional[str] = None,
    limit: int = Query(50, le=200),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(EvenementAgendaDB).where(
        EvenementAgendaDB.compagnie_id == current_user.compagnie_id
    )
    if employe_id:
        q = q.where(EvenementAgendaDB.employe_id == employe_id)
    if date_debut:
        dt_debut = datetime.combine(date_debut, datetime.min.time())
        q = q.where(EvenementAgendaDB.date_debut >= dt_debut)
    if date_fin:
        dt_fin = datetime.combine(date_fin, datetime.max.time())
        q = q.where(EvenementAgendaDB.date_debut <= dt_fin)
    if type_evenement:
        q = q.where(EvenementAgendaDB.type_evenement == type_evenement)
    q = q.where(EvenementAgendaDB.statut != "annule").order_by(EvenementAgendaDB.date_debut).limit(limit)
    r = await db.execute(q)
    evts = r.scalars().all()

    return [
        {
            "id": e.id, "titre": e.titre, "type_evenement": e.type_evenement,
            "date_debut": e.date_debut, "date_fin": e.date_fin,
            "toute_la_journee": e.toute_la_journee, "lieu": e.lieu,
            "lien_visio": e.lien_visio, "statut": e.statut,
            "participants": e.participants, "couleur": e.couleur,
            "lien_sinistre": e.lien_sinistre, "lien_contrat": e.lien_contrat,
        }
        for e in evts
    ]


@router.get(
    "/evenements/semaine",
    dependencies=[Depends(require_module("agenda"))],
)
async def vue_semaine(
    debut: Optional[date] = None,
    employe_id: Optional[int] = None,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Vue hebdomadaire : événements et tâches organisés par jour."""
    if not debut:
        aujourd_hui = date.today()
        debut = aujourd_hui - timedelta(days=aujourd_hui.weekday())

    fin = debut + timedelta(days=6)

    # Événements
    q_evt = select(EvenementAgendaDB).where(
        EvenementAgendaDB.compagnie_id == current_user.compagnie_id,
        EvenementAgendaDB.date_debut >= datetime.combine(debut, datetime.min.time()),
        EvenementAgendaDB.date_debut <= datetime.combine(fin, datetime.max.time()),
        EvenementAgendaDB.statut != "annule",
    )
    if employe_id:
        q_evt = q_evt.where(EvenementAgendaDB.employe_id == employe_id)
    r_evt = await db.execute(q_evt)
    evts_raw = [
        {"id": e.id, "titre": e.titre, "date_debut": e.date_debut.isoformat(),
         "type_evenement": e.type_evenement, "couleur": e.couleur, "lieu": e.lieu}
        for e in r_evt.scalars().all()
    ]

    # Tâches
    q_tache = select(TacheDB).where(
        TacheDB.compagnie_id == current_user.compagnie_id,
        TacheDB.date_echeance >= datetime.combine(debut, datetime.min.time()),
        TacheDB.date_echeance <= datetime.combine(fin, datetime.max.time()),
        TacheDB.statut.notin_(["terminee", "annulee"]),
    )
    if employe_id:
        q_tache = q_tache.where(TacheDB.assigne_a == employe_id)
    r_tache = await db.execute(q_tache)
    taches_raw = [
        {"id": t.id, "titre": t.titre, "date_echeance": t.date_echeance.isoformat() if t.date_echeance else None,
         "priorite": t.priorite, "statut": t.statut, "avancement_pct": t.avancement_pct}
        for t in r_tache.scalars().all()
    ]

    return gestionnaire.vue_semaine(evts_raw, taches_raw, debut)


@router.put(
    "/evenements/{event_id}",
    dependencies=[Depends(require_module("agenda"))],
)
async def modifier_evenement(
    event_id: int,
    payload: EvenementSchema,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(
        select(EvenementAgendaDB).where(
            EvenementAgendaDB.id == event_id,
            EvenementAgendaDB.compagnie_id == current_user.compagnie_id,
        )
    )
    evt = r.scalar_one_or_none()
    if not evt:
        raise HTTPException(404, "Événement introuvable")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(evt, field, value)
    await db.commit()
    return {"id": event_id, "message": "Événement mis à jour"}


@router.delete(
    "/evenements/{event_id}",
    dependencies=[Depends(require_module("agenda"))],
)
async def supprimer_evenement(
    event_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(
        select(EvenementAgendaDB).where(
            EvenementAgendaDB.id == event_id,
            EvenementAgendaDB.compagnie_id == current_user.compagnie_id,
        )
    )
    evt = r.scalar_one_or_none()
    if not evt:
        raise HTTPException(404, "Événement introuvable")
    evt.statut = "annule"
    await db.commit()
    return {"message": "Événement annulé"}


# ─────────────────────────────────────────────────────────────
# Tâches
# ─────────────────────────────────────────────────────────────

@router.post(
    "/taches",
    dependencies=[Depends(require_module("agenda"))],
)
async def creer_tache(
    payload: TacheSchema,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tache = TacheDB(
        compagnie_id=current_user.compagnie_id,
        titre=payload.titre,
        description=payload.description,
        assigne_a=payload.assigne_a,
        assigne_par=current_user.username,
        priorite=payload.priorite,
        statut="a_faire",
        date_echeance=payload.date_echeance,
        date_debut_prevue=payload.date_debut_prevue,
        rappel_j_moins=payload.rappel_j_moins,
        tags=payload.tags,
        lien_sinistre=payload.lien_sinistre,
        lien_contrat=payload.lien_contrat,
        lien_police=payload.lien_police,
    )
    db.add(tache)
    await db.commit()
    await db.refresh(tache)
    return {"id": tache.id, "titre": tache.titre, "statut": tache.statut}


@router.get(
    "/taches",
    dependencies=[Depends(require_module("agenda"))],
)
async def lister_taches(
    assigne_a: Optional[int] = None,
    statut: Optional[str] = None,
    priorite: Optional[str] = None,
    limit: int = Query(50, le=200),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(TacheDB).where(TacheDB.compagnie_id == current_user.compagnie_id)
    if assigne_a:
        q = q.where(TacheDB.assigne_a == assigne_a)
    if statut:
        q = q.where(TacheDB.statut == statut)
    if priorite:
        q = q.where(TacheDB.priorite == priorite)
    q = q.order_by(TacheDB.date_echeance.asc().nullsfirst(), TacheDB.priorite.desc()).limit(limit)
    r = await db.execute(q)
    taches = r.scalars().all()

    return [
        {
            "id": t.id, "titre": t.titre, "priorite": t.priorite,
            "statut": t.statut, "avancement_pct": t.avancement_pct,
            "assigne_a": t.assigne_a, "assigne_par": t.assigne_par,
            "date_echeance": t.date_echeance, "tags": t.tags,
            "lien_sinistre": t.lien_sinistre, "lien_police": t.lien_police,
            "cree_le": t.cree_le,
        }
        for t in taches
    ]


@router.get(
    "/taches/urgentes",
    dependencies=[Depends(require_module("agenda"))],
)
async def taches_urgentes(
    employe_id: Optional[int] = None,
    jours_horizon: int = 7,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(TacheDB).where(
        TacheDB.compagnie_id == current_user.compagnie_id,
        TacheDB.statut.notin_(["terminee", "annulee"]),
    )
    if employe_id:
        q = q.where(TacheDB.assigne_a == employe_id)
    r = await db.execute(q)
    taches_raw = [
        {
            "id": t.id, "titre": t.titre, "priorite": t.priorite,
            "statut": t.statut, "avancement_pct": t.avancement_pct,
            "date_echeance": t.date_echeance.isoformat() if t.date_echeance else None,
            "assigne_a": t.assigne_a, "lien_sinistre": t.lien_sinistre,
        }
        for t in r.scalars().all()
    ]
    return gestionnaire.taches_urgentes(taches_raw, jours_horizon)


@router.put(
    "/taches/{tache_id}",
    dependencies=[Depends(require_module("agenda"))],
)
async def modifier_tache(
    tache_id: int,
    payload: TacheSchema,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(
        select(TacheDB).where(
            TacheDB.id == tache_id,
            TacheDB.compagnie_id == current_user.compagnie_id,
        )
    )
    t = r.scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Tâche introuvable")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(t, field, value)
    await db.commit()
    return {"id": tache_id, "message": "Tâche mise à jour"}


@router.put(
    "/taches/{tache_id}/statut",
    dependencies=[Depends(require_module("agenda"))],
)
async def changer_statut_tache(
    tache_id: int,
    payload: ChangerStatutTacheSchema,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(
        select(TacheDB).where(
            TacheDB.id == tache_id,
            TacheDB.compagnie_id == current_user.compagnie_id,
        )
    )
    t = r.scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Tâche introuvable")

    t.statut = payload.statut
    if payload.avancement_pct is not None:
        t.avancement_pct = payload.avancement_pct
    if payload.statut == "terminee":
        t.date_completion = datetime.utcnow()
        t.avancement_pct = 100
    await db.commit()
    return {"id": tache_id, "statut": payload.statut}


@router.post(
    "/taches/{tache_id}/commentaire",
    dependencies=[Depends(require_module("agenda"))],
)
async def ajouter_commentaire(
    tache_id: int,
    payload: CommentaireTacheSchema,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(
        select(TacheDB).where(
            TacheDB.id == tache_id,
            TacheDB.compagnie_id == current_user.compagnie_id,
        )
    )
    t = r.scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Tâche introuvable")

    commentaires = list(t.commentaires or [])
    commentaires.append({
        "auteur": current_user.username,
        "texte": payload.texte,
        "date": datetime.utcnow().isoformat(),
    })
    t.commentaires = commentaires
    await db.commit()
    return {"message": "Commentaire ajouté", "nb_commentaires": len(commentaires)}


# ─────────────────────────────────────────────────────────────
# Résumé journalier
# ─────────────────────────────────────────────────────────────

@router.get(
    "/resume-journalier",
    dependencies=[Depends(require_module("agenda"))],
)
async def resume_journalier(
    employe_id: Optional[int] = None,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    eid = employe_id or current_user.user_id
    aujourd_hui = date.today()

    q_evt = select(EvenementAgendaDB).where(
        EvenementAgendaDB.compagnie_id == current_user.compagnie_id,
        EvenementAgendaDB.employe_id == eid,
        EvenementAgendaDB.date_debut >= datetime.combine(aujourd_hui, datetime.min.time()),
        EvenementAgendaDB.date_debut <= datetime.combine(aujourd_hui, datetime.max.time()),
        EvenementAgendaDB.statut != "annule",
    )
    r_evt = await db.execute(q_evt)
    evts = [{"titre": e.titre, "date_debut": e.date_debut.isoformat()} for e in r_evt.scalars().all()]

    q_tache = select(TacheDB).where(
        TacheDB.compagnie_id == current_user.compagnie_id,
        TacheDB.assigne_a == eid,
        TacheDB.statut.notin_(["terminee", "annulee"]),
    )
    r_tache = await db.execute(q_tache)
    taches = [
        {"titre": t.titre, "priorite": t.priorite, "date_echeance": t.date_echeance.isoformat() if t.date_echeance else None}
        for t in r_tache.scalars().all()
    ]

    resume = gestionnaire.resume_journalier(eid, evts, taches)
    return {
        "employe_id": eid,
        "date": aujourd_hui.isoformat(),
        "resume_texte": resume,
        "evenements_du_jour": evts,
        "taches_actives": taches,
    }


# ─────────────────────────────────────────────────────────────
# Rappels automatiques sinistres CIMA
# ─────────────────────────────────────────────────────────────

@router.post(
    "/rappels/sinistres",
    dependencies=[Depends(require_module("agenda"))],
)
async def rappels_sinistres_cima(
    payload: RappelsSinistresSchema,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Génère et enregistre des rappels pour les sinistres proches du délai CIMA (45 jours).
    À appeler périodiquement (cron quotidien).
    """
    rappels = gen_rappels.rappels_sinistres_en_retard(payload.sinistres)

    enregistres = 0
    for r in rappels:
        rappel_db = RappelDB(
            compagnie_id=current_user.compagnie_id,
            employe_id=r.employe_id,
            type_source=r.type_source,
            source_id=r.source_id,
            canal=payload.canal,
            message=r.message,
            statut="envoye",
        )
        db.add(rappel_db)
        enregistres += 1

    await db.commit()
    return {
        "rappels_generes": len(rappels),
        "rappels_enregistres": enregistres,
        "details": [{"employe_id": r.employe_id, "message": r.message} for r in rappels],
    }
