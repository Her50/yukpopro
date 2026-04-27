import { useState } from "react";
import { Upload, BarChart3, FileText, ArrowLeftRight, Download, CheckCircle } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { cn, formatMontant } from "@/components/ui";

const DEMO_ECRITURES = [
  { date: "22/04/2026", journal: "SIN",  compte_d: "6141", libelle_d: "Sinistres RC Auto",    montant: 2_500_000, compte_c: "3941", libelle_c: "PSAP Auto",     reference: "SIN-2026-018" },
  { date: "22/04/2026", journal: "POL",  compte_d: "411",  libelle_d: "Clients",              montant: 185_000,  compte_c: "7001", libelle_c: "Primes RC Auto", reference: "POL-2026-142" },
  { date: "21/04/2026", journal: "SIN",  compte_d: "6144", libelle_d: "Sinistres Maladie",    montant: 720_000,  compte_c: "3944", libelle_c: "PSAP Maladie",   reference: "SIN-2026-009" },
  { date: "20/04/2026", journal: "RASS", compte_d: "652",  libelle_d: "Primes cédées",        montant: 48_000,   compte_c: "411",  libelle_c: "Réassureur XYZ", reference: "RASS-2026-Q1" },
];

const DEMO_CHART = [
  { mois: "Jan", primes: 38, sinistres: 22, frais: 8 },
  { mois: "Fév", primes: 42, sinistres: 25, frais: 9 },
  { mois: "Mar", primes: 45, sinistres: 28, frais: 10 },
  { mois: "Avr", primes: 48, sinistres: 30, frais: 11 },
];

type Onglet = "journal" | "analytique" | "rapprochement";

export function ComptabilitePage() {
  const [onglet, setOnglet]   = useState<Onglet>("journal");
  const [dragOver, setDragOver] = useState(false);
  const [fichierAnalyse, setFichierAnalyse] = useState<string | null>(null);

  const ONGLETS: { id: Onglet; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
    { id: "journal",       label: "Journal PCSA",    icon: FileText },
    { id: "analytique",    label: "Rapport analytique", icon: BarChart3 },
    { id: "rapprochement", label: "Rapprochement",   icon: ArrowLeftRight },
  ];

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="px-8 pt-8 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
            Comptabilité
          </h1>
          <p className="text-sm text-gray-400 mt-0.5">PCSA · OHADA · Analyse intelligente factures et relevés</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium text-gray-300 border border-white/[0.06] hover:bg-white/[0.05] transition-all">
          <Download className="w-4 h-4" />
          Exporter PCSA
        </button>
      </div>

      {/* Onglets */}
      <div className="px-8 flex gap-2 mb-6">
        {ONGLETS.map(({ id, label, icon: Icon }) => (
          <button key={id} onClick={() => setOnglet(id)}
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

      {/* Journal PCSA */}
      {onglet === "journal" && (
        <div className="px-8">
          {/* OCR Upload */}
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f) setFichierAnalyse(f.name); }}
            className={cn(
              "border-2 border-dashed rounded-2xl p-8 text-center mb-6 transition-all cursor-pointer",
              dragOver ? "border-assurance-500/60 bg-assurance-500/05" : "border-white/[0.08] hover:border-assurance-500/30"
            )}>
            <Upload className="w-8 h-8 mx-auto mb-3 text-gray-500" />
            <p className="text-sm font-medium text-gray-300">Glissez une facture, relevé bancaire ou bordereau</p>
            <p className="text-xs text-gray-600 mt-1">PDF, PNG, JPG — OCR + codification automatique YukpoPro</p>
            {fichierAnalyse && (
              <p className="mt-3 text-xs text-ciel-400 flex items-center justify-center gap-2">
                <CheckCircle className="w-3.5 h-3.5" />{fichierAnalyse} analysé
              </p>
            )}
          </div>

          {/* Table journal */}
          <div className="rounded-2xl border border-white/[0.06] overflow-hidden" style={{ background: "rgba(17,24,39,0.8)" }}>
            <div className="px-5 py-3 border-b border-white/[0.06] flex items-center justify-between">
              <p className="text-sm font-semibold text-white">Écritures comptables — Avril 2026</p>
              <span className="text-xs text-gray-500">{DEMO_ECRITURES.length} lignes</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-white/[0.04]">
                    {["Date", "Jnl", "Cpt Débit", "Libellé", "Cpt Crédit", "Libellé", "Montant", "Réf."].map((h) => (
                      <th key={h} className="text-left px-4 py-2.5 text-gray-500 font-medium">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {DEMO_ECRITURES.map((e, i) => (
                    <tr key={i} className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                      <td className="px-4 py-2.5 text-gray-400">{e.date}</td>
                      <td className="px-4 py-2.5"><span className="px-1.5 py-0.5 rounded text-ciel-400 bg-assurance-500/10 font-mono">{e.journal}</span></td>
                      <td className="px-4 py-2.5 font-mono text-gray-300">{e.compte_d}</td>
                      <td className="px-4 py-2.5 text-gray-400 max-w-[120px] truncate">{e.libelle_d}</td>
                      <td className="px-4 py-2.5 font-mono text-gray-300">{e.compte_c}</td>
                      <td className="px-4 py-2.5 text-gray-400 max-w-[120px] truncate">{e.libelle_c}</td>
                      <td className="px-4 py-2.5 font-semibold text-white text-right">{formatMontant(e.montant)}</td>
                      <td className="px-4 py-2.5 font-mono text-ciel-500 text-xs">{e.reference}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Rapport analytique */}
      {onglet === "analytique" && (
        <div className="px-8 space-y-6">
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: "Primes collectées", val: "173 M FCFA", trend: "+8%", color: "green" },
              { label: "Charges sinistres",  val: "108 M FCFA", trend: "+3%", color: "orange" },
              { label: "Résultat technique", val: "65 M FCFA",  trend: "+12%", color: "blue" },
            ].map(({ label, val, trend, color }) => (
              <div key={label} className="rounded-2xl border p-5" style={{ background: "rgba(17,24,39,0.8)", borderColor: "rgba(255,255,255,0.06)" }}>
                <p className="text-xs text-gray-500 mb-1">{label}</p>
                <p className="text-2xl font-bold text-white">{val}</p>
                <p className={`text-xs mt-1 ${color === "green" ? "text-green-400" : color === "orange" ? "text-alerte-400" : "text-ciel-400"}`}>{trend} vs trim. précédent</p>
              </div>
            ))}
          </div>
          <div className="rounded-2xl border p-6" style={{ background: "rgba(17,24,39,0.8)", borderColor: "rgba(255,255,255,0.06)" }}>
            <h3 className="text-sm font-semibold text-white mb-4">Primes · Sinistres · Frais (M FCFA)</h3>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={DEMO_CHART} barCategoryGap="30%">
                <XAxis dataKey="mois" tick={{ fill: "#6B7280", fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#6B7280", fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: "#1F2937", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12, fontSize: 12 }} />
                <Bar dataKey="primes"    fill="#0054A6" radius={[4,4,0,0]} name="Primes" />
                <Bar dataKey="sinistres" fill="#f97316" radius={[4,4,0,0]} name="Sinistres" />
                <Bar dataKey="frais"     fill="#6B7280" radius={[4,4,0,0]} name="Frais" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Rapprochement */}
      {onglet === "rapprochement" && (
        <div className="px-8 max-w-lg">
          <p className="text-sm text-gray-400 mb-4">Importez un relevé bancaire pour rapprochement automatique :</p>
          <div className="border-2 border-dashed border-white/[0.08] rounded-2xl p-10 text-center hover:border-assurance-500/30 transition-all cursor-pointer mb-4">
            <Upload className="w-10 h-10 mx-auto mb-3 text-gray-500" />
            <p className="text-sm text-gray-300">Relevé bancaire CSV / PDF</p>
            <p className="text-xs text-gray-600 mt-1">YukpoPro identifiera automatiquement les rapprochements</p>
          </div>
          <div className="rounded-xl border border-white/[0.06] p-4 text-xs text-gray-400" style={{ background: "rgba(17,24,39,0.8)" }}>
            <p className="font-medium text-white mb-2">Dernier rapprochement — Mars 2026</p>
            <div className="flex justify-between mb-1"><span>Éléments rapprochés</span><span className="text-green-400 font-semibold">142 / 148 (95.9%)</span></div>
            <div className="flex justify-between"><span>Écarts détectés</span><span className="text-alerte-400">6 — investigation requise</span></div>
          </div>
        </div>
      )}

      <div className="pb-8" />
    </div>
  );
}
