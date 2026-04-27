import { useState, useEffect } from "react";
import { Users, BarChart3, Settings, Shield, UserCheck } from "lucide-react";
import { cn } from "@/components/ui";
import { adminApi } from "@/api/client";
import { useAuthStore } from "@/store";
import { Navigate } from "react-router-dom";

const DEMO_USERS = [
  { id: 1, email: "admin@yukpoassurance.com", nom: "Admin Principal", role: "super_admin", created_at: "2026-01-01" },
  { id: 2, email: "diallo@nsia.cm",           nom: "Diallo Moussa",   role: "gestionnaire",created_at: "2026-02-15" },
  { id: 3, email: "kouassi@nsia.cm",          nom: "Kouassi Jean",    role: "user",        created_at: "2026-03-10" },
  { id: 4, email: "traore@laarcm.com",        nom: "Traoré Aminata",  role: "gestionnaire",created_at: "2026-03-22" },
];

const DEMO_STATS = {
  users_total: 4,
  sinistres_total: 18,
  polices_total: 142,
  tokens_utilises: 12_400,
  agents_appels: { sinistres: 45, souscription: 32, comptabilite: 18, cima: 28 },
};

const ROLE_CONFIG: Record<string, string> = {
  super_admin:  "bg-red-500/10 text-red-400 border-red-500/20",
  admin:        "bg-alerte-500/10 text-alerte-400 border-alerte-500/20",
  gestionnaire: "bg-assurance-500/10 text-ciel-400 border-assurance-500/20",
  user:         "bg-gray-500/10 text-gray-400 border-gray-500/20",
};

export function AdminPage() {
  const { user } = useAuthStore();
  const [users, setUsers]   = useState(DEMO_USERS);
  const [stats, setStats]   = useState(DEMO_STATS);
  const [onglet, setOnglet] = useState<"stats" | "users">("stats");

  const isAdmin = ["admin", "super_admin"].includes(user?.role || "");
  if (!isAdmin) return <Navigate to="/chat" replace />;

  useEffect(() => {
    adminApi.users().then((res) => setUsers(res.data as typeof DEMO_USERS)).catch(() => {});
    adminApi.stats().then((res) => setStats(res.data as typeof DEMO_STATS)).catch(() => {});
  }, []);

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="px-8 pt-8 pb-4">
        <h1 className="text-2xl font-bold text-white" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
          Administration
        </h1>
        <p className="text-sm text-gray-400 mt-0.5">Gestion utilisateurs · Statistiques · Agents Yukpo</p>
      </div>

      {/* Onglets */}
      <div className="px-8 flex gap-2 mb-6">
        {[
          { id: "stats", label: "Statistiques", icon: BarChart3 },
          { id: "users", label: "Utilisateurs", icon: Users },
        ].map(({ id, label, icon: Icon }) => (
          <button key={id} onClick={() => setOnglet(id as typeof onglet)}
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

      {/* Stats */}
      {onglet === "stats" && (
        <div className="px-8 space-y-6 pb-8">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { icon: Users,     label: "Utilisateurs",  val: stats.users_total },
              { icon: Shield,    label: "Sinistres",      val: stats.sinistres_total },
              { icon: Settings,  label: "Polices",        val: stats.polices_total },
              { icon: BarChart3, label: "Tokens IA",      val: `${(stats.tokens_utilises / 1000).toFixed(1)}k` },
            ].map(({ icon: Icon, label, val }) => (
              <div key={label} className="rounded-2xl border p-5" style={{ background: "rgba(17,24,39,0.8)", borderColor: "rgba(255,255,255,0.06)" }}>
                <div className="flex items-center gap-3 mb-2">
                  <Icon className="w-5 h-5 text-ciel-400" />
                  <p className="text-xs text-gray-500">{label}</p>
                </div>
                <p className="text-2xl font-bold text-white">{val}</p>
              </div>
            ))}
          </div>

          {/* Appels agents */}
          <div className="rounded-2xl border p-6" style={{ background: "rgba(17,24,39,0.8)", borderColor: "rgba(255,255,255,0.06)" }}>
            <p className="text-sm font-semibold text-white mb-4">Appels agents Yukpo — 30 derniers jours</p>
            <div className="space-y-3">
              {Object.entries(stats.agents_appels).map(([agent, nb]) => {
                const max = Math.max(...Object.values(stats.agents_appels));
                return (
                  <div key={agent} className="flex items-center gap-4">
                    <span className="text-xs text-gray-400 capitalize w-28 flex-shrink-0">{agent}</span>
                    <div className="flex-1 h-2 rounded-full bg-white/[0.06] overflow-hidden">
                      <div className="h-full rounded-full"
                        style={{ width: `${(nb / max) * 100}%`, background: "linear-gradient(90deg, #0054A6, #00B0F0)" }} />
                    </div>
                    <span className="text-xs font-semibold text-white w-8 text-right">{nb}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Utilisateurs */}
      {onglet === "users" && (
        <div className="px-8 space-y-3 pb-8">
          {users.map((u) => (
            <div key={u.id} className="flex items-center justify-between rounded-2xl border p-4"
              style={{ background: "rgba(17,24,39,0.8)", borderColor: "rgba(255,255,255,0.06)" }}>
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl flex items-center justify-center text-sm font-bold text-white flex-shrink-0"
                  style={{ background: "linear-gradient(135deg, #0054A6 0%, #00B0F0 100%)" }}>
                  {u.nom.charAt(0)}
                </div>
                <div>
                  <p className="text-sm font-medium text-white">{u.nom}</p>
                  <p className="text-xs text-gray-500">{u.email}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className={cn("text-xs font-semibold px-2.5 py-1 rounded-full border capitalize", ROLE_CONFIG[u.role])}>
                  {u.role.replace(/_/g, " ")}
                </span>
                <span className="text-xs text-gray-600">{new Date(u.created_at).toLocaleDateString("fr-FR")}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
