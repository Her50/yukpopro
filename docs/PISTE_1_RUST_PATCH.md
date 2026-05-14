# Piste 1 — Patch Rust côté `yukpomnang2/`

Ce document décrit la route à ajouter dans le backend Rust pour recevoir
les publications de produits envoyées par YukpoShop (YukpoPro Python).

Le côté Python est déjà livré (commit suivant). Il attend cette route
pour fonctionner en prod ; en dev tu peux laisser `RUST_BRIDGE_ENABLED=false`
et le bridge ne fait rien.

---

## 1. Migration SQL (Postgres Rust)

Ajoute une table de traçabilité pour idempotency cross-source.

```sql
-- yukpomnang2/backend/migrations/<NEXT>_external_product_links.sql
CREATE TABLE IF NOT EXISTS external_product_links (
    id              BIGSERIAL PRIMARY KEY,
    source_app      VARCHAR(40)  NOT NULL,    -- 'yukposhop', 'shopify', ...
    external_id     VARCHAR(120) NOT NULL,    -- id côté source (ex: shop_products.id)
    rust_service_id INTEGER      NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    rust_user_id    INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    payload_jsonb   JSONB        NOT NULL,    -- snapshot du dernier payload reçu
    schema_version  INTEGER      NOT NULL DEFAULT 1,
    cree_le         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    maj_le          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (source_app, external_id)
);

CREATE INDEX idx_external_product_links_service_id
    ON external_product_links(rust_service_id);
```

---

## 2. Route Axum à créer

Fichier proposé : `yukpomnang2/backend/src/routes/integrations_yukposhop.rs`

```rust
//! Piste 1 — Bridge YukpoShop -> Yukpo Rust marketplace.
//!
//! Reçoit les produits publiés par YukpoShop (YukpoPro Python) et les
//! upsert dans la table `services` pour bénéficier de la recherche
//! native + matching IA + GPS-géolocalisation.
//!
//! Authentification : HMAC-SHA256 du body avec secret partagé
//! `YUKPOSHOP_BRIDGE_HMAC_KEY` (env var Fly secret).

use axum::{
    extract::State,
    http::{HeaderMap, StatusCode},
    response::IntoResponse,
    routing::post,
    Json, Router,
};
use base64::Engine;
use hmac::{Hmac, Mac};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::Sha256;
use sqlx::PgPool;
use std::sync::Arc;

use crate::AppState; // adapter selon ton AppState existant

const REPLAY_WINDOW_S: i64 = 300; // 5 min
const SOURCE_APP: &str = "yukposhop";

// ─── Schemas ─────────────────────────────────────────────────────────────

#[derive(Deserialize)]
pub struct YukposhopVendeur {
    pub email: String,
    pub nom_affiche: Option<String>,
    pub boutique_slug: Option<String>,
    pub boutique_url: Option<String>,
}

#[derive(Deserialize)]
pub struct YukposhopProduit {
    pub titre: String,
    pub description: String,
    pub prix: f64,
    pub devise: String,
    pub stock: i32,
    pub photos_urls: Vec<String>,
    pub tags: Vec<String>,
    pub slug: String,
    pub categorie: Option<String>,
    pub pays: String,
}

#[derive(Deserialize)]
pub struct YukposhopRetour {
    pub url_storefront: Option<String>,
    pub whatsapp_contact: Option<String>,
}

#[derive(Deserialize)]
pub struct YukposhopSyncRequest {
    pub schema_version: i32,
    pub source: String,
    pub external_id: String,
    pub external_updated_at: String,
    pub vendeur: YukposhopVendeur,
    pub produit: YukposhopProduit,
    pub retour_au_marchand: YukposhopRetour,
}

#[derive(Serialize)]
pub struct SyncResponse {
    pub ok: bool,
    pub rust_service_id: i32,
    pub action: &'static str, // "created" | "updated"
}

// ─── HMAC verification ──────────────────────────────────────────────────

fn verify_hmac(body: &[u8], headers: &HeaderMap, secret: &str) -> Result<(), &'static str> {
    let sig_b64 = headers
        .get("x-yukpo-signature")
        .and_then(|v| v.to_str().ok())
        .ok_or("missing X-Yukpo-Signature")?;
    let ts = headers
        .get("x-yukpo-timestamp")
        .and_then(|v| v.to_str().ok())
        .ok_or("missing X-Yukpo-Timestamp")?;

    // Anti-replay
    let ts_int: i64 = ts.parse().map_err(|_| "invalid timestamp")?;
    let now = chrono::Utc::now().timestamp();
    if (now - ts_int).abs() > REPLAY_WINDOW_S {
        return Err("timestamp out of replay window");
    }

    // HMAC compute
    let key = base64::engine::general_purpose::STANDARD
        .decode(secret)
        .unwrap_or_else(|_| secret.as_bytes().to_vec());
    let mut mac = <Hmac<Sha256> as Mac>::new_from_slice(&key)
        .map_err(|_| "bad hmac key")?;
    mac.update(ts.as_bytes());
    mac.update(b".");
    mac.update(body);
    let expected = base64::engine::general_purpose::STANDARD
        .encode(mac.finalize().into_bytes());

    if !constant_time_eq::constant_time_eq(expected.as_bytes(), sig_b64.as_bytes()) {
        return Err("HMAC mismatch");
    }
    Ok(())
}

// ─── Handler ────────────────────────────────────────────────────────────

pub async fn sync_yukposhop_produit(
    State(state): State<Arc<AppState>>,
    headers: HeaderMap,
    body: axum::body::Bytes,
) -> impl IntoResponse {
    // 1. Verify HMAC
    let secret = std::env::var("YUKPOSHOP_BRIDGE_HMAC_KEY").unwrap_or_default();
    if secret.is_empty() {
        return (StatusCode::SERVICE_UNAVAILABLE,
                Json(json!({"error": "bridge non configuré côté serveur"}))).into_response();
    }
    if let Err(e) = verify_hmac(&body, &headers, &secret) {
        tracing::warn!("[yukposhop bridge] HMAC reject: {e}");
        return (StatusCode::UNAUTHORIZED,
                Json(json!({"error": e}))).into_response();
    }

    // 2. Parse JSON
    let req: YukposhopSyncRequest = match serde_json::from_slice(&body) {
        Ok(r) => r,
        Err(e) => return (StatusCode::BAD_REQUEST,
                          Json(json!({"error": format!("invalid json: {e}")}))).into_response(),
    };
    if req.source != SOURCE_APP {
        return (StatusCode::BAD_REQUEST,
                Json(json!({"error": "source mismatch"}))).into_response();
    }

    // 3. Resolve or create user (par email)
    let user_id = match resolve_or_create_user(&state.db, &req.vendeur).await {
        Ok(id) => id,
        Err(e) => return (StatusCode::INTERNAL_SERVER_ERROR,
                          Json(json!({"error": format!("user resolve: {e}")}))).into_response(),
    };

    // 4. Compose le `data` JSONB pour services
    let data = json!({
        "titre":            req.produit.titre,
        "description":      req.produit.description,
        "prix":             req.produit.prix,
        "devise":           req.produit.devise,
        "stock":            req.produit.stock,
        "photos_urls":      req.produit.photos_urls,
        "tags":             req.produit.tags,
        "pays":             req.produit.pays,
        "type_produit":     "ecommerce",
        "boutique_url":     req.retour_au_marchand.url_storefront,
        "whatsapp_contact": req.retour_au_marchand.whatsapp_contact,
        "vendeur_email":    req.vendeur.email,
        "vendeur_nom":      req.vendeur.nom_affiche,
        "external_source":  SOURCE_APP,
        "external_id":      req.external_id,
    });

    // 5. Upsert via external_product_links (idempotent)
    let result = sqlx::query!(
        r#"
        WITH existing AS (
            SELECT rust_service_id FROM external_product_links
            WHERE source_app = $1 AND external_id = $2
        )
        SELECT rust_service_id FROM existing
        "#,
        SOURCE_APP, req.external_id,
    )
    .fetch_optional(&state.db)
    .await;

    let (rust_service_id, action) = match result {
        Ok(Some(row)) => {
            // UPDATE existing service
            let _ = sqlx::query!(
                "UPDATE services SET data = $1, is_active = TRUE, embedding_status = 'pending'
                 WHERE id = $2",
                data, row.rust_service_id,
            ).execute(&state.db).await;
            let _ = sqlx::query!(
                "UPDATE external_product_links SET payload_jsonb = $1, maj_le = NOW()
                 WHERE source_app = $2 AND external_id = $3",
                data, SOURCE_APP, req.external_id,
            ).execute(&state.db).await;
            (row.rust_service_id, "updated")
        }
        Ok(None) => {
            // INSERT new service
            let new_id = match sqlx::query!(
                r#"INSERT INTO services (user_id, data, is_active, embedding_status, category)
                   VALUES ($1, $2, TRUE, 'pending', 'ecommerce') RETURNING id"#,
                user_id, data,
            ).fetch_one(&state.db).await {
                Ok(r) => r.id,
                Err(e) => return (StatusCode::INTERNAL_SERVER_ERROR,
                                  Json(json!({"error": format!("insert service: {e}")}))).into_response(),
            };
            let _ = sqlx::query!(
                r#"INSERT INTO external_product_links
                   (source_app, external_id, rust_service_id, rust_user_id, payload_jsonb, schema_version)
                   VALUES ($1, $2, $3, $4, $5, $6)"#,
                SOURCE_APP, req.external_id, new_id, user_id, data, req.schema_version,
            ).execute(&state.db).await;
            (new_id, "created")
        }
        Err(e) => return (StatusCode::INTERNAL_SERVER_ERROR,
                          Json(json!({"error": format!("lookup: {e}")}))).into_response(),
    };

    // 6. Trigger indexation (full-text + embedding async)
    // → soit publish Redis pubsub 'service:created' / 'service:updated'
    // → soit invoque directement le service d'indexation

    tracing::info!("[yukposhop bridge] {} service_id={} external_id={} user_id={}",
                   action, rust_service_id, req.external_id, user_id);

    (StatusCode::OK, Json(SyncResponse {
        ok: true,
        rust_service_id,
        action,
    })).into_response()
}

async fn resolve_or_create_user(
    pool: &PgPool,
    vendeur: &YukposhopVendeur,
) -> Result<i32, sqlx::Error> {
    // Look up by email
    if let Some(row) = sqlx::query!(
        "SELECT id FROM users WHERE email = $1 LIMIT 1",
        vendeur.email,
    ).fetch_optional(pool).await? {
        return Ok(row.id);
    }
    // Create stub user
    let nom = vendeur.nom_affiche.clone().unwrap_or_else(|| "Marchand YukpoShop".to_string());
    let row = sqlx::query!(
        r#"INSERT INTO users (email, full_name, source, password_hash, role)
           VALUES ($1, $2, 'yukposhop', '!locked!', 'vendor') RETURNING id"#,
        vendeur.email, nom,
    ).fetch_one(pool).await?;
    Ok(row.id)
}

pub fn router() -> Router<Arc<AppState>> {
    Router::new()
        .route("/api/v1/integrations/yukposhop/sync", post(sync_yukposhop_produit))
}
```

Branche le router dans `main.rs` :

```rust
.merge(crate::routes::integrations_yukposhop::router())
```

---

## 3. Dépendances `Cargo.toml`

```toml
[dependencies]
# déjà probablement présents :
axum = "0.8"
sqlx = { version = "0.8", features = ["postgres", "json", "chrono"] }
chrono = "0.4"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tracing = "0.1"

# à ajouter si absents :
hmac = "0.12"
sha2 = "0.10"
base64 = "0.22"
constant_time_eq = "0.3"
```

---

## 4. Secret Fly à poser

```powershell
# Génère un secret base64 random (32 bytes)
$key = python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
echo "Bridge key: $key"

# Pose côté Rust (NOM DE TON APP — adapter si différent)
fly secrets set -a yukpomnang YUKPOSHOP_BRIDGE_HMAC_KEY="$key"

# Pose côté YukpoPro
fly secrets set -a yukpopro-backend `
  RUST_BRIDGE_ENABLED=true `
  RUST_BRIDGE_URL=https://yukpomnang.fly.dev/api/v1/integrations/yukposhop/sync `
  RUST_BRIDGE_HMAC_KEY="$key"
```

**ATTENTION** : la même clé doit être posée des DEUX côtés. Garde-la quelque
part en sécurité (1Password / Bitwarden) ; si tu la perds, regénère et re-pose.

---

## 5. Test fumée

Après déploiement côté Rust :

```bash
# Côté YukpoPro
fly ssh console -a yukpopro-backend
python -c "
import asyncio, os
os.environ['RUST_BRIDGE_ENABLED'] = 'true'
from modules.pro.yukposhop_rust_bridge import publier_produit_vers_rust
from core.database import async_session_maker
async def main():
    async with async_session_maker() as s:
        r = await publier_produit_vers_rust(
            produit_id=1, db=s,
            vendeur_email='test@yukpo.local', vendeur_nom='Test',
        )
        print(r)
asyncio.run(main())
"
```

Tu devrais voir :
```python
SyncResult(success=True, rust_service_id=12345, error=None, http_status=200, ...)
```

---

## 6. Suite naturelle (Piste 2 et au-delà)

Une fois Piste 1 stable :
- **Piste 2** (pull search) : YukpoShop storefront affiche `GET /api/universal-search`
  côté Rust pour cross-sell. Aucun changement côté Rust nécessaire (endpoint existant).
- **Piste 4** (social distribution unifiée) : YukpoShop délègue à `/api/social/products/distribute`
  côté Rust (suppression du doublon `shop_social_sync.py`).
- **Piste 5** (sync inventaire bidirectionnelle) : ajouter colonnes stock dans
  `external_product_links` + webhook Rust -> YukpoPro pour décrément vente.

Voir `docs/INTEGRATION_RUST_YUKPOSHOP.md` (synthèse stratégique du 14 mai 2026).
