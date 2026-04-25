/**
 * Enquêtes & Études — YukpoPro Web
 * Workflow complet : créer étude → audios terrain → transcription → formulaire collecte
 * → génération IA (XLSForm ODK/KoBoCollect) → analyses multiples → rapport académique
 */
import { useState, useRef, useCallback, useEffect } from "react";
import { useTranslation } from "react-i18next";
import {
  Plus, Upload, Play, FileText, BarChart2, Download, ChevronDown, ChevronUp,
  Mic, Loader2, ClipboardList, Users, MapPin, BookOpen, Wand2, Link,
  Copy, CheckCircle2, AlertCircle, Brain, TrendingUp, MessageSquareText,
  FileSpreadsheet, RefreshCw, Eye, ChevronRight,
} from "lucide-react";
import toast from "react-hot-toast";
import { enquetesApi } from "@/api/client";
import { useEnqueteStore } from "@/store/enqueteStore";
import { DemoBanner } from "@/components/DemoBanner";
import { FormBuilder, type BuilderFormulaire } from "@/components/enquetes/FormBuilder";
import { FormPreview } from "@/components/enquetes/FormPreview";
import { SurveyAnalytics } from "@/components/enquetes/SurveyAnalytics";
import { DictionnaireEditor } from "@/components/enquetes/DictionnaireEditor";
import { PlanAnalyseEditor } from "@/components/enquetes/PlanAnalyseEditor";

// ── Types ──────────────────────────────────────────────────────────────────────

type EtudeStatut = "brouillon" | "transcription" | "analyse" | "rapport_pret";
type EtudeMode   = "qualitatif" | "quantitatif" | "mixte";
type DetailTab   = "audio" | "formulaire" | "analyse" | "rapport";

interface Etude {
  etude_id: string; titre: string; mode: EtudeMode; methodologie: string;
  terrain: string; statut: EtudeStatut; n_transcriptions: number; n_reponses: number;
}
interface EtudeDetail extends Etude {
  contexte: string; questions_recherche: string[]; population_cible: string;
  n_themes: number; has_analyse: boolean; has_rapport: boolean; graphiques_disponibles: string[];
}
interface Transcription {
  locuteur: string; fichier: string; date_collecte: string;
  duree_estimee_min: number; extrait: string; longueur: number;
}
interface Theme {
  code: string; libelle: string; frequence: number; citations: string[]; sentiment: string;
}
interface AnalyseIntelligente {
  hypotheses: string[]; note_methodologique: string; plan_analyse: string;
  croisements_cibles: any[]; analyses_descriptives: any[]; graphiques: Record<string, string>;
}

const METHODOLOGIES = [
  { value: "exploratoire",     label: "Exploratoire",               desc: "Découvrir un sujet peu documenté" },
  { value: "descriptive",      label: "Descriptive",                desc: "Décrire et mesurer une situation" },
  { value: "phenomenologique", label: "Phénoménologique",           desc: "Analyser les expériences vécues" },
  { value: "theorie_ancree",   label: "Théorie ancrée",             desc: "Construire une théorie depuis les données" },
  { value: "ethnographique",   label: "Ethnographique",             desc: "Observer un groupe en immersion" },
  { value: "action",           label: "Recherche-action",           desc: "Produire un changement tout en étudiant" },
];
const MODES = [
  { value: "qualitatif",  label: "Qualitatif",  desc: "Entretiens, focus groups, observations" },
  { value: "quantitatif", label: "Quantitatif", desc: "Questionnaires, sondages, formulaires" },
  { value: "mixte",       label: "Mixte",       desc: "Combine entretiens et données chiffrées" },
];

const PIPELINE: { key: EtudeStatut; label: string }[] = [
  { key: "brouillon",    label: "Brouillon" },
  { key: "transcription",label: "Audio traité" },
  { key: "analyse",      label: "Analysé" },
  { key: "rapport_pret", label: "Rapport prêt" },
];
const STATUT_IDX: Record<EtudeStatut, number> = {
  brouillon: 0, transcription: 1, analyse: 2, rapport_pret: 3,
};

// ── Helpers ───────────────────────────────────────────────────────────────────

const btnBase = "flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold transition-all disabled:opacity-40 disabled:cursor-not-allowed";

const inputCls = [
  "w-full rounded-xl px-3 py-2.5 text-sm",
  "text-slate-800 dark:text-slate-100",
  "bg-white dark:bg-white/[0.06]",
  "border border-slate-200 dark:border-white/[0.1]",
  "placeholder-slate-400 dark:placeholder-slate-600",
  "focus:outline-none focus:border-[#0054A6] dark:focus:border-[#0054A6]/70",
  "focus:ring-2 focus:ring-[#0054A6]/10 dark:focus:ring-[#0054A6]/20",
  "transition-colors",
].join(" ");

const labelCls = "block text-sm font-semibold text-slate-700 dark:text-slate-200 mb-1.5";

const sentimentColor = (s: string) => ({
  positif: "#22C55E", négatif: "#EF4444", neutre: "#60A5FA", mixte: "#F59E0B",
}[s] ?? "#94A3B8");

// ── Composant principal ────────────────────────────────────────────────────────

export const EnquetesPage = () => {
  const { t } = useTranslation();
  // Store persistant (survit aux navigations)
  const expandedId      = useEnqueteStore(s => s.expandedId);
  const setExpanded     = useEnqueteStore(s => s.setExpandedId);
  const activeTab       = useEnqueteStore(s => s.activeTab);
  const setActiveTab    = useEnqueteStore(s => s.setActiveTab);
  const formView        = useEnqueteStore(s => s.formView);
  const setFormView     = useEnqueteStore(s => s.setFormView);
  const genIAMode       = useEnqueteStore(s => s.genIAMode);
  const setGenIAMode    = useEnqueteStore(s => s.setGenIAMode);
  const form            = useEnqueteStore(s => s.createForm);
  const setForm         = useEnqueteStore(s => s.setCreateForm);
  const patchForm       = useEnqueteStore(s => s.patchCreateForm);
  const genIAForm       = useEnqueteStore(s => s.genIAForm);
  const setGenIAForm    = useEnqueteStore(s => s.setGenIAForm);
  const patchGenIAForm  = useEnqueteStore(s => s.patchGenIAForm);
  const protocoleParams = useEnqueteStore(s => s.protocoleParams);
  const setProtocoleParams = useEnqueteStore(s => s.setProtocoleParams);
  const patchProtocoleParams = useEnqueteStore(s => s.patchProtocoleParams);
  const formulaire      = useEnqueteStore(s => s.formulaire);
  const setFormulaire   = useEnqueteStore(s => s.setFormulaire);
  const analyseResult   = useEnqueteStore(s => s.analyseResult);
  const setAnalyseResult= useEnqueteStore(s => s.setAnalyseResult);
  const analyseType     = useEnqueteStore(s => s.analyseType);
  const setAnalyseType  = useEnqueteStore(s => s.setAnalyseType);
  const rapport         = useEnqueteStore(s => s.rapport);
  const setRapport      = useEnqueteStore(s => s.setRapport);
  const resetEtudeContext = useEnqueteStore(s => s.resetEtudeContext);

  const [etudes,     setEtudes]     = useState<Etude[]>([]);
  const [loaded,     setLoaded]     = useState(false);
  const [loading,    setLoading]    = useState(false);
  const [detail,     setDetail]     = useState<EtudeDetail | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const [transcriptions, setTranscriptions] = useState<Transcription[]>([]);
  const [uploading,      setUploading]      = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const [generatingForm,   setGeneratingForm]    = useState(false);
  const [formDonnees,      setFormDonnees]       = useState<any | null>(null);
  const [copied,           setCopied]            = useState(false);
  const [builderForm,      setBuilderForm]       = useState<BuilderFormulaire | null>(null);
  const [loadingBuilder,   setLoadingBuilder]    = useState(false);
  const [protocoleFile,    setProtocoleFile]    = useState<File | null>(null);
  const [uploadingProt,    setUploadingProt]    = useState(false);
  const protocoleRef = useRef<HTMLInputElement>(null);

  const [analysing,        setAnalysing]         = useState<string | null>(null);
  const [generating,       setGenerating]        = useState(false);
  const [creating, setCreating] = useState(false);

  // ── Chargement ───────────────────────────────────────────────────────────────

  const chargerEtudes = useCallback(async () => {
    setLoading(true);
    try {
      const res = await enquetesApi.lister();
      setEtudes(res.etudes || []);
      setLoaded(true);
    } catch { toast.error(t("enquetes.errorLoad")); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { chargerEtudes(); }, [chargerEtudes]);

  useEffect(() => {
    if (expandedId && !detail) {
      (async () => {
        try {
          const [d, tr] = await Promise.all([
            enquetesApi.getEtude(expandedId),
            enquetesApi.listerTranscriptions(expandedId).catch(() => ({ transcriptions: [] })),
          ]);
          setDetail(d);
          setTranscriptions(tr.transcriptions || []);
        } catch { }
      })();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const ouvrirEtude = async (etude: Etude) => {
    if (expandedId === etude.etude_id) { setExpanded(null); setDetail(null); return; }
    setExpanded(etude.etude_id);
    resetEtudeContext();
    setTranscriptions([]); setFormDonnees(null);
    try {
      const [d, tr] = await Promise.all([
        enquetesApi.getEtude(etude.etude_id),
        enquetesApi.listerTranscriptions(etude.etude_id).catch(() => ({ transcriptions: [] })),
      ]);
      setDetail(d);
      setTranscriptions(tr.transcriptions || []);
    } catch { toast.error(t("enquetes.errorStudy")); }
  };

  const refreshDetail = async (id: string) => {
    try {
      const [d, tr] = await Promise.all([
        enquetesApi.getEtude(id),
        enquetesApi.listerTranscriptions(id).catch(() => ({ transcriptions: [] })),
      ]);
      setDetail(d);
      setTranscriptions(tr.transcriptions || []);
      setEtudes(prev => prev.map(e => e.etude_id === id ? { ...e, ...d } : e));
    } catch {}
  };

  // ── Création étude ────────────────────────────────────────────────────────────

  const creerEtude = async () => {
    if (!form.titre.trim()) { toast.error(t("enquetes.titleRequired")); return; }
    setCreating(true);
    try {
      await enquetesApi.creer({
        titre: form.titre, contexte: form.contexte, methodologie: form.methodologie,
        mode: form.mode, population_cible: form.population_cible, terrain: form.terrain,
        questions_recherche: form.questions_recherche.split("\n").map(s => s.trim()).filter(Boolean),
      });
      toast.success(t("enquetes.studyCreated"));
      setShowCreate(false);
      setForm({ titre: "", contexte: "", methodologie: "exploratoire", mode: "qualitatif", population_cible: "", terrain: "", questions_recherche: "" });
      chargerEtudes();
    } catch (err: any) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;
      if (status === 402) {
        const msg = typeof detail === "object" ? detail?.message : detail;
        toast.error(`Crédits insuffisants — ${msg || "Rechargez votre compte"}`);
      } else if (status === 422) {
        const fields = Array.isArray(detail)
          ? detail.map((d: any) => `${d.loc?.slice(-1)[0]}: ${d.msg}`).join(", ")
          : "Vérifiez les champs obligatoires";
        toast.error(`Données invalides — ${fields}`);
      } else {
        const msg = typeof detail === "string" ? detail : (err?.message ?? "Erreur serveur");
        toast.error(`Erreur ${status ?? ""}: ${msg}`.slice(0, 200));
      }
    }
    finally { setCreating(false); }
  };

  // ── Audio ─────────────────────────────────────────────────────────────────────

  const uploaderAudio = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !expandedId) return;
    setUploading(true);
    toast("Transcription Yukpo en cours…", { icon: "🎙️", duration: 10000 });
    try {
      const res = await enquetesApi.uploaderAudio(expandedId, file);
      toast.dismiss();
      toast.success(`Transcription terminée — ${res.duree_estimee_min} min enregistrées`);
      await refreshDetail(expandedId);
    } catch (err: any) {
      toast.dismiss();
      toast.error(err?.response?.data?.detail || "Erreur transcription");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  // ── Formulaire ────────────────────────────────────────────────────────────────

  const genererFormulaireIA = async () => {
    if (!genIAForm.titre || !genIAForm.description) { toast.error("Titre et description requis"); return; }
    setGeneratingForm(true);
    toast("Yukpo génère votre formulaire professionnel…", { icon: "✨", duration: 15000 });
    try {
      const res = await enquetesApi.genererFormulaireIa({
        ...genIAForm,
        creer_dans_etude: expandedId ?? undefined,
      });
      toast.dismiss();
      toast.success(`Formulaire "${res.titre_formulaire}" généré — ${res.questions?.length || 0} questions`);
      setFormulaire(res);
      setGenIAMode(false);
      if (expandedId) await refreshDetail(expandedId);
    } catch (err: any) {
      toast.dismiss();
      toast.error(err?.response?.data?.detail || "Erreur génération formulaire");
    } finally { setGeneratingForm(false); }
  };

  const chargerDonnees = async () => {
    if (!expandedId) return;
    try {
      const d = await enquetesApi.donneesFormulaire(expandedId);
      setFormDonnees(d);
    } catch { toast.error("Aucune donnée ou formulaire non créé"); }
  };

  const extraireFormulaireId = (f: any): string | null => {
    if (!f) return null;
    if (f.formulaire_id) return f.formulaire_id;
    if (f.lien_collecte) {
      const m = String(f.lien_collecte).match(/\/formulaire\/([a-f0-9-]+)/i);
      if (m) return m[1];
    }
    return null;
  };

  const ouvrirBuilder = async (view: "builder" | "preview" | "analytics" | "dictionnaire" | "plan") => {
    if (view === "dictionnaire" || view === "plan") {
      setFormView(view);
      return;
    }
    const fid = extraireFormulaireId(formulaire);
    if (!fid) { toast.error("Formulaire non disponible"); return; }
    setLoadingBuilder(true);
    try {
      const full = await enquetesApi.getFormulairePublic(fid);
      setBuilderForm({
        formulaire_id: full.formulaire_id,
        titre: full.titre,
        description: full.description || "",
        questions: full.questions || [],
      });
      if (view === "analytics") await chargerDonnees();
      setFormView(view);
    } catch {
      toast.error("Impossible de charger le formulaire");
    } finally { setLoadingBuilder(false); }
  };

  const telechargerQuestionnaireDocx = async () => {
    if (!expandedId) return;
    const url = enquetesApi.questionnaireDocxUrl(expandedId);
    const token = localStorage.getItem("yukpopro_token");
    try {
      const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "questionnaire.docx";
      document.body.appendChild(a); a.click(); a.remove();
    } catch { toast.error("Téléchargement impossible"); }
  };

  const uploaderProtocole = async () => {
    if (!protocoleFile || !expandedId) { toast.error("Sélectionnez un fichier"); return; }
    if (!protocoleParams.titre.trim()) { toast.error("Titre du formulaire requis"); return; }
    setUploadingProt(true);
    toast("Yukpo analyse votre protocole…", { icon: "📄", duration: 30000 });
    try {
      const res = await enquetesApi.uploadProtocole(expandedId, protocoleFile, protocoleParams);
      toast.dismiss();
      toast.success(`Formulaire généré — ${res.n_questions} questions. XLSForm dans Mes Documents.`);
      setFormulaire({
        titre_formulaire: res.titre_formulaire,
        questions: Array(res.n_questions).fill({}),
        lien_xlsform: res.lien_xlsform,
        lien_collecte: res.lien_collecte,
        sections_metadata: [],
      });
      setProtocoleFile(null);
      setProtocoleParams({ titre: "", objectif: "", population: "", n_questions: 20 });
      if (protocoleRef.current) protocoleRef.current.value = "";
      if (expandedId) await refreshDetail(expandedId);
    } catch (err: any) {
      toast.dismiss();
      toast.error(err?.response?.data?.detail || "Erreur analyse protocole");
    } finally { setUploadingProt(false); }
  };

  const copierLien = (lien: string) => {
    navigator.clipboard.writeText(window.location.origin + lien);
    setCopied(true);
    toast.success("Lien copié !");
    setTimeout(() => setCopied(false), 2000);
  };

  // ── Analyses ─────────────────────────────────────────────────────────────────

  const lancerAnalyse = async (type: "qualitative" | "quantitative" | "intelligente" | "commentaires") => {
    if (!expandedId) return;
    setAnalysing(type);
    setAnalyseType(type);
    const labels: Record<string, string> = {
      qualitative: "Codage thématique Yukpo…",
      quantitative: "Analyse statistique en cours…",
      intelligente: "Yukpo sélectionne les analyses pertinentes…",
      commentaires: "Analyse des questions ouvertes…",
    };
    toast(labels[type], { icon: "🔍", duration: 20000 });
    try {
      let res;
      if (type === "qualitative")  res = await enquetesApi.analyser(expandedId);
      else if (type === "quantitative") res = await enquetesApi.analyserQuantitatif(expandedId);
      else if (type === "intelligente") res = await enquetesApi.analyserIntelligent(expandedId);
      else res = await enquetesApi.analyserCommentaires(expandedId);
      toast.dismiss();
      toast.success("Analyse terminée !");
      setAnalyseResult(res);
      await refreshDetail(expandedId);
    } catch (err: any) {
      toast.dismiss();
      toast.error(err?.response?.data?.detail || "Erreur analyse");
    } finally { setAnalysing(null); }
  };

  // ── Rapport ───────────────────────────────────────────────────────────────────

  const genererRapport = async () => {
    if (!expandedId) return;
    setGenerating(true);
    toast("Génération du rapport académique…", { icon: "📄", duration: 30000 });
    try {
      const r = await enquetesApi.genererRapport(expandedId, "docx");
      toast.dismiss();
      toast.success(r.fichier_id_bureau
        ? "Rapport prêt — sauvegardé dans Mes Documents !"
        : "Rapport prêt !");
      setRapport(r);
      await refreshDetail(expandedId);
    } catch (err: any) {
      toast.dismiss();
      toast.error(err?.response?.data?.detail || "Erreur rapport");
    } finally { setGenerating(false); }
  };

  const telechargerDocx = async () => {
    if (!expandedId) return;
    toast("Génération Word en cours…", { icon: "📝" });
    try {
      const r = await enquetesApi.genererRapport(expandedId, "docx");
      if (r.fichier_docx) {
        const a = document.createElement("a");
        a.href = `data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,${r.fichier_docx}`;
        a.download = `rapport_${detail?.titre?.slice(0, 30) || "etude"}.docx`;
        a.click();
      }
    } catch { toast.error("Erreur génération Word"); }
  };

  const statutIdx = (s: EtudeStatut) => STATUT_IDX[s] ?? 0;

  // ── Rendu ─────────────────────────────────────────────────────────────────────

  return (
    <div
      className="flex flex-col h-full overflow-hidden"
      style={{ background: "var(--ykp-canvas)" }}
    >
      <DemoBanner className="mx-6 mt-4" />

      {/* ── Header ── */}
      <div
        className="flex-shrink-0 px-6 py-4 border-b"
        style={{ borderColor: "var(--ykp-border)" }}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold" style={{ color: "var(--ykp-text-primary)" }}>
              {t("enquetes.title")}
            </h1>
            <p className="text-xs mt-0.5" style={{ color: "var(--ykp-text-muted)" }}>
              {t("enquetes.subtitle")}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {loaded && etudes.length > 0 && (
              <div
                className="hidden sm:flex items-center gap-4 text-xs rounded-xl px-4 py-2 border"
                style={{ color: "var(--ykp-text-muted)", borderColor: "var(--ykp-border)", background: "var(--ykp-surface)" }}
              >
                <span>
                  <span className="font-semibold" style={{ color: "var(--ykp-text-primary)" }}>{etudes.length}</span>
                  {" "}{t("enquetes.studies")}
                </span>
                <span>
                  <span className="text-green-600 dark:text-green-400 font-semibold">{etudes.filter(e => e.statut === "rapport_pret").length}</span>
                  {" "}{t("enquetes.reports")}
                </span>
                <span>
                  <span className="text-[#0054A6] dark:text-blue-400 font-semibold">{etudes.reduce((s, e) => s + e.n_transcriptions, 0)}</span>
                  {" "}{t("enquetes.audios")}
                </span>
              </div>
            )}
            <button
              onClick={() => setShowCreate(!showCreate)}
              className={`${btnBase} text-white shadow-sm`}
              style={{ background: "linear-gradient(135deg,#0054A6,#0083d6)" }}
            >
              <Plus className="w-4 h-4" /> {t("enquetes.newStudy")}
            </button>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-3">

        {/* ── Formulaire création ── */}
        {showCreate && (
          <div
            className="rounded-2xl border p-5 space-y-4 shadow-sm"
            style={{
              background: "var(--ykp-surface)",
              borderColor: "#0054A6",
              borderWidth: 1,
              boxShadow: "0 0 0 3px rgba(0,84,166,0.07)",
            }}
          >
            <div className="flex items-center gap-2 pb-3 border-b" style={{ borderColor: "var(--ykp-border)" }}>
              <div className="w-7 h-7 rounded-lg bg-[#0054A6]/10 flex items-center justify-center">
                <Plus className="w-4 h-4 text-[#0054A6]" />
              </div>
              <h2 className="text-sm font-bold" style={{ color: "var(--ykp-text-primary)" }}>
                {t("enquetes.newStudyTitle")}
              </h2>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className={labelCls}>{t("enquetes.form.title")} <span className="text-[#0054A6]">*</span></label>
                <input
                  className={inputCls}
                  placeholder="Perceptions des services de santé au Cameroun"
                  value={form.titre}
                  onChange={e => patchForm({ titre: e.target.value })}
                />
              </div>
              <div>
                <label className={labelCls}>{t("enquetes.form.terrain")}</label>
                <input
                  className={inputCls}
                  placeholder="Yaoundé — quartiers périphériques"
                  value={form.terrain}
                  onChange={e => patchForm({ terrain: e.target.value })}
                />
              </div>
              <div>
                <label className={labelCls}>{t("enquetes.form.methodologie")}</label>
                <select
                  className={inputCls}
                  value={form.methodologie}
                  onChange={e => patchForm({ methodologie: e.target.value })}
                >
                  {METHODOLOGIES.map(m => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </select>
                {METHODOLOGIES.find(m => m.value === form.methodologie)?.desc && (
                  <p className="mt-1 text-xs" style={{ color: "var(--ykp-text-muted)" }}>
                    {METHODOLOGIES.find(m => m.value === form.methodologie)?.desc}
                  </p>
                )}
              </div>
              <div>
                <label className={labelCls}>{t("enquetes.form.modeEtude")}</label>
                <div className="flex gap-2">
                  {MODES.map(m => (
                    <button
                      key={m.value}
                      onClick={() => patchForm({ mode: m.value })}
                      className={`flex-1 py-2.5 rounded-xl text-xs font-semibold transition-all border ${
                        form.mode === m.value
                          ? "bg-[#0054A6] text-white border-[#0054A6] shadow-sm"
                          : "text-slate-500 dark:text-slate-400 border-slate-200 dark:border-white/[0.1] hover:border-[#0054A6]/50 hover:text-[#0054A6] dark:hover:text-blue-400"
                      }`}
                      style={form.mode !== m.value ? { background: "var(--ykp-input-bg)" } : undefined}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="md:col-span-2">
                <label className={labelCls}>{t("enquetes.form.population")}</label>
                <input
                  className={inputCls}
                  placeholder="Femmes rurales 25–45 ans, ménages à faible revenu"
                  value={form.population_cible}
                  onChange={e => patchForm({ population_cible: e.target.value })}
                />
              </div>
              <div className="md:col-span-2">
                <label className={labelCls}>{t("enquetes.form.contexte")}</label>
                <textarea
                  rows={2}
                  className={inputCls + " resize-none"}
                  placeholder="Décrivez la problématique, le contexte et les objectifs de votre étude…"
                  value={form.contexte}
                  onChange={e => patchForm({ contexte: e.target.value })}
                />
              </div>
              <div className="md:col-span-2">
                <label className={labelCls}>
                  {t("enquetes.form.questions")}
                  <span className="ml-1.5 text-xs font-normal px-1.5 py-0.5 rounded-md" style={{ background: "rgba(0,84,166,0.1)", color: "#0054A6" }}>
                    Axes de recherche — pas les questions du formulaire
                  </span>
                </label>
                <textarea
                  rows={3}
                  className={inputCls + " resize-none"}
                  placeholder={"Quels sont les obstacles à l'accès aux soins ?\nComment les ménages gèrent-ils les dépenses de santé ?"}
                  value={form.questions_recherche}
                  onChange={e => patchForm({ questions_recherche: e.target.value })}
                />
                <p className="mt-1 text-xs" style={{ color: "var(--ykp-text-muted)" }}>
                  Ce sont les grandes questions scientifiques qui guident l'étude. Les questions du formulaire de collecte se créent à l'étape suivante.
                </p>
              </div>
            </div>

            <div className="flex gap-2 pt-1">
              <button
                onClick={creerEtude}
                disabled={creating}
                className={`${btnBase} text-white shadow-sm`}
                style={{ background: "#0054A6" }}
              >
                {creating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                {creating ? t("enquetes.creating") : t("enquetes.create")}
              </button>
              <button
                onClick={() => setShowCreate(false)}
                className={`${btnBase} border`}
                style={{ color: "var(--ykp-text-muted)", borderColor: "var(--ykp-border)", background: "var(--ykp-input-bg)" }}
              >
                {t("common.cancel")}
              </button>
            </div>
          </div>
        )}

        {/* ── États de chargement ── */}
        {loading && !loaded && (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-8 h-8 text-[#0054A6] animate-spin" />
          </div>
        )}
        {loaded && etudes.length === 0 && (
          <div className="text-center py-20">
            <div
              className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-sm"
              style={{ background: "var(--ykp-surface)", border: "1px solid var(--ykp-border)" }}
            >
              <BookOpen className="w-7 h-7 text-slate-400 dark:text-slate-600" />
            </div>
            <p className="text-sm font-medium" style={{ color: "var(--ykp-text-secondary)" }}>
              {t("enquetes.noStudies")}
            </p>
            <p className="text-xs mt-1" style={{ color: "var(--ykp-text-muted)" }}>
              Cliquez sur « + Nouvelle étude » pour commencer
            </p>
          </div>
        )}

        {/* ── Liste des études ── */}
        {etudes.map(etude => {
          const isOpen = expandedId === etude.etude_id;
          const idx = statutIdx(etude.statut);
          const statutColors = [
            { text: "#94a3b8", bg: "rgba(148,163,184,0.08)", border: "rgba(148,163,184,0.2)" },
            { text: "#fbbf24", bg: "rgba(251,191,36,0.08)",  border: "rgba(251,191,36,0.2)" },
            { text: "#60a5fa", bg: "rgba(96,165,250,0.08)",  border: "rgba(96,165,250,0.2)" },
            { text: "#4ade80", bg: "rgba(74,222,128,0.08)",  border: "rgba(74,222,128,0.2)" },
          ][idx] ?? { text: "#94a3b8", bg: "rgba(148,163,184,0.08)", border: "rgba(148,163,184,0.2)" };

          return (
            <div
              key={etude.etude_id}
              className="rounded-2xl border overflow-hidden shadow-sm transition-shadow hover:shadow-md"
              style={{ background: "var(--ykp-surface)", borderColor: isOpen ? "#0054A6" : "var(--ykp-border)" }}
            >
              {/* En-tête carte */}
              <button
                className="w-full flex items-start gap-4 px-5 py-4 text-left transition-colors"
                style={{ background: isOpen ? "rgba(0,84,166,0.03)" : undefined }}
                onClick={() => ouvrirEtude(etude)}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 mb-2">
                    <span className="text-sm font-semibold" style={{ color: "var(--ykp-text-primary)" }}>
                      {etude.titre}
                    </span>
                    <span
                      className="text-xs px-2 py-0.5 rounded-full border font-medium"
                      style={{ color: statutColors.text, background: statutColors.bg, borderColor: statutColors.border }}
                    >
                      {PIPELINE[idx]?.label}
                    </span>
                    <span
                      className="text-xs px-2 py-0.5 rounded-full border"
                      style={{ color: "var(--ykp-text-muted)", background: "var(--ykp-canvas)", borderColor: "var(--ykp-border)" }}
                    >
                      {etude.mode}
                    </span>
                  </div>
                  {/* Pipeline visuel */}
                  <div className="flex items-center gap-1 mt-1">
                    {PIPELINE.map((step, i) => (
                      <div key={step.key} className="flex items-center gap-1">
                        <div
                          className="h-1.5 rounded-full transition-all"
                          style={{
                            width: i <= idx ? 28 : 16,
                            background: i <= idx ? "#0054A6" : "var(--ykp-border)",
                          }}
                        />
                        {i < PIPELINE.length - 1 && (
                          <ChevronRight className="w-3 h-3" style={{ color: "var(--ykp-border)" }} />
                        )}
                      </div>
                    ))}
                    <span className="text-xs ml-2" style={{ color: "var(--ykp-text-faint)" }}>
                      {etude.n_transcriptions > 0 && `${etude.n_transcriptions} audio · `}
                      {etude.n_reponses > 0 && `${etude.n_reponses} réponses`}
                      {etude.terrain && ` · ${etude.terrain}`}
                    </span>
                  </div>
                </div>
                {isOpen
                  ? <ChevronUp className="w-4 h-4 flex-shrink-0 mt-0.5" style={{ color: "#0054A6" }} />
                  : <ChevronDown className="w-4 h-4 flex-shrink-0 mt-0.5" style={{ color: "var(--ykp-text-faint)" }} />
                }
              </button>

              {/* Panneau détail */}
              {isOpen && detail && detail.etude_id === etude.etude_id && (
                <div className="border-t" style={{ borderColor: "var(--ykp-border)" }}>

                  {/* Onglets */}
                  <div
                    className="flex border-b overflow-x-auto"
                    style={{ borderColor: "var(--ykp-border)", background: "var(--ykp-canvas)" }}
                  >
                    {(["audio", "formulaire", "analyse", "rapport"] as DetailTab[]).map(tab => {
                      const labels: Record<DetailTab, string> = {
                        audio:      `🎙 ${t("enquetes.tabs.audio")}`,
                        formulaire: `📋 ${t("enquetes.tabs.formulaire")}`,
                        analyse:    `🔍 ${t("enquetes.tabs.analyse")}`,
                        rapport:    `📄 ${t("enquetes.tabs.rapport")}`,
                      };
                      const alerts: Record<DetailTab, boolean> = {
                        audio:      detail.n_transcriptions === 0,
                        formulaire: detail.mode !== "qualitatif" && detail.n_reponses === 0,
                        analyse:    !detail.has_analyse && detail.n_transcriptions > 0,
                        rapport:    detail.has_analyse && !detail.has_rapport,
                      };
                      const isActive = activeTab === tab;
                      return (
                        <button
                          key={tab}
                          onClick={() => setActiveTab(tab)}
                          className="px-4 py-3 text-xs font-semibold transition-all border-b-2 relative whitespace-nowrap flex-shrink-0"
                          style={{
                            color: isActive ? "#0054A6" : "var(--ykp-text-muted)",
                            borderBottomColor: isActive ? "#0054A6" : "transparent",
                          }}
                        >
                          {labels[tab]}
                          {alerts[tab] && (
                            <span className="absolute top-2 right-1 w-1.5 h-1.5 rounded-full bg-[#0054A6]" />
                          )}
                        </button>
                      );
                    })}
                  </div>

                  <div className="p-5 space-y-4">

                    {/* ── Onglet Audio ── */}
                    {activeTab === "audio" && (
                      <div className="space-y-4">
                        {detail.questions_recherche.length > 0 && (
                          <div
                            className="rounded-xl border p-4"
                            style={{ background: "var(--ykp-canvas)", borderColor: "var(--ykp-border)" }}
                          >
                            <p
                              className="text-xs mb-2 font-semibold uppercase tracking-wide"
                              style={{ color: "var(--ykp-text-muted)" }}
                            >
                              Questions de recherche
                            </p>
                            <ul className="space-y-1.5">
                              {detail.questions_recherche.map((q, i) => (
                                <li key={i} className="text-xs flex gap-2" style={{ color: "var(--ykp-text-secondary)" }}>
                                  <span className="font-bold shrink-0 text-[#0054A6]">{i + 1}.</span>{q}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Zone upload audio */}
                        <div
                          className="border-2 border-dashed rounded-xl p-8 text-center cursor-pointer group transition-all"
                          style={{ borderColor: uploading ? "#0054A6" : "var(--ykp-border)" }}
                          onClick={() => !uploading && fileRef.current?.click()}
                        >
                          <input ref={fileRef} type="file" accept="audio/*,.m4a,.wav,.mp3,.ogg,.webm" className="hidden" onChange={uploaderAudio} />
                          {uploading ? (
                            <div className="flex flex-col items-center gap-2">
                              <Loader2 className="w-8 h-8 text-[#0054A6] animate-spin" />
                              <p className="text-xs font-medium" style={{ color: "var(--ykp-text-secondary)" }}>
                                Transcription Yukpo en cours…
                              </p>
                            </div>
                          ) : (
                            <div className="flex flex-col items-center gap-2">
                              <div className="w-12 h-12 rounded-xl bg-[#0054A6]/08 flex items-center justify-center group-hover:bg-[#0054A6]/15 transition-all">
                                <Upload className="w-5 h-5 text-[#0054A6]" />
                              </div>
                              <p className="text-sm font-semibold" style={{ color: "var(--ykp-text-secondary)" }}>
                                {t("enquetes.audio.uploadAudio")}
                              </p>
                              <p className="text-xs" style={{ color: "var(--ykp-text-muted)" }}>
                                {t("enquetes.audio.uploadDesc")}
                              </p>
                            </div>
                          )}
                        </div>

                        {transcriptions.length > 0 && (
                          <div>
                            <p className="text-xs mb-2 font-semibold uppercase tracking-wide" style={{ color: "var(--ykp-text-muted)" }}>
                              {transcriptions.length} entretien(s) transcrit(s)
                            </p>
                            <div className="space-y-2">
                              {transcriptions.map((tr, i) => (
                                <div
                                  key={i}
                                  className="rounded-xl border p-3"
                                  style={{ background: "var(--ykp-canvas)", borderColor: "var(--ykp-border)" }}
                                >
                                  <div className="flex items-center justify-between mb-1">
                                    <span className="text-xs font-semibold" style={{ color: "var(--ykp-text-primary)" }}>
                                      {tr.locuteur}
                                    </span>
                                    <span className="text-xs" style={{ color: "var(--ykp-text-muted)" }}>
                                      {tr.duree_estimee_min} min · {(tr.longueur / 1000).toFixed(1)}k car.
                                    </span>
                                  </div>
                                  <p className="text-xs italic line-clamp-2" style={{ color: "var(--ykp-text-secondary)" }}>
                                    « {tr.extrait} »
                                  </p>
                                  {tr.date_collecte && (
                                    <p className="text-xs mt-1" style={{ color: "var(--ykp-text-faint)" }}>
                                      {tr.date_collecte}
                                    </p>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {transcriptions.length === 0 && (
                          <div
                            className="flex items-center gap-2 text-xs rounded-xl p-3 border"
                            style={{ color: "var(--ykp-text-muted)", background: "var(--ykp-canvas)", borderColor: "var(--ykp-border)" }}
                          >
                            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                            {t("enquetes.audio.noAudio")}
                          </div>
                        )}
                      </div>
                    )}

                    {/* ── Onglet Formulaire ── */}
                    {activeTab === "formulaire" && (
                      <div className="space-y-4">
                        {detail.mode === "qualitatif" ? (
                          <div
                            className="rounded-xl border p-4 text-center"
                            style={{ background: "var(--ykp-canvas)", borderColor: "var(--ykp-border)" }}
                          >
                            <p className="text-xs" style={{ color: "var(--ykp-text-secondary)" }}>
                              En mode <strong>qualitatif pur</strong>, la collecte se fait via entretiens audio (onglet Audios).
                              Passez en mode <strong>quantitatif</strong> ou <strong>mixte</strong> pour activer les formulaires.
                            </p>
                          </div>
                        ) : (
                          <>
                            {!genIAMode && !formulaire && (
                              <div className="space-y-3">
                                {/* Option A — Upload protocole */}
                                <div
                                  className="rounded-xl border p-4"
                                  style={{ background: "rgba(34,197,94,0.04)", borderColor: "rgba(34,197,94,0.25)" }}
                                >
                                  <div className="flex items-center gap-3 mb-3">
                                    <div className="w-9 h-9 rounded-lg bg-green-500/15 flex items-center justify-center shrink-0">
                                      <Upload className="w-4 h-4 text-green-600 dark:text-green-400" />
                                    </div>
                                    <div>
                                      <p className="text-sm font-semibold" style={{ color: "var(--ykp-text-primary)" }}>
                                        Option 1 — Uploader votre protocole{" "}
                                        <span className="text-green-600 dark:text-green-400 text-xs font-medium">(recommandé)</span>
                                      </p>
                                      <p className="text-xs mt-0.5" style={{ color: "var(--ykp-text-muted)" }}>
                                        PDF / DOCX / TXT — Yukpo extrait les objectifs, la population, les variables, et construit automatiquement le formulaire XLSForm
                                      </p>
                                    </div>
                                  </div>

                                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                                    <div>
                                      <label className={labelCls}>Titre du formulaire <span className="text-[#0054A6]">*</span></label>
                                      <input className={inputCls} placeholder="Enquête ménages 2026" value={protocoleParams.titre} onChange={e => patchProtocoleParams({ titre: e.target.value })} />
                                    </div>
                                    <div>
                                      <label className={labelCls}>Population cible</label>
                                      <input className={inputCls} placeholder="Auto-détecté depuis le protocole" value={protocoleParams.population} onChange={e => patchProtocoleParams({ population: e.target.value })} />
                                    </div>
                                    <div className="md:col-span-2">
                                      <label className={labelCls}>Objectif de l'étude</label>
                                      <input className={inputCls} placeholder="Auto-détecté depuis le protocole" value={protocoleParams.objectif} onChange={e => patchProtocoleParams({ objectif: e.target.value })} />
                                    </div>
                                    <div>
                                      <label className={labelCls}>Nombre de questions</label>
                                      <input type="number" min={5} max={60} className={inputCls} value={protocoleParams.n_questions} onChange={e => patchProtocoleParams({ n_questions: +e.target.value })} />
                                    </div>
                                  </div>

                                  <input ref={protocoleRef} type="file" accept=".pdf,.docx,.doc,.txt" className="hidden" onChange={e => setProtocoleFile(e.target.files?.[0] ?? null)} />
                                  <div className="flex items-center gap-2 flex-wrap">
                                    <button
                                      onClick={() => protocoleRef.current?.click()}
                                      className={`${btnBase} text-green-700 dark:text-green-400 border border-green-500/30 hover:bg-green-500/[0.08]`}
                                      style={{ background: "var(--ykp-input-bg)" }}
                                    >
                                      <FileText className="w-3.5 h-3.5" />
                                      {protocoleFile ? protocoleFile.name.slice(0, 40) : "Choisir fichier PDF/DOCX"}
                                    </button>
                                    {protocoleFile && (
                                      <button
                                        onClick={uploaderProtocole}
                                        disabled={uploadingProt}
                                        className={`${btnBase} text-white shadow-sm`}
                                        style={{ background: "#22C55E" }}
                                      >
                                        {uploadingProt ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Wand2 className="w-3.5 h-3.5" />}
                                        {uploadingProt ? "Analyse…" : "Analyser & générer"}
                                      </button>
                                    )}
                                  </div>
                                </div>

                                {/* Option B — Description manuelle */}
                                <button
                                  onClick={() => setGenIAMode(true)}
                                  className="w-full flex items-center gap-4 p-4 rounded-xl border transition-all text-left group"
                                  style={{
                                    background: "rgba(0,84,166,0.04)",
                                    borderColor: "rgba(0,84,166,0.2)",
                                  }}
                                >
                                  <div className="w-10 h-10 rounded-xl bg-[#0054A6]/10 flex items-center justify-center shrink-0 group-hover:bg-[#0054A6]/20 transition-all">
                                    <Wand2 className="w-5 h-5 text-[#0054A6]" />
                                  </div>
                                  <div className="flex-1">
                                    <p className="text-sm font-semibold" style={{ color: "var(--ykp-text-primary)" }}>
                                      Option 2 — Décrire le sujet manuellement
                                    </p>
                                    <p className="text-xs mt-0.5" style={{ color: "var(--ykp-text-muted)" }}>
                                      Si vous n'avez pas encore de protocole — renseignez juste le contexte, Yukpo génère le formulaire professionnel
                                    </p>
                                  </div>
                                  <ChevronRight className="w-4 h-4 shrink-0 group-hover:translate-x-1 transition-transform" style={{ color: "var(--ykp-text-faint)" }} />
                                </button>
                              </div>
                            )}

                            {/* Génération IA manuelle */}
                            {genIAMode && (
                              <div
                                className="rounded-xl border p-4 space-y-3"
                                style={{ background: "rgba(0,84,166,0.04)", borderColor: "rgba(0,84,166,0.2)" }}
                              >
                                <div className="flex items-center gap-2 mb-1">
                                  <Wand2 className="w-4 h-4 text-[#0054A6]" />
                                  <span className="text-sm font-bold" style={{ color: "var(--ykp-text-primary)" }}>
                                    Génération Yukpo
                                  </span>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                  <div>
                                    <label className={labelCls}>Titre du formulaire <span className="text-[#0054A6]">*</span></label>
                                    <input className={inputCls} placeholder="Enquête satisfaction soins primaires" value={genIAForm.titre} onChange={e => patchGenIAForm({ titre: e.target.value })} />
                                  </div>
                                  <div>
                                    <label className={labelCls}>Population cible <span className="text-[#0054A6]">*</span></label>
                                    <input className={inputCls} placeholder="Patients, ménages, bénéficiaires" value={genIAForm.population} onChange={e => patchGenIAForm({ population: e.target.value })} />
                                  </div>
                                  <div className="md:col-span-2">
                                    <label className={labelCls}>Description du sujet <span className="text-[#0054A6]">*</span></label>
                                    <textarea rows={2} className={inputCls + " resize-none"} placeholder="Contexte, thèmes à couvrir, enjeux spécifiques…" value={genIAForm.description} onChange={e => patchGenIAForm({ description: e.target.value })} />
                                  </div>
                                  <div className="md:col-span-2">
                                    <label className={labelCls}>Objectif principal</label>
                                    <input className={inputCls} placeholder="Mesurer la satisfaction, identifier les barrières d'accès…" value={genIAForm.objectif} onChange={e => patchGenIAForm({ objectif: e.target.value })} />
                                  </div>
                                  <div>
                                    <label className={labelCls}>Nombre de questions</label>
                                    <input type="number" min={5} max={40} className={inputCls} value={genIAForm.n_questions} onChange={e => patchGenIAForm({ n_questions: +e.target.value })} />
                                  </div>
                                </div>
                                <div className="flex gap-2 pt-1">
                                  <button
                                    onClick={genererFormulaireIA}
                                    disabled={generatingForm}
                                    className={`${btnBase} text-white shadow-sm`}
                                    style={{ background: "#0054A6" }}
                                  >
                                    {generatingForm ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Wand2 className="w-3.5 h-3.5" />}
                                    {generatingForm ? "Génération en cours…" : "Générer le formulaire"}
                                  </button>
                                  <button
                                    onClick={() => setGenIAMode(false)}
                                    className={`${btnBase} border`}
                                    style={{ color: "var(--ykp-text-muted)", borderColor: "var(--ykp-border)", background: "var(--ykp-input-bg)" }}
                                  >
                                    Annuler
                                  </button>
                                </div>
                              </div>
                            )}

                            {/* Formulaire existant */}
                            {formulaire && (
                              <div className="space-y-3">
                                <div
                                  className="rounded-xl border p-4"
                                  style={{ background: "rgba(34,197,94,0.04)", borderColor: "rgba(34,197,94,0.2)" }}
                                >
                                  <div className="flex items-center justify-between mb-3">
                                    <div className="flex items-center gap-2">
                                      <CheckCircle2 className="w-4 h-4 text-green-600 dark:text-green-400" />
                                      <span className="text-sm font-semibold" style={{ color: "var(--ykp-text-primary)" }}>
                                        {formulaire.titre_formulaire || "Formulaire"}
                                      </span>
                                    </div>
                                    <span className="text-xs" style={{ color: "var(--ykp-text-muted)" }}>
                                      {formulaire.questions?.length || 0} questions
                                    </span>
                                  </div>

                                  <div className="flex flex-wrap gap-2">
                                    {formulaire.lien_xlsform && (
                                      <a href={formulaire.lien_xlsform} download className={`${btnBase} text-green-700 dark:text-green-400 border border-green-500/25 hover:bg-green-500/[0.08]`} style={{ background: "var(--ykp-input-bg)" }}>
                                        <FileSpreadsheet className="w-3.5 h-3.5" /> XLSForm (ODK/KoBoCollect)
                                      </a>
                                    )}
                                    {formulaire.lien_collecte && (
                                      <button onClick={() => copierLien(formulaire.lien_collecte)} className={`${btnBase} text-blue-700 dark:text-blue-400 border border-blue-500/25 hover:bg-blue-500/[0.08]`} style={{ background: "var(--ykp-input-bg)" }}>
                                        {copied ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                                        Copier lien collecte
                                      </button>
                                    )}
                                    <button onClick={chargerDonnees} className={`${btnBase} border`} style={{ color: "var(--ykp-text-secondary)", borderColor: "var(--ykp-border)", background: "var(--ykp-input-bg)" }}>
                                      <RefreshCw className="w-3.5 h-3.5" /> Voir les réponses
                                    </button>
                                    <button disabled={loadingBuilder} onClick={() => ouvrirBuilder("builder")} className={`${btnBase} text-[#0054A6] border border-[#0054A6]/25 hover:bg-[#0054A6]/[0.08]`} style={{ background: "var(--ykp-input-bg)" }}>
                                      <ClipboardList className="w-3.5 h-3.5" /> Éditer les questions
                                    </button>
                                    <button disabled={loadingBuilder} onClick={() => ouvrirBuilder("preview")} className={`${btnBase} border`} style={{ color: "var(--ykp-text-secondary)", borderColor: "var(--ykp-border)", background: "var(--ykp-input-bg)" }}>
                                      <Eye className="w-3.5 h-3.5" /> Aperçu répondant
                                    </button>
                                    <button disabled={loadingBuilder} onClick={() => ouvrirBuilder("analytics")} className={`${btnBase} text-blue-700 dark:text-blue-300 border border-blue-400/25 hover:bg-blue-400/[0.08]`} style={{ background: "var(--ykp-input-bg)" }}>
                                      <BarChart2 className="w-3.5 h-3.5" /> Analytics
                                    </button>
                                    <button onClick={() => ouvrirBuilder("dictionnaire")} className={`${btnBase} text-purple-700 dark:text-purple-300 border border-purple-400/25 hover:bg-purple-400/[0.08]`} style={{ background: "var(--ykp-input-bg)" }}>
                                      <BookOpen className="w-3.5 h-3.5" /> Dictionnaire
                                    </button>
                                    <button onClick={() => ouvrirBuilder("plan")} className={`${btnBase} text-amber-700 dark:text-amber-300 border border-amber-400/25 hover:bg-amber-400/[0.08]`} style={{ background: "var(--ykp-input-bg)" }}>
                                      <FileText className="w-3.5 h-3.5" /> Plan d'analyse
                                    </button>
                                    <button onClick={telechargerQuestionnaireDocx} className={`${btnBase} border`} style={{ color: "var(--ykp-text-secondary)", borderColor: "var(--ykp-border)", background: "var(--ykp-input-bg)" }}>
                                      <Download className="w-3.5 h-3.5" /> Questionnaire Word
                                    </button>
                                  </div>

                                  {formView !== "none" && (
                                    <div className="mt-4 pt-4 border-t space-y-3" style={{ borderColor: "var(--ykp-border)" }}>
                                      <div className="flex items-center justify-between">
                                        <span className="text-xs uppercase tracking-wide font-semibold" style={{ color: "var(--ykp-text-muted)" }}>
                                          {formView === "builder" ? "Éditeur" : formView === "preview" ? "Aperçu" : formView === "analytics" ? "Analyse des réponses" : formView === "dictionnaire" ? "Dictionnaire variables" : "Plan d'analyse"}
                                        </span>
                                        <button onClick={() => setFormView("none")} className="text-xs hover:opacity-80" style={{ color: "var(--ykp-text-muted)" }}>
                                          Fermer ✕
                                        </button>
                                      </div>
                                      {formView === "builder" && builderForm && (
                                        <FormBuilder formulaire={builderForm} onPreview={() => setFormView("preview")} onSaved={upd => setBuilderForm(upd)} />
                                      )}
                                      {formView === "preview" && builderForm && <FormPreview formulaire={builderForm} />}
                                      {formView === "dictionnaire" && expandedId && <DictionnaireEditor etude_id={expandedId} />}
                                      {formView === "plan" && expandedId && <PlanAnalyseEditor etude_id={expandedId} />}
                                      {formView === "analytics" && builderForm && (
                                        <SurveyAnalytics
                                          etude_id={expandedId || ""}
                                          formulaireTitre={builderForm.titre}
                                          questions={builderForm.questions.map((q, i) => ({
                                            question_id: q.question_id || `q_${i}`,
                                            libelle: q.libelle,
                                            type_question: q.type_question,
                                            options: q.options,
                                            name_xlsform: q.name_xlsform,
                                            ordre: q.ordre ?? i,
                                          }))}
                                          reponses={formDonnees?.reponses || []}
                                        />
                                      )}
                                    </div>
                                  )}
                                  <p className="text-[10px] mt-2 flex items-center gap-1" style={{ color: "var(--ykp-text-faint)" }}>
                                    <CheckCircle2 className="w-3 h-3 text-green-500/70" />
                                    Le XLSForm est automatiquement sauvegardé dans <strong>Mes Documents</strong> dès le téléchargement.
                                  </p>
                                </div>

                                {formulaire.sections_metadata?.length > 0 && (
                                  <div>
                                    <p className="text-xs mb-2 font-semibold uppercase tracking-wide" style={{ color: "var(--ykp-text-muted)" }}>
                                      Sections du formulaire
                                    </p>
                                    <div className="flex flex-wrap gap-2">
                                      {formulaire.sections_metadata.map((s: any, i: number) => (
                                        <span
                                          key={i}
                                          className="text-xs px-2.5 py-1 rounded-lg border"
                                          style={{ color: "var(--ykp-text-secondary)", background: "var(--ykp-canvas)", borderColor: "var(--ykp-border)" }}
                                        >
                                          {s.titre}
                                        </span>
                                      ))}
                                    </div>
                                  </div>
                                )}

                                {formDonnees && (
                                  <div
                                    className="rounded-xl border p-4"
                                    style={{ background: "var(--ykp-canvas)", borderColor: "var(--ykp-border)" }}
                                  >
                                    <div className="flex items-center gap-2 mb-2">
                                      <Users className="w-4 h-4 text-[#0054A6]" />
                                      <span className="text-sm font-semibold" style={{ color: "var(--ykp-text-primary)" }}>
                                        {formDonnees.n_reponses} réponse(s) collectée(s)
                                      </span>
                                    </div>
                                    {formDonnees.n_reponses === 0 && (
                                      <p className="text-xs" style={{ color: "var(--ykp-text-muted)" }}>
                                        Partagez le lien de collecte avec vos répondants ou importez via KoBoCollect.
                                      </p>
                                    )}
                                  </div>
                                )}
                              </div>
                            )}

                            {!formulaire && detail.n_reponses > 0 && (
                              <div
                                className="flex items-center gap-3 p-3 rounded-xl border"
                                style={{ background: "var(--ykp-canvas)", borderColor: "var(--ykp-border)" }}
                              >
                                <Users className="w-4 h-4 text-[#0054A6]" />
                                <span className="text-xs" style={{ color: "var(--ykp-text-secondary)" }}>
                                  {detail.n_reponses} réponse(s) collectée(s)
                                </span>
                                <a
                                  href={enquetesApi.xlsformUrl(etude.etude_id)}
                                  download
                                  className={`${btnBase} ml-auto text-green-700 dark:text-green-400 border border-green-500/20 hover:bg-green-500/[0.08]`}
                                  style={{ background: "var(--ykp-input-bg)" }}
                                >
                                  <FileSpreadsheet className="w-3.5 h-3.5" /> XLSForm
                                </a>
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    )}

                    {/* ── Onglet Analyse ── */}
                    {activeTab === "analyse" && (
                      <div className="space-y-3">
                        {detail.n_transcriptions === 0 && detail.n_reponses === 0 && (
                          <div className="flex items-center gap-2 text-xs text-amber-700 dark:text-yellow-400 bg-amber-50 dark:bg-yellow-400/[0.06] rounded-xl p-3 border border-amber-200 dark:border-yellow-400/20">
                            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                            {t("enquetes.analyse.noDataWarning")}
                          </div>
                        )}

                        {detail.mode !== "quantitatif" && (
                          <AnalyseCard
                            icon={<Brain className="w-5 h-5 text-[#0054A6]" />}
                            titre={t("enquetes.analyse.thematic")}
                            desc={t("enquetes.analyse.thematicDesc")}
                            couleur="blue"
                            disabled={detail.n_transcriptions === 0}
                            loading={analysing === "qualitative"}
                            done={detail.has_analyse}
                            onLancer={() => lancerAnalyse("qualitative")}
                            labelLancer={t("enquetes.analyse.launch")}
                            labelRelancer={t("enquetes.analyse.relaunch")}
                          />
                        )}
                        {detail.mode !== "qualitatif" && (
                          <AnalyseCard
                            icon={<BarChart2 className="w-5 h-5 text-blue-600 dark:text-blue-400" />}
                            titre={t("enquetes.analyse.statistical")}
                            desc={t("enquetes.analyse.statisticalDesc")}
                            couleur="indigo"
                            disabled={detail.n_reponses === 0}
                            loading={analysing === "quantitative"}
                            done={false}
                            onLancer={() => lancerAnalyse("quantitative")}
                            labelLancer={t("enquetes.analyse.launch")}
                            labelRelancer={t("enquetes.analyse.relaunch")}
                          />
                        )}
                        {detail.mode !== "qualitatif" && (
                          <AnalyseCard
                            icon={<TrendingUp className="w-5 h-5 text-cyan-600 dark:text-cyan-400" />}
                            titre={t("enquetes.analyse.targeted")}
                            desc={t("enquetes.analyse.targetedDesc")}
                            couleur="cyan"
                            disabled={detail.n_reponses < 5}
                            loading={analysing === "intelligente"}
                            done={false}
                            onLancer={() => lancerAnalyse("intelligente")}
                            labelLancer={t("enquetes.analyse.launch")}
                            labelRelancer={t("enquetes.analyse.relaunch")}
                          />
                        )}
                        {detail.mode !== "qualitatif" && (
                          <AnalyseCard
                            icon={<MessageSquareText className="w-5 h-5 text-amber-600 dark:text-amber-400" />}
                            titre={t("enquetes.analyse.openEnded")}
                            desc={t("enquetes.analyse.openEndedDesc")}
                            couleur="amber"
                            disabled={detail.n_reponses === 0}
                            loading={analysing === "commentaires"}
                            done={false}
                            onLancer={() => lancerAnalyse("commentaires")}
                            labelLancer={t("enquetes.analyse.launch")}
                            labelRelancer={t("enquetes.analyse.relaunch")}
                          />
                        )}

                        {analyseResult && analyseType && (
                          <AnalyseResultats result={analyseResult} type={analyseType} />
                        )}
                      </div>
                    )}

                    {/* ── Onglet Rapport ── */}
                    {activeTab === "rapport" && (
                      <div className="space-y-4">
                        {!detail.has_analyse && (
                          <div className="flex items-center gap-2 text-xs text-amber-700 dark:text-yellow-400 bg-amber-50 dark:bg-yellow-400/[0.06] rounded-xl p-3 border border-amber-200 dark:border-yellow-400/20">
                            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                            {t("enquetes.rapport.needAnalysis")}
                          </div>
                        )}

                        <div className="flex flex-wrap gap-2">
                          <button
                            onClick={genererRapport}
                            disabled={generating || !detail.has_analyse}
                            className={`${btnBase} text-white shadow-sm`}
                            style={{ background: generating ? "var(--ykp-text-faint)" : "#0054A6" }}
                          >
                            {generating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileText className="w-3.5 h-3.5" />}
                            {generating ? t("enquetes.rapport.generating") : detail.has_rapport ? t("enquetes.rapport.regenBtn") : t("enquetes.rapport.generateBtn")}
                          </button>
                          {rapport && (
                            <button
                              onClick={telechargerDocx}
                              className={`${btnBase} text-green-700 dark:text-green-400 border border-green-500/25 hover:bg-green-500/[0.08]`}
                              style={{ background: "var(--ykp-input-bg)" }}
                            >
                              <Download className="w-3.5 h-3.5" /> {t("enquetes.rapport.downloadWord")}
                            </button>
                          )}
                        </div>

                        {rapport && <RapportDisplay rapport={rapport} />}
                      </div>
                    )}

                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ── Sous-composants ───────────────────────────────────────────────────────────

const COULEURS: Record<string, { bg: string; border: string; btn: string }> = {
  blue:   { bg: "rgba(0,84,166,0.06)",    border: "rgba(0,84,166,0.2)",   btn: "#0054A6" },
  indigo: { bg: "rgba(99,102,241,0.06)",  border: "rgba(99,102,241,0.2)", btn: "#6366f1" },
  cyan:   { bg: "rgba(6,182,212,0.06)",   border: "rgba(6,182,212,0.2)",  btn: "#0891b2" },
  amber:  { bg: "rgba(245,158,11,0.06)",  border: "rgba(245,158,11,0.2)", btn: "#d97706" },
};

const AnalyseCard = ({
  icon, titre, desc, couleur, disabled, loading, done, onLancer, labelLancer, labelRelancer,
}: {
  icon: React.ReactNode; titre: string; desc: string; couleur: string;
  disabled: boolean; loading: boolean; done: boolean; onLancer: () => void;
  labelLancer?: string; labelRelancer?: string;
}) => {
  const c = COULEURS[couleur] ?? COULEURS.blue;
  return (
    <div className="rounded-xl border p-4 shadow-sm" style={{ background: c.bg, borderColor: c.border }}>
      <div className="flex items-start gap-3">
        <div
          className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
          style={{ background: "var(--ykp-surface)", boxShadow: "0 1px 2px rgba(0,0,0,0.06)" }}
        >
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-semibold" style={{ color: "var(--ykp-text-primary)" }}>{titre}</span>
            {done && <CheckCircle2 className="w-3.5 h-3.5 text-green-600 dark:text-green-400" />}
          </div>
          <p className="text-xs leading-relaxed" style={{ color: "var(--ykp-text-muted)" }}>{desc}</p>
        </div>
        <button
          onClick={onLancer}
          disabled={disabled || loading}
          className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white transition-all disabled:opacity-40 shadow-sm"
          style={{ background: c.btn }}
        >
          {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
          {loading ? "…" : done ? (labelRelancer ?? "↺") : (labelLancer ?? "▶")}
        </button>
      </div>
    </div>
  );
};

const AnalyseResultats = ({ result, type }: { result: any; type: string }) => (
  <div
    className="rounded-xl border p-4 space-y-3"
    style={{ background: "var(--ykp-surface)", borderColor: "var(--ykp-border)" }}
  >
    <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--ykp-text-muted)" }}>
      Résultats — {type}
    </p>

    {result.n_themes > 0 && (
      <div className="flex items-center gap-2 text-xs" style={{ color: "var(--ykp-text-secondary)" }}>
        <Brain className="w-3.5 h-3.5 text-[#0054A6]" />
        {result.n_themes} thème(s) identifié(s)
        {result.saturation && <span className="text-green-600 dark:text-green-400">· Saturation atteinte</span>}
      </div>
    )}

    {result.hypotheses?.length > 0 && (
      <div>
        <p className="text-xs mb-1.5 font-medium" style={{ color: "var(--ykp-text-muted)" }}>Hypothèses testées</p>
        <ul className="space-y-1">
          {result.hypotheses.map((h: string, i: number) => (
            <li key={i} className="text-xs flex gap-2" style={{ color: "var(--ykp-text-secondary)" }}>
              <span className="text-cyan-600 dark:text-cyan-400 font-bold shrink-0">H{i + 1}.</span>{h}
            </li>
          ))}
        </ul>
      </div>
    )}

    {result.croisements_cibles?.length > 0 && (
      <div>
        <p className="text-xs mb-1.5 font-medium" style={{ color: "var(--ykp-text-muted)" }}>
          {result.n_croisements} croisement(s) pertinent(s)
        </p>
        <div className="flex flex-wrap gap-1.5">
          {result.croisements_cibles.map((c: any, i: number) => (
            <span key={i} className="text-xs px-2 py-0.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-700 dark:text-cyan-300">
              {c.var1} × {c.var2}
            </span>
          ))}
        </div>
      </div>
    )}

    {result.graphiques && Object.keys(result.graphiques).length > 0 && (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
        {Object.entries(result.graphiques).map(([key, b64]) => (
          <img key={key} src={b64 as string} alt={key} className="rounded-xl border w-full" style={{ borderColor: "var(--ykp-border)" }} />
        ))}
      </div>
    )}

    {result.note_methodologique && (
      <p className="text-xs italic pt-2 border-t" style={{ color: "var(--ykp-text-faint)", borderColor: "var(--ykp-border)" }}>
        {result.note_methodologique}
      </p>
    )}
  </div>
);

const RapportDisplay = ({ rapport }: { rapport: any }) => (
  <div className="space-y-4">
    {rapport.themes?.length > 0 && (
      <div>
        <p className="text-xs mb-2 font-semibold uppercase tracking-wide" style={{ color: "var(--ykp-text-muted)" }}>
          Thèmes identifiés
        </p>
        <div className="flex flex-wrap gap-2">
          {rapport.themes.map((t: Theme) => (
            <div
              key={t.code}
              className="rounded-xl border p-3 min-w-[160px]"
              style={{ borderColor: sentimentColor(t.sentiment) + "33", background: sentimentColor(t.sentiment) + "0D" }}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-semibold truncate" style={{ color: "var(--ykp-text-primary)" }}>{t.libelle}</span>
                <span className="text-xs ml-2 shrink-0 font-semibold" style={{ color: sentimentColor(t.sentiment) }}>{t.frequence}×</span>
              </div>
              {t.citations?.slice(0, 1).map((c, i) => (
                <p key={i} className="text-xs italic line-clamp-2" style={{ color: "var(--ykp-text-muted)" }}>« {c} »</p>
              ))}
            </div>
          ))}
        </div>
      </div>
    )}

    {rapport.rapport_texte && (
      <div
        className="rounded-xl border p-4 max-h-96 overflow-y-auto"
        style={{ background: "var(--ykp-canvas)", borderColor: "var(--ykp-border)" }}
      >
        <pre className="text-xs leading-relaxed font-sans whitespace-pre-wrap" style={{ color: "var(--ykp-text-secondary)" }}>
          {rapport.rapport_texte}
        </pre>
      </div>
    )}

    {rapport.graphiques && Object.keys(rapport.graphiques).length > 0 && (
      <div>
        <p className="text-xs mb-2 font-semibold uppercase tracking-wide" style={{ color: "var(--ykp-text-muted)" }}>Graphiques</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {Object.entries(rapport.graphiques).map(([key, b64]) => (
            <img key={key} src={b64 as string} alt={key} className="rounded-xl border w-full" style={{ borderColor: "var(--ykp-border)" }} />
          ))}
        </div>
      </div>
    )}
  </div>
);
