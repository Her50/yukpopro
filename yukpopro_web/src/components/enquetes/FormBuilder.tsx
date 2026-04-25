/**
 * FormBuilder — Éditeur visuel professionnel du formulaire de collecte.
 * Fonctionnalités : réorganisation, ajout/suppression/duplication de question,
 * édition des champs XLSForm (libellé, type, options, hint, relevant, constraint,
 * appearance, sections). Sauvegarde via enquetesApi.majFormulaire.
 */
import { useMemo, useState } from "react";
import {
  Plus, Trash2, Copy, ArrowUp, ArrowDown, Save, Eye, Settings2,
  ChevronDown, ChevronUp, Loader2,
} from "lucide-react";
import toast from "react-hot-toast";
import { enquetesApi } from "@/api/client";

export interface BuilderQuestion {
  question_id?: string;
  libelle: string;
  type_question: string;
  options: string[];
  obligatoire: boolean;
  hint?: string;
  section_id?: string;
  section_label?: string;
  relevant?: string;
  constraint?: string;
  constraint_message?: string;
  appearance?: string;
  parameters?: string;
  name_xlsform?: string;
  ordre?: number;
}

export interface BuilderFormulaire {
  formulaire_id: string;
  titre: string;
  description?: string;
  questions: BuilderQuestion[];
}

const TYPES: { value: string; label: string }[] = [
  { value: "text",            label: "Texte libre" },
  { value: "number",          label: "Nombre" },
  { value: "select_one",      label: "Choix unique" },
  { value: "select_multiple", label: "Choix multiple" },
  { value: "likert",          label: "Échelle Likert" },
  { value: "rating",          label: "Note / Rating" },
  { value: "date",            label: "Date" },
  { value: "oui_non",         label: "Oui / Non" },
  { value: "geopoint",        label: "Géolocalisation" },
  { value: "note",            label: "Instruction (info)" },
];

const APPEARANCES: Record<string, string[]> = {
  select_one:      ["", "minimal", "horizontal", "likert"],
  select_multiple: ["", "minimal", "horizontal"],
  text:            ["", "multiline"],
};

const slugify = (s: string) =>
  s.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 30);

const emptyQuestion = (ordre: number): BuilderQuestion => ({
  libelle: "",
  type_question: "text",
  options: [],
  obligatoire: true,
  hint: "",
  section_id: "",
  section_label: "",
  relevant: "",
  constraint: "",
  constraint_message: "",
  appearance: "",
  parameters: "",
  name_xlsform: `q${ordre + 1}`,
  ordre,
});

interface Props {
  formulaire: BuilderFormulaire;
  onSaved?: (updated: BuilderFormulaire) => void;
  onPreview?: () => void;
}

const inputCls = "w-full rounded-lg px-3 py-2 text-sm text-white bg-white/[0.06] border border-white/[0.08] focus:outline-none focus:border-yukpo-500/50 placeholder-gray-600";
const labelCls = "block text-xs text-gray-400 mb-1 font-medium";

export const FormBuilder = ({ formulaire, onSaved, onPreview }: Props) => {
  const [titre, setTitre] = useState(formulaire.titre);
  const [description, setDescription] = useState(formulaire.description || "");
  const [questions, setQuestions] = useState<BuilderQuestion[]>(
    (formulaire.questions || []).map((q, i) => ({
      ...q,
      options: q.options || [],
      name_xlsform: q.name_xlsform || `q${i + 1}`,
      ordre: q.ordre ?? i,
    })),
  );
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [saving, setSaving] = useState(false);

  const nameByIndex = useMemo(() => questions.map(q => q.name_xlsform || ""), [questions]);

  const update = (i: number, patch: Partial<BuilderQuestion>) =>
    setQuestions(qs => qs.map((q, idx) => idx === i ? { ...q, ...patch } : q));

  const move = (i: number, delta: -1 | 1) => {
    setQuestions(qs => {
      const next = [...qs];
      const j = i + delta;
      if (j < 0 || j >= next.length) return qs;
      [next[i], next[j]] = [next[j], next[i]];
      return next.map((q, idx) => ({ ...q, ordre: idx }));
    });
  };

  const add = () => setQuestions(qs => [...qs, emptyQuestion(qs.length)]);
  const duplicate = (i: number) =>
    setQuestions(qs => {
      const copy = { ...qs[i], name_xlsform: `${qs[i].name_xlsform || "q"}_copy` };
      const next = [...qs.slice(0, i + 1), copy, ...qs.slice(i + 1)];
      return next.map((q, idx) => ({ ...q, ordre: idx }));
    });
  const remove = (i: number) =>
    setQuestions(qs => qs.filter((_, idx) => idx !== i).map((q, idx) => ({ ...q, ordre: idx })));

  const save = async () => {
    for (const q of questions) {
      if (!q.libelle.trim()) { toast.error("Toutes les questions doivent avoir un libellé"); return; }
    }
    setSaving(true);
    try {
      const payload = {
        titre,
        description,
        questions: questions.map((q, i) => ({
          ...q,
          ordre: i,
          name_xlsform: q.name_xlsform || slugify(q.libelle) || `q${i + 1}`,
        })),
      };
      const res = await enquetesApi.majFormulaire(formulaire.formulaire_id, payload);
      toast.success("Formulaire enregistré");
      onSaved?.({
        formulaire_id: formulaire.formulaire_id,
        titre: res.titre,
        description: res.description,
        questions: payload.questions,
      });
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Erreur enregistrement");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className="text-sm font-semibold text-white flex items-center gap-2">
          <Settings2 className="w-4 h-4" />
          Éditeur de formulaire — {questions.length} question(s)
        </h3>
        <div className="flex gap-2">
          {onPreview && (
            <button
              onClick={onPreview}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white/[0.06] text-gray-200 border border-white/[0.08] hover:bg-white/[0.10]"
            >
              <Eye className="w-3.5 h-3.5" /> Aperçu
            </button>
          )}
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

      <div className="rounded-xl bg-white/[0.03] border border-white/[0.06] p-4 space-y-3">
        <div>
          <label className={labelCls}>Titre du formulaire</label>
          <input className={inputCls} value={titre} onChange={e => setTitre(e.target.value)} />
        </div>
        <div>
          <label className={labelCls}>Description</label>
          <textarea rows={2} className={inputCls + " resize-none"} value={description} onChange={e => setDescription(e.target.value)} />
        </div>
      </div>

      <div className="space-y-2">
        {questions.map((q, i) => (
          <QuestionRow
            key={i}
            q={q}
            index={i}
            total={questions.length}
            expanded={!!expanded[i]}
            onToggle={() => setExpanded(p => ({ ...p, [i]: !p[i] }))}
            onChange={patch => update(i, patch)}
            onMoveUp={() => move(i, -1)}
            onMoveDown={() => move(i, 1)}
            onDuplicate={() => duplicate(i)}
            onRemove={() => remove(i)}
            otherNames={nameByIndex.filter((_, idx) => idx !== i).filter(Boolean)}
          />
        ))}
      </div>

      <button
        onClick={add}
        className="w-full flex items-center justify-center gap-2 rounded-xl border border-dashed border-white/[0.12] py-3 text-xs text-gray-300 hover:text-white hover:border-white/[0.2]"
      >
        <Plus className="w-4 h-4" /> Ajouter une question
      </button>
    </div>
  );
};

const QuestionRow = ({
  q, index, total, expanded, onToggle, onChange, onMoveUp, onMoveDown, onDuplicate, onRemove, otherNames,
}: {
  q: BuilderQuestion;
  index: number;
  total: number;
  expanded: boolean;
  onToggle: () => void;
  onChange: (patch: Partial<BuilderQuestion>) => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onDuplicate: () => void;
  onRemove: () => void;
  otherNames: string[];
}) => {
  const needsOptions = ["select_one", "select_multiple", "likert", "rating"].includes(q.type_question);
  const appearances = APPEARANCES[q.type_question] || [];

  return (
    <div className="rounded-xl bg-white/[0.04] border border-white/[0.08] overflow-hidden">
      <div className="flex items-center gap-2 p-3">
        <span className="flex items-center justify-center w-7 h-7 rounded-full bg-[#0054A6]/20 text-[#6AB8F7] text-xs font-semibold">
          {index + 1}
        </span>
        <input
          className="flex-1 rounded-lg px-3 py-1.5 text-sm text-white bg-white/[0.06] border border-white/[0.08] focus:outline-none focus:border-yukpo-500/50"
          placeholder="Libellé de la question"
          value={q.libelle}
          onChange={e => onChange({ libelle: e.target.value })}
        />
        <select
          className="rounded-lg px-2 py-1.5 text-xs text-white bg-white/[0.06] border border-white/[0.08]"
          value={q.type_question}
          onChange={e => onChange({ type_question: e.target.value })}
        >
          {TYPES.map(t => <option key={t.value} value={t.value} className="bg-[#0b0b0b]">{t.label}</option>)}
        </select>
        <button onClick={onMoveUp} disabled={index === 0} className="p-1.5 rounded hover:bg-white/[0.08] disabled:opacity-30"><ArrowUp className="w-3.5 h-3.5 text-gray-300" /></button>
        <button onClick={onMoveDown} disabled={index === total - 1} className="p-1.5 rounded hover:bg-white/[0.08] disabled:opacity-30"><ArrowDown className="w-3.5 h-3.5 text-gray-300" /></button>
        <button onClick={onDuplicate} className="p-1.5 rounded hover:bg-white/[0.08]"><Copy className="w-3.5 h-3.5 text-gray-300" /></button>
        <button onClick={onRemove} className="p-1.5 rounded hover:bg-red-500/10"><Trash2 className="w-3.5 h-3.5 text-red-400" /></button>
        <button onClick={onToggle} className="p-1.5 rounded hover:bg-white/[0.08]">
          {expanded ? <ChevronUp className="w-3.5 h-3.5 text-gray-300" /> : <ChevronDown className="w-3.5 h-3.5 text-gray-300" />}
        </button>
      </div>

      {expanded && (
        <div className="border-t border-white/[0.06] p-3 space-y-3 bg-black/20">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Identifiant (pour logique conditionnelle)</label>
              <input
                className={inputCls}
                placeholder="ex: sexe"
                value={q.name_xlsform || ""}
                onChange={e => onChange({ name_xlsform: slugify(e.target.value) })}
              />
            </div>
            <div>
              <label className={labelCls}>Section / Groupe (optionnel)</label>
              <input
                className={inputCls}
                placeholder="ex: identification"
                value={q.section_label || ""}
                onChange={e => onChange({ section_label: e.target.value, section_id: slugify(e.target.value) })}
              />
            </div>
          </div>

          <div>
            <label className={labelCls}>Aide / hint</label>
            <input className={inputCls} value={q.hint || ""} onChange={e => onChange({ hint: e.target.value })} />
          </div>

          {needsOptions && (
            <div>
              <label className={labelCls}>Options (une par ligne)</label>
              <textarea
                rows={4}
                className={inputCls + " resize-none"}
                value={(q.options || []).join("\n")}
                onChange={e => onChange({ options: e.target.value.split("\n").map(s => s.trim()).filter(Boolean) })}
              />
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Logique conditionnelle (relevant)</label>
              <input
                className={inputCls}
                placeholder={otherNames.length ? `ex: \${${otherNames[0]}} = 'oui'` : "ex: ${sexe} = 'feminin'"}
                value={q.relevant || ""}
                onChange={e => onChange({ relevant: e.target.value })}
              />
              {otherNames.length > 0 && (
                <p className="text-[10px] text-gray-500 mt-1">
                  Variables disponibles : {otherNames.slice(0, 6).map(n => `\${${n}}`).join(", ")}
                </p>
              )}
            </div>
            <div>
              <label className={labelCls}>Contrainte (constraint)</label>
              <input
                className={inputCls}
                placeholder="ex: . > 0 et . < 120"
                value={q.constraint || ""}
                onChange={e => onChange({ constraint: e.target.value })}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Message d'erreur contrainte</label>
              <input className={inputCls} value={q.constraint_message || ""} onChange={e => onChange({ constraint_message: e.target.value })} />
            </div>
            {appearances.length > 0 && (
              <div>
                <label className={labelCls}>Apparence</label>
                <select
                  className={inputCls}
                  value={q.appearance || ""}
                  onChange={e => onChange({ appearance: e.target.value })}
                >
                  {appearances.map(a => <option key={a} value={a} className="bg-[#0b0b0b]">{a || "par défaut"}</option>)}
                </select>
              </div>
            )}
          </div>

          <div className="flex items-center gap-4 pt-1">
            <label className="flex items-center gap-2 text-xs text-gray-300 cursor-pointer">
              <input
                type="checkbox"
                checked={q.obligatoire}
                onChange={e => onChange({ obligatoire: e.target.checked })}
              />
              Obligatoire
            </label>
          </div>
        </div>
      )}
    </div>
  );
};
