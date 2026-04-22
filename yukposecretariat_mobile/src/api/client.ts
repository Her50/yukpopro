import axios from 'axios'
import * as SecureStore from 'expo-secure-store'

const BASE_URL = process.env.EXPO_PUBLIC_API_URL || 'https://yukpopro-backend.fly.dev/api/v1/bureau'
const AUTH_URL = process.env.EXPO_PUBLIC_API_URL?.replace('/bureau', '') || 'https://yukpopro-backend.fly.dev/api/v1'

const TOKEN_KEY = 'bureau_token'

const api = axios.create({ baseURL: BASE_URL })

api.interceptors.request.use(async cfg => {
  const token = await SecureStore.getItemAsync(TOKEN_KEY)
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

api.interceptors.response.use(
  r => r,
  err => {
    if (err.response?.status === 401) {
      SecureStore.deleteItemAsync(TOKEN_KEY)
    }
    return Promise.reject(err)
  },
)

// ─── Auth ─────────────────────────────────────────────────────────────────────
export const authAPI = {
  login: async (email: string, password: string) => {
    const params = new URLSearchParams({ username: email, password })
    const r = await axios.post(`${AUTH_URL}/auth/token`, params.toString(), {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    return r.data
  },
  saveToken: (token: string) => SecureStore.setItemAsync(TOKEN_KEY, token),
  getToken: () => SecureStore.getItemAsync(TOKEN_KEY),
  deleteToken: () => SecureStore.deleteItemAsync(TOKEN_KEY),
}

// ─── Rédaction ────────────────────────────────────────────────────────────────
export const redactionAPI = {
  types: () => api.get('/redaction/types'),
  generer: (data: Record<string, unknown>) => api.post('/redaction/generer', data),
  reformuler: (data: { texte: string; registre: string; pays: string }) =>
    api.post('/redaction/reformuler', data),
}

// ─── OCR ──────────────────────────────────────────────────────────────────────
export const ocrAPI = {
  scanner: (formData: FormData) =>
    api.post('/ocr/scanner', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  manuscrit: (formData: FormData) =>
    api.post('/ocr/manuscrit', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
}

// ─── Audio ────────────────────────────────────────────────────────────────────
export const audioAPI = {
  types: () => api.get('/audio/types'),
  transcrire: (formData: FormData) =>
    api.post('/audio/transcrire', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120_000,
    }),
}

// ─── Infographie ──────────────────────────────────────────────────────────────
export const infographieAPI = {
  gabarits: () => api.get('/infographie/gabarits'),
  generer: (data: { brief: string; type_gabarit: string; pays?: string }) =>
    api.post('/infographie/generer', data),
  genererDepuisModele: (formData: FormData) =>
    api.post('/infographie/generer-depuis-modele', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120_000,
    }),
  genererCustom: (data: { width_mm: number; height_mm: number; bleed_mm?: number; brief: string; pays?: string }) =>
    api.post('/infographie/generer-custom', data),
}

// ─── Traduction ───────────────────────────────────────────────────────────────
export const traductionAPI = {
  traduireTexte: (data: { contenu: string; langue_source: string; langue_cible: string; contexte_metier?: string }) =>
    api.post('/traduction/texte', data),
  traduireFichier: (formData: FormData) =>
    api.post('/traduction/fichier', formData, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120_000 }),
}

// ─── Mes Documents ────────────────────────────────────────────────────────────
export const documentsAPI = {
  lister: () => api.get('/documents/'),
  supprimer: (fichier_id: string) => api.delete(`/documents/${fichier_id}`),
  urlTelechargement: (fichier_id: string) => `${BASE_URL}/documents/${fichier_id}`,
}

// ─── Gestion ──────────────────────────────────────────────────────────────────
export const gestionAPI = {
  travaux: (statut?: string) => api.get('/gestion/travaux', { params: statut ? { statut } : {} }),
  creerTravail: (data: Record<string, unknown>) => api.post('/gestion/travaux', data),
  modifierTravail: (id: number, data: Record<string, unknown>) => api.patch(`/gestion/travaux/${id}`, data),
  genererDevis: (data: Record<string, unknown>) => api.post('/gestion/devis', data),
  genererFacture: (data: Record<string, unknown>) => api.post('/gestion/facture', data),
  transactions: (date?: string) => api.get('/gestion/caisse', { params: date ? { date_str: date } : {} }),
  enregistrerTransaction: (data: Record<string, unknown>) => api.post('/gestion/caisse', data),
  clients: (recherche?: string) => api.get('/gestion/clients', { params: recherche ? { recherche } : {} }),
  creerClient: (data: Record<string, unknown>) => api.post('/gestion/clients', data),
  whatsappClient: (id: number, message: string) =>
    api.get(`/gestion/clients/${id}/whatsapp`, { params: { message } }),
}
