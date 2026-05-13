"""Phase D8 — CRM client + scoring churn IA + relances automatiques.

Pipeline :
  1. Agrège un profil 360° pour chaque client final (telephone+email
     comme natural key) à partir de shop_orders + shop_client_events.
  2. LLM Sonnet/GPT-5-mini score % churn + segment + recommandations
     personnalisées (cross-sell, relance produit favori).
  3. Celery task daily relance les paniers abandonnés (J+1, J+3, J+7)
     via WhatsApp + SMS (réutilise core.notifications.notifier_telephone).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger("yukpo_assurance.pro.crm")


async def aggreger_clients_boutique(boutique_id: int, db) -> int:
    """Recalcule le profil 360° de tous les clients de la boutique.

    Lit shop_orders, regroupe par (telephone OU email) et crée/met à
    jour les shop_clients. Returns nb_clients_traites.
    """
    from sqlalchemy import desc, func, select
    from core.database import ShopClientDB, ShopOrderDB

    # Récupère toutes les commandes payées/expédiées/livrées (qui ont apporté
    # du revenu) groupées par client
    rows = (await db.execute(
        select(
            ShopOrderDB.client_telephone, ShopOrderDB.client_email,
            ShopOrderDB.client_nom,
            func.min(ShopOrderDB.cree_le).label("premiere"),
            func.max(ShopOrderDB.cree_le).label("derniere"),
            func.count(ShopOrderDB.id).label("nb"),
            func.sum(ShopOrderDB.montant_total).label("revenu"),
        )
        .where(ShopOrderDB.boutique_id == boutique_id)
        .where(ShopOrderDB.statut.in_(["payee", "expediee", "livree"]))
        .group_by(
            ShopOrderDB.client_telephone,
            ShopOrderDB.client_email,
            ShopOrderDB.client_nom,
        )
    )).all()

    nb_traites = 0
    for row in rows:
        tel = row.client_telephone
        email = row.client_email
        if not tel and not email:
            continue
        existant = None
        if tel:
            existant = (await db.execute(
                select(ShopClientDB)
                .where(ShopClientDB.boutique_id == boutique_id)
                .where(ShopClientDB.telephone == tel)
            )).scalar_one_or_none()
        if not existant and email:
            existant = (await db.execute(
                select(ShopClientDB)
                .where(ShopClientDB.boutique_id == boutique_id)
                .where(ShopClientDB.email == email)
            )).scalar_one_or_none()
        if not existant:
            existant = ShopClientDB(
                boutique_id=boutique_id, telephone=tel,
                email=email, nom=row.client_nom,
            )
            db.add(existant)

        existant.telephone = tel or existant.telephone
        existant.email = email or existant.email
        existant.nom = row.client_nom or existant.nom
        existant.premiere_commande_le = row.premiere
        existant.derniere_commande_le = row.derniere
        existant.nb_commandes = int(row.nb or 0)
        existant.revenu_total = float(row.revenu or 0)
        existant.modif_le = datetime.utcnow()
        nb_traites += 1

    await db.commit()
    return nb_traites


def _calculer_segment_simple(client: dict) -> str:
    """Segmentation rule-based (avant scoring IA) — fallback rapide.

      vip       : nb_commandes ≥ 5 et derniere < 60j
      recurrent : nb_commandes ≥ 2 et derniere < 90j
      new       : nb_commandes = 1 et premiere < 30j
      dormant   : nb_commandes ≥ 1 et derniere > 180j
      risque    : nb_commandes ≥ 2 et 90 < derniere < 180j
    """
    nb = client.get("nb_commandes", 0)
    derniere = client.get("derniere_commande_le")
    premiere = client.get("premiere_commande_le")
    now = datetime.utcnow()
    if not derniere:
        return "new"
    jours_depuis_derniere = (now - derniere).days if isinstance(derniere, datetime) else 999

    if nb >= 5 and jours_depuis_derniere < 60:
        return "vip"
    if nb >= 2 and jours_depuis_derniere < 90:
        return "recurrent"
    if nb == 1 and premiere and (now - premiere).days < 30:
        return "new"
    if jours_depuis_derniere > 180:
        return "dormant"
    if nb >= 2 and 90 <= jours_depuis_derniere <= 180:
        return "risque"
    return "new"


async def scorer_churn_ia(client: dict) -> dict:
    """LLM compose un score churn % + segment + 2-4 recos cross-sell.

    Returns: {score_churn_pct, segment, ltv_predite, recos: [...]}.
    """
    from core.ia_client import ia_client, ModeIA, ModelePrioritaire

    prompt = (
        f"Analyse ce profil client e-commerce et renvoie un JSON :\n"
        f"{{\"score_churn_pct\": 0-100, "
        f"\"segment\": \"vip|recurrent|dormant|risque|new\", "
        f"\"ltv_predite\": montant_estime, "
        f"\"recos\": [{{\"type\": \"relance|cross_sell|upgrade\", "
        f"\"message\": \"texte court WA <500 chars\"}}, ...]}}\n\n"
        f"PROFIL :\n{json.dumps(client, ensure_ascii=False, default=str)[:2000]}"
    )
    rep = await ia_client.appeler(
        prompt=prompt,
        systeme="Tu es un data scientist CRM expert e-commerce africain. "
                "Sois pragmatique, pas de jargon. JSON strict, rien d'autre.",
        mode=ModeIA.ANALYSE,
        max_tokens_override=1500,
        json_attendu=True,
        forcer_modele=ModelePrioritaire.CLAUDE_SONNET,
    )
    import re
    texte = (rep.contenu or "").strip()
    m = re.search(r"\{[\s\S]*\}", texte)
    if not m:
        # Fallback rule-based
        return {
            "score_churn_pct": 50,
            "segment": _calculer_segment_simple(client),
            "ltv_predite": None,
            "recos": [],
        }
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {
            "score_churn_pct": 50,
            "segment": _calculer_segment_simple(client),
            "recos": [],
        }


async def scorer_tous_clients_boutique(
    boutique_id: int, db, *, limit_par_run: int = 100,
) -> int:
    """Score les N clients les plus anciennement analysés.

    Returns nb_scored.
    """
    from sqlalchemy import asc, select
    from core.database import ShopClientDB

    # Priorité : clients jamais scorés OU scoré il y a > 7j
    q = (
        select(ShopClientDB)
        .where(ShopClientDB.boutique_id == boutique_id)
        .order_by(asc(ShopClientDB.derniere_analyse_le.is_(None)),
                  asc(ShopClientDB.derniere_analyse_le))
        .limit(limit_par_run)
    )
    clients = (await db.execute(q)).scalars().all()
    nb = 0
    for c in clients:
        client_dict = {
            "telephone": c.telephone, "email": c.email,
            "nom": c.nom, "ville": c.ville,
            "nb_commandes": c.nb_commandes,
            "revenu_total": float(c.revenu_total or 0),
            "premiere_commande_le": c.premiere_commande_le,
            "derniere_commande_le": c.derniere_commande_le,
            "source_acquisition": c.source_acquisition,
        }
        try:
            scoring = await scorer_churn_ia(client_dict)
            c.score_churn_pct = int(scoring.get("score_churn_pct") or 50)
            c.segment = scoring.get("segment") or _calculer_segment_simple(client_dict)
            c.ltv_predite = scoring.get("ltv_predite")
            c.recos_ia_json = scoring.get("recos") or []
            c.derniere_analyse_le = datetime.utcnow()
            nb += 1
        except Exception as e:
            logger.warning(f"[CRM/score] client={c.id} échec : {e}")
    await db.commit()
    return nb


async def relancer_client_wa(
    client, marchand_user_id: int, message: str,
) -> bool:
    """Envoi WA prioritaire + SMS fallback (réutilise Phase A)."""
    if not client.telephone:
        return False
    try:
        from core.notifications import notifier_telephone
        from modules.bureau.service_credits_bureau import debiter_forfait_unifie
        res = await notifier_telephone(
            client.telephone, message,
            metadata={"type": "crm_relance", "client_id": client.id},
            prefer="whatsapp",
        )
        if res["canal_final"] != "none":
            await debiter_forfait_unifie(
                marchand_user_id, "whatsapp_message", module="crm_relance",
            )
            return True
    except Exception as e:
        logger.warning(f"[CRM/relance] échec : {e}")
    return False
