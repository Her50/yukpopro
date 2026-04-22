/**
 * YukpoAssurance — Test de charge : Tarification actuarielle + ML
 * Simule des demandes de devis en parallèle (souscripteurs + agents).
 *
 * Usage :
 *   k6 run -e BASE_URL=http://localhost:8000 -e TOKEN=$JWT tests/k6/tarification_load.js
 */
import http from "k6/http";
import { check, sleep, group } from "k6";
import { Rate, Trend } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const TOKEN    = __ENV.TOKEN    || "";

const errorRate    = new Rate("errors");
const mlLatency    = new Trend("ml_predict_ms", true);
const calcLatency  = new Trend("calc_prime_ms", true);

export const options = {
  stages: [
    { duration: "1m",  target: 10 },
    { duration: "3m",  target: 30 },
    { duration: "1m",  target:  0 },
  ],
  thresholds: {
    http_req_duration: ["p(95)<2000"],  // tarification sans IA < 2s
    ml_predict_ms:     ["p(99)<4000"],  // ML prediction < 4s
    calc_prime_ms:     ["p(95)<1500"],  // calcul actuariel < 1.5s
    errors:            ["rate<0.01"],
  },
};

const headers = {
  "Content-Type": "application/json",
  Authorization: `Bearer ${TOKEN}`,
};

const ZONES  = ["yaounde", "douala", "bafoussam", "abidjan", "dakar", "libreville"];
const USAGES = ["particulier", "societe", "utilitaire", "taxi"];

export default function () {
  const seed = __VU * 13 + __ITER;

  // ── 1. Calcul de prime auto (actuariel) ───────────────────────────────
  group("calcul_prime_auto", () => {
    const payload = JSON.stringify({
      branche: "auto",
      age_assure: 25 + (seed % 45),
      zone_geographique: ZONES[seed % ZONES.length],
      puissance_fiscale_cv: 4 + (seed % 10),
      annee_vehicule: 2010 + (seed % 14),
      usage: USAGES[seed % USAGES.length],
      valeur_venale_fcfa: 2000000 + seed * 50000,
      sinistres_5_ans: seed % 4,
    });

    const t0 = Date.now();
    const r = http.post(`${BASE_URL}/api/v1/tarification/calculer`, payload, { headers });
    calcLatency.add(Date.now() - t0);

    const ok = check(r, {
      "tarification/calculer: 200": (res) => res.status === 200,
      "prime nette présente": (res) => {
        try { return JSON.parse(res.body).prime_nette_fcfa > 0; } catch { return false; }
      },
    });
    errorRate.add(!ok);
  });

  sleep(0.5);

  // ── 2. Prédiction ML ─────────────────────────────────────────────────
  group("ml_prediction", () => {
    const payload = JSON.stringify({
      age_conducteur: 25 + (seed % 45),
      anciennete_permis: seed % 30,
      nb_sinistres_3ans: seed % 3,
      nb_infractions_3ans: seed % 2,
      score_bonus_malus: 0.8 + (seed % 15) * 0.1,
      puissance_fiscale_cv: 4 + (seed % 10),
      age_vehicule_ans: seed % 20,
      valeur_venale_mfcfa: 3.0 + (seed % 20) * 1.5,
      usage: USAGES[seed % USAGES.length],
      zone: ZONES[seed % ZONES.length],
      mois_souscription: 1 + (seed % 12),
      branche: "auto_rc",
      prime_actuarielle_fcfa: 100000 + seed * 5000,
      taux_cession_reassurance: 0.15,
      ratio_sp_branche: 0.55 + (seed % 10) * 0.05,
    });

    const t0 = Date.now();
    const r = http.post(`${BASE_URL}/api/v1/tarification/ml/predire`, payload, { headers });
    mlLatency.add(Date.now() - t0);

    const ok = check(r, {
      "ml/predire: 200": (res) => res.status === 200,
      "score risque 0-100": (res) => {
        try {
          const b = JSON.parse(res.body);
          return b.score_risque >= 0 && b.score_risque <= 100;
        } catch { return false; }
      },
    });
    errorRate.add(!ok);
  });

  sleep(0.5);

  // ── 3. Multi-scénarios (1 VU sur 4) ─────────────────────────────────
  if (seed % 4 === 0) {
    group("multi_scenarios", () => {
      const payload = JSON.stringify({
        branche: "ird",
        age_assure: 35 + (seed % 30),
        zone_geographique: ZONES[seed % ZONES.length],
        valeur_bien_fcfa: 5000000 + seed * 100000,
        type_construction: "dur_standard",
        garanties_ird: ["incendie", "vol", "degat_eaux"],
      });

      const r = http.post(`${BASE_URL}/api/v1/tarification/simuler-multi-scenarios`, payload, { headers });
      const ok = check(r, {
        "multi-scenarios: 200": (res) => res.status === 200,
        "3 offres présentes": (res) => {
          try { return JSON.parse(res.body).offres_comparatives?.length === 3; } catch { return false; }
        },
      });
      errorRate.add(!ok);
    });
    sleep(1);
  }

  sleep(1 + Math.random());
}
