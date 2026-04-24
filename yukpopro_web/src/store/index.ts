import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { User, ProfilPro, CopiloteMessage } from "@/types";

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
        localStorage.setItem("yukpopro_token", token);
        set({ user, token, isAuthenticated: true });
      },

      logout: () => {
        localStorage.removeItem("yukpopro_token");
        localStorage.removeItem("yukpopro_user");
        set({ user: null, token: null, isAuthenticated: false });
      },
    }),
    {
      name: "yukpopro_auth",
      partialize: (state) => ({ user: state.user, token: state.token, isAuthenticated: state.isAuthenticated }),
    }
  )
);

// ── Profil Store ──────────────────────────────────────────────────────────────

interface ProfilState {
  profil: ProfilPro | null;
  profilCharge: boolean;
  setProfil: (p: ProfilPro) => void;
  clearProfil: () => void;
}

export const useProfilStore = create<ProfilState>()((set) => ({
  profil: null,
  profilCharge: false,
  setProfil: (p) => set({ profil: p, profilCharge: true }),
  clearProfil: () => set({ profil: null, profilCharge: false }),
}));

// ── Chat Store (YukpoPro — interface unifiée) ─────────────────────────────────

export interface ActiveDocument {
  id: number;
  titre: string;
  type_doc: string;
  contenu_genere?: string;
}

export interface ChatSession {
  id: string;
  title: string;
  createdAt: string;
  messages: CopiloteMessage[];
  activeDocument?: ActiveDocument | null;
}

interface ChatState {
  sessions: ChatSession[];
  activeSessionId: string | null;
  isLoading: boolean;
  // Compatibilité ancienne interface
  isOpen: boolean;
  isFullscreen: boolean;

  // Accesseurs
  activeMessages: () => CopiloteMessage[];
  activeSession: () => ChatSession | null;

  // Actions
  newSession: () => string;
  selectSession: (id: string) => void;
  deleteSession: (id: string) => void;
  addMessage: (msg: CopiloteMessage) => void;
  updateLastAssistantMessage: (content: string, agentUtilise?: string | null, fichiers?: string[], coutLlm?: import("@/types").CoutLLM | null, navSuggestions?: import("@/types").NavigationSuggestion[]) => void;
  setLoading: (loading: boolean) => void;
  setOpen: (open: boolean) => void;
  setFullscreen: (fs: boolean) => void;
  clearSession: () => void;
  // Document actif (édition depuis Mes Documents)
  setActiveDocument: (doc: ActiveDocument | null) => void;
  activeDocument: () => ActiveDocument | null;
  // Aliases
  setSessionId: (id: string) => void;
  setNbMessages: (n: number) => void;
}

const _makeSession = (): ChatSession => ({
  id: crypto.randomUUID(),
  title: "Nouvelle conversation",
  createdAt: new Date().toISOString(),
  messages: [],
});

export const useCopiloteStore = create<ChatState>()(
  persist(
    (set, get) => ({
      sessions: [],
      activeSessionId: null,
      isLoading: false,
      isOpen: false,
      isFullscreen: false,

      activeMessages: () => {
        const s = get().sessions.find(s => s.id === get().activeSessionId);
        return s?.messages ?? [];
      },
      activeSession: () =>
        get().sessions.find(s => s.id === get().activeSessionId) ?? null,

      newSession: () => {
        const session = _makeSession();
        set(state => ({
          sessions: [session, ...state.sessions].slice(0, 50),
          activeSessionId: session.id,
        }));
        return session.id;
      },

      selectSession: (id) => set({ activeSessionId: id }),

      deleteSession: (id) =>
        set(state => {
          const sessions = state.sessions.filter(s => s.id !== id);
          const activeSessionId = state.activeSessionId === id
            ? (sessions[0]?.id ?? null)
            : state.activeSessionId;
          return { sessions, activeSessionId };
        }),

      addMessage: (msg) =>
        set(state => {
          let { sessions, activeSessionId } = state;
          // Créer session si aucune active
          if (!activeSessionId || !sessions.find(s => s.id === activeSessionId)) {
            const session = _makeSession();
            sessions = [session, ...sessions].slice(0, 50);
            activeSessionId = session.id;
          }
          return {
            sessions: sessions.map(s =>
              s.id === activeSessionId
                ? {
                    ...s,
                    messages: [...s.messages, msg],
                    // Titre = premier message utilisateur (tronqué)
                    title: s.messages.length === 0 && msg.role === "user"
                      ? (msg.content as string).slice(0, 50)
                      : s.title,
                  }
                : s
            ),
            activeSessionId,
          };
        }),

      updateLastAssistantMessage: (content, agentUtilise, fichiers, coutLlm, navSuggestions) =>
        set(state => ({
          sessions: state.sessions.map(s =>
            s.id === state.activeSessionId
              ? {
                  ...s,
                  messages: s.messages.map((m, i) =>
                    i === s.messages.length - 1 && m.role === "assistant" && m.loading
                      ? { ...m, content, loading: false, agent_utilise: agentUtilise, fichiers, cout_llm: coutLlm, navigation_suggestions: navSuggestions }
                      : m
                  ),
                }
              : s
          ),
        })),

      setActiveDocument: (doc) =>
        set(state => ({
          sessions: state.sessions.map(s =>
            s.id === state.activeSessionId ? { ...s, activeDocument: doc } : s
          ),
        })),
      activeDocument: () => {
        const s = get().sessions.find(s => s.id === get().activeSessionId);
        return s?.activeDocument ?? null;
      },

      setLoading: (loading) => set({ isLoading: loading }),
      setOpen: (open) => set({ isOpen: open }),
      setFullscreen: (fs) => set({ isFullscreen: fs }),
      clearSession: () => {
        const session = _makeSession();
        set(state => ({
          sessions: [session, ...state.sessions].slice(0, 50),
          activeSessionId: session.id,
        }));
      },
      // Aliases pour compatibilité
      setSessionId: (id) => set({ activeSessionId: id }),
      setNbMessages: () => {},
    }),
    {
      name: "yukpopro_chat_v2",
      partialize: (s) => ({ sessions: s.sessions.slice(0, 20), activeSessionId: s.activeSessionId }),
    }
  )
);

// ── Documents Store (historique des documents générés — persisté backend) ─────

export interface DocGenere {
  id: string;           // string pour compatibilité (backend renvoie number)
  backendId?: number;   // ID côté base de données
  titre: string;
  type: string;         // rapport | slides | traduction | autre
  contenu?: string;     // markdown si disponible
  fichier?: string;     // nom du fichier téléchargeable
  createdAt: string;
  contexteConversation?: string;  // prompt / extrait de conversation
  meta?: Record<string, unknown>;
}

interface DocsState {
  documents: DocGenere[];
  loading: boolean;
  // Actions locales (UI immédiate)
  addDocument: (doc: Omit<DocGenere, "id" | "createdAt">) => void;
  removeDocument: (id: string) => void;
  updateDocument: (id: string, updates: Partial<DocGenere>) => void;
  clearAll: () => void;
  // Sync backend
  chargerDepuisBackend: () => Promise<void>;
  sauvegarderVersBackend: (doc: Omit<DocGenere, "id" | "createdAt">) => Promise<number | null>;
  supprimerVersBackend: (backendId: number) => Promise<void>;
}

export const useDocsStore = create<DocsState>()(
  persist(
    (set, get) => ({
      documents: [],
      loading: false,

      addDocument: (doc) =>
        set(state => ({
          documents: [
            { ...doc, id: crypto.randomUUID(), createdAt: new Date().toISOString() },
            ...state.documents,
          ].slice(0, 100),
        })),

      removeDocument: (id) =>
        set(state => ({ documents: state.documents.filter(d => d.id !== id) })),

      updateDocument: (id, updates) =>
        set(state => ({
          documents: state.documents.map(d => d.id === id ? { ...d, ...updates } : d),
        })),

      clearAll: () => set({ documents: [] }),

      chargerDepuisBackend: async () => {
        set({ loading: true });
        try {
          const { generateurApi } = await import("@/api/client");
          const res = await generateurApi.historiqueDocuments();
          const docs: DocGenere[] = res.documents.map(d => ({
            id: String(d.id),
            backendId: d.id,
            titre: d.titre,
            type: d.type_doc,
            contenu: d.contenu_genere,
            fichier: d.fichier,
            createdAt: d.cree_le,
            contexteConversation: d.contenu_source,
            meta: d.meta,
          }));
          set({ documents: docs, loading: false });
        } catch {
          set({ loading: false });
        }
      },

      sauvegarderVersBackend: async (doc) => {
        try {
          const { generateurApi } = await import("@/api/client");
          const res = await generateurApi.sauvegarderDocument({
            titre: doc.titre,
            type_doc: doc.type || "autre",
            fichier: doc.fichier,
            contenu_source: doc.contexteConversation,
            contenu_genere: doc.contenu,
            meta: doc.meta,
          });
          // Mettre à jour le doc local avec le backendId
          get().addDocument({ ...doc, backendId: res.id });
          return res.id;
        } catch {
          // Fallback : juste stockage local
          get().addDocument(doc);
          return null;
        }
      },

      supprimerVersBackend: async (backendId) => {
        try {
          const { generateurApi } = await import("@/api/client");
          await generateurApi.supprimerDocument(backendId);
        } catch { /* non bloquant */ }
        set(state => ({
          documents: state.documents.filter(d => d.backendId !== backendId),
        }));
      },
    }),
    { name: "yukpopro_docs_v2", partialize: (s) => ({ documents: s.documents }) }
  )
);

// ── UI Store ──────────────────────────────────────────────────────────────────

export type Theme = "light" | "dark" | "system";

const applyThemeClass = (theme: Theme) => {
  if (typeof document === "undefined") return;
  const resolved =
    theme === "system"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : theme;
  document.documentElement.classList.toggle("dark", resolved === "dark");
  document.documentElement.dataset.theme = resolved;
};

interface UIState {
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  setSidebarCollapsed: (v: boolean) => void;
  theme: Theme;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set, get) => ({
      sidebarCollapsed: false,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),
      theme: "light",
      setTheme: (t) => {
        applyThemeClass(t);
        set({ theme: t });
      },
      toggleTheme: () => {
        const current = get().theme;
        const next: Theme = current === "light" ? "dark" : "light";
        applyThemeClass(next);
        set({ theme: next });
      },
    }),
    {
      name: "yukpopro_ui",
      onRehydrateStorage: () => (state) => {
        if (state) applyThemeClass(state.theme);
        else applyThemeClass("light");
      },
    }
  )
);

// Apply theme as early as possible (before React paints) to avoid flash
if (typeof window !== "undefined") {
  try {
    const raw = localStorage.getItem("yukpopro_ui");
    const parsed = raw ? JSON.parse(raw) : null;
    const stored: Theme = parsed?.state?.theme ?? "light";
    applyThemeClass(stored);
  } catch {
    applyThemeClass("light");
  }
}
