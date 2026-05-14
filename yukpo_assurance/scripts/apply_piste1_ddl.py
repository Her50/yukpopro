"""Applique les colonnes de la migration 0014 (Piste 1) directement en SQL
idempotent. À utiliser quand la migration Alembic ne peut pas s'exécuter
(historique fragmenté, conflits 0002, etc.).

Lance depuis le container :
    fly ssh console -a yukpopro-backend
    cd /app && python scripts/apply_piste1_ddl.py
"""
import asyncio
import os
import sys


async def main() -> None:
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("ERROR: DATABASE_URL non défini")
        sys.exit(1)
    # asyncpg ne veut pas du préfixe sqlalchemy
    db_url = db_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    import asyncpg  # type: ignore
    conn = await asyncpg.connect(db_url, timeout=20)
    try:
        # État avant
        rows = await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='shop_products' AND column_name LIKE 'rust_%'"
        )
        existing_p = {r["column_name"] for r in rows}
        print(f"shop_products rust_* avant : {sorted(existing_p) or 'AUCUN'}")

        rows = await conn.fetch(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='shop_boutiques' AND column_name='rust_sync_enabled'"
        )
        print(f"shop_boutiques.rust_sync_enabled avant : {'OUI' if rows else 'NON'}")

        # DDL idempotent
        ddl_statements = [
            "ALTER TABLE shop_boutiques ADD COLUMN IF NOT EXISTS rust_sync_enabled BOOLEAN NOT NULL DEFAULT TRUE",
            "ALTER TABLE shop_products ADD COLUMN IF NOT EXISTS rust_service_id BIGINT",
            "ALTER TABLE shop_products ADD COLUMN IF NOT EXISTS rust_sync_status VARCHAR(20) NOT NULL DEFAULT 'pending'",
            "ALTER TABLE shop_products ADD COLUMN IF NOT EXISTS rust_sync_error TEXT",
            "ALTER TABLE shop_products ADD COLUMN IF NOT EXISTS rust_synced_at TIMESTAMP",
            "ALTER TABLE shop_products ADD COLUMN IF NOT EXISTS rust_sync_attempts INTEGER NOT NULL DEFAULT 0",
            "CREATE INDEX IF NOT EXISTS ix_shop_products_rust_sync_status "
            "ON shop_products(rust_sync_status) WHERE rust_sync_status IN ('pending','failed')",
        ]
        for stmt in ddl_statements:
            await conn.execute(stmt)
            print(f"  OK : {stmt[:80]}")

        # État après
        rows = await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='shop_products' AND column_name LIKE 'rust_%' ORDER BY column_name"
        )
        print(f"\nshop_products rust_* après : {[r['column_name'] for r in rows]}")

        # Marquer 0014 dans alembic_version si besoin
        rows = await conn.fetch("SELECT version_num FROM alembic_version")
        versions = [r["version_num"] for r in rows]
        print(f"\nalembic_version : {versions}")
        if "0014" not in versions:
            if "0013" in versions:
                await conn.execute("UPDATE alembic_version SET version_num='0014' WHERE version_num='0013'")
                print("alembic_version : 0013 -> 0014")
            elif not versions:
                await conn.execute("INSERT INTO alembic_version VALUES ('0014')")
                print("alembic_version : insert 0014")
            else:
                # Multiple heads ou rev inconnue — ne touche pas
                print(f"WARNING : alembic_version a des entrées non gérées ({versions}). "
                      f"À fixer manuellement si besoin.")

        print("\nDONE - Piste 1 DDL appliquée.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
