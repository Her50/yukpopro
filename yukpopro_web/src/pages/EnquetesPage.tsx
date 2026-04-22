/**
 * Enquêtes & Études — YukpoPro Web
 * Pipeline : créer étude → upload audios terrain → analyse thématique → rapport
 *           + formulaire de collecte → données quantitatives → analyse intelligente
 */
import { useState, useRef, useCallback } from "react";
import {
  Plus, Upload, Play, FileText, BarChart2, Download,
  ChevronDown, ChevronUp, Mic, MicOff, Loader2,
  ClipboardList, Users, MapPin, BookOpen, Trash2,
} from "lucide-react";
import toast from "react-hot-toast";
import { enquetesApi } from "@/api/client";

// ── Types ──────────────────────────────────────────────────────────────────────

interface Etude {
  etude_id: string;
  titre: string;
  mode: string;
  methodologie: string;
  terrain: string;
  n_transcriptions: number;
  n_reponses: number;
  statut: string;
  created_at: string;
}

interface EtudeDetail {
  etude_id: string;
  titre: string;
  contexte: string;
  questions_recherche: string[];
  methodologie: string;
  population_cible: string;
  terrain: string;
  mode: string;
  statut: string;
  n_transcriptions: number;
  n_themes: number;
  n_reponses: number;
  has_analyse: boolean;
  has_rapport: boolean;
  graphiques_disponibles: string[];
}

const METHODOLOGIES = [
  { value: "exploratoire", label: "Exploratoire" },
  { value: "phenomenologique", label: "Phénoménologique" },
  { value: "theorie_ancree", label: "Théorie ancrée" },
  { value: "ethnographique", label: "Ethnographique" },
];

const MODES = [
  { value: "qualitatif", label: "Qualitatif" },
  { value: "quantitatif", label: "Quantitatif" },
  { value: "mixte", label: "Mixte" },
];

// ── Composant principal ────────────────────────────────────────────────────────

export const EnquetesPage = () => {
  const [etudes, setEtudes] = useState<Etude[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EtudeDetail | null>(null);
  const [rapport, setRapport] = useState<any | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [analysing, setAnalysing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [showRapport, setShowRapport] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // Formulaire création
  const [form, setForm] = useState({
    titre: "", contexte: "", methodologie: "exploratoire",
    mode: "qualitatif", population_cible: "", terrain: "",
    questions_recherche: "",
  });

  // ── Chargement ───────────────────────────────────────────────────────────────

  const chargerEtudes = useCallback(async () => {
    setLoading(true);
    try {
      const res = await enquetesApi.lister();
      setEtudes(res.etudes || []);
      setLoaded(true);
    } catch {
      toast.error("Impossible de charger les études");
    } finally {
      setLoading(false);
    }
  }, []);

  const ouvrirEtude = async (id: string) => {
    if (selectedId === id) { setSelectedId(null); setDetail(null); return; }
    setSelectedId(id);
    setRapport(null);
    setShowRapport(false);
    try {
      const d = await enquetesApi.getEtude(id);
      setDetail(d);
    } catch {
      toast.error("Erreur chargement étude");
    }
  };

  // ── Création ─────────────────────────────────────────────────────────────────

  const creerEtude = async () => {
    if (!form.titre.trim()) { toast.error("Titre requis"); return; }
    setLoading(true);
    try {
      await enquetesApi.creer({
        titre: form.titre,
        contexte: form.contexte,
        methodologie: form.methodologie,
        mode: form.mode,
        population_cible: form.population_cible,
        terrain: form.terrain,
        questions_recherche: form.questions_recherche
          .split("\n").map(s => s.trim()).filter(Boolean),
      });
      toast.success("Étude créée !");
      setShowCreate(false);
      setForm({ titre: "", contexte: "", methodologie: "exploratoire", mode: "qualitatif", population_cible: "", terrain: "", questions_recherche: "" });
      chargerEtudes();
    } catch {
      toast.error("Erreur création");
    } finally {
      setLoading(false);
    }
  };

  // ── Upload audio ──────────────────────────────────────────────────────────────

  const uploaderAudio = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !selectedId) return;
    setUploading(true);
    toast("Transcription en cours…", { icon: "🎙️" });
    try {
      const res = await enquetesApi.uploaderAudio(selectedId, file);
      toast.success(`Transcription réussie — ${res.duree_estimee_min} min`);
      const d = await enquetesApi.getEtude(selectedId);
      setDetail(d);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Erreur transcription");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  // ── Analyse ───────────────────────────────────────────────────────────────────

  const lancerAnalyse = async () => {
    if (!selectedId) return;
    setAnalysing(true);
    toast("Analyse en cours — patience…", { icon: "🔍" });
    try {
      await enquetesApi.analyser(selectedId);
      toast.success("Analyse terminée !");
      const d = await enquetesApi.getEtude(selectedId);
      setDetail(d);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Erreur analyse");
    } finally {
      setAnalysing(false);
    }
  };

  // ── Rapport ───────────────────────────────────────────────────────────────────

  const genererRapport = async () => {
    if (!selectedId) return;
    setGenerating(true);
    toast("Génération du rapport…", { icon: "📄" });
    try {
      const r = await enquetesApi.genererRapport(selectedId, "json");
      setRapport(r);
      setShowRapport(true);
      toast.success("Rapport prêt !");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Erreur rapport");
    } finally {
      setGenerating(false);
    }
  };

  const telechargerDocx = async () => {
    if (!selectedId) return;
    toast("Génération Word…", { icon: "📝" });
    try {
      const r = await enquetesApi.genererRapport(selectedId, "docx");
      if (r.fichier_docx) {
        const a = document.createElement("a");
        a.href = `data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,${r.fichier_docx}`;
        a.download = `rapport_${detail?.titre?.slice(0, 30) || "etude"}.docx`;
        a.click();
      }
    } catch {
      toast.error("Erreur génération Word");
    }
  };

  // ── Couleurs statut ───────────────────────────────────────────────────────────

  const statutColor = (s: string) => {
    if (s === "rapport_pret") return "text-green-400 bg-green-400/10 border-green-400/20";
    if (s === "analyse")      return "text-blue-400 bg-blue-400/10 border-blue-400/20";
    if (s === "transcription") return "text-yellow-400 bg-yellow-400/10 border-yellow-400/20";
    return "text-gray-400 bg-gray-400/10 border-gray-400/20";
  };

  const statutLabel = (s: string) => ({
    brouillon: "Brouillon", transcription: "Transcrit",
    analyse: "Analysé", rapport_pret: "Rapport prêt",
  }[s] || s);

  const modeLabel = (m: string) => ({
    qualitatif: "Qualit.", quantitatif: "Quantit.", mixte: "Mixte",
  }[m] || m);

  // ── Init auto ────────────────────────────────────────────────────────────────

  if (!loaded && !loading) chargerEtudes();

  // ── Rendu ─────────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* ── Header ── */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-white/[0.06] flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Enquêtes & Études</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Collecte terrain · Analyse thématique · Rapport académique
          </p>
        </div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold text-white transition-all"
          style={{ background: "linear-gradient(135deg, #7B3FE4, #06B6D4)" }}
        >
          <Plus className="w-4 h-4" />
          Nouvelle étude
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-4">

        {/* ── Formulaire création ── */}
        {showCreate && (
          <div className="rounded-2xl border border-white/[0.08] p-5 space-y-4" style={{ background: "rgba(123,63,228,0.06)" }}>
            <h2 className="text-base font-semibold text-white">Nouvelle étude</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs text-gray-400 mb-1">Titre de l'étude *</label>
                <input
                  className="w-full rounded-xl px-3 py-2 text-sm text-white bg-white/[0.06] border border-white/[0.08] focus:outline-none focus:border-yukpo-500/50"
                  placeholder="Ex : Accès aux soins au Cameroun"
                  value={form.titre}
                  onChange={e => setForm(f => ({ ...f, titre: e.target.value }))}
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Terrain / Zone</label>
                <input
                  className="w-full rounded-xl px-3 py-2 text-sm text-white bg-white/[0.06] border border-white/[0.08] focus:outline-none focus:border-yukpo-500/50"
                  placeholder="Ex : Yaoundé, quartiers périphériques"
                  value={form.terrain}
                  onChange={e => setForm(f => ({ ...f, terrain: e.target.value }))}
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Méthodologie</label>
                <select
                  className="w-full rounded-xl px-3 py-2 text-sm text-white bg-white/[0.06] border border-white/[0.08] focus:outline-none"
                  value={form.methodologie}
                  onChange={e => setForm(f => ({ ...f, methodologie: e.target.value }))}
                >
                  {METHODOLOGIES.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Mode</label>
                <select
                  className="w-full rounded-xl px-3 py-2 text-sm text-white bg-white/[0.06] border border-white/[0.08] focus:outline-none"
                  value={form.mode}
                  onChange={e => setForm(f => ({ ...f, mode: e.target.value }))}
                >
                  {MODES.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
                </select>
              </div>
              <div className="md:col-span-2">
                <label className="block text-xs text-gray-400 mb-1">Population cible</label>
                <input
                  className="w-full rounded-xl px-3 py-2 text-sm text-white bg-white/[0.06] border border-white/[0.08] focus:outline-none"
                  placeholder="Ex : Femmes rurales 25-45 ans"
                  value={form.population_cible}
                  onChange={e => setForm(f => ({ ...f, population_cible: e.target.value }))}
                />
              </div>
              <div className="md:col-span-2">
                <label className="block text-xs text-gray-400 mb-1">Contexte / Objectif</label>
                <textarea
                  rows={2}
                  className="w-full rounded-xl px-3 py-2 text-sm text-white bg-white/[0.06] border border-white/[0.08] focus:outline-none resize-none"
                  placeholder="Décrivez l'objectif de votre étude…"
                  value={form.contexte}
                  onChange={e => setForm(f => ({ ...f, contexte: e.target.value }))}
                />
              </div>
              <div className="md:col-span-2">
                <label className="block text-xs text-gray-400 mb-1">Questions de recherche (une par ligne)</label>
                <textarea
                  rows={3}
                  className="w-full rounded-xl px-3 py-2 text-sm text-white bg-white/[0.06] border border-white/[0.08] focus:outline-none resize-none"
                  placeholder={"Quels sont les obstacles à l'accès aux soins ?\nComment les femmes gèrent-elles les dépenses de santé ?"}
                  value={form.questions_recherche}
                  onChange={e => setForm(f => ({ ...f, questions_recherche: e.target.value }))}
                />
              </div>
            </div>
            <div className="flex gap-3">
              <button
                onClick={creerEtude}
                disabled={loading}
                className="flex items-center gap-2 px-5 py-2 rounded-xl text-sm font-semibold text-white disabled:opacity-50"
                style={{ background: "#7B3FE4" }}
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                Créer
              </button>
              <button
                onClick={() => setShowCreate(false)}
                className="px-4 py-2 rounded-xl text-sm text-gray-400 hover:text-white border border-white/[0.08] hover:bg-white/[0.05] transition-all"
              >
                Annuler
              </button>
            </div>
          </div>
        )}

        {/* ── Liste des études ── */}
        {loading && !loaded && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-8 h-8 text-yukpo-400 animate-spin" />
          </div>
        )}

        {loaded && etudes.length === 0 && (
          <div className="text-center py-16 text-gray-500">
            <BookOpen className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p className="text-sm">Aucune étude — créez votre première étude de terrain.</p>
          </div>
        )}

        {etudes.map(etude => (
          <div key={etude.etude_id} className="rounded-2xl border border-white/[0.06] overflow-hidden" style={{ background: "#161B27" }}>
            {/* ── Ligne étude ── */}
            <button
              className="w-full flex items-center gap-4 px-5 py-4 hover:bg-white/[0.03] transition-all text-left"
              onClick={() => ouvrirEtude(etude.etude_id)}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-semibold text-white truncate">{etude.titre}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${statutColor(etude.statut)}`}>
                    {statutLabel(etude.statut)}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-white/[0.06] text-gray-400 border border-white/[0.06]">
                    {modeLabel(etude.mode)}
                  </span>
                </div>
                <div className="flex items-center gap-4 mt-1.5 text-xs text-gray-500">
                  {etude.terrain && <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{etude.terrain}</span>}
                  <span className="flex items-center gap-1"><Mic className="w-3 h-3" />{etude.n_transcriptions} audio(s)</span>
                  <span className="flex items-center gap-1"><Users className="w-3 h-3" />{etude.n_reponses} réponse(s)</span>
                </div>
              </div>
              {selectedId === etude.etude_id
                ? <ChevronUp className="w-4 h-4 text-gray-500 flex-shrink-0" />
                : <ChevronDown className="w-4 h-4 text-gray-500 flex-shrink-0" />}
            </button>

            {/* ── Panel détail ── */}
            {selectedId === etude.etude_id && detail && (
              <div className="px-5 pb-5 border-t border-white/[0.06] space-y-4 pt-4">

                {/* Infos */}
                {detail.questions_recherche.length > 0 && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1.5 font-medium uppercase tracking-wide">Questions de recherche</p>
                    <ul className="space-y-1">
                      {detail.questions_recherche.map((q, i) => (
                        <li key={i} className="text-xs text-gray-300 flex items-start gap-2">
                          <span className="text-yukpo-400 font-bold">{i + 1}.</span> {q}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Actions */}
                <div className="flex flex-wrap gap-2">
                  {/* Upload audio */}
                  <input
                    ref={fileRef}
                    type="file"
                    accept="audio/*"
                    className="hidden"
                    onChange={uploaderAudio}
                  />
                  <button
                    onClick={() => fileRef.current?.click()}
                    disabled={uploading}
                    className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-medium text-white border border-white/[0.08] hover:bg-white/[0.05] disabled:opacity-50 transition-all"
                  >
                    {uploading
                      ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      : <Upload className="w-3.5 h-3.5" />}
                    {uploading ? "Transcription…" : "Uploader audio"}
                  </button>

                  {/* Analyser */}
                  <button
                    onClick={lancerAnalyse}
                    disabled={analysing || detail.n_transcriptions === 0}
                    className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-medium text-white disabled:opacity-40 transition-all"
                    style={{ background: analysing ? "#333" : "#7B3FE4" }}
                  >
                    {analysing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                    {analysing ? "Analyse…" : "Analyser"}
                  </button>

                  {/* Rapport */}
                  <button
                    onClick={genererRapport}
                    disabled={generating || !detail.has_analyse}
                    className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-medium text-white disabled:opacity-40 transition-all"
                    style={{ background: generating ? "#333" : "#06B6D4" }}
                  >
                    {generating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileText className="w-3.5 h-3.5" />}
                    {generating ? "Génération…" : "Générer rapport"}
                  </button>

                  {/* Télécharger Word */}
                  {rapport && (
                    <button
                      onClick={telechargerDocx}
                      className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-medium text-green-400 border border-green-400/20 hover:bg-green-400/[0.08] transition-all"
                    >
                      <Download className="w-3.5 h-3.5" />
                      Télécharger Word
                    </button>
                  )}
                </div>

                {/* Stats */}
                <div className="grid grid-cols-3 gap-3">
                  {[
                    { label: "Audios", value: detail.n_transcriptions, icon: <Mic className="w-4 h-4" /> },
                    { label: "Thèmes", value: detail.n_themes, icon: <BarChart2 className="w-4 h-4" /> },
                    { label: "Réponses", value: detail.n_reponses, icon: <ClipboardList className="w-4 h-4" /> },
                  ].map(({ label, value, icon }) => (
                    <div key={label} className="rounded-xl border border-white/[0.06] px-4 py-3 flex items-center gap-3" style={{ background: "rgba(255,255,255,0.03)" }}>
                      <span className="text-yukpo-400">{icon}</span>
                      <div>
                        <p className="text-lg font-bold text-white">{value}</p>
                        <p className="text-xs text-gray-500">{label}</p>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Rapport */}
                {showRapport && rapport && (
                  <div className="rounded-xl border border-white/[0.06] p-4 space-y-3" style={{ background: "rgba(255,255,255,0.02)" }}>
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-semibold text-white">Rapport — {rapport.titre}</h3>
                      <button onClick={() => setShowRapport(false)} className="text-gray-500 hover:text-white text-xs">Fermer</button>
                    </div>

                    {/* Thèmes */}
                    {rapport.themes?.length > 0 && (
                      <div>
                        <p className="text-xs text-gray-500 mb-2 font-medium uppercase tracking-wide">Thèmes identifiés</p>
                        <div className="flex flex-wrap gap-2">
                          {rapport.themes.map((t: any) => (
                            <span
                              key={t.code}
                              className="text-xs px-2.5 py-1 rounded-full border font-medium"
                              style={{
                                color: t.sentiment === "positif" ? "#4ade80" : t.sentiment === "négatif" ? "#f87171" : "#60a5fa",
                                background: t.sentiment === "positif" ? "rgba(74,222,128,0.08)" : t.sentiment === "négatif" ? "rgba(248,113,113,0.08)" : "rgba(96,165,250,0.08)",
                                borderColor: t.sentiment === "positif" ? "rgba(74,222,128,0.2)" : t.sentiment === "négatif" ? "rgba(248,113,113,0.2)" : "rgba(96,165,250,0.2)",
                              }}
                            >
                              {t.libelle} ({t.frequence})
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Rapport texte */}
                    <div className="max-h-80 overflow-y-auto">
                      <pre className="text-xs text-gray-300 whitespace-pre-wrap leading-relaxed font-sans">
                        {rapport.rapport_texte}
                      </pre>
                    </div>

                    {/* Graphiques */}
                    {rapport.graphiques && Object.keys(rapport.graphiques).length > 0 && (
                      <div>
                        <p className="text-xs text-gray-500 mb-2 font-medium uppercase tracking-wide">Graphiques</p>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                          {Object.entries(rapport.graphiques).map(([key, b64]) => (
                            <img
                              key={key}
                              src={b64 as string}
                              alt={key}
                              className="rounded-xl border border-white/[0.06] w-full"
                            />
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
