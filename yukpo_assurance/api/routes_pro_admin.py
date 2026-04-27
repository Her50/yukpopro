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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import TokenData, get_current_user
from core.database import (
    async_session_maker, UtilisateurDB, CreditIAUserDB, ConsommationTokenDB,
    PaymentTransactionV2DB,
)

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
    cible: str = Field("tous", description="tous | plan | ids")
    plan: Optional[str] = None
    user_ids: Optional[List[int]] = None
    motif: Optional[str] = None


@router.post("/promotions", summary="Bonus crédits global ou ciblé")
async def lancer_promotion(
    req: PromotionRequest,
    admin: TokenData = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Distribue `montant` crédits bonus :
      - cible=tous   → tous les utilisateurs ayant un solde
      - cible=plan   → tous ceux d'un plan donné (req.plan)
      - cible=ids    → liste explicite (req.user_ids)
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
    elif req.cible != "tous":
        raise HTTPException(400, "cible invalide (tous | plan | ids)")

    res = await db.execute(q)
    credits = res.scalars().all()
    for c in credits:
        c.credits_alloues += req.montant
        c.mise_a_jour = datetime.utcnow()
    await db.commit()
    logger.info(f"[Admin {admin.user_id}] Promotion +{req.montant} crédits cible={req.cible} → {len(credits)} bénéficiaires")
    return {"succes": True, "beneficiaires": len(credits), "montant": req.montant}


@router.get("/stats/avancees", summary="Statistiques avancées plateforme")
async def stats_avancees(
    admin: TokenData = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    from modules.pro.service_credits import CREDITS_PAR_PLAN

    # Répartition par plan
    plan_res = await db.execute(
        select(CreditIAUserDB.plan, func.count()).group_by(CreditIAUserDB.plan)
    )
    repartition_plans = [{"plan": p or "gratuit", "count": int(n)} for p, n in plan_res.all()]

    # Total utilisateurs / actifs / bloqués
    total_users = int((await db.execute(select(func.count()).select_from(UtilisateurDB))).scalar() or 0)
    actifs = int((await db.execute(
        select(func.count()).select_from(UtilisateurDB).where(UtilisateurDB.actif == True)
    )).scalar() or 0)
    bloques = total_users - actifs

    # Inscriptions 30 derniers jours par jour
    since = datetime.utcnow() - timedelta(days=30)
    signups_res = await db.execute(
        select(func.date(UtilisateurDB.cree_le).label("jour"), func.count())
        .where(UtilisateurDB.cree_le >= since)
        .group_by(func.date(UtilisateurDB.cree_le))
        .order_by(func.date(UtilisateurDB.cree_le))
    )
    signups = [{"jour": str(j), "count": int(n)} for j, n in signups_res.all()]

    # MRR estimé (plans payants × prix mensuel approximatif)
    PRIX_MENSUEL = {"starter": 5000, "pro": 20000, "business": 100000}  # FCFA
    mrr = 0.0
    for r in repartition_plans:
        mrr += PRIX_MENSUEL.get(r["plan"], 0) * r["count"]

    # Top 10 consommateurs (30 derniers jours)
    top_res = await db.execute(
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

    return {
        "total_utilisateurs": total_users,
        "actifs": actifs,
        "bloques": bloques,
        "repartition_plans": repartition_plans,
        "signups_30j": signups,
        "mrr_estime_fcfa": mrr,
        "top_consommateurs": top_consommateurs,
        "credits_par_plan": CREDITS_PAR_PLAN,
    }


@router.get("/stats/revenus", summary="Chiffre d'affaires et revenus de la plateforme")
async def stats_revenus(
    admin: TokenData = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Retourne :
      - CA total (toutes transactions success) par devise
      - CA 30j / 7j / aujourd'hui
      - Évolution mensuelle (12 derniers mois)
      - Répartition par plan/pack
      - Répartition par provider (CinetPay, Stripe, …)
      - Compteurs success / pending / failed
      - 10 dernières transactions
    """
    now = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    j7 = now - timedelta(days=7)
    j30 = now - timedelta(days=30)
    m12 = now - timedelta(days=365)

    # CA total par devise (status = success)
    ca_devise_res = await db.execute(
        select(
            PaymentTransactionV2DB.currency,
            func.coalesce(func.sum(PaymentTransactionV2DB.amount), 0),
            func.count(),
        )
        .where(PaymentTransactionV2DB.status == "success")
        .group_by(PaymentTransactionV2DB.currency)
    )
    ca_par_devise = [
        {"devise": c or "XAF", "montant": float(s or 0), "transactions": int(n)}
        for c, s, n in ca_devise_res.all()
    ]

    async def _sum_since(since):
        r = await db.execute(
            select(
                PaymentTransactionV2DB.currency,
                func.coalesce(func.sum(PaymentTransactionV2DB.amount), 0),
                func.count(),
            )
            .where(and_(
                PaymentTransactionV2DB.status == "success",
                PaymentTransactionV2DB.completed_at >= since,
            ))
            .group_by(PaymentTransactionV2DB.currency)
        )
        return [
            {"devise": c or "XAF", "montant": float(s or 0), "transactions": int(n)}
            for c, s, n in r.all()
        ]

    ca_jour = await _sum_since(today)
    ca_7j = await _sum_since(j7)
    ca_30j = await _sum_since(j30)

    # Évolution mensuelle (12 mois) — agrégé en XAF/XOF additionné car valeurs proches
    monthly_res = await db.execute(
        select(
            func.date_trunc("month", PaymentTransactionV2DB.completed_at).label("mois"),
            PaymentTransactionV2DB.currency,
            func.coalesce(func.sum(PaymentTransactionV2DB.amount), 0),
            func.count(),
        )
        .where(and_(
            PaymentTransactionV2DB.status == "success",
            PaymentTransactionV2DB.completed_at >= m12,
        ))
        .group_by("mois", PaymentTransactionV2DB.currency)
        .order_by("mois")
    )
    evolution = [
        {"mois": m.strftime("%Y-%m") if m else "—", "devise": c or "XAF",
         "montant": float(s or 0), "transactions": int(n)}
        for m, c, s, n in monthly_res.all()
    ]

    # Par plan/pack
    par_plan_res = await db.execute(
        select(
            PaymentTransactionV2DB.plan_ou_pack,
            PaymentTransactionV2DB.currency,
            func.coalesce(func.sum(PaymentTransactionV2DB.amount), 0),
            func.count(),
        )
        .where(PaymentTransactionV2DB.status == "success")
        .group_by(PaymentTransactionV2DB.plan_ou_pack, PaymentTransactionV2DB.currency)
        .order_by(func.sum(PaymentTransactionV2DB.amount).desc())
    )
    par_plan = [
        {"plan": p or "—", "devise": c or "XAF", "montant": float(s or 0), "transactions": int(n)}
        for p, c, s, n in par_plan_res.all()
    ]

    # Par provider
    par_provider_res = await db.execute(
        select(
            PaymentTransactionV2DB.provider,
            PaymentTransactionV2DB.currency,
            func.coalesce(func.sum(PaymentTransactionV2DB.amount), 0),
            func.count(),
        )
        .where(PaymentTransactionV2DB.status == "success")
        .group_by(PaymentTransactionV2DB.provider, PaymentTransactionV2DB.currency)
    )
    par_provider = [
        {"provider": p or "—", "devise": c or "XAF", "montant": float(s or 0), "transactions": int(n)}
        for p, c, s, n in par_provider_res.all()
    ]

    # Compteurs status
    status_res = await db.execute(
        select(PaymentTransactionV2DB.status, func.count())
        .group_by(PaymentTransactionV2DB.status)
    )
    par_statut = {s or "?": int(n) for s, n in status_res.all()}

    # 10 dernières transactions
    last_res = await db.execute(
        select(PaymentTransactionV2DB)
        .order_by(PaymentTransactionV2DB.created_at.desc())
        .limit(10)
    )
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
        "evolution_12mois": evolution,
        "par_plan": par_plan,
        "par_provider": par_provider,
        "par_statut": par_statut,
        "dernieres_transactions": dernieres,
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
