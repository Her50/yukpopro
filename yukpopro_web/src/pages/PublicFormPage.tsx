/**
 * Page publique de collecte de réponses — accessible sans authentification.
 * URL: /formulaire/:formulaireId
 */
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import toast, { Toaster } from "react-hot-toast";
import { CheckCircle2, Loader2, AlertCircle, Send } from "lucide-react";
import { enquetesApi } from "@/api/client";

interface PubQuestion {
  question_id: string;
  libelle: string;
  type_question: string;
  options: string[];
  obligatoire: boolean;
  ordre: number;
  hint?: string;
  section_id?: string;
  section_label?: string;
  relevant?: string;
  constraint?: string;
  constraint_message?: string;
  appearance?: string;
  name_xlsform?: string;
}

interface PubForm {
  formulaire_id: string;
  titre: string;
  description: string;
  questions: PubQuestion[];
}

const inputBase =
  "w-full rounded-lg px-3 py-2 text-sm bg-white border border-gray-300 focus:outline-none focus:border-[#0054A6] text-gray-900 placeholder-gray-400";

const isRelevant = (q: PubQuestion, values: Record<string, any>, questions: PubQuestion[]): boolean => {
  if (!q.relevant) return true;
  // Support minimal XLSForm: ${name} = 'valeur'  |  ${name} != 'valeur'
  const re = /\$\{([a-zA-Z0-9_]+)\}\s*(=|!=)\s*'([^']*)'/g;
  let m: RegExpExecArray | null;
  let lastEnd = 0;
  let acc = true;
  let op: "and" | "or" = "and";
  while ((m = re.exec(q.relevant)) !== null) {
    const [full, name, cmp, val] = m;
    const between = q.relevant.slice(lastEnd, m.index).toLowerCase();
    if (between.includes(" or ")) op = "or";
    lastEnd = m.index + full.length;
    const src = questions.find(x => (x.name_xlsform || "") === name);
    const cur = src ? values[src.question_id] : undefined;
    const eq = String(cur ?? "") === val;
    const res = cmp === "=" ? eq : !eq;
    acc = op === "or" ? acc || res : acc && res;
  }
  return acc;
};

export const PublicFormPage = () => {
  const { formulaireId } = useParams<{ formulaireId: string }>();
  const [form, setForm] = useState<PubForm | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>("");
  const [values, setValues] = useState<Record<string, any>>({});
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!formulaireId) return;
    enquetesApi.getFormulairePublic(formulaireId)
      .then(setForm)
      .catch(e => setError(e?.response?.data?.detail || "Formulaire introuvable ou fermé"))
      .finally(() => setLoading(false));
  }, [formulaireId]);

  const setVal = (qid: string, v: any) => setValues(p => ({ ...p, [qid]: v }));

  const visibleQuestions = form
    ? form.questions.filter(q => isRelevant(q, values, form.questions) && !q.type_question.startsWith("begin_") && !q.type_question.startsWith("end_"))
    : [];

  const submit = async () => {
    if (!form || !formulaireId) return;
    for (const q of visibleQuestions) {
      if (q.obligatoire) {
        const v = values[q.question_id];
        if (v === undefined || v === "" || (Array.isArray(v) && v.length === 0)) {
          toast.error(`Veuillez répondre : ${q.libelle}`);
          return;
        }
      }
    }
    setSubmitting(true);
    try {
      await enquetesApi.soumettreFormulaire(formulaireId, values);
      setDone(true);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Erreur lors de l'envoi");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <Loader2 className="w-8 h-8 animate-spin text-[#0054A6]" />
      </div>
    );
  }
  if (error || !form) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
        <div className="max-w-md w-full bg-white rounded-2xl shadow p-6 text-center">
          <AlertCircle className="w-12 h-12 mx-auto text-red-500 mb-3" />
          <h1 className="text-lg font-semibold text-gray-900 mb-1">Formulaire indisponible</h1>
          <p className="text-sm text-gray-600">{error || "Ce formulaire n'est pas accessible."}</p>
        </div>
      </div>
    );
  }
  if (done) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
        <div className="max-w-md w-full bg-white rounded-2xl shadow p-6 text-center">
          <CheckCircle2 className="w-14 h-14 mx-auto text-green-500 mb-3" />
          <h1 className="text-lg font-semibold text-gray-900 mb-1">Merci pour votre participation</h1>
          <p className="text-sm text-gray-600">Vos réponses ont bien été enregistrées.</p>
        </div>
      </div>
    );
  }

  // Grouper par section
  const sections: { id: string; label: string; items: PubQuestion[] }[] = [];
  for (const q of visibleQuestions) {
    const sid = q.section_id || "_default";
    const slabel = q.section_label || "";
    let sec = sections.find(s => s.id === sid);
    if (!sec) {
      sec = { id: sid, label: slabel, items: [] };
      sections.push(sec);
    }
    sec.items.push(q);
  }

  return (
    <div className="min-h-screen bg-gray-50 py-8 px-4">
      <Toaster position="top-center" />
      <div className="max-w-2xl mx-auto">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
          <div className="bg-gradient-to-r from-[#0054A6] to-[#0A7BC4] text-white px-6 py-5">
            <h1 className="text-xl font-bold">{form.titre}</h1>
            {form.description && (
              <p className="text-sm text-white/80 mt-1">{form.description}</p>
            )}
          </div>
          <form
            onSubmit={e => { e.preventDefault(); submit(); }}
            className="px-6 py-5 space-y-6"
          >
            {sections.map((sec, si) => (
              <div key={sec.id + si} className="space-y-4">
                {sec.label && (
                  <h2 className="text-sm font-semibold text-gray-900 pb-2 border-b border-gray-200">
                    {sec.label}
                  </h2>
                )}
                {sec.items.map(q => (
                  <QuestionField key={q.question_id} q={q} value={values[q.question_id]} onChange={v => setVal(q.question_id, v)} />
                ))}
              </div>
            ))}
            <button
              type="submit"
              disabled={submitting}
              className="w-full flex items-center justify-center gap-2 bg-[#0054A6] text-white py-3 rounded-xl font-semibold hover:bg-[#003d7a] transition disabled:opacity-60"
            >
              {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              {submitting ? "Envoi..." : "Envoyer mes réponses"}
            </button>
          </form>
        </div>
        <p className="text-xs text-gray-400 text-center mt-4">
          Formulaire sécurisé — propulsé par YukpoPro
        </p>
      </div>
    </div>
  );
};

const QuestionField = ({ q, value, onChange }: { q: PubQuestion; value: any; onChange: (v: any) => void }) => {
  const label = (
    <label className="block text-sm font-medium text-gray-800 mb-1">
      {q.libelle}
      {q.obligatoire && <span className="text-red-500 ml-1">*</span>}
    </label>
  );
  const hint = q.hint ? <p className="text-xs text-gray-500 mt-1">{q.hint}</p> : null;

  const validate = (v: any) => {
    if (!q.constraint) return;
    // Support minimal: ". > X", ". < X", ". >= X", ". <= X", "regex(., '...')"
    const n = Number(v);
    const cons = q.constraint.replace(/\s/g, "");
    const m = cons.match(/^\.([<>]=?)(-?\d+(?:\.\d+)?)$/);
    if (m && !isNaN(n)) {
      const [, op, num] = m;
      const target = Number(num);
      const ok = op === ">" ? n > target : op === "<" ? n < target : op === ">=" ? n >= target : n <= target;
      if (!ok) toast.error(q.constraint_message || `Contrainte non respectée : ${q.constraint}`);
    }
  };

  switch (q.type_question) {
    case "number":
    case "integer":
    case "decimal":
      return (
        <div>
          {label}
          <input
            type="number"
            className={inputBase}
            value={value ?? ""}
            onChange={e => onChange(e.target.value === "" ? "" : Number(e.target.value))}
            onBlur={e => validate(e.target.value)}
          />
          {hint}
        </div>
      );
    case "select_one":
    case "likert":
    case "oui_non":
      return (
        <div>
          {label}
          <div className="space-y-2">
            {q.options.map(opt => (
              <label key={opt} className="flex items-center gap-2 px-3 py-2 rounded-lg border border-gray-200 hover:bg-gray-50 cursor-pointer text-sm">
                <input type="radio" name={q.question_id} value={opt} checked={value === opt} onChange={() => onChange(opt)} />
                <span>{opt}</span>
              </label>
            ))}
          </div>
          {hint}
        </div>
      );
    case "select_multiple": {
      const arr: string[] = Array.isArray(value) ? value : [];
      return (
        <div>
          {label}
          <div className="space-y-2">
            {q.options.map(opt => (
              <label key={opt} className="flex items-center gap-2 px-3 py-2 rounded-lg border border-gray-200 hover:bg-gray-50 cursor-pointer text-sm">
                <input
                  type="checkbox"
                  checked={arr.includes(opt)}
                  onChange={e => {
                    const next = e.target.checked ? [...arr, opt] : arr.filter(v => v !== opt);
                    onChange(next);
                  }}
                />
                <span>{opt}</span>
              </label>
            ))}
          </div>
          {hint}
        </div>
      );
    }
    case "rating":
    case "range": {
      const opts = q.options.length > 0 ? q.options : ["1", "2", "3", "4", "5"];
      return (
        <div>
          {label}
          <div className="flex gap-2 flex-wrap">
            {opts.map(o => (
              <button
                type="button"
                key={o}
                onClick={() => onChange(o)}
                className={`px-4 py-2 rounded-full text-sm border transition ${value === o ? "bg-[#0054A6] text-white border-[#0054A6]" : "bg-white text-gray-700 border-gray-300 hover:border-[#0054A6]"}`}
              >
                {o}
              </button>
            ))}
          </div>
          {hint}
        </div>
      );
    }
    case "date":
      return (
        <div>
          {label}
          <input type="date" className={inputBase} value={value ?? ""} onChange={e => onChange(e.target.value)} />
          {hint}
        </div>
      );
    case "geopoint":
      return (
        <div>
          {label}
          <input
            type="text"
            placeholder="latitude, longitude"
            className={inputBase}
            value={value ?? ""}
            onChange={e => onChange(e.target.value)}
          />
          <button
            type="button"
            className="mt-2 text-xs text-[#0054A6] hover:underline"
            onClick={() => {
              if (!navigator.geolocation) { toast.error("Géolocalisation non disponible"); return; }
              navigator.geolocation.getCurrentPosition(
                p => onChange(`${p.coords.latitude.toFixed(6)}, ${p.coords.longitude.toFixed(6)}`),
                () => toast.error("Impossible de récupérer la position"),
              );
            }}
          >
            📍 Utiliser ma position
          </button>
          {hint}
        </div>
      );
    case "note":
      return (
        <div className="bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 text-sm text-blue-900">
          {q.libelle}
        </div>
      );
    case "text":
    default:
      return (
        <div>
          {label}
          <textarea
            rows={2}
            className={inputBase + " resize-y"}
            value={value ?? ""}
            onChange={e => onChange(e.target.value)}
            onBlur={e => validate(e.target.value)}
          />
          {hint}
        </div>
      );
  }
};
