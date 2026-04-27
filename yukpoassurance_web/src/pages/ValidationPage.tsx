import { useEffect, useState } from "react";
import { CheckCircle, XCircle, Clock, AlertTriangle, Check, X } from "lucide-react";
import { cn, formatMontant } from "@/components/ui";
import { validationsApi } from "@/api/client";
import type { ValidationItem } from "@/types";
import toast from "react-hot-toast";

const DEMO_VALIDATIONS: ValidationItem[] = [
  { id: "1", type: "sinistre", description: "Règlement SIN-2026-018 — Kouassi Jean-Baptiste · RC Auto", montant: 2_500_000, reference: "SIN-2026-018", agent: "Agent Sinistres", statut: "pending", created_at: "2026-04-21T14:30:00Z" },
  { id: "2", type: "ecriture_comptable_sinistre", description: "Écriture comptable — débit 6141 / crédit 3941 — SIN-2026-016", montant: 850_000, reference: "SIN-2026-016", agent: "Agent Comptabilité", statut: "pending", created_at: "2026-04-21T11:15:00Z" },
  { id: "3", type: "expertise_sinistre", description: "Mission expertise automobile — Expert Coulibaly Paul · SIN-2026-020", reference: "SIN-2026-020", agent: "Agent Sinistres", statut: "pending", created_at: "2026-04-22T09:00:00Z" },
  { id: "4", type: "souscription", description: "Émission police RC Auto — Traoré Aminata · Véhicule LT-4521-A", montant: 185_000, reference: "POL-2026-142", agent: "Agent Souscription", statut: "approved", created_at: "2026-04-20T16:45:00Z" },
  { id: "5", type: "sinistre", description: "Règlement SIN-2026-011 — Bamba Seydou · Score fraude 82 — REJET", reference: "SIN-2026-011", agent: "Agent Sinistres", statut: "rejected", created_at: "2026-04-19T10:00:00Z" },
];

type Filtre = "tous" | "pending" | "approved" | "rejected";

const FILTRE_LABELS: Record<Filtre, string> = {
  tous: "Tous", pending: "En attente", approved: "Approuvés", rejected: "Rejetés",
};

const TYPE_CONFIG: Record<string, { label: string; color: string }> = {
  sinistre:                    { label: "Sinistre",       color: "text-ciel-400 bg-assurance-500/10 border-assurance-500/20" },
  ecriture_comptable_sinistre: { label: "Comptabilité",   color: "text-purple-400 bg-purple-500/10 border-purple-500/20" },
  expertise_sinistre:          { label: "Expertise",      color: "text-alerte-400 bg-alerte-500/10 border-alerte-500/20" },
  souscription:                { label: "Souscription",   color: "text-green-400 bg-green-500/10 border-green-500/20" },
  archivage_sinistre:          { label: "Archivage",      color: "text-gray-400 bg-gray-500/10 border-gray-500/20" },
  transmission_cheque:         { label: "Paiement",       color: "text-yellow-400 bg-yellow-500/10 border-yellow-500/20" },
};

export function ValidationPage() {
  const [items, setItems]     = useState<ValidationItem[]>(DEMO_VALIDATIONS);
  const [filtre, setFiltre]   = useState<Filtre>("tous");
  const [processing, setProcessing] = useState<string | null>(null);

  useEffect(() => {
    validationsApi.list()
      .then((res) => setItems(res.data as ValidationItem[]))
      .catch(() => {});
  }, []);

  const filtered = filtre === "tous" ? items : items.filter((i) => i.statut === filtre);

  const stats = {
    pending:  items.filter((i) => i.statut === "pending").length,
    approved: items.filter((i) => i.statut === "approved").length,
    rejected: items.filter((i) => i.statut === "rejected").length,
  };

  const handleApprouver = async (id: string) => {
    setProcessing(id);
    try {
      await validationsApi.approuver(id);
      setItems((prev) => prev.map((i) => i.id === id ? { ...i, statut: "approved" } : i));
      toast.success("Validé avec succès.");
    } catch {
      setItems((prev) => prev.map((i) => i.id === id ? { ...i, statut: "approved" } : i));
      toast.success("Validé (mode démo).");
    } finally {
      setProcessing(null);
    }
  };

  const handleRejeter = async (id: string) => {
    setProcessing(id);
    try {
      await validationsApi.rejeter(id, "Rejet manuel");
      setItems((prev) => prev.map((i) => i.id === id ? { ...i, statut: "rejected" } : i));
      toast.error("Rejeté.");
    } catch {
      setItems((prev) => prev.map((i) => i.id === id ? { ...i, statut: "rejected" } : i));
    } finally {
      setProcessing(null);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="px-8 pt-8 pb-4">
        <h1 className="text-2xl font-bold text-white" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
          File de validation
        </h1>
        <p className="text-sm text-gray-400 mt-0.5">Approbation obligatoire avant tout acte engageant la compagnie</p>
      </div>

      {/* Stats */}
      <div className="px-8 flex gap-4 mb-6">
        {([["pending", Clock, "text-alerte-400", "Attente"], ["approved", CheckCircle, "text-green-400", "Approuvés"], ["rejected", XCircle, "text-red-400", "Rejetés"]] as const).map(
          ([key, Icon, color, label]) => (
            <div key={key} className="flex items-center gap-3 rounded-xl border px-4 py-3"
              style={{ background: "rgba(17,24,39,0.8)", borderColor: "rgba(255,255,255,0.06)" }}>
              <Icon className={cn("w-5 h-5", color)} />
              <div>
                <p className="text-xl font-bold text-white">{stats[key]}</p>
                <p className="text-xs text-gray-500">{label}</p>
              </div>
            </div>
          )
        )}
      </div>

      {/* Filtres */}
      <div className="px-8 flex gap-2 mb-4">
        {(Object.keys(FILTRE_LABELS) as Filtre[]).map((f) => (
          <button key={f} onClick={() => setFiltre(f)}
            className={cn(
              "px-4 py-1.5 rounded-full text-sm font-medium transition-all border",
              filtre === f
                ? "text-white border-assurance-500/40 bg-assurance-500/15"
                : "text-gray-400 border-white/[0.06] hover:text-gray-200 hover:bg-white/[0.04]"
            )}>
            {FILTRE_LABELS[f]}
            {f === "pending" && stats.pending > 0 && (
              <span className="ml-1.5 text-xs bg-alerte-500 text-white rounded-full px-1.5 py-0.5">{stats.pending}</span>
            )}
          </button>
        ))}
      </div>

      {/* Liste */}
      <div className="px-8 space-y-3 pb-8">
        {filtered.length === 0 && (
          <p className="text-center text-gray-500 py-12 text-sm">Aucune validation dans cette catégorie.</p>
        )}
        {filtered.map((item) => {
          const typeInfo = TYPE_CONFIG[item.type] || { label: item.type, color: "text-gray-400 bg-gray-500/10 border-gray-500/20" };
          return (
            <div key={item.id} className={cn(
              "rounded-2xl border p-5 transition-all",
              item.statut === "pending" ? "border-alerte-500/20" : "border-white/[0.06]"
            )} style={{ background: "rgba(17,24,39,0.8)" }}>
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                    <span className={cn("text-xs font-semibold px-2.5 py-0.5 rounded-full border", typeInfo.color)}>
                      {typeInfo.label}
                    </span>
                    {item.reference && (
                      <span className="text-xs text-gray-500 font-mono">{item.reference}</span>
                    )}
                    {item.statut === "approved" && <span className="text-xs text-green-400 flex items-center gap-1"><CheckCircle className="w-3 h-3" />Approuvé</span>}
                    {item.statut === "rejected" && <span className="text-xs text-red-400 flex items-center gap-1"><XCircle className="w-3 h-3" />Rejeté</span>}
                    {item.statut === "pending" && <span className="text-xs text-alerte-400 flex items-center gap-1"><AlertTriangle className="w-3 h-3" />En attente</span>}
                  </div>
                  <p className="text-sm text-gray-200 mb-1">{item.description}</p>
                  <div className="flex items-center gap-3 text-xs text-gray-500">
                    {item.montant && <span className="font-medium text-white">{formatMontant(item.montant)}</span>}
                    {item.agent && <span>via {item.agent}</span>}
                    <span>{new Date(item.created_at).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })}</span>
                  </div>
                </div>

                {item.statut === "pending" && (
                  <div className="flex gap-2 flex-shrink-0">
                    <button
                      onClick={() => handleRejeter(item.id)}
                      disabled={processing === item.id}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium text-red-400 border border-red-500/20 hover:bg-red-500/10 transition-all disabled:opacity-50"
                    >
                      <X className="w-3.5 h-3.5" />Rejeter
                    </button>
                    <button
                      onClick={() => handleApprouver(item.id)}
                      disabled={processing === item.id}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold text-white border border-assurance-500/30 hover:brightness-110 transition-all disabled:opacity-50"
                      style={{ background: "linear-gradient(135deg, #0054A6 0%, #00B0F0 100%)" }}
                    >
                      <Check className="w-3.5 h-3.5" />Valider
                    </button>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
