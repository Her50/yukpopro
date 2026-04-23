import { useState, useEffect } from 'react'
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  RefreshControl, ActivityIndicator, Dimensions,
} from 'react-native'
import { BarChart, LineChart } from 'react-native-chart-kit'
import { Ionicons } from '@expo/vector-icons'
import { useRouter } from 'expo-router'
import { analyticsAPI } from '../../src/api/client'
import { useAuth } from '../../src/context/AuthContext'

const SCREEN_WIDTH = Dimensions.get('window').width
const CHART_WIDTH = SCREEN_WIDTH - 48

interface KPI {
  label: string
  value: string
  variation: string
  hausse: boolean
  icon: string
  couleur: string
}

interface AlerteMobile {
  type: 'error' | 'warning' | 'info'
  message: string
  date: string
}

interface PrimeParBranche {
  branche: string
  montant_millions: number
}

const CHART_CONFIG = {
  backgroundGradientFrom: '#fff',
  backgroundGradientTo: '#fff',
  color: (opacity = 1) => `rgba(29, 78, 216, ${opacity})`,
  strokeWidth: 2,
  barPercentage: 0.6,
  useShadowColorFromDataset: false,
  propsForLabels: { fontSize: 10 },
}

export default function DashboardScreen() {
  const [refreshing, setRefreshing] = useState(false)
  const [loading, setLoading] = useState(true)
  const [kpis, setKpis] = useState<KPI[]>([])
  const [alertes, setAlertes] = useState<AlerteMobile[]>([])
  const [primesBranches, setPrimesBranches] = useState<PrimeParBranche[]>([])
  const [hasError, setHasError] = useState(false)
  const { user, logout } = useAuth()
  const router = useRouter()

  const chargerDonnees = async () => {
    setHasError(false)
    try {
      const data = await analyticsAPI.getDashboard()
      setKpis(data?.kpis ?? [])
      setAlertes(data?.alertes ?? [])
      setPrimesBranches(data?.primes_par_branche ?? [])
    } catch {
      setHasError(true)
      setKpis([])
      setAlertes([])
      setPrimesBranches([])
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => { chargerDonnees() }, [])

  const onRefresh = () => {
    setRefreshing(true)
    chargerDonnees()
  }

  return (
    <ScrollView
      style={styles.container}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#1d4ed8" />}
    >
      {/* Bandeau utilisateur */}
      <View style={styles.userBanner}>
        <View>
          <Text
            style={styles.bonjour}
            accessibilityRole="header"
            accessibilityLevel={1}
          >
            Bonjour, {user?.nom?.split(' ')[0] || 'Utilisateur'} 👋
          </Text>
          <Text style={styles.compagnie}>{user?.compagnie_nom || 'YukpoAssurance'}</Text>
        </View>
        <TouchableOpacity onPress={logout} style={styles.logoutBtn} accessibilityLabel="Déconnexion">
          <Ionicons name="log-out-outline" size={22} color="#1e40af" />
        </TouchableOpacity>
      </View>

      {loading ? (
        <ActivityIndicator style={{ marginTop: 40 }} size="large" color="#1d4ed8" />
      ) : kpis.length === 0 && alertes.length === 0 && primesBranches.length === 0 ? (
        <View style={styles.emptyState}>
          <Ionicons
            name={hasError ? 'cloud-offline-outline' : 'bar-chart-outline'}
            size={48}
            color="#cbd5e1"
          />
          <Text style={styles.emptyTitle}>
            {hasError ? 'Impossible de charger les données' : 'Aucune donnée disponible'}
          </Text>
          <Text style={styles.emptyDesc}>
            {hasError
              ? 'Vérifie ta connexion ou réessaie.'
              : 'Importe ton portefeuille ou connecte ta source CIMA.'}
          </Text>
          <TouchableOpacity style={styles.emptyBtn} onPress={onRefresh}>
            <Ionicons name="refresh-outline" size={16} color="#fff" />
            <Text style={styles.emptyBtnText}>Réessayer</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <>
          {/* KPI Cards */}
          {kpis.length > 0 && (
          <View style={styles.kpiGrid}>
            {kpis.map((k, i) => (
              <View key={i} style={styles.kpiCard}>
                <View style={[styles.kpiIcon, { backgroundColor: k.couleur + '20' }]}>
                  <Ionicons name={k.icon as never} size={20} color={k.couleur} />
                </View>
                <Text style={styles.kpiValue}>{k.value}</Text>
                <Text style={styles.kpiLabel}>{k.label}</Text>
                <View style={[styles.variationBadge, { backgroundColor: k.hausse ? '#dcfce7' : '#fee2e2' }]}>
                  <Ionicons
                    name={k.hausse ? 'trending-up-outline' : 'trending-down-outline'}
                    size={11}
                    color={k.hausse ? '#16a34a' : '#dc2626'}
                  />
                  <Text style={[styles.variationText, { color: k.hausse ? '#16a34a' : '#dc2626' }]}>
                    {k.variation}
                  </Text>
                </View>
              </View>
            ))}
          </View>
          )}

          {/* Graphique Primes par branche */}
          {primesBranches.length > 0 && (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Primes par branche (M XAF)</Text>
            <BarChart
              data={{
                labels: primesBranches.map((b) => b.branche),
                datasets: [{ data: primesBranches.map((b) => b.montant_millions) }],
              }}
              width={CHART_WIDTH}
              height={180}
              chartConfig={CHART_CONFIG}
              style={{ borderRadius: 8, marginTop: 8 }}
              showValuesOnTopOfBars
              fromZero
              yAxisLabel=""
              yAxisSuffix="M"
            />
          </View>
          )}

          {/* Alertes CIMA */}
          {alertes.length > 0 && (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Alertes & Notifications</Text>
            {alertes.map((a, i) => (
              <View key={i} style={[styles.alerte, {
                backgroundColor: a.type === 'error' ? '#fef2f2' : a.type === 'warning' ? '#fffbeb' : '#eff6ff',
                borderLeftColor: a.type === 'error' ? '#ef4444' : a.type === 'warning' ? '#f59e0b' : '#3b82f6',
              }]}>
                <Ionicons
                  name={a.type === 'error' ? 'alert-circle-outline' : a.type === 'warning' ? 'warning-outline' : 'information-circle-outline'}
                  size={16}
                  color={a.type === 'error' ? '#ef4444' : a.type === 'warning' ? '#f59e0b' : '#3b82f6'}
                />
                <View style={{ flex: 1, marginLeft: 8 }}>
                  <Text style={styles.alerteMessage}>{a.message}</Text>
                  <Text style={styles.alerteDate}>{a.date}</Text>
                </View>
              </View>
            ))}
          </View>
          )}

          {/* Accès rapides */}
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Accès rapides</Text>
            <View style={styles.quickGrid}>
              {[
                { label: 'Nouveau sinistre', icon: 'add-circle-outline', route: '/(tabs)/sinistres', couleur: '#ef4444' },
                { label: 'Scanner CNI', icon: 'camera-outline', route: '/(tabs)/scanner', couleur: '#3b82f6' },
                { label: 'Copilote IA', icon: 'chatbubble-outline', route: '/(tabs)/chat', couleur: '#8b5cf6' },
                { label: 'Souscription', icon: 'document-text-outline', route: '/souscription', couleur: '#10b981' },
                { label: 'Commercial', icon: 'trending-up-outline', route: '/(tabs)/commercial', couleur: '#f59e0b' },
                { label: 'Fournisseurs', icon: 'storefront-outline', route: '/fournisseur', couleur: '#0ea5e9' },
                { label: 'Module RH', icon: 'people-outline', route: '/rh', couleur: '#7c3aed' },
                { label: 'Réunions', icon: 'calendar-outline', route: '/reunions', couleur: '#0d9488' },
                { label: 'Commissions', icon: 'cash-outline', route: '/commissions', couleur: '#16a34a' },
                { label: 'Juridique', icon: 'scale-outline', route: '/juridique', couleur: '#7c3aed' },
                { label: 'Archive', icon: 'archive-outline', route: '/archive', couleur: '#0891b2' },
              ].map((q, i) => (
                <TouchableOpacity
                  key={i}
                  style={styles.quickBtn}
                  onPress={() => router.push(q.route as never)}
                >
                  <View style={[styles.quickIcon, { backgroundColor: q.couleur + '20' }]}>
                    <Ionicons name={q.icon as never} size={24} color={q.couleur} />
                  </View>
                  <Text style={styles.quickLabel}>{q.label}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        </>
      )}
    </ScrollView>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f1f5f9' },
  userBanner: {
    backgroundColor: '#fff',
    padding: 16,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderBottomWidth: 1,
    borderBottomColor: '#e2e8f0',
  },
  bonjour: { fontSize: 16, fontWeight: 'bold', color: '#1e293b' },
  compagnie: { fontSize: 12, color: '#64748b', marginTop: 2 },
  logoutBtn: { padding: 8, borderRadius: 8, backgroundColor: '#eff6ff' },
  kpiGrid: { flexDirection: 'row', flexWrap: 'wrap', padding: 12, gap: 12 },
  kpiCard: {
    width: (SCREEN_WIDTH - 48) / 2,
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 14,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 4,
    elevation: 2,
  },
  kpiIcon: { width: 36, height: 36, borderRadius: 8, alignItems: 'center', justifyContent: 'center', marginBottom: 8 },
  kpiValue: { fontSize: 16, fontWeight: 'bold', color: '#1e293b' },
  kpiLabel: { fontSize: 11, color: '#64748b', marginTop: 2 },
  variationBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 3,
    paddingHorizontal: 6, paddingVertical: 3, borderRadius: 20, marginTop: 8, alignSelf: 'flex-start',
  },
  variationText: { fontSize: 11, fontWeight: '600' },
  card: {
    backgroundColor: '#fff', borderRadius: 12, margin: 12, marginTop: 0, padding: 16,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06, shadowRadius: 4, elevation: 2,
  },
  cardTitle: { fontSize: 14, fontWeight: '700', color: '#1e293b', marginBottom: 4 },
  alerte: {
    flexDirection: 'row', alignItems: 'flex-start', borderLeftWidth: 3,
    borderRadius: 8, padding: 10, marginTop: 8,
  },
  alerteMessage: { fontSize: 12, color: '#374151', fontWeight: '500' },
  alerteDate: { fontSize: 10, color: '#94a3b8', marginTop: 2 },
  quickGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginTop: 12 },
  quickBtn: { width: (SCREEN_WIDTH - 80) / 2, alignItems: 'center', gap: 8 },
  quickIcon: { width: 52, height: 52, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  quickLabel: { fontSize: 12, color: '#374151', fontWeight: '600', textAlign: 'center' },
  emptyState: {
    margin: 16, padding: 32, backgroundColor: '#fff', borderRadius: 12,
    alignItems: 'center', gap: 8,
  },
  emptyTitle: { fontSize: 14, fontWeight: '700', color: '#334155', marginTop: 8, textAlign: 'center' },
  emptyDesc: { fontSize: 12, color: '#64748b', textAlign: 'center', lineHeight: 18 },
  emptyBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: '#1d4ed8', paddingHorizontal: 16, paddingVertical: 10,
    borderRadius: 8, marginTop: 12,
  },
  emptyBtnText: { color: '#fff', fontSize: 13, fontWeight: '600' },
})
