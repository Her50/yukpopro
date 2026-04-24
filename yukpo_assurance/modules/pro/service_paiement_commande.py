"""
Service des commandes de paiement MoMo — activation provisoire + validation admin.

Référence unique : YYMMDD-NNN-TEL4
  - YYMMDD : date du jour (UTC)
  - NNN    : incrément journalier (001-999)
  - TEL4   : 4 derniers chiffres du numéro expéditeur

Flow :
  1. POST /paiement/initier        → crée commande (statut=attente, deadline=+3h)
  2. POST /paiement/confirmer       → user saisit son n° expéditeur + tx_id optionnel
                                      → passage en "provisoire" + activation immédiate
  3. Admin valide / rejette / upload relevé auto-match
  4. CRON /paiement/cron/auto-annulation : statut provisoire > deadline → annulation
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import CommandePaiementDB

logger = logging.getLogger("yukpo_assurance.pro.paiement_commande")

DELAI_DEADLINE_HEURES = 3
ADMIN_ROLES = ("admin", "super_admin", "yukpo_owner")

# Flag : paiement direct via API opérateur (CinetPay / MTN MoMo / Orange Money).
# Tant que les API ne sont pas intégrées, fallback automatique sur le flow manuel
# (commande provisoire + validation admin). Activer via env var PAIEMENT_DIRECT_ENABLED=1.
import os
PAIEMENT_DIRECT_ENABLED = os.getenv("PAIEMENT_DIRECT_ENABLED", "0") == "1"


async def paiement_direct_disponible(operateur: str) -> bool:
    """Retourne True si l'opérateur a une API directe configurée et opérationnelle."""
    if not PAIEMENT_DIRECT_ENABLED:
        return False
    # TODO: brancher CinetPay / NotchPay / API directes quand disponibles.
    return False


# ── Génération de référence ──────────────────────────────────────────────────

async def generer_reference(tel_expediteur: Optional[str], db: AsyncSession) -> str:
    """Génère une référence unique YYMMDD-NNN-TEL4."""
    now = datetime.utcnow()
    prefix = now.strftime("%y%m%d")
    # Compte les commandes du jour
    debut_jour = datetime(now.year, now.month, now.day)
    stmt = select(func.count(CommandePaiementDB.id)).where(
        CommandePaiementDB.cree_le >= debut_jour
    )
    count = (await db.execute(stmt)).scalar() or 0
    numero = f"{(count + 1):03d}"
    tel4 = _extraire_tel4(tel_expediteur) if tel_expediteur else "0000"
    return f"{prefix}-{numero}-{tel4}"


def _extraire_tel4(tel: Optional[str]) -> str:
    if not tel:
        return "0000"
    digits = re.sub(r"\D", "", tel)
    return digits[-4:].zfill(4) if digits else "0000"


# ── Création commande ────────────────────────────────────────────────────────

async def creer_commande(
    user_id: int,
    type_cmd: str,                  # "abonnement" | "recharge"
    plan_ou_pack: str,
    montant_fcfa: int,
    operateur: Optional[str],
    numero_destinataire: Optional[str],
    db: AsyncSession,
) -> CommandePaiementDB:
    """Crée une commande en statut 'attente' avec référence unique et deadline."""
    reference = await generer_reference(None, db)
    cmd = CommandePaiementDB(
        user_id=user_id,
        reference=reference,
        type=type_cmd,
        plan_ou_pack=plan_ou_pack,
        montant_fcfa=montant_fcfa,
        operateur=operateur,
        numero_destinataire=numero_destinataire,
        statut="attente",
        cree_le=datetime.utcnow(),
        deadline=datetime.utcnow() + timedelta(hours=DELAI_DEADLINE_HEURES),
    )
    db.add(cmd)
    await db.commit()
    await db.refresh(cmd)
    logger.info(f"[Paiement] Commande créée ref={reference} user={user_id} type={type_cmd}")
    return cmd


async def confirmer_commande(
    user_id: int,
    reference: str,
    numero_expediteur: str,
    tx_id: Optional[str],
    db: AsyncSession,
) -> CommandePaiementDB:
    """L'utilisateur confirme avoir payé → activation provisoire immédiate."""
    stmt = select(CommandePaiementDB).where(
        and_(
            CommandePaiementDB.reference == reference,
            CommandePaiementDB.user_id == user_id,
        )
    )
    cmd = (await db.execute(stmt)).scalar_one_or_none()
    if not cmd:
        raise ValueError("Référence introuvable")
    if cmd.statut not in ("attente", "provisoire"):
        raise ValueError(f"Commande déjà {cmd.statut}")

    # Mise à jour de la référence avec TEL4 correct si première confirmation
    tel4 = _extraire_tel4(numero_expediteur)
    if cmd.reference.endswith("-0000") and tel4 != "0000":
        nouvelle_ref = cmd.reference[:-4] + tel4
        cmd.reference = nouvelle_ref

    cmd.numero_expediteur = numero_expediteur
    cmd.tx_id = tx_id
    cmd.statut = "provisoire"
    # deadline: 3h à partir de la confirmation utilisateur
    cmd.deadline = datetime.utcnow() + timedelta(hours=DELAI_DEADLINE_HEURES)
    await db.commit()
    await db.refresh(cmd)

    # Activation provisoire immédiate
    await _activer_commande(cmd, db, source="provisoire")
    logger.info(f"[Paiement] Provisoire activé ref={cmd.reference} user={user_id}")
    return cmd


# ── Activation effective (abonnement ou recharge) ────────────────────────────

async def _activer_commande(cmd: CommandePaiementDB, db: AsyncSession, source: str) -> None:
    """Applique l'effet de la commande (abonnement ou crédits)."""
    from modules.pro.service_profil import get_or_create
    from modules.pro.service_credits import synchroniser_plan, get_ou_creer_credits

    profil, _ = await get_or_create(cmd.user_id, db)
    prefs = dict(profil.preferences or {})

    if cmd.type == "abonnement":
        date_debut = datetime.utcnow()
        date_fin = date_debut + timedelta(days=30)
        prefs["plan"] = cmd.plan_ou_pack
        prefs["abonnement_debut"] = date_debut.isoformat()
        prefs["abonnement_fin"] = date_fin.isoformat()
        prefs["derniere_reference"] = cmd.reference
        prefs["abonnement_statut"] = "provisoire" if source == "provisoire" else "actif"
        profil.preferences = prefs
        await db.commit()
        try:
            await synchroniser_plan(cmd.user_id, cmd.plan_ou_pack, db)
        except Exception as e:
            logger.warning(f"[Paiement] sync crédits échoué: {e}")
    elif cmd.type == "recharge":
        from core.database import async_session_maker
        # pack_500 → 500 crédits
        credits_map = {"pack_500": 500, "pack_2000": 2000, "pack_5000": 5000, "pack_15000": 15000}
        credits_ajout = credits_map.get(cmd.plan_ou_pack, 0)
        async with async_session_maker() as fresh_db:
            credit = await get_ou_creer_credits(cmd.user_id, fresh_db)
            credit.credits_alloues += credits_ajout
            credit.mise_a_jour = datetime.utcnow()
            await fresh_db.commit()
        historique = prefs.get("historique_recharges", [])
        historique.insert(0, {
            "reference": cmd.reference,
            "pack": cmd.plan_ou_pack,
            "credits": credits_ajout,
            "montant": cmd.montant_fcfa,
            "date": datetime.utcnow().strftime("%d/%m/%Y %H:%M"),
            "statut": "provisoire" if source == "provisoire" else "valide",
        })
        prefs["historique_recharges"] = historique[:20]
        profil.preferences = prefs
        await db.commit()


async def _annuler_commande(cmd: CommandePaiementDB, db: AsyncSession) -> None:
    """Rollback : retire l'abonnement ou les crédits accordés provisoirement."""
    from modules.pro.service_profil import get_or_create
    from modules.pro.service_credits import get_ou_creer_credits, synchroniser_plan

    profil, _ = await get_or_create(cmd.user_id, db)
    prefs = dict(profil.preferences or {})

    if cmd.type == "abonnement":
        if prefs.get("derniere_reference") == cmd.reference:
            prefs["plan"] = "gratuit"
            prefs["abonnement_fin"] = datetime.utcnow().isoformat()
            prefs["abonnement_statut"] = "annule"
            profil.preferences = prefs
            await db.commit()
            try:
                await synchroniser_plan(cmd.user_id, "gratuit", db)
            except Exception:
                pass
    elif cmd.type == "recharge":
        credits_map = {"pack_500": 500, "pack_2000": 2000, "pack_5000": 5000, "pack_15000": 15000}
        credits_retrait = credits_map.get(cmd.plan_ou_pack, 0)
        from core.database import async_session_maker
        async with async_session_maker() as fresh_db:
            credit = await get_ou_creer_credits(cmd.user_id, fresh_db)
            credit.credits_alloues = max(0, credit.credits_alloues - credits_retrait)
            credit.mise_a_jour = datetime.utcnow()
            await fresh_db.commit()


# ── Validation admin ─────────────────────────────────────────────────────────

async def valider_commande(
    commande_id: int,
    admin_id: int,
    source: str,
    db: AsyncSession,
    tx_id: Optional[str] = None,
) -> CommandePaiementDB:
    cmd = await db.get(CommandePaiementDB, commande_id)
    if not cmd:
        raise ValueError("Commande introuvable")
    if cmd.statut == "valide":
        return cmd
    cmd.statut = "valide"
    cmd.valide_par = admin_id
    cmd.valide_le = datetime.utcnow()
    cmd.match_source = source
    if tx_id and not cmd.tx_id:
        cmd.tx_id = tx_id
    # Confirmer l'abonnement (passage provisoire → actif)
    from modules.pro.service_profil import get_or_create
    profil, _ = await get_or_create(cmd.user_id, db)
    prefs = dict(profil.preferences or {})
    if cmd.type == "abonnement":
        prefs["abonnement_statut"] = "actif"
    profil.preferences = prefs
    await db.commit()
    await db.refresh(cmd)
    logger.info(f"[Paiement] Validé ref={cmd.reference} par admin={admin_id} source={source}")
    return cmd


async def rejeter_commande(
    commande_id: int,
    admin_id: int,
    motif: str,
    db: AsyncSession,
) -> CommandePaiementDB:
    cmd = await db.get(CommandePaiementDB, commande_id)
    if not cmd:
        raise ValueError("Commande introuvable")
    if cmd.statut == "valide":
        raise ValueError("Impossible de rejeter une commande déjà validée")
    await _annuler_commande(cmd, db)
    cmd.statut = "rejete"
    cmd.motif_rejet = motif[:300]
    cmd.valide_par = admin_id
    cmd.valide_le = datetime.utcnow()
    await db.commit()
    await db.refresh(cmd)
    logger.info(f"[Paiement] Rejeté ref={cmd.reference} par admin={admin_id} motif={motif}")
    return cmd


# ── Auto-annulation (cron) ───────────────────────────────────────────────────

async def annuler_commandes_expirees(db: AsyncSession) -> int:
    """Annule toutes les commandes provisoires dont la deadline est dépassée."""
    stmt = select(CommandePaiementDB).where(
        and_(
            CommandePaiementDB.statut.in_(("attente", "provisoire")),
            CommandePaiementDB.deadline < datetime.utcnow(),
        )
    )
    commandes = (await db.execute(stmt)).scalars().all()
    n = 0
    for cmd in commandes:
        await _annuler_commande(cmd, db)
        cmd.statut = "annule"
        cmd.motif_rejet = "Paiement non validé dans le délai de 3h"
        cmd.match_source = "cron"
        cmd.valide_le = datetime.utcnow()
        await db.commit()
        n += 1
    if n:
        logger.info(f"[Paiement] CRON auto-annulation: {n} commande(s)")
    return n


# ── Auto-match depuis relevé parsé par IA ───────────────────────────────────

async def auto_match_releve(
    paiements_extraits: list[dict],  # [{"tel": ..., "montant": ..., "tx_id": ..., "date": ...}, ...]
    admin_id: int,
    db: AsyncSession,
) -> dict:
    """
    Tente de matcher chaque ligne de relevé avec une commande provisoire.
    Match = (montant == cmd.montant_fcfa) AND (4 derniers digits du tel matchent).
    """
    stmt = select(CommandePaiementDB).where(
        CommandePaiementDB.statut.in_(("attente", "provisoire"))
    )
    commandes = (await db.execute(stmt)).scalars().all()

    matches = []
    non_matches = []
    for ligne in paiements_extraits:
        tel_ligne = _extraire_tel4(ligne.get("tel", ""))
        montant_ligne = int(ligne.get("montant", 0) or 0)
        cible = None
        for cmd in commandes:
            if cmd.statut == "valide":
                continue
            if cmd.montant_fcfa != montant_ligne:
                continue
            tel_cmd = _extraire_tel4(cmd.numero_expediteur)
            if tel_cmd == tel_ligne and tel_ligne != "0000":
                cible = cmd
                break
        if cible:
            await valider_commande(
                cible.id,
                admin_id=admin_id,
                source="releve_ia",
                db=db,
                tx_id=ligne.get("tx_id"),
            )
            matches.append({"reference": cible.reference, "montant": montant_ligne, "tel": tel_ligne})
        else:
            non_matches.append(ligne)
    return {"matches": matches, "non_matches": non_matches, "total_lignes": len(paiements_extraits)}
