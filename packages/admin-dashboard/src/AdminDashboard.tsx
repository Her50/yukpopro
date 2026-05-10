/**
 * Dashboard administrateur unifié — partagé entre YukpoPro et YukpoSecrétariat.
 *
 * Onglets : Overview / Consommation API / Alertes / Top Users / Providers.
 * Sélecteur de scope (Pro / Sec / Both) en haut, persisté en localStorage.
 *
 * L'app hôte injecte son instance axios (avec son intercepteur JWT) — le
 * composant reste agnostique à l'auth. Le baseURL doit déjà être configuré
 * (typiquement "/api/v1").
 */
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, BarChart3, Bell, Cpu, DollarSign, Layers, RefreshCw,
  TrendingUp, Users as UsersIcon, Zap,
} from "lucide-react";
import {
  adminCrossApi, type AppScope, type HttpClient,
  type DashboardKPIs, type UsageDay, type FeatureRow,
  type ProviderRow, type UserRow, type AlerteRow,
} from "./api";

export type { AppScope };

export interface AdminDashboardProps {
  /** Client HTTP injecté (axios ou équivalent), avec auth + baseURL "/api/v1". */
  http: HttpClient;
  /** Nom court de l'app hôte (affiché dans le header). */
  appLabel?: string;
  /** Scope par défaut si pas de préférence en localStorage. */
  defaultScope?: AppScope;
  /** Période en jours par défaut (1-365). */
  defaultJours?: number;
  /** Si fourni, surcharge la clé localStorage de persistance du scope. */
  storageKey?: string;
}

type Onglet = "overview" | "consommation" | "providers" | "users" | "alerts";

const TABS: { id: Onglet; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: "overview",     label: "Vue d'ensemble",  icon: BarChart3 },
  { id: "consommation", label: "Consommation API", icon: Cpu },
  { id: "providers",    label: "Fournisseurs",    icon: Layers },
  { id: "users",        label: "Top utilisateurs", icon: UsersIcon },
  { id: "alerts",       label: "Alertes",         icon: Bell },
];

const PERIODES = [
  { jours: 1,   label: "24h" },
  { jours: 7,   label: "7j" },
  { jours: 30,  label: "30j" },
  { jours: 90,  label: "90j" },
  { jours: 365, label: "1 an" },
];

export const AdminDashboard = ({
  http,
  appLabel = "Yukpo",
  defaultScope = "both",
  defaultJours = 30,
  storageKey = "yukpo_admin_cross_scope",
}: AdminDashboardProps) => {
  const api = useMemo(() => adminCrossApi(http), [http]);

  // ── Scope (persisté) ──────────────────────────────────────────────────
  const [scope, setScopeState] = useState<AppScope>(() => {
    try {
      const saved = localStorage.getItem(storageKey);
      if (saved === "pro" || saved === "sec" || saved === "both") return saved;
    } catch { /* ignore */ }
    return defaultScope;
  });
  const setScope = (s: AppScope) => {
    setScopeState(s);
    try { localStorage.setItem(storageKey, s); } catch { /* ignore */ }
  };

  const [jours, setJours] = useState<number>(defaultJours);
  const [tab, setTab] = useState<Onglet>("overview");
  const [refreshTick, setRefreshTick] = useState(0);
  const refresh = () => setRefreshTick(t => t + 1);

  // ── Données ──────────────────────────────────────────────────────────
  const [kpis, setKpis] = useState<DashboardKPIs | null>(null);
  const [usage, setUsage] = useState<UsageDay[]>([]);
  const [features, setFeatures] = useState<FeatureRow[]>([]);
  const [providers, setProviders] = useState<ProviderRow[]>([]);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [alertes, setAlertes] = useState<AlerteRow[]>([]);
  const [alertesResume, setAlertesResume] = useState<{ critical: number; warning: number; info: number }>({ critical: 0, warning: 0, info: 0 });
  const [chargement, setChargement] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);

  useEffect(() => {
    let annule = false;
    setChargement(true);
    setErreur(null);

    Promise.all([
      api.dashboard(scope, jours),
      api.usage(scope, jours),
      api.byFeature(scope, jours, 50),
      api.byProvider(scope, jours),
      api.byUser(scope, jours, 20),
      api.alerts(scope),
    ]).then(([kp, us, ft, pr, usr, al]) => {
      if (annule) return;
      setKpis(kp);
      setUsage(us.series);
      setFeatures(ft.features);
      setProviders(pr.providers);
      setUsers(usr.users);
      setAlertes(al.alertes);
      setAlertesResume(al.par_severite);
    }).catch((e: any) => {
      if (annule) return;
      const msg = e?.response?.data?.detail || e?.message || "Erreur de chargement";
      setErreur(typeof msg === "string" ? msg : "Erreur de chargement");
    }).finally(() => {
      if (!annule) setChargement(false);
    });

    return () => { annule = true; };
  }, [api, scope, jours, refreshTick]);

  return (
    <div className="space-y-6">

      {/* ── Header : titre + scope + période + refresh ──────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">Administration cross-app</h1>
          <p className="text-sm text-slate-400">
            {appLabel} — vue unifiée Pro + Secrétariat ·{" "}
            {chargement ? "chargement…" : `${alertesResume.critical} critique · ${alertesResume.warning} alertes`}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Scope toggle */}
          <div className="inline-flex rounded-lg border border-slate-600 bg-slate-800 p-0.5 text-xs">
            {(["pro", "sec", "both"] as AppScope[]).map(s => (
              <button
                key={s}
                onClick={() => setScope(s)}
                className={
                  "px-3 py-1.5 rounded-md font-semibold transition-colors " +
                  (scope === s
                    ? "bg-yukpo-600 text-white"
                    : "text-slate-300 hover:bg-slate-700")
                }
              >
                {s === "pro" ? "YukpoPro" : s === "sec" ? "Secrétariat" : "Les deux"}
              </button>
            ))}
          </div>

          {/* Période */}
          <select
            value={jours}
            onChange={e => setJours(parseInt(e.target.value, 10) || 30)}
            className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-1.5 text-xs text-white"
          >
            {PERIODES.map(p => (
              <option key={p.jours} value={p.jours}>{p.label}</option>
            ))}
          </select>

          <button
            onClick={refresh}
            disabled={chargement}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-600 bg-slate-800 px-3 py-1.5 text-xs text-white hover:bg-slate-700 disabled:opacity-50"
            title="Rafraîchir"
          >
            <RefreshCw className={"w-3.5 h-3.5 " + (chargement ? "animate-spin" : "")} />
            Actualiser
          </button>
        </div>
      </div>

      {/* ── Bandeau d'erreur ────────────────────────────────────────────────── */}
      {erreur && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          ⚠ {erreur}
        </div>
      )}

      {/* ── Tabs ────────────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-1 border-b border-slate-700">
        {TABS.map(({ id, label, icon: Icon }) => {
          const isCritical = id === "alerts" && alertesResume.critical > 0;
          return (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={
                "inline-flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors " +
                (tab === id
                  ? "border-yukpo-500 text-white"
                  : "border-transparent text-slate-400 hover:text-white hover:border-slate-600")
              }
            >
              <Icon className="w-4 h-4" />
              {label}
              {id === "alerts" && alertes.length > 0 && (
                <span className={
                  "ml-1 inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full text-[10px] font-bold " +
                  (isCritical ? "bg-red-500 text-white" : "bg-amber-500 text-white")
                }>
                  {alertes.length}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* ── Contenu ────────────────────────────────────────────────────────── */}
      {tab === "overview"     && <OverviewTab kpis={kpis} usage={usage} />}
      {tab === "consommation" && <ConsommationTab features={features} usage={usage} />}
      {tab === "providers"    && <ProvidersTab providers={providers} />}
      {tab === "users"        && <UsersTab users={users} />}
      {tab === "alerts"       && <AlertsTab alertes={alertes} resume={alertesResume} />}
    </div>
  );
};


// ══════════════════════════════════════════════════════════════════════════════
// OVERVIEW
// ══════════════════════════════════════════════════════════════════════════════

const OverviewTab = ({ kpis, usage }: { kpis: DashboardKPIs | null; usage: UsageDay[] }) => {
  if (!kpis) return <div className="text-sm text-slate-500">Chargement…</div>;
  const total = kpis.consommation.total;

  return (
    <div className="space-y-6">
      {/* KPIs principaux */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard
          icon={UsersIcon}
          label="Utilisateurs actifs"
          value={kpis.utilisateurs.actifs.toLocaleString("fr-FR")}
          sub={`${kpis.utilisateurs.total.toLocaleString("fr-FR")} comptes au total`}
          accent="blue"
        />
        <KpiCard
          icon={Zap}
          label="Appels IA"
          value={total.appels.toLocaleString("fr-FR")}
          sub={`${formatTokens(total.tokens_in + total.tokens_out)} tokens`}
          accent="violet"
        />
        <KpiCard
          icon={DollarSign}
          label="Coût IA"
          value={formatFCFA(total.fcfa)}
          sub={`${formatCredits(total.credits)} crédits débités`}
          accent="emerald"
        />
        <KpiCard
          icon={TrendingUp}
          label="Crédits alloués"
          value={(kpis.credits_alloues.pro + kpis.credits_alloues.sec).toLocaleString("fr-FR")}
          sub={`Pro: ${kpis.credits_alloues.pro.toLocaleString("fr-FR")} · Sec: ${kpis.credits_alloues.sec.toLocaleString("fr-FR")}`}
          accent="amber"
        />
      </div>

      {/* Répartition Pro vs Sec */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <SplitCard label="YukpoPro" data={kpis.consommation.pro} accent="blue" />
        <SplitCard label="YukpoSecrétariat" data={kpis.consommation.sec} accent="violet" />
      </div>

      {/* Sparkline simple coût/jour */}
      <div className="rounded-xl border border-slate-700 bg-slate-800/50 p-5">
        <div className="text-sm font-semibold text-white mb-3">Évolution du coût (FCFA / jour)</div>
        <UsageSparkline data={usage} />
      </div>

      {/* Top features */}
      <div className="rounded-xl border border-slate-700 bg-slate-800/50 p-5">
        <div className="text-sm font-semibold text-white mb-3">Top features les plus consommatrices</div>
        <TopFeaturesBars rows={kpis.top_features} />
      </div>
    </div>
  );
};

const KpiCard = ({
  icon: Icon, label, value, sub, accent,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string; value: string; sub: string;
  accent: "blue" | "violet" | "emerald" | "amber";
}) => {
  const accentMap: Record<string, string> = {
    blue:    "from-blue-500/15 to-blue-500/5 border-blue-500/30 text-blue-300",
    violet:  "from-violet-500/15 to-violet-500/5 border-violet-500/30 text-violet-300",
    emerald: "from-emerald-500/15 to-emerald-500/5 border-emerald-500/30 text-emerald-300",
    amber:   "from-amber-500/15 to-amber-500/5 border-amber-500/30 text-amber-300",
  };
  return (
    <div className={`rounded-xl border bg-gradient-to-br p-4 ${accentMap[accent]}`}>
      <div className="flex items-center gap-2 mb-2">
        <Icon className="w-4 h-4" />
        <span className="text-xs font-medium uppercase tracking-wide opacity-80">{label}</span>
      </div>
      <div className="text-2xl font-bold text-white">{value}</div>
      <div className="text-[11px] text-slate-400 mt-0.5">{sub}</div>
    </div>
  );
};

const SplitCard = ({
  label, data, accent,
}: {
  label: string;
  data: { appels: number; fcfa: number; credits: number; tokens_in: number; tokens_out: number };
  accent: "blue" | "violet";
}) => {
  const ringColor = accent === "blue" ? "border-blue-500/40" : "border-violet-500/40";
  return (
    <div className={`rounded-xl border ${ringColor} bg-slate-800/50 p-5`}>
      <div className="text-sm font-semibold text-white mb-3">{label}</div>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <Stat label="Appels" value={data.appels.toLocaleString("fr-FR")} />
        <Stat label="Coût" value={formatFCFA(data.fcfa)} />
        <Stat label="Crédits" value={formatCredits(data.credits)} />
        <Stat label="Tokens" value={formatTokens(data.tokens_in + data.tokens_out)} />
      </div>
    </div>
  );
};

const Stat = ({ label, value }: { label: string; value: string }) => (
  <div>
    <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
    <div className="text-base font-semibold text-white">{value}</div>
  </div>
);


// ══════════════════════════════════════════════════════════════════════════════
// CONSOMMATION (par feature)
// ══════════════════════════════════════════════════════════════════════════════

const ConsommationTab = ({ features, usage }: { features: FeatureRow[]; usage: UsageDay[] }) => (
  <div className="space-y-6">
    <div className="rounded-xl border border-slate-700 bg-slate-800/50 p-5">
      <div className="text-sm font-semibold text-white mb-3">Évolution journalière</div>
      <UsageSparkline data={usage} showSplit />
    </div>

    <div className="rounded-xl border border-slate-700 bg-slate-800/50 p-5">
      <div className="text-sm font-semibold text-white mb-3">
        Par feature ({features.length})
      </div>
      <TableFeatures rows={features} />
    </div>
  </div>
);

const TableFeatures = ({ rows }: { rows: FeatureRow[] }) => {
  if (rows.length === 0) return <div className="text-sm text-slate-500">Aucune donnée sur la période.</div>;
  const maxFcfa = Math.max(...rows.map(r => r.fcfa), 1);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-[10px] uppercase tracking-wider text-slate-500 border-b border-slate-700">
            <th className="text-left py-2 px-2">App</th>
            <th className="text-left py-2 px-2">Feature</th>
            <th className="text-right py-2 px-2">Appels</th>
            <th className="text-right py-2 px-2">Tokens</th>
            <th className="text-right py-2 px-2">Crédits</th>
            <th className="text-right py-2 px-2">FCFA</th>
            <th className="text-left py-2 px-2 w-1/4">Part</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={`${r.app}-${r.module}-${i}`} className="border-b border-slate-800/60 text-slate-200">
              <td className="py-2 px-2">
                <span className={
                  "px-1.5 py-0.5 rounded text-[10px] font-bold " +
                  (r.app === "pro" ? "bg-blue-500/20 text-blue-300" : "bg-violet-500/20 text-violet-300")
                }>{r.app === "pro" ? "PRO" : "SEC"}</span>
              </td>
              <td className="py-2 px-2 font-medium">{r.module}</td>
              <td className="py-2 px-2 text-right tabular-nums">{r.nb_appels.toLocaleString("fr-FR")}</td>
              <td className="py-2 px-2 text-right tabular-nums text-slate-400">{formatTokens(r.tokens_in + r.tokens_out)}</td>
              <td className="py-2 px-2 text-right tabular-nums text-slate-400">{formatCredits(r.credits)}</td>
              <td className="py-2 px-2 text-right tabular-nums font-semibold">{formatFCFA(r.fcfa)}</td>
              <td className="py-2 px-2">
                <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-yukpo-500 to-yukpo-400"
                    style={{ width: `${(r.fcfa / maxFcfa) * 100}%` }}
                  />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};


// ══════════════════════════════════════════════════════════════════════════════
// PROVIDERS
// ══════════════════════════════════════════════════════════════════════════════

const ProvidersTab = ({ providers }: { providers: ProviderRow[] }) => {
  if (providers.length === 0) {
    return <div className="text-sm text-slate-500">Aucune donnée provider sur la période.</div>;
  }

  const PROVIDER_LABELS: Record<string, { label: string; color: string }> = {
    anthropic:  { label: "Anthropic (Claude)",  color: "bg-orange-500" },
    openai:     { label: "OpenAI (GPT)",        color: "bg-emerald-500" },
    fal:        { label: "fal.ai (Flux/Recraft)", color: "bg-purple-500" },
    replicate:  { label: "Replicate",           color: "bg-pink-500" },
    elevenlabs: { label: "ElevenLabs (TTS)",    color: "bg-cyan-500" },
    azure:      { label: "Azure DocIntel",      color: "bg-blue-500" },
    local:      { label: "Local / Forfait",     color: "bg-slate-500" },
    unknown:    { label: "Non classé",          color: "bg-slate-600" },
  };

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-700 bg-slate-800/50 p-5">
        <div className="text-sm font-semibold text-white mb-4">Répartition par fournisseur</div>
        <div className="space-y-3">
          {providers.map(p => {
            const meta = PROVIDER_LABELS[p.provider] || { label: p.provider, color: "bg-slate-500" };
            return (
              <div key={p.provider}>
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2">
                    <div className={`w-2.5 h-2.5 rounded-full ${meta.color}`} />
                    <span className="font-medium text-white text-sm">{meta.label}</span>
                    <span className="text-[10px] text-slate-500">
                      {p.modeles.slice(0, 3).join(", ")}{p.modeles.length > 3 ? "…" : ""}
                    </span>
                  </div>
                  <div className="text-sm tabular-nums text-slate-300">
                    {formatFCFA(p.fcfa)} <span className="text-slate-500">({p.pct_fcfa.toFixed(1)}%)</span>
                  </div>
                </div>
                <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                  <div className={`h-full ${meta.color}`} style={{ width: `${p.pct_fcfa}%` }} />
                </div>
                <div className="mt-1 text-[10px] text-slate-500 flex gap-4">
                  <span>{p.nb_appels.toLocaleString("fr-FR")} appels</span>
                  <span>{formatTokens(p.tokens_in + p.tokens_out)} tokens</span>
                  <span>{formatUSD(p.usd)}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};


// ══════════════════════════════════════════════════════════════════════════════
// USERS
// ══════════════════════════════════════════════════════════════════════════════

const UsersTab = ({ users }: { users: UserRow[] }) => {
  if (users.length === 0) return <div className="text-sm text-slate-500">Aucun utilisateur sur la période.</div>;
  const maxFcfa = Math.max(...users.map(u => u.fcfa), 1);

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-800/50 p-5">
      <div className="text-sm font-semibold text-white mb-3">Top {users.length} consommateurs</div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] uppercase tracking-wider text-slate-500 border-b border-slate-700">
              <th className="text-left py-2 px-2">App</th>
              <th className="text-left py-2 px-2">Utilisateur</th>
              <th className="text-right py-2 px-2">Appels</th>
              <th className="text-right py-2 px-2">Crédits</th>
              <th className="text-right py-2 px-2">FCFA</th>
              <th className="text-left py-2 px-2 w-1/4">Part</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u, i) => (
              <tr key={`${u.app}-${u.user_id}`} className="border-b border-slate-800/60 text-slate-200">
                <td className="py-2 px-2">
                  <span className={
                    "px-1.5 py-0.5 rounded text-[10px] font-bold " +
                    (u.app === "pro" ? "bg-blue-500/20 text-blue-300" : "bg-violet-500/20 text-violet-300")
                  }>{u.app === "pro" ? "PRO" : "SEC"}</span>
                </td>
                <td className="py-2 px-2 font-medium">
                  {u.email || `User #${u.user_id}`}
                  <span className="text-[10px] text-slate-500 ml-2">#{u.user_id}</span>
                </td>
                <td className="py-2 px-2 text-right tabular-nums">{u.nb_appels.toLocaleString("fr-FR")}</td>
                <td className="py-2 px-2 text-right tabular-nums text-slate-400">{formatCredits(u.credits)}</td>
                <td className="py-2 px-2 text-right tabular-nums font-semibold">{formatFCFA(u.fcfa)}</td>
                <td className="py-2 px-2">
                  <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-yukpo-500 to-yukpo-400" style={{ width: `${(u.fcfa / maxFcfa) * 100}%` }} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};


// ══════════════════════════════════════════════════════════════════════════════
// ALERTS
// ══════════════════════════════════════════════════════════════════════════════

const AlertsTab = ({
  alertes, resume,
}: {
  alertes: AlerteRow[];
  resume: { critical: number; warning: number; info: number };
}) => {
  if (alertes.length === 0) {
    return (
      <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-6 text-center">
        <div className="text-4xl mb-2">✓</div>
        <div className="text-sm font-semibold text-emerald-200">Aucune alerte active</div>
        <div className="text-xs text-emerald-200/70 mt-1">Tous les seuils sont respectés sur la période.</div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex gap-2 text-xs">
        {resume.critical > 0 && <Pill color="red"    label={`${resume.critical} critique${resume.critical > 1 ? "s" : ""}`} />}
        {resume.warning > 0  && <Pill color="amber"  label={`${resume.warning} alerte${resume.warning > 1 ? "s" : ""}`} />}
        {resume.info > 0     && <Pill color="blue"   label={`${resume.info} info`} />}
      </div>

      {alertes.map((a, i) => (
        <AlertCard key={`${a.code}-${i}`} alerte={a} />
      ))}
    </div>
  );
};

const Pill = ({ color, label }: { color: "red" | "amber" | "blue"; label: string }) => {
  const map = {
    red:   "bg-red-500/20 text-red-300 border-red-500/40",
    amber: "bg-amber-500/20 text-amber-300 border-amber-500/40",
    blue:  "bg-blue-500/20 text-blue-300 border-blue-500/40",
  };
  return <span className={`inline-flex items-center px-2 py-0.5 rounded-full border ${map[color]} font-semibold`}>{label}</span>;
};

const AlertCard = ({ alerte }: { alerte: AlerteRow }) => {
  const colorMap = {
    critical: "border-red-500/40 bg-red-500/5",
    warning:  "border-amber-500/40 bg-amber-500/5",
    info:     "border-blue-500/40 bg-blue-500/5",
  };
  const iconColor = {
    critical: "text-red-400",
    warning:  "text-amber-400",
    info:     "text-blue-400",
  };
  return (
    <div className={`rounded-lg border ${colorMap[alerte.severite]} p-4`}>
      <div className="flex items-start gap-3">
        <AlertTriangle className={`w-5 h-5 flex-shrink-0 mt-0.5 ${iconColor[alerte.severite]}`} />
        <div className="flex-1">
          <div className="font-semibold text-white text-sm">{alerte.titre}</div>
          <div className="text-xs text-slate-300 mt-1">{alerte.message}</div>
          <div className="text-[10px] text-slate-500 mt-2 font-mono">
            code: {alerte.code} · seuil: {alerte.seuil.toLocaleString("fr-FR")} · valeur: {alerte.valeur.toLocaleString("fr-FR")}
          </div>
        </div>
      </div>
    </div>
  );
};


// ══════════════════════════════════════════════════════════════════════════════
// SPARKLINE & helpers
// ══════════════════════════════════════════════════════════════════════════════

const UsageSparkline = ({ data, showSplit = false }: { data: UsageDay[]; showSplit?: boolean }) => {
  if (data.length === 0) return <div className="text-sm text-slate-500">Aucune donnée.</div>;

  const maxFcfa = Math.max(...data.map(d => d.fcfa), 1);
  const W = 800, H = 120, pad = 4;
  const stepX = (W - pad * 2) / Math.max(1, data.length - 1);

  const pointsTotal = data.map((d, i) => {
    const x = pad + i * stepX;
    const y = H - pad - ((d.fcfa / maxFcfa) * (H - pad * 2));
    return `${x},${y}`;
  }).join(" ");

  const pointsPro = data.map((d, i) => {
    const x = pad + i * stepX;
    const y = H - pad - ((d.pro_fcfa / maxFcfa) * (H - pad * 2));
    return `${x},${y}`;
  }).join(" ");

  const pointsSec = data.map((d, i) => {
    const x = pad + i * stepX;
    const y = H - pad - ((d.sec_fcfa / maxFcfa) * (H - pad * 2));
    return `${x},${y}`;
  }).join(" ");

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-32" preserveAspectRatio="none">
        {!showSplit && <polyline fill="none" stroke="#7c3aed" strokeWidth="2" points={pointsTotal} />}
        {showSplit && (
          <>
            <polyline fill="none" stroke="#3b82f6" strokeWidth="2" points={pointsPro} />
            <polyline fill="none" stroke="#a855f7" strokeWidth="2" points={pointsSec} />
          </>
        )}
      </svg>
      <div className="flex flex-wrap justify-between text-[10px] text-slate-500 mt-1">
        <span>{data[0]?.jour}</span>
        <span>{data[data.length - 1]?.jour}</span>
      </div>
      {showSplit && (
        <div className="flex gap-4 text-[10px] text-slate-400 mt-2">
          <span className="inline-flex items-center gap-1.5"><span className="w-2 h-2 bg-blue-500 rounded-full" /> YukpoPro</span>
          <span className="inline-flex items-center gap-1.5"><span className="w-2 h-2 bg-violet-500 rounded-full" /> Secrétariat</span>
        </div>
      )}
    </div>
  );
};

const TopFeaturesBars = ({ rows }: { rows: { app: string; module: string; nb_appels: number; fcfa: number }[] }) => {
  if (rows.length === 0) return <div className="text-sm text-slate-500">Aucune donnée.</div>;
  const max = Math.max(...rows.map(r => r.fcfa), 1);
  return (
    <div className="space-y-1.5">
      {rows.map((r, i) => (
        <div key={`${r.app}-${r.module}-${i}`} className="text-xs">
          <div className="flex justify-between mb-0.5">
            <span className="text-slate-300">
              <span className={
                "inline-block px-1.5 py-0.5 rounded text-[9px] font-bold mr-2 " +
                (r.app === "pro" ? "bg-blue-500/20 text-blue-300" : "bg-violet-500/20 text-violet-300")
              }>{r.app === "pro" ? "PRO" : "SEC"}</span>
              {r.module}
            </span>
            <span className="text-slate-400 tabular-nums">{formatFCFA(r.fcfa)} · {r.nb_appels.toLocaleString("fr-FR")} appels</span>
          </div>
          <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
            <div className="h-full bg-gradient-to-r from-yukpo-500 to-yukpo-400" style={{ width: `${(r.fcfa / max) * 100}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
};


// ── Formatters ────────────────────────────────────────────────────────────────

function formatFCFA(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} M FCFA`;
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1)} k FCFA`;
  return `${Math.round(n).toLocaleString("fr-FR")} FCFA`;
}

function formatUSD(n: number): string {
  if (n >= 1_000) return `$${(n / 1_000).toFixed(1)}k`;
  return `$${n.toFixed(2)}`;
}

function formatCredits(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1)}k`;
  return Math.round(n).toLocaleString("fr-FR");
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1)}k`;
  return n.toLocaleString("fr-FR");
}
