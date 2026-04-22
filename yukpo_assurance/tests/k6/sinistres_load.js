/**
 * YukpoAssurance — Test de charge : Workflow Sinistres
 * Simule la réception, l'analyse fraude et la validation de sinistres auto.
 *
 * Usage :
 *   k6 run -e BASE_URL=http://localhost:8000 -e TOKEN=$JWT tests/k6/sinistres_load.js
 */
import http from "k6/http";
import { check, sleep, group } from "k6";
import { Rate, Counter, Trend } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const TOKEN    = __ENV.TOKEN    || "";

const errorRate        = new Rate("errors");
const fraudeDetectees  = new Counter("fraudes_detectees");
const fraudeLatency    = new Trend("fraude_analyse_ms", true);

export const options = {
  stages: [
    { duration: "1m",  target:  5 },   // montée
    { duration: "3m",  target: 25 },   // charge (25 gestionnaires simultanés)
    { duration: "1m",  target:  0 },   // descente
  ],
  thresholds: {
    http_req_duration:  ["p(95)<3000"],
    fraude_analyse_ms:  ["p(99)<6000"],  // analyse fraude IA < 6s
    errors:             ["rate<0.02"],
  },
};

const headers = {
  "Content-Type": "application/json",
  Authorization: `Bearer ${TOKEN}`,
};

// Génère un sinistre réaliste avec variations
function genererSinistre(vuId) {
  const types = ["collision", "vol", "incendie", "bris_glace", "catastrophe_naturelle"];
  const zones  = ["douala", "yaounde", "abidjan", "dakar", "libreville"];
  const isLitigieux = vuId % 7 === 0;  // 1 sur 7 → potentiellement frauduleux

  return {
    police_numero: `POL-2024-${10000 + vuId}`,
    type_sinistre: types[vuId % types.length],
    date_sinistre: "2024-03-15",
    lieu_sinistre: zones[vuId % zones.length],
    description: isLitigieux
      ? `Sinistre déclaré 48h après les faits. Tiers non identifié. Véhicule déjà sinistré 2 fois en 12 mois. Montant demandé: ${2000000 + vuId * 50000} FCFA.`
      : `Accrochage au carrefour. Constat amiable signé. Dommages matériels estimés à ${300000 + vuId * 10000} FCFA.`,
    montant_reclame_fcfa: isLitigieux ? 2000000 + vuId * 50000 : 300000 + vuId * 10000,
    assure_nom: `Assure Test ${vuId}`,
    assure_age: 25 + (vuId % 40),
    anciennete_contrat_mois: 3 + (vuId % 60),
    nb_sinistres_anterieurs: isLitigieux ? 3 : 0,
    pieces_fournies: ["constat", "photos"],
    documents_manquants: isLitigieux ? ["rapport_expertise"] : [],
  };
}

export default function () {
  const vuId = __VU * 100 + __ITER;

  // ── 1. Déclaration de sinistre ─────────────────────────────────────────
  let sinistre_id = null;
  group("reception_sinistre", () => {
    const payload = JSON.stringify(genererSinistre(vuId));
    const r = http.post(`${BASE_URL}/api/v1/sinistres/declarer`, payload, { headers });
    const ok = check(r, {
      "sinistres/declarer: 200 ou 201": (res) => [200, 201].includes(res.status),
    });
    errorRate.add(!ok);

    if (ok) {
      try {
        const body = JSON.parse(r.body);
        sinistre_id = body.sinistre_id || body.id;
      } catch { /* continue */ }
    }
  });

  sleep(0.5);

  // ── 2. Analyse fraude ──────────────────────────────────────────────────
  group("analyse_fraude", () => {
    const payload = JSON.stringify({
      sinistre_id: sinistre_id || `SIN-TEST-${vuId}`,
      description: `Description sinistre #${vuId} pour analyse fraude`,
      montant_reclame_fcfa: 500000 + vuId * 1000,
      nb_sinistres_anterieurs: vuId % 5,
      anciennete_contrat_mois: 12 + (vuId % 48),
      vehicule_age_ans: vuId % 15,
    });

    const t0 = Date.now();
    const r = http.post(`${BASE_URL}/api/v1/sinistres/analyser-fraude`, payload, { headers });
    fraudeLatency.add(Date.now() - t0);

    const ok = check(r, {
      "sinistres/analyser-fraude: 200": (res) => res.status === 200,
      "score fraude présent": (res) => {
        try {
          const body = JSON.parse(res.body);
          return typeof body.score_fraude === "number";
        } catch { return false; }
      },
    });
    errorRate.add(!ok);

    // Compter les fraudes détectées (score > 70)
    try {
      const body = JSON.parse(r.body);
      if (body.score_fraude > 70) fraudeDetectees.add(1);
    } catch { /* continue */ }
  });

  sleep(0.5);

  // ── 3. Liste des sinistres en cours ───────────────────────────────────
  group("liste_sinistres", () => {
    const r = http.get(
      `${BASE_URL}/api/v1/sinistres?statut=en_cours&page=1&limit=20`,
      { headers }
    );
    const ok = check(r, {
      "sinistres list: 200": (res) => res.status === 200,
    });
    errorRate.add(!ok);
  });

  sleep(1 + Math.random() * 2);
}
