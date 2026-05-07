"""
Yukpo Pro — Routes Organisations / Plan Entreprise.

POST /pro/orgs                          créer une org (current_user devient owner)
GET  /pro/orgs/me                       mon org active (ou 404)
PATCH /pro/orgs/{org_id}                update infos (admin/owner)

POST /pro/orgs/{org_id}/invites         inviter par email
GET  /pro/orgs/{org_id}/invites         lister invitations (admin/owner)
DELETE /pro/orgs/{org_id}/invites/{id}  révoquer
POST /pro/orgs/invites/{token}/accept   accepter (user connecté)
GET  /pro/orgs/invites/{token}          détails invitation (signed-in ou pas)

GET    /pro/orgs/{org_id}/members            liste membres
PATCH  /pro/orgs/{org_id}/members/{user_id}  changer rôle
DELETE /pro/orgs/{org_id}/members/{user_id}  retirer
POST   /pro/orgs/{org_id}/leave              quitter (membre)

GET  /pro/orgs/{org_id}/billing         historique factures
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, TokenData
from core.database import get_db, async_session_maker, UtilisateurDB
from sqlalchemy import select
from modules.pro import organizations as orgs

logger = logging.getLogger("yukpo_assurance.api.orgs")
router = APIRouter(prefix="/pro/orgs", tags=["Organisations"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class CreerOrgRequest(BaseModel):
    nom: str = Field(..., min_length=2, max_length=200)
    pays: Optional[str] = None
    secteur: Optional[str] = None
    prix_par_siege_fcfa: float = 8000.0
    devise: str = "XAF"
    max_seats: Optional[int] = None
    domain_auto_join: Optional[str] = None


class UpdateOrgRequest(BaseModel):
    nom: Optional[str] = None
    pays: Optional[str] = None
    secteur: Optional[str] = None
    domain_auto_join: Optional[str] = None
    settings: Optional[dict] = None


class InviterRequest(BaseModel):
    email: str
    role: str = "member"  # member | admin


class ChangerRoleRequest(BaseModel):
    role: str  # admin | member


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _exiger_role(*, user_id: int, org_id: int, roles: tuple[str, ...]) -> str:
    role = await orgs.get_role_dans_org(user_id, org_id)
    if role not in roles:
        raise HTTPException(status_code=403, detail=f"Réservé à {' ou '.join(roles)}")
    return role


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("", summary="Créer une organisation entreprise")
async def creer_org_route(
    req: CreerOrgRequest,
    current_user: TokenData = Depends(get_current_user),
):
    try:
        org = await orgs.creer_organisation(
            nom=req.nom, owner_id=current_user.user_id,
            pays=req.pays, secteur=req.secteur,
            prix_par_siege_fcfa=req.prix_par_siege_fcfa,
            devise=req.devise, max_seats=req.max_seats,
            domain_auto_join=req.domain_auto_join,
        )
        return org.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/me", summary="Mon organisation active")
async def mon_org(current_user: TokenData = Depends(get_current_user)):
    org = await orgs.get_org_de_user(current_user.user_id)
    if not org:
        raise HTTPException(status_code=404, detail="Aucune organisation active")
    role = await orgs.get_role_dans_org(current_user.user_id, org.id)
    return {**org.to_dict(), "mon_role": role}


@router.patch("/{org_id}", summary="Mettre à jour l'organisation")
async def update_org(
    org_id: int, req: UpdateOrgRequest,
    current_user: TokenData = Depends(get_current_user),
):
    await _exiger_role(user_id=current_user.user_id, org_id=org_id,
                       roles=("owner", "admin"))
    from sqlalchemy import update
    data = req.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(400, "Aucun champ fourni")
    if "domain_auto_join" in data and data["domain_auto_join"]:
        data["domain_auto_join"] = data["domain_auto_join"].lower()
        # Modification du domaine remet la vérification à 0 (sécurité)
        data["domain_verifie"] = False
    async with async_session_maker() as db:
        await db.execute(
            update(orgs.OrganizationDB)
            .where(orgs.OrganizationDB.id == org_id)
            .values(**data)
        )
        await db.commit()
        r = await db.execute(
            select(orgs.OrganizationDB).where(orgs.OrganizationDB.id == org_id)
        )
        org = r.scalar_one()
        return org.to_dict()


@router.post("/{org_id}/invites", summary="Inviter par email")
async def inviter(
    org_id: int, req: InviterRequest,
    current_user: TokenData = Depends(get_current_user),
):
    try:
        invite = await orgs.creer_invitation(
            org_id=org_id, email=req.email, role=req.role,
            invite_par=current_user.user_id,
        )
        # TODO: envoyer email avec lien d'acceptation
        # Pour MVP : retourner le token au caller (frontend affiche le lien)
        return {
            **invite.to_dict(inclure_token=True),
            "lien_acceptation": f"/pro/invites/{invite.token}",
        }
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{org_id}/invites", summary="Lister les invitations")
async def liste_invites(
    org_id: int,
    current_user: TokenData = Depends(get_current_user),
):
    await _exiger_role(user_id=current_user.user_id, org_id=org_id,
                       roles=("owner", "admin"))
    return {"invitations": await orgs.lister_invites(org_id)}


@router.delete("/{org_id}/invites/{invite_id}", summary="Révoquer une invitation")
async def revoquer_invite(
    org_id: int, invite_id: int,
    current_user: TokenData = Depends(get_current_user),
):
    try:
        return await orgs.revoquer_invitation(
            invite_id=invite_id, org_id=org_id,
            acteur_id=current_user.user_id,
        )
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/invites/{token}", summary="Détails d'une invitation (auth requis)")
async def details_invite(
    token: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Retourne le détail (org/role) pour permettre au front de pré-remplir l'écran d'acceptation."""
    async with async_session_maker() as db:
        r = await db.execute(
            select(orgs.OrganizationInviteDB, orgs.OrganizationDB)
            .join(orgs.OrganizationDB,
                  orgs.OrganizationDB.id == orgs.OrganizationInviteDB.org_id)
            .where(orgs.OrganizationInviteDB.token == token)
        )
        row = r.first()
        if not row:
            raise HTTPException(404, "Invitation introuvable")
        inv, org = row
        return {
            "invitation": inv.to_dict(),
            "organisation": {
                "nom": org.nom, "secteur": org.secteur, "pays": org.pays,
                "prix_par_siege_fcfa": org.prix_par_siege_fcfa,
                "devise": org.devise,
            },
        }


@router.post("/invites/{token}/accept", summary="Accepter une invitation")
async def accepter_invite(
    token: str,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # On a besoin de l'email — on le récupère depuis UtilisateurDB
    r = await db.execute(
        select(UtilisateurDB).where(UtilisateurDB.id == current_user.user_id)
    )
    user = r.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Utilisateur introuvable")
    try:
        return await orgs.accepter_invitation(
            token=token, user_id=current_user.user_id,
            user_email=user.email,
        )
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{org_id}/members", summary="Lister les membres")
async def liste_membres(
    org_id: int,
    current_user: TokenData = Depends(get_current_user),
):
    role = await orgs.get_role_dans_org(current_user.user_id, org_id)
    if not role:
        raise HTTPException(403, "Vous n'êtes pas membre de cette organisation")
    return {"membres": await orgs.lister_membres(org_id), "mon_role": role}


@router.patch("/{org_id}/members/{user_id}", summary="Changer le rôle d'un membre")
async def changer_role_membre(
    org_id: int, user_id: int, req: ChangerRoleRequest,
    current_user: TokenData = Depends(get_current_user),
):
    try:
        return await orgs.changer_role(
            org_id=org_id, user_id=user_id, nouveau_role=req.role,
            acteur_id=current_user.user_id,
        )
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/{org_id}/members/{user_id}", summary="Retirer un membre")
async def retirer_membre_route(
    org_id: int, user_id: int,
    current_user: TokenData = Depends(get_current_user),
):
    try:
        return await orgs.retirer_membre(
            org_id=org_id, user_id=user_id, acteur_id=current_user.user_id,
        )
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{org_id}/leave", summary="Quitter l'organisation (membre)")
async def quitter_org(
    org_id: int,
    current_user: TokenData = Depends(get_current_user),
):
    try:
        return await orgs.retirer_membre(
            org_id=org_id, user_id=current_user.user_id,
            acteur_id=current_user.user_id,
        )
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{org_id}/billing", summary="Historique factures de l'organisation")
async def historique_factures_route(
    org_id: int,
    current_user: TokenData = Depends(get_current_user),
):
    await _exiger_role(user_id=current_user.user_id, org_id=org_id,
                       roles=("owner", "admin"))
    return {"factures": await orgs.historique_factures(org_id)}
