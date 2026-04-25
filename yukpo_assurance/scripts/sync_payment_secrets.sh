#!/usr/bin/env bash
# ============================================================================
# sync_payment_secrets.sh
# ----------------------------------------------------------------------------
# Synchronise les secrets de paiement depuis GCP Secret Manager
# vers Fly.io (backend) et Vercel (frontend, clés publishable uniquement).
#
# Usage :
#   ./scripts/sync_payment_secrets.sh fly       # Fly seulement
#   ./scripts/sync_payment_secrets.sh vercel    # Vercel seulement
#   ./scripts/sync_payment_secrets.sh all       # les deux (défaut)
#
# Prérequis :
#   - gcloud auth (compte avec accès project yukpo-project)
#   - fly auth (FLY_ACCESS_TOKEN ou flyctl login)
#   - vercel CLI installée et authentifiée (vercel link sur yukpopro_web)
# ============================================================================
set -euo pipefail

GCP_PROJECT="${GCP_PROJECT:-yukpo-project}"
FLY_APP="${FLY_APP:-yukpopro-backend}"
VERCEL_DIR="${VERCEL_DIR:-../yukpopro_web}"
TARGET="${1:-all}"

# Mapping : <secret_GCP> → <env_var_backend>
declare -A FLY_SECRETS=(
  ["cinetpay-api-key"]="CINETPAY_API_KEY"
  ["cinetpay-api-password"]="CINETPAY_API_PASSWORD"
  ["cinetpay-secret-key"]="CINETPAY_SECRET_KEY"
  ["cinetpay-site-id"]="CINETPAY_SITE_ID"
  ["flutterwave-public-key"]="FLUTTERWAVE_PUBLIC_KEY"
  ["flutterwave-secret-key"]="FLUTTERWAVE_SECRET_KEY"
  ["mtn-money-webhook-secret"]="MTN_MOMO_WEBHOOK_SECRET"
  ["notchpay-public-key"]="NOTCHPAY_PUBLIC_KEY"
  ["notchpay-secret-key"]="NOTCHPAY_SECRET_KEY"
  ["orange-money-webhook-secret"]="ORANGE_MONEY_WEBHOOK_SECRET"
  ["paypal-client-id"]="PAYPAL_CLIENT_ID"
  ["paypal-client-secret"]="PAYPAL_CLIENT_SECRET"
  ["paypal-webhook-id"]="PAYPAL_WEBHOOK_ID"
  ["stripe-publishable-key"]="STRIPE_PUBLISHABLE_KEY"
  ["stripe-secret-key"]="STRIPE_SECRET_KEY"
  ["stripe-webhook-secret"]="STRIPE_WEBHOOK_SECRET"
)

# Mapping : <secret_GCP> → <env_var_frontend_VITE_*> (UNIQUEMENT publishable)
declare -A VERCEL_SECRETS=(
  ["stripe-publishable-key"]="VITE_STRIPE_PUBLISHABLE_KEY"
  ["paypal-client-id"]="VITE_PAYPAL_CLIENT_ID"
  ["flutterwave-public-key"]="VITE_FLUTTERWAVE_PUBLIC_KEY"
  ["notchpay-public-key"]="VITE_NOTCHPAY_PUBLIC_KEY"
)

log() { echo "[$(date +%H:%M:%S)] $*"; }

fetch_secret() {
  local name="$1"
  gcloud secrets versions access latest --secret="$name" --project="$GCP_PROJECT" 2>/dev/null || true
}

sync_fly() {
  log "→ Synchronisation vers Fly app: $FLY_APP"
  local args=()
  for gcp_name in "${!FLY_SECRETS[@]}"; do
    local env_name="${FLY_SECRETS[$gcp_name]}"
    local value
    value=$(fetch_secret "$gcp_name")
    if [[ -z "$value" ]]; then
      log "  ⚠ secret GCP '$gcp_name' vide ou inaccessible — skip $env_name"
      continue
    fi
    args+=("$env_name=$value")
    log "  ✓ $env_name pr\u00eat"
  done

  if [[ ${#args[@]} -gt 0 ]]; then
    log "Pousse ${#args[@]} secrets sur Fly (\u00e9vite redeploy auto avec --stage)..."
    fly secrets set --app "$FLY_APP" --stage "${args[@]}"
    log "  → Lance \`fly deploy --app $FLY_APP\` pour appliquer."
  fi
}

sync_vercel() {
  log "→ Synchronisation vers Vercel ($VERCEL_DIR)"
  if [[ ! -d "$VERCEL_DIR" ]]; then
    log "  ⚠ R\u00e9pertoire Vercel introuvable: $VERCEL_DIR"
    return 1
  fi
  pushd "$VERCEL_DIR" > /dev/null
  for gcp_name in "${!VERCEL_SECRETS[@]}"; do
    local env_name="${VERCEL_SECRETS[$gcp_name]}"
    local value
    value=$(fetch_secret "$gcp_name")
    if [[ -z "$value" ]]; then
      log "  ⚠ $gcp_name vide — skip $env_name"
      continue
    fi
    # Supprime puis r\u00e9-ajoute pour environnement production
    printf "y\n" | vercel env rm "$env_name" production 2>/dev/null || true
    printf "%s" "$value" | vercel env add "$env_name" production
    log "  ✓ $env_name d\u00e9ploy\u00e9 sur Vercel"
  done
  popd > /dev/null
}

case "$TARGET" in
  fly)    sync_fly ;;
  vercel) sync_vercel ;;
  all)    sync_fly; sync_vercel ;;
  *)      echo "Usage: $0 {fly|vercel|all}"; exit 1 ;;
esac

log "Termin\u00e9. Pense \u00e0 lancer: fly deploy --app $FLY_APP && (cd $VERCEL_DIR && vercel --prod)"
