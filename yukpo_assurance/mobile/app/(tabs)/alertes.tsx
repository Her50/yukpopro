/**
 * Écran Alertes — Notifications des agents (conformité, sinistralité, risques).
 */
import React, { useEffect, useState, useCallback } from 'react'
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  RefreshControl, Platform,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'

const API = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000'

type NiveauAlerte = 'info' | 'avertissement' | 'critique'

interface Alerte {
  id: string
  niveau: NiveauAlerte
  titre: string
  message: string
  agent: string
  timestamp: string
  lue: boolean
}

const NIVEAU_CONFIG: Record<NiveauAlerte, { icon: string; couleur: string; bg: string; border: string }> = {
  info:           { icon: 'information-circle-outline', couleur: '#3b82f6', bg: '#eff6ff', border: '#bfdbfe' },
  avertissement:  { icon: 'warning-outline',            couleur: '#f59e0b', bg: '#fffbeb', border: '#fde68a' },
  critique:       { icon: 'alert-circle-outline',       couleur: '#ef4444', bg: '#fef2f2', border: '#fecaca' },
}

// Données simulées (en production → endpoint GET /api/v1/agent/alertes)
const ALERTES_DEMO: Alerte[] = [
  {
    id: '1',
    niveau: 'critique',
    titre: 'Ratio solvabilité sous le seuil CIMA',
    message: 'Le ratio de solvabilité est à 92% — en dessous du minimum réglementaire de 100% (Art. 337-1 CIMA). Action immédiate requise.',
    agent: 'conformite',
    timestamp: new Date(Date.now() - 1800000).toISOString(),
    lue: false,
  },
  {
    id: '2',
    niveau: 'avertissement',
    titre: '28 polices en échéance dans 30 jours',
    message: 'Segment Auto Cameroun — taux de renouvellement estimé à 65%. Campagne de relance recommandée.',
    agent: 'commercial',
    timestamp: new Date(Date.now() - 7200000).toISOString(),
    lue: false,
  },
  {
    id: '3',
    niveau: 'info',
    titre: 'Rapport mensuel T1-2025 prêt',
    message: 'Le rapport de performance mensuel a été généré et est en attente de validation avant diffusion à la direction.',
    agent: 'intelligence',
    timestamp: new Date(Date.now() - 86400000).toISOString(),
    lue: true,
  },
]

export default function AlertesScreen() {
  const [alertes, setAlertes]       = useState<Alerte[]>(ALERTES_DEMO)
  const [refreshing, setRefreshing] = useState(false)
  const [filtre, setFiltre]         = useState<NiveauAlerte | 'tous'>('tous')

  const charger = useCallback(async () => {
    setRefreshing(true)
    try {
      // TODO: fetch réel depuis le backend
      // const res = await fetch(`${API}/api/v1/agent/alertes`)
      // const data = await res.json()
      // setAlertes(data.alertes ?? [])
    } finally {
      setRefreshing(false)
    }
  }, [])

  useEffect(() => { charger() }, [])

  const marquerLue = (id: string) => {
    setAlertes((prev) => prev.map((a) => a.id === id ? { ...a, lue: true } : a))
  }

  const alertesFiltrees = alertes.filter((a) => filtre === 'tous' || a.niveau === filtre)
  const nonLues = alertes.filter((a) => !a.lue).length

  return (
    <View style={styles.container}>
      {/* En-tête stats */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <Text style={styles.headerTitle}>
            {nonLues > 0 ? `${nonLues} alertes non lues` : 'Aucune alerte non lue'}
          </Text>
          <Text style={styles.headerSub}>{alertes.length} alerte(s) au total</Text>
        </View>
        {nonLues > 0 && (
          <TouchableOpacity
            style={styles.tuteLue}
            onPress={() => setAlertes((prev) => prev.map((a) => ({ ...a, lue: true })))}
          >
            <Text style={styles.tuteLueText}>Tout marquer lu</Text>
          </TouchableOpacity>
        )}
      </View>

      {/* Filtres */}
      <View style={styles.filtres}>
        {(['tous', 'critique', 'avertissement', 'info'] as const).map((n) => (
          <TouchableOpacity
            key={n}
            style={[styles.filtreBadge, filtre === n && styles.filtreActif]}
            onPress={() => setFiltre(n)}
          >
            <Text style={[styles.filtreText, filtre === n && styles.filtreTextActif]}>
              {n === 'tous' ? 'Tous' : n === 'critique' ? 'Critiques' : n === 'avertissement' ? 'Avertissements' : 'Infos'}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Liste */}
      <ScrollView
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={charger} tintColor="#4f46e5" />}
        contentContainerStyle={{ padding: 16, gap: 10 }}
      >
        {alertesFiltrees.length === 0 && (
          <View style={styles.emptyState}>
            <Ionicons name="notifications-off-outline" size={48} color="#c7d2fe" />
            <Text style={styles.emptyTitle}>Aucune alerte</Text>
          </View>
        )}

        {alertesFiltrees.map((alerte) => {
          const config = NIVEAU_CONFIG[alerte.niveau]
          return (
            <TouchableOpacity
              key={alerte.id}
              style={[styles.card, { backgroundColor: config.bg, borderColor: config.border }, alerte.lue && styles.cardLue]}
              onPress={() => marquerLue(alerte.id)}
              activeOpacity={0.85}
            >
              <View style={styles.cardHeader}>
                <Ionicons name={config.icon as any} size={20} color={config.couleur} />
                <Text style={[styles.cardTitre, { color: config.couleur }]}>{alerte.titre}</Text>
                {!alerte.lue && <View style={[styles.pointNonLu, { backgroundColor: config.couleur }]} />}
              </View>
              <Text style={styles.cardMessage}>{alerte.message}</Text>
              <View style={styles.cardMeta}>
                <Text style={styles.cardAgent}>🤖 Agent {alerte.agent}</Text>
                <Text style={styles.cardDate}>
                  {new Date(alerte.timestamp).toLocaleDateString('fr-FR', {
                    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'
                  })}
                </Text>
              </View>
            </TouchableOpacity>
          )
        })}
      </ScrollView>
    </View>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8fafc' },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    backgroundColor: '#fff', padding: 16, borderBottomWidth: 1, borderBottomColor: '#e2e8f0',
  },
  headerLeft: {},
  headerTitle: { fontSize: 16, fontWeight: 'bold', color: '#1e293b' },
  headerSub: { fontSize: 12, color: '#94a3b8', marginTop: 2 },
  tuteLue: { backgroundColor: '#eef2ff', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 20 },
  tuteLueText: { fontSize: 12, color: '#4f46e5', fontWeight: '600' },
  filtres: {
    flexDirection: 'row', gap: 8, padding: 12,
    backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#e2e8f0',
  },
  filtreBadge: {
    paddingHorizontal: 12, paddingVertical: 6, borderRadius: 20,
    backgroundColor: '#f1f5f9',
  },
  filtreActif: { backgroundColor: '#4f46e5' },
  filtreText: { fontSize: 12, fontWeight: '600', color: '#64748b' },
  filtreTextActif: { color: '#fff' },
  emptyState: { alignItems: 'center', paddingTop: 60 },
  emptyTitle: { fontSize: 16, fontWeight: 'bold', color: '#374151', marginTop: 16 },
  card: {
    borderRadius: 12, padding: 14, borderWidth: 1.5,
  },
  cardLue: { opacity: 0.7 },
  cardHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  cardTitre: { flex: 1, fontSize: 14, fontWeight: '700' },
  pointNonLu: { width: 8, height: 8, borderRadius: 4 },
  cardMessage: { fontSize: 13, color: '#374151', lineHeight: 19, marginBottom: 10 },
  cardMeta: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  cardAgent: { fontSize: 11, color: '#64748b' },
  cardDate: { fontSize: 11, color: '#94a3b8' },
})
