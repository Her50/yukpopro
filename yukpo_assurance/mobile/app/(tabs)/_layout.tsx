/**
 * Layout onglets mobiles — Architecture agent-first.
 *
 * Onglets principaux :
 *   1. Dashboard    — Vue synthétique KPI + alertes
 *   2. Agents       — Interface agent IA (instruction → exécution autonome)
 *   3. Validations  — File d'approbation humaine (swipe to approve)
 *   4. Alertes      — Notifications agents + conformité
 *   5. Yukpo IA     — Chat classique copilote CIMA
 */
import { Tabs } from 'expo-router'
import { Ionicons } from '@expo/vector-icons'
import { Platform, View, Text, StyleSheet } from 'react-native'
import { useEffect, useState } from 'react'

function TabIcon({ name, color, size }: { name: string; color: string; size: number }) {
  return <Ionicons name={name as any} size={size} color={color} />
}

function BadgeIcon({ name, color, size, badge }: { name: string; color: string; size: number; badge?: number }) {
  return (
    <View>
      <Ionicons name={name as any} size={size} color={color} />
      {badge != null && badge > 0 && (
        <View style={styles.badge}>
          <Text style={styles.badgeText}>{badge > 9 ? '9+' : badge}</Text>
        </View>
      )}
    </View>
  )
}

const API = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000'

export default function TabLayout() {
  const [nbValidations, setNbValidations] = useState(0)
  const [nbAlertes, setNbAlertes] = useState(0)

  useEffect(() => {
    const charger = async () => {
      try {
        const token = '' // TODO: récupérer depuis authStore mobile
        const res = await fetch(`${API}/api/v1/agent/stats`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        })
        if (res.ok) {
          const data = await res.json()
          setNbValidations(data.file_validation?.en_attente ?? 0)
        }
      } catch { /* ignore */ }
    }
    charger()
    const interval = setInterval(charger, 30_000) // refresh toutes les 30s
    return () => clearInterval(interval)
  }, [])

  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: '#4f46e5',  // indigo-600
        tabBarInactiveTintColor: '#94a3b8',
        tabBarStyle: {
          backgroundColor: '#ffffff',
          borderTopWidth: 1,
          borderTopColor: '#e2e8f0',
          height: Platform.OS === 'ios' ? 88 : 68,
          paddingBottom: Platform.OS === 'ios' ? 22 : 10,
          paddingTop: 8,
          shadowColor: '#000',
          shadowOffset: { width: 0, height: -2 },
          shadowOpacity: 0.05,
          shadowRadius: 8,
          elevation: 8,
        },
        tabBarLabelStyle: { fontSize: 10, fontWeight: '600' },
        headerStyle: { backgroundColor: '#4f46e5' },
        headerTintColor: '#fff',
        headerTitleStyle: { fontWeight: 'bold', fontSize: 16 },
      }}
    >
      {/* ─── 1. Dashboard ──────────────────────────────────── */}
      <Tabs.Screen
        name="dashboard"
        options={{
          title: 'Accueil',
          tabBarIcon: ({ color, size }) => <TabIcon name="home-outline" color={color} size={size} />,
          headerTitle: 'YukpoAssurance',
        }}
      />

      {/* ─── 2. Agents IA ─────────────────────────────────── */}
      <Tabs.Screen
        name="agent"
        options={{
          title: 'Agents',
          tabBarIcon: ({ color, size }) => <TabIcon name="flash-outline" color={color} size={size} />,
          headerTitle: 'Agents IA Autonomes',
          tabBarBadge: undefined,
        }}
      />

      {/* ─── 3. Validations ───────────────────────────────── */}
      <Tabs.Screen
        name="validations"
        options={{
          title: 'Validations',
          tabBarIcon: ({ color, size }) => (
            <BadgeIcon name="shield-checkmark-outline" color={color} size={size} badge={nbValidations} />
          ),
          headerTitle: 'Validations en attente',
          tabBarBadge: nbValidations > 0 ? nbValidations : undefined,
          tabBarBadgeStyle: { backgroundColor: '#f97316', fontSize: 10, minWidth: 18, height: 18 },
        }}
      />

      {/* ─── 4. Alertes ───────────────────────────────────── */}
      <Tabs.Screen
        name="alertes"
        options={{
          title: 'Alertes',
          tabBarIcon: ({ color, size }) => (
            <BadgeIcon name="notifications-outline" color={color} size={size} badge={nbAlertes} />
          ),
          headerTitle: 'Alertes & Conformité',
          tabBarBadge: nbAlertes > 0 ? nbAlertes : undefined,
          tabBarBadgeStyle: { backgroundColor: '#ef4444', fontSize: 10, minWidth: 18, height: 18 },
        }}
      />

      {/* ─── 5. Yukpo IA (chat classique) ─────────────────── */}
      <Tabs.Screen
        name="chat"
        options={{
          title: 'Yukpo IA',
          tabBarIcon: ({ color, size }) => <TabIcon name="chatbubble-outline" color={color} size={size} />,
          headerTitle: 'Yukpo IA — Copilote CIMA',
        }}
      />

      {/* ─── Écrans cachés (accessibles depuis d'autres pages) ─ */}
      <Tabs.Screen name="sinistres"  options={{ href: null }} />
      <Tabs.Screen name="commercial" options={{ href: null }} />
      <Tabs.Screen name="scanner"    options={{ href: null }} />
      <Tabs.Screen name="courtiers"  options={{ href: null }} />
    </Tabs>
  )
}

const styles = StyleSheet.create({
  badge: {
    position: 'absolute',
    top: -4,
    right: -8,
    backgroundColor: '#f97316',
    borderRadius: 10,
    minWidth: 16,
    height: 16,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 3,
  },
  badgeText: {
    color: '#fff',
    fontSize: 9,
    fontWeight: 'bold',
  },
})
