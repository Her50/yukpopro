#!/usr/bin/env bash
# Wrapper sécurisé pour `fly deploy`.
#
# Problème observé en prod (mai 2026) : `fly deploy` peut renvoyer "timeout
# waiting for health checks" alors que la machine reste en état `stopped`
# avec un lease orphelin. Le proxy Fly ne route alors AUCUNE requête vers
# la machine pendant ~5-10 min (PM01 errors), bloquant les téléchargements
# user qui voient "Erreur de connexion".
#
# Ce wrapper :
#   1. Run `fly deploy --remote-only` (idempotent)
#   2. Poll /health publique jusqu'à 200 (max 90s)
#   3. Si pas 200 → tente `fly machine restart` + nouveau poll
#   4. Si toujours KO → fly machine start + alerte
#   5. Exit non-zéro si vraiment KO pour qu'un CI échoue proprement
#
# Usage :
#   cd yukpo_assurance/
#   ./scripts/fly_deploy_safe.sh
#
# Override URL si app différente :
#   HEALTH_URL=https://other-app.fly.dev/health ./scripts/fly_deploy_safe.sh

set -euo pipefail

APP_NAME="${FLY_APP_NAME:-yukpopro-backend}"
HEALTH_URL="${HEALTH_URL:-https://${APP_NAME}.fly.dev/health}"
MAX_WAIT_S="${MAX_WAIT_S:-90}"
POLL_INTERVAL_S="${POLL_INTERVAL_S:-3}"

log() { echo "[$(date +%H:%M:%S)] $*" >&2; }

# Polling /health avec timeout. Retourne 0 si OK, 1 sinon.
wait_health() {
    local deadline=$(( $(date +%s) + MAX_WAIT_S ))
    log "Attente /health 200 (max ${MAX_WAIT_S}s)…"
    while [ "$(date +%s)" -lt "$deadline" ]; do
        local code
        code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$HEALTH_URL" 2>/dev/null || echo "000")
        if [ "$code" = "200" ]; then
            log "✓ /health = 200 OK"
            return 0
        fi
        log "… /health = $code (encore ${POLL_INTERVAL_S}s avant retry)"
        sleep "$POLL_INTERVAL_S"
    done
    log "✗ Timeout ${MAX_WAIT_S}s — /health pas 200"
    return 1
}

# Trouve l'ID machine actuelle (1 seule machine en config scale-to-zero)
get_machine_id() {
    fly machine list --json 2>/dev/null \
        | python3 -c "import sys,json;d=json.load(sys.stdin);print(d[0]['id'] if d else '')" \
        2>/dev/null || true
}

log "═══════════════════════════════════════════════════════════════"
log "Fly safe deploy → app=$APP_NAME · health=$HEALTH_URL"
log "═══════════════════════════════════════════════════════════════"

# Étape 1 — Deploy normal
log "Étape 1/3 : fly deploy --remote-only"
set +e
fly deploy --remote-only
DEPLOY_RC=$?
set -e

if [ "$DEPLOY_RC" -eq 0 ]; then
    log "Deploy CLI a renvoyé 0 — vérification health post-deploy…"
else
    log "Deploy CLI a renvoyé $DEPLOY_RC (timeout health check probable)"
    log "On vérifie quand même /health avant de paniquer (le lease peut juste être encore actif)"
fi

# Étape 2 — Health check
if wait_health; then
    log "═══════════════════════════════════════════════════════════════"
    log "✓ DEPLOY OK — app répond /health"
    log "═══════════════════════════════════════════════════════════════"
    exit 0
fi

# Étape 3 — Recovery : machine restart
log "Étape 2/3 : tentative recovery — fly machine restart"
MID=$(get_machine_id)
if [ -z "$MID" ]; then
    log "✗ Impossible de récupérer l'ID machine"
    exit 2
fi
log "  Machine ID = $MID"

set +e
fly machine restart "$MID"
RESTART_RC=$?
set -e

if [ "$RESTART_RC" -ne 0 ]; then
    log "  Restart échec — tentative start"
    fly machine start "$MID" || true
fi

# Re-poll health après restart
if wait_health; then
    log "═══════════════════════════════════════════════════════════════"
    log "✓ DEPLOY OK APRÈS RECOVERY"
    log "═══════════════════════════════════════════════════════════════"
    exit 0
fi

# Étape 4 — Vraie panne
log "═══════════════════════════════════════════════════════════════"
log "✗ DEPLOY EN PANNE — investigation manuelle requise"
log "  fly logs --no-tail"
log "  fly status"
log "  fly machine list"
log "═══════════════════════════════════════════════════════════════"
exit 3
