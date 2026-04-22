#!/usr/bin/env bash
# =============================================================================
# certbot_letsencrypt.sh — Certificat SSL Let's Encrypt (production)
# Usage : sudo bash scripts/certbot_letsencrypt.sh <domaine> <email>
# Exemple : sudo bash scripts/certbot_letsencrypt.sh app.yukpo-assurance.cm admin@yukpo.cm
#
# Pre-requis :
#   - certbot installe (apt install certbot python3-certbot-nginx)
#   - Nginx installe et en cours d'execution
#   - Port 80 ouvert et pointe vers ce serveur
#   - DNS du domaine configure (A record -> IP du serveur)
# =============================================================================
set -euo pipefail

DOMAIN="${1:-}"
EMAIL="${2:-}"
WEBROOT_DIR="/var/www/certbot"
NGINX_CONF_DIR="/etc/nginx/sites-available"

if [[ -z "$DOMAIN" || -z "$EMAIL" ]]; then
    echo "Usage : sudo bash $0 <domaine> <email>"
    echo "Exemple : sudo bash $0 app.yukpo-assurance.cm admin@yukpo.cm"
    exit 1
fi

if [[ $EUID -ne 0 ]]; then
    echo "Ce script doit etre execute en root (sudo)"
    exit 1
fi

echo "=== YukpoAssurance — Let's Encrypt (${DOMAIN}) ==="

# 1. Installer certbot si absent
if ! command -v certbot &>/dev/null; then
    echo "[1/5] Installation de certbot..."
    apt-get update -qq
    apt-get install -y certbot python3-certbot-nginx
else
    echo "[1/5] Certbot deja installe : $(certbot --version)"
fi

# 2. Creer le dossier webroot pour le challenge ACME
echo "[2/5] Creation du dossier webroot ACME..."
mkdir -p "$WEBROOT_DIR"
chown -R www-data:www-data "$WEBROOT_DIR" 2>/dev/null || true

# 3. Configurer Nginx pour le challenge HTTP-01 (port 80)
echo "[3/5] Configuration Nginx pour challenge ACME..."
cat > "/etc/nginx/sites-available/certbot-challenge" <<EOF
server {
    listen 80;
    server_name ${DOMAIN} www.${DOMAIN};

    location /.well-known/acme-challenge/ {
        root ${WEBROOT_DIR};
        allow all;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}
EOF

ln -sf "/etc/nginx/sites-available/certbot-challenge" "/etc/nginx/sites-enabled/" 2>/dev/null || true
nginx -t && nginx -s reload

# 4. Obtenir le certificat Let's Encrypt
echo "[4/5] Obtention du certificat Let's Encrypt..."
certbot certonly \
    --webroot \
    --webroot-path="$WEBROOT_DIR" \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    --domains "$DOMAIN,www.$DOMAIN" \
    --cert-name "$DOMAIN"

# 5. Configurer le renouvellement automatique
echo "[5/5] Configuration du renouvellement automatique..."
cat > "/etc/cron.d/certbot-renewal" <<EOF
# Renouvellement automatique Let's Encrypt — YukpoAssurance
# Verifie 2 fois par jour et renouvelle si expiration < 30j
0 3,15 * * * root certbot renew --quiet --post-hook "nginx -s reload" >> /var/log/certbot-renewal.log 2>&1
EOF

chmod 644 "/etc/cron.d/certbot-renewal"

echo ""
echo "=== Certificat Let's Encrypt installe avec succes ==="
echo "  Cert  : /etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
echo "  Cle   : /etc/letsencrypt/live/${DOMAIN}/privkey.pem"
echo ""
echo "Mettre a jour nginx.conf (ou docker-compose.yml) :"
echo "  ssl_certificate     /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;"
echo "  ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;"
echo "  ssl_trusted_certificate /etc/letsencrypt/live/${DOMAIN}/chain.pem;"
echo ""
echo "Renouvellement automatique : /etc/cron.d/certbot-renewal"
echo "Test de renouvellement : certbot renew --dry-run"
echo ""

# Afficher la date d'expiration
certbot certificates --cert-name "$DOMAIN" 2>/dev/null | grep -E "Expiry|Domains" || true
