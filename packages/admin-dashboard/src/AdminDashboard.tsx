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
  AlertTriangle, BarChart3, Bell, Cpu, DollarSign, Gift, Layers, Lock,
  Plus, RefreshCw, Search, TrendingUp, Unlock, Users as UsersIcon, X, Zap,
} from "lucide-react";
import {
  adminCrossApi, type AppScope, type HttpClient,
  type DashboardKPIs, type UsageDay, type FeatureRow,
  type ProviderRow, type UserRow, type AlerteRow,
  type UtilisateurAdminRow, type CiblePromotion, type PromotionRequest,
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

type Onglet = "overview" | "consommation" | "providers" | "users" | "gestion" | "promotions" | "alerts" | "forecast";

const TABS: { id: Onglet; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: "overview",     label: "Vue d'ensemble",   icon: BarChart3 },
  { id: "consommation", label: "Consommation API", icon: Cpu },
  { id: "providers",    label: "Fournisseurs",     icon: Layers },
  { id: "users",        label: "Top consommateurs",icon: UsersIcon },
  { id: "gestion",      label: "Utilisateurs",     icon: UsersIcon },
  { id: "promotions",   label: "Bonus & promo",    icon: Gift },
  { id: "forecast",     label: "Coûts prévisionnels", icon: TrendingUp },
  { id: "alerts",       label: "Alertes",          icon: Bell },
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
    // Panneau sombre : garantit la lisibilité quel que soit le thème de
    // la page hôte (canvas slate-100 en clair → texte blanc invisible
    // sans ce wrapper). Tout le contenu utilise text-white / slate-300/
    // 400 → contraste WCAG AA sur bg-slate-900.
    <div className="rounded-2xl bg-slate-900 ring-1 ring-slate-700/50 shadow-2xl p-5 sm:p-6 space-y-6 text-slate-100">

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
      {tab === "gestion"      && <GestionUsersTab api={api} scope={scope} />}
      {tab === "promotions"   && <PromotionsTab api={api} scope={scope} />}
      {tab === "forecast"     && <ForecastTab providers={providers} features={features} usage={usage} kpis={kpis} jours={jours} />}
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

function formatDate(iso?: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "numeric" });
  } catch { return "—"; }
}

function formatDateRelative(iso?: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    const diffMs = Date.now() - d.getTime();
    const min = Math.floor(diffMs / 60000);
    if (min < 1)   return "à l'instant";
    if (min < 60)  return `il y a ${min} min`;
    const h = Math.floor(min / 60);
    if (h < 24)    return `il y a ${h} h`;
    const j = Math.floor(h / 24);
    if (j < 30)    return `il y a ${j} j`;
    return formatDate(iso);
  } catch { return "—"; }
}


// ══════════════════════════════════════════════════════════════════════════════
// GESTION UTILISATEURS — liste détaillée + actions (crédits bonus, blocage)
// ══════════════════════════════════════════════════════════════════════════════

type CrossApi = ReturnType<typeof adminCrossApi>;

const GestionUsersTab = ({ api, scope }: { api: CrossApi; scope: AppScope }) => {
  const [users, setUsers] = useState<UtilisateurAdminRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const par_page = 50;
  const [recherche, setRecherche] = useState("");
  const [chargement, setChargement] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const refresh = () => setTick(t => t + 1);

  // Modale bonus
  const [bonusTarget, setBonusTarget] = useState<UtilisateurAdminRow | null>(null);
  const [bonusMontant, setBonusMontant] = useState<string>("100");
  const [bonusMotif, setBonusMotif] = useState<string>("");
  const [bonusEnvoi, setBonusEnvoi] = useState(false);

  useEffect(() => {
    let annule = false;
    setChargement(true);
    setErreur(null);
    api.listerUtilisateurs(scope, page, par_page, recherche || undefined)
      .then(r => { if (!annule) { setUsers(r.utilisateurs); setTotal(r.total); } })
      .catch((e: any) => {
        if (annule) return;
        const msg = e?.response?.data?.detail || e?.message || "Erreur de chargement";
        setErreur(typeof msg === "string" ? msg : "Erreur de chargement");
      })
      .finally(() => { if (!annule) setChargement(false); });
    return () => { annule = true; };
  }, [api, scope, page, tick]);

  const onSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    refresh();
  };

  const ouvrirBonus = (u: UtilisateurAdminRow) => {
    setBonusTarget(u);
    setBonusMontant("100");
    setBonusMotif("");
  };

  const envoyerBonus = async () => {
    if (!bonusTarget) return;
    const montant = parseInt(bonusMontant, 10);
    if (!Number.isFinite(montant) || montant <= 0) {
      setErreur("Montant invalide");
      return;
    }
    setBonusEnvoi(true);
    try {
      await api.ajouterCreditsBonus(bonusTarget.app, bonusTarget.id, {
        montant, motif: bonusMotif || undefined,
      });
      setBonusTarget(null);
      refresh();
    } catch (e: any) {
      setErreur(e?.response?.data?.detail || e?.message || "Échec de l'ajout");
    } finally {
      setBonusEnvoi(false);
    }
  };

  const toggleBlocage = async (u: UtilisateurAdminRow) => {
    try {
      if (u.bloque) {
        await api.debloquer(u.app, u.id);
      } else {
        const j = prompt("Bloquer pendant combien de jours ? (laisser vide = permanent)") ?? "";
        const jours = j.trim() ? parseInt(j, 10) : undefined;
        await api.bloquer(u.app, u.id, {
          duree_heures: jours ? jours * 24 : undefined,
        });
      }
      refresh();
    } catch (e: any) {
      setErreur(e?.response?.data?.detail || e?.message || "Échec");
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / par_page));

  return (
    <div className="space-y-4">
      {/* Barre filtre + recherche */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-700 bg-slate-800/50 p-3">
        <form onSubmit={onSearch} className="relative flex-1 min-w-[260px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input
            type="text"
            value={recherche}
            onChange={e => setRecherche(e.target.value)}
            placeholder="Rechercher email, nom, username…"
            className="w-full pl-10 pr-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white text-sm placeholder:text-slate-500 focus:outline-none focus:border-yukpo-500"
          />
        </form>
        <div className="text-xs text-slate-400">
          {chargement ? "Chargement…" : `${users.length}/${total} utilisateur${total > 1 ? "s" : ""}`}
        </div>
        <button
          onClick={refresh}
          disabled={chargement}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-600 bg-slate-800 px-3 py-1.5 text-xs text-white hover:bg-slate-700 disabled:opacity-50"
        >
          <RefreshCw className={"w-3.5 h-3.5 " + (chargement ? "animate-spin" : "")} />
          Actualiser
        </button>
      </div>

      {erreur && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-2 text-sm text-red-200">
          ⚠ {erreur}
        </div>
      )}

      {/* Tableau utilisateurs */}
      <div className="rounded-xl border border-slate-700 bg-slate-800/50 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[10px] uppercase tracking-wider text-slate-500 bg-slate-800/80 border-b border-slate-700">
                <th className="text-left py-2 px-3">App</th>
                <th className="text-left py-2 px-3">Utilisateur</th>
                <th className="text-left py-2 px-3">Plan</th>
                <th className="text-left py-2 px-3">Inscrit</th>
                <th className="text-left py-2 px-3">Dernière connexion</th>
                <th className="text-right py-2 px-3">Crédits</th>
                <th className="text-right py-2 px-3">Conso</th>
                <th className="text-right py-2 px-3 pr-4">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.length === 0 && !chargement && (
                <tr><td colSpan={8} className="py-10 text-center text-sm text-slate-500">
                  Aucun utilisateur trouvé.
                </td></tr>
              )}
              {users.map((u, i) => {
                const conso = u.conso_total || 0;
                const restants = u.credits_restants || 0;
                const restantsColor =
                  restants < 50 ? "text-red-300" :
                  restants < 200 ? "text-amber-300" :
                  "text-emerald-300";
                return (
                  <tr key={`${u.app}-${u.id}-${i}`} className={
                    "border-b border-slate-800/60 text-slate-200 " +
                    (u.bloque ? "bg-red-900/10" : "")
                  }>
                    <td className="py-2 px-3">
                      <span className={
                        "px-1.5 py-0.5 rounded text-[10px] font-bold " +
                        (u.app === "pro" ? "bg-blue-500/20 text-blue-300" : "bg-violet-500/20 text-violet-300")
                      }>{u.app === "pro" ? "PRO" : "SEC"}</span>
                    </td>
                    <td className="py-2 px-3 max-w-[220px]">
                      <div className="font-medium text-white truncate" title={u.email || ""}>
                        {u.email || u.username || `User #${u.id}`}
                      </div>
                      <div className="text-[10px] text-slate-500">
                        #{u.id}{u.role && u.role !== "user" ? ` · ${u.role}` : ""}
                        {u.bloque && <span className="ml-2 text-red-300">BLOQUÉ</span>}
                      </div>
                    </td>
                    <td className="py-2 px-3 text-slate-300 capitalize">{u.plan || "—"}</td>
                    <td className="py-2 px-3 text-slate-400 text-xs">{formatDate(u.cree_le)}</td>
                    <td className="py-2 px-3 text-slate-300 text-xs">
                      {formatDateRelative(u.derniere_connexion)}
                      {u.nb_connexions > 0 && (
                        <span className="text-[10px] text-slate-500 ml-1">({u.nb_connexions}×)</span>
                      )}
                    </td>
                    <td className={`py-2 px-3 text-right tabular-nums font-semibold ${restantsColor}`}>
                      {formatCredits(restants)}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums text-slate-400">
                      {formatCredits(conso)}
                    </td>
                    <td className="py-2 px-3 pr-4 text-right">
                      <div className="inline-flex gap-1.5">
                        <button
                          onClick={() => ouvrirBonus(u)}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/30"
                          title="Ajouter des crédits bonus"
                        >
                          <Plus className="w-3 h-3" /> Crédits
                        </button>
                        <button
                          onClick={() => toggleBlocage(u)}
                          className={
                            "inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-semibold border " +
                            (u.bloque
                              ? "bg-amber-500/20 text-amber-300 border-amber-500/30 hover:bg-amber-500/30"
                              : "bg-slate-700/50 text-slate-300 border-slate-600 hover:bg-slate-700")
                          }
                          title={u.bloque ? "Débloquer" : "Bloquer"}
                        >
                          {u.bloque
                            ? <><Unlock className="w-3 h-3" /> Débloquer</>
                            : <><Lock className="w-3 h-3" /> Bloquer</>}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span>Page {page} / {totalPages}</span>
          <div className="inline-flex gap-2">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="px-3 py-1.5 rounded-md border border-slate-600 bg-slate-800 text-white disabled:opacity-50"
            >Précédent</button>
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="px-3 py-1.5 rounded-md border border-slate-600 bg-slate-800 text-white disabled:opacity-50"
            >Suivant</button>
          </div>
        </div>
      )}

      {/* Modale Ajout crédits bonus */}
      {bonusTarget && (
        <ModalBonus
          target={bonusTarget}
          montant={bonusMontant} onMontant={setBonusMontant}
          motif={bonusMotif}     onMotif={setBonusMotif}
          envoi={bonusEnvoi}
          onClose={() => setBonusTarget(null)}
          onSubmit={envoyerBonus}
        />
      )}
    </div>
  );
};

const ModalBonus = ({
  target, montant, onMontant, motif, onMotif, envoi, onClose, onSubmit,
}: {
  target: UtilisateurAdminRow;
  montant: string; onMontant: (v: string) => void;
  motif: string;   onMotif: (v: string) => void;
  envoi: boolean;
  onClose: () => void; onSubmit: () => void;
}) => (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
    <div className="w-full max-w-md rounded-2xl bg-slate-900 border border-slate-700 shadow-2xl">
      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700">
        <div className="flex items-center gap-2">
          <Gift className="w-5 h-5 text-emerald-400" />
          <h3 className="text-white font-semibold">Ajouter des crédits bonus</h3>
        </div>
        <button onClick={onClose} className="p-1 rounded-md text-slate-400 hover:text-white hover:bg-slate-800">
          <X className="w-4 h-4" />
        </button>
      </div>
      <div className="px-5 py-4 space-y-3">
        <div className="text-sm text-slate-300">
          Bénéficiaire :
          <span className="ml-2 font-semibold text-white">{target.email || `User #${target.id}`}</span>
          <span className={
            "ml-2 px-1.5 py-0.5 rounded text-[10px] font-bold " +
            (target.app === "pro" ? "bg-blue-500/20 text-blue-300" : "bg-violet-500/20 text-violet-300")
          }>{target.app === "pro" ? "PRO" : "SEC"}</span>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1">Montant (crédits)</label>
          <input
            type="number" min={1} value={montant}
            onChange={e => onMontant(e.target.value)}
            className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-white focus:outline-none focus:border-yukpo-500"
          />
          <div className="text-[10px] text-slate-500 mt-1">
            Équivalent ≈ {Math.round((parseInt(montant, 10) || 0) * 0.6).toLocaleString("fr-FR")} FCFA d'utilisation
          </div>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1">Motif (audit)</label>
          <input
            type="text" value={motif} onChange={e => onMotif(e.target.value)}
            placeholder="Ex. compensation incident, parrainage, geste commercial…"
            className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-white placeholder:text-slate-500 focus:outline-none focus:border-yukpo-500"
          />
        </div>
      </div>
      <div className="px-5 py-3 border-t border-slate-700 flex justify-end gap-2">
        <button onClick={onClose} className="px-3 py-1.5 rounded-md border border-slate-600 bg-slate-800 text-sm text-slate-300 hover:bg-slate-700">
          Annuler
        </button>
        <button
          onClick={onSubmit} disabled={envoi}
          className="px-4 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-500 text-sm font-semibold text-white disabled:opacity-50"
        >
          {envoi ? "Envoi…" : "Créditer"}
        </button>
      </div>
    </div>
  </div>
);


// ══════════════════════════════════════════════════════════════════════════════
// PROMOTIONS — distribution masse / ciblée
// ══════════════════════════════════════════════════════════════════════════════

const PromotionsTab = ({ api, scope }: { api: CrossApi; scope: AppScope }) => {
  // Une promotion s'applique à UN app à la fois (chaque app a son propre
  // pot de crédits). Si scope="both", on demande à l'admin de choisir.
  const [app, setApp] = useState<"pro" | "sec">(scope === "sec" ? "sec" : "pro");
  useEffect(() => {
    if (scope === "pro") setApp("pro");
    else if (scope === "sec") setApp("sec");
  }, [scope]);

  const [montant, setMontant] = useState<string>("50");
  const [cible, setCible] = useState<CiblePromotion>("tous");
  const [planFilter, setPlanFilter] = useState<string>("");
  const [roleFilter, setRoleFilter] = useState<string>("");
  const [userIdsInput, setUserIdsInput] = useState<string>("");
  const [motif, setMotif] = useState<string>("");
  const [seuilCreditsMin, setSeuilCreditsMin] = useState<string>("");
  const [seuilCreditsMax, setSeuilCreditsMax] = useState<string>("");
  const [seuilAppelsMin, setSeuilAppelsMin] = useState<string>("");
  const [periodeJours, setPeriodeJours] = useState<string>("30");
  const [pays, setPays] = useState<string>("");
  const [continent, setContinent] = useState<string>("");

  const [envoi, setEnvoi] = useState(false);
  const [resultat, setResultat] = useState<string | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);

  const CIBLES: { id: CiblePromotion; label: string; aide: string; pro: boolean; sec: boolean }[] = [
    { id: "tous",         label: "Tous les utilisateurs actifs",          aide: "Distribution globale.", pro: true, sec: true },
    { id: "plan",         label: "Plan spécifique",                       aide: "Pour récompenser des plans payants. Pro uniquement.", pro: true, sec: false },
    { id: "role",         label: "Rôle spécifique",                       aide: "Ex. tous les admins, super_admin. Sec uniquement.", pro: false, sec: true },
    { id: "ids",          label: "Liste d'IDs (ciblé)",                   aide: "Une liste explicite d'identifiants.", pro: true, sec: true },
    { id: "consommation", label: "Consommation (forte / faible / appels)", aide: "Filtres seuils crédits/appels sur les N derniers jours.", pro: true, sec: true },
  ];
  const ciblesDisponibles = CIBLES.filter(c => (app === "pro" ? c.pro : c.sec));

  // Si la cible courante n'est plus dispo, on retombe sur "tous"
  useEffect(() => {
    if (!ciblesDisponibles.find(c => c.id === cible)) setCible("tous");
  }, [app]); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async () => {
    setErreur(null); setResultat(null);

    const n = parseInt(montant, 10);
    if (!Number.isFinite(n) || n <= 0) {
      setErreur("Montant invalide"); return;
    }
    const req: PromotionRequest = { montant: n, cible, motif: motif || undefined };
    if (cible === "plan") req.plan = planFilter || undefined;
    if (cible === "role") req.role = roleFilter || undefined;
    if (cible === "ids") {
      const ids = userIdsInput.split(/[\s,;]+/).map(s => s.trim()).filter(Boolean).map(Number).filter(Number.isFinite);
      if (ids.length === 0) { setErreur("Liste d'IDs vide"); return; }
      req.user_ids = ids;
    }
    if (cible === "consommation") {
      const sMin = parseFloat(seuilCreditsMin);
      const sMax = parseFloat(seuilCreditsMax);
      const aMin = parseInt(seuilAppelsMin, 10);
      const pj   = parseInt(periodeJours, 10);
      if (Number.isFinite(sMin)) req.seuil_credits_min = sMin;
      if (Number.isFinite(sMax)) req.seuil_credits_max = sMax;
      if (Number.isFinite(aMin)) req.seuil_appels_min = aMin;
      if (Number.isFinite(pj))   req.periode_jours = pj;
      if (req.seuil_credits_min === undefined && req.seuil_credits_max === undefined && req.seuil_appels_min === undefined) {
        setErreur("Au moins un seuil requis pour la cible consommation"); return;
      }
    }
    if (app === "pro") {
      if (pays.trim())      req.pays = pays.trim().toUpperCase();
      if (continent.trim()) req.continent = continent.trim().toUpperCase();
    }

    if (!confirm(
      `Confirmer la distribution de ${n} crédits ${cible === "tous" ? "à TOUS" : `(cible : ${cible})`} ` +
      `sur ${app === "pro" ? "YukpoPro" : "Secrétariat"} ?`,
    )) return;

    setEnvoi(true);
    try {
      const r = await api.lancerPromotion(app, req);
      const benef = r.beneficiaires ?? r.beneficiaires_count ?? 0;
      setResultat(
        `✓ ${benef.toLocaleString("fr-FR")} bénéficiaires crédités de ${n} crédits chacun ` +
        `(total ${(benef * n).toLocaleString("fr-FR")} crédits)${r.message ? " — " + r.message : ""}.`,
      );
    } catch (e: any) {
      setErreur(e?.response?.data?.detail || e?.message || "Échec de la promotion");
    } finally {
      setEnvoi(false);
    }
  };

  const cibleDesc = ciblesDisponibles.find(c => c.id === cible)?.aide || "";

  return (
    <div className="space-y-4">
      {/* Pavé bandeau d'info */}
      <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4 text-sm text-emerald-100/90">
        <div className="font-semibold text-emerald-200 mb-1">Distribution de crédits bonus en masse</div>
        Choisissez l'application cible (Pro ou Sec — les pots de crédits sont distincts) puis
        la stratégie de distribution. Les crédits sont <strong>ajoutés au plan existant</strong> de
        chaque bénéficiaire (n'écrasent pas).
      </div>

      <div className="rounded-xl border border-slate-700 bg-slate-800/50 p-5 space-y-4">

        {/* App ciblée */}
        <div>
          <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1.5">
            Application
          </label>
          <div className="inline-flex rounded-lg border border-slate-600 bg-slate-900 p-0.5 text-sm">
            <button
              type="button"
              onClick={() => setApp("pro")}
              className={"px-4 py-1.5 rounded-md font-semibold " + (app === "pro" ? "bg-blue-500 text-white" : "text-slate-300 hover:bg-slate-700")}
            >YukpoPro</button>
            <button
              type="button"
              onClick={() => setApp("sec")}
              className={"px-4 py-1.5 rounded-md font-semibold " + (app === "sec" ? "bg-violet-500 text-white" : "text-slate-300 hover:bg-slate-700")}
            >Secrétariat</button>
          </div>
        </div>

        {/* Montant */}
        <div>
          <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1.5">
            Montant par bénéficiaire (crédits)
          </label>
          <input
            type="number" min={1} value={montant}
            onChange={e => setMontant(e.target.value)}
            className="w-40 px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white focus:outline-none focus:border-yukpo-500"
          />
          <span className="ml-3 text-xs text-slate-500">
            ≈ {Math.round((parseInt(montant, 10) || 0) * 0.6).toLocaleString("fr-FR")} FCFA d'utilisation par bénéficiaire
          </span>
        </div>

        {/* Cible */}
        <div>
          <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1.5">
            Stratégie de distribution
          </label>
          <select
            value={cible}
            onChange={e => setCible(e.target.value as CiblePromotion)}
            className="w-full sm:w-auto min-w-[260px] px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white focus:outline-none focus:border-yukpo-500"
          >
            {ciblesDisponibles.map(c => (
              <option key={c.id} value={c.id}>{c.label}</option>
            ))}
          </select>
          {cibleDesc && <p className="text-[11px] text-slate-500 mt-1">{cibleDesc}</p>}
        </div>

        {/* Filtres conditionnels */}
        {cible === "plan" && (
          <div>
            <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1.5">
              Plan (Pro)
            </label>
            <select
              value={planFilter} onChange={e => setPlanFilter(e.target.value)}
              className="w-48 px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white"
            >
              <option value="">— sélectionner —</option>
              <option value="gratuit">Gratuit</option>
              <option value="starter">Starter</option>
              <option value="pro">Pro</option>
              <option value="business">Business</option>
            </select>
          </div>
        )}

        {cible === "role" && (
          <div>
            <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1.5">
              Rôle (Sec)
            </label>
            <select
              value={roleFilter} onChange={e => setRoleFilter(e.target.value)}
              className="w-48 px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white"
            >
              <option value="">— sélectionner —</option>
              <option value="user">user</option>
              <option value="admin">admin</option>
              <option value="super_admin">super_admin</option>
              <option value="yukpo_owner">yukpo_owner</option>
            </select>
          </div>
        )}

        {cible === "ids" && (
          <div>
            <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1.5">
              IDs utilisateurs (séparés par virgule, espace ou retour ligne)
            </label>
            <textarea
              value={userIdsInput} onChange={e => setUserIdsInput(e.target.value)}
              placeholder="123, 456, 789"
              rows={3}
              className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white placeholder:text-slate-500 focus:outline-none focus:border-yukpo-500"
            />
          </div>
        )}

        {cible === "consommation" && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div>
              <label className="block text-[10px] font-semibold text-slate-400 uppercase mb-1">Période (jours)</label>
              <input type="number" min={1} max={365} value={periodeJours} onChange={e => setPeriodeJours(e.target.value)}
                className="w-full px-2 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-white text-sm" />
            </div>
            <div>
              <label className="block text-[10px] font-semibold text-slate-400 uppercase mb-1">Crédits min</label>
              <input type="number" min={0} value={seuilCreditsMin} onChange={e => setSeuilCreditsMin(e.target.value)}
                placeholder="ex. 500"
                className="w-full px-2 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-white text-sm placeholder:text-slate-500" />
            </div>
            <div>
              <label className="block text-[10px] font-semibold text-slate-400 uppercase mb-1">Crédits max</label>
              <input type="number" min={0} value={seuilCreditsMax} onChange={e => setSeuilCreditsMax(e.target.value)}
                placeholder="ex. 100"
                className="w-full px-2 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-white text-sm placeholder:text-slate-500" />
            </div>
            <div>
              <label className="block text-[10px] font-semibold text-slate-400 uppercase mb-1">Appels min</label>
              <input type="number" min={0} value={seuilAppelsMin} onChange={e => setSeuilAppelsMin(e.target.value)}
                placeholder="ex. 20"
                className="w-full px-2 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-white text-sm placeholder:text-slate-500" />
            </div>
          </div>
        )}

        {/* Filtres géo (Pro seulement) */}
        {app === "pro" && (
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[10px] font-semibold text-slate-400 uppercase mb-1">Pays (ISO-2) — optionnel</label>
              <input type="text" value={pays} onChange={e => setPays(e.target.value)}
                placeholder="CM, CI, TG, FR, …" maxLength={2}
                className="w-full px-2 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-white text-sm placeholder:text-slate-500" />
            </div>
            <div>
              <label className="block text-[10px] font-semibold text-slate-400 uppercase mb-1">Continent — optionnel</label>
              <select value={continent} onChange={e => setContinent(e.target.value)}
                className="w-full px-2 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-white text-sm">
                <option value="">—</option>
                <option value="AF">Afrique</option>
                <option value="EU">Europe</option>
                <option value="NA">Amérique du Nord</option>
                <option value="SA">Amérique du Sud</option>
                <option value="AS">Asie</option>
                <option value="OC">Océanie</option>
              </select>
            </div>
          </div>
        )}

        {/* Motif */}
        <div>
          <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1.5">
            Motif (audit, optionnel)
          </label>
          <input type="text" value={motif} onChange={e => setMotif(e.target.value)}
            placeholder="Ex. campagne fin d'année, lancement YukpoPro, etc."
            className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white placeholder:text-slate-500 focus:outline-none focus:border-yukpo-500" />
        </div>

        {/* Submit */}
        <div className="flex justify-end pt-2 border-t border-slate-700">
          <button
            onClick={submit} disabled={envoi}
            className="inline-flex items-center gap-2 px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-sm font-semibold text-white disabled:opacity-50"
          >
            <Gift className="w-4 h-4" />
            {envoi ? "Distribution en cours…" : "Lancer la distribution"}
          </button>
        </div>
      </div>

      {resultat && (
        <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
          {resultat}
        </div>
      )}
      {erreur && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          ⚠ {erreur}
        </div>
      )}
    </div>
  );
};


// ══════════════════════════════════════════════════════════════════════════════
// FORECAST — Projections coûts mensuels basées sur consommation observée
// ══════════════════════════════════════════════════════════════════════════════
//
// Logique :
//   1. Aggrégation USD réel observé sur la période (sum providers.usd)
//   2. Extrapolation linéaire → projection 30j
//   3. Décomposition par provider (fal, Replicate, Anthropic, OpenAI…)
//   4. Décomposition par module/feature (visuels, vidéos, slides, chat…)
//   5. Scénarios "Et si nous avions N users ?" — multiplie proportionnellement
//      au ratio (N / utilisateurs_actifs_actuels).
//   6. Coûts infrastructure fixes (Fly, Postgres, Redis, Netlify) ajoutés
//      car ils n'apparaissent pas dans les providers (pas tracés par
//      service_credits_bureau).
//
// Tout est calculé en frontend depuis les données déjà fetchées par les
// autres onglets → 0 nouvel appel API.

interface ForecastTabProps {
  providers: ProviderRow[];
  features: FeatureRow[];
  usage: UsageDay[];
  kpis: DashboardKPIs | null;
  jours: number;
}

// Estimations infra Fly + outils (USD/mois) — révisable si la prod évolue
const _INFRA_FIXE_USD: { nom: string; usd: number; details: string }[] = [
  { nom: "Fly web (gunicorn ×2)",      usd: 72,  details: "performance-2x autoscale" },
  { nom: "Fly worker Celery",          usd: 71,  details: "performance-4x dédié vidéo/render" },
  { nom: "Fly worker burst",           usd: 9,   details: "scale-up à la demande 6h/jour" },
  { nom: "Postgres Fly managed",       usd: 35,  details: "db-shared-2x + 10 GB" },
  { nom: "Redis Upstash Pro",          usd: 10,  details: "256 MB broker Celery + cache" },
  { nom: "Volumes Fly (PDFs/MP4s)",    usd: 8,   details: "50 GB" },
  { nom: "Egress (downloads users)",   usd: 10,  details: "~500 GB/mois" },
  { nom: "Netlify Pro × 2 fronts",     usd: 38,  details: "YukpoPro + Secrétariat" },
  { nom: "Sentry + PostHog",           usd: 56,  details: "Erreurs + analytics" },
  { nom: "Backup Postgres + Domain",   usd: 12,  details: "Snapshots + DNS" },
];
const _INFRA_TOTAL_USD = _INFRA_FIXE_USD.reduce((s, x) => s + x.usd, 0);

const ForecastTab = ({ providers, features, usage, kpis, jours }: ForecastTabProps) => {
  // Calculs dérivés mémoïsés
  const stats = useMemo(() => {
    // 1. Coût brut providers observé sur la période
    const totalProvidersUsd = providers.reduce((s, p) => s + (p.usd || 0), 0);
    const totalProvidersFcfa = providers.reduce((s, p) => s + (p.fcfa || 0), 0);

    // 2. Conversion en USD/jour puis projection 30j
    const usdParJour = jours > 0 ? totalProvidersUsd / jours : 0;
    const fcfaParJour = jours > 0 ? totalProvidersFcfa / jours : 0;
    const projectionUsd30j = usdParJour * 30;
    const projectionFcfa30j = fcfaParJour * 30;

    // 3. Users actifs (sert de base de scale)
    const usersActifs = kpis?.utilisateurs.actifs || 0;
    const usdParUserMois = usersActifs > 0 ? projectionUsd30j / usersActifs : 0;

    // 4. Coût total mensuel projeté (providers + infra fixe)
    const totalProjMensuelUsd = projectionUsd30j + _INFRA_TOTAL_USD;
    const totalProjMensuelFcfa = totalProjMensuelUsd * 600; // 1 USD ≈ 600 XAF

    // 5. Coût facturé aux users (marge ×12 sur providers, infra absorbée)
    //    Approximation : revenue théorique = projectionUsd30j × 12
    const revenuTheoriqueUsd = projectionUsd30j * 12;
    const margeBruteUsd = revenuTheoriqueUsd - totalProjMensuelUsd;
    const margePct = revenuTheoriqueUsd > 0
      ? (margeBruteUsd / revenuTheoriqueUsd) * 100 : 0;

    // 6. Décomposition par provider triée
    const parProvider = providers
      .filter(p => p.usd > 0)
      .map(p => ({
        ...p,
        proj_30j_usd: jours > 0 ? (p.usd / jours) * 30 : 0,
        proj_30j_fcfa: jours > 0 ? (p.fcfa / jours) * 30 : 0,
      }))
      .sort((a, b) => b.proj_30j_usd - a.proj_30j_usd);

    // 7. Top features (modules) — utilise fcfa qui inclut tous les coûts
    const parFeature = features
      .filter(f => f.fcfa > 0)
      .map(f => ({
        ...f,
        proj_30j_fcfa: jours > 0 ? (f.fcfa / jours) * 30 : 0,
      }))
      .sort((a, b) => b.proj_30j_fcfa - a.proj_30j_fcfa)
      .slice(0, 8);

    return {
      jours, totalProvidersUsd, totalProvidersFcfa,
      usdParJour, fcfaParJour, projectionUsd30j, projectionFcfa30j,
      usersActifs, usdParUserMois,
      totalProjMensuelUsd, totalProjMensuelFcfa,
      revenuTheoriqueUsd, margeBruteUsd, margePct,
      parProvider, parFeature,
    };
  }, [providers, features, kpis, jours]);

  // Scénarios users (1k, 5k, 10k) — extrapolation proportionnelle
  const scenarios = useMemo(() => {
    if (stats.usersActifs === 0) {
      // Fallback : applique le forecast nominal sans scale
      return [
        { users: stats.usersActifs, totalUsd: stats.totalProjMensuelUsd, label: "Actuel" },
      ];
    }
    return [1000, 2500, 5000, 10000].map(n => {
      const ratio = n / stats.usersActifs;
      const apiUsd = stats.projectionUsd30j * ratio;
      // Infra scale partiellement avec users (autoscale Fly) — modèle simple
      // sub-linéaire : infra(N) = infra_base × (N / users_actifs)^0.5
      const infraScale = _INFRA_TOTAL_USD * Math.pow(ratio, 0.5);
      return {
        users: n,
        apiUsd, infraUsd: infraScale,
        totalUsd: apiUsd + infraScale,
        label: `${n.toLocaleString("fr-FR")} users`,
      };
    });
  }, [stats]);

  return (
    <div className="space-y-6">
      {/* ── Bandeau d'avertissement transparence ──────────────────────── */}
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-200">
        💡 <strong>Méthode</strong> : projection linéaire des {stats.jours} derniers jours
        × 30. Inclut le coût brut providers (fal.ai, Replicate, Anthropic, OpenAI…)
        + infra fixe estimée ({fmtUsd(_INFRA_TOTAL_USD)}/mois). Marge théorique calculée
        sur facturation user ×12 sur les appels providers (l'infra fixe est absorbée
        par le margin pool).
      </div>

      {/* ── KPIs synthèse ────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        <ForecastKpi
          label="Coût mensuel projeté"
          value={fmtUsd(stats.totalProjMensuelUsd)}
          sub={fmtFcfa(stats.totalProjMensuelFcfa)}
          tone="amber"
        />
        <ForecastKpi
          label="dont APIs providers"
          value={fmtUsd(stats.projectionUsd30j)}
          sub={`${stats.projectionUsd30j > 0 ? Math.round((stats.projectionUsd30j / stats.totalProjMensuelUsd) * 100) : 0}% du total`}
        />
        <ForecastKpi
          label="dont Infra fixe (Fly, etc.)"
          value={fmtUsd(_INFRA_TOTAL_USD)}
          sub={`${_INFRA_TOTAL_USD > 0 ? Math.round((_INFRA_TOTAL_USD / stats.totalProjMensuelUsd) * 100) : 0}% du total`}
        />
        <ForecastKpi
          label={`Coût / user actif (${stats.usersActifs})`}
          value={fmtUsd(stats.usdParUserMois)}
          sub={`Revenu théorique ×12 = ${fmtUsd(stats.usdParUserMois * 12)}/user`}
          tone="emerald"
        />
      </div>

      {/* ── Marge brute estimée ─────────────────────────────────────── */}
      {stats.projectionUsd30j > 0 && (
        <div className="rounded-xl border border-slate-700 bg-slate-800/50 p-4">
          <h3 className="text-sm font-semibold text-white mb-3">
            Marge brute estimée à facturation actuelle (×12 sur providers)
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div>
              <div className="text-xs text-slate-400">Revenu théorique</div>
              <div className="text-white font-bold">{fmtUsd(stats.revenuTheoriqueUsd)}</div>
            </div>
            <div>
              <div className="text-xs text-slate-400">Coûts (API + infra)</div>
              <div className="text-white font-bold">{fmtUsd(stats.totalProjMensuelUsd)}</div>
            </div>
            <div>
              <div className="text-xs text-slate-400">Marge brute</div>
              <div className={
                "font-bold " + (stats.margeBruteUsd > 0 ? "text-emerald-300" : "text-red-300")
              }>{fmtUsd(stats.margeBruteUsd)}</div>
            </div>
            <div>
              <div className="text-xs text-slate-400">Taux marge</div>
              <div className={
                "font-bold " + (stats.margePct > 50 ? "text-emerald-300"
                              : stats.margePct > 20 ? "text-amber-300"
                              : "text-red-300")
              }>{stats.margePct.toFixed(1)}%</div>
            </div>
          </div>
        </div>
      )}

      {/* ── Scénarios mise à l'échelle ──────────────────────────────── */}
      <div className="rounded-xl border border-slate-700 bg-slate-800/50 p-4">
        <h3 className="text-sm font-semibold text-white mb-3">
          📈 Projections selon nombre d'utilisateurs (extrapolation depuis votre mix actuel)
        </h3>
        <table className="w-full text-xs">
          <thead className="text-slate-400">
            <tr>
              <th className="text-left px-3 py-2">Échelle</th>
              <th className="text-right px-3 py-2">APIs providers</th>
              <th className="text-right px-3 py-2">Infra (sub-linéaire)</th>
              <th className="text-right px-3 py-2">Total /mois</th>
              <th className="text-right px-3 py-2">XAF /mois</th>
            </tr>
          </thead>
          <tbody>
            {scenarios.map(s => (
              <tr key={s.label} className="border-t border-slate-700">
                <td className="px-3 py-2 text-white font-medium">{s.label}</td>
                <td className="px-3 py-2 text-right text-slate-300">{fmtUsd(s.apiUsd)}</td>
                <td className="px-3 py-2 text-right text-slate-300">{fmtUsd(s.infraUsd || _INFRA_TOTAL_USD)}</td>
                <td className="px-3 py-2 text-right text-white font-bold">{fmtUsd(s.totalUsd)}</td>
                <td className="px-3 py-2 text-right text-slate-400">{fmtFcfa(s.totalUsd * 600)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {stats.usersActifs === 0 && (
          <p className="mt-3 text-xs text-amber-300">
            ⚠ Aucun utilisateur actif sur la période — scénarios non calculables.
            Ils s'affineront dès que les premières conso commenceront.
          </p>
        )}
      </div>

      {/* ── Décomposition par provider ──────────────────────────────── */}
      {stats.parProvider.length > 0 && (
        <div className="rounded-xl border border-slate-700 bg-slate-800/50 p-4">
          <h3 className="text-sm font-semibold text-white mb-3">
            🔧 Décomposition par fournisseur (projection 30 jours)
          </h3>
          <table className="w-full text-xs">
            <thead className="text-slate-400">
              <tr>
                <th className="text-left px-3 py-2">Provider</th>
                <th className="text-right px-3 py-2">Appels</th>
                <th className="text-right px-3 py-2">USD observé ({stats.jours}j)</th>
                <th className="text-right px-3 py-2">Projeté 30j</th>
                <th className="text-right px-3 py-2">% total</th>
                <th className="text-left px-3 py-2 pl-4">Modèles</th>
              </tr>
            </thead>
            <tbody>
              {stats.parProvider.map(p => {
                const pct = stats.projectionUsd30j > 0
                  ? (p.proj_30j_usd / stats.projectionUsd30j) * 100 : 0;
                return (
                  <tr key={p.provider} className="border-t border-slate-700">
                    <td className="px-3 py-2 text-white font-medium">{p.provider}</td>
                    <td className="px-3 py-2 text-right text-slate-300">{p.nb_appels.toLocaleString("fr-FR")}</td>
                    <td className="px-3 py-2 text-right text-slate-300">{fmtUsd(p.usd)}</td>
                    <td className="px-3 py-2 text-right text-white font-bold">{fmtUsd(p.proj_30j_usd)}</td>
                    <td className="px-3 py-2 text-right">
                      <span className={
                        "px-2 py-0.5 rounded text-[10px] font-semibold " +
                        (pct > 50 ? "bg-red-500/20 text-red-300"
                          : pct > 25 ? "bg-amber-500/20 text-amber-300"
                          : "bg-slate-500/20 text-slate-300")
                      }>{pct.toFixed(1)}%</span>
                    </td>
                    <td className="px-3 py-2 pl-4 text-slate-400 text-[10px]">
                      {(p.modeles || []).slice(0, 4).join(", ")}
                      {p.modeles && p.modeles.length > 4 ? "…" : ""}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Décomposition par feature/module ───────────────────────── */}
      {stats.parFeature.length > 0 && (
        <div className="rounded-xl border border-slate-700 bg-slate-800/50 p-4">
          <h3 className="text-sm font-semibold text-white mb-3">
            📊 Top 8 modules par coût projeté (30 jours)
          </h3>
          <table className="w-full text-xs">
            <thead className="text-slate-400">
              <tr>
                <th className="text-left px-3 py-2">Module</th>
                <th className="text-center px-3 py-2">App</th>
                <th className="text-right px-3 py-2">Appels ({stats.jours}j)</th>
                <th className="text-right px-3 py-2">Projeté 30j (XAF)</th>
                <th className="text-right px-3 py-2">Projeté 30j (USD)</th>
              </tr>
            </thead>
            <tbody>
              {stats.parFeature.map(f => (
                <tr key={`${f.app}-${f.module}`} className="border-t border-slate-700">
                  <td className="px-3 py-2 text-white font-medium">{f.module}</td>
                  <td className="px-3 py-2 text-center">
                    <span className={
                      "px-2 py-0.5 rounded text-[10px] font-semibold " +
                      (f.app === "pro"
                        ? "bg-blue-500/20 text-blue-300"
                        : "bg-purple-500/20 text-purple-300")
                    }>{f.app === "pro" ? "Pro" : "Sec"}</span>
                  </td>
                  <td className="px-3 py-2 text-right text-slate-300">{f.nb_appels.toLocaleString("fr-FR")}</td>
                  <td className="px-3 py-2 text-right text-white font-bold">{fmtFcfa(f.proj_30j_fcfa)}</td>
                  <td className="px-3 py-2 text-right text-slate-400">{fmtUsd(f.proj_30j_fcfa / 600)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Détail infra fixe ────────────────────────────────────── */}
      <details className="rounded-xl border border-slate-700 bg-slate-800/50 p-4">
        <summary className="text-sm font-semibold text-white cursor-pointer hover:text-emerald-300">
          🏗️ Décomposition infrastructure fixe ({fmtUsd(_INFRA_TOTAL_USD)}/mois)
        </summary>
        <table className="w-full text-xs mt-3">
          <thead className="text-slate-400">
            <tr>
              <th className="text-left px-3 py-2">Poste</th>
              <th className="text-right px-3 py-2">USD/mois</th>
              <th className="text-left px-3 py-2">Détails</th>
            </tr>
          </thead>
          <tbody>
            {_INFRA_FIXE_USD.map(i => (
              <tr key={i.nom} className="border-t border-slate-700">
                <td className="px-3 py-2 text-white">{i.nom}</td>
                <td className="px-3 py-2 text-right text-slate-300">{fmtUsd(i.usd)}</td>
                <td className="px-3 py-2 text-slate-400 text-[11px]">{i.details}</td>
              </tr>
            ))}
            <tr className="border-t-2 border-slate-600">
              <td className="px-3 py-2 text-white font-bold">Total infra</td>
              <td className="px-3 py-2 text-right text-white font-bold">{fmtUsd(_INFRA_TOTAL_USD)}</td>
              <td className="px-3 py-2 text-slate-400 text-[11px]">Indépendant du volume users (jusqu'à ~5000 MAU)</td>
            </tr>
          </tbody>
        </table>
        <p className="mt-3 text-xs text-slate-500">
          Ces estimations restent indicatives — révise les valeurs dans le code
          si tu changes la taille des VM Fly, ajoutes un Datadog, etc.
        </p>
      </details>
    </div>
  );
};


// Helpers de formatage
function fmtUsd(usd: number): string {
  if (!Number.isFinite(usd)) return "—";
  if (Math.abs(usd) >= 1000) return "$" + usd.toLocaleString("fr-FR", { maximumFractionDigits: 0 });
  if (Math.abs(usd) >= 10) return "$" + usd.toFixed(0);
  if (Math.abs(usd) >= 1) return "$" + usd.toFixed(2);
  return "$" + usd.toFixed(3);
}

function fmtFcfa(fcfa: number): string {
  if (!Number.isFinite(fcfa)) return "—";
  if (Math.abs(fcfa) >= 1_000_000) return (fcfa / 1_000_000).toFixed(1) + " M XAF";
  if (Math.abs(fcfa) >= 1_000) return (fcfa / 1_000).toFixed(0) + " k XAF";
  return Math.round(fcfa).toLocaleString("fr-FR") + " XAF";
}

// ForecastKpi : carte synthèse spécifique au tab Forecast (le KpiCard de
// l'OverviewTab a une signature avec icônes Lucide — on garde celui-ci minimal
// pour éviter une régression sur l'overview).
const ForecastKpi = ({ label, value, sub, tone = "default" }: {
  label: string; value: string; sub?: string;
  tone?: "default" | "amber" | "emerald" | "red";
}) => {
  const toneClass = tone === "amber" ? "border-amber-500/40 bg-amber-500/5"
    : tone === "emerald" ? "border-emerald-500/40 bg-emerald-500/5"
    : tone === "red" ? "border-red-500/40 bg-red-500/5"
    : "border-slate-700 bg-slate-800/50";
  return (
    <div className={"rounded-xl border p-4 " + toneClass}>
      <div className="text-xs text-slate-400">{label}</div>
      <div className="text-2xl font-bold text-white mt-1">{value}</div>
      {sub && <div className="text-[11px] text-slate-500 mt-1">{sub}</div>}
    </div>
  );
};
