"""
ServiceProfilPro — CRUD pour les profils professionnels.

Fonctions :
  - get_profil(user_id, db)        → ProfilProfessionnelDB | None
  - get_or_create(user_id, db)     → (ProfilProfessionnelDB, created: bool)
  - creer_profil(user_id, data, db)
  - mettre_a_jour(user_id, data, db)
  - incrementer_stat(user_id, stat_key, db)
  - ajouter_memoire(user_id, fait, db)
  - ajouter_badge(user_id, badge, db)
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.pro.profil_pro import ProfilProfessionnelDB

logger = logging.getLogger("yukpo_assurance.pro.service_profil")


# ── Seuils XP pour la progression ─────────────────────────────────────────────
_SEUILS_XP = {
    "debutant":   0,
    "initie":     100,
    "confirme":   500,
    "expert":     1500,
    "maitre":     5000,
}

# ── Badges automatiques (stat_key → badge) ────────────────────────────────────
_BADGES_AUTO: list[tuple[str, int, str]] = [
    ("nb_requetes_agent",   1,    "premier_pas"),
    ("nb_requetes_agent",   50,   "utilisateur_actif"),
    ("nb_requetes_agent",   200,  "power_user"),
    ("nb_rapports",         1,    "premier_rapport"),
    ("nb_rapports",         10,   "redacteur_pro"),
    ("nb_slides",           1,    "premiere_presentation"),
    ("nb_analyses_data",    1,    "data_explorer"),
    ("nb_requetes_rag",     10,   "chercheur_reglementaire"),
    ("nb_requetes_rag",     100,  "expert_reglementaire"),
]


async def get_profil(user_id: int, db: AsyncSession) -> Optional[ProfilProfessionnelDB]:
    """Récupère le profil d'un utilisateur, ou None s'il n'existe pas."""
    result = await db.execute(
        select(ProfilProfessionnelDB).where(ProfilProfessionnelDB.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_or_create(
    user_id: int,
    db: AsyncSession,
    defaults: Optional[dict] = None,
) -> tuple[ProfilProfessionnelDB, bool]:
    """
    Récupère le profil existant ou en crée un avec des valeurs par défaut.
    Retourne (profil, created: bool).
    """
    profil = await get_profil(user_id, db)
    if profil:
        return profil, False

    data = defaults or {}
    profil = ProfilProfessionnelDB(
        user_id=user_id,
        metier=data.get("metier", "professionnel"),
        pays=data.get("pays", "CM"),
        secteur=data.get("secteur", "prive"),
        niveau=data.get("niveau", "senior"),
        stats_usage={},
        badges=[],
        memoire_agent=[],
        contexte_metier={},
        preferences={},
    )
    db.add(profil)
    await db.commit()
    await db.refresh(profil)
    logger.info(f"[ServiceProfil] Profil créé pour user={user_id} métier={profil.metier}")
    return profil, True


async def creer_profil(
    user_id: int,
    data: dict,
    db: AsyncSession,
) -> ProfilProfessionnelDB:
    """
    Crée un nouveau profil professionnel.
    Lève une ValueError si un profil existe déjà pour cet utilisateur.
    """
    existant = await get_profil(user_id, db)
    if existant:
        raise ValueError(f"Un profil existe déjà pour user_id={user_id}")

    profil = ProfilProfessionnelDB(
        user_id=user_id,
        metier=data.get("metier", "professionnel"),
        specialite=data.get("specialite"),
        pays=data.get("pays", "CM"),
        zone=data.get("zone"),
        secteur=data.get("secteur", "prive"),
        niveau=data.get("niveau", "senior"),
        entreprise=data.get("entreprise"),
        taille_entreprise=data.get("taille_entreprise"),
        secteur_activite=data.get("secteur_activite"),
        langue_reponse=data.get("langue_reponse", "fr"),
        style_reponse=data.get("style_reponse", "professionnel"),
        format_prefere=data.get("format_prefere", "standard"),
        preferences=data.get("preferences", {}),
        contexte_metier=data.get("contexte_metier", {}),
        stats_usage={},
        badges=[],
        memoire_agent=[],
        abonnement=data.get("abonnement", "freemium"),
    )
    db.add(profil)
    await db.commit()
    await db.refresh(profil)
    logger.info(f"[ServiceProfil] Profil créé : user={user_id} métier={profil.metier} pays={profil.pays}")
    return profil


async def mettre_a_jour(
    user_id: int,
    data: dict,
    db: AsyncSession,
) -> ProfilProfessionnelDB:
    """
    Met à jour les champs d'un profil.
    Seuls les champs présents dans `data` sont modifiés (PATCH sémantique).
    """
    profil = await get_profil(user_id, db)
    if not profil:
        raise ValueError(f"Profil introuvable pour user_id={user_id}")

    # Champs éditables directement
    _champs_directs = [
        "metier", "specialite", "pays", "zone", "secteur", "niveau",
        "entreprise", "taille_entreprise", "secteur_activite",
        "langue_reponse", "style_reponse", "format_prefere", "abonnement",
    ]
    for champ in _champs_directs:
        if champ in data:
            setattr(profil, champ, data[champ])

    # JSON : merge au lieu de remplacer
    prefs = profil.preferences or {}
    if "bio" in data:
        prefs["bio"] = data["bio"]
    if "annees_experience" in data:
        prefs["annees_experience"] = data["annees_experience"]
    if "preferences" in data:
        prefs.update(data["preferences"])
    if prefs != (profil.preferences or {}):
        profil.preferences = prefs

    if "contexte_metier" in data:
        ctx = profil.contexte_metier or {}
        ctx.update(data["contexte_metier"])
        profil.contexte_metier = ctx

    profil.modifie_le = datetime.utcnow()
    profil.derniere_activite = datetime.utcnow()

    await db.commit()
    await db.refresh(profil)
    return profil


async def incrementer_stat(
    user_id: int,
    stat_key: str,
    db: AsyncSession,
    increment: int = 1,
    xp_gain: int = 1,
) -> ProfilProfessionnelDB:
    """
    Incrémente un compteur de statistiques (nb_rapports, nb_slides, etc.)
    et met à jour le niveau XP. Déclenche les badges automatiques.
    """
    profil = await get_profil(user_id, db)
    if not profil:
        return profil  # silencieux si profil absent

    stats = profil.stats_usage or {}
    stats[stat_key] = stats.get(stat_key, 0) + increment
    profil.stats_usage = stats

    # XP
    profil.points_xp = (profil.points_xp or 0) + xp_gain
    profil.niveau_xp = _calculer_niveau_xp(profil.points_xp)

    # Badges automatiques
    badges = list(profil.badges or [])
    for (k, seuil, badge) in _BADGES_AUTO:
        if k == stat_key and stats[stat_key] >= seuil and badge not in badges:
            badges.append(badge)
            logger.info(f"[ServiceProfil] Badge '{badge}' débloqué pour user={user_id}")
    profil.badges = badges
    profil.derniere_activite = datetime.utcnow()

    await db.commit()
    await db.refresh(profil)
    return profil


async def ajouter_memoire(
    user_id: int,
    fait: str,
    db: AsyncSession,
    max_faits: int = 50,
) -> ProfilProfessionnelDB:
    """
    Ajoute un fait à la mémoire persistante de l'agent pour cet utilisateur.
    Conserve les `max_faits` plus récents.
    """
    profil = await get_profil(user_id, db)
    if not profil:
        return profil

    memoire = list(profil.memoire_agent or [])
    memoire.append({
        "fait":  fait,
        "date":  datetime.utcnow().strftime("%Y-%m-%d"),
    })
    # Garder uniquement les N derniers faits
    if len(memoire) > max_faits:
        memoire = memoire[-max_faits:]
    profil.memoire_agent = memoire

    await db.commit()
    await db.refresh(profil)
    return profil


async def ajouter_badge(
    user_id: int,
    badge: str,
    db: AsyncSession,
) -> ProfilProfessionnelDB:
    """Ajoute manuellement un badge (si pas déjà présent)."""
    profil = await get_profil(user_id, db)
    if not profil:
        return profil

    badges = list(profil.badges or [])
    if badge not in badges:
        badges.append(badge)
        profil.badges = badges
        await db.commit()
        await db.refresh(profil)
    return profil


def _calculer_niveau_xp(points: int) -> str:
    """Retourne le niveau XP correspondant aux points."""
    niveau = "debutant"
    for nom, seuil in sorted(_SEUILS_XP.items(), key=lambda x: x[1], reverse=True):
        if points >= seuil:
            niveau = nom
            break
    return niveau


# ── Fonctions Admin ────────────────────────────────────────────────────────────

async def lister_tous_profils(
    db: AsyncSession,
    page: int = 1,
    par_page: int = 50,
) -> list:
    """Retourne tous les profils paginés (usage admin uniquement)."""
    from sqlalchemy import select, func
    offset = (page - 1) * par_page
    result = await db.execute(
        select(ProfilProfessionnelDB)
        .order_by(ProfilProfessionnelDB.date_creation.desc())
        .offset(offset)
        .limit(par_page)
    )
    profils = result.scalars().all()
    return [p.to_dict() for p in profils]


async def stats_globales(db: AsyncSession) -> dict:
    """Retourne les statistiques globales de la plateforme (usage admin)."""
    from sqlalchemy import select, func
    from collections import Counter

    result = await db.execute(select(ProfilProfessionnelDB))
    tous = result.scalars().all()

    nb_users = len(tous)
    nb_requetes = sum((p.stats_usage or {}).get("nb_requetes_agent", 0) for p in tous)
    nb_docs = sum((p.stats_usage or {}).get("nb_documents_generes", 0) for p in tous)

    metiers = Counter(p.metier for p in tous if p.metier)
    pays = Counter(p.pays for p in tous if p.pays)

    return {
        "nb_utilisateurs": nb_users,
        "nb_requetes_total": nb_requetes,
        "nb_documents_total": nb_docs,
        "metiers_top": [{"metier": k, "count": v} for k, v in metiers.most_common(10)],
        "pays_top": [{"pays": k, "count": v} for k, v in pays.most_common(10)],
    }
