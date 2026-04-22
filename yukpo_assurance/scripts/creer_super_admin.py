"""
Script de création du compte super_admin Yukpo.

Usage (première installation) :
    cd yukpo_assurance
    python scripts/creer_super_admin.py

Variables d'environnement (optionnelles) :
    SUPER_ADMIN_EMAIL     — email du compte   (défaut : admin@yukpo.cm)
    SUPER_ADMIN_PASSWORD  — mot de passe      (si absent, généré automatiquement)
    SUPER_ADMIN_NOM       — nom affiché        (défaut : Yukpo Admin)

IMPORTANT : À n'exécuter qu'une seule fois en production.
Le script est idempotent : il ne recrée pas le compte s'il existe déjà.
"""
from __future__ import annotations

import asyncio
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def main() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select
    from passlib.context import CryptContext
    from datetime import datetime as _dt

    from config.settings import settings
    from core.database import UtilisateurDB

    email    = os.environ.get("SUPER_ADMIN_EMAIL",    "admin@yukpo.cm")
    nom      = os.environ.get("SUPER_ADMIN_NOM",      "Yukpo Admin")
    password = os.environ.get("SUPER_ADMIN_PASSWORD", "")

    if not password:
        password = secrets.token_urlsafe(16)
        print(f"\n[INFO] Mot de passe généré automatiquement : {password}")
        print("[INFO] Conservez ce mot de passe — il ne sera plus affiché.\n")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Vérifier si un super_admin existe déjà
        result = await session.execute(
            select(UtilisateurDB).where(
                UtilisateurDB.role.in_(["super_admin", "yukpo_owner"])
            )
        )
        existant = result.scalars().first()

        if existant:
            print(f"[INFO] Compte super_admin déjà existant : {existant.email} (role={existant.role})")
            print("[INFO] Aucune modification effectuée.")
            return

        pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        username = email.split("@")[0]

        utilisateur = UtilisateurDB(
            username=username,
            email=email,
            nom=nom,
            hashed_password=pwd_ctx.hash(password),
            role="super_admin",
            compagnie_id=None,
            actif=True,
            cree_le=_dt.utcnow(),
            cree_par=0,
        )
        session.add(utilisateur)
        await session.commit()
        await session.refresh(utilisateur)

        print(f"[OK] Compte super_admin créé :")
        print(f"     Email    : {email}")
        print(f"     Username : {username}")
        print(f"     Nom      : {nom}")
        print(f"     Rôle     : super_admin")
        print(f"     ID       : {utilisateur.id}")
        print(f"     Password : {password}")
        print()
        print("[IMPORTANT] Changez le mot de passe dès la première connexion.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
