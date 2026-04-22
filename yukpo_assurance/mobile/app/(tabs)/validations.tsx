/**
 * Écran Validations — File d'approbation humaine sur mobile.
 *
 * Swipe right = Approuver / Swipe left = Rejeter
 * Après décision → l'agent reprend automatiquement le processus.
 */
import React, { useEffect, useState, useCallback } from 'react'
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  RefreshControl, ActivityIndicator, Alert, Modal, TextInput,
  Platform,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'

const API = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000'

interface ValidationItem {
  id: string
  type: string
  description: string
  montant: number
  statut: string
  cree_le: string
  expires_le: string
  peut_reprendre: boolean
  donnees: Record<string, unknown>
}

const TYPE_LABELS: Record<string, string> = {
  sinistre: 'Sinistre',
  emission_police: 'Police',
  conge_rh: 'Congé',
  recrutement_offre: 'Recrutement',
  embauche: 'Embauche',
  transaction_juridique: 'Transaction',
  ecriture_comptable_grande: 'Écriture comptable',
  cloture_comptable: 'Clôture',
  rapport_direction: 'Rapport direction',
}

export default function ValidationsScreen() {
  const [items, setItems]           = useState<ValidationItem[]>([])
  const [stats, setStats]           = useState({ en_attente: 0, montant_en_attente_fcfa: 0 })
  const [refreshing, setRefreshing] = useState(false)
  const [modalItem, setModalItem]   = useState<ValidationItem | null>(null)
  const [motifRejet, setMotifRejet] = useState('')
  const [commentaire, setCommentaire] = useState('')
  const [loading, setLoading]       = useState(false)
  const [reprise, setReprise]       = useState<{ statut: string; resume: string } | null>(null)

  const charger = useCallback(async () => {
    setRefreshing(true)
    try {
      const token = ''
      const res = await fetch(`${API}/api/v1/agent/validations?statut=en_attente&limit=50`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (res.ok) {
        const data = await res.json()
        setItems(data.validations ?? [])
        setStats(data.stats ?? stats)
      }
    } finally {
      setRefreshing(false)
    }
  }, [])

  useEffect(() => { charger() }, [])

  const approuver = async (item: ValidationItem) => {
    setLoading(true)
    try {
      const token = ''
      const res = await fetch(`${API}/api/v1/agent/approuver/${item.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ commentaire }),
      })
      const data = await res.json()
      setItems((prev) => prev.filter((i) => i.id !== item.id))

      if (data.reprise) {
        setReprise({ statut: data.reprise.statut, resume: data.reprise.resume })
      }
      setModalItem(null)
      setCommentaire('')
    } catch (err) {
      Alert.alert('Erreur', String(err))
    } finally {
      setLoading(false)
    }
  }

  const rejeter = async (item: ValidationItem) => {
    if (!motifRejet.trim()) {
      Alert.alert('Motif requis', 'Veuillez saisir le motif du rejet')
      return
    }
    setLoading(true)
    try {
      const token = ''
      const res = await fetch(`${API}/api/v1/agent/rejeter/${item.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ motif: motifRejet }),
      })
      const data = await res.json()
      setItems((prev) => prev.filter((i) => i.id !== item.id))

      if (data.reprise) {
        setReprise({ statut: data.reprise.statut, resume: data.reprise.resume })
      }
      setModalItem(null)
      setMotifRejet('')
    } catch (err) {
      Alert.alert('Erreur', String(err))
    } finally {
      setLoading(false)
    }
  }

  const formatMontant = (m: number) =>
    m > 0 ? `${m.toLocaleString('fr-FR')} FCFA` : '—'

  const urgenceItem = (item: ValidationItem) => {
    if (item.montant >= 5_000_000) return { color: '#ef4444', label: 'Critique' }
    if (item.montant >= 1_000_000) return { color: '#f97316', label: 'Important' }
    return { color: '#3b82f6', label: 'Standard' }
  }

  return (
    <View style={styles.container}>
      {/* Stats en-tête */}
      <View style={styles.statsBar}>
        <View style={styles.statItem}>
          <Text style={styles.statValue}>{stats.en_attente}</Text>
          <Text style={styles.statLabel}>En attente</Text>
        </View>
        <View style={styles.statDivider} />
        <View style={styles.statItem}>
          <Text style={styles.statValue}>
            {(stats.montant_en_attente_fcfa / 1_000_000).toFixed(1)}M
          </Text>
          <Text style={styles.statLabel}>FCFA en jeu</Text>
        </View>
        <TouchableOpacity style={styles.refreshBtn} onPress={charger}>
          <Ionicons name="refresh-outline" size={20} color="#4f46e5" />
        </TouchableOpacity>
      </View>

      {/* Notification reprise agent */}
      {reprise && (
        <View style={[styles.repriseCard, reprise.statut === 'termine' ? styles.repriseOk : styles.repriseAttente]}>
          <Ionicons name="sync-outline" size={16} color={reprise.statut === 'termine' ? '#16a34a' : '#f97316'} />
          <View style={{ flex: 1 }}>
            <Text style={styles.repriseLabel}>
              {reprise.statut === 'termine' ? 'Agent a terminé le processus' : 'Agent a repris — nouvelle étape en cours'}
            </Text>
            {reprise.resume && (
              <Text style={styles.repriseResume} numberOfLines={2}>{reprise.resume}</Text>
            )}
          </View>
          <TouchableOpacity onPress={() => setReprise(null)}>
            <Ionicons name="close" size={16} color="#94a3b8" />
          </TouchableOpacity>
        </View>
      )}

      {/* Liste des validations */}
      <ScrollView
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={charger} tintColor="#4f46e5" />}
        contentContainerStyle={{ padding: 16, gap: 10 }}
      >
        {items.length === 0 && !refreshing && (
          <View style={styles.emptyState}>
            <Ionicons name="shield-checkmark-outline" size={48} color="#c7d2fe" />
            <Text style={styles.emptyTitle}>Aucune validation en attente</Text>
            <Text style={styles.emptyDesc}>Les décisions importantes des agents apparaîtront ici</Text>
          </View>
        )}

        {items.map((item) => {
          const urgence = urgenceItem(item)
          return (
            <TouchableOpacity
              key={item.id}
              style={styles.card}
              onPress={() => setModalItem(item)}
              activeOpacity={0.85}
            >
              <View style={styles.cardHeader}>
                <View style={[styles.urgenceBadge, { backgroundColor: urgence.color + '20' }]}>
                  <Text style={[styles.urgenceText, { color: urgence.color }]}>{urgence.label}</Text>
                </View>
                <Text style={styles.cardType}>{TYPE_LABELS[item.type] || item.type}</Text>
                {item.peut_reprendre && (
                  <View style={styles.repriseBadge}>
                    <Ionicons name="sync-outline" size={10} color="#4f46e5" />
                    <Text style={styles.repriseTag}>Auto-reprise</Text>
                  </View>
                )}
              </View>

              <Text style={styles.cardDesc} numberOfLines={2}>{item.description}</Text>

              <View style={styles.cardFooter}>
                <Text style={styles.cardMontant}>{formatMontant(item.montant)}</Text>
                <View style={styles.cardActions}>
                  <TouchableOpacity
                    style={styles.btnRejet}
                    onPress={() => { setModalItem(item); /* show rejet */ }}
                  >
                    <Ionicons name="close" size={16} color="#ef4444" />
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={styles.btnApprouver}
                    onPress={() => approuver(item)}
                  >
                    <Ionicons name="checkmark" size={16} color="#fff" />
                    <Text style={styles.btnApprouverText}>Approuver</Text>
                  </TouchableOpacity>
                </View>
              </View>
            </TouchableOpacity>
          )
        })}
      </ScrollView>

      {/* Modal détail + rejet */}
      <Modal visible={!!modalItem} animationType="slide" presentationStyle="pageSheet">
        {modalItem && (
          <View style={styles.modal}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{TYPE_LABELS[modalItem.type] || modalItem.type}</Text>
              <TouchableOpacity onPress={() => setModalItem(null)}>
                <Ionicons name="close" size={24} color="#374151" />
              </TouchableOpacity>
            </View>
            <ScrollView style={styles.modalContent}>
              <Text style={styles.modalDesc}>{modalItem.description}</Text>
              <Text style={styles.modalMontant}>{formatMontant(modalItem.montant)}</Text>

              <View style={styles.modalDetails}>
                <Text style={styles.modalDetailsTitle}>Détails</Text>
                <Text style={styles.modalDetailsText}>
                  {JSON.stringify(modalItem.donnees, null, 2)}
                </Text>
              </View>

              <Text style={styles.sectionLabel}>Commentaire (optionnel)</Text>
              <TextInput
                style={styles.modalInput}
                value={commentaire}
                onChangeText={setCommentaire}
                placeholder="Votre commentaire..."
                multiline
              />

              <Text style={styles.sectionLabel}>Motif rejet (obligatoire si rejet)</Text>
              <TextInput
                style={styles.modalInput}
                value={motifRejet}
                onChangeText={setMotifRejet}
                placeholder="Motif du rejet..."
                multiline
              />
            </ScrollView>

            <View style={styles.modalActions}>
              <TouchableOpacity
                style={[styles.modalBtnRejet, loading && styles.btnDisabled]}
                onPress={() => rejeter(modalItem)}
                disabled={loading}
              >
                {loading ? <ActivityIndicator color="#ef4444" size="small" /> : (
                  <>
                    <Ionicons name="close-circle-outline" size={18} color="#ef4444" />
                    <Text style={styles.modalBtnRejetText}>Rejeter</Text>
                  </>
                )}
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.modalBtnApprouver, loading && styles.btnDisabled]}
                onPress={() => approuver(modalItem)}
                disabled={loading}
              >
                {loading ? <ActivityIndicator color="#fff" size="small" /> : (
                  <>
                    <Ionicons name="checkmark-circle-outline" size={18} color="#fff" />
                    <Text style={styles.modalBtnApprouverText}>Approuver</Text>
                  </>
                )}
              </TouchableOpacity>
            </View>
          </View>
        )}
      </Modal>
    </View>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8fafc' },
  statsBar: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: '#fff',
    paddingHorizontal: 20, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#e2e8f0',
  },
  statItem: { alignItems: 'center', flex: 1 },
  statValue: { fontSize: 22, fontWeight: 'bold', color: '#1e293b' },
  statLabel: { fontSize: 11, color: '#94a3b8', marginTop: 2 },
  statDivider: { width: 1, height: 40, backgroundColor: '#e2e8f0', marginHorizontal: 16 },
  refreshBtn: { padding: 8 },
  repriseCard: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    margin: 12, padding: 12, borderRadius: 10, borderWidth: 1,
  },
  repriseOk: { backgroundColor: '#f0fdf4', borderColor: '#bbf7d0' },
  repriseAttente: { backgroundColor: '#fff7ed', borderColor: '#fed7aa' },
  repriseLabel: { fontSize: 12, fontWeight: '600', color: '#374151' },
  repriseResume: { fontSize: 11, color: '#64748b', marginTop: 2 },
  emptyState: { alignItems: 'center', paddingTop: 60 },
  emptyTitle: { fontSize: 17, fontWeight: 'bold', color: '#374151', marginTop: 16 },
  emptyDesc: { fontSize: 13, color: '#94a3b8', textAlign: 'center', maxWidth: 240, marginTop: 8 },
  card: {
    backgroundColor: '#fff', borderRadius: 14, padding: 14,
    borderWidth: 1.5, borderColor: '#fed7aa', shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.05, shadowRadius: 8, elevation: 3,
  },
  cardHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  urgenceBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 20 },
  urgenceText: { fontSize: 10, fontWeight: '700' },
  cardType: { fontSize: 12, fontWeight: '600', color: '#374151' },
  repriseBadge: { flexDirection: 'row', alignItems: 'center', gap: 4, marginLeft: 'auto' as any, backgroundColor: '#eef2ff', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 10 },
  repriseTag: { fontSize: 9, color: '#4f46e5', fontWeight: '600' },
  cardDesc: { fontSize: 13, color: '#374151', lineHeight: 18, marginBottom: 10 },
  cardFooter: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  cardMontant: { fontSize: 15, fontWeight: 'bold', color: '#1e293b' },
  cardActions: { flexDirection: 'row', gap: 8 },
  btnRejet: {
    width: 36, height: 36, borderRadius: 10, backgroundColor: '#fef2f2',
    alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#fecaca',
  },
  btnApprouver: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: '#16a34a', paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10,
  },
  btnApprouverText: { color: '#fff', fontSize: 13, fontWeight: '600' },
  modal: { flex: 1, backgroundColor: '#fff' },
  modalHeader: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    padding: 16, paddingTop: Platform.OS === 'ios' ? 20 : 16, borderBottomWidth: 1, borderBottomColor: '#e2e8f0',
  },
  modalTitle: { fontSize: 17, fontWeight: 'bold', color: '#1e293b' },
  modalContent: { flex: 1, padding: 16 },
  modalDesc: { fontSize: 15, color: '#374151', lineHeight: 22, marginBottom: 8 },
  modalMontant: { fontSize: 24, fontWeight: 'bold', color: '#1e293b', marginBottom: 16 },
  modalDetails: { backgroundColor: '#f8fafc', borderRadius: 10, padding: 12, marginBottom: 16 },
  modalDetailsTitle: { fontSize: 11, fontWeight: '700', color: '#94a3b8', marginBottom: 6, textTransform: 'uppercase' },
  modalDetailsText: { fontSize: 11, color: '#64748b', fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
  sectionLabel: { fontSize: 12, fontWeight: '600', color: '#64748b', marginBottom: 6, marginTop: 8 },
  modalInput: {
    backgroundColor: '#f8fafc', borderRadius: 10, padding: 12, fontSize: 14, color: '#1e293b',
    borderWidth: 1, borderColor: '#e2e8f0', minHeight: 60, textAlignVertical: 'top',
  },
  modalActions: {
    flexDirection: 'row', gap: 10, padding: 16,
    paddingBottom: Platform.OS === 'ios' ? 30 : 16, borderTopWidth: 1, borderTopColor: '#e2e8f0',
  },
  modalBtnRejet: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    borderWidth: 1.5, borderColor: '#ef4444', borderRadius: 12, paddingVertical: 12,
  },
  modalBtnRejetText: { color: '#ef4444', fontWeight: '700', fontSize: 15 },
  modalBtnApprouver: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    backgroundColor: '#16a34a', borderRadius: 12, paddingVertical: 12,
  },
  modalBtnApprouverText: { color: '#fff', fontWeight: '700', fontSize: 15 },
  btnDisabled: { opacity: 0.5 },
})
