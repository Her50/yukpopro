﻿﻿# Script de déploiement complet Plausible CE self-host sur Fly.io
#
# Pré-requis :
#   - fly CLI authentifiée (fly auth whoami)
#   - Python 3 + psycopg2 installés localement (déjà OK sur ce poste)
#   - Compte Fly avec droits création apps + Postgres
#
# Étapes automatisées :
#   1. Crée si besoin : app yukpo-plausible, app yukpo-plausible-ch,
#      cluster Postgres yukpo-plausible-pg
#   2. Crée la DB plausible_db + user 'plausible' avec hash md5
#      (compat pg_hba.conf des Postgres Flex pour IPv6 inter-app)
#   3. Crée volumes (5GB plausible + 10GB clickhouse)
#   4. Déploie Clickhouse (dual-stack IPv6, config corrigée)
#   5. Pré-crée la base 'plausible_events_db' dans Clickhouse
#   6. Pose secrets Plausible (SECRET_KEY_BASE/TOTP_VAULT_KEY en base64,
#      DATABASE_URL avec .internal, ECTO_IPV6=true, pool size adapté)
#   7. Déploie Plausible avec Dockerfile patché (migrate avant start)
#   8. Alloue IPs publiques + crée certificat TLS pour le domaine
#
# Étapes manuelles APRÈS ce script (voir STATE.md) :
#   A. Cloudflare DNS : CNAME plausible -> yukpo-plausible.fly.dev (proxy off)
#   B. Premier admin via fly ssh + Plausible.Auth.create_user!
#   C. Login UI -> Settings -> API Keys -> New
#   D. Pose PLAUSIBLE_API_KEY sur yukpopro-backend
#
# Usage : .\deploy.ps1
# Idempotent : tout réutilise l'existant. Sûr de re-lancer après échec.

# Note : on garde Continue (pas Stop) car la moindre ligne stderr d'un .exe natif
# (warnings fly, progress bars docker) ferait avorter le script en Stop mode.
# On verifie explicitement $LASTEXITCODE apres chaque commande critique.
$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $ScriptDir

$APP_PLAUSIBLE = "yukpo-plausible"
$APP_CLICKHOUSE = "yukpo-plausible-ch"
$APP_POSTGRES = "yukpo-plausible-pg"
$REGION = "cdg"

function Write-Step($msg) { Write-Host ""; Write-Host $msg -ForegroundColor Yellow }
function Write-Ok($msg)   { Write-Host "  + $msg" -ForegroundColor Green }
function Write-Info($msg) { Write-Host "  i $msg" -ForegroundColor Cyan }
function Write-Warn($msg) { Write-Host "  ! $msg" -ForegroundColor Yellow }

function Invoke-PythonBlock {
    param([string]$Code)
    # Use Python's stdin to avoid quoting issues, capture both stdout/stderr,
    # return exit code via $LASTEXITCODE.
    $tmp = [IO.Path]::GetTempFileName()
    try {
        [IO.File]::WriteAllText($tmp, $Code, [Text.UTF8Encoding]::new($false))
        & python $tmp
    } finally {
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    }
}

function Test-FlyApp($name) {
    # fly status -a <missing> writes to stderr AND exits non-zero.
    # PS 5.1 in StrictMode treats stderr lines as NativeCommandError if
    # $ErrorActionPreference="Stop". Use try/catch + suppress to avoid abort.
    $existed = $false
    try {
        $out = & fly status -a $name 2>&1
        if ($LASTEXITCODE -eq 0) { $existed = $true }
    } catch {
        # NativeCommandError swallow
    }
    return $existed
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host " Plausible CE - deploiement Fly.io (patche v2)"  -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan

# ============================================================================
# Step 1 : Verifs prerequis
# ============================================================================
Write-Step "[1/8] Verifications prerequis..."

fly auth whoami 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { throw "fly CLI non authentifie. Lance 'fly auth login'." }
Write-Ok "fly CLI authentifie"

$pyCheck = & python -c "import psycopg2; print('OK')" 2>&1
if ($pyCheck -notmatch "OK") { throw "Python + psycopg2 requis : pip install psycopg2-binary" }
Write-Ok "Python + psycopg2 disponibles"

# ============================================================================
# Step 2 : Postgres - cree le cluster si absent
# ============================================================================
Write-Step "[2/8] Cluster Postgres ($APP_POSTGRES)..."

if (-not (Test-FlyApp $APP_POSTGRES)) {
    Write-Info "Creation du cluster Postgres Flex (peut prendre 2-3 min)..."
    fly postgres create `
        --name $APP_POSTGRES `
        --region $REGION `
        --initial-cluster-size 1 `
        --vm-size shared-cpu-1x `
        --volume-size 3 `
        --org personal
    if ($LASTEXITCODE -ne 0) { throw "Echec creation cluster Postgres" }
    Write-Ok "Cluster Postgres $APP_POSTGRES cree"
} else {
    Write-Ok "Cluster Postgres $APP_POSTGRES existe"
}

# Retrieve OPERATOR_PASSWORD (postgres user pwd) from the container env
Write-Info "Recuperation OPERATOR_PASSWORD depuis le container Postgres..."
$pgOpPass = (fly ssh console -a $APP_POSTGRES --command "printenv OPERATOR_PASSWORD" 2>&1 |
             Select-String -Pattern "^[A-Za-z0-9]{10,}$" |
             Select-Object -First 1).Line
if ([string]::IsNullOrWhiteSpace($pgOpPass)) {
    throw "Impossible de recuperer OPERATOR_PASSWORD. Lance 'fly ssh console -a $APP_POSTGRES' puis 'printenv OPERATOR_PASSWORD' manuellement."
}
Write-Ok "OPERATOR_PASSWORD recupere ($($pgOpPass.Length) chars)"

# ============================================================================
# Step 3 : Apps Plausible + Clickhouse - cree si absent
# ============================================================================
Write-Step "[3/8] Apps Plausible + Clickhouse..."

if (-not (Test-FlyApp $APP_PLAUSIBLE)) {
    fly apps create $APP_PLAUSIBLE --org personal
    if ($LASTEXITCODE -ne 0) { throw "Echec creation app $APP_PLAUSIBLE" }
    Write-Ok "App $APP_PLAUSIBLE creee"
} else {
    Write-Ok "App $APP_PLAUSIBLE existe"
}

if (-not (Test-FlyApp $APP_CLICKHOUSE)) {
    fly apps create $APP_CLICKHOUSE --org personal
    if ($LASTEXITCODE -ne 0) { throw "Echec creation app $APP_CLICKHOUSE" }
    Write-Ok "App $APP_CLICKHOUSE creee"
} else {
    Write-Ok "App $APP_CLICKHOUSE existe"
}

# ============================================================================
# Step 4 : Genere/lit le mot de passe user plausible (SANS BOM)
# ============================================================================
Write-Step "[4/8] Mot de passe user 'plausible' (PG)..."

$pgPassFile = Join-Path $ScriptDir ".plausible-pg-pass.txt"
if (Test-Path $pgPassFile) {
    # Read raw bytes and strip any BOM (PS 5.1 add UTF-8 BOM by default)
    $rawBytes = [IO.File]::ReadAllBytes($pgPassFile)
    if ($rawBytes.Length -ge 3 -and $rawBytes[0] -eq 0xEF -and $rawBytes[1] -eq 0xBB -and $rawBytes[2] -eq 0xBF) {
        $rawBytes = $rawBytes[3..($rawBytes.Length - 1)]
    }
    $pgUserPass = [Text.Encoding]::ASCII.GetString($rawBytes).Trim()
    Write-Ok "Mot de passe existant reutilise (sans BOM, $($pgUserPass.Length) chars)"
} else {
    # Generate via Python for portability + crypto strength
    $genCode = @"
import secrets, string
pw = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(40))
import sys
sys.stdout.write(pw)
"@
    $pgUserPass = (Invoke-PythonBlock $genCode).Trim()
    if ($pgUserPass.Length -ne 40) { throw "Generation mot de passe a echoue" }
    # Save WITHOUT BOM as pure ASCII bytes
    [IO.File]::WriteAllBytes($pgPassFile, [Text.Encoding]::ASCII.GetBytes($pgUserPass))
    Write-Ok "Nouveau mot de passe genere (40 chars ASCII, sans BOM)"
    Write-Warn "Fichier local .plausible-pg-pass.txt (gitignored, NE PAS COMMITTER)"
}

# ============================================================================
# Step 5 : Cree DB plausible_db + user 'plausible' via fly proxy
# ============================================================================
Write-Step "[5/8] DB plausible_db + user 'plausible' (hash md5)..."

# Lance fly proxy 5435 -> Postgres en arriere-plan, attend, lance Python.
# Port 5435 (pas 5432) pour eviter conflit avec eventuel Postgres local.
$proxyJob = Start-Job -ScriptBlock {
    param($app)
    & fly proxy 5435:5432 -a $app 2>&1
} -ArgumentList $APP_POSTGRES

Start-Sleep -Seconds 4  # proxy needs ~3-4s to establish wireguard tunnel

$pythonSetup = @"
import psycopg2, sys, time
OP = '$pgOpPass'
PW = '$pgUserPass'
for attempt in range(8):
    try:
        c = psycopg2.connect(host='127.0.0.1', port=5435, user='postgres', password=OP, dbname='postgres', connect_timeout=10)
        break
    except Exception as e:
        if attempt == 7:
            print(f'ERROR: connection failed after retries: {e}', file=sys.stderr)
            sys.exit(1)
        time.sleep(3)
c.autocommit = True
cur = c.cursor()
# Force md5 hash (compat pg_hba.conf default des Postgres Flex pour ::0/0)
cur.execute("SET password_encryption = 'md5'")
cur.execute("SELECT 1 FROM pg_database WHERE datname='plausible_db'")
if not cur.fetchone():
    cur.execute("CREATE DATABASE plausible_db")
    print('DB plausible_db creee')
else:
    print('DB plausible_db existe')
cur.execute("SELECT 1 FROM pg_roles WHERE rolname='plausible'")
if not cur.fetchone():
    cur.execute("CREATE USER plausible WITH PASSWORD %s SUPERUSER", (PW,))
    print("user 'plausible' cree (md5)")
else:
    cur.execute("ALTER USER plausible WITH PASSWORD %s SUPERUSER", (PW,))
    print("user 'plausible' mot de passe mis a jour (md5)")
cur.execute("GRANT ALL PRIVILEGES ON DATABASE plausible_db TO plausible")
# Verifie que le hash est bien md5
cur.execute("SELECT substring(rolpassword, 1, 3) FROM pg_authid WHERE rolname='plausible'")
prefix = cur.fetchone()[0]
print(f'hash prefix: {prefix}')
if prefix != 'md5':
    print('WARNING: password hash is NOT md5 - pg_hba.conf will reject IPv6 connections', file=sys.stderr)
    sys.exit(1)
# Verifie connexion comme plausible user
c.close()
c2 = psycopg2.connect(host='127.0.0.1', port=5435, user='plausible', password=PW, dbname='plausible_db', connect_timeout=10)
print('user plausible auth OK')
c2.close()
"@

try {
    Invoke-PythonBlock $pythonSetup
    if ($LASTEXITCODE -ne 0) { throw "Setup DB plausible_db echec" }
} finally {
    Stop-Job $proxyJob -ErrorAction SilentlyContinue
    Remove-Job $proxyJob -Force -ErrorAction SilentlyContinue
}
Write-Ok "DB + user 'plausible' configures avec hash md5"

# ============================================================================
# Step 6 : Volumes + deploy Clickhouse (dual-stack IPv6) + DB plausible_events_db
# ============================================================================
Write-Step "[6/8] Clickhouse - volume + deploy + DB..."

$chVolumes = fly volumes list -a $APP_CLICKHOUSE 2>&1 | Out-String
if ($chVolumes -notmatch "clickhouse_data") {
    fly volumes create clickhouse_data --size 10 --region $REGION --app $APP_CLICKHOUSE -y
    if ($LASTEXITCODE -ne 0) { throw "Echec creation volume clickhouse_data" }
    Write-Ok "Volume clickhouse_data (10GB) cree"
} else {
    Write-Ok "Volume clickhouse_data existant"
}

Push-Location (Join-Path $ScriptDir "clickhouse")
fly deploy --app $APP_CLICKHOUSE --remote-only
$chDeploy = $LASTEXITCODE
Pop-Location
if ($chDeploy -ne 0) { throw "Echec deploiement Clickhouse" }
Write-Ok "Clickhouse deploye (dual-stack IPv6)"

# Cree la DB plausible_events_db (idempotent grace au IF NOT EXISTS)
Write-Info "Creation DB Clickhouse plausible_events_db..."
fly ssh console -a $APP_CLICKHOUSE --command "clickhouse client -q 'CREATE DATABASE IF NOT EXISTS plausible_events_db'" 2>&1 | Out-Null
Write-Ok "DB Clickhouse plausible_events_db prete"

# ============================================================================
# Step 7 : Volume + secrets + deploy Plausible
# ============================================================================
Write-Step "[7/8] Plausible app - volume + secrets + deploy..."

$plVolumes = fly volumes list -a $APP_PLAUSIBLE 2>&1 | Out-String
if ($plVolumes -notmatch "plausible_data") {
    fly volumes create plausible_data --size 5 --region $REGION --app $APP_PLAUSIBLE -y
    if ($LASTEXITCODE -ne 0) { throw "Echec creation volume plausible_data" }
    Write-Ok "Volume plausible_data (5GB) cree"
} else {
    Write-Ok "Volume plausible_data existant"
}

# Generation secrets en base64 (formats requis par Plausible CE v2)
$secretsGenCode = @"
import secrets, base64
sk = base64.b64encode(secrets.token_bytes(48)).decode()  # 64 chars base64
tt = base64.b64encode(secrets.token_bytes(32)).decode()  # 44 chars base64 = 32 bytes raw (requis)
print(sk)
print(tt)
"@
$secretsLines = (Invoke-PythonBlock $secretsGenCode) -split "`r?`n" | Where-Object { $_ -ne "" }
$SECRET_KEY_BASE = $secretsLines[0]
$TOTP_VAULT_KEY = $secretsLines[1]

# .internal hostnames (pas .flycast) car migrate.sh appele au boot a besoin
# de DNS qui marche pour Postgres ET Clickhouse via 6PN inter-app.
$DATABASE_URL = "postgres://plausible:$pgUserPass@$APP_POSTGRES.internal:5432/plausible_db"
$CLICKHOUSE_DATABASE_URL = "http://default:@$APP_CLICKHOUSE.internal:8123/plausible_events_db"

Write-Info "Pose des 9 secrets Plausible..."
fly secrets set -a $APP_PLAUSIBLE `
    SECRET_KEY_BASE="$SECRET_KEY_BASE" `
    TOTP_VAULT_KEY="$TOTP_VAULT_KEY" `
    DATABASE_URL="$DATABASE_URL" `
    CLICKHOUSE_DATABASE_URL="$CLICKHOUSE_DATABASE_URL" `
    DATABASE_POOL_SIZE="10" `
    DATABASE_TLS_ENABLED="false" `
    ECTO_IPV6="true" `
    MAILER_EMAIL="no-reply@yukpomnang.com" `
    DISABLE_REGISTRATION="invite_only"
if ($LASTEXITCODE -ne 0) { throw "Echec pose secrets Plausible" }
Write-Ok "Secrets poses (9 dont ECTO_IPV6=true pour 6PN, pool_size=10)"

# Deploy : Dockerfile patche fait migrate avant start au 1er boot
Write-Info "Deploiement Plausible (peut prendre 2-3 min : pull image + migrate)..."
fly deploy --app $APP_PLAUSIBLE --remote-only --wait-timeout 300
if ($LASTEXITCODE -ne 0) { throw "Echec deploiement Plausible" }
Write-Ok "Plausible deploye (1er boot = migrate.sh puis start)"

# ============================================================================
# Step 8 : IPs publiques + certificat TLS
# ============================================================================
Write-Step "[8/8] IPs publiques + certificat TLS..."

$ipsList = fly ips list -a $APP_PLAUSIBLE 2>&1 | Out-String
if ($ipsList -notmatch "v4") {
    fly ips allocate-v4 --shared -a $APP_PLAUSIBLE | Out-Null
    Write-Ok "IPv4 partagee allouee"
} else {
    Write-Ok "IPv4 deja allouee"
}
if ($ipsList -notmatch "v6") {
    fly ips allocate-v6 -a $APP_PLAUSIBLE | Out-Null
    Write-Ok "IPv6 dediee allouee"
} else {
    Write-Ok "IPv6 deja allouee"
}

$certsList = fly certs list -a $APP_PLAUSIBLE 2>&1 | Out-String
if ($certsList -notmatch "plausible.yukpomnang.com") {
    fly certs create plausible.yukpomnang.com -a $APP_PLAUSIBLE | Out-Null
    Write-Ok "Certificat TLS cree pour plausible.yukpomnang.com (validation requise)"
} else {
    Write-Ok "Certificat plausible.yukpomnang.com existe"
}

# ============================================================================
# Recap final
# ============================================================================
Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host " Infrastructure Plausible : DEPLOYEE"            -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
Write-Host "ETAPES MANUELLES RESTANTES :" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. CLOUDFLARE DNS" -ForegroundColor Cyan
Write-Host "   https://dash.cloudflare.com -> zone yukpomnang.com -> DNS"
Write-Host "   Type    : CNAME"
Write-Host "   Name    : plausible"
Write-Host "   Target  : yukpo-plausible.fly.dev"
Write-Host "   Proxy   : DNS only (nuage GRIS - PAS orange)"
Write-Host ""
Write-Host "2. PREMIER ADMIN (1 min apres DNS propage)" -ForegroundColor Cyan
Write-Host "   fly ssh console -a yukpo-plausible"
Write-Host "   /app/bin/plausible eval 'Plausible.Auth.create_user!(`"admin@yukpomnang.com`", `"VOTRE_MDP_FORT`")'"
Write-Host "   exit"
Write-Host ""
Write-Host "3. LOGIN + API KEY" -ForegroundColor Cyan
Write-Host "   https://plausible.yukpomnang.com -> login admin"
Write-Host "   Settings -> API Keys -> + New API Key -> copier la cle"
Write-Host ""
Write-Host "4. POSE LA CLE COTE YUKPOPRO" -ForegroundColor Cyan
Write-Host "   fly secrets set -a yukpopro-backend ``"
Write-Host "     PLAUSIBLE_API_KEY=`"<CLE_COPIEE>`" ``"
Write-Host "     PLAUSIBLE_API_BASE=https://plausible.yukpomnang.com/api/v1 ``"
Write-Host "     PLAUSIBLE_SCRIPT_URL=https://plausible.yukpomnang.com/js/script.js"
Write-Host ""
Write-Host "5. VERIFIE LE STATUT" -ForegroundColor Cyan
Write-Host "   fly status -a yukpo-plausible           # machine 'started'"
Write-Host "   fly logs   -a yukpo-plausible           # cherche 'Access PlausibleWeb at http://0.0.0.0:8000'"
Write-Host "   curl -sI https://plausible.yukpomnang.com   # apres DNS + cert valides"
Write-Host ""

Pop-Location
