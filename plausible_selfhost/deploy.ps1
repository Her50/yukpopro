# Script de déploiement complet Plausible CE self-host sur Fly.io
#
# Pré-requis :
#   - fly CLI installée et authentifiée (fly auth whoami)
#   - Postgres yukpo-plausible-pg déjà créé et UP (cf STATE.md)
#
# Étapes automatisées :
#   1. Crée la DB plausible_db + user plausible (mot de passe auto-généré)
#   2. Déploie Clickhouse sur yukpo-plausible-ch (volume 10GB)
#   3. Crée le volume Plausible (5GB) + pose les secrets + déploie l'app
#
# Étapes restant à faire manuellement APRÈS ce script :
#   A. Cloudflare DNS : CNAME plausible → yukpo-plausible.fly.dev (proxy off)
#   B. fly certs create plausible.yukpomnang.com -a yukpo-plausible
#   C. Premier admin : fly ssh console -a yukpo-plausible puis bin/plausible eval
#   D. Login UI + créer API key → poser PLAUSIBLE_API_KEY sur yukpopro-backend
#
# Usage : .\deploy.ps1
#
# Idempotent : si l'app/volume/secret existe déjà, l'étape est sautée.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $ScriptDir

function New-RandomPassword {
    param([int]$Length = 32)
    $chars = (48..57) + (65..90) + (97..122)  # alphanum sans symboles (compat URL)
    -join ($chars | Get-Random -Count $Length | ForEach-Object { [char]$_ })
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Plausible CE — déploiement Fly.io"      -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ─── 1. Vérifs ───────────────────────────────────────────────────────────────
Write-Host "[1/6] Vérifications préalables..." -ForegroundColor Yellow

$pgStatus = fly status -a yukpo-plausible-pg 2>&1 | Out-String
if ($pgStatus -notmatch "started") {
    throw "Postgres yukpo-plausible-pg n'est pas UP. Vérifie 'fly status -a yukpo-plausible-pg'."
}
Write-Host "  ✓ Postgres yukpo-plausible-pg UP" -ForegroundColor Green

# ─── 2. Mot de passe Plausible user Postgres ─────────────────────────────────
Write-Host ""
Write-Host "[2/6] Génération credentials Postgres..." -ForegroundColor Yellow

$pgPassFile = Join-Path $ScriptDir ".plausible-pg-pass.txt"
if (Test-Path $pgPassFile) {
    $pgPass = Get-Content $pgPassFile -Raw
    $pgPass = $pgPass.Trim()
    Write-Host "  ✓ Mot de passe Postgres existant réutilisé (.plausible-pg-pass.txt)" -ForegroundColor Green
} else {
    $pgPass = New-RandomPassword -Length 40
    Set-Content -Path $pgPassFile -Value $pgPass -Encoding utf8 -NoNewline
    Write-Host "  ✓ Nouveau mot de passe Postgres généré et sauvegardé localement" -ForegroundColor Green
    Write-Host "  ⚠ FICHIER LOCAL .plausible-pg-pass.txt — NE PAS COMMITTER (déjà gitignored)" -ForegroundColor Yellow
}

# Création DB + user via attach (méthode officielle Fly Postgres Flex)
# Cf https://fly.io/docs/postgres/managing/attach-detach/
# On utilise PSQL en SSH plutôt qu'attach pour pouvoir réutiliser un user dédié.
Write-Host ""
Write-Host "[3/6] Création DB plausible_db + user plausible..." -ForegroundColor Yellow

$sql = @"
DO `$`$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname='plausible_db') THEN
    CREATE DATABASE plausible_db;
  END IF;
END
`$`$;
DO `$`$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='plausible') THEN
    CREATE USER plausible WITH PASSWORD '$pgPass' SUPERUSER;
  ELSE
    ALTER USER plausible WITH PASSWORD '$pgPass';
  END IF;
END
`$`$;
GRANT ALL PRIVILEGES ON DATABASE plausible_db TO plausible;
"@

# Encode SQL en base64 et exécute via fly ssh
$sqlB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($sql))
$cmd = "echo '$sqlB64' | base64 -d | psql -U postgres"
fly ssh console -a yukpo-plausible-pg --command "/bin/sh -c `"$cmd`""
if ($LASTEXITCODE -ne 0) { throw "Échec création DB plausible_db" }
Write-Host "  ✓ DB plausible_db + user plausible OK" -ForegroundColor Green

# ─── 4. Clickhouse deploy ────────────────────────────────────────────────────
Write-Host ""
Write-Host "[4/6] Déploiement Clickhouse..." -ForegroundColor Yellow

$chVolumes = fly volumes list -a yukpo-plausible-ch 2>&1 | Out-String
if ($chVolumes -notmatch "clickhouse_data") {
    fly volumes create clickhouse_data --size 10 --region cdg --app yukpo-plausible-ch -y
    if ($LASTEXITCODE -ne 0) { throw "Échec création volume clickhouse_data" }
    Write-Host "  ✓ Volume clickhouse_data (10GB) créé" -ForegroundColor Green
} else {
    Write-Host "  ✓ Volume clickhouse_data existant" -ForegroundColor Green
}

Push-Location (Join-Path $ScriptDir "clickhouse")
fly deploy --app yukpo-plausible-ch --remote-only
$chDeploy = $LASTEXITCODE
Pop-Location
if ($chDeploy -ne 0) { throw "Échec déploiement Clickhouse" }
Write-Host "  ✓ Clickhouse déployé" -ForegroundColor Green

$clickhouseUrl = "http://default:@yukpo-plausible-ch.flycast:8123/plausible_events_db"

# ─── 5. Plausible app — volume + secrets + deploy ────────────────────────────
Write-Host ""
Write-Host "[5/6] Déploiement Plausible app..." -ForegroundColor Yellow

$plVolumes = fly volumes list -a yukpo-plausible 2>&1 | Out-String
if ($plVolumes -notmatch "plausible_data") {
    fly volumes create plausible_data --size 5 --region cdg --app yukpo-plausible -y
    if ($LASTEXITCODE -ne 0) { throw "Échec création volume plausible_data" }
    Write-Host "  ✓ Volume plausible_data (5GB) créé" -ForegroundColor Green
} else {
    Write-Host "  ✓ Volume plausible_data existant" -ForegroundColor Green
}

$secretKeyBase = New-RandomPassword -Length 64
$totpVaultKey = New-RandomPassword -Length 48

$databaseUrl = "postgres://plausible:$pgPass@yukpo-plausible-pg.flycast:5432/plausible_db"

fly secrets set -a yukpo-plausible `
  SECRET_KEY_BASE=$secretKeyBase `
  TOTP_VAULT_KEY=$totpVaultKey `
  DATABASE_URL="$databaseUrl" `
  CLICKHOUSE_DATABASE_URL="$clickhouseUrl" `
  HTTP_PORT=8000 `
  LISTEN_IP=0.0.0.0 `
  MAILER_EMAIL=no-reply@yukpomnang.com `
  DISABLE_REGISTRATION=invite_only
if ($LASTEXITCODE -ne 0) { throw "Échec pose secrets Plausible" }
Write-Host "  ✓ Secrets posés" -ForegroundColor Green

fly deploy --app yukpo-plausible --remote-only
if ($LASTEXITCODE -ne 0) { throw "Échec déploiement Plausible" }
Write-Host "  ✓ Plausible déployé" -ForegroundColor Green

# ─── 6. Étapes manuelles restantes ───────────────────────────────────────────
Write-Host ""
Write-Host "[6/6] Étapes manuelles restantes" -ForegroundColor Yellow
Write-Host ""
Write-Host "  A. Cloudflare DNS :"                                                 -ForegroundColor Cyan
Write-Host "       Type CNAME | Name plausible | Target yukpo-plausible.fly.dev"
Write-Host "       Proxy : DNS only (nuage gris, PAS orange)"
Write-Host ""
Write-Host "  B. Certificat TLS Fly :"                                             -ForegroundColor Cyan
Write-Host "       fly certs create plausible.yukpomnang.com -a yukpo-plausible"
Write-Host ""
Write-Host "  C. Premier admin (substituer email + mot de passe) :"                -ForegroundColor Cyan
Write-Host "       fly ssh console -a yukpo-plausible"
Write-Host "       /app/bin/plausible eval 'Plausible.Auth.create_user!(`"admin@yukpomnang.com`", `"YourStrongPassword`")'"
Write-Host ""
Write-Host "  D. Login UI : https://plausible.yukpomnang.com"                       -ForegroundColor Cyan
Write-Host "       Settings → API Keys → New → copier la clé"
Write-Host ""
Write-Host "  E. Pose côté YukpoPro :"                                              -ForegroundColor Cyan
Write-Host "       fly secrets set -a yukpopro-backend ``"
Write-Host "         PLAUSIBLE_API_KEY=`"<CLE_COPIEE>`" ``"
Write-Host "         PLAUSIBLE_API_BASE=https://plausible.yukpomnang.com/api/v1 ``"
Write-Host "         PLAUSIBLE_SCRIPT_URL=https://plausible.yukpomnang.com/js/script.js"
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " Déploiement Plausible self-host : OK"   -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green

Pop-Location
