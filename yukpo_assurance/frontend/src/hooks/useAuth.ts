import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { authAPI } from '../api/client'
import { useAuthStore } from '../store/authStore'

export function useAuth() {
  const { user, token, isAuthenticated, setAuth, clearAuth } = useAuthStore()
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const navigate = useNavigate()

  const login = async (email: string, password: string) => {
    setIsLoading(true)
    setError(null)
    try {
      // En mode simulation : extraire le username depuis l'email (admin@yukpo.cm → admin)
      const username = email.includes('@') ? email.split('@')[0] : email
      const tokenData = await authAPI.login(username, password) as Record<string, unknown>
      const accessToken = tokenData.access_token as string
      localStorage.setItem('access_token', accessToken)
      const raw = await authAPI.me() as Record<string, unknown>
      // Normalise la réponse backend → format User du frontend
      const userData = {
        id: (raw.user_id ?? raw.id) as number,
        email: (raw.email ?? '') as string,
        nom: (raw.user_nom ?? raw.nom ?? '') as string,
        prenom: (raw.prenom ?? '') as string,
        role: (raw.role ?? 'agent') as string,
        compagnie: (raw.compagnie ?? 'YukpoAssurance') as string,
      }
      setAuth(userData, accessToken)
      navigate('/dashboard')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      let message = 'Identifiants incorrects. Veuillez réessayer.'
      if (typeof detail === 'string') {
        message = detail
      } else if (Array.isArray(detail) && detail.length > 0) {
        // Erreur de validation Pydantic : [{type, loc, msg, input}]
        message = (detail[0] as { msg?: string })?.msg || message
      }
      setError(message)
    } finally {
      setIsLoading(false)
    }
  }

  const logout = () => {
    clearAuth()
    navigate('/login')
  }

  return { user, token, isAuthenticated, login, logout, error, isLoading }
}
