import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { User, ChatMessage, ChatSession, DocGenere } from "@/types";

// ── Auth Store ────────────────────────────────────────────────────────────────

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  setAuth: (user: User, token: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      isAuthenticated: false,

      setAuth: (user, token) => {
        localStorage.setItem("yukpoassurance_token", token);
        set({ user, token, isAuthenticated: true });
      },

      logout: () => {
        localStorage.removeItem("yukpoassurance_token");
        set({ user: null, token: null, isAuthenticated: false });
      },
    }),
    {
      name: "yukpoassurance_auth",
      partialize: (s) => ({ user: s.user, token: s.token, isAuthenticated: s.isAuthenticated }),
    }
  )
);

// ── Chat Store ────────────────────────────────────────────────────────────────

interface ChatState {
  sessions: ChatSession[];
  activeSessionId: string | null;
  isLoading: boolean;

  activeMessages: () => ChatMessage[];
  activeSession: () => ChatSession | null;
  newSession: () => string;
  selectSession: (id: string) => void;
  deleteSession: (id: string) => void;
  addMessage: (msg: ChatMessage) => void;
  updateLastAssistantMessage: (content: string, agent?: string | null) => void;
  setLoading: (v: boolean) => void;
  clearSession: () => void;
}

const _makeSession = (): ChatSession => ({
  id: crypto.randomUUID(),
  title: "Nouvelle conversation",
  createdAt: new Date().toISOString(),
  messages: [],
});

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      sessions: [],
      activeSessionId: null,
      isLoading: false,

      activeMessages: () => {
        const s = get().sessions.find((s) => s.id === get().activeSessionId);
        return s?.messages ?? [];
      },

      activeSession: () =>
        get().sessions.find((s) => s.id === get().activeSessionId) ?? null,

      newSession: () => {
        const session = _makeSession();
        set((state) => ({
          sessions: [session, ...state.sessions].slice(0, 50),
          activeSessionId: session.id,
        }));
        return session.id;
      },

      selectSession: (id) => set({ activeSessionId: id }),

      deleteSession: (id) =>
        set((state) => {
          const sessions = state.sessions.filter((s) => s.id !== id);
          return {
            sessions,
            activeSessionId:
              state.activeSessionId === id ? (sessions[0]?.id ?? null) : state.activeSessionId,
          };
        }),

      addMessage: (msg) =>
        set((state) => {
          let { sessions, activeSessionId } = state;
          if (!activeSessionId || !sessions.find((s) => s.id === activeSessionId)) {
            const session = _makeSession();
            sessions = [session, ...sessions].slice(0, 50);
            activeSessionId = session.id;
          }
          return {
            sessions: sessions.map((s) =>
              s.id === activeSessionId
                ? {
                    ...s,
                    messages: [...s.messages, msg],
                    title:
                      s.messages.length === 0 && msg.role === "user"
                        ? (msg.content as string).slice(0, 50)
                        : s.title,
                  }
                : s
            ),
            activeSessionId,
          };
        }),

      updateLastAssistantMessage: (content, agent) =>
        set((state) => ({
          sessions: state.sessions.map((s) =>
            s.id === state.activeSessionId
              ? {
                  ...s,
                  messages: s.messages.map((m, i) =>
                    i === s.messages.length - 1 && m.role === "assistant" && m.loading
                      ? { ...m, content, loading: false, agent_utilise: agent }
                      : m
                  ),
                }
              : s
          ),
        })),

      setLoading: (v) => set({ isLoading: v }),

      clearSession: () => {
        const session = _makeSession();
        set((state) => ({
          sessions: [session, ...state.sessions].slice(0, 50),
          activeSessionId: session.id,
        }));
      },
    }),
    {
      name: "yukpoassurance_chat_v1",
      partialize: (s) => ({ sessions: s.sessions.slice(0, 20), activeSessionId: s.activeSessionId }),
    }
  )
);

// ── Documents Store ───────────────────────────────────────────────────────────

interface DocsState {
  documents: DocGenere[];
  addDocument: (doc: Omit<DocGenere, "id" | "createdAt">) => void;
  removeDocument: (id: string) => void;
  clearAll: () => void;
}

export const useDocsStore = create<DocsState>()(
  persist(
    (set) => ({
      documents: [],

      addDocument: (doc) =>
        set((state) => ({
          documents: [
            { ...doc, id: crypto.randomUUID(), createdAt: new Date().toISOString() },
            ...state.documents,
          ].slice(0, 100),
        })),

      removeDocument: (id) =>
        set((state) => ({ documents: state.documents.filter((d) => d.id !== id) })),

      clearAll: () => set({ documents: [] }),
    }),
    { name: "yukpoassurance_docs_v1", partialize: (s) => ({ documents: s.documents }) }
  )
);

// ── UI Store ──────────────────────────────────────────────────────────────────

interface UIState {
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  setSidebarCollapsed: (v: boolean) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),
    }),
    { name: "yukpoassurance_ui" }
  )
);
