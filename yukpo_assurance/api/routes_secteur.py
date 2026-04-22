"""
Routes FastAPI — Configuration multi-secteur.
- GET  /secteurs          : liste tous les secteurs disponibles
- GET  /secteurs/{code}   : détail d'un secteur et ses modules
- GET  /ma-compagnie      : secteur actuel de la compagnie connectée
- PUT  /ma-compagnie      : changer le secteur de la compagnie (admin/DG uniquement)
- GET  /modules-actifs    : modules actifs pour la compagnie connectée
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db, CompagnieDB
from core.auth import get_current_user, TokenData
from config.secteurs import (
    SECTEURS,
    get_secteur,
    modules_actifs,
    label_module,
    secteur_autorise_module,
)

router = APIRouter(prefix="/secteur", tags=["Secteur & Multi-tenant"])


# ─────────────────────────────────────────────────────────────
# Schémas
# ─────────────────────────────────────────────────────────────

class ChangerSecteurSchema(BaseModel):
    secteur: str


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

async def _get_compagnie(compagnie_id: int, db: AsyncSession):
    r = await db.execute(select(CompagnieDB).where(CompagnieDB.id == compagnie_id))
    return r.scalar_one_or_none()


def _secteur_detail(code: str) -> dict:
    info = get_secteur(code)
    if not info:
        return {}
    mods = modules_actifs(code)
    return {
        "code": code,
        "label": info.get("label", code),
        "reglementation": info.get("reglementation", ""),
        "nb_modules": len(mods),
        "modules": [
            {"code": m, "label": label_module(code, m)}
            for m in mods
        ],
    }


# ─────────────────────────────────────────────────────────────
# Routes publiques (authentifiées mais sans restriction module)
# ─────────────────────────────────────────────────────────────

@router.get("/secteurs")
async def lister_secteurs(_: TokenData = Depends(get_current_user)):
    """Retourne la liste de tous les secteurs disponibles dans la plateforme."""
    return [
        {
            "code": code,
            "label": info.get("label", code),
            "reglementation": info.get("reglementation", ""),
            "nb_modules": len(info.get("modules", [])),
        }
        for code, info in SECTEURS.items()
    ]


@router.get("/secteurs/{code}")
async def detail_secteur(
    code: str,
    _: TokenData = Depends(get_current_user),
):
    """Détail d'un secteur : label, réglementation, liste complète des modules."""
    if code not in SECTEURS:
        raise HTTPException(404, f"Secteur '{code}' inconnu")
    return _secteur_detail(code)


@router.get("/ma-compagnie")
async def secteur_ma_compagnie(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retourne le secteur configuré pour la compagnie de l'utilisateur connecté."""
    compagnie = await _get_compagnie(current_user.compagnie_id, db)
    if not compagnie:
        raise HTTPException(404, "Compagnie introuvable")

    secteur_code = getattr(compagnie, "secteur", "assurance") or "assurance"
    return {
        "compagnie_id": compagnie.id,
        "compagnie_nom": compagnie.nom,
        **_secteur_detail(secteur_code),
    }


@router.get("/modules-actifs")
async def mes_modules_actifs(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retourne les modules actifs pour la compagnie connectée.
    Utilisé par le frontend pour afficher/masquer les sections de navigation.
    """
    compagnie = await _get_compagnie(current_user.compagnie_id, db)
    secteur_code = "assurance"
    if compagnie:
        secteur_code = getattr(compagnie, "secteur", "assurance") or "assurance"

    mods = modules_actifs(secteur_code)
    return {
        "secteur": secteur_code,
        "modules": [
            {
                "code": m,
                "label": label_module(secteur_code, m),
                "actif": True,
            }
            for m in mods
        ],
    }


# ─────────────────────────────────────────────────────────────
# Changer le secteur (admin / DG uniquement)
# ─────────────────────────────────────────────────────────────

@router.put("/ma-compagnie")
async def changer_secteur(
    payload: ChangerSecteurSchema,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Change le secteur de la compagnie connectée.
    Réservé aux utilisateurs avec le rôle dg ou admin.
    """
    if current_user.role not in ("dg", "admin"):
        raise HTTPException(403, "Seul le DG ou un administrateur peut modifier le secteur")

    if payload.secteur not in SECTEURS:
        raise HTTPException(
            400,
            f"Secteur '{payload.secteur}' invalide. "
            f"Valeurs acceptées : {', '.join(SECTEURS.keys())}",
        )

    compagnie = await _get_compagnie(current_user.compagnie_id, db)
    if not compagnie:
        raise HTTPException(404, "Compagnie introuvable")

    ancien_secteur = getattr(compagnie, "secteur", "assurance")
    compagnie.secteur = payload.secteur
    await db.commit()

    return {
        "message": "Secteur mis à jour",
        "ancien_secteur": ancien_secteur,
        "nouveau_secteur": payload.secteur,
        "modules_actifs": modules_actifs(payload.secteur),
        "attention": (
            "Les modules non présents dans le nouveau secteur ne seront plus accessibles."
            if ancien_secteur != payload.secteur else ""
        ),
    }


# ─────────────────────────────────────────────────────────────
# Vérifier si un module est autorisé pour le secteur courant
# ─────────────────────────────────────────────────────────────

@router.get("/check-module/{module}")
async def verifier_module(
    module: str,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Vérifie si un module est accessible pour la compagnie connectée."""
    compagnie = await _get_compagnie(current_user.compagnie_id, db)
    secteur_code = "assurance"
    if compagnie:
        secteur_code = getattr(compagnie, "secteur", "assurance") or "assurance"

    autorise = secteur_autorise_module(secteur_code, module)
    return {
        "module": module,
        "secteur": secteur_code,
        "autorise": autorise,
        "label": label_module(secteur_code, module) if autorise else None,
    }
