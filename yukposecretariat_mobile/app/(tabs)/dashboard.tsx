import { useEffect, useState } from 'react'
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet, RefreshControl,
} from 'react-native'
import { useRouter } from 'expo-router'
import { Ionicons } from '@expo/vector-icons'
import { useAuth } from '../../src/context/AuthContext'
import { gestionAPI } from '../../src/api/client'

function formatFCFA(n: number) {
  return new Intl.NumberFormat('fr-FR').format(n) + ' FCFA'
}

const ACCES = [
  { label: 'Rédiger', icon: 'document-text' as const, route: '/redaction', color: '#2563eb' },
  { label: 'Scanner', icon: 'scan' as const, route: '/scanner', color: '#16a34a' },
  { label: 'Dicter', icon: 'mic' as const, route: '/audio', color: '#7c3aed' },
  { label: 'Infographie', icon: 'image' as const, route: '/infographie', color: '#ea580c' },
  { label: 'Kanban', icon: 'albums' as const, route: '/kanban', color: '#4f46e5' },
  { label: 'Caisse', icon: 'wallet' as const, route: '/caisse', color: '#059669' },
]

export default function DashboardScreen() {
  const router = useRouter()
  const { user, logout } = useAuth()
  const [caisse, setCaisse] = useState<{ total_entrees?: number; solde?: number } | null>(null)
  const [travaux, setTravaux] = useState<{ travaux?: { statut: string }[] } | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const charger = async () => {
    try {
      const [c, t] = await Promise.all([
        gestionAPI.transactions(),
        gestionAPI.travaux(),
      ])
      setCaisse(c.data.rapport)
      setTravaux(t.data)
    } catch { /* non bloquant */ }
  }

  useEffect(() => { charger() }, [])

  const onRefresh = async () => {
    setRefreshing(true)
    await charger()
    setRefreshing(false)
  }

  const enAttente = travaux?.travaux?.filter(t => t.statut === 'en_attente').length ?? 0
  const enCours = travaux?.travaux?.filter(t => t.statut === 'en_cours').length ?? 0

  return (
    <ScrollView
      style={s.container}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#2563eb" />}
    >
      {/* Header */}
      <View style={s.header}>
        <View>
          <Text style={s.greeting}>Bonjour, {user?.user_nom?.split(' ')[0] ?? 'secrétaire'} 👋</Text>
          <Text style={s.subtitle}>Que faisons-nous aujourd'hui ?</Text>
        </View>
        <TouchableOpacity onPress={logout} style={s.logoutBtn}>
          <Ionicons name="log-out-outline" size={22} color="#fff" />
        </TouchableOpacity>
      </View>

      {/* KPIs */}
      <View style={s.kpisRow}>
        <View style={[s.kpi, { backgroundColor: '#f0fdf4', borderColor: '#bbf7d0' }]}>
          <Text style={[s.kpiVal, { color: '#16a34a' }]}>{formatFCFA(caisse?.total_entrees ?? 0)}</Text>
          <Text style={s.kpiLabel}>Caisse du jour</Text>
        </View>
        <View style={[s.kpi, { backgroundColor: '#fff7ed', borderColor: '#fed7aa' }]}>
          <Text style={[s.kpiVal, { color: '#ea580c' }]}>{enAttente}</Text>
          <Text style={s.kpiLabel}>En attente</Text>
        </View>
        <View style={[s.kpi, { backgroundColor: '#eff6ff', borderColor: '#bfdbfe' }]}>
          <Text style={[s.kpiVal, { color: '#2563eb' }]}>{enCours}</Text>
          <Text style={s.kpiLabel}>En cours</Text>
        </View>
      </View>

      {/* Accès rapides */}
      <Text style={s.sectionTitle}>Accès rapides</Text>
      <View style={s.grid}>
        {ACCES.map(({ label, icon, route, color }) => (
          <TouchableOpacity
            key={route}
            style={s.gridItem}
            onPress={() => router.push(route as any)}
            activeOpacity={0.7}
          >
            <View style={[s.gridIcon, { backgroundColor: color }]}>
              <Ionicons name={icon} size={26} color="#fff" />
            </View>
            <Text style={s.gridLabel}>{label}</Text>
          </TouchableOpacity>
        ))}
      </View>
    </ScrollView>
  )
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f9fafb' },
  header: {
    backgroundColor: '#2563eb',
    paddingTop: 56,
    paddingBottom: 24,
    paddingHorizontal: 20,
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
  },
  greeting: { fontSize: 22, fontWeight: '700', color: '#fff' },
  subtitle: { fontSize: 13, color: '#bfdbfe', marginTop: 2 },
  logoutBtn: { padding: 6, borderRadius: 10, backgroundColor: 'rgba(255,255,255,0.2)' },
  kpisRow: {
    flexDirection: 'row',
    gap: 10,
    paddingHorizontal: 16,
    marginTop: -16,
    marginBottom: 8,
  },
  kpi: {
    flex: 1,
    borderRadius: 14,
    padding: 12,
    borderWidth: 1,
    backgroundColor: '#fff',
    shadowColor: '#000',
    shadowOpacity: 0.06,
    shadowRadius: 8,
    elevation: 3,
  },
  kpiVal: { fontSize: 15, fontWeight: '700' },
  kpiLabel: { fontSize: 10, color: '#6b7280', marginTop: 2 },
  sectionTitle: {
    fontSize: 15,
    fontWeight: '600',
    color: '#374151',
    paddingHorizontal: 16,
    marginTop: 16,
    marginBottom: 10,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    paddingHorizontal: 12,
    gap: 10,
    paddingBottom: 24,
  },
  gridItem: {
    width: '30%',
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 14,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOpacity: 0.05,
    shadowRadius: 6,
    elevation: 2,
    borderWidth: 1,
    borderColor: '#f3f4f6',
  },
  gridIcon: { borderRadius: 12, padding: 12, marginBottom: 8 },
  gridLabel: { fontSize: 11, fontWeight: '600', color: '#374151', textAlign: 'center' },
})
