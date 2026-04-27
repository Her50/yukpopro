import { useState } from "react";
import { RefreshCw, FileText, BarChart3 } from "lucide-react";
import { cn, formatMontant } from "@/components/ui";

const TRAITES_DEMO = [
  { code: "QP-AUTO-2026",  type: "Quote-part 30%",      branche: "RC Auto",      prime_cedee: 54_000_000, sinistre_cede: 33_000_000, reassureur: "African Re",   statut: "actif" },
  { code: "XL-MRH-2026",   type: "Excédent de sinistre", branche: "MRH",         prime_cedee: 12_000_000, sinistre_cede: 0,          reassureur: "SCOR SE",     statut: "actif" },
  { code: "QP-VIE-2026",   type: "Quote-part 25%",      branche: "Vie",          prime_cedee: 12_500_000, sinistre_cede: 2_000_000,  reassureur: "AXA XL",      statut: "actif" },
  { code: "SL-ALL-2026",   type: "Stop-loss 80%",        branche: "Toutes",      prime_cedee: 22_000_000, sinistre_cede: 0,          reassureur: "Munich Re",   statut: "actif" },
];

const PML_DEMO = [
  { scenario: "Incendie majeur Douala",    prob: "1/100 ans", pml_brut: 850_000_000, pml_net: 120_000_000, couverture: "XL MRH" },
  { scenario: "Accident collectif (bus)", prob: "1/50 ans",  pml_brut: 450_000_000, pml_net: 85_000_000,  couverture: "QP Auto" },
  { scenario: "Épidémie Maladie",         prob: "1/20 ans",  pml_brut: 200_000_000, pml_net: 50_000_000,  couverture: "SL All" },
];

type Onglet = "programme" | "pml" | "bordereau";

export function ReassurancePage() {
  const [onglet, setOnglet] = useState<Onglet>("programme");

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="px-8 pt-8 pb-4">
        <h1 className="text-2xl font-bold text-white" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
          Réassurance
        </h1>
        <p className="text-sm text-gray-400 mt-0.5">Programme · PML · Bordereaux cessions</p>
      </div>

      {/* Onglets */}
      <div className="px-8 flex gap-2 mb-6">
        {[
          { id: "programme", label: "Programme", icon: RefreshCw },
          { id: "pml",       label: "PML / Scénarios", icon: BarChart3 },
          { id: "bordereau", label: "Bordereaux", icon: FileText },
        ].map(({ id, label, icon: Icon }) => (
          <button key={id} onClick={() => setOnglet(id as Onglet)}
            className={cn(
              "flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all border",
              onglet === id
                ? "text-white border-assurance-500/40"
                : "text-gray-400 border-white/[0.06] hover:text-gray-200 hover:bg-white/[0.04]"
            )}
            style={onglet === id ? { background: "linear-gradient(135deg, #0054A6 0%, #00B0F0 100%)", borderColor: "transparent" } : {}}>
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
      </div>

      {/* Programme de réassurance */}
      {onglet === "programme" && (
        <div className="px-8 space-y-4 max-w-3xl pb-8">
          {/* KPI cessions */}
          <div className="grid grid-cols-3 gap-4 mb-2">
            {[
              { label: "Primes cédées", val: formatMontant(100_500_000), sub: "27.2% du portefeuille" },
              { label: "Sinistres cédés", val: formatMontant(35_000_000), sub: "34.8% S/C cédés" },
              { label: "Solde technique", val: formatMontant(65_500_000), sub: "Résultat cessions net" },
            ].map(({ label, val, sub }) => (
              <div key={label} className="rounded-2xl border p-4" style={{ background: "rgba(17,24,39,0.8)", borderColor: "rgba(255,255,255,0.06)" }}>
                <p className="text-xs text-gray-500 mb-1">{label}</p>
                <p className="text-xl font-bold text-white">{val}</p>
                <p className="text-xs text-ciel-500 mt-0.5">{sub}</p>
              </div>
            ))}
          </div>

          {/* Traités */}
          {TRAITES_DEMO.map((t) => (
            <div key={t.code} className="rounded-2xl border p-5" style={{ background: "rgba(17,24,39,0.8)", borderColor: "rgba(255,255,255,0.06)" }}>
              <div className="flex items-start justify-between mb-3">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-mono text-sm text-ciel-400">{t.code}</span>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-green-500/10 text-green-400 border border-green-500/20">Actif</span>
                  </div>
                  <p className="text-sm font-semibold text-white">{t.type} — {t.branche}</p>
                  <p className="text-xs text-gray-500">Réassureur : {t.reassureur}</p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-xs text-gray-500 mb-0.5">Primes cédées</p>
                  <p className="font-semibold text-white">{formatMontant(t.prime_cedee)}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 mb-0.5">Sinistres cédés</p>
                  <p className="font-semibold text-white">{formatMontant(t.sinistre_cede)}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* PML */}
      {onglet === "pml" && (
        <div className="px-8 space-y-4 max-w-2xl pb-8">
          <p className="text-sm text-gray-400 mb-2">Scénarios de Perte Maximale Probable (PML) :</p>
          {PML_DEMO.map((p) => (
            <div key={p.scenario} className="rounded-2xl border p-5" style={{ background: "rgba(17,24,39,0.8)", borderColor: "rgba(255,255,255,0.06)" }}>
              <div className="flex justify-between items-start mb-3">
                <div>
                  <p className="text-sm font-semibold text-white">{p.scenario}</p>
                  <p className="text-xs text-gray-500">Probabilité : {p.prob} · Couverture : {p.couverture}</p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-xs text-gray-500 mb-0.5">PML Brut</p>
                  <p className="text-lg font-bold text-alerte-400">{formatMontant(p.pml_brut)}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 mb-0.5">PML Net (après cession)</p>
                  <p className="text-lg font-bold text-green-400">{formatMontant(p.pml_net)}</p>
                </div>
              </div>
              <div className="mt-3 h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
                <div className="h-full rounded-full bg-gradient-to-r from-alerte-500 to-green-500"
                  style={{ width: `${Math.round(p.pml_net / p.pml_brut * 100)}%` }} />
              </div>
              <p className="text-xs text-gray-500 mt-1 text-right">Rétention : {Math.round(p.pml_net / p.pml_brut * 100)}%</p>
            </div>
          ))}
        </div>
      )}

      {/* Bordereau */}
      {onglet === "bordereau" && (
        <div className="px-8 max-w-xl pb-8">
          <p className="text-sm text-gray-400 mb-4">Bordereaux de cessions — T1 2026 :</p>
          <div className="rounded-2xl border overflow-hidden" style={{ background: "rgba(17,24,39,0.8)", borderColor: "rgba(255,255,255,0.06)" }}>
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-white/[0.06]">
                  {["Traité", "Branche", "Primes cédées", "S. cédés", "Solde"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-gray-500 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {TRAITES_DEMO.map((t) => (
                  <tr key={t.code} className="border-b border-white/[0.03] hover:bg-white/[0.02]">
                    <td className="px-4 py-3 font-mono text-ciel-400">{t.code}</td>
                    <td className="px-4 py-3 text-gray-300">{t.branche}</td>
                    <td className="px-4 py-3 text-white">{formatMontant(t.prime_cedee)}</td>
                    <td className="px-4 py-3 text-alerte-400">{formatMontant(t.sinistre_cede)}</td>
                    <td className="px-4 py-3 text-green-400 font-semibold">{formatMontant(t.prime_cedee - t.sinistre_cede)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
