"""
Yukpo Pro — Organisations / Plans Entreprise.

Modèle :
- 1 utilisateur peut appartenir à 0 ou 1 organisation (MVP).
- L'owner crée l'org + paie. Admins peuvent inviter/retirer/modifier.
- Members consomment l'app sous la souscription Entreprise.
- Tarification par siège (seat-based) facturée mensuellement sur le pic
  de membres actifs du mois. Pas de prorata au lancement.
"""
from __future__ import annotations

import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, JSON, ForeignKey, Float,
)
from sqlalchemy.dialects.postgresql import JSONB
from core.database import Base

logger = logging.getLogger("yukpo_assurance.organizations")


# ── Modèles DB ────────────────────────────────────────────────────────────────

class OrganizationDB(Base):
    """Organisation entreprise — plan multi-utilisateurs facturé par siège."""
    __tablename__ = "organizations"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    nom             = Column(String(200), nullable=False)
    slug            = Column(String(80),  unique=True, nullable=False, index=True)
    owner_id        = Column(Integer, nullable=False, index=True)  # ref utilisateurs.id

    # Plan & tarification
    plan            = Column(String(40), nullable=False, default="entreprise")
    prix_par_siege_fcfa = Column(Float,  nullable=False, default=8000.0)
    devise          = Column(String(8),  nullable=False, default="XAF")
    max_seats       = Column(Integer, nullable=True)  # null = illimité
    statut          = Column(String(40), nullable=False, default="actif",
                             index=True)  # actif | suspendu | ferme

    # Auto-join par domaine email vérifié
    domain_auto_join = Column(String(120), nullable=True, index=True)
    domain_verifie   = Column(Boolean, default=False, nullable=False)

    # Métadonnées
    pays            = Column(String(2),  nullable=True)
    secteur         = Column(String(80), nullable=True)
    logo_b64        = Column(JSON,       nullable=True)
    settings        = Column(JSON,       nullable=True, default=dict)

    cree_le         = Column(DateTime, default=datetime.utcnow, nullable=False)
    modifie_le      = Column(DateTime, default=datetime.utcnow,
                             onupdate=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "nom": self.nom, "slug": self.slug,
            "owner_id": self.owner_id,
            "plan": self.plan, "prix_par_siege_fcfa": self.prix_par_siege_fcfa,
            "devise": self.devise, "max_seats": self.max_seats,
            "statut": self.statut,
            "domain_auto_join": self.domain_auto_join,
            "domain_verifie":   self.domain_verifie,
            "pays": self.pays, "secteur": self.secteur,
            "settings": self.settings or {},
            "cree_le": self.cree_le.isoformat() if self.cree_le else None,
        }


class OrganizationMemberDB(Base):
    """Lien utilisateur ↔ organisation avec rôle."""
    __tablename__ = "organization_members"

    id        = Column(Integer, primary_key=True, autoincrement=True)
    org_id    = Column(Integer, nullable=False, index=True)  # ref organizations.id
    user_id   = Column(Integer, nullable=False, index=True)  # ref utilisateurs.id
    role      = Column(String(20), nullable=False, default="member",
                       index=True)  # owner | admin | member
    statut    = Column(String(20), nullable=False, default="actif",
                       index=True)  # actif | suspendu | parti

    invite_par = Column(Integer, nullable=True)  # user_id de l'invitant
    joined_at  = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_active_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "org_id": self.org_id, "user_id": self.user_id,
            "role": self.role, "statut": self.statut,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
            "last_active_at": self.last_active_at.isoformat() if self.last_active_at else None,
        }


class OrganizationInviteDB(Base):
    """Invitation envoyée par email — token à usage unique."""
    __tablename__ = "organization_invites"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    org_id      = Column(Integer, nullable=False, index=True)
    email       = Column(String(255), nullable=False, index=True)
    role        = Column(String(20), nullable=False, default="member")
    token       = Column(String(80), unique=True, nullable=False, index=True)
    invite_par  = Column(Integer, nullable=False)  # user_id qui a invité
    statut      = Column(String(20), nullable=False, default="en_attente",
                         index=True)  # en_attente | accepte | revoque | expire

    expires_at  = Column(DateTime, nullable=False)
    cree_le     = Column(DateTime, default=datetime.utcnow, nullable=False)
    accepte_le  = Column(DateTime, nullable=True)
    accepte_par = Column(Integer, nullable=True)  # user_id de celui qui a accepté

    def to_dict(self, *, inclure_token: bool = False) -> dict:
        d = {
            "id": self.id, "org_id": self.org_id, "email": self.email,
            "role": self.role, "statut": self.statut,
            "invite_par": self.invite_par,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "cree_le":    self.cree_le.isoformat() if self.cree_le else None,
            "accepte_le": self.accepte_le.isoformat() if self.accepte_le else None,
        }
        if inclure_token:
            d["token"] = self.token
        return d


class OrganizationBillingDB(Base):
    """Facture mensuelle organisation (pic de sièges actifs × prix unitaire)."""
    __tablename__ = "organization_billing"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    org_id            = Column(Integer, nullable=False, index=True)
    period_debut      = Column(DateTime, nullable=False)
    period_fin        = Column(DateTime, nullable=False, index=True)

    sieges_max        = Column(Integer, nullable=False, default=0)
    sieges_factures   = Column(Integer, nullable=False, default=0)
    prix_unitaire_fcfa = Column(Float,  nullable=False, default=0.0)
    montant_total_fcfa = Column(Float,  nullable=False, default=0.0)
    devise            = Column(String(8), nullable=False, default="XAF")

    statut            = Column(String(20), nullable=False, default="brouillon",
                               index=True)  # brouillon | a_payer | paye | echu | annule
    transaction_ref   = Column(String(80), nullable=True, index=True)
    paye_le           = Column(DateTime, nullable=True)

    detail            = Column(JSON, nullable=True)  # liste des membres facturés
    cree_le           = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "org_id": self.org_id,
            "period_debut": self.period_debut.isoformat() if self.period_debut else None,
            "period_fin":   self.period_fin.isoformat() if self.period_fin else None,
            "sieges_max":      self.sieges_max,
            "sieges_factures": self.sieges_factures,
            "prix_unitaire_fcfa": self.prix_unitaire_fcfa,
            "montant_total_fcfa": self.montant_total_fcfa,
            "devise": self.devise,
            "statut": self.statut,
            "transaction_ref": self.transaction_ref,
            "paye_le": self.paye_le.isoformat() if self.paye_le else None,
            "detail": self.detail or [],
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generer_slug(nom: str) -> str:
    import re, unicodedata
    s = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60]
    if not s:
        s = "org"
    suffix = secrets.token_hex(3)
    return f"{s}-{suffix}"


def _generer_token_invite() -> str:
    return secrets.token_urlsafe(32)


# ── Service ───────────────────────────────────────────────────────────────────

async def creer_organisation(
    *, nom: str, owner_id: int, pays: Optional[str] = None,
    secteur: Optional[str] = None, prix_par_siege_fcfa: float = 8000.0,
    devise: str = "XAF", max_seats: Optional[int] = None,
    domain_auto_join: Optional[str] = None,
) -> OrganizationDB:
    from core.database import async_session_maker
    from sqlalchemy import select

    async with async_session_maker() as db:
        # Empêche un user d'avoir 2 orgs (MVP : 1 org / user)
        existant = await db.execute(
            select(OrganizationMemberDB)
            .where(OrganizationMemberDB.user_id == owner_id)
            .where(OrganizationMemberDB.statut == "actif")
        )
        if existant.scalar_one_or_none():
            raise ValueError("Vous appartenez déjà à une organisation. Quittez-la d'abord.")

        org = OrganizationDB(
            nom=nom.strip()[:200], slug=_generer_slug(nom),
            owner_id=owner_id, plan="entreprise",
            prix_par_siege_fcfa=prix_par_siege_fcfa, devise=devise,
            max_seats=max_seats, pays=pays, secteur=secteur,
            domain_auto_join=(domain_auto_join or "").lower() or None,
            settings={},
        )
        db.add(org)
        await db.flush()
        # Owner = membre admin avec role 'owner'
        membre = OrganizationMemberDB(
            org_id=org.id, user_id=owner_id, role="owner", statut="actif",
        )
        db.add(membre)
        await db.commit()
        await db.refresh(org)
        logger.info(f"[Orgs] Org créée id={org.id} nom='{org.nom}' owner={owner_id}")
        return org


async def get_org_de_user(user_id: int) -> Optional[OrganizationDB]:
    """Retourne l'org active de l'utilisateur (ou None)."""
    from core.database import async_session_maker
    from sqlalchemy import select
    async with async_session_maker() as db:
        r = await db.execute(
            select(OrganizationMemberDB, OrganizationDB)
            .join(OrganizationDB, OrganizationDB.id == OrganizationMemberDB.org_id)
            .where(OrganizationMemberDB.user_id == user_id)
            .where(OrganizationMemberDB.statut == "actif")
            .where(OrganizationDB.statut == "actif")
            .limit(1)
        )
        row = r.first()
        if not row:
            return None
        return row[1]


async def get_role_dans_org(user_id: int, org_id: int) -> Optional[str]:
    from core.database import async_session_maker
    from sqlalchemy import select
    async with async_session_maker() as db:
        r = await db.execute(
            select(OrganizationMemberDB.role)
            .where(OrganizationMemberDB.user_id == user_id)
            .where(OrganizationMemberDB.org_id == org_id)
            .where(OrganizationMemberDB.statut == "actif")
        )
        return r.scalar_one_or_none()


async def lister_membres(org_id: int) -> list[dict]:
    from core.database import async_session_maker, UtilisateurDB
    from sqlalchemy import select
    async with async_session_maker() as db:
        r = await db.execute(
            select(OrganizationMemberDB, UtilisateurDB)
            .join(UtilisateurDB, UtilisateurDB.id == OrganizationMemberDB.user_id)
            .where(OrganizationMemberDB.org_id == org_id)
            .where(OrganizationMemberDB.statut == "actif")
            .order_by(OrganizationMemberDB.joined_at.asc())
        )
        out: list[dict] = []
        for membre, user in r.all():
            d = membre.to_dict()
            d["email"] = user.email
            d["nom"]   = f"{user.prenoms or ''} {user.nom}".strip()
            d["username"] = user.username
            out.append(d)
        return out


async def changer_role(*, org_id: int, user_id: int, nouveau_role: str,
                       acteur_id: int) -> dict:
    if nouveau_role not in ("admin", "member"):
        raise ValueError("Rôle invalide (admin | member)")
    role_acteur = await get_role_dans_org(acteur_id, org_id)
    if role_acteur not in ("owner", "admin"):
        raise PermissionError("Réservé à owner/admin")

    from core.database import async_session_maker
    from sqlalchemy import select, update
    async with async_session_maker() as db:
        r = await db.execute(
            select(OrganizationMemberDB)
            .where(OrganizationMemberDB.org_id == org_id)
            .where(OrganizationMemberDB.user_id == user_id)
        )
        m = r.scalar_one_or_none()
        if not m:
            raise ValueError("Membre introuvable")
        if m.role == "owner":
            raise ValueError("Impossible de changer le rôle de l'owner")
        await db.execute(
            update(OrganizationMemberDB)
            .where(OrganizationMemberDB.id == m.id)
            .values(role=nouveau_role)
        )
        await db.commit()
        return {"message": "Rôle mis à jour", "user_id": user_id, "role": nouveau_role}


async def retirer_membre(*, org_id: int, user_id: int, acteur_id: int) -> dict:
    role_acteur = await get_role_dans_org(acteur_id, org_id)
    if role_acteur not in ("owner", "admin") and acteur_id != user_id:
        raise PermissionError("Réservé à owner/admin (ou auto-départ)")

    from core.database import async_session_maker
    from sqlalchemy import select, update
    async with async_session_maker() as db:
        r = await db.execute(
            select(OrganizationMemberDB)
            .where(OrganizationMemberDB.org_id == org_id)
            .where(OrganizationMemberDB.user_id == user_id)
        )
        m = r.scalar_one_or_none()
        if not m:
            raise ValueError("Membre introuvable")
        if m.role == "owner":
            raise ValueError(
                "Impossible de retirer l'owner. Transférez d'abord la propriété."
            )
        await db.execute(
            update(OrganizationMemberDB)
            .where(OrganizationMemberDB.id == m.id)
            .values(statut="parti")
        )
        await db.commit()
        return {"message": "Membre retiré", "user_id": user_id}


async def creer_invitation(
    *, org_id: int, email: str, role: str, invite_par: int,
    duree_jours: int = 14,
) -> OrganizationInviteDB:
    if role not in ("admin", "member"):
        raise ValueError("Rôle invalide (admin | member)")
    role_acteur = await get_role_dans_org(invite_par, org_id)
    if role_acteur not in ("owner", "admin"):
        raise PermissionError("Réservé à owner/admin")
    email = (email or "").strip().lower()
    if "@" not in email:
        raise ValueError("Email invalide")

    from core.database import async_session_maker
    async with async_session_maker() as db:
        invite = OrganizationInviteDB(
            org_id=org_id, email=email, role=role,
            token=_generer_token_invite(),
            invite_par=invite_par,
            expires_at=datetime.utcnow() + timedelta(days=duree_jours),
            statut="en_attente",
        )
        db.add(invite)
        await db.commit()
        await db.refresh(invite)
        return invite


async def lister_invites(org_id: int) -> list[dict]:
    from core.database import async_session_maker
    from sqlalchemy import select
    async with async_session_maker() as db:
        r = await db.execute(
            select(OrganizationInviteDB)
            .where(OrganizationInviteDB.org_id == org_id)
            .order_by(OrganizationInviteDB.cree_le.desc())
            .limit(50)
        )
        return [i.to_dict() for i in r.scalars().all()]


async def revoquer_invitation(*, invite_id: int, org_id: int, acteur_id: int) -> dict:
    role_acteur = await get_role_dans_org(acteur_id, org_id)
    if role_acteur not in ("owner", "admin"):
        raise PermissionError("Réservé à owner/admin")
    from core.database import async_session_maker
    from sqlalchemy import select, update
    async with async_session_maker() as db:
        r = await db.execute(
            select(OrganizationInviteDB)
            .where(OrganizationInviteDB.id == invite_id)
            .where(OrganizationInviteDB.org_id == org_id)
        )
        inv = r.scalar_one_or_none()
        if not inv:
            raise ValueError("Invitation introuvable")
        if inv.statut != "en_attente":
            raise ValueError(f"Invitation déjà {inv.statut}")
        await db.execute(
            update(OrganizationInviteDB)
            .where(OrganizationInviteDB.id == invite_id)
            .values(statut="revoque")
        )
        await db.commit()
        return {"message": "Invitation révoquée"}


async def accepter_invitation(*, token: str, user_id: int, user_email: str) -> dict:
    """L'utilisateur accepte une invitation → devient membre."""
    from core.database import async_session_maker
    from sqlalchemy import select, update
    async with async_session_maker() as db:
        r = await db.execute(
            select(OrganizationInviteDB)
            .where(OrganizationInviteDB.token == token)
        )
        inv = r.scalar_one_or_none()
        if not inv:
            raise ValueError("Invitation introuvable")
        if inv.statut != "en_attente":
            raise ValueError(f"Invitation {inv.statut}")
        if inv.expires_at < datetime.utcnow():
            await db.execute(
                update(OrganizationInviteDB).where(OrganizationInviteDB.id == inv.id)
                .values(statut="expire")
            )
            await db.commit()
            raise ValueError("Invitation expirée")
        if (inv.email or "").lower() != (user_email or "").lower():
            raise PermissionError("Cette invitation est destinée à un autre email")

        # Vérifier que l'user n'a pas déjà une org active
        r2 = await db.execute(
            select(OrganizationMemberDB)
            .where(OrganizationMemberDB.user_id == user_id)
            .where(OrganizationMemberDB.statut == "actif")
        )
        if r2.scalar_one_or_none():
            raise ValueError(
                "Vous appartenez déjà à une organisation. Quittez-la d'abord."
            )

        # Créer le membre
        membre = OrganizationMemberDB(
            org_id=inv.org_id, user_id=user_id, role=inv.role,
            statut="actif", invite_par=inv.invite_par,
        )
        db.add(membre)
        await db.execute(
            update(OrganizationInviteDB).where(OrganizationInviteDB.id == inv.id)
            .values(statut="accepte", accepte_le=datetime.utcnow(),
                    accepte_par=user_id)
        )
        await db.commit()
        return {"message": "Bienvenue dans l'organisation", "org_id": inv.org_id,
                "role": inv.role}


async def auto_join_par_domaine(user_id: int, email: str) -> Optional[int]:
    """
    Si l'email matche le domaine vérifié d'une org, rattache l'utilisateur
    automatiquement comme member. Retourne l'org_id ou None.
    """
    domain = (email or "").split("@")[-1].lower().strip()
    if not domain or "." not in domain:
        return None
    from core.database import async_session_maker
    from sqlalchemy import select
    async with async_session_maker() as db:
        r = await db.execute(
            select(OrganizationDB)
            .where(OrganizationDB.domain_auto_join == domain)
            .where(OrganizationDB.domain_verifie == True)  # noqa: E712
            .where(OrganizationDB.statut == "actif")
            .limit(1)
        )
        org = r.scalar_one_or_none()
        if not org:
            return None
        # Vérifier qu'il n'a pas déjà une org
        r2 = await db.execute(
            select(OrganizationMemberDB)
            .where(OrganizationMemberDB.user_id == user_id)
            .where(OrganizationMemberDB.statut == "actif")
        )
        if r2.scalar_one_or_none():
            return None
        membre = OrganizationMemberDB(
            org_id=org.id, user_id=user_id, role="member", statut="actif",
        )
        db.add(membre)
        await db.commit()
        logger.info(f"[Orgs] Auto-join domaine: user {user_id} → org {org.id} ({domain})")
        return org.id


async def historique_factures(org_id: int) -> list[dict]:
    from core.database import async_session_maker
    from sqlalchemy import select
    async with async_session_maker() as db:
        r = await db.execute(
            select(OrganizationBillingDB)
            .where(OrganizationBillingDB.org_id == org_id)
            .order_by(OrganizationBillingDB.period_fin.desc())
            .limit(24)
        )
        return [f.to_dict() for f in r.scalars().all()]
