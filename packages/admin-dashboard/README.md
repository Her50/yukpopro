# @yukpo/admin-dashboard

Composant React partagé : dashboard administrateur unifié YukpoPro + YukpoSecrétariat.

Monté à l'identique dans :
- `yukpopro_web/src/pages/AdminPage.tsx`
- `yukposecretariat_web/src/pages/AdminPage.tsx`

L'admin choisit son scope (Pro / Sec / Both) via un toggle persistant en localStorage —
peu importe l'app où il est connecté, il voit le même dashboard et peut filtrer la vue.

## Onglets

1. **Vue d'ensemble** : KPIs (utilisateurs actifs, appels IA, coût, crédits alloués),
   répartition Pro vs Sec, sparkline coût/jour, top features.
2. **Consommation API** : évolution journalière (Pro+Sec dissociés), table par feature
   avec barre de répartition, totaux tokens/crédits/FCFA.
3. **Fournisseurs** : agrégation par éditeur (Anthropic, OpenAI, fal, Replicate,
   ElevenLabs, Azure, local), modèles utilisés, % de coût.
4. **Top utilisateurs** : top 20 consommateurs (toutes apps confondues si scope=both).
5. **Alertes** : seuils dépassés sur 24h (cost_daily_*, cost_provider_share,
   quota_user_exhausted), avec sévérité critical/warning/info.

## Endpoints backend consommés

Tous sous `/api/v1/admin-cross/*` (router `routes_admin_cross.py`) :

| Endpoint                     | Méthode | Description |
|------------------------------|---------|-------------|
| `/dashboard`                 | GET     | KPIs synthétiques cross-app |
| `/usage`                     | GET     | Agrégation par jour |
| `/cost`                      | GET     | Coûts USD/FCFA/crédits |
| `/by-feature`                | GET     | Top features consommatrices |
| `/by-provider`               | GET     | Conso par fournisseur LLM/IA |
| `/by-user`                   | GET     | Top utilisateurs consommateurs |
| `/alerts`                    | GET     | Alertes actives (seuils dépassés) |
| `/thresholds`                | GET     | Seuils configurés (lecture seule MVP) |

Tous prennent `?scope=pro|sec|both` (défaut: `both`) et `?jours=N` (défaut: 30).

## Scope

| Valeur  | Source                                                |
|---------|-------------------------------------------------------|
| `pro`   | Table `consommations_tokens` (YukpoPro uniquement)    |
| `sec`   | Table `consommations_bureau` (Secrétariat uniquement) |
| `both`  | Union des deux tables                                 |

La colonne `app_origine` (ajoutée en migration `0007_app_origine_tracking.py`) trace
explicitement la source de chaque enregistrement (`pro` / `sec`). Les valeurs sont
backfillées automatiquement au déploiement (lignes pré-existantes : `pro` pour
`consommations_tokens`, `sec` pour `consommations_bureau`).

## Classification des fournisseurs

Heuristique sur le champ `modele` des tables consommations_*, dans
`modules/admin_cross/providers.py`. Les patterns reconnus :

| Provider     | Patterns détectés                                          |
|--------------|------------------------------------------------------------|
| `anthropic`  | `claude*`, prefix `anthropic`                              |
| `openai`     | `gpt-*`, `text-embedding*`, `whisper-1`, contains `openai` |
| `fal`        | `flux-*`, `recraft*`, `ideogram*`, `flux/*`, contains `fal.ai` |
| `replicate`  | contains `replicate`, `rep-*`, `lora-training`             |
| `elevenlabs` | contains `elevenlabs`, `eleven-*`, `tts-eleven*`           |
| `azure`      | contains `azure`, `form-recognizer`, `document-intelligence` |
| `local`      | `forfait`, `local`, `whisper-local`, `embedded`            |
| `unknown`    | tout le reste                                              |

## Seuils d'alerte (MVP)

Définis dans `modules/admin_cross/alerts.py` (`SEUILS_DEFAUT`). Tous configurables
via variables d'environnement Fly.io.

| Catégorie                      | Variable env                       | Défaut       |
|--------------------------------|-------------------------------------|--------------|
| Feature 24h — warning          | `YK_ALERT_FEATURE_WARN_FCFA`       | 30 000 FCFA  |
| Feature 24h — critical         | `YK_ALERT_FEATURE_CRIT_FCFA`       | 100 000 FCFA |
| User 24h — warning             | `YK_ALERT_USER_WARN_FCFA`          | 10 000 FCFA  |
| User 24h — critical            | `YK_ALERT_USER_CRIT_FCFA`          | 30 000 FCFA  |
| Global 24h — warning           | `YK_ALERT_GLOBAL_WARN_FCFA`        | 150 000 FCFA |
| Global 24h — critical          | `YK_ALERT_GLOBAL_CRIT_FCFA`        | 500 000 FCFA |
| Provider concentré — warning   | `YK_ALERT_PROVIDER_PCT`             | 70.0 %       |
| User crédits bas — warning     | `YK_ALERT_QUOTA_WARN`              | 300 crédits  |

Pour modifier en prod :
```bash
fly secrets set YK_ALERT_FEATURE_CRIT_FCFA=200000 -a yukpopro-backend
```

## Architecture du partage

Le package est mappé via Vite alias dans les deux apps :

```ts
// yukpopro_web/vite.config.ts ET yukposecretariat_web/vite.config.ts
resolve: {
  alias: {
    '@yukpo/admin-dashboard': path.resolve(__dirname, '../packages/admin-dashboard/src'),
  },
  dedupe: ['react', 'react-dom', 'lucide-react', 'axios'],
}
```

Et dans tsconfig.json :
```json
"paths": {
  "@yukpo/admin-dashboard": ["../packages/admin-dashboard/src/index.ts"],
  "@yukpo/admin-dashboard/*": ["../packages/admin-dashboard/src/*"]
}
```

L'app hôte injecte son instance HTTP (axios) — le composant reste agnostique à
l'auth et utilise le client passé en prop. Voir `AdminDashboardProps`.

## Sécurité

Les endpoints `/admin-cross/*` exigent `role ∈ {admin, super_admin, yukpo_owner}`
côté backend (`_require_admin` dans `routes_admin_cross.py`). Le composant front
ajoute en plus une garde-fou côté client qui redirige vers `/chat` si l'user
n'est pas admin.

## Évolutions prévues

- Sous-onglet "Utilisateurs" avec actions admin (bonus crédits, blocage,
  promotions ciblées) — réintégrer les capacités de l'ancien AdminPage.
- Notifications externes (email + Slack) sur transitions OK→ALERTE.
- Anomaly detection IA (Claude analyse les patterns de conso) — phase 2.
- Export CSV des onglets pour analyse offline.
- Tracking explicit de la latence et du SLA par endpoint (nouvelle colonne
  `latence_ms` sur les tables consommations_*).
