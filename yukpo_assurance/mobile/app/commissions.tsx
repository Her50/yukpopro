import { useState } from 'react'
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  Dimensions,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { useRouter } from 'expo-router'

const SCREEN_WIDTH = Dimensions.get('window').width

// ─── Types ─────────────────────────────────────────────────────────────────────

type TypeIntermediaire = 'courtier' | 'agent' | 'apporteur'
type StatutCommission = 'due' | 'payee' | 'en_litige'

interface Commission {
  id: string
  intermediaire: string
  type: TypeIntermediaire
  periode: string
  branche: string
  primes: number
  taux: number
  montant: number
  statut: StatutCommission
}

// ─── Données démo ─────────────────────────────────────────────────────────────

const DEMO: Commission[] = [
  { id: '1', intermediaire: 'Cabinet Assur-Plus', type: 'courtier', periode: 'Mars 2026', branche: 'Auto', primes: 14_200_000, taux: 12, montant: 1_704_000, statut: 'due' },
  { id: '2', intermediaire: 'Transcam SARL', type: 'courtier', periode: 'Mars 2026', branche: 'MRH', primes: 8_500_000, taux: 10, montant: 850_000, statut: 'payee' },
  { id: '3', intermediaire: 'YK Courtage', type: 'courtier', periode: 'Fév 2026', branche: 'Vie', primes: 22_000_000, taux: 8, montant: 1_760_000, statut: 'en_litige' },
  { id: '4', intermediaire: 'Agent Gén. Mballa', type: 'agent', periode: 'Mars 2026', branche: 'Auto', primes: 6_400_000, taux: 10, montant: 640_000, statut: 'due' },
  { id: '5', intermediaire: 'Agent Gén. Mballa', type: 'agent', periode: 'Fév 2026', branche: 'MRH', primes: 3_200_000, taux: 10, montant: 320_000, statut: 'payee' },
  { id: '6', intermediaire: 'Apporteur Kouassi', type: 'apporteur', periode: 'Mars 2026', branche: 'Santé', primes: 4_800_000, taux: 6, montant: 288_000, statut: 'due' },
  { id: '7', intermediaire: 'Apporteur Fouda', type: 'apporteur', periode: 'Mars 2026', branche: 'RC', primes: 2_100_000, taux: 8, montant: 168_000, statut: 'payee' },
  { id: '8', intermediaire: 'Cabinet Assur-Plus', type: 'courtier', periode: 'Mars 2026', branche: 'Santé', primes: 5_900_000, taux: 10, montant: 590_000, statut: 'due' },
]

// ─── Utilitaires ──────────────────────────────────────────────────────────────

function fmt(v: number) {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`
  return `${v}`
}

const TYPE_CFG: Record<TypeIntermediaire, { label: string; icon: string; color: string }> = {
  courtier: { label: 'Courtier', icon: 'business-outline', color: '#3b82f6' },
  agent: { label: 'Agent', icon: 'person-outline', color: '#8b5cf6' },
  apporteur: { label: 'Apporteur', icon: 'people-outline', color: '#0ea5e9' },
}

const STATUT_CFG: Record<StatutCommission, { label: string; icon: string; color: string; bg: string }> = {
  due: { label: 'Due', icon: 'time-outline', color: '#92400e', bg: '#fef3c7' },
  payee: { label: 'Payée', icon: 'checkmark-circle-outline', color: '#166534', bg: '#dcfce7' },
  en_litige: { label: 'En litige', icon: 'warning-outline', color: '#dc2626', bg: '#fee2e2' },
}

// ─── Écran ────────────────────────────────────────────────────────────────────

export default function CommissionsScreen() {
  const router = useRouter()
  const [commissions, setCommissions] = useState<Commission[]>(DEMO)
  const [filtreType, setFiltreType] = useState<TypeIntermediaire | 'tous'>('tous')
  const [filtreStatut, setFiltreStatut] = useState<StatutCommission | 'tous'>('tous')

  let liste = commissions
  if (filtreType !== 'tous') liste = liste.filter(c => c.type === filtreType)
  if (filtreStatut !== 'tous') liste = liste.filter(c => c.statut === filtreStatut)

  const totalDue = commissions.filter(c => c.statut === 'due').reduce((s, c) => s + c.montant, 0)
  const totalPayee = commissions.filter(c => c.statut === 'payee').reduce((s, c) => s + c.montant, 0)
  const totalLitige = commissions.filter(c => c.statut === 'en_litige').reduce((s, c) => s + c.montant, 0)

  const payer = (id: string) =>
    setCommissions(prev => prev.map(c => c.id === id ? { ...c, statut: 'payee' as const } : c))

  const approuver = (id: string) =>
    setCommissions(prev => prev.map(c => c.id === id ? { ...c, statut: 'due' as const } : c))

  return (
    <ScrollView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color="#1e293b" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>Module Commissions</Text>
          <Text style={styles.subtitle}>Courtiers · Agents · Apporteurs</Text>
        </View>
        <TouchableOpacity style={styles.exportBtn}>
          <Ionicons name="download-outline" size={20} color="#1d4ed8" />
        </TouchableOpacity>
      </View>

      {/* KPI résumé */}
      <View style={styles.kpiRow}>
        <View style={[styles.kpiCard, { borderColor: '#fde68a', backgroundColor: '#fffbeb' }]}>
          <Ionicons name="time-outline" size={16} color="#92400e" />
          <Text style={[styles.kpiValue, { color: '#92400e' }]}>{fmt(totalDue)} XAF</Text>
          <Text style={styles.kpiLabel}>Dues</Text>
        </View>
        <View style={[styles.kpiCard, { borderColor: '#bbf7d0', backgroundColor: '#f0fdf4' }]}>
          <Ionicons name="checkmark-circle-outline" size={16} color="#166534" />
          <Text style={[styles.kpiValue, { color: '#166534' }]}>{fmt(totalPayee)} XAF</Text>
          <Text style={styles.kpiLabel}>Payées</Text>
        </View>
        <View style={[styles.kpiCard, { borderColor: '#fecaca', backgroundColor: '#fef2f2' }]}>
          <Ionicons name="warning-outline" size={16} color="#dc2626" />
          <Text style={[styles.kpiValue, { color: '#dc2626' }]}>{fmt(totalLitige)} XAF</Text>
          <Text style={styles.kpiLabel}>Litiges</Text>
        </View>
      </View>

      {/* Filtres type */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.filtresScroll}>
        <View style={styles.filtres}>
          {(['tous', 'courtier', 'agent', 'apporteur'] as const).map(t => (
            <TouchableOpacity
              key={t}
              style={[styles.filtreBadge, filtreType === t && styles.filtreBadgeActive]}
              onPress={() => setFiltreType(t)}
            >
              <Text style={[styles.filtreBadgeText, filtreType === t && styles.filtreBadgeTextActive]}>
                {t === 'tous' ? 'Tous' : TYPE_CFG[t].label}
              </Text>
            </TouchableOpacity>
          ))}
          <View style={styles.filtresDivider} />
          {(['tous', 'due', 'payee', 'en_litige'] as const).map(s => (
            <TouchableOpacity
              key={s}
              style={[styles.filtreBadge, filtreStatut === s && styles.filtreBadgeActive]}
              onPress={() => setFiltreStatut(s)}
            >
              <Text style={[styles.filtreBadgeText, filtreStatut === s && styles.filtreBadgeTextActive]}>
                {s === 'tous' ? 'Tous statuts' : STATUT_CFG[s].label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </ScrollView>

      {/* Liste commissions */}
      <View style={styles.liste}>
        {liste.map(c => {
          const tcfg = TYPE_CFG[c.type]
          const scfg = STATUT_CFG[c.statut]
          return (
            <View key={c.id} style={styles.commCard}>
              <View style={styles.commHeader}>
                <View style={[styles.commTypeIcon, { backgroundColor: tcfg.color + '20' }]}>
                  <Ionicons name={tcfg.icon as never} size={16} color={tcfg.color} />
                </View>
                <View style={{ flex: 1, marginLeft: 10 }}>
                  <Text style={styles.commNom}>{c.intermediaire}</Text>
                  <Text style={styles.commMeta}>{tcfg.label} · {c.branche} · {c.periode}</Text>
                </View>
                <View style={[styles.commStatut, { backgroundColor: scfg.bg }]}>
                  <Ionicons name={scfg.icon as never} size={11} color={scfg.color} />
                  <Text style={[styles.commStatutText, { color: scfg.color }]}>{scfg.label}</Text>
                </View>
              </View>

              <View style={styles.commDetails}>
                <View style={styles.commDetailItem}>
                  <Text style={styles.commDetailLabel}>Primes</Text>
                  <Text style={styles.commDetailValue}>{fmt(c.primes)} XAF</Text>
                </View>
                <View style={styles.commDetailItem}>
                  <Text style={styles.commDetailLabel}>Taux</Text>
                  <Text style={styles.commDetailValue}>{c.taux}%</Text>
                </View>
                <View style={styles.commDetailItem}>
                  <Text style={styles.commDetailLabel}>Commission</Text>
                  <Text style={[styles.commDetailValue, styles.commMontant]}>{fmt(c.montant)} XAF</Text>
                </View>
              </View>

              {c.statut === 'due' && (
                <TouchableOpacity style={styles.payerBtn} onPress={() => payer(c.id)}>
                  <Ionicons name="cash-outline" size={14} color="#fff" />
                  <Text style={styles.payerBtnText}>Payer</Text>
                </TouchableOpacity>
              )}
              {c.statut === 'en_litige' && (
                <TouchableOpacity style={styles.approuverBtn} onPress={() => approuver(c.id)}>
                  <Ionicons name="checkmark-outline" size={14} color="#1d4ed8" />
                  <Text style={styles.approuverBtnText}>Approuver</Text>
                </TouchableOpacity>
              )}
            </View>
          )
        })}

        {liste.length === 0 && (
          <View style={styles.emptyState}>
            <Ionicons name="cash-outline" size={40} color="#cbd5e1" />
            <Text style={styles.emptyText}>Aucune commission pour ces filtres</Text>
          </View>
        )}
      </View>
    </ScrollView>
  )
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f1f5f9' },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#fff', padding: 16, borderBottomWidth: 1, borderBottomColor: '#e2e8f0' },
  backBtn: { width: 36, height: 36, borderRadius: 8, backgroundColor: '#f1f5f9', alignItems: 'center', justifyContent: 'center' },
  title: { fontSize: 17, fontWeight: 'bold', color: '#1e293b' },
  subtitle: { fontSize: 12, color: '#64748b', marginTop: 2 },
  exportBtn: { width: 36, height: 36, borderRadius: 8, backgroundColor: '#eff6ff', alignItems: 'center', justifyContent: 'center' },
  kpiRow: { flexDirection: 'row', padding: 12, gap: 10 },
  kpiCard: { flex: 1, borderWidth: 1, borderRadius: 10, padding: 12, alignItems: 'center', gap: 4 },
  kpiValue: { fontSize: 13, fontWeight: 'bold' },
  kpiLabel: { fontSize: 10, color: '#64748b' },
  filtresScroll: { paddingLeft: 12, marginBottom: 0 },
  filtres: { flexDirection: 'row', gap: 6, paddingRight: 12, alignItems: 'center' },
  filtreBadge: { paddingHorizontal: 12, paddingVertical: 5, borderRadius: 20, borderWidth: 1, borderColor: '#d1d5db', backgroundColor: '#f8fafc' },
  filtreBadgeActive: { backgroundColor: '#1d4ed8', borderColor: '#1d4ed8' },
  filtreBadgeText: { fontSize: 11, color: '#64748b', fontWeight: '500' },
  filtreBadgeTextActive: { color: '#fff', fontWeight: '700' },
  filtresDivider: { width: 1, height: 20, backgroundColor: '#e2e8f0', marginHorizontal: 2 },
  liste: { padding: 12, gap: 10 },
  commCard: { backgroundColor: '#fff', borderRadius: 12, padding: 14, shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.06, elevation: 2 },
  commHeader: { flexDirection: 'row', alignItems: 'flex-start' },
  commTypeIcon: { width: 36, height: 36, borderRadius: 8, alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  commNom: { fontSize: 13, fontWeight: '700', color: '#1e293b' },
  commMeta: { fontSize: 11, color: '#64748b', marginTop: 2 },
  commStatut: { flexDirection: 'row', alignItems: 'center', gap: 3, paddingHorizontal: 7, paddingVertical: 3, borderRadius: 10 },
  commStatutText: { fontSize: 10, fontWeight: '600' },
  commDetails: { flexDirection: 'row', marginTop: 12, borderTopWidth: 1, borderTopColor: '#f1f5f9', paddingTop: 10 },
  commDetailItem: { flex: 1, alignItems: 'center' },
  commDetailLabel: { fontSize: 10, color: '#94a3b8' },
  commDetailValue: { fontSize: 12, color: '#1e293b', fontWeight: '600', marginTop: 2 },
  commMontant: { color: '#1d4ed8', fontSize: 13 },
  payerBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: '#16a34a', paddingVertical: 9, borderRadius: 8, marginTop: 10 },
  payerBtnText: { fontSize: 13, color: '#fff', fontWeight: '700' },
  approuverBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, borderWidth: 1, borderColor: '#bfdbfe', paddingVertical: 9, borderRadius: 8, marginTop: 10 },
  approuverBtnText: { fontSize: 13, color: '#1d4ed8', fontWeight: '700' },
  emptyState: { alignItems: 'center', paddingVertical: 48, gap: 10 },
  emptyText: { fontSize: 13, color: '#94a3b8' },
})
