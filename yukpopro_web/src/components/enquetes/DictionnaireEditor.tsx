/**
 * DictionnaireEditor — Édition du dictionnaire des variables d'un formulaire.
 * Enrichit chaque variable avec description métier, unité, catégorie, notes.
 * Bouton "Générer IA" pour pré-remplir automatiquement via le LLM.
 */
import { useEffect, useState } from "react";
import { BookOpen, Save, Sparkles, Loader2 } from "lucide-react";
import toast from "react-hot-toast";
import { enquetesApi } from "@/api/client";

interface VariableMeta {
  libelle: string;
  type: string;
  modalites: string[];
  section?: string;
  obligatoire?: boolean;
  description: string;
  unite: string;
  categorie: string;
  notes_metier: string;
  modalites_detaillees?: Record<string, string>;
}

interface Props {
  etude_id: string;
}

const CATEGORIES = [
  "démographique", "économique", "santé", "éducation",
  "opinion", "comportement", "géographique", "temporel", "autre",
];

const inputCls = "w-full rounded-lg px-2.5 py-1.5 text-xs text-white bg-white/[0.06] border border-white/[0.08] focus:outline-none focus:border-yukpo-500/50 placeholder-gray-600";

export const DictionnaireEditor = ({ etude_id }: Props) => {
  const [vars, setVars] = useState<Record<string, VariableMeta>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [genIA, setGenIA] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await enquetesApi.getDictionnaire(etude_id);
      setVars(res.variables || {});
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Chargement dictionnaire impossible");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [etude_id]);

  const update = (name: string, patch: Partial<VariableMeta>) =>
    setVars(v => ({ ...v, [name]: { ...v[name], ...patch } }));

  const save = async () => {
    setSaving(true);
    try {
      const toSend: Record<string, any> = {};
      for (const [name, meta] of Object.entries(vars)) {
        toSend[name] = {
          description: meta.description || "",
          unite: meta.unite || "",
          categorie: meta.categorie || "",
          notes_metier: meta.notes_metier || "",
          modalites_detaillees: meta.modalites_detaillees || {},
        };
      }
      await enquetesApi.setDictionnaire(etude_id, toSend);
      toast.success("Dictionnaire enregistré");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Erreur enregistrement");
    } finally {
      setSaving(false);
    }
  };

  const genererIA = async () => {
    setGenIA(true);
    toast("Claude analyse vos variables…", { icon: "✨", duration: 20000 });
    try {
      const res = await enquetesApi.genererDictionnaireIa(etude_id);
      setVars(res.variables || {});
      toast.dismiss();
      toast.success("Dictionnaire pré-rempli par l'IA");
    } catch (e: any) {
      toast.dismiss();
      toast.error(e?.response?.data?.detail || "Erreur IA");
    } finally {
      setGenIA(false);
    }
  };

  if (loading) {
    return <div className="flex items-center gap-2 text-xs text-gray-400 p-4"><Loader2 className="w-4 h-4 animate-spin" /> Chargement…</div>;
  }

  const entries = Object.entries(vars);
  if (entries.length === 0) {
    return <p className="text-xs text-gray-400 p-4">Aucune variable — créez d'abord un formulaire.</p>;
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className="text-sm font-semibold text-white flex items-center gap-2">
          <BookOpen className="w-4 h-4" /> Dictionnaire des variables ({entries.length})
        </h3>
        <div className="flex gap-2">
          <button
            onClick={genererIA}
            disabled={genIA}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-purple-500/10 text-purple-300 border border-purple-500/20 hover:bg-purple-500/[0.15] disabled:opacity-50"
          >
            {genIA ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
            Pré-remplir IA
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

      <div className="space-y-2 max-h-[60vh] overflow-y-auto pr-1">
        {entries.map(([name, meta]) => (
          <div key={name} className="rounded-lg bg-white/[0.04] border border-white/[0.08] p-3">
            <div className="flex items-center gap-2 mb-2 flex-wrap">
              <code className="text-xs px-2 py-0.5 rounded bg-white/[0.06] text-yukpo-400 font-mono">{name}</code>
              <span className="text-xs text-gray-400 truncate">{meta.libelle}</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] text-gray-500">{meta.type}</span>
              {meta.section && <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] text-gray-500">{meta.section}</span>}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              <div className="md:col-span-2">
                <label className="block text-[10px] text-gray-500 mb-0.5">Description métier</label>
                <input
                  className={inputCls}
                  placeholder="Ce que mesure précisément cette variable…"
                  value={meta.description || ""}
                  onChange={e => update(name, { description: e.target.value })}
                />
              </div>
              <div>
                <label className="block text-[10px] text-gray-500 mb-0.5">Unité</label>
                <input
                  className={inputCls}
                  placeholder="ans, FCFA, %, …"
                  value={meta.unite || ""}
                  onChange={e => update(name, { unite: e.target.value })}
                />
              </div>
              <div>
                <label className="block text-[10px] text-gray-500 mb-0.5">Catégorie</label>
                <select
                  className={inputCls}
                  value={meta.categorie || ""}
                  onChange={e => update(name, { categorie: e.target.value })}
                >
                  <option value="" className="bg-[#0b0b0b]">—</option>
                  {CATEGORIES.map(c => <option key={c} value={c} className="bg-[#0b0b0b]">{c}</option>)}
                </select>
              </div>
              <div className="md:col-span-2">
                <label className="block text-[10px] text-gray-500 mb-0.5">Notes métier</label>
                <input
                  className={inputCls}
                  placeholder="Attention, biais possible, précision de mesure, …"
                  value={meta.notes_metier || ""}
                  onChange={e => update(name, { notes_metier: e.target.value })}
                />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
