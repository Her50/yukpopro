"""
Routes Admin YukpoPro — Tableau de bord administrateur.

Endpoints :
  GET  /api/v1/pro/admin/utilisateurs  — Liste tous les utilisateurs avec profil
  GET  /api/v1/pro/admin/stats         — Statistiques globales de la plateforme
  PUT  /api/v1/pro/admin/utilisateurs/{user_id}/metier  — Changer le métier d'un user
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import TokenData, get_current_user
from core.database import async_session_maker

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

@router.get("/utilisateurs", summary="Liste tous les utilisateurs")
async def lister_utilisateurs(
    page:     int = 1,
    par_page: int = 50,
    admin: TokenData = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Retourne la liste paginée de tous les utilisateurs avec leur profil."""
    from modules.pro.service_profil import lister_tous_profils
    try:
        profils = await lister_tous_profils(db, page=page, par_page=par_page)
        return {
            "utilisateurs": profils,
            "page": page,
            "par_page": par_page,
            "admin_user_id": admin.user_id,
        }
    except Exception as e:
        logger.error(f"[Admin] Erreur liste utilisateurs: {e}")
        # Fallback : retourner liste vide si service non disponible
        return {"utilisateurs": [], "page": page, "par_page": par_page}


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
