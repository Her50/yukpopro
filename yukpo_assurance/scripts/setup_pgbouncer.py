#!/usr/bin/env python3
"""
YukpoAssurance — Configuration PgBouncer (Connection Pooling)

PgBouncer permet de gérer efficacement les connexions PostgreSQL en production.
Recommandé pour > 50 utilisateurs simultanés.

Usage:
    python scripts/setup_pgbouncer.py --host db.compagnie.cm --generate-config
    python scripts/setup_pgbouncer.py --install  # Installation sur Ubuntu/Debian
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

APP_DB_USER = "yukpo"
APP_DB_NAME = "yukpo_assurance"


def generer_config_pgbouncer(
    pg_host: str = "localhost",
    pg_port: int = 5432,
    pgbouncer_port: int = 6432,
    pool_size: int = 25,
    max_client_conn: int = 200,
    output_dir: str = "/etc/pgbouncer",
) -> str:
    """Génère la configuration PgBouncer optimisée pour YukpoAssurance."""

    config = f"""# pgbouncer.ini — YukpoAssurance Production
# Généré automatiquement par setup_pgbouncer.py

[databases]
{APP_DB_NAME} = host={pg_host} port={pg_port} dbname={APP_DB_NAME}

[pgbouncer]
listen_port = {pgbouncer_port}
listen_addr = 127.0.0.1
auth_type = scram-sha-256
auth_file = /etc/pgbouncer/userlist.txt

# Mode session : chaque client conserve une connexion pendant toute sa durée
# Mode transaction : connexion libérée après chaque transaction (recommandé pour FastAPI)
pool_mode = transaction

# Taille du pool de connexions vers PostgreSQL
default_pool_size = {pool_size}
max_client_conn = {max_client_conn}

# Délais
server_idle_timeout = 600
client_idle_timeout = 0
server_connect_timeout = 15
server_login_retry = 15

# Logs
log_connections = 0
log_disconnections = 0
log_pooler_errors = 1
stats_period = 60

# TLS vers PostgreSQL (obligatoire en production)
server_tls_sslmode = require

# Interface admin (monitoring)
admin_users = yukpo_admin
stats_users = yukpo_readonly

# Performance
server_round_robin = 1
ignore_startup_parameters = extra_float_digits,application_name
"""

    userlist = f"""# userlist.txt — Mots de passe hashés (scram-sha-256)
# Générez les hashes avec : echo -n "motdepasse" | md5sum  (pour md5)
# Ou via psql : SELECT 'md5' || md5('motdepasse' || 'username');
"{APP_DB_USER}" "REMPLACER_PAR_HASH_SCRAM"
"yukpo_admin" "REMPLACER_PAR_HASH_ADMIN"
"yukpo_readonly" "REMPLACER_PAR_HASH_READONLY"
"""

    systemd_service = """[Unit]
Description=PgBouncer — Connection Pooler for YukpoAssurance
After=network.target postgresql.service

[Service]
Type=simple
User=postgres
ExecStart=/usr/sbin/pgbouncer /etc/pgbouncer/pgbouncer.ini
ExecReload=/bin/kill -HUP $MAINPID
PIDFile=/var/run/postgresql/pgbouncer.pid
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
"""

    return config, userlist, systemd_service


def afficher_instructions_installation():
    print("""
==========================================================
  INSTALLATION PGBOUNCER — YukpoAssurance
==========================================================

1. UBUNTU/DEBIAN :
   sudo apt-get update && sudo apt-get install -y pgbouncer

2. RHEL/CENTOS/ALMALINUX :
   sudo dnf install -y pgbouncer  (EPEL requis)

3. CONFIGURATION :
   python scripts/setup_pgbouncer.py --generate-config
   sudo cp pgbouncer.ini /etc/pgbouncer/
   sudo cp userlist.txt /etc/pgbouncer/
   sudo chown postgres:postgres /etc/pgbouncer/*
   sudo chmod 600 /etc/pgbouncer/userlist.txt

4. DÉMARRAGE :
   sudo systemctl enable pgbouncer
   sudo systemctl start pgbouncer

5. METTRE À JOUR DATABASE_URL dans .env :
   DATABASE_URL=postgresql+asyncpg://yukpo:MOT_DE_PASSE@localhost:6432/yukpo_assurance

6. VÉRIFICATION :
   psql -h localhost -p 6432 -U yukpo -d yukpo_assurance -c "SHOW pool_mode;"

7. MONITORING :
   psql -h localhost -p 6432 -U yukpo_admin -d pgbouncer -c "SHOW STATS;"
==========================================================
""")


def main():
    parser = argparse.ArgumentParser(description="YukpoAssurance — Setup PgBouncer")
    parser.add_argument("--host", default="localhost", help="Hôte PostgreSQL")
    parser.add_argument("--port", type=int, default=5432, help="Port PostgreSQL")
    parser.add_argument("--pgbouncer-port", type=int, default=6432, help="Port PgBouncer")
    parser.add_argument("--pool-size", type=int, default=25, help="Taille pool par DB")
    parser.add_argument("--max-clients", type=int, default=200, help="Max connexions clients")
    parser.add_argument("--output-dir", default=".", help="Répertoire de sortie des configs")
    parser.add_argument("--generate-config", action="store_true", help="Générer les fichiers de config")
    parser.add_argument("--install", action="store_true", help="Afficher les instructions d'installation")
    args = parser.parse_args()

    if args.install:
        afficher_instructions_installation()
        return

    if args.generate_config:
        config, userlist, systemd = generer_config_pgbouncer(
            pg_host=args.host,
            pg_port=args.port,
            pgbouncer_port=args.pgbouncer_port,
            pool_size=args.pool_size,
            max_client_conn=args.max_clients,
            output_dir=args.output_dir,
        )
        out = Path(args.output_dir)
        out.mkdir(parents=True, exist_ok=True)

        (out / "pgbouncer.ini").write_text(config)
        (out / "userlist.txt").write_text(userlist)
        (out / "pgbouncer.service").write_text(systemd)

        print(f"Configuration générée dans {out}")
        print(f"   - pgbouncer.ini     -> configuration principale")
        print(f"   - userlist.txt      -> comptes (MODIFIER les hashes !)")
        print(f"   - pgbouncer.service -> service systemd")
        print()
        print("IMPORTANT : Modifiez les hashes dans userlist.txt avant déploiement !")
        afficher_instructions_installation()
    else:
        afficher_instructions_installation()


if __name__ == "__main__":
    main()
