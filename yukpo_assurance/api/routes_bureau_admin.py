"""
Yukpo Secrétariat — Routes Admin.

Réservé aux rôles admin / super_admin / yukpo_owner.

  GET    /api/v1/bureau/admin/utilisateurs              — Liste paginée + crédits + recharges
  GET    /api/v1/bureau/admin/utilisateurs/{user_id}    — Détails complets
  POST   /api/v1/bureau/admin/utilisateurs/{id}/credits-bonus  — Ajouter crédits bonus
  POST   /api/v1/bureau/admin/utilisateurs/{id}/bloquer
  POST   /api/v1/bureau/admin/utilisateurs/{id}/debloquer
  GET    /api/v1/bureau/admin/stats                     — Stats globales secrétariat
  GET    /api/v1/bureau/admin/stats/recharges           — Recharges par jour / total
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import TokenData, get_current_user
from core.database import (
    async_session_maker, UtilisateurDB, CreditBureauDB, ConsommationBureauDB,
)

logger = logging.getLogger("yukpo_assurance.api.bureau_admin")

router = APIRouter()
ADMIN_ROLES = ("admin", "super_admin", "yukpo_owner")


async def get_db() -> AsyncSession:
    async with async_session_maker() as session:
        yield session


def _exiger_admin(user: TokenData):
    if user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Réservé aux administrateurs")


# ── Schémas ───────────────────────────────────────────────────────────────────

class CreditsBonusRequest(BaseModel):
    credits: int = Field(..., gt=0, le=10_000_000, description="Nombre de crédits à ajouter")
    raison: Optional[str] = Field(None, description="Note interne (audit)")


class PromotionRequest(BaseModel):
    montant: int = Field(..., gt=0, le=1_000_000, description="Crédits à distribuer par utilisateur")
    cible: str = Field(..., description="tous | ids | consommation | role")
    user_ids: Optional[list[int]] = None
    role: Optional[str] = None
    seuil_credits_min: Optional[float] = None  # consommation min sur la période
    seuil_credits_max: Optional[float] = None
    seuil_appels_min:  Optional[int]   = None
    periode_jours: int = 30
    motif: Optional[str] = None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/utilisateurs", summary="Liste utilisateurs Secrétariat avec leurs crédits")
async def lister_utilisateurs(
    recherche: Optional[str] = Query(None, description="Recherche par email/nom/username"),
    page: int = Query(1, ge=1),
    par_page: int = Query(50, ge=1, le=200),
    actifs_seulement: bool = Query(False),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _exiger_admin(current_user)

    q = select(UtilisateurDB)
    if recherche:
        like = f"%{recherche.lower()}%"
        q = q.where(or_(
            func.lower(UtilisateurDB.email).like(like),
            func.lower(UtilisateurDB.nom).like(like),
            func.lower(UtilisateurDB.username).like(like),
        ))
    if actifs_seulement:
        q = q.where(UtilisateurDB.actif == True)  # noqa: E712

    total_q = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_q.scalar() or 0

    q = q.order_by(desc(UtilisateurDB.cree_le)).offset((page - 1) * par_page).limit(par_page)
    users = (await db.execute(q)).scalars().all()

    user_ids = [u.id for u in users]
    credits_map: dict[int, CreditBureauDB] = {}
    if user_ids:
        rows = (await db.execute(
            select(CreditBureauDB).where(CreditBureauDB.user_id.in_(user_ids))
        )).scalars().all()
        for c in rows:
            credits_map[c.user_id] = c

    items = []
    for u in users:
        c = credits_map.get(u.id)
        restants = (c.credits_alloues - c.credits_utilises) if c else 0
        items.append({
            "id":                u.id,
            "username":          u.username,
            "email":             u.email,
            "nom":                u.nom,
            "prenoms":           u.prenoms,
            "role":              u.role,
            "actif":             u.actif,
            "bloque_jusqu_au":   u.bloque_jusqu_au.isoformat() if u.bloque_jusqu_au else None,
            "cree_le":           u.cree_le.isoformat() if u.cree_le else None,
            "derniere_connexion": u.derniere_connexion.isoformat() if u.derniere_connexion else None,
            "nb_connexions":     u.nb_connexions or 0,
            "credits": {
                "plan":             c.plan if c else None,
                "credits_alloues":  c.credits_alloues if c else 0,
                "credits_utilises": round(c.credits_utilises, 1) if c else 0,
                "credits_restants": round(restants, 1) if c else 0,
                "fcfa_equivalent":  round((restants * 0.6), 0) if c else 0,
                "modifie_le":       c.mise_a_jour.isoformat() if c and c.mise_a_jour else None,
            } if c else None,
        })

    return {
        "utilisateurs": items,
        "total":        total,
        "page":         page,
        "par_page":     par_page,
        "total_pages":  max(1, (total + par_page - 1) // par_page),
    }


@router.get("/utilisateurs/{user_id}", summary="Détails complets d'un utilisateur")
async def details_utilisateur(
    user_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _exiger_admin(current_user)
    u = (await db.execute(select(UtilisateurDB).where(UtilisateurDB.id == user_id))).scalar_one_or_none()
    if not u:
        raise HTTPException(404, "Utilisateur introuvable")

    c = (await db.execute(select(CreditBureauDB).where(CreditBureauDB.user_id == user_id))).scalar_one_or_none()

    # Top consommations 30 jours
    since = datetime.utcnow() - timedelta(days=30)
    agg_module = (await db.execute(
        select(
            ConsommationBureauDB.module,
            func.sum(ConsommationBureauDB.credits_debites).label("credits"),
            func.count(ConsommationBureauDB.id).label("appels"),
        )
        .where(and_(
            ConsommationBureauDB.user_id == user_id,
            ConsommationBureauDB.cree_le >= since,
        ))
        .group_by(ConsommationBureauDB.module)
        .order_by(func.sum(ConsommationBureauDB.credits_debites).desc())
    )).all()

    # Dernières opérations
    derniere_consos = (await db.execute(
        select(ConsommationBureauDB)
        .where(ConsommationBureauDB.user_id == user_id)
        .order_by(ConsommationBureauDB.cree_le.desc())
        .limit(50)
    )).scalars().all()

    restants = (c.credits_alloues - c.credits_utilises) if c else 0

    return {
        "utilisateur": {
            "id":                u.id,
            "username":          u.username,
            "email":             u.email,
            "nom":               u.nom,
            "prenoms":           u.prenoms,
            "telephone":         u.telephone,
            "role":              u.role,
            "actif":             u.actif,
            "bloque_jusqu_au":   u.bloque_jusqu_au.isoformat() if u.bloque_jusqu_au else None,
            "cree_le":           u.cree_le.isoformat() if u.cree_le else None,
            "derniere_connexion": u.derniere_connexion.isoformat() if u.derniere_connexion else None,
            "nb_connexions":     u.nb_connexions or 0,
        },
        "credits": {
            "plan":             c.plan if c else None,
            "credits_alloues":  c.credits_alloues if c else 0,
            "credits_utilises": round(c.credits_utilises, 1) if c else 0,
            "credits_restants": round(restants, 1) if c else 0,
            "periode_debut":    c.periode_debut.isoformat() if c and c.periode_debut else None,
            "periode_fin":      c.periode_fin.isoformat() if c and c.periode_fin else None,
        } if c else None,
        "top_modules_30j": [
            {"module": m or "inconnu", "credits": round(cr or 0, 1), "appels": int(a or 0)}
            for (m, cr, a) in agg_module
        ],
        "dernieres_consommations": [
            {
                "id":              co.id,
                "date":            co.cree_le.isoformat() if co.cree_le else None,
                "module":          co.module,
                "modele":          co.modele,
                "tokens_input":    co.tokens_input or 0,
                "tokens_output":   co.tokens_output or 0,
                "credits_debites": round(co.credits_debites or 0, 1),
                "cout_fcfa":       round(co.cout_fcfa or 0, 2),
            } for co in derniere_consos
        ],
    }


@router.post("/utilisateurs/{user_id}/credits-bonus", summary="Ajouter crédits bonus")
async def ajouter_credits_bonus(
    user_id: int, req: CreditsBonusRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _exiger_admin(current_user)
    u = (await db.execute(select(UtilisateurDB).where(UtilisateurDB.id == user_id))).scalar_one_or_none()
    if not u:
        raise HTTPException(404, "Utilisateur introuvable")

    from modules.bureau.service_credits_bureau import get_ou_creer_credits_bureau
    credit = await get_ou_creer_credits_bureau(user_id, db)
    credit.credits_alloues += req.credits
    credit.mise_a_jour = datetime.utcnow()
    await db.commit()

    logger.info(
        f"[BureauAdmin] user_id={user_id} +{req.credits} crédits bonus "
        f"par admin={current_user.user_id} raison={req.raison or '-'}"
    )

    return {
        "succes":         True,
        "credits_ajoutes": req.credits,
        "nouveau_solde":  credit.credits_alloues - credit.credits_utilises,
        "message":        f"{req.credits:,} crédits ajoutés à {u.email}",
    }


@router.post("/utilisateurs/{user_id}/bloquer", summary="Bloquer un utilisateur")
async def bloquer_utilisateur(
    user_id: int, jours: int = Query(7, ge=1, le=365),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _exiger_admin(current_user)
    u = (await db.execute(select(UtilisateurDB).where(UtilisateurDB.id == user_id))).scalar_one_or_none()
    if not u:
        raise HTTPException(404, "Utilisateur introuvable")
    u.bloque_jusqu_au = datetime.utcnow() + timedelta(days=jours)
    u.actif = False
    await db.commit()
    logger.warning(f"[BureauAdmin] user_id={user_id} BLOQUÉ {jours}j par admin={current_user.user_id}")
    return {"succes": True, "bloque_jusqu_au": u.bloque_jusqu_au.isoformat()}


@router.post("/utilisateurs/{user_id}/debloquer", summary="Débloquer un utilisateur")
async def debloquer_utilisateur(
    user_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _exiger_admin(current_user)
    u = (await db.execute(select(UtilisateurDB).where(UtilisateurDB.id == user_id))).scalar_one_or_none()
    if not u:
        raise HTTPException(404, "Utilisateur introuvable")
    u.bloque_jusqu_au = None
    u.actif = True
    u.tentatives_echec = 0
    await db.commit()
    logger.info(f"[BureauAdmin] user_id={user_id} débloqué par admin={current_user.user_id}")
    return {"succes": True}


@router.post("/promotion", summary="Distribuer des crédits bonus en masse (campagne)")
async def lancer_promotion(
    req: PromotionRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Distribue `montant` crédits à tous les utilisateurs d'une cible.
    Cibles possibles :
      - tous          : tous les utilisateurs actifs
      - ids           : liste explicite (req.user_ids)
      - role          : tous les users avec un rôle donné (req.role)
      - consommation  : users dépassant des seuils sur N derniers jours
                        (seuil_credits_min/max + seuil_appels_min)
    """
    _exiger_admin(current_user)
    if req.cible not in ("tous", "ids", "consommation", "role"):
        raise HTTPException(400, "Cible invalide (tous | ids | consommation | role)")

    # Construire la liste user_ids cible
    target_ids: list[int] = []

    if req.cible == "ids":
        target_ids = req.user_ids or []
        if not target_ids:
            raise HTTPException(400, "user_ids vide")

    elif req.cible == "role":
        if not req.role:
            raise HTTPException(400, "role manquant")
        rows = (await db.execute(
            select(UtilisateurDB.id).where(UtilisateurDB.role == req.role)
        )).scalars().all()
        target_ids = list(rows)

    elif req.cible == "tous":
        rows = (await db.execute(
            select(UtilisateurDB.id).where(UtilisateurDB.actif == True)  # noqa: E712
        )).scalars().all()
        target_ids = list(rows)

    elif req.cible == "consommation":
        if req.seuil_credits_min is None and req.seuil_credits_max is None and req.seuil_appels_min is None:
            raise HTTPException(400, "Au moins un seuil requis (credits_min/max ou appels_min)")
        since = datetime.utcnow() - timedelta(days=req.periode_jours)
        agg = (await db.execute(
            select(
                ConsommationBureauDB.user_id,
                func.sum(ConsommationBureauDB.credits_debites).label("credits"),
                func.count(ConsommationBureauDB.id).label("appels"),
            )
            .where(ConsommationBureauDB.cree_le >= since)
            .group_by(ConsommationBureauDB.user_id)
        )).all()
        for (uid, credits, appels) in agg:
            credits = float(credits or 0)
            appels = int(appels or 0)
            if req.seuil_credits_min is not None and credits < req.seuil_credits_min: continue
            if req.seuil_credits_max is not None and credits > req.seuil_credits_max: continue
            if req.seuil_appels_min  is not None and appels  < req.seuil_appels_min:  continue
            target_ids.append(uid)

    if not target_ids:
        return {
            "succes": True, "beneficiaires": 0, "montant_total": 0,
            "message": "Aucun utilisateur ne correspond à la cible",
        }

    # Distribuer les crédits via get_ou_creer_credits_bureau
    from modules.bureau.service_credits_bureau import get_ou_creer_credits_bureau

    nb_ok = 0
    for uid in target_ids:
        try:
            credit = await get_ou_creer_credits_bureau(uid, db)
            credit.credits_alloues += req.montant
            credit.mise_a_jour = datetime.utcnow()
            nb_ok += 1
        except Exception as e:
            logger.warning(f"[BureauAdmin/Promotion] échec uid={uid}: {e}")
    await db.commit()

    logger.info(
        f"[BureauAdmin/Promotion] cible={req.cible} montant={req.montant} "
        f"beneficiaires={nb_ok}/{len(target_ids)} motif={req.motif or '-'} "
        f"par admin={current_user.user_id}"
    )

    return {
        "succes":         True,
        "beneficiaires":  nb_ok,
        "cible_taille":   len(target_ids),
        "montant_total":  nb_ok * req.montant,
        "message":        f"{req.montant:,} crédits distribués à {nb_ok} utilisateur(s)",
    }


@router.get("/stats", summary="Statistiques globales Secrétariat")
async def stats_globales(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _exiger_admin(current_user)
    now = datetime.utcnow()
    j7  = now - timedelta(days=7)
    j30 = now - timedelta(days=30)

    nb_users = (await db.execute(select(func.count()).select_from(UtilisateurDB))).scalar() or 0
    nb_users_actifs = (await db.execute(
        select(func.count()).select_from(UtilisateurDB).where(UtilisateurDB.actif == True)  # noqa: E712
    )).scalar() or 0
    nb_users_30j = (await db.execute(
        select(func.count()).select_from(UtilisateurDB).where(UtilisateurDB.cree_le >= j30)
    )).scalar() or 0

    # Crédits agrégés
    sum_alloues = (await db.execute(select(func.sum(CreditBureauDB.credits_alloues)))).scalar() or 0
    sum_utilises = (await db.execute(select(func.sum(CreditBureauDB.credits_utilises)))).scalar() or 0

    # Consommation 7j et 30j
    consom_7j = (await db.execute(
        select(func.sum(ConsommationBureauDB.credits_debites), func.count())
        .where(ConsommationBureauDB.cree_le >= j7)
    )).first()
    consom_30j = (await db.execute(
        select(func.sum(ConsommationBureauDB.credits_debites), func.count())
        .where(ConsommationBureauDB.cree_le >= j30)
    )).first()

    # Top modules 30j
    agg_module = (await db.execute(
        select(
            ConsommationBureauDB.module,
            func.sum(ConsommationBureauDB.credits_debites).label("credits"),
            func.count(ConsommationBureauDB.id).label("appels"),
        )
        .where(ConsommationBureauDB.cree_le >= j30)
        .group_by(ConsommationBureauDB.module)
        .order_by(func.sum(ConsommationBureauDB.credits_debites).desc())
        .limit(8)
    )).all()

    # Top utilisateurs (consommation 30j)
    top_users = (await db.execute(
        select(
            ConsommationBureauDB.user_id,
            func.sum(ConsommationBureauDB.credits_debites).label("credits"),
        )
        .where(ConsommationBureauDB.cree_le >= j30)
        .group_by(ConsommationBureauDB.user_id)
        .order_by(func.sum(ConsommationBureauDB.credits_debites).desc())
        .limit(10)
    )).all()

    # Hydrate top_users avec emails
    if top_users:
        ids = [t[0] for t in top_users]
        users_rows = (await db.execute(
            select(UtilisateurDB).where(UtilisateurDB.id.in_(ids))
        )).scalars().all()
        users_map = {u.id: u for u in users_rows}
    else:
        users_map = {}

    return {
        "utilisateurs": {
            "total":              nb_users,
            "actifs":             nb_users_actifs,
            "nouveaux_30j":       nb_users_30j,
        },
        "credits": {
            "total_alloues":      int(sum_alloues),
            "total_utilises":     round(float(sum_utilises), 1),
            "total_restants":     round(float(sum_alloues - sum_utilises), 1),
            "fcfa_equivalent":    round(float(sum_alloues - sum_utilises) * 0.6, 0),
        },
        "consommation_7j":  {
            "credits": round(float(consom_7j[0] or 0), 1),
            "appels":  int(consom_7j[1] or 0),
        },
        "consommation_30j": {
            "credits": round(float(consom_30j[0] or 0), 1),
            "appels":  int(consom_30j[1] or 0),
        },
        "top_modules_30j": [
            {"module": m or "inconnu", "credits": round(c or 0, 1), "appels": int(a or 0)}
            for (m, c, a) in agg_module
        ],
        "top_utilisateurs_30j": [
            {
                "user_id": uid,
                "email":   users_map.get(uid).email if users_map.get(uid) else f"#{uid}",
                "nom":     users_map.get(uid).nom if users_map.get(uid) else None,
                "credits": round(float(cr or 0), 1),
            }
            for (uid, cr) in top_users
        ],
    }
