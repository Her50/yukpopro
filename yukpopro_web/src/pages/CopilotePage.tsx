import { useEffect, useRef, KeyboardEvent, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Send, RefreshCw, Sparkles, Bot, Maximize2, Minimize2 } from "lucide-react";
import toast from "react-hot-toast";
import { Card, Spinner, Button } from "@/components/ui";
import { useCopiloteStore, useProfilStore } from "@/store";
import { copiloteApi } from "@/api/client";

const genId = () => `${Date.now()}-${Math.random().toString(36).slice(2)}`;

export const CopilotePage = () => {
  const { messages, isLoading, addMessage, updateLastAssistantMessage, setLoading, clearSession, setSessionId, setNbMessages } = useCopiloteStore();
  const { profil } = useProfilStore();
  const [inputValue, setInputValue] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (messages.length === 0) {
      copiloteApi.suggestions().then((d) => setSuggestions(d.suggestions?.slice(0, 4) || [])).catch(() => {});
    }
  }, [messages.length]);

  const sendMessage = async (text: string) => {
    const msg = text.trim();
    if (!msg || isLoading) return;
    setInputValue("");
    setSuggestions([]);

    addMessage({ id: genId(), role: "user", content: msg, timestamp: new Date().toISOString() });
    addMessage({ id: genId(), role: "assistant", content: "", timestamp: new Date().toISOString(), loading: true });
    setLoading(true);

    try {
      const res = await copiloteApi.chat(msg, profil?.pays);
      updateLastAssistantMessage(res.reponse, res.agent_utilise);
      setSessionId(res.session_id);
      setNbMessages(res.nb_messages_session);
    } catch {
      updateLastAssistantMessage("Désolé, une erreur est survenue. Veuillez réessayer.", null);
      toast.error("Erreur de connexion");
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
    copiloteApi.suggestions().then((d) => setSuggestions(d.suggestions?.slice(0, 4) || [])).catch(() => {});
  };

  return (
    <div className="flex flex-col h-screen max-h-screen">
      {/* Header */}
      <div className="px-6 py-4 border-b border-slate-700/50 flex items-center justify-between bg-slate-900/50">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-yukpo-gradient flex items-center justify-center shadow-yukpo">
            <svg width="20" height="20" viewBox="0 0 64 64" fill="none">
              <path d="M10 8 L32 32" stroke="white" strokeWidth="10" strokeLinecap="round"/>
              <path d="M54 8 L32 32" stroke="white" strokeWidth="10" strokeLinecap="round"/>
              <path d="M32 32 L32 56" stroke="white" strokeWidth="10" strokeLinecap="round"/>
            </svg>
          </div>
          <div>
            <h1 className="font-display font-bold text-white">Yukpo Assistant</h1>
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
              <span className="text-xs text-slate-400">
                {profil?.metier ? `Yukpo ${profil.metier} · ${profil.pays}` : "Yukpo disponible"}
              </span>
            </div>
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={handleNouvelle} icon={<RefreshCw className="w-4 h-4" />}>
          Nouvelle session
        </Button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-6 max-w-2xl mx-auto text-center">
            <div className="w-20 h-20 rounded-3xl bg-yukpo-gradient flex items-center justify-center shadow-yukpo-lg">
              <svg width="40" height="40" viewBox="0 0 64 64" fill="none">
                <path d="M10 8 L32 32" stroke="white" strokeWidth="9" strokeLinecap="round"/>
                <path d="M54 8 L32 32" stroke="white" strokeWidth="9" strokeLinecap="round"/>
                <path d="M32 32 L32 56" stroke="white" strokeWidth="9" strokeLinecap="round"/>
              </svg>
            </div>
            <div>
              <h2 className="text-xl font-display font-bold text-white">Bonjour ! Je suis Yukpo Assistant</h2>
              <p className="text-slate-400 mt-2 leading-relaxed">
                Votre assistant YukpoPro. Je réponds à toutes vos questions —
                métier, calculs, réglementation africaine, rédaction, traduction, ou simplement pour discuter.
              </p>
            </div>

            {suggestions.length > 0 && (
              <div className="w-full grid grid-cols-1 md:grid-cols-2 gap-3">
                {suggestions.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => sendMessage(s)}
                    className="text-left text-sm text-slate-300 bg-slate-800 hover:bg-slate-700 border border-slate-700 hover:border-yukpo-500/50 rounded-xl px-4 py-3 transition-all"
                  >
                    <div className="flex items-start gap-2">
                      <Sparkles className="w-3.5 h-3.5 text-yukpo-400 flex-shrink-0 mt-0.5" />
                      {s}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <>
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex gap-3 max-w-4xl ${msg.role === "user" ? "ml-auto flex-row-reverse" : ""}`}
              >
                {msg.role === "assistant" && (
                  <div className="w-8 h-8 rounded-xl bg-yukpo-gradient flex items-center justify-center flex-shrink-0 mt-1 shadow-md">
                    <svg width="14" height="14" viewBox="0 0 64 64" fill="none">
                      <path d="M10 8 L32 32" stroke="white" strokeWidth="12" strokeLinecap="round"/>
                      <path d="M54 8 L32 32" stroke="white" strokeWidth="12" strokeLinecap="round"/>
                      <path d="M32 32 L32 56" stroke="white" strokeWidth="12" strokeLinecap="round"/>
                    </svg>
                  </div>
                )}
                <div className={`flex flex-col ${msg.role === "user" ? "items-end" : ""}`}>
                  <div
                    className={`px-4 py-3 rounded-2xl text-sm max-w-2xl ${
                      msg.role === "user"
                        ? "bg-yukpo-500 text-white rounded-tr-sm"
                        : "bg-slate-800 text-slate-100 rounded-tl-sm border border-slate-700/50"
                    }`}
                  >
                    {msg.loading ? (
                      <div className="flex items-center gap-1.5 py-0.5">
                        {[0, 1, 2].map((i) => (
                          <span key={i} className="w-2 h-2 bg-yukpo-400 rounded-full animate-bounce" style={{ animationDelay: `${i * 0.15}s` }} />
                        ))}
                      </div>
                    ) : (
                      <ReactMarkdown
                        className="prose prose-sm prose-invert max-w-none"
                        components={{
                          code: ({ children }) => (
                            <code className="bg-slate-900 text-yukpo-300 px-1.5 py-0.5 rounded font-mono text-xs">{children}</code>
                          ),
                          pre: ({ children }) => (
                            <pre className="bg-slate-900 p-3 rounded-xl overflow-x-auto text-xs my-2 border border-slate-700">{children}</pre>
                          ),
                          table: ({ children }) => (
                            <div className="overflow-x-auto">
                              <table className="text-xs border-collapse border border-slate-600 w-full">{children}</table>
                            </div>
                          ),
                          th: ({ children }) => <th className="border border-slate-600 px-2 py-1 bg-slate-700 text-left">{children}</th>,
                          td: ({ children }) => <td className="border border-slate-600 px-2 py-1">{children}</td>,
                        }}
                      >
                        {msg.content}
                      </ReactMarkdown>
                    )}
                  </div>
                  {msg.agent_utilise && (
                    <span className="inline-flex items-center gap-1 text-xs bg-yukpo-500/20 text-yukpo-300 border border-yukpo-500/30 rounded-full px-2.5 py-1 mt-1.5">
                      <Bot className="w-3 h-3" /> Agent {msg.agent_utilise} activé
                    </span>
                  )}
                  <span className="text-xs text-slate-600 mt-1 px-1">
                    {new Date(msg.timestamp).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
                  </span>
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Input zone */}
      <div className="px-6 py-4 border-t border-slate-700/50 bg-slate-900/50">
        <div className="max-w-4xl mx-auto">
          <div className="flex gap-3 bg-slate-800 rounded-2xl border border-slate-600/50 focus-within:border-yukpo-500/50 transition-colors p-2">
            <textarea
              ref={inputRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Posez votre question… (Entrée pour envoyer, Shift+Entrée pour nouvelle ligne)"
              rows={1}
              className="flex-1 bg-transparent text-white placeholder-slate-500 text-sm px-3 py-2 resize-none focus:outline-none min-h-[44px] max-h-40"
              onInput={(e) => {
                const t = e.target as HTMLTextAreaElement;
                t.style.height = "auto";
                t.style.height = Math.min(t.scrollHeight, 160) + "px";
              }}
            />
            <button
              onClick={() => sendMessage(inputValue)}
              disabled={!inputValue.trim() || isLoading}
              className={`w-10 h-10 mt-1 rounded-xl flex items-center justify-center flex-shrink-0 transition-all ${
                inputValue.trim() && !isLoading
                  ? "bg-yukpo-gradient hover:opacity-90 text-white shadow-md active:scale-95"
                  : "bg-slate-700 text-slate-500 cursor-not-allowed"
              }`}
            >
              {isLoading ? <Spinner size="sm" /> : <Send className="w-4 h-4" />}
            </button>
          </div>
          <p className="text-xs text-slate-600 mt-2 text-center">
            Yukpo Assistant peut faire appel aux agents spécialisés si votre question le nécessite.
          </p>
        </div>
      </div>
    </div>
  );
};
