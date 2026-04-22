import { useState, useRef } from 'react'
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet,
  ActivityIndicator, Alert, Share,
} from 'react-native'
import { Audio } from 'expo-av'
import * as DocumentPicker from 'expo-document-picker'
import { audioAPI } from '../../src/api/client'

const TYPES_DOC = [
  { cle: 'dictee', label: 'Texte dicté' },
  { cle: 'pv_reunion', label: 'PV de réunion' },
  { cle: 'compte_rendu', label: 'Compte rendu' },
  { cle: 'lettre', label: 'Lettre' },
  { cle: 'liste_taches', label: 'Liste de tâches' },
]

export default function AudioScreen() {
  const [recording, setRecording] = useState<Audio.Recording | null>(null)
  const [isRecording, setIsRecording] = useState(false)
  const [audioUri, setAudioUri] = useState<string | null>(null)
  const [typeDoc, setTypeDoc] = useState('dictee')
  const [pays, setPays] = useState('CM')
  const [loading, setLoading] = useState(false)
  const [resultat, setResultat] = useState<{ document_formate: string; type_document: string } | null>(null)

  const demarrerEnregistrement = async () => {
    try {
      const { status } = await Audio.requestPermissionsAsync()
      if (status !== 'granted') { Alert.alert('Permission refusée', 'Autorisez le microphone'); return }

      await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true })
      const rec = new Audio.Recording()
      await rec.prepareToRecordAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY)
      await rec.startAsync()
      setRecording(rec)
      setIsRecording(true)
    } catch (e) {
      Alert.alert('Erreur', 'Impossible de démarrer l\'enregistrement')
    }
  }

  const arreterEnregistrement = async () => {
    if (!recording) return
    try {
      await recording.stopAndUnloadAsync()
      const uri = recording.getURI()
      setAudioUri(uri)
      setRecording(null)
      setIsRecording(false)
    } catch (e) {
      Alert.alert('Erreur', 'Erreur lors de l\'arrêt')
    }
  }

  const importerFichier = async () => {
    const res = await DocumentPicker.getDocumentAsync({
      type: ['audio/*'],
    })
    if (!res.canceled && res.assets[0]) {
      setAudioUri(res.assets[0].uri)
    }
  }

  const transcrire = async () => {
    if (!audioUri) { Alert.alert('Erreur', 'Enregistrez ou importez un audio'); return }
    setLoading(true)
    try {
      const fd = new FormData()
      fd.append('fichier', {
        uri: audioUri,
        name: 'audio.m4a',
        type: 'audio/m4a',
      } as unknown as Blob)
      fd.append('type_document_cible', typeDoc)
      fd.append('pays', pays)

      const r = await audioAPI.transcrire(fd)
      setResultat(r.data)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      Alert.alert('Erreur', err.response?.data?.detail || 'Transcription échouée')
    } finally {
      setLoading(false)
    }
  }

  const partager = async () => {
    if (!resultat) return
    await Share.share({ message: resultat.document_formate, title: 'Transcription' })
  }

  return (
    <ScrollView style={s.container}>
      <View style={s.header}>
        <Text style={s.title}>🎤 Dicter → Document</Text>
        <Text style={s.subtitle}>Audio enregistré → Word professionnel</Text>
      </View>

      <View style={s.card}>
        {/* Enregistrement */}
        <View style={{ flexDirection: 'row', gap: 10, marginBottom: 16 }}>
          <TouchableOpacity
            style={[s.btn, { flex: 1, backgroundColor: isRecording ? '#dc2626' : '#7c3aed' }]}
            onPress={isRecording ? arreterEnregistrement : demarrerEnregistrement}
          >
            <Text style={s.btnText}>{isRecording ? '⏹ Arrêter' : '🔴 Dicter'}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[s.btn, { flex: 1, backgroundColor: '#374151' }]}
            onPress={importerFichier}
          >
            <Text style={s.btnText}>📂 Importer</Text>
          </TouchableOpacity>
        </View>

        {isRecording && (
          <Text style={{ color: '#dc2626', textAlign: 'center', fontWeight: '600', marginBottom: 12 }}>
            ● Enregistrement en cours…
          </Text>
        )}

        {audioUri && !isRecording && (
          <Text style={{ color: '#16a34a', textAlign: 'center', fontSize: 13, marginBottom: 12 }}>
            ✓ Audio prêt à transcrire
          </Text>
        )}

        {/* Type de document */}
        <Text style={s.label}>Type de document à produire</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 16 }}>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            {TYPES_DOC.map(t => (
              <TouchableOpacity
                key={t.cle}
                onPress={() => setTypeDoc(t.cle)}
                style={[s.chip, typeDoc === t.cle && s.chipActive]}
              >
                <Text style={[s.chipText, typeDoc === t.cle && s.chipTextActive]}>{t.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </ScrollView>

        {/* Pays */}
        <Text style={s.label}>Pays</Text>
        <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16 }}>
          {['CM', 'SN', 'CI', 'TG'].map(p => (
            <TouchableOpacity
              key={p}
              onPress={() => setPays(p)}
              style={[s.chip, pays === p && s.chipActive]}
            >
              <Text style={[s.chipText, pays === p && s.chipTextActive]}>{p}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <TouchableOpacity
          style={[s.btn, loading && s.btnDisabled]}
          onPress={transcrire}
          disabled={loading || !audioUri}
        >
          {loading ? <ActivityIndicator color="#fff" /> : <Text style={s.btnText}>✨ Transcrire et formater</Text>}
        </TouchableOpacity>
      </View>

      {resultat && (
        <View style={s.card}>
          <Text style={s.label}>{TYPES_DOC.find(t => t.cle === resultat.type_document)?.label ?? resultat.type_document}</Text>
          <Text style={s.markdown}>{resultat.document_formate}</Text>
          <TouchableOpacity style={[s.btn, { backgroundColor: '#16a34a', marginTop: 12 }]} onPress={partager}>
            <Text style={s.btnText}>📤 Partager le document</Text>
          </TouchableOpacity>
        </View>
      )}
    </ScrollView>
  )
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f9fafb' },
  header: { backgroundColor: '#7c3aed', paddingTop: 56, paddingBottom: 20, paddingHorizontal: 20 },
  title: { fontSize: 22, fontWeight: '700', color: '#fff' },
  subtitle: { fontSize: 13, color: '#ddd6fe', marginTop: 4 },
  card: { backgroundColor: '#fff', borderRadius: 20, padding: 18, margin: 16, shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 8, elevation: 3 },
  label: { fontSize: 13, fontWeight: '600', color: '#374151', marginBottom: 8 },
  chip: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 20, backgroundColor: '#f3f4f6', borderWidth: 1, borderColor: '#e5e7eb' },
  chipActive: { backgroundColor: '#7c3aed', borderColor: '#7c3aed' },
  chipText: { fontSize: 12, color: '#6b7280', fontWeight: '500' },
  chipTextActive: { color: '#fff' },
  btn: { backgroundColor: '#2563eb', borderRadius: 14, paddingVertical: 14, alignItems: 'center' },
  btnDisabled: { opacity: 0.6 },
  btnText: { color: '#fff', fontSize: 14, fontWeight: '600' },
  markdown: { fontSize: 13, color: '#374151', lineHeight: 20 },
})
