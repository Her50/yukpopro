# Infrastructure Scaling — Guide d'activation

Ce guide détaille les **4 améliorations infra** prêtes côté code mais qui
nécessitent des actions manuelles (création comptes tiers, secrets Fly,
migration données) pour s'activer.

État au commit du jour :

| Amélioration | Code prêt ? | Action manuelle requise |
|---|---|---|
| 1. Cloudflare R2 (storage S3-compatible) | ✅ `core/storage.py` + boto3 | Créer compte Cloudflare R2 + 4 fly secrets |
| 2. Multi-région CDG + JNB | ✅ fly.toml documenté | `fly scale count` après R2 actif |
| 3. Worker vidéo dédié perf-8x | ✅ Celery routing `video_heavy` + entrypoint.sh `YUKPO_DISABLE_WEB` | Décommenter `[processes]` fly.toml + R2 actif |
| 4. Postgres dédié | ⏸ Pas de code spécifique | Créer DB Postgres dédiée + migration data |

---

## 1. Cloudflare R2 — storage S3-compatible illimité ($0.015/GB, egress GRATUIT)

### Pourquoi
- Volume Fly = 50 GB max raisonnable, region-specific (CDG seulement)
- À 5000+ users : volume insuffisant + impossible multi-région
- R2 = pas de limite, pas de coût egress (vs S3 $0.09/GB)
- **Économie cible à l'échelle** : ~$50/mois R2 vs ~$500/mois S3 équivalent

### Étape 1 — Créer le compte Cloudflare R2

1. Va sur https://dash.cloudflare.com/sign-up (gratuit)
2. Plan R2 : « Pay as you go » (10 GB gratuits/mois, puis $0.015/GB)
3. Crée un **bucket** :
   - Nom : `yukpo-prod-storage` (ou ce que tu veux)
   - Location : `Western Europe (WEUR)` recommandé (proche Fly CDG)
4. Crée un **API Token R2** :
   - Dashboard R2 → "Manage R2 API Tokens" → "Create API Token"
   - Permissions : `Object Read & Write`
   - Bucket : `yukpo-prod-storage`
   - Note **Access Key ID** + **Secret Access Key** (s'affichent une seule fois !)
5. Note ton **Account ID** (visible dans l'URL du dashboard ou Overview R2)

### Étape 2 — Configurer Fly secrets

```bash
fly secrets set \
  R2_ACCOUNT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
  R2_ACCESS_KEY_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
  R2_SECRET_ACCESS_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
  R2_BUCKET=yukpo-prod-storage
```

→ La machine redémarre. `core/storage.py` détecte les 4 env vars et active R2.

### Étape 3 — Vérifier l'activation

```bash
curl -H "Authorization: Bearer $JWT" \
  https://yukpopro-backend.fly.dev/api/v1/admin-cross/storage-info
# (à exposer côté backend — endpoint helper à créer)
```

OU via Python REPL Fly :
```bash
fly ssh console
python -c "from core.storage import storage_info; print(storage_info())"
# → {'r2_enabled': True, 'r2_bucket': 'yukpo-prod-storage', ...}
```

### Étape 4 — Migration progressive endpoint par endpoint

Le storage fonctionne en **dual mode** :
- Tant que les endpoints écrivent via `Path.write_bytes` → local seulement
- Quand on les refactor pour `storage.save_artifact(category, name, bytes)` → R2 + fallback local

**Ordre de migration recommandé** (du plus gros volume au plus petit) :

1. `routes_bureau_freeform.py` (PDFs 5-20 MB)
2. `routes_bureau_video.py` (MP4 5-50 MB)
3. `routes_pro_generateurs.py` (HTML landing/slides 100-300 KB)
4. `routes_bureau_documents.py` (lecture multi-source)
5. Autres routes (gdrive, agent, audio, etc.) au fur et à mesure

Pattern de refactor :

```python
# Avant
fid = "bureau_video_..."
(_DATA_DIR / fid).write_bytes(mp4_bytes)

# Après
from core.storage import save_artifact, signed_url
fid = "bureau_video_..."
save_artifact("bureau", fid, mp4_bytes, content_type="video/mp4")
# Pour URL publique partageable (R2 only) :
share_url = signed_url("bureau", fid, expires_in_s=3600)
```

---

## 2. Multi-région (CDG + JNB) — latence 3× meilleure Afrique australe

### Pré-requis
- ✅ R2 activé (sinon volume CDG-only inaccessible depuis JNB)
- ✅ Postgres réplique read en JNB OU latence Postgres acceptable (CDG-JNB ~150ms)

### Activation

```bash
# Ajoute une machine perf-4x à Johannesburg
fly scale count 2 --region cdg --region jnb

# Fly route automatiquement les requêtes vers la région la plus proche du user
# (geo-routing natif anycast). Pas de config DNS supplémentaire requise.
```

### Coût

| Profil trafic | Coût mensuel JNB |
|---|---|
| ~50 users actifs Afrique du Sud / Nigeria (~2h/jour pic) | ~$6 |
| ~500 users (~8h/jour) | ~$24 |
| ~5000 users (~16h/jour) | ~$48 |
| 24/7 saturé | ~$71 |

### Désactivation rapide si problème

```bash
fly scale count 0 --region jnb
```

---

## 3. Worker vidéo dédié (perf-8x)

### Pré-requis
- ✅ R2 activé (volume cross-machine impossible sinon)
- ✅ Plus d'1 perf-8x dispo dans ton plan Fly (vérifie quota)

### Activation

1. Décommenter le bloc `[processes]` dans `fly.toml` (commentaire détaillé dedans)
2. Créer une app secondaire OU utiliser process group :
   ```bash
   # Option A : process group sur la même app (recommandé)
   fly deploy   # déploie web + videow processes
   fly scale count 1 --process-group videow
   fly secrets set --process-group videow \
     YUKPO_DISABLE_WEB=true \
     CELERY_QUEUES=video_heavy \
     CELERY_WORKER_ROLE=video \
     CELERY_WORKER_CONCURRENCY=2
   ```

3. **Migrer** la route `/bureau/video/generer` pour utiliser Celery (actuellement appel synchrone) :
   - Créer `tasks/video_tasks.py` avec `@celery_app.task(name="bureau.video.compose")`
   - Route POST retourne `job_id` immédiatement (~50ms), frontend polle `/bureau/video/status/{id}`
   - Celery route auto vers queue `video_heavy` (config déjà dans `core/celery_app.py`)

### Coût

- Worker perf-8x avec auto-stop : **$30-80/mois** selon volume vidéo
- Justifié dès **50+ vidéos /jour** générées (sinon le worker généraliste suffit)

---

## 4. Postgres dédié — passage de shared à db-shared-2x ou managed externe

### Pourquoi
- Postgres shared Fly = ressources partagées, latence variable
- À 1000+ users : besoin d'IOPS prévisibles + backups automatiques

### Option A — Fly Postgres dédié (recommandé court terme)

```bash
# Crée un cluster Postgres dédié 2x (4 GB RAM, 10 GB SSD)
fly postgres create \
  --name yukpopro-db-dedie \
  --region cdg \
  --vm-size shared-cpu-2x \
  --volume-size 10 \
  --initial-cluster-size 1

# Récupère la connection string
fly postgres attach yukpopro-db-dedie -a yukpopro-backend

# → fly met à jour DATABASE_URL automatiquement, machine redémarre
```

**Migration data** depuis l'ancien Postgres :
```bash
fly postgres connect -a OLD_DB_NAME
pg_dump > backup.sql

fly postgres connect -a yukpopro-db-dedie
\i backup.sql
```

Coût : ~$20/mois (shared-cpu-2x avec 10 GB SSD).

### Option B — Postgres managé externe (Neon / Supabase / Crunchy)

| Provider | Tarif starter | Avantage |
|---|---|---|
| **Neon** | $19/mois (3 GB) | Scale-to-zero, branching DB pour dev, latence CDG bonne |
| **Supabase** | $25/mois | Postgres + auth + storage + edge functions intégrés |
| **Crunchy Bridge** | $35/mois | Postgres ops pro, 24/7 monitoring |

Modif Yukpo : juste `fly secrets set DATABASE_URL="postgres://..."` puis redeploy.

### Quand migrer

Indicateurs déclencheurs :
- `pg_stat_statements` montre queries > 500ms régulières
- `pg_stat_activity` montre régulièrement >50 connexions actives
- Backups manuels manquants (Fly shared n'a pas de backup auto inclus)
- Compliance OHADA / RGPD nécessite rétention/audit logs

---

## 📊 Synthèse coût supplémentaire si tout activé

| Composant | Coût mensuel |
|---|---|
| R2 storage (100 GB stocké) | $1.50 |
| R2 egress (illimité) | $0 |
| JNB région secondaire (auto-stop) | ~$20 |
| Worker vidéo dédié perf-8x (auto-stop) | ~$50 |
| Postgres dédié shared-cpu-2x | $20 |
| **Total supp** | **~$91/mois** |

**À comparer avec** : économies de latence (UX Afrique australe), capacité 5× plus grande, queues non-bloquantes (vidéo n'empêche plus le reste de tourner), DB stable. Justifié dès 500+ users actifs.

---

## ⚠️ Ce que j'AI PRÉPARÉ vs ce que tu DOIS FAIRE

### Côté code (déjà fait dans ce commit)

- ✅ `core/storage.py` — abstraction R2+local avec fallback gracieux
- ✅ `boto3` ajouté dans `requirements-cloud.txt`
- ✅ `core/celery_app.py` — task_routes pour queue `video_heavy`
- ✅ `entrypoint.sh` — support `CELERY_QUEUES`, `CELERY_WORKER_ROLE`, `YUKPO_DISABLE_WEB`
- ✅ `fly.toml` — documentation `[processes]` à décommenter
- ✅ Ce document `INFRA_SCALING.md`

### Côté toi (actions manuelles)

1. **Créer compte Cloudflare R2** + bucket + API token
2. **`fly secrets set R2_* ...`** (4 secrets)
3. (Plus tard, quand prêt) `fly scale count 2 --region cdg --region jnb`
4. (Plus tard) Décommenter `[processes]` fly.toml + `fly deploy`
5. (Plus tard) Migration Postgres dédié

Tant que tu n'as pas fait l'étape 2, le code R2 reste inactif mais ne casse rien (fallback local automatique).

---

## 5. Landing publication Netlify + Notifications WA/SMS/Email (Phase A Sprint 1)

### Pourquoi

- Module `modules/pro/landing_publisher.py` déploie les landings HTML
  générées par YukpoPro/YukpoSec vers Netlify via leur API officielle,
  sous-domaine `<slug>.yukpomnang.com`.
- **Stratégie notification (contexte africain) : WhatsApp prioritaire,
  SMS Twilio en fallback automatique, email SendGrid en bonus optionnel.**
  Le helper `core/notifications.notifier_telephone()` tente WA d'abord
  et bascule sur SMS si le destinataire n'a pas WhatsApp ou si la
  fenêtre 24h Business n'est pas ouverte.
- Sans `NETLIFY_API_TOKEN`, l'endpoint `/api/v1/pro/landing-page/publier`
  renvoie 503. Sans `SENDGRID_API_KEY`, les emails sont simulés (log) —
  pas bloquant car WhatsApp/SMS couvrent les notifs marchand + visiteur.

### Configuration Twilio recommandée pour SMS (en plus du WA existant)

Twilio WA est déjà configuré (`TWILIO_WHATSAPP_NUMBER`). Pour activer
le fallback SMS automatique :

**Option A — Messaging Service (recommandée)** :
1. Console Twilio → Messaging → Services → Create Messaging Service
2. Friendly name : `YukpoPro Notifications`
3. Use case : "Notify my users"
4. Add Senders :
   - Alphanumeric Sender ID `YukpoPro` (gratuit, supporté Cameroun /
     CI / Sénégal / Burkina / Mali — SMS one-way, parfait pour notifs)
   - OU acheter un numéro Twilio SMS-enabled (~$1-3/mois)
5. Copier le Messaging Service SID (commence par `MG…`)
6. `fly secrets set -a yukpopro-backend TWILIO_MESSAGING_SERVICE_SID=MG…`

**Option B — Numéro Twilio simple** :
1. Console → Phone Numbers → Buy → cocher capability SMS
2. `fly secrets set -a yukpopro-backend TWILIO_SMS_NUMBER=+14155551234`

Sans `TWILIO_MESSAGING_SERVICE_SID` ni `TWILIO_SMS_NUMBER` posés, le SMS
fallback tombe en simulation (log). WhatsApp continue de fonctionner.

### Étape 1 — Compte Netlify + API token

1. Créer un compte sur https://app.netlify.com (gratuit, plan free
   suffisant pour 100 sites + 100 GB bandwidth/mois).
2. **User settings → Applications → New access token** → nom "Yukpo
   prod publisher". Copie le token (visible une seule fois).
3. (Optionnel) Si tu utilises une team Netlify dédiée, note son
   `team_slug` (visible dans l'URL `app.netlify.com/teams/<team_slug>`).

### Étape 2 — Wildcard DNS Cloudflare

Pour que les sites créés soient accessibles sur `<slug>.yukpomnang.com` :

1. Cloudflare Dashboard → zone `yukpomnang.com` → DNS → Add record :
   ```
   Type   : CNAME
   Name   : *               (= wildcard)
   Target : apex-loadbalancer.netlify.com
   Proxy  : DNS only         (orange cloud OFF — Netlify gère son TLS)
   TTL    : Auto
   ```
2. Si Netlify demande une vérification du custom_domain, suis l'assistant
   (TXT record temporaire). En général : pas nécessaire avec wildcard.

### Étape 3 — Compte SendGrid + API key

1. Créer un compte SendGrid (https://app.sendgrid.com — plan free =
   100 emails/jour, suffisant pour MVP).
2. Settings → API Keys → Create API Key → permissions "Mail Send"
   uniquement (sécurité min privilege). Copie la clé.
3. Settings → Sender Authentication → Single Sender Verification :
   vérifier `no-reply@yukpomnang.com` (ou domaine déjà vérifié si
   disponible). Sans verification, SendGrid rejette les envois.

### Étape 4 — Fly secrets

```bash
fly secrets set \
  NETLIFY_API_TOKEN=netlify_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
  LANDING_DOMAIN_BASE=yukpomnang.com \
  SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
  SENDGRID_FROM_EMAIL=no-reply@yukpomnang.com \
  SENDGRID_FROM_NAME="YukpoPro" \
  YUKPO_PUBLIC_API_BASE=https://yukpopro-backend.fly.dev

# (Optionnel team Netlify)
fly secrets set NETLIFY_TEAM_SLUG=ma-team-yukpo
```

`YUKPO_PUBLIC_API_BASE` = URL absolue du backend, utilisée par le helper
`injecter_publication` pour reconstruire le `<form action>` du formulaire
de contact qui ira vers `/api/v1/landing-leads/{slug}`. Si non défini,
URL relative — fonctionne uniquement si Netlify rewrite vers le backend.

### Étape 5 — Migration DB

La migration Alembic `0009_landing_publications` ajoute les tables
`landing_publications` et `landing_leads`. Au démarrage Fly :

```bash
fly ssh console -C "alembic upgrade head"
```

(ou laisser `core.database.init_db()` créer les tables au boot — il
détecte les classes `LandingPublicationDB` / `LandingLeadDB` via
SQLAlchemy `Base.metadata.create_all`).

### Étape 6 — Vérification

1. Génère une landing depuis le chat YukpoPro ("génère une landing pour
   ma boutique cuir Douala").
2. Clique le lien "🚀 Publier en ligne" → page `/publier-landing/...`.
3. Choisis un slug (ex. `test-landing-001`) → "Publier maintenant".
4. Vérifie l'URL `https://test-landing-001.yukpomnang.com` (TLS Netlify
   auto-provisionné en 1-2 min).
5. Sur la landing publiée, remplis le formulaire de contact.
6. Vérifie que le lead apparaît dans `/mes-leads` ET que tu reçois la
   notification WhatsApp + email.

### Coûts récurrents

| Composant | Tarif | Note |
|---|---|---|
| Netlify free tier | $0 | 100 sites + 100 GB/mois suffisants pour MVP |
| Netlify Pro (si > 100 sites) | $19/mois/membre | À déclencher à ~50 marchands payants |
| SendGrid free tier | $0 | 100 emails/jour (~3000/mois) |
| SendGrid Essentials | $19.95/mois | 50k emails/mois — déclencher à ~30 marchands actifs |
| Cloudflare DNS wildcard | $0 | inclus dans le plan gratuit |

### Désactivation rapide

```bash
fly secrets unset NETLIFY_API_TOKEN
# → endpoint /pro/landing-page/publier renvoie 503,
# notifications email retombent en mode simulé.
# Les leads continuent d'être enregistrés en DB + WhatsApp Twilio.
```

---

## 6. Phase B — Plausible Analytics + pixels + newsletter

### 6.1 Plausible Analytics

**Option cloud (rapide, recommandée pour démarrer)** :

1. Crée un compte sur https://plausible.io (trial 30j gratuit, puis $9/mois
   < 10k pageviews, $19/mois < 100k).
2. Settings → API Keys → Generate new key (permissions read uniquement).
3. ⚠️ Plausible cloud requiert d'ajouter CHAQUE domaine dans le dashboard
   (Settings → Sites → Add site). Pour automatiser : utilise l'API Sites
   ou ajoute manuellement chaque `<slug>.yukpomnang.com` au moment de la
   publication (TODO Sprint B5 : auto-add site via API au publish).
4. `fly secrets set PLAUSIBLE_API_KEY=… PLAUSIBLE_API_BASE=https://plausible.io/api/v1 \
       PLAUSIBLE_SCRIPT_URL=https://plausible.io/js/script.js`

**Option self-hosted (~$10/mois, RGPD-friendly, illimité)** :

1. Déploie Plausible CE sur une app Fly séparée :
   ```bash
   fly app create yukpo-plausible
   # Suivre la doc Docker Compose de Plausible :
   # https://github.com/plausible/community-edition
   # Configurer Postgres + Clickhouse via fly volumes.
   ```
2. `fly secrets set PLAUSIBLE_API_BASE=https://yukpo-plausible.fly.dev/api/v1 \
       PLAUSIBLE_SCRIPT_URL=https://yukpo-plausible.fly.dev/js/script.js`

### 6.2 Pixels publicitaires

Aucune action serveur — les pixels Facebook/GA4/TikTok/Snap/Clarity sont
juste des IDs publics que le marchand colle dans
`/tracking-settings` côté YukpoPro. Le backend les injecte automatiquement
dans `<head>` de la landing lors du publish.

### 6.3 Newsletter (Brevo / Mailchimp)

Le marchand colle SA clé API perso dans `/tracking-settings`. La clé est
stockée chiffrée côté Yukpo (MVP : clair en DB → chiffrer avec
`cryptography.Fernet` + `SECRET_KEY` plus tard si compliance le requiert).

Aucune clé Yukpo-globale n'est requise.

### 6.4 Email automation J+0 / J+3 / J+7

Réutilise SendGrid (cf. section 5.3). Le scheduler Celery beat envoie
les follow-ups quotidiennement (06:00 UTC) — assure-toi qu'un worker
Celery + beat tournent côté Fly :

```bash
# Si tu n'utilises pas encore Celery beat :
fly secrets set CELERY_BEAT_ENABLED=true
# Et dans entrypoint.sh : conditionner le lancement de
#   celery -A core.celery_app beat --loglevel=info
# en parallèle du worker.
```

Tant que beat n'est pas lancé, l'auto-reply J+0 fonctionne quand même
(appelé en synchro depuis la route `/landing-leads/{slug}`), seuls J+3
et J+7 nécessitent beat.
