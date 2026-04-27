import { useState } from "react";
import { FolderOpen, FileText, Download, Trash2, Search } from "lucide-react";
import { cn } from "@/components/ui";
import { useDocsStore } from "@/store";
import type { DocGenere } from "@/types";

const DEMO_DOCS: DocGenere[] = [
  { id: "1", titre: "Courrier règlement SIN-2026-018", type: "courrier_sinistre", createdAt: "2026-04-22T10:30:00Z" },
  { id: "2", titre: "Police RC Auto POL-2026-142 — Kouassi J.B.", type: "police", createdAt: "2026-04-21T16:00:00Z" },
  { id: "3", titre: "Rapport expertise SIN-2026-015", type: "rapport_expertise", createdAt: "2026-04-20T14:15:00Z" },
  { id: "4", titre: "États CIMA C12 — T4 2025", type: "etat_cima", createdAt: "2026-04-18T09:00:00Z" },
  { id: "5", titre: "Bordereau cessions T1 2026", type: "bordereau_reassurance", createdAt: "2026-04-15T11:00:00Z" },
];

const TYPE_CONFIG: Record<string, { label: string; color: string }> = {
  courrier_sinistre:    { label: "Courrier sinistre",   color: "text-ciel-400 bg-assurance-500/10 border-assurance-500/20" },
  police:               { label: "Police",               color: "text-green-400 bg-green-500/10 border-green-500/20" },
  rapport_expertise:    { label: "Rapport expertise",    color: "text-purple-400 bg-purple-500/10 border-purple-500/20" },
  etat_cima:            { label: "État CIMA",            color: "text-alerte-400 bg-alerte-500/10 border-alerte-500/20" },
  bordereau_reassurance:{ label: "Bordereau réass.",     color: "text-teal-400 bg-teal-500/10 border-teal-500/20" },
};

export function DocumentsPage() {
  const { documents, removeDocument } = useDocsStore();
  const [search, setSearch] = useState("");

  const allDocs = [...DEMO_DOCS, ...documents];
  const filtered = allDocs.filter((d) =>
    d.titre.toLowerCase().includes(search.toLowerCase()) ||
    d.type.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="px-8 pt-8 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
            Documents
          </h1>
          <p className="text-sm text-gray-400 mt-0.5">Polices, courriers, rapports, états CIMA</p>
        </div>
      </div>

      <div className="px-8 mb-6">
        <div className="relative max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
          <input
            className="w-full bg-white/[0.04] border border-white/[0.06] rounded-xl pl-9 pr-4 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-assurance-500/40 transition-all"
            placeholder="Rechercher un document…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      <div className="px-8 space-y-3 pb-8">
        {filtered.length === 0 && (
          <div className="text-center py-16">
            <FolderOpen className="w-12 h-12 mx-auto mb-3 text-gray-700" />
            <p className="text-sm text-gray-500">Aucun document trouvé.</p>
          </div>
        )}
        {filtered.map((doc) => {
          const typeInfo = TYPE_CONFIG[doc.type] || { label: doc.type, color: "text-gray-400 bg-gray-500/10 border-gray-500/20" };
          return (
            <div key={doc.id} className="flex items-center gap-4 rounded-2xl border p-4"
              style={{ background: "rgba(17,24,39,0.8)", borderColor: "rgba(255,255,255,0.06)" }}>
              <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{ background: "rgba(0,84,166,0.12)", border: "1px solid rgba(0,176,240,0.2)" }}>
                <FileText className="w-5 h-5 text-ciel-400" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-white truncate">{doc.titre}</p>
                <div className="flex items-center gap-2 mt-1">
                  <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full border", typeInfo.color)}>
                    {typeInfo.label}
                  </span>
                  <span className="text-xs text-gray-600">
                    {new Date(doc.createdAt).toLocaleDateString("fr-FR", { dateStyle: "medium" })}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <button className="p-2 text-gray-500 hover:text-ciel-400 hover:bg-assurance-500/10 rounded-lg transition-all">
                  <Download className="w-4 h-4" />
                </button>
                {!DEMO_DOCS.find((d) => d.id === doc.id) && (
                  <button onClick={() => removeDocument(doc.id)}
                    className="p-2 text-gray-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-all">
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
