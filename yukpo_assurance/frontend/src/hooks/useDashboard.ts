import { useState, useEffect, useCallback } from 'react'
import { analyticsAPI } from '../api/client'
import { DashboardData } from '../api/types'

const REFRESH_INTERVAL = 5 * 60 * 1000 // 5 minutes

export function useDashboard(annee = 2025) {
  const [data, setData] = useState<DashboardData | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  const fetchDashboard = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const result = await analyticsAPI.getDashboard(annee)
      setData(result as DashboardData)
      setLastUpdated(new Date())
    } catch {
      setError('Impossible de charger les données du tableau de bord.')
    } finally {
      setIsLoading(false)
    }
  }, [annee])

  useEffect(() => {
    fetchDashboard()
    const interval = setInterval(fetchDashboard, REFRESH_INTERVAL)
    return () => clearInterval(interval)
  }, [fetchDashboard])

  return { data, isLoading, error, lastUpdated, refresh: fetchDashboard }
}
