# État du self-host Plausible — étapes restantes

## ✅ Fait (session 2026-05-13)

1. **App `yukpo-plausible`** créée (vide, pas encore déployée)
2. **App `yukpo-plausible-ch`** créée (Clickhouse, vide)
3. **Postgres `yukpo-plausible-pg`** opérationnel :
   - Hostname interne : `yukpo-plausible-pg.flycast:5432`
   - Hostname interne : `yukpo-plausible-pg.internal:5432`
   - Username : `postgres`
   - **Password** : affiché dans la sortie de `fly postgres create yukpo-plausible-pg`
     — Hernandez l'a sauvegardé côté terminal (NON committé en clair ici par sécurité)
   - Format connection string : `postgres://postgres / <PWD> @ yukpo-plausible-pg.flycast / 5432` (EXEMPLE — substituer les vrais credentials)
   - Pour récupérer si perdu : `fly pg connect -a yukpo-plausible-pg` (Fly utilise
     les credentials internes automatiquement) ou re-créer un user avec
     `CREATE USER plausible WITH PASSWORD '...' SUPERUSER;`

## ⏸ Restant — étapes interactives à faire toi-même

### 1. Créer la base `plausible` dans le cluster Postgres

```powershell
fly pg connect -a yukpo-plausible-pg
# Dans le prompt psql :
CREATE DATABASE plausible_db;
CREATE USER plausible WITH PASSWORD '<EXAMPLE_GENERER_UN_MOT_DE_PASSE_FORT>' SUPERUSER;
GRANT ALL PRIVILEGES ON DATABASE plausible_db TO plausible;
\q
```

### 2. Déployer Clickhouse (app `yukpo-plausible-ch`)

Crée un dossier `plausible_selfhost/clickhouse/` avec un `fly.toml` Clickhouse minimal + Dockerfile basé sur `clickhouse/clickhouse-server:24.3`. Cf. https://fly.io/docs/app-guides/run-a-clickhouse-server/

Ou plus simple : **utiliser Clickhouse Cloud** ($25/mois starter, $0 trial 30j) — pas de setup infra :
- https://clickhouse.cloud → Create service → région `eu-central` (proche CDG)
- Récupère hostname + user + password
- Connection string format : `clickhouse://default:PASSWORD@HOST:8443/plausible_events_db?secure=1`

### 3. Volume Plausible app

```powershell
fly volume create plausible_data --size 5 --region cdg --app yukpo-plausible -y
```

### 4. Secrets Plausible app

```powershell
$secret = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 48 | % {[char]$_})
$totp = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | % {[char]$_})

fly secrets set -a yukpo-plausible `
  SECRET_KEY_BASE=$secret `
  TOTP_VAULT_KEY=$totp `
  DATABASE_URL="<format-EXEMPLE-substituer: postgres scheme avec user 'plausible' + VOTRE_MOT_DE_PASSE + host yukpo-plausible-pg.flycast port 5432 db plausible_db>" `
  CLICKHOUSE_DATABASE_URL="<TON_CLICKHOUSE_URL_ETAPE_2>" `
  HTTP_PORT=8000 `
  LISTEN_IP=0.0.0.0 `
  MAILER_EMAIL=no-reply@yukpomnang.com
```

### 5. Deploy Plausible

```powershell
cd plausible_selfhost
fly deploy --app yukpo-plausible --remote-only
```

### 6. DNS Cloudflare — CNAME spécifique AVANT le wildcard

⚠️ Important : le wildcard `*.yukpomnang.com → Netlify` capte aussi `plausible.yukpomnang.com`. Il FAUT ajouter un record CNAME spécifique pour `plausible` qui prend priorité :

- Type **CNAME**, Name **plausible**, Target **yukpo-plausible.fly.dev**, Proxy **DNS only** (gris)

Le record spécifique précède le wildcard automatiquement.

### 7. Premier admin Plausible

```powershell
fly ssh console -a yukpo-plausible
/app/bin/plausible eval "Plausible.Auth.create_admin_user(\"admin@yukpomnang.com\", \"motdepasse_changeme\")"
exit
```

### 8. Login + créer API key

- https://plausible.yukpomnang.com (login admin)
- Settings → API Keys → **+ New API Key** → copie

### 9. Poser les secrets côté YukpoPro

```powershell
fly secrets set -a yukpopro-backend `
  PLAUSIBLE_API_KEY="<CLE_ETAPE_8>" `
  PLAUSIBLE_API_BASE=https://plausible.yukpomnang.com/api/v1 `
  PLAUSIBLE_SCRIPT_URL=https://plausible.yukpomnang.com/js/script.js
```

## Coût mensuel total une fois tout déployé

| Composant | Coût |
|---|---|
| yukpo-plausible (perf-1x auto-stop) | ~$3/mois |
| yukpo-plausible-pg (Postgres) | ~$2/mois |
| Clickhouse Cloud (alternative recommandée) OU yukpo-plausible-ch self-hosted | ~$25/mois OU ~$4/mois |
| Volume 5 GB | ~$1/mois |
| **Total** | **~$10-31/mois** |

## Si tu veux annuler proprement

```powershell
fly apps destroy yukpo-plausible -y
fly apps destroy yukpo-plausible-ch -y
fly postgres destroy yukpo-plausible-pg -y
```

Les apps sont GRATUITES tant que tu ne les déploies pas (0 machine running).
