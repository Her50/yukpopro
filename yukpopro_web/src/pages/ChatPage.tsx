/**
 * YukpoPro — Interface de chat unifiée
 * Remplace CopilotePage, AgentsPage, GenerateursPage, AnalysePage, TraductionPage
 * Un seul chat intelligent qui orchestre tous les agents et outils.
 */
import React, { useState, useRef, useEffect, useCallback, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { motion, AnimatePresence } from "framer-motion";
import toast from "react-hot-toast";
import {
  Send, Plus, Trash2, MessageSquare, Paperclip, X,
  ChevronLeft, ChevronRight, Bot, Sparkles, Download,
  FileText, Image, Table, Globe, BarChart2,
  Pencil, Save, User as UserIcon, Mic, MicOff,
  Copy, Check,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAuthStore, useProfilStore, useCopiloteStore, useDocsStore } from "@/store";
import { chatApi, profilApi, copiloteApi, reunionsApi, generateurApi, type UploadedFile } from "@/api/client";
import { acquireWakeLock, releaseWakeLock } from "@/utils/wakeLock";
import { cn } from "@/components/ui";
import type { CopiloteMessage, NavigationSuggestion } from "@/types";
import { METIERS, PAYS_AFRIQUE } from "@/types";
import { METIERS_CONFIG } from "@/data/metiers-config";

// ── Types ─────────────────────────────────────────────────────────────────────

interface AttachedFile {
  id: string;
  name: string;
  size: number;
  type: string;
  content?: string; // base64 ou texte extrait
}

// ── Composant principal ───────────────────────────────────────────────────────

export const ChatPage = () => {
  const { t } = useTranslation();
  const { user } = useAuthStore();
  const { profil } = useProfilStore();
  const {
    sessions, activeSessionId, isLoading,
    newSession, selectSession, deleteSession,
    addMessage, updateLastAssistantMessage, setLoading, clearSession,
    activeMessages, activeSession, activeDocument, setActiveDocument,
  } = useCopiloteStore();
  const { addDocument } = useDocsStore();

  const [input, setInput] = useState("");
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  const [historySidebarOpen, setHistorySidebarOpen] = useState(() => window.innerWidth >= 768);
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 768);
  const [uploadingFile, setUploadingFile] = useState(false);
  const [profilModalOpen, setProfilModalOpen] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [audioModalOpen, setAudioModalOpen] = useState(false);
  const [audioSeconds, setAudioSeconds] = useState(0);
  const recognitionRef = useRef<any>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Détecter mobile/desktop
  useEffect(() => {
    const check = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      if (mobile) setHistorySidebarOpen(false);
    };
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const messages = activeMessages();
  const metierCtx = METIERS_CONFIG[profil?.metier ?? "default"] ?? METIERS_CONFIG.default;
  const suggestions = metierCtx.suggestions;

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Focus input
  useEffect(() => {
    inputRef.current?.focus();
  }, [activeSessionId]);

  // ── Envoi de message ───────────────────────────────────────────────────────

  const sendMessage = useCallback(async (content: string, files: AttachedFile[] = []) => {
    if (!content.trim() && files.length === 0) return;
    if (isLoading) return;

    const userMsg: CopiloteMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: content.trim(),
      timestamp: new Date().toISOString(),
      fichiers: files.map(f => f.name),
    };

    addMessage(userMsg);
    setInput("");
    setAttachedFiles([]);
    setLoading(true);

    // Message assistant "en cours..."
    const assistantMsg: CopiloteMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      timestamp: new Date().toISOString(),
      loading: true,
    };
    addMessage(assistantMsg);

    try {
      const activeDoc = activeDocument();

      // Sprint G1 — Orchestrateur silencieux (boîte noire) :
      // 1. Détecter intent + devis interne (sans afficher au user)
      // 2. Si intent = génération doc/visuel ET peut_payer → générer silencieux
      // 3. Si intent = génération ET solde insuffisant → afficher carte amber bloquante
      // 4. Sinon (conversationnel/ambigu) → flow chatApi.send normal
      const briefAvecContexte = content.trim() + (activeDoc ?
        `\n\n[Contexte : doc actif "${activeDoc.titre}" type=${activeDoc.type_doc}]` : "");

      let orch: any = null;
      try {
        orch = await generateurApi.orchestrer({
          brief: briefAvecContexte,
          contexte_fichiers: files.length > 0
            ? files.map(f => `${f.name} (${f.type})`).join(", ") : undefined,
        });
      } catch { /* fallback silencieux : pas d'orchestration → flow normal */ }

      const isGeneration = orch && (
        orch.intent_detecte === "generation_rapport" ||
        orch.intent_detecte === "generation_slides" ||
        orch.intent_detecte === "generation_visuel"
      );

      // Cas 1 : génération détectée mais SOLDE INSUFFISANT → bloquer avec explication
      if (isGeneration && orch.peut_payer === false) {
        const fb = orch.fallback_si_solde_insuffisant;
        const fbMsg = fb
          ? `\n\n💡 Mode économique disponible : **${fb.mode}** à ${fb.fcfa_user.toLocaleString()} FCFA (${fb.credits.toLocaleString()} crédits).`
          : "";
        updateLastAssistantMessage(
          `⚠️ **Solde insuffisant pour cette génération**\n\n` +
          `${orch.template_label} demande ${orch.fcfa_user.toLocaleString()} FCFA (${orch.credits_estimes.toLocaleString()} crédits).\n` +
          `Tu as ${orch.credits_disponibles.toLocaleString()} crédits.${fbMsg}\n\n` +
          `[→ Recharger mes crédits](/abonnement)`,
          null,
        );
        return;
      }

      // Cas 2 : génération détectée + solde OK → exécuter SILENCIEUSEMENT
      if (isGeneration && orch.peut_payer === true) {
        const cible = orch.endpoint_cible || "";
        try {
          if (orch.type_sortie === "rapport" || cible.includes("rapport")) {
            const r = await generateurApi.rapport(orch.payload_pret as any);
            updateLastAssistantMessage(
              `✓ ${orch.template_label} généré.\n` +
              (r.fichier_genere ? `[Télécharger](${generateurApi.telecharger(r.fichier_genere)})` : ""),
              null, r.fichier_genere ? [r.fichier_genere] : undefined,
            );
            if (r.fichier_genere) {
              addDocument({
                titre: orch.template_label || content.slice(0, 60),
                type: "rapport", fichier: r.fichier_genere,
                contexteConversation: content,
              });
              toast.success("Document prêt");
            }
            return;
          }
          if (orch.type_sortie === "slides" || cible.includes("slides")) {
            const r = await generateurApi.slides(orch.payload_pret as any);
            updateLastAssistantMessage(
              `✓ ${orch.template_label} généré.\n` +
              (r.fichier_genere ? `[Télécharger](${generateurApi.telecharger(r.fichier_genere)})` : ""),
              null, r.fichier_genere ? [r.fichier_genere] : undefined,
            );
            if (r.fichier_genere) {
              addDocument({
                titre: orch.template_label || content.slice(0, 60),
                type: "slides", fichier: r.fichier_genere,
                contexteConversation: content,
              });
              toast.success("Présentation prête");
            }
            return;
          }
          // generation_visuel → bascule Designer Pro (TODO Sprint G1.2)
        } catch (genErr: any) {
          // Si l'endpoint cible échoue → fallback chat normal pour ne pas bloquer
          // eslint-disable-next-line no-console
          console.warn("[ChatPage/G1] génération échouée, fallback chat:", genErr);
        }
      }

      // Cas 3 (par défaut) : conversationnel/ambigu → chatApi.send normal
      const res = await chatApi.send({
        message: content.trim(),
        pays: profil?.pays,
        fichiers: files.map(f => ({ nom: f.name, contenu: f.content || "", type: f.type })),
        document_ref: activeDoc ? {
          id: activeDoc.id,
          titre: activeDoc.titre,
          type_doc: activeDoc.type_doc,
          contenu_genere: activeDoc.contenu_genere,
        } : undefined,
      });

      updateLastAssistantMessage(
        res.reponse,
        res.agent_utilise ?? null,
        res.fichiers_generes ?? undefined,
        res.cout_llm ?? null,
        res.navigation_suggestions ?? [],
      );

      // Sauvegarder les documents générés dans l'historique
      if (res.fichiers_generes && res.fichiers_generes.length > 0) {
        res.fichiers_generes.forEach(f => {
          addDocument({
            titre: content.slice(0, 60) || f,
            type: f.endsWith(".docx") ? "rapport" : f.endsWith(".pptx") ? "slides" : "traduction",
            fichier: f,
            contexteConversation: content,
          });
        });
        const nb = res.fichiers_generes.length;
        toast.success(nb === 1 ? "Document prêt — lien de téléchargement disponible" : `${nb} documents prêts au téléchargement`);
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      if (detail && typeof detail === "object" && detail.code === "CREDITS_EPUISES") {
        updateLastAssistantMessage(
          `⚠️ **${detail.message}** ${detail.action}\n\n[→ Recharger mes crédits / Changer de plan](/abonnement)`,
          null,
        );
        toast.error(t("chat.creditsExpired"));
      } else {
        const msg = typeof detail === "string" ? detail : t("chat.connectionError");
        updateLastAssistantMessage(`⚠️ ${msg}`, null);
        toast.error(t("chat.yukpoError"));
      }
    } finally {
      setLoading(false);
    }
  }, [isLoading, profil, addMessage, updateLastAssistantMessage, setLoading]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    sendMessage(input, attachedFiles);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input, attachedFiles);
    }
  };

  // ── Upload de fichier ──────────────────────────────────────────────────────

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length === 0) return;
    setUploadingFile(true);

    for (const file of files) {
      try {
        const content = await readFileAsBase64(file);
        setAttachedFiles(prev => [...prev, {
          id: crypto.randomUUID(),
          name: file.name,
          size: file.size,
          type: file.type,
          content,
        }]);
      } catch {
        toast.error(`Impossible de lire ${file.name}`);
      }
    }
    setUploadingFile(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const removeFile = (id: string) =>
    setAttachedFiles(prev => prev.filter(f => f.id !== id));

  // ── Helpers ────────────────────────────────────────────────────────────────

  const handleNewSession = () => {
    newSession();
    setInput("");
    setAttachedFiles([]);
  };

  // ── Enregistrement audio (MediaRecorder + SpeechRecognition) ─────────────

  const startRecording = async () => {
    // Essai 1 : SpeechRecognition (Chrome/Edge) — transcription en temps réel, mode continu
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (SR) {
      const recognition = new SR();
      recognitionRef.current = recognition;
      recognition.lang = "fr-FR";
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;

      let finalTranscript = "";

      recognition.onresult = (e: any) => {
        let interim = "";
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const res = e.results[i];
          if (res.isFinal) finalTranscript += res[0].transcript + " ";
          else interim += res[0].transcript;
        }
        // Afficher en direct dans le champ texte
        setInput(finalTranscript + interim);
      };
      recognition.onerror = (e: any) => {
        if (e.error !== "aborted") toast.error(t("chat.micError", { err: e.error }));
        stopRecording(false);
      };
      recognition.onend = () => {
        // Ne pas arrêter si l'utilisateur n'a pas cliqué stop
        if (isRecording) recognition.start();
      };
      recognition.start();
      setIsRecording(true);
      setAudioModalOpen(true);
      setAudioSeconds(0);
      timerRef.current = setInterval(() => setAudioSeconds(s => s + 1), 1000);
      acquireWakeLock();
      return;
    }

    // Essai 2 : MediaRecorder (Firefox, Safari, etc.) — enregistrement blob
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
      mediaRecorderRef.current = mr;
      audioChunksRef.current = [];

      mr.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      mr.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        const blob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        await envoyerAudio(blob);
      };

      mr.start(500);
      setIsRecording(true);
      setAudioModalOpen(true);
      setAudioSeconds(0);
      timerRef.current = setInterval(() => setAudioSeconds(s => s + 1), 1000);
      // Empêche l'écran de s'éteindre pendant l'enregistrement (Chrome/Edge/Android).
      acquireWakeLock();
    } catch (err) {
      toast.error(t("chat.micPermissionError"));
    }
  };

  const stopRecording = (send = true) => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }

    // SpeechRecognition
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
      setIsRecording(false);
      setAudioModalOpen(false);
      releaseWakeLock();
      if (send && input.trim()) {
        sendMessage(input.trim(), []);
        setInput("");
      }
      return;
    }

    // MediaRecorder — onstop déclenchera envoyerAudio() qui transcrira puis enverra
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      // Si l'utilisateur annule (send=false), on désactive le flag pour bypass envoyerAudio
      if (!send) (mediaRecorderRef.current as MediaRecorder & { _cancelled?: boolean })._cancelled = true;
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
    setAudioModalOpen(false);
    releaseWakeLock();
  };

  const envoyerAudio = async (blob: Blob) => {
    const mr = mediaRecorderRef.current as (MediaRecorder & { _cancelled?: boolean }) | null;
    if (mr?._cancelled) return; // utilisateur a annulé l'enregistrement
    // Transcription côté serveur via Whisper (endpoint réunion réutilisé).
    // Une fois transcrit, on envoie le résultat comme un message texte normal —
    // l'orchestrateur du chat le traite alors comme une question écrite classique.
    const toastId = toast.loading(t("chat.audioTranscribing"));
    try {
      const fd = new FormData();
      fd.append("audio", blob, `audio_${Date.now()}.webm`);
      fd.append("langue", "auto");
      const res = await reunionsApi.transcrireDirect(fd);
      const texte = (res.transcription || "").trim();
      if (!texte) {
        toast.error(t("chat.audioTranscriptionEmpty"), { id: toastId });
        return;
      }
      toast.dismiss(toastId);
      sendMessage(texte, []);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || t("chat.audioTranscriptionError"), { id: toastId });
    }
  };

  const blobToBase64 = (blob: Blob): Promise<string> =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve((reader.result as string).split(",")[1] || "");
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });

  const toggleRecording = () => {
    if (isRecording) stopRecording(true);
    else startRecording();
  };

  const formatDureeAudio = (sec: number) => {
    const m = Math.floor(sec / 60).toString().padStart(2, "0");
    const s = (sec % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} o`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
  };

  const fileIcon = (type: string) => {
    if (type.startsWith("image/")) return <Image className="w-3.5 h-3.5" />;
    if (type.includes("spreadsheet") || type.includes("excel") || type.includes("csv"))
      return <Table className="w-3.5 h-3.5" />;
    return <FileText className="w-3.5 h-3.5" />;
  };

  // ── Rendu ──────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-full overflow-hidden" style={{ background: "transparent" }}>

      {/* ── Sidebar historique ─────────────────────────────────────────────── */}
      <AnimatePresence initial={false}>
        {historySidebarOpen && (
          <>
            {/* Overlay backdrop sur mobile */}
            {isMobile && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onClick={() => setHistorySidebarOpen(false)}
                className="fixed inset-0 bg-black/50 z-20"
              />
            )}

            <motion.div
              initial={isMobile ? { x: -280 } : { width: 0, opacity: 0 }}
              animate={isMobile ? { x: 0 } : { width: 260, opacity: 1 }}
              exit={isMobile ? { x: -280 } : { width: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className={cn(
                "flex flex-col bg-slate-900 border-r border-slate-800 overflow-hidden",
                isMobile
                  ? "fixed left-0 top-0 h-full w-72 z-30 shadow-2xl flex-shrink-0"
                  : "flex-shrink-0"
              )}
              style={!isMobile ? { width: 260 } : undefined}
            >
              {/* Header */}
              <div className="p-3 border-b border-slate-800 flex-shrink-0 flex gap-2">
                <button
                  onClick={handleNewSession}
                  className="flex-1 flex items-center gap-2 px-3 py-2.5 rounded-xl bg-yukpo-600 hover:bg-yukpo-500 text-white text-sm font-semibold transition-colors"
                >
                  <Plus className="w-4 h-4" />
                  {t('chat.newConversation')}
                </button>
                {isMobile && (
                  <button
                    onClick={() => setHistorySidebarOpen(false)}
                    className="p-2.5 rounded-xl text-slate-400 hover:text-white hover:bg-slate-700 transition-colors"
                  >
                    <X className="w-4 h-4" />
                  </button>
                )}
              </div>

              {/* Sessions */}
              <div className="flex-1 overflow-y-auto py-2">
                {sessions.length === 0 ? (
                  <p className="text-center text-slate-500 text-xs mt-8 px-4">
                    {t('chat.noConversations')}
                  </p>
                ) : (
                  sessions.map((session) => (
                    <div
                      key={session.id}
                      className={cn(
                        "group flex items-center gap-2 mx-2 px-3 py-2.5 rounded-xl cursor-pointer text-sm transition-colors",
                        session.id === activeSessionId
                          ? "bg-yukpo-500/20 border border-yukpo-400/40 text-white font-medium"
                          : "text-slate-200 hover:bg-slate-800 hover:text-white"
                      )}
                      onClick={() => { selectSession(session.id); if (isMobile) setHistorySidebarOpen(false); }}
                    >
                      <MessageSquare className="w-3.5 h-3.5 flex-shrink-0 opacity-60" />
                      <span className="flex-1 truncate">{session.title}</span>
                      <button
                        onClick={(e) => { e.stopPropagation(); deleteSession(session.id); }}
                        className="opacity-0 group-hover:opacity-100 hover:text-red-400 transition-opacity p-0.5"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  ))
                )}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* ── Zone principale ─────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

        {/* Header */}
        <div className="flex-shrink-0 flex items-center gap-3 px-4 py-3 border-b border-slate-800 bg-slate-900">
          <button
            onClick={() => setHistorySidebarOpen(!historySidebarOpen)}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-700 transition-colors"
          >
            {historySidebarOpen ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          </button>

          <div className="flex items-center gap-2 flex-1 min-w-0">
            <div className="w-7 h-7 rounded-lg bg-yukpo-gradient flex items-center justify-center flex-shrink-0">
              <Sparkles className="w-4 h-4 text-white" />
            </div>
            <div className="min-w-0">
              <h1 className="text-white font-semibold text-sm">Yukpo Pro</h1>
              <p className="text-slate-400 text-xs truncate">
                {activeSession()?.title && messages.length > 0
                  ? activeSession()!.title
                  : `${metierCtx.label} · ${profil?.pays ?? "Afrique"}`}
              </p>
            </div>
          </div>

          <button
            onClick={() => setProfilModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-slate-400 hover:text-white hover:bg-slate-700 transition-colors border border-slate-700"
            title={t('chat.editProfile')}
          >
            <Pencil className="w-3.5 h-3.5" />
            {messages.length === 0 && <span className="hidden sm:inline">{t('chat.myProfile')}</span>}
          </button>

          {messages.length > 0 && (
            <button
              onClick={handleNewSession}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-slate-400 hover:text-white hover:bg-slate-700 transition-colors border border-slate-700"
            >
              <Plus className="w-3.5 h-3.5" />
              {t('chat.new')}
            </button>
          )}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto">
          {messages.length === 0 ? (
            // ── Écran de bienvenue ──────────────────────────────────────────
            <WelcomeScreen
              profil={profil}
              user={user}
              metierCtx={metierCtx}
              suggestions={[]}
              onSuggestion={() => {}}
              onEditProfil={() => setProfilModalOpen(true)}
            />
          ) : (
            // ── Messages ────────────────────────────────────────────────────
            <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
              {messages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} />
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* ── Zone d'input ───────────────────────────────────────────────── */}
        <div className="flex-shrink-0 bg-slate-900 border-t border-slate-800 px-4 py-4">
          <div className="max-w-3xl mx-auto">

            {/* Document en cours d'édition */}
            {activeDocument() && (
              <div className="flex items-center gap-2 mb-3 px-3 py-2 rounded-lg bg-yukpo-500/10 border border-yukpo-500/30 text-xs">
                <Pencil className="w-3.5 h-3.5 text-yukpo-400 flex-shrink-0" />
                <span className="text-slate-300">{t("chat.editingDocument")}</span>
                <span className="text-yukpo-300 font-medium truncate max-w-md">{activeDocument()?.titre}</span>
                <button
                  type="button"
                  onClick={() => setActiveDocument(null)}
                  className="ml-auto text-slate-400 hover:text-red-400"
                  title={t("chat.exitEditMode")}
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {/* Fichiers attachés */}
            {attachedFiles.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-3">
                {attachedFiles.map(f => (
                  <div key={f.id} className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-700 border border-slate-600 text-xs text-slate-300">
                    {fileIcon(f.type)}
                    <span className="max-w-[120px] truncate">{f.name}</span>
                    <span className="text-slate-500">{formatFileSize(f.size)}</span>
                    <button onClick={() => removeFile(f.id)} className="hover:text-red-400 ml-1">
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <form onSubmit={handleSubmit}>
              <div className={cn(
                "flex items-end gap-2 rounded-2xl border transition-colors bg-slate-800",
                isLoading ? "border-slate-700" : "border-slate-600 focus-within:border-yukpo-500"
              )}>
                {/* Bouton fichier */}
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isLoading || uploadingFile}
                  className="flex-shrink-0 p-3 text-slate-400 hover:text-yukpo-400 transition-colors disabled:opacity-40"
                  title={t("chat.attachFileTitle")}
                >
                  {uploadingFile
                    ? <div className="w-5 h-5 border-2 border-slate-500 border-t-yukpo-400 rounded-full animate-spin" />
                    : <Paperclip className="w-5 h-5" />
                  }
                </button>

                {/* Bouton micro */}
                <button
                  type="button"
                  onClick={toggleRecording}
                  disabled={isLoading}
                  className={cn(
                    "flex-shrink-0 p-3 transition-colors disabled:opacity-40",
                    isRecording
                      ? "text-red-400 animate-pulse"
                      : "text-slate-400 hover:text-yukpo-400"
                  )}
                  title={isRecording ? t("chat.stopDictation") : t("chat.voiceDictation")}
                >
                  {isRecording ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
                </button>

                {/* Input texte */}
                <textarea
                  ref={inputRef}
                  rows={1}
                  value={input}
                  onChange={(e) => {
                    setInput(e.target.value);
                    e.target.style.height = "auto";
                    e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px";
                  }}
                  onKeyDown={handleKeyDown}
                  placeholder={
                    attachedFiles.length > 0
                      ? t('chat.attachPlaceholder')
                      : t('chat.mainPlaceholder')
                  }
                  className="flex-1 bg-transparent text-white text-sm placeholder-slate-500 py-3 pr-2 resize-none focus:outline-none min-h-[48px] max-h-[160px] overflow-y-auto"
                  style={{ height: "48px" }}
                />

                {/* Bouton envoyer */}
                <button
                  type="submit"
                  disabled={(!input.trim() && attachedFiles.length === 0) || isLoading}
                  className="flex-shrink-0 m-2 p-2 rounded-xl bg-yukpo-600 hover:bg-yukpo-500 text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {isLoading
                    ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    : <Send className="w-4 h-4" />
                  }
                </button>
              </div>
            </form>

            <p className="text-center text-slate-600 text-xs mt-2">
              {t('chat.disclaimer')}
            </p>
          </div>
        </div>
      </div>

      {/* Input fichier caché */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.png,.jpg,.jpeg,.ppt,.pptx"
        onChange={handleFileSelect}
        className="hidden"
      />

      {/* ── Modal Audio ─────────────────────────────────────────────────── */}
      <AnimatePresence>
        {audioModalOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4"
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="bg-slate-900 border border-slate-700 rounded-2xl p-8 w-full max-w-sm shadow-2xl text-center"
            >
              {/* Animation micro */}
              <div className="relative w-20 h-20 mx-auto mb-6">
                <div className="absolute inset-0 rounded-full bg-red-500/20 animate-ping" />
                <div className="absolute inset-2 rounded-full bg-red-500/30 animate-ping animation-delay-75" />
                <div className="relative w-20 h-20 rounded-full bg-red-500/20 border-2 border-red-500 flex items-center justify-center">
                  <Mic className="w-8 h-8 text-red-400" />
                </div>
              </div>

              <h3 className="text-white font-bold text-lg mb-1">{t('chat.recordingTitle')}</h3>
              <p className="text-slate-400 text-sm mb-3">
                {recognitionRef.current
                  ? t('chat.speakRealtime')
                  : t('chat.speakClear')}
              </p>

              {/* Transcription en temps réel */}
              {input && (
                <div className="bg-slate-800 rounded-xl p-3 mb-4 text-left">
                  <p className="text-slate-300 text-sm leading-relaxed line-clamp-4">{input}</p>
                </div>
              )}

              {/* Timer */}
              <div className="font-mono text-2xl text-red-400 font-bold mb-6">
                {formatDureeAudio(audioSeconds)}
              </div>

              {/* Actions */}
              <div className="flex gap-3">
                <button
                  onClick={() => { stopRecording(false); setInput(""); }}
                  className="flex-1 px-4 py-3 rounded-xl border border-slate-600 text-slate-400 hover:text-white hover:border-slate-500 transition-colors text-sm font-medium"
                >
                  {t('common.cancel')}
                </button>
                <button
                  onClick={() => stopRecording(true)}
                  className="flex-1 px-4 py-3 rounded-xl bg-yukpo-600 hover:bg-yukpo-500 text-white transition-colors text-sm font-bold flex items-center justify-center gap-2"
                >
                  <Send className="w-4 h-4" />
                  {t('common.send')}
                </button>
              </div>

              <p className="text-slate-600 text-xs mt-3">
                {recognitionRef.current
                  ? t("chat.transcriptionAuto")
                  : t("chat.audioMessage")}
              </p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Modale édition profil */}
      <AnimatePresence>
        {profilModalOpen && (
          <ProfilModal
            profil={profil}
            onClose={() => setProfilModalOpen(false)}
            onSaved={(updated) => {
              useProfilStore.getState().setProfil(updated);
              setProfilModalOpen(false);
              toast.success(t("chat.profileUpdated"));
            }}
          />
        )}
      </AnimatePresence>
    </div>
  );
};

// ── Écran de bienvenue ────────────────────────────────────────────────────────

// ── Construit le message de bienvenue contextuel ─────────────────────────────

const PAYS_LABELS: Record<string, string> = {
  CM: "Cameroun", CI: "Côte d'Ivoire", SN: "Sénégal", BF: "Burkina Faso",
  TG: "Togo", BJ: "Bénin", ML: "Mali", NE: "Niger", GA: "Gabon",
  CG: "Congo", CD: "RD Congo", TD: "Tchad", CF: "Centrafrique",
  GN: "Guinée", DZ: "Algérie", MA: "Maroc", TN: "Tunisie",
  MG: "Madagascar", MR: "Mauritanie", GQ: "Guinée équatoriale",
  RW: "Rwanda", BI: "Burundi", DJ: "Djibouti", FR: "France",
};

function buildWelcomeText(profil: any, metierCtx: typeof METIERS_CONFIG[string]): string {
  if (!profil?.metier) {
    return "Je suis Yukpo Pro, votre assistant professionnel intelligent. Posez-moi une question, envoyez un document à analyser ou traduire, ou demandez-moi de générer un rapport — je comprends le langage naturel et m'adapte à votre demande.";
  }
  const paysNom = profil.pays ? (PAYS_LABELS[profil.pays] || profil.pays) : "";
  const surPays = paysNom ? ` au ${paysNom}` : " en Afrique";
  const metierLabel = metierCtx.label || "professionnels";
  const agents = metierCtx.agents.slice(0, 2).map((a) => `l'${a}`).join(" et ");
  return `Je suis Yukpo Pro, votre assistant IA dédié aux ${metierLabel.toLowerCase()}${surPays}. Je peux analyser vos documents, générer des rapports, traduire vos fichiers et mobiliser ${agents || "des agents spécialisés"} pour des analyses pointues. Posez-moi votre première question ou envoyez un document.`;
}

const WelcomeScreen = ({
  profil, user, metierCtx, onEditProfil,
}: {
  profil: any; user: any; metierCtx: typeof METIERS_CONFIG[string];
  suggestions: string[]; onSuggestion: (s: string) => void; onEditProfil: () => void;
}) => {
  const { t } = useTranslation();
  const prenom = user?.prenom || user?.nom?.split(" ")[0] || "";
  const fallbackText = React.useMemo(() => buildWelcomeText(profil, metierCtx), [profil, metierCtx]);
  const [welcomeText, setWelcomeText] = React.useState<string>(fallbackText);

  React.useEffect(() => {
    let cancelled = false;
    copiloteApi
      .welcome()
      .then((res) => {
        if (!cancelled && res?.message) setWelcomeText(res.message);
      })
      .catch(() => {
        // garde le fallback grammaticalement correct
      });
    return () => { cancelled = true; };
  }, [profil?.metier, profil?.pays, profil?.niveau_expertise]);

  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6 py-12 max-w-xl mx-auto w-full text-center">
      <div className="w-16 h-16 rounded-2xl bg-yukpo-gradient flex items-center justify-center mb-6 shadow-lg shadow-yukpo-500/20">
        <span className="text-2xl">{metierCtx.emoji}</span>
      </div>

      <h2 className="text-2xl font-display font-bold text-white mb-1">
        {prenom ? t('chat.hello', { name: prenom }) : t('chat.helloDefault')}
      </h2>

      <p className="text-yukpo-400 text-xs font-semibold uppercase tracking-widest mb-5">
        Yukpo Pro — Assistant IA
      </p>

      <p className="text-slate-300 text-[15px] leading-relaxed mb-6 max-w-md">
        {welcomeText}
      </p>

      <button
        onClick={onEditProfil}
        className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-yukpo-400 transition-colors underline underline-offset-2"
      >
        <Pencil className="w-3 h-3" />
        {profil?.metier ? t('chat.editProfile') : t('chat.configureProfile')}
      </button>
    </div>
  );
};

// ── Bulle de message ──────────────────────────────────────────────────────────

const NavSuggestionButtons = ({ suggestions }: { suggestions: NavigationSuggestion[] }) => {
  const navigate = useNavigate();
  if (!suggestions || suggestions.length === 0) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {suggestions.map((s) => (
        <button
          key={s.route}
          onClick={() => navigate(s.route)}
          title={s.description}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors"
          style={{
            background: "rgba(0,84,166,0.15)",
            borderColor: "rgba(0,176,240,0.35)",
            color: "#00B0F0",
          }}
          onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = "rgba(0,84,166,0.3)"; }}
          onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "rgba(0,84,166,0.15)"; }}
        >
          <span>→</span>
          {s.label}
        </button>
      ))}
    </div>
  );
};

const MessageBubble = ({ message }: { message: CopiloteMessage }) => {
  const isUser = message.role === "user";
  const proseRef = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState(false);
  const { t } = useTranslation();

  const handleCopy = async () => {
    const raw = (message.content as string) || "";
    if (!raw) return;
    const html = proseRef.current?.innerHTML || "";
    try {
      if (html && typeof ClipboardItem !== "undefined" && navigator.clipboard?.write) {
        await navigator.clipboard.write([
          new ClipboardItem({
            "text/html": new Blob([html], { type: "text/html" }),
            "text/plain": new Blob([raw], { type: "text/plain" }),
          }),
        ]);
      } else {
        await navigator.clipboard.writeText(raw);
      }
      setCopied(true);
      toast.success(t("chat.messageCopied"));
      setTimeout(() => setCopied(false), 2000);
    } catch {
      try {
        await navigator.clipboard.writeText(raw);
        setCopied(true);
        toast.success(t("chat.messageCopied"));
        setTimeout(() => setCopied(false), 2000);
      } catch {
        toast.error(t("chat.copyFailed"));
      }
    }
  };

  if (isUser) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex justify-end"
      >
        <div className="max-w-[80%]">
          {message.fichiers && message.fichiers.length > 0 && (
            <div className="flex flex-wrap gap-1.5 justify-end mb-1.5">
              {message.fichiers.map((f, i) => (
                <span key={i} className="flex items-center gap-1 px-2 py-0.5 rounded-md bg-slate-700 text-slate-300 text-xs">
                  <Paperclip className="w-3 h-3" />
                  {f}
                </span>
              ))}
            </div>
          )}
          <div className="bg-yukpo-500/20 border border-yukpo-400/30 text-slate-100 rounded-2xl rounded-tr-sm px-4 py-3 text-sm leading-relaxed">
            {message.content as string}
          </div>
        </div>
      </motion.div>
    );
  }

  // Assistant
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex gap-3"
    >
      <div className="w-8 h-8 rounded-xl bg-yukpo-gradient flex items-center justify-center flex-shrink-0 mt-0.5">
        <Sparkles className="w-4 h-4 text-white" />
      </div>

      <div className="flex-1 min-w-0">
        {/* Badge agent utilisé */}
        {message.agent_utilise && (
          <div className="flex items-center gap-1.5 mb-1.5">
            <Bot className="w-3 h-3 text-yukpo-400" />
            <span className="text-xs text-yukpo-400 font-medium">{message.agent_utilise}</span>
          </div>
        )}

        {/* Contenu */}
        {message.loading ? (
          <div className="flex gap-1 items-center py-2">
            {[0, 1, 2].map(i => (
              <div
                key={i}
                className="w-2 h-2 rounded-full bg-slate-500 animate-bounce"
                style={{ animationDelay: `${i * 0.15}s` }}
              />
            ))}
          </div>
        ) : (
          <div>
            <div ref={proseRef} className="prose prose-invert prose-sm max-w-none text-slate-200
              prose-headings:text-white prose-headings:font-semibold
              prose-strong:text-white prose-code:text-yukpo-300
              prose-pre:bg-slate-800 prose-pre:border prose-pre:border-slate-700
              prose-blockquote:border-yukpo-500 prose-blockquote:text-slate-300
              prose-a:text-yukpo-400 prose-li:text-slate-300">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content as string}</ReactMarkdown>
            </div>
            <div className="mt-2 flex justify-end">
              <button
                type="button"
                onClick={handleCopy}
                aria-label={t("chat.copyMessage")}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium bg-white hover:bg-slate-100 text-slate-700 hover:text-slate-900 border border-slate-300 shadow-sm"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                {copied ? t("common.copied") : t("common.copy")}
              </button>
            </div>
          </div>
        )}

        {/* Fichiers générés — carte téléchargement proéminente */}
        {message.fichiers && message.fichiers.length > 0 && !message.loading && (
          <div className="mt-4 rounded-xl border-2 border-emerald-500/40 bg-gradient-to-br from-emerald-500/10 to-yukpo-500/10 p-4">
            <div className="flex items-center gap-2 mb-3">
              <div className="w-8 h-8 rounded-lg bg-emerald-500/20 flex items-center justify-center">
                <Download className="w-4 h-4 text-emerald-300" />
              </div>
              <div>
                <div className="text-sm font-semibold text-emerald-100">
                  {message.fichiers.length === 1 ? "Document prêt à télécharger" : `${message.fichiers.length} documents prêts à télécharger`}
                </div>
                <div className="text-[11px] text-slate-400">Cliquez pour récupérer votre fichier — également disponible dans <a href="/documents" className="underline hover:text-yukpo-300">Mes documents</a></div>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {message.fichiers.map((f, i) => {
                const nomFichier = f.split(/[/\\]/).pop() || f;
                const ext = (nomFichier.split(".").pop() || "").toLowerCase();
                const labelExt = ext === "docx" ? "Word" : ext === "pptx" ? "PowerPoint" : ext === "pdf" ? "PDF" : ext === "xlsx" ? "Excel" : ext.toUpperCase();
                return (
                  <a
                    key={i}
                    href={`/api/v1/pro/generateurs/fichier/${encodeURIComponent(nomFichier)}`}
                    download={nomFichier}
                    className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold shadow-md hover:shadow-lg transition-all"
                  >
                    <Download className="w-4 h-4" />
                    <span>Télécharger {labelExt}</span>
                    <span className="text-xs font-normal opacity-80 truncate max-w-[180px]">— {nomFichier}</span>
                  </a>
                );
              })}
            </div>
          </div>
        )}

        {/* Boutons de navigation vers les modules */}
        {message.navigation_suggestions && message.navigation_suggestions.length > 0 && !message.loading && (
          <NavSuggestionButtons suggestions={message.navigation_suggestions} />
        )}

        {/* Tokens consommés (transparent, discret — pas de montant) */}
        {message.cout_llm && !message.loading && (
          <div className="mt-2 flex items-center gap-2 text-[10px] text-slate-500">
            <span title={`Modèle : ${message.cout_llm.modele} · ${message.cout_llm.tokens_input} in + ${message.cout_llm.tokens_output} out`}>
              💡 {message.cout_llm.tokens_input + message.cout_llm.tokens_output} tokens
            </span>
          </div>
        )}
      </div>
    </motion.div>
  );
};

// ── Modale édition profil ──────────────────────────────────────────────────────

const NIVEAUX_EXPERTISE_KEYS = [
  { value: "debutant",      key: "expertiseDebutant" },
  { value: "intermediaire", key: "expertiseIntermediaire" },
  { value: "senior",        key: "expertiseSenior" },
  { value: "expert",        key: "expertiseExpert" },
] as const;

const ProfilModal = ({
  profil, onClose, onSaved,
}: {
  profil: any;
  onClose: () => void;
  onSaved: (updated: any) => void;
}) => {
  const { t } = useTranslation();
  const [metier, setMetier]     = useState(profil?.metier || "");
  const [pays, setPays]         = useState(profil?.pays || "CM");
  const [secteur, setSecteur]   = useState(profil?.secteur || "");
  const [entreprise, setEntreprise] = useState(profil?.entreprise || "");
  const [niveau, setNiveau]     = useState(profil?.niveau_expertise || "intermediaire");
  const [annees, setAnnees]     = useState(String(profil?.annees_experience || ""));
  const [bio, setBio]           = useState(profil?.bio || "");
  const [saving, setSaving]     = useState(false);

  const handleSave = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const updated = await profilApi.update({
        metier, pays, secteur, entreprise,
        niveau_expertise: niveau as any,
        annees_experience: annees ? parseInt(annees) : undefined,
        bio,
      });
      onSaved(updated);
    } catch {
      toast.error(t("chat.profileUpdateError"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      {/* Overlay */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="fixed inset-0 bg-black/60 z-40"
      />

      {/* Panel slide-over droite */}
      <motion.div
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", damping: 28, stiffness: 300 }}
        className="fixed right-0 top-0 h-full w-full sm:max-w-md bg-slate-900 border-l border-slate-700 z-50 flex flex-col shadow-2xl"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700 flex-shrink-0">
          <div className="flex items-center gap-2">
            <UserIcon className="w-4 h-4 text-yukpo-400" />
            <h2 className="text-white font-semibold text-sm">{t('chat.modalTitle')}</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-700 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <p className="px-5 py-3 text-xs text-slate-400 border-b border-slate-800 flex-shrink-0">
          {t('chat.modalDesc')}
        </p>

        {/* Formulaire */}
        <div className="flex-1 overflow-y-auto">
          <form id="profil-form" onSubmit={handleSave} className="p-5 space-y-4">
            {/* Métier */}
            <div>
              <label className="text-xs font-medium text-slate-400 block mb-1.5">{t('chat.profession')}</label>
              <select
                value={metier}
                onChange={(e) => setMetier(e.target.value)}
                className="w-full bg-slate-800 border border-slate-600 rounded-xl text-white px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-yukpo-500"
              >
                <option value="">{t("chat.selectProfession")}</option>
                {METIERS.map((m) => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </select>
            </div>

            {/* Pays + Niveau */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-slate-400 block mb-1.5">{t('profil.pays')}</label>
                <select
                  value={pays}
                  onChange={(e) => setPays(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-600 rounded-xl text-white px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-yukpo-500"
                >
                  {PAYS_AFRIQUE.map((p) => (
                    <option key={p.value} value={p.value}>{p.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-slate-400 block mb-1.5">{t('profil.niveau')}</label>
                <select
                  value={niveau}
                  onChange={(e) => setNiveau(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-600 rounded-xl text-white px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-yukpo-500"
                >
                  {NIVEAUX_EXPERTISE_KEYS.map((n) => (
                    <option key={n.value} value={n.value}>{t(`chat.${n.key}`)}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Secteur + Entreprise */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-slate-400 block mb-1.5">{t('profil.secteur')}</label>
                <input
                  type="text"
                  value={secteur}
                  onChange={(e) => setSecteur(e.target.value)}
                  placeholder={t("chat.secteurPlaceholder")}
                  className="w-full bg-slate-800 border border-slate-600 rounded-xl text-white placeholder-slate-500 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-yukpo-500"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-400 block mb-1.5">{t('profil.entreprise')}</label>
                <input
                  type="text"
                  value={entreprise}
                  onChange={(e) => setEntreprise(e.target.value)}
                  placeholder={t("chat.entreprisePlaceholder")}
                  className="w-full bg-slate-800 border border-slate-600 rounded-xl text-white placeholder-slate-500 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-yukpo-500"
                />
              </div>
            </div>

            {/* Années d'expérience */}
            <div>
              <label className="text-xs font-medium text-slate-400 block mb-1.5">{t('profil.annees')}</label>
              <input
                type="number"
                min="0"
                max="50"
                value={annees}
                onChange={(e) => setAnnees(e.target.value)}
                placeholder={t("chat.anneesPlaceholder")}
                className="w-full bg-slate-800 border border-slate-600 rounded-xl text-white placeholder-slate-500 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-yukpo-500"
              />
            </div>

            {/* Bio */}
            <div>
              <label className="text-xs font-medium text-slate-400 block mb-1.5">{t('profil.bio')}</label>
              <textarea
                value={bio}
                onChange={(e) => setBio(e.target.value)}
                placeholder={t("chat.bioPlaceholder")}
                rows={3}
                className="w-full bg-slate-800 border border-slate-600 rounded-xl text-white placeholder-slate-500 px-3 py-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-yukpo-500"
              />
            </div>
          </form>
        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-slate-700 flex-shrink-0 flex gap-3">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 px-4 py-2.5 rounded-xl border border-slate-600 text-slate-300 hover:text-white hover:border-slate-500 text-sm transition-colors"
          >
            {t('common.cancel')}
          </button>
          <button
            type="submit"
            form="profil-form"
            disabled={saving}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-yukpo-600 hover:bg-yukpo-500 text-white text-sm font-semibold transition-colors disabled:opacity-50"
          >
            {saving
              ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              : <Save className="w-4 h-4" />
            }
            {saving ? t('common.saving') : t('common.save')}
          </button>
        </div>
      </motion.div>
    </>
  );
};

// ── Helper lecture fichier ─────────────────────────────────────────────────────

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}
