"""Liste les comptes super_admin / admin présents en DB (sans mots de passe)."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

async def main():
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select, or_
    from config.settings import settings
    from core.database import UtilisateurDB

    eng = create_async_engine(settings.DATABASE_URL, echo=False)
    sm = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    async with sm() as s:
        r = await s.execute(
            select(UtilisateurDB).where(
                or_(
                    UtilisateurDB.role.in_(["super_admin", "yukpo_owner", "admin"]),
                    UtilisateurDB.email.ilike("%admin%"),
                )
            ).order_by(UtilisateurDB.id)
        )
        rows = r.scalars().all()
        if not rows:
            print("Aucun admin trouvé en DB.")
        else:
            print(f"{len(rows)} compte(s) admin :\n")
            for u in rows:
                print(f"  ID={u.id:<4} email={u.email:<40} username={u.username:<25} "
                      f"role={u.role:<15} actif={u.actif} créé={u.cree_le.isoformat() if u.cree_le else 'N/A'}")
    await eng.dispose()

asyncio.run(main())
