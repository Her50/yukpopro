import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { authAPI } from '../api/client'

interface User {
  user_id: number
  user_nom: string
  role: string
}

interface AuthCtx {
  user: User | null
  token: string | null
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, nom: string) => Promise<void>
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
    const r = await fetch('/api/v1/auth/token', { method: 'POST', body: params })
    if (!r.ok) throw new Error('Identifiants incorrects')
    const data = await r.json()
    localStorage.setItem('bureau_token', data.access_token)
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

  const logout = () => {
    localStorage.removeItem('bureau_token')
    setToken(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, token, login, register, logout, loading }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth doit être dans AuthProvider')
  return ctx
}
