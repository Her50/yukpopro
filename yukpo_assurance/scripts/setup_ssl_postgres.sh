#!/bin/bash
# YukpoAssurance — Configuration TLS/SSL pour PostgreSQL
# Active HTTPS entre l'application et PostgreSQL
# Usage: sudo bash scripts/setup_ssl_postgres.sh

set -e

PG_DATA=${PGDATA:-/var/lib/postgresql/data}
CERT_DIR="/etc/ssl/postgresql"

echo "=== YukpoAssurance — Setup TLS PostgreSQL ==="

# Créer les certificats auto-signés (pour test/staging)
mkdir -p "$CERT_DIR"
cd "$CERT_DIR"

# CA
openssl genrsa -out ca.key 4096
openssl req -new -x509 -days 3650 -key ca.key -out ca.crt \
    -subj "/C=CM/ST=Littoral/L=Douala/O=YukpoAssurance/CN=YukpoCA"

# Serveur PostgreSQL
openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr \
    -subj "/C=CM/ST=Littoral/L=Douala/O=YukpoAssurance/CN=postgres"
openssl x509 -req -days 365 -in server.csr -CA ca.crt -CAkey ca.key \
    -CAcreateserial -out server.crt

# Permissions correctes
chmod 600 server.key ca.key
chown postgres:postgres server.key server.crt ca.crt ca.key

echo "Certificats créés dans $CERT_DIR"

# Configurer postgresql.conf
cat >> "$PG_DATA/postgresql.conf" << 'EOF'

# ── TLS/SSL YukpoAssurance ──────────────────────────────────
ssl = on
ssl_cert_file = '/etc/ssl/postgresql/server.crt'
ssl_key_file  = '/etc/ssl/postgresql/server.key'
ssl_ca_file   = '/etc/ssl/postgresql/ca.crt'
ssl_ciphers   = 'HIGH:!aNULL:!MD5'
ssl_prefer_server_ciphers = on
ssl_min_protocol_version = 'TLSv1.2'
EOF

echo "postgresql.conf mis à jour"

# Configurer pg_hba.conf pour forcer TLS
cat >> "$PG_DATA/pg_hba.conf" << 'EOF'

# YukpoAssurance — Connexions SSL obligatoires
hostssl yukpo_assurance yukpo 0.0.0.0/0 scram-sha-256
EOF

echo "pg_hba.conf mis à jour"
echo ""
echo "IMPORTANT : Redémarrez PostgreSQL : sudo systemctl restart postgresql"
echo "IMPORTANT : Mettez à jour DATABASE_URL avec ?ssl=require"
