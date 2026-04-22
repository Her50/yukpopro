/**
 * YukpoAssurance — Enquêtes & Études terrain
 * Module d'analyse qualitative IA : audio terrain → transcription → rapport
 */
import { useState, useRef, useEffect } from 'react'
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  TextInput, Modal, Alert, ActivityIndicator, Platform,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { useRouter } from 'expo-router'
import { apiClient } from '../src/api/client'

type Mode = 'qualitatif' | 'quantitatif' | 'mixte'
type Statut = 'brouillon' | 'transcription' | 'analyse' | 'rapport_pret'

interface Etude {
  etude_id: string
  titre: string
  contexte: string
  mode: Mode
  terrain: string
  statut: Statut
  n_transcriptions: number
  n_themes: number
  rapport_texte?: string
}

const STATUT_COLOR: Record<Statut, string> = {
  brouillon: '#94A3B8', transcription: '#F59E0B', analyse: '#6366F1', rapport_pret: '#22C55E',
}
const STATUT_LABEL: Record<Statut, string> = {
  brouillon: 'Brouillon', transcription: 'Audios collectés', analyse: 'Analysé', rapport_pret: 'Rapport prêt',
}

const fmtDur = (s: number) =>
  `${Math.floor(s / 60).toString().padStart(2, '0')}:${(s % 60).toString().padStart(2, '0')}`

let Audio: any = null
try { Audio = require('expo-av').Audio } catch (_) {}

export default function EnquetesPage() {
  const router = useRouter()
  const [etudes,    setEtudes]    = useState<Etude[]>([])
  const [loading,   setLoading]   = useState(false)
  const [showForm,  setShowForm]  = useState(false)
  const [active,    setActive]    = useState<Etude | null>(null)
  const [showRec,   setShowRec]   = useState(false)
  const [analysing, setAnalysing] = useState(false)

  // Formulaire
  const [titre,    setTitre]    = useState('')
  const [contexte, setContexte] = useState('')
  const [terrain,  setTerrain]  = useState('')
  const [mode,     setMode]     = useState<Mode>('qualitatif')
  const [saving,   setSaving]   = useState(false)

  // Enregistrement
  const recordingRef = useRef<any>(null)
  const timerRef     = useRef<ReturnType<typeof setInterval> | null>(null)
  const [recording,    setRecording]    = useState(false)
  const [paused,       setPaused]       = useState(false)
  const [dur,          setDur]          = useState(0)
  const [transcribing, setTranscribing] = useState(false)
  const [locuteur,     setLocuteur]     = useState('Répondant')

  useEffect(() => {
    charger()
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [])

  const charger = async () => {
    setLoading(true)
    try {
      const res = await apiClient.get('/enquetes/')
      setEtudes(res.data.etudes || [])
    } catch (_) {}
    setLoading(false)
  }

  const handleCreer = async () => {
    if (!titre.trim() || !contexte.trim()) {
      Alert.alert('Titre et contexte requis'); return
    }
    setSaving(true)
    try {
      await apiClient.post('/enquetes/', { titre, contexte, terrain, mode, questions_recherche: [], methodologie: 'exploratoire', population_cible: '' })
      await charger()
      setTitre(''); setContexte(''); setTerrain(''); setMode('qualitatif')
      setShowForm(false)
    } catch (e: any) {
      Alert.alert('Erreur', e?.response?.data?.detail || 'Création échouée')
    }
    setSaving(false)
  }

  const handleStart = async () => {
    if (!Audio) { Alert.alert('expo-av requis', 'npm install expo-av'); return }
    const { status } = await Audio.requestPermissionsAsync()
    if (status !== 'granted') { Alert.alert('Permission refusée'); return }
    await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true })
    const { recording: rec } = await Audio.Recording.createAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY)
    recordingRef.current = rec
    setRecording(true); setPaused(false); setDur(0)
    timerRef.current = setInterval(() => setDur(d => d + 1), 1000)
  }

  const handlePause = async () => {
    if (!recordingRef.current) return
    const st = await recordingRef.current.getStatusAsync()
    if (st.isRecording) {
      await recordingRef.current.pauseAsync(); setPaused(true)
      if (timerRef.current) clearInterval(timerRef.current)
    } else {
      await recordingRef.current.startAsync(); setPaused(false)
      timerRef.current = setInterval(() => setDur(d => d + 1), 1000)
    }
  }

  const handleStop = async () => {
    if (!recordingRef.current || !active) return
    if (timerRef.current) clearInterval(timerRef.current)
    setTranscribing(true)
    try {
      await recordingRef.current.stopAndUnloadAsync()
      const uri = recordingRef.current.getURI()
      recordingRef.current = null; setRecording(false); setPaused(false)
      if (!uri) throw new Error('URI introuvable')

      const form = new FormData()
      const ext = uri.split('.').pop() || 'm4a'
      const mime: Record<string, string> = { m4a: 'audio/mp4', mp3: 'audio/mpeg', wav: 'audio/wav' }
      // @ts-ignore
      form.append('audio', { uri, name: `terrain.${ext}`, type: mime[ext] ?? 'audio/mp4' })
      form.append('locuteur', locuteur)
      form.append('langue', 'fr')

      const res = await apiClient.post(`/enquetes/${active.etude_id}/audio`, form, {
        headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120_000,
      })
      const updated = { ...active, n_transcriptions: res.data.n_transcriptions_total, statut: 'transcription' as Statut }
      setActive(updated)
      setEtudes(prev => prev.map(e => e.etude_id === active.etude_id ? updated : e))
      Alert.alert('Transcrit !', `${res.data.longueur_totale} caractères\n\n${res.data.extrait}`)
    } catch (err: any) {
      Alert.alert('Erreur', err?.response?.data?.detail || err.message)
    }
    setTranscribing(false)
  }

  const handleAnalyser = async (etude: Etude) => {
    setAnalysing(true)
    try {
      const res = await apiClient.post(`/enquetes/${etude.etude_id}/analyser`)
      const updated = { ...etude, statut: 'analyse' as Statut, n_themes: res.data.n_themes }
      setEtudes(prev => prev.map(e => e.etude_id === etude.etude_id ? updated : e))
      Alert.alert('Analyse terminée', `${res.data.n_themes} thèmes identifiés`, [
        { text: 'Générer rapport', onPress: () => handleRapport(updated) },
        { text: 'OK' },
      ])
    } catch (err: any) {
      Alert.alert('Erreur', err?.response?.data?.detail)
    }
    setAnalysing(false)
  }

  const handleRapport = async (etude: Etude) => {
    setAnalysing(true)
    try {
      const res = await apiClient.post(`/enquetes/${etude.etude_id}/rapport`, null, { params: { format_rapport: 'json' }, timeout: 180_000 })
      const updated = { ...etude, statut: 'rapport_pret' as Statut, rapport_texte: res.data.rapport_texte, n_themes: res.data.n_themes }
      setEtudes(prev => prev.map(e => e.etude_id === etude.etude_id ? updated : e))
      setActive(updated)
      Alert.alert('Rapport prêt !', `${res.data.n_themes} thèmes · ${res.data.n_entretiens} entretiens`)
    } catch (err: any) {
      Alert.alert('Erreur', err?.response?.data?.detail)
    }
    setAnalysing(false)
  }

  return (
    <View style={st.container}>
      {/* Header */}
      <View style={st.header}>
        <TouchableOpacity onPress={() => router.back()} style={{ marginRight: 12 }}>
          <Ionicons name="arrow-back" size={22} color="#4f46e5" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={st.headerTitle}>Enquêtes & Études</Text>
          <Text style={st.headerSub}>Analyse qualitative / quantitative IA</Text>
        </View>
        <TouchableOpacity style={st.addBtn} onPress={() => setShowForm(true)}>
          <Ionicons name="add" size={20} color="#fff" />
        </TouchableOpacity>
      </View>

      {/* Liste */}
      <ScrollView style={st.flex} contentContainerStyle={st.content}>
        {loading && <ActivityIndicator color="#4f46e5" style={{ marginTop: 40 }} />}

        {!loading && etudes.length === 0 && (
          <View style={st.empty}>
            <Ionicons name="analytics-outline" size={48} color="#4f46e5" style={{ marginBottom: 16 }} />
            <Text style={st.emptyTitle}>Aucune étude</Text>
            <Text style={st.emptyText}>Créez une étude et enregistrez vos entretiens terrain</Text>
            <TouchableOpacity style={st.emptyBtn} onPress={() => setShowForm(true)}>
              <Text style={st.emptyBtnTxt}>+ Nouvelle étude</Text>
            </TouchableOpacity>
          </View>
        )}

        {etudes.map(e => (
          <View key={e.etude_id} style={st.card}>
            <View style={st.cardHead}>
              <Text style={st.cardTitle} numberOfLines={1}>{e.titre}</Text>
              <View style={[st.statutBadge, { backgroundColor: STATUT_COLOR[e.statut] + '22' }]}>
                <Text style={[st.statutTxt, { color: STATUT_COLOR[e.statut] }]}>{STATUT_LABEL[e.statut]}</Text>
              </View>
            </View>
            <Text style={st.cardCtx} numberOfLines={2}>{e.contexte}</Text>
            <Text style={st.cardMeta}>{e.mode} · {e.n_transcriptions} audio · {e.terrain}</Text>

            <View style={st.cardBtns}>
              <TouchableOpacity style={[st.btn, { backgroundColor: '#4f46e5' }]} onPress={() => { setActive(e); setShowRec(true) }}>
                <Ionicons name="mic-outline" size={13} color="#fff" />
                <Text style={st.btnTxt}>Enregistrer</Text>
              </TouchableOpacity>
              {e.n_transcriptions > 0 && e.statut !== 'rapport_pret' && (
                <TouchableOpacity style={[st.btn, { backgroundColor: '#7C3AED' }, analysing && st.disabled]} onPress={() => !analysing && handleAnalyser(e)} disabled={analysing}>
                  {analysing ? <ActivityIndicator size="small" color="#fff" /> : <Ionicons name="sparkles-outline" size={13} color="#fff" />}
                  <Text style={st.btnTxt}>Analyser</Text>
                </TouchableOpacity>
              )}
              {e.statut === 'analyse' && (
                <TouchableOpacity style={[st.btn, { backgroundColor: '#D97706' }, analysing && st.disabled]} onPress={() => !analysing && handleRapport(e)} disabled={analysing}>
                  <Ionicons name="reader-outline" size={13} color="#fff" />
                  <Text style={st.btnTxt}>Rapport</Text>
                </TouchableOpacity>
              )}
              {e.statut === 'rapport_pret' && (
                <TouchableOpacity style={[st.btn, { backgroundColor: '#16A34A' }]} onPress={() => { setActive(e); setShowRec(false) }}>
                  <Ionicons name="document-text-outline" size={13} color="#fff" />
                  <Text style={st.btnTxt}>Voir rapport</Text>
                </TouchableOpacity>
              )}
            </View>
          </View>
        ))}
      </ScrollView>

      {/* Modal Enregistrement */}
      <Modal visible={showRec && !!active} animationType="slide" presentationStyle="pageSheet">
        {active && (
          <View style={st.modal}>
            <View style={st.modalHead}>
              <Text style={st.modalTitle} numberOfLines={1}>{active.titre}</Text>
              <TouchableOpacity onPress={() => setShowRec(false)}>
                <Ionicons name="close" size={24} color="#1e293b" />
              </TouchableOpacity>
            </View>
            <ScrollView contentContainerStyle={st.modalBody} keyboardShouldPersistTaps="handled">
              <Text style={st.label}>Nom du répondant</Text>
              <TextInput style={st.input} value={locuteur} onChangeText={setLocuteur} placeholder="Répondant 1" />

              <Text style={st.label}>Enregistrement audio</Text>
              <View style={st.recBox}>
                {recording && (
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                    <View style={[st.recDot, paused && { backgroundColor: '#94A3B8' }]} />
                    <Text style={{ color: '#EF4444', fontWeight: '600' }}>
                      {paused ? 'Pause' : 'Enregistrement'} — {fmtDur(dur)}
                    </Text>
                  </View>
                )}
                {transcribing ? (
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <ActivityIndicator size="small" color="#4f46e5" />
                    <Text style={{ color: '#4f46e5' }}>Transcription en cours…</Text>
                  </View>
                ) : !recording ? (
                  <TouchableOpacity style={st.recBtn} onPress={handleStart}>
                    <Ionicons name="mic" size={18} color="#fff" />
                    <Text style={st.recBtnTxt}>Démarrer l'entretien</Text>
                  </TouchableOpacity>
                ) : (
                  <View style={{ flexDirection: 'row', gap: 8 }}>
                    <TouchableOpacity style={[st.recBtn, { backgroundColor: '#D97706', flex: 1 }]} onPress={handlePause}>
                      <Ionicons name={paused ? 'play' : 'pause'} size={16} color="#fff" />
                      <Text style={st.recBtnTxt}>{paused ? 'Reprendre' : 'Pause'}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={[st.recBtn, { backgroundColor: '#475569', flex: 2 }]} onPress={handleStop}>
                      <Ionicons name="stop" size={16} color="#fff" />
                      <Text style={st.recBtnTxt}>Arrêter & transcrire</Text>
                    </TouchableOpacity>
                  </View>
                )}
              </View>

              <Text style={{ color: '#64748b', fontSize: 12, marginTop: 8 }}>
                {active.n_transcriptions} entretien(s) enregistré(s) pour cette étude
              </Text>
            </ScrollView>
          </View>
        )}
      </Modal>

      {/* Modal Nouvelle étude */}
      <Modal visible={showForm} animationType="slide" presentationStyle="pageSheet">
        <View style={st.modal}>
          <View style={st.modalHead}>
            <Text style={st.modalTitle}>Nouvelle étude</Text>
            <TouchableOpacity onPress={() => setShowForm(false)}>
              <Ionicons name="close" size={24} color="#1e293b" />
            </TouchableOpacity>
          </View>
          <ScrollView contentContainerStyle={st.modalBody} keyboardShouldPersistTaps="handled">
            <Text style={st.label}>Titre *</Text>
            <TextInput style={st.input} value={titre} onChangeText={setTitre} placeholder="Perceptions des assurés sur…" />

            <Text style={st.label}>Contexte & Objectif *</Text>
            <TextInput style={[st.input, { minHeight: 80 }]} value={contexte} onChangeText={setContexte}
              placeholder="Décrivez l'objectif de l'étude…" multiline textAlignVertical="top" />

            <Text style={st.label}>Terrain</Text>
            <TextInput style={st.input} value={terrain} onChangeText={setTerrain} placeholder="Douala, Abidjan, Dakar…" />

            <Text style={st.label}>Mode</Text>
            {(['qualitatif', 'quantitatif', 'mixte'] as Mode[]).map(m => (
              <TouchableOpacity key={m} style={[st.modeChip, mode === m && st.modeChipActive]} onPress={() => setMode(m)}>
                <Text style={[st.modeChipTxt, mode === m && { color: '#4f46e5', fontWeight: '700' }]}>{m}</Text>
                {mode === m && <Ionicons name="checkmark" size={16} color="#4f46e5" />}
              </TouchableOpacity>
            ))}
          </ScrollView>
          <View style={st.modalFooter}>
            <TouchableOpacity style={[st.footBtn, { backgroundColor: '#f1f5f9' }]} onPress={() => setShowForm(false)}>
              <Text style={{ color: '#64748b', fontWeight: '600' }}>Annuler</Text>
            </TouchableOpacity>
            <TouchableOpacity style={[st.footBtn, { backgroundColor: '#4f46e5' }, saving && st.disabled]} onPress={handleCreer} disabled={saving}>
              {saving ? <ActivityIndicator size="small" color="#fff" /> : <Text style={{ color: '#fff', fontWeight: '700' }}>Créer</Text>}
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </View>
  )
}

const st = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8fafc' },
  flex:      { flex: 1 },
  header:    { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingTop: Platform.OS === 'ios' ? 56 : 16, paddingBottom: 14, backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#e2e8f0' },
  headerTitle:{ fontSize: 18, fontWeight: 'bold', color: '#1e293b' },
  headerSub: { fontSize: 11, color: '#94a3b8', marginTop: 1 },
  addBtn:    { width: 36, height: 36, borderRadius: 10, backgroundColor: '#4f46e5', alignItems: 'center', justifyContent: 'center' },
  content:   { padding: 16, paddingBottom: 40, gap: 12 },
  empty:     { alignItems: 'center', paddingVertical: 60 },
  emptyTitle:{ fontSize: 17, fontWeight: 'bold', color: '#1e293b', marginBottom: 8 },
  emptyText: { color: '#94a3b8', textAlign: 'center', marginBottom: 20 },
  emptyBtn:  { backgroundColor: '#4f46e5', paddingHorizontal: 20, paddingVertical: 12, borderRadius: 10 },
  emptyBtnTxt:{ color: '#fff', fontWeight: '600' },

  card:      { backgroundColor: '#fff', borderRadius: 14, padding: 14, shadowColor: '#000', shadowOpacity: 0.05, shadowRadius: 4, shadowOffset: { width: 0, height: 2 }, elevation: 2 },
  cardHead:  { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 6 },
  cardTitle: { flex: 1, fontSize: 15, fontWeight: '700', color: '#1e293b', marginRight: 8 },
  cardCtx:   { color: '#64748b', fontSize: 12, lineHeight: 18, marginBottom: 6 },
  cardMeta:  { color: '#94a3b8', fontSize: 11, marginBottom: 10 },
  cardBtns:  { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  statutBadge:{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
  statutTxt: { fontSize: 10, fontWeight: '700' },

  btn:       { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8 },
  btnTxt:    { color: '#fff', fontSize: 12, fontWeight: '600' },
  disabled:  { opacity: 0.5 },

  modal:     { flex: 1, backgroundColor: '#fff' },
  modalHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 20, paddingTop: Platform.OS === 'ios' ? 56 : 20, paddingBottom: 14, borderBottomWidth: 1, borderBottomColor: '#e2e8f0' },
  modalTitle:{ fontSize: 18, fontWeight: 'bold', color: '#1e293b', flex: 1 },
  modalBody: { padding: 20, gap: 4, paddingBottom: 32 },
  label:     { fontSize: 11, fontWeight: '600', color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6, marginTop: 12 },
  input:     { borderWidth: 1, borderColor: '#e2e8f0', borderRadius: 10, paddingHorizontal: 14, paddingVertical: 11, fontSize: 14, color: '#1e293b', backgroundColor: '#f8fafc' },

  recBox:    { backgroundColor: '#f8fafc', borderRadius: 12, padding: 12, borderWidth: 1, borderColor: '#e2e8f0' },
  recDot:    { width: 8, height: 8, borderRadius: 4, backgroundColor: '#EF4444' },
  recBtn:    { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: '#EF4444', paddingVertical: 12, borderRadius: 10 },
  recBtnTxt: { color: '#fff', fontWeight: '600', fontSize: 13 },

  modeChip:  { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderWidth: 1, borderColor: '#e2e8f0', borderRadius: 10, paddingHorizontal: 14, paddingVertical: 10, marginBottom: 6 },
  modeChipActive: { borderColor: '#4f46e5', backgroundColor: '#EEF2FF' },
  modeChipTxt: { color: '#64748b', fontSize: 14, textTransform: 'capitalize' },

  modalFooter:{ flexDirection: 'row', gap: 10, paddingHorizontal: 20, paddingBottom: Platform.OS === 'ios' ? 32 : 16, paddingTop: 12, borderTopWidth: 1, borderTopColor: '#e2e8f0' },
  footBtn:   { flex: 1, paddingVertical: 14, borderRadius: 12, alignItems: 'center' },
})
