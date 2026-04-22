import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'
import * as SecureStore from 'expo-secure-store'

// L'URL de l'API peut être surchargée via les variables d'environnement Expo
const API_URL = process.env.EXPO_PUBLIC_API_URL || 'https://api.yukpo-assurance.cm'

export const apiClient = axios.create({
  baseURL: API_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// Attach JWT
apiClient.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    try {
      const token = await SecureStore.getItemAsync('access_token')
      if (token && config.headers) {
        config.headers.Authorization = `Bearer ${token}`
      }
    } catch { /* ignore */ }
    return config
  },
  (error) => Promise.reject(error)
)

// Handle 401
apiClient.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    if (error.response?.status === 401) {
      await SecureStore.deleteItemAsync('access_token')
      await SecureStore.deleteItemAsync('user')
      // Navigation handled by auth context
    }
    return Promise.reject(error)
  }
)

// ─── Auth ──────────────────────────────────────────────────────────────────

export const authAPI = {
  login: async (username: string, password: string) => {
    const form = new FormData()
    form.append('username', username)
    form.append('password', password)
    const { data } = await apiClient.post('/api/v1/auth/login', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },
  me: async () => {
    const { data } = await apiClient.get('/api/v1/auth/me')
    return data
  },
}

// ─── Dashboard ─────────────────────────────────────────────────────────────

export const analyticsAPI = {
  getDashboard: async (annee = 2024) => {
    const { data } = await apiClient.get(`/api/v1/analytics/dashboard/${annee}`)
    return data
  },
}

// ─── Sinistres ─────────────────────────────────────────────────────────────

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
  uploadDocument: async (sistreId: string, uri: string, type: string) => {
    const form = new FormData()
    form.append('fichier', { uri, name: `doc_${Date.now()}.jpg`, type: 'image/jpeg' } as unknown as Blob)
    form.append('type_document', type)
    const { data } = await apiClient.post(`/api/v1/sinistres/${sistreId}/documents`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },
}

// ─── OCR / Documents ───────────────────────────────────────────────────────

export const ocrAPI = {
  analyserImage: async (uri: string, typeDocument: string) => {
    const form = new FormData()
    form.append('fichier', { uri, name: 'scan.jpg', type: 'image/jpeg' } as unknown as Blob)
    form.append('type_document', typeDocument)
    const { data } = await apiClient.post('/api/v1/comptabilite/analyser-piece', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },
  analyserCNI: async (uri: string) => {
    const form = new FormData()
    form.append('fichier', { uri, name: 'cni.jpg', type: 'image/jpeg' } as unknown as Blob)
    const { data } = await apiClient.post('/api/v1/souscription/kyc/analyser-cni', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },
  analyserCarteGrise: async (uri: string) => {
    const form = new FormData()
    form.append('fichier', { uri, name: 'carte_grise.jpg', type: 'image/jpeg' } as unknown as Blob)
    const { data } = await apiClient.post('/api/v1/souscription/kyc/analyser-carte-grise', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },
}

// ─── Chat IA ───────────────────────────────────────────────────────────────

export const chatAPI = {
  createSession: async () => {
    const { data } = await apiClient.post('/api/v1/chat/sessions', { titre: 'Session mobile' })
    return {
      id: (data.session_id ?? data.id) as string,
      titre: (data.titre ?? 'Nouvelle conversation') as string,
      created_at: (data.creee_le ?? data.created_at ?? new Date().toISOString()) as string,
    }
  },
  // Accepte un objet payload (compatibilité avec chat.tsx)
  sendMessage: async (payload: { session_id: string; content: string }) => {
    const { data } = await apiClient.post('/api/v1/chat/message', {
      session_id: payload.session_id,
      message: payload.content,
    })
    return data
  },
}

// ─── Souscription ──────────────────────────────────────────────────────────

export const souscriptionAPI = {
  calculerPrime: async (payload: unknown) => {
    const { data } = await apiClient.post('/api/v1/tarification/calculer', payload)
    return data
  },
  soumettre: async (payload: unknown) => {
    const { data } = await apiClient.post('/api/v1/souscription/soumettre', payload)
    return data
  },
}

// ─── Courtiers ─────────────────────────────────────────────────────────────

export const courtiersAPI = {
  getTableauBord: async () => {
    const { data } = await apiClient.get('/api/v1/courtiers/tableau-de-bord')
    return data
  },
  getCommissions: async () => {
    const { data } = await apiClient.get('/api/v1/courtiers/commissions')
    return data
  },
  getProductions: async () => {
    const { data } = await apiClient.get('/api/v1/courtiers/productions')
    return data
  },
}
