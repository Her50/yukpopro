import { useEffect, useState } from "react";
import {
  TrendingUp, TrendingDown, ShieldCheck, FileText,
  AlertTriangle, BarChart3, Scale, RefreshCw,
} from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from "recharts";
import { cn, formatMontant } from "@/components/ui";
import { dashboardApi } from "@/api/client";

// ── Données démo ───────────────────────────────────────────────────────────────

const DEMO_KPIS = {
  primes_nettes_fcfa: 485_000_000,
  ratio_sp_pct: 62.4,
  marge_solvabilite_pct: 138.7,
  polices_actives: 3_241,
  sinistres_ouverts: 47,
  sinistres_en_souffrance: 3,
  taux_fraude_pct: 2.1,
  reservations_cima_fcfa: 92_000_000,
};

const DEMO_BRANCHES = [
  { branche: "RC Auto",  primes: 180, sinistres: 110 },
  { branche: "MRH",      primes: 95,  sinistres: 42 },
  { branche: "Transport",primes: 75,  sinistres: 38 },
  { branche: "Maladie",  primes: 65,  sinistres: 55 },
  { branche: "Vie",      primes: 50,  sinistres: 8 },
  { branche: "RC Gén.",  primes: 20,  sinistres: 12 },
];

const DEMO_PIE = [
  { name: "RC Auto", value: 37, color: "#0054A6" },
  { name: "MRH",     value: 20, color: "#00B0F0" },
  { name: "Transport",value: 15, color: "#22c55e" },
  { name: "Maladie", value: 13, color: "#f97316" },
  { name: "Vie",     value: 10, color: "#a855f7" },
  { name: "Autres",  value: 5,  color: "#6B7280" },
];

const DEMO_ALERTES = [
  { niveau: "error",   message: "3 sinistres en souffrance dépassent 90j (Art. 12-bis CIMA)" },
  { niveau: "warning", message: "Marge de solvabilité proche du seuil (138.7% — min 100%)" },
  { niveau: "info",    message: "États C5 trimestriels à déposer avant le 30/04/2026" },
];

// ── KPI Card ──────────────────────────────────────────────────────────────────

function KpiCard({ label, value, sub, trend, icon: Icon, color = "blue" }: {
  label: string; value: string; sub?: string; trend?: "up" | "down" | "neutral";
  icon: React.ComponentType<{ className?: string }>; color?: "blue" | "green" | "red" | "orange";
}) {
  const colors = {
    blue:   { bg: "rgba(0,84,166,0.12)",  border: "rgba(0,84,166,0.25)",  icon: "text-ciel-400" },
    green:  { bg: "rgba(34,197,94,0.12)", border: "rgba(34,197,94,0.25)", icon: "text-green-400" },
    red:    { bg: "rgba(239,68,68,0.12)", border: "rgba(239,68,68,0.25)", icon: "text-red-400" },
    orange: { bg: "rgba(249,115,22,0.12)",border: "rgba(249,115,22,0.25)",icon: "text-alerte-400" },
  }[color];

  return (
    <div className="rounded-2xl p-5 border" style={{ background: "rgba(17,24,39,0.8)", borderColor: "rgba(255,255,255,0.06)" }}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-gray-500 font-medium mb-1">{label}</p>
          <p className="text-xl font-bold text-white">{value}</p>
          {sub && <p className="text-xs text-gray-500 mt-0.5">{sub}</p>}
        </div>
        <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ background: colors.bg, border: `1px solid ${colors.border}` }}>
          <Icon className={cn("w-5 h-5", colors.icon)} />
        </div>
      </div>
      {trend && (
        <div className={cn("flex items-center gap-1 mt-3 text-xs font-medium",
          trend === "up" ? "text-green-400" : trend === "down" ? "text-red-400" : "text-gray-500")}>
          {trend === "up" && <TrendingUp className="w-3 h-3" />}
          {trend === "down" && <TrendingDown className="w-3 h-3" />}
          {trend === "up" ? "+8.2% vs trimestre précédent" : trend === "down" ? "-3.1% vs trimestre précédent" : "Stable"}
        </div>
      )}
    </div>
  );
}

// ── Dashboard Page ─────────────────────────────────────────────────────────────

export function DashboardPage() {
  const [kpis, setKpis] = useState(DEMO_KPIS);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    dashboardApi.kpis()
      .then((res) => setKpis(res.data as typeof DEMO_KPIS))
      .catch(() => {})
      .then(() => setLoading(false));
  }, []);

  return (
    <div className="flex-1 overflow-y-auto">
      {/* Header */}
      <div className="px-8 pt-8 pb-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
              Tableau de bord
            </h1>
            <p className="text-sm text-gray-400 mt-0.5">Indicateurs CIMA · Exercice 2026</p>
          </div>
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <RefreshCw className={cn("w-3.5 h-3.5", loading && "animate-spin")} />
            Actualisé il y a 2 min
          </div>
        </div>
      </div>

      {/* Alertes CIMA */}
      <div className="px-8 mb-6 space-y-2">
        {DEMO_ALERTES.map((a, i) => (
          <div key={i} className={cn(
            "flex items-center gap-3 rounded-xl px-4 py-2.5 text-sm border",
            a.niveau === "error"   ? "bg-red-500/10 border-red-500/20 text-red-300" :
            a.niveau === "warning" ? "bg-alerte-500/10 border-alerte-500/20 text-alerte-300" :
                                     "bg-assurance-500/10 border-assurance-500/20 text-ciel-300"
          )}>
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            {a.message}
          </div>
        ))}
      </div>

      {/* KPIs */}
      <div className="px-8 grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <KpiCard label="Primes nettes" value={formatMontant(kpis.primes_nettes_fcfa)} sub="YTD 2026" trend="up" icon={BarChart3} color="blue" />
        <KpiCard label="Ratio S/P" value={`${kpis.ratio_sp_pct}%`} sub={kpis.ratio_sp_pct < 80 ? "✓ Conforme" : "⚠ Vigilance"} trend={kpis.ratio_sp_pct < 80 ? "up" : "down"} icon={Scale} color={kpis.ratio_sp_pct < 80 ? "green" : "orange"} />
        <KpiCard label="Marge solvabilité" value={`${kpis.marge_solvabilite_pct}%`} sub="Minimum CIMA: 100%" trend="neutral" icon={ShieldCheck} color={kpis.marge_solvabilite_pct >= 120 ? "green" : "orange"} />
        <KpiCard label="Polices actives" value={kpis.polices_actives.toLocaleString("fr-FR")} trend="up" icon={FileText} color="blue" />
        <KpiCard label="Sinistres ouverts" value={kpis.sinistres_ouverts.toString()} sub={`dont ${kpis.sinistres_en_souffrance} en souffrance`} icon={ShieldCheck} color={kpis.sinistres_en_souffrance > 0 ? "red" : "green"} />
        <KpiCard label="Taux de fraude" value={`${kpis.taux_fraude_pct}%`} sub="Détectée par IA" icon={AlertTriangle} color="orange" />
        <KpiCard label="Provisions CIMA" value={formatMontant(kpis.reservations_cima_fcfa)} sub="PSAP + PM" icon={BarChart3} color="blue" />
        <KpiCard label="Délai moyen" value="18 j" sub="Offre d'indemnisation · Art. 12-bis" trend="up" icon={RefreshCw} color="green" />
      </div>

      {/* Charts */}
      <div className="px-8 grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">

        {/* Barres primes vs sinistres */}
        <div className="rounded-2xl border p-6" style={{ background: "rgba(17,24,39,0.8)", borderColor: "rgba(255,255,255,0.06)" }}>
          <h3 className="text-sm font-semibold text-white mb-4">Primes vs Sinistres par branche (M FCFA)</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={DEMO_BRANCHES} barCategoryGap="30%">
              <XAxis dataKey="branche" tick={{ fill: "#6B7280", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#6B7280", fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{ background: "#1F2937", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12, fontSize: 12 }}
                labelStyle={{ color: "#F9FAFB" }}
              />
              <Bar dataKey="primes"    fill="#0054A6" radius={[4, 4, 0, 0]} name="Primes" />
              <Bar dataKey="sinistres" fill="#00B0F0" radius={[4, 4, 0, 0]} name="Sinistres" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Pie répartition */}
        <div className="rounded-2xl border p-6" style={{ background: "rgba(17,24,39,0.8)", borderColor: "rgba(255,255,255,0.06)" }}>
          <h3 className="text-sm font-semibold text-white mb-4">Répartition du portefeuille</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={DEMO_PIE} cx="50%" cy="50%" innerRadius={55} outerRadius={85}
                dataKey="value" paddingAngle={3}>
                {DEMO_PIE.map((entry, i) => (
                  <Cell key={i} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ background: "#1F2937", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12, fontSize: 12 }}
              />
              <Legend formatter={(v) => <span style={{ color: "#9CA3AF", fontSize: 11 }}>{v}</span>} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
