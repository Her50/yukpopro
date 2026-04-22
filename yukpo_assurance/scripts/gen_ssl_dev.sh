#!/usr/bin/env bash
# =============================================================================
# gen_ssl_dev.sh — Certificat SSL auto-signe pour developpement local
# Usage : bash scripts/gen_ssl_dev.sh [domaine] [duree_jours]
# Exemple : bash scripts/gen_ssl_dev.sh localhost 365
# =============================================================================
set -euo pipefail

DOMAIN="${1:-localhost}"
DAYS="${2:-365}"
SSL_DIR="$(dirname "$0")/../nginx/ssl"
KEY_FILE="$SSL_DIR/${DOMAIN}.key"
CERT_FILE="$SSL_DIR/${DOMAIN}.crt"
CSR_FILE="$SSL_DIR/${DOMAIN}.csr"
EXT_FILE="$SSL_DIR/${DOMAIN}.ext"

echo "=== YukpoAssurance — Generation certificat SSL dev ==="
echo "Domaine : $DOMAIN | Duree : ${DAYS} jours"

# Creer le dossier SSL si absent
mkdir -p "$SSL_DIR"
chmod 700 "$SSL_DIR"

# Fichier d'extensions pour SAN (Subject Alternative Names)
cat > "$EXT_FILE" <<EOF
[req]
default_bits       = 4096
prompt             = no
default_md         = sha256
req_extensions     = v3_req
distinguished_name = dn

[dn]
C  = CM
ST = Centre
L  = Yaounde
O  = YukpoAssurance Dev
OU = IT
CN = ${DOMAIN}

[v3_req]
subjectAltName = @alt_names

[alt_names]
DNS.1 = ${DOMAIN}
DNS.2 = www.${DOMAIN}
DNS.3 = api.${DOMAIN}
IP.1  = 127.0.0.1
IP.2  = ::1
EOF

# 1. Generer la cle privee RSA 4096 bits
echo "[1/3] Generation cle privee RSA 4096..."
openssl genrsa -out "$KEY_FILE" 4096
chmod 600 "$KEY_FILE"

# 2. Generer la CSR (Certificate Signing Request)
echo "[2/3] Generation CSR..."
openssl req \
    -new \
    -key "$KEY_FILE" \
    -out "$CSR_FILE" \
    -config "$EXT_FILE"

# 3. Auto-signer le certificat (CA = lui-meme)
echo "[3/3] Auto-signature du certificat ($DAYS jours)..."
openssl x509 \
    -req \
    -days "$DAYS" \
    -in "$CSR_FILE" \
    -signkey "$KEY_FILE" \
    -out "$CERT_FILE" \
    -extensions v3_req \
    -extfile "$EXT_FILE" \
    -sha256

# Nettoyage
rm -f "$CSR_FILE" "$EXT_FILE"

chmod 644 "$CERT_FILE"

echo ""
echo "=== Certificat genere avec succes ==="
echo "  Cle     : $KEY_FILE"
echo "  Cert    : $CERT_FILE"
echo ""
echo "Mettre a jour nginx.conf :"
echo "  ssl_certificate     /etc/nginx/ssl/${DOMAIN}.crt;"
echo "  ssl_certificate_key /etc/nginx/ssl/${DOMAIN}.key;"
echo ""
echo "ATTENTION : Certificat auto-signe — A utiliser UNIQUEMENT en developpement."
echo "            En production, utiliser scripts/certbot_letsencrypt.sh"
echo ""

# Afficher les infos du certificat
openssl x509 -in "$CERT_FILE" -noout -subject -dates -fingerprint
