import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { authAPI } from '../api/client'

interface User {
  user_id: number
  user_nom: string
  user_nom_brut?: string
  nom?: string | null
  prenoms?: string | null
  email?: string | null
  role: string
}

interface AuthCtx {
  user: User | null
  token: string | null
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, nom: string) => Promise<void>
  refreshUser: () => Promise<void>
  logout: () => void
  loading: boolean
}

const AuthContext = createContext<AuthCtx | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(localStorage.getItem('bureau_token'))
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (token) {
      authAPI.me()
        .then(r => setUser(r.data))
        .catch(() => { setToken(null); localStorage.removeItem('bureau_token') })
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [token])

  const login = async (email: string, password: string) => {
    const params = new URLSearchParams({ username: email, password })
    const ctrl = new AbortController()
    const t = setTimeout(() => ctrl.abort(), 15_000)
    let r: Response
    try {
      r = await fetch('/api/v1/auth/token', { method: 'POST', body: params, signal: ctrl.signal })
    } finally { clearTimeout(t) }
    if (!r.ok) throw new Error('Identifiants incorrects')
    const data = await r.json()
    localStorage.setItem('bureau_token', data.access_token)

    // Décode le JWT pour pré-remplir un user (pas bloquant) — protège
    // contre un timeout /auth/me qui ferait pendre la connexion à l'infini.
    try {
      const payload = JSON.parse(atob(data.access_token.split('.')[1]))
      setUser({
        user_id: payload.sub || payload.user_id || 0,
        user_nom: payload.nom || payload.username || email.split('@')[0],
        role: payload.role || 'agent',
      })
    } catch {}

    // Charge /auth/me en arrière-plan pour enrichir le user (nom, prenoms…).
    authAPI.me().then(me => setUser(me.data)).catch(e => {
      console.warn('[Auth] /auth/me après login a échoué (non bloquant):', e)
    })

    setToken(data.access_token)
  }

  const register = async (email: string, password: string, nom: string) => {
    const r = await fetch('/api/v1/auth/register/pro', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, nom }),
    })
    if (!r.ok) {
      const err = await r.json().catch(() => ({}))
      throw new Error(err.detail || 'Inscription échouée')
    }
    // Auto-login après inscription
    await login(email, password)
  }

  const refreshUser = async () => {
    try {
      const r = await authAPI.me()
      setUser(r.data)
    } catch (e) {
      console.warn('[Auth] refreshUser échoué:', e)
    }
  }

  const logout = () => {
    localStorage.removeItem('bureau_token')
    setToken(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, token, login, register, refreshUser, logout, loading }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth doit être dans AuthProvider')
  return ctx
}
