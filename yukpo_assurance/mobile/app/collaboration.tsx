import { useState, useEffect, useRef } from 'react'
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  TextInput, ActivityIndicator,
} from 'react-native'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

const API_BASE = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000/api/v1'
const WS_BASE = API_BASE.replace(/^http/, 'ws')

async function apiFetch(path: string, opts: RequestInit = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...opts,
    headers: { 'Content-Type': 'application/json', ...(opts.headers ?? {}) },
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

type Tab = 'documents' | 'notifs'

const STATUT_COLORS: Record<string, { bg: string; text: string }> = {
  brouillon:  { bg: '#f3f4f6', text: '#374151' },
  en_review:  { bg: '#fef9c3', text: '#713f12' },
  approuve:   { bg: '#dcfce7', text: '#166534' },
  rejete:     { bg: '#fee2e2', text: '#991b1b' },
  archive:    { bg: '#f3f4f6', text: '#9ca3af' },
}

export default function CollaborationScreen() {
  const [tab, setTab] = useState<Tab>('documents')
  const qc = useQueryClient()
  const wsRef = useRef<WebSocket | null>(null)

  // WebSocket pour notifications temps réel
  useEffect(() => {
    try {
      const ws = new WebSocket(`${WS_BASE}/collaboration/ws/1/1`)
      ws.onmessage = () => {
        qc.invalidateQueries({ queryKey: ['m-notifs'] })
        qc.invalidateQueries({ queryKey: ['m-docs-collab'] })
      }
      wsRef.current = ws
      return () => ws.close()
    } catch { /* WebSocket non disponible */ }
  }, [])

  return (
    <View style={styles.container}>
      <View style={styles.tabBar}>
        {([
          { id: 'documents', label: '📄 Documents' },
          { id: 'notifs', label: '🔔 Notifications' },
        ] as { id: Tab; label: string }[]).map(t => (
          <TouchableOpacity
            key={t.id}
            style={[styles.tabBtn, tab === t.id && styles.tabBtnActive]}
            onPress={() => setTab(t.id)}
          >
            <Text style={[styles.tabLabel, tab === t.id && styles.tabLabelActive]}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>
      {tab === 'documents' && <TabDocuments qc={qc} />}
      {tab === 'notifs' && <TabNotifications qc={qc} />}
    </View>
  )
}

function TabDocuments({ qc }: { qc: any }) {
  const [selected, setSelected] = useState<number | null>(null)
  const [filterStatut, setFilterStatut] = useState('')
  const { data, isLoading } = useQuery({
    queryKey: ['m-docs-collab', filterStatut],
    queryFn: () => apiFetch(`/collaboration/documents?limit=20${filterStatut ? '&statut=' + filterStatut : ''}`),
  })
  const docs: any[] = data?.documents ?? []

  if (selected !== null) {
    return <DocDetail docId={selected} onBack={() => setSelected(null)} qc={qc} />
  }

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent}>
      {/* Filtre statut */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 8 }}>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {['', 'brouillon', 'en_review', 'approuve', 'rejete'].map(s => (
            <TouchableOpacity
              key={s}
              style={[styles.filterChip, filterStatut === s && styles.filterChipActive]}
              onPress={() => setFilterStatut(s)}
            >
              <Text style={[styles.filterText, filterStatut === s && styles.filterTextActive]}>
                {s || 'Tous'}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </ScrollView>

      {isLoading ? (
        <ActivityIndicator color="#1e3a8a" style={{ marginTop: 20 }} />
      ) : docs.map((d: any) => (
        <TouchableOpacity key={d.id} style={styles.docCard} onPress={() => setSelected(d.id)}>
          <View style={styles.docIcon}>
            <Text style={{ fontSize: 22 }}>📄</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.docTitle} numberOfLines={1}>{d.titre}</Text>
            <Text style={styles.docSub}>{d.reference} · {d.type_document?.replace(/_/g, ' ')}</Text>
            <Text style={styles.docSub}>v{d.version_courante} · {d.auteur_nom}</Text>
          </View>
          {d.statut && STATUT_COLORS[d.statut] && (
            <View style={[styles.badge, { backgroundColor: STATUT_COLORS[d.statut].bg }]}>
              <Text style={[styles.badgeText, { color: STATUT_COLORS[d.statut].text }]}>{d.statut}</Text>
            </View>
          )}
        </TouchableOpacity>
      ))}
      {!isLoading && docs.length === 0 && (
        <Text style={styles.empty}>Aucun document</Text>
      )}
    </ScrollView>
  )
}

function DocDetail({ docId, onBack, qc }: { docId: number; onBack: () => void; qc: any }) {
  const { data, isLoading } = useQuery({
    queryKey: ['m-doc-detail', docId],
    queryFn: () => apiFetch(`/collaboration/documents/${docId}`),
  })
  const [commentaire, setCommentaire] = useState('')
  const approuverMut = useMutation({
    mutationFn: ({ decision }: { decision: string }) =>
      apiFetch(`/collaboration/documents/${docId}/approuver`, {
        method: 'POST', body: JSON.stringify({ decision, commentaire: '' }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['m-doc-detail', docId] })
      qc.invalidateQueries({ queryKey: ['m-docs-collab'] })
    },
  })
  const commenterMut = useMutation({
    mutationFn: (contenu: string) =>
      apiFetch(`/collaboration/documents/${docId}/commentaires`, {
        method: 'POST', body: JSON.stringify({ contenu }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['m-doc-detail', docId] })
      setCommentaire('')
    },
  })

  if (isLoading) return <ActivityIndicator style={{ marginTop: 40 }} color="#1e3a8a" />
  if (!data) return null
  const doc = data
  const etapeCourante = doc.etapes_workflow?.find((e: any) => e.statut === 'en_attente')

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent}>
      <TouchableOpacity onPress={onBack} style={styles.backBtn}>
        <Text style={styles.backBtnText}>← Retour</Text>
      </TouchableOpacity>

      <View style={styles.detailCard}>
        <Text style={styles.detailTitle}>{doc.titre}</Text>
        <Text style={styles.docSub}>{doc.reference} · {doc.type_document?.replace(/_/g, ' ')}</Text>
        {doc.statut && STATUT_COLORS[doc.statut] && (
          <View style={[styles.badge, { backgroundColor: STATUT_COLORS[doc.statut].bg, marginTop: 8 }]}>
            <Text style={[styles.badgeText, { color: STATUT_COLORS[doc.statut].text }]}>{doc.statut}</Text>
          </View>
        )}
        {doc.description && <Text style={[styles.docSub, { marginTop: 8 }]}>{doc.description}</Text>}
      </View>

      {/* Workflow */}
      {doc.etapes_workflow?.length > 0 && (
        <View style={styles.detailCard}>
          <Text style={styles.sectionTitle}>Workflow d'approbation</Text>
          {doc.etapes_workflow.map((e: any, i: number) => (
            <View key={i} style={styles.etapeRow}>
              <View style={[styles.etapeNum, {
                backgroundColor: e.statut === 'approuve' ? '#16a34a' : e.statut === 'rejete' ? '#dc2626' : e.statut === 'en_attente' ? '#d97706' : '#d1d5db',
              }]}>
                <Text style={styles.etapeNumText}>{e.etape}</Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.etapeNom}>{e.approbateur_nom}</Text>
                <Text style={styles.etapeRole}>{e.approbateur_role}</Text>
              </View>
              <Text style={styles.etapeStatut}>{e.statut}</Text>
            </View>
          ))}
          {etapeCourante && (
            <View style={styles.approvalBtns}>
              <TouchableOpacity
                style={[styles.approvalBtn, { backgroundColor: '#16a34a' }]}
                onPress={() => approuverMut.mutate({ decision: 'approuve' })}
                disabled={approuverMut.isPending}
              >
                <Text style={styles.approvalBtnText}>✓ Approuver</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.approvalBtn, { backgroundColor: '#dc2626' }]}
                onPress={() => approuverMut.mutate({ decision: 'rejete' })}
                disabled={approuverMut.isPending}
              >
                <Text style={styles.approvalBtnText}>✕ Rejeter</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>
      )}

      {/* Commentaires */}
      <View style={styles.detailCard}>
        <Text style={styles.sectionTitle}>Commentaires ({doc.commentaires?.length ?? 0})</Text>
        {(doc.commentaires ?? []).map((c: any) => (
          <View key={c.id} style={styles.commentItem}>
            <Text style={styles.commentAuteur}>{c.auteur_nom}</Text>
            <Text style={styles.commentTexte}>{c.contenu}</Text>
          </View>
        ))}
        <View style={styles.commentInput}>
          <TextInput
            style={styles.commentTextInput}
            placeholder="Ajouter un commentaire…"
            value={commentaire}
            onChangeText={setCommentaire}
            multiline
          />
          <TouchableOpacity
            style={[styles.sendBtn, !commentaire.trim() && { opacity: 0.4 }]}
            onPress={() => commentaire.trim() && commenterMut.mutate(commentaire)}
            disabled={!commentaire.trim() || commenterMut.isPending}
          >
            <Text style={styles.sendBtnText}>Envoyer</Text>
          </TouchableOpacity>
        </View>
      </View>
    </ScrollView>
  )
}

function TabNotifications({ qc }: { qc: any }) {
  const { data, isLoading } = useQuery({
    queryKey: ['m-notifs'],
    queryFn: () => apiFetch('/collaboration/notifications?limit=20'),
  })
  const marquerMut = useMutation({
    mutationFn: (id: number) => apiFetch(`/collaboration/notifications/${id}/lue`, { method: 'PATCH' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['m-notifs'] }),
  })
  const notifs: any[] = data?.notifications ?? []

  if (isLoading) return <ActivityIndicator style={{ marginTop: 40 }} color="#1e3a8a" />

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent}>
      {notifs.map((n: any) => (
        <TouchableOpacity
          key={n.id}
          style={[styles.notifCard, n.lu && styles.notifCardLue]}
          onPress={() => !n.lu && marquerMut.mutate(n.id)}
        >
          <View style={[styles.notifDot, { backgroundColor: n.lu ? '#d1d5db' : '#2563eb' }]} />
          <View style={{ flex: 1 }}>
            <Text style={[styles.notifTitre, n.lu && { fontWeight: '400', color: '#6b7280' }]}>{n.titre}</Text>
            {n.message && <Text style={styles.notifMsg} numberOfLines={2}>{n.message}</Text>}
            <Text style={styles.notifDate}>{new Date(n.cree_le).toLocaleString('fr-FR')}</Text>
          </View>
        </TouchableOpacity>
      ))}
      {notifs.length === 0 && <Text style={styles.empty}>Aucune notification</Text>}
    </ScrollView>
  )
}

const styles = StyleSheet.create({
  container:          { flex: 1, backgroundColor: '#f9fafb' },
  tabBar:             { flexDirection: 'row', backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#e5e7eb' },
  tabBtn:             { flex: 1, paddingVertical: 12, alignItems: 'center' },
  tabBtnActive:       { borderBottomWidth: 2, borderBottomColor: '#1e3a8a' },
  tabLabel:           { fontSize: 14, color: '#6b7280', fontWeight: '500' },
  tabLabelActive:     { color: '#1e3a8a', fontWeight: '700' },
  scroll:             { flex: 1 },
  scrollContent:      { padding: 16, gap: 10, paddingBottom: 32 },
  filterChip:         { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 20, backgroundColor: '#f3f4f6', borderWidth: 1, borderColor: '#e5e7eb' },
  filterChipActive:   { backgroundColor: '#dbeafe', borderColor: '#93c5fd' },
  filterText:         { fontSize: 12, color: '#6b7280' },
  filterTextActive:   { color: '#1d4ed8', fontWeight: '600' },
  docCard:            { flexDirection: 'row', alignItems: 'center', backgroundColor: '#fff', borderRadius: 12, padding: 14, gap: 12, shadowColor: '#000', shadowOpacity: 0.04, shadowRadius: 4, elevation: 1 },
  docIcon:            { width: 44, height: 44, borderRadius: 12, backgroundColor: '#eff6ff', alignItems: 'center', justifyContent: 'center' },
  docTitle:           { fontSize: 14, fontWeight: '600', color: '#111827' },
  docSub:             { fontSize: 11, color: '#9ca3af', marginTop: 1 },
  badge:              { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 20 },
  badgeText:          { fontSize: 11, fontWeight: '600' },
  empty:              { textAlign: 'center', marginTop: 40, color: '#9ca3af', fontSize: 14 },
  backBtn:            { marginBottom: 8 },
  backBtnText:        { color: '#2563eb', fontSize: 14 },
  detailCard:         { backgroundColor: '#fff', borderRadius: 12, padding: 16, shadowColor: '#000', shadowOpacity: 0.05, shadowRadius: 4, elevation: 1 },
  detailTitle:        { fontSize: 18, fontWeight: '700', color: '#111827' },
  sectionTitle:       { fontSize: 14, fontWeight: '700', color: '#111827', marginBottom: 10 },
  etapeRow:           { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 },
  etapeNum:           { width: 26, height: 26, borderRadius: 13, alignItems: 'center', justifyContent: 'center' },
  etapeNumText:       { color: '#fff', fontSize: 12, fontWeight: '700' },
  etapeNom:           { fontSize: 13, fontWeight: '600', color: '#111827' },
  etapeRole:          { fontSize: 11, color: '#6b7280' },
  etapeStatut:        { fontSize: 11, color: '#6b7280' },
  approvalBtns:       { flexDirection: 'row', gap: 10, marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: '#f3f4f6' },
  approvalBtn:        { flex: 1, paddingVertical: 10, borderRadius: 10, alignItems: 'center' },
  approvalBtnText:    { color: '#fff', fontWeight: '700', fontSize: 14 },
  commentItem:        { backgroundColor: '#f9fafb', borderRadius: 8, padding: 10, marginBottom: 6 },
  commentAuteur:      { fontSize: 11, fontWeight: '700', color: '#1e3a8a', marginBottom: 2 },
  commentTexte:       { fontSize: 13, color: '#374151' },
  commentInput:       { flexDirection: 'row', gap: 8, marginTop: 8, alignItems: 'flex-end' },
  commentTextInput:   { flex: 1, backgroundColor: '#f3f4f6', borderRadius: 10, padding: 10, fontSize: 13, maxHeight: 80 },
  sendBtn:            { backgroundColor: '#1e3a8a', borderRadius: 10, paddingHorizontal: 14, paddingVertical: 10 },
  sendBtnText:        { color: '#fff', fontWeight: '600', fontSize: 13 },
  notifCard:          { flexDirection: 'row', alignItems: 'flex-start', gap: 12, backgroundColor: '#eff6ff', borderRadius: 12, padding: 14, borderWidth: 1, borderColor: '#bfdbfe' },
  notifCardLue:       { backgroundColor: '#fff', borderColor: '#e5e7eb' },
  notifDot:           { width: 8, height: 8, borderRadius: 4, marginTop: 4 },
  notifTitre:         { fontSize: 14, fontWeight: '700', color: '#111827' },
  notifMsg:           { fontSize: 12, color: '#6b7280', marginTop: 2 },
  notifDate:          { fontSize: 11, color: '#9ca3af', marginTop: 4 },
})
