import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { authAPI } from '../api/client'
import axios from 'axios'

interface User { user_id: number; user_nom: string; role: string }

interface AuthCtx {
  user: User | null
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  loading: boolean
  token: string | null
}

const AuthContext = createContext<AuthCtx | null>(null)

const AUTH_URL = process.env.EXPO_PUBLIC_API_URL?.replace('/bureau', '') || 'https://yukpopro-backend.fly.dev/api/v1'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    authAPI.getToken().then(async t => {
      if (t) {
        setToken(t)
        try {
          const r = await axios.get(`${AUTH_URL}/auth/me`, {
            headers: { Authorization: `Bearer ${t}` },
          })
          setUser(r.data)
        } catch {
          await authAPI.deleteToken()
        }
      }
      setLoading(false)
    })
  }, [])

  const login = async (email: string, password: string) => {
    const data = await authAPI.login(email, password)
    await authAPI.saveToken(data.access_token)
    setToken(data.access_token)
    const r = await axios.get(`${AUTH_URL}/auth/me`, {
      headers: { Authorization: `Bearer ${data.access_token}` },
    })
    setUser(r.data)
  }

  const logout = async () => {
    await authAPI.deleteToken()
    setToken(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, login, logout, loading, token }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth hors AuthProvider')
  return ctx
}
