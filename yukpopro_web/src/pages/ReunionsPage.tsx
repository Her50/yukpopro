/**
 * Réunions IA — Yukpo Pro
 * Enregistrement audio réel + transcription IA multilingue + rapport automatique
 * Identifie les participants, décisions, actions et suivi recommandations.
 */
import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { motion, AnimatePresence } from "framer-motion";
import toast from "react-hot-toast";
import {
  Plus, Users, Calendar, Trash2, Mic, MicOff,
  FileText, CheckCircle, Clock, Sparkles, X, Download,
  Radio, Square, Languages, ChevronDown, AlertCircle,
  Play, Pause, Pencil, RefreshCw,
} from "lucide-react";
import { reunionsApi } from "@/api/client";
import { DemoBanner } from "@/components/DemoBanner";
import { useAuthStore } from "@/store";
import { useTranslateLiveStore } from "@/store/translateLiveStore";
import { getRecorderStream } from "@/store/recorderStore";
import { useReunionFormStore } from "@/store/reunionFormStore";

// ── Types ──────────────────────────────────────────────────────────────────────

interface Participant { nom: string; role?: string; }

type StatutReunion = "brouillon" | "enregistrement" | "transcription" | "analyse" | "termine";

interface Reunion {
  id: string;
  titre: string;
  date: string;
  participants: Participant[];
  notes: string;           // notes saisies manuellement OU transcription
  rapport?: string;
  fichierRapport?: string; // nom du fichier DOCX généré côté serveur
  statut: StatutReunion;
  createdAt: string;
  dureeEnregistrement?: number; // secondes
  langue: string;          // langue choisie par l'utilisateur
  langueDetectee?: string;
}

// ── Langues supportées ────────────────────────────────────────────────────────

const LANGUES = [
  { code: "auto", label: "Détection auto" },
  { code: "fr",   label: "Français" },
  { code: "en",   label: "English" },
  { code: "ar",   label: "العربية (Arabe)" },
  { code: "sw",   label: "Kiswahili" },
  { code: "pt",   label: "Português" },
  { code: "es",   label: "Español" },
  { code: "de",   label: "Deutsch" },
  { code: "zh",   label: "中文" },
  { code: "wo",   label: "Wolof" },
  { code: "ha",   label: "Hausa" },
  { code: "yo",   label: "Yoruba" },
];

// ── Utilitaires ───────────────────────────────────────────────────────────────

const makeId  = () => crypto.randomUUID();
const today   = () => new Date().toISOString().slice(0, 10);
const fmtDuration = (s: number) => `${Math.floor(s / 60).toString().padStart(2, "0")}:${(s % 60).toString().padStart(2, "0")}`;

function buildPrompt(reunion: Reunion): string {
  const parts = [
    `Réunion : ${reunion.titre}`,
    `Date : ${reunion.date}`,
    reunion.participants.length > 0
      ? `Participants : ${reunion.participants.map(p => p.nom + (p.role ? ` (${p.role})` : "")).join(", ")}`
      : "",
    reunion.langueDetectee ? `Langue de réunion : ${reunion.langueDetectee}` : "",
    "",
    "Transcription / notes de réunion :",
    reunion.notes,
    "",
    "---",
    "En tant qu'assistant professionnel Yukpo Pro, génère un rapport de réunion structuré et percutant en Markdown avec exactement ces sections :",
    "## 1. Résumé exécutif",
    "## 2. Participants présents",
    "(Liste les personnes identifiées dans la transcription, avec rôle si mentionné)",
    "## 3. Points importants discutés",
    "## 4. Décisions prises",
    "(Liste numérotée de chaque décision formelle)",
    "## 5. Plan d'action",
    "Tableau Markdown : | Action | Responsable | Échéance | Priorité |",
    "## 6. Recommandations & suivi",
    "(Points à surveiller, risques, prochaine réunion suggérée)",
    "",
    "Sois précis, professionnel et synthétique. Identifie les personnes mentionnées dans la transcription.",
  ].filter(Boolean).join("\n");
  return parts;
}

// ── Hook enregistrement audio (persistant via recorderStore) ─────────────────
import { useRecorderStore } from "@/store/recorderStore";

function useAudioRecorder() {
  const s = useRecorderStore();
  return {
    isRecording: s.isRecording,
    isPaused: s.isPaused,
    duration: s.duration,
    audioBlob: s.audioBlob,
    supported: s.supported,
    liveSpeech: s.liveSpeech,
    start: (langue: string = "auto") => s.start(langue).catch(() => toast.error("Microphone inaccessible — vérifiez les permissions.")),
    pause: s.pause,
    resume: s.resume,
    stop: s.stop,
    reset: s.reset,
  };
}

// ── Composant formulaire création ─────────────────────────────────────────────

const FormulaireReunion = ({
  onSave, onClose,
}: { onSave: (r: Reunion) => void; onClose: () => void }) => {
  const form = useReunionFormStore();
  const titre = form.titre;
  const date = form.date;
  const notes = form.notes;
  const participants = form.participants;
  const langue = form.langue;
  const transcriptionDone = form.transcriptionDone;
  const traduireLive = form.traduireLive;
  const langueCible = form.langueCible;

  const setTitre = form.setTitre;
  const setDate = form.setDate;
  const setNotes = form.setNotes as (v: string | ((p: string) => string)) => void;
  const setParticipants = (v: Participant[] | ((p: Participant[]) => Participant[])) => {
    const next = typeof v === "function" ? (v as (p: Participant[]) => Participant[])(form.participants) : v;
    form.setParticipants(next);
  };
  const setLangue = form.setLangue;
  const setTranscriptionDone = form.setTranscriptionDone;
  const setTraduireLive = form.setTraduireLive;
  const setLangueCible = form.setLangueCible;

  const [showLangs,    setShowLangs]    = useState(false);
  const [transcribing, setTranscribing] = useState(false);

  const recorder = useAudioRecorder();
  const liveSpeech = recorder.liveSpeech;

  // Mode rapporteur-traducteur : traduit le même stream micro en direct
  const token = useAuthStore((s) => s.token);
  const tLignes = useTranslateLiveStore((s) => s.lignes);
  const tInterim = useTranslateLiveStore((s) => s.currentInterim);
  const tActive = useTranslateLiveStore((s) => s.active);
  const startTranslate = useTranslateLiveStore((s) => s.start);
  const stopTranslate = useTranslateLiveStore((s) => s.stop);

  const addParticipant = () => setParticipants(prev => [...prev, { nom: "", role: "" }]);
  const removeParticipant = (i: number) => setParticipants(prev => prev.filter((_, idx) => idx !== i));
  const updateParticipant = (i: number, field: keyof Participant, val: string) =>
    setParticipants(prev => prev.map((p, idx) => idx === i ? { ...p, [field]: val } : p));

  const handleStartRecording = async () => {
    await recorder.start(langue);
    if (traduireLive && token) {
      // Attendre un tick pour laisser le stream s'initialiser dans recorderStore
      await new Promise((r) => setTimeout(r, 50));
      const stream = getRecorderStream();
      if (stream) {
        await startTranslate({
          token,
          source: langue === "auto" ? "auto" : langue,
          target: langueCible,
          sourceMode: "microphone",
          ttsAvailable: false,
          externalStream: stream,
          onError: (msg) => toast.error(msg),
        });
      } else {
        toast.error("Stream micro indisponible pour la traduction");
      }
    }
  };

  const handleStopRecording = async () => {
    if (tActive) await stopTranslate();
    setTranscribing(true);
    const blob = await recorder.stop();
    if (!blob) { setTranscribing(false); return; }

    try {
      const formData = new FormData();
      const ext = blob.type.includes("webm") ? "webm" : blob.type.includes("ogg") ? "ogg" : "mp4";
      formData.append("audio", blob, `enregistrement.${ext}`);
      formData.append("langue", langue);

      const res = await reunionsApi.transcrireDirect(formData);
      const texte = res.transcription || "";
      const infos = res.traduit
        ? `\n[Transcrit depuis ${res.langue_detectee} → ${langue}]`
        : res.langue_detectee && res.langue_detectee !== "unknown"
          ? `\n[Langue détectée : ${res.langue_detectee}]`
          : "";
      setNotes(prev => (prev.trim() ? prev + "\n\n--- Transcription ---\n" + texte + infos : texte + infos));
      setTranscriptionDone(true);
      const msg = res.traduit
        ? `Transcrit depuis ${res.langue_detectee} et traduit en ${langue} — ${texte.length} caractères`
        : `Transcription réussie — ${texte.length} caractères (${res.langue_detectee})`;
      toast.success(msg);
    } catch (err: any) {
      if (liveSpeech.trim()) {
        setNotes(prev => (prev.trim() ? prev + "\n\n--- Notes live ---\n" + liveSpeech : liveSpeech));
        toast("Transcription Yukpo indisponible — notes live utilisées", { icon: "⚠️" });
      } else {
        toast.error("Erreur de transcription. Le service YukpoPro est temporairement indisponible.");
      }
    } finally {
      setTranscribing(false);
    }
  };

  const handleTogglePause = () => {
    if (recorder.isPaused) recorder.resume();
    else recorder.pause();
  };

  const handleSave = () => {
    if (!titre.trim()) { toast.error("Saisissez un titre de réunion"); return; }
    if (!notes.trim()) { toast.error("Ajoutez des notes ou enregistrez la réunion d'abord"); return; }
    onSave({
      id: makeId(),
      titre: titre.trim(),
      date,
      participants: participants.filter(p => p.nom.trim()),
      notes: notes.trim(),
      statut: "brouillon",
      createdAt: new Date().toISOString(),
      dureeEnregistrement: recorder.duration || undefined,
      langue: langue,
    });
    form.reset();
    recorder.reset();
  };

  const langueLabel = LANGUES.find(l => l.code === langue)?.label || "Détection auto";

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        onClick={onClose}
        className="fixed inset-0 bg-black/60 z-40"
      />
      <motion.div
        initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
        transition={{ type: "spring", damping: 28, stiffness: 300 }}
        className="fixed right-0 top-0 h-full w-full sm:max-w-lg bg-slate-900 border-l border-slate-700 z-50 flex flex-col shadow-2xl"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700 flex-shrink-0">
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-blue-400" />
            <h2 className="text-white font-semibold text-sm">Nouvelle réunion</h2>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-700">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {/* Titre + Date */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-400 block mb-1.5 font-medium">Titre *</label>
              <input
                type="text"
                value={titre}
                onChange={e => setTitre(e.target.value)}
                placeholder="Réunion mensuelle équipe finance"
                className="w-full bg-slate-800 border border-slate-600 rounded-xl text-white placeholder-slate-500 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1.5 font-medium">Date</label>
              <input
                type="date"
                value={date}
                onChange={e => setDate(e.target.value)}
                className="w-full bg-slate-800 border border-slate-600 rounded-xl text-white px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          {/* Participants */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs text-slate-400 font-medium">Participants</label>
              <button onClick={addParticipant} className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1">
                <Plus className="w-3 h-3" /> Ajouter
              </button>
            </div>
            <div className="space-y-2">
              {participants.map((p, i) => (
                <div key={i} className="flex gap-2">
                  <input
                    type="text"
                    value={p.nom}
                    onChange={e => updateParticipant(i, "nom", e.target.value)}
                    placeholder="Nom"
                    className="flex-1 bg-slate-800 border border-slate-700 rounded-lg text-white placeholder-slate-600 px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
                  />
                  <input
                    type="text"
                    value={p.role || ""}
                    onChange={e => updateParticipant(i, "role", e.target.value)}
                    placeholder="Rôle"
                    className="w-28 bg-slate-800 border border-slate-700 rounded-lg text-white placeholder-slate-600 px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
                  />
                  {participants.length > 1 && (
                    <button onClick={() => removeParticipant(i)} className="text-slate-600 hover:text-red-400 px-1">
                      <X className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Langue de réunion */}
          <div>
            <label className="text-xs text-slate-400 font-medium mb-1.5 flex items-center gap-1.5">
              <Languages className="w-3.5 h-3.5" /> Langue de la réunion
            </label>
            <div className="relative">
              <button
                onClick={() => setShowLangs(!showLangs)}
                className="w-full flex items-center justify-between bg-slate-800 border border-slate-700 rounded-xl px-3 py-2.5 text-sm text-white hover:border-blue-500 focus:outline-none"
              >
                <span>{langueLabel}</span>
                <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${showLangs ? "rotate-180" : ""}`} />
              </button>
              <AnimatePresence>
                {showLangs && (
                  <motion.div
                    initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
                    className="absolute z-50 top-full mt-1 w-full bg-slate-800 border border-slate-700 rounded-xl shadow-xl overflow-hidden"
                  >
                    {LANGUES.map(l => (
                      <button
                        key={l.code}
                        onClick={() => { setLangue(l.code); setShowLangs(false); }}
                        className={`w-full text-left px-3 py-2 text-sm hover:bg-slate-700 transition-colors ${langue === l.code ? "text-blue-400 bg-blue-500/10" : "text-white"}`}
                      >
                        {l.label}
                      </button>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>

          {/* Zone enregistrement */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs text-slate-400 font-medium">Enregistrement audio</label>
              {recorder.isRecording && (
                <span className="flex items-center gap-1.5 text-xs text-red-400 animate-pulse">
                  <Radio className="w-3 h-3" />
                  {recorder.isPaused ? "Pause" : "Enregistrement"} — {fmtDuration(recorder.duration)}
                </span>
              )}
            </div>

            {!recorder.supported ? (
              <div className="flex items-center gap-2 bg-amber-500/10 border border-amber-500/30 rounded-xl p-3">
                <AlertCircle className="w-4 h-4 text-amber-400 flex-shrink-0" />
                <p className="text-amber-300 text-xs">Microphone non disponible sur ce navigateur.</p>
              </div>
            ) : (
              <div className="rounded-xl p-3 space-y-3" style={{ background: "var(--ykp-elevated)", border: "1px solid var(--ykp-border)" }}>
                {/* Visualiseur */}
                {recorder.isRecording && (
                  <div className="flex items-center justify-center gap-0.5 h-6">
                    {Array.from({ length: 16 }).map((_, i) => (
                      <div
                        key={i}
                        className={`w-1 rounded-full transition-all ${recorder.isPaused ? "bg-slate-600 h-1" : "bg-blue-400"}`}
                        style={recorder.isPaused ? {} : {
                          height: `${Math.random() * 18 + 4}px`,
                          animation: `pulse ${0.4 + Math.random() * 0.6}s ease-in-out infinite alternate`,
                        }}
                      />
                    ))}
                  </div>
                )}

                {/* Mode rapporteur-traducteur */}
                {!recorder.isRecording && (
                  <div className="bg-slate-900/40 rounded-lg p-2.5 border border-slate-700/60 space-y-2">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={traduireLive}
                        onChange={(e) => setTraduireLive(e.target.checked)}
                        className="rounded"
                      />
                      <span className="text-xs text-slate-300 font-medium flex items-center gap-1.5">
                        <Languages className="w-3.5 h-3.5 text-purple-400" />
                        Traduire en direct pendant la réunion
                      </span>
                    </label>
                    {traduireLive && (
                      <div className="flex items-center gap-2 pl-6">
                        <span className="text-[11px] text-slate-500">Langue cible :</span>
                        <select
                          value={langueCible}
                          onChange={(e) => setLangueCible(e.target.value)}
                          className="bg-slate-800 border border-slate-600 rounded-md text-xs text-white px-2 py-1 focus:outline-none focus:border-purple-500"
                        >
                          {LANGUES.filter((l) => l.code !== "auto").map((l) => (
                            <option key={l.code} value={l.code}>{l.label}</option>
                          ))}
                        </select>
                        <span className="text-[10px] text-slate-600">(même micro, pas de 2e capture)</span>
                      </div>
                    )}
                  </div>
                )}

                {/* Boutons enregistrement */}
                <div className="flex gap-2">
                  {!recorder.isRecording ? (
                    <button
                      onClick={handleStartRecording}
                      disabled={transcribing}
                      className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white text-sm font-semibold transition-colors"
                    >
                      <Mic className="w-4 h-4" /> Démarrer l'enregistrement
                    </button>
                  ) : (
                    <>
                      <button
                        onClick={handleTogglePause}
                        className="flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl bg-amber-600 hover:bg-amber-500 text-white text-sm font-medium transition-colors"
                      >
                        {recorder.isPaused ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
                        {recorder.isPaused ? "Reprendre" : "Pause"}
                      </button>
                      <button
                        onClick={handleStopRecording}
                        disabled={transcribing}
                        className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-white text-sm font-medium transition-colors"
                      >
                        <Square className="w-3.5 h-3.5" />
                        {transcribing ? "Transcription…" : "Arrêter et transcrire"}
                      </button>
                    </>
                  )}
                </div>

                {/* Transcription live */}
                {liveSpeech && (
                  <div className="bg-slate-900/60 rounded-lg p-2 border border-slate-700">
                    <p className="text-xs text-slate-500 mb-1">Transcription live :</p>
                    <p className="text-slate-300 text-xs leading-relaxed">{liveSpeech}</p>
                  </div>
                )}

                {/* Traduction live (mode rapporteur-traducteur) */}
                {traduireLive && tActive && (
                  <div className="bg-purple-950/30 rounded-lg p-2 border border-purple-700/40 max-h-48 overflow-y-auto space-y-1.5">
                    <p className="text-xs text-purple-300 mb-1 flex items-center gap-1.5">
                      <Languages className="w-3 h-3" /> Traduction live → {langueCible}
                    </p>
                    {tLignes.length === 0 && !tInterim && (
                      <p className="text-slate-500 text-xs italic">En attente de parole…</p>
                    )}
                    {tLignes.slice(-6).map((l) => (
                      <div key={l.utteranceId} className="text-xs">
                        <span className="text-slate-500">[{l.sourceLang}]</span>{" "}
                        <span className="text-slate-400">{l.source}</span>
                        {l.translated && (
                          <div className="text-purple-200 pl-3">→ {l.translated}</div>
                        )}
                      </div>
                    ))}
                    {tInterim && <p className="text-slate-500 italic text-xs">{tInterim}</p>}
                  </div>
                )}

                {transcribing && (
                  <div className="flex items-center gap-2 py-1">
                    <div className="w-3 h-3 border-2 border-blue-400 border-t-transparent rounded-full animate-spin flex-shrink-0" />
                    <p className="text-blue-300 text-xs">Yukpo transcrit votre réunion…</p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Notes manuelles */}
          <div>
            {transcriptionDone ? (
              <div className="flex items-center gap-2 mb-1.5">
                <CheckCircle className="w-3.5 h-3.5 text-green-400 flex-shrink-0" />
                <label className="text-xs text-green-300 font-medium">
                  Transcription terminée — modifiez si nécessaire avant de sauvegarder
                </label>
              </div>
            ) : (
              <label className="text-xs text-slate-400 font-medium block mb-1.5">
                Notes textuelles * <span className="text-slate-600 font-normal">(ou ajoutées par transcription)</span>
              </label>
            )}
            <textarea
              value={notes}
              onChange={e => { setNotes(e.target.value); }}
              placeholder="Saisissez les points clés, ou utilisez l'enregistrement pour transcrire automatiquement…"
              rows={6}
              className={`w-full bg-slate-800 border rounded-xl text-white placeholder-slate-500 px-3 py-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 ${transcriptionDone ? "border-green-500/40" : "border-slate-600"}`}
            />
          </div>

          <div className="flex items-start gap-2 bg-blue-500/10 border border-blue-500/30 rounded-xl p-3">
            <Sparkles className="w-4 h-4 text-blue-400 flex-shrink-0 mt-0.5" />
            <p className="text-blue-300 text-xs">
              Yukpo Pro génère un rapport structuré avec participants identifiés, décisions, plan d'action et suivi.
              L'enregistrement est transcrit par Yukpo (15+ langues supportées).
            </p>
          </div>
        </div>

        <div className="px-5 py-4 border-t border-slate-700 flex gap-3 flex-shrink-0">
          <button onClick={onClose} className="flex-1 px-4 py-2.5 rounded-xl border border-slate-600 text-slate-300 hover:text-white text-sm transition-colors">
            Annuler
          </button>
          <button
            onClick={handleSave}
            disabled={recorder.isRecording || transcribing}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-semibold transition-colors"
          >
            <FileText className="w-4 h-4" />
            Enregistrer
          </button>
        </div>
      </motion.div>
    </>
  );
};

// ── Modal édition transcription avant analyse ─────────────────────────────────

const EditionTranscriptionModal = ({
  reunion,
  onConfirm,
  onClose,
}: {
  reunion: Reunion;
  onConfirm: (notesEditees: string) => void;
  onClose: () => void;
}) => {
  const [notes, setNotes] = useState(reunion.notes);

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        onClick={onClose}
        className="fixed inset-0 bg-black/70 z-40"
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.96 }}
        className="fixed inset-4 md:inset-12 lg:inset-20 bg-slate-900 border border-slate-700 rounded-2xl z-50 flex flex-col shadow-2xl overflow-hidden"
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700 flex-shrink-0">
          <div className="flex items-center gap-2">
            <Pencil className="w-4 h-4 text-blue-400" />
            <div>
              <h2 className="text-white font-semibold text-sm">Éditer la transcription</h2>
              <p className="text-slate-400 text-xs mt-0.5">{reunion.titre} · {new Date(reunion.date).toLocaleDateString("fr-FR")}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-700">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-hidden flex flex-col p-5 gap-3">
          <div className="flex items-start gap-2 bg-blue-500/10 border border-blue-500/30 rounded-xl p-3 flex-shrink-0">
            <Sparkles className="w-4 h-4 text-blue-400 flex-shrink-0 mt-0.5" />
            <p className="text-blue-300 text-xs">
              Corrigez ou complétez la transcription avant de générer le rapport.
              Yukpo Pro utilisera ce texte pour produire un rapport anonymisé et structuré.
            </p>
          </div>
          <textarea
            value={notes}
            onChange={e => setNotes(e.target.value)}
            className="flex-1 w-full bg-slate-800 border border-slate-600 rounded-xl text-white placeholder-slate-500 px-4 py-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 leading-relaxed"
            placeholder="Transcription de la réunion…"
          />
        </div>

        <div className="px-5 py-4 border-t border-slate-700 flex gap-3 flex-shrink-0">
          <button onClick={onClose} className="px-4 py-2.5 rounded-xl border border-slate-600 text-slate-300 hover:text-white text-sm transition-colors">
            Annuler
          </button>
          <button
            onClick={() => onConfirm(notes.trim() || reunion.notes)}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold transition-colors"
          >
            <Sparkles className="w-4 h-4" />
            Générer le rapport avec ce texte
          </button>
        </div>
      </motion.div>
    </>
  );
};

// ── Carte réunion ─────────────────────────────────────────────────────────────

const ReunionCard = ({
  reunion, onAnalyse, onEdit, onSelect, onDelete,
}: {
  reunion: Reunion;
  onAnalyse: () => void;
  onEdit: () => void;
  onSelect: () => void;
  onDelete: () => void;
}) => {
  const statusConfig: Record<StatutReunion, { label: string; color: string; icon: any }> = {
    brouillon:      { label: "Brouillon",        color: "bg-slate-700 text-slate-400",     icon: Clock },
    enregistrement: { label: "Enreg. en cours",  color: "bg-red-500/20 text-red-400",      icon: Radio },
    transcription:  { label: "Transcription…",   color: "bg-blue-500/20 text-blue-400",    icon: Sparkles },
    analyse:        { label: "Yukpo analyse…",   color: "bg-amber-500/20 text-amber-400",  icon: Sparkles },
    termine:        { label: "Rapport prêt",     color: "bg-green-500/20 text-green-400",  icon: CheckCircle },
  };
  const cfg = statusConfig[reunion.statut];
  const StatusIcon = cfg.icon;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
      className="bg-slate-900 border border-slate-700/60 rounded-2xl p-4 hover:border-slate-600 transition-colors group"
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <h3 className="text-white font-semibold text-sm truncate">{reunion.titre}</h3>
          <div className="flex items-center gap-3 mt-1 flex-wrap">
            <span className="text-slate-500 text-xs flex items-center gap-1">
              <Calendar className="w-3 h-3" />
              {new Date(reunion.date).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" })}
            </span>
            {reunion.participants.length > 0 && (
              <span className="text-slate-500 text-xs flex items-center gap-1">
                <Users className="w-3 h-3" />
                {reunion.participants.length} participant{reunion.participants.length > 1 ? "s" : ""}
              </span>
            )}
            {reunion.dureeEnregistrement && (
              <span className="text-slate-500 text-xs flex items-center gap-1">
                <Mic className="w-3 h-3" />
                {fmtDuration(reunion.dureeEnregistrement)}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className={`flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${cfg.color}`}>
            <StatusIcon className="w-3 h-3" />
            {cfg.label}
          </span>
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
            className="opacity-0 group-hover:opacity-100 p-1 text-slate-600 hover:text-red-400 transition-all"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <p className="text-slate-500 text-xs leading-relaxed line-clamp-2 mb-3">{reunion.notes}</p>

      <div className="flex gap-2">
        {reunion.statut === "termine" ? (
          <>
            <button
              onClick={onSelect}
              className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl bg-green-500/10 border border-green-500/30 text-green-400 text-xs font-medium hover:bg-green-500/20 transition-colors"
            >
              <FileText className="w-3.5 h-3.5" /> Voir le rapport
            </button>
            <button
              onClick={onEdit}
              title="Éditer la transcription et régénérer"
              className="flex items-center justify-center gap-1 px-2.5 py-2 rounded-xl bg-slate-700 hover:bg-slate-600 text-slate-400 hover:text-white text-xs transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </>
        ) : (
          <>
            <button
              onClick={onEdit}
              disabled={reunion.statut === "analyse" || reunion.statut === "transcription"}
              title="Éditer la transcription avant d'analyser"
              className="flex items-center justify-center gap-1 px-2.5 py-2 rounded-xl bg-slate-700 hover:bg-slate-600 text-slate-300 hover:text-white text-xs transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Pencil className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={onAnalyse}
              disabled={reunion.statut === "analyse" || reunion.statut === "transcription"}
              className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold disabled:opacity-50 disabled:cursor-wait transition-colors"
            >
              <Sparkles className="w-3.5 h-3.5" />
              {reunion.statut === "analyse" ? "Analyse en cours…" : "Analyser avec Yukpo Pro"}
            </button>
          </>
        )}
      </div>
    </motion.div>
  );
};

// ── Rapport modal ─────────────────────────────────────────────────────────────

const RapportModal = ({
  reunion, onClose, onEditerEtRegenerer, onRapportUpdated,
}: {
  reunion: Reunion;
  onClose: () => void;
  onEditerEtRegenerer: () => void;
  onRapportUpdated: (rapport: string, fichier: string) => void;
}) => {
  const [isEditing, setIsEditing]   = useState(false);
  const [rapportEdit, setRapportEdit] = useState(reunion.rapport || "");
  const [savingDocx, setSavingDocx]  = useState(false);
  const [newFichier, setNewFichier]  = useState<string | undefined>(reunion.fichierRapport);

  const nomFichier = newFichier ?? reunion.fichierRapport;

  const telechargerMd = () => {
    const blob = new Blob([rapportEdit], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `rapport_${reunion.titre.replace(/\s+/g, "_")}.md`;
    a.click();
  };

  const genererDocxDepuisEdition = async () => {
    setSavingDocx(true);
    try {
      const participantsStr = reunion.participants.length > 0
        ? reunion.participants.map(p => p.nom + (p.role ? ` (${p.role})` : "")).join(", ")
        : undefined;
      const res = await reunionsApi.rapportDocxDepuisMarkdown({
        rapport_markdown: rapportEdit,
        titre: reunion.titre,
        participants: participantsStr,
        date: reunion.date,
      });
      setNewFichier(res.fichier);
      onRapportUpdated(rapportEdit, res.fichier);
      setIsEditing(false);
      toast.success("Rapport DOCX régénéré avec vos modifications !");
    } catch {
      toast.error("Erreur lors de la génération DOCX");
    } finally {
      setSavingDocx(false);
    }
  };

  return (
    <>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        onClick={onClose} className="fixed inset-0 bg-black/70 z-40" />
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.96 }}
        className="fixed inset-4 md:inset-8 bg-slate-900 border border-slate-700 rounded-2xl z-50 flex flex-col shadow-2xl overflow-hidden"
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700 flex-shrink-0">
          <div>
            <h2 className="text-white font-bold">{reunion.titre}</h2>
            <p className="text-slate-400 text-xs mt-0.5">
              {new Date(reunion.date).toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
              {reunion.participants.length > 0 && ` · ${reunion.participants.map(p => p.nom).join(", ")}`}
              {reunion.dureeEnregistrement && ` · ${fmtDuration(reunion.dureeEnregistrement)} d'enregistrement`}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {/* Basculer mode édition / aperçu */}
            {isEditing ? (
              <>
                <button
                  onClick={() => setIsEditing(false)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs transition-colors"
                >
                  <X className="w-3.5 h-3.5" /> Annuler
                </button>
                <button
                  onClick={genererDocxDepuisEdition}
                  disabled={savingDocx}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs font-medium transition-colors"
                >
                  {savingDocx
                    ? <><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Génération…</>
                    : <><Download className="w-3.5 h-3.5" /> Sauvegarder & DOCX</>}
                </button>
              </>
            ) : (
              <>
                {/* Éditer le rapport directement */}
                <button
                  onClick={() => { setRapportEdit(reunion.rapport || ""); setIsEditing(true); }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-600/20 border border-amber-600/40 text-amber-400 hover:bg-amber-600/30 text-xs font-medium transition-colors"
                  title="Éditer le rapport et régénérer le DOCX"
                >
                  <Pencil className="w-3.5 h-3.5" /> Éditer le rapport
                </button>
                {/* Régénérer depuis transcription */}
                <button
                  onClick={onEditerEtRegenerer}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 hover:text-white text-xs transition-colors"
                  title="Modifier la transcription et régénérer"
                >
                  <RefreshCw className="w-3.5 h-3.5" /> Retranscription
                </button>
                {/* Télécharger DOCX */}
                {nomFichier && (
                  <a
                    href={`/api/v1/pro/generateurs/fichier/${encodeURIComponent(nomFichier)}`}
                    download={nomFichier}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-colors"
                  >
                    <Download className="w-3.5 h-3.5" /> DOCX
                  </a>
                )}
                <button
                  onClick={telechargerMd}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 hover:text-white text-xs transition-colors"
                >
                  <FileText className="w-3.5 h-3.5" /> Markdown
                </button>
              </>
            )}
            <button onClick={onClose} className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-700">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Badge Mes Documents */}
        {nomFichier && !isEditing && (
          <div className="px-6 py-2 bg-green-500/10 border-b border-green-500/20 flex items-center gap-2">
            <CheckCircle className="w-3.5 h-3.5 text-green-400 flex-shrink-0" />
            <span className="text-green-300 text-xs">Sauvegardé dans Mes Documents — {nomFichier}</span>
          </div>
        )}
        {isEditing && (
          <div className="px-6 py-2 bg-amber-500/10 border-b border-amber-500/20 flex items-center gap-2">
            <Pencil className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
            <span className="text-amber-300 text-xs">Mode édition — modifiez le rapport, puis cliquez "Sauvegarder & DOCX" pour régénérer le fichier Word</span>
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {isEditing ? (
            <textarea
              value={rapportEdit}
              onChange={e => setRapportEdit(e.target.value)}
              className="w-full h-full min-h-[60vh] bg-slate-800 border border-slate-600 rounded-xl text-white text-sm px-4 py-3 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono leading-relaxed"
              spellCheck={false}
            />
          ) : (
            <div className="prose prose-invert prose-sm max-w-none
              prose-headings:text-white prose-headings:font-bold
              prose-strong:text-white prose-code:text-blue-300
              prose-table:text-sm prose-th:text-slate-300 prose-td:text-slate-400
              prose-blockquote:border-blue-500 prose-a:text-blue-400">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{rapportEdit}</ReactMarkdown>
            </div>
          )}
        </div>
      </motion.div>
    </>
  );
};

// ── Page principale ───────────────────────────────────────────────────────────

const STORAGE_KEY = "yukpopro_reunions_v2";

function loadReunions(): Reunion[] {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]"); }
  catch { return []; }
}
function saveReunions(r: Reunion[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(r));
}

export const ReunionsPage = () => {
  const [reunions, setReunions]        = useState<Reunion[]>(loadReunions);
  const showForm = useReunionFormStore((s) => s.isOpen);
  const openForm = useReunionFormStore((s) => s.open);
  const closeForm = useReunionFormStore((s) => s.close);
  const setShowForm = (v: boolean) => (v ? openForm() : closeForm());
  const [selectedReunion, setSelected] = useState<Reunion | null>(null);
  const [editingReunion, setEditing]   = useState<Reunion | null>(null);

  const persist = (r: Reunion[]) => { setReunions(r); saveReunions(r); };

  const handleSave = (r: Reunion) => {
    persist([r, ...reunions]);
    setShowForm(false);
    toast.success("Réunion enregistrée !");
  };

  const handleDelete = (id: string) => {
    persist(reunions.filter(r => r.id !== id));
    if (selectedReunion?.id === id) setSelected(null);
  };

  const handleAnalyse = async (id: string, notesOverride?: string) => {
    const reunion = reunions.find(r => r.id === id);
    if (!reunion) return;

    // Mettre à jour les notes si elles ont été éditées
    const notesFinales = notesOverride ?? reunion.notes;
    const reunionsAvant = notesOverride
      ? reunions.map(r => r.id === id ? { ...r, notes: notesFinales } : r)
      : reunions;

    const updated = reunionsAvant.map(r => r.id === id ? { ...r, statut: "analyse" as const, notes: notesFinales } : r);
    persist(updated);

    // Sérialiser les participants en string pour l'API
    const participantsStr = reunion.participants.length > 0
      ? reunion.participants.map(p => p.nom + (p.role ? ` (${p.role})` : "")).join(", ")
      : undefined;

    // Langue : utiliser celle choisie à la création, fallback fr
    const langue = (reunion.langue && reunion.langue !== "auto") ? reunion.langue : "fr";

    try {
      // Contexte additionnel (hors date — déjà dans le titre/rapport)
      const contexteParties = [
        reunion.langueDetectee ? `Langue détectée : ${reunion.langueDetectee}` : null,
      ].filter(Boolean);

      const res = await reunionsApi.genererRapport({
        transcription: notesFinales,
        titre: reunion.titre,
        participants: participantsStr,
        langue,
        contexte: contexteParties.length > 0 ? contexteParties.join(" | ") : undefined,
        duree_secondes: reunion.dureeEnregistrement || undefined,
      });
      const updated2 = (notesOverride
        ? reunions.map(r => r.id === id ? { ...r, notes: notesFinales } : r)
        : reunions
      ).map(r =>
        r.id === id
          ? { ...r, statut: "termine" as const, notes: notesFinales, rapport: res.rapport, fichierRapport: res.fichier ?? undefined }
          : r
      );
      persist(updated2);
      toast.success("Rapport de réunion généré !");
      setSelected({ ...reunion, notes: notesFinales, statut: "termine", rapport: res.rapport, fichierRapport: res.fichier ?? undefined });
    } catch (err: any) {
      persist(reunions.map(r => r.id === id ? { ...r, statut: "brouillon" as const } : r));
      toast.error(err?.response?.data?.detail || "Erreur lors de l'analyse");
    }
  };

  const handleEditerEtAnalyser = (id: string, notesEditees: string) => {
    setEditing(null);
    setSelected(null);
    handleAnalyse(id, notesEditees);
  };

  const reunionsTerminees = reunions.filter(r => r.statut === "termine");
  const reunionsEnAttente = reunions.filter(r => r.statut !== "termine");

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="p-4 md:p-6 space-y-5 max-w-5xl mx-auto w-full">
        <DemoBanner />
        {/* Header */}
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <h1 className="text-xl md:text-2xl font-display font-bold text-white flex items-center gap-2">
              <Users className="w-6 h-6 text-blue-400" />
              Réunions Yukpo
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              Enregistrez, transcrivez (15+ langues) et générez des rapports percutants avec plan d'action.
            </p>
          </div>
          <button
            onClick={() => setShowForm(true)}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold transition-colors"
          >
            <Plus className="w-4 h-4" />
            Nouvelle réunion
          </button>
        </div>

        {/* Onboarding */}
        {reunions.length === 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {[
              { icon: Mic,         title: "1. Enregistrez",    desc: "Cliquez Démarrer — l'audio est capturé et transcrit automatiquement par Yukpo en 15+ langues." },
              { icon: Sparkles,    title: "2. Rapport Yukpo",  desc: "Yukpo Pro génère un rapport structuré : participants, décisions, plan d'action avec responsables." },
              { icon: CheckCircle, title: "3. Suivi & Export", desc: "Téléchargez le rapport Markdown et suivez les recommandations et actions assignées." },
            ].map(({ icon: Icon, title, desc }) => (
              <div key={title} className="p-4 rounded-xl text-center" style={{ background: "var(--ykp-surface)", border: "1px solid var(--ykp-border)" }}>
                <div className="w-9 h-9 rounded-xl bg-blue-500/20 flex items-center justify-center mx-auto mb-3">
                  <Icon className="w-4 h-4 text-blue-400" />
                </div>
                <p className="text-white text-sm font-semibold mb-1">{title}</p>
                <p className="text-slate-400 text-xs leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        )}

        {/* En attente */}
        {reunionsEnAttente.length > 0 && (
          <div>
            <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5" /> À analyser ({reunionsEnAttente.length})
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {reunionsEnAttente.map(r => (
                <ReunionCard
                  key={r.id}
                  reunion={r}
                  onAnalyse={() => handleAnalyse(r.id)}
                  onEdit={() => setEditing(r)}
                  onSelect={() => setSelected(r)}
                  onDelete={() => handleDelete(r.id)}
                />
              ))}
            </div>
          </div>
        )}

        {/* Terminées */}
        {reunionsTerminees.length > 0 && (
          <div>
            <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
              <CheckCircle className="w-3.5 h-3.5 text-green-400" /> Rapports générés ({reunionsTerminees.length})
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {reunionsTerminees.map(r => (
                <ReunionCard
                  key={r.id}
                  reunion={r}
                  onAnalyse={() => handleAnalyse(r.id)}
                  onEdit={() => setEditing(r)}
                  onSelect={() => setSelected(r)}
                  onDelete={() => handleDelete(r.id)}
                />
              ))}
            </div>
          </div>
        )}

        {/* Vide */}
        {reunions.length === 0 && (
          <div className="text-center py-12">
            <div className="w-14 h-14 rounded-2xl bg-blue-500/10 flex items-center justify-center mx-auto mb-4">
              <Users className="w-7 h-7 text-blue-400" />
            </div>
            <p className="text-slate-400 text-sm mb-4">Aucune réunion enregistrée.</p>
            <button
              onClick={() => setShowForm(true)}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold transition-colors"
            >
              <Plus className="w-4 h-4" /> Créer ma première réunion
            </button>
          </div>
        )}
      </div>

      {/* Modales */}
      <AnimatePresence>
        {showForm && (
          <FormulaireReunion onSave={handleSave} onClose={() => setShowForm(false)} />
        )}
        {editingReunion && (
          <EditionTranscriptionModal
            reunion={editingReunion}
            onConfirm={(notes) => handleEditerEtAnalyser(editingReunion.id, notes)}
            onClose={() => setEditing(null)}
          />
        )}
        {selectedReunion?.rapport && !editingReunion && (
          <RapportModal
            reunion={selectedReunion}
            onClose={() => setSelected(null)}
            onEditerEtRegenerer={() => {
              setEditing(selectedReunion);
              setSelected(null);
            }}
            onRapportUpdated={(rapport, fichier) => {
              const updated = reunions.map(r =>
                r.id === selectedReunion.id
                  ? { ...r, rapport, fichierRapport: fichier }
                  : r
              );
              persist(updated);
              setSelected(prev => prev ? { ...prev, rapport, fichierRapport: fichier } : prev);
            }}
          />
        )}
      </AnimatePresence>
    </div>
  );
};
