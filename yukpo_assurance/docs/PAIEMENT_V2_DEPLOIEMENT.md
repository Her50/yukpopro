# Paiement v2 — Déploiement production (Fly + Vercel)

## Architecture

```
yukpopro_web (Vercel)              yukpopro_backend (Fly.io / yukpopro-backend)
   │                                       │
   │  POST /api/v1/paiement/v2/initier ───>│  PaymentOrchestrator
   │                                       │     │
   │                                       │     ├─ MTN MoMo (priorité 1 si CM)
   │                                       │     ├─ Orange Money
   │                                       │     ├─ Campay (fintech CM)
   │                                       │     ├─ CinetPay (CEMAC/UEMOA)
   │                                       │     ├─ Flutterwave (Pan-African)
   │                                       │     ├─ NotchPay
   │                                       │     ├─ Stripe / PayPal (intl)
   │                                       │     └─ Legacy manuel (admin 3h)
   │                                       │
   │  webhook ◄────────────────────────────│  /paiement/v2/webhook/{provider}
```

## Source unique des secrets

GCP Secret Manager (project `yukpo-project`) — détail dans
`modules/paiement/v2/secrets_loader.py:GCP_SECRET_MAP`.

## Procédure de mise en prod

### 1. Vérifier les secrets GCP

```bash
gcloud secrets list --project=yukpo-project --filter="name~pay OR name~stripe OR name~cinetpay"
```

Secrets requis (déjà présents) :
- `cinetpay-api-key`, `cinetpay-api-password`, `cinetpay-secret-key`, `cinetpay-site-id`
- `flutterwave-public-key`, `flutterwave-secret-key`
- `mtn-money-webhook-secret`, `orange-money-webhook-secret`
- `notchpay-public-key`, `notchpay-secret-key`
- `paypal-client-id`, `paypal-client-secret`, `paypal-webhook-id`
- `stripe-publishable-key`, `stripe-secret-key`, `stripe-webhook-secret`

Secrets à créer pour MTN/Orange direct (si non encore présents) :
```bash
gcloud secrets create mtn-momo-api-user --project=yukpo-project --data-file=-
gcloud secrets create mtn-momo-api-key --project=yukpo-project --data-file=-
gcloud secrets create mtn-momo-subscription-key --project=yukpo-project --data-file=-
gcloud secrets create orange-money-client-id --project=yukpo-project --data-file=-
gcloud secrets create orange-money-client-secret --project=yukpo-project --data-file=-
gcloud secrets create orange-money-merchant-key --project=yukpo-project --data-file=-
gcloud secrets create campay-permanent-token --project=yukpo-project --data-file=-
```

### 2. Migration DB

```bash
cd yukpo_assurance
alembic upgrade head    # applique 0006_payments_v2
```

Tables créées : `wallet_yukpopro`, `payment_transactions_v2`,
`payment_attempts`, `payment_webhook_events`.

### 3. Sync secrets vers Fly + Vercel

```bash
chmod +x scripts/sync_payment_secrets.sh
./scripts/sync_payment_secrets.sh all
```

Le script :
- Lit chaque secret via `gcloud secrets versions access latest`
- Pousse sur Fly via `fly secrets set --app yukpopro-backend --stage`
- Pousse les clés **publishable** sur Vercel comme `VITE_*` (production env)

### 4. Configurer les callback URLs

Sur Fly :
```bash
fly secrets set --app yukpopro-backend \
  PAYMENT_CALLBACK_HOST=https://yukpopro-backend.fly.dev \
  MTN_MOMO_ENVIRONMENT=production \
  ORANGE_MONEY_ENVIRONMENT=production \
  CAMPAY_ENV=production \
  PAYPAL_SANDBOX=false
```

Côté providers (panneau admin de chacun), enregistrer les webhooks :
- MTN MoMo : `https://yukpopro-backend.fly.dev/api/v1/paiement/v2/webhook/mtn_momo`
- Orange Money : `.../webhook/orange_money`
- CinetPay : `.../webhook/cinetpay`
- Flutterwave : `.../webhook/flutterwave`
- Stripe : `.../webhook/stripe` (configurer endpoint + récupérer signing secret)
- PayPal : `.../webhook/paypal`
- NotchPay : `.../webhook/notchpay`
- Campay : `.../webhook/campay`

### 5. Déploiement

```bash
fly deploy --app yukpopro-backend
cd ../yukpopro_web && vercel --prod
```

### 6. Vérification

```bash
curl https://yukpopro-backend.fly.dev/api/v1/paiement/v2/health \
  -H "Authorization: Bearer <token_admin>"
```

Doit retourner `{ "providers": { "mtn_momo": true, "orange_money": true, ... } }`.

## Cascade par pays

| Pays | Cascade prioritaire |
|------|---------------------|
| CM   | MTN MoMo → Orange Money → Campay → CinetPay → NotchPay → Flutterwave |
| CI   | Orange Money → MTN → Wave → CinetPay → Flutterwave |
| SN   | Wave → Orange Money → CinetPay → Flutterwave |
| BF/ML | Orange Money → CinetPay → Flutterwave |
| TG   | CinetPay → Flutterwave |
| NG   | Flutterwave → NotchPay → Stripe |
| Intl | Stripe → PayPal → Flutterwave |

Ultime fallback : `LegacyManualProvider` → flux manuel admin (validation 3h)
identique à l'existant `gestionnaire_paiement.py`.

## Rollback rapide

Si le système v2 cause un incident, désactiver via env var :
```bash
fly secrets set --app yukpopro-backend YUKPO_PAYMENT_V2_ENABLED=false
```

(à câbler côté `routes_pro_abonnement.py` si on veut un kill-switch — sinon
le frontend continuera d'appeler les endpoints v1 existants en parallèle).

## Monitoring

Endpoints à instrumenter dans Grafana / Fly metrics :
- `/api/v1/paiement/v2/initier` : latence p95, taux d'erreur, distribution providers
- `/api/v1/paiement/v2/webhook/*` : count, taux signature_invalid
- Table `payment_attempts` : agréger pour suivre la cascade (provider primary vs fallbacks)
