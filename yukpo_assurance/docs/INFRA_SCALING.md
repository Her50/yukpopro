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
