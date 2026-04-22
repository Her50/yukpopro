/**
 * YukpoAssurance — Smoke Test k6
 * Vérification rapide que les endpoints critiques répondent correctement.
 * Usage : k6 run tests/k6/smoke.js
 */
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const TOKEN    = __ENV.TOKEN    || "";

const errorRate = new Rate("errors");

export const options = {
  vus: 1,
  duration: "30s",
  thresholds: {
    http_req_duration: ["p(95)<2000"],
    errors:            ["rate<0.05"],
  },
};

const headers = () => ({
  "Content-Type": "application/json",
  ...(TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {}),
});

export default function () {
  // ── Santé ────────────────────────────────────────────────────────────────
  {
    const r = http.get(`${BASE_URL}/health`);
    const ok = check(r, {
      "health: 200": (res) => res.status === 200,
      "health: statut ok": (res) => {
        try { return JSON.parse(res.body).statut === "ok"; } catch { return false; }
      },
    });
    errorRate.add(!ok);
  }

  sleep(0.5);

  // ── Santé SI (ORASS/Mercure) ─────────────────────────────────────────────
  {
    const r = http.get(`${BASE_URL}/health/si`);
    const ok = check(r, {
      "health/si: 200": (res) => res.status === 200,
    });
    errorRate.add(!ok);
  }

  sleep(0.5);

  // ── Barème tarifaire (sans IA — réponse rapide) ──────────────────────────
  {
    const r = http.get(`${BASE_URL}/api/v1/tarification/baremes/auto`, {
      headers: headers(),
    });
    const ok = check(r, {
      "barème auto: 200 ou 401": (res) => [200, 401].includes(res.status),
    });
    errorRate.add(!ok);
  }

  sleep(1);
}
