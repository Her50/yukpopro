import axios from "axios";
import toast from "react-hot-toast";

// ── Instance Axios ────────────────────────────────────────────────────────────

export const apiClient = axios.create({
  baseURL: "/api/v1",
  timeout: 120_000,
  headers: { "Content-Type": "application/json" },
});

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("yukpoassurance_token");
  if (token) (config.headers as Record<string, string>).Authorization = `Bearer ${token}`;
  return config;
});

apiClient.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("yukpoassurance_token");
      window.location.href = "/login";
    } else if (err.response?.status === 429) {
      toast.error("Trop de requêtes — réessayez dans quelques instants.");
    } else if (err.response?.status >= 500) {
      toast.error("Erreur serveur — réessayez.");
    }
    return Promise.reject(err);
  }
);

// ── Auth ──────────────────────────────────────────────────────────────────────

export const authApi = {
  login: (email: string, password: string) =>
    apiClient.post("/auth/login", { email, password }),

  register: (data: { email: string; password: string; nom?: string; compagnie?: string }) =>
    apiClient.post("/auth/register", data),

  me: () => apiClient.get("/auth/me"),
};

// ── Chat / Agents ─────────────────────────────────────────────────────────────

export const chatApi = {
  sendMessage: (data: {
    message: string;
    session_id?: string;
    agent?: string;
    images?: string[];
  }) => apiClient.post("/chat/message", data),

  getSessions: () => apiClient.get("/chat/sessions"),

  getHistory: (sessionId: string) =>
    apiClient.get(`/chat/sessions/${sessionId}/messages`),

  deleteSession: (sessionId: string) =>
    apiClient.delete(`/chat/sessions/${sessionId}`),
};

// ── Sinistres ─────────────────────────────────────────────────────────────────

export const sinistresApi = {
  list: (params?: { branche?: string; statut?: string; page?: number }) =>
    apiClient.get("/sinistres", { params }),

  get: (ref: string) => apiClient.get(`/sinistres/${ref}`),

  declare: (data: FormData) =>
    apiClient.post("/sinistres/declarer", data, {
      headers: { "Content-Type": "multipart/form-data" },
    }),

  updateStatut: (ref: string, statut: string, commentaire?: string) =>
    apiClient.patch(`/sinistres/${ref}/statut`, { statut, commentaire }),

  fraudeScore: (ref: string) => apiClient.get(`/sinistres/${ref}/fraude/score`),

  uploadPiece: (ref: string, data: FormData) =>
    apiClient.post(`/sinistres/${ref}/pieces`, data, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
};

// ── Souscription ──────────────────────────────────────────────────────────────

export const souscriptionApi = {
  tarifier: (data: Record<string, unknown>) =>
    apiClient.post("/souscription/tarifier", data),

  emettre: (data: Record<string, unknown>) =>
    apiClient.post("/souscription/emettre", data),

  list: (params?: { branche?: string; statut?: string }) =>
    apiClient.get("/polices", { params }),

  get: (policeId: string) => apiClient.get(`/polices/${policeId}`),
};

// ── Comptabilité ──────────────────────────────────────────────────────────────

export const comptabiliteApi = {
  analyserDocument: (data: FormData) =>
    apiClient.post("/comptabilite/analyser", data, {
      headers: { "Content-Type": "multipart/form-data" },
    }),

  rapportAnalytique: (params?: { periode?: string; branche?: string }) =>
    apiClient.get("/comptabilite/rapport", { params }),

  rapprochement: (data: FormData) =>
    apiClient.post("/comptabilite/rapprochement", data, {
      headers: { "Content-Type": "multipart/form-data" },
    }),

  exportPCSA: (params?: { periode?: string }) =>
    apiClient.get("/comptabilite/export-pcsa", { params, responseType: "blob" }),
};

// ── CIMA ──────────────────────────────────────────────────────────────────────

export const cimaApi = {
  ratios: () => apiClient.get("/cima/ratios"),

  qa: (question: string) => apiClient.post("/cima/qa", { question }),

  etats: (codeEtat: string, params?: { annee?: number }) =>
    apiClient.get(`/cima/etats/${codeEtat}`, { params }),

  alertes: () => apiClient.get("/cima/alertes"),
};

// ── Réassurance ───────────────────────────────────────────────────────────────

export const reassuranceApi = {
  programme: () => apiClient.get("/reassurance/programme"),

  pml: (data: { branche: string; scenario: string }) =>
    apiClient.post("/reassurance/pml", data),

  bordereau: (params?: { traite?: string; periode?: string }) =>
    apiClient.get("/reassurance/bordereau", { params }),
};

// ── Documents ────────────────────────────────────────────────────────────────

export const documentsApi = {
  generer: (data: { type: string; contenu: string; titre?: string }) =>
    apiClient.post("/documents/generer", data),

  historique: (params?: { page?: number; limit?: number }) =>
    apiClient.get("/documents/historique", { params }),

  telecharger: (id: number) =>
    apiClient.get(`/documents/${id}/telecharger`, { responseType: "blob" }),

  supprimer: (id: number) => apiClient.delete(`/documents/${id}`),
};

// ── Validations ───────────────────────────────────────────────────────────────

export const validationsApi = {
  list: (statut?: "pending" | "approved" | "rejected") =>
    apiClient.get("/validations", { params: { statut } }),

  stats: () => apiClient.get("/validations/stats"),

  approuver: (id: string, commentaire?: string) =>
    apiClient.post(`/validations/${id}/approuver`, { commentaire }),

  rejeter: (id: string, motif: string) =>
    apiClient.post(`/validations/${id}/rejeter`, { motif }),
};

// ── Dashboard ─────────────────────────────────────────────────────────────────

export const dashboardApi = {
  kpis: () => apiClient.get("/analytics/kpis"),
  chartsBranches: () => apiClient.get("/analytics/branches"),
  chartsCharges: (annee?: number) => apiClient.get("/analytics/charges", { params: { annee } }),
  alertesCima: () => apiClient.get("/cima/alertes"),
};

// ── Admin ─────────────────────────────────────────────────────────────────────

export const adminApi = {
  users: (params?: { page?: number; role?: string }) =>
    apiClient.get("/admin/users", { params }),

  stats: () => apiClient.get("/admin/stats"),

  updateRole: (userId: number, role: string) =>
    apiClient.patch(`/admin/users/${userId}/role`, { role }),

  agentsStats: () => apiClient.get("/admin/agents/stats"),
};
