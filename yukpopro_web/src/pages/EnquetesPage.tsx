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
  { value: "exploratoire",     label: "Exploratoire" },
  { value: "phenomenologique", label: "Phénoménologique" },
  { value: "theorie_ancree",   label: "Théorie ancrée" },
  { value: "ethnographique",   label: "Ethnographique" },
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
const inputCls = "w-full rounded-xl px-3 py-2 text-sm text-white bg-white/[0.06] border border-white/[0.08] focus:outline-none focus:border-yukpo-500/50 placeholder-gray-600";
const labelCls = "block text-xs text-gray-400 mb-1 font-medium";

const sentimentColor = (s: string) => ({
  positif: "#22C55E", négatif: "#EF4444", neutre: "#60A5FA", mixte: "#F59E0B",
}[s] ?? "#94A3B8");

// ── Composant principal ────────────────────────────────────────────────────────

export const EnquetesPage = () => {
  const { t } = useTranslation();
  // Store persistant (survit aux navigations) : navigation, brouillons, résultats coûteux
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

  // État éphémère (rechargé depuis backend ou non persistant entre nav)
  const [etudes,     setEtudes]     = useState<Etude[]>([]);
  const [loaded,     setLoaded]     = useState(false);
  const [loading,    setLoading]    = useState(false);
  const [detail,     setDetail]     = useState<EtudeDetail | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  // État onglet Audio
  const [transcriptions, setTranscriptions] = useState<Transcription[]>([]);
  const [uploading,      setUploading]      = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // État onglet Formulaire
  const [generatingForm,   setGeneratingForm]    = useState(false);
  const [formDonnees,      setFormDonnees]       = useState<any | null>(null);
  const [copied,           setCopied]            = useState(false);
  const [builderForm,      setBuilderForm]       = useState<BuilderFormulaire | null>(null);
  const [loadingBuilder,   setLoadingBuilder]    = useState(false);
  // Upload protocole
  const [protocoleFile,    setProtocoleFile]    = useState<File | null>(null);
  const [uploadingProt,    setUploadingProt]    = useState(false);
  const protocoleRef = useRef<HTMLInputElement>(null);

  // État onglet Analyse
  const [analysing,        setAnalysing]         = useState<string | null>(null); // type en cours

  // État onglet Rapport
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

  // Réhydratation : si expandedId est restauré du store, recharger detail/transcriptions
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
        } catch { /* étude supprimée — laisse expandedId, l'utilisateur peut nettoyer */ }
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
    } catch { toast.error("Erreur création"); }
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
      if (view === "analytics") {
        await chargerDonnees();
      }
      setFormView(view);
    } catch {
      toast.error("Impossible de charger le formulaire");
    } finally {
      setLoadingBuilder(false);
    }
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

  // ── Render helpers ────────────────────────────────────────────────────────────

  const statutIdx = (s: EtudeStatut) => STATUT_IDX[s] ?? 0;

  // ── Rendu ─────────────────────────────────────────────────────────────────────

  return (
    <div
      className="flex flex-col h-full overflow-hidden"
      style={{ background: "var(--ykp-canvas)" }}
    >
      <DemoBanner className="mx-6 mt-4" />
      {/* ── Header ── */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-white/[0.06]">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-white">{t("enquetes.title")}</h1>
            <p className="text-xs text-gray-500 mt-0.5">{t("enquetes.subtitle")}</p>
          </div>
          <div className="flex items-center gap-3">
            {loaded && etudes.length > 0 && (
              <div className="hidden sm:flex items-center gap-4 text-xs text-gray-500 border border-white/[0.06] rounded-xl px-4 py-2">
                <span><span className="text-white font-semibold">{etudes.length}</span> {t("enquetes.studies")}</span>
                <span><span className="text-green-400 font-semibold">{etudes.filter(e => e.statut === "rapport_pret").length}</span> {t("enquetes.reports")}</span>
                <span><span className="text-yukpo-400 font-semibold">{etudes.reduce((s, e) => s + e.n_transcriptions, 0)}</span> {t("enquetes.audios")}</span>
              </div>
            )}
            <button
              onClick={() => setShowCreate(!showCreate)}
              className={`${btnBase} text-white`}
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
          <div className="rounded-2xl border border-yukpo-500/20 p-5 space-y-4" style={{ background: "rgba(123,63,228,0.06)" }}>
            <h2 className="text-sm font-bold text-white">{t("enquetes.newStudyTitle")}</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className={labelCls}>{t("enquetes.form.title")} *</label>
                <input className={inputCls} placeholder="Perceptions des services de santé au Cameroun" value={form.titre} onChange={e => patchForm({ titre: e.target.value })} />
              </div>
              <div>
                <label className={labelCls}>{t("enquetes.form.terrain")}</label>
                <input className={inputCls} placeholder="Yaoundé — quartiers périphériques" value={form.terrain} onChange={e => patchForm({ terrain: e.target.value })} />
              </div>
              <div>
                <label className={labelCls}>{t("enquetes.form.methodologie")}</label>
                <select className={inputCls} value={form.methodologie} onChange={e => patchForm({ methodologie: e.target.value })}>
                  {METHODOLOGIES.map(m => <option key={m.value} value={m.value} style={{ background: "var(--ykp-elevated)", color: "var(--ykp-text-primary)" }}>{m.label}</option>)}
                </select>
              </div>
              <div>
                <label className={labelCls}>{t("enquetes.form.modeEtude")}</label>
                <div className="flex gap-2">
                  {MODES.map(m => (
                    <button key={m.value} onClick={() => patchForm({ mode: m.value })}
                      className={`flex-1 py-2 rounded-xl text-xs font-medium transition-all border ${form.mode === m.value ? "text-yukpo-200 border-yukpo-500/40 bg-yukpo-500/10" : "text-gray-500 border-white/[0.06] hover:border-white/[0.12]"}`}>
                      {m.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="md:col-span-2">
                <label className={labelCls}>{t("enquetes.form.population")}</label>
                <input className={inputCls} placeholder="Femmes rurales 25–45 ans, ménages à faible revenu" value={form.population_cible} onChange={e => patchForm({ population_cible: e.target.value })} />
              </div>
              <div className="md:col-span-2">
                <label className={labelCls}>{t("enquetes.form.contexte")}</label>
                <textarea rows={2} className={inputCls + " resize-none"} placeholder="Décrivez la problématique, le contexte et les objectifs de votre étude…" value={form.contexte} onChange={e => patchForm({ contexte: e.target.value })} />
              </div>
              <div className="md:col-span-2">
                <label className={labelCls}>{t("enquetes.form.questions")} <span className="text-gray-600 font-normal">{t("enquetes.form.questionsHint")}</span></label>
                <textarea rows={3} className={inputCls + " resize-none"} placeholder={"Quels sont les obstacles à l'accès aux soins ?\nComment les ménages gèrent-ils les dépenses de santé ?"} value={form.questions_recherche} onChange={e => patchForm({ questions_recherche: e.target.value })} />
              </div>
            </div>
            <div className="flex gap-2">
              <button onClick={creerEtude} disabled={creating} className={`${btnBase} text-white`} style={{ background: "#0054A6" }}>
                {creating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                {creating ? t("enquetes.creating") : t("enquetes.create")}
              </button>
              <button onClick={() => setShowCreate(false)} className={`${btnBase} text-gray-400 border border-white/[0.08] hover:bg-white/[0.05]`}>{t("common.cancel")}</button>
            </div>
          </div>
        )}

        {/* ── États de chargement ── */}
        {loading && !loaded && (
          <div className="flex items-center justify-center py-16"><Loader2 className="w-8 h-8 text-yukpo-400 animate-spin" /></div>
        )}
        {loaded && etudes.length === 0 && (
          <div className="text-center py-16">
            <BookOpen className="w-12 h-12 mx-auto mb-3 text-gray-700" />
            <p className="text-sm text-gray-500">{t("enquetes.noStudies")}</p>
          </div>
        )}

        {/* ── Liste des études ── */}
        {etudes.map(etude => {
          const isOpen = expandedId === etude.etude_id;
          const idx = statutIdx(etude.statut);
          return (
            <div key={etude.etude_id} className="rounded-2xl border overflow-hidden" style={{ background: "var(--ykp-surface)", borderColor: "var(--ykp-border)" }}>

              {/* En-tête carte */}
              <button className="w-full flex items-start gap-4 px-5 py-4 hover:bg-white/[0.025] transition-all text-left" onClick={() => ouvrirEtude(etude)}>
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 mb-2">
                    <span className="text-sm font-semibold text-white">{etude.titre}</span>
                    <span className="text-xs px-2 py-0.5 rounded-full border font-medium"
                      style={{ color: idx >= 3 ? "#4ade80" : idx >= 2 ? "#60a5fa" : idx >= 1 ? "#fbbf24" : "#94a3b8", background: idx >= 3 ? "rgba(74,222,128,0.08)" : idx >= 2 ? "rgba(96,165,250,0.08)" : idx >= 1 ? "rgba(251,191,36,0.08)" : "rgba(148,163,184,0.08)", borderColor: idx >= 3 ? "rgba(74,222,128,0.2)" : idx >= 2 ? "rgba(96,165,250,0.2)" : idx >= 1 ? "rgba(251,191,36,0.2)" : "rgba(148,163,184,0.2)" }}>
                      {PIPELINE[idx]?.label}
                    </span>
                    <span className="text-xs text-gray-600 bg-white/[0.04] px-2 py-0.5 rounded-full border border-white/[0.06]">{etude.mode}</span>
                  </div>
                  {/* Pipeline visuel */}
                  <div className="flex items-center gap-1 mt-1">
                    {PIPELINE.map((step, i) => (
                      <div key={step.key} className="flex items-center gap-1">
                        <div className={`h-1.5 rounded-full transition-all ${i <= idx ? "bg-yukpo-500" : "bg-white/[0.08]"}`} style={{ width: i <= idx ? 28 : 16 }} />
                        {i < PIPELINE.length - 1 && <ChevronRight className="w-3 h-3 text-gray-700" />}
                      </div>
                    ))}
                    <span className="text-xs text-gray-600 ml-2">
                      {etude.n_transcriptions > 0 && `${etude.n_transcriptions} audio · `}
                      {etude.n_reponses > 0 && `${etude.n_reponses} réponses`}
                      {etude.terrain && ` · ${etude.terrain}`}
                    </span>
                  </div>
                </div>
                {isOpen ? <ChevronUp className="w-4 h-4 text-gray-500 flex-shrink-0 mt-0.5" /> : <ChevronDown className="w-4 h-4 text-gray-500 flex-shrink-0 mt-0.5" />}
              </button>

              {/* Panneau détail */}
              {isOpen && detail && detail.etude_id === etude.etude_id && (
                <div className="border-t border-white/[0.06]">

                  {/* Onglets */}
                  <div className="flex border-b border-white/[0.06] px-4">
                    {(["audio", "formulaire", "analyse", "rapport"] as DetailTab[]).map(tab => {
                      const labels: Record<DetailTab, string> = {
                        audio: `🎙 ${t("enquetes.tabs.audio")}`,
                        formulaire: `📋 ${t("enquetes.tabs.formulaire")}`,
                        analyse: `🔍 ${t("enquetes.tabs.analyse")}`,
                        rapport: `📄 ${t("enquetes.tabs.rapport")}`,
                      };
                      const alerts: Record<DetailTab, boolean> = {
                        audio: detail.n_transcriptions === 0,
                        formulaire: detail.mode !== "qualitatif" && detail.n_reponses === 0,
                        analyse: !detail.has_analyse && detail.n_transcriptions > 0,
                        rapport: detail.has_analyse && !detail.has_rapport,
                      };
                      return (
                        <button key={tab} onClick={() => setActiveTab(tab)}
                          className={`px-4 py-3 text-xs font-medium transition-all border-b-2 relative ${activeTab === tab ? "text-yukpo-300 border-yukpo-400" : "text-gray-500 border-transparent hover:text-gray-300"}`}>
                          {labels[tab]}
                          {alerts[tab] && <span className="absolute top-2 right-1 w-1.5 h-1.5 rounded-full bg-yukpo-400" />}
                        </button>
                      );
                    })}
                  </div>

                  <div className="p-5 space-y-4">

                    {/* ── Onglet Audio ── */}
                    {activeTab === "audio" && (
                      <div className="space-y-4">
                        {detail.questions_recherche.length > 0 && (
                          <div className="rounded-xl border border-white/[0.06] p-3 bg-white/[0.02]">
                            <p className="text-xs text-gray-500 mb-2 font-semibold uppercase tracking-wide">Questions de recherche</p>
                            <ul className="space-y-1">
                              {detail.questions_recherche.map((q, i) => (
                                <li key={i} className="text-xs text-gray-300 flex gap-2"><span className="text-yukpo-400 font-bold shrink-0">{i + 1}.</span>{q}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Zone upload */}
                        <div
                          className="border-2 border-dashed border-white/[0.1] rounded-xl p-6 text-center hover:border-yukpo-500/40 transition-all cursor-pointer group"
                          onClick={() => !uploading && fileRef.current?.click()}
                        >
                          <input ref={fileRef} type="file" accept="audio/*,.m4a,.wav,.mp3,.ogg,.webm" className="hidden" onChange={uploaderAudio} />
                          {uploading
                            ? <div className="flex flex-col items-center gap-2"><Loader2 className="w-8 h-8 text-yukpo-400 animate-spin" /><p className="text-xs text-gray-400">Transcription Yukpo en cours…</p></div>
                            : <div className="flex flex-col items-center gap-2">
                                <div className="w-10 h-10 rounded-xl bg-yukpo-500/10 flex items-center justify-center group-hover:bg-yukpo-500/20 transition-all"><Upload className="w-5 h-5 text-yukpo-400" /></div>
                                <p className="text-xs text-gray-300 font-medium">{t("enquetes.audio.uploadAudio")}</p>
                                <p className="text-xs text-gray-600">{t("enquetes.audio.uploadDesc")}</p>
                              </div>}
                        </div>

                        {/* Liste transcriptions */}
                        {transcriptions.length > 0 && (
                          <div>
                            <p className="text-xs text-gray-500 mb-2 font-semibold uppercase tracking-wide">{transcriptions.length} entretien(s) transcrit(s)</p>
                            <div className="space-y-2">
                              {transcriptions.map((t, i) => (
                                <div key={i} className="rounded-xl border border-white/[0.06] p-3 bg-white/[0.02]">
                                  <div className="flex items-center justify-between mb-1">
                                    <span className="text-xs font-semibold text-white">{t.locuteur}</span>
                                    <span className="text-xs text-gray-500">{t.duree_estimee_min} min · {(t.longueur / 1000).toFixed(1)}k car.</span>
                                  </div>
                                  <p className="text-xs text-gray-400 line-clamp-2 italic">« {t.extrait} »</p>
                                  {t.date_collecte && <p className="text-xs text-gray-600 mt-1">{t.date_collecte}</p>}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {transcriptions.length === 0 && (
                          <div className="flex items-center gap-2 text-xs text-gray-600 bg-white/[0.02] rounded-xl p-3 border border-white/[0.04]">
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
                          <div className="rounded-xl border border-white/[0.06] p-4 bg-white/[0.02] text-center">
                            <p className="text-xs text-gray-400">En mode <strong className="text-white">qualitatif pur</strong>, la collecte se fait via entretiens audio (onglet Audios). Passez en mode <strong className="text-white">quantitatif</strong> ou <strong className="text-white">mixte</strong> pour activer les formulaires.</p>
                          </div>
                        ) : (
                          <>
                            {/* Workflow options */}
                            {!genIAMode && !formulaire && (
                              <div className="space-y-3">
                                {/* Option A — Upload protocole (recommandée) */}
                                <div className="rounded-xl border border-green-500/25 p-4" style={{ background: "rgba(34,197,94,0.04)" }}>
                                  <div className="flex items-center gap-2 mb-3">
                                    <div className="w-8 h-8 rounded-lg bg-green-500/15 flex items-center justify-center shrink-0">
                                      <Upload className="w-4 h-4 text-green-400" />
                                    </div>
                                    <div>
                                      <p className="text-sm font-semibold text-white">Option 1 — Uploader votre protocole <span className="text-green-400 text-xs">(recommandé)</span></p>
                                      <p className="text-xs text-gray-500 mt-0.5">PDF / DOCX / TXT — Yukpo extrait les objectifs, la population, les variables, et construit automatiquement le formulaire XLSForm</p>
                                    </div>
                                  </div>

                                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                                    <div>
                                      <label className={labelCls}>Titre du formulaire *</label>
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

                                  <input
                                    ref={protocoleRef}
                                    type="file"
                                    accept=".pdf,.docx,.doc,.txt"
                                    className="hidden"
                                    onChange={e => setProtocoleFile(e.target.files?.[0] ?? null)}
                                  />
                                  <div className="flex items-center gap-2 flex-wrap">
                                    <button
                                      onClick={() => protocoleRef.current?.click()}
                                      className={`${btnBase} text-green-400 border border-green-500/25 hover:bg-green-500/[0.08]`}
                                    >
                                      <FileText className="w-3.5 h-3.5" />
                                      {protocoleFile ? protocoleFile.name.slice(0, 40) : "Choisir fichier PDF/DOCX"}
                                    </button>
                                    {protocoleFile && (
                                      <button
                                        onClick={uploaderProtocole}
                                        disabled={uploadingProt}
                                        className={`${btnBase} text-white`}
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
                                  className="w-full flex items-center gap-4 p-4 rounded-xl border border-yukpo-500/25 hover:border-yukpo-500/50 transition-all text-left group"
                                  style={{ background: "rgba(123,63,228,0.06)" }}
                                >
                                  <div className="w-10 h-10 rounded-xl bg-yukpo-500/15 flex items-center justify-center shrink-0 group-hover:bg-yukpo-500/25 transition-all">
                                    <Wand2 className="w-5 h-5 text-yukpo-400" />
                                  </div>
                                  <div className="flex-1">
                                    <p className="text-sm font-semibold text-white">Option 2 — Décrire le sujet manuellement</p>
                                    <p className="text-xs text-gray-500 mt-0.5">Si vous n'avez pas encore de protocole — renseignez juste le contexte, Yukpo génère le formulaire professionnel</p>
                                  </div>
                                  <ChevronRight className="w-4 h-4 text-gray-600 shrink-0 group-hover:text-gray-400 transition-all" />
                                </button>
                              </div>
                            )}

                            {/* Formulaire de génération IA */}
                            {genIAMode && (
                              <div className="rounded-xl border border-yukpo-500/20 p-4 space-y-3" style={{ background: "rgba(123,63,228,0.04)" }}>
                                <div className="flex items-center gap-2 mb-1">
                                  <Wand2 className="w-4 h-4 text-yukpo-400" />
                                  <span className="text-sm font-semibold text-white">Génération Yukpo</span>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                  <div>
                                    <label className={labelCls}>Titre du formulaire *</label>
                                    <input className={inputCls} placeholder="Enquête satisfaction soins primaires" value={genIAForm.titre} onChange={e => patchGenIAForm({ titre: e.target.value })} />
                                  </div>
                                  <div>
                                    <label className={labelCls}>Population cible *</label>
                                    <input className={inputCls} placeholder="Patients, ménages, bénéficiaires" value={genIAForm.population} onChange={e => patchGenIAForm({ population: e.target.value })} />
                                  </div>
                                  <div className="md:col-span-2">
                                    <label className={labelCls}>Description du sujet *</label>
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
                                  <button onClick={genererFormulaireIA} disabled={generatingForm} className={`${btnBase} text-white`} style={{ background: "#0054A6" }}>
                                    {generatingForm ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Wand2 className="w-3.5 h-3.5" />}
                                    {generatingForm ? "Génération en cours…" : "Générer le formulaire"}
                                  </button>
                                  <button onClick={() => setGenIAMode(false)} className={`${btnBase} text-gray-400 border border-white/[0.08]`}>Annuler</button>
                                </div>
                              </div>
                            )}

                            {/* Formulaire existant */}
                            {formulaire && (
                              <div className="space-y-3">
                                <div className="rounded-xl border border-green-500/20 p-4 bg-green-500/[0.04]">
                                  <div className="flex items-center justify-between mb-3">
                                    <div className="flex items-center gap-2">
                                      <CheckCircle2 className="w-4 h-4 text-green-400" />
                                      <span className="text-sm font-semibold text-white">{formulaire.titre_formulaire || "Formulaire"}</span>
                                    </div>
                                    <span className="text-xs text-gray-500">{formulaire.questions?.length || 0} questions</span>
                                  </div>

                                  {/* Actions formulaire */}
                                  <div className="flex flex-wrap gap-2">
                                    {formulaire.lien_xlsform && (
                                      <a
                                        href={formulaire.lien_xlsform}
                                        download
                                        className={`${btnBase} text-green-400 border border-green-500/20 hover:bg-green-500/[0.08]`}
                                      >
                                        <FileSpreadsheet className="w-3.5 h-3.5" />
                                        XLSForm (ODK/KoBoCollect)
                                      </a>
                                    )}
                                    {formulaire.lien_collecte && (
                                      <button onClick={() => copierLien(formulaire.lien_collecte)} className={`${btnBase} text-blue-400 border border-blue-500/20 hover:bg-blue-500/[0.08]`}>
                                        {copied ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                                        Copier lien collecte
                                      </button>
                                    )}
                                    <button onClick={chargerDonnees} className={`${btnBase} text-gray-400 border border-white/[0.08] hover:bg-white/[0.05]`}>
                                      <RefreshCw className="w-3.5 h-3.5" />
                                      Voir les réponses
                                    </button>
                                    <button disabled={loadingBuilder} onClick={() => ouvrirBuilder("builder")} className={`${btnBase} text-yukpo-400 border border-yukpo-400/20 hover:bg-yukpo-400/[0.08]`}>
                                      <ClipboardList className="w-3.5 h-3.5" />
                                      Éditer les questions
                                    </button>
                                    <button disabled={loadingBuilder} onClick={() => ouvrirBuilder("preview")} className={`${btnBase} text-gray-300 border border-white/[0.08] hover:bg-white/[0.05]`}>
                                      <Eye className="w-3.5 h-3.5" />
                                      Aperçu répondant
                                    </button>
                                    <button disabled={loadingBuilder} onClick={() => ouvrirBuilder("analytics")} className={`${btnBase} text-blue-300 border border-blue-400/20 hover:bg-blue-400/[0.08]`}>
                                      <BarChart2 className="w-3.5 h-3.5" />
                                      Analytics
                                    </button>
                                    <button onClick={() => ouvrirBuilder("dictionnaire")} className={`${btnBase} text-purple-300 border border-purple-400/20 hover:bg-purple-400/[0.08]`}>
                                      <BookOpen className="w-3.5 h-3.5" />
                                      Dictionnaire
                                    </button>
                                    <button onClick={() => ouvrirBuilder("plan")} className={`${btnBase} text-amber-300 border border-amber-400/20 hover:bg-amber-400/[0.08]`}>
                                      <FileText className="w-3.5 h-3.5" />
                                      Plan d'analyse
                                    </button>
                                    <button onClick={telechargerQuestionnaireDocx} className={`${btnBase} text-gray-300 border border-white/[0.08] hover:bg-white/[0.05]`}>
                                      <Download className="w-3.5 h-3.5" />
                                      Questionnaire Word
                                    </button>
                                  </div>

                                  {formView !== "none" && (
                                    <div className="mt-4 pt-4 border-t border-white/[0.08] space-y-3">
                                      <div className="flex items-center justify-between">
                                        <span className="text-xs uppercase tracking-wide text-gray-500 font-semibold">
                                          {formView === "builder" ? "Éditeur" : formView === "preview" ? "Aperçu" : formView === "analytics" ? "Analyse des réponses" : formView === "dictionnaire" ? "Dictionnaire variables" : "Plan d'analyse"}
                                        </span>
                                        <button onClick={() => setFormView("none")} className="text-xs text-gray-400 hover:text-white">Fermer ✕</button>
                                      </div>
                                      {formView === "builder" && builderForm && (
                                        <FormBuilder
                                          formulaire={builderForm}
                                          onPreview={() => setFormView("preview")}
                                          onSaved={upd => setBuilderForm(upd)}
                                        />
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
                                  <p className="text-[10px] text-gray-500 mt-2 flex items-center gap-1">
                                    <CheckCircle2 className="w-3 h-3 text-green-500/70" />
                                    Le XLSForm est automatiquement sauvegardé dans <strong className="text-gray-400">Mes Documents</strong> dès le téléchargement.
                                  </p>
                                </div>

                                {/* Aperçu des sections */}
                                {formulaire.sections_metadata?.length > 0 && (
                                  <div>
                                    <p className="text-xs text-gray-500 mb-2 font-semibold uppercase tracking-wide">Sections du formulaire</p>
                                    <div className="flex flex-wrap gap-2">
                                      {formulaire.sections_metadata.map((s: any, i: number) => (
                                        <span key={i} className="text-xs px-2.5 py-1 rounded-lg bg-white/[0.04] border border-white/[0.06] text-gray-300">{s.titre}</span>
                                      ))}
                                    </div>
                                  </div>
                                )}

                                {/* Données collectées */}
                                {formDonnees && (
                                  <div className="rounded-xl border border-white/[0.06] p-4 bg-white/[0.02]">
                                    <div className="flex items-center gap-2 mb-3">
                                      <Users className="w-4 h-4 text-yukpo-400" />
                                      <span className="text-sm font-semibold text-white">{formDonnees.n_reponses} réponse(s) collectée(s)</span>
                                    </div>
                                    {formDonnees.n_reponses === 0 && (
                                      <p className="text-xs text-gray-500">Partagez le lien de collecte avec vos répondants ou importez via KoBoCollect.</p>
                                    )}
                                  </div>
                                )}
                              </div>
                            )}

                            {/* XLSForm depuis étude si formulaire créé directement */}
                            {!formulaire && detail.n_reponses > 0 && (
                              <div className="flex items-center gap-3 p-3 rounded-xl border border-white/[0.06] bg-white/[0.02]">
                                <Users className="w-4 h-4 text-yukpo-400" />
                                <span className="text-xs text-gray-300">{detail.n_reponses} réponse(s) collectée(s)</span>
                                <a href={enquetesApi.xlsformUrl(etude.etude_id)} download className={`${btnBase} ml-auto text-green-400 border border-green-500/20 hover:bg-green-500/[0.08]`}>
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
                          <div className="flex items-center gap-2 text-xs text-yellow-400 bg-yellow-400/[0.06] rounded-xl p-3 border border-yellow-400/20">
                            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                            {t("enquetes.analyse.noDataWarning")}
                          </div>
                        )}

                        {/* Analyse qualitative */}
                        {detail.mode !== "quantitatif" && (
                          <AnalyseCard
                            icon={<Brain className="w-5 h-5 text-yukpo-400" />}
                            titre={t("enquetes.analyse.thematic")}
                            desc={t("enquetes.analyse.thematicDesc")}
                            couleur="yukpo"
                            disabled={detail.n_transcriptions === 0}
                            loading={analysing === "qualitative"}
                            done={detail.has_analyse}
                            onLancer={() => lancerAnalyse("qualitative")} labelLancer={t("enquetes.analyse.launch")} labelRelancer={t("enquetes.analyse.relaunch")}
                          />
                        )}

                        {/* Analyse quantitative */}
                        {detail.mode !== "qualitatif" && (
                          <AnalyseCard
                            icon={<BarChart2 className="w-5 h-5 text-blue-400" />}
                            titre={t("enquetes.analyse.statistical")}
                            desc={t("enquetes.analyse.statisticalDesc")}
                            couleur="blue"
                            disabled={detail.n_reponses === 0}
                            loading={analysing === "quantitative"}
                            done={false}
                            onLancer={() => lancerAnalyse("quantitative")} labelLancer={t("enquetes.analyse.launch")} labelRelancer={t("enquetes.analyse.relaunch")}
                          />
                        )}

                        {/* Analyse intelligente */}
                        {detail.mode !== "qualitatif" && (
                          <AnalyseCard
                            icon={<TrendingUp className="w-5 h-5 text-cyan-400" />}
                            titre={t("enquetes.analyse.targeted")}
                            desc={t("enquetes.analyse.targetedDesc")}
                            couleur="cyan"
                            disabled={detail.n_reponses < 5}
                            loading={analysing === "intelligente"}
                            done={false}
                            onLancer={() => lancerAnalyse("intelligente")} labelLancer={t("enquetes.analyse.launch")} labelRelancer={t("enquetes.analyse.relaunch")}
                          />
                        )}

                        {/* Analyse commentaires */}
                        {detail.mode !== "qualitatif" && (
                          <AnalyseCard
                            icon={<MessageSquareText className="w-5 h-5 text-amber-400" />}
                            titre={t("enquetes.analyse.openEnded")}
                            desc={t("enquetes.analyse.openEndedDesc")}
                            couleur="amber"
                            disabled={detail.n_reponses === 0}
                            loading={analysing === "commentaires"}
                            done={false}
                            onLancer={() => lancerAnalyse("commentaires")} labelLancer={t("enquetes.analyse.launch")} labelRelancer={t("enquetes.analyse.relaunch")}
                          />
                        )}

                        {/* Résultats analyse */}
                        {analyseResult && analyseType && (
                          <AnalyseResultats result={analyseResult} type={analyseType} />
                        )}
                      </div>
                    )}

                    {/* ── Onglet Rapport ── */}
                    {activeTab === "rapport" && (
                      <div className="space-y-4">
                        {!detail.has_analyse && (
                          <div className="flex items-center gap-2 text-xs text-yellow-400 bg-yellow-400/[0.06] rounded-xl p-3 border border-yellow-400/20">
                            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                            {t("enquetes.rapport.needAnalysis")}
                          </div>
                        )}

                        <div className="flex flex-wrap gap-2">
                          <button onClick={genererRapport} disabled={generating || !detail.has_analyse} className={`${btnBase} text-white`} style={{ background: generating ? "#333" : "#0054A6" }}>
                            {generating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileText className="w-3.5 h-3.5" />}
                            {generating ? t("enquetes.rapport.generating") : detail.has_rapport ? t("enquetes.rapport.regenBtn") : t("enquetes.rapport.generateBtn")}
                          </button>
                          {rapport && (
                            <button onClick={telechargerDocx} className={`${btnBase} text-green-400 border border-green-500/20 hover:bg-green-500/[0.08]`}>
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
  yukpo: { bg: "rgba(0,84,166,0.06)", border: "rgba(0,84,166,0.2)", btn: "#0054A6" },
  blue:  { bg: "rgba(96,165,250,0.06)", border: "rgba(96,165,250,0.2)", btn: "#3B82F6" },
  cyan:  { bg: "rgba(6,182,212,0.06)",  border: "rgba(6,182,212,0.2)",  btn: "#06B6D4" },
  amber: { bg: "rgba(251,191,36,0.06)", border: "rgba(251,191,36,0.2)", btn: "#D97706" },
};

const AnalyseCard = ({ icon, titre, desc, couleur, disabled, loading, done, onLancer, labelLancer, labelRelancer }: {
  icon: React.ReactNode; titre: string; desc: string; couleur: string;
  disabled: boolean; loading: boolean; done: boolean; onLancer: () => void;
  labelLancer?: string; labelRelancer?: string;
}) => {
  const c = COULEURS[couleur] ?? COULEURS.yukpo;
  return (
    <div className="rounded-xl border p-4" style={{ background: c.bg, borderColor: c.border }}>
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-xl bg-white/[0.06] flex items-center justify-center shrink-0">{icon}</div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-semibold text-white">{titre}</span>
            {done && <CheckCircle2 className="w-3.5 h-3.5 text-green-400" />}
          </div>
          <p className="text-xs text-gray-500 leading-relaxed">{desc}</p>
        </div>
        <button
          onClick={onLancer}
          disabled={disabled || loading}
          className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white transition-all disabled:opacity-40"
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
  <div className="rounded-xl border border-white/[0.06] p-4 space-y-3 bg-white/[0.02]">
    <p className="text-xs text-gray-500 font-semibold uppercase tracking-wide">Résultats — {type}</p>

    {/* Thèmes */}
    {result.n_themes > 0 && (
      <div className="flex items-center gap-2 text-xs text-gray-300">
        <Brain className="w-3.5 h-3.5 text-yukpo-400" /> {result.n_themes} thème(s) identifié(s)
        {result.saturation && <span className="text-green-400">· Saturation atteinte</span>}
      </div>
    )}

    {/* Hypothèses analyse intelligente */}
    {result.hypotheses?.length > 0 && (
      <div>
        <p className="text-xs text-gray-500 mb-1.5">Hypothèses testées</p>
        <ul className="space-y-1">
          {result.hypotheses.map((h: string, i: number) => (
            <li key={i} className="text-xs text-gray-300 flex gap-2"><span className="text-cyan-400 font-bold shrink-0">H{i+1}.</span>{h}</li>
          ))}
        </ul>
      </div>
    )}

    {/* Croisements */}
    {result.croisements_cibles?.length > 0 && (
      <div>
        <p className="text-xs text-gray-500 mb-1.5">{result.n_croisements} croisement(s) pertinent(s)</p>
        <div className="flex flex-wrap gap-1.5">
          {result.croisements_cibles.map((c: any, i: number) => (
            <span key={i} className="text-xs px-2 py-0.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-300">
              {c.var1} × {c.var2}
            </span>
          ))}
        </div>
      </div>
    )}

    {/* Graphiques */}
    {result.graphiques && Object.keys(result.graphiques).length > 0 && (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
        {Object.entries(result.graphiques).map(([key, b64]) => (
          <img key={key} src={b64 as string} alt={key} className="rounded-xl border border-white/[0.06] w-full" />
        ))}
      </div>
    )}

    {result.note_methodologique && (
      <p className="text-xs text-gray-500 italic border-t border-white/[0.04] pt-2">{result.note_methodologique}</p>
    )}
  </div>
);

const RapportDisplay = ({ rapport }: { rapport: any }) => (
  <div className="space-y-4">
    {/* Thèmes */}
    {rapport.themes?.length > 0 && (
      <div>
        <p className="text-xs text-gray-500 mb-2 font-semibold uppercase tracking-wide">Thèmes identifiés</p>
        <div className="flex flex-wrap gap-2">
          {rapport.themes.map((t: Theme) => (
            <div key={t.code} className="rounded-xl border p-3 min-w-[160px]"
              style={{ borderColor: sentimentColor(t.sentiment) + "33", background: sentimentColor(t.sentiment) + "0D" }}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-semibold text-white truncate">{t.libelle}</span>
                <span className="text-xs ml-2 shrink-0" style={{ color: sentimentColor(t.sentiment) }}>{t.frequence}×</span>
              </div>
              {t.citations?.slice(0, 1).map((c, i) => (
                <p key={i} className="text-xs text-gray-500 italic line-clamp-2">« {c} »</p>
              ))}
            </div>
          ))}
        </div>
      </div>
    )}

    {/* Rapport texte */}
    {rapport.rapport_texte && (
      <div className="rounded-xl border border-white/[0.06] p-4 bg-white/[0.02] max-h-96 overflow-y-auto">
        <pre className="text-xs text-gray-300 whitespace-pre-wrap leading-relaxed font-sans">{rapport.rapport_texte}</pre>
      </div>
    )}

    {/* Graphiques */}
    {rapport.graphiques && Object.keys(rapport.graphiques).length > 0 && (
      <div>
        <p className="text-xs text-gray-500 mb-2 font-semibold uppercase tracking-wide">Graphiques</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {Object.entries(rapport.graphiques).map(([key, b64]) => (
            <img key={key} src={b64 as string} alt={key} className="rounded-xl border border-white/[0.06] w-full" />
          ))}
        </div>
      </div>
    )}
  </div>
);
