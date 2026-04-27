import { useState, useEffect } from "react";
import {
  Plus, Search, ShieldCheck, Car, Heart, Home, Truck, Briefcase,
  AlertTriangle, ChevronRight, X, Camera, Upload, FileText,
  CheckCircle, Clock, Scale, RefreshCw,
} from "lucide-react";
import { cn, formatMontant } from "@/components/ui";
import { sinistresApi } from "@/api/client";
import type { Sinistre, EtapeWorkflow } from "@/types";
import toast from "react-hot-toast";

// ── Config ────────────────────────────────────────────────────────────────────

const STATUT_CONFIG: Record<string, { label: string; classes: string }> = {
  ouvert:             { label: "Ouvert",      classes: "bg-blue-500/10 text-blue-400 border-blue-500/20" },
  en_cours:           { label: "En cours",    classes: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20" },
  expertise_en_cours: { label: "Expertise",   classes: "bg-purple-500/10 text-purple-400 border-purple-500/20" },
  relance:            { label: "Relancé",     classes: "bg-alerte-500/10 text-alerte-400 border-alerte-500/20" },
  contentieux:        { label: "Contentieux", classes: "bg-red-500/10 text-red-400 border-red-500/20" },
  accord:             { label: "Accord",      classes: "bg-teal-500/10 text-teal-400 border-teal-500/20" },
  clos:               { label: "Clôturé",     classes: "bg-green-500/10 text-green-400 border-green-500/20" },
  rejet:              { label: "Rejeté",      classes: "bg-red-500/10 text-red-400 border-red-500/20" },
};

const BRANCHE_CONFIG: Record<string, { icon: React.ComponentType<{ className?: string }>; color: string; label: string }> = {
  auto:      { icon: Car,       color: "text-blue-400",   label: "RC Auto" },
  vie:       { icon: Heart,     color: "text-rose-400",   label: "Vie" },
  sante:     { icon: Heart,     color: "text-emerald-400",label: "Santé" },
  mrh:       { icon: Home,      color: "text-orange-400", label: "MRH" },
  transport: { icon: Truck,     color: "text-cyan-400",   label: "Transport" },
  rc:        { icon: Briefcase, color: "text-purple-400", label: "RC Générale" },
};

const ETAPES_LABELS = [
  "Ouverture", "Accusé réception", "Mise en cause", "Relances",
  "Réclamation pièces", "Mission expert/avocat", "Bons prise en charge",
  "Préavis saisine", "Requête unilatérale", "Étude rapport expertise",
  "Identification victimes", "Notes techniques", "Offre indemnisation",
  "Accord règlement", "PV transaction", "Quittances", "Transmission chèques", "Révisions",
];

// ── Démo ──────────────────────────────────────────────────────────────────────

const DEMO: Sinistre[] = [
  {
    id: "1", numero: "SIN-2026-018", branche: "auto", statut: "en_cours",
    date_sinistre: "2026-03-15", date_declaration: "2026-03-16",
    montant_estime: 2_500_000, montant_regle: 0,
    assure_nom: "Kouassi Jean-Baptiste", description: "Collision carrefour Akwa — constat amiable",
    score_fraude: 12, police_numero: "POL-AUTO-001",
    etapes_workflow: [
      { id: "ouverture",         label: "Ouverture",           statut: "fait",     date: "16/03/2026" },
      { id: "accuse_reception",  label: "Accusé réception",    statut: "fait",     date: "16/03/2026" },
      { id: "mise_en_cause",     label: "Mise en cause",       statut: "fait",     date: "18/03/2026" },
      { id: "relances",          label: "Relances",            statut: "fait",     date: "25/03/2026" },
      { id: "reclamation_pieces",label: "Réclamation pièces",  statut: "fait",     date: "18/03/2026" },
      { id: "mission_expert",    label: "Mission expert",      statut: "en_cours", date: "01/04/2026" },
    ],
  },
  {
    id: "2", numero: "SIN-2026-015", branche: "vie", statut: "ouvert",
    date_sinistre: "2026-03-01", date_declaration: "2026-03-03",
    montant_estime: 25_000_000,
    assure_nom: "Traoré Aminata", description: "Décès assuré — capital vie bénéficiaires",
    score_fraude: 3, police_numero: "POL-VIE-042",
    etapes_workflow: [
      { id: "ouverture",        label: "Ouverture",        statut: "fait", date: "03/03/2026" },
      { id: "accuse_reception", label: "Accusé réception", statut: "fait", date: "03/03/2026" },
    ],
  },
  {
    id: "3", numero: "SIN-2026-009", branche: "sante", statut: "clos",
    date_sinistre: "2026-02-10", date_declaration: "2026-02-11",
    montant_estime: 850_000, montant_regle: 720_000,
    assure_nom: "Diallo Moussa", description: "Hospitalisation 5 jours — factures validées",
    score_fraude: 5, police_numero: "POL-SANTE-088",
  },
  {
    id: "4", numero: "SIN-2026-011", branche: "auto", statut: "rejet",
    date_sinistre: "2026-03-10", date_declaration: "2026-03-15",
    montant_estime: 12_000_000,
    assure_nom: "Bamba Seydou", description: "Véhicule incendié — suspicion fraude (score 82)",
    score_fraude: 82, police_numero: "POL-AUTO-031",
  },
];

// ── Composants ────────────────────────────────────────────────────────────────

function ScoreFraude({ score }: { score?: number }) {
  if (score == null) return null;
  const [color, label] = score < 30 ? ["text-green-400", "Faible"] : score < 60 ? ["text-yellow-400", "Moyen"] : ["text-red-400", "Élevé"];
  return <span className={cn("text-xs font-semibold", color)}>Fraude {label} ({score})</span>;
}

function WorkflowTimeline({ etapes }: { etapes?: EtapeWorkflow[] }) {
  const resolved = ETAPES_LABELS.map((label, i) => {
    const id = label.toLowerCase().replace(/\s+/g, "_");
    const found = etapes?.find((e) => e.id === id || e.label === label);
    if (found) return found;
    return { id, label, statut: "en_attente" as const };
  });

  return (
    <div className="space-y-1">
      {resolved.map((e, i) => (
        <div key={e.id || i} className="flex items-start gap-3">
          <div className="flex flex-col items-center mt-1">
            <div className={cn(
              "w-2.5 h-2.5 rounded-full flex-shrink-0",
              e.statut === "fait" ? "bg-green-500" :
              e.statut === "en_cours" ? "bg-yellow-400 animate-pulse" : "bg-gray-700"
            )} />
            {i < resolved.length - 1 && <div className="w-px flex-1 bg-gray-800 mt-1" style={{ minHeight: 14 }} />}
          </div>
          <div className="pb-2 min-w-0">
            <p className={cn("text-xs leading-tight",
              e.statut === "fait" ? "text-gray-300 font-medium" :
              e.statut === "en_cours" ? "text-yellow-400 font-semibold" : "text-gray-600"
            )}>
              {i + 1}. {e.label}
            </p>
            {e.date && <p className="text-[10px] text-gray-600 mt-0.5">{e.date}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}

function SinistreCard({ s, onClick }: { s: Sinistre; onClick: () => void }) {
  const statut  = STATUT_CONFIG[s.statut] || { label: s.statut, classes: "bg-gray-500/10 text-gray-400 border-gray-500/20" };
  const branche = BRANCHE_CONFIG[s.branche] || { icon: ShieldCheck, color: "text-gray-400", label: s.branche };
  const Icon    = branche.icon;

  return (
    <button onClick={onClick}
      className="w-full text-left rounded-2xl border p-4 hover:border-assurance-500/30 transition-all"
      style={{ background: "rgba(17,24,39,0.8)", borderColor: "rgba(255,255,255,0.06)" }}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
            style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)" }}>
            <Icon className={cn("w-4 h-4", branche.color)} />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-white truncate">{s.numero}</p>
            <p className="text-xs text-gray-500 truncate">{s.assure_nom}</p>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1 flex-shrink-0">
          <span className={cn("text-xs font-medium px-2 py-0.5 rounded-full border", statut.classes)}>
            {statut.label}
          </span>
          <span className="text-xs text-gray-600">{new Date(s.date_sinistre).toLocaleDateString("fr-FR")}</span>
        </div>
      </div>
      <div className="mt-3 flex items-center justify-between">
        <p className="text-xs text-gray-500 line-clamp-1 flex-1 mr-2">{s.description}</p>
        <div className="flex items-center gap-3 flex-shrink-0">
          <span className="text-xs font-medium text-gray-300">{formatMontant(s.montant_estime)}</span>
          <ScoreFraude score={s.score_fraude} />
          <ChevronRight className="w-3 h-3 text-gray-600" />
        </div>
      </div>
    </button>
  );
}

function SinistreDetail({ s, onClose }: { s: Sinistre; onClose: () => void }) {
  const statut  = STATUT_CONFIG[s.statut] || { label: s.statut, classes: "bg-gray-500/10 text-gray-400 border-gray-500/20" };
  const branche = BRANCHE_CONFIG[s.branche] || { icon: ShieldCheck, color: "text-gray-400", label: s.branche };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: "rgba(0,0,0,0.7)", backdropFilter: "blur(4px)" }}>
      <div className="bg-gray-900 rounded-2xl border border-white/[0.08] max-w-lg w-full max-h-[90vh] overflow-y-auto shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-white/[0.06]">
          <div>
            <h3 className="text-lg font-bold text-white">{s.numero}</h3>
            <p className="text-sm text-gray-500">{s.assure_nom} · {s.police_numero}</p>
          </div>
          <button onClick={onClose} className="p-1.5 text-gray-500 hover:text-gray-200 rounded-lg hover:bg-white/[0.05]">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-5">
          {/* Infos grille */}
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div><p className="text-xs text-gray-500 mb-1">Statut</p>
              <span className={cn("text-xs font-medium px-2 py-0.5 rounded-full border", statut.classes)}>{statut.label}</span>
            </div>
            <div><p className="text-xs text-gray-500 mb-1">Branche</p>
              <span className="text-sm font-medium text-white">{branche.label}</span>
            </div>
            <div><p className="text-xs text-gray-500 mb-1">Date sinistre</p>
              <span className="text-sm font-medium text-white">{new Date(s.date_sinistre).toLocaleDateString("fr-FR", { dateStyle: "long" })}</span>
            </div>
            <div><p className="text-xs text-gray-500 mb-1">Montant estimé</p>
              <span className="text-sm font-medium text-white">{formatMontant(s.montant_estime)}</span>
            </div>
            {s.montant_regle != null && s.montant_regle > 0 && (
              <div><p className="text-xs text-gray-500 mb-1">Montant réglé</p>
                <span className="text-sm font-medium text-green-400">{formatMontant(s.montant_regle)}</span>
              </div>
            )}
            <div><p className="text-xs text-gray-500 mb-1">Score fraude</p>
              <ScoreFraude score={s.score_fraude} />
            </div>
          </div>

          <div>
            <p className="text-xs text-gray-500 mb-1.5">Description</p>
            <p className="text-sm text-gray-300 bg-white/[0.03] rounded-xl p-3 border border-white/[0.04]">{s.description}</p>
          </div>

          {/* Imputation comptable */}
          <div className="rounded-xl border border-assurance-500/20 p-4 text-xs space-y-1.5" style={{ background: "rgba(0,84,166,0.08)" }}>
            <p className="text-ciel-400 font-semibold mb-2">Imputation comptable OHADA</p>
            <div className="flex justify-between text-gray-300">
              <span>Charge sinistre :</span>
              <span className="font-mono">6141 — Sinistres {branche.label}</span>
            </div>
            <div className="flex justify-between text-gray-300">
              <span>Provision PSAP :</span>
              <span className="font-mono">3941 — PSAP {branche.label}</span>
            </div>
          </div>

          {/* Workflow timeline */}
          <div className="rounded-xl border border-white/[0.06] p-4" style={{ background: "rgba(255,255,255,0.02)" }}>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">Suivi étapes règlement</p>
            <WorkflowTimeline etapes={s.etapes_workflow} />
          </div>

          {/* Actions */}
          {s.statut === "ouvert" && (
            <div className="flex gap-2">
              <button className="flex-1 py-2 rounded-xl text-sm font-semibold text-white hover:brightness-110 transition-all"
                style={{ background: "linear-gradient(135deg, #0054A6 0%, #00B0F0 100%)" }}>
                Instruire
              </button>
              <button className="flex-1 py-2 rounded-xl text-sm font-medium text-gray-300 border border-white/[0.08] hover:bg-white/[0.05] transition-all">
                Expertise
              </button>
            </div>
          )}
          {s.statut === "en_cours" && (
            <div className="flex gap-2">
              <button className="flex-1 py-2 rounded-xl text-sm font-semibold text-white bg-green-600 hover:bg-green-500 transition-all">
                Clôturer & Régler
              </button>
              <button className="flex-1 py-2 rounded-xl text-sm font-medium text-red-400 border border-red-500/20 hover:bg-red-500/10 transition-all">
                Rejeter
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function SinistresPage() {
  const [sinistres, setSinistres] = useState<Sinistre[]>(DEMO);
  const [search, setSearch]       = useState("");
  const [selected, setSelected]   = useState<Sinistre | null>(null);
  const [showNew, setShowNew]      = useState(false);

  useEffect(() => {
    sinistresApi.list().then((res) => setSinistres(res.data as Sinistre[])).catch(() => {});
  }, []);

  const filtered = sinistres.filter((s) =>
    s.numero.toLowerCase().includes(search.toLowerCase()) ||
    s.assure_nom.toLowerCase().includes(search.toLowerCase())
  );

  const stats = {
    ouverts:    sinistres.filter((s) => ["ouvert", "en_cours", "expertise_en_cours"].includes(s.statut)).length,
    souffrance: sinistres.filter((s) => s.statut === "relance" || s.statut === "contentieux").length,
    clos:       sinistres.filter((s) => s.statut === "clos").length,
  };

  return (
    <div className="flex-1 overflow-y-auto">
      {/* Header */}
      <div className="px-8 pt-8 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
            Sinistres
          </h1>
          <p className="text-sm text-gray-400 mt-0.5">Instruction · Règlement · Suivi CIMA</p>
        </div>
        <button onClick={() => setShowNew(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold text-white hover:brightness-110 transition-all"
          style={{ background: "linear-gradient(135deg, #0054A6 0%, #00B0F0 100%)" }}>
          <Plus className="w-4 h-4" />
          Nouveau sinistre
        </button>
      </div>

      {/* Stats */}
      <div className="px-8 flex gap-4 mb-6">
        {[
          { icon: Clock, label: "En cours", val: stats.ouverts, color: "text-ciel-400" },
          { icon: AlertTriangle, label: "Souffrance", val: stats.souffrance, color: "text-alerte-400" },
          { icon: CheckCircle, label: "Clôturés", val: stats.clos, color: "text-green-400" },
        ].map(({ icon: Icon, label, val, color }) => (
          <div key={label} className="flex items-center gap-3 rounded-xl border px-4 py-3"
            style={{ background: "rgba(17,24,39,0.8)", borderColor: "rgba(255,255,255,0.06)" }}>
            <Icon className={cn("w-5 h-5", color)} />
            <div>
              <p className="text-xl font-bold text-white">{val}</p>
              <p className="text-xs text-gray-500">{label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Recherche */}
      <div className="px-8 mb-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
          <input
            className="w-full max-w-sm bg-white/[0.04] border border-white/[0.06] rounded-xl pl-9 pr-4 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-assurance-500/40 transition-all"
            placeholder="Rechercher un sinistre ou assuré…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {/* Liste */}
      <div className="px-8 space-y-3 pb-8">
        {filtered.map((s) => (
          <SinistreCard key={s.id} s={s} onClick={() => setSelected(s)} />
        ))}
        {filtered.length === 0 && (
          <p className="text-center text-gray-500 text-sm py-12">Aucun sinistre trouvé.</p>
        )}
      </div>

      {/* Detail modal */}
      {selected && <SinistreDetail s={selected} onClose={() => setSelected(null)} />}

      {/* Modale déclaration (renvoi vers ChatPage) */}
      {showNew && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: "rgba(0,0,0,0.7)" }}>
          <div className="bg-gray-900 rounded-2xl border border-white/[0.08] p-8 max-w-sm w-full text-center shadow-2xl">
            <ShieldCheck className="w-12 h-12 mx-auto mb-4" style={{ color: "#00B0F0" }} />
            <h3 className="text-lg font-bold text-white mb-2">Déclarer un sinistre</h3>
            <p className="text-sm text-gray-400 mb-6">
              La déclaration se fait via YukpoPro — les informations du document sont extraites automatiquement.
            </p>
            <div className="flex gap-3">
              <button onClick={() => setShowNew(false)}
                className="flex-1 py-2 rounded-xl text-sm text-gray-400 border border-white/[0.06] hover:bg-white/[0.04] transition-all">
                Annuler
              </button>
              <a href="/chat" className="flex-1 py-2 rounded-xl text-sm font-semibold text-white text-center hover:brightness-110 transition-all"
                style={{ background: "linear-gradient(135deg, #0054A6 0%, #00B0F0 100%)" }}>
                Aller à l'agent IA
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
