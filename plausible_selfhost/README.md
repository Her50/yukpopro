# Plausible CE self-hosted sur Fly.io

Déploiement Plausible Community Edition pour Yukpo (analytics web RGPD, gratuit illimité, sans cookies tiers).

## Architecture

```
                 plausible.yukpomnang.com
                          │
                          ▼
              ┌─────────────────────────┐
              │  yukpo-plausible (Fly)  │  ← Phoenix/Elixir app
              │       perf-1x CDG       │
              └────┬──────────────┬─────┘
                   │              │
        DATABASE_URL          CLICKHOUSE_DATABASE_URL
                   │              │
                   ▼              ▼
        ┌──────────────┐  ┌──────────────────┐
        │  Postgres    │  │   Clickhouse     │
        │  Fly managed │  │   Fly app perf-1x│
        │  (sessions)  │  │   (events colonn.)│
        └──────────────┘  └──────────────────┘
```

## Setup pas à pas

### 1. Créer les apps Fly (3 apps)

```bash
cd plausible_selfhost

# App principale Plausible
fly launch --name yukpo-plausible --copy-config --no-deploy --region cdg

# Postgres managed Fly (sessions, sites, users)
fly postgres create --name yukpo-plausible-pg \
    --region cdg --vm-size shared-cpu-1x --volume-size 3 --initial-cluster-size 1

# Clickhouse — pas managé par Fly, on déploie une app dédiée
# (ou alternative payante : Clickhouse Cloud / Aiven)
fly launch --name yukpo-plausible-ch --no-deploy --region cdg \
    --image clickhouse/clickhouse-server:24.3
```

### 2. Volumes persistants

```bash
fly volume create plausible_data       --size 5  --region cdg --app yukpo-plausible
fly volume create plausible_clickhouse --size 10 --region cdg --app yukpo-plausible-ch
```

### 3. Attacher Postgres + récupérer DATABASE_URL

```bash
fly postgres attach yukpo-plausible-pg --app yukpo-plausible
# → injecte DATABASE_URL automatiquement
```

### 4. Configurer les secrets Plausible

```bash
SECRET_KEY=$(openssl rand -base64 48)

fly secrets set --app yukpo-plausible \
  SECRET_KEY_BASE=$SECRET_KEY \
  TOTP_VAULT_KEY=$(openssl rand -base64 32) \
  CLICKHOUSE_DATABASE_URL=http://yukpo-plausible-ch.internal:8123/plausible_events_db \
  HTTP_PORT=8000 \
  LISTEN_IP=0.0.0.0 \
  MAILER_EMAIL=no-reply@yukpomnang.com
```

(Optionnel — pour envoyer les emails Plausible : ajouter SMTP_* ou réutiliser SendGrid)

### 5. Déployer les 3 apps

```bash
fly deploy --app yukpo-plausible-ch  # Clickhouse d'abord
fly deploy --app yukpo-plausible      # Plausible ensuite
```

### 6. DNS Cloudflare

Dans dash.cloudflare.com → zone yukpomnang.com → DNS → Add :
- Type `CNAME`, Name `plausible`, Target `yukpo-plausible.fly.dev`, Proxy **DNS only** (gris), TTL Auto

→ `plausible.yukpomnang.com` est accessible. Plausible auto-provisionne le TLS via Fly.

### 7. Premier admin Plausible

```bash
fly ssh console -a yukpo-plausible
$ /app/bin/plausible eval "Plausible.Auth.create_admin_user(\"admin@yukpomnang.com\", \"motdepasse\")"
```

Puis se connecter à https://plausible.yukpomnang.com avec ces credentials.

### 8. Créer la clé API

Dashboard Plausible → Settings → API Keys → Generate.

### 9. Configurer YukpoPro pour pointer sur ce Plausible

```bash
fly secrets set -a yukpopro-backend \
  PLAUSIBLE_API_BASE=https://plausible.yukpomnang.com/api/v1 \
  PLAUSIBLE_SCRIPT_URL=https://plausible.yukpomnang.com/js/script.js \
  PLAUSIBLE_API_KEY=<clé générée à l'étape 8>
```

### 10. Ajouter chaque sous-domaine landing/site/shop publié

Pour chaque `<slug>.yukpomnang.com` qu'un user publie, Plausible doit avoir le site enregistré (sinon il refuse les events). Deux options :

**A. Manuel** : dashboard Plausible → Add Site pour chaque slug à mesure.

**B. Auto** : étendre `landing_publisher.py` pour appeler `POST /api/v1/sites` Plausible API au moment de la publication. À faire en Sprint follow-up.

## Coûts mensuels estimés

| Composant | Spec | Coût |
|---|---|---|
| yukpo-plausible (Phoenix) | perf-1x 1GB auto-stop | ~$3/mois |
| yukpo-plausible-pg (Postgres) | shared-cpu-1x 3GB | ~$2/mois |
| yukpo-plausible-ch (Clickhouse) | shared-cpu-1x 2GB | ~$4/mois |
| Volumes (15 GB total) | | ~$2/mois |
| **Total** | | **~$11/mois** |

Pour <100k pageviews/mois. Au-delà, scale Clickhouse à perf-2x (~$10/mois additionnels).

## Alternative : Plausible Cloud

Si tu ne veux pas gérer 3 apps Fly + Clickhouse, abonnement Plausible Cloud à $9-19/mois est plus simple :

```bash
fly secrets set -a yukpopro-backend \
  PLAUSIBLE_API_BASE=https://plausible.io/api/v1 \
  PLAUSIBLE_SCRIPT_URL=https://plausible.io/js/script.js \
  PLAUSIBLE_API_KEY=<clé Plausible Cloud>
```

## Désactivation propre

```bash
fly apps destroy yukpo-plausible
fly apps destroy yukpo-plausible-pg
fly apps destroy yukpo-plausible-ch
# Puis retirer côté backend :
fly secrets unset -a yukpopro-backend PLAUSIBLE_API_BASE PLAUSIBLE_SCRIPT_URL PLAUSIBLE_API_KEY
```
