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

// Types d'erreurs crédits remontées par le backend
export type CreditErrorKind = 'credits_epuises' | 'module_non_autorise'

export interface CreditError {
  kind: CreditErrorKind
  message: string
  plan?: string
  module?: string
  restants?: number
  alloues?: number
  plansEligibles?: string[]
}

/**
 * Analyse un détail d'erreur backend au format
 *   "CREDITS_EPUISES|<used>|<allocated>"         (ou "|restants=X|plan=Y")
 *   "MODULE_NON_AUTORISE|<module>|<plan>|Plans donnant accès : ..."
 * et le transforme en objet CreditError. Retourne null si non applicable.
 */
export function parseCreditError(detail: unknown): CreditError | null {
  if (typeof detail !== 'string') return null
  if (detail.startsWith('CREDITS_EPUISES')) {
    const parts = detail.split('|')
    const byKey: Record<string, string> = {}
    for (const p of parts.slice(1)) {
      const [k, v] = p.split('=')
      if (v !== undefined) byKey[k] = v
    }
    const numeric = parts.slice(1).filter(x => /^\d+(\.\d+)?$/.test(x))
    return {
      kind: 'credits_epuises',
      message: 'Vos crédits Yukpo sont épuisés. Rechargez ou passez à un plan supérieur.',
      plan: byKey.plan,
      restants: byKey.restants ? Number(byKey.restants) : (numeric[0] !== undefined ? Number(numeric[0]) : undefined),
      alloues: numeric[1] !== undefined ? Number(numeric[1]) : undefined,
    }
  }
  if (detail.startsWith('MODULE_NON_AUTORISE')) {
    const [, module, plan, ...rest] = detail.split('|')
    const tail = rest.join('|')
    const plansMatch = tail.match(/Plans donnant accès\s*:\s*(.+)$/i)
    const plansEligibles = plansMatch
      ? plansMatch[1].split(',').map(s => s.trim()).filter(Boolean)
      : []
    return {
      kind: 'module_non_autorise',
      message: `Votre plan actuel (${plan}) ne donne pas accès à ${module}.`,
      module,
      plan,
      plansEligibles,
    }
  }
  return null
}

// ─── Callbacks globaux pour l'UI crédits ──────────────────────────────────
// L'écran principal enregistre ces handlers (ex: ouverture d'une modale
// « Recharger / Upgrader ») afin que tous les appels API déclenchent l'UX
// correcte sans ajouter un try/catch dans chaque écran.
type CreditErrorHandler = (e: CreditError) => void
let onCreditsEpuises: CreditErrorHandler | null = null
let onModuleNonAutorise: CreditErrorHandler | null = null

export function configureCreditHandlers(handlers: {
  onCreditsEpuises?: CreditErrorHandler
  onModuleNonAutorise?: CreditErrorHandler
}) {
  onCreditsEpuises = handlers.onCreditsEpuises ?? null
  onModuleNonAutorise = handlers.onModuleNonAutorise ?? null
}

// Handle 401 (déconnexion) + 402 crédits épuisés + 403 module non autorisé
apiClient.interceptors.response.use(
  (res) => res,
  async (error: AxiosError<{ detail?: string }>) => {
    const status = error.response?.status
    if (status === 401) {
      await SecureStore.deleteItemAsync('access_token')
      await SecureStore.deleteItemAsync('user')
      // Navigation handled by auth context
    } else if (status === 402 || status === 403) {
      const creditErr = parseCreditError(error.response?.data?.detail)
      if (creditErr) {
        if (creditErr.kind === 'credits_epuises' && onCreditsEpuises) {
          onCreditsEpuises(creditErr)
        } else if (creditErr.kind === 'module_non_autorise' && onModuleNonAutorise) {
          onModuleNonAutorise(creditErr)
        }
        // Attacher l'objet structuré pour les écrans qui préfèrent gérer localement
        ;(error as AxiosError & { creditError?: CreditError }).creditError = creditErr
      }
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

// ─── Crédits Yukpo (solde, plans, recharge) ────────────────────────────────

export interface SoldeCredits {
  plan: string
  credits_alloues: number
  credits_utilises: number
  credits_restants: number
  pct_utilise: number
  label_plan: string
  renouvellement_le?: string | null
  credits_en_fcfa_equiv?: number
  explication?: string
}

export const creditsAPI = {
  // YukpoPro (assurance) — /api/v1/pro/abonnement/ renvoie solde+plan+quota
  getSolde: async (): Promise<SoldeCredits> => {
    const { data } = await apiClient.get('/api/v1/pro/abonnement/')
    return {
      plan: data.plan_actif ?? data.plan,
      credits_alloues: data.credits_alloues,
      credits_utilises: data.credits_utilises,
      credits_restants: data.credits_restants,
      pct_utilise: data.pct_utilise,
      label_plan: data.label_credits ?? data.label_plan ?? '',
      renouvellement_le: data.renouvellement_le,
      credits_en_fcfa_equiv: data.credits_en_fcfa_equiv,
      explication: data.explication_credits ?? data.explication,
    }
  },
  listerPlans: async () => {
    const { data } = await apiClient.get('/api/v1/pro/abonnement/plans')
    return data
  },
  listerPacks: async () => {
    const { data } = await apiClient.get('/api/v1/pro/abonnement/packs-credits')
    return data
  },
  initierRecharge: async (packId: string) => {
    const { data } = await apiClient.post('/api/v1/pro/abonnement/initier-recharge', { pack_id: packId })
    return data
  },
  initierUpgrade: async (planId: string, operateur: string, numero: string) => {
    const { data } = await apiClient.post('/api/v1/pro/abonnement/initier', {
      plan_id: planId,
      operateur,
      numero_paiement: numero,
    })
    return data
  },
  // YukpoSecrétariat (bureau)
  getSoldeBureau: async (): Promise<SoldeCredits> => {
    const { data } = await apiClient.get('/api/v1/bureau/abonnement/')
    return {
      plan: data.plan_actif ?? data.plan,
      credits_alloues: data.credits_alloues,
      credits_utilises: data.credits_utilises,
      credits_restants: data.credits_restants,
      pct_utilise: data.pct_utilise,
      label_plan: data.label_credits ?? data.label_plan ?? data.nom_plan ?? '',
      renouvellement_le: data.renouvellement_le,
      credits_en_fcfa_equiv: data.credits_en_fcfa_equiv,
      explication: data.explication ?? data.explication_credits,
    }
  },
  listerPacksBureau: async () => {
    const { data } = await apiClient.get('/api/v1/bureau/abonnement/packs-credits')
    return data
  },
  initierRechargeBureau: async (packId: string) => {
    const { data } = await apiClient.post('/api/v1/bureau/abonnement/initier-recharge', { pack_id: packId })
    return data
  },
  initierUpgradeBureau: async (planId: string, operateur: string, numero: string) => {
    const { data } = await apiClient.post('/api/v1/bureau/abonnement/initier', {
      plan_id: planId,
      operateur,
      numero_paiement: numero,
    })
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
