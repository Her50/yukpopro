import { useState, useEffect } from 'react'
import {
  View, Text, ScrollView, TouchableOpacity,
  StyleSheet, ActivityIndicator, Alert, Share,
} from 'react-native'
import { documentsAPI } from '../../src/api/client'

interface Document {
  fichier_id: string; type: string; type_label: string; icone: string;
  extension: string; taille_ko: number; date_creation: number; nom_affiche: string
}

function dateLocale(ts: number) {
  return new Date(ts * 1000).toLocaleDateString('fr-FR', {
    day: '2-digit', month: 'short', year: 'numeric',
  })
}

const EXT_COLORS: Record<string, { bg: string; text: string }> = {
  PDF: { bg: '#fee2e2', text: '#b91c1c' },
  DOCX: { bg: '#dbeafe', text: '#1d4ed8' },
  PNG: { bg: '#dcfce7', text: '#15803d' },
  JPG: { bg: '#dcfce7', text: '#15803d' },
}

export default function DocumentsScreen() {
  const [docs, setDocs] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const charger = async (silently = false) => {
    if (!silently) setLoading(true)
    else setRefreshing(true)
    try {
      const r = await documentsAPI.lister()
      setDocs(r.data.documents)
    } catch {
      Alert.alert('Erreur', 'Impossible de charger vos documents')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => { charger() }, [])

  const supprimer = (doc: Document) => {
    Alert.alert(
      'Supprimer',
      `Supprimer "${doc.nom_affiche}" ?`,
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Supprimer', style: 'destructive',
          onPress: async () => {
            try {
              await documentsAPI.supprimer(doc.fichier_id)
              setDocs(prev => prev.filter(d => d.fichier_id !== doc.fichier_id))
            } catch {
              Alert.alert('Erreur', 'Suppression impossible')
            }
          },
        },
      ],
    )
  }

  const partager = async (doc: Document) => {
    const url = documentsAPI.urlTelechargement(doc.fichier_id)
    try {
      await Share.share({ message: `Document : ${doc.nom_affiche}\nTélécharger : ${url}` })
    } catch {
      Alert.alert('Info', `Lien : ${url}`)
    }
  }

  return (
    <ScrollView style={s.container}>
      <View style={s.header}>
        <Text style={s.title}>📂 Mes Documents</Text>
        <Text style={s.subtitle}>{docs.length} document{docs.length !== 1 ? 's' : ''} généré{docs.length !== 1 ? 's' : ''}</Text>
      </View>

      <View style={s.refreshRow}>
        <TouchableOpacity onPress={() => charger(true)} style={s.refreshBtn} disabled={refreshing}>
          {refreshing
            ? <ActivityIndicator size="small" color="#ea580c" />
            : <Text style={s.refreshText}>🔄 Actualiser</Text>
          }
        </TouchableOpacity>
      </View>

      {loading ? (
        <View style={{ padding: 40, alignItems: 'center' }}>
          <ActivityIndicator size="large" color="#ea580c" />
          <Text style={{ color: '#9ca3af', marginTop: 12 }}>Chargement…</Text>
        </View>
      ) : docs.length === 0 ? (
        <View style={s.empty}>
          <Text style={{ fontSize: 40, marginBottom: 12 }}>📭</Text>
          <Text style={{ color: '#6b7280', fontWeight: '600' }}>Aucun document</Text>
          <Text style={{ color: '#9ca3af', fontSize: 12, marginTop: 4, textAlign: 'center' }}>
            Les documents générés apparaîtront ici automatiquement
          </Text>
        </View>
      ) : (
        <View style={s.list}>
          {docs.map(doc => {
            const extStyle = EXT_COLORS[doc.extension] || { bg: '#f3f4f6', text: '#374151' }
            return (
              <View key={doc.fichier_id} style={s.docItem}>
                <Text style={{ fontSize: 24 }}>{doc.icone}</Text>
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Text style={s.docNom} numberOfLines={1}>{doc.nom_affiche}</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 3 }}>
                    <View style={[s.extBadge, { backgroundColor: extStyle.bg }]}>
                      <Text style={[s.extText, { color: extStyle.text }]}>{doc.extension}</Text>
                    </View>
                    <Text style={s.docMeta}>{doc.taille_ko} Ko · {dateLocale(doc.date_creation)}</Text>
                  </View>
                </View>
                <View style={{ flexDirection: 'row', gap: 4 }}>
                  <TouchableOpacity onPress={() => partager(doc)} style={s.actionBtn}>
                    <Text>📤</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => supprimer(doc)} style={[s.actionBtn, { backgroundColor: '#fee2e2' }]}>
                    <Text>🗑️</Text>
                  </TouchableOpacity>
                </View>
              </View>
            )
          })}
        </View>
      )}
    </ScrollView>
  )
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f9fafb' },
  header: { backgroundColor: '#ea580c', paddingTop: 56, paddingBottom: 20, paddingHorizontal: 20 },
  title: { fontSize: 22, fontWeight: '700', color: '#fff' },
  subtitle: { fontSize: 13, color: '#fed7aa', marginTop: 4 },
  refreshRow: { flexDirection: 'row', justifyContent: 'flex-end', paddingHorizontal: 16, paddingTop: 12 },
  refreshBtn: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 12, backgroundColor: '#fff', borderWidth: 1, borderColor: '#e5e7eb' },
  refreshText: { fontSize: 12, color: '#ea580c', fontWeight: '600' },
  empty: { alignItems: 'center', padding: 48 },
  list: { padding: 16, gap: 8 },
  docItem: { backgroundColor: '#fff', borderRadius: 16, padding: 14, flexDirection: 'row', alignItems: 'center', shadowColor: '#000', shadowOpacity: 0.04, shadowRadius: 6, elevation: 2 },
  docNom: { fontSize: 13, fontWeight: '600', color: '#111827' },
  docMeta: { fontSize: 11, color: '#9ca3af' },
  extBadge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 },
  extText: { fontSize: 10, fontWeight: '700' },
  actionBtn: { width: 34, height: 34, borderRadius: 10, backgroundColor: '#f3f4f6', alignItems: 'center', justifyContent: 'center' },
})
