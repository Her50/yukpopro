/**
 * SurveyAnalytics — Tableau de bord des réponses collectées.
 * KPIs + distribution par question + table brute + export CSV +
 * analyses conversationnelles à la demande (Phase E4) avec
 * suggestions cliquables (P3 #9).
 */
import { useMemo, useState } from "react";
import { Download, Users, CheckSquare, Clock, BarChart3, Sparkles, Send, Loader2 } from "lucide-react";
import { enquetesApi } from "@/api/client";

export interface AnalyticsQuestion {
  question_id: string;
  libelle: string;
  type_question: string;
  options?: string[];
  name_xlsform?: string;
  ordre?: number;
}

interface PromptAnalysisResult {
  prompt: string;
  titre_analyse?: string;
  synthese_md?: string;
  tableaux?: { titre: string; donnees: any[][] }[];
  graphiques?: Record<string, string>;
  n_reponses_analyses?: number;
}

interface Props {
  etude_id: string;
  formulaireTitre?: string;
  questions: AnalyticsQuestion[];
  reponses: Record<string, any>[];
  // Phase E1 — suggestions générées par le LLM à la création de l'étude.
  // Affichées comme boutons 1-clic qui déclenchent /analyser-prompt.
  analyses_suggerees?: string[];
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

export const SurveyAnalytics = ({ etude_id, formulaireTitre, questions, reponses, analyses_suggerees }: Props) => {
  // État conversation analyse (multi-tour côté front, multi-tour côté
  // backend via `avec_historique: true` qui injecte l'historique stocké).
  const [promptDraft, setPromptDraft] = useState("");
  const [history, setHistory] = useState<PromptAnalysisResult[]>([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);

  const lancerAnalyse = async (prompt: string) => {
    const p = (prompt || "").trim();
    if (!p || analyzing) return;
    setAnalyzing(true);
    setAnalyzeError(null);
    try {
      const res = await enquetesApi.analyserPrompt(etude_id, p, {
        avec_historique: history.length > 0,
      });
      setHistory(h => [...h, {
        prompt: p,
        titre_analyse: res.titre_analyse,
        synthese_md: res.synthese_md,
        tableaux: res.tableaux,
        graphiques: res.graphiques,
        n_reponses_analyses: res.n_reponses_analyses,
      }]);
      setPromptDraft("");
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || "Erreur";
      setAnalyzeError(typeof detail === "string" ? detail : JSON.stringify(detail).slice(0, 200));
    } finally {
      setAnalyzing(false);
    }
  };
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

      {/* Phase E4 — Analyses conversationnelles à la demande */}
      <div className="rounded-xl bg-gradient-to-br from-violet-500/10 to-blue-500/10 border border-violet-400/20 p-4">
        <div className="flex items-center gap-2 mb-3">
          <Sparkles className="w-4 h-4 text-violet-300" />
          <h4 className="text-sm font-semibold text-white">Analyses conversationnelles</h4>
        </div>
        {analyses_suggerees && analyses_suggerees.length > 0 && history.length === 0 && (
          <div className="mb-3">
            <p className="text-xs text-gray-400 mb-2">Suggestions Yukpo (1 clic = 1 analyse) :</p>
            <div className="flex flex-wrap gap-1.5">
              {analyses_suggerees.map((s, i) => (
                <button
                  key={i}
                  disabled={analyzing}
                  onClick={() => lancerAnalyse(s)}
                  className="text-xs px-2.5 py-1.5 rounded-md bg-white/[0.06] hover:bg-white/[0.12] border border-white/[0.10] text-gray-200 disabled:opacity-50 disabled:cursor-not-allowed text-left max-w-[280px]"
                  title={s}
                >
                  {s.length > 60 ? s.slice(0, 57) + "…" : s}
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="flex gap-2">
          <input
            type="text"
            value={promptDraft}
            onChange={e => setPromptDraft(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && !analyzing) lancerAnalyse(promptDraft); }}
            placeholder={history.length > 0 ? "Question de suivi (« et par âge maintenant ? »)…" : "Pose une question d'analyse (ex. : « score NPS par genre »)"}
            className="flex-1 px-3 py-2 rounded-lg bg-white/[0.05] border border-white/[0.10] text-sm text-white placeholder-gray-500 focus:outline-none focus:border-violet-400/50"
            disabled={analyzing}
          />
          <button
            onClick={() => lancerAnalyse(promptDraft)}
            disabled={analyzing || !promptDraft.trim()}
            className="px-3 py-2 rounded-lg bg-violet-500 hover:bg-violet-400 text-white text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
          >
            {analyzing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          </button>
        </div>
        {analyzeError && <p className="text-xs text-rose-400 mt-2">{analyzeError}</p>}
        {history.length > 0 && (
          <div className="mt-4 space-y-3">
            {history.map((h, i) => (
              <div key={i} className="rounded-lg bg-black/20 border border-white/[0.05] p-3">
                <p className="text-xs text-violet-300 font-medium mb-1">{h.prompt}</p>
                {h.titre_analyse && <h5 className="text-sm font-semibold text-white mb-1">{h.titre_analyse}</h5>}
                {h.synthese_md && (
                  <div className="text-xs text-gray-200 whitespace-pre-wrap leading-relaxed">{h.synthese_md}</div>
                )}
                {h.graphiques && Object.keys(h.graphiques).length > 0 && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2">
                    {Object.entries(h.graphiques).map(([nom, b64]) => (
                      <img key={nom} src={`data:image/png;base64,${b64}`} alt={nom} className="rounded border border-white/[0.05] w-full" />
                    ))}
                  </div>
                )}
                {h.n_reponses_analyses != null && (
                  <p className="text-[10px] text-gray-500 mt-1">{h.n_reponses_analyses} réponses analysées</p>
                )}
              </div>
            ))}
          </div>
        )}
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
