/**
 * YukpoAssurance — Stress Test complet
 * Pousse le système jusqu'à 100 VUs simultanés pour identifier les points de rupture.
 * Combine tous les endpoints critiques en proportion réaliste.
 *
 * Usage :
 *   k6 run -e BASE_URL=http://localhost:8000 -e TOKEN=$JWT tests/k6/full_stress.js
 *
 * ⚠️  À exécuter en dehors des heures de production ou sur un environnement de staging dédié.
 */
import http from "k6/http";
import { check, sleep, group } from "k6";
import { Rate, Trend, Counter } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const TOKEN    = __ENV.TOKEN    || "";

const errorRate    = new Rate("errors");
const p95Trend     = new Trend("all_requests_p95", true);
const requestTotal = new Counter("total_requests");

export const options = {
  scenarios: {
    // Scénario 1 : Utilisateurs actifs normaux (copilote, sinistres)
    normal_users: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "2m",  target: 30 },
        { duration: "4m",  target: 60 },
        { duration: "2m",  target: 30 },
        { duration: "2m",  target:  0 },
      ],
      gracefulRampDown: "30s",
    },
    // Scénario 2 : Pics de charge (fin de mois, arrêtés comptables)
    peak_load: {
      executor: "ramping-vus",
      startVUs: 0,
      startTime: "3m",
      stages: [
        { duration: "1m",  target: 100 },   // pic brutal
        { duration: "2m",  target: 100 },   // maintien
        { duration: "1m",  target:   0 },   // libération
      ],
      gracefulRampDown: "1m",
    },
  },
  thresholds: {
    http_req_duration:   ["p(95)<5000", "p(99)<10000"],
    http_req_failed:     ["rate<0.05"],    // max 5% d'erreurs en stress
    errors:              ["rate<0.05"],
  },
};

const headers = {
  "Content-Type": "application/json",
  Authorization: `Bearer ${TOKEN}`,
};

// Répartition réaliste du trafic :
// 40% copilote | 25% tarification | 20% sinistres | 10% CIMA | 5% santé
function getScenario(seed) {
  const r = seed % 100;
  if (r < 40) return "copilote";
  if (r < 65) return "tarification";
  if (r < 85) return "sinistres";
  if (r < 95) return "cima";
  return "health";
}

export default function () {
  const seed = __VU * 17 + __ITER;
  const scenario = getScenario(seed);

  const t0 = Date.now();
  let ok = true;

  switch (scenario) {
    case "copilote": {
      const r = http.post(
        `${BASE_URL}/api/v1/copilote/question-cima`,
        JSON.stringify({
          question: `Question stress test VU=${__VU} ITER=${__ITER} — délai CIMA sinistre auto ?`,
          contexte: "gestionnaire",
        }),
        { headers, timeout: "20s" }
      );
      ok = check(r, { "copilote 200/5xx ok": (res) => [200, 429, 503].includes(res.status) });
      break;
    }

    case "tarification": {
      const r = http.post(
        `${BASE_URL}/api/v1/tarification/calculer`,
        JSON.stringify({
          branche: seed % 2 === 0 ? "auto" : "ird",
          age_assure: 25 + (seed % 40),
          zone_geographique: "douala",
          puissance_fiscale_cv: 4 + (seed % 8),
          valeur_venale_fcfa: 1500000 + seed * 30000,
        }),
        { headers, timeout: "10s" }
      );
      ok = check(r, { "tarification 200": (res) => res.status === 200 });
      break;
    }

    case "sinistres": {
      const r = http.post(
        `${BASE_URL}/api/v1/sinistres/analyser-fraude`,
        JSON.stringify({
          sinistre_id: `STR-${__VU}-${__ITER}`,
          description: `Sinistre stress test — accident véhicule ${__VU}`,
          montant_reclame_fcfa: 500000 + seed * 5000,
          nb_sinistres_anterieurs: seed % 4,
          anciennete_contrat_mois: 6 + (seed % 48),
        }),
        { headers, timeout: "15s" }
      );
      ok = check(r, { "sinistres fraude 200": (res) => res.status === 200 });
      break;
    }

    case "cima": {
      const r = http.post(
        `${BASE_URL}/api/v1/cima/verifier-conformite`,
        JSON.stringify({
          primes_emises_fcfa: 2_500_000_000,
          fonds_propres_fcfa: 1_800_000_000,
          sinistres_payes_fcfa: 1_200_000_000,
          provisions_techniques_fcfa: 850_000_000,
          exercice: 2023,
          pays: "CM",
        }),
        { headers, timeout: "20s" }
      );
      ok = check(r, { "cima conformite 200": (res) => res.status === 200 });
      break;
    }

    default: {
      const r = http.get(`${BASE_URL}/health`);
      ok = check(r, { "health 200": (res) => res.status === 200 });
    }
  }

  p95Trend.add(Date.now() - t0);
  requestTotal.add(1);
  errorRate.add(!ok);

  sleep(0.5 + Math.random() * 1.5);
}

export function handleSummary(data) {
  const p95 = data.metrics.all_requests_p95?.values?.["p(95)"] || 0;
  const p99 = data.metrics.http_req_duration?.values?.["p(99)"] || 0;
  const errRate = (data.metrics.errors?.values?.rate || 0) * 100;
  const rps = data.metrics.http_reqs?.values?.rate || 0;

  return {
    stdout: `
╔══════════════════════════════════════════════════════╗
║         YukpoAssurance — Résultats Stress Test       ║
╠══════════════════════════════════════════════════════╣
║  Requêtes totales : ${String(data.metrics.total_requests?.values?.count || 0).padEnd(34)}║
║  Débit (req/s)    : ${String(rps.toFixed(1)).padEnd(34)}║
║  p95 latence      : ${String(p95.toFixed(0) + " ms").padEnd(34)}║
║  p99 latence      : ${String(p99.toFixed(0) + " ms").padEnd(34)}║
║  Taux d'erreur    : ${String(errRate.toFixed(2) + "%").padEnd(34)}║
╚══════════════════════════════════════════════════════╝
`,
  };
}
