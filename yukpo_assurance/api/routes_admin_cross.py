"""Admin cross-app — dashboard unifié YukpoPro + YukpoSecrétariat.

Endpoints administrateur consolidés permettant de visualiser la
consommation IA, les revenus, les utilisateurs et les alertes pour :
  - scope=pro   (uniquement YukpoPro)
  - scope=sec   (uniquement YukpoSecrétariat)
  - scope=both  (les deux apps agrégées) — défaut

Réservé aux rôles admin / super_admin / yukpo_owner — l'admin peut donc
être connecté indistinctement sur l'une ou l'autre application et voir
le même dashboard avec le scope qu'il choisit.

Endpoints exposés (préfixés /api/v1/admin-cross) :
  - GET /dashboard          : KPIs synthétiques (utilisateurs, revenus, conso)
  - GET /usage              : agrégation par jour / par feature / par app
  - GET /cost               : coût USD / FCFA / crédits par jour
  - GET /by-feature         : top features les plus consommatrices
  - GET /by-provider        : conso par fournisseur (Anthropic/OpenAI/fal/...)
  - GET /by-user            : top consommateurs (toutes apps confondues)
  - GET /alerts             : alertes actives (seuils dépassés)
  - GET /thresholds         : seuils configurés (lecture seule pour MVP)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, TokenData
from core.database import (
    async_session_maker,
    ConsommationTokenDB,
    ConsommationBureauDB,
    CreditIAUserDB,
    CreditBureauDB,
    UtilisateurDB,
)
from modules.admin_cross import (
    classifier_provider,
    PROVIDERS_KNOWN,
    evaluer_alertes,
    SEUILS_DEFAUT,
)


logger = logging.getLogger("yukpo_assurance.api.admin_cross")

router = APIRouter()


async def get_db():
    async with async_session_maker() as session:
        yield session


def _require_admin(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """Accès admin/super_admin/yukpo_owner — peu importe l'app de connexion."""
    if current_user.role not in ("admin", "super_admin", "yukpo_owner"):
        raise HTTPException(
            status_code=403,
            detail="Accès réservé aux administrateurs (Pro, Secrétariat ou Yukpo).",
        )
    return current_user


def _normaliser_scope(scope: str | None) -> str:
    s = (scope or "both").lower().strip()
    return s if s in ("pro", "sec", "both") else "both"


def _date_debut(jours: int) -> datetime:
    return datetime.utcnow() - timedelta(days=max(1, min(jours, 365)))


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD — KPIs synthétiques
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/dashboard", summary="KPIs synthétiques cross-app")
async def dashboard(
    scope: str = Query("both", regex="^(pro|sec|both)$"),
    jours: int = Query(30, ge=1, le=365),
    admin: TokenData = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Vue d'ensemble : utilisateurs actifs, revenus IA, conso totale, top features."""
    scope = _normaliser_scope(scope)
    since = _date_debut(jours)

    # ─── Utilisateurs ─────────────────────────────────────────────────────
    nb_users_total = (await db.execute(select(func.count(UtilisateurDB.id)))).scalar() or 0
    nb_users_actifs = (await db.execute(
        select(func.count(UtilisateurDB.id)).where(UtilisateurDB.actif == True)
    )).scalar() or 0

    # ─── Conso & coûts ────────────────────────────────────────────────────
    conso_pro = {"appels": 0, "fcfa": 0.0, "credits": 0.0, "tokens_in": 0, "tokens_out": 0}
    conso_sec = {"appels": 0, "fcfa": 0.0, "credits": 0.0, "tokens_in": 0, "tokens_out": 0}

    if scope in ("pro", "both"):
        r = await db.execute(
            select(
                func.count().label("nb"),
                func.coalesce(func.sum(ConsommationTokenDB.cout_fcfa), 0),
                func.coalesce(func.sum(ConsommationTokenDB.credits_debites), 0),
                func.coalesce(func.sum(ConsommationTokenDB.tokens_input), 0),
                func.coalesce(func.sum(ConsommationTokenDB.tokens_output), 0),
            ).where(ConsommationTokenDB.cree_le >= since)
        )
        nb, fcfa, cr, ti, to = r.one()
        conso_pro = {"appels": int(nb or 0), "fcfa": float(fcfa or 0), "credits": float(cr or 0),
                     "tokens_in": int(ti or 0), "tokens_out": int(to or 0)}

    if scope in ("sec", "both"):
        r = await db.execute(
            select(
                func.count().label("nb"),
                func.coalesce(func.sum(ConsommationBureauDB.cout_fcfa), 0),
                func.coalesce(func.sum(ConsommationBureauDB.credits_debites), 0),
                func.coalesce(func.sum(ConsommationBureauDB.tokens_input), 0),
                func.coalesce(func.sum(ConsommationBureauDB.tokens_output), 0),
            ).where(ConsommationBureauDB.cree_le >= since)
        )
        nb, fcfa, cr, ti, to = r.one()
        conso_sec = {"appels": int(nb or 0), "fcfa": float(fcfa or 0), "credits": float(cr or 0),
                     "tokens_in": int(ti or 0), "tokens_out": int(to or 0)}

    # ─── Top features (modules) ───────────────────────────────────────────
    top_features: list[dict] = []
    if scope in ("pro", "both"):
        r = await db.execute(
            select(
                ConsommationTokenDB.module,
                func.count().label("nb"),
                func.coalesce(func.sum(ConsommationTokenDB.cout_fcfa), 0).label("fcfa"),
            ).where(ConsommationTokenDB.cree_le >= since)
             .group_by(ConsommationTokenDB.module)
             .order_by(func.sum(ConsommationTokenDB.cout_fcfa).desc())
             .limit(10)
        )
        for module, nb, fcfa in r.all():
            top_features.append({"app": "pro", "module": module or "unknown",
                                  "nb_appels": int(nb), "fcfa": float(fcfa or 0)})

    if scope in ("sec", "both"):
        r = await db.execute(
            select(
                ConsommationBureauDB.module,
                func.count().label("nb"),
                func.coalesce(func.sum(ConsommationBureauDB.cout_fcfa), 0).label("fcfa"),
            ).where(ConsommationBureauDB.cree_le >= since)
             .group_by(ConsommationBureauDB.module)
             .order_by(func.sum(ConsommationBureauDB.cout_fcfa).desc())
             .limit(10)
        )
        for module, nb, fcfa in r.all():
            top_features.append({"app": "sec", "module": module or "unknown",
                                  "nb_appels": int(nb), "fcfa": float(fcfa or 0)})

    # Re-tri global top 10 (toutes apps confondues si scope=both)
    top_features.sort(key=lambda x: x["fcfa"], reverse=True)
    top_features = top_features[:10]

    # ─── Crédits totaux émis ──────────────────────────────────────────────
    credits_pro = (await db.execute(
        select(func.coalesce(func.sum(CreditIAUserDB.credits_alloues), 0))
    )).scalar() or 0
    credits_sec = (await db.execute(
        select(func.coalesce(func.sum(CreditBureauDB.credits_alloues), 0))
    )).scalar() or 0

    return {
        "scope": scope,
        "periode_jours": jours,
        "utilisateurs": {
            "total": int(nb_users_total),
            "actifs": int(nb_users_actifs),
        },
        "consommation": {
            "pro": conso_pro,
            "sec": conso_sec,
            "total": {
                "appels": conso_pro["appels"] + conso_sec["appels"],
                "fcfa": conso_pro["fcfa"] + conso_sec["fcfa"],
                "credits": conso_pro["credits"] + conso_sec["credits"],
                "tokens_in": conso_pro["tokens_in"] + conso_sec["tokens_in"],
                "tokens_out": conso_pro["tokens_out"] + conso_sec["tokens_out"],
            },
        },
        "credits_alloues": {
            "pro": int(credits_pro),
            "sec": int(credits_sec),
        },
        "top_features": top_features,
    }


# ══════════════════════════════════════════════════════════════════════════════
# USAGE — agrégation par jour
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/usage", summary="Usage agrégé par jour")
async def usage(
    scope: str = Query("both", regex="^(pro|sec|both)$"),
    jours: int = Query(30, ge=1, le=365),
    admin: TokenData = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Agrégation par jour : nb_appels, FCFA, crédits, tokens_in, tokens_out."""
    scope = _normaliser_scope(scope)
    since = _date_debut(jours)

    # On agrège par jour (en UTC). Côté frontend, on assume une journée UTC
    # qui suffit pour des dashboards admin.
    par_jour: dict[str, dict] = {}

    async def _accumuler_pro():
        r = await db.execute(
            select(
                func.date_trunc("day", ConsommationTokenDB.cree_le).label("jour"),
                func.count().label("nb"),
                func.coalesce(func.sum(ConsommationTokenDB.cout_fcfa), 0),
                func.coalesce(func.sum(ConsommationTokenDB.credits_debites), 0),
                func.coalesce(func.sum(ConsommationTokenDB.tokens_input), 0),
                func.coalesce(func.sum(ConsommationTokenDB.tokens_output), 0),
            ).where(ConsommationTokenDB.cree_le >= since)
             .group_by("jour").order_by("jour")
        )
        for jour, nb, fcfa, cr, ti, to in r.all():
            key = jour.strftime("%Y-%m-%d") if jour else "unknown"
            d = par_jour.setdefault(key, {"jour": key, "nb_appels": 0, "fcfa": 0.0,
                                          "credits": 0.0, "tokens_in": 0, "tokens_out": 0,
                                          "pro_fcfa": 0.0, "sec_fcfa": 0.0})
            d["nb_appels"] += int(nb or 0)
            d["fcfa"] += float(fcfa or 0)
            d["credits"] += float(cr or 0)
            d["tokens_in"] += int(ti or 0)
            d["tokens_out"] += int(to or 0)
            d["pro_fcfa"] += float(fcfa or 0)

    async def _accumuler_sec():
        r = await db.execute(
            select(
                func.date_trunc("day", ConsommationBureauDB.cree_le).label("jour"),
                func.count().label("nb"),
                func.coalesce(func.sum(ConsommationBureauDB.cout_fcfa), 0),
                func.coalesce(func.sum(ConsommationBureauDB.credits_debites), 0),
                func.coalesce(func.sum(ConsommationBureauDB.tokens_input), 0),
                func.coalesce(func.sum(ConsommationBureauDB.tokens_output), 0),
            ).where(ConsommationBureauDB.cree_le >= since)
             .group_by("jour").order_by("jour")
        )
        for jour, nb, fcfa, cr, ti, to in r.all():
            key = jour.strftime("%Y-%m-%d") if jour else "unknown"
            d = par_jour.setdefault(key, {"jour": key, "nb_appels": 0, "fcfa": 0.0,
                                          "credits": 0.0, "tokens_in": 0, "tokens_out": 0,
                                          "pro_fcfa": 0.0, "sec_fcfa": 0.0})
            d["nb_appels"] += int(nb or 0)
            d["fcfa"] += float(fcfa or 0)
            d["credits"] += float(cr or 0)
            d["tokens_in"] += int(ti or 0)
            d["tokens_out"] += int(to or 0)
            d["sec_fcfa"] += float(fcfa or 0)

    if scope in ("pro", "both"):
        await _accumuler_pro()
    if scope in ("sec", "both"):
        await _accumuler_sec()

    series = sorted(par_jour.values(), key=lambda x: x["jour"])
    return {"scope": scope, "periode_jours": jours, "series": series}


# ══════════════════════════════════════════════════════════════════════════════
# COST — coût détaillé
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/cost", summary="Coûts agrégés (USD/FCFA/crédits)")
async def cost(
    scope: str = Query("both", regex="^(pro|sec|both)$"),
    jours: int = Query(30, ge=1, le=365),
    admin: TokenData = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    scope = _normaliser_scope(scope)
    since = _date_debut(jours)

    pro = {"usd": 0.0, "fcfa": 0.0, "credits": 0.0, "appels": 0}
    sec = {"usd": 0.0, "fcfa": 0.0, "credits": 0.0, "appels": 0}

    if scope in ("pro", "both"):
        r = await db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(ConsommationTokenDB.cout_usd), 0),
                func.coalesce(func.sum(ConsommationTokenDB.cout_fcfa), 0),
                func.coalesce(func.sum(ConsommationTokenDB.credits_debites), 0),
            ).where(ConsommationTokenDB.cree_le >= since)
        )
        nb, usd, fcfa, cr = r.one()
        pro = {"appels": int(nb or 0), "usd": float(usd or 0),
               "fcfa": float(fcfa or 0), "credits": float(cr or 0)}

    if scope in ("sec", "both"):
        r = await db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(ConsommationBureauDB.cout_usd), 0),
                func.coalesce(func.sum(ConsommationBureauDB.cout_fcfa), 0),
                func.coalesce(func.sum(ConsommationBureauDB.credits_debites), 0),
            ).where(ConsommationBureauDB.cree_le >= since)
        )
        nb, usd, fcfa, cr = r.one()
        sec = {"appels": int(nb or 0), "usd": float(usd or 0),
               "fcfa": float(fcfa or 0), "credits": float(cr or 0)}

    return {
        "scope": scope,
        "periode_jours": jours,
        "pro": pro,
        "sec": sec,
        "total": {
            "appels": pro["appels"] + sec["appels"],
            "usd": pro["usd"] + sec["usd"],
            "fcfa": pro["fcfa"] + sec["fcfa"],
            "credits": pro["credits"] + sec["credits"],
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# BY-FEATURE
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/by-feature", summary="Consommation par feature (module)")
async def by_feature(
    scope: str = Query("both", regex="^(pro|sec|both)$"),
    jours: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=500),
    admin: TokenData = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Top features les plus consommatrices, triées par FCFA décroissant."""
    scope = _normaliser_scope(scope)
    since = _date_debut(jours)
    rows: list[dict] = []

    if scope in ("pro", "both"):
        r = await db.execute(
            select(
                ConsommationTokenDB.module,
                func.count().label("nb"),
                func.coalesce(func.sum(ConsommationTokenDB.cout_fcfa), 0).label("fcfa"),
                func.coalesce(func.sum(ConsommationTokenDB.credits_debites), 0).label("cr"),
                func.coalesce(func.sum(ConsommationTokenDB.tokens_input), 0).label("ti"),
                func.coalesce(func.sum(ConsommationTokenDB.tokens_output), 0).label("to"),
            ).where(ConsommationTokenDB.cree_le >= since)
             .group_by(ConsommationTokenDB.module)
        )
        for module, nb, fcfa, cr, ti, to in r.all():
            rows.append({"app": "pro", "module": module or "unknown",
                         "nb_appels": int(nb or 0), "fcfa": float(fcfa or 0),
                         "credits": float(cr or 0),
                         "tokens_in": int(ti or 0), "tokens_out": int(to or 0)})

    if scope in ("sec", "both"):
        r = await db.execute(
            select(
                ConsommationBureauDB.module,
                func.count().label("nb"),
                func.coalesce(func.sum(ConsommationBureauDB.cout_fcfa), 0).label("fcfa"),
                func.coalesce(func.sum(ConsommationBureauDB.credits_debites), 0).label("cr"),
                func.coalesce(func.sum(ConsommationBureauDB.tokens_input), 0).label("ti"),
                func.coalesce(func.sum(ConsommationBureauDB.tokens_output), 0).label("to"),
            ).where(ConsommationBureauDB.cree_le >= since)
             .group_by(ConsommationBureauDB.module)
        )
        for module, nb, fcfa, cr, ti, to in r.all():
            rows.append({"app": "sec", "module": module or "unknown",
                         "nb_appels": int(nb or 0), "fcfa": float(fcfa or 0),
                         "credits": float(cr or 0),
                         "tokens_in": int(ti or 0), "tokens_out": int(to or 0)})

    rows.sort(key=lambda x: x["fcfa"], reverse=True)
    return {"scope": scope, "periode_jours": jours, "features": rows[:limit]}


# ══════════════════════════════════════════════════════════════════════════════
# BY-PROVIDER
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/by-provider", summary="Consommation par fournisseur LLM/IA")
async def by_provider(
    scope: str = Query("both", regex="^(pro|sec|both)$"),
    jours: int = Query(30, ge=1, le=365),
    admin: TokenData = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Agrégation par fournisseur (Anthropic, OpenAI, fal, Replicate…)
    via classification heuristique du champ `modele`."""
    scope = _normaliser_scope(scope)
    since = _date_debut(jours)

    par_provider: dict[str, dict] = {p: {"provider": p, "nb_appels": 0, "fcfa": 0.0,
                                          "usd": 0.0, "credits": 0.0,
                                          "tokens_in": 0, "tokens_out": 0,
                                          "modeles": set()}
                                       for p in PROVIDERS_KNOWN}

    async def _agreg_table(table_cls, app_label):
        r = await db.execute(
            select(
                table_cls.modele,
                func.count(),
                func.coalesce(func.sum(table_cls.cout_usd), 0),
                func.coalesce(func.sum(table_cls.cout_fcfa), 0),
                func.coalesce(func.sum(table_cls.credits_debites), 0),
                func.coalesce(func.sum(table_cls.tokens_input), 0),
                func.coalesce(func.sum(table_cls.tokens_output), 0),
            ).where(table_cls.cree_le >= since)
             .group_by(table_cls.modele)
        )
        for modele, nb, usd, fcfa, cr, ti, to in r.all():
            p = classifier_provider(modele)
            d = par_provider[p]
            d["nb_appels"] += int(nb or 0)
            d["usd"] += float(usd or 0)
            d["fcfa"] += float(fcfa or 0)
            d["credits"] += float(cr or 0)
            d["tokens_in"] += int(ti or 0)
            d["tokens_out"] += int(to or 0)
            if modele:
                d["modeles"].add(str(modele))

    if scope in ("pro", "both"):
        await _agreg_table(ConsommationTokenDB, "pro")
    if scope in ("sec", "both"):
        await _agreg_table(ConsommationBureauDB, "sec")

    # Sérialiser : sets → listes triées, ne garder que les providers utilisés
    sortie = []
    total_fcfa = sum(d["fcfa"] for d in par_provider.values())
    for p, d in par_provider.items():
        if d["nb_appels"] == 0 and d["fcfa"] == 0:
            continue
        d["modeles"] = sorted(d["modeles"])
        d["pct_fcfa"] = round((d["fcfa"] / total_fcfa) * 100, 2) if total_fcfa > 0 else 0.0
        sortie.append(d)
    sortie.sort(key=lambda x: x["fcfa"], reverse=True)

    return {"scope": scope, "periode_jours": jours,
            "providers": sortie, "total_fcfa": total_fcfa}


# ══════════════════════════════════════════════════════════════════════════════
# BY-USER (top consommateurs)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/by-user", summary="Top utilisateurs consommateurs")
async def by_user(
    scope: str = Query("both", regex="^(pro|sec|both)$"),
    jours: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
    admin: TokenData = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    scope = _normaliser_scope(scope)
    since = _date_debut(jours)
    rows: list[dict] = []

    async def _agreg(table_cls, app_label):
        r = await db.execute(
            select(
                table_cls.user_id,
                func.count(),
                func.coalesce(func.sum(table_cls.cout_fcfa), 0),
                func.coalesce(func.sum(table_cls.credits_debites), 0),
            ).where(table_cls.cree_le >= since)
             .group_by(table_cls.user_id)
             .order_by(func.sum(table_cls.cout_fcfa).desc())
             .limit(limit)
        )
        for uid, nb, fcfa, cr in r.all():
            rows.append({"app": app_label, "user_id": int(uid),
                         "nb_appels": int(nb or 0),
                         "fcfa": float(fcfa or 0), "credits": float(cr or 0)})

    if scope in ("pro", "both"):
        await _agreg(ConsommationTokenDB, "pro")
    if scope in ("sec", "both"):
        await _agreg(ConsommationBureauDB, "sec")

    # Enrichissement email (batch)
    user_ids = list({r["user_id"] for r in rows})
    emails: dict[int, str] = {}
    if user_ids:
        r = await db.execute(
            select(UtilisateurDB.id, UtilisateurDB.email).where(UtilisateurDB.id.in_(user_ids))
        )
        for uid, email in r.all():
            emails[int(uid)] = email or ""
    for row in rows:
        row["email"] = emails.get(row["user_id"], "")

    rows.sort(key=lambda x: x["fcfa"], reverse=True)
    return {"scope": scope, "periode_jours": jours, "users": rows[:limit]}


# ══════════════════════════════════════════════════════════════════════════════
# ALERTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/alerts", summary="Alertes actives (seuils dépassés)")
async def alerts(
    scope: str = Query("both", regex="^(pro|sec|both)$"),
    admin: TokenData = Depends(_require_admin),
):
    """Évalue les seuils statiques et retourne les alertes actives.

    Catégories : cost_daily_feature, cost_daily_user, cost_daily_global,
    cost_provider_share, quota_user_exhausted.
    """
    scope = _normaliser_scope(scope)
    alertes_specs = await evaluer_alertes(scope=scope)

    return {
        "scope": scope,
        "evaluees_le": datetime.utcnow().isoformat(),
        "nb_alertes": len(alertes_specs),
        "par_severite": {
            "critical": sum(1 for a in alertes_specs if a.severite == "critical"),
            "warning":  sum(1 for a in alertes_specs if a.severite == "warning"),
            "info":     sum(1 for a in alertes_specs if a.severite == "info"),
        },
        "alertes": [
            {
                "code": a.code,
                "severite": a.severite,
                "titre": a.titre,
                "message": a.message,
                "valeur": a.valeur,
                "seuil": a.seuil,
                "contexte": a.contexte,
                "detectee_le": a.detectee_le.isoformat(),
            }
            for a in alertes_specs
        ],
    }


@router.get("/thresholds", summary="Seuils d'alerte configurés")
async def thresholds(
    admin: TokenData = Depends(_require_admin),
):
    """Renvoie la configuration des seuils. Pour MVP, lecture seule —
    les modifs passent par variables d'environnement YK_ALERT_*."""
    return {
        "seuils": SEUILS_DEFAUT,
        "configurable_via": "Variables d'env YK_ALERT_* (cf. modules/admin_cross/alerts.py)",
        "providers_connus": list(PROVIDERS_KNOWN),
    }
