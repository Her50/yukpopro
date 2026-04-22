import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 120000,            // 2 min — OCR + génération documents longs
  withCredentials: true,      // Envoie les cookies httpOnly (JWT sécurisé côté serveur)
})

// Request interceptor — Bearer token + CSRF token
apiClient.interceptors.request.use(
  (config) => {
    // 1. Bearer token depuis localStorage → Authorization header
    //    (exempt de CSRF côté backend car les headers ne peuvent pas être forgés par CSRF)
    const token = localStorage.getItem('access_token')
    if (token && config.headers) {
      config.headers['Authorization'] = `Bearer ${token}`
    }

    // 2. Token CSRF lu depuis le cookie non-httpOnly (sécurité additionnelle)
    const getCookie = (name: string) => {
      const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'))
      return match ? decodeURIComponent(match[2]) : null
    }
    const csrfToken = getCookie('csrf_token')
    if (csrfToken && config.headers && config.method !== 'get') {
      config.headers['X-CSRF-Token'] = csrfToken
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor — handle 401/403
apiClient.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    const axiosErr = error as { response?: { status?: number } }
    if (axiosErr.response?.status === 401) {
      // Nettoyage sessionStorage (plus de localStorage pour les tokens)
      sessionStorage.removeItem('user_info')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// ─── Auth ───────────────────────────────────────────────────────────────────
export const authAPI = {
  login: async (username: string, password: string) => {
    const { data } = await apiClient.post('/api/v1/auth/login', { username, password })
    return data
  },
  me: async () => {
    const { data } = await apiClient.get('/api/v1/auth/me')
    return data
  },
}

// ─── Chat ────────────────────────────────────────────────────────────────────
export const chatAPI = {
  createSession: async (titre?: string) => {
    const { data } = await apiClient.post('/api/v1/chat/sessions', { titre: titre || 'Nouvelle conversation' })
    const d = data as Record<string, unknown>
    // Normalize backend shape (session_id, creee_le) to frontend shape (id, created_at)
    return {
      id: (d.session_id ?? d.id) as string,
      titre: d.titre as string,
      created_at: (d.creee_le ?? d.created_at ?? new Date().toISOString()) as string,
      updated_at: (d.mise_a_jour ?? d.updated_at ?? new Date().toISOString()) as string,
    }
  },
  sendMessage: async (payload: { session_id: string; content: string; fichiers?: string[] }) => {
    // Backend uses 'message' field, not 'content'
    const { data } = await apiClient.post('/api/v1/chat/message', {
      session_id: payload.session_id,
      message: payload.content,
    })
    return data
  },
  getSessions: async () => {
    const { data } = await apiClient.get('/api/v1/chat/sessions/mes-sessions')
    // Backend returns { sessions: [...] } where each session has session_id/mise_a_jour
    const d = data as Record<string, unknown>
    const sessions: Record<string, unknown>[] = Array.isArray(data) ? data : ((d.sessions ?? d.items ?? []) as Record<string, unknown>[])
    return sessions.map((s) => ({
      id: (s.session_id ?? s.id) as string,
      titre: s.titre as string,
      created_at: (s.creee_le ?? s.created_at ?? new Date().toISOString()) as string,
      updated_at: (s.mise_a_jour ?? s.updated_at ?? new Date().toISOString()) as string,
      messages_count: (s.nb_messages ?? 0) as number,
    }))
  },
  renameSession: async (sessionId: string, titre: string) => {
    const { data } = await apiClient.patch(`/api/v1/chat/sessions/${sessionId}`, { titre })
    return data
  },
  getStreamUrl: (sessionId: string, content: string): string => {
    const token = localStorage.getItem('access_token')
    const params = new URLSearchParams({ session_id: sessionId, content, token: token || '' })
    return `${BASE_URL}/api/v1/chat/message-stream?${params.toString()}`
  },
}

// ─── Analytics ───────────────────────────────────────────────────────────────
export const analyticsAPI = {
  getDashboard: async (annee = 2025) => {
    const { data } = await apiClient.get(`/api/v1/analytics/dashboard/${annee}`)
    return data
  },
}

// ─── Sinistres ────────────────────────────────────────────────────────────────
export const sinistresAPI = {
  list: async (params?: Record<string, string>) => {
    const { data } = await apiClient.get('/api/v1/sinistres/', { params })
    return data
  },
  declarer: async (payload: unknown) => {
    const { data } = await apiClient.post('/api/v1/sinistres/declarer', payload)
    return data
  },
  getScoreFraude: async (id: string) => {
    const { data } = await apiClient.get(`/api/v1/sinistres/${id}/fraude/score`)
    return data
  },
}

// ─── Documents ────────────────────────────────────────────────────────────────
export interface DocHistoriqueBackend {
  id: number
  titre: string
  type_doc: string
  fichier?: string
  contenu_source?: string
  contenu_genere?: string
  session_id?: string
  meta: Record<string, unknown>
  cree_le: string
  modifie_le: string
}

export const documentsAPI = {
  generer: async (payload: { prompt: string; type_document: string; contexte?: string }) => {
    const { data } = await apiClient.post('/api/v1/documents/generer-depuis-prompt', payload)
    return data
  },

  historique: async (type_doc?: string): Promise<{ documents: DocHistoriqueBackend[]; total: number }> => {
    const params = type_doc ? { type_doc } : {}
    const { data } = await apiClient.get('/api/v1/documents/historique', { params })
    return data
  },

  sauvegarder: async (payload: {
    titre: string
    type_doc: string
    fichier?: string
    contenu_source?: string
    contenu_genere?: string
    session_id?: string
    meta?: Record<string, unknown>
  }): Promise<DocHistoriqueBackend> => {
    const { data } = await apiClient.post('/api/v1/documents/historique', payload)
    return data
  },

  supprimer: async (doc_id: number): Promise<void> => {
    await apiClient.delete(`/api/v1/documents/historique/${doc_id}`)
  },

  traduireFichier: async (formData: FormData) => {
    const { data } = await apiClient.post('/api/v1/documents/traduire-fichier', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },
}

// ─── CIMA ─────────────────────────────────────────────────────────────────────
export const cimaAPI = {
  getRatios: async () => {
    const { data } = await apiClient.get('/api/v1/cima/ratios')
    return data
  },
  poserQuestion: async (question: string, contexte?: string) => {
    const { data } = await apiClient.post('/api/v1/cima/question', { question, contexte })
    return data
  },
}

// ─── Courtiers ────────────────────────────────────────────────────────────────
export const courtiersAPI = {
  getTableauBord: async () => {
    const { data } = await apiClient.get('/api/v1/courtiers/tableau-de-bord')
    return data
  },
}

// ─── RH ───────────────────────────────────────────────────────────────────────
export const rhAPI = {
  getEmployes: async () => {
    const { data } = await apiClient.get('/api/v1/rh/employes')
    return data
  },
}

// ─── Commercial ───────────────────────────────────────────────────────────────
export const commercialAPI = {
  getProspects: async () => {
    const { data } = await apiClient.get('/api/v1/commercial/prospects')
    return data
  },
}

// ─── Souscription ─────────────────────────────────────────────────────────────
export const souscriptionAPI = {
  soumettre: async (payload: unknown) => {
    const { data } = await apiClient.post('/api/v1/souscription/soumettre', payload)
    return data
  },
}

// ─── Tarification ─────────────────────────────────────────────────────────────
export const tarificationAPI = {
  calculer: async (payload: unknown) => {
    const { data } = await apiClient.post('/api/v1/tarification/calculer', payload)
    return data
  },
  predireML: async (payload: unknown) => {
    const { data } = await apiClient.post('/api/v1/tarification/ml/predire', payload)
    return data
  },
  getBaremes: async (branche?: string) => {
    const params = branche ? { branche } : undefined
    const { data } = await apiClient.get('/api/v1/tarification/baremes/auto', { params })
    return data
  },
  getDeriveModele: async () => {
    const { data } = await apiClient.get('/api/v1/tarification/ml/derive')
    return data
  },
  importerCSVORASS: async (fichier: File, reentrainer = true) => {
    const form = new FormData()
    form.append('fichier', fichier)
    form.append('reentrainer', String(reentrainer))
    const { data } = await apiClient.post('/api/v1/tarification/ml/importer-csv-orass', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },
}

// ─── Comptabilité ─────────────────────────────────────────────────────────────
export const comptabiliteAPI = {
  analyserPiece: async (fichier: File, typeDocument: string) => {
    const form = new FormData()
    form.append('fichier', fichier)
    form.append('type_document', typeDocument)
    const { data } = await apiClient.post('/api/v1/comptabilite/analyser-piece', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },
  getRapprochement: async (params?: { debut?: string; fin?: string }) => {
    const { data } = await apiClient.get('/api/v1/comptabilite/rapprochement', { params })
    return data
  },
  getAnalytique: async (annee?: number, mois?: number) => {
    const { data } = await apiClient.get('/api/v1/comptabilite/analytique', { params: { annee, mois } })
    return data
  },
  exporterPCSA: async (debut: string, fin: string) => {
    const { data } = await apiClient.get('/api/v1/comptabilite/exporter-pcsa', {
      params: { debut, fin },
      responseType: 'blob',
    })
    return data
  },
}

// ─── Réassurance ──────────────────────────────────────────────────────────────
export const reassuranceAPI = {
  getProgramme: async () => {
    const { data } = await apiClient.get('/api/v1/reassurance/programme')
    return data
  },
  calculerPML: async (payload?: unknown) => {
    const { data } = await apiClient.post('/api/v1/reassurance/pml/calculer', payload || {})
    return data
  },
  getBordereauCession: async (trimestre?: string, annee?: number) => {
    const { data } = await apiClient.get('/api/v1/reassurance/bordereau-cession', {
      params: { trimestre, annee },
    })
    return data
  },
  getEtatC12: async (annee: number) => {
    const { data } = await apiClient.get(`/api/v1/reassurance/etat-c12/${annee}`)
    return data
  },
  analyserProgramme: async () => {
    const { data } = await apiClient.post('/api/v1/reassurance/analyser-programme')
    return data
  },
}

// ─── Health ───────────────────────────────────────────────────────────────────
export const healthAPI = {
  check: async () => {
    const { data } = await apiClient.get('/health')
    return data
  },
}
