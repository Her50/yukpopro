import { useEffect, useState } from "react";
import { Users, BarChart3, Cpu, RefreshCw, Search, Shield, TrendingUp, FileText } from "lucide-react";
import { Button, Card, Badge, Spinner } from "@/components/ui";
import { adminApi } from "@/api/client";
import { useAuthStore } from "@/store";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";

interface StatGlobale {
  nb_utilisateurs: number;
  nb_requetes_total: number;
  nb_documents_total: number;
  metiers_top: { metier: string; count: number }[];
  pays_top: { pays: string; count: number }[];
}

interface UtilisateurAdmin {
  user_id: number;
  metier: string;
  pays: string;
  niveau: string;
  secteur: string;
  points_xp: number;
  niveau_xp: string;
  stats_usage?: Record<string, number>;
}

const METIERS_DISPONIBLES = [
  "comptable", "DRH", "daf", "juriste", "banquier", "ingenieur",
  "directeur_commercial", "charge_projets_ong", "responsable_microfinance",
  "transitaire", "fiscaliste", "consultant", "entrepreneur", "professionnel",
];

export const AdminPage = () => {
  const { user } = useAuthStore();
  const navigate = useNavigate();

  const [stats, setStats] = useState<StatGlobale | null>(null);
  const [utilisateurs, setUtilisateurs] = useState<UtilisateurAdmin[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [editingUser, setEditingUser] = useState<number | null>(null);
  const [newMetier, setNewMetier] = useState("");

  // Vérification rôle admin
  useEffect(() => {
    if (user && !["admin", "super_admin", "yukpo_owner"].includes(user.role)) {
      navigate("/dashboard");
      toast.error("Accès réservé aux administrateurs");
    }
  }, [user]);

  const charger = async () => {
    setLoading(true);
    try {
      const [s, u] = await Promise.allSettled([adminApi.stats(), adminApi.utilisateurs()]);
      if (s.status === "fulfilled") setStats(s.value);
      if (u.status === "fulfilled") setUtilisateurs(u.value.utilisateurs || []);
    } catch (_) {
      toast.error("Erreur de chargement");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { charger(); }, []);

  const handleChangerMetier = async (userId: number) => {
    if (!newMetier) return;
    try {
      await adminApi.changerMetier(userId, newMetier);
      toast.success("Métier mis à jour");
      setEditingUser(null);
      setNewMetier("");
      charger();
    } catch (_) {
      toast.error("Erreur lors de la mise à jour");
    }
  };

  const utilisateursFiltres = utilisateurs.filter((u) =>
    !search ||
    u.metier?.toLowerCase().includes(search.toLowerCase()) ||
    u.pays?.toLowerCase().includes(search.toLowerCase())
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-red-500/20 flex items-center justify-center">
            <Shield className="w-5 h-5 text-red-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white">Administration</h1>
            <p className="text-slate-400 text-sm">Tableau de bord admin YukpoPro</p>
          </div>
        </div>
        <Button variant="ghost" size="sm" icon={<RefreshCw className="w-4 h-4" />} onClick={charger}>
          Actualiser
        </Button>
      </div>

      {/* Stats globales */}
      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { label: "Utilisateurs", value: stats.nb_utilisateurs, icon: Users, color: "text-yukpo-400" },
            { label: "Requêtes IA", value: stats.nb_requetes_total, icon: Cpu, color: "text-accent-400" },
            { label: "Documents", value: stats.nb_documents_total, icon: FileText, color: "text-gold-400" },
            { label: "Agents actifs", value: 11, icon: TrendingUp, color: "text-green-400" },
          ].map((s) => (
            <Card key={s.label} className="p-4">
              <div className="flex items-center gap-3 mb-2">
                <s.icon className={`w-5 h-5 ${s.color}`} />
                <span className="text-slate-400 text-sm">{s.label}</span>
              </div>
              <div className="text-2xl font-bold text-white">{s.value.toLocaleString()}</div>
            </Card>
          ))}
        </div>
      )}

      {/* Top métiers & pays */}
      {stats && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card className="p-5">
            <h3 className="text-white font-semibold mb-4 flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-yukpo-400" /> Top Métiers
            </h3>
            <div className="space-y-2">
              {stats.metiers_top.length === 0 && (
                <p className="text-slate-500 text-sm">Aucune donnée</p>
              )}
              {stats.metiers_top.map((m) => (
                <div key={m.metier} className="flex items-center justify-between">
                  <span className="text-slate-300 text-sm capitalize">{m.metier.replace(/_/g, " ")}</span>
                  <Badge variant="primary">{m.count}</Badge>
                </div>
              ))}
            </div>
          </Card>

          <Card className="p-5">
            <h3 className="text-white font-semibold mb-4 flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-accent-400" /> Top Pays
            </h3>
            <div className="space-y-2">
              {stats.pays_top.length === 0 && (
                <p className="text-slate-500 text-sm">Aucune donnée</p>
              )}
              {stats.pays_top.map((p) => (
                <div key={p.pays} className="flex items-center justify-between">
                  <span className="text-slate-300 text-sm">{p.pays}</span>
                  <Badge variant="accent">{p.count}</Badge>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {/* Liste utilisateurs */}
      <Card className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-white font-semibold flex items-center gap-2">
            <Users className="w-4 h-4 text-yukpo-400" />
            Utilisateurs ({utilisateursFiltres.length})
          </h3>
          <div className="relative">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Filtrer par métier, pays..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="bg-slate-900 border border-slate-700 rounded-lg pl-9 pr-4 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-yukpo-500 w-64"
            />
          </div>
        </div>

        {utilisateursFiltres.length === 0 ? (
          <p className="text-slate-500 text-sm text-center py-8">
            {utilisateurs.length === 0
              ? "Aucun utilisateur trouvé — le backend est peut-être en mode simulation"
              : "Aucun résultat pour cette recherche"}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-slate-400">
                  <th className="text-left py-2 pr-4">ID</th>
                  <th className="text-left py-2 pr-4">Métier</th>
                  <th className="text-left py-2 pr-4">Pays</th>
                  <th className="text-left py-2 pr-4">Niveau</th>
                  <th className="text-left py-2 pr-4">XP</th>
                  <th className="text-left py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {utilisateursFiltres.map((u) => (
                  <tr key={u.user_id} className="border-b border-slate-800 hover:bg-slate-800/40">
                    <td className="py-3 pr-4 text-slate-400">#{u.user_id}</td>
                    <td className="py-3 pr-4">
                      {editingUser === u.user_id ? (
                        <select
                          value={newMetier}
                          onChange={(e) => setNewMetier(e.target.value)}
                          className="bg-slate-900 border border-yukpo-500 rounded px-2 py-1 text-sm text-white"
                        >
                          <option value="">-- choisir --</option>
                          {METIERS_DISPONIBLES.map((m) => (
                            <option key={m} value={m}>{m.replace(/_/g, " ")}</option>
                          ))}
                        </select>
                      ) : (
                        <span className="text-white capitalize">{u.metier?.replace(/_/g, " ") || "—"}</span>
                      )}
                    </td>
                    <td className="py-3 pr-4 text-slate-300">{u.pays || "—"}</td>
                    <td className="py-3 pr-4">
                      <Badge variant={u.niveau === "expert" ? "gold" : "secondary"}>{u.niveau || "—"}</Badge>
                    </td>
                    <td className="py-3 pr-4 text-yukpo-400 font-medium">{u.points_xp || 0} XP</td>
                    <td className="py-3">
                      {editingUser === u.user_id ? (
                        <div className="flex gap-2">
                          <Button size="sm" variant="primary" onClick={() => handleChangerMetier(u.user_id)}>
                            Sauver
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => { setEditingUser(null); setNewMetier(""); }}>
                            Annuler
                          </Button>
                        </div>
                      ) : (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => { setEditingUser(u.user_id); setNewMetier(u.metier || ""); }}
                        >
                          Changer métier
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Info connexion admin */}
      <Card className="p-4 border-red-500/30 bg-red-500/5">
        <div className="flex items-start gap-3">
          <Shield className="w-5 h-5 text-red-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-red-400 font-semibold text-sm">Compte Administrateur</p>
            <p className="text-slate-400 text-sm mt-1">
              En tant qu'administrateur, vous avez accès à tous les agents IA (quelque soit votre métier configuré).
              Pour vous connecter : utilisez le nom d'utilisateur <code className="bg-slate-800 px-1 rounded">admin</code> avec le mot de passe <code className="bg-slate-800 px-1 rounded">Admin123!</code> ou <code className="bg-slate-800 px-1 rounded">yukpo2025</code>.
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
};
