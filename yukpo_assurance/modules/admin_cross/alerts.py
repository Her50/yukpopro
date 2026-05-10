"""Système d'alertes admin (MVP — seuils statiques en config).

Les seuils sont définis ici en dur (puis surchargeables via env si besoin
plus tard). À chaque appel /admin-cross/alerts, on évalue les seuils en
agrégeant les tables consommations_* et on retourne la liste des alertes
actives avec leur sévérité.

Pas de notification email/Slack pour le MVP — uniquement affichage dans
le dashboard admin. Pour passer à l'envoi externe : ajouter un job cron
qui appelle evaluer_alertes() et notifie sur les transitions OK→ALERTE.

Catégories d'alertes :
  - cost_daily_feature       : conso > seuil sur une feature en 24h
  - cost_daily_user          : conso > seuil pour un user en 24h
  - cost_daily_global        : conso totale (toutes apps) > seuil/jour
  - cost_provider_share      : un provider dépasse X% du coût total
  - latency_high             : pas implémenté en MVP (manque tracking latence)
  - quota_user_exhausted     : crédits restants user < seuil
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, func, and_

from core.database import (
    async_session_maker,
    ConsommationTokenDB,
    ConsommationBureauDB,
    CreditIAUserDB,
    CreditBureauDB,
    UtilisateurDB,
)
from .providers import classifier_provider


# ─── Spécification d'une alerte ──────────────────────────────────────────────


@dataclass
class AlerteSpec:
    code: str           # ex: "cost_daily_feature"
    severite: str       # info | warning | critical
    titre: str          # libellé court affiché
    message: str        # détail multiline
    valeur: float       # valeur observée
    seuil: float        # seuil franchi
    contexte: dict[str, Any]  # dimensions concernées (user_id, feature, provider…)
    detectee_le: datetime


# ─── Seuils par défaut (FCFA réels Yukpo) ────────────────────────────────────
#
# Ces valeurs reflètent une économie de SaaS B2B africain où le coût IA
# moyen visé par utilisateur actif est ~5k-20k FCFA/mois. Tout dépassement
# au-delà mérite l'attention de l'admin.

SEUILS_DEFAUT = {
    # Conso d'une feature (module) sur 24h, toutes apps confondues
    "cost_daily_feature_warning_fcfa":   int(os.getenv("YK_ALERT_FEATURE_WARN_FCFA",  "30000")),
    "cost_daily_feature_critical_fcfa":  int(os.getenv("YK_ALERT_FEATURE_CRIT_FCFA",  "100000")),
    # Conso d'un seul user sur 24h
    "cost_daily_user_warning_fcfa":      int(os.getenv("YK_ALERT_USER_WARN_FCFA",     "10000")),
    "cost_daily_user_critical_fcfa":     int(os.getenv("YK_ALERT_USER_CRIT_FCFA",     "30000")),
    # Conso globale (Pro + Sec) sur 24h
    "cost_daily_global_warning_fcfa":    int(os.getenv("YK_ALERT_GLOBAL_WARN_FCFA",   "150000")),
    "cost_daily_global_critical_fcfa":   int(os.getenv("YK_ALERT_GLOBAL_CRIT_FCFA",   "500000")),
    # Provider qui prend > X% du coût quotidien
    "cost_provider_share_warning_pct":   float(os.getenv("YK_ALERT_PROVIDER_PCT",     "70.0")),
    # User dont le solde de crédits restants est très bas (alerte business)
    "quota_user_warning_credits":        int(os.getenv("YK_ALERT_QUOTA_WARN",         "300")),
}


# ─── Évaluation des alertes ──────────────────────────────────────────────────


async def _conso_par_feature_24h(scope: str) -> list[dict]:
    """Agrège FCFA dépensés par module sur les dernières 24h, pour le scope."""
    since = datetime.utcnow() - timedelta(hours=24)
    rows: list[dict] = []

    async with async_session_maker() as session:
        if scope in ("pro", "both"):
            r = await session.execute(
                select(
                    ConsommationTokenDB.module,
                    func.coalesce(func.sum(ConsommationTokenDB.cout_fcfa), 0).label("fcfa"),
                ).where(ConsommationTokenDB.cree_le >= since)
                 .group_by(ConsommationTokenDB.module)
            )
            for module, fcfa in r.all():
                rows.append({"app": "pro", "module": module or "unknown", "fcfa": float(fcfa or 0)})

        if scope in ("sec", "both"):
            r = await session.execute(
                select(
                    ConsommationBureauDB.module,
                    func.coalesce(func.sum(ConsommationBureauDB.cout_fcfa), 0).label("fcfa"),
                ).where(ConsommationBureauDB.cree_le >= since)
                 .group_by(ConsommationBureauDB.module)
            )
            for module, fcfa in r.all():
                rows.append({"app": "sec", "module": module or "unknown", "fcfa": float(fcfa or 0)})

    return rows


async def _conso_par_user_24h(scope: str, top_n: int = 50) -> list[dict]:
    since = datetime.utcnow() - timedelta(hours=24)
    rows: list[dict] = []

    async with async_session_maker() as session:
        if scope in ("pro", "both"):
            r = await session.execute(
                select(
                    ConsommationTokenDB.user_id,
                    func.coalesce(func.sum(ConsommationTokenDB.cout_fcfa), 0).label("fcfa"),
                ).where(ConsommationTokenDB.cree_le >= since)
                 .group_by(ConsommationTokenDB.user_id)
                 .order_by(func.sum(ConsommationTokenDB.cout_fcfa).desc())
                 .limit(top_n)
            )
            for uid, fcfa in r.all():
                rows.append({"app": "pro", "user_id": int(uid), "fcfa": float(fcfa or 0)})

        if scope in ("sec", "both"):
            r = await session.execute(
                select(
                    ConsommationBureauDB.user_id,
                    func.coalesce(func.sum(ConsommationBureauDB.cout_fcfa), 0).label("fcfa"),
                ).where(ConsommationBureauDB.cree_le >= since)
                 .group_by(ConsommationBureauDB.user_id)
                 .order_by(func.sum(ConsommationBureauDB.cout_fcfa).desc())
                 .limit(top_n)
            )
            for uid, fcfa in r.all():
                rows.append({"app": "sec", "user_id": int(uid), "fcfa": float(fcfa or 0)})

    return rows


async def _conso_par_provider_24h(scope: str) -> dict[str, float]:
    since = datetime.utcnow() - timedelta(hours=24)
    par_provider: dict[str, float] = {}

    async with async_session_maker() as session:
        if scope in ("pro", "both"):
            r = await session.execute(
                select(ConsommationTokenDB.modele, func.coalesce(func.sum(ConsommationTokenDB.cout_fcfa), 0))
                .where(ConsommationTokenDB.cree_le >= since)
                .group_by(ConsommationTokenDB.modele)
            )
            for modele, fcfa in r.all():
                p = classifier_provider(modele)
                par_provider[p] = par_provider.get(p, 0) + float(fcfa or 0)

        if scope in ("sec", "both"):
            r = await session.execute(
                select(ConsommationBureauDB.modele, func.coalesce(func.sum(ConsommationBureauDB.cout_fcfa), 0))
                .where(ConsommationBureauDB.cree_le >= since)
                .group_by(ConsommationBureauDB.modele)
            )
            for modele, fcfa in r.all():
                p = classifier_provider(modele)
                par_provider[p] = par_provider.get(p, 0) + float(fcfa or 0)

    return par_provider


async def _users_quota_bas() -> list[dict]:
    """Users dont les crédits restants sont sous le seuil d'alerte."""
    seuil = SEUILS_DEFAUT["quota_user_warning_credits"]
    rows: list[dict] = []

    async with async_session_maker() as session:
        # YukpoPro
        r = await session.execute(
            select(CreditIAUserDB.user_id, CreditIAUserDB.credits_alloues, CreditIAUserDB.credits_utilises)
        )
        for uid, alloues, utilises in r.all():
            restants = max(0, int(alloues or 0) - int(utilises or 0))
            if restants < seuil:
                rows.append({"app": "pro", "user_id": int(uid), "credits_restants": restants, "alloues": int(alloues or 0)})

        # YukpoSecrétariat
        r = await session.execute(
            select(CreditBureauDB.user_id, CreditBureauDB.credits_alloues, CreditBureauDB.credits_utilises)
        )
        for uid, alloues, utilises in r.all():
            restants = max(0, int(alloues or 0) - float(utilises or 0))
            if restants < seuil:
                rows.append({"app": "sec", "user_id": int(uid), "credits_restants": int(restants), "alloues": int(alloues or 0)})

    return rows


async def evaluer_alertes(scope: str = "both") -> list[AlerteSpec]:
    """Évalue tous les seuils et retourne la liste des alertes actives.

    scope : 'pro' | 'sec' | 'both'
    """
    if scope not in ("pro", "sec", "both"):
        scope = "both"

    alertes: list[AlerteSpec] = []
    now = datetime.utcnow()

    # ─── 1. Conso par feature 24h ─────────────────────────────────────────
    par_feature = await _conso_par_feature_24h(scope)
    warn_f = SEUILS_DEFAUT["cost_daily_feature_warning_fcfa"]
    crit_f = SEUILS_DEFAUT["cost_daily_feature_critical_fcfa"]

    for row in par_feature:
        fcfa = row["fcfa"]
        if fcfa >= crit_f:
            alertes.append(AlerteSpec(
                code="cost_daily_feature",
                severite="critical",
                titre=f"Feature « {row['module']} » ({row['app']}) : {fcfa:,.0f} FCFA / 24h",
                message=f"La feature « {row['module']} » sur {row['app']} a consommé {fcfa:,.0f} FCFA en 24h, au-delà du seuil critique {crit_f:,.0f} FCFA.",
                valeur=fcfa, seuil=crit_f, contexte={"app": row["app"], "module": row["module"]},
                detectee_le=now,
            ))
        elif fcfa >= warn_f:
            alertes.append(AlerteSpec(
                code="cost_daily_feature",
                severite="warning",
                titre=f"Feature « {row['module']} » ({row['app']}) : {fcfa:,.0f} FCFA / 24h",
                message=f"La feature « {row['module']} » sur {row['app']} a consommé {fcfa:,.0f} FCFA en 24h, au-delà du seuil d'alerte {warn_f:,.0f} FCFA.",
                valeur=fcfa, seuil=warn_f, contexte={"app": row["app"], "module": row["module"]},
                detectee_le=now,
            ))

    # ─── 2. Conso par user 24h ────────────────────────────────────────────
    par_user = await _conso_par_user_24h(scope)
    warn_u = SEUILS_DEFAUT["cost_daily_user_warning_fcfa"]
    crit_u = SEUILS_DEFAUT["cost_daily_user_critical_fcfa"]

    for row in par_user:
        fcfa = row["fcfa"]
        if fcfa >= crit_u:
            alertes.append(AlerteSpec(
                code="cost_daily_user",
                severite="critical",
                titre=f"User #{row['user_id']} ({row['app']}) : {fcfa:,.0f} FCFA / 24h",
                message=f"L'utilisateur #{row['user_id']} sur {row['app']} a consommé {fcfa:,.0f} FCFA en 24h, au-delà du seuil critique {crit_u:,.0f} FCFA. Vérifier l'usage légitime ou abuse potentielle.",
                valeur=fcfa, seuil=crit_u, contexte={"app": row["app"], "user_id": row["user_id"]},
                detectee_le=now,
            ))
        elif fcfa >= warn_u:
            alertes.append(AlerteSpec(
                code="cost_daily_user",
                severite="warning",
                titre=f"User #{row['user_id']} ({row['app']}) : {fcfa:,.0f} FCFA / 24h",
                message=f"L'utilisateur #{row['user_id']} sur {row['app']} a consommé {fcfa:,.0f} FCFA en 24h.",
                valeur=fcfa, seuil=warn_u, contexte={"app": row["app"], "user_id": row["user_id"]},
                detectee_le=now,
            ))

    # ─── 3. Conso globale 24h ─────────────────────────────────────────────
    total_24h = sum(r["fcfa"] for r in par_feature)
    warn_g = SEUILS_DEFAUT["cost_daily_global_warning_fcfa"]
    crit_g = SEUILS_DEFAUT["cost_daily_global_critical_fcfa"]
    if total_24h >= crit_g:
        alertes.append(AlerteSpec(
            code="cost_daily_global", severite="critical",
            titre=f"Conso globale 24h : {total_24h:,.0f} FCFA",
            message=f"La consommation totale (scope={scope}) atteint {total_24h:,.0f} FCFA sur 24h, au-delà du seuil critique {crit_g:,.0f} FCFA. Investiguer immédiatement.",
            valeur=total_24h, seuil=crit_g, contexte={"scope": scope},
            detectee_le=now,
        ))
    elif total_24h >= warn_g:
        alertes.append(AlerteSpec(
            code="cost_daily_global", severite="warning",
            titre=f"Conso globale 24h : {total_24h:,.0f} FCFA",
            message=f"La consommation totale (scope={scope}) atteint {total_24h:,.0f} FCFA sur 24h.",
            valeur=total_24h, seuil=warn_g, contexte={"scope": scope},
            detectee_le=now,
        ))

    # ─── 4. Concentration sur un provider ─────────────────────────────────
    par_provider = await _conso_par_provider_24h(scope)
    total_provider = sum(par_provider.values())
    pct_seuil = SEUILS_DEFAUT["cost_provider_share_warning_pct"]
    if total_provider > 0:
        for provider, fcfa in par_provider.items():
            pct = (fcfa / total_provider) * 100
            if pct >= pct_seuil and provider not in ("unknown", "local"):
                alertes.append(AlerteSpec(
                    code="cost_provider_share", severite="warning",
                    titre=f"Provider « {provider} » : {pct:.1f}% du coût 24h",
                    message=f"Le fournisseur {provider} concentre {pct:.1f}% du coût IA des dernières 24h ({fcfa:,.0f}/{total_provider:,.0f} FCFA). Risque de dépendance — vérifier la diversification.",
                    valeur=pct, seuil=pct_seuil, contexte={"provider": provider, "fcfa": fcfa, "total": total_provider},
                    detectee_le=now,
                ))

    # ─── 5. Users à quota presque épuisé ──────────────────────────────────
    if scope in ("both",):
        # Cette alerte n'a de sens qu'en vue cross-app — on skip si scope filtré
        users_bas = await _users_quota_bas()
        for u in users_bas[:20]:  # plafonner pour ne pas spammer
            alertes.append(AlerteSpec(
                code="quota_user_exhausted", severite="info",
                titre=f"User #{u['user_id']} ({u['app']}) : crédits bas ({u['credits_restants']})",
                message=f"L'utilisateur #{u['user_id']} sur {u['app']} a {u['credits_restants']} crédits restants sur {u['alloues']}. Opportunité commerciale (relance recharge).",
                valeur=u["credits_restants"], seuil=SEUILS_DEFAUT["quota_user_warning_credits"],
                contexte={"app": u["app"], "user_id": u["user_id"], "alloues": u["alloues"]},
                detectee_le=now,
            ))

    # Tri : critical d'abord, puis warning, puis info
    ordre = {"critical": 0, "warning": 1, "info": 2}
    alertes.sort(key=lambda a: (ordre.get(a.severite, 99), -a.valeur))

    return alertes
