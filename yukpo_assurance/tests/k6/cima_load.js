/**
 * YukpoAssurance — Test de charge : Conformité CIMA + États C1-C20
 * Simule des actuaires et direction générale accédant aux états réglementaires.
 *
 * Usage :
 *   k6 run -e BASE_URL=http://localhost:8000 -e TOKEN=$JWT tests/k6/cima_load.js
 */
import http from "k6/http";
import { check, sleep, group } from "k6";
import { Rate, Trend } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const TOKEN    = __ENV.TOKEN    || "";

const errorRate         = new Rate("errors");
const conformiteLatency = new Trend("conformite_check_ms", true);
const etatLatency       = new Trend("etat_generation_ms", true);

export const options = {
  stages: [
    { duration: "1m",  target:  5 },
    { duration: "3m",  target: 20 },
    { duration: "1m",  target:  0 },
  ],
  thresholds: {
    http_req_duration:    ["p(95)<10000"],  // États CIMA peuvent prendre jusqu'à 10s (IA + calculs)
    conformite_check_ms:  ["p(99)<8000"],
    etat_generation_ms:   ["p(99)<12000"],
    errors:               ["rate<0.02"],
  },
};

const headers = {
  "Content-Type": "application/json",
  Authorization: `Bearer ${TOKEN}`,
};

// Données financières types d'une compagnie CIMA (anonymisées)
const DONNEES_COMPAGNIE = {
  primes_emises_fcfa: 2_500_000_000,
  primes_cedees_fcfa:   375_000_000,
  sinistres_payes_fcfa: 1_200_000_000,
  provisions_techniques_fcfa: 850_000_000,
  fonds_propres_fcfa: 1_800_000_000,
  total_bilan_fcfa: 6_500_000_000,
  placements_actifs_fcfa: 3_200_000_000,
  frais_gestion_fcfa: 420_000_000,
  branches: ["auto", "ird", "rc", "transport", "vie"],
  pays: "CM",
  exercice: 2023,
};

export default function () {
  // ── 1. Vérification conformité CIMA globale ───────────────────────────
  group("conformite_globale", () => {
    const t0 = Date.now();
    const r = http.post(
      `${BASE_URL}/api/v1/cima/verifier-conformite`,
      JSON.stringify(DONNEES_COMPAGNIE),
      { headers }
    );
    conformiteLatency.add(Date.now() - t0);

    const ok = check(r, {
      "cima/conformite: 200": (res) => res.status === 200,
      "résultat conformité présent": (res) => {
        try {
          const body = JSON.parse(res.body);
          return body.statut_conformite !== undefined;
        } catch { return false; }
      },
    });
    errorRate.add(!ok);
  });

  sleep(2);

  // ── 2. Calcul provision PSAP (1 VU sur 2) ────────────────────────────
  if (__VU % 2 === 0) {
    group("provision_psap", () => {
      const r = http.post(
        `${BASE_URL}/api/v1/cima/provisions/psap`,
        JSON.stringify({
          methode: "dossier_par_dossier",
          sinistres_ouverts: [
            { id: "S001", montant_estime_fcfa: 2_500_000, anciennete_jours: 90 },
            { id: "S002", montant_estime_fcfa: 8_000_000, anciennete_jours: 180 },
            { id: "S003", montant_estime_fcfa: 450_000,   anciennete_jours: 30 },
          ],
          exercice: 2023,
        }),
        { headers }
      );
      const ok = check(r, {
        "provisions/psap: 200": (res) => res.status === 200,
      });
      errorRate.add(!ok);
    });

    sleep(1.5);
  }

  // ── 3. État C5 (rapport sur provisions — lourd, 1 VU sur 5 seulement)
  if (__VU % 5 === 0) {
    group("etat_C5", () => {
      const t0 = Date.now();
      const r = http.post(
        `${BASE_URL}/api/v1/cima/rapport-complet`,
        JSON.stringify({
          exercice: 2023,
          compagnie_id: `COMP_TEST_${__VU}`,
          ...DONNEES_COMPAGNIE,
        }),
        { headers, timeout: "30s" }
      );
      etatLatency.add(Date.now() - t0);

      const ok = check(r, {
        "cima/rapport-complet: 200": (res) => res.status === 200,
      });
      errorRate.add(!ok);
    });

    sleep(5);
  }

  // ── 4. Question CIMA rapide ───────────────────────────────────────────
  group("question_cima_rapide", () => {
    const questions = [
      "Quel est le ratio de couverture des engagements réglementaires (Art. 337 CIMA) ?",
      "Délai de production du C1 après clôture de l'exercice ?",
      "Quels actifs admis en représentation des provisions techniques selon CIMA ?",
    ];
    const q = questions[__VU % questions.length];

    const r = http.post(
      `${BASE_URL}/api/v1/copilote/question-cima`,
      JSON.stringify({ question: q, contexte: "actuaire" }),
      { headers }
    );
    const ok = check(r, {
      "copilote/cima-rapide: 200": (res) => res.status === 200,
    });
    errorRate.add(!ok);
  });

  sleep(2 + Math.random() * 3);
}
