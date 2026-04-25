/**
 * PlanAnalyseEditor — Éditeur markdown du plan d'analyse.
 * Génération IA + édition libre + export DOCX.
 */
import { useEffect, useState } from "react";
import { FileText, Save, Sparkles, Loader2, Download, Eye, Edit3 } from "lucide-react";
import toast from "react-hot-toast";
import { enquetesApi } from "@/api/client";

interface Props {
  etude_id: string;
}

const renderMarkdown = (md: string) => {
  const lines = md.split("\n");
  const out: JSX.Element[] = [];
  lines.forEach((l, i) => {
    if (l.startsWith("# ")) out.push(<h1 key={i} className="text-base font-bold text-white mt-3 mb-1">{l.slice(2)}</h1>);
    else if (l.startsWith("## ")) out.push(<h2 key={i} className="text-sm font-semibold text-white mt-2 mb-1">{l.slice(3)}</h2>);
    else if (l.startsWith("### ")) out.push(<h3 key={i} className="text-xs font-semibold text-gray-200 mt-1.5">{l.slice(4)}</h3>);
    else if (l.startsWith("- ") || l.startsWith("* ")) out.push(<li key={i} className="text-xs text-gray-300 ml-4 list-disc">{l.slice(2)}</li>);
    else if (l.trim() === "") out.push(<div key={i} className="h-2" />);
    else out.push(<p key={i} className="text-xs text-gray-300 leading-relaxed">{l}</p>);
  });
  return <div>{out}</div>;
};

export const PlanAnalyseEditor = ({ etude_id }: Props) => {
  const [plan, setPlan] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [genIA, setGenIA] = useState(false);
  const [mode, setMode] = useState<"edit" | "preview">("preview");

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const res = await enquetesApi.getPlanAnalyse(etude_id);
        setPlan(res.plan_analyse || "");
        if (!res.plan_analyse) setMode("edit");
      } catch (e: any) {
        toast.error(e?.response?.data?.detail || "Chargement impossible");
      } finally {
        setLoading(false);
      }
    })();
  }, [etude_id]);

  const save = async () => {
    setSaving(true);
    try {
      await enquetesApi.setPlanAnalyse(etude_id, plan);
      toast.success("Plan d'analyse enregistré");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Erreur enregistrement");
    } finally { setSaving(false); }
  };

  const genererIA = async () => {
    setGenIA(true);
    toast("Claude construit votre plan d'analyse…", { icon: "✨", duration: 30000 });
    try {
      const res = await enquetesApi.genererPlanAnalyseIa(etude_id);
      setPlan(res.plan_analyse || "");
      setMode("preview");
      toast.dismiss();
      toast.success("Plan d'analyse généré");
    } catch (e: any) {
      toast.dismiss();
      toast.error(e?.response?.data?.detail || "Erreur IA");
    } finally { setGenIA(false); }
  };

  const downloadDocx = async () => {
    const url = enquetesApi.planAnalyseDocxUrl(etude_id);
    const token = localStorage.getItem("yukpopro_token");
    try {
      const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "plan_analyse.docx";
      document.body.appendChild(a); a.click(); a.remove();
    } catch {
      toast.error("Impossible de télécharger");
    }
  };

  if (loading) {
    return <div className="flex items-center gap-2 text-xs text-gray-400 p-4"><Loader2 className="w-4 h-4 animate-spin" /> Chargement…</div>;
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className="text-sm font-semibold text-white flex items-center gap-2">
          <FileText className="w-4 h-4" /> Plan d'analyse
        </h3>
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={() => setMode(mode === "edit" ? "preview" : "edit")}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white/[0.06] text-gray-200 border border-white/[0.08] hover:bg-white/[0.10]"
          >
            {mode === "edit" ? <><Eye className="w-3.5 h-3.5" /> Aperçu</> : <><Edit3 className="w-3.5 h-3.5" /> Éditer</>}
          </button>
          <button
            onClick={genererIA}
            disabled={genIA}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-purple-500/10 text-purple-300 border border-purple-500/20 hover:bg-purple-500/[0.15] disabled:opacity-50"
          >
            {genIA ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
            Générer IA
          </button>
          <button
            onClick={downloadDocx}
            disabled={!plan}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white/[0.06] text-gray-200 border border-white/[0.08] hover:bg-white/[0.10] disabled:opacity-50"
          >
            <Download className="w-3.5 h-3.5" /> Word
          </button>
          <button
            onClick={save}
            disabled={saving}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-[#0054A6] text-white hover:bg-[#003d7a] disabled:opacity-60"
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
            Enregistrer
          </button>
        </div>
      </div>

      {mode === "edit" ? (
        <textarea
          className="w-full rounded-xl px-3 py-2 text-xs text-gray-100 bg-white/[0.04] border border-white/[0.08] focus:outline-none focus:border-yukpo-500/50 font-mono resize-none"
          rows={22}
          value={plan}
          onChange={e => setPlan(e.target.value)}
          placeholder="# Plan d'analyse — Titre étude&#10;&#10;## 1. Objectifs analytiques&#10;…"
        />
      ) : (
        <div className="rounded-xl bg-white/[0.03] border border-white/[0.06] p-4 max-h-[60vh] overflow-y-auto">
          {plan ? renderMarkdown(plan) : (
            <p className="text-xs text-gray-500 italic">Aucun plan — utilisez "Générer IA" ou passez en mode Édition.</p>
          )}
        </div>
      )}
    </div>
  );
};
