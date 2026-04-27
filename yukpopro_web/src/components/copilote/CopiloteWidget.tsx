import { useState, useRef, useEffect, KeyboardEvent } from "react";
import ReactMarkdown from "react-markdown";
import {
  MessageSquare, X, Send, Minimize2, Maximize2, Bot,
  RefreshCw, Sparkles, ChevronDown,
} from "lucide-react";
import { cn, Button, Spinner } from "@/components/ui";
import { useCopiloteStore, useProfilStore } from "@/store";
import { copiloteApi } from "@/api/client";
import type { CopiloteMessage } from "@/types";

// UUID fallback si crypto.randomUUID non dispo
const genId = () => `${Date.now()}-${Math.random().toString(36).slice(2)}`;

const TypingDots = () => (
  <div className="flex items-center gap-1 py-1">
    {[0, 1, 2].map((i) => (
      <span
        key={i}
        className="w-2 h-2 bg-yukpo-400 rounded-full animate-bounce"
        style={{ animationDelay: `${i * 0.15}s` }}
      />
    ))}
  </div>
);

const AgentBadge = ({ agent }: { agent: string }) => (
  <span className="inline-flex items-center gap-1 text-xs bg-yukpo-500/20 text-yukpo-300 border border-yukpo-500/30 rounded-full px-2 py-0.5 mt-1">
    <Bot className="w-3 h-3" />
    Agent {agent}
  </span>
);

const MessageBubble = ({ msg }: { msg: CopiloteMessage }) => {
  const isUser = msg.role === "user";
  return (
    <div className={cn("flex gap-2 max-w-[85%]", isUser && "ml-auto flex-row-reverse")}>
      {/* Avatar */}
      {!isUser && (
        <div className="w-7 h-7 rounded-full bg-yukpo-gradient flex items-center justify-center flex-shrink-0 mt-1">
          <svg width="14" height="14" viewBox="0 0 64 64" fill="none">
            <path d="M10 8 L32 32" stroke="white" strokeWidth="12" strokeLinecap="round"/>
            <path d="M54 8 L32 32" stroke="white" strokeWidth="12" strokeLinecap="round"/>
            <path d="M32 32 L32 56" stroke="white" strokeWidth="12" strokeLinecap="round"/>
          </svg>
        </div>
      )}

      <div className={cn("flex flex-col", isUser && "items-end")}>
        <div
          className={cn(
            "px-3.5 py-2.5 rounded-2xl text-sm",
            isUser
              ? "bg-yukpo-500 text-white rounded-tr-sm"
              : "bg-slate-700/80 text-slate-100 rounded-tl-sm border border-slate-600/50"
          )}
        >
          {msg.loading ? (
            <TypingDots />
          ) : (
            <ReactMarkdown
              className="prose prose-sm prose-invert max-w-none"
              components={{
                code: ({ children }) => (
                  <code className="bg-slate-900 text-yukpo-300 px-1 py-0.5 rounded text-xs font-mono">
                    {children}
                  </code>
                ),
                pre: ({ children }) => (
                  <pre className="bg-slate-900 p-2 rounded-lg overflow-x-auto text-xs my-1">
                    {children}
                  </pre>
                ),
              }}
            >
              {msg.content}
            </ReactMarkdown>
          )}
        </div>
        {msg.agent_utilise && <AgentBadge agent={msg.agent_utilise} />}
        <span className="text-xs text-slate-500 mt-1 px-1">
          {new Date(msg.timestamp).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
        </span>
      </div>
    </div>
  );
};

export const CopiloteWidget = () => {
  const { isOpen, isFullscreen, isLoading, activeMessages, setOpen, setFullscreen, addMessage, updateLastAssistantMessage, setLoading, clearSession, setSessionId, setNbMessages } = useCopiloteStore();
  const messages = activeMessages();
  const { profil } = useProfilStore();
  const [inputValue, setInputValue] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Scroll auto
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Charger les suggestions à l'ouverture
  useEffect(() => {
    if (isOpen && messages.length === 0) {
      copiloteApi.suggestions().then((data) => {
        setSuggestions(data.suggestions?.slice(0, 3) || []);
      }).catch(() => {});
    }
  }, [isOpen, messages.length]);

  const sendMessage = async (text: string) => {
    const msg = text.trim();
    if (!msg || isLoading) return;
    setInputValue("");

    // Ajouter message user
    addMessage({ id: genId(), role: "user", content: msg, timestamp: new Date().toISOString() });
    // Ajouter placeholder assistant
    const placeholderId = genId();
    addMessage({ id: placeholderId, role: "assistant", content: "", timestamp: new Date().toISOString(), loading: true });
    setLoading(true);

    try {
      const res = await copiloteApi.chat(msg, profil?.pays);
      updateLastAssistantMessage(res.reponse, res.agent_utilise);
      setSessionId(res.session_id);
      setNbMessages(res.nb_messages_session);
      setSuggestions([]);
    } catch {
      updateLastAssistantMessage("Désolé, une erreur est survenue. Veuillez réessayer.", null);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(inputValue);
    }
  };

  const handleNouvelle = async () => {
    await copiloteApi.nouveau().catch(() => {});
    clearSession();
    setSuggestions([]);
    setTimeout(() => {
      copiloteApi.suggestions().then((d) => setSuggestions(d.suggestions?.slice(0, 3) || [])).catch(() => {});
    }, 300);
  };

  // ── Bouton flottant ────────────────────────────────────────────────────────
  if (!isOpen) {
    return (
      <button
        onClick={() => setOpen(true)}
        className={cn(
          "fixed bottom-6 right-6 z-50",
          "w-14 h-14 rounded-2xl",
          "bg-yukpo-gradient shadow-yukpo-lg",
          "flex items-center justify-center",
          "transition-all duration-300 hover:scale-110 active:scale-95",
          "group"
        )}
        aria-label="Ouvrir Yukpo Copilote"
      >
        <MessageSquare className="w-6 h-6 text-white" />
        {/* Badge notification */}
        <span className="absolute -top-1 -right-1 w-4 h-4 bg-gold-500 rounded-full flex items-center justify-center">
          <Sparkles className="w-2.5 h-2.5 text-white" />
        </span>
        {/* Tooltip */}
        <div className="absolute bottom-full right-0 mb-2 px-3 py-1.5 bg-slate-800 text-white text-xs rounded-xl opacity-0 group-hover:opacity-100 whitespace-nowrap border border-slate-700 transition-opacity">
          Yukpo Copilote IA
        </div>
      </button>
    );
  }

  // ── Fenêtre copilote ────────────────────────────────────────────────────────
  return (
    <div
      className={cn(
        "fixed z-50 bg-slate-900 border border-slate-700/50 rounded-2xl shadow-yukpo-lg",
        "flex flex-col overflow-hidden",
        "transition-all duration-300 animate-slide-up",
        isFullscreen
          ? "inset-4 md:inset-8"
          : "bottom-6 right-6 w-96 h-[600px]"
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 bg-yukpo-gradient border-b border-slate-700/30">
        <div className="w-8 h-8 rounded-xl bg-white/20 flex items-center justify-center">
          <svg width="16" height="16" viewBox="0 0 64 64" fill="none">
            <path d="M10 8 L32 32" stroke="white" strokeWidth="12" strokeLinecap="round"/>
            <path d="M54 8 L32 32" stroke="white" strokeWidth="12" strokeLinecap="round"/>
            <path d="M32 32 L32 56" stroke="white" strokeWidth="12" strokeLinecap="round"/>
          </svg>
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-bold text-white">Yukpo Copilote</h3>
          <div className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
            <span className="text-xs text-white/70">
              {profil?.metier ? `Assistant ${profil.metier}` : "Toujours disponible"}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={handleNouvelle}
            className="p-1.5 hover:bg-white/20 rounded-lg text-white/70 hover:text-white transition-colors"
            title="Nouvelle conversation"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            onClick={() => setFullscreen(!isFullscreen)}
            className="p-1.5 hover:bg-white/20 rounded-lg text-white/70 hover:text-white transition-colors"
          >
            {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
          <button
            onClick={() => setOpen(false)}
            className="p-1.5 hover:bg-white/20 rounded-lg text-white/70 hover:text-white transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-4 text-center">
            <div className="w-16 h-16 rounded-2xl bg-yukpo-gradient flex items-center justify-center shadow-yukpo">
              <svg width="32" height="32" viewBox="0 0 64 64" fill="none">
                <path d="M10 8 L32 32" stroke="white" strokeWidth="10" strokeLinecap="round"/>
                <path d="M54 8 L32 32" stroke="white" strokeWidth="10" strokeLinecap="round"/>
                <path d="M32 32 L32 56" stroke="white" strokeWidth="10" strokeLinecap="round"/>
              </svg>
            </div>
            <div>
              <p className="text-white font-semibold">Bonjour ! Je suis Yukpo Copilote</p>
              <p className="text-slate-400 text-sm mt-1">
                Votre assistant professionnel IA. Posez-moi n'importe quelle question.
              </p>
            </div>

            {/* Suggestions */}
            {suggestions.length > 0 && (
              <div className="w-full space-y-2 mt-2">
                <p className="text-xs text-slate-500 font-medium">Suggestions :</p>
                {suggestions.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => sendMessage(s)}
                    className="w-full text-left text-xs text-slate-300 bg-slate-800 hover:bg-slate-700 border border-slate-700 hover:border-yukpo-500/50 rounded-xl px-3 py-2.5 transition-colors"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {messages.map((msg: CopiloteMessage) => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-slate-700/50">
        <div className="flex gap-2 bg-slate-800 rounded-xl border border-slate-600/50 focus-within:border-yukpo-500/50 transition-colors p-1">
          <textarea
            ref={inputRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Posez votre question… (Entrée pour envoyer)"
            rows={1}
            className="flex-1 bg-transparent text-white placeholder-slate-500 text-sm px-3 py-2 resize-none focus:outline-none max-h-32 min-h-[40px]"
            style={{ height: "auto" }}
            onInput={(e) => {
              const t = e.target as HTMLTextAreaElement;
              t.style.height = "auto";
              t.style.height = Math.min(t.scrollHeight, 128) + "px";
            }}
          />
          <button
            onClick={() => sendMessage(inputValue)}
            disabled={!inputValue.trim() || isLoading}
            className={cn(
              "w-9 h-9 mt-0.5 rounded-lg flex items-center justify-center flex-shrink-0 transition-all",
              inputValue.trim() && !isLoading
                ? "bg-yukpo-500 hover:bg-yukpo-600 text-white shadow-md active:scale-95"
                : "bg-slate-700 text-slate-500 cursor-not-allowed"
            )}
          >
            {isLoading ? <Spinner size="sm" /> : <Send className="w-4 h-4" />}
          </button>
        </div>
        <p className="text-xs text-slate-600 mt-1.5 text-center">
          Shift+Entrée pour nouvelle ligne
        </p>
      </div>
    </div>
  );
};
