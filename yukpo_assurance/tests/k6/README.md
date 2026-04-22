# YukpoAssurance — Tests de charge k6

## Prérequis

```bash
# Installer k6 (Linux/Mac)
brew install k6
# ou : https://k6.io/docs/getting-started/installation/

# Windows (via Chocolatey)
choco install k6

# Démarrer l'API en local avant les tests
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

## Variables d'environnement

```bash
export K6_BASE_URL=http://localhost:8000   # URL de l'API
export K6_TOKEN=eyJhbGci...               # JWT valide (admin)
```

## Scénarios disponibles

| Script | Description | VUs | Durée |
|--------|-------------|-----|-------|
| `smoke.js` | Vérification basique (1 VU) | 1 | 30s |
| `copilote_load.js` | Endpoints copilote + IA | 10→50 | 5min |
| `sinistres_load.js` | Workflow sinistres complet | 5→25 | 5min |
| `cima_load.js` | Conformité + états CIMA | 5→20 | 5min |
| `tarification_load.js` | Calcul de prime + ML | 10→30 | 5min |
| `full_stress.js` | Stress test global | 10→100 | 10min |

## Exécution rapide

```bash
# Smoke test (vérification que tout fonctionne)
k6 run tests/k6/smoke.js

# Test charge copilote
k6 run -e BASE_URL=http://localhost:8000 -e TOKEN=$K6_TOKEN tests/k6/copilote_load.js

# Stress test complet
k6 run -e BASE_URL=http://localhost:8000 -e TOKEN=$K6_TOKEN tests/k6/full_stress.js

# Avec export des métriques vers Grafana/InfluxDB
k6 run --out influxdb=http://localhost:8086/k6 tests/k6/full_stress.js
```

## Seuils SLA définis

- **p95 < 2000ms** — 95% des requêtes en moins de 2 secondes
- **p99 < 5000ms** — 99% des requêtes en moins de 5 secondes (endpoints IA)
- **taux d'erreur < 1%** — moins de 1% de réponses en erreur
- **disponibilité > 99%** — les endpoints /health répondent toujours

## Interpréter les résultats

```
✓ http_req_duration.............: avg=320ms  p(95)=1842ms  p(99)=4102ms
✓ http_req_failed...............: 0.12%
✓ iterations...................: 1243  212/s
```

Un `✓` signifie que le seuil est respecté. Un `✗` déclenche une alerte.
