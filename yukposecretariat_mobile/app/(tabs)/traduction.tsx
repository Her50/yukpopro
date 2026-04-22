import { useState } from 'react'
import {
  View, Text, ScrollView, TextInput, TouchableOpacity,
  StyleSheet, ActivityIndicator, Alert,
} from 'react-native'
import { Picker } from '@react-native-picker/picker'
import { traductionAPI } from '../../src/api/client'

const LANGUES = [
  { code: 'fr', label: '🇫🇷 Français' }, { code: 'en', label: '🇬🇧 Anglais' },
  { code: 'es', label: '🇪🇸 Espagnol' }, { code: 'pt', label: '🇵🇹 Portugais' },
  { code: 'ar', label: '🇲🇦 Arabe' }, { code: 'wo', label: '🇸🇳 Wolof' },
  { code: 'ha', label: '🇳🇬 Haoussa' }, { code: 'sw', label: '🇹🇿 Swahili' },
]

const CONTEXTES = [
  { code: '', label: 'Général' },
  { code: 'juridique', label: 'Juridique OHADA' },
  { code: 'comptabilite', label: 'Comptabilité SYSCOHADA' },
  { code: 'assurance', label: 'Assurance CIMA' },
  { code: 'rh', label: 'Ressources humaines' },
  { code: 'commercial', label: 'Commercial' },
  { code: 'medical', label: 'Médical' },
]

export default function TraductionScreen() {
  const [langSource, setLangSource] = useState('fr')
  const [langCible, setLangCible] = useState('en')
  const [contexte, setContexte] = useState('')
  const [contenu, setContenu] = useState('')
  const [loading, setLoading] = useState(false)
  const [resultat, setResultat] = useState<{
    texte_traduit: string; nb_mots_source: number; nb_mots_cible: number
  } | null>(null)

  const traduire = async () => {
    if (!contenu.trim()) { Alert.alert('Erreur', 'Saisissez un texte à traduire'); return }
    if (langSource === langCible) { Alert.alert('Erreur', 'La langue source et cible doivent être différentes'); return }
    setLoading(true)
    try {
      const r = await traductionAPI.traduireTexte({
        contenu, langue_source: langSource, langue_cible: langCible, contexte_metier: contexte,
      })
      setResultat(r.data)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      Alert.alert('Erreur', err.response?.data?.detail || 'Erreur de traduction')
    } finally {
      setLoading(false)
    }
  }

  return (
    <ScrollView style={s.container} keyboardShouldPersistTaps="handled">
      <View style={s.header}>
        <Text style={s.title}>🌐 Traduction IA</Text>
        <Text style={s.subtitle}>Terminologie africaine francophone intégrée</Text>
      </View>

      <View style={s.card}>
        <Text style={s.label}>Langue source</Text>
        <View style={s.pickerWrap}>
          <Picker selectedValue={langSource} onValueChange={v => setLangSource(v)} style={s.picker}>
            {LANGUES.map(l => <Picker.Item key={l.code} label={l.label} value={l.code} />)}
          </Picker>
        </View>

        <Text style={s.label}>Langue cible</Text>
        <View style={s.pickerWrap}>
          <Picker selectedValue={langCible} onValueChange={v => setLangCible(v)} style={s.picker}>
            {LANGUES.map(l => <Picker.Item key={l.code} label={l.label} value={l.code} />)}
          </Picker>
        </View>

        <Text style={s.label}>Contexte métier</Text>
        <View style={s.pickerWrap}>
          <Picker selectedValue={contexte} onValueChange={v => setContexte(v)} style={s.picker}>
            {CONTEXTES.map(c => <Picker.Item key={c.code} label={c.label} value={c.code} />)}
          </Picker>
        </View>

        <Text style={s.label}>Texte à traduire</Text>
        <TextInput
          style={s.textarea}
          value={contenu}
          onChangeText={setContenu}
          multiline
          numberOfLines={6}
          placeholder="Collez votre texte ici…"
          placeholderTextColor="#9ca3af"
          textAlignVertical="top"
        />
        <Text style={{ fontSize: 11, color: '#9ca3af', marginBottom: 16 }}>
          {contenu.split(/\s+/).filter(Boolean).length} mots
        </Text>

        <TouchableOpacity style={[s.btn, loading && s.btnDisabled]} onPress={traduire} disabled={loading}>
          {loading ? <ActivityIndicator color="#fff" /> : <Text style={s.btnText}>🌐 Traduire</Text>}
        </TouchableOpacity>
      </View>

      {resultat && (
        <View style={s.card}>
          <Text style={s.label}>Traduction</Text>
          <Text style={{ fontSize: 11, color: '#9ca3af', marginBottom: 12 }}>
            {resultat.nb_mots_source} mots → {resultat.nb_mots_cible} mots
          </Text>
          <View style={s.resultBox}>
            <Text style={s.resultText}>{resultat.texte_traduit}</Text>
          </View>
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
  card: { backgroundColor: '#fff', borderRadius: 20, padding: 18, margin: 16, shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 8, elevation: 3 },
  label: { fontSize: 13, fontWeight: '600', color: '#374151', marginBottom: 8 },
  pickerWrap: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 12, marginBottom: 16, overflow: 'hidden' },
  picker: { height: 48 },
  textarea: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, fontSize: 13, color: '#111827', minHeight: 130, marginBottom: 8 },
  btn: { backgroundColor: '#ea580c', borderRadius: 14, paddingVertical: 14, alignItems: 'center' },
  btnDisabled: { opacity: 0.6 },
  btnText: { color: '#fff', fontSize: 14, fontWeight: '600' },
  resultBox: { backgroundColor: '#f9fafb', borderRadius: 12, padding: 14 },
  resultText: { fontSize: 13, color: '#111827', lineHeight: 20 },
})
