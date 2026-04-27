import { useState, useRef, useEffect, useCallback } from "react";
import {
  Send, Plus, Trash2, MessageSquare, Bot, User, Loader2,
  ShieldCheck, FileText, BarChart3, Scale, Car, Sparkles, Image,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn, Spinner } from "@/components/ui";
import { useChatStore, useAuthStore } from "@/store";
import { chatApi } from "@/api/client";
import type { ChatMessage } from "@/types";

// ── Agent shortcuts ───────────────────────────────────────────────────────────

const AGENT_SHORTCUTS = [
  { icon: ShieldCheck, label: "Nouveau sinistre",    instruction: "MODE DÉCLARATION — déclarer un nouveau sinistre" },
  { icon: FileText,    label: "Nouvelle police",     instruction: "Je veux émettre une nouvelle police RC Auto" },
  { icon: Car,         label: "Tarif RC Auto",       instruction: "Calculer la prime RC Auto — branche B03" },
  { icon: Scale,       label: "Ratios CIMA",         instruction: "Affiche les ratios de solvabilité CIMA de ma compagnie" },
  { icon: BarChart3,   label: "Provisions CIMA",     instruction: "Calculer les provisions techniques CIMA" },
  { icon: Sparkles,    label: "Rapport expertise",   instruction: "Générer un rapport d'expertise sinistre" },
];

// ── Message Bubble ─────────────────────────────────────────────────────────────

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] px-4 py-2.5 rounded-2xl rounded-tr-sm text-sm text-white"
          style={{ background: "linear-gradient(135deg, #0054A6 0%, #0079D4 100%)" }}>
          {msg.content}
        </div>
      </div>
    );
  }

  if (msg.loading) {
    return (
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ background: "rgba(0,84,166,0.15)", border: "1px solid rgba(0,176,240,0.2)" }}>
          <Bot className="w-4 h-4 text-ciel-400" />
        </div>
        <div className="flex items-center gap-1.5 px-4 py-2.5 rounded-2xl rounded-tl-sm"
          style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.06)" }}>
          {[0, 150, 300].map((d) => (
            <span key={d} className="w-1.5 h-1.5 rounded-full bg-ciel-400 animate-bounce"
              style={{ animationDelay: `${d}ms` }} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3">
      <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 mt-1"
        style={{ background: "rgba(0,84,166,0.15)", border: "1px solid rgba(0,176,240,0.2)" }}>
        <Bot className="w-4 h-4 text-ciel-400" />
      </div>
      <div className="flex-1 min-w-0">
        {msg.agent_utilise && (
          <p className="text-[10px] text-ciel-500 mb-1 font-medium uppercase tracking-wide">
            {msg.agent_utilise.replace(/_/g, " ")}
          </p>
        )}
        <div className="prose prose-invert prose-assurance prose-sm max-w-none"
          style={{ color: "#D1D5DB" }}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
        </div>
        {msg.fichiers && msg.fichiers.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {msg.fichiers.map((f, i) => (
              <a key={i} href={f} target="_blank" rel="noreferrer"
                className="inline-flex items-center gap-1 text-xs text-ciel-400 hover:text-ciel-300 underline">
                <FileText className="w-3 h-3" />{f.split("/").pop()}
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main Chat Page ────────────────────────────────────────────────────────────

export function ChatPage() {
  const { user }           = useAuthStore();
  const chatStore          = useChatStore();
  const messages           = chatStore.activeMessages();
  const sessions           = chatStore.sessions;
  const activeId           = chatStore.activeSessionId;
  const isLoading          = chatStore.isLoading;

  const [input, setInput]  = useState("");
  const [images, setImages] = useState<string[]>([]);
  const bottomRef          = useRef<HTMLDivElement>(null);
  const textRef            = useRef<HTMLTextAreaElement>(null);
  const fileRef            = useRef<HTMLInputElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = useCallback(async (text?: string) => {
    const content = (text ?? input).trim();
    if (!content || isLoading) return;
    setInput("");

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(), role: "user", content,
      timestamp: new Date().toISOString(),
    };
    chatStore.addMessage(userMsg);

    const assistantMsg: ChatMessage = {
      id: crypto.randomUUID(), role: "assistant", content: "", loading: true,
    };
    chatStore.addMessage(assistantMsg);
    chatStore.setLoading(true);

    try {
      const res = await chatApi.sendMessage({
        message: content,
        session_id: activeId || undefined,
        images: images.length ? images : undefined,
      });
      const d = res.data as { response?: string; message?: string; agent_utilise?: string };
      chatStore.updateLastAssistantMessage(
        d.response || d.message || "Réponse reçue.",
        d.agent_utilise
      );
    } catch {
      chatStore.updateLastAssistantMessage("Erreur de connexion — vérifiez votre réseau.");
    } finally {
      chatStore.setLoading(false);
      setImages([]);
    }
  }, [input, isLoading, activeId, images, chatStore]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    Array.from(files).forEach((file) => {
      const reader = new FileReader();
      reader.onload = () => setImages((prev) => [...prev, reader.result as string]);
      reader.readAsDataURL(file);
    });
    e.target.value = "";
  };

  const isEmpty = messages.length === 0;

  return (
    <div className="flex h-full min-h-0">

      {/* Sidebar sessions */}
      <div className="w-56 flex-shrink-0 flex flex-col border-r border-white/[0.06]" style={{ background: "#0D1117" }}>
        <div className="p-3 border-b border-white/[0.06]">
          <button onClick={() => chatStore.newSession()}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-medium text-white transition-all hover:brightness-110"
            style={{ background: "linear-gradient(135deg, #0054A6 0%, #00B0F0 100%)" }}>
            <Plus className="w-4 h-4" />
            Nouvelle conversation
          </button>
        </div>
        <div className="flex-1 overflow-y-auto py-2 space-y-0.5 px-2">
          {sessions.map((s) => (
            <button key={s.id} onClick={() => chatStore.selectSession(s.id)}
              className={cn(
                "w-full text-left px-3 py-2.5 rounded-xl text-sm transition-all flex items-center justify-between group",
                s.id === activeId
                  ? "text-white bg-assurance-500/10 border border-assurance-500/20"
                  : "text-gray-400 hover:text-gray-200 hover:bg-white/[0.04] border border-transparent"
              )}>
              <div className="flex items-center gap-2 min-w-0">
                <MessageSquare className="w-3.5 h-3.5 flex-shrink-0 text-gray-500" />
                <span className="truncate text-xs">{s.title}</span>
              </div>
              <button onClick={(e) => { e.stopPropagation(); chatStore.deleteSession(s.id); }}
                className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-red-400 transition-all flex-shrink-0 ml-1">
                <Trash2 className="w-3 h-3" />
              </button>
            </button>
          ))}
        </div>
      </div>

      {/* Zone de chat */}
      <div className="flex-1 flex flex-col min-w-0">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.06]">
          <div>
            <h2 className="text-base font-semibold text-white">YukpoPro Assurance</h2>
            <p className="text-xs text-gray-500 mt-0.5">Agents spécialisés CIMA · Sinistres · Souscription · Comptabilité</p>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            <span className="text-xs text-green-400">En ligne</span>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {isEmpty && (
            <div className="h-full flex flex-col items-center justify-center text-center py-10">
              <div className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
                style={{ background: "linear-gradient(135deg, #0054A6 0%, #00B0F0 100%)", boxShadow: "0 0 30px rgba(0,84,166,0.3)" }}>
                <ShieldCheck className="w-8 h-8 text-white" />
              </div>
              <h3 className="text-lg font-semibold text-white mb-2">
                Bonjour{user?.nom ? `, ${user.nom}` : ""} !
              </h3>
              <p className="text-sm text-gray-400 mb-8 max-w-sm">
                Je suis l'assistant IA de YukpoAssurance, spécialisé en droit CIMA. Comment puis-je vous aider ?
              </p>
              <div className="grid grid-cols-2 gap-2 w-full max-w-sm">
                {AGENT_SHORTCUTS.map(({ icon: Icon, label, instruction }) => (
                  <button key={label} onClick={() => sendMessage(instruction)}
                    className="flex items-center gap-2 p-3 rounded-xl text-sm text-left text-gray-300 hover:text-white transition-all border border-white/[0.06] hover:border-assurance-500/30 hover:bg-assurance-500/05"
                    style={{ background: "rgba(255,255,255,0.03)" }}>
                    <Icon className="w-4 h-4 text-ciel-400 flex-shrink-0" />
                    <span className="text-xs leading-tight">{label}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg) => (
            <MessageBubble key={msg.id} msg={msg} />
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Images preview */}
        {images.length > 0 && (
          <div className="px-6 py-2 flex gap-2 flex-wrap border-t border-white/[0.06]">
            {images.map((img, i) => (
              <div key={i} className="relative w-14 h-14 rounded-lg overflow-hidden flex-shrink-0">
                <img src={img} alt="" className="w-full h-full object-cover" />
                <button onClick={() => setImages((prev) => prev.filter((_, j) => j !== i))}
                  className="absolute inset-0 bg-black/50 opacity-0 hover:opacity-100 flex items-center justify-center text-white text-xs transition-opacity">
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Input */}
        <div className="px-6 py-4 border-t border-white/[0.06]">
          <div className="flex gap-2 items-end rounded-2xl border border-white/[0.08] px-4 py-3 focus-within:border-assurance-500/40 transition-colors"
            style={{ background: "rgba(255,255,255,0.04)" }}>
            <button onClick={() => fileRef.current?.click()}
              className="text-gray-500 hover:text-ciel-400 transition-colors flex-shrink-0 mb-0.5">
              <Image className="w-5 h-5" />
            </button>
            <input ref={fileRef} type="file" accept="image/*,.pdf" multiple className="hidden" onChange={handleImageUpload} />
            <textarea
              ref={textRef}
              rows={1}
              className="flex-1 bg-transparent text-sm text-white placeholder-gray-600 resize-none focus:outline-none leading-6 max-h-36"
              placeholder="Déclarer un sinistre, calculer une prime, vérifier un ratio CIMA…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              style={{ scrollbarWidth: "none" }}
            />
            <button
              onClick={() => sendMessage()}
              disabled={!input.trim() || isLoading}
              className="w-9 h-9 flex items-center justify-center rounded-xl text-white disabled:opacity-40 transition-all hover:brightness-110 flex-shrink-0"
              style={{ background: "linear-gradient(135deg, #0054A6 0%, #00B0F0 100%)" }}
            >
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            </button>
          </div>
          <p className="text-xs text-gray-600 text-center mt-2">
            Shift+Entrée pour saut de ligne · CIMA Art. 12-bis · Réponses soumises à validation humaine
          </p>
        </div>
      </div>
    </div>
  );
}
