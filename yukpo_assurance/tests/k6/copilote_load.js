/**
 * YukpoAssurance — Test de charge : Copilote + IA
 * Simule des agents/courtiers utilisant l'assistant IA en simultané.
 *
 * Usage :
 *   k6 run -e BASE_URL=http://localhost:8000 -e TOKEN=$JWT tests/k6/copilote_load.js
 */
import http from "k6/http";
import { check, sleep, group } from "k6";
import { Rate, Trend } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const TOKEN    = __ENV.TOKEN    || "";

const errorRate      = new Rate("errors");
const iaLatency      = new Trend("ia_response_duration_ms", true);

export const options = {
  stages: [
    { duration: "1m",  target: 10 },   // montée en charge
    { duration: "3m",  target: 50 },   // charge nominale (50 agents simultanés)
    { duration: "1m",  target:  0 },   // descente
  ],
  thresholds: {
    http_req_duration:      ["p(95)<5000"],  // IA peut prendre jusqu'à 5s
    ia_response_duration_ms:["p(99)<8000"],  // 99% < 8s (raisonnement complexe)
    errors:                 ["rate<0.02"],   // < 2% d'erreurs
  },
};

const headers = {
  "Content-Type": "application/json",
  Authorization: `Bearer ${TOKEN}`,
};

// Questions CIMA variées pour éviter le cache (chaque VU pose une question légèrement différente)
const QUESTIONS_CIMA = [
  "Quel est le délai de règlement des sinistres automobiles selon l'article 12 du Code CIMA ?",
  "Comment calculer la provision PSAP pour un sinistre déclaré mais non encore liquidé ?",
  "Quelles sont les obligations de l'assuré en cas de sinistre incendie selon le Code CIMA ?",
  "Quel est le plafond de la garantie RC obligatoire automobile dans la zone CIMA ?",
  "Comment se calcule le coefficient de réduction-majoration (CRM) selon le barème CIMA ?",
  "Quelles branches d'assurance sont obligatoires selon le Livre II du Code CIMA ?",
  "Quelles sont les conditions de résiliation d'un contrat automobile à l'échéance ?",
  "Quel est le taux de provision pour risques en cours (PPNA) au prorata temporis ?",
  "Comment l'article 308 du Code CIMA encadre-t-il la réassurance obligatoire ?",
  "Quelle est la procédure de règlement à l'amiable des sinistres corporels auto ?",
];

const QUESTIONS_REDACTION = [
  "Rédige une lettre de relance de prime impayée pour un assuré ayant 30 jours de retard.",
  "Prépare un courrier de résiliation pour non-paiement de prime après mise en demeure.",
  "Rédige un avenant d'extension de garantie tous risques sur un contrat automobile.",
  "Prépare une déclaration de sinistre pour un accident de la circulation avec tiers.",
  "Rédige un accusé de réception de sinistre avec le numéro de dossier et les pièces à fournir.",
];

export default function () {
  const vuId = __VU % QUESTIONS_CIMA.length;

  // ── 1. Question CIMA ───────────────────────────────────────────────────
  group("copilote_cima", () => {
    const payload = JSON.stringify({
      question: QUESTIONS_CIMA[vuId],
      contexte: "conseiller_sinistres",
    });

    const t0 = Date.now();
    const r = http.post(`${BASE_URL}/api/v1/copilote/question-cima`, payload, { headers });
    const duration = Date.now() - t0;
    iaLatency.add(duration);

    const ok = check(r, {
      "copilote/question-cima: 200": (res) => res.status === 200,
      "réponse non vide": (res) => {
        try { return JSON.parse(res.body).reponse?.length > 20; } catch { return false; }
      },
    });
    errorRate.add(!ok);
  });

  sleep(2 + Math.random() * 2);   // pause réaliste 2-4s entre questions

  // ── 2. Calcul indemnité ────────────────────────────────────────────────
  group("copilote_indemnite", () => {
    const payload = JSON.stringify({
      type_sinistre: "corporel",
      age_victime: 30 + Math.floor(Math.random() * 30),
      salaire_mensuel_fcfa: 150000 + Math.floor(Math.random() * 200000),
      taux_invalidite_pct: Math.floor(Math.random() * 40),
      duree_itt_jours: Math.floor(Math.random() * 60),
    });

    const r = http.post(`${BASE_URL}/api/v1/copilote/calculer-indemnite`, payload, { headers });
    const ok = check(r, {
      "copilote/indemnite: 200": (res) => res.status === 200,
    });
    errorRate.add(!ok);
  });

  sleep(1 + Math.random());

  // ── 3. Rédaction courrier (1 VU sur 3 seulement pour limiter la charge IA)
  if (__VU % 3 === 0) {
    group("copilote_redaction", () => {
      const payload = JSON.stringify({
        type_courrier: "relance_prime",
        contexte: QUESTIONS_REDACTION[__VU % QUESTIONS_REDACTION.length],
        assure_nom: `Assuré Test ${__VU}`,
        police_numero: `POL-2024-${1000 + __VU}`,
      });

      const t0 = Date.now();
      const r = http.post(`${BASE_URL}/api/v1/copilote/rediger-courrier`, payload, { headers });
      iaLatency.add(Date.now() - t0);

      const ok = check(r, {
        "copilote/rediger-courrier: 200": (res) => res.status === 200,
      });
      errorRate.add(!ok);
    });
    sleep(3 + Math.random() * 2);
  }
}
