"""Phase D7 — Analytics pub unifiées (ROAS cross-canal).

Récupère les métriques pub de Facebook Ads, Google Ads, TikTok Ads,
Snapchat Ads ; croise avec les commandes Yukpo via UTM/fbclid/gclid ;
calcule le ROAS par campagne et émet des recommandations IA.

Pour MVP : implémentation FB Ads (le plus utilisé en Afrique francophone).
Google/TikTok/Snap = même pattern, à ajouter au fil de l'eau.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

logger = logging.getLogger("yukpo_assurance.pro.shop_ads")


_META_GRAPH = "https://graph.facebook.com/v19.0"


async def recuperer_metriques_fb_ads(
    ad_account_id: str, access_token: str, *, jours: int = 30,
) -> list[dict]:
    """Récupère les insights FB Ads des N derniers jours, agrégés par campagne+jour.

    Returns: list de dicts {campagne_id, campagne_nom, jour, depenses, impressions,
    clics, conversions_externes, devise}.
    """
    since = (datetime.utcnow().date() - timedelta(days=jours)).isoformat()
    until = datetime.utcnow().date().isoformat()

    url = f"{_META_GRAPH}/act_{ad_account_id}/insights"
    params = {
        "access_token": access_token,
        "level": "campaign",
        "time_increment": 1,  # jour par jour
        "time_range": json.dumps({"since": since, "until": until}),
        "fields": "campaign_id,campaign_name,spend,impressions,clicks,actions,date_start",
        "limit": 500,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        rep = await client.get(url, params=params)
        if rep.status_code >= 300:
            logger.warning(f"[FB Ads/insights] erreur {rep.status_code}: {rep.text[:200]}")
            return []
        data = rep.json().get("data", [])

    out = []
    for row in data:
        conversions = 0
        for action in row.get("actions", []):
            if action.get("action_type") in (
                "purchase", "omni_purchase", "offsite_conversion.fb_pixel_purchase",
            ):
                try:
                    conversions += int(float(action.get("value", 0)))
                except Exception:
                    pass
        out.append({
            "platform": "fb_ads",
            "campagne_id": row.get("campaign_id"),
            "campagne_nom": row.get("campaign_name"),
            "jour": row.get("date_start"),
            "depenses": float(row.get("spend") or 0),
            "impressions": int(row.get("impressions") or 0),
            "clics": int(row.get("clicks") or 0),
            "conversions_externes": conversions,
            "devise": "XAF",  # à enrichir depuis ad_account_info
        })
    return out


async def croiser_avec_commandes(
    boutique_id: int, metriques: list[dict], db,
) -> list[dict]:
    """Pour chaque métrique campagne/jour, matche les commandes locales
    via UTM source/campaign + fbclid (stocké dans utm_source). Calcule
    conversions_locales + revenu_local.
    """
    from sqlalchemy import and_, func, select
    from core.database import ShopOrderDB

    for m in metriques:
        # Match basique : utm_campaign == campagne_nom OU campagne_id
        jour = m["jour"]
        jour_dt = datetime.fromisoformat(jour) if isinstance(jour, str) else jour
        deb = datetime.combine(jour_dt, datetime.min.time()) if hasattr(jour_dt, "date") else jour_dt
        fin = deb + timedelta(days=1)

        q = (
            select(
                func.count(ShopOrderDB.id).label("nb"),
                func.sum(ShopOrderDB.montant_total).label("revenu"),
            )
            .where(ShopOrderDB.boutique_id == boutique_id)
            .where(ShopOrderDB.cree_le >= deb)
            .where(ShopOrderDB.cree_le < fin)
            .where(ShopOrderDB.statut.in_(["payee", "expediee", "livree"]))
        )
        # Filtre UTM si campagne identifiable
        if m.get("campagne_nom"):
            q = q.where(
                (ShopOrderDB.utm_campaign == m["campagne_nom"])
                | (ShopOrderDB.utm_campaign == m["campagne_id"])
            )
        else:
            q = q.where(ShopOrderDB.utm_campaign == m.get("campagne_id"))

        res = (await db.execute(q)).one()
        m["conversions_locales"] = int(res.nb or 0)
        m["revenu_local"] = float(res.revenu or 0)

    return metriques


def calculer_roas(metriques: list[dict]) -> dict:
    """Agrège ROAS par campagne et global.

    Returns: {
      par_campagne: [{campagne_id, nom, depenses, revenu, roas, conversions, …}],
      global: {depenses, revenu, roas, conversions, ...},
      meilleur_roas: {...}, pire_roas: {...},
    }
    """
    par_campagne: dict[str, dict] = {}
    for m in metriques:
        cid = m.get("campagne_id")
        if cid not in par_campagne:
            par_campagne[cid] = {
                "campagne_id": cid,
                "campagne_nom": m.get("campagne_nom", "(sans nom)"),
                "depenses": 0.0, "impressions": 0, "clics": 0,
                "conversions_externes": 0, "conversions_locales": 0,
                "revenu_local": 0.0,
            }
        c = par_campagne[cid]
        c["depenses"] += float(m.get("depenses") or 0)
        c["impressions"] += int(m.get("impressions") or 0)
        c["clics"] += int(m.get("clics") or 0)
        c["conversions_externes"] += int(m.get("conversions_externes") or 0)
        c["conversions_locales"] += int(m.get("conversions_locales") or 0)
        c["revenu_local"] += float(m.get("revenu_local") or 0)

    for c in par_campagne.values():
        c["roas"] = round(c["revenu_local"] / c["depenses"], 2) if c["depenses"] > 0 else None
        c["cpa"] = (
            round(c["depenses"] / c["conversions_locales"], 2)
            if c["conversions_locales"] > 0 else None
        )
        c["ctr_pct"] = (
            round(100 * c["clics"] / c["impressions"], 2)
            if c["impressions"] > 0 else 0
        )

    campagnes = list(par_campagne.values())
    total_dep = sum(c["depenses"] for c in campagnes)
    total_rev = sum(c["revenu_local"] for c in campagnes)
    total_conv = sum(c["conversions_locales"] for c in campagnes)
    roas_global = round(total_rev / total_dep, 2) if total_dep > 0 else None

    # Sort + meilleur/pire (uniquement les campagnes avec dépense réelle)
    campagnes_avec_dep = [c for c in campagnes if c["depenses"] > 50]
    campagnes_avec_dep.sort(key=lambda x: x.get("roas") or -1, reverse=True)
    meilleur = campagnes_avec_dep[0] if campagnes_avec_dep else None
    pire = campagnes_avec_dep[-1] if len(campagnes_avec_dep) >= 2 else None

    return {
        "par_campagne": campagnes,
        "global": {
            "depenses": round(total_dep, 2),
            "revenu_local": round(total_rev, 2),
            "roas": roas_global,
            "conversions_locales": total_conv,
            "nb_campagnes": len(campagnes),
        },
        "meilleur_roas": meilleur, "pire_roas": pire,
    }


async def generer_recommandations_ia(roas_data: dict) -> str:
    """LLM Opus → recommandations actionnables (markdown) sur le ROAS."""
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire

    contexte = json.dumps(roas_data, ensure_ascii=False, default=str)[:6000]
    prompt = (
        f"Analyse ces données ROAS d'un marchand africain francophone et "
        f"propose 4-6 recommandations CONCRÈTES (markdown) :\n\n"
        f"DONNÉES :\n{contexte}\n\n"
        f"Structure :\n"
        f"- 1-2 reco budget (augmenter X, couper Y avec ROAS chiffré)\n"
        f"- 1-2 reco audience (élargir, lookalike, retargeting)\n"
        f"- 1-2 reco créa (visuels, CTAs)\n"
        f"Ne PAS inventer de chiffres. Cite ROAS et dépenses réels."
    )
    rep = await ia_client.appeler(
        prompt=prompt,
        systeme="Tu es un media buyer senior expert FB/Google Ads marché africain.",
        mode=ModeIA.ANALYSE,
        max_tokens_override=2500,
        forcer_modele=ModelePrioritaire.CLAUDE_OPUS,
    )
    return (rep.contenu or "").strip()
