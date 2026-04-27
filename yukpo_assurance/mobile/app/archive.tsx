/**
 * Archive numérique mobile — Accès transversal à tous les documents scannés
 * Accessible depuis le dashboard et tous les modules.
 */
import { useState } from 'react'
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  TextInput, ActivityIndicator, Dimensions, Modal,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { useRouter } from 'expo-router'
import * as ImagePicker from 'expo-image-picker'

const SCREEN_W = Dimensions.get('window').width

// ─── Types ────────────────────────────────────────────────────────────────────

type ModuleDoc = 'sinistres' | 'souscription' | 'comptabilite' | 'rh' | 'reassurance' | 'commercial' | 'fournisseurs'
type StatutOcr = 'non_traite' | 'en_cours' | 'extrait' | 'importe_orass'

interface DocArchive {
  id: string
  nom: string
  type_document: string
  module: ModuleDoc
  reference: string
  date_upload: string
  taille_ko: number
  uploade_par: string
  tags: string[]
  statut_ocr: StatutOcr
  confiance_ocr?: number
}

// ─── Config ───────────────────────────────────────────────────────────────────

const MODULES_CFG: Record<ModuleDoc | 'tous', { label: string; icon: string; couleur: string }> = {
  tous:          { label: 'Tous',          icon: 'folder-outline',       couleur: '#64748b' },
  sinistres:     { label: 'Sinistres',     icon: 'shield-outline',       couleur: '#ef4444' },
  souscription:  { label: 'Souscription',  icon: 'document-text-outline',couleur: '#3b82f6' },
  comptabilite:  { label: 'Comptabilité',  icon: 'cash-outline',         couleur: '#f59e0b' },
  rh:            { label: 'RH',            icon: 'people-outline',       couleur: '#8b5cf6' },
  reassurance:   { label: 'Réassurance',   icon: 'shield-checkmark-outline', couleur: '#0ea5e9' },
  commercial:    { label: 'Commercial',    icon: 'trending-up-outline',  couleur: '#10b981' },
  fournisseurs:  { label: 'Fournisseurs',  icon: 'storefront-outline',   couleur: '#6366f1' },
}

// ─── Données démo ──────────────────────────────────────────────────────────────

const DOCS_DEMO: DocArchive[] = [
  { id: 'd1', nom: 'constat_amiable_SIN-342.pdf', type_document: 'Constat', module: 'sinistres', reference: 'SIN-2026-0342', date_upload: '2026-04-08 14:32', taille_ko: 245, uploade_par: 'Traore F.', tags: ['auto', 'B10'], statut_ocr: 'importe_orass', confiance_ocr: 0.94 },
  { id: 'd2', nom: 'facture_clinique_SIN-289.pdf', type_document: 'Facture', module: 'sinistres', reference: 'SIN-2026-0289', date_upload: '2026-04-07 09:15', taille_ko: 312, uploade_par: 'Clinique Sœurs', tags: ['vie', 'B80'], statut_ocr: 'extrait', confiance_ocr: 0.91 },
  { id: 'd3', nom: 'police_auto_COMT-1892.pdf', type_document: 'Contrat', module: 'souscription', reference: 'COMT-2026-1892', date_upload: '2026-04-05 11:20', taille_ko: 158, uploade_par: 'Bamba A.', tags: ['auto', 'police'], statut_ocr: 'importe_orass', confiance_ocr: 0.97 },
  { id: 'd4', nom: 'bulletin_paie_EMP001_mars.pdf', type_document: 'Bulletin de paie', module: 'rh', reference: 'EMP-001', date_upload: '2026-04-01 08:00', taille_ko: 89, uploade_par: "N'Goran MC.", tags: ['rh', 'paie'], statut_ocr: 'extrait', confiance_ocr: 0.99 },
  { id: 'd5', nom: 'traite_SCOR_2026.pdf', type_document: 'Traité réassurance', module: 'reassurance', reference: 'TRAITE-SCOR-2026', date_upload: '2026-01-15', taille_ko: 2840, uploade_par: 'Kouassi JB.', tags: ['réassurance', 'SCOR'], statut_ocr: 'importe_orass', confiance_ocr: 0.88 },
  { id: 'd6', nom: 'facture_garage_342.pdf', type_document: 'Facture', module: 'fournisseurs', reference: 'SIN-2026-0342', date_upload: '2026-04-09 16:45', taille_ko: 195, uploade_par: 'Garage YDE', tags: ['garage', 'fournisseur'], statut_ocr: 'en_cours' },
  { id: 'd7', nom: 'devis_expertise_301.pdf', type_document: 'Rapport', module: 'sinistres', reference: 'SIN-2026-0301', date_upload: '2026-04-06', taille_ko: 420, uploade_par: 'Expert SARL', tags: ['expertise'], statut_ocr: 'non_traite' },
  { id: 'd8', nom: 'cni_client_COMT-1950.jpg', type_document: 'CNI/Passeport', module: 'souscription', reference: 'COMT-2026-1950', date_upload: '2026-04-03', taille_ko: 520, uploade_par: 'Bamba A.', tags: ['cni'], statut_ocr: 'importe_orass', confiance_ocr: 0.96 },
]

// ─── Helpers ──────────────────────────────────────────────────────────────────

const ocrCfg = (s: StatutOcr) => ({
  non_traite:    { label: 'Non traité',    bg: '#f1f5f9', c: '#64748b' },
  en_cours:      { label: 'OCR…',          bg: '#eff6ff', c: '#3b82f6' },
  extrait:       { label: 'Extrait',       bg: '#eff6ff', c: '#1d4ed8' },
  importe_orass: { label: '✓ ORASS',       bg: '#f0fdf4', c: '#16a34a' },
}[s])

const fmt = (ko: number) => ko < 1000 ? `${ko} Ko` : `${(ko / 1024).toFixed(1)} Mo`

// ─── Carte document ────────────────────────────────────────────────────────────

function CarteDoc({ doc, onPress }: { doc: DocArchive; onPress: () => void }) {
  const mcfg = MODULES_CFG[doc.module]
  const ocr = ocrCfg(doc.statut_ocr)
  return (
    <TouchableOpacity style={s.docCard} onPress={onPress}>
      <View style={[s.docIcon, { backgroundColor: mcfg.couleur + '20' }]}>
        <Ionicons name={mcfg.icon as never} size={18} color={mcfg.couleur} />
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={s.docNom} numberOfLines={1}>{doc.nom}</Text>
        <View style={{ flexDirection: 'row', gap: 6, marginTop: 2, flexWrap: 'wrap' }}>
          <Text style={[s.moduleBadge, { backgroundColor: mcfg.couleur + '15', color: mcfg.couleur }]}>{mcfg.label}</Text>
          <Text style={s.docRef}>{doc.reference}</Text>
        </View>
        <Text style={s.docMeta}>{doc.date_upload} · {fmt(doc.taille_ko)} · {doc.uploade_par}</Text>
      </View>
      <View style={[s.ocrBadge, { backgroundColor: ocr.bg }]}>
        <Text style={[s.ocrText, { color: ocr.c }]}>{ocr.label}</Text>
      </View>
    </TouchableOpacity>
  )
}

// ─── Modal détail ─────────────────────────────────────────────────────────────

function ModalDetail({ doc, onClose }: { doc: DocArchive | null; onClose: () => void }) {
  if (!doc) return null
  const mcfg = MODULES_CFG[doc.module]
  const ocr = ocrCfg(doc.statut_ocr)
  return (
    <Modal visible animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <ScrollView style={{ flex: 1, backgroundColor: '#f8fafc' }}>
        <View style={s.modalHeader}>
          <View style={{ flex: 1 }}>
            <Text style={s.modalNom}>{doc.nom}</Text>
            <Text style={s.modalRef}>{doc.reference}</Text>
          </View>
          <TouchableOpacity onPress={onClose} style={s.closeBtn}>
            <Ionicons name="close" size={22} color="#64748b" />
          </TouchableOpacity>
        </View>
        <View style={{ padding: 16, gap: 12 }}>
          <View style={s.detailCard}>
            <Text style={s.detailTitle}>Informations</Text>
            {[
              ['Module', mcfg.label],
              ['Type', doc.type_document],
              ['Référence', doc.reference],
              ['Uploadé par', doc.uploade_par],
              ['Date', doc.date_upload],
              ['Taille', fmt(doc.taille_ko)],
            ].map(([k, v]) => (
              <View key={k} style={s.infoRow}>
                <Text style={s.infoKey}>{k}</Text>
                <Text style={s.infoVal}>{v}</Text>
              </View>
            ))}
          </View>
          {/* Tags */}
          <View style={s.detailCard}>
            <Text style={s.detailTitle}>Tags</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
              {doc.tags.map(t => (
                <View key={t} style={{ backgroundColor: '#f1f5f9', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 20 }}>
                  <Text style={{ fontSize: 11, color: '#64748b' }}>{t}</Text>
                </View>
              ))}
            </View>
          </View>
          {/* OCR */}
          <View style={[s.detailCard, { borderLeftWidth: 4, borderLeftColor: ocr.c }]}>
            <Text style={s.detailTitle}>Statut OCR</Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 6 }}>
              <View style={[s.ocrBadge, { backgroundColor: ocr.bg }]}>
                <Text style={[s.ocrText, { color: ocr.c }]}>{ocr.label}</Text>
              </View>
              {doc.confiance_ocr && (
                <Text style={{ fontSize: 13, color: '#374151' }}>Confiance {Math.round(doc.confiance_ocr * 100)}%</Text>
              )}
            </View>
          </View>
          {/* Actions */}
          <View style={{ gap: 10 }}>
            <TouchableOpacity style={[s.actionBtn, { backgroundColor: '#1d4ed8' }]}>
              <Ionicons name="download-outline" size={18} color="#fff" />
              <Text style={s.actionText}>Télécharger</Text>
            </TouchableOpacity>
            {doc.statut_ocr !== 'importe_orass' && (
              <TouchableOpacity style={[s.actionBtn, { backgroundColor: '#10b981' }]}>
                <Ionicons name="cloud-upload-outline" size={18} color="#fff" />
                <Text style={s.actionText}>Importer dans ORASS/Mercure</Text>
              </TouchableOpacity>
            )}
          </View>
        </View>
      </ScrollView>
    </Modal>
  )
}

// ─── Zone upload ───────────────────────────────────────────────────────────────

function ZoneUpload({ onAdd }: { onAdd: (d: DocArchive) => void }) {
  const [visible, setVisible] = useState(false)
  const [module, setModule] = useState<ModuleDoc>('sinistres')
  const [reference, setReference] = useState('')
  const [typeDoc, setTypeDoc] = useState('Facture')
  const [uploading, setUploading] = useState(false)

  const capturer = () => {
    const modules = Object.keys(MODULES_CFG).filter(k => k !== 'tous') as ModuleDoc[]
    if (!modules.includes(module)) return
    setVisible(true)
  }

  const prendrePhoto = async () => {
    const perm = await ImagePicker.requestCameraPermissionsAsync()
    if (perm.status !== 'granted') return
    const result = await ImagePicker.launchCameraAsync({ quality: 0.9, allowsEditing: true })
    if (!result.canceled && result.assets[0]) {
      setUploading(true)
      await new Promise(r => setTimeout(r, 1000))
      onAdd({
        id: Date.now().toString(),
        nom: `scan_${typeDoc.toLowerCase().replace(/\s/g, '_')}_${Date.now()}.jpg`,
        type_document: typeDoc,
        module,
        reference: reference || 'REF-' + Date.now(),
        date_upload: new Date().toLocaleString('fr-FR'),
        taille_ko: 280,
        uploade_par: 'Moi',
        tags: [module],
        statut_ocr: 'en_cours',
      })
      setUploading(false)
      setVisible(false)
    }
  }

  const MODULES_LIST = Object.entries(MODULES_CFG).filter(([k]) => k !== 'tous') as [ModuleDoc, typeof MODULES_CFG.sinistres][]

  return (
    <>
      <TouchableOpacity style={s.fabBtn} onPress={() => setVisible(true)}>
        <Ionicons name="add" size={26} color="#fff" />
      </TouchableOpacity>

      <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={() => setVisible(false)}>
        <ScrollView style={{ flex: 1, backgroundColor: '#f8fafc' }}>
          <View style={s.modalHeader}>
            <Text style={s.modalNom}>Ajouter un document</Text>
            <TouchableOpacity onPress={() => setVisible(false)} style={s.closeBtn}>
              <Ionicons name="close" size={22} color="#64748b" />
            </TouchableOpacity>
          </View>
          <View style={{ padding: 16, gap: 14 }}>
            <View>
              <Text style={s.fieldLabel}>Module</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: 6 }}>
                <View style={{ flexDirection: 'row', gap: 8, paddingRight: 8 }}>
                  {MODULES_LIST.map(([k, v]) => (
                    <TouchableOpacity key={k} onPress={() => setModule(k)}
                      style={[s.moduleChip, { backgroundColor: module === k ? v.couleur : '#f1f5f9' }]}>
                      <Ionicons name={v.icon as never} size={12} color={module === k ? '#fff' : '#64748b'} />
                      <Text style={{ fontSize: 11, fontWeight: '600', color: module === k ? '#fff' : '#475569' }}>{v.label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </ScrollView>
            </View>
            <View>
              <Text style={s.fieldLabel}>Référence (n° sinistre, police…)</Text>
              <TextInput style={s.input} placeholder="SIN-2026-XXXX" value={reference}
                onChangeText={setReference} autoCapitalize="characters" />
            </View>
            <View>
              <Text style={s.fieldLabel}>Type de document</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: 6 }}>
                <View style={{ flexDirection: 'row', gap: 8, paddingRight: 8 }}>
                  {['Facture', 'Contrat', 'Rapport', 'CNI/Passeport', 'Constat', 'Attestation', 'Autre'].map(t => (
                    <TouchableOpacity key={t} onPress={() => setTypeDoc(t)}
                      style={[s.typeChip, typeDoc === t && { backgroundColor: '#1d4ed8', borderColor: '#1d4ed8' }]}>
                      <Text style={[s.typeChipText, typeDoc === t && { color: '#fff' }]}>{t}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </ScrollView>
            </View>
            <TouchableOpacity style={s.scanMainBtn} onPress={prendrePhoto} disabled={uploading}>
              {uploading ? <ActivityIndicator color="#fff" /> : <Ionicons name="camera-outline" size={28} color="#fff" />}
              <Text style={s.scanMainText}>{uploading ? 'Upload OCR…' : 'Scanner avec la caméra'}</Text>
            </TouchableOpacity>
            <Text style={{ fontSize: 11, color: '#94a3b8', textAlign: 'center' }}>
              Le document sera automatiquement analysé par YukpoPro et indexé dans l'archive.
            </Text>
          </View>
        </ScrollView>
      </Modal>
    </>
  )
}

// ─── Écran principal ──────────────────────────────────────────────────────────

export default function ArchiveScreen() {
  const router = useRouter()
  const [docs, setDocs] = useState<DocArchive[]>(DOCS_DEMO)
  const [search, setSearch] = useState('')
  const [filtreModule, setFiltreModule] = useState<ModuleDoc | 'tous'>('tous')
  const [selected, setSelected] = useState<DocArchive | null>(null)

  const filtered = docs.filter(d => {
    const matchModule = filtreModule === 'tous' || d.module === filtreModule
    const q = search.toLowerCase()
    const matchSearch = !search || d.nom.toLowerCase().includes(q) || d.reference.toLowerCase().includes(q) || d.tags.join(' ').toLowerCase().includes(q)
    return matchModule && matchSearch
  })

  const stats = {
    total: docs.length,
    importe: docs.filter(d => d.statut_ocr === 'importe_orass').length,
    extrait: docs.filter(d => d.statut_ocr === 'extrait').length,
    enCours: docs.filter(d => d.statut_ocr === 'en_cours').length,
  }

  const addDoc = (d: DocArchive) => setDocs(prev => [d, ...prev])

  return (
    <View style={{ flex: 1, backgroundColor: '#f1f5f9' }}>
      {/* Header */}
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.backBtn}>
          <Ionicons name="arrow-back" size={20} color="#1e293b" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={s.headerTitle}>Archive numérique</Text>
          <Text style={s.headerSub}>{stats.total} docs · {stats.importe} dans ORASS</Text>
        </View>
      </View>

      {/* Stats */}
      <View style={s.statsRow}>
        {[
          { l: 'Total', v: stats.total, c: '#3b82f6' },
          { l: 'ORASS', v: stats.importe, c: '#10b981' },
          { l: 'Extraits', v: stats.extrait, c: '#1d4ed8' },
          { l: 'En cours', v: stats.enCours, c: '#f59e0b' },
        ].map((k, i) => (
          <View key={i} style={[s.statCard, { borderTopColor: k.c }]}>
            <Text style={[s.statVal, { color: k.c }]}>{k.v}</Text>
            <Text style={s.statLabel}>{k.l}</Text>
          </View>
        ))}
      </View>

      {/* Recherche */}
      <View style={s.searchRow}>
        <Ionicons name="search-outline" size={16} color="#94a3b8" style={{ position: 'absolute', left: 26, zIndex: 1 }} />
        <TextInput style={s.searchInput} placeholder="Rechercher par nom, référence, tag…"
          value={search} onChangeText={setSearch} />
      </View>

      {/* Filtres module */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.filtreBar}>
        <View style={{ flexDirection: 'row', gap: 8, padding: 10 }}>
          {(Object.entries(MODULES_CFG) as [ModuleDoc | 'tous', typeof MODULES_CFG.sinistres][]).map(([k, v]) => {
            const cnt = k === 'tous' ? docs.length : docs.filter(d => d.module === k).length
            return (
              <TouchableOpacity key={k}
                style={[s.filtreChip, filtreModule === k && { backgroundColor: v.couleur, borderColor: v.couleur }]}
                onPress={() => setFiltreModule(k)}>
                <Ionicons name={v.icon as never} size={11} color={filtreModule === k ? '#fff' : '#64748b'} />
                <Text style={[s.filtreText, filtreModule === k && { color: '#fff' }]}>{v.label} ({cnt})</Text>
              </TouchableOpacity>
            )
          })}
        </View>
      </ScrollView>

      {/* Liste */}
      <ScrollView contentContainerStyle={{ padding: 12, paddingBottom: 80, gap: 8 }}>
        {filtered.map(d => <CarteDoc key={d.id} doc={d} onPress={() => setSelected(d)} />)}
        {filtered.length === 0 && (
          <View style={{ alignItems: 'center', paddingVertical: 60 }}>
            <Ionicons name="folder-open-outline" size={48} color="#cbd5e1" />
            <Text style={{ color: '#94a3b8', marginTop: 10 }}>Aucun document trouvé</Text>
          </View>
        )}
      </ScrollView>

      {/* FAB upload */}
      <ZoneUpload onAdd={addDoc} />

      {/* Modal détail */}
      {selected && <ModalDetail doc={selected} onClose={() => setSelected(null)} />}
    </View>
  )
}

// ─── Styles ───────────────────────────────────────────────────────────────────
const s = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#fff', padding: 16, paddingTop: 20, borderBottomWidth: 1, borderBottomColor: '#e2e8f0' },
  backBtn: { padding: 6, borderRadius: 8, backgroundColor: '#f1f5f9' },
  headerTitle: { fontSize: 16, fontWeight: '700', color: '#1e293b' },
  headerSub: { fontSize: 11, color: '#64748b', marginTop: 1 },

  statsRow: { flexDirection: 'row', gap: 8, padding: 12, backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#e2e8f0' },
  statCard: { flex: 1, backgroundColor: '#f8fafc', borderRadius: 8, padding: 8, alignItems: 'center', borderTopWidth: 3 },
  statVal: { fontSize: 20, fontWeight: '800' },
  statLabel: { fontSize: 9, color: '#94a3b8', fontWeight: '600', marginTop: 2 },

  searchRow: { backgroundColor: '#fff', padding: 10, position: 'relative' },
  searchInput: { backgroundColor: '#f1f5f9', borderRadius: 10, paddingLeft: 36, paddingRight: 12, paddingVertical: 8, fontSize: 13, color: '#1e293b' },

  filtreBar: { backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#e2e8f0', maxHeight: 50 },
  filtreChip: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 20, backgroundColor: '#f1f5f9', borderWidth: 1, borderColor: '#e2e8f0' },
  filtreText: { fontSize: 11, fontWeight: '600', color: '#475569' },

  docCard: { backgroundColor: '#fff', borderRadius: 12, padding: 12, flexDirection: 'row', alignItems: 'flex-start', gap: 10, elevation: 1, shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.05, shadowRadius: 2 },
  docIcon: { width: 40, height: 40, borderRadius: 10, alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  docNom: { fontSize: 13, fontWeight: '600', color: '#1e293b' },
  moduleBadge: { fontSize: 10, fontWeight: '700', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  docRef: { fontSize: 10, fontFamily: 'monospace', color: '#3b82f6' },
  docMeta: { fontSize: 10, color: '#94a3b8', marginTop: 3 },
  ocrBadge: { paddingHorizontal: 6, paddingVertical: 3, borderRadius: 20, flexShrink: 0 },
  ocrText: { fontSize: 10, fontWeight: '700' },

  modalHeader: { flexDirection: 'row', alignItems: 'flex-start', padding: 16, borderBottomWidth: 1, borderBottomColor: '#e2e8f0', gap: 12, backgroundColor: '#fff' },
  modalNom: { fontSize: 16, fontWeight: '700', color: '#1e293b' },
  modalRef: { fontSize: 12, color: '#64748b', marginTop: 2 },
  closeBtn: { padding: 6, borderRadius: 8, backgroundColor: '#f1f5f9' },
  detailCard: { backgroundColor: '#fff', borderRadius: 12, padding: 14, elevation: 1 },
  detailTitle: { fontSize: 12, fontWeight: '700', color: '#374151', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 },
  infoRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 5, borderBottomWidth: 1, borderBottomColor: '#f1f5f9' },
  infoKey: { fontSize: 12, color: '#94a3b8', fontWeight: '600' },
  infoVal: { fontSize: 12, color: '#1e293b', fontWeight: '500', flex: 1, textAlign: 'right' },
  actionBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, padding: 14, borderRadius: 10 },
  actionText: { color: '#fff', fontSize: 14, fontWeight: '700' },

  fabBtn: { position: 'absolute', bottom: 20, right: 20, width: 54, height: 54, borderRadius: 27, backgroundColor: '#1d4ed8', alignItems: 'center', justifyContent: 'center', elevation: 6, shadowColor: '#1d4ed8', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.4, shadowRadius: 8 },

  fieldLabel: { fontSize: 12, fontWeight: '600', color: '#374151', marginBottom: 4 },
  input: { backgroundColor: '#fff', borderWidth: 1, borderColor: '#d1d5db', borderRadius: 8, padding: 10, fontSize: 13, color: '#1e293b' },
  moduleChip: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 20 },
  typeChip: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 20, backgroundColor: '#f1f5f9', borderWidth: 1, borderColor: '#e2e8f0' },
  typeChipText: { fontSize: 11, fontWeight: '600', color: '#475569' },
  scanMainBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 12, backgroundColor: '#1d4ed8', borderRadius: 14, padding: 18, elevation: 3, shadowColor: '#1d4ed8', shadowOffset: { width: 0, height: 3 }, shadowOpacity: 0.3, shadowRadius: 6 },
  scanMainText: { color: '#fff', fontSize: 16, fontWeight: '700' },
})
