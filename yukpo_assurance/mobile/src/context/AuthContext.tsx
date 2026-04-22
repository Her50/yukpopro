import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import * as SecureStore from 'expo-secure-store'
import { authAPI } from '../api/client'

interface User {
  id: string
  nom: string
  email: string
  role: string
  compagnie_id: string
  compagnie_nom: string
}

interface AuthContextType {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  // Restore session on app start
  useEffect(() => {
    const restoreSession = async () => {
      try {
        const savedToken = await SecureStore.getItemAsync('access_token')
        const savedUser = await SecureStore.getItemAsync('user')
        if (savedToken && savedUser) {
          setToken(savedToken)
          setUser(JSON.parse(savedUser))
        }
      } catch { /* ignore */ } finally {
        setIsLoading(false)
      }
    }
    restoreSession()
  }, [])

  const login = async (username: string, password: string) => {
    const data = await authAPI.login(username, password)
    const accessToken = data.access_token
    const me = await authAPI.me()

    await SecureStore.setItemAsync('access_token', accessToken)
    await SecureStore.setItemAsync('user', JSON.stringify(me))

    setToken(accessToken)
    setUser(me)
  }

  const logout = async () => {
    await SecureStore.deleteItemAsync('access_token')
    await SecureStore.deleteItemAsync('user')
    setToken(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, token, isAuthenticated: !!token, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
