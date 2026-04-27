import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ScrollView, Alert, ActivityIndicator,
} from 'react-native'
import { useState } from 'react'
import * as DocumentPicker from 'expo-document-picker'
import * as ImagePicker from 'expo-image-picker'
import * as FileSystem from 'expo-file-system'
import { Ionicons } from '@expo/vector-icons'
import { api } from '../src/api/client'

type Onglet = 'upload' | 'csv' | 'image' | 'correspondances'

const TYPES_PIECE = ['facture', 'recu', 'releve_bancaire', 'quittance', 'bordereau', 'autre']

export default function ComptabiliteScreen() {
  const [onglet, setOnglet] = useState<Onglet>('upload')

  // Upload pièce
  const [typePiece, setTypePiece] = useState('facture')
  const [idRef, setIdRef] = useState('')
  const [fichierNom, setFichierNom] = useState('')
  const [fichierUri, setFichierUri] = useState('')
  const [resultatUpload, setResultatUpload] = useState<any>(null)
  const [loadingUpload, setLoadingUpload] = useState(false)

  // CSV
  const [csvTexte, setCsvTexte] = useState('')
  const [resultatCsv, setResultatCsv] = useState<any>(null)
  const [loadingCsv, setLoadingCsv] = useState(false)

  // Image
  const [imageB64, setImageB64] = useState('')
  const [imageNom, setImageNom] = useState('')
  const [resultatImage, setResultatImage] = useState<any>(null)
  const [loadingImage, setLoadingImage] = useState(false)

  const choisirFichier = async () => {
    const res = await DocumentPicker.getDocumentAsync({ type: ['application/pdf', 'image/*'] })
    if (!res.canceled && res.assets?.[0]) {
      setFichierNom(res.assets[0].name)
      setFichierUri(res.assets[0].uri)
    }
  }

  const traiterUpload = async () => {
    if (!fichierUri) return Alert.alert('Requis', 'Choisissez un fichier')
    setLoadingUpload(true)
    try {
      const fd = new FormData()
      fd.append('type_piece', typePiece)
      fd.append('fichier', { uri: fichierUri, name: fichierNom, type: 'application/octet-stream' } as any)
      if (idRef.trim()) fd.append('id_reference', idRef.trim())
      const r = await api.post('/comptabilite/piece/traiter-upload', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setResultatUpload(r.data)
    } catch (e: any) {
      Alert.alert('Erreur', e?.response?.data?.detail ?? 'Erreur traitement')
    } finally {
      setLoadingUpload(false)
    }
  }

  const traiterCsv = async () => {
    if (!csvTexte.trim()) return Alert.alert('Requis', 'Entrez le contenu CSV')
    setLoadingCsv(true)
    try {
      const r = await api.post('/comptabilite/rapprochement/csv', { contenu_csv: csvTexte })
      setResultatCsv(r.data)
    } catch (e: any) {
      Alert.alert('Erreur', e?.response?.data?.detail ?? 'Erreur CSV')
    } finally {
      setLoadingCsv(false)
    }
  }

  const choisirImage = async () => {
    const res = await ImagePicker.launchImageLibraryAsync({ base64: true, quality: 0.8 })
    if (!res.canceled && res.assets?.[0]) {
      setImageB64(res.assets[0].base64 ?? '')
      setImageNom(res.assets[0].fileName ?? 'image.jpg')
    }
  }

  const traiterImage = async () => {
    if (!imageB64) return Alert.alert('Requis', 'Choisissez une image')
    setLoadingImage(true)
    try {
      const r = await api.post('/comptabilite/rapprochement/image', { image_b64: imageB64 })
      setResultatImage(r.data)
    } catch (e: any) {
      Alert.alert('Erreur', e?.response?.data?.detail ?? 'Erreur image')
    } finally {
      setLoadingImage(false)
    }
  }

  return (
    <ScrollView style={styles.container}>
      {/* Onglets */}
      <View style={styles.tabs}>
        {([
          { key: 'upload', label: 'Pièce OCR' },
          { key: 'csv',    label: 'CSV' },
          { key: 'image',  label: 'Image' },
          { key: 'correspondances', label: 'Lettres' },
        ] as const).map(({ key, label }) => (
          <TouchableOpacity key={key} style={[styles.tab, onglet === key && styles.tabActive]}
            onPress={() => setOnglet(key)}>
            <Text style={[styles.tabText, onglet === key && styles.tabTextActive]}>{label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* ── Upload OCR ── */}
      {onglet === 'upload' && (
        <View style={styles.section}>
          <Text style={styles.label}>Type de pièce</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 12 }}>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              {TYPES_PIECE.map((t) => (
                <TouchableOpacity key={t} style={[styles.chip, typePiece === t && styles.chipActive]}
                  onPress={() => setTypePiece(t)}>
                  <Text style={[styles.chipText, typePiece === t && styles.chipTextActive]}>
                    {t.replace(/_/g, ' ').toUpperCase()}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </ScrollView>

          <Text style={styles.label}>ID de référence (optionnel)</Text>
          <TextInput style={styles.input} placeholder="SIN-2024-001"
            value={idRef} onChangeText={setIdRef} />

          <TouchableOpacity style={styles.uploadBox} onPress={choisirFichier}>
            <Text style={styles.uploadIcon}>📎</Text>
            <Text style={styles.uploadText}>{fichierNom || 'Choisir un fichier (PDF, image)'}</Text>
          </TouchableOpacity>

          <TouchableOpacity style={styles.btn} onPress={traiterUpload} disabled={loadingUpload}>
            {loadingUpload
              ? <ActivityIndicator color="#fff" size="small" />
              : <Text style={styles.btnText}>Traiter avec Yukpo</Text>}
          </TouchableOpacity>

          {resultatUpload && <ResultatBlock data={resultatUpload} />}
        </View>
      )}

      {/* ── CSV ── */}
      {onglet === 'csv' && (
        <View style={styles.section}>
          <Text style={styles.label}>Contenu CSV du relevé bancaire</Text>
          <TextInput
            style={[styles.input, { height: 160, textAlignVertical: 'top', fontFamily: 'monospace', fontSize: 11 }]}
            multiline
            placeholder={'date,libelle,montant,sens\n2024-01-15,PRIME AUTO,150000,credit'}
            value={csvTexte}
            onChangeText={setCsvTexte}
          />
          <TouchableOpacity style={styles.btn} onPress={traiterCsv} disabled={loadingCsv}>
            {loadingCsv
              ? <ActivityIndicator color="#fff" size="small" />
              : <Text style={styles.btnText}>Analyser le rapprochement</Text>}
          </TouchableOpacity>
          {resultatCsv && <ResultatBlock data={resultatCsv} />}
        </View>
      )}

      {/* ── Image ── */}
      {onglet === 'image' && (
        <View style={styles.section}>
          <TouchableOpacity style={styles.uploadBox} onPress={choisirImage}>
            <Text style={styles.uploadIcon}>🖼️</Text>
            <Text style={styles.uploadText}>{imageNom || 'Choisir un relevé scanné (image)'}</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.btn} onPress={traiterImage} disabled={loadingImage}>
            {loadingImage
              ? <ActivityIndicator color="#fff" size="small" />
              : <Text style={styles.btnText}>Analyser l'image</Text>}
          </TouchableOpacity>
          {resultatImage && <ResultatBlock data={resultatImage} />}
        </View>
      )}

      {/* ── Correspondances ── */}
      {onglet === 'correspondances' && (
        <OngletCorrespondancesCompta />
      )}
    </ScrollView>
  )
}

// ── Correspondances comptabilité ──────────────────────────────────────────────

const TEMPLATES_COMPTA = [
  { id: 'relance_paiement', label: 'Relance paiement', icon: 'cash-outline' },
  { id: 'quittance_prime', label: 'Quittance de prime', icon: 'receipt-outline' },
  { id: 'mise_en_demeure', label: 'Mise en demeure', icon: 'warning-outline' },
  { id: 'etat_compte', label: 'État de compte', icon: 'document-text-outline' },
  { id: 'notification_virement', label: 'Notification virement', icon: 'swap-horizontal-outline' },
  { id: 'recu_paiement', label: 'Reçu de paiement', icon: 'checkmark-circle-outline' },
]

function OngletCorrespondancesCompta() {
  const [templateChoisi, setTemplateChoisi] = useState<string | null>(null)
  const [reference, setReference] = useState('')
  const [contexte, setContexte] = useState('')
  const [lettre, setLettre] = useState('')
  const [loading, setLoading] = useState(false)

  const generer = () => {
    if (!templateChoisi) return
    setLoading(true)
    const today = new Date().toLocaleDateString('fr-FR', { year: 'numeric', month: 'long', day: 'numeric' })
    const template = TEMPLATES_COMPTA.find(t => t.id === templateChoisi)
    setTimeout(() => {
      setLettre(
        `Douala, le ${today}\n\nObjet : ${template?.label}${reference ? ` — Réf. ${reference}` : ''}\n\n` +
        `Monsieur/Madame,\n\nNous vous contactons au sujet de votre compte${reference ? ` N° ${reference}` : ''}.` +
        `\n\n${contexte || 'Veuillez trouver ci-joint les informations relatives à votre dossier.'}\n\n` +
        `Nous restons à votre disposition pour tout renseignement complémentaire.\n\nCordialement,\nLe Service Comptabilité`
      )
      setLoading(false)
    }, 800)
  }

  return (
    <View style={styles.section}>
      <Text style={styles.label}>Modèle de lettre</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        {TEMPLATES_COMPTA.map(t => (
          <TouchableOpacity key={t.id} onPress={() => setTemplateChoisi(t.id)}
            style={[styles.chip, templateChoisi === t.id && styles.chipActive, { flexDirection: 'row', gap: 4, alignItems: 'center' }]}>
            <Ionicons name={t.icon as any} size={12} color={templateChoisi === t.id ? '#fff' : '#6b7280'} />
            <Text style={[styles.chipText, templateChoisi === t.id && styles.chipTextActive]}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {templateChoisi && (
        <>
          <Text style={styles.label}>Référence (police, client…)</Text>
          <TextInput style={styles.input} placeholder="POL-2026-001" value={reference} onChangeText={setReference} />

          <Text style={styles.label}>Contexte / montant</Text>
          <TextInput
            style={[styles.input, { minHeight: 60, textAlignVertical: 'top' }]}
            placeholder="Montant, motif, délai…"
            value={contexte}
            onChangeText={setContexte}
            multiline
          />

          <TouchableOpacity style={[styles.btn, loading && { opacity: 0.6 }]} onPress={generer} disabled={loading}>
            {loading ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.btnText}>Générer avec YukpoPro</Text>}
          </TouchableOpacity>
        </>
      )}

      {lettre !== '' && (
        <View style={[styles.card, { borderColor: '#c4b5fd' }]}>
          <Text style={[styles.cardTitle, { color: '#5b21b6' }]}>Lettre générée</Text>
          <TextInput
            style={{ fontSize: 12, color: '#1f2937', lineHeight: 18, fontFamily: 'monospace', minHeight: 160, textAlignVertical: 'top' }}
            value={lettre}
            onChangeText={setLettre}
            multiline
          />
          <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
            <TouchableOpacity style={[styles.btn, { flex: 1, flexDirection: 'row', gap: 6, justifyContent: 'center', alignItems: 'center' }]}
              onPress={() => Alert.alert('Envoi', 'La lettre sera envoyée par email.')}>
              <Ionicons name="send-outline" size={14} color="#fff" />
              <Text style={styles.btnText}>Envoyer</Text>
            </TouchableOpacity>
            <TouchableOpacity style={[styles.btn, { flex: 1, backgroundColor: '#f3f4f6', flexDirection: 'row', gap: 6, justifyContent: 'center', alignItems: 'center' }]}
              onPress={() => Alert.alert('Export', 'Export PDF disponible sur web.')}>
              <Ionicons name="download-outline" size={14} color="#374151" />
              <Text style={[styles.btnText, { color: '#374151' }]}>Exporter</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}
    </View>
  )
}

function ResultatBlock({ data }: { data: any }) {
  const hasAnomalies = data?.anomalies?.length > 0
  return (
    <View style={[styles.card, { borderColor: hasAnomalies ? '#fde68a' : '#bbf7d0' }]}>
      <Text style={[styles.cardTitle, { color: hasAnomalies ? '#92400e' : '#065f46' }]}>
        {hasAnomalies ? '⚠ Anomalies détectées' : '✓ Traitement réussi'}
      </Text>
      {data.resume && <Text style={styles.cardText}>{data.resume}</Text>}
      {data.analyse && <Text style={styles.cardText}>{data.analyse}</Text>}
      {data.anomalies?.map((a: string, i: number) => (
        <Text key={i} style={styles.anomalie}>• {a}</Text>
      ))}
      {data.donnees_extraites && Object.entries(data.donnees_extraites)
        .filter(([, v]) => v !== null && v !== '')
        .map(([k, v]) => (
          <View key={k} style={styles.row}>
            <Text style={styles.rowLabel}>{k.replace(/_/g, ' ')}</Text>
            <Text style={styles.rowValue}>{String(v)}</Text>
          </View>
        ))}
    </View>
  )
}

const styles = StyleSheet.create({
  container:       { flex: 1, backgroundColor: '#f9fafb' },
  tabs:            { flexDirection: 'row', backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#e5e7eb' },
  tab:             { flex: 1, paddingVertical: 13, alignItems: 'center' },
  tabActive:       { borderBottomWidth: 2, borderBottomColor: '#7c3aed' },
  tabText:         { fontSize: 13, color: '#9ca3af', fontWeight: '600' },
  tabTextActive:   { color: '#7c3aed' },
  section:         { padding: 16, gap: 10 },
  label:           { fontSize: 12, color: '#6b7280', fontWeight: '600', marginBottom: 2 },
  input:           { backgroundColor: '#fff', borderRadius: 10, paddingHorizontal: 14, paddingVertical: 12, fontSize: 13, color: '#111827', borderWidth: 1, borderColor: '#e5e7eb' },
  uploadBox:       { backgroundColor: '#fff', borderRadius: 10, borderWidth: 1.5, borderColor: '#e5e7eb', borderStyle: 'dashed', paddingVertical: 20, alignItems: 'center', gap: 6 },
  uploadIcon:      { fontSize: 28 },
  uploadText:      { fontSize: 13, color: '#6b7280' },
  btn:             { backgroundColor: '#7c3aed', borderRadius: 10, paddingVertical: 13, alignItems: 'center', marginTop: 4 },
  btnText:         { color: '#fff', fontWeight: '700', fontSize: 14 },
  chip:            { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: '#f3f4f6' },
  chipActive:      { backgroundColor: '#7c3aed' },
  chipText:        { fontSize: 10, color: '#6b7280', fontWeight: '700' },
  chipTextActive:  { color: '#fff' },
  card:            { backgroundColor: '#fff', borderRadius: 12, padding: 14, borderWidth: 1.5, marginTop: 8 },
  cardTitle:       { fontSize: 13, fontWeight: '700', marginBottom: 8 },
  cardText:        { fontSize: 13, color: '#374151', lineHeight: 20, marginBottom: 6 },
  anomalie:        { fontSize: 12, color: '#92400e', marginBottom: 4 },
  row:             { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 3 },
  rowLabel:        { fontSize: 11, color: '#9ca3af', flex: 1, textTransform: 'capitalize' },
  rowValue:        { fontSize: 12, color: '#111827', fontWeight: '600', flex: 1, textAlign: 'right' },
})
