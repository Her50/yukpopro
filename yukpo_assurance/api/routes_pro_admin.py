"""
Routes Admin YukpoPro — Tableau de bord administrateur.

Endpoints :
  GET   /api/v1/pro/admin/utilisateurs              — Liste paginée (enrichie : email, plan, conso, actif…)
  GET   /api/v1/pro/admin/utilisateurs/{user_id}    — Détails complets d'un utilisateur
  PUT   /api/v1/pro/admin/utilisateurs/{user_id}/metier
  PUT   /api/v1/pro/admin/utilisateurs/{user_id}/abonnement   — Forcer plan + crédits
  POST  /api/v1/pro/admin/utilisateurs/{user_id}/bloquer
  POST  /api/v1/pro/admin/utilisateurs/{user_id}/debloquer
  POST  /api/v1/pro/admin/utilisateurs/{user_id}/credits-bonus
  POST  /api/v1/pro/admin/promotions                — Bonus crédits ciblé (filtres)
  GET   /api/v1/pro/admin/stats                     — Stats globales
  GET   /api/v1/pro/admin/stats/avancees            — Stats avancées (plans, MRR, signups)
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import TokenData, get_current_user
from core.database import (
    async_session_maker, UtilisateurDB, CreditIAUserDB, ConsommationTokenDB,
    PaymentTransactionV2DB,
)
from core.pays_devise import pays_du_continent, get_continent, CONTINENT_LABELS
from modules.pro.profil_pro import ProfilProfessionnelDB


def _resolve_pays_filter(pays: Optional[str], continent: Optional[str]) -> Optional[List[str]]:
    """Renvoie la liste des codes pays à filtrer, ou None si pas de filtre.

    - pays="CM" → ["CM"]
    - continent="AF" → tous les pays africains
    - rien → None
    """
    if pays:
        return [pays.strip().upper()]
    if continent:
        codes = pays_du_continent(continent)
        return codes or [continent.strip().upper()]  # fallback au cas où
    return None


async def _user_ids_du_pays(db: AsyncSession, pays_codes: List[str]) -> List[int]:
    """Liste des user_id ayant un profil_pro dont pays ∈ pays_codes."""
    res = await db.execute(
        select(ProfilProfessionnelDB.user_id).where(ProfilProfessionnelDB.pays.in_(pays_codes))
    )
    return [int(r[0]) for r in res.all()]

logger = logging.getLogger("yukpo_assurance.api.pro_admin")

router = APIRouter()


async def get_db():
    async with async_session_maker() as session:
        yield session


def _require_admin(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """Vérifie que l'utilisateur a le rôle admin ou super_admin."""
    if current_user.role not in ("admin", "super_admin", "yukpo_owner"):
        raise HTTPException(
            status_code=403,
            detail="Accès réservé aux administrateurs YukpoPro",
        )
    return current_user


# ── Modèles ───────────────────────────────────────────────────────────────────

class ChangerMetierRequest(BaseModel):
    metier: str
    niveau: Optional[str] = None
    pays: Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════════
# Routes
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/utilisateurs", summary="Liste paginée et enrichie des utilisateurs")
async def lister_utilisateurs(
    page: int = 1,
    par_page: int = 50,
    search: Optional[str] = None,
    plan: Optional[str] = None,
    statut: Optional[str] = None,  # actif | bloque
    admin: TokenData = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Retourne la liste enrichie : email, role, plan, crédits, conso, dernière connexion,
    statut actif/bloqué. Supporte filtres serveur (search, plan, statut).
    """
    offset = (page - 1) * par_page
    q = select(UtilisateurDB)
    if search:
        like = f"%{search.lower()}%"
        q = q.where(or_(
            func.lower(UtilisateurDB.username).like(like),
            func.lower(UtilisateurDB.email).like(like),
            func.lower(UtilisateurDB.nom).like(like),
        ))
    if statut == "actif":
        q = q.where(UtilisateurDB.actif == True)
    elif statut == "bloque":
        q = q.where(or_(
            UtilisateurDB.actif == False,
            UtilisateurDB.bloque_jusqu_au.isnot(None),
        ))

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = int(total_result.scalar() or 0)

    q = q.order_by(UtilisateurDB.id.desc()).offset(offset).limit(par_page)
    result = await db.execute(q)
    users = result.scalars().all()

    # Enrichissement crédits + conso (batch)
    user_ids = [u.id for u in users]
    credits_map: dict[int, CreditIAUserDB] = {}
    conso_map: dict[int, dict] = {}
    if user_ids:
        cred_res = await db.execute(
            select(CreditIAUserDB).where(CreditIAUserDB.user_id.in_(user_ids))
        )
        for c in cred_res.scalars().all():
            credits_map[c.user_id] = c
        conso_res = await db.execute(
            select(
                ConsommationTokenDB.user_id,
                func.count().label("nb_appels"),
                func.coalesce(func.sum(ConsommationTokenDB.credits_debites), 0).label("credits_total"),
            )
            .where(ConsommationTokenDB.user_id.in_(user_ids))
            .group_by(ConsommationTokenDB.user_id)
        )
        for row in conso_res.all():
            conso_map[row.user_id] = {"nb_appels": int(row.nb_appels), "credits_total": float(row.credits_total or 0)}

    items = []
    now = datetime.utcnow()
    for u in users:
        cred = credits_map.get(u.id)
        conso = conso_map.get(u.id, {"nb_appels": 0, "credits_total": 0})
        bloque = (not u.actif) or (u.bloque_jusqu_au is not None and u.bloque_jusqu_au > now)
        item = {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "nom": u.nom,
            "prenoms": u.prenoms,
            "role": u.role,
            "telephone": u.telephone,
            "actif": u.actif,
            "bloque": bloque,
            "bloque_jusqu_au": u.bloque_jusqu_au.isoformat() if u.bloque_jusqu_au else None,
            "derniere_connexion": u.derniere_connexion.isoformat() if u.derniere_connexion else None,
            "nb_connexions": u.nb_connexions or 0,
            "cree_le": u.cree_le.isoformat() if u.cree_le else None,
            "plan": cred.plan if cred else "gratuit",
            "credits_alloues": cred.credits_alloues if cred else 0,
            "credits_utilises": cred.credits_utilises if cred else 0,
            "credits_restants": (cred.credits_alloues - cred.credits_utilises) if cred else 0,
            "periode_fin": cred.periode_fin.isoformat() if cred and cred.periode_fin else None,
            "conso_total": conso["credits_total"],
            "nb_appels_total": conso["nb_appels"],
        }
        if plan and item["plan"] != plan:
            continue
        items.append(item)

    return {
        "utilisateurs": items,
        "page": page,
        "par_page": par_page,
        "total": total,
    }


@router.get("/utilisateurs/{user_id}", summary="Détails complets d'un utilisateur")
async def details_utilisateur(
    user_id: int,
    admin: TokenData = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    u = (await db.execute(select(UtilisateurDB).where(UtilisateurDB.id == user_id))).scalar_one_or_none()
    if not u:
        raise HTTPException(404, "Utilisateur introuvable")
    cred = (await db.execute(select(CreditIAUserDB).where(CreditIAUserDB.user_id == user_id))).scalar_one_or_none()

    # Conso 30j par module
    since = datetime.utcnow() - timedelta(days=30)
    conso_res = await db.execute(
        select(
            ConsommationTokenDB.module,
            func.count().label("appels"),
            func.coalesce(func.sum(ConsommationTokenDB.credits_debites), 0).label("credits"),
        )
        .where(and_(
            ConsommationTokenDB.user_id == user_id,
            ConsommationTokenDB.cree_le >= since,
        ))
        .group_by(ConsommationTokenDB.module)
        .order_by(func.sum(ConsommationTokenDB.credits_debites).desc())
    )
    conso_par_module = [
        {"module": r.module or "inconnu", "appels": int(r.appels), "credits": float(r.credits or 0)}
        for r in conso_res.all()
    ]

    # Transactions paiement
    tx_res = await db.execute(
        select(PaymentTransactionV2DB)
        .where(PaymentTransactionV2DB.user_id == user_id)
        .order_by(PaymentTransactionV2DB.created_at.desc())
        .limit(20)
    )
    transactions = [{
        "reference": t.reference, "type": t.type, "plan": t.plan_ou_pack,
        "amount": float(t.amount), "currency": t.currency, "status": t.status,
        "provider": t.provider, "created_at": t.created_at.isoformat() if t.created_at else None,
    } for t in tx_res.scalars().all()]

    now = datetime.utcnow()
    bloque = (not u.actif) or (u.bloque_jusqu_au is not None and u.bloque_jusqu_au > now)
    return {
        "utilisateur": {
            "id": u.id, "username": u.username, "email": u.email,
            "nom": u.nom, "prenoms": u.prenoms, "role": u.role,
            "telephone": u.telephone, "actif": u.actif, "bloque": bloque,
            "bloque_jusqu_au": u.bloque_jusqu_au.isoformat() if u.bloque_jusqu_au else None,
            "derniere_connexion": u.derniere_connexion.isoformat() if u.derniere_connexion else None,
            "nb_connexions": u.nb_connexions or 0,
            "cree_le": u.cree_le.isoformat() if u.cree_le else None,
        },
        "credits": {
            "plan": cred.plan if cred else "gratuit",
            "credits_alloues": cred.credits_alloues if cred else 0,
            "credits_utilises": cred.credits_utilises if cred else 0,
            "credits_restants": (cred.credits_alloues - cred.credits_utilises) if cred else 0,
            "periode_debut": cred.periode_debut.isoformat() if cred and cred.periode_debut else None,
            "periode_fin": cred.periode_fin.isoformat() if cred and cred.periode_fin else None,
        },
        "conso_30j": conso_par_module,
        "transactions": transactions,
    }


# ── Mutations admin ──────────────────────────────────────────────────────────

class AbonnementRequest(BaseModel):
    plan: str = Field(..., description="gratuit | starter | pro | business")
    credits_bonus: int = Field(0, ge=0, description="Crédits supplémentaires à ajouter")
    duree_jours: int = Field(30, ge=1, le=365)


@router.put("/utilisateurs/{user_id}/abonnement", summary="Forcer le plan d'un utilisateur")
async def forcer_abonnement(
    user_id: int,
    req: AbonnementRequest,
    admin: TokenData = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    from modules.pro.service_credits import get_ou_creer_credits, CREDITS_PAR_PLAN
    if req.plan not in CREDITS_PAR_PLAN:
        raise HTTPException(400, f"Plan invalide. Choix : {list(CREDITS_PAR_PLAN.keys())}")
    cred = await get_ou_creer_credits(user_id, db)
    cred.plan = req.plan
    cred.credits_alloues = CREDITS_PAR_PLAN[req.plan] + req.credits_bonus
    cred.credits_utilises = 0
    cred.periode_debut = datetime.utcnow()
    cred.periode_fin = datetime.utcnow() + timedelta(days=req.duree_jours)
    cred.mise_a_jour = datetime.utcnow()
    await db.commit()
    logger.info(f"[Admin {admin.user_id}] Forcé abonnement user={user_id} plan={req.plan} +{req.credits_bonus} crédits")
    return {"succes": True, "user_id": user_id, "plan": cred.plan, "credits_alloues": cred.credits_alloues}


class BloquerRequest(BaseModel):
    motif: Optional[str] = None
    duree_heures: Optional[int] = Field(None, description="Si null = blocage permanent (actif=False)")


@router.post("/utilisateurs/{user_id}/bloquer", summary="Bloquer un utilisateur")
async def bloquer_utilisateur(
    user_id: int,
    req: BloquerRequest,
    admin: TokenData = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    u = (await db.execute(select(UtilisateurDB).where(UtilisateurDB.id == user_id))).scalar_one_or_none()
    if not u:
        raise HTTPException(404, "Utilisateur introuvable")
    if u.id == admin.user_id:
        raise HTTPException(400, "Impossible de se bloquer soi-même")
    if req.duree_heures:
        u.bloque_jusqu_au = datetime.utcnow() + timedelta(hours=req.duree_heures)
    else:
        u.actif = False
    await db.commit()
    logger.warning(f"[Admin {admin.user_id}] Bloqué user={user_id} motif={req.motif} duree={req.duree_heures}h")
    return {"succes": True, "user_id": user_id, "actif": u.actif, "bloque_jusqu_au": u.bloque_jusqu_au.isoformat() if u.bloque_jusqu_au else None}


@router.post("/utilisateurs/{user_id}/debloquer", summary="Débloquer un utilisateur")
async def debloquer_utilisateur(
    user_id: int,
    admin: TokenData = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    u = (await db.execute(select(UtilisateurDB).where(UtilisateurDB.id == user_id))).scalar_one_or_none()
    if not u:
        raise HTTPException(404, "Utilisateur introuvable")
    u.actif = True
    u.bloque_jusqu_au = None
    u.tentatives_echec = 0
    await db.commit()
    logger.info(f"[Admin {admin.user_id}] Débloqué user={user_id}")
    return {"succes": True, "user_id": user_id, "actif": True}


class CreditsBonusRequest(BaseModel):
    montant: int = Field(..., gt=0)
    motif: Optional[str] = None


@router.post("/utilisateurs/{user_id}/credits-bonus", summary="Ajouter des crédits bonus")
async def ajouter_credits_bonus(
    user_id: int,
    req: CreditsBonusRequest,
    admin: TokenData = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    from modules.pro.service_credits import get_ou_creer_credits
    cred = await get_ou_creer_credits(user_id, db)
    cred.credits_alloues += req.montant
    cred.mise_a_jour = datetime.utcnow()
    await db.commit()
    logger.info(f"[Admin {admin.user_id}] Bonus +{req.montant} crédits user={user_id} motif={req.motif}")
    return {"succes": True, "user_id": user_id, "credits_alloues": cred.credits_alloues}


class PromotionRequest(BaseModel):
    montant: int = Field(..., gt=0)
    cible: str = Field("tous", description="tous | plan | ids | consommation")
    plan: Optional[str] = None
    user_ids: Optional[List[int]] = None
    motif: Optional[str] = None
    # Filtres "consommation" — agrégation sur ConsommationTokenDB
    seuil_credits_min: Optional[float] = Field(
        None, description="Cumul crédits débités ≥ seuil (sur la période)"
    )
    seuil_credits_max: Optional[float] = Field(
        None, description="Cumul crédits débités ≤ seuil (sur la période)"
    )
    seuil_appels_min: Optional[int] = Field(
        None, description="Nombre d'appels (consommations) ≥ seuil (sur la période)"
    )
    periode_jours: Optional[int] = Field(
        30, ge=1, le=365, description="Fenêtre d'analyse de la consommation, en jours"
    )
    # Filtre géographique combinable avec n'importe quelle cible
    pays: Optional[str] = None
    continent: Optional[str] = None


@router.post("/promotions", summary="Bonus crédits global ou ciblé")
async def lancer_promotion(
    req: PromotionRequest,
    admin: TokenData = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Distribue `montant` crédits bonus :
      - cible=tous          → tous les utilisateurs ayant un solde
      - cible=plan          → tous ceux d'un plan donné (req.plan)
      - cible=ids           → liste explicite (req.user_ids)
      - cible=consommation  → utilisateurs filtrés sur leur conso agrégée
                              (seuil_credits_min/max, seuil_appels_min)
                              sur les `periode_jours` derniers jours

    Le filtre `pays` ou `continent` peut être combiné avec n'importe quelle cible.
    """
    q = select(CreditIAUserDB)

    if req.cible == "plan":
        if not req.plan:
            raise HTTPException(400, "plan requis pour cible=plan")
        q = q.where(CreditIAUserDB.plan == req.plan)
    elif req.cible == "ids":
        if not req.user_ids:
            raise HTTPException(400, "user_ids requis pour cible=ids")
        q = q.where(CreditIAUserDB.user_id.in_(req.user_ids))
    elif req.cible == "consommation":
        if (
            req.seuil_credits_min is None
            and req.seuil_credits_max is None
            and req.seuil_appels_min is None
        ):
            raise HTTPException(
                400,
                "Au moins un seuil (seuil_credits_min/max ou seuil_appels_min) requis pour cible=consommation",
            )
        depuis = datetime.utcnow() - timedelta(days=req.periode_jours or 30)
        agg_res = await db.execute(
            select(
                ConsommationTokenDB.user_id,
                func.coalesce(func.sum(ConsommationTokenDB.credits_debites), 0).label("cum"),
                func.count().label("appels"),
            )
            .where(ConsommationTokenDB.cree_le >= depuis)
            .group_by(ConsommationTokenDB.user_id)
        )
        ids_match: List[int] = []
        for r in agg_res.all():
            cum = float(r.cum or 0)
            appels = int(r.appels or 0)
            if req.seuil_credits_min is not None and cum < req.seuil_credits_min:
                continue
            if req.seuil_credits_max is not None and cum > req.seuil_credits_max:
                continue
            if req.seuil_appels_min is not None and appels < req.seuil_appels_min:
                continue
            ids_match.append(int(r.user_id))
        if not ids_match:
            return {"succes": True, "beneficiaires": 0, "montant": req.montant}
        q = q.where(CreditIAUserDB.user_id.in_(ids_match))
    elif req.cible != "tous":
        raise HTTPException(400, "cible invalide (tous | plan | ids | consommation)")

    # Filtre géographique additionnel
    pays_codes = _resolve_pays_filter(req.pays, req.continent)
    if pays_codes:
        ids_pays = await _user_ids_du_pays(db, pays_codes)
        if not ids_pays:
            return {"succes": True, "beneficiaires": 0, "montant": req.montant}
        q = q.where(CreditIAUserDB.user_id.in_(ids_pays))

    res = await db.execute(q)
    credits = res.scalars().all()
    for c in credits:
        c.credits_alloues += req.montant
        c.mise_a_jour = datetime.utcnow()
    await db.commit()
    logger.info(
        f"[Admin {admin.user_id}] Promotion +{req.montant} crédits cible={req.cible} "
        f"pays={req.pays or req.continent or '*'} → {len(credits)} bénéficiaires"
    )
    return {"succes": True, "beneficiaires": len(credits), "montant": req.montant}


@router.get("/stats/avancees", summary="Statistiques avancées plateforme")
async def stats_avancees(
    admin: TokenData = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
    pays: Optional[str] = Query(None, description="Code ISO alpha-2 (ex: CM)"),
    continent: Optional[str] = Query(None, description="Code continent (AF/EU/AM/AS)"),
):
    from modules.pro.service_credits import CREDITS_PAR_PLAN

    # Filtre géographique
    pays_codes = _resolve_pays_filter(pays, continent)
    geo_user_ids: Optional[List[int]] = None
    if pays_codes:
        geo_user_ids = await _user_ids_du_pays(db, pays_codes)
        if not geo_user_ids:
            return {
                "total_utilisateurs": 0, "actifs": 0, "bloques": 0,
                "repartition_plans": [], "top_plan_users": None,
                "signups_30j": [], "mrr_estime_fcfa": 0,
                "top_consommateurs": [], "upgrades_30j": [],
                "abonnes_reguliers": [], "credits_par_plan": CREDITS_PAR_PLAN,
                "filtres": {"pays": pays, "continent": continent},
            }

    # Répartition par plan
    plan_stmt = select(CreditIAUserDB.plan, func.count()).group_by(CreditIAUserDB.plan)
    if geo_user_ids is not None:
        plan_stmt = plan_stmt.where(CreditIAUserDB.user_id.in_(geo_user_ids))
    plan_res = await db.execute(plan_stmt)
    repartition_plans = [{"plan": p or "gratuit", "count": int(n)} for p, n in plan_res.all()]
    repartition_plans_sorted = sorted(repartition_plans, key=lambda x: x["count"], reverse=True)
    top_plan_users = repartition_plans_sorted[0] if repartition_plans_sorted else None

    # Total utilisateurs / actifs / bloqués
    total_stmt = select(func.count()).select_from(UtilisateurDB)
    if geo_user_ids is not None:
        total_stmt = total_stmt.where(UtilisateurDB.id.in_(geo_user_ids))
    total_users = int((await db.execute(total_stmt)).scalar() or 0)
    actifs_stmt = select(func.count()).select_from(UtilisateurDB).where(UtilisateurDB.actif == True)
    if geo_user_ids is not None:
        actifs_stmt = actifs_stmt.where(UtilisateurDB.id.in_(geo_user_ids))
    actifs = int((await db.execute(actifs_stmt)).scalar() or 0)
    bloques = total_users - actifs

    # Inscriptions 30 derniers jours par jour
    since = datetime.utcnow() - timedelta(days=30)
    signups_stmt = (
        select(func.date(UtilisateurDB.cree_le).label("jour"), func.count())
        .where(UtilisateurDB.cree_le >= since)
        .group_by(func.date(UtilisateurDB.cree_le))
        .order_by(func.date(UtilisateurDB.cree_le))
    )
    if geo_user_ids is not None:
        signups_stmt = signups_stmt.where(UtilisateurDB.id.in_(geo_user_ids))
    signups_res = await db.execute(signups_stmt)
    signups = [{"jour": str(j), "count": int(n)} for j, n in signups_res.all()]

    # MRR estimé (plans payants × prix mensuel approximatif)
    PRIX_MENSUEL = {"starter": 5000, "pro": 20000, "business": 100000}  # FCFA
    mrr = 0.0
    for r in repartition_plans:
        mrr += PRIX_MENSUEL.get(r["plan"], 0) * r["count"]

    # Top 10 consommateurs (30 derniers jours)
    top_stmt = (
        select(
            ConsommationTokenDB.user_id,
            func.coalesce(func.sum(ConsommationTokenDB.credits_debites), 0).label("credits"),
            func.count().label("appels"),
        )
        .where(ConsommationTokenDB.cree_le >= since)
        .group_by(ConsommationTokenDB.user_id)
        .order_by(func.sum(ConsommationTokenDB.credits_debites).desc())
        .limit(10)
    )
    if geo_user_ids is not None:
        top_stmt = top_stmt.where(ConsommationTokenDB.user_id.in_(geo_user_ids))
    top_res = await db.execute(top_stmt)
    top_rows = list(top_res.all())
    top_ids = [int(r.user_id) for r in top_rows]
    user_map = {}
    if top_ids:
        u_res = await db.execute(select(UtilisateurDB).where(UtilisateurDB.id.in_(top_ids)))
        for u in u_res.scalars().all():
            user_map[u.id] = u
    top_consommateurs = [{
        "user_id": int(r.user_id),
        "username": user_map.get(int(r.user_id)).username if user_map.get(int(r.user_id)) else f"#{r.user_id}",
        "email": user_map.get(int(r.user_id)).email if user_map.get(int(r.user_id)) else None,
        "credits": float(r.credits or 0),
        "appels": int(r.appels),
    } for r in top_rows]

    # Upgrades 30j : utilisateurs avec ≥2 paiements abonnement où le dernier
    # plan est plus cher que le premier (sur 30j).
    PRIX_PLAN_FCFA = {"gratuit": 0, "starter": 5000, "pro": 20000, "business": 100000}
    upg_stmt = (
        select(PaymentTransactionV2DB)
        .where(and_(
            PaymentTransactionV2DB.status == "success",
            PaymentTransactionV2DB.type == "abonnement",
            PaymentTransactionV2DB.completed_at >= since,
        ))
        .order_by(PaymentTransactionV2DB.user_id, PaymentTransactionV2DB.completed_at)
    )
    if geo_user_ids is not None:
        upg_stmt = upg_stmt.where(PaymentTransactionV2DB.user_id.in_(geo_user_ids))
    upg_res = await db.execute(upg_stmt)
    par_user: dict[int, list] = {}
    for tx in upg_res.scalars().all():
        if tx.user_id is None:
            continue
        par_user.setdefault(int(tx.user_id), []).append(tx)
    upgrade_ids: list[int] = []
    upgrades_detail: list[dict] = []
    abonnes_reguliers_ids: list[int] = []
    for uid, txs in par_user.items():
        if len(txs) >= 2:
            premier = (txs[0].plan_ou_pack or "").lower()
            dernier = (txs[-1].plan_ou_pack or "").lower()
            if PRIX_PLAN_FCFA.get(dernier, 0) > PRIX_PLAN_FCFA.get(premier, 0):
                upgrade_ids.append(uid)
                upgrades_detail.append({
                    "user_id": uid, "depuis": premier or "—", "vers": dernier or "—",
                    "nb_paiements": len(txs),
                })
        if len(txs) >= 3:
            abonnes_reguliers_ids.append(uid)

    # Abonnés réguliers (≥3 paiements abonnement réussis sur 90j)
    since_90 = datetime.utcnow() - timedelta(days=90)
    reg_stmt = (
        select(
            PaymentTransactionV2DB.user_id,
            func.count().label("nb"),
            func.coalesce(func.sum(PaymentTransactionV2DB.amount), 0).label("total"),
        )
        .where(and_(
            PaymentTransactionV2DB.status == "success",
            PaymentTransactionV2DB.type == "abonnement",
            PaymentTransactionV2DB.completed_at >= since_90,
        ))
        .group_by(PaymentTransactionV2DB.user_id)
        .having(func.count() >= 3)
        .order_by(func.count().desc())
        .limit(20)
    )
    if geo_user_ids is not None:
        reg_stmt = reg_stmt.where(PaymentTransactionV2DB.user_id.in_(geo_user_ids))
    reg_res = await db.execute(reg_stmt)
    abonnes_reguliers = [
        {"user_id": int(r.user_id), "nb_paiements": int(r.nb), "total": float(r.total or 0)}
        for r in reg_res.all()
    ]
    # Enrichir upgrades + reguliers avec username
    enrich_ids = list({d["user_id"] for d in upgrades_detail} | {d["user_id"] for d in abonnes_reguliers})
    if enrich_ids:
        u_res = await db.execute(select(UtilisateurDB).where(UtilisateurDB.id.in_(enrich_ids)))
        umap = {u.id: u for u in u_res.scalars().all()}
        for d in upgrades_detail:
            u = umap.get(d["user_id"])
            d["username"] = u.username if u else f"#{d['user_id']}"
            d["email"] = u.email if u else None
        for d in abonnes_reguliers:
            u = umap.get(d["user_id"])
            d["username"] = u.username if u else f"#{d['user_id']}"
            d["email"] = u.email if u else None

    return {
        "total_utilisateurs": total_users,
        "actifs": actifs,
        "bloques": bloques,
        "repartition_plans": repartition_plans,
        "top_plan_users": top_plan_users,
        "signups_30j": signups,
        "mrr_estime_fcfa": mrr,
        "top_consommateurs": top_consommateurs,
        "upgrades_30j": upgrades_detail,
        "abonnes_reguliers": abonnes_reguliers,
        "credits_par_plan": CREDITS_PAR_PLAN,
        "filtres": {"pays": pays, "continent": continent},
    }


@router.get("/stats/revenus", summary="Chiffre d'affaires et revenus de la plateforme")
async def stats_revenus(
    admin: TokenData = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
    date_debut: Optional[str] = Query(None, description="ISO YYYY-MM-DD — début de la période personnalisée"),
    date_fin: Optional[str] = Query(None, description="ISO YYYY-MM-DD — fin de la période personnalisée"),
    pays: Optional[str] = Query(None, description="Code ISO alpha-2 (ex: CM)"),
    continent: Optional[str] = Query(None, description="Code continent (AF/EU/AM/AS)"),
):
    """
    Retourne :
      - CA total (toutes transactions success) par devise
      - CA 30j / 7j / aujourd'hui
      - CA sur période personnalisée (si date_debut/date_fin fournis)
      - Évolution mensuelle (12 derniers mois)
      - Répartition par plan/pack (+ top_plan_ca)
      - Répartition par provider (CinetPay, Stripe, …)
      - Compteurs success / pending / failed
      - 10 dernières transactions

    Filtres optionnels :
      - date_debut / date_fin : restreint TOUS les agrégats à cette fenêtre
      - pays / continent : restreint aux utilisateurs ayant un profil dans ce pays
    """
    now = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    j7 = now - timedelta(days=7)
    j30 = now - timedelta(days=30)
    m12 = now - timedelta(days=365)

    # Parse période personnalisée
    custom_debut: Optional[datetime] = None
    custom_fin: Optional[datetime] = None
    if date_debut:
        try:
            custom_debut = datetime.fromisoformat(date_debut)
        except ValueError:
            raise HTTPException(400, "date_debut invalide (format ISO YYYY-MM-DD attendu)")
    if date_fin:
        try:
            custom_fin = datetime.fromisoformat(date_fin)
            # inclusive jusqu'à fin de journée
            if custom_fin.hour == 0 and custom_fin.minute == 0:
                custom_fin = custom_fin + timedelta(days=1) - timedelta(seconds=1)
        except ValueError:
            raise HTTPException(400, "date_fin invalide (format ISO YYYY-MM-DD attendu)")

    # Filtre géographique → liste de user_ids
    pays_codes = _resolve_pays_filter(pays, continent)
    geo_user_ids: Optional[List[int]] = None
    if pays_codes:
        geo_user_ids = await _user_ids_du_pays(db, pays_codes)
        if not geo_user_ids:
            # Aucun utilisateur dans ce pays → tout vide
            return {
                "ca_total_par_devise": [], "ca_aujourdhui": [], "ca_7j": [], "ca_30j": [],
                "ca_periode": [], "evolution_12mois": [], "par_plan": [], "top_plan_ca": None,
                "par_provider": [], "par_statut": {}, "dernieres_transactions": [],
                "filtres": {"pays": pays, "continent": continent, "date_debut": date_debut, "date_fin": date_fin},
            }

    def _apply_geo(stmt):
        if geo_user_ids is not None:
            return stmt.where(PaymentTransactionV2DB.user_id.in_(geo_user_ids))
        return stmt

    def _apply_period(stmt):
        if custom_debut is not None:
            stmt = stmt.where(PaymentTransactionV2DB.completed_at >= custom_debut)
        if custom_fin is not None:
            stmt = stmt.where(PaymentTransactionV2DB.completed_at <= custom_fin)
        return stmt

    # CA total par devise (status = success) — applique geo + période si fournie
    base_total = select(
        PaymentTransactionV2DB.currency,
        func.coalesce(func.sum(PaymentTransactionV2DB.amount), 0),
        func.count(),
    ).where(PaymentTransactionV2DB.status == "success").group_by(PaymentTransactionV2DB.currency)
    base_total = _apply_geo(_apply_period(base_total))
    ca_devise_res = await db.execute(base_total)
    ca_par_devise = [
        {"devise": c or "XAF", "montant": float(s or 0), "transactions": int(n)}
        for c, s, n in ca_devise_res.all()
    ]

    async def _sum_between(since, until=None):
        stmt = select(
            PaymentTransactionV2DB.currency,
            func.coalesce(func.sum(PaymentTransactionV2DB.amount), 0),
            func.count(),
        ).where(and_(
            PaymentTransactionV2DB.status == "success",
            PaymentTransactionV2DB.completed_at >= since,
        )).group_by(PaymentTransactionV2DB.currency)
        if until is not None:
            stmt = stmt.where(PaymentTransactionV2DB.completed_at <= until)
        stmt = _apply_geo(stmt)
        r = await db.execute(stmt)
        return [
            {"devise": c or "XAF", "montant": float(s or 0), "transactions": int(n)}
            for c, s, n in r.all()
        ]

    ca_jour = await _sum_between(today)
    ca_7j = await _sum_between(j7)
    ca_30j = await _sum_between(j30)
    ca_periode: List[dict] = []
    if custom_debut is not None or custom_fin is not None:
        ca_periode = await _sum_between(custom_debut or datetime(1970, 1, 1), custom_fin)

    # Évolution mensuelle (12 mois) — agrégé en XAF/XOF additionné car valeurs proches
    monthly_stmt = select(
        func.date_trunc("month", PaymentTransactionV2DB.completed_at).label("mois"),
        PaymentTransactionV2DB.currency,
        func.coalesce(func.sum(PaymentTransactionV2DB.amount), 0),
        func.count(),
    ).where(and_(
        PaymentTransactionV2DB.status == "success",
        PaymentTransactionV2DB.completed_at >= (custom_debut or m12),
    )).group_by("mois", PaymentTransactionV2DB.currency).order_by("mois")
    if custom_fin is not None:
        monthly_stmt = monthly_stmt.where(PaymentTransactionV2DB.completed_at <= custom_fin)
    monthly_res = await db.execute(_apply_geo(monthly_stmt))
    evolution = [
        {"mois": m.strftime("%Y-%m") if m else "—", "devise": c or "XAF",
         "montant": float(s or 0), "transactions": int(n)}
        for m, c, s, n in monthly_res.all()
    ]

    # Par plan/pack
    par_plan_stmt = select(
        PaymentTransactionV2DB.plan_ou_pack,
        PaymentTransactionV2DB.currency,
        func.coalesce(func.sum(PaymentTransactionV2DB.amount), 0),
        func.count(),
    ).where(PaymentTransactionV2DB.status == "success").group_by(
        PaymentTransactionV2DB.plan_ou_pack, PaymentTransactionV2DB.currency
    ).order_by(func.sum(PaymentTransactionV2DB.amount).desc())
    par_plan_res = await db.execute(_apply_geo(_apply_period(par_plan_stmt)))
    par_plan = [
        {"plan": p or "—", "devise": c or "XAF", "montant": float(s or 0), "transactions": int(n)}
        for p, c, s, n in par_plan_res.all()
    ]
    top_plan_ca = par_plan[0] if par_plan else None

    # Par provider
    par_provider_stmt = select(
        PaymentTransactionV2DB.provider,
        PaymentTransactionV2DB.currency,
        func.coalesce(func.sum(PaymentTransactionV2DB.amount), 0),
        func.count(),
    ).where(PaymentTransactionV2DB.status == "success").group_by(
        PaymentTransactionV2DB.provider, PaymentTransactionV2DB.currency
    )
    par_provider_res = await db.execute(_apply_geo(_apply_period(par_provider_stmt)))
    par_provider = [
        {"provider": p or "—", "devise": c or "XAF", "montant": float(s or 0), "transactions": int(n)}
        for p, c, s, n in par_provider_res.all()
    ]

    # Compteurs status
    status_stmt = select(PaymentTransactionV2DB.status, func.count()).group_by(PaymentTransactionV2DB.status)
    status_res = await db.execute(_apply_geo(_apply_period(status_stmt)))
    par_statut = {s or "?": int(n) for s, n in status_res.all()}

    # 10 dernières transactions
    last_stmt = select(PaymentTransactionV2DB).order_by(PaymentTransactionV2DB.created_at.desc()).limit(10)
    last_res = await db.execute(_apply_geo(last_stmt))
    dernieres = []
    for t in last_res.scalars().all():
        dernieres.append({
            "reference": t.reference,
            "user_id": int(t.user_id) if t.user_id else None,
            "type": t.type,
            "plan": t.plan_ou_pack,
            "amount": float(t.amount or 0),
            "currency": t.currency,
            "provider": t.provider,
            "status": t.status,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        })

    return {
        "ca_total_par_devise": ca_par_devise,
        "ca_aujourdhui": ca_jour,
        "ca_7j": ca_7j,
        "ca_30j": ca_30j,
        "ca_periode": ca_periode,
        "evolution_12mois": evolution,
        "par_plan": par_plan,
        "top_plan_ca": top_plan_ca,
        "par_provider": par_provider,
        "par_statut": par_statut,
        "dernieres_transactions": dernieres,
        "filtres": {
            "pays": pays, "continent": continent,
            "date_debut": date_debut, "date_fin": date_fin,
        },
    }


@router.get("/stats", summary="Statistiques globales de la plateforme")
async def stats_plateforme(
    admin: TokenData = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Retourne les statistiques d'utilisation globales."""
    from modules.pro.service_profil import stats_globales
    try:
        stats = await stats_globales(db)
        return stats
    except Exception as e:
        logger.error(f"[Admin] Erreur stats: {e}")
        return {
            "nb_utilisateurs": 0,
            "nb_requetes_total": 0,
            "nb_documents_total": 0,
            "metiers_top": [],
            "pays_top": [],
        }


@router.put("/utilisateurs/{user_id}/metier", summary="Modifier le métier d'un utilisateur")
async def changer_metier_utilisateur(
    user_id: int,
    req: ChangerMetierRequest,
    admin: TokenData = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Change le métier (et donc l'agent IA) d'un utilisateur."""
    from modules.pro.service_profil import mettre_a_jour
    data = {"metier": req.metier}
    if req.niveau:
        data["niveau"] = req.niveau
    if req.pays:
        data["pays"] = req.pays
    try:
        profil = await mettre_a_jour(user_id, data, db)
        return {"succes": True, "user_id": user_id, "profil": profil.to_dict()}
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Utilisateur introuvable : {e}")


@router.get("/geo/options", summary="Pays et continents disponibles pour les filtres admin")
async def geo_options(admin: TokenData = Depends(_require_admin)):
    """Retourne la liste des continents et pays connus pour alimenter les selects UI."""
    from core.pays_devise import PAYS_CONTINENT
    pays = sorted([{"code": c, "continent": cont} for c, cont in PAYS_CONTINENT.items()],
                  key=lambda x: x["code"])
    return {
        "continents": [{"code": k, "label": v} for k, v in CONTINENT_LABELS.items()],
        "pays": pays,
    }


@router.get("/agents", summary="Liste tous les agents disponibles avec leurs capacités")
async def lister_agents(admin: TokenData = Depends(_require_admin)):
    """Retourne tous les agents IA disponibles sur la plateforme."""
    return {
        "agents": [
            {"id": "comptable",        "label": "Agent Comptable",       "metiers": ["comptable", "auditeur", "fiscaliste"]},
            {"id": "drh",              "label": "Agent DRH",              "metiers": ["DRH", "gestionnaire_rh"]},
            {"id": "daf",              "label": "Agent DAF",              "metiers": ["daf"]},
            {"id": "juriste",          "label": "Agent Juridique",        "metiers": ["juriste", "avocat"]},
            {"id": "banquier",         "label": "Agent Bancaire",         "metiers": ["banquier", "analyste_credit"]},
            {"id": "ingenieur",        "label": "Agent Ingénieur",        "metiers": ["ingenieur", "chef_projet"]},
            {"id": "commercial",       "label": "Agent Commercial",       "metiers": ["directeur_commercial", "commercial"]},
            {"id": "ong",              "label": "Agent ONG",              "metiers": ["charge_projets_ong", "coordinateur_ong"]},
            {"id": "microfinance",     "label": "Agent Microfinance",     "metiers": ["responsable_microfinance", "credit_officer"]},
            {"id": "douanier",         "label": "Agent Douanier",         "metiers": ["transitaire", "douanier"]},
            {"id": "generaliste",      "label": "Agent Généraliste",      "metiers": ["*"]},
        ],
        "total": 11,
    }
