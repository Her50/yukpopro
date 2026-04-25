/**
 * SurveyAnalytics — Tableau de bord des réponses collectées.
 * KPIs + distribution par question + table brute + export CSV.
 */
import { useMemo } from "react";
import { Download, Users, CheckSquare, Clock, BarChart3 } from "lucide-react";
import { enquetesApi } from "@/api/client";

export interface AnalyticsQuestion {
  question_id: string;
  libelle: string;
  type_question: string;
  options?: string[];
  name_xlsform?: string;
  ordre?: number;
}

interface Props {
  etude_id: string;
  formulaireTitre?: string;
  questions: AnalyticsQuestion[];
  reponses: Record<string, any>[];
}

const CHART_COLORS = ["#0054A6", "#0A7BC4", "#3B9FE0", "#6AB8F7", "#94D1FF", "#C4E5FF"];

const Kpi = ({ icon: Icon, label, value }: { icon: any; label: string; value: string | number }) => (
  <div className="rounded-xl bg-white/[0.04] border border-white/[0.08] px-4 py-3">
    <div className="flex items-center gap-2 text-xs text-gray-400">
      <Icon className="w-3.5 h-3.5" />
      {label}
    </div>
    <div className="text-xl font-bold text-white mt-1">{value}</div>
  </div>
);

const computeDistribution = (q: AnalyticsQuestion, reponses: Record<string, any>[]) => {
  const counts: Record<string, number> = {};
  let total = 0;
  for (const r of reponses) {
    const v = r[q.question_id];
    if (v === undefined || v === null || v === "") continue;
    total++;
    if (Array.isArray(v)) {
      for (const x of v) counts[String(x)] = (counts[String(x)] || 0) + 1;
    } else {
      counts[String(v)] = (counts[String(v)] || 0) + 1;
    }
  }
  const items = Object.entries(counts)
    .map(([label, n]) => ({ label, n, pct: total ? (n / total) * 100 : 0 }))
    .sort((a, b) => b.n - a.n);
  return { items, total };
};

const isCategorical = (q: AnalyticsQuestion) =>
  ["select_one", "select_multiple", "oui_non", "likert", "rating"].includes(q.type_question);

export const SurveyAnalytics = ({ etude_id, formulaireTitre, questions, reponses }: Props) => {
  const sorted = useMemo(() => [...questions].sort((a, b) => (a.ordre ?? 0) - (b.ordre ?? 0)), [questions]);
  const catQuestions = sorted.filter(isCategorical);
  const completionRate = useMemo(() => {
    if (reponses.length === 0 || sorted.length === 0) return 0;
    let filled = 0;
    let expected = 0;
    for (const r of reponses) {
      for (const q of sorted) {
        expected++;
        const v = r[q.question_id];
        if (v !== undefined && v !== null && v !== "" && !(Array.isArray(v) && v.length === 0)) filled++;
      }
    }
    return expected ? Math.round((filled / expected) * 100) : 0;
  }, [sorted, reponses]);

  const latest = useMemo(() => {
    const dates = reponses.map(r => r._soumis_le).filter(Boolean).sort();
    return dates.length ? dates[dates.length - 1] : null;
  }, [reponses]);

  const csvHref = enquetesApi.csvDonneesUrl(etude_id);
  const token = typeof window !== "undefined" ? localStorage.getItem("yukpopro_token") : null;
  const downloadCsv = async () => {
    try {
      const res = await fetch(csvHref, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("Erreur export");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${(formulaireTitre || "donnees").replace(/[^a-zA-Z0-9]+/g, "_")}.csv`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch {
      window.open(csvHref, "_blank");
    }
  };

  if (reponses.length === 0) {
    return (
      <div className="rounded-2xl bg-white/[0.03] border border-white/[0.06] p-8 text-center">
        <BarChart3 className="w-10 h-10 text-gray-500 mx-auto mb-3" />
        <p className="text-sm text-gray-300 font-medium">Aucune réponse collectée pour le moment.</p>
        <p className="text-xs text-gray-500 mt-1">Partagez le lien de collecte pour commencer.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className="text-sm font-semibold text-white flex items-center gap-2">
          <BarChart3 className="w-4 h-4" /> Analyse des réponses
        </h3>
        <button
          onClick={downloadCsv}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white/[0.06] text-gray-200 border border-white/[0.08] hover:bg-white/[0.10]"
        >
          <Download className="w-3.5 h-3.5" /> Exporter CSV
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi icon={Users} label="Réponses" value={reponses.length} />
        <Kpi icon={CheckSquare} label="Taux complétion" value={`${completionRate}%`} />
        <Kpi icon={BarChart3} label="Questions" value={sorted.length} />
        <Kpi icon={Clock} label="Dernière" value={latest ? new Date(latest).toLocaleDateString() : "—"} />
      </div>

      <div className="space-y-3">
        {catQuestions.map(q => {
          const { items, total } = computeDistribution(q, reponses);
          if (total === 0) return null;
          return (
            <div key={q.question_id} className="rounded-xl bg-white/[0.04] border border-white/[0.08] p-4">
              <div className="flex items-start justify-between mb-3 gap-2">
                <h4 className="text-sm font-medium text-white">{q.libelle}</h4>
                <span className="text-xs text-gray-400 shrink-0">{total} réponses</span>
              </div>
              <div className="space-y-2">
                {items.map((it, i) => (
                  <div key={it.label}>
                    <div className="flex justify-between text-xs text-gray-300 mb-1">
                      <span className="truncate pr-2">{it.label}</span>
                      <span className="shrink-0">{it.n} ({it.pct.toFixed(1)}%)</span>
                    </div>
                    <div className="h-2 rounded-full bg-white/[0.05] overflow-hidden">
                      <div
                        className="h-full rounded-full"
                        style={{ width: `${it.pct}%`, background: CHART_COLORS[i % CHART_COLORS.length] }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      <div className="rounded-xl bg-white/[0.03] border border-white/[0.06] overflow-hidden">
        <div className="px-4 py-2 border-b border-white/[0.06] text-xs text-gray-400 font-medium">
          Données brutes (aperçu)
        </div>
        <div className="overflow-x-auto max-h-80">
          <table className="w-full text-xs">
            <thead className="bg-white/[0.04] sticky top-0">
              <tr>
                {sorted.map(q => (
                  <th key={q.question_id} className="text-left px-3 py-2 font-medium text-gray-300 whitespace-nowrap">
                    {q.name_xlsform || q.libelle.slice(0, 30)}
                  </th>
                ))}
                <th className="text-left px-3 py-2 font-medium text-gray-300">Soumis le</th>
              </tr>
            </thead>
            <tbody>
              {reponses.slice(0, 50).map((r, i) => (
                <tr key={i} className="border-t border-white/[0.04]">
                  {sorted.map(q => {
                    const v = r[q.question_id];
                    const disp = Array.isArray(v) ? v.join(", ") : (v ?? "");
                    return (
                      <td key={q.question_id} className="px-3 py-1.5 text-gray-300 whitespace-nowrap max-w-[200px] truncate">
                        {String(disp)}
                      </td>
                    );
                  })}
                  <td className="px-3 py-1.5 text-gray-500 whitespace-nowrap">
                    {r._soumis_le ? new Date(r._soumis_le).toLocaleString() : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {reponses.length > 50 && (
            <div className="px-3 py-2 text-xs text-gray-500 bg-white/[0.02] border-t border-white/[0.04]">
              Affichage limité à 50 lignes — exportez en CSV pour tout récupérer.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
