import { useEffect, useState } from "react";
import {
  Users, BarChart3, Cpu, RefreshCw, Search, Shield, FileText, TrendingUp,
  Lock, Unlock, Gift, Edit3, X, Mail, Calendar, Activity, DollarSign,
  Megaphone, ChevronRight, Ban, Plus, Wallet, CreditCard, TrendingDown,
} from "lucide-react";
import { Button, Card, Badge, Spinner } from "@/components/ui";
import { adminApi } from "@/api/client";
import { useAuthStore } from "@/store";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";

type Tab = "overview" | "users" | "revenus" | "promotions";

interface UserItem {
  id: number;
  username: string;
  email: string;
  nom: string;
  prenoms?: string;
  role: string;
  telephone?: string;
  actif: boolean;
  bloque: boolean;
  bloque_jusqu_au?: string | null;
  derniere_connexion?: string | null;
  nb_connexions: number;
  cree_le?: string;
  plan: string;
  credits_alloues: number;
  credits_utilises: number;
  credits_restants: number;
  periode_fin?: string | null;
  conso_total: number;
  nb_appels_total: number;
}

interface StatsAvancees {
  total_utilisateurs: number;
  actifs: number;
  bloques: number;
  repartition_plans: { plan: string; count: number }[];
  signups_30j: { jour: string; count: number }[];
  mrr_estime_fcfa: number;
  top_consommateurs: { user_id: number; username: string; email?: string; credits: number; appels: number }[];
  credits_par_plan: Record<string, number>;
}

const PLAN_BADGE: Record<string, "slate" | "corp" | "purple" | "gold" | "green"> = {
  gratuit: "slate", starter: "corp", pro: "purple", business: "gold",
};

const fmt = (n: number) => n.toLocaleString("fr-FR", { maximumFractionDigits: 0 });
const fmtDate = (iso?: string | null) => iso ? new Date(iso).toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "numeric" }) : "—";

export const AdminPage = () => {
  const { user } = useAuthStore();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("overview");

  // Auth check
  useEffect(() => {
    if (user && !["admin", "super_admin", "yukpo_owner"].includes(user.role)) {
      navigate("/dashboard");
      toast.error("Accès réservé aux administrateurs");
    }
  }, [user]);

  return (
    <div className="p-3 sm:p-6 max-w-7xl mx-auto space-y-4 sm:space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-rose-500/15 flex items-center justify-center">
            <Shield className="w-5 h-5 text-rose-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold" style={{ color: "var(--ykp-text-primary)" }}>Administration</h1>
            <p className="text-sm" style={{ color: "var(--ykp-text-muted)" }}>
              Console de management — utilisateurs, abonnements, promotions
            </p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b overflow-x-auto -mx-3 sm:mx-0 px-3 sm:px-0" style={{ borderColor: "var(--ykp-border)" }}>
        {([
          { id: "overview", label: "Vue d'ensemble", icon: BarChart3 },
          { id: "users", label: "Utilisateurs", icon: Users },
          { id: "revenus", label: "Revenus / CA", icon: Wallet },
          { id: "promotions", label: "Promotions", icon: Megaphone },
        ] as { id: Tab; label: string; icon: any }[]).map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-2 px-3 sm:px-4 py-2.5 text-sm font-medium transition-colors border-b-2 whitespace-nowrap shrink-0 ${
              tab === t.id
                ? "border-corp-600 text-corp-700"
                : "border-transparent hover:text-corp-600"
            }`}
            style={tab !== t.id ? { color: "var(--ykp-text-muted)" } : {}}
          >
            <t.icon className="w-4 h-4" />
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" && <OverviewTab />}
      {tab === "users" && <UsersTab />}
      {tab === "revenus" && <RevenusTab />}
      {tab === "promotions" && <PromotionsTab />}
    </div>
  );
};

// ─────────────────────── Onglet Vue d'ensemble ───────────────────────

const OverviewTab = () => {
  const [stats, setStats] = useState<StatsAvancees | null>(null);
  const [loading, setLoading] = useState(true);

  const charger = async () => {
    setLoading(true);
    try {
      const d = await adminApi.statsAvancees();
      setStats(d);
    } catch {
      toast.error("Erreur de chargement");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { charger(); }, []);

  if (loading || !stats) return <div className="flex justify-center py-16"><Spinner size="lg" /></div>;

  const maxSignup = Math.max(1, ...stats.signups_30j.map(s => s.count));
  const totalPlanUsers = stats.repartition_plans.reduce((acc, r) => acc + r.count, 0) || 1;

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <Button variant="ghost" size="sm" icon={<RefreshCw className="w-4 h-4" />} onClick={charger}>Actualiser</Button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KPI icon={Users} label="Utilisateurs" value={fmt(stats.total_utilisateurs)} color="text-corp-600" />
        <KPI icon={Activity} label="Actifs" value={fmt(stats.actifs)} color="text-emerald-600" />
        <KPI icon={Ban} label="Bloqués" value={fmt(stats.bloques)} color="text-rose-600" />
        <KPI icon={DollarSign} label="MRR estimé" value={`${fmt(stats.mrr_estime_fcfa)} F`} color="text-amber-600" />
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Répartition plans */}
        <Card className="p-5">
          <h3 className="font-semibold mb-4 flex items-center gap-2" style={{ color: "var(--ykp-text-primary)" }}>
            <BarChart3 className="w-4 h-4 text-corp-600" /> Répartition par plan
          </h3>
          <div className="space-y-3">
            {stats.repartition_plans.map((r) => {
              const pct = (r.count / totalPlanUsers) * 100;
              return (
                <div key={r.plan}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="flex items-center gap-2">
                      <Badge variant={PLAN_BADGE[r.plan] || "slate"} size="sm">{r.plan}</Badge>
                      <span style={{ color: "var(--ykp-text-secondary)" }}>{r.count} utilisateurs</span>
                    </span>
                    <span className="font-medium" style={{ color: "var(--ykp-text-primary)" }}>{pct.toFixed(0)}%</span>
                  </div>
                  <div className="h-2 rounded-full overflow-hidden" style={{ background: "var(--ykp-elevated)" }}>
                    <div className="h-full" style={{ width: `${pct}%`, background: "linear-gradient(90deg,#00B0F0,#0054A6)" }} />
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        {/* Inscriptions 30j */}
        <Card className="p-5">
          <h3 className="font-semibold mb-4 flex items-center gap-2" style={{ color: "var(--ykp-text-primary)" }}>
            <TrendingUp className="w-4 h-4 text-emerald-600" /> Nouvelles inscriptions (30j)
          </h3>
          {stats.signups_30j.length === 0 ? (
            <p className="text-sm py-8 text-center" style={{ color: "var(--ykp-text-muted)" }}>Aucune inscription récente</p>
          ) : (
            <div className="flex items-end gap-1 h-40">
              {stats.signups_30j.map((s) => {
                const px = Math.max(Math.round((s.count / maxSignup) * 160), 4);
                return (
                  <div key={s.jour} className="flex-1 h-full flex flex-col justify-end items-center group relative">
                    <div className="w-full rounded-t" style={{ height: `${px}px`, background: "linear-gradient(180deg,#34d399,#059669)" }} />
                    <div className="absolute -top-9 opacity-0 group-hover:opacity-100 bg-black text-white text-xs px-2 py-1 rounded whitespace-nowrap z-10 pointer-events-none">
                      {s.jour.slice(5)} : {s.count}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      </div>

      {/* Top consommateurs */}
      <Card className="p-5">
        <h3 className="font-semibold mb-4 flex items-center gap-2" style={{ color: "var(--ykp-text-primary)" }}>
          <Cpu className="w-4 h-4 text-amber-600" /> Top 10 consommateurs (30j)
        </h3>
        {stats.top_consommateurs.length === 0 ? (
          <p className="text-sm py-8 text-center" style={{ color: "var(--ykp-text-muted)" }}>Aucune consommation enregistrée</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase border-b" style={{ color: "var(--ykp-text-muted)", borderColor: "var(--ykp-border)" }}>
                  <th className="py-2">Utilisateur</th>
                  <th className="py-2">Email</th>
                  <th className="py-2 text-right">Crédits consommés</th>
                  <th className="py-2 text-right">Appels</th>
                </tr>
              </thead>
              <tbody>
                {stats.top_consommateurs.map((u) => (
                  <tr key={u.user_id} className="border-b" style={{ borderColor: "var(--ykp-border)" }}>
                    <td className="py-2 font-medium" style={{ color: "var(--ykp-text-primary)" }}>{u.username}</td>
                    <td className="py-2" style={{ color: "var(--ykp-text-secondary)" }}>{u.email || "—"}</td>
                    <td className="py-2 text-right font-semibold text-amber-600">{fmt(u.credits)}</td>
                    <td className="py-2 text-right" style={{ color: "var(--ykp-text-secondary)" }}>{u.appels}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
};

const KPI = ({ icon: Icon, label, value, color }: { icon: any; label: string; value: string; color: string }) => (
  <Card className="p-4">
    <div className="flex items-center gap-2 text-xs font-semibold uppercase" style={{ color: "var(--ykp-text-muted)" }}>
      <Icon className={`w-3.5 h-3.5 ${color}`} /> {label}
    </div>
    <p className="text-2xl font-bold mt-2" style={{ color: "var(--ykp-text-primary)" }}>{value}</p>
  </Card>
);

// ─────────────────────── Onglet Utilisateurs ───────────────────────

const UsersTab = () => {
  const [users, setUsers] = useState<UserItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [planFilter, setPlanFilter] = useState("");
  const [statutFilter, setStatutFilter] = useState("");
  const [selectedUser, setSelectedUser] = useState<UserItem | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  const charger = async () => {
    setLoading(true);
    try {
      const d = await adminApi.utilisateurs({
        page, par_page: 50,
        search: search || undefined,
        plan: planFilter || undefined,
        statut: statutFilter || undefined,
      });
      setUsers(d.utilisateurs || []);
      setTotal(d.total || 0);
    } catch {
      toast.error("Erreur de chargement");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { charger(); }, [page, planFilter, statutFilter]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    charger();
  };

  return (
    <div className="space-y-4">
      {/* Filtres */}
      <Card className="p-4">
        <form onSubmit={handleSearchSubmit} className="flex flex-wrap gap-3">
          <div className="flex-1 min-w-64 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: "var(--ykp-text-muted)" }} />
            <input
              type="text" placeholder="Rechercher (username, email, nom)…"
              value={search} onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-lg border pl-9 pr-3 py-2 text-sm"
              style={{ background: "var(--ykp-surface)", borderColor: "var(--ykp-border)", color: "var(--ykp-text-primary)" }}
            />
          </div>
          <select value={planFilter} onChange={(e) => { setPlanFilter(e.target.value); setPage(1); }}
            className="rounded-lg border px-3 py-2 text-sm"
            style={{ background: "var(--ykp-surface)", borderColor: "var(--ykp-border)", color: "var(--ykp-text-primary)" }}>
            <option value="">Tous les plans</option>
            <option value="gratuit">Gratuit</option>
            <option value="starter">Starter</option>
            <option value="pro">Pro</option>
            <option value="business">Business</option>
          </select>
          <select value={statutFilter} onChange={(e) => { setStatutFilter(e.target.value); setPage(1); }}
            className="rounded-lg border px-3 py-2 text-sm"
            style={{ background: "var(--ykp-surface)", borderColor: "var(--ykp-border)", color: "var(--ykp-text-primary)" }}>
            <option value="">Tous statuts</option>
            <option value="actif">Actifs</option>
            <option value="bloque">Bloqués</option>
          </select>
          <Button type="submit" size="sm" icon={<Search className="w-4 h-4" />}>Rechercher</Button>
        </form>
      </Card>

      <Card className="p-0 overflow-hidden">
        {loading ? (
          <div className="flex justify-center py-16"><Spinner /></div>
        ) : users.length === 0 ? (
          <p className="text-center py-12 text-sm" style={{ color: "var(--ykp-text-muted)" }}>Aucun utilisateur</p>
        ) : (
          <>
            {/* Vue table (md+) */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase border-b" style={{ color: "var(--ykp-text-muted)", borderColor: "var(--ykp-border)" }}>
                    <th className="py-3 px-4">Utilisateur</th>
                    <th className="py-3 px-4">Plan</th>
                    <th className="py-3 px-4 text-right">Crédits</th>
                    <th className="py-3 px-4 text-right">Conso totale</th>
                    <th className="py-3 px-4">Dernière connexion</th>
                    <th className="py-3 px-4">Statut</th>
                    <th className="py-3 px-4"></th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id} className="border-b hover:bg-slate-50" style={{ borderColor: "var(--ykp-border)" }}>
                      <td className="py-3 px-4">
                        <div className="font-semibold" style={{ color: "var(--ykp-text-primary)" }}>{u.username}</div>
                        <div className="text-xs" style={{ color: "var(--ykp-text-muted)" }}>{u.email}</div>
                      </td>
                      <td className="py-3 px-4">
                        <Badge variant={PLAN_BADGE[u.plan] || "slate"} size="sm">{u.plan}</Badge>
                      </td>
                      <td className="py-3 px-4 text-right">
                        <div className="font-medium" style={{ color: "var(--ykp-text-primary)" }}>
                          {fmt(u.credits_restants)} <span className="font-normal" style={{ color: "var(--ykp-text-muted)" }}>/ {fmt(u.credits_alloues)}</span>
                        </div>
                      </td>
                      <td className="py-3 px-4 text-right" style={{ color: "var(--ykp-text-secondary)" }}>
                        {fmt(u.conso_total)} cr · {u.nb_appels_total}
                      </td>
                      <td className="py-3 px-4 text-xs" style={{ color: "var(--ykp-text-secondary)" }}>{fmtDate(u.derniere_connexion)}</td>
                      <td className="py-3 px-4">
                        {u.bloque
                          ? <Badge variant="red" size="sm">Bloqué</Badge>
                          : <Badge variant="green" size="sm">Actif</Badge>}
                      </td>
                      <td className="py-3 px-4">
                        <Button size="sm" variant="ghost" icon={<ChevronRight className="w-4 h-4" />} onClick={() => setSelectedUser(u)}>
                          Gérer
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {/* Vue cards (mobile) */}
            <div className="md:hidden divide-y" style={{ borderColor: "var(--ykp-border)" }}>
              {users.map((u) => (
                <button key={u.id} onClick={() => setSelectedUser(u)}
                  className="w-full text-left p-3 active:bg-slate-100 flex items-start gap-3"
                  style={{ borderColor: "var(--ykp-border)" }}>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold truncate" style={{ color: "var(--ykp-text-primary)" }}>{u.username}</span>
                      <Badge variant={PLAN_BADGE[u.plan] || "slate"} size="sm">{u.plan}</Badge>
                      {u.bloque
                        ? <Badge variant="red" size="sm">Bloqué</Badge>
                        : <Badge variant="green" size="sm">Actif</Badge>}
                    </div>
                    <div className="text-xs mt-0.5 truncate" style={{ color: "var(--ykp-text-muted)" }}>{u.email}</div>
                    <div className="flex justify-between mt-1.5 text-xs" style={{ color: "var(--ykp-text-secondary)" }}>
                      <span>{fmt(u.credits_restants)} / {fmt(u.credits_alloues)} cr</span>
                      <span>{fmt(u.conso_total)} consommés</span>
                    </div>
                  </div>
                  <ChevronRight className="w-4 h-4 mt-1 shrink-0" style={{ color: "var(--ykp-text-muted)" }} />
                </button>
              ))}
            </div>
          </>
        )}
        {total > 50 && (
          <div className="flex justify-between items-center px-4 py-3 border-t text-sm" style={{ borderColor: "var(--ykp-border)" }}>
            <span style={{ color: "var(--ykp-text-muted)" }}>{total} utilisateurs</span>
            <div className="flex gap-2">
              <Button size="sm" variant="ghost" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Précédent</Button>
              <span className="px-2 py-1" style={{ color: "var(--ykp-text-secondary)" }}>{page} / {Math.ceil(total / 50)}</span>
              <Button size="sm" variant="ghost" disabled={page * 50 >= total} onClick={() => setPage(p => p + 1)}>Suivant</Button>
            </div>
          </div>
        )}
      </Card>

      {selectedUser && <UserDrawer user={selectedUser} onClose={() => setSelectedUser(null)} onUpdated={charger} />}
    </div>
  );
};

// ─────────────────────── Drawer détails utilisateur ───────────────────────

const UserDrawer = ({ user, onClose, onUpdated }: { user: UserItem; onClose: () => void; onUpdated: () => void }) => {
  const [details, setDetails] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<"abo" | "bonus" | null>(null);
  const [abo, setAbo] = useState({ plan: user.plan, credits_bonus: 0, duree_jours: 30 });
  const [bonus, setBonus] = useState({ montant: 0, motif: "" });
  const [busy, setBusy] = useState(false);

  const charger = async () => {
    setLoading(true);
    try { setDetails(await adminApi.detailsUtilisateur(user.id)); } catch {} finally { setLoading(false); }
  };
  useEffect(() => { charger(); }, [user.id]);

  const handleForcer = async () => {
    setBusy(true);
    try {
      await adminApi.forcerAbonnement(user.id, abo.plan, abo.credits_bonus, abo.duree_jours);
      toast.success("Abonnement modifié");
      setAction(null); onUpdated(); charger();
    } catch { toast.error("Erreur"); } finally { setBusy(false); }
  };

  const handleBonus = async () => {
    if (bonus.montant <= 0) return;
    setBusy(true);
    try {
      await adminApi.creditsBonus(user.id, bonus.montant, bonus.motif);
      toast.success(`+${bonus.montant} crédits ajoutés`);
      setAction(null); setBonus({ montant: 0, motif: "" }); onUpdated(); charger();
    } catch { toast.error("Erreur"); } finally { setBusy(false); }
  };

  const handleBloquer = async () => {
    if (!confirm(`Bloquer ${user.username} ?`)) return;
    setBusy(true);
    try {
      await adminApi.bloquer(user.id, "Action admin");
      toast.success("Utilisateur bloqué"); onUpdated(); onClose();
    } catch { toast.error("Erreur"); } finally { setBusy(false); }
  };

  const handleDebloquer = async () => {
    setBusy(true);
    try {
      await adminApi.debloquer(user.id);
      toast.success("Utilisateur débloqué"); onUpdated(); onClose();
    } catch { toast.error("Erreur"); } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex" onClick={onClose}>
      <div className="flex-1 bg-black/40" />
      <div className="w-full max-w-xl h-full overflow-y-auto shadow-2xl" style={{ background: "var(--ykp-bg)" }}
        onClick={(e) => e.stopPropagation()}>
        <div className="p-4 sm:p-5 border-b sticky top-0 z-10" style={{ borderColor: "var(--ykp-border)", background: "var(--ykp-bg)" }}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-xl font-bold" style={{ color: "var(--ykp-text-primary)" }}>{user.username}</h2>
              <p className="text-sm flex items-center gap-1" style={{ color: "var(--ykp-text-muted)" }}>
                <Mail className="w-3.5 h-3.5" /> {user.email}
              </p>
            </div>
            <Button variant="ghost" size="sm" icon={<X className="w-4 h-4" />} onClick={onClose}>Fermer</Button>
          </div>
          <div className="flex flex-wrap gap-2 mt-3">
            <Badge variant={PLAN_BADGE[user.plan] || "slate"} size="sm">{user.plan}</Badge>
            {user.bloque ? <Badge variant="red" size="sm">Bloqué</Badge> : <Badge variant="green" size="sm">Actif</Badge>}
            <Badge variant="slate" size="sm">{user.role}</Badge>
          </div>
        </div>

        <div className="p-4 sm:p-5 space-y-4 sm:space-y-5">
          {/* Actions */}
          <div className="grid grid-cols-2 gap-2">
            <Button size="sm" variant={action === "abo" ? "primary" : "secondary"} icon={<Edit3 className="w-4 h-4" />}
              onClick={() => setAction(action === "abo" ? null : "abo")}>Changer plan</Button>
            <Button size="sm" variant={action === "bonus" ? "primary" : "secondary"} icon={<Gift className="w-4 h-4" />}
              onClick={() => setAction(action === "bonus" ? null : "bonus")}>Bonus crédits</Button>
            {user.bloque
              ? <Button size="sm" variant="secondary" icon={<Unlock className="w-4 h-4" />} onClick={handleDebloquer} disabled={busy}>Débloquer</Button>
              : <Button size="sm" variant="danger" icon={<Lock className="w-4 h-4" />} onClick={handleBloquer} disabled={busy}>Bloquer</Button>}
          </div>

          {action === "abo" && (
            <Card className="p-4 space-y-3">
              <h4 className="font-semibold text-sm">Forcer le plan</h4>
              <select value={abo.plan} onChange={(e) => setAbo({ ...abo, plan: e.target.value })}
                className="w-full rounded border px-2 py-1.5 text-sm"
                style={{ background: "var(--ykp-surface)", borderColor: "var(--ykp-border)", color: "var(--ykp-text-primary)" }}>
                <option value="gratuit">Gratuit (3 000)</option>
                <option value="starter">Starter (5 000)</option>
                <option value="pro">Pro (20 000)</option>
                <option value="business">Business (100 000)</option>
              </select>
              <div className="grid grid-cols-2 gap-2">
                <label className="text-xs">
                  <span style={{ color: "var(--ykp-text-muted)" }}>Crédits bonus</span>
                  <input type="number" min={0} value={abo.credits_bonus}
                    onChange={(e) => setAbo({ ...abo, credits_bonus: parseInt(e.target.value) || 0 })}
                    className="w-full rounded border px-2 py-1.5 text-sm mt-1"
                    style={{ background: "var(--ykp-surface)", borderColor: "var(--ykp-border)", color: "var(--ykp-text-primary)" }} />
                </label>
                <label className="text-xs">
                  <span style={{ color: "var(--ykp-text-muted)" }}>Durée (jours)</span>
                  <input type="number" min={1} max={365} value={abo.duree_jours}
                    onChange={(e) => setAbo({ ...abo, duree_jours: parseInt(e.target.value) || 30 })}
                    className="w-full rounded border px-2 py-1.5 text-sm mt-1"
                    style={{ background: "var(--ykp-surface)", borderColor: "var(--ykp-border)", color: "var(--ykp-text-primary)" }} />
                </label>
              </div>
              <Button size="sm" onClick={handleForcer} disabled={busy}>Appliquer</Button>
            </Card>
          )}

          {action === "bonus" && (
            <Card className="p-4 space-y-3">
              <h4 className="font-semibold text-sm">Bonus crédits ponctuel</h4>
              <input type="number" min={1} placeholder="Montant" value={bonus.montant || ""}
                onChange={(e) => setBonus({ ...bonus, montant: parseInt(e.target.value) || 0 })}
                className="w-full rounded border px-2 py-1.5 text-sm"
                style={{ background: "var(--ykp-surface)", borderColor: "var(--ykp-border)", color: "var(--ykp-text-primary)" }} />
              <input type="text" placeholder="Motif (optionnel)" value={bonus.motif}
                onChange={(e) => setBonus({ ...bonus, motif: e.target.value })}
                className="w-full rounded border px-2 py-1.5 text-sm"
                style={{ background: "var(--ykp-surface)", borderColor: "var(--ykp-border)", color: "var(--ykp-text-primary)" }} />
              <Button size="sm" onClick={handleBonus} disabled={busy || bonus.montant <= 0}>
                <Plus className="w-4 h-4 mr-1" /> Ajouter {bonus.montant > 0 ? fmt(bonus.montant) + " crédits" : ""}
              </Button>
            </Card>
          )}

          {/* Détails */}
          {loading ? (
            <div className="flex justify-center py-8"><Spinner /></div>
          ) : details && (
            <>
              <Card className="p-4 space-y-2">
                <h4 className="font-semibold text-sm flex items-center gap-2" style={{ color: "var(--ykp-text-primary)" }}>
                  <Activity className="w-4 h-4 text-corp-600" /> Crédits
                </h4>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div><span style={{ color: "var(--ykp-text-muted)" }}>Alloués :</span> <strong>{fmt(details.credits.credits_alloues)}</strong></div>
                  <div><span style={{ color: "var(--ykp-text-muted)" }}>Utilisés :</span> <strong>{fmt(details.credits.credits_utilises)}</strong></div>
                  <div><span style={{ color: "var(--ykp-text-muted)" }}>Restants :</span> <strong className="text-emerald-600">{fmt(details.credits.credits_restants)}</strong></div>
                  <div><span style={{ color: "var(--ykp-text-muted)" }}>Fin période :</span> <strong>{fmtDate(details.credits.periode_fin)}</strong></div>
                </div>
              </Card>

              <Card className="p-4 space-y-2">
                <h4 className="font-semibold text-sm flex items-center gap-2" style={{ color: "var(--ykp-text-primary)" }}>
                  <Calendar className="w-4 h-4 text-corp-600" /> Activité
                </h4>
                <div className="text-sm space-y-1" style={{ color: "var(--ykp-text-secondary)" }}>
                  <div>Dernière connexion : <strong>{fmtDate(details.utilisateur.derniere_connexion)}</strong></div>
                  <div>Nb connexions : <strong>{details.utilisateur.nb_connexions}</strong></div>
                  <div>Inscrit le : <strong>{fmtDate(details.utilisateur.cree_le)}</strong></div>
                </div>
              </Card>

              {details.conso_30j.length > 0 && (
                <Card className="p-4">
                  <h4 className="font-semibold text-sm mb-3 flex items-center gap-2" style={{ color: "var(--ykp-text-primary)" }}>
                    <Cpu className="w-4 h-4 text-corp-600" /> Consommation 30j (par module)
                  </h4>
                  <div className="space-y-1 text-sm">
                    {details.conso_30j.map((m: any) => (
                      <div key={m.module} className="flex justify-between">
                        <span style={{ color: "var(--ykp-text-secondary)" }}>{m.module}</span>
                        <span style={{ color: "var(--ykp-text-primary)" }}>{fmt(m.credits)} cr · {m.appels} appels</span>
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              {details.transactions.length > 0 && (
                <Card className="p-4">
                  <h4 className="font-semibold text-sm mb-3 flex items-center gap-2" style={{ color: "var(--ykp-text-primary)" }}>
                    <DollarSign className="w-4 h-4 text-amber-600" /> Transactions ({details.transactions.length})
                  </h4>
                  <div className="space-y-2 text-xs">
                    {details.transactions.slice(0, 10).map((t: any) => (
                      <div key={t.reference} className="flex justify-between">
                        <span style={{ color: "var(--ykp-text-secondary)" }}>{t.type} · {t.plan || "—"}</span>
                        <span><strong>{fmt(t.amount)} {t.currency}</strong> · <Badge variant={t.status === "success" ? "green" : t.status === "failed" ? "red" : "slate"} size="sm">{t.status}</Badge></span>
                      </div>
                    ))}
                  </div>
                </Card>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

// ─────────────────────── Onglet Revenus / CA ───────────────────────

interface RevenusData {
  ca_total_par_devise: { devise: string; montant: number; transactions: number }[];
  ca_aujourdhui: { devise: string; montant: number; transactions: number }[];
  ca_7j: { devise: string; montant: number; transactions: number }[];
  ca_30j: { devise: string; montant: number; transactions: number }[];
  evolution_12mois: { mois: string; devise: string; montant: number; transactions: number }[];
  par_plan: { plan: string; devise: string; montant: number; transactions: number }[];
  par_provider: { provider: string; devise: string; montant: number; transactions: number }[];
  par_statut: Record<string, number>;
  dernieres_transactions: any[];
}

const sumAmount = (arr: { montant: number }[]) => arr.reduce((a, b) => a + b.montant, 0);
const sumTx = (arr: { transactions: number }[]) => arr.reduce((a, b) => a + b.transactions, 0);

const RevenusTab = () => {
  const [data, setData] = useState<RevenusData | null>(null);
  const [loading, setLoading] = useState(true);

  const charger = async () => {
    setLoading(true);
    try { setData(await adminApi.statsRevenus()); }
    catch { toast.error("Erreur de chargement"); }
    finally { setLoading(false); }
  };
  useEffect(() => { charger(); }, []);

  if (loading || !data) return <div className="flex justify-center py-16"><Spinner size="lg" /></div>;

  const success = data.par_statut.success || 0;
  const pending = data.par_statut.pending || 0;
  const failed = data.par_statut.failed || 0;

  // Évolution 12 mois agrégé toutes devises (FCFA proche XAF/XOF)
  const evolutionAgg = data.evolution_12mois.reduce<Record<string, number>>((acc, e) => {
    acc[e.mois] = (acc[e.mois] || 0) + e.montant;
    return acc;
  }, {});
  const moisOrd = Object.keys(evolutionAgg).sort();
  const maxMois = Math.max(1, ...Object.values(evolutionAgg));

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <Button variant="ghost" size="sm" icon={<RefreshCw className="w-4 h-4" />} onClick={charger}>Actualiser</Button>
      </div>

      {/* CA totaux */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KPI icon={Wallet} label="CA total" value={`${fmt(sumAmount(data.ca_total_par_devise))} F`} color="text-emerald-600" />
        <KPI icon={TrendingUp} label="CA 30j" value={`${fmt(sumAmount(data.ca_30j))} F`} color="text-corp-600" />
        <KPI icon={TrendingUp} label="CA 7j" value={`${fmt(sumAmount(data.ca_7j))} F`} color="text-amber-600" />
        <KPI icon={DollarSign} label="CA aujourd'hui" value={`${fmt(sumAmount(data.ca_aujourdhui))} F`} color="text-purple-600" />
      </div>

      {/* CA par devise */}
      <Card className="p-5">
        <h3 className="font-semibold mb-3 flex items-center gap-2" style={{ color: "var(--ykp-text-primary)" }}>
          <DollarSign className="w-4 h-4 text-emerald-600" /> Chiffre d'affaires par devise
        </h3>
        {data.ca_total_par_devise.length === 0 ? (
          <p className="text-sm py-6 text-center" style={{ color: "var(--ykp-text-muted)" }}>Aucune transaction réussie</p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {data.ca_total_par_devise.map((d) => (
              <div key={d.devise} className="rounded-lg border p-3" style={{ borderColor: "var(--ykp-border)", background: "var(--ykp-surface)" }}>
                <div className="text-xs uppercase font-semibold" style={{ color: "var(--ykp-text-muted)" }}>{d.devise}</div>
                <div className="text-xl font-bold mt-1" style={{ color: "var(--ykp-text-primary)" }}>{fmt(d.montant)}</div>
                <div className="text-xs" style={{ color: "var(--ykp-text-secondary)" }}>{d.transactions} transactions</div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Évolution mensuelle */}
      <Card className="p-5">
        <h3 className="font-semibold mb-4 flex items-center gap-2" style={{ color: "var(--ykp-text-primary)" }}>
          <TrendingUp className="w-4 h-4 text-corp-600" /> Évolution sur 12 mois
        </h3>
        {moisOrd.length === 0 ? (
          <p className="text-sm py-8 text-center" style={{ color: "var(--ykp-text-muted)" }}>Pas de données mensuelles</p>
        ) : (
          <div className="flex items-end gap-2 h-48 overflow-x-auto">
            {moisOrd.map((m) => {
              const v = evolutionAgg[m];
              const px = Math.max(Math.round((v / maxMois) * 180), 4);
              return (
                <div key={m} className="flex-1 min-w-[40px] h-full flex flex-col justify-end items-center group relative">
                  <div className="w-full rounded-t" style={{ height: `${px}px`, background: "linear-gradient(180deg,#34d399,#059669)" }} />
                  <span className="text-[10px] mt-1" style={{ color: "var(--ykp-text-muted)" }}>{m.slice(2)}</span>
                  <div className="absolute -top-9 opacity-0 group-hover:opacity-100 bg-black text-white text-xs px-2 py-1 rounded whitespace-nowrap z-10 pointer-events-none">
                    {fmt(v)} F
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Par plan */}
        <Card className="p-5">
          <h3 className="font-semibold mb-3 flex items-center gap-2" style={{ color: "var(--ykp-text-primary)" }}>
            <CreditCard className="w-4 h-4 text-corp-600" /> Par plan / pack
          </h3>
          {data.par_plan.length === 0 ? (
            <p className="text-sm py-6 text-center" style={{ color: "var(--ykp-text-muted)" }}>—</p>
          ) : (
            <div className="space-y-2 text-sm">
              {data.par_plan.map((r, i) => (
                <div key={i} className="flex justify-between border-b pb-1" style={{ borderColor: "var(--ykp-border)" }}>
                  <span style={{ color: "var(--ykp-text-secondary)" }}>{r.plan} <span className="text-xs">({r.devise})</span></span>
                  <span className="font-semibold" style={{ color: "var(--ykp-text-primary)" }}>{fmt(r.montant)} · <span className="text-xs font-normal" style={{ color: "var(--ykp-text-muted)" }}>{r.transactions}</span></span>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Par provider */}
        <Card className="p-5">
          <h3 className="font-semibold mb-3 flex items-center gap-2" style={{ color: "var(--ykp-text-primary)" }}>
            <Activity className="w-4 h-4 text-amber-600" /> Par provider
          </h3>
          {data.par_provider.length === 0 ? (
            <p className="text-sm py-6 text-center" style={{ color: "var(--ykp-text-muted)" }}>—</p>
          ) : (
            <div className="space-y-2 text-sm">
              {data.par_provider.map((r, i) => (
                <div key={i} className="flex justify-between border-b pb-1" style={{ borderColor: "var(--ykp-border)" }}>
                  <span style={{ color: "var(--ykp-text-secondary)" }}>{r.provider} <span className="text-xs">({r.devise})</span></span>
                  <span className="font-semibold" style={{ color: "var(--ykp-text-primary)" }}>{fmt(r.montant)} · <span className="text-xs font-normal" style={{ color: "var(--ykp-text-muted)" }}>{r.transactions}</span></span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Statut transactions */}
      <Card className="p-5">
        <h3 className="font-semibold mb-3 flex items-center gap-2" style={{ color: "var(--ykp-text-primary)" }}>
          <FileText className="w-4 h-4 text-corp-600" /> Transactions par statut
        </h3>
        <div className="grid grid-cols-3 gap-3">
          <div className="rounded-lg p-3 bg-emerald-50 border border-emerald-200">
            <div className="text-xs font-semibold uppercase text-emerald-700">Réussies</div>
            <div className="text-2xl font-bold text-emerald-700 mt-1">{fmt(success)}</div>
          </div>
          <div className="rounded-lg p-3 bg-amber-50 border border-amber-200">
            <div className="text-xs font-semibold uppercase text-amber-700">En attente</div>
            <div className="text-2xl font-bold text-amber-700 mt-1">{fmt(pending)}</div>
          </div>
          <div className="rounded-lg p-3 bg-rose-50 border border-rose-200">
            <div className="text-xs font-semibold uppercase text-rose-700 flex items-center gap-1"><TrendingDown className="w-3 h-3" /> Échouées</div>
            <div className="text-2xl font-bold text-rose-700 mt-1">{fmt(failed)}</div>
          </div>
        </div>
      </Card>

      {/* Dernières transactions */}
      <Card className="p-5">
        <h3 className="font-semibold mb-3 flex items-center gap-2" style={{ color: "var(--ykp-text-primary)" }}>
          <Calendar className="w-4 h-4 text-corp-600" /> 10 dernières transactions
        </h3>
        {data.dernieres_transactions.length === 0 ? (
          <p className="text-sm py-6 text-center" style={{ color: "var(--ykp-text-muted)" }}>Aucune transaction</p>
        ) : (
          <div className="overflow-x-auto -mx-2">
            <table className="w-full text-xs sm:text-sm min-w-[640px]">
              <thead>
                <tr className="text-left text-xs uppercase border-b" style={{ color: "var(--ykp-text-muted)", borderColor: "var(--ykp-border)" }}>
                  <th className="py-2 px-2">Référence</th>
                  <th className="py-2 px-2">Type</th>
                  <th className="py-2 px-2">Plan</th>
                  <th className="py-2 px-2 text-right">Montant</th>
                  <th className="py-2 px-2">Provider</th>
                  <th className="py-2 px-2">Statut</th>
                  <th className="py-2 px-2">Date</th>
                </tr>
              </thead>
              <tbody>
                {data.dernieres_transactions.map((t) => (
                  <tr key={t.reference} className="border-b" style={{ borderColor: "var(--ykp-border)" }}>
                    <td className="py-2 px-2 font-mono text-xs" style={{ color: "var(--ykp-text-secondary)" }}>{t.reference?.slice(0, 14)}…</td>
                    <td className="py-2 px-2">{t.type}</td>
                    <td className="py-2 px-2">{t.plan || "—"}</td>
                    <td className="py-2 px-2 text-right font-semibold" style={{ color: "var(--ykp-text-primary)" }}>{fmt(t.amount)} {t.currency}</td>
                    <td className="py-2 px-2" style={{ color: "var(--ykp-text-secondary)" }}>{t.provider || "—"}</td>
                    <td className="py-2 px-2">
                      <Badge variant={t.status === "success" ? "green" : t.status === "failed" ? "red" : "slate"} size="sm">{t.status}</Badge>
                    </td>
                    <td className="py-2 px-2 text-xs" style={{ color: "var(--ykp-text-muted)" }}>{fmtDate(t.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
};

// ─────────────────────── Onglet Promotions ───────────────────────

const PromotionsTab = () => {
  const [montant, setMontant] = useState(1000);
  const [cible, setCible] = useState<"tous" | "plan" | "ids">("tous");
  const [plan, setPlan] = useState("gratuit");
  const [userIdsRaw, setUserIdsRaw] = useState("");
  const [motif, setMotif] = useState("");
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (montant <= 0) return toast.error("Montant invalide");
    let user_ids: number[] | undefined;
    if (cible === "ids") {
      user_ids = userIdsRaw.split(/[\s,]+/).map(s => parseInt(s.trim())).filter(Boolean);
      if (!user_ids.length) return toast.error("Liste d'IDs invalide");
    }
    if (!confirm(`Distribuer ${montant} crédits à la cible "${cible}" ?`)) return;
    setBusy(true);
    try {
      const r = await adminApi.promotion(montant, cible, { plan: cible === "plan" ? plan : undefined, user_ids, motif });
      toast.success(`Promotion appliquée à ${r.beneficiaires} utilisateur(s)`);
      setMontant(1000); setUserIdsRaw(""); setMotif("");
    } catch { toast.error("Erreur"); } finally { setBusy(false); }
  };

  return (
    <Card className="p-4 sm:p-6 max-w-2xl">
      <div className="flex items-center gap-2 mb-2">
        <Megaphone className="w-5 h-5 text-amber-600" />
        <h3 className="text-lg font-bold" style={{ color: "var(--ykp-text-primary)" }}>Lancer une promotion</h3>
      </div>
      <p className="text-sm mb-5" style={{ color: "var(--ykp-text-muted)" }}>
        Distribue des crédits bonus à un groupe d'utilisateurs (ajout à <code>credits_alloues</code>).
      </p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="text-sm font-medium block mb-1" style={{ color: "var(--ykp-text-primary)" }}>Montant (crédits)</label>
          <input type="number" min={1} value={montant} onChange={(e) => setMontant(parseInt(e.target.value) || 0)}
            className="w-full rounded border px-3 py-2 text-sm"
            style={{ background: "var(--ykp-surface)", borderColor: "var(--ykp-border)", color: "var(--ykp-text-primary)" }} />
        </div>

        <div>
          <label className="text-sm font-medium block mb-1" style={{ color: "var(--ykp-text-primary)" }}>Cible</label>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {[
              { v: "tous", lbl: "Tous", d: "Tous les utilisateurs" },
              { v: "plan", lbl: "Par plan", d: "Un plan spécifique" },
              { v: "ids", lbl: "Liste IDs", d: "Utilisateurs précis" },
            ].map((c) => (
              <button key={c.v} type="button" onClick={() => setCible(c.v as any)}
                className={`text-left px-3 py-2 rounded border text-sm ${cible === c.v ? "border-corp-600 bg-corp-50" : ""}`}
                style={cible !== c.v ? { borderColor: "var(--ykp-border)", background: "var(--ykp-surface)" } : {}}>
                <div className="font-semibold" style={{ color: cible === c.v ? "#0054A6" : "var(--ykp-text-primary)" }}>{c.lbl}</div>
                <div className="text-xs" style={{ color: "var(--ykp-text-muted)" }}>{c.d}</div>
              </button>
            ))}
          </div>
        </div>

        {cible === "plan" && (
          <div>
            <label className="text-sm font-medium block mb-1" style={{ color: "var(--ykp-text-primary)" }}>Plan ciblé</label>
            <select value={plan} onChange={(e) => setPlan(e.target.value)}
              className="w-full rounded border px-3 py-2 text-sm"
              style={{ background: "var(--ykp-surface)", borderColor: "var(--ykp-border)", color: "var(--ykp-text-primary)" }}>
              <option value="gratuit">Gratuit</option>
              <option value="starter">Starter</option>
              <option value="pro">Pro</option>
              <option value="business">Business</option>
            </select>
          </div>
        )}

        {cible === "ids" && (
          <div>
            <label className="text-sm font-medium block mb-1" style={{ color: "var(--ykp-text-primary)" }}>IDs utilisateurs (séparés par virgule ou espace)</label>
            <textarea value={userIdsRaw} onChange={(e) => setUserIdsRaw(e.target.value)}
              placeholder="ex: 12, 34, 56"
              className="w-full rounded border px-3 py-2 text-sm h-20"
              style={{ background: "var(--ykp-surface)", borderColor: "var(--ykp-border)", color: "var(--ykp-text-primary)" }} />
          </div>
        )}

        <div>
          <label className="text-sm font-medium block mb-1" style={{ color: "var(--ykp-text-primary)" }}>Motif (audit)</label>
          <input type="text" value={motif} onChange={(e) => setMotif(e.target.value)}
            placeholder="ex: Promotion lancement"
            className="w-full rounded border px-3 py-2 text-sm"
            style={{ background: "var(--ykp-surface)", borderColor: "var(--ykp-border)", color: "var(--ykp-text-primary)" }} />
        </div>

        <Button type="submit" disabled={busy} icon={<Megaphone className="w-4 h-4" />}>
          {busy ? "Distribution…" : "Lancer la promotion"}
        </Button>
      </form>
    </Card>
  );
};
