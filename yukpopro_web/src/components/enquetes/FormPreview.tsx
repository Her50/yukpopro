/**
 * FormPreview — Aperçu du formulaire tel qu'il apparaîtra aux répondants.
 * Rendu readonly basé sur les questions de BuilderFormulaire.
 */
import type { BuilderFormulaire, BuilderQuestion } from "./FormBuilder";

interface Props {
  formulaire: BuilderFormulaire;
}

const fieldCls = "w-full rounded-lg px-3 py-2 text-sm bg-gray-100 border border-gray-200 text-gray-500";

export const FormPreview = ({ formulaire }: Props) => {
  const questions = [...formulaire.questions].sort((a, b) => (a.ordre ?? 0) - (b.ordre ?? 0));
  const sections: { id: string; label: string; items: BuilderQuestion[] }[] = [];
  for (const q of questions) {
    const sid = q.section_id || "_default";
    let sec = sections.find(s => s.id === sid);
    if (!sec) {
      sec = { id: sid, label: q.section_label || "", items: [] };
      sections.push(sec);
    }
    sec.items.push(q);
  }

  return (
    <div className="rounded-2xl bg-white text-gray-900 p-5 border border-white/[0.1]">
      <h3 className="text-lg font-bold text-[#0054A6] mb-1">{formulaire.titre}</h3>
      {formulaire.description && (
        <p className="text-sm text-gray-600 mb-5">{formulaire.description}</p>
      )}
      <div className="space-y-6">
        {sections.map((sec, i) => (
          <div key={sec.id + i} className="space-y-3">
            {sec.label && (
              <h4 className="text-sm font-semibold text-gray-900 pb-1 border-b border-gray-200">
                {sec.label}
              </h4>
            )}
            {sec.items.map((q, qi) => (
              <div key={qi}>
                <label className="block text-sm font-medium text-gray-800 mb-1">
                  {q.libelle || <span className="italic text-gray-400">(sans libellé)</span>}
                  {q.obligatoire && <span className="text-red-500 ml-1">*</span>}
                </label>
                {q.hint && <p className="text-xs text-gray-500 mb-1">{q.hint}</p>}
                <PreviewInput q={q} />
                {q.relevant && (
                  <p className="text-[10px] text-amber-600 mt-1">↪ Affichée si : {q.relevant}</p>
                )}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
};

const PreviewInput = ({ q }: { q: BuilderQuestion }) => {
  switch (q.type_question) {
    case "number":
      return <input disabled type="number" className={fieldCls} placeholder="0" />;
    case "select_one":
    case "likert":
    case "oui_non":
      return (
        <div className="space-y-1.5">
          {(q.options.length ? q.options : ["Option 1"]).map(o => (
            <label key={o} className="flex items-center gap-2 text-sm text-gray-700">
              <input type="radio" disabled /> {o}
            </label>
          ))}
        </div>
      );
    case "select_multiple":
      return (
        <div className="space-y-1.5">
          {(q.options.length ? q.options : ["Option 1"]).map(o => (
            <label key={o} className="flex items-center gap-2 text-sm text-gray-700">
              <input type="checkbox" disabled /> {o}
            </label>
          ))}
        </div>
      );
    case "rating":
      return (
        <div className="flex gap-1.5">
          {(q.options.length ? q.options : ["1", "2", "3", "4", "5"]).map(o => (
            <span key={o} className="px-3 py-1.5 rounded-full border border-gray-300 text-xs text-gray-600">{o}</span>
          ))}
        </div>
      );
    case "date":
      return <input disabled type="date" className={fieldCls} />;
    case "geopoint":
      return <input disabled className={fieldCls} placeholder="latitude, longitude" />;
    case "note":
      return <div className="bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 text-sm text-blue-900">{q.libelle}</div>;
    default:
      return <textarea disabled rows={2} className={fieldCls + " resize-none"} placeholder="Réponse libre…" />;
  }
};
