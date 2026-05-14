# État Plausible self-host sur Fly.io

## Statut actuel (2026-05-14)

Le **script `deploy.ps1` est entièrement patché** avec tous les écueils
rencontrés lors des 4 tentatives de déploiement. Il automatise :
- Création des 3 apps Fly (Postgres Flex + Clickhouse + Plausible)
- Mot de passe DB sans BOM PowerShell
- User `plausible` avec hash **md5** (compat `pg_hba.conf` Postgres Flex pour
  les connexions IPv6 inter-app `::0/0 md5`)
- `SECRET_KEY_BASE` + `TOTP_VAULT_KEY` générés en **base64** (32 bytes raw
  pour TOTP — sinon Plausible refuse au boot)
- Clickhouse config **dual-stack** (`<listen_host>::</listen_host>` SEUL —
  pas de `0.0.0.0` séparé sinon conflit "Address already in use")
- DB `plausible_events_db` pré-créée dans Clickhouse
- Secrets Plausible : `ECTO_IPV6=true`, `DATABASE_POOL_SIZE=10`,
  `DATABASE_TLS_ENABLED=false`, `.internal` hostnames (pas `.flycast`)

## ⚠️ Blocage architectural restant

Plausible CE v2.1.4 a un **timeout de queue Ecto hardcodé à ~6s** lors
de la migration. Sur Fly.io, la connexion Postgres inter-app (via flycast
ou .internal sur Wireguard IPv6) prend **5-8s** pour la première
acquisition de pool. Résultat : `(DBConnection.ConnectionError) connection
not available and request was dropped from queue after 5818ms` quand
`Ecto.Migrator.lock_for_migrations` essaie d'acquérir le lock.

**Cause** : pas un bug de notre infra, mais un mismatch Plausible/Fly.

### 3 voies pour débloquer (au choix selon budget)

#### Option A — Plausible Cloud (recommandé, 9$/mo, 0 effort)
- Skip self-host complet
- Créer compte sur https://plausible.io/register
- Plan starter = 10k pageviews/mois
- Garder le script local pour quand Plausible release la fix

```powershell
fly secrets set -a yukpopro-backend `
  PLAUSIBLE_API_KEY="<clé fournie par Plausible Cloud>" `
  PLAUSIBLE_API_BASE=https://plausible.io/api/v1 `
  PLAUSIBLE_SCRIPT_URL=https://plausible.io/js/script.js
```

#### Option B — Postgres managé externe (Neon, free tier)
- Crée un projet Neon https://neon.tech (Postgres serverless, 0.5GB free)
- Connection string : `postgres://user:pass@ep-xxx.eu-central-1.aws.neon.tech/neondb?sslmode=require`
- Latence connexion = **<300ms** au lieu de 6s sur Fly inter-app
- Patcher `deploy.ps1` : remplacer step 2 (création Postgres Flex) et step 5
  (DB+user) par "lit la URL Neon depuis `.env`"
- Le reste du script marche tel quel
- Économie : ~3$/mo (pas de Postgres Flex Fly)

#### Option C — Postgres + Clickhouse dans LA MÊME machine Plausible
- Restructure Dockerfile : embarque postgres + clickhouse + plausible
  via `supervisord` ou `s6-overlay` (architecture Plausible v1 d'origine)
- Latence connexion = **<10ms** (localhost)
- Effort : ~1 jour de bricolage Dockerfile + perte des avantages
  process-isolation Fly
- Pas recommandé sauf si vraiment self-host total exigé

## Comment relancer le script proprement

```powershell
# Si tu choisis Option B (Neon), édite d'abord plausible_selfhost\.env :
# DATABASE_URL=postgres://user:pass@ep-xxx.neon.tech/neondb?sslmode=require
# (le script lira cette URL au lieu de créer Postgres Flex)

cd plausible_selfhost
.\deploy.ps1
```

Le script est **idempotent** : tu peux le relancer autant de fois que tu
veux, il réutilise tout l'existant.

## Fichiers locaux (gitignored)

- `.plausible-pg-pass.txt` : mot de passe user `plausible` (ASCII pur, sans BOM)
- `.env` (à créer pour Option B) : `DATABASE_URL=postgres://...`

## Écueils résolus (changelog patches)

| # | Symptôme | Patch |
|---|---|---|
| 1 | `Échec création DB plausible_db` (fly ssh + base64 piping) | Utilise `fly proxy` + `psycopg2` Python local |
| 2 | `password authentication failed for user "plausible"` | `SET password_encryption='md5'` AVANT `ALTER USER` |
| 3 | `TOTP_VAULT_KEY must be Base64 encoded 32 bytes` | `base64.b64encode(secrets.token_bytes(32))` |
| 4 | Mot de passe avec BOM UTF-8 ≠ pw côté DB | `[IO.File]::WriteAllBytes` en ASCII pur |
| 5 | Clickhouse `Listen [::]:8123 failed: Address already in use` | UN seul `<listen_host>::</listen_host>` (dual-stack) |
| 6 | Clickhouse `A setting 'max_memory_usage' appeared at top level` | Settings user-level → `users.xml profiles`, pas `config.xml` |
| 7 | Plausible `Mint.TransportError, non-existing domain` (Clickhouse) | `ECTO_IPV6=true` + Clickhouse `listen_host=::` |
| 8 | Migrations bloquent au lock `connection dropped after 5818ms` | **PAS de patch côté infra** — voir Options A/B/C ci-dessus |
| 9 | PS 5.1 lit deploy.ps1 mal (caractères accentués) | Sauvegarde avec BOM UTF-8 (`b'\xef\xbb\xbf' + utf8_content`) |
| 10 | `$ErrorActionPreference="Stop"` avorte sur stderr fly | `="Continue"` + check explicite `$LASTEXITCODE` |

## Coût mensuel actuel (apps Fly créées, idle)

| App | Statut | Coût |
|---|---|---|
| yukpo-plausible-pg (shared-cpu-2x, 1GB, vol 3GB) | started | ~$5/mo |
| yukpo-plausible-ch (shared-cpu-2x, 2GB, vol 10GB) | started | ~$7/mo |
| yukpo-plausible (shared-cpu-1x, 1GB, vol 5GB) | stopped (auto-scale) | ~$1/mo |
| **Total** | | **~$13/mo** |

## Si tu veux tout détruire maintenant

```powershell
fly apps destroy yukpo-plausible -y
fly apps destroy yukpo-plausible-ch -y
fly apps destroy yukpo-plausible-pg -y
```
