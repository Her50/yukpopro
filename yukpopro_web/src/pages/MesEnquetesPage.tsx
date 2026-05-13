/**
 * MesEnquetesPage — YukpoPro (Phase E3)
 *
 * Liste les études du user avec stats temps réel.
 * Création = via le chat ("génère un questionnaire / sondage / audit / ...").
 * AUCUN catalogue de templates limitant — l'universalité passe par le
 * prompt LLM puissant côté backend (Opus 4.7 + 24k tokens).
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft, BarChart3, ClipboardList, Copy, ExternalLink,
  Loader2, RefreshCw, Users,
} from "lucide-react";
import toast from "react-hot-toast";
import { http } from "@/api/client";

type Enquete = {
  etude_id: string; titre: string; methodologie: string;
  formulaire_id: string | null; nb_questions: number;
  nb_reponses: number; dernier_repondant: string | null;
  taux_completion_pct: number;
  sparkline_7j: { date: string; n: number }[];
  lien_public: string | null;
  has_analyse: boolean;
};

const EXEMPLES_PROMPTS = [
  "génère un questionnaire de satisfaction client pour mon garage à Douala",
  "crée un audit de conformité OHADA pour ma PME (30 questions)",
  "fais un sondage d'opinion sur la qualité des transports en commun à Yaoundé",
  "génère un formulaire de recensement bénéficiaires ONG en zone rurale Tchad",
  "crée une évaluation 360° pour mes managers (sections : tech + soft skills)",
  "génère un suivi cohorte longitudinale d'élèves Bamako 6e-3e",
  "fais une enquête santé maternelle aligné indicateurs OMS pour Centrafrique",
  "compose un audit fournisseurs avec critères ISO 14001 + RSE",
];

export const MesEnquetesPage = () => {
  const { t } = useTranslation();
  const [enquetes, setEnquetes] = useState<Enquete[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    let annule = false;
    setLoading(true);
    http.get("/enquetes/mes-enquetes")
      .then(r => { if (!annule) setEnquetes(r.data.enquetes || []); })
      .catch((e: any) => {
        if (annule) return;
        toast.error(e?.response?.data?.detail || e?.message || "Erreur");
      })
      .finally(() => { if (!annule) setLoading(false); });
    return () => { annule = true; };
  }, [refreshTick]);

  const copierLien = (lien: string) => {
    const url = `${window.location.origin}${lien}`;
    navigator.clipboard?.writeText(url).then(() => toast.success("Lien copié"));
  };

  const copierExemple = (texte: string) => {
    navigator.clipboard?.writeText(texte).then(() =>
      toast.success("Exemple copié — collez-le dans le chat"));
  };

  return (
    <div className="p-4 md:p-6 max-w-6xl mx-auto">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-6">
        <div>
          <Link to="/chat" className="inline-flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900 mb-2">
            <ArrowLeft className="w-4 h-4" />
            {t("commun.retour_chat", "Retour au chat")}
          </Link>
          <h1 className="text-2xl md:text-3xl font-bold flex items-center gap-2">
            <ClipboardList className="w-6 h-6 text-violet-600" />
            {t("enquetes.titre", "Mes enquêtes & études")}
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            {t("enquetes.sous_titre",
               "Formulaires XLSForm + analyses IA conversationnelles. "
               + "Génère un formulaire pour N'IMPORTE QUEL domaine en tapant "
               + "ta demande dans le chat — santé, droit, RH, ONG, marketing, "
               + "recherche, agriculture, gouvernance, industrie…")}
          </p>
        </div>
        <button
          onClick={() => setRefreshTick(t => t + 1)}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-sm font-medium min-h-[44px]"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          {t("enquetes.refresh", "Rafraîchir")}
        </button>
      </div>

      {loading && (
        <div className="flex justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-violet-600" />
        </div>
      )}

      {!loading && enquetes.length === 0 && (
        <div className="space-y-4">
          <div className="bg-violet-50 border border-violet-200 rounded-xl p-6 md:p-8 text-center">
            <ClipboardList className="w-12 h-12 mx-auto text-violet-400 mb-3" />
            <h2 className="text-lg font-bold text-violet-900 mb-2">
              {t("enquetes.demarrer", "Décrivez votre besoin dans le chat")}
            </h2>
            <p className="text-sm text-violet-800 mb-4">
              {t("enquetes.aide_demarrer",
                 "Le LLM Opus 4.7 compose un formulaire complet (15-50 questions "
                 + "structurées XLSForm) adapté EXACTEMENT à votre contexte. "
                 + "Aucune limite de domaine, aucun template figé.")}
            </p>
            <Link to="/chat"
                  className="inline-block px-5 py-2.5 rounded-lg bg-violet-600 hover:bg-violet-700 text-white text-sm font-medium">
              {t("enquetes.aller_chat", "Ouvrir le chat")}
            </Link>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl p-5">
            <h3 className="font-semibold text-slate-900 mb-2">
              💡 {t("enquetes.exemples_titre", "Exemples pour vous inspirer (cliquer pour copier)")}
            </h3>
            <p className="text-xs text-slate-500 mb-3">
              {t("enquetes.exemples_aide",
                 "Ce ne sont PAS des templates — juste des exemples. "
                 + "Vous pouvez tout demander, même très spécifique à votre métier.")}
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {EXEMPLES_PROMPTS.map((ex, i) => (
                <button key={i} onClick={() => copierExemple(ex)}
                        className="text-left text-sm p-3 rounded-lg bg-slate-50 hover:bg-violet-50 hover:border-violet-200 border border-slate-200 transition-colors">
                  <Copy className="w-3.5 h-3.5 inline mr-1.5 text-slate-400" />
                  {ex}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {enquetes.map(e => (
          <EnqueteCard key={e.etude_id} e={e} onCopier={copierLien} t={t as any} />
        ))}
      </div>
    </div>
  );
};

const EnqueteCard = ({ e, onCopier, t }: {
  e: Enquete; onCopier: (lien: string) => void;
  t: (k: string, fb?: string) => string;
}) => {
  const maxN = Math.max(1, ...e.sparkline_7j.map(p => p.n));
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 hover:shadow-md transition-shadow">
      <div className="flex flex-col md:flex-row md:items-start gap-3">
        <div className="flex-grow min-w-0">
          <h2 className="font-bold text-lg text-slate-900 truncate">{e.titre}</h2>
          <div className="flex flex-wrap gap-2 text-xs text-slate-500 mt-1 mb-2">
            <span className="px-2 py-0.5 bg-slate-100 rounded">{e.methodologie}</span>
            <span>· {e.nb_questions} questions</span>
          </div>
          <div className="flex flex-wrap gap-4 text-sm mt-3">
            <div className="flex items-center gap-1.5"><Users className="w-4 h-4 text-violet-600" /><strong>{e.nb_reponses}</strong> {t("enquetes.reponses", "réponses")}</div>
            <div className="text-slate-600">{t("enquetes.completion", "Complétion")} <strong>{e.taux_completion_pct}%</strong></div>
          </div>
          {/* Sparkline 7j */}
          <div className="flex items-end gap-0.5 h-8 mt-3">
            {e.sparkline_7j.map((p, i) => (
              <div key={i}
                   className="bg-violet-500 rounded-t flex-1 min-w-[8px]"
                   style={{ height: `${(p.n / maxN) * 100}%`, opacity: p.n ? 1 : 0.15 }}
                   title={`${p.date}: ${p.n}`} />
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-2 flex-shrink-0">
          {e.lien_public && (
            <button onClick={() => onCopier(e.lien_public!)}
                    className="inline-flex items-center justify-center gap-1 px-3 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-medium min-h-[44px]">
              <Copy className="w-4 h-4" />
              {t("enquetes.copier_lien", "Copier lien")}
            </button>
          )}
          {e.lien_public && (
            <a href={e.lien_public} target="_blank" rel="noopener"
               className="inline-flex items-center justify-center gap-1 px-3 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-medium min-h-[44px]">
              <ExternalLink className="w-4 h-4" />
              {t("enquetes.apercu", "Aperçu")}
            </a>
          )}
          <Link to={`/mes-enquetes/${e.etude_id}/analyser`}
                className="inline-flex items-center justify-center gap-1 px-3 py-2 rounded-lg bg-violet-600 hover:bg-violet-700 text-white text-xs font-medium min-h-[44px]">
            <BarChart3 className="w-4 h-4" />
            {t("enquetes.analyser", "Analyser")}
          </Link>
        </div>
      </div>
    </div>
  );
};
