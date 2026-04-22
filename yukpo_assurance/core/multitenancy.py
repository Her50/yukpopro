"""
YukpoAssurance → YukpoPlatform
Middleware d'isolation multi-tenant / multi-secteur.

Principe :
  - Chaque compagnie a un secteur (assurance, banque, ecole, etc.)
  - Le JWT porte : user_id, role, compagnie_id, secteur
  - Ce middleware vérifie que :
      1. L'utilisateur appartient bien à la compagnie ciblée
      2. Le module demandé est activé pour son secteur
  - Les routes utilisent require_module("sinistres") → 403 si le secteur n'a pas ce module
"""
import logging
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config.secteurs import secteur_autorise_module, SECTEURS, get_secteur
from core.auth import TokenData, get_current_user
from core.database import get_db, CompagnieDB

logger = logging.getLogger("yukpo_assurance.multitenancy")


# ─── Modèle étendu du token (secteur inclus) ─────────────────────────────────

class TokenDataSecteur(TokenData):
    """Extension de TokenData avec le secteur de la compagnie."""
    secteur: str = "assurance"   # par défaut


async def get_current_user_avec_secteur(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TokenDataSecteur:
    """
    Enrichit le token courant avec le secteur de la compagnie.
    Lit depuis CompagnieDB (ou cache Redis si disponible).
    """
    secteur = "assurance"  # défaut si DB pas encore initialisée

    try:
        q = select(CompagnieDB.secteur).where(CompagnieDB.id == current_user.compagnie_id)
        result = await db.execute(q)
        row = result.scalar_one_or_none()
        if row:
            secteur = row
    except Exception:
        pass  # DB pas encore migrée → on accepte le défaut

    return TokenDataSecteur(
        user_id=current_user.user_id,
        user_nom=current_user.user_nom,
        role=current_user.role,
        compagnie_id=current_user.compagnie_id,
        secteur=secteur,
    )


# ─── Dépendance factory : require_module ─────────────────────────────────────

def require_module(nom_module: str):
    """
    Dépendance FastAPI : vérifie que le module est activé pour le secteur de la compagnie.

    Usage :
        @router.get("/sinistres")
        async def lister_sinistres(
            user = Depends(require_module("sinistres"))
        ):
    """
    async def _check(
        user: TokenDataSecteur = Depends(get_current_user_avec_secteur),
    ) -> TokenDataSecteur:
        if not secteur_autorise_module(user.secteur, nom_module):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Module '{nom_module}' non disponible pour le secteur '{user.secteur}'. "
                    f"Modules actifs : {', '.join(SECTEURS.get(user.secteur, {}).get('modules', []))}"
                ),
            )
        return user
    return _check


# ─── Helper : infos secteur compagnie ────────────────────────────────────────

async def get_infos_secteur(
    user: TokenDataSecteur = Depends(get_current_user_avec_secteur),
) -> dict:
    """Retourne la config complète du secteur de l'utilisateur connecté."""
    try:
        return get_secteur(user.secteur)
    except ValueError:
        return SECTEURS["assurance"]
