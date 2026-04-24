import { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  RefreshCw, Check, X, Upload, FileText, AlertTriangle, Clock, Zap, Search,
} from "lucide-react";
import toast from "react-hot-toast";
import { Button, Card, Badge, Spinner } from "@/components/ui";
import { adminPaiementsApi } from "@/api/client";
import { useAuthStore } from "@/store";

interface Commande {
  id: number;
  reference: string;
  user_id: number;
  user?: { email?: string; nom?: string; username?: string };
  type: string;
  plan_ou_pack: string;
  montant_fcfa: number;
  operateur?: string;
  numero_destinataire?: string;
  numero_expediteur?: string;
  tx_id?: string;
  statut: string;
  motif_rejet?: string;
  cree_le: string;
  deadline: string;
  en_retard?: boolean;
  match_source?: string;
  valide_le?: string;
}

export const AdminPaiementsPage = () => {
  const { user } = useAuthStore();
  const navigate = useNavigate();
  const [commandes, setCommandes] = useState<Commande[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"pending" | "all">("pending");
  const [uploadLoading, setUploadLoading] = useState(false);
  const [dernierResult, setDernierResult] = useState<any>(null);
  const [filterQ, setFilterQ] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (user && !["admin", "super_admin", "yukpo_owner"].includes(user.role)) {
      toast.error("Accès réservé aux administrateurs");
      navigate("/dashboard");
    }
  }, [user, navigate]);

  const charger = async () => {
    setLoading(true);
    try {
      const res = tab === "pending" ? await adminPaiementsApi.pending() : await adminPaiementsApi.all();
      setCommandes(res.commandes || []);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Erreur chargement");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { charger(); }, [tab]);

  const valider = async (id: number) => {
    if (!confirm("Confirmer la validation du paiement ?")) return;
    try {
      await adminPaiementsApi.valider(id);
      toast.success("Paiement validé");
      charger();
    } catch (e: any) { toast.error(e?.response?.data?.detail || "Erreur"); }
  };

  const rejeter = async (id: number) => {
    const motif = prompt("Motif de rejet (obligatoire, min 3 caractères) :");
    if (!motif || motif.length < 3) return;
    try {
      await adminPaiementsApi.rejeter(id, motif);
      toast.success("Paiement rejeté (rollback effectué)");
      charger();
    } catch (e: any) { toast.error(e?.response?.data?.detail || "Erreur"); }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadLoading(true);
    try {
      const res = await adminPaiementsApi.uploadReleve(file);
      setDernierResult(res);
      toast.success(`${res.matches?.length || 0} paiement(s) auto-validé(s)`);
      charger();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Erreur upload");
    } finally {
      setUploadLoading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const lancerCron = async () => {
    try {
      const res = await adminPaiementsApi.cronAutoAnnulation();
      toast.success(`${res.annulees} commande(s) annulée(s)`);
      charger();
    } catch (e: any) { toast.error(e?.response?.data?.detail || "Erreur"); }
  };

  const filtered = commandes.filter((c) => {
    const q = filterQ.toLowerCase();
    return !q
      || c.reference.toLowerCase().includes(q)
      || (c.user?.email || "").toLowerCase().includes(q)
      || (c.numero_expediteur || "").includes(q)
      || String(c.montant_fcfa).includes(q);
  });

  const badgeStatut = (s: string) => {
    const map: Record<string, any> = {
      attente: "secondary", provisoire: "purple", valide: "success", rejete: "danger", annule: "secondary",
    };
    return <Badge variant={map[s] || "secondary"}>{s}</Badge>;
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-display font-bold text-white">Paiements MoMo — Admin</h1>
          <p className="text-slate-400 text-sm mt-1">
            Validation manuelle + auto-match IA depuis relevé. Activation provisoire 3h → annulation auto si non confirmée.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" icon={<RefreshCw className="w-3 h-3" />} onClick={charger}>Actualiser</Button>
          <Button variant="ghost" size="sm" icon={<Clock className="w-3 h-3" />} onClick={lancerCron}>Lancer CRON</Button>
        </div>
      </div>

      {/* Upload relevé */}
      <Card className="p-5 border-yukpo-500/30 bg-yukpo-500/5">
        <div className="flex items-start gap-4 flex-wrap">
          <div className="flex-1 min-w-[200px]">
            <h2 className="text-white font-semibold flex items-center gap-2">
              <Upload className="w-4 h-4 text-yukpo-400" /> Upload relevé MoMo
            </h2>
            <p className="text-slate-400 text-sm mt-1">
              PDF / image / CSV / Excel — IA extrait les paiements et auto-valide les commandes matchées (même montant + 4 derniers digits tel).
            </p>
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,.webp,.csv,.txt,.xlsx,.xls"
            onChange={handleUpload}
            className="hidden"
          />
          <Button variant="primary" loading={uploadLoading} onClick={() => fileRef.current?.click()}>
            <FileText className="w-4 h-4" /> Choisir un fichier
          </Button>
        </div>

        {dernierResult && (
          <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
            <div className="bg-green-500/10 border border-green-500/30 rounded-xl p-3">
              <p className="text-green-300 font-semibold">{dernierResult.matches?.length || 0} match(s)</p>
              <p className="text-slate-400 text-xs mt-1">Auto-validés</p>
            </div>
            <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-3">
              <p className="text-amber-300 font-semibold">{dernierResult.non_matches?.length || 0} non matché(s)</p>
              <p className="text-slate-400 text-xs mt-1">À vérifier manuellement</p>
            </div>
            <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-3">
              <p className="text-white font-semibold">{dernierResult.total_lignes || 0} ligne(s)</p>
              <p className="text-slate-400 text-xs mt-1">Extraites du relevé</p>
            </div>
          </div>
        )}
      </Card>

      {/* Tabs + recherche */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex gap-2">
          <button
            onClick={() => setTab("pending")}
            className={`px-4 py-2 rounded-xl text-sm font-medium ${tab === "pending" ? "bg-yukpo-500 text-white" : "text-slate-400 hover:text-white"}`}
          >
            En attente / provisoires
          </button>
          <button
            onClick={() => setTab("all")}
            className={`px-4 py-2 rounded-xl text-sm font-medium ${tab === "all" ? "bg-yukpo-500 text-white" : "text-slate-400 hover:text-white"}`}
          >
            Toutes (90j)
          </button>
        </div>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input
            type="text"
            placeholder="Rechercher (réf, email, tel, montant)..."
            value={filterQ}
            onChange={(e) => setFilterQ(e.target.value)}
            className="pl-10 pr-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white text-sm w-72"
          />
        </div>
      </div>

      {/* Liste commandes */}
      {loading ? (
        <div className="flex justify-center py-12"><Spinner size="lg" /></div>
      ) : filtered.length === 0 ? (
        <Card className="p-10 text-center text-slate-400">Aucune commande.</Card>
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-800/50 text-slate-400 text-xs uppercase tracking-wide">
                <tr>
                  <th className="px-4 py-3 text-left">Référence</th>
                  <th className="px-4 py-3 text-left">Utilisateur</th>
                  <th className="px-4 py-3 text-left">Type / Plan</th>
                  <th className="px-4 py-3 text-right">Montant</th>
                  <th className="px-4 py-3 text-left">Tel expéditeur</th>
                  <th className="px-4 py-3 text-left">Statut</th>
                  <th className="px-4 py-3 text-left">Deadline</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((c) => (
                  <tr key={c.id} className="border-t border-slate-800 hover:bg-slate-800/30">
                    <td className="px-4 py-3">
                      <code className="text-yukpo-300 text-xs">{c.reference}</code>
                      {c.tx_id && <p className="text-slate-500 text-xs mt-0.5">TX: {c.tx_id}</p>}
                    </td>
                    <td className="px-4 py-3">
                      <p className="text-white">{c.user?.nom || c.user?.username || `User #${c.user_id}`}</p>
                      <p className="text-slate-500 text-xs">{c.user?.email}</p>
                    </td>
                    <td className="px-4 py-3">
                      <p className="text-white capitalize">{c.plan_ou_pack}</p>
                      <p className="text-slate-500 text-xs">{c.type} · {c.operateur}</p>
                    </td>
                    <td className="px-4 py-3 text-right text-gold-400 font-semibold">
                      {c.montant_fcfa.toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-slate-300">{c.numero_expediteur || <span className="text-slate-600">—</span>}</td>
                    <td className="px-4 py-3">
                      {badgeStatut(c.statut)}
                      {c.match_source && <p className="text-slate-500 text-xs mt-0.5">{c.match_source}</p>}
                    </td>
                    <td className="px-4 py-3 text-xs">
                      <p className={c.en_retard ? "text-red-400 font-semibold" : "text-slate-400"}>
                        {c.en_retard ? <><AlertTriangle className="w-3 h-3 inline" /> Dépassée</> : new Date(c.deadline).toLocaleString("fr-FR")}
                      </p>
                      <p className="text-slate-600">Créée : {new Date(c.cree_le).toLocaleString("fr-FR")}</p>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {(c.statut === "attente" || c.statut === "provisoire") && (
                        <div className="flex gap-1 justify-end">
                          <button onClick={() => valider(c.id)} className="p-1.5 rounded-lg bg-green-500/20 text-green-400 hover:bg-green-500/30" title="Valider">
                            <Check className="w-4 h-4" />
                          </button>
                          <button onClick={() => rejeter(c.id)} className="p-1.5 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30" title="Rejeter">
                            <X className="w-4 h-4" />
                          </button>
                        </div>
                      )}
                      {c.motif_rejet && <p className="text-xs text-red-400 mt-1">{c.motif_rejet}</p>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
};
