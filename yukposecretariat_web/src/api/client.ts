import axios from 'axios'

const BASE = import.meta.env.VITE_API_URL || '/api/v1/bureau'

const api = axios.create({ baseURL: BASE })

api.interceptors.request.use(cfg => {
  const token = localStorage.getItem('bureau_token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

api.interceptors.response.use(
  r => r,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('bureau_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  },
)

// ─── Auth (partagée avec YukpoPro) ────────────────────────────────────────────
const authApi = axios.create({ baseURL: import.meta.env.VITE_API_URL?.replace('/bureau', '') || '/api/v1' })

export const authAPI = {
  login: (email: string, password: string) =>
    authApi.post('/auth/token', { username: email, password }, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }),
  me: () => authApi.get('/auth/me', { headers: { Authorization: `Bearer ${localStorage.getItem('bureau_token')}` } }),
}

// ─── Rédaction ────────────────────────────────────────────────────────────────
export const redactionAPI = {
  types: () => api.get('/redaction/types'),
  generer: (data: Record<string, unknown>) => api.post('/redaction/generer', data),
  reformuler: (data: { texte: string; registre: string; pays: string }) => api.post('/redaction/reformuler', data),
  calculerPrix: (type_doc: string, nb_mots_estime: number) =>
    api.post('/redaction/calculer-prix', { type_doc, nb_mots_estime }),
  telecharger: (fichier_id: string) =>
    api.get(`/redaction/fichier/${fichier_id}`, { responseType: 'blob' }),
}

// ─── OCR ──────────────────────────────────────────────────────────────────────
export const ocrAPI = {
  scanner: (formData: FormData) =>
    api.post('/ocr/scanner', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  manuscrit: (formData: FormData) =>
    api.post('/ocr/manuscrit', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  telecharger: (fichier_id: string) =>
    api.get(`/ocr/fichier/${fichier_id}`, { responseType: 'blob' }),
}

// ─── Audio ────────────────────────────────────────────────────────────────────
export const audioAPI = {
  types: () => api.get('/audio/types'),
  transcrire: (formData: FormData) =>
    api.post('/audio/transcrire', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120_000,
    }),
  telecharger: (fichier_id: string) =>
    api.get(`/audio/fichier/${fichier_id}`, { responseType: 'blob' }),
}

// ─── Infographie ──────────────────────────────────────────────────────────────
export const infographieAPI = {
  gabarits: () => api.get('/infographie/gabarits'),
  generer: (data: { brief: string; type_gabarit: string; pays?: string }) =>
    api.post('/infographie/generer', data),
  genererManuel: (data: Record<string, unknown>) =>
    api.post('/infographie/generer-manuel', data),
  telecharger: (fichier_id: string) =>
    api.get(`/infographie/fichier/${fichier_id}`, { responseType: 'blob' }),
}

// ─── Gestion ──────────────────────────────────────────────────────────────────
export const gestionAPI = {
  // Kanban
  travaux: (statut?: string) => api.get('/gestion/travaux', { params: statut ? { statut } : {} }),
  creerTravail: (data: Record<string, unknown>) => api.post('/gestion/travaux', data),
  modifierTravail: (id: number, data: Record<string, unknown>) => api.patch(`/gestion/travaux/${id}`, data),

  // Devis & Facture
  genererDevis: (data: Record<string, unknown>) => api.post('/gestion/devis', data),
  genererFacture: (data: Record<string, unknown>) => api.post('/gestion/facture', data),
  telechargerDoc: (pdf_id: string) => api.get(`/gestion/document/${pdf_id}`, { responseType: 'blob' }),

  // Caisse
  transactions: (date?: string) => api.get('/gestion/caisse', { params: date ? { date_str: date } : {} }),
  enregistrerTransaction: (data: Record<string, unknown>) => api.post('/gestion/caisse', data),

  // CRM
  clients: (recherche?: string) => api.get('/gestion/clients', { params: recherche ? { recherche } : {} }),
  creerClient: (data: Record<string, unknown>) => api.post('/gestion/clients', data),
  ficheClient: (id: number) => api.get(`/gestion/clients/${id}`),
  whatsappClient: (id: number, message: string) =>
    api.get(`/gestion/clients/${id}/whatsapp`, { params: { message } }),
}

export default api
